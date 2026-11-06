// background.js — service worker (Manifest V3).
// Giữ THẬT MỎNG theo thiết kế: chỉ chuyển tiếp phím tắt + kiểm tra/cài cập nhật.
// Mọi việc nặng (dịch, đọc, cache) đều nằm ở server.py, nên cập nhật server
// là đủ, không cần đụng extension.

const DEFAULT_SERVER = "http://127.0.0.1:8000";

async function getServerUrl() {
  const { serverUrl } = await chrome.storage.sync.get("serverUrl");
  return (serverUrl || DEFAULT_SERVER).replace(/\/$/, "");
}

async function sendToActiveTab(msg) {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (tab && tab.id) chrome.tabs.sendMessage(tab.id, msg).catch(() => {});
}

chrome.commands.onCommand.addListener(async (command) => {
  if (command === "toggle-dub") sendToActiveTab({ type: "dub-toggle" });
  if (command === "cycle-subtitle") sendToActiveTab({ type: "subtitle-cycle" });
});

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  (async () => {
    try {
      const server = await getServerUrl();
      if (msg.type === "update-check") {
        const r = await fetch(`${server}/api/update/check`);
        sendResponse({ ok: true, data: await r.json() });
      } else if (msg.type === "update-apply") {
        const r = await fetch(`${server}/api/update/apply`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ download_url: msg.downloadUrl || "" }),
        });
        sendResponse({ ok: r.ok, data: await r.json().catch(() => ({})) });
      } else if (msg.type === "server-health") {
        const r = await fetch(`${server}/health`);
        sendResponse({ ok: r.ok, data: await r.json().catch(() => ({})) });
      } else if (msg.type === "open-tab") {
        await chrome.tabs.create({ url: msg.url });
        sendResponse({ ok: true });
      }
    } catch (e) {
      sendResponse({ ok: false, error: String(e && e.message || e) });
    }
  })();
  return true; // giữ cổng message mở cho async
});
