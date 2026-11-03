# Plan: Game Mobile Automation Manager (giả lập Android)

## Context
Xây app desktop (Windows chính, macOS cho Android Emulator) quản lý nhiều máy giả lập, tự chơi game thay người dùng. Người dùng làm mẫu lần đầu (ghi macro), app học và lặp lại; gặp sai thì tự retry/ghi nhận để cải thiện. Quản lý theo dòng (mỗi dòng = 1 máy giả lập + tài khoản + chế độ + lịch). Đồng bộ dữ liệu (kịch bản, tài khoản, lịch, trạng thái học) lên server CDM của người dùng để chuyển máy.

Quyết định đã chốt: giả lập LDPlayer + BlueStacks/Nox/MEmu + Android Emulator/Genymotion; tự học = macro + nhận diện ảnh/OCR (không RL); stack Python (core/agent) + Tauri/Electron UI + FastAPI server; nhiều game ngay từ đầu (profile theo game); chưa rõ API server CDM => thiết kế sync API riêng, adapter sau.

## Kiến trúc
```
UI (Tauri/Electron + React)  <-- WebSocket/REST localhost -->  Agent (Python, FastAPI local)
                                                                 |- Emulator layer (driver per emulator)
                                                                 |- Device layer (ADB: screencap, input, app control)
                                                                 |- Vision (OpenCV template match, OCR, screen-state)
                                                                 |- Recorder / Player / Learner
                                                                 |- Scheduler (APScheduler)
                                                                 |- Local DB (SQLite) + Credential vault (OS keyring)
                                                                 `- Sync client
                                          Sync client <-- HTTPS --> Server CDM (FastAPI + Postgres)
