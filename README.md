# F2L Downloader (PC Edition)

**Fast · Reliable · Simple**

A high-performance Windows download manager with a sleek Liquid Glass dark UI and multi-threaded segmented downloads (2–16 parallel connection threads).

---

## Features
- **Multi-Threaded Segmented Engine**: Split files into 2 to 16 byte-range connections for maximum download speeds.
- **Liquid Glass Dark UI**: Custom-tailored dark theme matching the original F2L aesthetic with frosted cards and progress bars.
- **Full Download Control**: Pause, resume, auto-retry, and cancel downloads.
- **Live Metrics**: Real-time speed (MB/s), ETA counter, and bytes progress.
- **Status Tabs**: All, Active, Completed, Failed, and Settings.
- **One-Click Actions**: Directly open downloaded files or show them in Windows File Explorer.
- **Windows Setup Wizard**: Ready-to-install `F2LDownloader_Setup.exe` with desktop shortcut and uninstaller.

---

## Running and Installing

### 1. Run Setup Wizard
Double click:
`F2LDownloader_Setup.exe` (in `installer_output/` or in your `Downloads` folder).
Follow the setup wizard to install it to your PC.

### 2. Run Directly from Source (Developer Mode)
```cmd
cd F2LDownloader-PC
python app.py
```

### 3. Rebuilding the Installer
Simply double-click:
`build.bat`
Or run:
```cmd
python -m PyInstaller --noconfirm --onedir --windowed --name "F2LDownloader" --collect-all customtkinter app.py
"C:\Users\Goutham Josh\AppData\Local\Programs\Inno Setup 6\ISCC.exe" installer.iss
```
The resulting installer will be generated in `installer_output/F2LDownloader_Setup.exe`.

---

## Developed by
**Goutham Josh** — [github.com/GouthamSER](https://github.com/GouthamSER)
