# Queue file-age filter

In Select and set up, choose **File creation age**:

- **All files** (default): creation date does not restrict selection.
- **Hours**, **days**, or **weeks**: enter a positive whole number to select files
  created within that recent interval, including its boundary.

The filter works with the selected folder scope, including subfolders by default,
or an individually selected video. Preview lists only matching videos and reports
counts excluded by age or missing creation dates. Saved-history checks still apply.
Selection is fixed at preview time; this is not a continuously watched folder.
Changing the control invalidates the preview. Existing queued jobs are unaffected.

Creation means the filesystem birth timestamp, not release date, modification time,
or Unix metadata-change time. Linux uses statx birth time; Windows uses its creation
timestamp. A filesystem or mount that does not expose birth time cannot safely be
age-filtered: such files are excluded and counted, not assigned guessed dates.
Copying or replacing files may change their filesystem creation time.

The standalone automatic-workflow adapter uses the same selection helper:

```text
python -m media_workflow VIDEO --output-dir OUTPUT --age-unit days --age-value 7
```

This CLI example analyzes the single video if it matches; it does not enable
conversion or replacement. The queue stores the selected age settings with each
submitted job. No encoder-quality, preservation or publication checks change.
