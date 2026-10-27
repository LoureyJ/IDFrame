"""Supervised, resumable MODNet fine-tuning on public P3M image/alpha pairs."""

import argparse
import hashlib
import json
import math
from pathlib import Path
import random
import time

import torch
import torch.nn.functional as F

from adapt_modnet import MODNet, export_onnx
from p3m_dataset import P3MDataset

ROOT = Path(__file__).resolve().parents[1]


def supervised_loss(outputs, image, alpha):
    """Supervise semantic, boundary detail, and compositing using real soft alpha labels."""
    semantic, detail, matte = outputs
    coarse = F.interpolate(
        alpha, size=semantic.shape[-2:], mode="bilinear", align_corners=False
    )
    coarse = F.avg_pool2d(F.pad(coarse, (1, 1, 1, 1), mode="replicate"), 3, stride=1)
    dilation = F.max_pool2d(alpha, 7, stride=1, padding=3)
    erosion = -F.max_pool2d(-alpha, 7, stride=1, padding=3)
    boundary = (dilation - erosion > 0.01).float()
    detail_error = (detail - alpha).abs() * boundary
    detail_loss = detail_error.sum() / boundary.sum().clamp_min(1)
    weight = 1 + 4 * boundary
    matte_loss = ((matte - alpha).abs() * weight).mean()
    rgb = (image + 1) / 2
    composition = ((rgb * matte - rgb * alpha).abs() * weight).mean()
    return (
        10 * F.mse_loss(semantic, coarse) + 10 * detail_loss + matte_loss + composition
    )


def evaluate(model, dataset, indices):
    """Measure equal-weight per-image alpha errors on a strictly held-out selection."""
    model.eval()
    values = []
    with torch.inference_mode():
        for index in sorted(indices):
            image, alpha = dataset[index]
            prediction = model(image[None], True)[2][0]
            error = prediction - alpha
            boundary = (
                F.max_pool2d(alpha[None], 7, 1, 3)[0]
                + F.max_pool2d(-alpha[None], 7, 1, 3)[0]
                > 0.01
            )
            interior = alpha > 0.98
            values.append(
                {
                    "mae": float(error.abs().mean()),
                    "mse": float(error.square().mean()),
                    "boundary_mae": (
                        float(error[boundary].abs().mean()) if boundary.any() else 0.0
                    ),
                    "interior_deficit": (
                        float((1 - prediction[interior]).mean())
                        if interior.any()
                        else 0.0
                    ),
                }
            )
    return {
        key: sum(value[key] for value in values) / len(values) for key in values[0]
    } | {"images": len(values), "max_side": dataset.max_side}


def save_checkpoint(path, model, optimizer, epoch, position, report):
    """Atomically retain model, optimizer, exact cursor, RNG, and dataset/run metadata."""
    temporary = path.with_suffix(".tmp")
    torch.save(
        {
            "model": model.state_dict(),
            "optimizer": optimizer.state_dict(),
            "epoch": epoch,
            "position": position,
            "torch_rng": torch.get_rng_state(),
            "report": report,
        },
        temporary,
    )
    temporary.replace(path)


def restore_checkpoint(path, model, optimizer, expected, keys, *, epochs):
    """Restore an exact training cursor after validating dataset and optimizer inputs."""
    saved = torch.load(path, map_location="cpu", weights_only=True)
    for key in keys:
        if saved["report"][key] != expected[key]:
            raise ValueError("Resume configuration differs: " + key)
    if epochs < saved["epoch"]:
        raise ValueError("Requested epochs precede the saved training cursor")
    model.load_state_dict(saved["model"])
    optimizer.load_state_dict(saved["optimizer"])
    torch.set_rng_state(saved["torch_rng"])
    report = saved["report"]
    report["epochs_requested"] = epochs
    report["training_complete"] = False
    return saved["epoch"], saved["position"], report


def verify_data(root):
    """Require every pinned shard's published length and SHA-256 before training."""
    provenance = json.loads((root / "provenance.json").read_text())
    for entry in provenance["files"]:
        path = root / entry["path"]
        if not path.is_file() or path.stat().st_size != entry["size"]:
            raise ValueError("Missing or incomplete shard: " + entry["path"])
        with path.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != entry["lfs"]["oid"]:
                raise ValueError("Dataset hash mismatch")
    return provenance


