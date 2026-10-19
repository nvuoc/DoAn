# 09 — Tương thích, chuyển lõi và hoàn tác

Trạng thái: kế hoạch đích đề xuất v3.0, 19/10/2026 (UTC+7). Chưa đổi engine mặc định, route, schema hoặc hạ tầng của ParrotGo. Viết lại lõi không mặc nhiên cho phép đổi sản phẩm, dữ liệu, cấu hình provider, domain hay cơ chế admission. Lịch sử deploy và hướng dẫn trong tài liệu nguồn là bằng chứng quá khứ, không phải lệnh cần thực thi khi đọc bộ tài liệu này.

## 1. Mục tiêu chuyển đổi

Có thể thay toàn bộ phần hiểu lượt → state/reducer → policy/planner → điều phối công cụ → response → commit. Các adapter Web, CLI, LiveKit, TTS và dashboard tiếp tục qua facade tương thích. Phiên đã hoạt động không bị đổi engine giữa lượt, booking mới không mất khi rollback, operator không bị hai engine giành quyền ghi.

Lõi mới đề xuất đặt dưới `src/conversation/`; đây là tên kiến trúc cần được hiện thực trong repo, chưa phải package đã tồn tại. CLI chạy cùng lõi qua adapter; không dựng ứng dụng `taxi_ai` song song, không đổi lệnh ASGI `src.web.server:app` để đạt mục tiêu viết lại core.

## 2. Inventory phải bảo toàn

Các đường dẫn sau là hiện trạng trong repo nguồn, không phải link nội bộ của gói export:

| Hợp đồng hiện tại | Điểm sở hữu | Điều cần giữ khi thay lõi |
|---|---|---|
| Runner CLI/voice | `src/cli/runner.py`, `SessionRunner` | Facade khởi tạo, chuẩn bị/commit lượt, post-booking và cách truyền metadata delivery |
| Factory Web | `src/web/runtime.py`, `src/web/server.py`, `src/web/routes/` | `create_app(WebRuntime(...))`, runtime tại `app.state.runtime`, route/status/payload đã công bố |
| Voice loop | `src/services/voice_controller.py`, `src/livekit_agent.py` | turn assembly, cancellation, generation/epoch, phát/ACK, release khi lỗi |
| Booking DAL | `src/db/sqlite_manager.py`, `src/core/nodes/persistence.py` | Booking success sau commit, contact, verification, service area, retry được |
| Resume v4 | `agent_requests`, `agent_request_sessions` và `dashboard_calls` | Request identity, generation, quyền truy cập; không tự gộp theo phone |
| Dashboard v5 | `src/db/dashboard_migrations.py`, `dashboard_store.py` | Schema kiểm tra tường minh; không tự migration lúc startup |
| Task/lifecycle operator | `src/db/operator_tasks.py`, `src/services/booking_operations.py` | Task tạo cùng booking; sửa/hủy có revision, idempotency, audit và fence AI |
| Outbox/transcript | Dashboard SQLite + Redis/SSE | DB là authority; event invalidation không phát PII; inbox ghi trước HTTP ACK |
| Admission chung | `src/services/admission.py` | Reservation/claim/heartbeat/expiry/release và lease account chung Web/voice |
| Provider facade | `src/services/llm_extractor.py`, `src/services/vietmap_client.py` | Giữ import cũ; không tạo transport/cache singleton trùng |
| Cấu hình/chạy | `src/config.py`, `.env.example`, launchers | Không đổi key/provider/model mặc định bằng refactor; không đọc `.env` vào artifact |

Một số đường dẫn cần tìm lại khi code đã thay đổi; inventory là snapshot ngày biên soạn. [Baseline repo](13_REPO_BASELINE.md) và manifest nguồn xác định chính xác bản đã đọc.

## 3. Mapping nghiệp vụ cần viết thành adapter

