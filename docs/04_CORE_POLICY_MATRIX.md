# Policy matrix — Quyền nghiệp vụ của lõi mới

Phiên bản 3.0 · đề xuất ngày 19/10/2026. Tài liệu này cùng [registry](../decisions/OPEN_DECISIONS.md) là nguồn chuẩn cho quyết định nghiệp vụ. Không có phê duyệt doanh nghiệp mới trong tác vụ soạn gói. Quy tắc trong PLAN/BONUS được điều chỉnh tại [truy vết](12_SOURCE_TRACEABILITY.md).

## 1. Các mức tiếp nhận phải phân biệt

| Mức | Ý nghĩa | Được nói với khách |
|---|---|---|
| Draft saved | Lưu phần đang nhập | Đã giữ thông tin đang trao đổi |
| Support request recorded | Ghi yêu cầu cần người hỗ trợ, chưa đủ tự động tạo đơn | Đã ghi nhận yêu cầu hỗ trợ, nếu transaction thật đã lưu và có kênh xử lý |
| Request recorded | Booking/intake được ghi vào SQLite và task tương ứng | Đã ghi nhận yêu cầu đặt xe, đang chờ quy trình xác nhận của đơn vị |
| Dispatch accepted | Backend điều phối thật ACK | Chỉ mô tả theo trạng thái/nguồn thực; tính năng này khóa mặc định |
| Driver assigned | Có tài xế được phân công và dữ liệu hợp lệ | Chỉ nêu khi đã tích hợp nguồn thật; không suy từ booking ID |
| Simulated outcome | Mocks tạo kết quả trong DB thử | Chế độ thử; chưa điều xe thật |

Tên nội bộ legacy `booked` không được dùng để suy ra dispatch. Lời khách nghe lấy từ outcome có thẩm quyền sau commit, không lấy từ model hoặc tên enum đơn lẻ. Tóm tắt sau booking chỉ dùng customer reference được phép công khai; ID nội bộ không tự trở thành credential truy cập.

## 2. Baseline phát triển bảo thủ

Các giá trị sau là **đề xuất mặc định cho lõi mới để phát triển/kiểm thử**, không sửa cấu hình runtime hiện tại và không giả là doanh nghiệp đã duyệt. Feature cần phê duyệt giữ đóng trong connected.

| ID | Baseline phát triển | Gate liên quan |
|---|---|---|
| POL-01 | `success_semantics=request_recorded`; real dispatch disabled | Mở dispatch cần API/status reconciliation và phê duyệt lời hứa |
| POL-02 | Pickup/destination đủ điều kiện, xe4/7, giờ hợp lệ, contact theo auth flow; passengers tùy chọn nhưng đã cung cấp phải hợp lệ/capacity | Giảm required slots phải có policy version và test |
| POL-03 | `allow_unverified_auto_booking=false`; hỗ trợ text-only chỉ ghi support request khi có kênh thật | Không nâng verification bằng lời khách đồng ý |
| POL-04 | Broad destination được lưu draft; chưa tự chốt booking hoặc estimate bằng tâm khu vực | Cần definition of sufficiency và validated routing anchor |
| POL-05 | Trước request_recorded: reducer sửa draft; sau đó: tạo operator task, không báo đã đổi/hủy | Bot mutate đơn thật cần nghiệp vụ/quyền riêng |
| POL-06 | Handoff chỉ khi adapter xác nhận khả dụng/đã tạo ticket hoặc queue thật | Không có người trực thì nói rõ phương án thực tế |
| POL-07 | Thiếu route/tariff thì unavailable cho phần số tương ứng; demo chỉ trong fixture/sandbox có nhãn | Tariff approved và source/units/TTL tests |
| POL-08 | Operational logging không ghi raw/PII mới; debug thật tắt; export mặc định redact | Retention/access/delete policy cần duyệt trước thêm dữ liệu thật |
| POL-09 | Tôn trọng scope configured/catalog của runtime; không tự mặc định Hà Nội | Mở rộng vùng cần coverage/ambiguity/provider tests |
| POL-10 | Giữ budget hiện tại làm baseline đo; không tự nâng timeout/quota | SLO/chi phí và load evidence trước rollout |

## 3. Readiness theo vai trò địa chỉ

