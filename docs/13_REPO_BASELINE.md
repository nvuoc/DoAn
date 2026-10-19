# Mốc repo hiện tại và phạm vi thay thế

Ngày đối chiếu: 19/10/2026, UTC+7. HEAD được ghi trong [SOURCE_MANIFEST](../SOURCE_MANIFEST.json): `60760c65011b077acc75ce249f85edf6d28ab243`. Workspace có thay đổi và file chưa theo dõi; hai PLAN cũng chưa tracked. Đây là snapshot làm cơ sở thiết kế, không phải cam kết production đang chạy cùng SHA.

## 1. Các module và hành vi đã có

| Khu vực repo | Vai trò hiện tại | Lõi mới phải làm rõ |
|---|---|---|
| `src/cli/runner.py` | SessionRunner, lock, voice snapshot, prepare/commit, epoch/state version, request resume | Đưa application service ra khỏi phụ thuộc CLI; typed contract thay đọc graph |
| `src/core/graph.py` | 8 node, InMemorySaver mặc định, graph không persist dùng lúc prepare | Graph orchestration không là nguồn state thứ hai |
| `src/core/state.py`, `validators.py` | Schema, readiness, source validation, địa chỉ verified/service area, xe4/7 | Domain model mới có compatibility mapping, không bypass safety |
| `src/core/nodes/state_reducer.py` | Quyết slots/revision/readiness, pending confirm/cancel, binding nhiều ý | Giữ quyền reducer, whole-turn causality và version dependency |
| `src/core/nodes/persistence.py` | Commit, guards địa chỉ/contact/scope, thay lời thành công khi commit lỗi | Không phát success trước commit; retry path và terminal result |
| `src/services/nlu/` | Legacy rules/mock/provider và engine model_v2 opt-in | Một semantic boundary của core mới; fixture không parser rescue live |
| `src/services/nlu/model.py` | Full-turn proposal, source/reference validation, không tự chọn tool | Mở uncertainty/acts/context có schema và provenance |
| `src/services/address_refinement.py` | Merge components/augment, loại dependencies khi đổi đường/tỉnh | Không tạo append thứ hai; thiết kế normalized projection và immutable raw |
| `src/services/address_verification.py`, `map_resolver.py` | Số nhà/ngõ/entity guard, candidates/evidence, live adapters | Hypotheses không tự verify, policy text-only có gate |
| `src/services/stt_aliases.py`, `maps/normalization.py` | Spoken aliases, bounded variants, number/address normalization một phần | Benchmark mở rộng phonetic/G2P thay vì giả đang chưa có gì |
| `src/addressbridge/`, runtime adapter | Địa giới Hà Nội, historical mapping, candidate-only, flag theo phiên | Coverage Hà Nội khác toàn quốc; source/temporal evidence không dispatch authority |
| `src/services/response_planner.py` | Answer segments, một decision, quay lại question, speed preference | Delivery refs và exact presented history độc lập graph |
| `src/services/output_delivery.py`, `voice_controller.py` | Barge-in, current response/playback ACK, carry final, deadline, post-booking support | Core control contract phải đáp ứng, adapter giữ audio |
| `src/services/runner_bridge.py` | Tuần tự blocking runner/thread, cancellation barrier | Async wrapper không làm mất thứ tự commit/invalidate |
| `src/db/sqlite_manager.py` | Turn idempotency, booking/transcript/checkpoint, durable request generation | One atomic authority; resume giữ request/operation identity |
| `src/services/booking_operations.py`, dashboard services | Operator sửa/hủy, tasks/audit/outbox/quyền | AI mất quyền khi takeover/updated generation; không khôi phục checkpoint cũ |
| `src/web/runtime.py`, routes, presentation | Runtime trên app.state, per-session store, thread calls và public response | Compatibility adapter cung cấp DTO, router không đọc internals core |
| `src/services/admission.py`, Web/LiveKit | SQLite capacity/reservation/heartbeat/expiry chung | Giữ outer admission, không thêm bộ đếm trong core |
| `src/testing/robustness/`, `eval/booking/` | Scenario/fixture/transport/replay/mutation/oracle và validation provenance | Dùng lại công cụ qua engine adapter, không dựng oracle bằng engine mới |

Các đường dẫn ở bảng là code repo, không phải bản sao trong gói. Tên package `src/conversation/` ở kế hoạch là đích đề xuất. Không đổi `src.web.server:app`, facades import cũ và lệnh chạy chỉ để đạt một cấu trúc thư mục mới.

## 2. Ranh giới API cần compatibility

HTTP/Web đang dùng `bot_response`, `response_plan`, `speech_rate`, `resume_after_answer`, `question_response_id`, `booking_state`, latency và endpoint delay. Worker LiveKit đọc snapshot, prepare/commit, request ownership, terminal booking view và post-booking support. Dashboard còn tham gia quyền sở hữu, tasks và callback.

Core mới cần `TurnResult`, `SnapshotView`, `BookingView`, `OwnershipView` và commands typed. Mapping HTTP giữ semantics current reference, không public internal booking ID hoặc dùng customer reference như authorization. Những tài liệu cũ mô tả booking_id trên wire phải đối chiếu bản P1/P2 mới hơn và code hiện hành trước khi lập compatibility tests.

