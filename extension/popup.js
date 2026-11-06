// popup.js — giao diện cài đặt + cập nhật 1 chạm.
const DEFAULT_SERVER = "http://127.0.0.1:8000";
const $ = (id) => document.getElementById(id);

let serverUrl = DEFAULT_SERVER;
let pendingUpdateUrl = "";

async function getServer() {
  const s = await chrome.storage.sync.get("serverUrl");
  serverUrl = (s.serverUrl || DEFAULT_SERVER).replace(/\/$/, "");
  return serverUrl;
}
async function api(path, opts) {
  const r = await fetch(serverUrl + path, opts);
  if (!r.ok) throw new Error("HTTP " + r.status);
  return r.json();
}
function setStatus(msg, ok) {
  const el = $("status");
  el.textContent = msg;
  el.className = "status " + (ok === true ? "ok" : ok === false ? "bad" : "");
}

async function loadAll() {
  await getServer();
  try {
    const h = await api("/health");
    setStatus(`✅ Server đang chạy — v${h.version} | LLM: ${h.llm.reachable ? "kết nối được" : "CHƯA kết nối được (" + h.llm.base_url + ")"}`, h.llm.reachable);
    $("curVer").textContent = "v" + h.version;
  } catch (e) {
    setStatus("⚠️ Chưa kết nối được server — bật START_WINDOWS.bat trên máy anh rồi mở lại popup.", false);
    $("curVer").textContent = "?";
  }
  try {
    const v = await api("/api/voices");
    const sel = $("voice");
    sel.innerHTML = "";
    const addGroup = (label, items) => {
      if (!items.length) return;
      const g = document.createElement("optgroup");
      g.label = label;
      for (const it of items) {
        const o = document.createElement("option");
        o.value = it.id; o.textContent = it.label;
        g.appendChild(o);
      }
      sel.appendChild(g);
    };
    addGroup("VieNeu-TTS (local, mặc định)", v.vieneu_presets || []);
    addGroup("Giọng clone của anh", [v.clone].concat(v.custom || []));
    addGroup("Edge-TTS (cần mạng, dự phòng)", v.edge || []);
    sel.value = v.default || sel.options[0]?.value || "";
  } catch (e) { /* server chưa chạy: để trống */ }
  try {
    const s = await api("/api/settings");
    $("preset").value = s.llm_preset || "unsloth";
    $("baseUrl").value = s.llm_base_url || "";
    $("model").value = s.llm_model || "";
    $("duck").value = s.duck_volume ?? 0.15;
    $("duckVal").textContent = Math.round(($("duck").value) * 100) + "% (tiếng gốc còn " + Math.round($("duck").value * 100) + "%)";
    $("glossary").value = (s.glossary || []).map((g) => `${g.en} = ${g.vi}`).join("\n");
    if (s.voice) $("voice").value = s.voice;
  } catch (e) { /* bỏ qua */ }
  const st = await chrome.storage.sync.get(["dubEnabled", "subMode"]);
  $("enabled").checked = !!st.dubEnabled;
  if (st.subMode) $("subMode").value = st.subMode;
}

