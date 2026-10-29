"""Optional offline eye-line straightening; no changes to background-removal models."""

import math
from pathlib import Path

import numpy as np
import onnxruntime as ort
from PIL import Image, ImageOps

MODEL_PATH = Path(__file__).resolve().parent / "models" / "face_alignment.onnx"
MODEL_URL = (
    "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/"
    "models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
)
MODEL_SHA256 = "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"
OUTPUTS = [
    f"{kind}_{stride}"
    for kind in ("cls", "obj", "bbox", "kps")
    for stride in (8, 16, 32)
]


class OfflineAligner:
    """Estimate a reversible rotation only when explicitly requested by the user."""

    def __init__(self, model_path=MODEL_PATH):
        """Remember a bundled detector path without starting inference or networking."""
        self.model_path = Path(model_path)
        self._session = None

    def estimate(self, photo):
        """Try quarter turns and return absolute clockwise degrees, or no correction."""
        source = ImageOps.contain(photo.convert("RGB"), (640, 640))
        best = None
        for coarse in (0, 90, 180, 270):
            rotated = source.rotate(coarse, expand=True)
            faces = self._detect(rotated)
            if len(faces) > 1:
                return None
            if not faces:
                continue
            face = faces[0]
            left, right = sorted(face["points"][:2], key=lambda point: point[0])
            dx, dy = right - left
            if dx < 5 or face["points"][2, 1] <= min(left[1], right[1]):
                continue
            roll = math.degrees(math.atan2(dy, dx))
            if abs(roll) > 35:
                continue
            if best is None or face["score"] > best[0]:
                best = face["score"], (-(coarse + roll) + 180) % 360 - 180
        return None if best is None else round(best[1], 1)

    def _detect(self, photo):
        """Decode YuNet landmarks using OpenCV's published FaceDetectorYN equations."""
        if self._session is None:
            if not self.model_path.is_file():
                raise FileNotFoundError(
                    "Auto-skew model is missing. Run setup.bat on the host and publish the update."
                )
            options = ort.SessionOptions()
            options.intra_op_num_threads = 2
            options.inter_op_num_threads = 1
            self._session = ort.InferenceSession(
                str(self.model_path), options, providers=["CPUExecutionProvider"]
            )
        small = ImageOps.contain(photo, (384, 384), Image.Resampling.BILINEAR)
        tensor = np.zeros((1, 3, 640, 640), dtype=np.float32)
        tensor[0, :, : small.height, : small.width] = np.asarray(small)[
            :, :, ::-1
        ].transpose(2, 0, 1)
        predictions = dict(zip(OUTPUTS, self._session.run(OUTPUTS, {"input": tensor})))
        candidates = []
        for stride in (8, 16, 32):
            scores = np.sqrt(
                np.clip(predictions[f"cls_{stride}"][0, :, 0], 0, 1)
                * np.clip(predictions[f"obj_{stride}"][0, :, 0], 0, 1)
            )
            for index in np.flatnonzero(scores >= 0.9):
                row, col = divmod(int(index), 640 // stride)
                box = predictions[f"bbox_{stride}"][0, index]
                center = (np.array([col, row]) + box[:2]) * stride
                size = np.exp(box[2:]) * stride
                points = (
                    predictions[f"kps_{stride}"][0, index].reshape(5, 2)
                    + np.array([col, row])
                ) * stride
                candidates.append(
                    {
                        "box": np.r_[center - size / 2, center + size / 2],
                        "points": points,
                        "score": float(scores[index]),
                    }
                )
        kept = []
        for face in sorted(candidates, key=lambda face: -face["score"]):
            if all(self._iou(face["box"], other["box"]) < 0.3 for other in kept):
                kept.append(face)
        return kept

    @staticmethod
    def _iou(first, second):
        """Measure box overlap so duplicate predictions cannot appear as extra people."""
        intersection = np.maximum(
            0, np.minimum(first[2:], second[2:]) - np.maximum(first[:2], second[:2])
        ).prod()
        union = (
            (first[2:] - first[:2]).prod()
            + (second[2:] - second[:2]).prod()
            - intersection
        )
        return intersection / max(1, union)
