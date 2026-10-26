"""Local MODNet adaptation using SOC or optional coarse scribble supervision.

No alpha accuracy is claimed: training uses sub-objective consistency or weak
interior labels, not ground-truth alpha error. Visually review weights before use.
Reference: https://github.com/ZHKKKe/MODNet/blob/master/src/trainer.py
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import random
import sys
import time

import numpy as np
import PIL
from PIL import Image, ImageDraw, ImageOps
import torch
import torch.nn.functional as F

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "training" / "vendor" / "MODNet"))
from src.models.modnet import MODNet


def tensor_from_photo(path, max_side=512, flip=False):
    with Image.open(path) as image:
        image = ImageOps.exif_transpose(image).convert("RGB")
        scale = max_side / max(image.size)
        size = tuple(max(64, round(side * scale / 32) * 32) for side in image.size)
        image = image.resize(size, Image.Resampling.LANCZOS)
        if flip:
            image = ImageOps.mirror(image)
        pixels = np.asarray(image, dtype=np.float32) / 127.5 - 1
    return torch.from_numpy(pixels.transpose(2, 0, 1).copy()).unsqueeze(0)


def blur(value):
    kernel = torch.tensor([[1., 2., 1.], [2., 4., 2.], [1., 2., 1.]], device=value.device) / 16
    return F.conv2d(F.pad(value, (1, 1, 1, 1), mode="reflect"), kernel[None, None])


def soc_step(model, teacher, optimizer, image):
    model.train()
    model.freeze_norm()
    optimizer.zero_grad(set_to_none=True)
    semantic, detail, matte = model(image, False)
    with torch.no_grad():
        _, teacher_detail, teacher_matte = teacher(image, False)
        foreground = (matte > .1).float() * F.interpolate((semantic > .1).float(), size=matte.shape[-2:], mode="bilinear", align_corners=False)
        side = max(3, int(sum(matte.shape[-2:]) / 2 * .05) | 1)
        dilated = F.max_pool2d(foreground, side, stride=1, padding=side // 2)
        eroded = -F.max_pool2d(-foreground, side, stride=1, padding=side // 2)
        boundary = (dilated != eroded).float()
    downsampled = blur(F.interpolate(matte, size=semantic.shape[-2:], mode="bilinear", align_corners=False))
    pseudo_semantic = downsampled.detach() * (downsampled.detach() > .01)
    pseudo_matte = semantic.detach() * (semantic.detach() > .01)
    semantic_loss = 100 * (F.mse_loss(semantic, pseudo_semantic) + F.mse_loss(downsampled, pseudo_matte))
    denominator = boundary.sum().clamp_min(1)
    detail_loss = ((detail - teacher_detail).abs() * boundary).sum() / denominator
    matte_loss = ((matte - teacher_matte).abs() * boundary).sum() / denominator
    loss = semantic_loss + detail_loss + matte_loss
    if not torch.isfinite(loss):
        raise ValueError("Training produced a non-finite loss")
    loss.backward()
    torch.nn.utils.clip_grad_norm_(model.parameters(), 1.)
    optimizer.step()
    return {"loss": float(loss.detach()), "semantic": float(semantic_loss.detach()),
            "detail": float(detail_loss.detach()), "matte": float(matte_loss.detach())}


def guidance_mask(size, entry, flip=False):
    """255=foreground, 0=background, 128=unknown; never label fine edges."""
    width, height = size
    mask = Image.new("L", size, 128)
    draw = ImageDraw.Draw(mask)
    for key, value in [("background", 0), ("foreground", 255)]:
        for x, y, radius in entry[key]:
            x, y, radius = x * width / 100, y * height / 100, radius * min(size) / 100
            draw.ellipse((x-radius, y-radius, x+radius, y+radius), fill=value)
    if flip:
        mask = ImageOps.mirror(mask)
    return torch.from_numpy(np.asarray(mask).copy())[None, None]


def balanced_scribble_loss(prediction, labels):
    labels = F.interpolate(labels.float(), size=prediction.shape[-2:], mode="nearest")
    terms = []
    for value in (0, 255):
        known = labels == value
        if known.any():
            target = torch.full_like(prediction[known], value / 255)
            terms.append(F.binary_cross_entropy(prediction[known].clamp(1e-7, 1-1e-7), target))
    return torch.stack(terms).mean()


def guided_step(model, teacher, optimizer, image, labels=None):
    model.train()
    model.freeze_norm()
    optimizer.zero_grad(set_to_none=True)
    semantic, detail, matte = model(image, False)
    with torch.no_grad():
        old_semantic, old_detail, old_matte = teacher(image, False)
    if labels is None:
        # Replay the accepted model's full soft mattes on the curl examples.
        loss = 5 * F.mse_loss(semantic, old_semantic) + F.mse_loss(detail, old_detail) + 3 * F.mse_loss(matte, old_matte)
    else:
        supervised = (balanced_scribble_loss(semantic, labels) +
                      .5 * balanced_scribble_loss(detail, labels) +
                      balanced_scribble_loss(matte, labels))
        unknown = labels == 128
        anchor = ((matte - old_matte).square() * unknown).sum() / unknown.sum().clamp_min(1)
        loss = supervised + .05 * anchor
    if not torch.isfinite(loss):
        raise ValueError("Guided training produced a non-finite loss")
    loss.backward()
    torch.nn.utils.clip_grad_norm_(model.parameters(), 1.)
    optimizer.step()
    return {"loss": float(loss.detach())}


class MatteOnly(torch.nn.Module):
    def __init__(self, model):
        super().__init__()
        self.model = model

    def forward(self, image):
        return self.model(image, True)[2]


def export_onnx(model, path):
    model.eval()
    wrapper = MatteOnly(model)
    torch.onnx.export(wrapper, torch.zeros((1, 3, 512, 512)), str(path), dynamo=False,
                      opset_version=17, input_names=["input"], output_names=["alpha"],
                      dynamic_axes={"input": {2: "height", 3: "width"}, "alpha": {2: "height", 3: "width"}})


def discover_photos(root, recursive=True):
    """Include nested challenge sets and AVIF photos without basename collisions."""
    return sorted(path for path in (root.rglob("*") if recursive else root.iterdir()) if path.is_file()
                  and path.suffix.lower() in {".jpg", ".jpeg", ".png", ".avif", ".webp"})


def preview_path(photo, root, destination):
    # Keep both the relative directory and original extension: image.jpg and
    # image.png, including those in different folders, must have separate outputs.
    relative = photo.relative_to(root)
    return destination / relative.parent / (relative.name + ".png")


def previews(model, photos, destination, photo_root):
    destination.mkdir(parents=True, exist_ok=True)
    model.eval()
    with torch.inference_mode():
        for photo in photos:
            alpha = model(tensor_from_photo(photo, max_side=768), True)[2][0, 0].numpy()
            with Image.open(photo) as source:
                source = ImageOps.exif_transpose(source).convert("RGBA")
                mask = Image.fromarray(np.uint8(np.clip(alpha, 0, 1) * 255)).resize(source.size, Image.Resampling.LANCZOS)
                source.putalpha(mask)
                output = preview_path(photo, photo_root, destination)
                output.parent.mkdir(parents=True, exist_ok=True)
                source.save(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--photos", type=Path, default=ROOT / "training photos")
    parser.add_argument("--checkpoint", type=Path, default=ROOT / "training/checkpoints/modnet_photographic_portrait_matting.ckpt")
    parser.add_argument("--output", type=Path, default=ROOT / "build/training-review/modnet-adaptation")
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--lr", type=float, default=1e-5)
    parser.add_argument("--guidance", type=Path, help="Optional coarse foreground/background scribbles JSON")
    parser.add_argument("--root-only", action="store_true", help="Reproduce the original seven root portraits without nested challenge folders")
    args = parser.parse_args()
    random.seed(42)
    np.random.seed(42)
    torch.manual_seed(42)
    torch.set_num_threads(4)
    torch.set_num_interop_threads(1)
    photos = discover_photos(args.photos, recursive=not args.root_only)
    if not photos:
        parser.error("No training photos found")
    guidance = json.loads(args.guidance.read_text())["photos"] if args.guidance else {}
    unknown_photos = set(guidance) - {p.relative_to(args.photos).as_posix() for p in photos}
    if unknown_photos:
        parser.error(f"Guidance refers to missing photos: {sorted(unknown_photos)}")
    args.output.mkdir(parents=True, exist_ok=True)
    model = MODNet(backbone_pretrained=False)
    checkpoint = torch.load(args.checkpoint, map_location="cpu", weights_only=True)
    model.load_state_dict({name.removeprefix("module."): tensor for name, tensor in checkpoint.items()})
    model.eval()
    print(f"CPU adaptation on {len(photos)} photos ({len(guidance)} with weak scribble labels); {args.epochs} epochs", flush=True)
    previews(model, photos, args.output / "before", args.photos)
    export_onnx(model, args.output / "baseline.onnx")
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr, betas=(.9, .99))
    history = []
    start = time.perf_counter()
    fixed_teacher = copy.deepcopy(model).eval() if args.guidance else None
    for epoch in range(args.epochs):
        teacher = fixed_teacher if args.guidance else copy.deepcopy(model).eval()
        order = list(photos)
        random.shuffle(order)
        values = []
        for photo in order:
            flip = random.random() < .5
            image = tensor_from_photo(photo, flip=flip)
            if args.guidance:
                entry = guidance.get(photo.relative_to(args.photos).as_posix())
                labels = guidance_mask(tuple(reversed(image.shape[-2:])), entry, flip) if entry else None
                values.append(guided_step(model, teacher, optimizer, image, labels))
            else:
                values.append(soc_step(model, teacher, optimizer, image))
        result = {"epoch": epoch + 1, "mean_loss": sum(v["loss"] for v in values) / len(values),
                  "elapsed_seconds": round(time.perf_counter() - start, 2)}
        history.append(result)
        print(json.dumps(result), flush=True)
        if epoch + 1 in {3, 6, args.epochs}:
            torch.save(model.state_dict(), args.output / f"epoch-{epoch + 1}.pt")
            previews(model, photos, args.output / f"epoch-{epoch + 1}", args.photos)
    export_onnx(model, args.output / "adapted.onnx")
    report = {"method": "MODNet weak scribble supervision with frozen-teacher curl replay" if args.guidance else "MODNet self-supervised sub-objective consistency (SOC) adaptation",
              "seed": 42, "learning_rate": args.lr, "epochs": args.epochs,
              "steps": args.epochs * len(photos), "device": "cpu", "ground_truth_masks": False,
              "limitations": "Loss is a training objective, not measured segmentation accuracy. All listed photos are adaptation examples; none is an independent labelled validation set. Coarse scribbles, when supplied, are weak labels rather than precise alpha mattes.",
              "checkpoint_sha256": hashlib.sha256(args.checkpoint.read_bytes()).hexdigest(),
              "guidance_sha256": hashlib.sha256(args.guidance.read_bytes()).hexdigest() if args.guidance else None,
              "guided_photos": sorted(guidance),
              "environment": {"torch": torch.__version__, "numpy": np.__version__, "Pillow": PIL.__version__},
              "preprocessing": {"training_max_side": 512, "preview_max_side": 768, "normalization": "RGB / 127.5 - 1", "dimensions": "aspect-preserving, rounded to multiples of 32"},
              "photos": [{"file": p.relative_to(args.photos).as_posix(), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in photos],
              "history": history}
    (args.output / "training-report.json").write_text(json.dumps(report, indent=2))
    print("Adaptation and ONNX export complete. Review before/after outputs before deployment.", flush=True)


if __name__ == "__main__":
    main()
