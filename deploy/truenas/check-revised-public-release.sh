#!/usr/bin/env bash
# Isolated final checks only; never deploy, publish, prune or mount library media.
set -euo pipefail
stage=/mnt/FR4G/Apps/muxmender/public-final-checks-20261012-r1
image=sha256:e57d69f29e4c6d144cce5a3ab0be79f3afc56d165a4d8f35d89acd3760a2a9ec
context=/mnt/FR4G/Apps/muxmender/public-image-20261012-r1/context-01e7c685f3a3-Qr5osA
[[ $(id -u) = 0 ]] || { echo 'Run with sudo.' >&2; exit 1; }
[[ $# = 0 || ( $# = 1 && $1 = --run ) ]] || exit 2
if [[ ${1:-} != --run ]]; then
  systemd-run --unit=muxmender-public-final-checks-20261012-r1 --collect --no-block \
    /usr/bin/bash "$stage/check-revised-public-release.sh" --run
  echo "Isolated revised-image checks started. Status: $stage/result.txt"
  exit 0
fi
exec > >(tee -a "$stage/checks.log") 2>&1
trap 'code=$?; if [[ "$code" != 0 ]]; then printf "status=failed\nexit_code=%s\n" "$code" > "$stage/result.txt"; fi' EXIT
phase() { printf 'status=running\nphase=%s\n' "$1" > "$stage/result.txt"; }
idle() {
  python3 - <<'PY'
import json,subprocess,urllib.error,urllib.request
try:
    data=json.load(urllib.request.urlopen('http://truenas:8767/api/controls',timeout=15))
except urllib.error.URLError:
    state=subprocess.check_output(['docker','inspect','--format','{{.State.Running}}',
                                   'ix-muxmender-muxmender-1'],text=True,timeout=15).strip()
    assert state=='false', 'Production activity cannot be verified; no isolated GPU work started'
else:
    assert isinstance(data.get('jobs'),list) and not data.get('snapshot_stale') and not data.get('snapshot_error')
    assert not any(j.get('state') in ('running','queued','pending') for j in data['jobs']), 'Production work present'
PY
}
[[ $(docker image inspect --format '{{.Id}}' "$image") = "$image" ]] || exit 2
[[ -d "$context/vendor/ffmpeg9-source" ]] || exit 2
work=$(mktemp -d "$stage/work-XXXXXX")
chmod 755 "$work"
for kind in copy cancel; do
  phase "Checking production idle before generated $kind workflow"
  idle
  mkdir -m 755 "$work/$kind"
  chown 568:568 "$work/$kind"
  phase "Running revised-image generated $kind workflow"
  docker run --rm --network none --gpus all --cpus 2 --memory 12g \
    --mount "type=bind,src=$stage,dst=/release-tools,readonly" \
    --mount "type=bind,src=$work/$kind,dst=/work" --entrypoint /usr/bin/tini \
    "$image" -- python3 -B /release-tools/check_public_installation.py "initialize-$kind" --work /work
  phase "Checking revised-image $kind history after recreation"
  docker run --rm --network none --cpus 2 --memory 12g \
    --mount "type=bind,src=$stage,dst=/release-tools,readonly" \
    --mount "type=bind,src=$work/$kind,dst=/work" --entrypoint /usr/bin/tini \
    "$image" -- python3 -B /release-tools/check_public_installation.py "upgrade-$kind" --work /work
done
phase 'Collecting exact Ubuntu sources and license notices'
# Changes apt only inside a disposable container, never on the TrueNAS host.
docker run --rm --user 0:0 --cpus 2 --memory 2g \
  --mount "type=bind,src=$stage,dst=/release-tools,readonly" \
  --mount "type=bind,src=$context,dst=/build-context,readonly" \
  --mount "type=bind,src=$work,dst=/work" --entrypoint /usr/bin/tini \
  "$image" -- python3 -B /release-tools/collect_release_sources.py --destination /work/materials
phase 'Recording read-only storage inventory for later cleanup review'
bash "$stage/inventory-release-storage.sh" > "$work/storage-inventory.txt"
chmod -R a+rX "$work"
printf 'status=passed\nphase=Revised lifecycle checks and source collection finished\nwork=%s\nimage=%s\n' \
  "$work" "$image" > "$stage/result.txt"
echo 'Source completeness and license compatibility still need review. No publication, deployment or cleanup performed.'
