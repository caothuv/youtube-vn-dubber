#!/usr/bin/env bash
# dong-goi-ban-moi.sh — đóng gói bản mới cho máy chủ update (chạy trong Muse hoặc máy anh)
# Cách dùng: ./dong-goi-ban-moi.sh <so-phien-ban> <duong-dan-tai-zip>
#   Vd: ./dong-goi-ban-moi.sh 0.1.1 http://VPS_IP/dubber/youtube-vn-dubber-0.1.1.zip
# Việc làm:
#   1. Đổi số phiên bản trong app (version.json gốc + server/version.json).
#   2. Zip sạch (bỏ cache, .env, log, backup).
#   3. Ghi version.json mới vào cùng thư mục này, khớp đúng số phiên bản + link zip.
#   4. In 2 dòng để anh chép 2 file này lên VPS/GitHub là xong.
set -eu
SRC_DIR="$(cd "$(dirname "$0")/.." && pwd)"
OUT_DIR="$(cd "$(dirname "$0")" && pwd)"
VER="${1:-}"
DL_URL="${2:-}"
if [ -z "$VER" ] || [ -z "$DL_URL" ]; then
  echo "Dung: $0 <so-phien-ban> <duong-dan-tai-zip>"
  echo "Vd: $0 0.1.1 http://VPS_IP/dubber/youtube-vn-dubber-0.1.1.zip"
  exit 1
fi
ZIP_NAME="youtube-vn-dubber-${VER}.zip"
# 1. Doi so phien ban trong app truoc khi zip (de zip va version.json khop nhau)
python3 - "$SRC_DIR" "$VER" <<'PYEOF'
import json, sys
from pathlib import Path
src, ver = Path(sys.argv[1]), sys.argv[2]
for p in (src / "version.json", src / "server" / "version.json"):
    d = json.loads(p.read_text(encoding="utf-8"))
    d["version"] = ver
    p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Da doi version trong app thanh {ver}")
PYEOF
cd "$SRC_DIR"
zip -qr "$OUT_DIR/$ZIP_NAME" . \
  -x "server/cache/*" "server/.env" "server/server.log" "server/__pycache__/*" \
     "update_backup/*" "_update_tmp/*" "update-source/*" "*.pyc"
cat > "$OUT_DIR/version.json" <<EOF
{
  "app": "youtube-vn-dubber",
  "version": "$VER",
  "date": "$(date +%F)",
  "download_url": "$DL_URL",
  "changelog": "Xem CHANGELOG.md trong ban $VER."
}
EOF
echo "Xong: $OUT_DIR/$ZIP_NAME"
echo "Xong: $OUT_DIR/version.json (version $VER)"
echo "Chep 2 file nay len cho phuc vu update (VPS hoac GitHub Releases)."
