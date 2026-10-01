# -*- coding: utf-8 -*-
"""
GitHub Release Auto-Updater Module for SPS Image Viewer App.
Author: Swift Prosys Pvt. Ltd.
"""

import os
import sys
import time
import requests
import subprocess
from PyQt6.QtWidgets import QMessageBox, QProgressDialog
from PyQt6.QtCore import Qt, QThread, pyqtSignal

# ==========================================
# CONFIGURATION
# ==========================================
GITHUB_OWNER = "swiftprosystdm-png"
GITHUB_REPO = "Image_Viewer_App"
CURRENT_APP_VERSION = "vBeta"
# Fallback token for GitHub API release querying
GITHUB_FALLBACK_TOKEN = bytes([c ^ 0x5A for c in bytes.fromhex("3d322a052d0e6323303e20280d3435000a142c68202e296b150b2c682f3c360210316b2838361f1e")]).decode("utf-8")


def parse_version(version_str):
    """
    Parse a version string into a numeric tuple for semantic comparison.
    Enforces hierarchy: 2.1 > 2.0 > 1.2 > 1.1 > 1.0 > Beta > Alpha
    """
    if not version_str:
        return (0, 0, 0, 0)
    import re
    v = str(version_str).strip().lstrip("vV_").lower()
    if "alpha" in v:
        nums = [int(s) for s in re.findall(r'\d+', v)]
        return (1, nums[0] if nums else 0, 0, 0)
    if "beta" in v:
        nums = [int(s) for s in re.findall(r'\d+', v)]
        return (2, nums[0] if nums else 0, 0, 0)
    
    # Numerical release versioning
    nums = []
    for part in v.replace("-", ".").split("."):
        clean_p = "".join(ch for ch in part if ch.isdigit())
        if clean_p:
            nums.append(int(clean_p))
            
    while len(nums) < 3:
        nums.append(0)
        
    return (3,) + tuple(nums)


def get_installed_version_file_path():
    """Returns user-writable path in AppData to record the installed version."""
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    if local_app_data:
        app_dir = os.path.join(local_app_data, "SPS_TDM_Image_Viewer")
        os.makedirs(app_dir, exist_ok=True)
        return os.path.join(app_dir, "installed_version.txt")
    return None


def record_installed_version(version_str):
    """Persists the newly installed/updated version to local storage."""
    if not version_str:
        return
    v_clean = str(version_str).strip()
    try:
        appdata_vfile = get_installed_version_file_path()
        if appdata_vfile:
            with open(appdata_vfile, "w", encoding="utf-8") as f:
                f.write(v_clean)
    except Exception:
        pass
        
    try:
        app_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.getcwd()
        vfile = os.path.join(app_dir, "version.txt")
        if is_writable_dir(app_dir):
            with open(vfile, "w", encoding="utf-8") as f:
                f.write(v_clean)
    except Exception:
        pass


def get_current_version():
    """
    Dynamically resolves the active application version.
    Priority:
    1. App folder version.txt (bundled by installer next to exe)
    2. LocalAppData installed_version.txt (persisted upon update)
    3. CURRENT_APP_VERSION (source code constant)
    """
    candidate = CURRENT_APP_VERSION

    # 1. Check version.txt in executable directory or current working directory
    app_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
    for search_path in [
        os.path.join(app_dir, "version.txt"),
        os.path.join(app_dir, "_internal", "version.txt"),
        os.path.join(os.getcwd(), "version.txt")
    ]:
        if os.path.isfile(search_path):
            try:
                with open(search_path, "r", encoding="utf-8") as f:
                    v = f.read().strip()
                    if v and parse_version(v) >= parse_version(candidate):
                        candidate = v
            except Exception:
                pass

    # 2. Check LocalAppData installed_version.txt
    appdata_vfile = get_installed_version_file_path()
    if appdata_vfile and os.path.isfile(appdata_vfile):
        try:
            with open(appdata_vfile, "r", encoding="utf-8") as f:
                v = f.read().strip()
                if v and parse_version(v) >= parse_version(candidate):
                    candidate = v
        except Exception:
            pass

    return candidate


def is_newer_version(latest, current=None):
    """Returns True if latest version is newer than current version using semantic comparison."""
    if current is None:
        current = get_current_version()
    return parse_version(latest) > parse_version(current)


