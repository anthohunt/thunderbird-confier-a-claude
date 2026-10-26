#!/usr/bin/env python3
"""Persistent native host "claude_tb_bridge", started by Thunderbird when the extension calls connectNative.

Relays the commands that tb_reply.py drops as JSON files in <queue_dir>/inbox to the extension, and writes the
extension's answers to <queue_dir>/outbox/<id>.json (which tb_reply.py is waiting for).
Log: <queue_dir>/host.log
"""
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_config, read_message, write_message  # noqa: E402

CFG = load_config()
QUEUE = CFG["queue_dir"]
INBOX = os.path.join(QUEUE, "inbox")
OUTBOX = os.path.join(QUEUE, "outbox")
LOG = os.path.join(QUEUE, "host.log")
_out_lock = threading.Lock()


def log(msg):
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S") + " " + msg + "\n")
    except OSError:
        pass


def send(obj):
    with _out_lock:
        write_message(obj)


def reader():
    """Extension -> outbox files."""
    import json
    while True:
        msg = read_message()
        if msg is None:
            log("stdin closed, exiting")
            os._exit(0)
        rid = os.path.basename(str(msg.get("id", "noid")))   # never let an id leave the outbox folder
        path = os.path.join(OUTBOX, rid + ".json")
        with open(path + ".tmp", "w", encoding="utf-8") as f:
            json.dump(msg, f, ensure_ascii=False)
        os.replace(path + ".tmp", path)
        log("answer written for %s ok=%s" % (rid, msg.get("ok")))


def main():
    import json
    os.makedirs(INBOX, exist_ok=True)
    os.makedirs(OUTBOX, exist_ok=True)
    log("host started (pid %d)" % os.getpid())
    threading.Thread(target=reader, daemon=True).start()
    while True:
        try:
            for name in sorted(os.listdir(INBOX)):
                if not name.endswith(".json"):
                    continue
                p = os.path.join(INBOX, name)
                try:
                    with open(p, encoding="utf-8") as f:
                        cmd = json.load(f)
                except (OSError, ValueError) as e:
                    log("bad command file %s: %r" % (name, e))
                    cmd = None
                try:
                    os.remove(p)
                except OSError:
                    pass
                if cmd is None:
                    continue
                cmd.setdefault("id", os.path.splitext(name)[0])
                log("forwarding %s action=%s" % (cmd["id"], cmd.get("action")))
                send(cmd)
        except Exception as e:  # noqa: BLE001 - keep the host alive
            log("loop error %r" % e)
        time.sleep(0.3)


if __name__ == "__main__":
    main()
