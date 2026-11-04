# thunderbird-confier-a-claude

Two ways to connect Thunderbird to a command-line AI agent such as [Claude Code](https://docs.claude.com/en/docs/claude-code):

1. **Hand to AI** (mail → agent). Right-click a mail, type an optional instruction. The whole thread and its attachments are exported to a folder and your agent is started in a terminal on that folder, with a ready-made prompt.
2. **Reply bridge** (agent → mail). The agent, or you, runs `cli/tb_reply.py` and a real **Reply / Reply all / Forward / New** window opens in Thunderbird, **inside the existing thread** (quote and threading kept), body pre-filled, attachments added. **You review and press Send yourself**: the tool never sends anything.

## What is in the repository
- `extension/`: the Thunderbird add-on (Manifest V2, Thunderbird 115+): `background.js` (right-click item, export), `popup.*` (instruction window), `reply.js` (reply bridge).
- `host/`: `hand_to_ai.py` (one-shot native host that starts your agent), `bridge_host.py` (persistent native host for the reply bridge), `prompt.md` (the prompt template), `common.py`.
- `cli/tb_reply.py`: the command-line tool (Python, works on Linux, macOS, Windows).
- `install.py`: registers the native hosts and builds the add-on package.
- `config.example.json`: settings. `tests/test_hosts.py`: end-to-end tests without Thunderbird.

## Install
Requirements: Thunderbird 115 or newer, Python 3.8 or newer, and your agent's command on the PATH (default: `claude`).
```
git clone <this repository> && cd thunderbird-confier-a-claude
python3 install.py                       # registers the native hosts, builds extension/hand-to-ai.xpi
python3 tests/test_hosts.py              # optional: checks the hosts and the CLI (prints OK lines)
```
Then, in Thunderbird:
- **Quick try (always works):** menu ☰ → Add-ons and Themes → ⚙ → *Debug Add-ons* → *Load Temporary Add-on…* → pick `extension/manifest.json`. Lasts until Thunderbird restarts.
- **Permanent:** install `extension/hand-to-ai.xpi` (⚙ → *Install Add-on From File…*). Thunderbird only accepts signed add-ons by default: either sign the package yourself as an unlisted add-on at addons.thunderbird.net, or, on a build that allows it, set `xpinstall.signatures.required` to `false` in the Config Editor.

Native host locations: Linux `~/.mozilla/native-messaging-hosts/` (and `~/.thunderbird/…`), macOS `~/Library/Application Support/Mozilla/NativeMessagingHosts/`, Windows registry `HKCU\Software\Mozilla\NativeMessagingHosts\<name>` ([Mozilla documentation](https://developer.mozilla.org/en-US/Add-ons/WebExtensions/Native_manifests)). The author's daily use was on Windows; the Linux and macOS paths follow the documentation and were checked with a simulated extension, not with a real Thunderbird.

## Settings
Copy `config.example.json` to `~/.config/thunderbird-confier-a-claude/config.json` (Windows: `%APPDATA%\thunderbird-confier-a-claude\config.json`), or point `TB_CONFIRMER_CONFIG` at another file. Every key is optional.
| Key | Default | Meaning |
|---|---|---|
| `command` | `["claude"]` | The agent started in the mail folder (a list: program and arguments). |
| `prompt_as_argument` | `true` | Append the prompt as the last argument. The prompt is always also written to `INSTRUCTIONS.md` in the folder. |
| `terminal` | auto | Terminal prefix, for example `["gnome-terminal", "--"]`. Auto: `x-terminal-emulator`, `gnome-terminal`, `konsole`, `xfce4-terminal` or `xterm` on Linux, `open` on macOS, `cmd /c start` on Windows. |
| `prompt_file` | `host/prompt.md` | Prompt template. Placeholders: `{{SUBJECT}} {{FROM}} {{DATE}} {{COUNT}} {{THREAD}} {{FOLDER}} {{INSTRUCTION}}`. |
| `queue_dir` | `<config dir>/queue` | Where the CLI and the bridge host exchange commands and answers. |

## Use
**Hand to AI:** right-click a mail → *Hand to AI* → type an instruction (or leave it empty) → *Hand over*. The thread goes to `<Downloads>/claude-mail/<date>_<subject>/` (`NN-message.txt`, `NN-ATT-*` attachments, `manifest.json`, `INSTRUCTIONS.md`, a launcher script) and your agent starts there. Thunderbird has no thread API, so the thread is rebuilt by normalised subject (best effort; `thread: partial` is passed on when it was cut at 50 messages).

**Reply bridge** (Thunderbird must be running):
```
python3 cli/tb_reply.py --ping
python3 cli/tb_reply.py --mode replyAll --subject "Quarterly report" --body-file body.html --attach report.pdf
python3 cli/tb_reply.py --mode reply --author alice --subject "Quarterly report" --body-file body.html
python3 cli/tb_reply.py --mode forward --subject "Quarterly report" --to bob@example.org --body-file body.html
python3 cli/tb_reply.py --mode new --to a@example.org --cc c@example.org --subject "Invoices" --body-file body.html --attach inv1.pdf inv2.pdf
```
`--subject` is a search query for reply, reply all and forward (the most recent match is used; add `--author` to be sure); `--new-subject` rewrites the subject; `--body-file` is an HTML fragment placed above the quote. The answer is a JSON line (`"ok": true`, the matched message, the subject really set, the attachments added).

## How it works
```
CLI tb_reply.py --(JSON file in queue/inbox)--> bridge_host.py (persistent native host)
                                                    | stdio native messaging
                                                    v
                          extension reply.js --> compose.beginReply / beginForward / beginNew + addAttachment
                                                    |
                    answer JSON --> queue/outbox/<id>.json --> read by the CLI
```

## Safety
- The add-on never sends a mail. Opening a window is not sending.
- Anything handed over is written to your Downloads folder and read by your agent: do not hand over mail you would not show to that agent's provider.
- The native hosts only accept the add-on's own identifier (`allowed_extensions`). Change the identifier in `extension/manifest.json` if you publish your own build; `install.py` reads it from there.
- The queue folder is trusted: anyone who can write in it can open compose windows. Keep it in your own profile folder (the default).

## Limits
- Scheduled sending, the Microsoft 365 route and the calendar import that existed in the author's private version are not part of this repository.
- Only the tests with a simulated extension are automatic; the add-on itself has to be tried in Thunderbird.

## Licenses
Code: Apache License 2.0 (`LICENSE`, `NOTICE`). Text and documentation: CC BY 4.0 (`LICENSE-docs`). The icons in `extension/icons/` were generated for this project (a plain geometric drawing), under the same terms. No third-party library is included.
