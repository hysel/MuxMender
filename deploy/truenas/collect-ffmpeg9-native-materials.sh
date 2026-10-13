#!/bin/bash
# Exact-image source/notice collection only; no production or media mounts.
set -euo pipefail
stage=/mnt/FR4G/Apps/muxmender/ffmpeg9-native-20261012-r1
image=sha256:067a847ceba0dbd189ad95be8a815442a7373389b9822ad59a888f0b26c020cf
[[ $(id -u) = 0 ]] || { echo 'Run with sudo'; exit 1; }
[[ $# = 0 || ( $# = 1 && $1 = --run ) ]] || exit 2
if [[ ${1:-} != --run ]]; then
 systemd-run --unit=muxmender-ffmpeg9-materials-r1 --collect --no-block /bin/bash "$stage/collect-ffmpeg9-native-materials.sh" --run
 echo "Background source collection started: $stage/materials-result.txt"
 exit 0
fi
exec >> "$stage/materials.log" 2>&1
trap 'code=$?; if [[ $code != 0 ]]; then printf "status=failed\nexit_code=%s\n" "$code" > "$stage/materials-result.txt"; fi' EXIT
printf 'status=running\nphase=Collecting exact-image sources and notices\n' > "$stage/materials-result.txt"
[[ $(docker image inspect --format '{{.Id}}' "$image") = "$image" ]]
printf '%s  %s\n' 6d51e759c51f540ebb1cc4c0669c18263be6ff66465b78c34d453a6967718112 "$stage/candidate.tar" | sha256sum -c -
work=$(mktemp -d "$stage/materials-XXXXXXXX")
chmod 755 "$work"
mkdir "$work/context"
tar --no-same-owner -xf "$stage/candidate.tar" -C "$work/context"
# Include the actual patched reader sources, not an older reader's notices.
mkdir -p "$work/context/vendor/gpu-reader/source"
cp -a "$stage/../output/ffmpeg9-only-20261012/reader-export/source/." "$work/context/vendor/gpu-reader/source/"
docker run --rm --user 0:0 --cpus 2 --memory 2g --mount "type=bind,src=$stage,dst=/release-tools,readonly" --mount "type=bind,src=$work/context,dst=/build-context,readonly" --mount "type=bind,src=$work,dst=/work" --entrypoint /usr/bin/tini "$image" -- python3 -B /release-tools/collect_release_sources.py --destination /work/collected
chmod -R a+rX "$work"
printf 'status=passed\nphase=Source collection complete; review required\nwork=%s\nimage=%s\n' "$work" "$image" > "$stage/materials-result.txt"
