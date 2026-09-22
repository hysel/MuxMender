# Starting work on a ZFS server

A large ZFS read cache can make available RAM look low even when the server
is idle. MuxMender now reads ARC statistics as well as Linux memory pressure.
It does not change the ZFS cache configuration or reserve memory from other apps.

When the normal memory threshold is not met, one job may start after 30 seconds
of healthy readings. This requires at least 6 GiB of available host RAM, 8 GiB
of resident evictable ARC, low memory and storage pressure, and no ARC request
to free memory. Cache credit is limited to half the evictable amount, capped at
8 GiB, and never added on top of MemAvailable. ARC's minimum size is protected;
ghost entries and secondary cache are not counted.

This path permits only one active job. Additional jobs still need the normal
memory headroom. Container memory limits, CPU load, GPU load, temperature and
storage-pressure checks still apply. Missing ARC data retains the previous
behavior. Running jobs are not suspended when admission closes.

This is a bounded admission heuristic, not a per-video peak-memory prediction
or a guarantee against out-of-memory failures. On the inspected server, a
read-only check found about 126 GiB of RAM, 112 GiB of ARC, 105 GiB of eligible
resident cache and no memory pressure. These readings qualified for the serial
path. An actual encode with this policy still requires deployment and observation.
