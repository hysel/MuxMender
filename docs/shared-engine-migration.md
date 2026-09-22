# Shared engine migration (after v32, not deployed)

## Implemented

- Extracted existing CLI rename planner, application transaction, identity checks,
  release suffix handling and title cleaning into `media_naming.py`. CLI symbols
  remain aliases for compatibility, not copies. Conversion naming and publication
  use that module too. Explicit existing-file renames preserve release details;
  new encoded outputs do not acquire stale source codec labels.
- `media_workflow.automatic_arguments` is the only mapping from normal app
  settings to automatic-engine arguments. CLI and app parity tests enforce this.
- `muxmender.py automatic` calls that same engine. Example (safe copy):

```bash
python python/muxmender.py automatic /media/movie.mkv --output-dir /output/new-job --mode encode --hardware auto --playback-verified-codecs hevc av1
```

Omit `--mode encode` for read-only analysis (reports may be written). `--mode test`
runs trials only. The automatic CLI does not authorize original deletion.
Replacement is still the separately authorized journaled publisher used by the app.
- Corrected stale HDR support text in the app.
- Added repository instructions requiring shared implementations and parity tests.

## Not yet merged — do not claim feature parity

The older default CLI remains a compatibility entry point. Its specialized DV,
Intel AV1 HDR repair, compatibility-audio/default-track and video-only publication
paths still need migration into automatic orchestration. They must be reused,
not rewritten, with unified quality evidence and publication receipts before
being enabled for unattended replacements. Existing-file cleanup remains the
shared standalone planner and requires a reviewed scope; it is not exposed as an
automatic app media-cleanup operation. No new Docker release accompanies this
refactor, and no active jobs or media have been changed.
