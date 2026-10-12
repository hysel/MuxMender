#!/usr/bin/env bash
# Export only the tested image. No credentials, push, build, restart or pruning.
set -euo pipefail
stage=/mnt/FR4G/Apps/muxmender/public-image-export-20261012-r1
image=sha256:20bceb9acd80f3bcf9e6a81312f4eede6d576b06fab978ab48e5da48f10c8c04
[[ $(id -u) == 0 ]] || { echo 'Run with sudo.' >&2; exit 1; }
[[ $# == 0 || ( $# == 1 && $1 == --run ) ]] || exit 2
if [[ ${1:-} != --run ]]; then
  systemd-run --unit=muxmender-public-export-20261012-r1 --collect --no-block \
    /usr/bin/bash "$stage/export-qualified-public-image.sh" --run
  echo "Export started; status: $stage/result.txt"
  exit 0
fi
exec > >(tee -a "$stage/export.log") 2>&1
trap 'code=$?; if [[ $code != 0 ]]; then printf "status=failed\nexit_code=%s\n" "$code" > "$stage/result.txt"; fi' EXIT
[[ $(docker image inspect --format '{{.Id}}' "$image") == "$image" ]] || exit 2
printf 'status=running\nphase=Exporting already-qualified image\n' > "$stage/result.txt"
[[ ! -e "$stage/qualified-image.tar" && ! -e "$stage/qualified-image.tar.partial" ]] || {
  echo 'An export already exists. Inspect it before retrying.' >&2; exit 1;
}
docker image save --output "$stage/qualified-image.tar.partial" "$image"
mv "$stage/qualified-image.tar.partial" "$stage/qualified-image.tar"
chmod 644 "$stage/qualified-image.tar"
checksum=$(sha256sum "$stage/qualified-image.tar" | cut -d ' ' -f1)
printf 'status=passed\nphase=Qualified image exported\nimage_id=%s\narchive_sha256=%s\n' "$image" "$checksum" > "$stage/result.txt"
echo 'Export complete. Nothing published or deployed; no login required.'
