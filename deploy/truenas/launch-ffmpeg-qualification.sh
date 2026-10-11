#!/bin/bash
set -euo pipefail
stage=/mnt/FR4G/Apps/muxmender/output/ffmpeg-upgrade-native-20261010-r1
app=ix-muxmender-muxmender-1
container=muxmender-ffmpeg9-qualification
image=muxmender-ffmpeg9-qualification:20261010-r1
[[ $EUID -eq 0 ]] || { echo 'Run this isolated test launcher with sudo'; exit 1; }
cd "$stage"
sha256sum -c context.sha256
docker inspect "$container" >/dev/null 2>&1 && { echo 'Qualification container already exists; inspect its results first'; exit 1; }
[[ ! -e "$stage/work/results" ]] || { echo 'Qualification results already exist; refusing to overwrite'; exit 1; }
media=$(docker inspect --format '{{range .Mounts}}{{if eq .Destination "/media"}}{{.Source}}{{end}}{{end}}' "$app")
[[ "$media" == /mnt/* && -d "$media" ]] || { echo 'Installed media mount is unavailable'; exit 1; }
base=$(docker inspect --format '{{.Image}}' "$app")
alias=muxmender-ffmpeg9-base:20261010-r1
docker image tag "$base" "$alias"
trap 'docker image rm "$alias" >/dev/null 2>&1 || true' EXIT
mapfile -t devices < <(nvidia-smi --query-gpu=uuid --format=csv,noheader)
[[ ${#devices[@]} -eq 1 && ${devices[0]} == GPU-* ]] || { echo 'Expected one visible GPU; explicit assignment is required for multi-GPU hosts'; exit 1; }
mkdir -p "$stage/work"
chown 3005:3005 "$stage/work"
chmod 750 "$stage/work"
docker build --pull=false --build-arg "BASE_IMAGE=$alias" -f Dockerfile.ffmpeg-qualification -t "$image" .
docker run -d --name "$container" --read-only --cap-drop ALL --security-opt no-new-privileges --memory 8g --cpus 2 \
  --gpus "device=${devices[0]}" --env NVIDIA_DRIVER_CAPABILITIES=compute,video,utility \
  --mount "type=bind,src=$media,dst=/media,readonly" \
  --mount type=bind,src=/mnt/FR4G/Apps/muxmender/output,dst=/output,readonly \
  --mount "type=bind,src=$stage/work,dst=/work" \
  --tmpfs /tmp:rw,noexec,nosuid,size=256m \
  "$image" --output /work/results --candidate-bin /opt/ffmpeg9/bin
echo 'Isolated qualification started. The app, driver, queue and originals were not changed.'
