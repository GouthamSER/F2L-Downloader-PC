@echo off
echo ==========================================
echo   Building F2L Downloader for Windows
echo ==========================================

echo [1/2] Packaging standalone executable with PyInstaller...
python -m PyInstaller --noconfirm --onedir --windowed --name "F2LDownloader" --icon=app_icon.ico --add-data "f2l_logo.png;." --add-data "app_icon.ico;." --collect-all customtkinter app.py
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] PyInstaller failed!
    pause
    exit /b %ERRORLEVEL%
)

echo [2/2] Compiling Setup Wizard with Inno Setup...
"C:\Users\Goutham Josh\AppData\Local\Programs\Inno Setup 6\ISCC.exe" installer.iss
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Inno Setup compiler failed!
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo Copying Setup Wizard to Downloads folder...
copy /Y "installer_output\F2LDownloader_Setup.exe" "..\..\F2LDownloader_Setup.exe"

echo ==========================================
echo   SUCCESS!
echo   Installer: installer_output\F2LDownloader_Setup.exe
echo ==========================================
pause
