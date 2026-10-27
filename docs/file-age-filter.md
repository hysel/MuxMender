# Queue file-age filter

In Select and set up, choose **File creation date**:

- **All files** (default): creation date does not restrict selection.
- **Created within the last**: select recently created files, including the age
  boundary.
- **Older than**: select files created before the age boundary. For example,
  **Older than → 2 → Days** leaves files created in the last two days alone.

For either filter, enter a positive whole number and choose **Minutes**, **Hours**,
**Days**, or **Weeks**. The default is still **All files**.

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

The queue stores the selected age settings with each submitted job. No
encoder-quality, preservation or replacement checks change.
