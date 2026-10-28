# Fast MODNet Distillation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Improve the accepted MODNet using reviewed BiRefNet soft masks while targeting 1–5 seconds per client operation on the measured host.

**Architecture:** Preserve MODNet and client preprocessing. Fine-tune its decoder from the accepted checkpoint using cached, reviewed BiRefNet portrait masks and real P3M alpha pairs. Freeze the shared backbone and normalization running statistics to reduce forgetting; decoder normalization affine weights and biases remain trainable. Hold out the main failures and camouflage cases. BiRefNet is not a client dependency.

**Tech Stack:** Existing host PyTorch, Pillow, P3M loader, ONNX exporter and CPU ONNX Runtime.

**Spec:** `docs/superpowers/specs/2026-10-28-fast-modnet-distillation.md`, recording the user-approved workflow and the 1–5 second target.

## Global Constraints

- No OTA publication, installer rebuild or release publication without user request.
- Never push photos, private annotations, model weights or local builds.
- Run prepare-only and maintain a changelog only if application/deployment payload changes.
- Preserve unrelated `ui_inspector.py` and `ui_theme.py` work.
- No guarantees about client machines that were not benchmarked.

## Review Focus

- Bad teacher mattes must be excluded, not silently used as ground truth.
- Training and held-out photos must be disjoint by path and image bytes; subject disjointness is not asserted without metadata.
- Soft alpha and paired transforms must preserve hair rather than threshold it.
- Confidently wrong pixels need stable logit gradients and detached teacher targets.
- Speed/quality must use actual client geometry; faster tensor-only timings are insufficient.

## Tasks

1. [x] Review cached masks and record a private train/holdout/exclusion manifest with hashes. Reserve the three main failures and all camouflage examples. Exclude uncertain teacher outputs, captions/watermarks and held-object cases from teacher training.
2. [x] Write failing tests for soft-mask corrections, teacher detachment, saturated-logit gradients and source/holdout separation. Implement focused host-only distillation utilities and verify those tests.
3. [x] Run a bounded decoder fine-tune from the accepted checkpoint with 128 real public training masks and reviewed local teacher pairs; keep 64 public selection rows separate. Use local 768px geometry and public 512px geometry. Save four epoch checkpoints with provenance, optimizer and RNG state. Do not call this a full P3M epoch.
4. [x] Select by held-out foreground retention and alpha/boundary errors. Check actual-client ONNX parity, white 1200px/600 DPI exports, and all 41 local photos. Benchmark complete processing/export against the 1–5 second target, separating cold and warm timing.
5. [x] Obtain independent code review, record successes/failures and quality limitations, then commit/push only maintained code and public-safe reports. Activate weights only if the person-first quality and speed checks support improvement; otherwise retain the experiment without deployment.
