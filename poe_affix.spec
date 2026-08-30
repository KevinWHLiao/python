# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_all, collect_submodules

ctk_datas, ctk_binaries, ctk_hiddenimports = collect_all("customtkinter")

a = Analysis(
    ["poe_affix_gui.py"],
    pathex=[],
    binaries=ctk_binaries,
    datas=[
        ("poe_affix_data/mods.json", "poe_affix_data"),
        ("poe_affix_data/mods_poe2.json", "poe_affix_data"),
        ("poe_affix_data/crafting.json", "poe_affix_data"),
        ("poe_affix_data/vendor.json", "poe_affix_data"),
        ("poe_affix_data/names_zh.json", "poe_affix_data"),
        ("poe_affix_data/league_starters.json", "poe_affix_data"),
        *ctk_datas,
    ],
    hiddenimports=collect_submodules("poe_affix") + ctk_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="PoE查詢工具",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
