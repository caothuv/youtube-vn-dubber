// content.js — chạy trên trang xem YouTube (youtube.com/watch*).
// Việc nặng (dịch + đọc + cache) nằm ở server.py. File này chỉ:
//  - lấy phụ đề tiếng Anh của video (YouTube timedtext API),
//  - đặt lịch phát giọng Việt đúng mốc giờ của video,
//  - hạ nhỏ tiếng gốc còn ~15% khi giọng Việt đang đọc,
//  - tua / đổi tốc độ thì nhảy theo ngay,
//  - hiện phụ đề tiếng Việt (tùy chọn) + nút tóm tắt AI.
(() => {
  "use strict";

  const DEFAULT_SERVER = "http://127.0.0.1:8000";
  const PREFETCH_SECONDS = 15;   // lồng trước các câu sắp tới trong 15 giây
  const PREFETCH_COUNT = 3;      // tối đa 3 câu chờ sẵn
  const TICK_MS = 200;

  let serverUrl = DEFAULT_SERVER;
  let video = null, videoId = "", videoTitle = "", videoChannel = "";
  let cues = [];                 // [{index, start, end, en, vi, audioUrl}]
  let ready = new Map();         // index -> audioUrl
  let pending = new Set();       // index đang chờ server
  let enabled = false;
  let nativeBypass = false;      // video đã có rãnh tiếng Việt gốc
  let nativeChecked = false;
  let subMode = "vi";            // off | vi | both
  let duckVolume = 0.15;
  let savedVolume = 1, ducking = false;
  let currentIndex = -1;
  let audio = null;
  let btnDub = null, btnSum = null, subBox = null, modal = null;
  let statusTimer = null;

  // ------------------------------------------------------------ tiện ích
  const $ = (sel, root = document) => root.querySelector(sel);
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  function fmtTime(s) { const m = Math.floor(s / 60), ss = Math.floor(s % 60); return m + ":" + String(ss).padStart(2, "0"); }

  async function loadSettings() {
    const s = await chrome.storage.sync.get(["serverUrl", "duckVolume", "subMode", "dubEnabled"]);
    serverUrl = (s.serverUrl || DEFAULT_SERVER).replace(/\/$/, "");
    if (typeof s.duckVolume === "number") duckVolume = s.duckVolume;
    if (s.subMode) subMode = s.subMode;
    if (typeof s.dubEnabled === "boolean") enabled = s.dubEnabled;
  }

  async function serverGet(path) {
    const r = await fetch(serverUrl + path);
    if (!r.ok) throw new Error("Server trả lỗi " + r.status);
    return r.json();
  }
  async function serverPost(path, body) {
    const r = await fetch(serverUrl + path, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!r.ok) throw new Error("Server trả lỗi " + r.status);
    return r.json();
  }

  // ------------------------------------------------------------ lấy phụ đề
  async function fetchCaptions() {
    const base = `https://www.youtube.com/api/timedtext?v=${videoId}&fmt=json3`;
    for (const q of [`${base}&lang=en`, `${base}&lang=en&kind=asr`]) {
      try {
        const r = await fetch(q);
        if (!r.ok) continue;
        const data = await r.json();
        const events = (data.events || []).filter((e) => e.segs && e.segs.length);
        if (!events.length) continue;
        return events.map((e, i) => ({
          index: i,
          start: (e.tStartMs || 0) / 1000,
          end: ((e.tStartMs || 0) + (e.dDurationMs || 0)) / 1000,
          en: e.segs.map((s) => s.utf8 || "").join("").replace(/\n/g, " ").trim(),
        })).filter((c) => c.en);
      } catch (e) { /* thử cách khác */ }
    }
    return [];
  }

  // Đọc ytInitialPlayerResponse từ trang (cần chèn script vì content script
  // không thấy biến JS của trang). Chỉ để biết video có rãnh tiếng Việt gốc không.
  function detectNativeDub() {
    return new Promise((resolve) => {
      const done = (found) => { if (!nativeChecked) { nativeChecked = true; resolve(found); } };
      const onMsg = (ev) => {
        if (ev.source !== window || !ev.data || ev.data.type !== "YVDUB_PLAYER") return;
        window.removeEventListener("message", onMsg);
        const tracks = ev.data.audioTracks || [];
        done(tracks.some((t) => (t.languageCode || "").toLowerCase().startsWith("vi")));
      };
      window.addEventListener("message", onMsg);
      const sc = document.createElement("script");
      sc.textContent = `(() => {
        try {
          const pr = window.ytInitialPlayerResponse || {};
          const at = pr?.captions?.playerCaptionsTracklistRenderer?.audioTracks || [];
          window.postMessage({ type: "YVDUB_PLAYER",
            audioTracks: at.map(a => ({ languageCode: a.languageCode })) }, "*");
        } catch (e) { window.postMessage({ type: "YVDUB_PLAYER", audioTracks: [] }, "*"); }
      })();`;
      (document.head || document.documentElement).appendChild(sc);
      sc.remove();
      setTimeout(() => done(false), 3000); // quá 3 giây không trả lời thì coi như không có
    });
  }

  // ------------------------------------------------------------ giao diện
  function injectStyles() {
    if (document.getElementById("yvdub-css")) return;
    const link = document.createElement("link");
    link.id = "yvdub-css"; link.rel = "stylesheet"; link.type = "text/css";
    link.href = chrome.runtime.getURL("content.css");
    document.head.appendChild(link);
  }

  function makeButtons() {
    const bar = $(".ytp-right-controls");
    btnDub = document.createElement("button");
    btnDub.className = "ytp-button yvdub-btn";
    btnDub.title = "Bật / tắt lồng tiếng Việt AI (Alt+V)";
    btnDub.textContent = "🎧 AI Việt";
    btnDub.addEventListener("click", () => toggleDub());
    btnSum = document.createElement("button");
    btnSum.className = "ytp-button yvdub-btn";
    btnSum.title = "Tóm tắt video bằng AI";
    btnSum.textContent = "📝 Tóm tắt AI";
    btnSum.addEventListener("click", () => showSummary());
    if (bar) {
      bar.insertBefore(btnSum, bar.firstChild);
      bar.insertBefore(btnDub, bar.firstChild);
    } else {
      // dự phòng: nút nổi góc phải nếu không chèn được vào thanh YouTube
      const wrap = document.createElement("div");
      wrap.className = "yvdub-float";
      wrap.append(btnDub, btnSum);
      document.body.appendChild(wrap);
    }
    updateButtons();
  }

  function updateButtons() {
    if (!btnDub) return;
    btnDub.classList.toggle("yvdub-on", enabled);
    btnDub.textContent = enabled ? "🎧 AI Việt: BẬT" : "🎧 AI Việt";
    if (btnSum) btnSum.disabled = !cues.length;
  }

  function makeSubBox() {
    const player = $(".html5-video-player") || document.body;
    subBox = document.createElement("div");
    subBox.id = "yvdub-sub";
    subBox.className = "yvdub-sub";
    player.appendChild(subBox);
  }

  function renderSub(cue) {
    if (!subBox) return;
    if (subMode === "off" || !cue || !cue.vi) { subBox.style.display = "none"; return; }
    subBox.style.display = "block";
    subBox.innerHTML = "";
    const vi = document.createElement("div");
    vi.className = "yvdub-vi"; vi.textContent = cue.vi;
    subBox.appendChild(vi);
    if (subMode === "both") {
      const en = document.createElement("div");
      en.className = "yvdub-en"; en.textContent = cue.en;
      subBox.appendChild(en);
    }
  }

  function toast(msg, ms = 4000) {
    let t = $("#yvdub-toast");
    if (!t) { t = document.createElement("div"); t.id = "yvdub-toast"; document.body.appendChild(t); }
    t.textContent = msg; t.style.display = "block";
    clearTimeout(statusTimer);
    statusTimer = setTimeout(() => { t.style.display = "none"; }, ms);
  }

  // ------------------------------------------------------------ động cơ lồng tiếng
  function cueAt(t) {
    return cues.find((c) => t >= c.start && t < c.end) || null;
  }

  function ensureAudio() {
    if (!audio) {
      audio = new Audio();
      audio.preload = "auto";
      audio.addEventListener("ended", () => { setDuck(false); currentIndex = -1; });
      audio.addEventListener("error", () => { setDuck(false); });
    }
    return audio;
  }

  function setDuck(on) {
    if (!video) return;
    if (on && !ducking) { savedVolume = video.volume; video.volume = duckVolume; ducking = true; }
    if (!on && ducking) { video.volume = savedVolume; ducking = false; }
  }

  async function prefetch(fromTime) {
    if (!enabled || !cues.length) return;
    const upcoming = cues
      .filter((c) => c.start > fromTime && c.start <= fromTime + PREFETCH_SECONDS)
      .filter((c) => !ready.has(c.index) && !pending.has(c.index))
      .slice(0, PREFETCH_COUNT);
    if (!upcoming.length) return;
    upcoming.forEach((c) => pending.add(c.index));
    try {
      const res = await serverPost("/api/dub-batch", {
        video_id: videoId, title: videoTitle, channel: videoChannel,
        cues: upcoming.map((c) => ({ index: c.index, en_text: c.en })),
      });
      for (const r of res.results || []) {
        pending.delete(r.index);
        const cue = cues[r.index];
        if (r.audio_url && cue) { cue.vi = r.vi || cue.vi; cue.audioUrl = serverUrl + r.audio_url; ready.set(r.index, cue.audioUrl); }
      }
    } catch (e) {
      upcoming.forEach((c) => pending.delete(c.index));
    }
  }

  function tick() {
    if (!video || !enabled || nativeBypass) return;
    const t = video.currentTime;
    const cue = cueAt(t);
    if (cue && ready.has(cue.index)) {
      if (currentIndex !== cue.index) {
        const a = ensureAudio();
        a.src = ready.get(cue.index);
        a.playbackRate = Math.min(video.playbackRate || 1, 2);
        a.currentTime = Math.max(0, t - cue.start);
        a.play().catch(() => {});
        currentIndex = cue.index;
      }
      if (!video.paused && audio.paused) audio.play().catch(() => {});
      if (video.paused && !audio.paused) audio.pause();
      setDuck(true);
      renderSub(cue);
    } else {
      if (currentIndex !== -1) {
        // hết câu hoặc câu chưa có âm thanh: dừng giọng đọc, trả tiếng gốc
        if (audio && !audio.paused) audio.pause();
        setDuck(false);
        currentIndex = -1;
      }
      renderSub(cue && cue.vi ? cue : null);
      prefetch(t);
    }
  }

  function toggleDub(force) {
    enabled = typeof force === "boolean" ? force : !enabled;
    chrome.storage.sync.set({ dubEnabled: enabled });
    updateButtons();
    if (!enabled) {
      if (audio && !audio.paused) audio.pause();
      setDuck(false); currentIndex = -1; renderSub(null);
      toast("Đã tắt lồng tiếng AI.");
    } else {
      if (!cues.length) { toast("Video này không có phụ đề tiếng Anh nên chưa lồng được."); enabled = false; updateButtons(); return; }
      if (nativeBypass) { toast("Video đã có tiếng Việt gốc — đang dùng tiếng gốc. Bấm lại để ép dùng giọng AI."); nativeBypass = false; }
      toast("Đã bật lồng tiếng AI — đang chuẩn bị các câu sắp tới...");
      prefetch(video ? video.currentTime : 0);
    }
  }

  // ------------------------------------------------------------ tóm tắt AI
  async function showSummary() {
    if (!cues.length) { toast("Chưa có phụ đề để tóm tắt."); return; }
    if (modal) modal.remove();
    modal = document.createElement("div");
    modal.className = "yvdub-modal";
    modal.innerHTML = `<div class="yvdub-modal-box">
      <h3>📝 Tóm tắt video bằng AI</h3>
      <div class="yvdub-modal-body">Đang tóm tắt, chờ xíu...</div>
      <div class="yvdub-modal-actions">
        <button class="yvdub-btn2" id="yvdub-listen">🔊 Nghe tóm tắt</button>
        <button class="yvdub-btn2" id="yvdub-close">Đóng</button>
      </div></div>`;
    document.body.appendChild(modal);
    modal.querySelector("#yvdub-close").addEventListener("click", () => modal.remove());
    modal.querySelector("#yvdub-listen").addEventListener("click", async (ev) => {
      ev.target.disabled = true; ev.target.textContent = "Đang đọc...";
      try {
        const body = modal.querySelector(".yvdub-modal-body").textContent;
        const r = await fetch(serverUrl + "/v1/audio/speech", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ input: body, voice: "default", response_format: "mp3" }),
        });
        if (!r.ok) throw new Error("TTS lỗi " + r.status);
        const blob = await r.blob();
        new Audio(URL.createObjectURL(blob)).play().catch(() => {});
        ev.target.textContent = "🔊 Đang đọc...";
      } catch (e) { ev.target.textContent = "Đọc lỗi, thử lại sau"; }
    });
    try {
      const transcript = cues.map((c) => `[${fmtTime(c.start)}] ${c.en}`).join("\n");
      const res = await serverPost("/api/summarize", { video_id: videoId, title: videoTitle, channel: videoChannel, transcript });
      const body = modal.querySelector(".yvdub-modal-body");
      body.innerHTML = "";
      (res.summary || "").split("\n").filter((l) => l.trim()).forEach((line) => {
        const d = document.createElement("div");
        d.textContent = line.replace(/^[-•\s]+/, "• ");
        body.appendChild(d);
      });
    } catch (e) {
      modal.querySelector(".yvdub-modal-body").textContent = "Tóm tắt lỗi: " + (e.message || e) + " (kiểm tra server + LLM backend)";
    }
  }

  // ------------------------------------------------------------ khởi tạo theo video
  async function initForVideo() {
    const url = new URL(location.href);
    const id = url.searchParams.get("v");
    if (!id) return;
    if (id === videoId && video) return; // vẫn video cũ
    videoId = id;
    cues = []; ready.clear(); pending.clear(); currentIndex = -1; nativeBypass = false; nativeChecked = false;
    video = $("video");
    if (!video) { setTimeout(initForVideo, 1000); return; }
    videoTitle = document.title.replace(/ - YouTube$/, "");
    videoChannel = ($("ytd-channel-name a") || {}).textContent?.trim() || "";
    try {
      const h = await serverGet("/health").catch(() => null);
      if (!h) { toast("⚠️ Server lồng tiếng chưa chạy — bật START_WINDOWS.bat rồi tải lại trang."); }
    } catch (e) { /* bỏ qua, tick vẫn thử lại khi bật */ }
    nativeBypass = await detectNativeDub();
    cues = await fetchCaptions();
    updateButtons();
    if (nativeBypass && enabled) toast("Video đã có tiếng Việt gốc — đang dùng tiếng gốc.");
    if (!cues.length) toast("Video này không có phụ đề tiếng Anh nên chưa lồng được.");
    video.addEventListener("seeking", () => { if (audio && !audio.paused) audio.pause(); setDuck(false); currentIndex = -1; });
    video.addEventListener("ratechange", () => { if (audio) audio.playbackRate = Math.min(video.playbackRate || 1, 2); });
    video.addEventListener("pause", () => { if (audio && !audio.paused) audio.pause(); });
    video.addEventListener("play", () => { if (enabled) prefetch(video.currentTime); });
    setInterval(tick, TICK_MS);
    if (enabled) prefetch(video.currentTime);
  }

  chrome.runtime.onMessage.addListener((msg) => {
    if (msg.type === "dub-toggle") toggleDub();
    if (msg.type === "subtitle-cycle") {
      subMode = subMode === "off" ? "vi" : subMode === "vi" ? "both" : "off";
      chrome.storage.sync.set({ subMode });
      toast("Phụ đề: " + (subMode === "off" ? "Tắt" : subMode === "vi" ? "Chỉ tiếng Việt" : "Song ngữ Việt - Anh"));
      renderSub(cueAt(video ? video.currentTime : 0));
    }
    if (msg.type === "settings-changed") loadSettings().then(() => updateButtons());
  });

  // YouTube là trang SPA: đổi video không tải lại trang -> nghe sự kiện này.
  window.addEventListener("yt-navigate-finish", () => setTimeout(initForVideo, 800));

  (async () => {
    await loadSettings();
    injectStyles();
    // chờ thanh điều khiển YouTube xuất hiện rồi chèn nút
    for (let i = 0; i < 20 && !$(".ytp-right-controls"); i++) await sleep(500);
    makeButtons();
    makeSubBox();
    await initForVideo();
  })();
})();
