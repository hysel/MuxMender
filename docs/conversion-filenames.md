# Readable conversion filenames

Pending change after v32 (not deployed): cryptic group/code/resolution filenames
such as `release-code.1080p.mkv` use the immediate folder title for the final output
when that folder contains only one media file. For example:
`Example Film/release-code.1080p.mkv` becomes `Example Film/Example Film.mkv`.
This is a folder-derived label, not an externally verified movie identity.

Safe-copy mode preserves the source. Replacement mode publishes the readable
name only through the existing validated, journaled, no-clobber replacement
transaction. Receipts retain original and published paths for history matching.
Already completed files are not renamed retroactively.

Existing descriptive filenames, episode identifiers, multiple-media folders,
generic folders and basename-linked external subtitle/artwork sets retain their
names. Conflicts never overwrite existing destinations. Embedded tracks remain
subject to normal preservation checks. No resizing or quality-policy changes.
