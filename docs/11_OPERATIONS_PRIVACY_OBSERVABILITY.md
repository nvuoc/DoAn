# 11 — Vận hành, ngân sách, quyền riêng tư và quan sát

Trạng thái: đặc tả đích đề xuất v3.0, ngày 19/10/2026 (UTC+7). Các con số dưới đây là baseline thử nghiệm phát triển, chưa phải SLA hoặc cấu hình production đã áp dụng. [POL-08 và POL-10](04_CORE_POLICY_MATRIX.md) và [quyết định mở](../decisions/OPEN_DECISIONS.md) ghi điều kiện để dùng với dữ liệu/ngân sách thật.

## 1. Tách ba profile để chẩn đoán đúng

| Profile đích | NLU và công cụ | Side effect | Điều được kết luận |
|---|---|---|---|
| `fixture` | Proposal có cấu trúc, map/FAQ/route fixtures có version | SQLite riêng, effects mô phỏng | Logic state/transaction trong phạm vi fixture |
| `sandbox` | NLU provider thật được cho phép; công cụ theo fixture hoặc adapter sandbox đã khai báo | Effects mô phỏng, DB riêng, không task/dispatch production | Chất lượng NLU trên tập đã chạy và robustness tích hợp sandbox |
| `connected` | Provider hiện được cấu hình, cùng timeout/cooldown được bảo toàn | Local booking intake và task thực theo policy hiện có | Ghi nhận request vào hệ thống; chưa có dispatch thật |

Profile này là vocabulary đích; không đổi ngầm `LLM_MODE`, `MAP_MODE`, `RAG_ENABLED` hoặc launcher cũ. Log luôn ghi profile và adapter mode của từng dịch vụ. Không suy “sandbox” nghĩa mọi công cụ đều offline; report phải liệt kê call thật. Mock không dùng parser legacy để giả hành vi `model_v2`.

Self-host Qwen là phương án hạ tầng riêng: cần endpoint contract, tài nguyên, warmup, concurrency, token budget, revision và số đo. Viết lại lõi không tự thay provider hoặc tải model. Nhà cung cấp nào cũng chỉ trả proposal, không được cầm credential booking hoặc tự gọi công cụ nghiệp vụ.

## 2. Định nghĩa các mốc thời gian

| Metric | Bắt đầu → kết thúc | Ranh giới |
|---|---|---|
| `adapter_turn_assembly_ms` | Nguồn ASR/VAD đầu tiên phù hợp → admitted final turn | Adapter; không thuộc core latency |
| `core_prepare_ms` | Core nhận turn đã chốt → prepared candidate | NLU/read-only tools/reducer/planner/renderer |
| `core_commit_ms` | Bắt đầu chờ ghi → commit xong | Bao gồm queue/SQLite lock; không network |
| `core_result_ms` | Core admission → durable result có thể trả | Có cả prepare và commit |
| `response_first_audio_agent_ms` | Adapter nhận lượt → audio hữu ích đầu phía agent | Không thay cho đo tại loa khách |
| `response_first_audio_client_ms` | Mốc lượt phía client → audio hữu ích output phía client | Cần clock correlation/uncertainty; thiếu thì null |
| `question_delivery_ms` | Committed response → đủ evidence presentation đúng playback | Chưa chứng minh người thật đã nghe |
| `operator_takeover_ms` | Intent được tiếp nhận → worker ACK takeover đúng generation | Không chỉ broker publish |
| `operation_reconcile_age_s` | Bắt đầu UNKNOWN → hiện tại/kết thúc | Quan trọng khi có dispatch ngoài |

Filler/nhạc chờ không tính là câu trả lời hữu ích. Mỗi metric có denominator, unit, nguồn, missing count và clock domain. Không trừ timestamp hai process chưa đồng bộ rồi công bố latency chính xác. Persist UTC để recovery; đo elapsed trong process bằng monotonic. Report p50/p95/p99 và lỗi/timeout cạnh nhau; không loại mẫu chậm để làm đẹp percentile.

Repo hiện cấu hình core chuẩn bị 8 giây, audio hữu ích 12 giây, STT final watchdog 3 giây và no-progress 10 giây. Đây là các setting đã đọc từ `src/config.py`/tài liệu hiện trạng, không phải kết quả đo engine mới. Core chỉ điều khiển ngân sách phần mình; adapter chịu VAD/STT/TTS và cả tổng thời gian nghe được.

