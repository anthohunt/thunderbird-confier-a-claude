"""End-to-end tests of the native hosts and the CLI, with a fake extension speaking the
native-messaging protocol on stdio. No Thunderbird needed. Run: python3 tests/test_hosts.py"""
import base64, json, os, struct, subprocess, sys, tempfile, threading, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable
tmp = tempfile.mkdtemp()
cfg_path = os.path.join(tmp, "config.json")
queue = os.path.join(tmp, "queue")
json.dump({"command": ["touch", "agent-started"], "prompt_as_argument": False, "terminal": ["sh"],
           "queue_dir": queue}, open(cfg_path, "w"))
ENV = dict(os.environ, TB_CONFIRMER_CONFIG=cfg_path)


def frame(obj):
    d = json.dumps(obj).encode()
    return struct.pack("=I", len(d)) + d


def read_frame(stream):
    n = struct.unpack("=I", stream.read(4))[0]
    return json.loads(stream.read(n))


def test_hand_to_ai():
    folder = os.path.join(tmp, "claude-mail", "2027-01-01_120000_quarterly-report")
    os.makedirs(folder)
    open(os.path.join(folder, "01-message.txt"), "w").write("hello")
    msg = {"folderAbs": folder, "subject": "Quarterly report", "from": "alice@example.org", "date": "2027-01-01",
           "messageCount": 1, "thread": "full", "instruction": "List the open questions."}
    p = subprocess.run([PY, ROOT + "/host/hand_to_ai.py"], input=frame(msg), capture_output=True, env=ENV, timeout=20)
    n = struct.unpack("=I", p.stdout[:4])[0]
    resp = json.loads(p.stdout[4:4 + n])
    assert resp["ok"], resp
    instr = open(os.path.join(folder, "INSTRUCTIONS.md")).read()
    assert "Quarterly report" in instr and "List the open questions." in instr and "{{" not in instr, instr
    for _ in range(50):   # the launcher runs detached: wait for its marker
        if os.path.exists(os.path.join(folder, "agent-started")): break
        time.sleep(0.1)
    assert os.path.exists(os.path.join(folder, "agent-started")), "agent was not started in the mail folder"
    bad = subprocess.run([PY, ROOT + "/host/hand_to_ai.py"], input=frame({"folderAbs": "/nonexistent"}),
                         capture_output=True, env=ENV, timeout=20)
    assert json.loads(bad.stdout[4:])["ok"] is False
    print("OK: hand_to_ai writes INSTRUCTIONS.md, starts the agent in the folder, reports a missing folder")


def test_bridge():
    host = subprocess.Popen([PY, ROOT + "/host/bridge_host.py"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, env=ENV)
    seen = []

    def fake_extension():   # answers every command like reply.js would
        while True:
            try: cmd = read_frame(host.stdout)
            except Exception: return
            seen.append(cmd)
            ans = {"id": cmd["id"], "ok": True}
            if cmd["action"] == "ping": ans.update(pong=True, tb="140.0")
            else: ans.update(matched={"subject": cmd.get("subject")}, subject="Re: " + str(cmd.get("subject")),
                             attached=[a["name"] for a in cmd.get("attachments", [])])
            host.stdin.write(frame(ans)); host.stdin.flush()
    threading.Thread(target=fake_extension, daemon=True).start()
    try:
        r = subprocess.run([PY, ROOT + "/cli/tb_reply.py", "--ping"], capture_output=True, env=ENV, timeout=30)
        assert r.returncode == 0 and json.loads(r.stdout)["pong"], r.stdout
        body = os.path.join(tmp, "body.html"); open(body, "w").write("<p>Thanks, see attached.</p>")
        att = os.path.join(tmp, "report.pdf"); open(att, "wb").write(b"%PDF-1.4 test")
        r = subprocess.run([PY, ROOT + "/cli/tb_reply.py", "--mode", "replyAll", "--subject", "Quarterly report",
                            "--author", "alice", "--body-file", body, "--attach", att, "--cc", "bob@example.org"],
                           capture_output=True, env=ENV, timeout=30)
        out = json.loads(r.stdout)
        assert r.returncode == 0 and out["attached"] == ["report.pdf"], r.stdout
        cmd = seen[-1]
        assert cmd["action"] == "replyAll" and cmd["author"] == "alice" and cmd["cc"] == ["bob@example.org"]
        assert cmd["body"] == "<p>Thanks, see attached.</p>"
        assert base64.b64decode(cmd["attachments"][0]["dataB64"]) == b"%PDF-1.4 test"
        assert cmd["attachments"][0]["contentType"] == "application/pdf"
        r = subprocess.run([PY, ROOT + "/cli/tb_reply.py", "--mode", "new", "--subject", "x"], capture_output=True, env=ENV)
        assert r.returncode == 1 and "requires --to" in r.stdout.decode()
        print("OK: bridge host + CLI round trip (ping, reply all with body/cc/attachment, argument checks)")
    finally:
        host.terminate()
    # no extension answering -> CLI times out cleanly and leaves no stale command
    r = subprocess.run([PY, ROOT + "/cli/tb_reply.py", "--ping", "--timeout", "2"], capture_output=True, env=ENV)
    assert r.returncode == 1 and b"timeout" in r.stdout
    assert not [f for f in os.listdir(queue + "/inbox") if f.endswith(".json")], "stale command left"
    print("OK: timeout when Thunderbird is not connected")


test_hand_to_ai()
test_bridge()
