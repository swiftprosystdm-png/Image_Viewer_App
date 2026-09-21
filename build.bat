@echo off
setlocal

echo ============================================================
echo  SPS TDM IMAGE VIEWER - EXE + INSTALLER BUILDER
echo ============================================================
echo.

REM Make sure we run from the folder this .bat file is in
cd /d "%~dp0"

echo [1/4] Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo [ERROR] Python was not found in PATH.
    echo Please install Python 3.10+ from https://python.org and try again.
    pause
    exit /b 1
)

echo [2/4] Installing/updating required packages...
python -m pip install --upgrade pip >nul
python -m pip install PyQt6 cryptography numpy requests Pillow pyinstaller
if errorlevel 1 (
    echo.
    echo [ERROR] Failed to install dependencies. Check your internet connection.
    pause
    exit /b 1
)

echo.
echo [3/4] Building the standalone .exe (this can take a few minutes)...
echo.
python build_exe.py

if not exist "dist\SPS_TDM_Image_Viewer.exe" (
    echo.
    echo [WARNING] .exe build failed or was not found in dist\.
    echo Scroll up for the PyInstaller error output.
    pause
    exit /b 1
)

echo.
echo [4/4] Building the Windows installer (optional - needs Inno Setup)...
echo.

REM Locate Inno Setup's command-line compiler (ISCC.exe) as thoroughly as
REM possible, since it can end up in several different places depending on
REM the Inno Setup version and how/where it was installed:
REM   1. The standard Program Files locations, for v7, v6 and v5
REM   2. Already on PATH (e.g. user added it manually)
REM   3. Wherever Inno Setup's own installer recorded itself in the registry
set "ISCC="
if exist "%ProgramFiles%\Inno Setup 7\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 7\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles(x86)%\Inno Setup 7\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 7\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles(x86)%\Inno Setup 5\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 5\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 5\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 5\ISCC.exe"

if not defined ISCC (
    for /f "delims=" %%P in ('where ISCC.exe 2^>nul') do if not defined ISCC set "ISCC=%%P"
)

if not defined ISCC (
    for /f "tokens=2,*" %%A in ('reg query "HKLM\SOFTWARE\WOW6432Node\JRSoftware\Inno Setup 7_is1" /v "InstallLocation" 2^>nul ^| find "InstallLocation"') do (
        if exist "%%B\ISCC.exe" set "ISCC=%%B\ISCC.exe"
    )
)
if not defined ISCC (
    for /f "tokens=2,*" %%A in ('reg query "HKLM\SOFTWARE\JRSoftware\Inno Setup 7" /v "InstallLocation" 2^>nul ^| find "InstallLocation"') do (
        if exist "%%B\ISCC.exe" set "ISCC=%%B\ISCC.exe"
    )
)
if not defined ISCC (
    for /f "tokens=2,*" %%A in ('reg query "HKLM\SOFTWARE\WOW6432Node\JRSoftware\Inno Setup 6_is1" /v "InstallLocation" 2^>nul ^| find "InstallLocation"') do (
        if exist "%%B\ISCC.exe" set "ISCC=%%B\ISCC.exe"
    )
)
if not defined ISCC (
    for /f "tokens=2,*" %%A in ('reg query "HKLM\SOFTWARE\JRSoftware\Inno Setup 6" /v "InstallLocation" 2^>nul ^| find "InstallLocation"') do (
        if exist "%%B\ISCC.exe" set "ISCC=%%B\ISCC.exe"
    )
)

if defined ISCC (
    "%ISCC%" "SPS_TDM_Viewer_Setup.iss"
    echo.
    echo ============================================================
    if exist "Output\SPS_TDM_Image_Viewer_Setup.exe" (
        echo [DONE] Installer created:
        echo   %cd%\Output\SPS_TDM_Image_Viewer_Setup.exe
        echo This single file installs the app on ANY Windows 7/8/10/11 PC.
    ) else (
        echo [WARNING] Installer build did not produce the expected file.
    )
    echo ============================================================
) else (
    echo Inno Setup's compiler ^(ISCC.exe^) was not found automatically.
    echo Your standalone app .exe is still ready to use:
    echo   %cd%\dist\SPS_TDM_Image_Viewer.exe
    echo.
    echo If Inno Setup IS installed on this PC but in a non-standard folder,
    echo you can still build the installer manually - this always works
    echo regardless of where it's installed:
    echo   1. Open the Start Menu, search "Inno Setup Compiler", open it.
    echo   2. File ^> Open... and select:
    echo      %cd%\SPS_TDM_Viewer_Setup.iss
    echo   3. Click Build ^> Compile ^(or press Ctrl+F9^).
    echo   4. The installer appears at:
    echo      %cd%\Output\SPS_TDM_Image_Viewer_Setup.exe
    echo.
    echo If Inno Setup is NOT installed, get it free from:
    echo   https://jrsoftware.org/isdl.php
    echo Then just re-run this build.bat, or use the manual steps above.
)

