**English** · [Français](README.fr.md)

# Hand to AI for Thunderbird

**Right-click a mail in Thunderbird to hand its thread to a command-line AI agent; the agent opens pre-filled replies that you send yourself.**

[![Right-click a thread, Hand to AI, the thread lands in a folder, Claude Code drafts the answer, a Reply all opens pre-filled in Thunderbird (click for the full video)](docs/demo.gif)](https://drive.google.com/file/d/1dxDcTe66kMsXDhIvdrtuL_6a-FysO6Fo/view)

*Real run in Thunderbird 159 on a demo account with made-up mails. [Full video (0:57)](https://drive.google.com/file/d/1dxDcTe66kMsXDhIvdrtuL_6a-FysO6Fo/view)*

## Using it

- **Hand to AI.** Right-click a mail, type an optional instruction, press *Hand over*.
- **One folder per mail.** The whole thread (`NN-message.txt`), its attachments and the prompt (`INSTRUCTIONS.md`) go to `Downloads/claude-mail/<date>_<subject>/`.
- **Your agent.** Claude Code by default; any command-line agent through `config.json`.
- **Reply bridge.** `cli/tb_reply.py` opens a Reply, Reply all, Forward or New window inside the thread, body and attachments filled in.
- **You send.** The tool only opens windows; it never sends a mail.

## Architecture

![Architecture: the add-on exports the thread to a folder and calls a one-shot native host that starts the agent; the agent runs tb_reply.py, which drops a JSON command in a queue folder read by a persistent native host, and the add-on opens the reply window](docs/architecture.svg)

## Install

Thunderbird 115 or newer, Python 3.8 or newer, your agent's command on the PATH (default `claude`).

```
git clone https://github.com/anthohunt/thunderbird-confier-a-claude && cd thunderbird-confier-a-claude
python3 install.py           # registers the two native hosts, builds extension/hand-to-ai.xpi
python3 tests/test_hosts.py  # optional: three OK lines
```

In Thunderbird: ☰ → Add-ons and Themes → ⚙ → *Debug Add-ons* → *Load Temporary Add-on…* → `extension/manifest.json` (until the next restart), or ⚙ → *Install Add-on From File…* → `extension/hand-to-ai.xpi` (unsigned: sign it as an unlisted add-on, or set `xpinstall.signatures.required` to `false` where the build allows it).

<details>
<summary>Reply bridge commands</summary>

```
python3 cli/tb_reply.py --ping
python3 cli/tb_reply.py --mode replyAll --subject "Quarterly report" --body-file body.html --attach report.pdf
python3 cli/tb_reply.py --mode reply --author alice --subject "Quarterly report" --body-file body.html
python3 cli/tb_reply.py --mode forward --subject "Quarterly report" --to bob@example.org --body-file body.html
python3 cli/tb_reply.py --mode new --to a@example.org --subject "Invoices" --body-file body.html --attach inv1.pdf inv2.pdf
```

`--subject` searches the mail to answer (the most recent match; add `--author` to be sure), `--new-subject` rewrites it, `--body-file` is an HTML fragment placed above the quote. The answer is one JSON line: the matched mail, the subject set, the attachments added. Thunderbird must be running.
</details>

<details>
<summary>Settings</summary>

`~/.config/thunderbird-confier-a-claude/config.json` (Windows: `%APPDATA%\thunderbird-confier-a-claude\config.json`), or the file named by `TB_CONFIRMER_CONFIG`. Every key is optional; see `config.example.json`.

| Key | Default | Meaning |
|---|---|---|
| `command` | `["claude"]` | Agent started in the mail folder (program and arguments). |
| `prompt_as_argument` | `true` | Adds the prompt as the last argument; it is always in `INSTRUCTIONS.md` too. |
| `terminal` | auto | Terminal prefix, e.g. `["gnome-terminal", "--"]`. |
| `prompt_file` | `host/prompt.md` | Prompt template (`{{SUBJECT}} {{FROM}} {{DATE}} {{COUNT}} {{THREAD}} {{FOLDER}} {{INSTRUCTION}}`). |
| `queue_dir` | `<config dir>/queue` | Where the CLI and the bridge host exchange commands. Anyone who can write there can open compose windows. |
</details>

## Status

- **Checked on 17/11/2026** on Windows 11 with Thunderbird 159: right-click export, instruction window and reply bridge (Reply all, Cc kept, attachment added) work.
- **Known issue on Windows.** Started from Thunderbird, the agent's terminal does not appear (Thunderbird ends what its native host starts); the folder and `INSTRUCTIONS.md` are written. The same launcher works when started by hand. The author's private version goes through a Windows scheduled task; that fix is not in this repository yet.
- **Linux and macOS** follow the Mozilla documentation and pass the simulated tests (`tests/test_hosts.py`); not tried with a real Thunderbird.
- **Thread** rebuilt by subject (Thunderbird has no thread API); cut at 50 messages.
- **Privacy.** A handed-over thread is read by your agent and its provider.
- **License.** Code Apache 2.0, text CC BY 4.0.

---

**Anthony Hunt** · [ingevision.cloud](https://ingevision.cloud/?lang=en&p=thunderbird-agent) · [LinkedIn](https://www.linkedin.com/in/anthony-hunt-3948a9196) · [GitHub](https://github.com/anthohunt)
