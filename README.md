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
| M6 sync (server LWW + lịch sử xung đột, blob ảnh mẫu, mật khẩu mã hoá AES-GCM/PBKDF2) | xong, test 2 client; đã thử Postgres 16 thật |
| UI (bảng dòng, recorder, sync, trạng thái live qua WebSocket) | build + 4 test; chưa kiểm thử với agent + giả lập thật |
| M7 driver BlueStacks/Nox/MEmu/Android Emulator/Genymotion | viết theo tài liệu/trí nhớ, chỉ test parsing bằng mock |
| M8 log xoay vòng, vỏ Electron (`ui/electron`, chạy dev + `--dir` macOS kèm agent PyInstaller OK), cấu hình NSIS + auto-update | installer NSIS Windows, build agent PyInstaller trên Windows (có thể cần `--collect-all rapidocr_onnxruntime` nếu dùng OCR) và auto-update chưa kiểm chứng |
| Báo lỗi ngoài (P1): `agent/src/gamebot/notify/` (Notifier nền, dedupe, giới hạn tần suất, tin phục hồi) + Telegram qua env `GAMEBOT_TELEGRAM_TOKEN`/`GAMEBOT_TELEGRAM_CHAT_ID` | xong, 9 test bằng kênh giả; chưa gửi thử bot Telegram thật; ảnh chụp lỗi chưa được truyền từ scheduler vào event |
| Báo lỗi ngoài (P3): watchdog `GameLost` (bật mặc định, kiểm tra 5s) và `ScreenFrozen` (`Game.still_s`, mặc định 0 = tắt, bật theo từng game; UI gợi ý 180s); ảnh chụp lỗi đi vào event cho Notifier, không vào log/WebSocket | xong, test với thiết bị giả (gồm luồng login có `watch_package`); chưa thử trên giả lập thật; màn hình tĩnh hợp lệ quá `still_s` sẽ bị báo nhầm |
| Báo lỗi ngoài (P4-5): API `/notify/channels`, `/notify/test`; kênh Telegram, Teams, Zalo ([Zalo Bot](https://bot.zaloplatforms.com/docs/apis/sendMessage/), kiểm 2026-11-04), Facebook ([Messenger Send API](https://developers.facebook.com/docs/messenger-platform/send-messages), kiểm 2026-11-04, chỉ trong 24 giờ sau tin nhắn cuối của người nhận); UI `NotifyPanel` chọn loại kênh; token lưu keyring | xong, pytest 109 pass, vitest 17 pass, ruff sạch; Zalo/Facebook chỉ gửi text; Telegram gửi ảnh lỗi chỉ khi bật `send_image` (mặc định tắt, ảnh có thể chứa OTP); GameLost cần 3 lần lệch liên tiếp, bỏ qua gms/systemui; ScreenFrozen so thumbnail xám bỏ vùng status bar (sendPhoto Zalo chỉ nhận URL, upload Facebook chưa xác minh); chưa gửi thử thật; Teams chỉ nhận host `*.webhook.office.com`, `*.logic.azure.com`, `*.powerplatform.com` (chưa xác nhận hết bằng tài liệu Microsoft); RỦI RO: API agent chưa có xác thực, ai chạy được trên máy (hoặc DNS rebinding) có thể thêm kênh và nhận ảnh/nội dung lỗi, cần TrustedHostMiddleware + token cục bộ trước khi mở rộng; dedupe 5 phút có thể nuốt lỗi giống hệt tái diễn ngay sau khi phục hồi |

## Chưa kiểm chứng / hạn chế

- Chưa chạy với giả lập hay game thật (máy phát triển chỉ có `adb`). Định dạng output ldconsole/memuc/NoxConsole/gmtool, cổng ADB của Nox/MEmu/BlueStacks là giả định cần kiểm tra trên máy thật.
- Recorder: đã thêm ghi bước gõ chữ/phím qua API `POST /recorder/text` (`value`) và `/recorder/key` (`keycode` số hoặc `KEYCODE_*`) cùng ô nhập + nút Enter/Back/Home trong UI; mới test bằng thiết bị giả (pytest + vitest), chưa thử trên giả lập thật (chữ có `%s` nguyên văn sẽ bị Android hiểu là khoảng trắng; giá trị dạng `{placeholder}` chỉ được ghi, không gõ lúc ghi). Ngoài ra recorder: ngoài chế độ qua UI còn có chế độ bắt trực tiếp từ giả lập (`getevent -lt`, endpoint `/recorder/live/start|stop`, parse tap/swipe một ngón, màn hình dọc); mới kiểm thử bằng output getevent mẫu, chưa chạy trên giả lập thật (định dạng `getevent` và thiết bị cảm ứng có thể khác theo giả lập; chưa xử lý xoay màn hình).
- OCR (`rapidocr-onnxruntime`, extra `ocr`): đã chạy OCR thật trên ảnh mẫu (Python 3.13, đọc đúng "02:15:00" -> 8100s), test tự skip nếu thiếu dependency. `onnxruntime` chưa có wheel cho Python 3.15 (venv mặc định của agent) nên cần Python 3.11-3.14 để dùng OCR; chưa thử trên ảnh game thật và chưa đóng gói PyInstaller kèm OCR.
- Sync: xoá rows/scripts/games/accounts lan sang máy khác qua tombstone (last-write-wins; tạo lại cùng tên sau khi xoá thì bản mới thắng); thống kê bước dùng tổng số lần chạy làm version; dòng đồng bộ theo `name` (gắn máy giả lập giữ cục bộ).
- Chưa có xác thực/phân quyền ngoài token, rate limit chỉ in-memory theo process, theo IP/user (sau reverse proxy cần chuyển tiếp IP thật, nếu không mọi client chung một IP); server CDM thật chưa biết API nên dựng server mới.
- Game có thể cấm bot; dùng có rủi ro khoá tài khoản.
