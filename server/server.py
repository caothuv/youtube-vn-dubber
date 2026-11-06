#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
youtube-vn-dubber — server.py
Local FastAPI server cho extension lồng tiếng Việt YouTube.

Vai trò:
  1. Dịch phụ đề Anh -> Việt qua cổng OpenAI-Compatible (/v1/chat/completions)
     của Unsloth / DeepSeek / Ollama / LM Studio / Gemini (cấu hình trong .env).
  2. Đọc tiếng Việt bằng VieNeu-TTS v3 Turbo (mặc định, chạy CPU, 0 GB VRAM,
     clone giọng từ mẫu 3-8 giây) hoặc Edge-TTS (dự phòng, cần mạng).
  3. Cache vĩnh viễn bản dịch + file âm thanh trên đĩa (xem lại là phát ngay).
  4. Tự cập nhật 1 chạm: /api/update/check + /api/update/apply.

Chạy:  python server.py            (mặc định cổng 8000)
       Trên Windows: bấm đúp START_WINDOWS.bat
"""
import asyncio
import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
from pathlib import Path
from urllib.parse import urlparse

import httpx
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response

# ---------------------------------------------------------------- paths
BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
CACHE_DIR = BASE_DIR / "cache"
AUDIO_DIR = CACHE_DIR / "audio"
TRANS_CACHE_FILE = CACHE_DIR / "translations.json"
CONFIG_FILE = BASE_DIR / "config.json"
VERSION_FILE = BASE_DIR / "version.json"
CUSTOM_VOICES_DIR = BASE_DIR / "custom_voices"
CUSTOM_VOICES_FILE = CUSTOM_VOICES_DIR / "voices.json"
LOG_FILE = BASE_DIR / "server.log"

for d in (CACHE_DIR, AUDIO_DIR, CUSTOM_VOICES_DIR):
    d.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler(LOG_FILE, encoding="utf-8")],
)
log = logging.getLogger("dubber")

# ---------------------------------------------------------------- .env
def load_dotenv(path: Path):
    """Đọc file .env kiểu KEY=VALUE đơn giản (không cần thư viện ngoài)."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        os.environ.setdefault(key, val)

load_dotenv(BASE_DIR / ".env")
load_dotenv(ROOT_DIR / ".env")

