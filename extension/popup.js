const $ = (id) => document.getElementById(id);
const fmtTime = (ts) => new Date(ts).toLocaleTimeString();

async function renderHistory() {
  const { history = [] } = await chrome.storage.local.get(["history"]);
  const wrap = $("history");
  if (!history.length) {
    wrap.innerHTML = '<div class="empty">No submissions yet.</div>';
    return;
  }
  wrap.innerHTML = history.map((h) => `
    <div class="item">
      <div class="name">${escapeHtml(h.filename || h.url || "(unknown)")}</div>
      <div class="meta">
        ${fmtTime(h.submitted_at)} · ${escapeHtml((h.status || "queued"))}
        · <a href="http://localhost:5173" target="_blank">open</a>
      </div>
    </div>
  `).join("");
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]));
}

$("sendBtn").addEventListener("click", async () => {
  const url = $("urlInput").value.trim();
  if (!url) return;
  $("sendBtn").disabled = true;
  $("hint").textContent = "Sending…";
  try {
    const resp = await chrome.runtime.sendMessage({ type: "submit-url", url });
    if (resp && resp.ok) {
      $("urlInput").value = "";
      $("hint").textContent = "Queued. Check the dashboard.";
      await renderHistory();
    } else {
      $("hint").textContent = (resp && resp.error) || "Submit failed.";
    }
  } catch (e) {
    $("hint").textContent = String(e);
  } finally {
    $("sendBtn").disabled = false;
  }
});

$("urlInput").addEventListener("keydown", (e) => {
  if (e.key === "Enter") $("sendBtn").click();
});

renderHistory();
