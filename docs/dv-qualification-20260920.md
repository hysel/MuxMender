# NVIDIA DV qualification

First test: Combined-HDR series S01E01, 3840x1920, Profile 8.1. Stopped during source
inspection before encoding. Frame inspection confirmed simultaneous HDR10+
(SMPTE 2094-40) and Dolby Vision. No metadata was stripped and no source changed.
This is not a GPU limitation or evidence of an invalid source. Combined dynamic
metadata needs both preservation paths and checks; keep this as a follow-up case.

Second runner uses DV series B S01E03, 3840x2160, Profile 8.1. A one-second frame
probe near five minutes found DV RPU/metadata and static mastering/content-light
metadata without HDR10+. The shared test still inspects the complete extracted
sample before encoding; the initial probe does not certify the whole episode.

The separate runner is `run_dv_qualification_v2.py` in the existing qualification
folder; dependencies/shared modules are unchanged. No app image or queue changed.
No full-file quality or replacement approval has been granted by either probe.

## Second test result

Run `run-20260920-134111-6f025694`: 720 frames / 30 seconds, NVIDIA HEVC CQ18 p7,
no B frames. Structural validation passed: DV parsed metadata and frame order,
timing, static HDR, copied audio/subtitle packets, startup interleaving and decode.
RPU binary bytes differ, but canonical content comparison passed; this is not
claimed byte-identical preservation. Source size/mtime unchanged.

Encoding took about 21 seconds; complete workflow took 191.6 seconds. Video
payload grew from 52,974,507 to 75,968,198 bytes (+43.41%). Therefore this candidate
does NOT qualify for space-saving replacement. No perceptual quality score was
measured by this structural experiment. Next: shared quality/size trials with
less conservative NVENC settings, retaining all metadata checks. Full-file and
combined HDR10+/DV qualification remain outstanding.
