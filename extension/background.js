/*
 * Hand to AI - background script (Manifest V2, Thunderbird 115+).
 *
 * Right-click a mail -> "Hand to AI". A small window asks for an optional
 * instruction, then:
 *   1. rebuilds the thread (best effort, by normalised subject)
 *   2. extracts body + headers of every message to .txt files
 *   3. extracts the attachments to plain files
 *   4. writes everything under <Downloads>/claude-mail/<timestamp>_<subject>/
 *   5. asks the one-shot native host "hand_to_ai" to start the configured
 *      command-line agent on that folder (no daemon: Thunderbird starts the
 *      host on demand).
 *
 * The buffer lives under the download folder because Thunderbird's downloads
 * API can only write there; the absolute path is resolved afterwards with
 * downloads.search and passed to the host.
 */

const messenger = globalThis.messenger || globalThis.browser;

const MENU_ID = "hand-to-ai";
const HOST = "hand_to_ai";
const MAX_THREAD = 50; // safety limit: beyond this the thread is truncated and marked "partial"

messenger.menus.create({
  id: MENU_ID,
  title: "Hand to AI",
  contexts: ["message_list"],
  icons: { "16": "icons/robot-16.png", "32": "icons/robot-32.png" },
});

messenger.menus.onClicked.addListener(async (info) => {
  if (info.menuItemId !== MENU_ID) return;
  const sel = info.selectedMessages;
  if (!sel || !sel.messages || sel.messages.length === 0) {
    notify("Hand to AI", "No mail selected.");
    return;
  }
  const msg = sel.messages[0];
  // Do not act yet: open a small window where the user may type an optional
  // instruction. The real work starts when that window answers (see below).
  const qs = "id=" + encodeURIComponent(msg.id) + "&subject=" + encodeURIComponent(msg.subject || "");
  try {
    await messenger.windows.create({
      type: "popup",
      url: messenger.runtime.getURL("popup.html") + "?" + qs,
      width: 460,
      height: 340,
      allowScriptsToClose: true,
    });
  } catch (e) {
    console.error("[hand-to-ai] could not open the window:", e);
    notify("Hand to AI failed", String(e && e.message ? e.message : e));
  }
});

// Answer of the window: {kind:'hand-to-ai:submit', id, instruction}.
// The listener is NOT async and returns a Promise only for our own messages,
// so it never steals answers meant for reply.js (the other background script).
messenger.runtime.onMessage.addListener((message) => {
  if (!message || message.kind !== "hand-to-ai:submit") return;
  return (async () => {
    try {
      const msg = await messenger.messages.get(message.id);
      if (!msg) throw new Error("mail not found (id " + message.id + ")");
      await handOff(msg, message.instruction || "");
      notify("Hand to AI", "Mail handed to the AI.");
    } catch (e) {
      console.error("[hand-to-ai] failed:", e);
      notify("Hand to AI failed", String(e && e.message ? e.message : e));
    }
    return { ok: true };
  })();
});

