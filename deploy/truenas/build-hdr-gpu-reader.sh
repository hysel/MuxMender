#!/usr/bin/env bash
set -euo pipefail
stage="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
destination="$stage/binary-r3"
if [[ -e "$destination" ]]; then
  echo 'Research binary destination already exists; inspect it before rebuilding.' >&2
  exit 1
fi
cd -- "$stage"
sha256sum -c context.sha256
docker build --progress=plain --file Dockerfile.hdr-gpu-reader \
  --output "type=local,dest=$destination" .
chmod 755 "$destination" "$destination/bin" "$destination/bin/ffprobe-cuda"
echo "Research binary ready: $destination/bin/ffprobe-cuda"
echo 'The installed app, queue, media files and host driver were not changed.'
