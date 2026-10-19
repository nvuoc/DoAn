# Truy vết hợp nhất và các quyết định chỉnh sửa

Ngày 19/10/2026 · Nguồn gốc/checksum ở [SOURCE_MANIFEST](../SOURCE_MANIFEST.json). Lưu nguyên [PLAN](../sources/PLAN.md) và [BONUS](../sources/PLAN_BONUS.md). Toàn bộ heading của hai nguồn được liệt kê trong [SOURCE_COVERAGE.json](../SOURCE_COVERAGE.json) với line, destination và disposition; kiểm tra cấu trúc đó không thay review ngữ nghĩa của từng yêu cầu.

## 1. Cách hợp nhất

Không ghép nguyên hai file thành một tập chỉ dẫn có mâu thuẫn. Đặc tả v3 giữ yêu cầu/tình huống hữu ích, sửa giải pháp chưa an toàn, chuyển các phần chưa cần sang roadmap và giữ nguyên nguồn để người review đối chiếu. “Giữ” không có nghĩa đã triển khai; “sửa” có lý do dưới đây; “hoãn” có gate/feature disabled.

Ví dụ, câu trong BONUS bảo Tier1 luôn thắng, pseudocode nối raw và ví dụ facts địa giới không được áp dụng như luật chuẩn. Các lời “bạn có muốn”, phần nhận xét lặp và chỉ dẫn tạo project mới chỉ tồn tại trong archive, không là backlog thi hành.

## 2. Đối chiếu tất cả phần của PLAN

