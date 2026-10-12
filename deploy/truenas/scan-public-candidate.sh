#!/usr/bin/env bash
set -euo pipefail
stage=/mnt/FR4G/Apps/muxmender/public-security-20261011-r1
image=sha256:48a3b7a7b3f516225a9c98f7f025d5746ea23579ff4f57aa99864d833fe64b03
scanner_sha=c6e65abddb348e25f10549df887045629cf28cc72453cd1c63acb717316b3f3f
[[ $(id -u) = 0 ]] || { echo 'Run with sudo.' >&2; exit 1; }
printf '%s  %s\n' "$scanner_sha" "$stage/trivy_0.75.0_Linux-64bit.tar.gz" | sha256sum -c -
if [[ ${1:-} != --run ]]; then
  systemd-run --unit=muxmender-public-security-20261011-r1 --collect --no-block \
    /usr/bin/bash "$stage/scan-public-candidate.sh" --run
  echo "Isolated scan started. Status: $stage/result.txt"
  exit 0
fi
exec > >(tee -a "$stage/scan.log") 2>&1
trap 'code=$?; if [[ "$code" != 0 ]]; then printf "status=failed\nexit_code=%s\n" "$code" > "$stage/result.txt"; fi' EXIT
phase() { printf 'status=running\nphase=%s\n' "$1" > "$stage/result.txt"; }
work=$(mktemp -d "$stage/work-XXXXXX")
chmod 755 "$work"
mkdir -m 755 "$work/input" "$work/tools" "$work/results"
chown 568:568 "$work/results"
phase 'Exporting the exact tested candidate image'
actual=$(docker image inspect --format '{{.Id}}' "$image")
[[ "$actual" = "$image" ]] || exit 2
docker image inspect "$image" > "$work/input/image-inspect.json"
docker save --output "$work/input/image.tar" "$image"
chmod a+r "$work/input/image.tar"
tar -xzf "$stage/trivy_0.75.0_Linux-64bit.tar.gz" -C "$work/tools" trivy
chmod 555 "$work/tools/trivy"
phase 'Generating software inventory and vulnerability report'
# Scanner sees only an exported archive, never the Docker socket or media mounts.
docker run --rm --user 568:568 --cpus 2 --memory 4g --read-only \
  --cap-drop ALL --security-opt no-new-privileges:true --tmpfs /tmp:rw,size=1g \
  --mount "type=bind,src=$work/input,dst=/scan-input,readonly" \
  --mount "type=bind,src=$work/tools,dst=/scan-tools,readonly" \
  --mount "type=bind,src=$work/results,dst=/scan-output" \
  --entrypoint /scan-tools/trivy "$image" image --input /scan-input/image.tar \
  --cache-dir /scan-output/cache --timeout 30m --scanners vuln --format cyclonedx \
  --output /scan-output/image.cdx.json
phase 'Writing detailed security findings'
docker run --rm --user 568:568 --cpus 2 --memory 4g --read-only \
  --cap-drop ALL --security-opt no-new-privileges:true --tmpfs /tmp:rw,size=1g \
  --mount "type=bind,src=$work/input,dst=/scan-input,readonly" \
  --mount "type=bind,src=$work/tools,dst=/scan-tools,readonly" \
  --mount "type=bind,src=$work/results,dst=/scan-output" \
  --entrypoint /scan-tools/trivy "$image" image --input /scan-input/image.tar \
  --cache-dir /scan-output/cache --timeout 30m --scanners vuln --format json \
  --output /scan-output/vulnerabilities.json
chmod -R a+rX "$work/results"
printf 'status=passed\nphase=Security scan completed; findings need review\nwork=%s\nimage=%s\nscanner_sha256=%s\n' \
  "$work" "$image" "$scanner_sha" > "$stage/result.txt"
echo 'Scan completion is not a clean-security or release-approval claim. No publication or production changes.'
