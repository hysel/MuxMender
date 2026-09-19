# Adaptive parallel workers — shared host

Includes v17 whole-folder queues/lifetime savings and v16 task progress.
UI resource profiles persist in requests.json; no new environment variables.

| Profile | Max files | CPU admission ceiling | Available RAM required | GPU admission ceiling |
| --- | ---: | ---: | ---: | ---: |
| Quiet | 1 | 55% | 10 GiB | 60% |
| Shared host (default) | 2 | 70% | 10 GiB | 75% |
| Faster | 4 | 80% | 8 GiB | 85% |

Additional workers require 30 seconds sustained healthy readings and 60 seconds
since the previous launch. Sampling is every five seconds. Memory/IO PSI, free
VRAM (2 GiB minimum), GPU temperature (<80 C), CPU affinity/quota, cgroup-v2
memory availability and combined scratch reservations also restrict admission.
NVIDIA measurements include graphics/compute and encoder utilization. Other GPU
vendors/missing telemetry degrade to serial execution; missing host health waits.
No ZFS ARC reclaimability is counted as immediately available RAM.

This is adaptive admission, not hard live CPU/GPU throttling: existing workers
finish at nice +10 when pressure rises. A lowered ceiling drains naturally.
It cannot reserve GPU time for Plex, guarantee its latency, or see contention in
other hypervisor guests. Use Quiet or pause the queue for more headroom. Hard CPU,
memory and I/O limits require deployment/cgroup controls. Faster is opt-in and is
not a measured throughput recommendation. No changes to Plex, drivers or ARC.

Publication is an isolated subprocess with independent progress logs. Source/
destination claims serialize same-stem inputs through publication. Per-job process
groups allow stopping all owned children. The lease is held until worker threads
exit; unclean restarts retain the existing review/pause behavior. Disk checks and
quality/preservation gates remain mandatory.

## Host snapshot (2026-09-18)

TrueNAS guest: 8 vCPUs, 125.8 GiB RAM, RTX 5050 8 GiB. Available RAM ~10.9 GiB,
ZFS ARC ~107.3 GiB, GPU 0%, encoder 0%, temperature 46 C. Short CPU sample ~5%
busy excluding iowait; 1-minute load 3.89 initially. Output/media pool ~22 TiB
available. These are transient readings, not spare-resource guarantees. Recommend
Shared host, maximum two jobs, and compare throughput/Plex responsiveness before
opting into Faster.

## Deployment

Wait for current work to finish (or pause admissions and allow active work to drain).
No active jobs are restarted by staging this build.

```sh
sudo docker build -f /mnt/FR4G/Apps/muxmender/app-build-20260918-v18/deploy/truenas/Dockerfile.app -t muxmender-app:20260918-v18 /mnt/FR4G/Apps/muxmender/app-build-20260918-v18
```

Select `20260918-v18`. Earlier staged versions do not need separate deployment.
Review live Resources feedback; Parallel production throughput remains to be
validated after deployment. Tests cover concurrent claims, shutdown, telemetry
backoff, reservations, and profile persistence with synthetic/mock workers.
