#!/usr/bin/env bash
# One-time manual publication. Never builds, deploys, restarts or prunes anything.
set -euo pipefail
set +x # Do not echo registry credentials even if invoked with bash -x.
umask 077
usage() {
  echo 'Usage: sudo bash publish-reviewed-image.sh --context /absolute/reviewed-context --image sha256:HEX [--publish]'
  echo 'Without --publish, only local checks run. Never put registry tokens in arguments.'
}
context=''; image=''; publish=false
while (($#)); do
  case "$1" in
    --context) context="${2:?Missing context}"; shift 2 ;;
    --image) image="${2:?Missing image ID}"; shift 2 ;;
    --publish) publish=true; shift ;;
    --help) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
  esac
done
[[ "$context" == /* && -d "$context" && "$image" =~ ^sha256:[a-f0-9]{64}$ ]] || { usage >&2; exit 2; }
context=$(realpath -e -- "$context")
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
repo_root=$(cd -- "$script_dir/../.." && pwd -P)
command -v python3 >/dev/null
command -v docker >/dev/null
[[ $(docker image inspect --format '{{.Id}}' "$image") == "$image" ]] || { echo 'Exact local image missing' >&2; exit 1; }

# The same material audit is used by Actions and manual publication.
version=$(python3 -B - "$repo_root" "$context" "$image" <<'PY'
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(sys.argv[1]) / 'tools'))
from audit_public_release import audit
root = Path(sys.argv[2])
manifest = json.loads((root / 'public-release.json').read_text())
audit(root, manifest['version'], manifest['revision'])
if manifest.get('qualified_image_id') != sys.argv[3]:
    raise SystemExit('Release review must identify the exact qualified image ID')
if manifest.get('repository') != 'ghcr.io/hysel/muxmender':
    raise SystemExit('Unexpected publication repository')
print(manifest['version'])
PY
)
target="ghcr.io/hysel/muxmender:$version"
temporary=$(mktemp -d /tmp/muxmender-publish-XXXXXXXX)
container=''
cleanup() {
  if [[ -n "$container" ]]; then docker rm "$container" >/dev/null 2>&1 || true; fi
  case "$temporary" in
    /tmp/muxmender-publish-*)
      # Only our newly created private directory, never app/storage mounts.
      rm -rf -- "$temporary" ;;
  esac
}
trap cleanup EXIT
export DOCKER_CONFIG="$temporary/auth"
mkdir -m 700 "$DOCKER_CONFIG"

# Read files from an unstarted disposable container; no GPU or media mounts.
container=$(docker create --network none --entrypoint /bin/true "$image")
docker cp "$container:/opt/muxmender-notices/public-materials" "$temporary/image-materials"
docker cp "$container:/opt/muxmender/app_version.py" "$temporary/app_version.py"
python3 -B - "$context" "$temporary" "$version" <<'PY'
import hashlib, re, sys
from pathlib import Path
context, temporary = map(Path, sys.argv[1:3])
expected = context / 'public-materials'
actual = temporary / 'image-materials'
def files(root):
    result = {}
    for path in root.rglob('*'):
        if path.is_symlink(): raise SystemExit('Linked publication materials are not supported')
        if path.is_file():
            with path.open('rb') as stream:
                result[path.relative_to(root).as_posix()] = hashlib.file_digest(stream, 'sha256').hexdigest()
    return result
if not expected.is_dir() or not files(expected) or files(expected) != files(actual):
    raise SystemExit('Image notices differ from the reviewed materials')
if any('REVIEW-PENDING' in name for name in files(actual)):
    raise SystemExit('Research-only image cannot be published')
match = re.search(r"^VERSION\s*=\s*['\"]([^'\"]+)['\"]", (temporary/'app_version.py').read_text(), re.M)
if not match or match.group(1) != sys.argv[3]:
    raise SystemExit('Image app version does not match the review')
PY
docker rm "$container" >/dev/null
container=''
echo "Local publication checks passed for $target ($image)."
if [[ "$publish" != true ]]; then
  echo 'Nothing uploaded. Use --publish only after explicit publication approval.'
  exit 0
fi
[[ -t 0 ]] || { echo 'Publication requires an interactive terminal for confirmation and credentials' >&2; exit 1; }
read -r -p "Type the exact version $version to approve this public upload: " confirmation
[[ "$confirmation" == "$version" ]] || { echo 'Publication cancelled'; exit 1; }
read -r -p 'GitHub username: ' registry_user
[[ -n "$registry_user" ]] || exit 1
read -r -s -p 'Short-lived GHCR token (hidden): ' registry_token
printf '\n'
printf '%s' "$registry_token" | docker login ghcr.io --username "$registry_user" --password-stdin
unset registry_token
if docker manifest inspect "$target" > "$temporary/manifest.json" 2> "$temporary/manifest-error"; then
  echo 'That release tag exists. It will not be overwritten.' >&2
  exit 1
fi
grep -Eqi 'manifest unknown|manifest_unknown' "$temporary/manifest-error" || {
  cat "$temporary/manifest-error" >&2
  echo 'Could not confirm an unused tag; nothing pushed.' >&2
  exit 1
}
docker tag "$image" "$target"
docker push "$target"
docker logout ghcr.io >/dev/null
echo "Uploaded $target. The installed app and queue were not changed."
echo 'Check GitHub package visibility and verify an anonymous pull before announcing availability.'
