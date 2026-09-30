"""
build_exe.py - Standalone Executable Builder for SPS TDM Image Viewer.
Builds a single, standalone Windows executable (.exe) with embedded icon,
theme styling, brand logo, and the keyboard-shortcuts reference file.
"""

import os
import sys
import subprocess

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ICO_PATH = os.path.join(BASE_DIR, "Swift_Prosys.ico")
LOGO_PATH = os.path.join(BASE_DIR, "Swift-ProSys-Logo.png")
SHORTCUTS_PATH = os.path.join(BASE_DIR, "Keyboard_Shortcuts.txt")
ENTRY_POINT = os.path.join(BASE_DIR, "viewer_app.py")
EXE_NAME = "SPS_TDM_Image_Viewer"


def _kill_running_instances():
    """Ensure no previous instance of the .exe is running and locking the file."""
    try:
        subprocess.run(
            ["taskkill", "/F", "/IM", f"{EXE_NAME}.exe", "/T"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    except Exception:
        pass


def build():
    print("=" * 60)
    print(" BUILDING SPS TDM IMAGE VIEWER STANDALONE EXE")
    print("=" * 60)

    # 1. Close any running instances locking dist\SPS_TDM_Image_Viewer.exe
    _kill_running_instances()

    # 2. Validate prerequisites
    if not os.path.exists(ENTRY_POINT):
        print(f"Error: Entry point not found: {ENTRY_POINT}")
        sys.exit(1)
    if not os.path.exists(ICO_PATH):
        print(f"Warning: Icon file not found: {ICO_PATH}")
    if not os.path.exists(SHORTCUTS_PATH):
        print(f"Warning: Keyboard_Shortcuts.txt not found: {SHORTCUTS_PATH}")

    # Check if target dist exe is still locked
    # NOTE: --onedir puts the exe inside dist\<EXE_NAME>\<EXE_NAME>.exe
    # (not directly in dist\ like --onefile did).
    dist_exe = os.path.join(BASE_DIR, "dist", EXE_NAME, f"{EXE_NAME}.exe")
    if os.path.exists(dist_exe):
        try:
            with open(dist_exe, "a+b"):
                pass
        except PermissionError:
            print(f"[ERROR] '{dist_exe}' is currently locked by another program.")
            print("Please close any open instances of the Image Viewer and try again.")
            sys.exit(1)

    # 3. Build PyInstaller command line
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onedir",
        "--windowed",
        f"--name={EXE_NAME}",
        f"--icon={ICO_PATH}",
        f"--add-data={ICO_PATH};.",
        f"--add-data={LOGO_PATH};.",
        f"--add-data={SHORTCUTS_PATH};.",
        "--hidden-import=cryptography",
        "--hidden-import=PyQt6",
        "--hidden-import=requests",
        # Pillow loads several image-format plugins (JPEG 2000/openjpeg,
        # WebP, etc.) as dynamic binary libraries at runtime, which
        # PyInstaller's default import scan can miss - that's what caused
        # ".jp2 files fail to open" on a different PC even though it
        # worked when run as a plain Python script here. --collect-all
        # forces every one of Pillow's binaries, data files, and
        # submodules into the exe, making it fully self-contained.
        "--collect-all=PIL",
        ENTRY_POINT
    ]

    print("Running command:")
    print(" ".join(cmd))
    print("-" * 60)

    result = subprocess.run(cmd, cwd=BASE_DIR)
    if result.returncode != 0:
        print("\n[FAILED] PyInstaller build failed with exit code:", result.returncode)
        sys.exit(result.returncode)

    dist_exe = os.path.join(BASE_DIR, "dist", EXE_NAME, f"{EXE_NAME}.exe")
    if os.path.exists(dist_exe):
        size_mb = os.path.getsize(dist_exe) / (1024 * 1024)
        print("\n" + "=" * 60)
        print("[SUCCESS] Build completed successfully!")
        print(f"Executable: {dist_exe}")
        print(f"(folder: {os.path.dirname(dist_exe)})")
        print(f"Exe Size: {size_mb:.2f} MB")
        print("=" * 60)
    else:
        print("\n[WARNING] dist exe not found at expected location:", dist_exe)


if __name__ == "__main__":
    build()
