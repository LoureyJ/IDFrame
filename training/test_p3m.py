"""Small labeled fixtures prove P3M loading and supervised loss without private data."""

from io import BytesIO
from pathlib import Path
import tempfile
import unittest

import numpy as np
from PIL import Image
import pyarrow as pa
import pyarrow.parquet as pq
import torch

from p3m_dataset import P3MDataset, prepare_pair
from train_p3m import supervised_loss, save_checkpoint, restore_checkpoint
from evaluate_p3m import alpha_metrics, cached_prediction, prepare_cache


def encoded(image):
    """Encode a fixture image in memory using the dataset's embedded-byte layout."""
    stream = BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


class P3MTests(unittest.TestCase):
    """Check continuous alpha, paired geometry, split safety, and loss gradients."""

    def test_pair_keeps_soft_alpha_and_synchronized_flip(self):
        """Image colors and soft labels follow the same geometric transformation."""
        rgb = Image.new("RGB", (64, 64), "black")
        rgb.paste("white", (32, 0, 64, 64))
        alpha = Image.new("L", (64, 64), 0)
        alpha.paste(127, (32, 0, 64, 64))
        image, mask = prepare_pair(rgb, alpha, max_side=64, flip=True)
        self.assertEqual(tuple(image.shape), (3, 64, 64))
        self.assertAlmostEqual(mask[0, 20, 10].item(), 127 / 255, places=5)
        self.assertEqual(image[0, 20, 10].item(), 1)
        self.assertEqual(mask[0, 20, 50].item(), 0)

    def test_mismatched_pair_is_rejected(self):
        """A different-size label cannot silently supervise the wrong pixels."""
        with self.assertRaises(ValueError):
            prepare_pair(Image.new("RGB", (64, 64)), Image.new("L", (32, 64)))

    def test_parquet_loader_uses_only_requested_split(self):
        """Official evaluation rows cannot enter the training split by globbing."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            row = {
                "image": {
                    "bytes": encoded(Image.new("RGB", (64, 64), "red")),
                    "path": "p_1.jpg",
                },
                "mask": {
                    "bytes": encoded(Image.new("L", (64, 64), 127)),
                    "path": "p_1.png",
                },
            }
            for split in ("train", "P3M_500_P"):
                pq.write_table(
                    pa.Table.from_pylist([row]), root / f"{split}-00000.parquet"
                )
            dataset = P3MDataset(root, "train", max_side=64)
            self.assertEqual(len(dataset), 1)
            image, mask = dataset[0]
            self.assertEqual(tuple(mask.shape), (1, 64, 64))
            self.assertTrue(
                all("train-" in str(path) for path, _, _ in dataset.records)
            )
            with self.assertRaises(ValueError):
                P3MDataset(root, "unknown")

    def test_supervised_loss_is_finite_and_has_gradients(self):
        """All three MODNet branches receive a meaningful labeled loss."""
        image = torch.zeros(1, 3, 64, 64)
        alpha = torch.zeros(1, 1, 64, 64)
        alpha[:, :, 16:48, 16:48] = 1
        outputs = tuple(
            torch.full(shape, 0.5, requires_grad=True)
            for shape in [(1, 1, 4, 4), (1, 1, 64, 64), (1, 1, 64, 64)]
        )
        loss = supervised_loss(outputs, image, alpha)
        self.assertTrue(np.isfinite(loss.item()))
        loss.backward()
        self.assertTrue(all(value.grad is not None for value in outputs))

    def test_alpha_metrics_detect_missing_foreground(self):
        """Perfect masks score zero while erased solid foreground incurs a penalty."""
        target = np.zeros((64, 64), dtype=np.float32)
        target[16:48, 16:48] = 1
        perfect = alpha_metrics(target, target)
        damaged = alpha_metrics(np.zeros_like(target), target)
        self.assertEqual(perfect["mae"], 0)
        self.assertEqual(perfect["interior_deficit"], 0)
        self.assertGreater(damaged["mae"], 0)
        self.assertEqual(damaged["interior_deficit"], 1)

    def test_cached_failure_remains_visible_after_restart(self):
        """Resuming evaluation must not turn a failed inference into a successful row."""

        class FailingRemover:
            """Simulate an inference failure without loading model weights."""

            def remove(self, image):
                """Fail consistently for a corrupted model input."""
                raise ValueError("fixture inference failed")

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "0000.png"
            image = Image.new("RGB", (64, 64))
            first, failure = cached_prediction(FailingRemover(), image, (64, 64), path)
            self.assertFalse(path.exists())
            second, resumed_failure = cached_prediction(
                FailingRemover(), image, (64, 64), path
            )
            self.assertEqual(failure, "fixture inference failed")
            self.assertEqual(resumed_failure, failure)
            self.assertEqual(first.tobytes(), second.tobytes())

    def test_evaluation_cache_rejects_changed_or_missing_identity(self):
        """A hard interruption cannot allow another model or dataset to reuse masks."""
        identity = {"model_sha256": "first", "dataset_revision": "revision-one"}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "owned"
            prepare_cache(path, identity)
            Image.new("L", (8, 8), 30).save(path / "cached.png")
            prepare_cache(path, identity)
            for changed in (
                identity | {"model_sha256": "second"},
                identity | {"dataset_revision": "revision-two"},
            ):
                with self.assertRaises(ValueError):
                    prepare_cache(path, changed)
            unowned = Path(directory) / "unowned"
            unowned.mkdir()
            Image.new("L", (8, 8)).save(unowned / "cached.png")
            with self.assertRaises(ValueError):
                prepare_cache(unowned, identity)

    def test_checkpoint_restores_optimizer_rng_and_cursor(self):
        """A resumed optimizer takes the same next step as uninterrupted training."""
        torch.manual_seed(17)
        model = torch.nn.Linear(2, 1)
        optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
        optimizer.zero_grad()
        model(torch.ones(1, 2)).sum().backward()
        optimizer.step()
        report = {
            "dataset_revision": "fixture",
            "steps": 3,
            "epochs_requested": 1,
            "training_complete": False,
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "resume.pt"
            save_checkpoint(path, model, optimizer, 0, 3, report)
            next_input = torch.rand(1, 2)
            optimizer.zero_grad()
            model(next_input).sum().backward()
            optimizer.step()
            expected = {
                name: value.clone() for name, value in model.state_dict().items()
            }
            epoch, position, resumed = restore_checkpoint(
                path, model, optimizer, report, ("dataset_revision",), epochs=2
            )
            self.assertEqual((epoch, position, resumed["steps"]), (0, 3, 3))
            self.assertEqual(resumed["epochs_requested"], 2)
            self.assertTrue(torch.equal(torch.rand(1, 2), next_input))
            optimizer.zero_grad()
            model(next_input).sum().backward()
            optimizer.step()
            for name, value in model.state_dict().items():
                self.assertTrue(torch.equal(value, expected[name]))
            with self.assertRaises(ValueError):
                restore_checkpoint(
                    path,
                    model,
                    optimizer,
                    {"dataset_revision": "other"},
                    ("dataset_revision",),
                    epochs=2,
                )


if __name__ == "__main__":
    unittest.main()
