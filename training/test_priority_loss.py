"""Verify person retention, soft edges, and background suppression gradients."""

import unittest

import torch

from priority_loss import region_priority_loss, local_priority_loss


class PriorityLossTests(unittest.TestCase):
    """Exercise priorities on independently specified opacity examples."""

    def test_confident_wrong_mattes_still_receive_corrections(self):
        """Even saturated sigmoid outputs must learn from explicit person/object corrections."""
        logits = torch.tensor([[[[-40.0, 40.0]]]], requires_grad=True)
        matte = logits.sigmoid()
        teacher = torch.tensor([[[[0.0, 1.0]]]])
        labels = torch.tensor([[[[255, 0]]]])
        loss = local_priority_loss(
            (matte, matte, matte),
            (teacher, teacher, teacher),
            labels,
            matte_logits=logits,
        )
        loss.backward()
        self.assertTrue(torch.isfinite(loss))
        self.assertLess(logits.grad[0, 0, 0, 0].item(), -1)
        self.assertGreater(logits.grad[0, 0, 0, 1].item(), 1)

    def test_single_region_crops_have_finite_gradients(self):
        """Person-only, background-only, and transition-only crops cannot divide by zero."""
        for opacity in (0.0, 0.5, 1.0):
            prediction = torch.full((1, 1, 1, 1), 0.4, requires_grad=True)
            loss = region_priority_loss(
                prediction, torch.full_like(prediction, opacity)
            )
            loss.backward()
            self.assertTrue(torch.isfinite(loss))
            self.assertTrue(torch.isfinite(prediction.grad).all())

    def test_replay_without_scribbles_supports_different_branch_sizes(self):
        """Unlabelled replay uses the teacher without requiring same-size semantic outputs."""
        outputs = tuple(
            torch.full(shape, 0.5, requires_grad=True)
            for shape in ((1, 1, 1, 1), (1, 1, 2, 2), (1, 1, 2, 2))
        )
        teacher = tuple(torch.ones_like(value) for value in outputs)
        labels = torch.full((1, 1, 2, 2), 128)
        loss = local_priority_loss(outputs, teacher, labels)
        loss.backward()
        self.assertTrue(torch.isfinite(loss))
        self.assertTrue(all((value.grad < 0).all() for value in outputs))

    def test_missing_person_costs_more_than_equal_background_residue(self):
        """Prioritize an equally sized missing person region over false background opacity."""
        alpha = torch.tensor([[[[1.0, 0.0]]]])
        missing = region_priority_loss(torch.tensor([[[[0.5, 0.0]]]]), alpha)
        residue = region_priority_loss(torch.tensor([[[[1.0, 0.5]]]]), alpha)
        self.assertGreater(missing.item(), residue.item())

    def test_soft_hair_is_not_forced_to_binary_opacity(self):
        """A true fractional strand must beat fully erased and fully opaque alternatives."""
        alpha = torch.tensor([[[[0.0, 0.25, 0.75, 1.0]]]])
        exact = region_priority_loss(alpha, alpha)
        self.assertLess(
            exact.item(), region_priority_loss(torch.zeros_like(alpha), alpha).item()
        )
        self.assertLess(
            exact.item(), region_priority_loss(torch.ones_like(alpha), alpha).item()
        )

    def test_gradients_restore_person_and_erase_labeled_objects(self):
        """Gradient descent increases person opacity and decreases background-object opacity."""
        prediction = torch.tensor([[[[0.4, 0.6, 0.5]]]], requires_grad=True)
        alpha = torch.tensor([[[[1.0, 0.0, 0.25]]]])
        region_priority_loss(prediction, alpha).backward()
        self.assertLess(prediction.grad[0, 0, 0, 0].item(), 0)
        self.assertGreater(prediction.grad[0, 0, 0, 1].item(), 0)
        self.assertGreater(prediction.grad[0, 0, 0, 2].item(), 0)

    def test_local_labels_override_wrong_teacher_and_protect_unknown_person(self):
        """Explicit corrections beat erroneous teachers while unknown foreground remains protected."""
        matte = torch.tensor([[[[0.5, 0.5, 0.5]]]], requires_grad=True)
        teacher = torch.tensor([[[[0.0, 1.0, 1.0]]]])
        labels = torch.tensor([[[[255, 0, 128]]]])
        local_priority_loss(
            (matte, matte, matte), (teacher, teacher, teacher), labels
        ).backward()
        self.assertLess(matte.grad[0, 0, 0, 0].item(), 0)
        self.assertGreater(matte.grad[0, 0, 0, 1].item(), 0)
        self.assertLess(matte.grad[0, 0, 0, 2].item(), 0)


if __name__ == "__main__":
    unittest.main()
