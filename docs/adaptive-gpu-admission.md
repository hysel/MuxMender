# Let GPU concurrency follow measured results

GPU-heavy stages now learn their processing rate rather than inheriting the
CPU validation limit. They start one at a time. CPU-only preparation and
validation retain their separate existing pools.

After three comparable serial measurements, sustained resource headroom and a
backlog, the scheduler can test two GPU stages. It compares normalized processing
rates from similar-duration stages with matching resolution, pixel format,
frame rate, color transfer and codec/filter settings. Unknown video profiles
stay serial until comparable evidence is available. It keeps
two only after three measurements overlapping for at least 80% of their stage
duration show at least 10% more estimated
aggregate stage throughput. This is a throughput proxy, not proof that a whole
library completes faster; different scene complexity and shared-host load matter.

Busy GPU engines, low VRAM, high temperature, CPU/memory/storage pressure,
missing measurements or GPU-sharing requests lower admission to one. Existing
work drains normally; replacement transactions are never suspended by this
policy. A failed or inconclusive experiment returns to one with a cooldown.
Quiet mode limits new workers to one GPU stage. Other profiles cap experiments
at two. Quality, codec settings and publication checks are unchanged.

The dashboard resource summary shows the GPU-stage limit and its reason.
The small learning record lives under the output folder's shared admission
directory. It holds bounded rates and hashed stage-family identifiers, no media
or source filenames. OS locks still release slots when a worker dies.

The production app must be updated to use this code. Simulated policy and Linux
lock tests are not hardware qualification; measure finished jobs on the actual
GPU before claiming a processing-time improvement.
