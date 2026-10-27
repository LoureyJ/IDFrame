"""Evaluate actual ONNX portrait inference on untouched public P3M test splits."""

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np
from PIL import Image, ImageFilter, ImageOps

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from portrait import PortraitRemover
from p3m_dataset import P3MDataset


def alpha_metrics(prediction, target):
    """Measure opacity errors, boundary error, and missing solid foreground per image."""
    if prediction.shape != target.shape or not np.isfinite(prediction).all():
        raise ValueError("Invalid predicted alpha")
    error = prediction - target
    mask = Image.fromarray(np.uint8(np.clip(target, 0, 1) * 255))
    dilation = np.asarray(mask.filter(ImageFilter.MaxFilter(7)), dtype=np.float32)
    erosion = np.asarray(mask.filter(ImageFilter.MinFilter(7)), dtype=np.float32)
    boundary = dilation - erosion > 2
    interior = target > 0.98
    return {
        "mae": float(np.abs(error).mean()),
        "mse": float(np.square(error).mean()),
        "boundary_mae": (
            float(np.abs(error[boundary]).mean()) if boundary.any() else 0.0
        ),
        "interior_deficit": (
            float((1 - prediction[interior]).mean()) if interior.any() else 0.0
        ),
    }


def cached_prediction(remover, rgb, size, path):
    """Cache only successful inference; failed rows are retried and stay visible on resume."""
    if path.exists():
        with Image.open(path) as image:
            return image.convert("L"), None
    failure_path = path.with_suffix(".failure.json")
    try:
        prediction = (
            remover.remove(rgb).getchannel("A").resize(size, Image.Resampling.LANCZOS)
        )
    except (ValueError, RuntimeError) as error:
        failure_path.write_text(json.dumps({"error": str(error)}))
        return Image.new("L", size), str(error)
    prediction.save(path)
    failure_path.unlink(missing_ok=True)
    return prediction, None


def prepare_cache(output, identity):
    """Bind a prediction directory to immutable model, dataset and preprocessing inputs."""
    output.mkdir(parents=True, exist_ok=True)
    owner = output / "cache-identity.json"
    if owner.exists():
        if json.loads(owner.read_text()) != identity:
            raise ValueError(
                "Evaluation cache belongs to different model, data or preprocessing"
            )
        return
    if any(output.iterdir()):
        raise ValueError(
            "Existing evaluation files have no cache identity; use a new output directory"
        )
    temporary = output / "cache-identity.tmp"
    temporary.write_text(json.dumps(identity, indent=2))
    temporary.replace(owner)


def main():
    """Save per-image metrics and masks without altering deployed weights or training data."""
    import onnxruntime as ort

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=ROOT / "build/datasets/p3m10k")
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--limit", type=int, help="Explicit diagnostic subset per split"
    )
    parser.add_argument("--threads", type=int, default=1)
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("Limit must be positive")
    model_sha = hashlib.sha256(args.model.read_bytes()).hexdigest()
    provenance = json.loads((args.data / "provenance.json").read_text())
    prepare_cache(
        args.output,
        {
            "model_sha256": model_sha,
            "dataset_revision": provenance["revision"],
            "dataset_provenance_sha256": hashlib.sha256(
                (args.data / "provenance.json").read_bytes()
            ).hexdigest(),
            "preprocessing_sha256": hashlib.sha256(
                (ROOT / "portrait.py").read_bytes()
            ).hexdigest(),
            "model_type": "matting",
            "max_metric_side": 768,
        },
    )
    report_path = args.output / "evaluation.json"
    if (
        report_path.exists()
        and json.loads(report_path.read_text())["model_sha256"] != model_sha
    ):
        raise ValueError("Output directory already belongs to a different model")
    options = ort.SessionOptions()
    options.intra_op_num_threads = max(1, args.threads)
    options.inter_op_num_threads = 1
    remover = PortraitRemover(model_path=args.model, model_type="matting")
    remover._session = ort.InferenceSession(
        str(args.model), sess_options=options, providers=["CPUExecutionProvider"]
    )
    report = {
        "model_sha256": model_sha,
        "dataset_revision": provenance["revision"],
        "onnxruntime": ort.__version__,
        "max_metric_side": 768,
        "input": "actual client PortraitRemover preprocessing and alpha conversion",
        "aggregation": "equal-weight per-image mean; custom boundary band, not official benchmark scores",
        "limit_per_split": args.limit,
        "complete": False,
        "failures": [],
        "splits": {},
        "rows": [],
    }
    started = time.monotonic()
    try:
        for split in ("P3M_500_P", "P3M_500_NP"):
            dataset = P3MDataset(args.data / "data", split)
            if len(dataset) != 500:
                raise ValueError("Expected 500 rows in " + split)
            count = min(len(dataset), args.limit or len(dataset))
            folder = args.output / split
            folder.mkdir(exist_ok=True)
            values = []
            for index in range(count):
                rgb, target = dataset.pair(index)
                target = ImageOps.contain(target, (768, 768), Image.Resampling.LANCZOS)
                cached = folder / f"{index:04d}.png"
                prediction, failure = cached_prediction(
                    remover, rgb, target.size, cached
                )
                if failure is not None:
                    report["failures"].append(
                        {"split": split, "index": index, "error": failure}
                    )
                if prediction.size != target.size:
                    raise ValueError("Cached prediction geometry differs")
                metrics = alpha_metrics(
                    np.asarray(prediction, dtype=np.float32) / 255,
                    np.asarray(target, dtype=np.float32) / 255,
                )
                values.append(metrics)
                report["rows"].append({"split": split, "index": index} | metrics)
                if (index + 1) % 50 == 0:
                    print(
                        json.dumps(
                            {
                                "split": split,
                                "images": index + 1,
                                "elapsed_seconds": round(time.monotonic() - started, 1),
                            }
                        ),
                        flush=True,
                    )
                    report_path.write_text(json.dumps(report, indent=2))
            report["splits"][split] = {
                key: sum(value[key] for value in values) / len(values)
                for key in values[0]
            } | {"images": len(values)}
        report["complete"] = args.limit is None
        print(
            json.dumps(
                {
                    "complete": report["complete"],
                    "splits": report["splits"],
                    "failures": len(report["failures"]),
                }
            ),
            flush=True,
        )
    finally:
        report["elapsed_seconds"] = round(time.monotonic() - started, 1)
        report_path.write_text(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
