#!/usr/bin/env bash
# update_server.sh — script cập nhật 1 chạm (Linux/macOS, dùng để test trên VM)
# Cách dùng: update_server.sh <duong-dan-zip-ban-moi> <thu-muc-cai-dat>
# Giữ lại: server/cache, server/.env, server/custom_voices, server/config.json
set -u
ZIP="$1"; ROOT="$2"
LOG="$ROOT/update.log"
echo "[$(date)] Bat dau cap nhat tu $ZIP" >> "$LOG"
sleep 3
python3 - "$ZIP" "$ROOT" <<'PYEOF'
import json, shutil, sys, zipfile
from pathlib import Path

zip_path, root = Path(sys.argv[1]), Path(sys.argv[2])
log = root / "update.log"
def say(msg):
    with open(log, "a", encoding="utf-8") as f:
        f.write(msg + "\n")

try:
    import datetime
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = root / "update_backup" / ts
    # 1. Sao lưu (trừ cache, .env, custom_voices, config.json, server.log)
    for src in (root / "extension", root / "server"):
        if not src.exists():
            continue
        dst = backup / src.name
        shutil.copytree(src, dst, ignore=shutil.ignore_patterns(
            "cache", "custom_voices", ".env", "config.json", "server.log",
            "__pycache__", ".venv"))
    for f in ("START_WINDOWS.bat", "version.json", "README_HUONG_DAN.md", "CHANGELOG.md"):
        if (root / f).exists():
            backup.mkdir(parents=True, exist_ok=True)
            shutil.copy2(root / f, backup / f)
    say(f"Da sao luu vao {backup}")

    # 2. Giải nén zip mới vào thư mục tạm
    tmp = root / "_update_tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(tmp)
    # Nếu zip có thư mục gốc duy nhất thì xuống 1 cấp
    subs = [d for d in tmp.iterdir() if d.is_dir()]
    src = tmp
    if len(subs) == 1 and (subs[0] / "version.json").exists():
        src = subs[0]

    # 3. Chép đè, giữ lại cache/.env/custom_voices/config.json/version.json/server.log
    def copy_keep(src_dir, dst_dir, keep):
        for item in src_dir.iterdir():
            if item.name in keep:
                continue
            dst = dst_dir / item.name
            if item.is_dir():
                shutil.copytree(item, dst, dirs_exist_ok=True)
            else:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, dst)

    copy_keep(src / "extension", root / "extension", set())
    copy_keep(src / "server", root / "server",
              {"cache", "custom_voices", ".env", "config.json", "version.json", "server.log"})
    for f in ("START_WINDOWS.bat", "README_HUONG_DAN.md", "CHANGELOG.md"):
        if (src / f).exists():
            shutil.copy2(src / f, root / f)
    if (src / "version.json").exists():
        shutil.copy2(src / "version.json", root / "version.json")
        shutil.copy2(src / "version.json", root / "server" / "version.json")
    shutil.rmtree(tmp, ignore_errors=True)
    zip_path.unlink(missing_ok=True)
    say("Da thay file moi xong")
    say("Cap nhat xong. (Linux: tu chay lai server bang tay.)")
except Exception as e:
    say(f"LOI cap nhat: {e}")
    sys.exit(1)
PYEOF
exit $?
