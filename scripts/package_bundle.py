#!/usr/bin/env python3
import hashlib
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def extract_tzst(archive_path: Path, dest_dir: Path) -> None:
    if not archive_path.is_file():
        raise FileNotFoundError(f"Missing archive: {archive_path}")
    dest_dir.mkdir(parents=True, exist_ok=True)
    run(["tar", "--zstd", "--overwrite", "-xf", str(archive_path), "-C", str(dest_dir)])


def is_elf_file(path: Path) -> bool:
    try:
        with path.open("rb") as f:
            return f.read(4) == b"\x7fELF"
    except OSError:
        return False


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: package_bundle.py <winlator_src_dir> <out_dir>", file=sys.stderr)
        return 1

    winlator_dir = Path(sys.argv[1]).resolve()
    out_dir = Path(sys.argv[2]).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    assets_dir = winlator_dir / "app" / "app" / "src" / "main" / "assets"
    installable_dir = winlator_dir / "installable_components"

    if not assets_dir.is_dir():
        raise RuntimeError(f"Winlator assets directory not found: {assets_dir}")

    commit_sha = subprocess.check_output(
        ["git", "-C", str(winlator_dir), "rev-parse", "HEAD"], text=True
    ).strip()

    staging = out_dir / "staging"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True, exist_ok=True)

    rootfs_dir = staging / "rootfs"
    extract_tzst(assets_dir / "rootfs.tzst", rootfs_dir)
    if (assets_dir / "rootfs_patches.tzst").is_file():
        extract_tzst(assets_dir / "rootfs_patches.tzst", rootfs_dir)

    box64_archive = installable_dir / "box64" / "box64-0.4.5.tzst"
    box64_version = "0.4.5"
    if not box64_archive.is_file():
        box64_archive = assets_dir / "box64" / "box64-0.4.4.tzst"
        box64_version = "0.4.4"
    extract_tzst(box64_archive, rootfs_dir)

    turnip_default = assets_dir / "graphics_driver" / "turnip-26.2.0.tzst"
    if turnip_default.is_file():
        extract_tzst(turnip_default, rootfs_dir)

    container_pattern_dir = staging / "container_pattern"
    extract_tzst(assets_dir / "container_pattern.tzst", container_pattern_dir)

    dxwrapper_out = staging / "dxwrapper"
    dxwrapper_out.mkdir(parents=True, exist_ok=True)
    dxwrapper_versions = []

    dx_archives = [
        ("dxvk-2.6.1", installable_dir / "dxvk" / "dxvk-2.6.1.tzst"),
        ("dxvk-2.4.1", assets_dir / "dxwrapper" / "dxvk-2.4.1.tzst"),
        ("dxvk-1.10.3", assets_dir / "dxwrapper" / "dxvk-1.10.3.tzst"),
        ("vkd3d-3.0b", installable_dir / "vkd3d" / "vkd3d-3.0b.tzst"),
        ("vkd3d-2.14.1", assets_dir / "dxwrapper" / "vkd3d-2.14.1.tzst"),
        ("d7vk-1.11", assets_dir / "dxwrapper" / "d7vk-1.11.tzst"),
        ("d8vk-1.0", assets_dir / "dxwrapper" / "d8vk-1.0.tzst"),
    ]
    for name, arch in dx_archives:
        if arch.is_file():
            extract_tzst(arch, dxwrapper_out / name)
            dxwrapper_versions.append(name)

    cnc_ddraw_dir = assets_dir / "dxwrapper" / "cnc-ddraw-6.6"
    if cnc_ddraw_dir.is_dir():
        shutil.copytree(cnc_ddraw_dir, dxwrapper_out / "cnc-ddraw-6.6", symlinks=True)
        dxwrapper_versions.append("cnc-ddraw-6.6")

    drv_out = staging / "graphics_driver"
    drv_out.mkdir(parents=True, exist_ok=True)
    driver_versions = []
    for drv_file in sorted((assets_dir / "graphics_driver").glob("*.tzst")):
        drv_name = drv_file.stem
        extract_tzst(drv_file, drv_out / drv_name)
        driver_versions.append(drv_name)

    meta_out = staging / "meta"
    meta_out.mkdir(parents=True, exist_ok=True)
    for meta_name in [
        "common_dlls.json",
        "gpu_cards.json",
        "wine_debug_channels.json",
        "wine_startmenu.json",
        "gamepad_models.json",
    ]:
        src_file = assets_dir / meta_name
        if src_file.is_file():
            shutil.copy2(src_file, meta_out / meta_name)

    for box_cfg in ["default.box64rc", "env_vars.json"]:
        src_cfg = assets_dir / "box64" / box_cfg
        if src_cfg.is_file():
            shutil.copy2(src_cfg, meta_out / box_cfg)

    addons_src = winlator_dir / "wine_addons"
    if addons_src.is_dir():
        shutil.copytree(addons_src, staging / "wine_addons", symlinks=True)

    symlinks: list[tuple[str, str]] = []
    executables: list[str] = []
    regular_files: list[Path] = []
    empty_dirs: list[str] = []
    uncompressed_bytes = 0

    for root, dirs, files in os.walk(staging, followlinks=False):
        root_path = Path(root)
        keep_dirs = []
        for d in dirs:
            full_d = root_path / d
            rel_d = full_d.relative_to(staging).as_posix()
            if os.path.islink(full_d):
                symlinks.append((rel_d, os.readlink(full_d)))
                full_d.unlink()
            else:
                keep_dirs.append(d)
                if not any(full_d.iterdir()):
                    empty_dirs.append(rel_d + "/")
        dirs[:] = keep_dirs

        for f in files:
            full_f = root_path / f
            rel_f = full_f.relative_to(staging).as_posix()
            if os.path.islink(full_f):
                symlinks.append((rel_f, os.readlink(full_f)))
                full_f.unlink()
            elif full_f.is_file():
                st = full_f.lstat()
                uncompressed_bytes += st.st_size
                if (st.st_mode & 0o111) != 0 or is_elf_file(full_f):
                    executables.append(rel_f)
                regular_files.append(full_f)

    symlinks.sort(key=lambda item: item[0])
    executables.sort()
    empty_dirs.sort()

    symlinks_file = staging / "symlinks.tsv"
    with symlinks_file.open("w", encoding="utf-8", newline="\n") as f:
        for rel_path, target in symlinks:
            f.write(f"{rel_path}\t{target}\n")

    exec_file = staging / "executables.txt"
    with exec_file.open("w", encoding="utf-8", newline="\n") as f:
        for rel_path in executables:
            f.write(f"{rel_path}\n")

    manifest = {
        "schemaVersion": 1,
        "sourceRepo": "brunodev85/winlator",
        "sourceCommit": commit_sha,
        "components": {
            "box64": box64_version,
            "dxwrapper": dxwrapper_versions,
            "graphicsDrivers": driver_versions,
        },
        "fileCount": len(regular_files),
        "symlinkCount": len(symlinks),
        "executableCount": len(executables),
        "uncompressedBytes": uncompressed_bytes,
    }
    manifest_file = staging / "runtime_manifest.json"
    manifest_file.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    bundle_path = out_dir / "paket-winlator-bundle.zip"
    if bundle_path.exists():
        bundle_path.unlink()

    all_to_zip = sorted(regular_files + [symlinks_file, exec_file, manifest_file])
    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for dir_arc in empty_dirs:
            zf.writestr(zipfile.ZipInfo(dir_arc), b"")
        for file_path in all_to_zip:
            arcname = file_path.relative_to(staging).as_posix()
            zf.write(file_path, arcname=arcname)

    sha256 = hashlib.sha256()
    with bundle_path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            sha256.update(chunk)
    digest = sha256.hexdigest()
    (out_dir / "paket-winlator-bundle.zip.sha256").write_text(
        f"{digest}  paket-winlator-bundle.zip\n", encoding="utf-8"
    )

    shutil.rmtree(staging)
    print(json.dumps(manifest, indent=2))
    print(f"Created {bundle_path} ({bundle_path.stat().st_size} bytes), sha256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