$("duck").addEventListener("input", () => {
  $("duckVal").textContent = Math.round($("duck").value * 100) + "% (tiếng gốc còn " + Math.round($("duck").value * 100) + "%)";
});
$("preset").addEventListener("change", () => {
  const presets = { unsloth: "http://127.0.0.1:8888/v1", deepseek: "https://api.deepseek.com/v1", ollama: "http://127.0.0.1:11434/v1", lmstudio: "http://127.0.0.1:1234/v1", gemini: "https://generativelanguage.googleapis.com/v1beta/openai", custom: "" };
  $("baseUrl").value = presets[$("preset").value] ?? "";
});
$("scanModels").addEventListener("click", async () => {
  $("modelList").textContent = "Đang quét...";
  try {
    const data = await api("/v1/models");
    const ids = (data.data || []).map((m) => m.id);
    $("modelList").textContent = ids.length ? "Có: " + ids.slice(0, 5).join(", ") + (ids.length > 5 ? "..." : "") : "Không thấy model nào.";
    if (ids.length && !$("model").value) $("model").value = ids[0];
  } catch (e) { $("modelList").textContent = "Quét lỗi — kiểm tra server + LLM backend."; }
});
$("refreshVoices").addEventListener("click", loadAll);
$("addVoice").addEventListener("click", () => {
  $("voiceName").hidden = false;
  $("voiceFile").click();
});
$("voiceFile").addEventListener("change", async () => {
  const f = $("voiceFile").files[0];
  const name = ($("voiceName").value || "").trim() || (f ? f.name.replace(/\.[^.]+$/, "") : "");
  if (!f || !name) { alert("Chọn file mẫu giọng và gõ tên giọng."); return; }
  const fd = new FormData();
  fd.append("name", name);
  fd.append("file", f);
  try {
    const r = await fetch(serverUrl + "/api/voices/add", { method: "POST", body: fd });
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || "Lỗi");
    alert("Đã thêm giọng: " + data.voice.label + ". Chọn giọng này trong danh sách rồi bấm Lưu.");
    loadAll();
  } catch (e) { alert("Thêm giọng lỗi: " + e.message); }
});
$("save").addEventListener("click", async () => {
  const glossary = $("glossary").value.split("\n").map((l) => l.trim()).filter(Boolean)
    .map((l) => { const [en, vi] = l.split("=").map((x) => x.trim()); return en ? { en, vi: vi || en } : null; })
    .filter(Boolean);
  try {
    await api("/api/settings", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({
      llm_preset: $("preset").value, llm_base_url: $("baseUrl").value.trim(),
      llm_model: $("model").value.trim(), voice: $("voice").value,
      duck_volume: parseFloat($("duck").value), glossary,
    })});
    await chrome.storage.sync.set({ serverUrl, dubEnabled: $("enabled").checked, subMode: $("subMode").value, duckVolume: parseFloat($("duck").value) });
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (tab?.id) chrome.tabs.sendMessage(tab.id, { type: "settings-changed" }).catch(() => {});
    setStatus("✅ Đã lưu cài đặt.", true);
  } catch (e) { setStatus("❌ Lưu lỗi: " + e.message, false); }
});
$("enabled").addEventListener("change", async () => {
  await chrome.storage.sync.set({ dubEnabled: $("enabled").checked });
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (tab?.id) chrome.tabs.sendMessage(tab.id, { type: "dub-toggle" }).catch(() => {});
});

// ---- Cập nhật 1 chạm ----
$("checkUpdate").addEventListener("click", async () => {
  $("updateInfo").textContent = "Đang kiểm tra...";
  $("applyUpdate").hidden = true;
  try {
    const data = await new Promise((resolve, reject) => {
      chrome.runtime.sendMessage({ type: "update-check" }, (res) => {
        if (chrome.runtime.lastError) reject(new Error(chrome.runtime.lastError.message));
        else if (!res?.ok) reject(new Error(res?.error || "Lỗi"));
        else resolve(res.data);
      });
    });
    if (data.status === "not_configured") {
      $("updateInfo").textContent = "Chưa cấu hình nguồn cập nhật (UPDATE_SOURCE trong .env). Xem README mục Cập nhật.";
    } else if (data.status === "up_to_date") {
      $("updateInfo").textContent = `✅ Đã là bản mới nhất (v${data.current}).`;
    } else if (data.status === "update_available") {
      pendingUpdateUrl = data.download_url || "";
      $("updateInfo").textContent = `⬆️ Có bản mới v${data.latest} (đang dùng v${data.current}).\n${data.changelog ? "Thay đổi: " + data.changelog.slice(0, 300) : ""}`;
      $("applyUpdate").hidden = false;
      $("applyUpdate").textContent = `⬆️ Cập nhật lên v${data.latest} ngay`;
    } else {
      $("updateInfo").textContent = "Kiểm tra lỗi: " + (data.message || JSON.stringify(data));
    }
  } catch (e) { $("updateInfo").textContent = "Kiểm tra lỗi: " + e.message + " (server có đang chạy không?)"; }
});
$("applyUpdate").addEventListener("click", async () => {
  $("applyUpdate").disabled = true;
  $("updateInfo").textContent = "Đang tải bản mới và cập nhật... server sẽ khởi động lại trong 10-20 giây. Đừng tắt cửa sổ này.";
  try {
    await new Promise((resolve, reject) => {
      chrome.runtime.sendMessage({ type: "update-apply", downloadUrl: pendingUpdateUrl }, (res) => {
        if (chrome.runtime.lastError) reject(new Error(chrome.runtime.lastError.message));
        else if (!res?.ok) reject(new Error(res?.data?.detail || res?.error || "Lỗi"));
        else resolve(res.data);
      });
    });
    // chờ server sống lại
    for (let i = 0; i < 20; i++) {
      await new Promise((r) => setTimeout(r, 2000));
      try { const h = await api("/health"); $("updateInfo").textContent = `✅ Cập nhật xong! Server đã chạy lại — bản v${h.version}.`; $("applyUpdate").hidden = true; loadAll(); return; }
      catch (e) { /* vẫn đang khởi động lại */ }
    }
    $("updateInfo").textContent = "Server chưa lên lại sau 40 giây — kiểm tra cửa sổ server trên máy anh.";
  } catch (e) { $("updateInfo").textContent = "Cập nhật lỗi: " + e.message; }
  $("applyUpdate").disabled = false;
});

document.addEventListener("DOMContentLoaded", loadAll);