## 3. Ngân sách phát triển đề xuất

Baseline sau dùng cho harness và benchmark ban đầu. Có thể cấu hình thấp hơn; việc nới cho production cần có evidence và trần chi phí. Provider override không được vượt absolute turn deadline.

| Nguồn tài nguyên | Baseline đề xuất | Khi hết ngân sách |
|---|---|---|
| Core prepare | Tối đa 8 giây từ admission, adapter có thể cấp ít hơn | Hủy quyền commit prepared work; trả lỗi có loại |
| Phần dự phòng commit | Giữ ít nhất 0,5 giây trong tổng deadline do adapter cấp | Không bắt đầu thêm tool nếu ăn vào dự phòng; thực tế phải đo lock contention |
| NLU | Một phân tích nguyên lượt; thêm tối đa một retry/repair khi loại lỗi cho phép và còn budget | Không dùng parser mock; hỏi lại/handoff qua lượt commit hợp lệ hoặc typed error |
| Map | Tối đa 4 provider calls/lượt, gồm search và details, cache hit không tính provider call | Giữ hypotheses/bằng chứng cũ hợp lệ; làm rõ, không bịa tọa độ |
| FAQ retrieval | Tối đa một request batch/lượt | Báo phần chưa có căn cứ, không dựng policy |
| Route | Tối đa một request/lượt cho đúng snapshot tuyến | Không báo cự ly/ETA thiếu nguồn |
| Tổng calls read-only | Tối đa 8/lượt và cùng absolute deadline | Planner ưu tiên công cụ cần cho quyết định hiện tại |
| Parallel reads | Tối đa 2/lượt; map pool phát triển tối đa 3 trên process | Queue hữu hạn, deadline tiếp tục chạy khi chờ |
| Giao dịch SQLite | Ngắn, không network; busy timeout không vượt deadline còn lại | Rollback, kiểm kết quả trước retry; không giữ audio loop |
| Post-result diagnostics | Queue hữu hạn, không chờ sink khi trả TTS | Drop metric có counter; không drop booking/history bền vững |

8 giây chuẩn bị cộng thời gian commit vẫn phải nằm trong deadline tổng của adapter; không được tự gia hạn lượt. Nếu adapter cấp tổng 8 giây, prepare phải dừng sớm để giữ dự phòng. SQLite timeout hiện hữu 5/10 giây không được bê nguyên vào caller chỉ còn vài trăm ms; compatibility adapter cần timeout thích ứng và test riêng trước thay cấu hình.

Các cap là upper bound, không yêu cầu gọi đủ. Không tạo một LLM cho ASR repair, một LLM cho NLU, một LLM cho rerank và một LLM cho render trên mọi lượt. Phonetic/alias nên sinh hypotheses có giới hạn và cache có version. Không lấy song song nhiều giả thuyết làm lý do vượt trần provider hoặc mất thứ tự fast path/cooldown hiện tại.

Để chọn SLO thật, chạy ma trận câu đơn, đa ý, địa chỉ phân mảnh, cache cold/warm, lỗi provider, contention và bốn phiên đồng thời. Báo chi phí theo provider calls/tokens và đơn giá được cấp tại thời điểm thử; không tự điền giá. Thiếu telemetry giá thì báo lượng dùng, không báo chi phí 0.

## 4. Taxonomy lỗi và cách xử lý

