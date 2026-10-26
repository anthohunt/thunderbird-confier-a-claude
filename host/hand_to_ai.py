#!/usr/bin/env python3
"""One-shot native host "hand_to_ai", started by Thunderbird when the user hands a mail over.

Receives {folderAbs, subject, from, date, messageCount, thread, instruction}, writes
INSTRUCTIONS.md and a small launcher script in the mail folder, then starts the configured
command-line agent in a terminal window. Answers {ok: true} or {ok: false, error}.
Set HAND_TO_AI_DRY_RUN=1 to write the files without starting anything (tests).
"""
import os
import shlex
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_config, read_message, write_message  # noqa: E402

DEFAULT_INSTRUCTION = "Read the thread and the attachments, then summarise what matters and what is expected of the user."


def render_prompt(cfg, msg, folder):
    template = open(cfg["prompt_file"], encoding="utf-8").read()
    instruction = (msg.get("instruction") or "").strip() or DEFAULT_INSTRUCTION
    values = {
        "{{SUBJECT}}": str(msg.get("subject", "")),
        "{{FROM}}": str(msg.get("from", "")),
        "{{DATE}}": str(msg.get("date", "")),
        "{{COUNT}}": str(msg.get("messageCount", "")),
        "{{THREAD}}": str(msg.get("thread", "")),
        "{{FOLDER}}": folder,
        "{{INSTRUCTION}}": "Instruction from the user: " + instruction,
    }
    for k, v in values.items():
        template = template.replace(k, v)
    return template


def write_launcher(cfg, folder, prompt):
    """Launcher script in the folder: avoids every quoting problem between terminal and shell."""
    cmd = list(cfg["command"])
    if cfg["prompt_as_argument"]:
        cmd.append(prompt)
    if os.name == "nt":
        path = os.path.join(folder, "launch.bat")
        quoted = " ".join(subprocess.list2cmdline([c]) for c in cmd)
        with open(path, "w", encoding="utf-8") as f:
            f.write('@echo off\r\ncd /d "%~dp0"\r\n' + quoted + "\r\n")
        return path
    ext = ".command" if sys.platform == "darwin" else ".sh"
    path = os.path.join(folder, "launch" + ext)
    with open(path, "w", encoding="utf-8") as f:
        f.write('#!/bin/sh\ncd "$(dirname "$0")" || exit 1\nexec ' + " ".join(shlex.quote(c) for c in cmd) + "\n")
    os.chmod(path, 0o755)
    return path


def terminal_prefix(cfg):
    if cfg.get("terminal"):
        return list(cfg["terminal"])
    if os.name == "nt":
        return ["cmd", "/c", "start", ""]
    if sys.platform == "darwin":
        return ["open"]
    for name, prefix in (("x-terminal-emulator", ["-e"]), ("gnome-terminal", ["--"]), ("konsole", ["-e"]),
                         ("xfce4-terminal", ["-x"]), ("xterm", ["-e"])):
        if shutil.which(name):
            return [name] + prefix
    raise RuntimeError('no terminal emulator found: set "terminal" in config.json')


def handle(msg):
    folder = msg.get("folderAbs")
    if not folder or not os.path.isdir(folder):
        raise RuntimeError("mail folder not found: %r" % (folder,))
    cfg = load_config()
    prompt = render_prompt(cfg, msg, folder)
    with open(os.path.join(folder, "INSTRUCTIONS.md"), "w", encoding="utf-8") as f:
        f.write(prompt)
    launcher = write_launcher(cfg, folder, prompt)
    if os.environ.get("HAND_TO_AI_DRY_RUN"):
        return {"ok": True, "dryRun": True, "launcher": launcher}
    cmd = terminal_prefix(cfg) + [launcher]
    kwargs = {"cwd": folder, "stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if os.name == "nt":
        kwargs["creationflags"] = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(cmd, **kwargs)
    return {"ok": True, "launcher": launcher}


def main():
    msg = read_message()
    if msg is None:
        return
    try:
        write_message(handle(msg))
    except Exception as e:  # noqa: BLE001 - the extension shows the text in a notification
        write_message({"ok": False, "error": "%s: %s" % (type(e).__name__, e)})


if __name__ == "__main__":
    main()
