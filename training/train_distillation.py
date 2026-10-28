"""Fine-tune the accepted fast MODNet using reviewed cached teacher masks and real P3M alpha."""

import argparse
import hashlib
import json
from pathlib import Path
import random
import time

import numpy as np
from PIL import Image
import torch

from adapt_modnet import MODNet, export_onnx, load_training_photo
from distillation import distillation_loss, validate_split
from p3m_dataset import P3MDataset, prepare_pair
from train_p3m import evaluate, restore_checkpoint, save_checkpoint, verify_data

ROOT = Path(__file__).resolve().parents[1]


def fingerprint(path):
    """Hash local inputs without retaining their full bytes in memory."""
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def load_manifest(path):
    """Verify reviewed source/mask identities and keep held-out photos out of training."""
    manifest = json.loads(path.read_text())
    if any(row["role"] not in {"train", "holdout"} for row in manifest["rows"]):
        raise ValueError("Every reviewed photo needs an explicit train or holdout role")
    training = [row for row in manifest["rows"] if row["role"] == "train"]
    held = [row for row in manifest["rows"] if row["role"] == "holdout"]
    if not training or not held:
        raise ValueError(
            "Reviewed teacher training and held-out photos are both required"
        )
    validate_split(training, held)
    for row in manifest["rows"]:
        if (
            fingerprint(Path(manifest["photo_root"]) / row["sample"])
            != row["source_sha256"]
        ):
            raise ValueError("Source photo changed since mask review")
        if fingerprint(row["teacher_mask"]) != row["teacher_mask_sha256"]:
            raise ValueError("Teacher mask changed since review")
        if (
            row["role"] == "train"
            and fingerprint(row["target"]) != row["target_sha256"]
        ):
            raise ValueError("Reviewed target changed since manifest creation")
    return manifest, training, held


def teacher_pair(manifest, row, *, corrected):
    """Align a reviewed source and soft mask to the actual 768px student geometry."""
    image = load_training_photo(Path(manifest["photo_root"]) / row["sample"])
    with Image.open(row["target"] if corrected else row["teacher_mask"]) as mask:
        return prepare_pair(image, mask.convert("L"), max_side=768)


def evaluate_local(model, selection):
    """Measure agreement with reviewed held-out teacher masks, not ground-truth alpha accuracy."""
    values = []
    model.eval()
    with torch.inference_mode():
        for image, alpha in selection:
            prediction = model(image[None], True)[2][0]
            values.append(float((prediction - alpha).abs().mean()))
    return {
        "teacher_alpha_mae": sum(values) / len(values),
        "images": len(values),
        "max_side": 768,
    }


