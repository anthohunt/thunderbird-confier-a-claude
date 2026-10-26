/*
 * Bridge module (reply.js): the OPPOSITE direction of the right-click item.
 * Here the command-line agent drives Thunderbird. It opens a real Reply /
 * Reply all / Forward window INSIDE the existing thread (quote and threading
 * kept), or a brand new message, with a pre-filled body and attachments.
 * The user reviews the window and presses Send; nothing is ever sent from here.
 *
 * Transport: the persistent native host "claude_tb_bridge" (connectNative),
 * which relays JSON commands dropped in a queue folder by the CLI tb_reply.py.
 */
(function () {
  const mx = globalThis.messenger || globalThis.browser;
  const HOST = "claude_tb_bridge";
  let port = null;

  function connect() {
    try {
      port = mx.runtime.connectNative(HOST);
    } catch (e) {
      console.error("[tb-bridge] connectNative failed:", e);
      setTimeout(connect, 10000);
      return;
    }
    port.onMessage.addListener(onCommand);
    port.onDisconnect.addListener(() => {
      console.warn("[tb-bridge] host disconnected, retry in 5 s", port && port.error ? port.error.message : "");
      port = null;
      setTimeout(connect, 5000);
    });
    console.log("[tb-bridge] connected to native host");
  }

  async function onCommand(cmd) {
    const id = cmd.id || "noid";
    try {
      const result = await handle(cmd);
      // id LAST: a result must never overwrite the command id (the answer file is named after it).
      if (port) port.postMessage(Object.assign({ ok: true }, result, { id: id }));
    } catch (e) {
      if (port) port.postMessage({ id: id, ok: false, error: String(e && e.message ? e.message : e) });
    }
  }

  async function handle(cmd) {
    if (cmd.action === "ping") {
      let v = "?";
      try { v = (await mx.runtime.getBrowserInfo()).version; } catch (e) {}
      return { pong: true, tb: v };
    }
    if (["reply", "replyAll", "forward", "new"].includes(cmd.action)) {
      // "new" = fresh message outside any thread: no target message to look up.
      const target = cmd.action === "new" ? null : await findMessage(cmd);
      const details = {};
      if (cmd.to) details.to = cmd.to;
      if (cmd.cc) details.cc = cmd.cc;
      if (cmd.bcc) details.bcc = cmd.bcc;
      if (cmd.identityId) details.identityId = cmd.identityId;
      // For reply/forward cmd.subject is a SEARCH query; only newSubject rewrites the
      // subject. For "new" there is no search, so cmd.subject IS the subject.
      const subj = cmd.newSubject || (cmd.action === "new" ? cmd.subject : null);
      if (subj) details.subject = subj;

      let tab;
      if (cmd.action === "new") {
        tab = await mx.compose.beginNew(null, details);
      } else if (cmd.action === "forward") {
        tab = await mx.compose.beginForward(target.id, "forwardInline", details);
      } else {
        const rt = cmd.action === "replyAll" ? "replyToAll" : "replyToSender";
        tab = await mx.compose.beginReply(target.id, rt, details);
      }
      if (cmd.body) await injectBody(tab.id, cmd.body);
      const attached = [];
      if (Array.isArray(cmd.attachments)) {
        for (const a of cmd.attachments) {
          await addAttachment(tab.id, a);
          attached.push(a.name);
        }
      }
      return {
        matched: target ? { subject: target.subject, author: target.author, date: target.date } : null,
        subject: await readSubject(tab.id),
        attached: attached,
      };
    }
    throw new Error("unknown action: " + cmd.action);
  }

  async function findMessage(cmd) {
    const q = {};
    if (cmd.headerMessageId) q.headerMessageId = cmd.headerMessageId;
    if (cmd.subject) q.subject = cmd.subject;
    if (cmd.author) q.author = cmd.author;
    if (Object.keys(q).length === 0) throw new Error("no query (subject/author/headerMessageId)");
    const page = await mx.messages.query(q);
    const msgs = (page && page.messages) ? page.messages : [];
    if (!msgs.length) throw new Error("no message matched " + JSON.stringify(q));
    msgs.sort((a, b) => new Date(b.date) - new Date(a.date));
    return msgs[0]; // the most recent match
  }

  async function injectBody(tabId, html) {
    let lastErr = null;
    for (let i = 0; i < 12; i++) { // the compose window may not be ready yet
      try {
        const d = await mx.compose.getComposeDetails(tabId);
        if (d.isPlainText) {
          await mx.compose.setComposeDetails(tabId, {
            plainTextBody: htmlToText(html) + "\n\n" + (d.plainTextBody || ""),
          });
        } else {
          const body = d.body || "";
          const m = body.match(/<body[^>]*>/i);
          let nb;
          if (m) {
            const at = body.indexOf(m[0]) + m[0].length;
            nb = body.slice(0, at) + html + body.slice(at);
          } else {
            nb = html + body;
          }
          await mx.compose.setComposeDetails(tabId, { body: nb });
        }
        return;
      } catch (e) {
        lastErr = e;
        await new Promise((r) => setTimeout(r, 300));
      }
    }
    throw new Error("could not inject body: " + lastErr);
  }

  // Reads back the subject really set in the window: proof that an override took
  // effect (a reply otherwise keeps the inherited "Re: ...").
  async function readSubject(tabId) {
    try {
      return (await mx.compose.getComposeDetails(tabId)).subject || "";
    } catch (e) {
      return null;
    }
  }

  async function addAttachment(tabId, a) { // a = { name, contentType, dataB64 }
    const bin = atob(a.dataB64 || "");
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    const file = new File([bytes], a.name || "attachment", { type: a.contentType || "application/octet-stream" });
    await mx.compose.addAttachment(tabId, { file: file, name: a.name || "attachment" });
  }

  function htmlToText(html) {
    return html
      .replace(/<br\s*\/?>/gi, "\n")
      .replace(/<\/(p|div|li)>/gi, "\n")
      .replace(/<[^>]+>/g, "")
      .replace(/&nbsp;/g, " ").replace(/&amp;/g, "&")
      .replace(/&lt;/g, "<").replace(/&gt;/g, ">")
      .trim();
  }

  connect();
})();
