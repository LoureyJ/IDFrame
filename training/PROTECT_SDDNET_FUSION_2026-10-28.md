# Protect-person and SDDNet mask fusion: 28 October 2026

The user requested combining Protect mode with SDDNet. The architectures and
weight tensors differ, so this implementation combines their aligned output
masks rather than averaging incompatible model parameters. The accepted MODNet
and both other model checkpoints remain unchanged.

## Implemented experiment

`shadow_fusion.py` exposes the host-only `fuse_shadow_masks` function. Inputs are
native-resolution L-mode masks: MODNet fine-hair opacity, U2Net Protect opacity,
and SDDNet shadow probability. White means person in the first two and shadow
in the third. The helper checks alignment, positive dimensions, modes and
finite valid fusion parameters. It never modifies its inputs or portrait RGB.

1. Resize the Protect mask proportionally to a 256px maximum side.
2. Erode it and select values above 245/255 as a conservative interior guard.
   `core_radius` controls erosion as a fraction of the smaller resized side.
3. Resize the guard to source dimensions with bilinear interpolation. Preserve
   extra fractional MODNet detail when Protect has some support and SDDNet's
   shadow probability is below 0.5. This is a heuristic, not a trained hair parser.
4. Restore stronger Protect opacity inside the guard, filling confidently
   protected person interiors that MODNet missed.
5. Attenuate shadow outside the guard, preserving original RGB:

```text
base  = matte + (max(matte, protect) - matte) * guard
alpha = base * (1 - strength * shadow * (1 - guard))
```

The helper defaults to strength 1 and core radius 0.05 for experimentation.
Those defaults are not approved production settings. SDDNet provenance and
preprocessing are unchanged from the [dedicated detector screen](SDDNET_SHADOW_SCREEN_2026-10-28.md).
No SDDNet code or weights are redistributed in this repository.

## Image review

The same five screened photos were evaluated using cached native masks. Six
settings combine core radii 0.03, 0.05, 0.075 with strengths 0.5 and 1. Every
comparison page includes active MODNet and unguarded subtraction as references.
All five pages were visually inspected. The following measurements refer only
to the requested cast-shadow example, not independent overall accuracy.

| Method | Mean opacity in teacher-derived shadow region | Coarse person-region deficit |
| --- | ---: | ---: |
| Active MODNet | 0.847690 | 0.002407 |
| Unguarded shadow subtraction | 0.169266 | 0.142599 |
| Guard radius 0.03, strength 0.5 | 0.669040 | 0.001159 |
| Guard radius 0.03, strength 1 | 0.490835 | 0.001292 |
| Guard radius 0.05, strength 1 | 0.311297 | 0.008640 |
| Guard radius 0.075, strength 1 | 0.206640 | 0.019631 |

The conservative guard protects the annotated body much better than naive
subtraction and restores some missing interiors. At radius 0.03, the shadow
region has about 21% less mean opacity at half strength and 42% less at full
strength, compared with active MODNet. These are teacher-derived region opacity
changes on one examined example, not shadow-removal accuracy percentages.

The important limitations remain visible: Protect itself includes some cast
shadow, so guarding its interior also preserves part of that shadow. Larger
erosion allows more shadow removal but exposes real portrait pixels. The scalp
in the detached-decoration example still fades, and the blurry portrait loses
hair or develops visibly artificial guard transitions. Guarding the body does
not establish reliable fine-hair preservation.

**Decision:** retain the implemented fusion as a host experiment, with comparison
outputs for inspection. It does not pass the portrait-quality gate and is not
enabled in the application. No new full-set benchmark or combined three-engine
latency claim is made after the five-photo quality screen fails.

## Verification and state

Seven focused tests cover protected interiors, restoration of missing person
interiors, removal outside person support, exact non-shadow soft alpha, uncertain
shadow over extra hair, empty masks and mismatched geometry. Tests were observed
failing before the corresponding implementation/fixes, then passing. All 32
host training tests, Ruff, Black formatting and function-purpose documentation
checks pass. Boundary review caught and fixed rejection of zero-sized masks.

The existing application and deployment payload are unchanged; client version
remains 1.1.18. No prepare-only version increment, installer rebuild, OTA update
or release publication is performed. Unrelated UI modifications are preserved.

Local evidence: `build/shadow-fusion-review/report.json` and five
`comparison-XX.jpg` pages. These and all underlying photographs/masks stay out
of Git. Preview exports are diagnostic artifacts, not an activated client model.
