"""Bundle an already-built runtime locally. No downloads or existing-file writes."""
import hashlib
import json
import shutil
import time
import uuid
from pathlib import Path


def main():
    root = Path(__file__).resolve().parent
    build = root / "build" / "preview"
    names = ["muxmender-dv-preview.exe", "muxmender-color-test.exe", "muxmender-d3d11.exe"]
    files = [build / name for name in names] + sorted(build.glob("*.dll"))
    if not all(p.is_file() for p in files) or not list(build.glob("libplacebo-*.dll")):
        raise SystemExit("Build the native runtime first with build-native.ps1 -Test")
    licenses = sorted((root / "vcpkg_installed" / "x64-windows-release" / "share").glob("*/copyright"))
    placebo_license = root / "build" / "_deps" / "libplacebo-src" / "LICENSE"
    if not licenses or not placebo_license.is_file():
        raise SystemExit("Dependency license files are missing; refusing incomplete bundle")
    target = root / "dist" / ("runtime-" + time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8])
    target.mkdir(parents=True, exist_ok=False)
    notices = target / "licenses"
    notices.mkdir()
    for source in files:
        shutil.copy2(source, target / source.name)
    for source in licenses:
        shutil.copy2(source, notices / (source.parent.name + ".txt"))
    shutil.copy2(placebo_license, notices / "libplacebo.txt")
    sources = target / "build-instructions"
    sources.mkdir()
    for name in ("README.md", "build-native.ps1", "vcpkg.json", "CMakeLists.txt", "meson-clang.ini"):
        if (root / name).is_file():
            shutil.copy2(root / name, sources / name)
    shutil.copytree(root / "src", sources / "src")
    manifest = {
        "scope": "Unsigned local testing bundle; not a public release or self-updating installer",
        "libplacebo_source": "https://code.videolan.org/videolan/libplacebo",
        "libplacebo_commit": "3330a515d62139259c26239014f286e233bd3a5c",
        "ffmpeg_cli": "Install separately; native DLLs do not provide the ffmpeg/ffprobe commands",
        "requirements": "Windows x64, working Direct3D 11 driver; run color-test before real media. Missing runtime DLL errors require dependency diagnosis, not automatic driver replacement.",
        "distribution": "Before public redistribution, review all notices and corresponding-source obligations; this local bundle is not a claim of distribution compliance.",
        "sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
    }
    with (target / "runtime.json").open("x", encoding="utf-8") as out:
        json.dump(manifest, out, indent=2)
    archive = shutil.make_archive(str(target), "zip", target)
    print(f"Runtime: {target}\nArchive: {archive}\nOriginals and earlier builds retained.")


if __name__ == "__main__":
    main()
