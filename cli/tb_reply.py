#!/usr/bin/env python3
"""Open a pre-filled Reply / Reply all / Forward / New window in Thunderbird, IN the existing thread.

The user always reviews the window and presses Send; this tool never sends anything.

  tb_reply.py --ping
  tb_reply.py --mode replyAll --subject "Quarterly report" --body-file body.html --attach a.pdf b.xlsx
  tb_reply.py --mode reply --author "alice" --subject "Quarterly report" --body-file body.html
  tb_reply.py --mode forward --subject "Quarterly report" --to bob@example.com --body-file body.html
  tb_reply.py --mode new --to a@example.com --cc c@example.com --subject "Invoices" --body-file body.html

--subject    reply/replyAll/forward: SEARCH query on the thread (the most recent match is used);
             new: the subject of the message itself.
--new-subject  rewrites the subject (drops an inherited "Re: ..." when the answer starts a new topic).
--body-file  an HTML fragment (not a full document) inserted above the quoted text.
Prints the extension's JSON answer; exit code 0 when ok.
"""
import argparse
import base64
import json
import mimetypes
import os
import sys
import time
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "host"))
from common import load_config  # noqa: E402


def fail(msg):
    print(json.dumps({"ok": False, "error": msg}))
    sys.exit(1)


def split_list(values):
    out = []
    for v in values or []:
        out += [p.strip() for p in v.split(",") if p.strip()]
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", choices=["reply", "replyAll", "forward", "new"], default="replyAll")
    ap.add_argument("--subject")
    ap.add_argument("--author")
    ap.add_argument("--header-message-id")
    ap.add_argument("--body-file")
    ap.add_argument("--to", nargs="*")
    ap.add_argument("--cc", nargs="*")
    ap.add_argument("--bcc", nargs="*")
    ap.add_argument("--new-subject")
    ap.add_argument("--identity-id")
    ap.add_argument("--attach", nargs="*")
    ap.add_argument("--ping", action="store_true")
    ap.add_argument("--timeout", type=int, default=25)
    a = ap.parse_args(argv)

    queue = load_config()["queue_dir"]
    inbox, outbox = os.path.join(queue, "inbox"), os.path.join(queue, "outbox")
    os.makedirs(inbox, exist_ok=True)
    os.makedirs(outbox, exist_ok=True)
    cid = uuid.uuid4().hex
    cmd = {"id": cid}

    if a.ping:
        cmd["action"] = "ping"
    else:
        cmd["action"] = a.mode
        for key, val in (("subject", a.subject), ("author", a.author), ("headerMessageId", a.header_message_id),
                         ("newSubject", a.new_subject), ("identityId", a.identity_id)):
            if val:
                cmd[key] = val
        for key, val in (("to", a.to), ("cc", a.cc), ("bcc", a.bcc)):
            if split_list(val):
                cmd[key] = split_list(val)
        if a.body_file:
            if not os.path.exists(a.body_file):
                fail("body file not found: " + a.body_file)
            with open(a.body_file, encoding="utf-8") as f:
                cmd["body"] = f.read()
        if a.mode == "new":
            if not cmd.get("to"):
                fail("--mode new requires --to")
            if not (a.subject or a.new_subject):
                fail("--mode new requires --subject")
        elif not (a.subject or a.author or a.header_message_id):
            fail("give at least --subject, --author or --header-message-id")
        atts = []
        for path in split_list(a.attach):
            if not os.path.exists(path):
                fail("attachment not found: " + path)
            with open(path, "rb") as f:
                data = base64.b64encode(f.read()).decode()
            atts.append({"name": os.path.basename(path),
                         "contentType": mimetypes.guess_type(path)[0] or "application/octet-stream",
                         "dataB64": data})
        if atts:
            cmd["attachments"] = atts

    tmp, final = os.path.join(inbox, cid + ".tmp"), os.path.join(inbox, cid + ".json")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cmd, f)
    os.replace(tmp, final)

    answer = os.path.join(outbox, cid + ".json")
    deadline = time.time() + a.timeout
    while time.time() < deadline:
        if os.path.exists(answer):
            time.sleep(0.1)
            with open(answer, encoding="utf-8") as f:
                resp = json.load(f)
            os.remove(answer)
            print(json.dumps(resp, ensure_ascii=False))
            sys.exit(0 if resp.get("ok") else 1)
        time.sleep(0.2)
    try:
        os.remove(final)  # nobody took it: do not leave a stale command for a later start
    except OSError:
        pass
    fail("timeout: is Thunderbird running with the extension enabled and the native host registered?")


if __name__ == "__main__":
    main()