| Mã nhóm | Có retry không? | Hành vi có thẩm quyền |
|---|---|---|
| `INPUT_INVALID`, `INPUT_CONFLICT` | Không tự sửa bằng đổi ID | Reject; domain không đổi |
| `UNAUTHORIZED`, `OWNERSHIP_LOST` | Chỉ sau xác thực/claim hợp lệ mới | Reject/stale; không lộ state ngoài quyền |
| `STATE_CONFLICT`, `QUESTION_STALE` | Có thể chuẩn bị lại có hạn; binding cũ không nâng cấp | Không submit bằng proposal cũ |
| `PROVIDER_TIMEOUT`, `PROVIDER_UNAVAILABLE` | Theo deadline, policy và cooldown | Không fallback mock; không giả provider đã xác minh |
| `PROVIDER_RATE_LIMITED` | Tôn trọng retry-after/cooldown trong budget | Không tạo thác retry từ nhiều worker |
| `PROVIDER_AUTH`, `PROVIDER_BAD_REQUEST` | Không retry mù | Cảnh báo vận hành; phản hồi an toàn không có secret |
| `PROVIDER_INVALID_SCHEMA` | Tối đa repair/retry được phép | Lưu schema error codes, không raw output mặc định |
| `NO_MATCH`, `AMBIGUOUS`, `UNVERIFIED_DETAIL` | Là kết quả domain, không outage | Giữ bằng chứng; hỏi làm rõ theo policy |
| `POLICY_DATA_MISSING`, `TARIFF_UNAVAILABLE` | Chờ dữ liệu version hợp lệ | Không bịa chính sách/giá |
| `STORE_BUSY`, `STORE_WRITE_FAILED` | Có hạn khi chắc rollback | Không phát response chưa commit |
| `COMMIT_OUTCOME_UNCERTAIN` | Đọc lại ID trước quyết định | Không nói đã/không đặt khi chưa xác minh |
| `EXTERNAL_OUTCOME_UNKNOWN` | Reconcile cùng operation/key | Không submit key mới |
| `DELIVERY_FAILED`, `DELIVERY_ACK_MISSING` | Có thể presentation mới nếu còn hợp lệ | Không hủy booking đã commit; không grant confirmation |
| `CANCELLED`, `DEADLINE_EXCEEDED` | Lượt mới hoặc recovery có quyền | Late result bị fence |
| `HANDOFF_UNAVAILABLE` | Chỉ khi có đường hỗ trợ thật | Không nói đã chuyển nếu không có tiếp nhận |

Typed errors ở contract có thể dùng mã chi tiết hơn; phải ánh xạ taxonomy vào một registry versioned, không dựa parse message string. Provider body/stacktrace không đưa vào text cho khách. Timeout task Python không chứng minh thread/provider request dừng; quyền commit và việc đóng stream cần xử lý riêng.

## 5. Retry, cooldown và backpressure

- Retry chỉ khi side effect không xảy ra hoặc được contract idempotency bảo vệ; read-only retry vẫn tiêu tiền/budget.
- Không reset deadline mỗi lần retry; timeout mỗi call bằng min(provider timeout, remaining budget trừ dự phòng).
- Jitter/backoff chỉ trong phần thời gian còn lại; không sleep giữ request lock hoặc SQLite transaction.
- Cooldown dùng scope provider/endpoint phù hợp và giữ hiện trạng đã kiểm chứng; không vô hiệu bằng cách tạo client mới.
- Giới hạn số executor kể cả caller đã hủy. Executor “mồ côi” tính vào utilization cho tới kết thúc; không mở vô hạn để thay cái đã timeout.
- Per-request serialization tránh hai commit đồng thời; IO/DB chạy ngoài event loop audio. Không đặt global lock cho toàn bộ hội thoại.
- Queue đầy trả overload có loại hoặc dừng admission ở runtime chung. Không tạo counter admission riêng trong core.

Các ngưỡng process/container phải tính cả Web, worker, RAG và operator. SQLite chia sẻ trên host không tự biến thành kiến trúc nhiều máy; network filesystem/WAL là quyết định hạ tầng cần chứng minh. Không đổi journal mode trong request path.

## 6. Trace và metrics tối thiểu

Trace không chứa chain-of-thought thô. Ghi structured reason codes, rule IDs và evidence references đủ để debug.

```text
trace_id, request_id_opaque, session_id_opaque, turn_id, input_id,
engine_id, engine_revision, state_schema_version,
profile, provider_adapter, model_revision, prompt_hash,
policy_bundle, catalog_revision, faq_revision, tariff_revision,
state_version_before, state_version_after, observed_state_version,
owner_generation, booking_revision, operation_id, response_id,
stage, elapsed_ms, remaining_budget_ms, provider_call_count,
outcome_code, error_code, retry_count, cache_result, pii_redacted
```