| Target core | Legacy tương thích | Giới hạn |
|---|---|---|
| `collecting` | `call_sessions.booking_status=collecting` | Không tự coi có đủ slot là đã sẵn sàng |
| `awaiting_confirmation` | `confirming` | Giữ question/revision/delivery binding; không chỉ map chuỗi |
| `submitting` | Không có đối ứng đầy đủ trong legacy session CHECK | Chỉ dùng internal operation; không ghi enum lạ vào bảng cũ |
| `request_recorded` | Session `booked`, booking `confirmed` | Chỉ local intake; giữ `dispatch_status=not_integrated` |
| `cancel_pending` | `cancel_pending` hoặc operator follow-up còn mở | Yêu cầu hủy chưa phải đơn đã hủy |
| `cancelled` | Session `canceled`, booking `canceled` theo loại thao tác | Phân biệt hủy draft và hủy booking; cần audit/ủy quyền |
| `operator_required` | `operator_required` + task/request hiện có | Không hứa người đang nghe nếu chưa takeover ACK |
| `submit_failed` | Không ép thêm enum vào bảng cũ | Lưu operation/error nội bộ, facade trả lỗi đã định nghĩa |

Các mapping này là thiết kế, chưa áp dụng. Facade không được suy booking outcome chỉ từ enum session. Đọc booking, dispatch và task có thẩm quyền để trình bày.

### Ownership và đồng ghi

Trong coexist, chọn một authority ownership dùng cho mọi writer. Baseline chuyển đổi là giữ `agent_requests.generation` cùng transaction với booking và lệnh operator. New core coordinator đọc/kiểm generation này; SQL target không tạo một fence độc lập có thể lệch. Khi muốn chuyển authority sang domain schema mới, phải migration tất cả writer/reader liên quan trong cùng release tương thích và có chứng minh rollback.

Trước cutover, mọi đường ghi booking/operator phải qua API transaction-aware. Không vừa gọi DAL cũ tự commit vừa ghi core store riêng rồi đối soát “best effort”. Không chạy hai engine authoritative cho cùng request; mirror ghi hai DB không phải đảm bảo atomicity.

Legacy `bookings.session_id` đang unique. Nếu một adapter cho phép tạo request mới trong cùng cuộc gọi, phải có thiết kế session nghiệp vụ tương thích hoặc migration được review; không lặng lẽ bỏ unique constraint. Quan hệ request–session của lõi mới không tự sửa constraint legacy.

## 4. Pin engine theo request

Tại lúc tạo request, server ghi engine identifier/version, state schema version, policy bundle và version dữ liệu/prompt cần tái tạo. Cấu hình mặc định chỉ quyết định request mới, không đổi pin của request đang sống. Provider thực tế được log; failover chỉ theo policy đã khai báo và không chuyển live sang mock.

| Loại request | Engine được chọn |
|---|---|
| Request legacy có checkpoint cũ | Legacy cho tới khi kết thúc hoặc được migration có chủ đích |
| Request mới thuộc cohort thử | New core, pin ngay từ lần tạo |
| Request new core gọi lại ở session mới | Cùng engine/schema đã pin; không chọn theo process nhận mới |
| Request operator đang sở hữu | Quyền operator giữ ưu tiên; AI không tự claim lại |
| Request không xác định version | Từ chối mutate; hiển thị/đọc an toàn hoặc chuyển hỗ trợ |

Không canh random mỗi turn hoặc mỗi worker. Router đọc pin từ DB. Nếu binary hiện tại không hỗ trợ pin, trả lỗi có loại và route tới instance tương thích hoặc duy trì maintenance cho request đó; không đọc JSON tùy ý rồi đoán.

## 5. Lộ trình thực hiện có gate

| Pha | Đầu ra cụ thể | Bằng chứng để đi tiếp |
|---|---|---|
| C0 — Đóng contract | Domain schemas, mapping, policy baseline, independent oracle | Contract fixtures kiểm validate; review các quyết định đang mở |
| C1 — Pure core | NLU proposal boundary, deterministic reducer/planner, renderer | L1/L2, whole-turn conflicts, location safety và question bindings đạt |
| C2 — Transaction harness | Local store/operation/outbox/fence/recovery | Race/fault tests L4, retry rollback và takeover đạt trên DB riêng |
| C3 — Facade adapter | `SessionRunner` compatibility, Web/voice/TTS adapter | API contract, admission, delivery và old import/run commands đạt |
| C4 — So sánh cô lập | Shadow/replay có capability bị giới hạn | Báo lỗi theo denominator; không side effect đối chứng |
| C5 — Opt-in dev/cohort | Engine pin bền vững, canary observability | Những gate liên quan có evidence; chỉ các feature đã có policy được bật |
| C6 — Tăng phạm vi | Cohort rộng hơn cho request mới | Baseline so sánh và vận hành trong budget; rollback đã diễn tập |
| C7 — Bỏ phần lõi cũ | Reader tương thích dữ liệu giữ lại; legacy request đã drain | Không reader/writer còn phụ thuộc graph cũ; artifacts phục hồi lưu đủ |

