# Alternative technology comparison: 28 October 2026

The user asked whether another technology could make the portrait parameters
correct. A local CPU prototype combined the existing U2Net human segmenter,
the accepted MODNet, a heuristic trimap, and PyMatting closed-form alpha
estimation. This is an inference experiment, not another training run and not
a change to the deployed model. No method guarantees a correct mask for every
photo or makes coarse labels equivalent to ground-truth hair mattes.

## Method

Input RGB is contained within 768px without changing source files. The human
segmenter's largest connected component above 0.5 selects the proposed person.
An eroded, above-0.95 core defines certain foreground. A 12px surrounding band,
extended to 24px where MODNet opacity exceeds 0.03, defines uncertain support.
Everything else is certain background. These constants are experimental
heuristics, not validated production parameters. The RGB and trimap are passed
to `pymatting.estimate_alpha_cf` with a 2,000-iteration limit. Original pixels
are retained; no generative restoration or invented hair detail is used.

The test uses two known office failures and one blurry hair challenge. Active
model SHA-256 remains
`17567979483c1e9e7dd6809e84917e169a76ea052633b0b5285168e33e2917ae`.
Runtime uses CPU, with two threads per ONNX session. Local machine has about
15.6 GiB RAM and Intel Iris Xe integrated graphics. No GPU acceleration was used.

## Observations

The blurry example retains substantially more of the visible head/hair region,
but some surrounding background remains. The office examples reveal an upstream
mask problem: a wall logo and a vertical decoration remain joined to the proposed
person. The shirt's printed area also loses opacity. PyMatting follows its trimap;
it cannot reliably repair background incorrectly declared to be definite
foreground. Thus the two-stage design is feasible but these masks are not good
enough to deploy.

Measured extra processing after active MODNet inference was 1.53s, 2.20s and
6.28s for the three examples. Baseline MODNet took 0.80s, 0.58s and 1.08s.
These are individual local measurements, not general hardware benchmarks;
initial import/JIT compilation and session creation are excluded. The third
example triggered an incomplete-Cholesky positive-definiteness warning, then
returned a finite result. It would need handling before production use.

Three white RGB 1200-by-1200 / 600 DPI exports and comparison images are retained
locally. There are no independent alpha masks for these examples and no overall
accuracy claim. Existing coarse-region scores cover small interiors only and
miss some of the visible retained objects, so visual inspection is material.

**Decision: do not integrate this prototype.** A stronger person-specific mask
is the next candidate to benchmark; BiRefNet-portrait is a published alternative,
while SAM 2 supports point/box prompts for interactive person selection. Neither
was downloaded or tested here. SAM 2 segmentation masks still require matting
for soft hair opacity. Any alternative must be compared on full silhouettes,
foreground loss, retained objects, edge detail and CPU latency before deployment.

## Local reproduction and dependencies

Private driver: `build/compare_hybrid_matting.py`.
Outputs: `build/hybrid-matting-2026-10-28/`, including `comparison.jpg`,
`report.json`, three cutouts, trimaps and white exports. Photos and outputs remain
outside Git. Optional host-only packages were added to `.training-venv`:
PyMatting 1.1.16, SciPy 1.18.1, Numba 0.68.1 and llvmlite 0.50.0. Existing
NumPy 2.5.4 and Pillow 12.3.0 were retained. These dependencies were not added to
the application runtime or its standard requirements.

Official references:

- [PyMatting code and MIT license](https://github.com/pymatting/pymatting)
- [PyMatting alpha estimation documentation](https://pymatting.github.io/alpha.html)
- [BiRefNet-portrait model card](https://huggingface.co/ZhengPeng7/BiRefNet-portrait)
- [SAM 2 code and prompt interfaces](https://github.com/facebookresearch/sam2)

No app/deployment code, active weights, installer or OTA channel was changed.
Client version remains 1.1.18.
