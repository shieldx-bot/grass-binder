# Grass Desktop trên mybinder.org

Chạy `grass_desktop_hotfix16.py` (HOTFIX 16) trên [mybinder.org](https://mybinder.org) — không cần cài gì trên máy.

[![Binder](https://mybinder.org/badge_logo.svg)](https://mybinder.org/v2/gh/shieldx-bot/grass-binder/HEAD)

## Cách chạy

1. Mở link Binder ở badge trên (đợi 2–5 phút lần đầu để build container).
2. Mở **New ▸ Terminal** (khuyên dùng, nhanh nhất) hoặc một notebook.

### Cách A — Terminal (khuyên dùng)

```bash
python3 -c "import grass_desktop_hotfix16"   # chạy init + print banner HOTFIX 16
# nếu session ở Drive: dán URL vào env trước, rồi chạy 1 lệnh:
GRASS_SESSION_URL='https://drive.google.com/uc?export=download&id=<FILE_ID>' \
  python3 -c "import grass_desktop_hotfix16 as g; g.main()"
```

### Cách B — Notebook (1 cell duy nhất)

```python
import os
os.environ["GRASS_SESSION_URL"] = "https://drive.google.com/uc?export=download&id=<FILE_ID>"

import grass_desktop_hotfix16 as g
g.main()
```

Log phải hiện `[hotfix] GRASS HOTFIX 16` ngay đầu — nếu không thấy nghĩa là bạn đang chạy bản cũ.
Khi thấy `[earn] 🟢 EARNING` + `opening bridge tunnel ...` là node đang được tính điểm.

## Thông tin nhạy cảm

Repo này **không** chứa email, mật khẩu hay URL session — chúng được truyền qua biến môi trường
(`GRASS_EMAIL`, `GRASS_PASSWORD`, `GRASS_SESSION_URL`) ngay lúc chạy.
**Tuyệt đối không commit** giá trị thật của các biến này lên GitHub.

## Lưu ý về mybinder

- Máy ephemeral: container bị xoá khi idle ~10 phút — chạy lại từ đầu mỗi phiên (script tự cài lại deps, mất vài phút).
- RAM thấp (~1–2 GB): nếu app/webkit bị OOM kill, thử lại hoặc đổi sang Deepnote/Colab.
- Lần đầu build: script tự `apt-get install` Xvfb/webkit... (jovyan có sudo không mật khẩu).

## File

- `grass_desktop_hotfix16.py` — toàn bộ script (bản đã tẩy thông tin cá nhân).
- `requirements.txt` — Python deps (zstandard, mss); apt deps script tự cài.
