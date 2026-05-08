// EchoStream MV3 service worker:
//   - registers a context menu on links and pages,
//   - POSTs the chosen URL to the local API,
//   - keeps a small history in chrome.storage for the popup.

const API_BASE = "http://localhost:8000";

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: "echostream-send-link",
    title: "Send video link to EchoStream",
    contexts: ["link"],
    targetUrlPatterns: ["http://*/*", "https://*/*"],
  });
  chrome.contextMenus.create({
    id: "echostream-send-page",
    title: "Send this page URL to EchoStream",
    contexts: ["page", "video"],
  });
});

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  let url = null;
  if (info.menuItemId === "echostream-send-link") url = info.linkUrl;
  else if (info.menuItemId === "echostream-send-page") url = info.pageUrl || (tab && tab.url);
  if (!url) return;
  await sendToEchoStream(url);
});

async function sendToEchoStream(url) {
  const startedAt = Date.now();
  await setBadge("…", "#818cf8");
  try {
    const res = await fetch(`${API_BASE}/upload-url`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || `HTTP ${res.status}`);
    }
    const data = await res.json();
    await pushHistory({
      task_id: data.task_id,
      filename: data.filename,
      url,
      submitted_at: startedAt,
      status: "queued",
    });
    await setBadge("OK", "#10b981");
    setTimeout(() => chrome.action.setBadgeText({ text: "" }), 4000);
    return { ok: true, data };
  } catch (err) {
    await setBadge("ERR", "#f43f5e");
    setTimeout(() => chrome.action.setBadgeText({ text: "" }), 6000);
    throw err;
  }
}

async function setBadge(text, color) {
  await chrome.action.setBadgeText({ text });
  await chrome.action.setBadgeBackgroundColor({ color });
}

async function pushHistory(entry) {
  const { history = [] } = await chrome.storage.local.get(["history"]);
  history.unshift(entry);
  await chrome.storage.local.set({ history: history.slice(0, 25) });
}

// Popup uses the same submit logic on demand
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg && msg.type === "submit-url" && typeof msg.url === "string") {
    sendToEchoStream(msg.url)
      .then((r) => sendResponse(r))
      .catch((e) => sendResponse({ ok: false, error: String(e && e.message || e) }));
    return true; // keep the message channel open for the async response
  }
  return false;
});
