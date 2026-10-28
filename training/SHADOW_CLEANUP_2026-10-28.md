# Targeted shadow-removal experiment: 28 October 2026

The user requested better cast-shadow removal like BEN2 on the supplied
comparison example, with limited remaining Codex usage. This bounded experiment
keeps the accepted MODNet architecture and weights as the starting point. No
client changes, extra inference engine or automatic model activation are made.

The first screen tested five inference scales (384, 512, 640, 768, 1024) and
twelve input gamma/horizontal-flip combinations on the shadow example. None
produced a clean BEN2-like result. Output RGB always remained the original RGB;
gamma was applied only to the model input during the diagnostic screen.

Two targeted fusion-branch fine-tunes start from the accepted checkpoint
`12ac97b675eb0397d20276df169c79c190da131c3389933abc23d469a367b567`:
32 updates at Adam learning rate 0.00001, then a separate 96-update run at
0.0001. Only the existing fusion branch is trainable. Other model parameters
and normalization running statistics remain frozen. Seed is 119; gradients
are clipped at 1. Training uses four CPU threads.

The shadow example uses its cached official BEN2 base alpha as a background
correction: where teacher opacity is below 5/255, the target becomes background;
elsewhere it retains active MODNet alpha. Shadow-example training uses a 512px
maximum side. Alternating replay uses the original active masks on the other
40 photos at 384px. The 32-update run visits 16 distinct replay examples; the
96-update run visits all 40 plus eight repeats. Loss combines stable matte-logit
BCE and five times mean absolute matte error. No new model family or P3M model
is introduced, and BEN2 is not needed for student inference.

At the actual 768px geometry, a diagnostic shadow region is defined where
original MODNet alpha exceeds 0.2 and BEN2 alpha is below 0.02. Person-retention
diagnostics use BEN2 alpha above 0.98. These regions are teacher-derived,
not manually annotated ground truth or unseen validation.

| Checkpoint | Mean opacity in shadow region | Deficit in teacher-solid person region |
| --- | ---: | ---: |
| Accepted starting weights | 0.842394 | 0.001073 |
| 32 updates, learning rate 0.00001 | 0.837470 | 0.001336 |
| 16 updates, learning rate 0.0001 | 0.816876 | 0.004218 |
| 32 updates, learning rate 0.0001 | 0.804142 | 0.008388 |
| 64 updates, learning rate 0.0001 | 0.679565 | 0.010929 |
| 96 updates, learning rate 0.0001 | 0.465441 | 0.008642 |

The stronger run lowers mean opacity in this shadow region by about 44.7%,
but increases person-region opacity deficit. Actual exported-image inspection
shows a conspicuous ghost shadow outline and more transparent portrait regions.
That is not a clean shadow-removal fix. The measurement is not a claim that
44.7% of arbitrary shadows will be removed.

**Decision: do not activate either candidate.** The fast app has not gained
BEN2-quality shadow removal from these small runs. Broader correct shadow/person
supervision and separate validation are needed before a deployment decision.
No further training is launched after this bounded attempt.

Local evidence is under `build/shadow-scale-probe/`,
`build/shadow-strong-probe/` and
`build/new-photos-review/review-shadow-2026-10-28/`. The shadow image itself is
a training example and the other 40 images are replay examples; the 41-photo
client regression review is not independent accuracy validation. All weights,
photos, masks and review images remain outside Git. The existing BEN2 comparison
export remains available locally as
`build/engine-benchmark-2026-10-28/ben2/export-07.png`.

The actual-client review completed on all 41 photos. All white RGB
1200-by-1200 / 600 DPI exports passed; ONNX/PyTorch parity on three client
geometries had a maximum mean alpha difference below 1.6e-7. Across the 22
coarsely annotated office photos, foreground deficit worsened from 0.00537824
to 0.00937229, and background opacity worsened from 0.02004417 to 0.02034596.
The mean alpha drift on the other 19 challenges was 0.02090998; drift is not
accuracy. These diagnostics reinforce rejection of the candidate.

All 41 source hashes and the active model hash remain unchanged. Non-fusion
state and normalization running buffers were verified bit-identical to the
accepted checkpoint. Client version stays 1.1.18. No application/deployment
payload changed, so no prepare-only version increment, OTA publication,
installer rebuild or release publication was performed.
