"""Host-only objectives for person retention, soft boundaries, and labeled background removal."""

import torch
import torch.nn.functional as F


def masked_mean(value, mask):
    """Average only selected pixels, returning differentiable zero for an empty region."""
    return (value * mask).sum() / mask.sum().clamp_min(1)


def region_priority_loss(prediction, alpha):
    """Penalize missing person most, preserve fractional strands, and suppress true background."""
    foreground = alpha >= 0.98
    background = alpha <= 0.02
    transition = ~(foreground | background)
    loss = (
        8 * masked_mean(F.relu(alpha - prediction), foreground)
        + 3 * masked_mean(F.relu(prediction - alpha), background)
        + 3 * masked_mean((prediction - alpha).abs(), transition)
    )
    # Match opacity changes without thresholding soft strands into binary masks.
    for dimension in (-2, -1):
        if alpha.shape[dimension] > 1:
            loss = (
                loss
                + 2
                * (
                    torch.diff(prediction, dim=dimension)
                    - torch.diff(alpha, dim=dimension)
                )
                .abs()
                .mean()
            )
    return loss


def local_priority_loss(outputs, teacher_outputs, labels, *, matte_logits=None):
    """Use known local corrections while distilling the accepted person in unknown regions."""
    matte = outputs[2]
    foreground = labels == 255
    background = labels == 0
    unknown = labels == 128
    # Training supplies pre-sigmoid logits so confidently wrong mattes retain gradients.
    value = matte if matte_logits is None else matte_logits
    binary_loss = (
        F.binary_cross_entropy
        if matte_logits is None
        else F.binary_cross_entropy_with_logits
    )
    foreground_loss = binary_loss(value, torch.ones_like(value), reduction="none")
    background_loss = binary_loss(value, torch.zeros_like(value), reduction="none")
    teacher_loss = binary_loss(value, teacher_outputs[2].detach(), reduction="none")
    loss = (
        8 * masked_mean(foreground_loss, foreground)
        + 3 * masked_mean(background_loss, background)
        + 6 * masked_mean(teacher_loss, unknown)
    )
    for weight, prediction, teacher in zip((5, 1), outputs[:2], teacher_outputs[:2]):
        branch_labels = F.interpolate(
            labels.float(), size=prediction.shape[-2:], mode="nearest"
        )
        target = torch.where(
            branch_labels == 255, torch.ones_like(teacher), teacher.detach()
        )
        target = torch.where(branch_labels == 0, torch.zeros_like(target), target)
        loss = loss + weight * F.mse_loss(prediction, target)
    return loss
