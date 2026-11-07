"""Baut NeonCut für die Veröffentlichung.

Ergebnis im Ordner  release/ :
  * NeonCut-Setup-<version>.exe     – Installer (braucht Inno Setup 6)
  * NeonCut-Portable-<version>.zip  – entpacken & NeonCut.exe starten

Benutzung:  pip install -r requirements.txt pyinstaller
            python build_exe.py
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PySide6.QtGui import QGuiApplication

HERE = Path(__file__).resolve().parent
BUILD, DIST, RELEASE = HERE / "build", HERE / "dist", HERE / "release"
sys.path.insert(0, str(HERE))
VERSION = re.search(r'VERSION = "([^"]+)"', (HERE / "neoncut.py").read_text(encoding="utf-8")).group(1)


def find_iscc():
    cands = [shutil.which("iscc"),
             Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe",
             Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Inno Setup 6" / "ISCC.exe",
             Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Inno Setup 6" / "ISCC.exe"]
    return next((str(c) for c in cands if c and Path(c).exists()), None)


def main():
    app = QGuiApplication(sys.argv)  # noqa: F841 – für QPixmap
    from ui_kit import app_icon_pixmap
    for d in (BUILD, DIST, RELEASE):
        shutil.rmtree(d, ignore_errors=True)
    BUILD.mkdir()
    RELEASE.mkdir()
    ico = BUILD / "icon.ico"
    app_icon_pixmap(256).save(str(ico))

    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir", "--windowed",
           "--name", "NeonCut", "--icon", str(ico),
           "--distpath", str(DIST), "--workpath", str(BUILD / "pyi"), "--specpath", str(BUILD),
           "--exclude-module", "tkinter", "--exclude-module", "onnxruntime", "--exclude-module", "torch"]
    for mod in ("QtWebEngineCore", "QtWebEngineWidgets", "QtQml", "QtQuick", "QtPdf", "QtMultimedia",
                "Qt3DCore", "QtCharts", "QtDataVisualization", "QtNetwork", "QtOpenGL"):
        cmd += ["--exclude-module", f"PySide6.{mod}"]
    try:
        import ctranslate2  # noqa: F401
        import faster_whisper  # noqa: F401
        cmd += ["--collect-all", "ctranslate2", "--collect-data", "faster_whisper",
                "--hidden-import", "faster_whisper", "--hidden-import", "tokenizers"]
        print("Auto-Untertitel: enthalten")
    except Exception:
        print("Hinweis: faster-whisper nicht installiert – Auto-Untertitel fehlen in diesem Build")
    cmd.append(str(HERE / "neoncut.py"))
    subprocess.run(cmd, check=True)

    zip_name = f"NeonCut-Portable-{VERSION}"
    shutil.make_archive(str(RELEASE / zip_name), "zip", DIST, "NeonCut")
    print("OK:", zip_name + ".zip")

    iscc = find_iscc()
    if not iscc:
        print("Hinweis: Inno Setup nicht gefunden, Installer uebersprungen (https://jrsoftware.org/isdl.php)")
        return
    out = Path(tempfile.mkdtemp(prefix="neoncut_setup_"))
    base = [iscc, "/Q", f"/DAppVersion={VERSION}", f"/DSourceDir={DIST / 'NeonCut'}", f"/DOutputDir={out}"]
    iss = str(HERE / "installer" / "neoncut.iss")
    if subprocess.run(base + [f"/DIconFile={ico}", iss]).returncode != 0:
        print("Hinweis: Setup-Icon blockiert (Virenscanner?), baue ohne eigenes Setup-Icon")
        if subprocess.run(base + [iss]).returncode != 0:
            print("Hinweis: Installer konnte lokal nicht gebaut werden (Virenscanner?) - GitHub Actions baut ihn.")
            return
    name = f"NeonCut-Setup-{VERSION}.exe"
    shutil.move(str(out / name), str(RELEASE / name))
    shutil.rmtree(out, ignore_errors=True)
    print("OK:", name)
    print("Fertig, alles liegt in", RELEASE)


if __name__ == "__main__":
    main()