| Nguồn | Quyết định | Đích chuẩn trong v3 |
|---|---|---|
| §1 Mục tiêu/DoD/phạm vi/ưu tiên | Sửa scope CLI-only thành core đa adapter, giữ safety/không bịa và mock truthfulness | [Kế hoạch](../PLAN_HOP_NHAT.md), [contract](01_CORE_CONTRACT.md) |
| §2 Quyết định kiến trúc | Giữ boundary; model/backend pluggable; một atomic domain authority | [Giao dịch](03_CORE_TRANSACTION_PROTOCOL.md), [registry](../decisions/OPEN_DECISIONS.md) |
| §3 Modules và turn/error pipeline | Mở whole-turn fold, typed controls và guarded commit; graph không source thứ hai | [Contract](01_CORE_CONTRACT.md), [state](02_CORE_STATE_MACHINE.md) |
| §4 Profiles/model serving | Giữ fixture/sandbox/connected; self-host là thử nghiệm, không tự đổi config | [Kế hoạch](../PLAN_HOP_NHAT.md), [ops](11_OPERATIONS_PRIVACY_OBSERVABILITY.md) |
| §5 CLI commands/debug/resume | CLI là adapter; các commands mới là deliverables, chưa lệnh có sẵn | [Backlog](10_IMPLEMENTATION_BACKLOG.md), [migration](09_MIGRATION_AND_CUTOVER.md) |
| §6 Schemas/lifecycle/required slots/history | Chuẩn hóa IDs/versions/availability/delivery; không copy nguyên schema không compatibility | [State](02_CORE_STATE_MACHINE.md), [policy](04_CORE_POLICY_MATRIX.md) |
| §7 Intent/acts/roles/negation/references | Giữ ordered acts; mở uncertainty/refinement/source evidence, whole-turn authorize | [NLU/context](05_NLU_AND_CONTEXT.md) |
| §8 Graph/planner/confirmation/idempotency/handoff/invariants | Giải xung đột priority vs order; idempotency xuyên session; durable owner + delivery | [Giao dịch](03_CORE_TRANSACTION_PROTOCOL.md), [response](07_RESPONSE_AND_DELIVERY.md) |
| §9 Địa chỉ/alias/ngõ/parent-child/Vietmap | Giữ evidence/precision; prominence soft; map API phải xác minh tại integration | [Location/knowledge](06_LOCATION_AND_KNOWLEDGE.md), [policy](04_CORE_POLICY_MATRIX.md) |
| §10 Route/ETA/fare/cache | Giữ provenance/range/tariff; không tự dùng heuristics như nguồn route thật | [Location/knowledge](06_LOCATION_AND_KNOWLEDGE.md), POL-07 |
| §11 FAQ/policy/approved/effective/source | Giữ hard rules ngoài RAG, scope/temporal/conflict; dùng port adapter hiện có | [Location/knowledge](06_LOCATION_AND_KNOWLEDGE.md) |
| §12 Templates/recall/style/clarification | Mở delivery-aware exact recall, bounded issues và one decision | [Response/delivery](07_RESPONSE_AND_DELIVERY.md), [NLU](05_NLU_AND_CONTEXT.md) |
| §13 Chín mẫu hội thoại | Giữ các tình huống; chuyển thành synthetic cases, không coi facts/giá là đã chạy | [Examples](../examples/scenarios.jsonl), [acceptance](08_TEST_FACTORY_AND_ACCEPTANCE.md) |
| §14 L1/L2/L3/ma trận/gold | Giữ và thêm L4 event timeline; quy mô corpus là tham khảo | [Acceptance](08_TEST_FACTORY_AND_ACCEPTANCE.md) |
| §15 Semantic-first/mutators/oracle/metrics/report | Giữ independent oracle/frozen holdout; mở M1-M5 và observable ambiguity | [Acceptance](08_TEST_FACTORY_AND_ACCEPTANCE.md), [scenario schema](../schemas/scenario.schema.json) |
| §16 Repo/dependencies/env/install/serving/smoke | Thay layout taxi_ai-cli bằng rebuild trong repo; giữ entrypoints qua facade | [Baseline](13_REPO_BASELINE.md), [migration](09_MIGRATION_AND_CUTOVER.md), [backlog](10_IMPLEMENTATION_BACKLOG.md) |
| §17 Interfaces/transaction/logging/privacy/quota | Đã có nền, mở runtime controls, phase recovery, trusted envelope và redaction | [Contract](01_CORE_CONTRACT.md), [transaction](03_CORE_TRANSACTION_PROTOCOL.md), [ops](11_OPERATIONS_PRIVACY_OBSERVABILITY.md) |
| §18 Pseudocode/prompt/reference tests/debug | Thay code minh họa không an toàn bằng protocol/state tables; scripts trong archive không thực thi | [State](02_CORE_STATE_MACHINE.md), [NLU](05_NLU_AND_CONTEXT.md), [schemas](../schemas/turn-input.schema.json) |
| §19 M0-M8/acceptance/stop | Thay mốc dựng repo mới bằng R0-R8 có behavior slices và cutover gates | [Backlog](10_IMPLEMENTATION_BACKLOG.md), [acceptance](08_TEST_FACTORY_AND_ACCEPTANCE.md) |
| §20 Risks/missing data/distinctions | Giữ, chuyển quyết định thực tế thành registry và safe disabled feature | [Registry](../decisions/OPEN_DECISIONS.md), [policy](04_CORE_POLICY_MATRIX.md) |
| Phụ lục A 64 phát ngôn | Giữ nguyên text, số thứ tự, contextual suggestions/provenance; không đổi thành gold tự động | [64 seeds](../data/original-64.jsonl) |
| Phụ lục B Demo policies/places/tariffs/tests/admin data | Giữ vai trò fixture; không dùng số/địa chỉ làm facts; cases mới có preconditions | [Policy](04_CORE_POLICY_MATRIX.md), [examples](../examples/scenarios.jsonl), [geo](06_LOCATION_AND_KNOWLEDGE.md) |
| Phụ lục C Sources/effectiveness/version maintenance | Giữ archive và yêu cầu integration recheck; không tuyên bố mọi URL mới đã verify | [Sources README](../sources/README.md), [ops](11_OPERATIONS_PRIVACY_OBSERVABILITY.md) |
| Phụ lục D Coding handoff/checklists | Viết lại theo scope repo mới, compatibility và đúng quyền tác vụ | [Kế hoạch](../PLAN_HOP_NHAT.md), [backlog](10_IMPLEMENTATION_BACKLOG.md) |

## 3. Đối chiếu BONUS theo nhóm nội dung

