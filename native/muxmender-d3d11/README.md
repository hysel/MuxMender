# Experimental native D3D11 helper

This is an experimental diagnostic prototype, not a production optimizer.

- `muxmender-d3d11.exe` checks hardware D3D11 device creation.
- `muxmender-color-test.exe` renders a generated 64x64 SDR pattern with
  libplacebo, downloads the pixels, and checks all channels (tolerance 2/255).
  It refuses software fallback. It accepts no media paths and writes no media.
- Neither test validates Dolby Vision, HDR preservation, AMF encoding, or
  long-running GPU stability. Default production fallback behavior is unchanged.
- `muxmender-dv-preview.exe` maps parsed per-frame Dolby Vision metadata through
  libplacebo/D3D11 and writes an explicitly selected SDR BT.709 diagnostic.
  Only single-layer profile 5 is accepted. Missing frame metadata fails closed.
  It preserves dimensions, uses 16-bit RGB rendering and 10-bit YUV 4:4:4 FFV1,
  and does not include audio/subtitles. FFV1 is lossless for the converted SDR
  frames; the HDR-to-SDR conversion itself is not lossless or HDR-preserving.
  This is intentionally not a space-saving delivery format.

## Build prerequisites

Development tools: Visual Studio C++ toolchain and Windows SDK, Clang 22.1.3,
CMake, Ninja, Python with Meson. These are not intended end-user requirements;
packaging and runtime dependency/license review remain unfinished.

The vcpkg manifest pins its registry baseline. Install its dependencies for
`x64-windows-release` into `vcpkg_installed` before building. The pkg-config
adapter supplies the static SPIRV-Cross C API and its transitive libraries;
`--dont-define-prefix` prevents incorrect prefix relocation.

Expected upstream source: https://code.videolan.org/videolan/libplacebo
at commit `3330a515d62139259c26239014f286e233bd3a5c`, with its submodules,
under `build/_deps/libplacebo-src`. No upstream source patch is needed.

Run in the existing VS Code terminal (does not open another window):

```powershell
cd E:\Users\itama\OneDrive\Repos\MuxMender\native\muxmender-d3d11
.\build-native.ps1 -Test
```

The script performs no installation, Git operation, or media modification.
Override `-VisualStudioPath` and `-Python` for other development machines.
For just the already-built generated-color test:

```powershell
.\build\preview\muxmender-color-test.exe
```

## Verified locally on 2026-09-04

Clang build: libplacebo 7.371.0, D3D11 and built-in Dolby Vision support enabled;
Vulkan/OpenGL disabled. Generated SDR test passed on AMD Radeon RX 7800 XT,
D3D11 feature level 12_1, with maximum channel error 0/255.

The profile 5 source provided for testing produced 72 frames at 3832x1600,
23.976 fps, 3.003 seconds, with BT.709 tags. Full decode validation succeeded.
The first output frame was visually inspected: natural skin tones and yellow
uniforms, without the purple cast. This is not a calibrated color-quality test.

## Diagnostic preview usage

From the repository root, using the existing CLI (dry run is the default):

```powershell
python muxmender.py 'SOURCE.mkv' --dolby-vision-policy sdr-preview --dolby-preview-backend d3d11 --preview-seconds 3 --output-dir 'PREVIEW-DIRECTORY'
# Add --execute to generate; native progress is inherited by the same terminal.
```

This explicit CLI backend only accepts a single selected file. It rejects
delete/overwrite/resize options, runs the synthetic preflight before execution,
and verifies output dimensions, codec, duration and SDR tags afterwards.
Preflight is limited to 30 seconds; the preview process to 120 seconds.
The normal optimization path and VS Code extension defaults are unchanged.

```powershell
.\build\preview\muxmender-dv-preview.exe --input 'SOURCE.mkv' --output 'NEW-preview.mkv' --start 300 --seconds 3 --sdr-preview --dry-run
# Remove only --dry-run to generate the preview with terminal progress.
```

Duration is limited to 1..10 seconds. Dry run probes the source but does not
initialize the GPU or create output. Existing outputs are rejected before
reading input, and Windows CREATE_NEW provides an additional atomic no-clobber
check. Original media is opened only for reading. No delete/move/rename API is
used. Failed partial outputs are retained, so choose a new output name to retry.
Tests use and clean up only their own generated text fixtures, never user media.

AMF encoding, extension integration, installer packaging, and HDR output
are not implemented by this diagnostic. Hardware encoding still requires
separate controlled validation; do not interpret this color test as AMF success.

## Standalone HDR delivery test

The separate `--native-delivery-test` workflow now combines reconstruction,
audio/subtitle copying, HEVC encoding, decoding validation, and comparison.
No VS Code installation or extension is required. From the repository root:

```powershell
python -u muxmender.py 'SOURCE.mkv' --native-delivery-test --dolby-vision-policy hdr-preview --dolby-preview-backend d3d11 --preview-start 300 --preview-seconds 10 --hardware amd --hardware-fallback never --resolution keep --output-dir test-output
# Review the dry-run plan, then add --execute to run with terminal progress.
```

This is a bounded 1–10 second, single-layer Dolby Vision profile 5 test, not a
full-library conversion mode. Choosing HDR preview explicitly discards Dolby
Vision dynamic metadata in favor of reconstructed BT.2020/PQ video. It does
not claim identical Dolby Vision playback. Audio/subtitle packet data and
timestamps are checked against the aligned reference; original dimensions
are preserved. All intermediates and failed outputs are retained in a unique
run directory with `validation.json`. No original is replaced or removed.

`--hardware amd` requires AMF. `--hardware auto` requests GPU-first selection;
`--hardware-fallback ask` offers an interactive CPU retry after encoder failure.
CPU encoding still requires the D3D11 color stage for this particular workflow.
Missing dependencies are reported; driver installation is never automatic.
FFmpeg and FFprobe CLI executables are separate requirements. The local runtime
can be bundled using `python native/muxmender-d3d11/package-runtime.py`, then
selected with `--d3d11-helper PATH-TO/muxmender-dv-preview.exe`.

Size comparison reads a padded packet interval and filters by presentation
timestamp to avoid missing reordered frames at seek boundaries. Savings are
reported only when source/output packet counts and normalized presentation
timestamps match. The percentage measures compressed video payload, not whole
container size. SSIM compares the encoded result to the reconstructed PQ
reference after chroma matching; it is not proof of perceptually identical
quality. Playback review remains necessary.
