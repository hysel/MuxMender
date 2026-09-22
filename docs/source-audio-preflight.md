# Catching damaged audio before encoding

The shared CLI and app engine now decode every source audio track before codec
trials and full conversion. This reads the source without modifying it. Silent
videos bypass the check. Progress is reported during the audio scan.

Why: a reported AVI case finished video conversion but failed the final audio
check. Reading the complete original audio reproduced the same incomplete AC-3
frame error. The copied final packets matched the original. The problem was
already in the input, rather than introduced by video encoding.

A preflight failure stops work early and records the decoder error in
`source-audio-preflight.json`. It does not approve replacement, conceal errors,
drop audio packets, or mark the media as already optimized. Final output audio
validation still runs independently, even after the source check passes.

This saves unnecessary encoding work for damaged inputs. Healthy inputs incur
an additional audio-only read/decode; no universal runtime improvement is
claimed. There is no automatic repair for truncated compressed audio: that
requires separate evidence that valid audio and synchronization are preserved.

## Staged preflight

Before codec trials, the engine now runs these checks in order:

1. Check stream identities, finite positive duration, conflicting metadata tags
   and chapter intervals. No fixed resolution or container preference is added.
2. Inspect MP4 AAC priming and check whether the preservation tool is available.
3. Decode every source audio track, with visible progress and strict errors.
4. For full-conversion jobs, read copied audio/subtitle/cover packets and reject
   reported demux errors before encoding. This is not subtitle rendering or
   proof that every attachment will work in every player.
5. Continue the existing video/HDR sample and real encoder capability tests.

The copied-track evidence from step 4 can replace the later source-side packet
read only within this workflow instance. Before reuse, the engine hashes the
source and evidence again. Changed source bytes stop the job; changed evidence
is collected again. A restarted process cannot inherit this in-memory cache.

`source-preflight.json` records the current step and outcome. These early checks
do not replace full output video, audio, timing, metadata or quality validation.
No additional mandatory full source-video decode was introduced. Full preflight
reads do add upfront I/O, particularly for a file later found not worth encoding;
their purpose is early fault detection and evidence reuse, not a claimed speedup
for every input.