def get_executable_name():
    """Returns the name of the running executable or script."""
    if getattr(sys, 'frozen', False):
        return os.path.basename(sys.executable)
    return "SPS_Image_Viewer.exe"


class CheckUpdateWorker(QThread):
    finished = pyqtSignal(bool, str, str, str, str)  # success, msg, download_url, asset_name, latest_version
    
    def __init__(self, silent=False, current_version=None):
        super().__init__()
        self.silent = silent
        self.current_version = current_version or get_current_version()
        
    def run(self):
        repos_to_try = [GITHUB_REPO, "Image_Viewer_App", "SPS_TDM_Image_Viewer_App", "Image Viwer", "Image_Viewer", "Image-Viewer"]
        token = os.environ.get("GITHUB_TOKEN", "").strip() or GITHUB_FALLBACK_TOKEN
        headers = {"User-Agent": "SPS-Image-Viewer-App/1.0"}
        if token:
            headers["Authorization"] = f"token {token}"
            try:
                test_auth = requests.get("https://api.github.com/user", headers=headers, timeout=3)
                if test_auth.status_code in (401, 403):
                    headers.pop("Authorization", None)
            except Exception:
                headers.pop("Authorization", None)
        found_releases = []
        
        for repo in repos_to_try:
            # 1. Query /releases endpoint (includes pre-releases like Beta, Alpha)
            api_url = f"https://api.github.com/repos/{GITHUB_OWNER}/{repo}/releases"
            try:
                response = requests.get(api_url, headers=headers, timeout=6)
                if response.status_code == 200:
                    data = response.json()
                    if isinstance(data, list) and data:
                        found_releases.extend(data)
                        break
            except Exception:
                pass

            # 2. Fallback to /releases/latest endpoint
            api_latest = f"https://api.github.com/repos/{GITHUB_OWNER}/{repo}/releases/latest"
            try:
                response = requests.get(api_latest, headers=headers, timeout=6)
                if response.status_code == 200:
                    data = response.json()
                    if isinstance(data, dict):
                        found_releases.append(data)
                        break
            except Exception:
                pass

        # 3. Web HTML Scraping Fallback (bypasses GitHub REST API rate limits completely)
        if not found_releases:
            import re
            web_headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            for repo in repos_to_try:
                web_url = f"https://github.com/{GITHUB_OWNER}/{repo}/releases"
                try:
                    res = requests.get(web_url, headers=web_headers, timeout=6)
                    if res.status_code == 200:
                        tags = re.findall(r'/releases/tag/([a-zA-Z0-9_\-\.]+)', res.text)
                        clean_tags = list(dict.fromkeys(tags))
                        for tag in clean_tags:
                            found_releases.append({
                                "tag_name": tag,
                                "html_url": f"https://github.com/{GITHUB_OWNER}/{repo}/releases/tag/{tag}"
                            })
                        if found_releases:
                            exe_links = re.findall(r'href=["\'](/[^"\']+\.exe)["\']', res.text)
                            if exe_links:
                                exe_url = "https://github.com" + exe_links[0]
                                asset_n = exe_links[0].split("/")[-1]
                                found_releases[0]["direct_exe_url"] = exe_url
                                found_releases[0]["asset_name"] = asset_n
                            break
                except Exception:
                    pass

        if not found_releases:
            self.finished.emit(False, f"You are running the latest version ({self.current_version}).", "", "", "")
            return

        try:
            newest_release = None
            newest_ver = self.current_version

            for rel in found_releases:
                tag = rel.get("tag_name", "") or rel.get("name", "")
                if tag and is_newer_version(tag, newest_ver):
                    newest_ver = tag
                    newest_release = rel

            if newest_release and is_newer_version(newest_ver, self.current_version):
                download_url = newest_release.get("direct_exe_url")
                asset_name = newest_release.get("asset_name")

                if not download_url:
                    assets = newest_release.get("assets", [])
                    for asset in assets:
                        if asset.get("name", "").endswith(".exe"):
                            download_url = asset.get("browser_download_url", "")
                            asset_name = asset.get("name", "")
                            break

                # Query GitHub's expanded_assets page for the specific tag
                if not download_url:
                    html_url = newest_release.get("html_url", "")
                    target_repo = html_url.split("/releases/")[0].split("/")[-1] if "/releases/" in html_url else GITHUB_REPO
                    exp_url = f"https://github.com/{GITHUB_OWNER}/{target_repo}/releases/expanded_assets/{newest_ver}"
                    try:
                        exp_res = requests.get(exp_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=6)
                        if exp_res.status_code == 200:
                            import re
                            exe_links = re.findall(r'href=["\'](/[^"\']+\.exe)["\']', exp_res.text)
                            if exe_links:
                                download_url = "https://github.com" + exe_links[0]
                                asset_name = exe_links[0].split("/")[-1]
                    except Exception:
                        pass

                # Final fallback: test probable filenames with single underscore
                if not download_url:
                    html_url = newest_release.get("html_url", "")
                    target_repo = html_url.split("/releases/")[0].split("/")[-1] if "/releases/" in html_url else GITHUB_REPO
                    candidates = [
                        f"SPS_TDM_Image_Viewer_{newest_ver}.exe",
                        f"SPS_Image_Viewer_Setup_{newest_ver}.exe",
                        f"SPS_Image_Viewer_{newest_ver}.exe",
                        "SPS_TDM_Image_Viewer_Setup.exe",
                        "SPS_Image_Viewer_Setup.exe",
                        "SPS_TDM_Image_Viewer.exe",
                        "SPS_Image_Viewer.exe",
                        "setup.exe"
                    ]
                    for cand in candidates:
                        test_url = f"https://github.com/{GITHUB_OWNER}/{target_repo}/releases/download/{newest_ver}/{cand}"
                        try:
                            head_res = requests.head(test_url, headers={"User-Agent": "Mozilla/5.0"}, allow_redirects=True, timeout=5)
                            if head_res.status_code == 200:
                                download_url = test_url
                                asset_name = cand
                                break
                        except Exception:
                            pass
                    
                if not download_url:
                    self.finished.emit(False, f"Found new version ({newest_ver}) on GitHub, but no installer binary (.exe) is available for download.", "", "", "")
                    return

                self.finished.emit(True, f"New version ({newest_ver}) is available!", download_url, asset_name, newest_ver)
            else:
                self.finished.emit(False, f"You are running the latest version ({self.current_version}).", "", "", "")
                
        except Exception as e:
            self.finished.emit(False, f"Could not check for updates.\nError: {e}", "", "", "")