def main():
    """Run reproducible decoder distillation and export diagnostic weights without activating them."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--data", type=Path, default=ROOT / "build/datasets/p3m10k")
    parser.add_argument("--epochs", type=int, default=4)
    parser.add_argument("--lr", type=float, default=0.000002)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    if args.epochs < 1 or not np.isfinite(args.lr) or args.lr <= 0:
        parser.error("Epochs and learning rate must be positive")
    if not args.resume and (args.output / "report.json").exists():
        parser.error(
            "Output already contains a run; choose a new directory or --resume"
        )
    torch.manual_seed(91)
    torch.set_num_threads(4)
    torch.set_num_interop_threads(1)
    manifest, training, held = load_manifest(args.manifest)
    if (
        fingerprint(ROOT / "models/portrait_hair.onnx")
        != manifest["active_model_sha256"]
    ):
        raise ValueError("Active model changed; review the starting checkpoint again")
    if (
        fingerprint(args.checkpoint)
        != "12ac97b675eb0397d20276df169c79c190da131c3389933abc23d469a367b567"
    ):
        raise ValueError(
            "This reviewed run must start from the accepted student checkpoint"
        )
    provenance = verify_data(args.data)
    dataset = P3MDataset(args.data / "data", "train", 512)
    if len(dataset) != 9421:
        raise ValueError("Expected 9421 public training-split images")
    validation = sorted(random.Random(73).sample(range(len(dataset)), 64))
    available = [index for index in range(len(dataset)) if index not in set(validation)]
    public_indices = sorted(random.Random(91).sample(available, 128))
    args.output.mkdir(parents=True, exist_ok=True)
    report = {
        "method": "Reviewed BiRefNet soft-mask distillation into accepted MODNet decoder",
        "manifest_sha256": fingerprint(args.manifest),
        "checkpoint_sha256": fingerprint(args.checkpoint),
        "active_model_sha256": manifest["active_model_sha256"],
        "dataset_revision": provenance["revision"],
        "teacher_model_sha256": manifest["teacher_model_sha256"],
        "public_indices": public_indices,
        "validation_indices": validation,
        "official_tests_used_for_training": False,
        "local_training_photos": len(training),
        "local_held_out_photos": len(held),
        "public_max_side": 512,
        "local_max_side": 768,
        "teacher_repeats_per_epoch": 2,
        "epochs_requested": args.epochs,
        "learning_rate": args.lr,
        "seed": 91,
        "history": [],
        "training_complete": False,
        "activation": "Not activated",
        "client_speed_target_seconds": [1, 5],
        "limitations": "Reviewed teacher pseudo-labels and coarse interior corrections are not precise ground truth. Photo/hash split is checked; subject-disjointness is not verified. This is 128 public pairs, not a full P3M epoch.",
    }
    model = MODNet(backbone_pretrained=False)
    model.load_state_dict(
        torch.load(args.checkpoint, map_location="cpu", weights_only=True)
    )
    model.backbone.requires_grad_(False)
    frozen = {key: value.clone() for key, value in model.backbone.state_dict().items()}
    report["trainable_parameters"] = sum(
        value.numel() for value in model.parameters() if value.requires_grad
    )
    report["total_parameters"] = sum(value.numel() for value in model.parameters())
    optimizer = torch.optim.Adam(
        [value for value in model.parameters() if value.requires_grad],
        lr=args.lr,
        betas=(0.9, 0.99),
    )
    start_epoch = start_position = 0
    if args.resume:
        keys = (
            "manifest_sha256",
            "checkpoint_sha256",
            "dataset_revision",
            "public_indices",
            "validation_indices",
            "learning_rate",
            "public_max_side",
            "local_max_side",
            "teacher_repeats_per_epoch",
        )
        start_epoch, start_position, report = restore_checkpoint(
            args.output / "resume.pt",
            model,
            optimizer,
            report,
            keys,
            epochs=args.epochs,
        )
    # Only three reviewed good teacher examples are used for held-out local selection.
    local_selection = [
        teacher_pair(manifest, row, corrected=False)
        for row in held
        if row["index"] in {0, 1, 2}
    ]
    if len(local_selection) != 3:
        raise ValueError(
            "The main three held-out examples must remain outside training"
        )
    if "baseline_public" not in report:
        print("Measuring held-out public and local baselines.", flush=True)
        report["baseline_public"] = evaluate(model, dataset, validation)
        report["baseline_local"] = evaluate_local(model, local_selection)
    print("Preparing 128 public pairs and reviewed local soft masks.", flush=True)
    public_pairs = {
        index: dataset.sample(index, 91 + index) for index in public_indices
    }
    local_pairs = [teacher_pair(manifest, row, corrected=True) for row in training]
    print(
        json.dumps(
            {
                "event": "ready",
                "trainable": report["trainable_parameters"],
                "total": report["total_parameters"],
                "public_pairs": len(public_pairs),
                "local_pairs": len(local_pairs),
                "baseline_public": report["baseline_public"],
                "baseline_local": report["baseline_local"],
            }
        ),
        flush=True,
    )
    captured = {}

    def capture_logits(module, inputs, result):
        """Capture the existing matte logits for stable gradients without changing architecture."""
        captured["logits"] = result

    hook = model.f_branch.conv_f.register_forward_hook(capture_logits)
    steps = report.get("steps", 0)
    started = time.monotonic()
    try:
        for epoch in range(start_epoch, args.epochs):
            order = [("public", index) for index in public_indices]
            order += [("teacher", index) for index in range(len(local_pairs))] * 2
            random.Random(91 + epoch).shuffle(order)
            first = start_position if epoch == start_epoch else 0
            for position in range(first, len(order)):
                kind, index = order[position]
                image, alpha = (
                    public_pairs[index] if kind == "public" else local_pairs[index]
                )
                rng = random.Random(91 + epoch * len(order) + position)
                if rng.random() < 0.5:
                    image, alpha = torch.flip(image, (-1,)), torch.flip(alpha, (-1,))
                image = ((image + 1) * rng.uniform(0.95, 1.05) - 1).clamp(-1, 1)
                model.train()
                # Freeze running statistics; decoder affine weights still learn.
                model.freeze_norm()
                optimizer.zero_grad(set_to_none=True)
                outputs = model(image[None], False)
                logits = captured.pop("logits")
                if not torch.allclose(logits.sigmoid(), outputs[2]):
                    raise ValueError("Captured logits do not match the matte output")
                loss = distillation_loss(outputs, image[None], alpha[None], logits)
                if not torch.isfinite(loss):
                    raise ValueError("Non-finite distillation loss")
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                optimizer.step()
                steps += 1
                report["steps"] = steps
                if steps == 1 or steps % 16 == 0:
                    entry = {
                        "epoch": epoch + 1,
                        "step": steps,
                        "kind": kind,
                        "loss": float(loss.detach()),
                        "seconds_this_session": round(time.monotonic() - started, 1),
                    }
                    report["history"].append(entry)
                    print(json.dumps(entry), flush=True)
                    (args.output / "report.json").write_text(
                        json.dumps(report, indent=2)
                    )
                if steps % 32 == 0:
                    save_checkpoint(
                        args.output / "resume.pt",
                        model,
                        optimizer,
                        epoch,
                        position + 1,
                        report,
                    )
            metrics = {
                "epoch": epoch + 1,
                "public": evaluate(model, dataset, validation),
                "local": evaluate_local(model, local_selection),
            }
            report.setdefault("selections", []).append(metrics)
            torch.save(model.state_dict(), args.output / f"epoch-{epoch+1}.pt")
            save_checkpoint(
                args.output / "resume.pt", model, optimizer, epoch + 1, 0, report
            )
            print(json.dumps({"event": "epoch_complete", **metrics}), flush=True)
            (args.output / "report.json").write_text(json.dumps(report, indent=2))
        if not all(
            torch.equal(value, frozen[key])
            for key, value in model.backbone.state_dict().items()
        ):
            raise ValueError("Frozen backbone unexpectedly changed")
        hook.remove()
        report["frozen_backbone_unchanged"] = True
        report["training_complete"] = True
        export_onnx(model.eval(), args.output / "final.onnx")
        report["final_onnx_sha256"] = fingerprint(args.output / "final.onnx")
        report["activation"] = (
            "Awaiting selection, client quality checks and 1–5 second speed gate"
        )
    finally:
        hook.remove()
        (args.output / "report.json").write_text(json.dumps(report, indent=2))
    print(
        json.dumps(
            {
                "event": "training_complete",
                "steps": steps,
                "final_onnx_sha256": report["final_onnx_sha256"],
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
