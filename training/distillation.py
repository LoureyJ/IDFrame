"""Host-only soft-mask distillation for the existing fast MODNet architecture."""

import torch
import torch.nn.functional as F

from train_p3m import supervised_loss


def corrected_teacher_alpha(alpha, labels):
    """Apply reviewed interior corrections without changing soft unknown edges or teacher tensors."""
    if alpha.shape != labels.shape:
        raise ValueError("Teacher alpha and correction geometry differ")
    if not torch.isfinite(alpha).all() or (alpha < 0).any() or (alpha > 1).any():
        raise ValueError("Teacher alpha must be finite opacity between zero and one")
    if not ((labels == 0) | (labels == 128) | (labels == 255)).all():
        raise ValueError("Correction labels must be background, unknown, or foreground")
    target = alpha.detach().clone()
    target[labels == 255] = 1
    target[labels == 0] = 0
    return target


def distillation_loss(outputs, image, alpha, matte_logits):
    """Teach soft mattes with supervised branch losses and stable person-weighted logit gradients."""
    target = alpha.detach()
    if outputs[2].shape != target.shape or matte_logits.shape != target.shape:
        raise ValueError("Student matte, logits and target geometry differ")
    weights = torch.where(target >= 0.98, 3.0, 1.0)
    weights = torch.where((target > 0.02) & (target < 0.98), 4.0, weights)
    binary = F.binary_cross_entropy_with_logits(matte_logits, target, reduction="none")
    stable_matte = (binary * weights).sum() / weights.sum().clamp_min(1)
    return supervised_loss(outputs, image, target) + 2 * stable_matte


def validate_split(training, held_out):
    """Reject repeated paths or image bytes that contaminate a held-out photo partition."""
    for key in ("sample", "source_sha256"):
        train_values = [row[key] for row in training]
        held_values = [row[key] for row in held_out]
        if len(set(train_values)) != len(train_values) or len(set(held_values)) != len(
            held_values
        ):
            raise ValueError("Duplicate photo identity within a split: " + key)
        if set(train_values) & set(held_values):
            raise ValueError("Training and held-out photos overlap: " + key)
