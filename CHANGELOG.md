# CHANGELOG — youtube-vn-dubber

## 0.1.0 — 2026-11-06 (bản đầu tiên)

- Lồng tiếng Việt gần-thời-gian-thực trên YouTube: lấy phụ đề tiếng Anh
  (timedtext), dịch qua LLM OpenAI-Compatible, đọc bằng VieNeu-TTS v3 Turbo.
- Giọng mặc định: preset VieNeu (Nam/Bắc/Trung) + clone giọng từ mẫu 3-10 giây
  (nút "Thêm giọng mới" trong popup). Edge-TTS (Nam Minh / Hoài My) là dự phòng.
- Lồng trước (prefetch) các câu sắp tới trong 15 giây; cache vĩnh viễn bản dịch
  + file âm thanh trên đĩa — xem lại / tua lại phát ngay.
- Hạ tiếng gốc còn 15% khi giọng Việt đang đọc; tua video ngắt câu cũ ngay;
  theo tốc độ phát của YouTube (1.25x, 1.5x...).
- Tự nhận diện video đã có rãnh tiếng Việt gốc → nhường tiếng gốc.
- Phụ đề: tắt / chỉ tiếng Việt / song ngữ Việt - Anh (Alt+S).
- Nút 📝 Tóm tắt AI: 5 gạch đầu dòng tiếng Việt + nghe tóm tắt.
- Từ điển thuật ngữ riêng; giữ nguyên chính tả gốc từ mượn tiếng Anh
  (chatbot, prompt, AI agent — đã test A/B, bản gốc nghe chuẩn hơn).
- Cập nhật server 1 chạm từ popup (kiểm tra → tải → thay file → khởi động lại).
- Backend dịch: preset Unsloth (mặc định) / DeepSeek / Ollama / LM Studio /
  Gemini / Custom; tự quét model từ /v1/models.