Bốn trục độc lập: identity verified, pickup viable, destination sufficient, route estimable. Giá trị `unknown` khác `false`; thiếu nguồn không được coi là verified. `customer_confirmed` chỉ xác nhận lời hiểu đúng ý khách, không nâng evidence map.

| Input/evidence | Cho phép giữ draft | Cho phép hỏi/xác nhận | Auto booking baseline | Estimate |
|---|---|---|---|---|
| Pickup chỉ tỉnh/thành | Có | Hỏi đường/POI/mốc cụ thể | Chưa đủ | Không lấy tâm tỉnh để tính như vị trí khách |
| Pickup POI lớn, chưa biết sảnh/cổng | Có | Hỏi một mốc nếu cần tìm khách | Theo viability và verification; không bịa cổng | Chỉ nếu anchor phù hợp purpose có nguồn |
| Pickup đường + số/ngõ chưa được xác minh | Có, giữ raw | Readback/mốc/support | Chặn; POL-03 gate | Không suy ngõ kế bên theo số |
| Pickup có identity/required details verified, khách xác nhận đúng version | Có | Tiếp tục slot khác | Có nếu toàn policy đạt | Theo route prerequisites |
| Destination tên thành phố/vùng rộng | Có | Không ép chi tiết vô ích; làm rõ nếu cần phân biệt | POL-04 giữ đóng trước duyệt | Chỉ rough nếu anchor/range được duyệt |
| Destination hospital/sân bay nhiều cơ sở | Có | Hỏi cơ sở/khu vực khi thiếu căn cứ | Chưa đủ nếu branch unresolved | Chưa tính bằng branch đoán |
| Destination POI rõ, không biết cổng | Có | Không hỏi cổng trừ điều kiện phục vụ cần | Theo evidence và policy; không cần geocode tới cửa | Anchor POI phải phù hợp purpose |
| Chain brand chưa có nhánh | Có | Hỏi một discriminator | Chặn arbitrary Top1 | Chặn nếu endpoint chưa xác định |
| Khách từ chối/không biết destination | Có, mark availability | Giải thích ngắn hoặc hỗ trợ | Chặn trong baseline POL-02 | Unavailable |

Địa chỉ map không tìm ra không được gọi là giả. Địa chỉ thiếu tỉnh có thể cần hỏi, không tự kết luận ngoài vùng. Kết quả có xung đột số ngõ/nhà không được đề xuất như khớp; giữ phân biệt candidate, rejected, unverified và verified.

## 4. Ma trận intent và thay đổi state

| Lượt | Booking slots | Conversation state | Side effect |
|---|---|---|---|
| Pure information query | Giữ nguyên | Có thể đổi focus có scope | Read-only tool |
| Recall/repeat | Giữ nguyên | Có thể cập nhật output history/delivery | Không booking |
| Preference only | Giữ nguyên | Đổi preference được hỗ trợ | Không booking |
| Express uncertainty | Giữ candidate như giả thuyết, chưa confirm | Đổi unresolved issue/focus | Không submit |
| Explicit set/replace/refine | Apply sau validate source/scope | Invalidate dependencies liên quan | Chưa submit nếu chưa đủ xác nhận |
| Confirm location + sửa slot khác | Confirm target đúng version nếu eligible, apply slot khác | Tạo decision tiếp theo | Không tự submit toàn chuyến |
| Confirm booking + edit trip | Apply edit, invalid summary | Tóm tắt lại version mới | Không submit summary cũ |
| Cancel draft | Không xóa lịch sử; draft cancelled | Thông báo sau commit | Local transaction |
| Cancel request đã ghi | Giữ đơn active cho tới authoritative result | Tạo pending task | Operator task baseline |
| Hỏi sang B khi pending A | Booking giữ A | Focus B, pending A hold có giới hạn | Read-only; yes/no mơ hồ không chọn A/B |

Khi một lượt có nhiều acts, xử lý scope/thứ tự/conditional dependencies trước side effect. Không dùng priority list như quyền thực thi sớm từng prefix.

## 5. Điều kiện xác nhận

Một confirmation hợp lệ cần source ngữ nghĩa rõ, đúng logical question, target tồn tại, phiên bản phụ thuộc còn đúng, policy cho phép và delivery evidence phù hợp channel. NLU confidence không cấp quyền. Câu hỏi chưa presented, stale response hoặc hidden candidate không đủ điều kiện.

