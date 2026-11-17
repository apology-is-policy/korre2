# Provenance

The player code at the repo root (`CMakeLists.txt`, `main.cpp`, `src/`, `include/`, `pffft/`, `imtui/`,
`LICENSE`, `readme.md`) was imported unchanged on 2026-11-17 from

    https://github.com/apology-is-policy/korre
    commit e26b3fc340036a9543d89f841db7ff0827fd729c (2024-02-11, "Update .gitignore"), 31 commits

Left out of the import: the IDE settings folder (`.idea/`) and upstream's `.gitignore`, whose rules were
merged into this repo's. Everything else is byte-for-byte the upstream tree at that commit.

Vendored third-party code inside it: `imtui/` (ggerganov/imtui with Dear ImGui, patched upstream in
commits 0a0d89b, b4e1199 and 400a76b), `pffft/`, and `src/decoders/minimp3*.h`.
Licence: GPL-3.0 (`LICENSE`).