Metric labels có cardinality thấp: engine/profile/stage/outcome/error group. Request/session/turn IDs chỉ dùng trace/log có giới hạn, không làm nhãn Prometheus vô hạn. Payload hash là correlation nội bộ có kiểm soát, không public hash của số điện thoại/địa chỉ dễ dò.

Counters/gauges cần có: admitted/committed/replayed/rejected; input conflicts; stale commits blocked; cancelled/late results; confirmation rejected by cause; duplicate operation suppressed; local booking recorded; outbox pending/oldest age; handoff intent vs ACK; delivery missing/old ACK; provider timeout/rate limit/cooldown; queue size/dropped metrics; operation unknown count/age; SQLite busy/rollback duration; admission lease/release errors từ runtime hiện có.

Thiếu số đo thì trả `null`/missing và counter tương ứng. Không lấy “log không thấy lỗi” làm số lỗi bằng 0. Không lấy lịch sử test trong docs làm kết quả runtime hiện tại.

## 7. Health và readiness

| Probe | Kiểm tra | Không được làm |
|---|---|---|
| Liveness | Process/event loop còn tiến triển | Tạo booking hoặc gọi model có tính phí |
| Core readiness | Schema được hỗ trợ, bundle hợp lệ, store đọc/ghi probe riêng nếu được thiết kế, ownership coordinator sẵn sàng | Tự migration, tự seed dữ liệu hoặc đổi provider |
| Provider status | Trạng thái cấu hình/cooldown/last observation | Tự tuyên quota còn khi provider không cho biết |
| Dashboard readiness | Outbox/commands/handoff backlog theo DB | Báo takeover xong vì Redis có message |
| Voice readiness | Worker registration và điều kiện kết nối đã kiểm | Suy âm thanh tại loa đạt chỉ từ worker registered |
| Admission readiness | Store chung và release/lease hoạt động | Reset lease đang sống để làm probe xanh |

Probe phải tránh lộ đường dẫn, token hoặc PII. Store không ghi được chặn nhận nghiệp vụ mới; request đã có cần lỗi rõ. Provider outage có thể cho phép FAQ/local status tùy policy; readiness phải mô tả degraded capability, không giả toàn hệ thống healthy hoặc tự tắt mọi tính năng.

## 8. Phân loại dữ liệu và quyền truy cập

| Loại | Ví dụ | Mặc định thiết kế |
|---|---|---|
| Bí mật xác thực | API key, cookie, token, claim secret, auth hash | Không vào prompt/log/test/report; chỉ adapter cần quyền |
| Dữ liệu khách nhạy cảm theo ngữ cảnh | Điểm đón nhà riêng, bệnh viện, số liên hệ, lịch sử đi lại | Truy cập theo request/account/operator đã được cấp quyền |
| Nội dung gốc | ASR final, text người dùng, response đã commit | Bất biến khi giữ lại; truy vấn recall theo quyền và retention |
| Bằng chứng domain | Candidate refs, provider refs, verification source | Lưu đủ audit, không biến hypotheses thành fact |
| Telemetry vận hành | Duration, counts, error/rule IDs | Redacted, hạn chế cardinality; không raw transcript |
| Corpus synthetic | Câu tổng hợp/fixtures trong gói này | Có provenance; không gán thành transcript thật |

Tách storage nghiệp vụ cần giữ nguyên văn khỏi log vận hành. “Raw bất biến” không có nghĩa giữ mọi transcript vô thời hạn. Quyền xóa/retention cần áp vào DB, WAL/checkpoint, backup, export, trace và các snapshot derived theo policy được chốt; không hứa đã xóa triệt để chỉ vì xóa một row.

Baseline development chỉ dùng synthetic và giữ artifacts trong thư mục riêng. Triển khai với dữ liệu thật bị chặn ở phần retention/access/encryption chưa có quyết định; không tự đặt thời hạn pháp lý. Cần owner doanh nghiệp xác định mục đích, retention theo loại dữ liệu, quyền truy cập/xuất, phạm vi provider processing, thời gian backup và cách đáp ứng xóa. Đây là yêu cầu thiết kế vận hành, không phải tư vấn pháp luật hoặc chứng nhận tuân thủ.