Đây là trình tự đề xuất, không có mốc thời gian hoặc chữ ký duyệt giả. Phần chưa có quyết định nghiệp vụ có default bảo thủ trong [OPEN_DECISIONS](../decisions/OPEN_DECISIONS.md); không chặn viết pure core/fixture của các phần độc lập. Gate không phải yêu cầu deploy ngay trong tác vụ chuẩn bị tài liệu.

## 6. Shadow và so sánh hai engine

Shadow dùng snapshot đã được phép sử dụng hoặc synthetic replay, một DB riêng, side-effect capability bị loại bỏ. Kết quả shadow chỉ là evidence phân tích; không được phát TTS, trả cho khách, tạo booking/task, gửi handoff hoặc đổi ownership thật.

- Adapter nghiệp vụ shadow trả structured simulated outcomes; không dùng các fake này ghi vào bảng live.
- Read-only provider thật chỉ được bật khi phạm vi sử dụng dữ liệu và chi phí đã được cho phép. Mặc định offline fixtures; không tự gọi thêm mạng vì đã có key trong máy.
- Request IDs được namespace cho shadow store; giữ correlation tham chiếu không chứa PII. Không import auth secrets/claim token/cookie từ production.
- Shadow callback và metric không được gây tác động vào voice latency. Queue hữu hạn, loại mẫu khi overload và ghi số bị loại.
- So sánh semantics: slot mutation, clarification, evidence, questions, outcome, latency/cost; không lấy câu chữ của engine cũ làm oracle duy nhất.
- Lỗi cũ đã được xác nhận phải có expected behavior riêng; không ép new core giữ bug để đạt tỷ lệ bằng nhau.

Gate chất lượng phải ghi rõ mock/provider/audio và provider calls. Bài chạy chỉ có fixture không chứng minh NLU live; script/schema validation không phải benchmark engine.

## 7. Drain và cutover request mới

Hai cách hợp lệ, chọn theo khả năng hạ tầng tại release thật:

1. **Hai engine trong binary tương thích:** request cũ giữ pin legacy; request mới chọn cohort new core. Khi chưa có request cũ cần code, mới gỡ legacy implementation.
2. **Maintenance/drain:** ngừng admission mới bằng cơ chế hiện có, chờ các lease/call hoạt động kết thúc theo policy, giữ đủ thời gian xử lý task/operation, rồi dừng writer để backup/migration. Không kill turn đang commit để ép drain nhanh.

Phải inventory Web session RAM, LiveKit worker, pending voice reservations, request có operation UNKNOWN, outbox pending, operator đang claim và callback chưa xong. “Không còn cuộc gọi” không chứng minh hết công việc bền vững. Request chưa xong cần owner mới hoặc đưa về trạng thái chờ hợp lệ có audit.

Admission không bị reset để làm số về 0. Reservation lỗi/expired vẫn release theo store chung. Thu hồi Web/voice owner không đồng nghĩa xóa request hoặc booking. Phiên RAM đang chạy không tự khôi phục nhờ core store mới; adapter còn phải thực hiện protocol resume có quyền.

## 8. Migration dữ liệu và tương thích checkpoint

Mọi migration thật cần file versioned riêng và dry-run trên bản sao SQLite tổng hợp hoặc backup được bảo vệ. Không có lệnh trong gói này chạy migration production.

Các bước thiết kế:

1. Chụp inventory schema/migration version thực tế; khác biệt môi trường phải được xử lý tường minh.
2. Thêm schema theo kiểu mở rộng tương thích trước khi thay reader/writer; old binaries phải hiểu hoặc bỏ qua an toàn.
3. Tạo pin legacy cho request cũ nếu cần; không biến lịch sử không có checkpoint thành request có thể mutate.
4. Ánh xạ source request ID, generation, booking ID, event sequence và schema format; kiểm FK, duplicate và revision. Không tạo booking mới khi chuyển checkpoint.
5. Dữ liệu không ánh xạ được đi vào hàng review/read-only có lý do; không tự điền tọa độ, confirmation, delivery hoặc owner.
6. Đối chiếu counts, tổng task, booking reference, status, revision và hash của dữ liệu bất biến trước/sau.
7. Xác nhận new/old compatible binary trên DB đã migration; test rollback với booking mới được tạo sau migration.

