"""Shared helpers for the two native hosts and the command-line tool."""
import json
import os
import struct
import sys

APP = "thunderbird-confier-a-claude"


def config_dir():
    if os.name == "nt":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, APP)


def load_config():
    """Settings file: $TB_CONFIRMER_CONFIG or <config dir>/config.json. Missing file = defaults."""
    path = os.environ.get("TB_CONFIRMER_CONFIG") or os.path.join(config_dir(), "config.json")
    cfg = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
    defaults = {
        "command": ["claude"],           # the agent started in the mail folder
        "prompt_as_argument": True,      # append the prompt as the last argument
        "terminal": None,                # list prefix, e.g. ["gnome-terminal", "--"]; None = auto-detect
        "prompt_file": os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompt.md"),
        "queue_dir": os.path.join(config_dir(), "queue"),
    }
    for key, value in defaults.items():
        if cfg.get(key) is None:         # missing or null = default
            cfg[key] = value
    return cfg


def read_message(stream=None):
    """One native-messaging frame (4-byte length in native byte order, then UTF-8 JSON)."""
    stream = stream or sys.stdin.buffer
    raw = stream.read(4)
    if len(raw) < 4:
        return None
    (n,) = struct.unpack("=I", raw)
    return json.loads(stream.read(n).decode("utf-8"))


def write_message(obj, stream=None):
    stream = stream or sys.stdout.buffer
    data = json.dumps(obj).encode("utf-8")
    stream.write(struct.pack("=I", len(data)))
    stream.write(data)
    stream.flush()
