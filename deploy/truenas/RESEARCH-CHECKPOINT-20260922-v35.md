# MuxMender 20260922-v35

Packages the shared-engine checkpoint and completed research review. Nineteen
research runs covered 18 sources: 16 validated copies and two remaining keep
decisions after reconciling retries. Potential savings were 79.912 GB, not
space already reclaimed. See docs/research-checkpoint-20260922.md.

Includes shared timing/validation improvements, queue file-age selection and
the opt-in NVENC peak-rate setting. Peak-rate defaults are unchanged. Dolby
Vision automatic routing remains disabled; research is not blanket certification.
No publication or queue resume occurs merely by installing this version.

Build the staged context as muxmender-app:20260922-v35, then update the existing
TrueNAS app image tag, preserving mounts, user IDs and settings. Review the
displayed version before resuming. No driver update is required by this package.
