# TrueNAS v28: fewer unnecessary eligibility skips

Version: `20260919-v28`. This package is not a running deployment.

## Changes

- Default VMAF mean/fifth-percentile floors: 90/90; default minimum savings: 10%.
- Preserve 10-bit SDR instead of forcing 8-bit input to encoders. Probe the
  requested depth and dimensions; reject output depth, dimension or timing changes.
- Recover unknown scan type from decoded evidence, retaining full frame validation.
- Preserve trailing JPEG/PNG artwork as attachments, including exact image packet
  hashes, disposition and metadata. Never discard artwork to qualify a file.
- Keep unspecified color properties unspecified. For H.264 only, missing range
  can be resolved using three sampled bitstream-header windows proving absent
  video signal syntax. ITU-T H.264 Annex E specifies inferred limited range in
  this case. This is not a resolution-based BT.709 assumption.
- A bounded metadata-only remux clears encoder-invented color tags on generated
  output. All normal validation follows. Exclusively owned encoder temporaries
  are removed only after structural validation; sources are never in that registry.
- UI auto quality enables bounded retries. AMD/Intel gain the transparent preset;
  NVIDIA gains CQ 20/18 alternatives within the existing extra-trial budget.
- Metadata errors now identify the changed properties instead of just a track number.

## Verification and remaining limits

Read-only audit of last night's 72 unsupported inputs: 51 now pass preflight;
17 still require HDR handling, one has Dolby Vision, three are untagged MPEG-4
Part 2 files without verified range evidence. One additional overnight skip was
already efficient and intentionally remains skipped: 22 of 73 total skips remain.
Eligibility is not a promise of conversion or of any savings.

SDR case A, three shared scenes, AMD HEVC transparent:
mean VMAF 96.029/96.524/96.340; p5 95.357/92.949/95.121;
25.797% aggregate sample savings. Structure, copied tracks and decode passed.
Original hashes checked by the trial workflow. No full movie was replaced.

Generated 10-bit SDR passed AMD HEVC and AV1 preservation and quality checks.
Generated multiple-cover/untagged-color combined case passed image hash and
disposition preservation. AMD AV1 1080p produced 1082 lines in a real test and
was correctly rejected; this restriction is not bypassed or cropped away.

NVIDIA/Intel real 10-bit and color-finalization runtime trials are still required
on the deployment hardware; the four-frame runtime probes do not certify them.
HDR is not evaluated using an SDR quality model or automatically tone-mapped.

Standard: https://www.itu.int/rec/dologin_pub.asp?id=T-REC-H.264-202408-I%21%21PDF-E&lang=e&type=items

## Deployment

Build the staged context with admin Docker access; this does not restart the app:

```sh
sudo docker build -f /mnt/FR4G/Apps/muxmender/app-build-20260919-v28/deploy/truenas/Dockerfile.app -t muxmender-app:20260919-v28 /mnt/FR4G/Apps/muxmender/app-build-20260919-v28
```

Update the TrueNAS app image tag after the build succeeds. Keep the existing
mounts and GPU assignments. Then select the same folder with Retry skipped/failed
files. Do not clear the history ledger: replaced files should remain protected.
