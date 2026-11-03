# Đóng gói (M8)

Vỏ desktop: **Electron** (`ui/electron/`), installer bằng `electron-builder`, auto-update bằng `electron-updater`.
Chọn Electron vì không cần toolchain Rust và đã chạy được trên macOS dev.

## Trạng thái kiểm chứng
| Hạng mục | Trạng thái |
|---|---|
| Vỏ Electron chế độ dev (macOS): mở UI qua `app://ui`, tự chạy `uv run python -m gamebot`, tắt agent khi thoát | đã chạy |
| Agent PyInstaller (`gamebot-agent`, macOS arm64, onedir ~187MB, `agent/packaging/gamebot-agent.spec`) | đã build, chạy được: lắng nghe 127.0.0.1:8731, `/health` OK (lần chạy đầu trên macOS có thể chậm vài giây) |
| `electron-builder --dir` (macOS, không ký) kèm agent trong `Resources/agent/` | đã chạy: app đóng gói tự chạy agent, UI gọi được API, agent tắt khi app nhận SIGTERM |
| Build agent bằng PyInstaller trên Windows (`.exe`) | chưa kiểm chứng (chỉ build trên macOS) |
| OCR (`rapidocr_onnxruntime`) trong bản đóng gói | chưa kiểm chứng, spec chưa gom package này |
| Installer NSIS Windows | chỉ có cấu hình, chưa kiểm chứng |
| Auto-update | chỉ có code + cấu hình, chưa kiểm chứng với feed thật |

## Chạy dev
```bash
cd ui && npm install && npm run desktop:dev
```
Biến môi trường: `GAMEBOT_NO_AGENT=1` (không tự chạy agent), `GAMEBOT_UI_URL=http://localhost:5173` (tải từ Vite dev server).

## Build installer
1. Agent (onedir; chạy trên đúng OS đích):
   `cd agent && uv run --with pyinstaller pyinstaller packaging/gamebot-agent.spec --distpath dist --workpath build --noconfirm`
   Kết quả `agent/dist/gamebot-agent/` (Windows: `gamebot-agent.exe`) được `extraResources` copy vào `resources/agent/`. Entry là `agent/packaging/entry.py` (vì `__main__.py` dùng import tương đối). Nếu dùng OCR, cài `rapidocr_onnxruntime` trước và thêm `collect_all` vào spec.
2. `cd ui && npm ci && npm run desktop:dist:win` -> `ui/release/*.exe` (NSIS) + `latest.yml`.
   `npm run desktop:pack` tạo bản thư mục không installer (macOS: `release/mac-arm64`).
Chưa ký số (Windows sẽ hiện SmartScreen); macOS đặt `identity: null`.

## Auto-update
- Chỉ chạy khi app đã đóng gói và có URL feed: biến `GAMEBOT_UPDATE_URL` hoặc file `<userData>/update.json` dạng `{"url": "https://host/path/"}`. Không có URL thì bỏ qua, không hardcode.
- Feed kiểu `generic`: đăng `latest.yml` và file `.exe` từ `ui/release/` lên URL đó; tăng `version` trong `ui/package.json` mỗi bản.
- Tải về xong sẽ cài khi thoát app. Chưa ký số, tin cậy dựa vào HTTPS của server feed.

## Dữ liệu và bảo mật
- Dữ liệu người dùng ở `%USERPROFILE%\.gamebot` (SQLite, ảnh mẫu, log xoay vòng `gamebot.log`); đổi bằng `GAMEBOT_DATA`.
- Mật khẩu game chỉ nằm trong Windows Credential Manager (keyring), không vào SQLite/log/sync trừ khi bật passphrase.
- Agent chỉ lắng nghe 127.0.0.1; CORS cho phép localhost và `app://*` (origin của UI đóng gói là `app://ui`).

## Server sync
`cd server && uv run python -m cdmsync create-user <tên>` in token một lần; `CDM_DATABASE_URL=postgresql+psycopg://...` chọn Postgres (mặc định SQLite). Chưa kiểm thử với Postgres thật.
