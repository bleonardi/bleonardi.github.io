"""
Creates a macOS .app bundle for site_editor.py (SiteVoice).
Run once: python3 create_app.py
Then find SiteVoice.app in ~/Applications and drag to your Dock.
"""
import os
import stat
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

TOOLS_DIR   = Path(__file__).parent.resolve()
SITE_ROOT   = TOOLS_DIR.parent
APP_NAME    = "SiteVoice"
APPS_DIR    = Path.home() / "Applications"
APPS_DIR.mkdir(exist_ok=True)
APP_PATH    = APPS_DIR / f"{APP_NAME}.app"
MAIN_SCRIPT = TOOLS_DIR / "site_editor.py"

# Prefer the Python.framework install (has PySide6); fall back to whatever's running
def _find_python() -> str:
    import subprocess, shutil
    for candidate in [
        "/Library/Frameworks/Python.framework/Versions/3.14/bin/python3",
        "/Library/Frameworks/Python.framework/Versions/3.13/bin/python3",
        "/opt/homebrew/bin/python3",
    ]:
        if Path(candidate).exists():
            r = subprocess.run([candidate, "-c", "import PySide6"], capture_output=True)
            if r.returncode == 0:
                return candidate
    return sys.executable

PYTHON_PATH = _find_python()

# Palette matches bleonardi.github.io design tokens
ACCENT = (122, 92, 46)    # #7a5c2e  antique gold
WHITE  = (255, 255, 255)


def make_icon_png(size: int) -> Image.Image:
    pad    = max(2, size // 16)
    inner  = size - 2 * pad
    img    = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw   = ImageDraw.Draw(img)
    radius = max(4, size // 8)
    draw.rounded_rectangle(
        [pad, pad, pad + inner, pad + inner], radius=radius, fill=ACCENT
    )

    font_size = int(inner * 0.62)
    font_path = TOOLS_DIR / "assets" / "fonts" / "SourceSerif4-SemiBold.ttf"
    try:
        font = ImageFont.truetype(str(font_path), font_size)
    except Exception:
        font = ImageFont.load_default()

    letter = "S"
    bbox   = draw.textbbox((0, 0), letter, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    tx = (size - tw) / 2 - bbox[0]
    ty = (size - th) / 2 - bbox[1] - int(inner * 0.03)
    draw.text((tx, ty), letter, font=font, fill=WHITE)
    return img


def build_iconset(iconset_dir: Path):
    iconset_dir.mkdir(parents=True, exist_ok=True)
    sizes = [16, 32, 64, 128, 256, 512, 1024]
    for s in sizes:
        make_icon_png(s).save(iconset_dir / f"icon_{s}x{s}.png")
        if s * 2 in sizes:
            make_icon_png(s * 2).save(iconset_dir / f"icon_{s}x{s}@2x.png")


def build_icns(dest: Path) -> bool:
    iconset = TOOLS_DIR / "AppIcon.iconset"
    build_iconset(iconset)
    result = subprocess.run(
        ["iconutil", "-c", "icns", str(iconset), "-o", str(dest)],
        capture_output=True,
    )
    shutil.rmtree(iconset, ignore_errors=True)
    return result.returncode == 0


def build_app():
    if APP_PATH.exists():
        shutil.rmtree(APP_PATH)

    macos_dir     = APP_PATH / "Contents" / "MacOS"
    resources_dir = APP_PATH / "Contents" / "Resources"
    macos_dir.mkdir(parents=True)
    resources_dir.mkdir(parents=True)

    # Launcher shell script
    launcher = macos_dir / "SiteVoice"
    launcher.write_text(f"""\
#!/bin/bash
# exec replaces bash with Python so macOS tracks the right PID as the app process.
# arch -arm64 forces the arm64 slice of the universal Python binary.
export PATH="{Path(PYTHON_PATH).parent}:/opt/homebrew/bin:$PATH"
cd "{TOOLS_DIR}"
exec arch -arm64 "{PYTHON_PATH}" "{MAIN_SCRIPT}"
""")
    launcher.chmod(launcher.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    # Icon
    icns_path = resources_dir / "AppIcon.icns"
    icon_ok   = build_icns(icns_path)
    icon_key  = "<string>AppIcon</string>" if icon_ok else "<string></string>"

    # Info.plist
    (APP_PATH / "Contents" / "Info.plist").write_text(f"""\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>{APP_NAME}</string>
    <key>CFBundleDisplayName</key>
    <string>{APP_NAME}</string>
    <key>CFBundleIdentifier</key>
    <string>com.bleonardi.sitevoice</string>
    <key>CFBundleVersion</key>
    <string>1.0</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleExecutable</key>
    <string>SiteVoice</string>
    <key>CFBundleIconFile</key>
    {icon_key}
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>LSMinimumSystemVersion</key>
    <string>11.0</string>
    <key>NSRequiresAquaSystemAppearance</key>
    <false/>
</dict>
</plist>
""")

    print(f"✓ Created: {APP_PATH}")
    print(f"  Icon:    {'yes' if icon_ok else 'no (iconutil failed — PIL may be missing)'}")
    print()
    print("Next steps:")
    print("  • Find it in ~/Applications and drag to your Dock")
    print("  • Or: open ~/Applications and double-click to launch")


if __name__ == "__main__":
    build_app()
