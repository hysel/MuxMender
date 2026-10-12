#!/usr/bin/env bash
# Export the tested image for GitHub publication. Does not build, push or deploy.
set -euo pipefail
stage=/mnt/FR4G/Apps/muxmender/release-stage-20261012-v61
image=sha256:a2cd06a2d83e3a32ed0557edcb3b787cde832c4d8e0dc4e360df69ed848c255c
test "$(id -u)" = 0
if [[ ${1:-} != --run ]]; then
  systemd-run --unit=muxmender-export-20261012-v61 --collect --no-block \
    /usr/bin/bash "$stage/export-v61.sh" --run
  echo 'Export started; no production changes.'
  exit 0
fi
test "$(docker image inspect --format '{{.Id}}' "$image")" = "$image"
grep -qx 'status=passed' "$stage/result.txt"
test "$(cat "$stage/image-id.txt")" = "$image"
test ! -e "$stage/qualified-image.tar"
test ! -e "$stage/qualified-image.tar.partial"
docker image save --output "$stage/qualified-image.tar.partial" "$image"
mv "$stage/qualified-image.tar.partial" "$stage/qualified-image.tar"
chmod 644 "$stage/qualified-image.tar"
sha256sum "$stage/qualified-image.tar" > "$stage/export-sha256.txt"
