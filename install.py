#!/usr/bin/env python3
"""Register the two native hosts for Thunderbird and build the extension package.

  python3 install.py            install (hosts + extension/hand-to-ai.xpi)
  python3 install.py --uninstall

Linux / macOS: writes the host manifests in the user-level Mozilla folders documented at
https://developer.mozilla.org/en-US/Add-ons/WebExtensions/Native_manifests
Windows: writes the manifests next to the hosts and registers them under
HKCU\\Software\\Mozilla\\NativeMessagingHosts\\<name>.
The extension itself is installed from Thunderbird (see README).
"""
import json
import os
import shutil
import stat
import sys
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
HOST_DIR = os.path.join(ROOT, "host")
EXT_DIR = os.path.join(ROOT, "extension")
HOSTS = {  # native host name -> (python file, description)
    "hand_to_ai": ("hand_to_ai.py", "Starts a command-line AI agent on a mail folder"),
    "claude_tb_bridge": ("bridge_host.py", "Relays reply/forward commands from the CLI to Thunderbird"),
}


def extension_id():
    with open(os.path.join(EXT_DIR, "manifest.json"), encoding="utf-8") as f:
        return json.load(f)["applications"]["gecko"]["id"]


def manifest_dirs():
    if sys.platform == "darwin":
        return [os.path.expanduser("~/Library/Application Support/Mozilla/NativeMessagingHosts")]
    if os.name == "nt":
        return [os.path.join(HOST_DIR, "manifests")]
    return [os.path.expanduser("~/.mozilla/native-messaging-hosts"),
            os.path.expanduser("~/.thunderbird/native-messaging-hosts")]


def wrapper(name, script):
    """Native manifests need ONE executable path: a tiny wrapper that runs the right Python."""
    if os.name == "nt":
        path = os.path.join(HOST_DIR, name + ".bat")
        with open(path, "w", encoding="ascii") as f:
            f.write('@echo off\r\n"%s" "%s" %%*\r\n' % (sys.executable, os.path.join(HOST_DIR, script)))
    else:
        path = os.path.join(HOST_DIR, name + ".sh")
        with open(path, "w", encoding="utf-8") as f:
            f.write('#!/bin/sh\nexec "%s" "%s" "$@"\n' % (sys.executable, os.path.join(HOST_DIR, script)))
        os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


def install():
    ext_id = extension_id()
    written = []
    for name, (script, desc) in HOSTS.items():
        manifest = {"name": name, "description": desc, "path": wrapper(name, script),
                    "type": "stdio", "allowed_extensions": [ext_id]}
        for d in manifest_dirs():
            os.makedirs(d, exist_ok=True)
            p = os.path.join(d, name + ".json")
            with open(p, "w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=2)
            written.append(p)
        if os.name == "nt":
            import winreg
            key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Mozilla\NativeMessagingHosts\\" + name)
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, written[-1])
            winreg.CloseKey(key)
    xpi = os.path.join(EXT_DIR, "hand-to-ai.xpi")
    with zipfile.ZipFile(xpi, "w", zipfile.ZIP_DEFLATED) as z:
        for base, _, files in os.walk(EXT_DIR):
            for fn in files:
                full = os.path.join(base, fn)
                if full != xpi:
                    z.write(full, os.path.relpath(full, EXT_DIR).replace(os.sep, "/"))
    print("native host manifests:\n  " + "\n  ".join(written))
    print("extension package: " + xpi)


def uninstall():
    for name in HOSTS:
        for d in manifest_dirs():
            p = os.path.join(d, name + ".json")
            if os.path.exists(p):
                os.remove(p)
                print("removed " + p)
        if os.name == "nt":
            import winreg
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, r"Software\Mozilla\NativeMessagingHosts\\" + name)
            except OSError:
                pass
        for ext in (".sh", ".bat"):
            w = os.path.join(HOST_DIR, name + ext)
            if os.path.exists(w):
                os.remove(w)
    xpi = os.path.join(EXT_DIR, "hand-to-ai.xpi")
    if os.path.exists(xpi):
        os.remove(xpi)


if __name__ == "__main__":
    uninstall() if "--uninstall" in sys.argv else install()
