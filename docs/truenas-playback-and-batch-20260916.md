# TrueNAS playback result and bounded follow-up batch

User confirmed Episode A AV1 playback passed on both Chrome and Sony.
This is user-reported playback evidence, not automated Plex telemetry.

- Source: Series A S01E16 Episode A, 3,051,603,039 bytes.
- Output: `auto-20260916-135938-e6f2ee11/full-av1.mkv`, 2,156,812,796 bytes.
- Reduction: 29.32197378113831%; not freed space while the original is retained.
- Automated state: `validated-copy-awaiting-playback`; report left unchanged.
- Source SHA256: `417dc726eaa2fe8ec700c6b563d3107d4a5123d4a1e189c11aa6389b927b8c23`.
- Output SHA256: `81da38340c7449258209da0298a61157ba0caf34ce8d6d2469dd6af5f052a0a4`.
- E copy verified against output checksum; retained for current playback work.

Next approved scope: S01E06 Episode B, S01E08 Episode C, S01E10 Episode D. All passed
read-only eligibility probes. No expected savings are asserted in advance.
The historical title-specific batch helper ran them serially through the standard measured
codec-selection flow. Each eligible output is a separate full validated copy;
full-resolution, color, timing, track and source-integrity checks are unchanged.
No source replacement, deletion, or automatic media-library publication.

Default is dry-run. Execution requires a read-only media mount, disjoint output
directory, >=12 GiB free, and an unused batch directory. Repeating submission
fails rather than rerunning jobs. An execution failure stops remaining episodes.
Job history displays each individual episode; `batch-summary.json` records the
batch sequence and exit codes, not a claim that every output passed validation.

Launch once from the TrueNAS administrator shell (worker runs as UID/GID 3005):

```bash
sudo docker exec -d --user 3005:3005 ix-muxmender-muxmender-1 \
  python3 -B /output/EXAMPLE_BATCH_HELPER.py --execute
```

No image rebuild or app restart is needed. Do not restart the container while
the batch is running. The dashboard remains at http://192.168.1.232:8767.