def env(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()

# ---------------------------------------------------------------- version
def current_version() -> str:
    try:
        return json.loads(VERSION_FILE.read_text(encoding="utf-8")).get("version", "0.0.0")
    except Exception:
        return "0.0.0"

VERSION = current_version()
PORT = int(env("PORT", "8000") or 8000)

# ---------------------------------------------------------------- config
DEFAULT_SETTINGS = {
    "llm_preset": "unsloth",          # unsloth | deepseek | ollama | lmstudio | gemini | custom
    "llm_base_url": env("LLM_BASE_URL", "http://127.0.0.1:8888/v1"),
    "llm_api_key": env("LLM_API_KEY", "local"),
    "llm_model": env("LLM_MODEL", ""),   # trống = tự quét từ /v1/models
    "voice": env("TTS_VOICE", "Minh Triết"),   # tên preset VieNeu, "clone", hoặc "edge:..."
    "clone_ref": env("CLONE_REF", ""),         # đường dẫn file mẫu giọng clone
    "duck_volume": float(env("DUCK_VOLUME", "0.15") or 0.15),
    "glossary": [],                   # [{"en": "thread", "vi": "luồng xử lý"}]
}

PRESETS = {
    "unsloth":  {"base_url": "http://127.0.0.1:8888/v1", "api_key": "local", "label": "Unsloth Desktop (local)"},
    "deepseek": {"base_url": "https://api.deepseek.com/v1", "api_key": env("DEEPSEEK_API_KEY", ""), "label": "DeepSeek API"},
    "ollama":   {"base_url": "http://127.0.0.1:11434/v1", "api_key": "local", "label": "Ollama (local)"},
    "lmstudio": {"base_url": "http://127.0.0.1:1234/v1", "api_key": "local", "label": "LM Studio (local)"},
    "gemini":   {"base_url": "https://generativelanguage.googleapis.com/v1beta/openai", "api_key": env("GEMINI_API_KEY", ""), "label": "Google Gemini"},
    "custom":   {"base_url": "", "api_key": "", "label": "Tùy chỉnh"},
}

def load_settings() -> dict:
    s = dict(DEFAULT_SETTINGS)
    try:
        if CONFIG_FILE.exists():
            s.update(json.loads(CONFIG_FILE.read_text(encoding="utf-8")))
    except Exception as e:
        log.warning("Không đọc được config.json: %s", e)
    # preset đè base_url/api_key khi preset không phải custom
    preset = PRESETS.get(s.get("llm_preset", "unsloth"), PRESETS["unsloth"])
    if s.get("llm_preset") != "custom":
        s["llm_base_url"] = preset["base_url"]
        if preset["api_key"]:
            s["llm_api_key"] = preset["api_key"]
    return s

def save_settings(s: dict):
    CONFIG_FILE.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")

SETTINGS = load_settings()

# ---------------------------------------------------------------- helpers
def sha1(*parts: str) -> str:
    h = hashlib.sha1()
    for p in parts:
        h.update(str(p).encode("utf-8"))
    return h.hexdigest()[:20]

def strip_think(text: str) -> str:
    """Bỏ khối <think>...</think> của model reasoning (Qwen3, DeepSeek-R1...)."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
    return text.strip().strip('"').strip("'").strip()

def split_sentences(text: str, limit: int = 200):
    """Chẻ câu dài thành đoạn <= limit ký tự, ưu tiên cắt ở dấu câu."""
    text = " ".join(text.split())
    if len(text) <= limit:
        return [text]
    chunks, buf = [], ""
    for piece in re.split(r"(?<=[.!?…:;])\s+", text):
        if len(buf) + len(piece) + 1 <= limit:
            buf = (buf + " " + piece).strip()
        else:
            if buf:
                chunks.append(buf)
            if len(piece) > limit:  # câu đơn quá dài: cắt ở dấu phẩy
                sub, cur = [], ""
                for w in piece.split(" "):
                    if len(cur) + len(w) + 1 > limit:
                        sub.append(cur)
                        cur = w
                    else:
                        cur = (cur + " " + w).strip()
                if cur:
                    sub.append(cur)
                chunks.extend(sub)
                buf = ""
            else:
                buf = piece
    if buf:
        chunks.append(buf)
    return [c for c in chunks if c]

def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default

def save_json(path: Path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None

# ---------------------------------------------------------------- app
app = FastAPI(title="youtube-vn-dubber server", version=VERSION)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=False,
    allow_methods=["*"], allow_headers=["*"],
)

# ================================================================ TTS: VieNeu
_tts_lock = threading.Lock()
_tts = None

def get_vieneu():
    """Nạp VieNeu-TTS v3 Turbo (lazy, chỉ khi cần đọc lần đầu)."""
    global _tts
    if _tts is None:
        from vieneu import Vieneu
        _tts = Vieneu()
        log.info("VieNeu-TTS đã nạp xong.")
    return _tts

def vieneu_presets():
    try:
        tts = get_vieneu()
        out = []
        for item in tts.list_preset_voices():
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                out.append({"id": item[1], "label": item[0]})
            else:
                out.append({"id": str(item), "label": str(item)})
        return out
    except Exception as e:
        log.warning("Không lấy được preset VieNeu: %s", e)
        return []

def tts_vieneu(text: str, voice: str, ref_audio: str = "") -> Path:
    """Đọc 1 đoạn tiếng Việt bằng VieNeu, trả về file WAV (48kHz)."""
    import numpy as np
    tts = get_vieneu()
    chunks = split_sentences(text, 200)
    audios = []
    with _tts_lock:
        for ch in chunks:
            kwargs = {"denoise": True}
            if ref_audio:
                kwargs["ref_audio"] = ref_audio
            elif voice:
                kwargs["voice"] = voice
            audios.append(tts.infer(ch, **kwargs))
    merged = np.concatenate(audios) if len(audios) > 1 else audios[0]
    tmp = Path(tempfile.mktemp(suffix=".wav"))
    tts.save(merged, tmp)
    return tmp

def wav_duration(path: Path) -> float:
    try:
        import wave
        with wave.open(str(path), "rb") as w:
            return w.getnframes() / w.getframerate()
    except Exception:
        return 0.0

def to_mp3_if_possible(wav_path: Path) -> Path:
    """Đổi WAV -> MP3 nếu có ffmpeg, không thì giữ WAV."""
    if not ffmpeg_available():
        return wav_path
    mp3_path = wav_path.with_suffix(".mp3")
    r = subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(wav_path),
         "-codec:a", "libmp3lame", "-q:a", "4", str(mp3_path)],
        capture_output=True, text=True)
    if r.returncode == 0 and mp3_path.exists():
        wav_path.unlink(missing_ok=True)
        return mp3_path
    return wav_path

# ================================================================ TTS: Edge (dự phòng)
EDGE_VOICES = [
    {"id": "edge:vi-VN-NamMinhNeural", "label": "Nam Minh (Edge, cần mạng)"},
    {"id": "edge:vi-VN-NamMinhNeural-deep", "label": "Nam Minh Deep -4Hz (Edge, cần mạng)"},
    {"id": "edge:vi-VN-HoaiMyNeural", "label": "Hoài My (Edge, cần mạng)"},
]

async def _edge_synthesize(text: str, voice_id: str, out_path: Path):
    import edge_tts
    deep = voice_id.endswith("-deep")
    base = voice_id.replace("-deep", "")
    kwargs = {}
    if deep:
        kwargs["pitch"] = "-4Hz"
    comm = edge_tts.Communicate(text, base, **kwargs)
    await comm.save(str(out_path))

def tts_edge(text: str, voice_id: str) -> Path:
    """Edge-TTS: chỉ là dự phòng khi VieNeu lỗi; BẮT BUỘC có mạng."""
    tmp = Path(tempfile.mktemp(suffix=".mp3"))
    asyncio.run(_edge_synthesize(text, voice_id.replace("edge:", ""), tmp))
    return tmp

def speak(text: str, voice: str, ref_audio: str = "") -> Path:
    """Đọc 1 đoạn tiếng Việt. Mặc định VieNeu; edge:... thì dùng Edge-TTS."""
    if voice.startswith("edge:"):
        return tts_edge(text, voice)
    return tts_vieneu(text, voice, ref_audio)

# ================================================================ Dịch: LLM qua /chat/completions
TRANSLATE_SYSTEM = (
    "Bạn là phiên dịch viên Anh-Việt cho video YouTube. Dịch câu phụ đề sang "
    "tiếng Việt nói tự nhiên, ngắn gọn, dễ nghe bằng tai nghe, giữ đúng ý gốc.\n"
    "QUY TẮC BẮT BUỘC:\n"
    "- GIỮ NGUYÊN chính tả gốc của mọi từ mượn / thuật ngữ tiếng Anh "
    "(chatbot, prompt, AI agent, API, tab, thread, yield...). KHÔNG viết phiên âm "
    "kiểu 'chát-bót', 'prôm'.\n"
    "- Chỉ trả về ĐÚNG 1 câu tiếng Việt đã dịch, không giải thích, không thêm "
    "chữ nào khác, không dùng markdown.\n"
    "- Nếu câu gốc đã là tiếng Việt thì trả lại y nguyên."
)

def _is_loopback(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host in ("localhost", "127.0.0.1", "::1")

def smart_client(url: str, timeout: float) -> httpx.Client:
    """Client HTTP. URL localhost thì KHÔNG đi qua proxy hệ thống
    (proxy không bao giờ tới được localhost); URL ngoài thì đi proxy như thường."""
    if _is_loopback(url):
        return httpx.Client(timeout=timeout, trust_env=False, follow_redirects=True)
    return httpx.Client(timeout=timeout, follow_redirects=True)

def llm_chat(messages, timeout=120.0):
    """Gọi /v1/chat/completions của backend LLM đang chọn. Trả về text thô."""
    s = SETTINGS
    base = (s.get("llm_base_url") or "").rstrip("/")
    key = s.get("llm_api_key") or "local"
    model = s.get("llm_model") or ""
    if not model:
        model = detect_model(base, key) or "default"
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    payload = {"model": model, "messages": messages, "temperature": 0.3, "stream": False}
    with smart_client(base, timeout) as client:
        r = client.post(f"{base}/chat/completions", json=payload, headers=headers)
        r.raise_for_status()
        data = r.json()
    text = data["choices"][0]["message"]["content"]
    return strip_think(text or "")

def detect_model(base: str, key: str):
    """Hỏi /v1/models lấy model đầu tiên (cho Unsloth/Ollama/LM Studio)."""
    try:
        headers = {"Authorization": f"Bearer {key}"}
        with smart_client(base, 10.0) as client:
            r = client.get(f"{base}/models", headers=headers)
            r.raise_for_status()
            models = r.json().get("data", [])
        if models:
            return models[0].get("id", "")
    except Exception as e:
        log.warning("Không quét được /v1/models ở %s: %s", base, e)
    return ""

def glossary_text() -> str:
    items = SETTINGS.get("glossary") or []
    if not items:
        return ""
    lines = []
    for g in items:
        if isinstance(g, dict) and g.get("en"):
            lines.append(f'- "{g["en"]}" -> "{g.get("vi", g["en"])}"')
    return ("\nTừ điển thuật ngữ riêng (dịch đúng theo đây):\n" + "\n".join(lines)) if lines else ""

def translate_en_vi(text: str, title: str = "", channel: str = "") -> str:
    """Dịch 1 câu Anh -> Việt, có cache đĩa. Trả về câu Việt."""
    text = " ".join((text or "").split())
    if not text:
        return ""
    cache = load_json(TRANS_CACHE_FILE, {})
    key = sha1(text, title, channel, glossary_text(), SETTINGS.get("llm_model", ""))
    if key in cache:
        return cache[key]
    ctx = ""
    if title or channel:
        ctx = f'\nNgữ cảnh video: tiêu đề "{title}", kênh "{channel}".'
    user = f"{ctx}{glossary_text()}\nDịch câu này sang tiếng Việt:\n{text}"
    vi = llm_chat([
        {"role": "system", "content": TRANSLATE_SYSTEM},
        {"role": "user", "content": user},
    ])
    if vi:
        cache[key] = vi
        save_json(TRANS_CACHE_FILE, cache)
    return vi

def audio_duration(path: Path) -> float:
    """Thời lượng file âm thanh (mp3/wav). Dùng ffprobe nếu có, không thì wave."""
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                            "format=duration", "-of", "csv=p=0", str(path)],
                           capture_output=True, text=True, timeout=10)
        return float(r.stdout.strip())
    except Exception:
        return wav_duration(path)

# ================================================================ Cache âm thanh
def audio_cache_path(video_id: str, vi_text: str, voice: str, suffix: str = "") -> Path:
    name = f"{sha1(video_id, vi_text, voice)}"
    if suffix:
        return AUDIO_DIR / f"{name}{suffix}"
    for ext in (".mp3", ".wav"):
        p = AUDIO_DIR / f"{name}{ext}"
        if p.exists():
            return p
    return AUDIO_DIR / f"{name}.wav"

# ================================================================ API
@app.get("/health")
def health():
    try:
        base = SETTINGS.get("llm_base_url", "")
        with smart_client(base, 5.0) as c:
            r = c.get(f"{base.rstrip('/')}/models",
                      headers={"Authorization": f"Bearer {SETTINGS.get('llm_api_key', 'local')}"})
            llm_ok = r.status_code == 200
    except Exception:
        llm_ok = False
    total_mb = sum(p.stat().st_size for p in AUDIO_DIR.glob("*") if p.is_file()) / 1e6
    return {
        "status": "ok", "version": VERSION,
        "tts": "vieneu" if _tts is not None else "vieneu-chua-nap",
        "llm": {"base_url": SETTINGS.get("llm_base_url"), "reachable": llm_ok,
                "model": SETTINGS.get("llm_model") or "(tu-dong-quet)"},
        "cache_audio_mb": round(total_mb, 1),
        "ffmpeg": ffmpeg_available(),
    }

@app.get("/version")
def version():
    return {"version": VERSION, "app": "youtube-vn-dubber-server"}

@app.get("/v1/models")
def list_models():
    base = SETTINGS.get("llm_base_url", "")
    key = SETTINGS.get("llm_api_key", "local")
    try:
        with smart_client(base, 10.0) as c:
            r = c.get(f"{base.rstrip('/')}/models", headers={"Authorization": f"Bearer {key}"})
            r.raise_for_status()
            return r.json()
    except Exception as e:
        raise HTTPException(502, f"Không lấy được danh sách model từ {base}: {e}")

@app.get("/api/voices")
def list_voices():
    custom = load_json(CUSTOM_VOICES_FILE, {"voices": []}).get("voices", [])
    return {
        "default": SETTINGS.get("voice", "Minh Triết"),
        "vieneu_presets": vieneu_presets(),
        "clone": {"id": "clone", "label": "Giọng clone (mẫu trong custom_voices/)"},
        "custom": custom,
        "edge": EDGE_VOICES,
    }

@app.post("/api/voices/add")
async def add_voice(name: str = Form(...), file: UploadFile = File(...)):
    """Thêm giọng clone mới: tải file mẫu giọng 3-10 giây lên."""
    if not name.strip():
        raise HTTPException(400, "Thiếu tên giọng.")
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", name.strip())[:40]
    dest = CUSTOM_VOICES_DIR / f"{safe}.wav"
    data = await file.read()
    if len(data) < 1000:
        raise HTTPException(400, "File mẫu quá nhỏ, cần 3-10 giây giọng sạch.")
    dest.write_bytes(data)
    voices = load_json(CUSTOM_VOICES_FILE, {"voices": []})
    entry = {"id": f"custom:{safe}", "label": name.strip(), "ref": str(dest.name)}
    voices["voices"] = [v for v in voices.get("voices", []) if v.get("id") != entry["id"]]
    voices["voices"].append(entry)
    save_json(CUSTOM_VOICES_FILE, voices)
    return {"ok": True, "voice": entry}

@app.get("/api/audio/{name}")
def serve_audio(name: str):
    p = AUDIO_DIR / Path(name).name
    if not p.exists() or p.suffix.lower() not in (".mp3", ".wav"):
        raise HTTPException(404, "Không có file âm thanh này.")
    media = "audio/mpeg" if p.suffix.lower() == ".mp3" else "audio/wav"
    return FileResponse(p, media_type=media)

@app.post("/v1/audio/speech")
async def openai_tts(req: Request):
    """Cổng TTS chuẩn OpenAI: {model, input, voice, response_format}."""
    body = await req.json()
    text = (body.get("input") or "").strip()
    voice = (body.get("voice") or SETTINGS.get("voice", "Minh Triết")).strip()
    fmt = (body.get("response_format") or "mp3").lower()
    if not text:
        raise HTTPException(400, "Thiếu input.")
    ref = ""
    if voice == "clone":
        ref = SETTINGS.get("clone_ref") or ""
        if not ref:
            customs = load_json(CUSTOM_VOICES_FILE, {"voices": []}).get("voices", [])
            if customs:
                ref = str(CUSTOM_VOICES_DIR / customs[0]["ref"])
        voice = SETTINGS.get("voice", "Minh Triết")
    elif voice.startswith("custom:"):
        customs = load_json(CUSTOM_VOICES_FILE, {"voices": []}).get("voices", [])
        hit = [c for c in customs if c.get("id") == voice]
        if not hit:
            raise HTTPException(404, f"Không có giọng {voice}.")
        ref = str(CUSTOM_VOICES_DIR / hit[0]["ref"])
        voice = SETTINGS.get("voice", "Minh Triết")
    try:
        wav = speak(text, voice, ref)
    except Exception as e:
        log.exception("TTS lỗi")
        raise HTTPException(500, f"TTS lỗi: {e}")
    if fmt == "wav":
        return FileResponse(wav, media_type="audio/wav", filename="speech.wav")
    out = to_mp3_if_possible(wav)
    return FileResponse(out, media_type="audio/mpeg" if out.suffix == ".mp3" else "audio/wav",
                        filename="speech.mp3" if out.suffix == ".mp3" else "speech.wav")

@app.post("/api/translate")
async def api_translate(req: Request):
    body = await req.json()
    text = (body.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "Thiếu text.")
    try:
        vi = translate_en_vi(text, body.get("title", ""), body.get("channel", ""))
    except Exception as e:
        log.exception("Dịch lỗi")
        raise HTTPException(502, f"Dịch lỗi (kiểm tra LLM backend): {e}")
    return {"en": text, "vi": vi}

def dub_one_cue(video_id: str, index: int, en_text: str, title: str, channel: str):
    """Dịch + đọc 1 cue. Trả dict kết quả (dùng lại cache nếu có)."""
    s = SETTINGS
    voice = s.get("voice", "Minh Triết")
    ref = ""
    if voice == "clone":
        ref = s.get("clone_ref") or ""
        if not ref:
            customs = load_json(CUSTOM_VOICES_FILE, {"voices": []}).get("voices", [])
            if customs:
                ref = str(CUSTOM_VOICES_DIR / customs[0]["ref"])
        voice = s.get("voice", "Minh Triết")
    elif voice.startswith("custom:"):
        customs = load_json(CUSTOM_VOICES_FILE, {"voices": []}).get("voices", [])
        hit = [c for c in customs if c.get("id") == voice]
        if hit:
            ref = str(CUSTOM_VOICES_DIR / hit[0]["ref"])
        voice = s.get("voice", "Minh Triết")
    vi = translate_en_vi(en_text, title, channel)
    if not vi:
        return {"index": index, "en": en_text, "vi": "", "audio_url": "",
                "duration": 0.0, "cached": False, "error": "Khong dich duoc cau nay."}
    path = audio_cache_path(video_id, vi, voice + ref)
    cached = path.exists()
    if not cached:
        tmp = speak(vi, voice, ref)
        out = to_mp3_if_possible(tmp)
        # LƯU Ý: tên file cache phải khớp định dạng thật (mp3 sau khi đổi).
        path = audio_cache_path(video_id, vi, voice + ref, suffix=out.suffix)
        shutil.move(str(out), str(path))
    return {"index": index, "en": en_text, "vi": vi,
            "audio_url": f"/api/audio/{path.name}",
            "duration": audio_duration(path),
            "cached": cached, "error": ""}

@app.post("/api/dub-cue")
async def api_dub_cue(req: Request):
    """Lồng 1 cue: dịch + đọc (hoặc trả cache). Extension gọi trước khi cue tới."""
    body = await req.json()
    en = (body.get("en_text") or body.get("text") or "").strip()
    if not en:
        raise HTTPException(400, "Thiếu en_text.")
    try:
        return dub_one_cue(body.get("video_id", ""), int(body.get("index", 0)),
                           en, body.get("title", ""), body.get("channel", ""))
    except Exception as e:
        log.exception("dub-cue lỗi")
        raise HTTPException(502, f"Lồng cue lỗi: {e}")

@app.post("/api/dub-batch")
async def api_dub_batch(req: Request):
    """Lồng trước nhiều cue 1 lần (prefetch). cues: [{index, en_text}]."""
    body = await req.json()
    cues = body.get("cues") or []
    if not isinstance(cues, list) or not cues:
        raise HTTPException(400, "Thiếu cues.")
    out = []
    for c in cues[:20]:  # giới hạn 20 cue / lần để khỏi kẹt
        try:
            out.append(dub_one_cue(body.get("video_id", ""), int(c.get("index", 0)),
                                   (c.get("en_text") or "").strip(),
                                   body.get("title", ""), body.get("channel", "")))
        except Exception as e:
            out.append({"index": c.get("index", 0), "en": c.get("en_text", ""),
                        "vi": "", "audio_url": "", "duration": 0.0,
                        "cached": False, "error": str(e)[:200]})
    return {"results": out}

@app.post("/api/summarize")
async def api_summarize(req: Request):
    """Tóm tắt video thành 5 gạch đầu dòng tiếng Việt."""
    body = await req.json()
    transcript = (body.get("transcript") or "").strip()
    title = body.get("title", "")
    if not transcript:
        raise HTTPException(400, "Thiếu transcript.")
    cache = load_json(CACHE_DIR / "summaries.json", {})
    key = sha1(body.get("video_id", ""), transcript[:2000])
    if key in cache:
        return {"summary": cache[key], "cached": True}
    prompt = (
        f"Tóm tắt video YouTube sau thành ĐÚNG 5 gạch đầu dòng tiếng Việt, "
        f"ngắn gọn, đủ ý chính, không thêm lời dẫn.\n"
        f"Tiêu đề: {title}\nNội dung (tiếng Anh, có thể cắt ngắn):\n{transcript[:12000]}"
    )
    try:
        text = llm_chat([
            {"role": "system", "content": "Bạn tóm tắt video bằng tiếng Việt, đúng 5 gạch đầu dòng, mỗi dòng 1 ý."},
            {"role": "user", "content": prompt},
        ], timeout=180.0)
    except Exception as e:
        log.exception("Tóm tắt lỗi")
        raise HTTPException(502, f"Tóm tắt lỗi: {e}")
    cache[key] = text
    save_json(CACHE_DIR / "summaries.json", cache)
    return {"summary": text, "cached": False}

@app.get("/api/settings")
def get_settings():
    s = dict(SETTINGS)
    s.pop("llm_api_key", None)
    s["presets"] = {k: {"base_url": v["base_url"], "label": v["label"]} for k, v in PRESETS.items()}
    return s

@app.post("/api/settings")
async def post_settings(req: Request):
    global SETTINGS
    body = await req.json()
    allowed = {"llm_preset", "llm_base_url", "llm_api_key", "llm_model",
               "voice", "clone_ref", "duck_volume", "glossary"}
    for k, v in body.items():
        if k in allowed:
            SETTINGS[k] = v
    save_settings(SETTINGS)
    SETTINGS = load_settings()
    return {"ok": True}

# ================================================================ Tự cập nhật 1 chạm
# Cơ chế: popup bấm "Cập nhật" -> server tải zip bản mới, kiểm tra xong thì
# chạy script update_server (bat/sh) rồi tự tắt. Script chờ server tắt hẳn,
# sao lưu file cũ, giải nén đè lên thư mục cài đặt (GIỮ LẠI cache/, .env,
# custom_voices/, config.json), rồi chạy lại START_WINDOWS.bat.
# Extension chạy bản giải nén thì KHÔNG tự cập nhật được — popup sẽ báo link
# tải zip mới + hướng dẫn bấm Làm mới ở chrome://extensions (xem README).

def _parse_version(v: str):
    parts = []
    for x in re.split(r"[.\-+]", str(v)):
        try:
            parts.append(int(x))
        except ValueError:
            parts.append(0)
    return tuple(parts + [0] * (3 - len(parts)))

def _fetch_latest():
    """Đọc nguồn cập nhật từ biến UPDATE_SOURCE (.env).
    - trống: chưa cấu hình.
    - 'owner/repo': GitHub Releases mới nhất.
    - URL tới version.json: {version, download_url, changelog}.
    """
    src = env("UPDATE_SOURCE", "").strip()
    if not src:
        return {"status": "not_configured",
                "message": "Chua cau hinh UPDATE_SOURCE trong .env (vd: owner/repo hoac URL file version.json)."}
    try:
        if src.startswith("http://") or src.startswith("https://"):
            with smart_client(src, 20.0) as c:
                r = c.get(src)
                r.raise_for_status()
                data = r.json()
            return {"status": "ok", "latest": str(data.get("version", "")),
                    "download_url": data.get("download_url", ""),
                    "changelog": data.get("changelog", "")}
        owner_repo = src.strip("/")
        with smart_client(f"https://api.github.com/repos/{owner_repo}/releases/latest", 20.0) as c:
            r = c.get(f"https://api.github.com/repos/{owner_repo}/releases/latest",
                      headers={"Accept": "application/vnd.github+json"})
            r.raise_for_status()
            data = r.json()
        assets = data.get("assets", [])
        dl = assets[0].get("browser_download_url", "") if assets else ""
        tag = str(data.get("tag_name", "")).lstrip("v")
        return {"status": "ok", "latest": tag, "download_url": dl,
                "changelog": data.get("body", "")}
    except Exception as e:
        return {"status": "error", "message": f"Khong doc duoc nguon cap nhat: {e}"}

@app.get("/api/update/check")
def update_check():
    info = _fetch_latest()
    if info.get("status") != "ok":
        return {"status": info["status"], "current": VERSION,
                "message": info.get("message", "")}
    latest = info.get("latest", "")
    if not latest or _parse_version(latest) <= _parse_version(VERSION):
        return {"status": "up_to_date", "current": VERSION, "latest": latest or VERSION}
    return {"status": "update_available", "current": VERSION, "latest": latest,
            "download_url": info.get("download_url", ""),
            "changelog": info.get("changelog", "")}

def _download_zip(url: str, dest: Path):
    with smart_client(url, 300.0) as c:
        with c.stream("GET", url) as r:
            r.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in r.iter_bytes(65536):
                    f.write(chunk)
    with zipfile.ZipFile(dest) as z:
        names = z.namelist()
        if not any(n.endswith("version.json") for n in names):
            raise ValueError("File zip khong co version.json — khong phai ban cap nhat dung.")
        bad = [n for n in names if n.startswith("/") or ".." in Path(n).parts]
        if bad:
            raise ValueError("File zip chua duong dan khong an toan.")
    return dest

def _apply_update(zip_path: Path):
    """Chạy script cập nhật rồi tắt server. Script tự làm phần còn lại."""
    script = (ROOT_DIR / "update_server.bat") if os.name == "nt" else (ROOT_DIR / "update_server.sh")
    if not script.exists():
        raise FileNotFoundError(f"Thieu script cap nhat: {script}")
    if os.name == "nt":
        subprocess.Popen(["cmd", "/c", str(script), str(zip_path), str(ROOT_DIR)],
                         creationflags=subprocess.CREATE_NEW_CONSOLE | subprocess.DETACHED_PROCESS,
                         close_fds=True)
    else:
        subprocess.Popen(["bash", str(script), str(zip_path), str(ROOT_DIR)],
                         start_new_session=True, close_fds=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # Tắt server sau 1 giây để updater chiếm chỗ (trả response trước đã).
    threading.Timer(1.0, lambda: os._exit(0)).start()

@app.post("/api/update/apply")
async def update_apply(req: Request):
    body = {}
    try:
        body = await req.json()
    except Exception:
        pass
    dry_run = bool(body.get("dry_run"))
    url = (body.get("download_url") or "").strip()
    if not url:
        info = _fetch_latest()
        if info.get("status") != "ok":
            raise HTTPException(400, info.get("message", "Khong tim duoc ban moi."))
        url = info.get("download_url", "")
    if not url:
        raise HTTPException(400, "Ban moi khong co link tai zip.")
    tmp = Path(tempfile.mktemp(suffix=".zip"))
    try:
        _download_zip(url, tmp)
        with zipfile.ZipFile(tmp) as z:
            vdata = None
            for n in z.namelist():
                if n.endswith("version.json"):
                    vdata = json.loads(z.read(n))
                    break
        new_ver = str((vdata or {}).get("version", "?"))
    except Exception as e:
        tmp.unlink(missing_ok=True)
        raise HTTPException(400, f"Tai/kiem tra ban moi loi: {e}")
    if dry_run:
        tmp.unlink(missing_ok=True)
        return {"ok": True, "dry_run": True, "new_version": new_ver,
                "message": "Da tai va kiem tra xong, chua ap dung."}
    try:
        _apply_update(tmp)
    except Exception as e:
        tmp.unlink(missing_ok=True)
        raise HTTPException(500, f"Khong chay duoc script cap nhat: {e}")
    return {"ok": True, "status": "restarting", "new_version": new_ver,
            "message": "Server dang cap nhat va khoi dong lai, doi 10-20 giay roi thu lai."}

# ---------------------------------------------------------------- main
if __name__ == "__main__":
    import uvicorn
    log.info("youtube-vn-dubber server v%s — http://127.0.0.1:%d", VERSION, PORT)
    log.info("LLM backend: %s (preset %s)", SETTINGS.get("llm_base_url"), SETTINGS.get("llm_preset"))
    log.info("Giong mac dinh: %s | ffmpeg: %s", SETTINGS.get("voice"), ffmpeg_available())
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="info")
