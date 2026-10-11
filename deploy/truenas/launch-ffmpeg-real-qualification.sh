#!/bin/bash
set -euo pipefail
stage=/mnt/FR4G/Apps/muxmender/output/ffmpeg-real-qualification-20261010-r1
image=muxmender-ffmpeg9-full-qualification:20261010-r5
name=muxmender-ffmpeg-real-qualification-r1
[[ $EUID -eq 0 ]] || { echo 'Run with sudo'; exit 1; }
cd "$stage"
sha256sum -c payload.sha256
docker image inspect "$image" >/dev/null
docker inspect "$name" >/dev/null 2>&1 && { echo 'Container exists; inspect before retry'; exit 1; }
[[ ! -e "$stage/work/results" ]] || { echo 'Results exist; refusing overwrite'; exit 1; }
media=$(docker inspect --format '{{range .Mounts}}{{if eq .Destination "/media"}}{{.Source}}{{end}}{{end}}' ix-muxmender-muxmender-1)
output=$(docker inspect --format '{{range .Mounts}}{{if eq .Destination "/output"}}{{.Source}}{{end}}{{end}}' ix-muxmender-muxmender-1)
[[ -n "$media" && -d "$media" && -n "$output" && -d "$output" ]] || { echo 'Existing mounts unavailable'; exit 1; }
mapfile -t devices < <(nvidia-smi --query-gpu=uuid --format=csv,noheader)
[[ ${#devices[@]} -eq 1 && ${devices[0]} == GPU-* ]] || { echo 'Explicit GPU assignment required'; exit 1; }
mkdir -p "$stage/work"
chown 3005:3005 "$stage/work"
chmod 750 "$stage/work"
docker run -d --pull=never --name "$name" --read-only --init --network none \
  --cap-drop ALL --security-opt no-new-privileges --memory 16g --cpus 4 \
  --gpus "device=${devices[0]}" --env NVIDIA_DRIVER_CAPABILITIES=compute,video,utility,graphics \
  --env TMPDIR=/work --mount "type=bind,src=$stage/work,dst=/work" \
  --mount "type=bind,src=$media,dst=/media,readonly" \
  --mount "type=bind,src=$output,dst=/output,readonly" \
  --mount "type=bind,src=$stage/qualify_ffmpeg_real.py,dst=/qualification.py,readonly" \
  --tmpfs /tmp:rw,noexec,nosuid,size=256m --entrypoint python3 "$image" \
  -B /qualification.py --output /work/results \
  --request-id 8b624ee9896249ba80ba2b50245ea42b \
  --request-id d19fadde64654397bb74c9a448071b14 \
  --request-id d0c66bc626524d2aa574aead5e33b507 \
  --request-id d26cd398f5e64ab9880f465fbb8759cc
echo 'Started eight serial full-source evaluations. Originals are read-only; production unchanged.'
