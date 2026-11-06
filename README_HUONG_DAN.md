# Lồng tiếng Việt AI cho YouTube — Hướng dẫn cài đặt & sử dụng

> **Nói trước cho rõ:** đây là lồng tiếng **gần-thời gian-thực, không phải 0 mili-giây**.
> Lần đầu xem 1 video mới, câu chưa có trong bộ nhớ đệm sẽ chậm vài giây
> (dịch + đọc xong mới phát). Xem lại / tua lại thì phát ngay vì đã lưu sẵn.
> Câu nào đang đọc mà anh tua video thì giọng cũ ngắt ngay, câu mới nhảy tới liền.

## Cái này làm được gì?

- Mở video YouTube tiếng Anh → bấm nút **🎧 AI Việt** → nghe tiếng Việt bằng
  **giọng clone VieNeu-TTS v3 Turbo** (giọng Việt, chạy ngay trên máy anh,
  không tốn VRAM, không cần mạng cho phần đọc).
- Dịch qua **Unsloth Desktop** trên card RTX 4070 Ti Super (miễn phí, mặc định),
  hoặc DeepSeek API / Ollama / LM Studio / Gemini (chọn trong popup).
- Có nút **📝 Tóm tắt AI**: tóm tắt video thành 5 gạch đầu dòng tiếng Việt,
  bấm 🔊 là đọc tóm tắt vào tai nghe.
- Phím tắt: **Alt+V** bật/tắt lồng tiếng, **Alt+S** đổi chế độ phụ đề.

## Cần có trước

1. **Windows 11**, Python 3.11 trở lên.
   Chưa có thì tải ở https://www.python.org/downloads/
   (lúc cài **nhớ tích ô "Add python.exe to PATH"**).
2. **Unsloth Desktop đang mở** (mặc định), hoặc key DeepSeek nếu dùng cloud.
3. **Google Chrome** (hoặc Edge).

## Cài đặt — làm 1 lần duy nhất

**Bước 1 — Giải nén.**
Giải nén file `youtube-vn-dubber.zip` ra chỗ nào cũng được, ví dụ
`C:\youtube-vn-dubber\`. (Đường dẫn **không có dấu tiếng Việt và không có
khoảng trắng** thì ít lỗi nhất.)

**Bước 2 — Bật server.**
Bấm đúp file **`START_WINDOWS.bat`** trong thư mục vừa giải nén.
- Lần đầu: nó tự tạo môi trường ảo + cài thư viện (mất vài phút, cần mạng).
  Cứ để cửa sổ đen chạy, đừng tắt.
- Khi thấy dòng `Uvicorn running on http://127.0.0.1:8000` là xong.
- **Đừng đóng cửa sổ đen này** trong lúc xem YouTube. Tắt server thì đóng nó.

**Bước 3 — Nạp extension vào Chrome.**
1. Mở Chrome, gõ vào thanh địa chỉ: `chrome://extensions` rồi Enter.
2. Bật công tắc **Developer mode** (góc trên bên phải).
3. Bấm **Load unpacked** → chọn thư mục **`extension`** trong
   `C:\youtube-vn-dubber\extension` → bấm **Select Folder**.
4. Thấy biểu tượng tai nghe 🎧 trên thanh công cụ là được.

**Bước 4 — Mở video YouTube tiếng Anh.**
- Trên thanh điều khiển của video sẽ có 2 nút mới: **🎧 AI Việt** và
  **📝 Tóm tắt AI**. Bấm **🎧 AI Việt** là nghe tiếng Việt.
- Lần đầu bật, các câu sắp tới cần vài giây để dịch + đọc trước — cứ để
  video chạy, giọng sẽ khớp dần. Tua lại đoạn vừa nghe là phát ngay.
- Bấm vào biểu tượng 🎧 trên thanh công cụ Chrome để mở **popup cài đặt**:
  đổi giọng đọc, đổi backend dịch (Unsloth/DeepSeek...), thêm từ điển thuật
  ngữ, chỉnh âm lượng tiếng gốc, thêm giọng clone mới.

## Đổi giọng đọc / thêm giọng clone

- Trong popup: mục **Giọng đọc** → chọn giọng VieNeu có sẵn (Nam/Bắc/Trung)
  → bấm **💾 Lưu cài đặt**.
- Muốn **clone giọng người nói trong video**: chuẩn bị 1 file ghi âm giọng đó
  3–10 giây (giọng sạch, không nhạc nền) → trong popup bấm **➕ Thêm giọng
  mới** → chọn file + gõ tên → bấm **💾 Lưu** → chọn giọng mới trong danh sách.
- Giọng Edge-TTS (Nam Minh, Hoài My) chỉ là dự phòng, **cần mạng** mới đọc được.

## Cập nhật 1 chạm (không cần cài lại)

**Server:** mở popup → mục **🔄 Cập nhật** → bấm **🔍 Kiểm tra cập nhật**.
Có bản mới thì bấm **⬆️ Cập nhật ngay** — server tự tải về, sao lưu bản cũ,
thay file, khởi động lại. Anh chỉ chờ 10–20 giây rồi dùng tiếp.
(Lưu ý: cần cấu hình `UPDATE_SOURCE` trong file `server\.env` — xem mục dưới.
Chưa cấu hình thì nút kiểm tra sẽ báo "chưa cấu hình nguồn cập nhật".)

**Extension:** extension đang chạy bản giải nén nên **không tự cập nhật được**.
Khi có zip mới: giải nén đè lên thư mục cũ → vào `chrome://extensions` →
bấm nút **Làm mới (↻)** trên thẻ extension là xong, không cần nạp lại.
Muốn cập nhật im lặng hoàn toàn thì phải đăng extension lên Chrome Web Store
(phí 1 lần 5 USD, làm sau — xem mục "Về sau" bên dưới).

