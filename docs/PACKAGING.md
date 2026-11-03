# Đóng gói (M8) — hướng dẫn, chưa chạy thử trên Windows

Trạng thái: chỉ là quy trình dự kiến; chưa build installer thật (máy phát triển là macOS, không có Windows/giả lập).

## Thành phần
1. **Agent (Python)** — gói thành 1 file chạy bằng PyInstaller trên Windows:
   `cd agent && uv run --with pyinstaller pyinstaller -F -n gamebot-agent -p src --collect-all rapidocr_onnxruntime src/gamebot/__main__.py`
   (cần thêm `__main__.py` gọi `uvicorn.run(create_app(run_scheduler=True), host="127.0.0.1", port=8731)` khi đóng gói).
   OCR là dependency tuỳ chọn (`rapidocr-onnxruntime`), cần cài trước khi đóng gói nếu dùng OCR đọc giờ.
2. **UI** — `cd ui && npm ci && npm run build` tạo `ui/dist`. Bọc bằng Tauri hoặc Electron: cửa sổ tải `dist/`, khởi chạy `gamebot-agent.exe` làm sidecar, URL agent mặc định `http://127.0.0.1:8731` (đổi bằng `VITE_AGENT_URL` lúc build).
3. **Installer** — Tauri bundle (`tauri build`, NSIS/MSI) hoặc `electron-builder` (NSIS). Auto-update: `tauri-plugin-updater` hoặc `electron-updater`, trỏ tới server do người dùng quản lý; cần ký bản cập nhật.

## Dữ liệu và bảo mật
- Dữ liệu người dùng ở `%USERPROFILE%\.gamebot` (SQLite, ảnh mẫu, log xoay vòng `gamebot.log`); đổi bằng biến `GAMEBOT_DATA`.
- Mật khẩu game chỉ nằm trong Windows Credential Manager (keyring), không vào SQLite/log/sync trừ khi bật passphrase.
- Agent chỉ lắng nghe 127.0.0.1; UI gọi qua CORS giới hạn origin localhost/tauri/app.

## Server sync
`cd server && uv run python -m cdmsync create-user <tên>` in token một lần; `CDM_DATABASE_URL=postgresql+psycopg://...` chọn Postgres (mặc định SQLite). Chưa kiểm thử với Postgres thật.
