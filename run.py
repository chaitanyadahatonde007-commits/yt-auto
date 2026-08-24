"""Start ChannelForge from Windows CMD, PowerShell, VS Code, or Mac/Linux.

    py -3 run.py
    python run.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def venv_python() -> Path:
    if os.name == "nt":
        return ROOT / ".venv" / "Scripts" / "python.exe"
    return ROOT / ".venv" / "bin" / "python"


def ensure_venv() -> Path:
    py = venv_python()
    if not py.exists():
        print("Creating virtual environment…")
        subprocess.check_call([sys.executable, "-m", "venv", str(ROOT / ".venv")])
    return py


def relaunch_in_venv() -> None:
    py = ensure_venv()
    if Path(sys.executable).resolve() == py.resolve():
        return
    raise SystemExit(subprocess.call([str(py), str(ROOT / "run.py"), *sys.argv[1:]]))


def install_deps() -> None:
    print("Installing Python packages…")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "pip"])
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", str(ROOT / "requirements.txt")])


def ensure_voice_runtime() -> None:
    dest = ROOT / "vendor" / "espeak-ng"
    if (dest / "espeak-ng.wasm").exists():
        return
    npm = shutil.which("npm")
    if not npm:
        print()
        print("Node.js / npm is not on PATH. The local voice needs it.")
        print("Install Node.js from https://nodejs.org/ then open a new terminal.")
        raise SystemExit(1)
    print("Installing local voice runtime…")
    dest.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.check_call([npm, "pack", "espeak-ng", "--pack-destination", tmp])
        tgz = next(Path(tmp).glob("espeak-ng-*.tgz"), None)
        if not tgz:
            raise SystemExit("Could not download espeak-ng")
        with tarfile.open(tgz) as archive:
            archive.extractall(tmp)
        dist = Path(tmp) / "package" / "dist"
        shutil.copy2(dist / "espeak-ng.js", dest / "espeak-ng.js")
        shutil.copy2(dist / "espeak-ng.wasm", dest / "espeak-ng.wasm")


def main() -> None:
    os.chdir(ROOT)
    relaunch_in_venv()
    try:
        install_deps()
        ensure_voice_runtime()
    except subprocess.CalledProcessError as exc:
        print(f"Setup failed ({exc.returncode}).")
        raise SystemExit(exc.returncode) from exc

    host = os.environ.get("YT_AUTO_HOST", "127.0.0.1")
    port = int(os.environ.get("YT_AUTO_PORT", "8000"))
    print()
    print("ChannelForge is starting.")
    print(f"Open http://localhost:{port}")
    print("Leave this terminal open. Press Ctrl+C to stop.")
    print()
    import uvicorn

    uvicorn.run("app.main:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
