#!/usr/bin/env bash
set -euo pipefail
test "$(id -u)" = 0 || { echo 'Run with sudo bash.'; exit 1; }
context=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
source_dir='/mnt/FR4G/Media/Animation/Example_HDR_Film 1993'
source_name='Example_HDR_Film.1993.2160p.uhd.bluray.x265-b0mbardiers.mkv'
test -f "$source_dir/$source_name"
docker image inspect muxmender-hdr10plus-test:20260919-standalone1 >/dev/null
docker build -t muxmender-hdr10-test:20260919-2 "$context"
name="muxmender-hdr10-$(date +%Y%m%d-%H%M%S)-$$"
output="/mnt/FR4G/Apps/muxmender/output/$name"
test ! -e "$output"
install -d -o 3005 -g 3005 -m 0770 "$output"
docker run -d --name "$name" --user 3005:3005 --network none --gpus "${MUXMENDER_GPU_REQUEST:-all}" \
  --read-only --cap-drop ALL --security-opt no-new-privileges --cpus 4 --memory 6g \
  --pids-limit 256 --tmpfs /tmp:rw,nosuid,nodev,size=256m \
  --mount "type=bind,src=$source_dir,dst=/source,readonly" \
  --mount "type=bind,src=$output,dst=/output" \
  muxmender-hdr10-test:20260919-2 --source "/source/$source_name" --output-dir /output
echo "Started: $name"
echo "Output: $output"
echo "Follow logs: sudo docker logs -f $name"
echo 'Detached test; originals are read-only. The main app is unchanged.'