```

## Mô-đun & trách nhiệm
1. **Emulator layer** (`EmulatorDriver` interface: `scan()`, `start()`, `stop()`, `adb_serial()`): LDPlayer (`ldconsole list2/launch/quit`), BlueStacks/Nox/MEmu (đọc config instance + `adb connect` cổng), Android Emulator/Genymotion (`adb devices`). Fallback chung: ADB.
2. **Device layer** (ADB qua `adbutils`/`pure-python-adb`): screencap nhanh, tap/swipe/key/text, start/stop package, kiểm tra app foreground.
3. **Vision**: template matching (OpenCV, đa tỉ lệ), OCR (PaddleOCR/RapidOCR) cho text/số, "screen fingerprint" để nhận dạng màn hình hiện tại (login, main, nhiệm vụ, popup...).
4. **Recorder**: bắt thao tác người dùng (tap/swipe qua `getevent` hoặc overlay), mỗi bước lưu: hành động + ảnh crop vùng đích + màn hình trước/sau + thời gian chờ. Xuất ra kịch bản dạng state-graph (node = màn hình, edge = hành động), không phải toạ độ cứng.
5. **Player + Learner** ("tự học"):
   - Chạy kịch bản: trước mỗi bước xác nhận đúng màn hình (fingerprint), tìm đích bằng template (không dùng toạ độ cứng), sau bước xác nhận màn hình kết quả.
   - Sai/không khớp: retry → thử biến thể (template khác tỉ lệ, đợi lâu hơn) → xử lý popup lạ bằng thư viện "popup handlers" → nếu vẫn kẹt thì dừng, chụp ảnh, báo UI để người dùng dạy lại bước đó.
   - Học: lưu thống kê theo bước (tỉ lệ thành công, thời gian chờ tối ưu, template mới thành công được thêm làm biến thể, popup mới được người dùng gán hành động). Học là thống kê + cập nhật template, có thể xem/hoàn tác.
6. **Game profile**: mỗi game = package name + bộ kịch bản (login, nhiệm vụ, train, hoạt động) + danh sách popup handler. Dạng dữ liệu (JSON + ảnh), không code riêng từng game.
7. **Account & login**: lưu user/pass bằng OS keyring (Windows Credential Manager), không lưu plaintext trong DB/sync; sync mật khẩu chỉ khi bật và mã hoá E2E bằng passphrase người dùng. Kịch bản login dùng text-input qua ADB.
8. **Chế độ ưu tiên** mỗi dòng: Nhiệm vụ / Train / Hoạt động (event) — mỗi chế độ là 1 workflow trong game profile; dòng chọn thứ tự ưu tiên, scheduler quyết định chạy gì.
9. **Scheduler & tự cập nhật giờ**: lịch hẹn giờ theo dòng (cron-like + khung giờ hoạt động). Giờ hoạt động thay đổi: (a) đọc lại thời gian từ UI game bằng OCR (vd. "còn 02:15:00") và cập nhật lịch; (b) nguồn giờ từ server CDM/bảng cấu hình game do người dùng sửa; (c) phát hiện lệch (hoạt động không xuất hiện đúng giờ) → tự dời lịch + cảnh báo. Hàng đợi ưu tiên, tránh nhiều dòng tranh tài nguyên (giới hạn số máy chạy đồng thời).
10. **UI theo dòng**: bảng, mỗi dòng: [chọn/quét máy] [game] [tài khoản/mật khẩu] [chế độ ưu tiên] [lịch] [trạng thái live + log + nút Dạy lại/Pause]. Màn hình recorder (xem live screen, đánh dấu bước), màn hình thư viện kịch bản, màn hình sync.
11. **Sync server CDM**: FastAPI + Postgres. Entity: user/device, game_profile (versioned), script, template assets (blob), account (mã hoá), schedule, learner_stats. Cơ chế: version + `updated_at`, last-write-wins theo bản ghi, conflict thì giữ bản mới + lưu bản cũ; đẩy/kéo thủ công và tự động; xác thực token. Xin API sẵn có của CDM nếu có để làm adapter.

## Lộ trình (milestone)
- **M0 – Nền tảng**: repo, cấu trúc monorepo (`agent/`, `ui/`, `server/`, `shared/`), SQLite schema, CI lint/test.
- **M1 – Emulator + ADB**: quét/khởi động/dừng LDPlayer + ADB chung, screencap/tap; UI bảng dòng cơ bản (thêm dòng, chọn máy).
- **M2 – Recorder + Player**: ghi macro có ảnh mẫu, phát lại có xác nhận màn hình; test trên 1 game.
- **M3 – Learner**: retry/biến thể template, popup handlers, thống kê thành công, UI "dạy lại bước".
- **M4 – Login & chế độ**: tài khoản (keyring), workflow Nhiệm vụ/Train/Hoạt động, ưu tiên.
- **M5 – Scheduler**: hẹn giờ, OCR cập nhật giờ tự động, hàng đợi đa máy.
- **M6 – Sync CDM**: server FastAPI, sync kịch bản/lịch/tài khoản mã hoá, đa máy.
- **M7 – Mở rộng giả lập**: BlueStacks/Nox/MEmu, Android Emulator/Genymotion; thêm game thứ 2 để kiểm chứng tính tổng quát.
- **M8 – Hardening**: log/crash recovery, auto-update app, đóng gói installer.

## Rủi ro & lưu ý
- Nhiều game cấm bot/macro (ToS, có thể khoá tài khoản) và có anti-cheat phát hiện giả lập/ADB: người dùng cần tự chấp nhận rủi ro; thêm jitter ngẫu nhiên thời gian/toạ độ để hành vi tự nhiên.
- Độ phân giải/DPI khác nhau giữa giả lập: (1) ép giả lập về đúng size/DPI lúc ghi (`adb shell wm size/density`, `ldconsole modify`), khôi phục sau khi chạy; (2) recorder lưu metadata size/DPI/aspect, nếu không ép được thì chuẩn hoá giữ tỉ lệ (letterbox, không kéo méo); (3) toạ độ lưu dạng phần trăm + neo cạnh; (4) template đa tỉ lệ chỉ nhận khi điểm khớp vượt ngưỡng và đúng màn hình, biến thể thành công được lưu; (5) đổi kích thước giữa chừng → dừng và báo.
- Lưu mật khẩu game: bảo mật là ưu tiên (keyring + E2E khi sync), không bao giờ log.
- Cần OCR/CV chạy nhẹ để nhiều máy cùng lúc (giới hạn FPS, chỉ chụp khi cần).
- Server CDM: chưa biết API → cần người dùng cung cấp hoặc xác nhận tự dựng server mới.
- Rule dự án: sau khi triển khai, ADR ghi vào KB, README cập nhật tiến độ.

## Xác minh (end-to-end)
- Unit: driver mock ADB, vision với ảnh mẫu cố định, scheduler với đồng hồ giả.
- Integration: chạy LDPlayer thật → ghi 1 kịch bản login+nhiệm vụ → phát lại 20 lần, đo tỉ lệ thành công; cố tình đổi popup/độ phân giải để kiểm tra learner.
- Sync: 2 máy (hoặc 2 profile dữ liệu) → đẩy/kéo, xác nhận kịch bản chạy được trên máy thứ 2, mật khẩu giải mã đúng, conflict xử lý đúng.
- Lịch: đổi giờ hoạt động trên game → xác nhận lịch tự cập nhật theo OCR.