### Cấu hình nguồn cập nhật (cho người phát hành bản mới)

Mở file `server\.env` bằng Notepad, thêm 1 trong 2 dòng:
- `UPDATE_SOURCE=ten-github-cua-anh/youtube-vn-dubber` (đọc từ GitHub Releases)
- `UPDATE_SOURCE=https://example.com/dubber/version.json` (file version.json tự host)

File `version.json` của bản mới phải có dạng:
`{"version": "0.2.0", "download_url": "https://.../youtube-vn-dubber-v0.2.0.zip", "changelog": "Sửa..."}`

## Hỏi đáp nhanh (gặp lỗi thì đọc đây trước)

**Bấm 🎧 AI Việt mà không có tiếng?**
1. Cửa sổ đen của server còn mở không? Tắt rồi thì bấm lại START_WINDOWS.bat.
2. Unsloth Desktop có đang mở + đã load model chưa? (Popup báo "LLM: CHƯA kết
   nối được" là do đây.) Mở Unsloth, load model, tải lại trang YouTube.
3. Video có phụ đề tiếng Anh không? Video không có phụ đề thì extension báo
   ngay "không có phụ đề tiếng Anh nên chưa lồng được".

**Giọng đọc chậm / câu tới trễ?**
Lần đầu xem video mới là bình thường — server đang dịch + đọc trước các câu
sắp tới. Để video chạy 10–20 giây đầu, hoặc bấm tạm dừng 10 giây rồi xem tiếp.
Xem lại lần 2 là phát ngay nhờ cache.

**Tua video mà giọng cũ vẫn đọc?**
Giọng cũ ngắt ngay khi tua. Câu mới cần 1–2 giây để lấy từ cache (hoặc vài giây
nếu chưa cache). Nếu câu mới mãi không lên: kiểm tra server + Unsloth.

**Lỗi "port 8000 đã dùng"?**
Mở file `server\.env`, sửa `PORT=8000` thành `PORT=8001`, chạy lại file .bat,
rồi vào popup sửa địa chỉ server thành `http://127.0.0.1:8001`.

**Video tiếng Việt mà extension vẫn lồng?**
Extension tự nhận diện rãnh tiếng Việt gốc và nhường (báo "đang dùng tiếng
Việt gốc"). Muốn ép dùng giọng AI thì bấm lại nút 🎧 AI Việt 1 lần nữa.

**Muốn dùng DeepSeek thay vì Unsloth?**
1. Lấy key ở https://platform.deepseek.com/api_keys
2. Mở file `server\.env`, điền `DEEPSEEK_API_KEY=sk-...` rồi lưu.
3. Chạy lại server. Trong popup chọn preset **DeepSeek API** → **💾 Lưu**.
   (DeepSeek tính tiền theo token — video càng dài càng tốn, dùng khi cần
   dịch chuẩn thuật ngữ.)

## Cái gì chưa có trong bản 0.1.0 (nói thẳng)

- **Video không có phụ đề:** chưa lồng được. Cần nghe trực tiếp từ âm thanh
  (ASR) — tính năng này chưa làm, sẽ thêm ở bản sau.
- **"0ms" khi tua:** câu mới chưa cache vẫn phải chờ dịch + đọc vài giây.
  Chỉ câu đã cache mới phát tức thì.
- **Từ mượn tiếng Anh:** giữ nguyên chính tả gốc (chatbot, prompt, AI agent)
  — đã test A/B với anh, bản đọc nguyên chữ nghe chuẩn hơn bản phiên âm.
- **Extension tự cập nhật:** chưa có (bản giải nén). Cần đăng Chrome Web Store.

## Về sau (để sau, không gấp)

- Đăng extension lên Chrome Web Store (phí 1 lần 5 USD ≈ 130.000đ) để extension
  tự cập nhật im lặng như app thường.
- Thêm ASR (nghe trực tiếp) cho video không có phụ đề.
- Thêm giọng F5-TTS: đã test, đọc tiếng Việt không nghe hiểu được nên **không
  dùng làm mặc định** trong bản này.

## Sửa gì so với bản nháp ban đầu?

1. Bỏ câu "ngắt câu cũ trong 0ms / phát cache trong 0ms" — nói đúng: ngắt thì
   nhanh, câu mới chưa cache vẫn chờ vài giây.
2. "Nam Minh Deep -4Hz" không phải tên giọng thật — làm bằng giọng
   NamMinhNeural + chỉnh cao độ -4Hz.
3. F5-TTS **không** làm giọng mặc định (test live: đọc tiếng Việt không hiểu
   được). Mặc định là VieNeu-TTS v3 Turbo, đã test full video 4 phút.
4. Dịch chuyển hẳn về server (extension giữ mỏng) để cập nhật 1 chạm chỉ cần
   đổi server, khỏi đụng extension. Key API chỉ nằm trong file `.env` trên
   server, không nằm trong extension.
5. Bỏ Faster-Whisper GPU khỏi server bản 0.1.0: lồng real-time lấy phụ đề sẵn
   của YouTube, không cần ASR. ASR để bản sau.

## Riêng tư

- Phụ đề + bản dịch chỉ gửi tới server local trên máy anh và backend LLM anh
  chọn (Unsloth local thì không ra khỏi máy; DeepSeek/Gemini thì gửi text
  lên cloud của họ).
- File `.env` có key — đừng gửi file này cho ai, đừng đưa lên mạng.
