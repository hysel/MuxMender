# Reading the dashboard

The dashboard should answer three questions: what is running, what is it doing,
and what happened to the files that finished?

## Follow the current step

Automatic jobs report these steps when they apply:

1. Inspect the source.
2. Compare short test encodes.
3. Encode the full video.
4. Validate the result.
5. Put the approved replacement in place.
6. Clean up eligible work files.

Safe-copy jobs do not replace the original or run replacement cleanup.

A percentage belongs to the current check. Reaching 100% on that check does not
mean the whole job is finished. The time estimate also covers that check, not
every remaining step. When there is not enough information yet, the dashboard
shows a measuring or waiting message instead of inventing a percentage.

## Read the result

A completed conversion passed its applicable checks. A kept file may simply
have missed the quality or size target. A failure means something prevented
the work from completing; read its reason before retrying.

Older job records may not have the newer step information. The dashboard labels
that gap rather than guessing. Technical details and resource settings can be
expanded when you need them.

## Understand the savings

Size reduction compares the original with the output. Lifetime savings count
confirmed replacements, not every test copy. Percentages and GB describe file
sizes; snapshots may mean your storage pool does not immediately show the same
amount of free space.

The app and CLI use the same job progress information. These features are in
the code; check the [status report](STATUS.md) for deployment context.
