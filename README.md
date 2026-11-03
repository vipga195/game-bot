# game-bot

App desktop tự chơi game mobile trên giả lập Android: người dùng làm mẫu lần đầu, app ghi macro kèm ảnh mẫu, phát lại và tự retry/học khi sai. Quản lý theo dòng (máy giả lập + game + tài khoản + chế độ + lịch), đồng bộ lên server CDM.

Plan: [docs/PLAN.md](docs/PLAN.md). Đóng gói: [docs/PACKAGING.md](docs/PACKAGING.md).

## Cấu trúc và cách chạy

- `agent/` — Python (FastAPI local cổng 8731, ADB, vision, scheduler, sync client).
  `cd agent && uv sync && uv run pytest -q && uv run ruff check .`; chạy: `uv run python -m gamebot`.
- `server/` — FastAPI + SQLAlchemy (SQLite khi test, Postgres qua `CDM_DATABASE_URL`).
  `cd server && uv sync && uv run pytest -q`; tạo token: `uv run python -m cdmsync create-user <tên>`; chạy: `uv run python -m cdmsync`.
- `ui/` — React + Vite + TypeScript (chạy trong trình duyệt/Tauri/Electron). `cd ui && npm install && npm test && npm run build`; dev: `npm run dev` (agent phải đang chạy).
- `shared/` — chưa dùng (schema nằm trong pydantic của agent/server).

## Tiến độ

| Mốc | Trạng thái |
|---|---|
| M0 nền tảng (monorepo, SQLite, FastAPI) | xong, có test |
| M1 emulator + ADB (LDPlayer, ADB chung, ép size/DPI) | xong với mock; chưa thử LDPlayer thật |
| M2 recorder + player (state-graph, toạ độ % + neo cạnh, template đa tỉ lệ, ép/khôi phục size, dừng khi đổi size, letterbox) | xong, test bằng game giả lập ảnh tổng hợp |
| M3 learner (thống kê bước, biến thể template, popup handler, hoàn tác, dạy lại) | xong, có test |
| M4 tài khoản (keyring), workflow login + chế độ, ưu tiên | xong, có test |
| M5 scheduler (hàng đợi ưu tiên, giới hạn đồng thời, OCR giờ sự kiện, phát hiện lệch lịch) | xong, test với đồng hồ giả |
| M6 sync (server LWW + lịch sử xung đột, blob ảnh mẫu, mật khẩu mã hoá AES-GCM/PBKDF2) | xong, test 2 client; chưa thử Postgres thật |
| UI (bảng dòng, recorder, sync, trạng thái live qua WebSocket) | build + 4 test; chưa kiểm thử với agent + giả lập thật |
| M7 driver BlueStacks/Nox/MEmu/Android Emulator/Genymotion | viết theo tài liệu/trí nhớ, chỉ test parsing bằng mock |
| M8 log xoay vòng, vỏ Electron (`ui/electron`, chạy dev + `--dir` macOS OK), cấu hình NSIS + auto-update | installer Windows và auto-update chưa kiểm chứng; chưa build agent PyInstaller |

## Chưa kiểm chứng / hạn chế

- Chưa chạy với giả lập hay game thật (máy phát triển chỉ có `adb`). Định dạng output ldconsole/memuc/NoxConsole/gmtool, cổng ADB của Nox/MEmu/BlueStacks là giả định cần kiểm tra trên máy thật.
- Recorder ghi qua UI (người dùng bấm trên ảnh màn hình live, agent thực hiện và ghi); chưa bắt thao tác trực tiếp trên cửa sổ giả lập (`getevent`).
- OCR (`rapidocr-onnxruntime`) là phụ thuộc tuỳ chọn, chưa cài/chạy; chỉ kiểm thử qua OCR giả. Python 3.15 trên máy này có thể chưa có wheel.
- Sync: xoá rows/scripts/games/accounts lan sang máy khác qua tombstone (last-write-wins; tạo lại cùng tên sau khi xoá thì bản mới thắng); thống kê bước dùng tổng số lần chạy làm version; dòng đồng bộ theo `name` (gắn máy giả lập giữ cục bộ).
- Chưa có xác thực/phân quyền ngoài token, chưa rate limit server; server CDM thật chưa biết API nên dựng server mới.
- Game có thể cấm bot; dùng có rủi ro khoá tài khoản.