| Nhóm trong BONUS | Giữ/mở/sửa | Quyết định v3 |
|---|---|---|
| Phục hồi ASR tại NLU, 3 lớp text | Giữ có chỉnh | Raw server-owned bất biến; normalization/hypothesis có nguồn; self confidence không quyền |
| Span validation khi canonical khác raw | Mở | Source span chứng minh khách nói; normalization mapping kiểm riêng; không tắt source guard |
| Side-talk và ignored_spans | Sửa | Model đề xuất span, vẫn audit và kiểm safety/conflicts, không xóa mù |
| Địa chỉ bị cắt nhiều lượt | Giữ | Merge component idempotent; không nối raw thành lịch sử mới |
| Số đếm/giờ/phương ngữ | Giữ có scope | Typed normalizer, ambiguous numbers hỏi lại, time neo input timestamp/timezone |
| VniPhonetic/Soundex | Thử nghiệm | Bảng nhóm âm là giả thuyết; benchmark collision/dialect/POI nhỏ trước áp dụng |
| Anchor + phonetic match | Giữ có điều kiện | Cần bằng chứng số/ngõ và địa bàn thật, không suy địa chỉ tồn tại từ ngữ âm |
| Adaptive clarification | Giữ | Issue progress và bounded attempts; câu đóng chỉ khi hypothesis được hỗ trợ |
| Self-repair markers, corrupted connector | Giữ | Whole-turn scope/conditional reasoning, không last-wins khi bất định |
| M1 dialect/spoken numbers | Sửa oracle | Chỉ assert equivalence khi transform giữ semantics; hẻm/kiệt/ngách/xuyệt không mọi nơi tương đương |
| M2 phonetic corruption | Sửa oracle | Guess có thể ambiguous; không bắt giữ command khi text không đủ nghĩa |
| M3 drop/truncation/negation | Sửa oracle | Không yêu cầu phát hiện từ mất không thể quan sát; no unsafe action theo context |
| M4 background injection | Giữ có review | Không giả mọi câu chèn là noise, xem đối tượng và scope hướng tới tổng đài |
| M5 multi-turn fragmentation | Giữ | Final projection đầy đủ, partial không được buộc đoán thông tin chưa đến |
| Patch schema v2.1 | Thay schema chuẩn | Tên field v3 thống nhất; không duy trì nhiều tên confidence/reconstructed text cạnh tranh |
| APPEND_OR_REFINE_SLOT pseudocode | Thay implementation idea | Component operation có dedup/dependencies; số nhà mới revalidate version/confirm |
| Normalizer YAML/homophones | Sửa | Candidate rules có source/scope, không map quỷ chiến thành cancel tự động |
| Phonetic consonant/rhyme/tone dictionary | Thử nghiệm | Không tuyên bố chuẩn âm vị thống nhất; giữ alternate evidence và hard constraints |
| Templates progressive escalation | Giữ có chỉnh copy | Không nói “tín hiệu nhiễu” khi chỉ suy từ text; không hứa tài xế gọi khi chưa có path |
| Bất đối xứng đón/đến | Giữ nguyên tắc, sửa gate | Pickup viable/destination sufficient/route estimable/verification độc lập |
| Loại tọa độ chính xác, tự anchor tâm vùng | Bác luật tuyệt đối | Giữ role/precision/source; không tự chọn center/branch hoặc nâng readiness |
| Một lượt một địa chỉ, origin-first | Sửa | Một offered decision, được extract nhiều địa chỉ; ưu tiên ý khách/safety, không khóa cứng origin-first |
| ContextDiffFormatter/scope override | Giữ có điều kiện | Chỉ lược phần không làm mất phân biệt; scope theo endpoint/inquiry, không scope toàn chuyến |
| Visual clue coaching | Giữ | Hướng dẫn đọc biển hiệu/mốc/người quanh đó, không giả nhìn được cảnh thật |
| Co-located POI <100m | Thử nghiệm | Threshold tune theo dữ liệu/độ chính xác; uniqueness trong results không chứng minh ngoài đời |
| Alley number mismatch guard | Giữ | Exact structure/number evidence, không lấy result đầu gần giống |
| Tuyệt đối tin khách, chọn ngõ gần số | Bác quyền auto-book | Giữ raw/support, không nâng verification hoặc suy tọa độ ngõ từ số thứ tự |
| Viet-lish aliases/G2P | Giữ và thử nghiệm | Reviewed aliases có scope; G2P generated cần provenance/benchmark; no fake universal coverage |
| Single-letter entity guard | Giữ có điều kiện | E/K/cổng/tòa là hypotheses, explicit user correction/branch/area vẫn ưu tiên |
| LLM phonetic guess canonical | Giữ có điều kiện | Song song raw/candidate có budget; model guess không verified name |
| Tier1–4 hard weights/85% | Bác luật cứng | Prominence soft feature sau filter, tune/dev freeze/holdout; POI nhỏ exact có thể đúng |
| Luôn hai luồng raw/reconstructed | Sửa | Bounded query plan, cache/budget/deadline, không nhân request bắt buộc mọi lượt |
| Hỏi FAQ trả thẳng địa điểm lớn | Sửa | Giữ uncertainty/reference, hỏi phân biệt hoặc conditional facts có source |
| Express uncertainty | Giữ | Không confirm/reject tự động; evidence mới có thể hỗ trợ hoặc xung đột |
| Pending hold/resume | Giữ và mở | Có target/version/expiry/delivery; hỏi xen ngang không tự xóa nhưng không giữ vô hạn |
| Đại từ tự trỏ pending | Sửa | Explicit/new focus được xét trước; pending không ghi đè referent rõ của câu |
| Answer & bridge back | Giữ | Một decision rõ, long answer có resume hook; reuse only current summary |
| Hỏi B trong khi đặt A | Giữ có chỉnh | Booking A giữ nguyên; hỏi A/B cần lựa chọn rõ, yes/no không tự chọn |
| Ví dụ facts Bích Động/Hà Đông/cơ sở viện | Chỉ giữ tình huống | Chưa xác minh facts hiện tại trong gói; tra source effective, không đưa lời ví dụ thành answer thật |
| Tuyên bố 50–60%, 100%, không bao giờ | Loại khỏi acceptance | Thay metric/denominator/setup/budget và evidence thật |
| Các câu hỏi mời hợp nhất và đoạn tóm tắt lặp | Lưu archive, không normative | Yêu cầu đã được hợp nhất vào docs v3, tránh nhiều nguồn cùng thẩm quyền |

