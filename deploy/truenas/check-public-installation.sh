#!/usr/bin/env bash
set -euo pipefail
stage=/mnt/FR4G/Apps/muxmender/public-materials-20261011-r1
image=sha256:38ef3df0b98396f8d58bdb83dbbd8d5a142370ab2012d953a84e18f54fff850e
[[ $(id -u) = 0 ]] || { echo 'Run with sudo.' >&2; exit 1; }
if [[ ${1:-} != --run ]]; then
  systemd-run --unit=muxmender-public-materials-20261011-r1 --collect --no-block \
    /usr/bin/bash "$stage/check-public-installation.sh" --run
  echo "Isolated checks started. Status: $stage/result.txt"
  exit 0
fi
exec > >(tee -a "$stage/checks.log") 2>&1
trap 'code=$?; if [[ "$code" != 0 ]]; then printf "status=failed\nexit_code=%s\n" "$code" > "$stage/result.txt"; fi' EXIT
phase() { printf 'status=running\nphase=%s\n' "$1" > "$stage/result.txt"; }
work=$(mktemp -d "$stage/work-XXXXXX")
chmod 755 "$work"
mkdir -m 755 "$work/install"
chown 568:568 "$work/install"
phase 'Installation on generated media using old image'
old_image=$(docker inspect --format '{{.Image}}' ix-muxmender-muxmender-1)
docker run --rm --network none --cpus 2 --memory 12g \
  --mount "type=bind,src=$stage,dst=/release-tools,readonly" \
  --mount "type=bind,src=$work/install,dst=/work" --entrypoint python3 \
  "$old_image" -B /release-tools/check_public_installation.py initialize --work /work
phase 'Upgrade check with retained history and generated source'
docker run --rm --network none --cpus 2 --memory 12g \
  --mount "type=bind,src=$stage,dst=/release-tools,readonly" \
  --mount "type=bind,src=$work/install,dst=/work" --entrypoint python3 \
  "$image" -B /release-tools/check_public_installation.py upgrade --work /work
phase 'Collecting exact Ubuntu sources and license notices'
# Root is limited to this disposable container; only its new work directory is writable.
docker run --rm --user 0:0 --cpus 2 --memory 2g \
  --mount "type=bind,src=$stage,dst=/release-tools,readonly" \
  --mount "type=bind,src=/mnt/FR4G/Apps/muxmender/public-image-20261011-r1/context-4980287067e6-hofcUG,dst=/build-context,readonly" \
  --mount "type=bind,src=$work,dst=/work" --entrypoint python3 \
  "$image" -B /release-tools/collect_release_sources.py --destination /work/materials
chmod -R a+rX "$work"
printf 'status=passed\nphase=Installation checks and source collection finished\nwork=%s\n' "$work" > "$stage/result.txt"
echo 'Source collection is not completed legal clearance. Nothing published or deployed.'
