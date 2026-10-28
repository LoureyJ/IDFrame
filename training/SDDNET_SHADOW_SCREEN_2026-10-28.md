# Dedicated SDDNet shadow-detector screen: 28 October 2026

The user approved testing SDDNet as a possible companion to the accepted MODNet.
The first gate is detecting the supplied cast shadow without removing the person,
while keeping complete CPU processing within 1–5 seconds. This is a local
research screen, not production integration or another MODNet fine-tune.

## Provenance and method

Author repository: [SDDNet_ACMMM23](https://github.com/rmcong/SDDNet_ACMMM23),
commit `dddcdd4673dc24a411addcc9d4cbc63a6b30da73`. The actual `test.py` selects
EfficientNet-B3, not the ResNeXt mentioned in the README. Its SBU checkpoint
comes from the author's linked Drive folder, file ID
`19TU7zki31CdRBQDqB0eHB0RPwTPeXscB`, 158,448,475 bytes. Download length matches
the folder metadata. Locally calculated SHA-256:
`96ebe4fae382b9d83ad0507b635b256788a96b7c1732bd16074ab8af2b56851b`.
No independently published checkpoint checksum was found.

The model loads on CPU with `weights_only=True` and a strict state-dictionary
match. Separate ImageNet initialization is disabled because the complete task
checkpoint already supplies the backbone. Other test settings follow the author:
512-square OpenCV linear RGB resize, float32 /255 input, the model's internal
ImageNet normalization, and sigmoid of the `logit` output. Shadow probabilities
are resized bilinearly to native dimensions. No CRF or threshold tuning is added.
The architecture source is unchanged. An isolated `efficientnet-pytorch==0.7.1`
installation is added under ignored `.tools/engine-bench`; the app runtime is
unchanged. Four PyTorch CPU threads and one OpenCV thread are used.

The diagnostic combines original MODNet alpha with shadow probability as
`alpha * (1 - shadow_probability)`, retaining original RGB. This intentionally
simple subtraction is tested to expose false removal, not assumed to be safe.
The pipeline measures decode, MODNet, shadow detection, white framing/export;
the measurement also includes per-photo hash verification. Loading is separate.
Outputs use the existing white RGB 1200px / 600 DPI contract. Native HEIC decoding
and UI scheduling are not measured. Timing is on this host, not a client guarantee.

## Five-photo results

| Case | Description | Detector seconds | Diagnostic pipeline seconds |
| --- | --- | ---: | ---: |
| 7 | Requested cast-shadow failure | 0.432 | 1.075 |
| 0 | Patterned shirt and office backdrop | 0.391 | 1.152 |
| 1 | Detached decoration | 0.391 | 1.499 |
| 2 | Blurry head/hair | 0.367 | 0.953 |
| 32 | Fine curls against colored background | 0.379 | 0.709 |

Model setup/loading took 0.270 seconds and the first detector call 0.461 seconds.
These are a small warm screen, not a 41-photo latency distribution.

On the cast-shadow example, mean shadow probability is 0.7528 in the region
where active MODNet retains opacity but cached BEN2 treats it as background.
It is also 0.1421 inside existing coarse person annotations. These are mean
probabilities, not detection accuracy or the percentage of a person erased.
Teacher-derived regions and coarse annotations are not independent full masks.

All five comparison pages were visually reviewed. The detector recognizes the
cast shadow, but also marks naturally shaded clothing, hair and portrait edges.
Subtraction removes shirt regions, makes hair transparent and substantially
erases the blurry hair. The curly-hair example also loses valid portrait regions.
The central issue is that a shadow detector does not distinguish an unwanted
background shadow from valid shading on the person.

## Decision

SDDNet is fast enough in this limited screen to remain a possible supporting
component, but **direct automatic integration fails the person-retention gate**.
The screen therefore stops at five photos rather than extending a visibly unsafe
subtraction rule across the full set. No production behavior is changed.

A future integration needs an independently validated person/hair protection
stage or a user-reviewed shadow selection. The current MODNet mask alone cannot
supply that protection because it already includes the cast shadow. License
terms for redistribution of SDDNet code/weights also remain unresolved; public
availability alone is not treated as permission to bundle them in clients.

Local source, weights, provenance, reports, shadow maps and diagnostic comparison
pages remain under ignored `build/sddnet-probe/`. All five source hashes and PNG
output contracts were checked, and active weights remain unchanged. Client
version remains 1.1.18. No installer, OTA update or GitHub release was published.