Xác nhận địa chỉ phụ thuộc location_version của target; sửa xe không tự làm mất xác nhận địa chỉ đã đúng, nhưng có thể làm summary chuyến mất hiệu lực. Xác nhận toàn chuyến phụ thuộc booking_revision và tất cả dữ liệu quan trọng được đọc. Resume/takeover không khôi phục việc đã nghe ở playback cũ. Lưỡng lự, câu hỏi ngược, “thế á” không được ép thành confirm/reject.

## 6. Hỗ trợ, hủy và sau booking

HandoffTicket có reason, request/draft reference, trạng thái đã commit, unresolved slots, raw event refs, candidate/rejection summary, pending questions và evidence versions. Chỉ người có quyền đọc PII mới tải full address. Không cần đưa mọi lịch sử vào prompt hoặc public event.

Khi khách không biết đang ở đâu: hướng dẫn đọc số nhà/tên đường trên biển hiệu, một mốc dễ nhìn, hoặc nhờ người quanh đó. Có thể giữ text-only support request khi path thật tồn tại. Không nói “tài xế sẽ gọi” nếu chưa có quy trình được duyệt hoặc chưa có tài xế.

Sau request_recorded, luồng read-only support lấy đơn hiện hành; yêu cầu sửa/hủy tạo task bền vững có idempotency rồi mới nói đã tiếp nhận. Operator sửa/hủy thắng AI checkpoint: generation/revision phải revalidate. Khách chỉ yêu cầu hủy chưa đồng nghĩa đơn bị hủy. Khi chưa có nguồn phân công tài xế, không tạo ETA tới đón.

Hủy một lượt tính toán, ngắt TTS, kết thúc phiên và hủy booking là bốn hành động khác nhau. Mất kết nối không tự hủy booking đã commit. Cancel draft và resume phải hỏi rõ khi không chắc dùng lại thông tin nào.

## 7. Clarification và style

Mỗi response tối đa một offered decision. Có thể lấy nhiều slot trong cùng một lượt. Không có thứ tự cứng phải xong pickup mới được hiểu destination; ưu tiên lời khách đang chủ động sửa, safety và tiến triển.

Issue có ID/target/location_version, số lần hỏi, evidence mới và các câu đã hỏi. Baseline phát triển: tối đa hai lần hỏi lặp không có tiến triển trên cùng issue, sau đó đổi chiến lược hoặc nêu hỗ trợ; số này là đề xuất kiểm thử cần POL-10 nghiệm thu, không overwrite cấu hình legacy3. Có thể hỏi mở → câu đóng nếu có hypothesis được hỗ trợ → mốc khác; không lặp nguyên câu hoặc reset count chỉ vì alias khác.

Rút gọn địa chỉ chỉ bỏ phần đã rõ và không làm mất phân biệt. Preferences ngắn/chậm/hỏi ít không bỏ disclaimer, confirmation hoặc permission. Lõi chỉ gửi speech preference trong capability của adapter; adapter unsupported trả rõ, không hứa đã đổi âm thanh.

## 8. Invariants và acceptance riêng cho policy

- `POL-T01`: pure inquiry giữ booking slots và semantic revision, dù focus thay đổi.
- `POL-T02`: customer_confirmed của unverified address vẫn không qua auto-book gate.
- `POL-T03`: broad destination không bị gán branch/center im lặng; policy mới phải có test riêng.
- `POL-T04`: request_recorded có task/outcome đúng; không claim dispatch/driver/ETA.
- `POL-T05`: operator unavailable không tạo lời hứa chuyển máy hoặc cuộc gọi tài xế.
- `POL-T06`: cancel task và booking status độc lập cho đến khi operator authoritative mutation commit.
- `POL-T07`: giá thiếu tariff không được sinh, currency/units/source/validity được kiểm.
- `POL-T08`: feature chưa duyệt bị khóa trong connected nhưng fixture/sandbox synthetic vẫn phát triển được.
- `POL-T09`: lựa chọn không có permission, stale question hoặc version mismatch không mutate booking.
- `POL-T10`: xưng hô không suy giới tính; câu trả lời dùng dữ liệu scope thực có.

Mỗi lần đổi policy cần diff decision, owner phê duyệt, version/effective time, affected cases, rollback rule và manifest. Không nâng readiness chỉ để làm acceptance xanh.
