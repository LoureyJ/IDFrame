"""Read pinned P3M image/alpha pairs without extracting gigabytes of duplicates."""

from io import BytesIO
from pathlib import Path
import random

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
import pyarrow.parquet as pq
import torch


def prepare_pair(rgb, alpha, max_side=384, flip=False, augmentation_seed=None):
    """Apply paired geometry and optional input-only degradation, retaining soft alpha."""
    if rgb.size != alpha.size:
        raise ValueError("Image and alpha dimensions differ")
    if max_side < 64 or max_side % 32:
        raise ValueError("Maximum side must be at least 64 and aligned to 32")
    scale = max_side / max(rgb.size)
    size = tuple(max(64, round(side * scale / 32) * 32) for side in rgb.size)
    rgb = rgb.convert("RGB").resize(size, Image.Resampling.LANCZOS)
    alpha = alpha.convert("L").resize(size, Image.Resampling.LANCZOS)
    if flip:
        rgb, alpha = ImageOps.mirror(rgb), ImageOps.mirror(alpha)
    if augmentation_seed is not None:
        rng = random.Random(augmentation_seed)
        if rng.random() < 0.3:
            rgb = rgb.filter(ImageFilter.GaussianBlur(rng.uniform(0.2, 1.2)))
        if rng.random() < 0.3:
            rgb = ImageEnhance.Brightness(rgb).enhance(rng.uniform(0.75, 1.25))
        if rng.random() < 0.3:
            stream = BytesIO()
            rgb.save(stream, format="JPEG", quality=rng.randint(35, 85))
            stream.seek(0)
            with Image.open(stream) as compressed:
                rgb = compressed.convert("RGB")
    pixels = np.asarray(rgb, dtype=np.float32) / 127.5 - 1
    matte = np.asarray(alpha, dtype=np.float32) / 255
    return (
        torch.from_numpy(pixels.transpose(2, 0, 1).copy()),
        torch.from_numpy(matte.copy())[None],
    )


class P3MDataset:
    """Keep a single decoded Parquet row group cached and enforce explicit splits."""

    def __init__(self, root, split, max_side=384):
        """Index only the requested split's local shards, preserving row-group locality."""
        if split not in {"train", "P3M_500_P", "P3M_500_NP"}:
            raise ValueError("Unknown P3M split")
        self.max_side = max_side
        self.records = []
        self.groups = []
        self._key = self._rows = None
        for path in sorted(Path(root).glob(split + "-*.parquet")):
            metadata = pq.ParquetFile(path).metadata
            for group in range(metadata.num_row_groups):
                first = len(self.records)
                self.records.extend(
                    (path, group, row)
                    for row in range(metadata.row_group(group).num_rows)
                )
                self.groups.append(list(range(first, len(self.records))))
        if not self.records:
            raise ValueError("No complete Parquet shards for " + split)

    def __len__(self):
        """Return the indexed row count without loading image bytes."""
        return len(self.records)

    def pair(self, index):
        """Decode one matched embedded RGB image and continuous alpha matte."""
        path, group, row = self.records[index]
        key = (path, group)
        if key != self._key:
            self._rows = (
                pq.ParquetFile(path)
                .read_row_group(group, columns=["image", "mask"])
                .to_pylist()
            )
            self._key = key
        record = self._rows[row]
        if Path(record["image"]["path"]).stem != Path(record["mask"]["path"]).stem:
            raise ValueError("Mismatched image/mask identifiers")
        with Image.open(BytesIO(record["image"]["bytes"])) as image:
            rgb = image.convert("RGB")
        with Image.open(BytesIO(record["mask"]["bytes"])) as image:
            alpha = image.convert("L")
        if rgb.size != alpha.size:
            raise ValueError("Mismatched image/mask dimensions")
        return rgb, alpha

    def sample(self, index, augmentation_seed=None):
        """Return tensors with deterministic paired transforms and optional degradation."""
        return prepare_pair(
            *self.pair(index),
            self.max_side,
            flip=augmentation_seed is not None and augmentation_seed % 2 == 1,
            augmentation_seed=augmentation_seed,
        )

    def __getitem__(self, index):
        """Load an unaugmented pair for evaluation or fixture checks."""
        return self.sample(index)

    def epoch_order(self, excluded, seed):
        """Shuffle groups and their rows without repeatedly decoding random large groups."""
        rng = random.Random(seed)
        groups = list(self.groups)
        rng.shuffle(groups)
        order = []
        for group in groups:
            rows = [index for index in group if index not in excluded]
            rng.shuffle(rows)
            order.extend(rows)
        return order
