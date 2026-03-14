# nomadicml-mcp.spec
# Used by PyInstaller to build the standalone binary.
# Run with: pyinstaller nomadicml-mcp.spec

import sys
import platform

# Platform-specific binary name
p = sys.platform
a = platform.machine().lower()
if p == "darwin" and a == "arm64":
    binary_name = "nomadicml-mcp-darwin-arm64"
elif p == "darwin":
    binary_name = "nomadicml-mcp-darwin-x64"
elif p == "linux":
    binary_name = "nomadicml-mcp-linux-x64"
elif p == "win32":
    binary_name = "nomadicml-mcp-win32-x64"
else:
    binary_name = "nomadicml-mcp"

a = Analysis(
    ["src/nomadicml_mcp/server.py"],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        "nomadicml",
        "nomadicml.video",
        "mcp",
        "mcp.server",
        "mcp.server.fastmcp",
        "httpx",
        "tenacity",
        "anyio",
        "anyio._backends._asyncio",
        "anyio._backends._trio",
    ],
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
    name=binary_name,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
