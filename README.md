# game-bot

App desktop tự chơi game mobile trên giả lập Android: người dùng làm mẫu lần đầu, app ghi macro kèm ảnh mẫu, phát lại và tự retry/học khi sai. Quản lý theo dòng (máy giả lập + game + tài khoản + chế độ + lịch), đồng bộ lên server CDM.

Plan đầy đủ: [docs/PLAN.md](docs/PLAN.md).

## Cấu trúc

- `agent/` — Python (FastAPI local, ADB, vision, scheduler). Chạy: `cd agent && uv sync && uv run pytest`.
- `ui/` — Tauri/Electron + React (chưa làm).
- `server/` — FastAPI + Postgres đồng bộ CDM (chưa làm).
- `shared/` — schema dùng chung (chưa làm).

## Tiến độ

- M0 nền tảng: monorepo, SQLite schema, FastAPI skeleton — đang làm.
- M1 emulator + ADB: driver LDPlayer / ADB chung, đọc và ép size/DPI màn hình — đang làm.
- M2–M8: chưa bắt đầu (recorder/player, learner, login + chế độ, scheduler, sync, thêm giả lập, đóng gói).

## Còn lại / lưu ý

- Chưa kiểm thử với giả lập thật (máy này chưa có `ldconsole`; có `adb`).
- Chưa biết API server CDM; đang giả định dựng server sync mới.
- Game có thể cấm bot; dùng có rủi ro khoá tài khoản.