async function handOff(msg, instruction) {
  const rel = `claude-mail/${timestamp()}_${slugify(normSubject(msg.subject)) || "no-subject"}`;
  const { messages, partial } = await threadMessages(msg);

  const files = [];
  let idx = 0;
  for (const m of messages) {
    idx++;
    const nn = String(idx).padStart(2, "0");
    let full = null;
    try {
      full = await messenger.messages.getFull(m.id, { decodeContent: true });
    } catch (e) { /* unreadable body */ }
    const body = full ? extractText(full) : "(body unreadable)";
    const header =
      `From    : ${m.author}\n` +
      `Date    : ${m.date}\n` +
      `Subject : ${m.subject}\n` +
      `To      : ${(m.recipients || []).join(", ")}\n` +
      (m.ccList && m.ccList.length ? `Cc      : ${m.ccList.join(", ")}\n` : "") +
      `\n----------------------------------------\n\n`;
    await saveText(`${rel}/${nn}-message.txt`, header + body);
    files.push({ file: `${nn}-message.txt`, from: m.author, date: m.date });

    let atts = [];
    try {
      atts = await messenger.messages.listAttachments(m.id);
    } catch (e) { atts = []; }
    for (const att of atts) {
      if (!att.partName || /^text\//i.test(att.contentType || "")) continue; // skip text body parts
      try {
        const file = await messenger.messages.getAttachmentFile(m.id, att.partName);
        const safeName = `${nn}-ATT-${sanitizeFilename(att.name || att.partName)}`;
        await saveFile(`${rel}/${safeName}`, file);
        files.push({ file: safeName, attachment: true, original: att.name });
      } catch (e) {
        console.warn("[hand-to-ai] attachment skipped:", att.name, e);
      }
    }
  }

  // manifest.json lists the files; its download id gives the absolute folder.
  const manifestId = await saveText(`${rel}/manifest.json`, JSON.stringify(files, null, 2));
  let folderAbs = null;
  try {
    const items = await messenger.downloads.search({ id: manifestId });
    if (items && items[0] && items[0].filename) {
      folderAbs = items[0].filename.replace(/[\\/][^\\/]+$/, "");
    }
  } catch (e) { /* the host falls back on folderRel */ }

  const resp = await messenger.runtime.sendNativeMessage(HOST, {
    folderAbs,
    folderRel: rel,
    subject: msg.subject,
    from: msg.author,
    date: msg.date,
    messageCount: messages.length,
    thread: partial ? "partial" : "full",
    instruction: (instruction || "").trim(),
  });
  if (!resp || resp.ok === false) {
    throw new Error((resp && resp.error) || "native host unreachable");
  }
}

// No thread API in Thunderbird: group by normalised subject.
async function threadMessages(msg) {
  const base = normSubject(msg.subject);
  const out = [msg];
  let partial = false;
  if (base) {
    try {
      const seen = new Set([msg.id]);
      const res = await messenger.messages.query({ subject: base });
      for (const m of (res && res.messages) ? res.messages : []) {
        if (seen.has(m.id)) continue;
        if (normSubject(m.subject) !== base) continue;
        seen.add(m.id);
        out.push(m);
        if (out.length >= MAX_THREAD) { partial = true; break; }
      }
    } catch (e) {
      partial = true; // keep at least the selected mail
    }
  }
  out.sort((a, b) => new Date(a.date) - new Date(b.date));
  return { messages: out, partial };
}

// --- writing through the downloads API (waits for the real end of the download)
async function saveText(relPath, text) {
  return download(URL.createObjectURL(new Blob([text], { type: "text/plain;charset=utf-8" })), relPath);
}
async function saveFile(relPath, file) {
  return download(URL.createObjectURL(file), relPath);
}
async function download(url, relPath) {
  const id = await messenger.downloads.download({
    url,
    filename: relPath, // relative to the Downloads folder; sub-folders are created
    conflictAction: "uniquify",
    saveAs: false,
  });
  await waitComplete(id);
  setTimeout(() => { try { URL.revokeObjectURL(url); } catch (e) {} }, 60000);
  return id;
}
function waitComplete(id) {
  return new Promise((resolve) => {
    function listener(delta) {
      if (delta.id !== id) return;
      if ((delta.state && delta.state.current === "complete") || delta.error) {
        messenger.downloads.onChanged.removeListener(listener);
        resolve(); // one failed attachment must not fail the whole batch
      }
    }
    messenger.downloads.onChanged.addListener(listener);
  });
}

// Recursive text extraction from a MessagePart (prefers text/plain).
function extractText(part) {
  const plain = [];
  const html = [];
  (function walk(p) {
    if (!p) return;
    const ct = (p.contentType || "").toLowerCase();
    if (p.body) {
      if (ct.startsWith("text/plain")) plain.push(p.body);
      else if (ct.startsWith("text/html")) html.push(p.body);
    }
    if (p.parts) p.parts.forEach(walk);
  })(part);
  if (plain.length) return plain.join("\n\n");
  if (html.length) return stripHtml(html.join("\n\n"));
  return "(no text body found)";
}
function stripHtml(s) {
  return s
    .replace(/<style[\s\S]*?<\/style>/gi, "")
    .replace(/<script[\s\S]*?<\/script>/gi, "")
    .replace(/<\/(p|div|br|li|tr|h\d)>/gi, "\n")
    .replace(/<[^>]+>/g, "")
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function normSubject(s) {
  return (s || "").replace(/^((re|fwd?|fw|tr|aw|wg)\s*:\s*)+/gi, "").trim();
}
const DIACRITICS = /[̀-ͯ]/g;
function slugify(s) {
  return (s || "")
    .normalize("NFD").replace(DIACRITICS, "")
    .toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 40);
}
function sanitizeFilename(s) {
  return (s || "file").replace(/[<>:"/\\|?*\s]/g, "_").slice(0, 120);
}
function timestamp() {
  const d = new Date(), p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}_${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}`;
}
function notify(title, message) {
  try {
    messenger.notifications.create({ type: "basic", title, message });
  } catch (e) { /* notifications are optional */ }
}