Các phương thức như `prepare_voice_turn/commit_voice_turn` có thể giữ qua facade hoặc thay implementation; contract an toàn phải tương đương. Public prepare/commit không bắt buộc nếu service mới làm được hủy và commit fencing bên trong.

## 3. Những guard cần đưa thành acceptance

1. Câu hỏi phải được trình bày đúng response/revision trước short confirm; hidden/deferred choice không được chọn.
2. Prepare cũ không mutate authoritative graph/DB; commit kiểm epoch/state/session/deadline và durable owner.
3. Operator mutation/resume generation ngăn worker trước đó tiếp tục ghi.
4. Booking, task, response/history và checkpoint được lưu nhất quán; commit lỗi không để response_plan đọc success cũ.
5. Số nhà/ngõ không khớp provider không được customer readback nâng thành verified.
6. Không dùng tâm phường/đường như địa chỉ nhà đã xác minh; chain/parent-child cần đúng identity.
7. Web/voice dùng cùng admission; restart/rollback không tạo shadow counter.
8. Post-booking yêu cầu sửa/hủy là task cho operator theo baseline, không báo hủy hoàn tất.
9. Scope/account ownership không gộp theo số điện thoại hoặc text địa chỉ; restore có quyền, expiry và time revalidation.
10. Provider live lỗi rõ, không âm thầm dùng parser mock; test offline không gọi mạng.

## 4. Bằng chứng kiểm thử có sẵn và giới hạn

Trong lượt phân tích trước của cùng cuộc trao đổi, chạy 8 file: `test_address_refinement.py`, `test_address_safety_pr06m.py`, `test_address_confirmation_once.py`, `test_model_understanding.py`, `test_booking_suggestions.py`, `test_conversation_experience.py`, `test_robustness_tool.py`, `test_booking_eval_dataset.py` bằng `.venv`/offline: **281 passed, 26,47 giây**. Đây là kiểm chứng lõi hiện tại, không chạy lại trong tác vụ tạo gói và không chứng minh engine mới.

Báo cáo repo `docs/changes/2026-10-18-2129-bo-sung-coverage-va-booking-evaluation.md` ghi full suite có coverage **1623 passed/33 failed**, sau đó nhóm rerun có 32 lỗi wrapper Bash trên Windows và secret-scan đã được sửa trong thay đổi đồng thời. Đây là baseline lịch sử không bất biến/không suite xanh; cần chạy lại ở commit/env cố định khi bắt đầu rewrite.

Tài liệu robustness ghi baseline regression 861/139 và stress còn FAIL/BLOCKED; đó là kết quả lịch sử theo oracle đã ghi, không tỷ lệ hiểu model production. Không mang số đó sang manifest engine mới. Corpus/gold thật và audio acceptance còn cần chuẩn bị theo scope tác vụ triển khai.

Tác vụ gói tài liệu chỉ kiểm package, schema, fixtures và SQL minh họa; không chạy toàn runtime suite, provider thật, audio, migration hoặc deploy. [Biên bản gói](../validation/VALIDATION.md) ghi kết quả thực tế.

## 5. Lệnh làm mốc khi bắt đầu code

Các lệnh sau là hướng dẫn cho tác vụ triển khai, chưa chạy trong lần soạn gói. Chạy từ repo bằng shell riêng; `tests/conftest.py` hiện đã cô lập môi trường, nhưng biến được đặt rõ trước import:

```powershell
$env:PARROTGO_DISABLE_DOTENV = '1'
$env:LLM_MODE = 'mock'
$env:MAP_MODE = 'mock'
$env:RAG_ENABLED = 'false'
$env:PERSISTENT_DB_PATH = 'E:/ParrotGo/.tmp/core-rebuild-baseline/bookings.sqlite3'
$env:ADMISSION_DB_PATH = 'E:/ParrotGo/.tmp/core-rebuild-baseline/admission.sqlite3'
.\.venv\Scripts\python.exe -X utf8 -m pytest -q -p no:cacheprovider --basetemp=.tmp/core-rebuild-baseline/pytest-run
```

Basetemp phải là thư mục mới chỉ chứa dữ liệu tạm vì pytest có thể xóa nội dung của nó. Không trỏ DB/config vào production để chuẩn bị test. CI/Linux và Windows phải ghi môi trường khác nhau, không skip assertion để che lỗi nền.

## 6. Những gì có thể viết mới và những gì phải giữ về hành vi

Được viết mới: domain representation, ontology, graph topology, planner, reducer implementation, context builder, persistence adapter/service API và internal package. Không có yêu cầu mang nguyên các regex/fast paths cũ vào engine mới. Legacy giữ riêng trong giai đoạn pin/drain; lỗi live của engine mới không rơi lại legacy giữa lượt.

Cần giữ bằng contract hoặc thay đổi có phê duyệt: quyền sở hữu, confirmation/delivery safety, committed booking truth, dữ liệu gốc, HTTP/public imports, admission, operator workflow, supported vehicles/scope/config. Khi thay hành vi sản phẩm có chủ ý, registry/policy/version/oracle phải thay đồng bộ, không dùng lý do refactor để nới luật.