SQL minh họa lưu JSON dạng đọc được để thử bằng synthetic; không cung cấp encryption. Production phải chọn cơ chế bảo vệ file/volume, transport, key lifecycle và export được kiểm chứng trước khi có claim bảo mật. Auth/contact của repo là tự khai, chưa có OTP; core không nâng mức tin cậy danh tính chỉ vì đã có `account_id`.

## 9. Logging an toàn và xuất bằng chứng

Mặc định chỉ log IDs mờ, rule/error codes và versions. Redaction chạy trước sink; redact key theo field name và deny-list các cấu trúc provider raw. Exception logger phải loại header/body/query chứa credential hoặc transcript. Không đưa `.env`, tài khoản thật, mã booking khách, số điện thoại thật, coordinate nhà riêng hoặc customer audio vào gói test/báo cáo.

Xuất PII là thao tác riêng có quyền và audit, không phải bật `--debug`. Public/test artifacts dùng synthetic; hạn chế quyền file cho backup/report. Không lấy data từ call thật để tự sinh catalog spoken aliases; catalog chỉ nhận nguồn có quyền sử dụng và có duyệt.

Prompt chứa các phần tin cậy và không tin cậy phân tách rõ. User text, retrieved FAQ hoặc provider label không thể tạo control event, bỏ confirmation, thay policy hoặc cấp quyền API. Không cung cấp credential side effect cho model; không thực thi code/tool name lấy từ nội dung retrieval. Mọi operation vẫn qua deterministic policy và transaction coordinator.

## 10. Runbook theo sự cố

| Triệu chứng | Kiểm chứng đầu tiên | Hành động an toàn |
|---|---|---|
| Khách hỏi “đã đặt chưa?” sau mất mạng | Turn/operation/result và booking/task cùng request | Trả trạng thái có thẩm quyền; không chạy lại submit |
| Latency tăng | Breakdown queue/NLU/map/lock/TTS, sample counts | Giảm optional search; giữ deadline, không bỏ confirmation |
| SQLite busy tăng | Writer duration, long reads, disk/WAL, shared path | Dừng cohort mới nếu cần; không đổi journal mode nóng |
| Worker cũ còn trả câu | Request generation, turn phase, response revision | Fence worker và delivery; giữ booking đã commit |
| Operator takeover chậm | Durable command, generation, completion ACK, room | Không hứa đã có người nghe; giữ task/callback thật |
| Broker ngừng | Outbox backlog và reconciler | Khôi phục transport; domain commit không bị xóa |
| Duplicate kết quả | Input IDs/hash, operation unique, consumer dedup | Dừng side effect liên quan, đối soát; không xóa audit để che lỗi |
| Address model chọn sai | Source utterance, versions, hypotheses, evidence, question | Sửa rule/data qua regression; không tăng prominence vô điều kiện |
| External UNKNOWN tăng | Operation/key/reference và provider status | Reconcile hoặc operator; không blind retry key mới |
| Store không đọc được | Backup integrity, disk health, current writer | Chặn mutation; phục hồi theo [09](09_MIGRATION_AND_CUTOVER.md), bảo toàn đơn mới |

Incident report ghi timeline UTC+7 cho người đọc và UTC chuẩn trong telemetry, affected requests bằng opaque refs, claim nào đã phát, authoritative outcome, containment, test tái hiện, giới hạn bằng chứng. Không tự gửi email/Slack hoặc thông báo khách từ runbook; các hành động bên ngoài cần authorization của tác vụ triển khai thực tế.

## 11. Điều kiện bàn giao vận hành

Implementation cần có test failure injection cho metrics sink chết/queue đầy, provider 429/timeout/auth error, SQLite contention/commit uncertain, restart, stale worker, ACK cũ và outbox lặp. Redaction cần thử bằng synthetic canary secrets; không dùng key thật. Backup/restore và rollback cần rehearsal trên DB riêng có booking phát sinh sau snapshot.

Có thể hoàn thành phát triển offline trong khi POL-08/POL-10 đang chờ quyết định. Không gọi đó là production-ready và không báo metric/SLO đạt khi chưa có run evidence. Xem [test factory](08_TEST_FACTORY_AND_ACCEPTANCE.md), [backlog](10_IMPLEMENTATION_BACKLOG.md) và [giao thức giao dịch](03_CORE_TRANSACTION_PROTOCOL.md).
