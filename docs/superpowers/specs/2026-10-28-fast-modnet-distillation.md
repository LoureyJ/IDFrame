# Fast MODNet distillation design

The user approved using BiRefNet as an offline training teacher while retaining
MODNet as the fast client student. Target client processing time is ideally
under one second, with 1–5 seconds acceptable on the tested host. This is a
measured target, not a guarantee for every client machine or source image.

Use cached, visually reviewed BiRefNet portrait masks, preserve soft alpha and
apply only existing reviewed coarse interior corrections. Exclude known teacher
body-loss, uncertain hair and unwanted-object failures from teacher training.
Keep the three main shirt/decoration/blurry-head cases and all camouflage photos
outside student fitting. Exact image hashes must not cross training/held-out
partitions; subject-disjointness is not claimed without metadata.

Continue from the accepted MODNet checkpoint. Freeze the shared backbone and
normalization running statistics; allow decoder normalization affine weights
and biases to adapt with the decoder. Train with real P3M alpha labels and local
soft teacher targets. Local examples use actual 768px client geometry; public
training uses 512px. Teacher inference never runs on clients. Save reproducible
checkpoints and compare held-out person retention, alpha boundaries, teacher
agreement, complete client latency and exports before activation.

No OTA publication or installer rebuild is authorized by this training request.
Code and public-safe reports are committed and pushed; photos, private labels,
weights and builds remain local. Any application/deployment payload change
requires prepare-only versioning and matching changelog notes. Retain original
active weights if the quality/speed gates fail.
