#!/usr/bin/env python3
"""
One-time setup for Studio on Windows, Mac or Linux.

    python3 studio/setup_studio.py

1. installs the Python packages
2. downloads Blender 4.5 LTS (portable, into ~/.studio/blender)
3. downloads the Kokoro voice model with its Hindi voices (~350 MB)
4. checks ffmpeg, the Claude Code CLI and Hindi text shaping
5. saves the paths in ~/.studio/settings.json
"""
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import zipfile

HOME = os.path.join(os.path.expanduser("~"), ".studio")
BLENDER_VER = "4.5.15"
BLENDER_BASE = f"https://download.blender.org/release/Blender4.5/blender-{BLENDER_VER}"
KOKORO = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
PACKAGES = ["numpy", "scipy", "pillow", "soundfile", "kokoro-onnx"]


def say(msg):
    print("•", msg, flush=True)


def download(url, path):
    if os.path.exists(path) and os.path.getsize(path) > 0:
        say(f"already have {os.path.basename(path)}")
        return path
    say(f"downloading {url}")
    tmp = path + ".part"
    with urllib.request.urlopen(url) as r, open(tmp, "wb") as f:
        total = int(r.headers.get("Content-Length", 0))
        done = 0
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            if total:
                print(f"\r  {done * 100 // total:3d}%", end="", flush=True)
    print()
    os.replace(tmp, path)
    return path


def install_packages():
    say("installing Python packages: " + ", ".join(PACKAGES))
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", *PACKAGES])


def install_blender():
    sysname, machine = platform.system(), platform.machine().lower()
    dest = os.path.join(HOME, "blender")
    os.makedirs(dest, exist_ok=True)
    if sysname == "Windows":
        z = download(f"{BLENDER_BASE}-windows-x64.zip", os.path.join(dest, "blender.zip"))
        exe = os.path.join(dest, f"blender-{BLENDER_VER}-windows-x64", "blender.exe")
        if not os.path.exists(exe):
            say("unpacking Blender…")
            zipfile.ZipFile(z).extractall(dest)
        return exe
    if sysname == "Darwin":
        arch = "arm64" if machine in ("arm64", "aarch64") else "x64"
        dmg = download(f"{BLENDER_BASE}-macos-{arch}.dmg", os.path.join(dest, "blender.dmg"))
        app = os.path.join(dest, "Blender.app")
        if not os.path.exists(app):
            say("copying Blender.app out of the disk image…")
            mnt = os.path.join(dest, "mnt")
            os.makedirs(mnt, exist_ok=True)
            subprocess.check_call(["hdiutil", "attach", "-nobrowse", "-mountpoint", mnt, dmg])
            try:
                shutil.copytree(os.path.join(mnt, "Blender.app"), app, symlinks=True)
            finally:
                subprocess.call(["hdiutil", "detach", mnt])
        return os.path.join(app, "Contents", "MacOS", "Blender")
    tar = download(f"{BLENDER_BASE}-linux-x64.tar.xz", os.path.join(dest, "blender.tar.xz"))
    exe = os.path.join(dest, f"blender-{BLENDER_VER}-linux-x64", "blender")
    if not os.path.exists(exe):
        say("unpacking Blender…")
        tarfile.open(tar).extractall(dest)
    return exe


def install_voices():
    d = os.path.join(HOME, "models")
    os.makedirs(d, exist_ok=True)
    for f in ("kokoro-v1.0.onnx", "voices-v1.0.bin"):
        download(KOKORO + f, os.path.join(d, f))
    return d


def check_tools():
    ok = True
    if not shutil.which("ffmpeg"):
        ok = False
        say("ffmpeg is missing. Windows: `winget install Gyan.FFmpeg`  Mac: `brew install ffmpeg`")
    if not shutil.which("claude"):
        ok = False
        say("Claude Code is missing (it writes the stories). Install: `npm install -g @anthropic-ai/claude-code`, "
            "then run `claude` once to log in.")
    from PIL import features
    if not features.check("raqm"):
        ok = False
        say("Pillow cannot shape Hindi text on this computer (raqm/fribidi missing). Mac: `brew install fribidi`. "
            "Windows: put fribidi-0.dll next to python.exe. Without it Hindi captions will render incorrectly.")
    return ok


def main():
    os.makedirs(HOME, exist_ok=True)
    install_packages()
    blender = install_blender()
    models = install_voices()
    conf = os.path.join(HOME, "settings.json")
    s = json.load(open(conf)) if os.path.exists(conf) else {}
    s.update({"blender": blender, "models": models})
    s.setdefault("engine", "BLENDER_EEVEE_NEXT")
    json.dump(s, open(conf, "w"), indent=1)
    say(f"Blender: {blender}")
    say(f"voices:  {models}")
    good = check_tools()
    say("setup finished" + ("" if good else " (fix the items above, then run Studio)"))
    say("start Studio with: python3 studio/app.py")


if __name__ == "__main__":
    main()
