# Getting started

MuxMender works on video files you already have. You choose what to process,
how much space you want to save, and whether to keep the original. It tries
supported encoding settings and checks the result before accepting it.

## Use the app

Open the dashboard address configured for your installation. In TrueNAS, media
and output folders and GPUs are assigned in the app settings. The output folder
is still needed for work in progress and job records, even in replacement mode.

1. **Select a folder or video.** Subfolders are included by default. Choose one
   level if you only want files directly inside the selected folder.
2. **Choose an action.** Inspect files, test short clips, create smaller copies,
   or replace originals after successful validation. These are different jobs;
   inspection does not automatically lead to conversion. Replacement permanently
   removes the original.
3. **Set your preferences.** Choose automatic or supported manual encoding
   settings, your quality target and minimum size reduction. Select output
   codecs you know your players can use.
4. **Preview and queue the selection.** Past decisions may mean some files do
   not need another attempt. The [creation-age filter](file-age-filter.md) can
   limit a new request to recently created files.
5. **Follow progress and read the results.** A kept file is not necessarily a
   failure: the output may not save enough space or meet the quality target.

Resolution stays unchanged unless you explicitly request another workflow.
HDR, audio and subtitles need their own checks; a playable picture alone does
not prove that all information survived.

## Choose the right action

| Action | What happens | What happens to the original? |
| --- | --- | --- |
| **Inspect videos — no conversion** | Reads the video's properties and checks the processing plan. **Inspection complete** means this inspection finished, not that a smaller video was created. | Unchanged; no encoding or disk savings. |
| **Test quality and size — samples only** | Tries short encoded samples to compare quality and size. It does not create a full converted video. | Unchanged. |
| **Create smaller copies — only if checks pass** | Tests candidates, then converts and validates the full video if a candidate qualifies. | Kept alongside the new copy; this does not free library space. |
| **Convert and replace originals — only after all checks pass** | Converts, validates and verifies the new file at its destination before replacing the original. Requires explicit confirmation. | Permanently removed only after successful checks and verified copying. |
| **Keep originals — do not convert** | Records your decision not to convert. | Unchanged; no encoding. |

If you see **Inspection complete** and want a smaller video, submit a new request
for the same selection with **Create smaller copies** or **Convert and replace
originals**. Review the selection before queuing it. Resuming an existing queue
keeps its saved action; it does not turn an inspection job into a conversion job.

A completed inspection is not a verdict that the file cannot be made smaller.
Likewise, passing sample tests does not guarantee the full output will pass every
check. Read the final result to see whether a copy was created, the original was
replaced, or the original was kept—and why.

## Understand progress and savings

The [dashboard guide](processing-dashboard.md) explains the steps. Percentages
describe the current check, not the whole job. Some steps need time to gather
enough information for an estimate.

Results show size reduction in percent and GB where available. Lifetime savings
count confirmed replacements. Keeping both copies does not free disk space,
and filesystem snapshots may retain deleted data.

After verified replacement, [cleanup](replacement-cleanup.md) removes eligible
generated work files. It keeps job history and does not sweep active jobs or
safe-copy outputs.

## Prefer a script?

Inspect a single file without converting it:

```powershell
python python/media_workflow.py "D:\Media\Example.mkv" --output-dir "E:\Optimized"
```

See the available options:

```powershell
python python/media_workflow.py --help
```

Run these from the repository folder with Python 3.10 or newer and FFmpeg /
FFprobe installed. The [standalone guide](STANDALONE.md) and older
[local web planner](WEBUI.md) describe separate entry points with different controls.

## Before a large run

Start with a small selection and confirm your players handle the results. Keep
enough output space for unfinished work. Use safe-copy mode if unsure about
replacement. The current app has no dashboard login: keep it on a trusted
network, not exposed directly to the internet.

Merged code is not automatically installed on your server. Check the
[status report](STATUS.md) and [roadmap](TODO.md) before deploying an update.
