# Reducing long HDR validation waits

The observed job had spent roughly 92 minutes in total, not 92 minutes in its
current validation pass. Its output frame audit had taken about 22 minutes at
70% completion. The reader used two CPU threads; another job was encoding.
The GPU was busy encoding, while the validation reader decoded on the CPU.

## Measured comparison

We tested a separate copy of that 4K HDR output locally, using the same 60-second
window twice per configuration. All 1,439 frames produced matching validation
fields and complete side-data evidence.

| Reader | Median elapsed time |
| --- | ---: |
| Two threads, full frame JSON | 20.78 seconds |
| Four threads, full frame JSON | 13.13 seconds |

That is approximately 37% less time for the sampled reader stage, or 1.58 times
the throughput. It is **not** a measured TrueNAS or whole-job speedup. The
four-thread command was separately checked against the full validation evidence;
no decoded frames or metadata checks were removed.

Selecting fewer JSON fields brought only a small additional gain. Production
still requests the full HDR frame JSON to retain all side-data evidence.

## Implementation

Long HDR readers can now use four threads when measured CPU and memory headroom
permit it. Otherwise they retain two. The policy considers container CPU limits,
CPU utilization, available RAM and storage/memory pressure. It leaves at least
two of the estimated available CPU cores outside this reader's budget and caps
the reader at four threads. It samples at stage start, not continuously inside
an already running decoder. Existing queue admission controls remain active.

Validation now reports an estimated remaining time for its current reader pass.
That estimate does not include later checks. HDR frame-audit time is categorized
as validation rather than generic other work.

The active production job was not restarted or changed. A deployed build and
same-host measurement are still required to quantify the TrueNAS improvement.