def main():
    """Train a reproducible candidate; never replace the deployed ONNX model automatically."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=ROOT / "build/datasets/p3m10k")
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=ROOT / "training/checkpoints/modnet_photographic_portrait_matting.ckpt",
    )
    parser.add_argument("--output", type=Path, default=ROOT / "build/p3m-review")
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--max-side", type=int, default=384)
    parser.add_argument("--validation-size", type=int, default=400)
    parser.add_argument("--lr", type=float, default=1e-5)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument(
        "--max-steps",
        type=int,
        help="Explicit smoke-run cap, never counted as full training",
    )
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    if (
        args.epochs < 1
        or args.validation_size < 1
        or not math.isfinite(args.lr)
        or args.lr <= 0
        or args.max_side < 64
        or args.threads < 1
        or (args.max_steps is not None and args.max_steps < 1)
    ):
        parser.error(
            "Epochs, validation size, threads, step cap and learning rate must be positive; max-side must be at least 64"
        )
    checkpoint = args.output / "resume.pt"
    if args.resume and not checkpoint.is_file():
        parser.error("Resume checkpoint is missing")
    if not args.resume and (
        checkpoint.exists() or (args.output / "report.json").exists()
    ):
        parser.error("Output already contains a run; use --resume or a new directory")
    torch.manual_seed(args.seed)
    torch.set_num_threads(max(1, args.threads))
    torch.set_num_interop_threads(1)
    provenance = verify_data(args.data)
    dataset = P3MDataset(args.data / "data", "train", args.max_side)
    if len(dataset) != 9421:
        raise ValueError("Expected exactly 9421 training-split rows")
    if args.validation_size >= len(dataset):
        raise ValueError("Validation selection must leave training rows")
    validation = set(
        random.Random(args.seed).sample(range(len(dataset)), args.validation_size)
    )
    args.output.mkdir(parents=True, exist_ok=True)
    report = {
        "method": "supervised MODNet fine-tuning with real P3M alpha mattes",
        "dataset_mirror": provenance["mirror"],
        "dataset_revision": provenance["revision"],
        "source_training_rows": len(dataset),
        "training_rows": len(dataset) - len(validation),
        "selection_validation_rows": len(validation),
        "validation_indices": sorted(validation),
        "official_tests_used_for_training": False,
        "seed": args.seed,
        "learning_rate": args.lr,
        "epochs_requested": args.epochs,
        "max_side": args.max_side,
        "device": "cpu",
        "threads": args.threads,
        "checkpoint_sha256": hashlib.sha256(args.checkpoint.read_bytes()).hexdigest(),
        "smoke_step_cap": args.max_steps,
        "history": [],
        "training_complete": False,
    }
    model = MODNet(backbone_pretrained=False)
    state = torch.load(args.checkpoint, map_location="cpu", weights_only=True)
    model.load_state_dict(
        {name.removeprefix("module."): value for name, value in state.items()}
    )
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr, betas=(0.9, 0.99))
    cursor_epoch = cursor_position = step = 0
    if args.resume:
        keys = (
            "dataset_revision",
            "seed",
            "max_side",
            "learning_rate",
            "validation_indices",
            "checkpoint_sha256",
            "smoke_step_cap",
        )
        cursor_epoch, cursor_position, report = restore_checkpoint(
            checkpoint, model, optimizer, report, keys, epochs=args.epochs
        )
        step = report.get("steps", 0)
    print(
        json.dumps(
            {
                "event": "start",
                "rows": len(dataset),
                "train": report["training_rows"],
                "validation": len(validation),
                "device": "cpu",
                "resume_step": step,
            }
        ),
        flush=True,
    )
    if "baseline_selection" not in report:
        # A bounded smoke check does not pretend to evaluate the complete validation set.
        selection = (
            sorted(validation)[: min(len(validation), 16)]
            if args.max_steps
            else sorted(validation)
        )
        report["baseline_selection"] = evaluate(model, dataset, selection)
        (args.output / "report.json").write_text(json.dumps(report, indent=2))
    start = time.perf_counter()
    try:
        for epoch in range(cursor_epoch, args.epochs):
            order = dataset.epoch_order(validation, args.seed + epoch)
            first = cursor_position if epoch == cursor_epoch else 0
            for position in range(first, len(order)):
                index = order[position]
                image, alpha = dataset.sample(
                    index, args.seed + epoch * len(dataset) + index
                )
                model.train()
                model.freeze_norm()
                optimizer.zero_grad(set_to_none=True)
                loss = supervised_loss(
                    model(image[None], False), image[None], alpha[None]
                )
                if not torch.isfinite(loss):
                    raise ValueError("Non-finite training loss")
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                optimizer.step()
                step += 1
                report["steps"] = step
                if step % 20 == 0 or step == 1:
                    entry = {
                        "epoch": epoch + 1,
                        "step": step,
                        "epoch_position": position + 1,
                        "loss": float(loss.detach()),
                        "elapsed_this_session_seconds": round(
                            time.perf_counter() - start, 2
                        ),
                    }
                    print(json.dumps(entry), flush=True)
                    report["history"].append(entry)
                    (args.output / "report.json").write_text(
                        json.dumps(report, indent=2)
                    )
                if step % 250 == 0 or (args.max_steps and step >= args.max_steps):
                    save_checkpoint(
                        checkpoint, model, optimizer, epoch, position + 1, report
                    )
                if args.max_steps and step >= args.max_steps:
                    report["smoke_seconds_per_step"] = (
                        time.perf_counter() - start
                    ) / max(1, step)
                    report["estimated_seconds_per_full_epoch"] = report[
                        "smoke_seconds_per_step"
                    ] * len(order)
                    report["candidate_selection"] = evaluate(
                        model, dataset, sorted(validation)[:16]
                    )
                    torch.save(model.state_dict(), args.output / "smoke-model.pt")
                    print(
                        json.dumps(
                            {
                                "event": "smoke_complete",
                                "seconds_per_step": report["smoke_seconds_per_step"],
                                "estimated_epoch_hours": report[
                                    "estimated_seconds_per_full_epoch"
                                ]
                                / 3600,
                            }
                        ),
                        flush=True,
                    )
                    return
            metrics = evaluate(model, dataset, sorted(validation))
            report["candidate_selection"] = metrics
            report["epochs_completed"] = epoch + 1
            torch.save(model.state_dict(), args.output / f"epoch-{epoch + 1}.pt")
            save_checkpoint(checkpoint, model, optimizer, epoch + 1, 0, report)
            print(
                json.dumps(
                    {
                        "event": "epoch_complete",
                        "epoch": epoch + 1,
                        "validation": metrics,
                    }
                ),
                flush=True,
            )
        report["training_complete"] = True
        export_onnx(model.eval(), args.output / "candidate.onnx")
        report["candidate_sha256"] = hashlib.sha256(
            (args.output / "candidate.onnx").read_bytes()
        ).hexdigest()
        report["activation"] = (
            "not activated; awaiting held-out official evaluation, client comparison and visual review"
        )
    finally:
        (args.output / "report.json").write_text(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
