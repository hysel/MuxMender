# Experimental AMD AV1 QP80 preview

## Full-file copy and batch planning

Add `--full` to use the entire input, without extracting a reference. Default
behavior remains dry-run; `--full --execute` is required to encode. Full mode
ignores preview start/duration, preserves chapters and track metadata, verifies
the original SHA-256 before/after, and rejects savings below 5%. Failed outputs
remain for investigation. There is no automatic publication or source deletion.

```powershell
python -B python/amd_av1_preview.py "Y:\TV\episode.mkv" --output-dir "E:\MuxMender-TestOutputs" --full --dry-run
python -B python/library_planner.py "Y:\TV" --amd-av1 --reports "E:\MuxMender-TestOutputs\plans"
```

The recursive plan only reads media and writes reports, never starts an encoder.
It lists skip/review reasons and does not invent savings estimates. Eligibility
does not prove hardware availability or perceptual quality. Full-file jobs need
twice the input size plus a 5 GiB reserve before starting. Playback review remains
necessary; QP80 is not a lossless setting or a universal quality guarantee.

Full-file encode progress uses encoded frames divided by the counted source
video packets. This avoids sparse/empty subtitle tracks leaving the muxer's
output-time counter stuck or invalid. That progress estimate is separate from
decoded-frame validation and never approves output integrity. Verification can
take longer than GPU encoding: source and output frame timestamps are decoded,
then output geometry/audio are checked, followed by the source checksum.

## Bounded preview

Standalone script, no VS Code required. This opt-in route is limited to
progressive 1920x1080, square-pixel, 8-bit SDR video without Dolby Vision.
It uses the QP80 preset reviewed on Battlestar S02E20, not a universal quality
default. Existing optimizer defaults and strict geometry gate are unchanged.

From the repository root, plan first:

```powershell
python -B python/amd_av1_preview.py "Y:\TV\episode.mkv" --output-dir "E:\MuxMender-TestOutputs" --start 900 --seconds 30 --dry-run
```

Replace `--dry-run` with `--execute` to generate a preview. Supply `--ffmpeg`
and `--ffprobe` with executable paths if they are not on PATH. After installation,
the equivalent entry point is `muxmender-preview-amd-av1`.

Default behavior is dry-run: no GPU initialization or output directory creation.
Execution requires an existing AMD AV1 encoder and never installs software or
falls back to CPU. Outputs use a fresh unique directory and FFmpeg `-n`.
There are no delete, replace, or source-rename options. Failed files remain.
New media goes only beneath the specified output directory. Small dashboard
records use the repository reports folder. Progress is logged on the local
dashboard; displayed percentages are stage-specific.

Validation checks color/bit depth, copied audio/subtitle packet hashes and
timing, decoded video frame count/timestamps, full output audio/video decode,
and displayed geometry on every decoded frame. Exact 1920x1080 is accepted;
1920x1082 is accepted only with exactly two bottom crop rows AND every displayed
frame still 1920x1080. Other dimensions, rotation and source cropping are blocked.
No scaling filter is used. This does not guarantee other players honor cropping.

The copied preview can include keyframe lead-in (up to 15 seconds beyond the
requested 1–30 seconds). It compares decoded frames, not open-GOP packet counts.
Chapters are intentionally excluded from this excerpt. This is not a full-file
publication route or proof of whole-episode savings. Review picture quality and
audio/subtitle playback before considering further use. The validation report
marks savings below 5% as unacceptable; it never promotes the file automatically.

Source size/mtime is checked before/after; this preview does not claim a whole-
source checksum comparison. The prior full S02E20 test did compare checksums.