Chi tiết chuẩn nằm ở [NLU](05_NLU_AND_CONTEXT.md), [location](06_LOCATION_AND_KNOWLEDGE.md), [response](07_RESPONSE_AND_DELIVERY.md) và [acceptance](08_TEST_FACTORY_AND_ACCEPTANCE.md).

## 4. Các bổ sung phát sinh từ mục tiêu rewrite

| ID | Khoảng trống cần lấp | Tài liệu |
|---|---|---|
| ADD-01 | ASR text-to-text scope, trusted input/control và typed result | [Contract](01_CORE_CONTRACT.md) |
| ADD-02 | Session/request/draft/turn/operation identity xuyên reconnect | [State](02_CORE_STATE_MACHINE.md), [transaction](03_CORE_TRANSACTION_PROTOCOL.md) |
| ADD-03 | Generated/committed/presented, overlap timing và immutable admission binding | [Delivery](07_RESPONSE_AND_DELIVERY.md) |
| ADD-04 | Whole-turn authorization, question pinning, target-specific dependencies | [NLU](05_NLU_AND_CONTEXT.md), [state](02_CORE_STATE_MACHINE.md) |
| ADD-05 | Cancel/commit linearization, durable owner generation, operator takeover | [Transaction](03_CORE_TRANSACTION_PROTOCOL.md) |
| ADD-06 | Atomic state/effect/response store, crash recovery, external UNKNOWN | [Transaction](03_CORE_TRANSACTION_PROTOCOL.md), [SQL ví dụ](../examples/storage-target.sql) |
| ADD-07 | Business policy registry/conservative gates và post-booking lifecycle | [Policy](04_CORE_POLICY_MATRIX.md), [registry](../decisions/OPEN_DECISIONS.md) |
| ADD-08 | L4 event timelines, race/crash/negative contract tests | [Acceptance](08_TEST_FACTORY_AND_ACCEPTANCE.md) |
| ADD-09 | Deadline cascade, config pinning, privacy/redaction, observability | [Ops](11_OPERATIONS_PRIVACY_OBSERVABILITY.md) |
| ADD-10 | Compatibility facade, engine pin/drain, shadow no effects, rollback | [Migration](09_MIGRATION_AND_CUTOVER.md) |
| ADD-11 | Existing baseline failures/dirty state và current implementation mapping | [Baseline](13_REPO_BASELINE.md) |
| ADD-12 | Phụ thuộc công việc, review gates và Definition of Ready/Done | [Backlog](10_IMPLEMENTATION_BACKLOG.md) |

## 5. Những gì không được suy từ gói

Không suy đã được doanh nghiệp phê duyệt, đã kiểm đủ docs upstream, đã có API keys/GPU/tariff, đã chạy core mới, đã đo audio/live, đã migrate/deploy hoặc branch protection đã required. Checksum/heading coverage chỉ kiểm tính toàn vẹn/độ phủ cấu trúc. Acceptance là kế hoạch kiểm chứng, không là kết quả đã đạt.
