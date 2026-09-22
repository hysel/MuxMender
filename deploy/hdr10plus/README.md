# Standalone HDR10+ preservation test

Target: HDR case A, using the completed NVIDIA full encode.
This is an isolated validation image, not an update to the TrueNAS app.

Run `sudo bash /absolute/path/to/package/run.sh`. Keep the build shell open
until the script prints `Started`. The test then runs detached and survives
shell timeouts. Re-running starts another test, so do not run it twice.

The original movie and encoded intermediate are mounted read-only. A unique
output folder is writable. No GPU is needed: this restores metadata, remuxes,
and decodes for validation, without re-encoding. Runtime is limited to four CPU
cores, 6 GiB RAM, and six hours per stage. The application queue is unchanged.

The Docker build downloads Python/MKVToolNix packages. hdr10plus_tool 1.7.2
is bundled from its official GitHub release and checked against its SHA-256.
The build runs the HDR validator and streaming JSON parser unit tests.

The job verifies stream metadata, all decoded frame timestamps/color/HDR10+
metadata, copied audio/subtitle packet hashes and timing, and a full decode.
`preservation.json` is produced only after these checks pass. Picture quality
is not automatically approved and no replacement is performed.

Inputs and intermediate test outputs are retained. Failed outputs must not
be published as validated media. The container is retained for log inspection.
No Docker daemon socket, privileged mode, host networking, or writable media
mount is used. Current app code/release is not changed.
