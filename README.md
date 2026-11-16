# paket-winlator

Bundler otomatis untuk menggabungkan komponen runtime Winlator (`rootfs`, `rootfs_patches`, `container_pattern`, `box64`, `turnip`, `vortek`, `gladio`, `dxvk`, `vkd3d`, `wine_addons`, dan metadata) menjadi satu arsip `.zip` siap import di Android.

## Output Paket

Workflow GitHub Actions menghasilkan:
- `paket-winlator-bundle.zip`
- `paket-winlator-bundle.zip.sha256`

Di dalam arsip `.zip` tersedia:
- `rootfs/` (base rootfs + patch + Box64 + Turnip default)
- `container_pattern/` (template `.wine` container)
- `dxwrapper/` (`dxvk-2.6.1`, `dxvk-2.4.1`, `dxvk-1.10.3`, `vkd3d-3.0b`, `vkd3d-2.14.1`, `d7vk-1.11`, `d8vk-1.0`, `cnc-ddraw-6.6`)
- `graphics_driver/` (`turnip-26.2.0`, `vortek-2.1`, `gladio-1.1`, `zink-22.2.5`, `virgl-23.1.9`)
- `meta/` & `wine_addons/` (`common_dlls.json`, `gpu_cards.json`, `default.box64rc`, `wine-gecko`, `wine-mono`)
- `symlinks.tsv`, `executables.txt`, dan `runtime_manifest.json` untuk pemulihan symlink serta permission di Android.
