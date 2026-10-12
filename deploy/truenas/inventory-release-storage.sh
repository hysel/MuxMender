#!/usr/bin/env bash
# Read-only preparation. No prune, removal, app restart or configuration changes.
set -euo pipefail
base=/mnt/FR4G/Apps/muxmender
echo 'Container references (including stopped containers):'
docker ps -a --no-trunc --format '{{.ID}} {{.Names}} {{.Image}} {{.Status}}'
echo 'Resolved image references:'
while IFS= read -r container; do
  [[ -n "$container" ]] || continue
  docker inspect --format '{{.Name}} {{.Image}} {{.State.Running}}' "$container"
done < <(docker ps -aq)
echo 'Image tags and logical sizes (layers may be shared):'
docker image ls --no-trunc --format '{{.Repository}}:{{.Tag}} {{.ID}} {{.Size}}'
echo 'Docker storage summary:'
docker system df
echo 'Known release/research staging folders, not production media or output:'
shopt -s nullglob
folders=("$base"/public-image-* "$base"/public-security-* "$base"/public-copy-lifecycle-* \
         "$base"/public-cancellation-* "$base"/public-materials-*)
if [[ ${#folders[@]} -gt 0 ]]; then du -sh -- "${folders[@]}"; fi
echo 'Inventory only. No cleanup performed; publication and exact-target review are required.'
