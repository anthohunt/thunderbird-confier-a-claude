/*
 * Hand to AI - instruction window. Opened by background.js with ?id=<messageId>&subject=<...>.
 * "Hand over" answers {kind:'hand-to-ai:submit', id, instruction} to the background script and
 * closes. "Cancel" (or the close button) sends nothing, so nothing is launched.
 */
const messenger = globalThis.messenger || globalThis.browser;
const params = new URLSearchParams(location.search);
const msgId = Number(params.get("id"));
const subject = params.get("subject") || "(no subject)";
const instrEl = document.getElementById("instruction");
document.getElementById("subject").textContent = subject;
document.title = "Hand to AI: " + subject;

function cancel() { window.close(); }

async function confide() {
  try {
    await messenger.runtime.sendMessage({ kind: "hand-to-ai:submit", id: msgId, instruction: instrEl.value.trim() });
  } catch (e) {
    console.error("[hand-to-ai popup] send failed:", e);
  }
  window.close();
}

document.getElementById("confide").addEventListener("click", confide);
document.getElementById("cancel").addEventListener("click", cancel);
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") { e.preventDefault(); cancel(); }
  else if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); confide(); }
});
window.addEventListener("load", () => instrEl.focus());