echo.
echo ============================================================
echo  WHICH FILE TO SHARE WITH OTHERS
echo ============================================================
if exist "Output\SPS_TDM_Image_Viewer_Setup.exe" (
    echo Share THIS file - it installs the app like a normal Windows
    echo program ^(Start Menu shortcut, Control Panel uninstall entry^):
    echo.
    echo   %cd%\Output\SPS_TDM_Image_Viewer_Setup.exe
) else (
    echo No installer was built this time, so all you have is the plain
    echo standalone .exe below. Sharing THIS file does NOT add a Start
    echo Menu entry and does NOT show up in Control Panel to uninstall -
    echo it just runs directly, like a portable app:
    echo.
    echo   %cd%\dist\SPS_TDM_Image_Viewer.exe
    echo.
    echo For the full install experience ^(Start Menu + Control Panel
    echo uninstall^), install Inno Setup from https://jrsoftware.org/isdl.php
    echo and re-run build.bat.
)
echo ============================================================
echo.
pause

REM ============================================================
REM  STEP 5: PUBLISH RELEASE TO GITHUB (for Check for Updates)
REM ============================================================
REM
REM  This step uploads the built installer (or standalone .exe)
REM  to a GitHub Release so that the in-app "Check for Updates"
REM  button can detect and download it automatically.
REM
REM  REQUIREMENTS:
REM    - GitHub CLI (gh) installed: https://cli.github.com
REM    - Already logged in:  gh auth login
REM    - GitHub repo:  sarathimurugan247-spec/Image_Viewer_App
REM
REM  HOW TO SET THE VERSION:
REM    Edit the VERSION= line below before running build.bat.
REM    It must match APP_VERSION in viewer_app.py and
REM    CURRENT_APP_VERSION in updater.py  (e.g. v1.1 / v2.0)
REM ============================================================

set "VERSION=vBeta"
set "GITHUB_REPO=Astalakshmi18/Image_Viewer_App"

echo.
echo ============================================================
echo  [5/5] Publishing GitHub Release %VERSION% for Check for Updates...
echo ============================================================
echo.

REM Check if GitHub CLI is available
gh --version >nul 2>&1
if errorlevel 1 (
    echo [SKIP] GitHub CLI ^(gh^) is not installed on this PC.
    echo        The .exe was built successfully but NOT uploaded to GitHub.
    echo.
    echo  To enable the in-app "Check for Updates" to detect new versions:
    echo    1. Install GitHub CLI from: https://cli.github.com
    echo    2. Run:  gh auth login
    echo    3. Re-run build.bat
    echo.
    goto :end
)

REM Decide which file to upload: installer is preferred, else standalone exe
set "UPLOAD_FILE="
if exist "Output\SPS_TDM_Image_Viewer_Setup.exe" (
    set "UPLOAD_FILE=Output\SPS_TDM_Image_Viewer_Setup.exe"
) else if exist "dist\SPS_TDM_Image_Viewer.exe" (
    set "UPLOAD_FILE=dist\SPS_TDM_Image_Viewer.exe"
)

if not defined UPLOAD_FILE (
    echo [SKIP] No built .exe found to upload. Skipping GitHub release.
    goto :end
)

echo Uploading: %UPLOAD_FILE%
echo  To repo : %GITHUB_REPO%
echo  Tag     : %VERSION%
echo.

REM Create the GitHub release and upload the file in one command.
REM --clobber replaces asset if the same tag already exists.
gh release create "%VERSION%" "%UPLOAD_FILE%" ^
    --repo "%GITHUB_REPO%" ^
    --title "SPS TDM Image Viewer %VERSION%" ^
    --notes "SPS TDM Image Viewer %VERSION% - New release.%NL%Users with the app installed will be notified automatically via Check for Updates." ^
    --clobber

if errorlevel 1 (
    echo.
    echo [WARNING] GitHub release upload failed.
    echo  - Make sure you are logged in:  gh auth login
    echo  - Make sure the repo exists:  https://github.com/%GITHUB_REPO%
    echo  - Make sure you have push access to the repo.
) else (
    echo.
    echo [DONE] GitHub Release %VERSION% published successfully!
    echo  In-app "Check for Updates" will now detect this version.
    echo  Release URL: https://github.com/%GITHUB_REPO%/releases/tag/%VERSION%
)

:end
echo.
pause