Checkpoint `checkpoint_version=1` trong schema v4 hiện có không đồng nghĩa state schema của lõi mới. Phải có converter có version và validation, hoặc giữ legacy reader. Không nạp graph checkpoint cũ thẳng vào schema mới.

Khi resume: xác thực account/call access ở adapter, khách chọn tiếp tục rõ ràng, claim generation atomic, đọc state đã commit, kiểm lại giờ đón/vùng phục vụ/các dữ kiện hết hiệu lực. Không restore playback eligibility; phát lại câu phù hợp bằng response/playback mới. Booking operator đã sửa/hủy hoặc đang được xử lý cần đọc authoritative state và giữ AI mất quyền nếu chưa được trao lại.

## 9. Rollback không làm mất booking mới

| Sự cố | Hoàn tác an toàn |
|---|---|
| New core lỗi ngữ nghĩa | Tắt cohort cho request mới; request pin new giữ instance tương thích hoặc chuyển hỗ trợ có fence |
| Provider new lỗi | Áp lỗi/cooldown theo policy; giữ engine pin; không đổi sang mock |
| New binary lỗi trước migration | Quay binary tương thích trước, không đổi dữ liệu |
| Đã migration additive | Dùng binary đọc schema mới/compatibility reader đã thử; có thể giữ cột/bảng thêm |
| Đã có booking mới | Không chép backup cũ đè DB hiện tại; đối soát/fix forward hoặc chuyển sang compatible binary |
| Writer mới đã đổi format không tương thích | Dừng cohort và giữ maintenance cần thiết; converter ngược phải được thử trên copy trước |
| External operation đang UNKNOWN | Giữ operation ledger/key/reference; không chạy submit mới từ engine cũ |
| Outbox chậm sau rollback | Consumer tương thích xử lý cùng event IDs; không xóa outbox để làm sạch readiness |

Backup là điểm phục hồi thảm họa, không phải cơ chế undo mọi release. Thử restore trên DB riêng, đối chiếu WAL bằng backup API, kiểm toàn vẹn và thời điểm chụp. Nếu phải phục hồi thảm họa, cần đối soát mọi đơn phát sinh sau backup theo thủ tục riêng; không tuyên bố zero data loss khi chưa có bằng chứng.

Ngừng triển khai không được sửa branch protection, push hay sửa cấu hình VPS tự động trong tác vụ viết lại. Khi phát hành thật, dùng quy trình hiện hành và phạm vi đã được người dùng cho phép.

## 10. Checklist hồ sơ phát hành cần có

- SHA/digest app/Web/worker và version engine/schema/prompt/policy/catalog/FAQ/tariff.
- Danh sách test thực chạy, số pass/fail/blocked, log, môi trường, fixture/live/audio; diff với baseline thực.
- Compatibility matrix: binary cũ/mới × DB cũ/mới × request legacy/new × quyền bot/operator.
- Race/fault evidence và recovery UNKNOWN; zero safety failure trong tập test bị khóa đã chạy.
- Counts và hashes trước/sau dry-run; không đưa PII vào báo cáo.
- Cohort routing, drain plan, health/readiness, stop trigger, rollback binary và người thực hiện được phân công khi triển khai.
- Các quyết định POL chưa chốt và tính năng tương ứng vẫn disabled; không dùng checklist như bằng chứng đã được duyệt.
- Báo cáo mới trong `docs/changes/` khi thay đổi repo thật; không sửa báo cáo lịch sử để thay chứng cứ.

Tài liệu này chuẩn bị thiết kế chuyển đổi. Chưa tạo converter, migration, facade, deployment hay kết quả canary. Cần hiện thực và kiểm chứng theo [backlog](10_IMPLEMENTATION_BACKLOG.md) và [nghiệm thu](08_TEST_FACTORY_AND_ACCEPTANCE.md).
