#!/usr/bin/env bash
set -euo pipefail
if [ "$(id -u)" != 0 ]; then echo 'Run this script with sudo bash.' >&2; exit 1; fi
build_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
source_dir='/mnt/FR4G/Media/Animation/Example_HDR_Film'
source_name='Example_HDR_Film.2020.HDR.2160p.WEB-DL.x265-ROCCaT.mkv'
encoded_dir='/mnt/FR4G/Apps/muxmender/output/hdr10plus-nvidia-full-20260919-134128-57025c3f'
encoded_name='encoded-before-hdr10plus-restoration.mkv'
test -f "$source_dir/$source_name"
test -f "$encoded_dir/$encoded_name"
test -f "$encoded_dir/encoding-result.json"
if [ "$(uname -m)" != x86_64 ]; then echo 'This package is built for x86_64.' >&2; exit 1; fi
image='muxmender-hdr10plus-test:20260919-standalone1'
docker build -f "$build_dir/Dockerfile" -t "$image" "$build_dir"
run_name="muxmender-hdr10plus-$(date +%Y%m%d-%H%M%S)-$$"
output_dir="/mnt/FR4G/Apps/muxmender/output/$run_name"
if [ -e "$output_dir" ]; then echo 'Output already exists; refusing reuse.' >&2; exit 1; fi
install -d -o 3005 -g 3005 -m 0770 "$output_dir"
docker run -d --name "$run_name" --user 3005:3005 --network none \
  --read-only --cap-drop ALL --security-opt no-new-privileges \
  --cpus 4 --memory 6g --pids-limit 256 --tmpfs /tmp:rw,nosuid,nodev,size=256m \
  --mount "type=bind,src=$source_dir,dst=/source,readonly" \
  --mount "type=bind,src=$encoded_dir,dst=/encoded,readonly" \
  --mount "type=bind,src=$output_dir,dst=/output" \
  "$image" --source "/source/$source_name" --encoded "/encoded/$encoded_name" \
  --output-dir /output --timeout 21600
echo "Started: $run_name"
echo "Output: $output_dir"
echo "Follow logs: sudo docker logs -f $run_name"
echo 'This detached job survives shell disconnection. No source replacement or deletion is enabled.'