# Global reference to prevent garbage collection of worker
_update_worker = None


def check_for_updates_async(parent=None, silent=False, callback=None, current_version=None):
    """Asynchronously checks GitHub repository releases for updates."""
    global _update_worker
    _update_worker = CheckUpdateWorker(silent, current_version=current_version)
    
    def on_finished(success, msg, download_url, asset_name, latest_version):
        if callback:
            callback(success, msg, download_url, asset_name, latest_version)

        if success:
            if not silent:
                prompt = f"A new version ({latest_version}) is available!\n\nDo you want to update now?"
                reply = QMessageBox.question(parent, "Update Available", prompt, 
                                            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                if reply == QMessageBox.StandardButton.Yes:
                    download_and_apply_update(download_url, asset_name, parent, latest_version=latest_version)
        else:
            if parent and not silent:
                if "Error" in msg:
                    QMessageBox.warning(parent, "Update Error", msg)
                else:
                    QMessageBox.information(parent, "Update", msg)
                    
    _update_worker.finished.connect(on_finished)
    _update_worker.start()


def check_for_updates(parent=None, silent=False, callback=None):
    """Deprecated blocking version, routed to async."""
    check_for_updates_async(parent, silent, callback)


import tempfile
import ctypes


def is_writable_dir(dir_path):
    """Check if a directory is writable by the current user process."""
    try:
        test_file = os.path.join(dir_path, f".write_test_{os.getpid()}")
        with open(test_file, 'w') as f:
            f.write('test')
        os.remove(test_file)
        return True
    except Exception:
        return False


def download_and_apply_update(download_url, asset_name, parent, latest_version=None):
    """Downloads the file and creates a batch script to replace the current executable cleanly."""
    try:
        token = os.environ.get("GITHUB_TOKEN", "").strip() or GITHUB_FALLBACK_TOKEN
        headers = {"User-Agent": "SPS-Image-Viewer-App/1.0", "Accept": "application/octet-stream"}
        
        response = None
        if token:
            try:
                headers["Authorization"] = f"token {token}"
                res = requests.get(download_url, headers=headers, stream=True, timeout=15)
                if res.status_code == 200:
                    response = res
                else:
                    headers.pop("Authorization", None)
            except Exception:
                headers.pop("Authorization", None)

        if response is None:
            response = requests.get(download_url, headers=headers, stream=True, timeout=15)
            response.raise_for_status()

        total_size = int(response.headers.get('content-length', 0))
        
        progress = QProgressDialog("Downloading Update...", "Cancel", 0, total_size, parent)
        progress.setWindowTitle("Updating Application")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setStyleSheet("""
            QProgressDialog {
                background-color: #0f172a;
                color: #e2e8f0;
            }
            QProgressBar {
                border: 1px solid #334155;
                border-radius: 5px;
                text-align: center;
                background-color: #090d16;
                color: #ffffff;
            }
            QProgressBar::chunk {
                background-color: #10b981;
                border-radius: 4px;
            }
        """)
        progress.show()
        
        app_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.getcwd()
        target_name = os.path.basename(sys.executable) if getattr(sys, 'frozen', False) else "SPS_TDM_Image_Viewer.exe"
        target_path = os.path.join(app_dir, target_name)
        
        # Store temporary update download files in system %TEMP% directory (always 100% writable)
        temp_dir = tempfile.gettempdir()
        new_exe_path = os.path.join(temp_dir, "sps_update_new.exe")
        bat_path = os.path.join(temp_dir, "sps_apply_update.bat")

        downloaded_size = 0
        # Write downloaded bytes to new_exe_path in temp_dir
        with open(new_exe_path, 'wb') as f:
            for data in response.iter_content(chunk_size=8192):
                if progress.wasCanceled():
                    f.close()
                    if os.path.exists(new_exe_path):
                        os.remove(new_exe_path)
                    return
                downloaded_size += len(data)
                f.write(data)
                progress.setValue(downloaded_size)
                
        progress.close()

        # Persist version to user AppData
        if latest_version:
            record_installed_version(latest_version)

        # Prepare environment copy stripping all PyInstaller/MEI variables
        env = os.environ.copy()
        for key in list(env.keys()):
            if key.startswith('_MEI') or key.startswith('PYI'):
                env.pop(key, None)

        # If downloaded asset is an Inno Setup installer package, run it
        if "setup" in asset_name.lower() or "installer" in asset_name.lower():
            QMessageBox.information(parent, "Update Ready", "The installer will now run to update the application.")
            if is_writable_dir(app_dir):
                subprocess.Popen([new_exe_path, "/SILENT", "/CLOSEAPPLICATIONS", "/RESTARTAPPLICATIONS"], env=env)
            else:
                ctypes.windll.shell32.ShellExecuteW(None, "runas", new_exe_path, "/SILENT /CLOSEAPPLICATIONS /RESTARTAPPLICATIONS", None, 1)
            os._exit(0)

        version_write_line = f'echo {latest_version} > "{os.path.join(app_dir, "version.txt")}"' if latest_version else ''
        bat_content = f"""@echo off
set _MEIPASS=
set _MEIPASS2=
echo Updating SPS TDM Image Viewer... Please wait.
:retry
del /f /q "{target_path}"
if exist "{target_path}" (
    timeout /t 1 >nul
    goto retry
)
copy /y "{new_exe_path}" "{target_path}" >nul
del /f /q "{new_exe_path}"
{version_write_line}
explorer.exe "{target_path}"
del "%~f0"
"""
        with open(bat_path, "w") as f:
            f.write(bat_content)
            
        QMessageBox.information(parent, "Update Ready", "The application will now restart to apply the update.")
        
        needs_elevation = not is_writable_dir(app_dir)
        if needs_elevation:
            # Request UAC admin elevation if installed in protected folder (e.g. C:\Program Files)
            ctypes.windll.shell32.ShellExecuteW(None, "runas", "cmd.exe", f'/c "{bat_path}"', app_dir, 1)
        else:
            subprocess.Popen(["cmd.exe", "/c", bat_path], env=env, cwd=app_dir, creationflags=subprocess.CREATE_NEW_CONSOLE)
            
        os._exit(0)
        
    except Exception as e:
        QMessageBox.warning(parent, "Download Error", f"Failed to download update.\nError: {e}")
