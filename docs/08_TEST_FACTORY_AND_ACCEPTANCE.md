# 08 — Test Factory, oracle và nghiệm thu lõi mới

Phiên bản thiết kế 3.0 • 19/10/2026 • **Đặc tả kiểm thử, chưa có kết quả của engine mới**.

Hợp nhất `PLAN.md` §§14–15, 18–19, phụ lục A/B và mutators M1–M5 của BONUS; bổ sung timeline L4, oracle có mức thông tin, delivery/commit races và cutover. Bằng chứng lịch sử repo chỉ dùng đối chiếu, không được đổi tên thành kết quả mới. [Baseline repo](13_REPO_BASELINE.md) ghi phạm vi và mốc dữ liệu.

## 1. Bốn lớp kiểm thử và ba profile

| Lớp | Đối tượng | Điều chứng minh |
|---|---|---|
| L1 seed | Phát ngôn, provenance, context dependency, mutation lineage | Tài nguyên tạo case; **không phải** một intent gold cố định |
| L2 contextual turn | Một lượt trong state/question/focus đã xác định | Hiểu, slot delta, next decision và các điều cấm |
| L3 conversation | Chuỗi lượt và tool results có thể đi tới thật | Duy trì context, sửa/hủy/resume, booking/knowledge/recall |
| L4 event timeline | User/control events, delivery, fault, concurrency và restart | Thứ tự commit, fencing, retry và phục hồi đúng trong cuộc gọi |

`fixture`: proposal NLU và tool fixtures kiểm soát, không chứng minh model hiểu tiếng Việt. `sandbox`: NLU thật, effect mô phỏng, DB cô lập; provider khác live chỉ khi bật tường minh và có budget. `connected`: adapter/provider hiện hữu với intake booking nội bộ, không tự bật dispatch doanh nghiệp. Không âm thầm thay profile khi thiếu key hoặc provider lỗi.

Test factory dự kiến mở rộng hạ tầng `src/testing/robustness/` hoặc xây adapter trên cùng corpus; không buộc giữ nguyên graph/test implementation cũ. Mục tiêu là giữ case nghiệp vụ và bằng chứng đúng, không tạo runner thứ hai chỉ đổi tên.

## 2. Dữ liệu kèm bộ tài liệu

- [64 seed nguồn](../data/original-64.jsonl): trích đúng cột phát ngôn phụ lục A của `PLAN.md`, giữ chữ thường, dấu, lỗi và câu lặp. Đây là văn bản có trong tài liệu nguồn do người dùng cung cấp; không xác nhận chúng do người dùng tự viết hay là transcript khách hàng. Nhãn gợi ý trong PLAN không được coi là gold.
- [Scenario schema](../schemas/scenario.schema.json): JSON Schema 2020-12 cho đặc tả case độc lập engine.
- [Các scenario tổng hợp](../examples/scenarios.jsonl): case được biên soạn để review thiết kế; fixture IDs và địa chỉ đường X/Y là tổng hợp, không phải dữ liệu map thật. Không có kết quả thực thi engine kèm chúng.

Mỗi case phải có ID, nguồn/phiên bản, precondition, context, sự kiện và assertion. Dataset được đóng băng bằng checksum; sửa oracle có lý do và review riêng, không sửa cùng prompt để làm điểm xanh. Một case mới có `review.status=design_review_only` chưa phải gold do người đánh giá nghiệp vụ độc lập duyệt.

64 seed có phụ thuộc context khác nhau. “việt yên” có thể là trả lời origin, destination hoặc chủ đề hỏi; “nói lại xem nào” lặp ở #24/#39 phải giữ cả hai ID; seed #2 không được ép thành hủy chắc chắn. Sao chép 64 text ra 100.000 biến thể không biến chúng thành 100.000 tình huống gốc độc lập.

## 3. Contract quan sát độc lập engine

Runner mới chuyển engine outputs và DB audit về `Observation` ổn định. Assertions dùng JSON Pointer bắt đầu `/`; thiếu path là FAIL, kể cả `falsy/unchanged`. Không buộc test biết node graph, class reducer hay vị trí checkpoint. Mapping được version hóa và kiểm bằng các thử nghiệm contract độc lập.

| Nhánh Observation | Nội dung |
|---|---|
| `/result` | status, state_version, response_id hoặc null, error code |
| `/booking` | status, booking_revision, origin/destination components và evidence, xe/số người/giờ |
| `/dialogue` | next_question.kind/target, presented eligibility, focus, preferences |
| `/operations` | local_booking_count, submit_attempts, cancel_attempts, support_tasks, outcome |
| `/response` | text, question_count, claims chuẩn hóa, source_ids, delivered text/IDs |
| `/delivery` | question_eligible, active response/playback IDs, accepted/rejected ACK |
| `/audit` | accepted_turn_ids, committed_turn_ids, replay_count, ownership_generation, stale_writes |
| `/tools` | provider calls, deadlines, stale_results_applied, source/version của evidence |

`response.claims` được xác định từ renderer facts/metadata và kiểm văn bản kèm theo, không chỉ tin một cờ “safe” do engine trả. Claims tối thiểu: success kind (`request_recorded/dispatch_confirmed`), asserted fare, asserted exact location, operator acceptance. Đối chiếu với rows/operation outcomes từ DB riêng; engine tự nói đã commit chưa phải bằng chứng commit.

`/booking` luôn lấy read model có thẩm quyền mới nhất sau event; `/result` là kết quả của lượt được quan sát. Khi replay một lượt cũ sau các lượt mới, result/response giữ version của outcome đã lưu nhưng `/booking` không được quay về bản cũ. Một event interrupt/delivery không tự thay result của user turn cuối; race case lấy kết quả của lượt được phát async sau khi barrier đã release và join.

Toán tử scenario: `eq`, `ne`, `in`, `contains`, `not_contains`, `unchanged`, `exists`, `truthy`, `falsy`, `gte`, `lte`. `unchanged` so với checkpoint ngay trước event của assertion; `at=final` so initial snapshot trừ khi chỉ rõ `baseline_event`. Assertion có reason nghiệp vụ. `contains` với array so phần tử, với string so substring; không thay bằng fuzzy chung. Text tự nhiên không bắt giống nguyên văn, riêng recall exact phải khớp text/event đã trình bày.

Trong fixtures, đề xuất NLU chuẩn có thể được cấp theo `event_id` để kiểm reducer/transaction. Chạy sandbox thay bằng model thật; không lấy proposal fixture làm đầu ra “model đã hiểu”. `initial` là target-state setup của adapter test, không migration checkpoint sản xuất. Mọi named fixture phải có nội dung trong case hoặc bundle version có checksum.

Fixture `nlu_proposals` là kế hoạch ngữ nghĩa **đã qua validation** để cô lập domain; không phải raw JSON response từ SDK. Adapter triển khai phải chuyển chúng thành schema typed thực, cùng references/source hợp lệ hoặc cấp qua seam sau validator. Bộ test validator riêng cung cấp SDK mock cố tình sai schema/span/source để kiểm đường thất bại; sandbox luôn chạy validator đầy đủ. Alias như `turn_u1`, `q1`, `r1` là ký hiệu tổng hợp trong đặc tả scenario, harness ánh xạ tất định sang ID hợp lệ của contract; không đưa trực tiếp chúng vào API production.

### 3.1 Payload timeline trong ví dụ

| Event/hint của harness | Cách thực thi bắt buộc |
|---|---|
| `user_turn.payload.await_result=false` | Bắt đầu lượt async, giữ handle; join khi barrier release hoặc kết thúc scenario |
| `barrier` arm/await/release | Gắn hook có tên vào điểm pipeline; await chứng minh đã tới; không tới là BLOCKED/ERROR |
| `fault` target/error/bounded | Fault adapter một lần hoặc số lần xác định, không tác động DB/ổ đĩa ngoài sandbox |
| `restart.point` | Fault hook đúng điểm đó, đóng worker/connection, mở lại từ SQLite trên disk; không chỉ đặt lại object |
| `delivery` | Harness tạo trusted control event theo schema thật, pin response/playback và timing; không gửi vào NLU |
| `trusted_input_timing` | Hint setup của harness, ánh xạ vào `TurnInput.trusted.input_timing`; không là field khách công khai được tự cấp |
| `initial` có question eligible | Materialize question/response/delivery evidence hợp lệ trong DB test; không chỉ tiêm boolean bỏ qua guard |

Mọi null component trong Observation phải được materialize thành null thay vì vắng path, để assertion số nhà/ngõ bị loại có nghĩa thống nhất. Test semantic proposal không chứng minh normalizer/NLU đã tạo đúng proposal; các ca M1/M2 có thể chạy lại sandbox bằng cùng text và oracle khi adapter đã sẵn sàng.

Observation không phải `TurnResult` nguyên trạng. Nếu contract trả `response=null` khi lỗi chưa commit, normalized `/response` vẫn có `text=null` (hoặc error template đã được adapter duyệt), `question_count=0`, `source_ids=[]` và claims boolean false; đây là biểu diễn **không có claim**, không phải một response nghiệp vụ mới. Luôn giữ `/result/response_id=null` và đối chiếu durable store để tránh adapter vô tình phát câu thành công đã chuẩn bị nhưng chưa commit.

## 4. Oracle dựa thông tin hệ thống nhận được

| `information` | Định nghĩa | Kỳ vọng được phép |
|---|---|---|
| `clear` | Với context và metadata đã pin, cách hiểu đủ rõ | Expected value/action cụ thể; chỉ bảo toàn nghĩa khi mutation thật sự giữ nghĩa |
| `ambiguous` | Từ hai cách hiểu hợp lý còn sống | Hỏi phân biệt/giữ state/không giao dịch; không bắt đoán intent ẩn |
| `irrecoverable` | Thông tin phân biệt đã mất, không còn trong text/context/metadata | Không bịa khôi phục; giữ các invariant xác nhận/giao dịch; có thể cần input mới |

`information` gắn từng user event, không chỉ toàn dataset. Hidden semantic plan của generator là nhãn nghiên cứu, không là dữ liệu SUT đã nhìn thấy. Ví dụ “không đặt nữa” bị mất `không` thành “đặt nữa” vẫn hợp nghĩa: không thể bắt SUT biết chắc khách muốn hủy. Có thể kiểm rằng lời này không vượt qua xác nhận chuyến còn thiếu, nhưng nếu context đã cho phép một ý định mới rõ ràng thì oracle phải ghi đúng khả năng quan sát và quyết định policy; không dựng bài toán bất khả thi.

Oracle có ba lớp độc lập: exact deterministic (slots/IDs/counters/version), invariant/metamorphic (query không đổi booking, retry không tạo đôi), review-based (tự nhiên/grounding khó). LLM judge chỉ ghi nhận xét phụ; không xóa FAIL an toàn hoặc quyết định gold một mình. Reference reducer test phải là bảng quy tắc/spec đơn giản do người review đối chiếu, không import reducer SUT để tự chấm chính nó.

## 5. Mutators hợp nhất M1–M5

| Mutator | Phép biến đổi và precondition | Oracle sau chỉnh sửa |
|---|---|---|
| `M1_DIALECT_COLLOQUIAL` | Từ đệm/phương ngữ/số đọc có quy tắc; role rõ | Bảo toàn nghĩa **chỉ khi** equivalence được review. “ngõ↔kiệt↔xuyệt” không được blanket coi tương đương |
| `M2_PHONETIC_CONFUSION` | Đổi âm gần trên tên/lệnh/số, có catalog và context | Recovery candidate hoặc clarification tùy ambiguity; không bắt mọi lỗi được tự khôi phục |
| `M3_WORD_DROP_TRUNCATION` | Mất từ/phủ định/đầu-cuối; lưu mask đã mất | Tính lại `information`; không yêu cầu đoán dữ liệu ẩn; kiểm confirmation/fencing |
| `M4_BACKGROUND_SIDETALK` | Chèn lời ngoài luồng có dấu hiệu hoặc metadata | Giữ tác vụ có nguồn; nếu nhiễu có phủ định/sửa ý khó tách thì ambiguous, không xóa mạnh |
| `M5_SPLIT_TURN_VAD` | Chia một địa chỉ thành các lượt có quan hệ bổ sung; hoặc ASR segments cùng lượt | Nếu chia lượt: merge component, không mất số/nguồn. Nếu segments: adapter gom đúng; interim không ghi booking |

Các phép bổ sung của PLAN tiếp tục có: `ADD_FILLER`, `PARAPHRASE`, `SYNONYM_POI_ALIAS`, `REPLACE_ENTITY`, `APPEND_SLOT`, `CORRECT_PREVIOUS_VALUE`, `ADD_NEGATION`, `CHANGE_REFERENCE`, `INSERT_QUESTION`, `INSERT_PUSHBACK`, `REORDER_INDEPENDENT`, `CONTEXT_SWAP`, `INJECT_TOOL_FAILURE`. Mỗi phép khai báo giữ/đổi/mất nghĩa; cập nhật semantic plan và oracle tương ứng. Không đảo confirm/edit hoặc câu hỏi/sửa ý như “independent” nếu có dependency thời gian.

Mutation lưu parent case IDs, generator/version, RNG seed, parameters, before/after semantic plan, thông tin còn quan sát được, validation/review. Tạo lỗi số nhà có chủ đích được phép; validator chỉ cấm đổi số **ngoài ý định** trong phép phải giữ nghĩa. Review tập trung cả ca giữ và mất nghĩa, không chỉ lựa chọn biến thể dễ.

## 6. Sinh dữ liệu, split và chống rò rỉ

1. Chọn semantic plan và context có thể đi tới, gồm policy/version và tool evidence cần thiết.
2. Kiểm operation composition trên bảng luật độc lập, đặc biệt inquiry/edit/confirm/cancel và role references.
3. Hiện thực câu tiếng Việt bằng quy tắc hoặc model; giữ original và lineage.
4. Kiểm span/số/phủ định/địa chỉ; tính lại ambiguity khi câu chữ làm đổi nghĩa.
5. Kiểm prelude bằng assertions, không chỉ giả định đã tới pending desired.
6. Dedup exact/normalized/event/semantic signatures, giữ các case text giống nhưng context khác rõ ràng.
7. Tách train/dev/gold **theo root family và thực thể/alias family khi cần**, không chia ngẫu nhiên các paraphrase cùng seed vào cả train và test.
8. Review mẫu phân tầng và toàn bộ ca P0; freeze version/checksum trước benchmark.

Gold độc lập không chỉ lấy các scenario ví dụ trong tài liệu này. Quy mô lập kế hoạch giữ tinh thần PLAN: 150–250 seeds đa dạng, 300–600 L2, 200–400 L3, 2.000–5.000 biến thể có lineage và 300–500 gold độc lập; bổ sung tối thiểu mỗi lịch race quan trọng ở L4. Đây là mục tiêu thu thập, chưa là dữ liệu đã có và chưa thay thế gate chất lượng.

## 7. L4: lịch sự kiện và fault injection

Race tests dùng barrier/latch hoặc clock điều khiển; không dùng sleep suy đoán thứ tự. Phải kiểm đã tới barrier mong muốn; không tới thì BLOCKED/ERROR, không PASS.

| Lịch phải kiểm | Assertions độc lập |
|---|---|
| Cancel/interrupt thắng trước commit | Không rows/authoritative response từ lượt cũ; stale write=0 |
| Commit thắng rồi interrupt | Một booking giữ nguyên; không “hủy” bằng rollback; thông báo/reconcile đúng |
| Hai lượt cùng state_version | Một commit được chấp nhận; lượt còn stale/retry phù hợp, không overwrite |
| Callback TTS của playback cũ | Không kích hoạt question hiện hành; ACK cũ bị từ chối |
| Response tạo nhưng chưa delivered, khách “vâng” | Không submit từ confirmation chưa đủ delivery |
| Khách nói “ừ” khi câu hỏi chưa phát xong, ASR final tới sau ACK | Eligibility theo input timing/context gốc; không hợp thức hóa bằng thời điểm final/retry |
| Request trùng cùng ID/hash | Một outcome/booking; replay đúng response đã lưu |
| Cùng ID khác hash | `INPUT_CONFLICT`, không side effect |
| Provider/map trả sau deadline/đổi location | Stale result không áp dụng |
| Operator takeover giữa NLU và commit | Fencing owner cũ, không output hoặc booking từ quyền cũ |
| Worker cũ quay lại sau reconnect | Owner generation cũ không gia hạn quyền ghi |
| Crash sau commit trước HTTP/TTS | Retry đọc durable outcome, không submit lần hai |
| Crash sau chuẩn bị external operation | Cùng operation key khi reconcile; UNKNOWN không blind submit mới |
| ASR interim, duplicate final, late final | Interim không vào core; dedup bằng source identity; câu lặp hợp lệ vẫn được giữ |
| Bốn phiên đồng thời | State/history/DB ownership và outputs không lẫn nhau |

Restart test dùng SQLite trên disk riêng, đóng/mở process/connection thật, không chỉ khởi tạo object mới trên cùng RAM. Kiểm lock/disk-full/commit-failure bằng fault adapter có giới hạn; không làm đầy ổ thật. Test dispatch tương lai chỉ dùng backend giả có idempotency/reconcile contract, không gọi hãng.

## 8. Trình tự runner và bằng chứng

Mỗi run pin suite hash, git revision/worktree status, engine, profile, policy/catalog/tariff/prompt/model/adapter versions, giờ/timezone, RNG seed, budget và concurrency. Env offline phải được đặt **trước import**: `LLM_MODE=mock`, `MAP_MODE=mock`, `RAG_ENABLED=false`, `PERSISTENT_DB_PATH` riêng dưới `.tmp/` và `ADMISSION_DB_PATH` riêng nếu adapter dùng admission. Không đưa `.env` vào manifest.

Runner setup isolated store/clock/fixtures → chạy prelude có assertion → phát timeline → thu observation và audit DB → kiểm từng assertion cùng invariant chung → finalize → lưu evidence. Network transport bị chặn trong fixture; một request live ngoài dự định là ERROR. Không dùng cùng cache singleton/provider state giữa các ca mà không reset có kiểm chứng.

Mỗi case lưu: input tổng hợp và event IDs, before/after observation, state diff, tool requests đã redact, source versions, assertion actual/expected, timing, barrier trace, operation rows và reproduction parameters. Report cần JSONL máy đọc, summary JSON, JUnit và Markdown/HTML dễ review. Trace raw text chỉ cho synthetic/protected artifacts; không đưa transcript khách thật hay secret vào gói này.

Trạng thái: PASS = mọi assertion đã thực thi đạt; FAIL = lệch nghiệp vụ/invariant; ERROR = setup/fixture/tool harness sai; BLOCKED = chưa tới điều kiện cần hoặc provider/budget cản; NOT_RUN = chưa thực thi. Mẫu số gồm từng loại; không gộp BLOCKED thành PASS hoặc loại ca khó khỏi denominator. Exit 0 chỉ khi không FAIL/ERROR/BLOCKED/NOT_RUN theo suite bắt buộc; exit 1 có FAIL/ERROR; exit 2 còn blocked/not_run và không có fail/error.

Model thật chạy k lần nếu cần đo reliability: lưu mọi lần, không retry lấy kết quả tốt nhất. Retry provider theo cấu hình runtime khác với chạy lại benchmark. Metrics latency chỉ lấy mẫu đã thực thi, báo failure/timeout riêng; không gọi thời gian core là thời gian tới audio.

## 9. Các metric và cách tính

| Metric | Mẫu số và lưu ý |
|---|---|
| Act/slot exact match | Events clear có gold; tách raw/normalized, partial/F1 chỉ là phụ |
| Query mutation count | Tất cả lượt thuần inquiry; báo số vi phạm tuyệt đối |
| Wrong submit/cancel, duplicate booking | Mọi case P0 và audit DB, báo count tuyệt đối |
| Geo top-1/top-3 | Case có gold entity và dữ liệu phủ; tách ambiguous/coverage-gap |
| False auto-accept, wrong number/parent/branch | Mọi quyết định đủ điều kiện tương ứng, không chỉ case thành công |
| Grounded claims | Claims với nguồn/hiệu lực/điều kiện; claims bịa là P0/P1 theo tác hại |
| Recall exactness | Đúng event/text được trình bày hoặc user turn trước; không chấm chỉ ý gần giống |
| Clarification no-progress | Vấn đề bị hỏi lại cùng loại dù không có thông tin mới vượt budget |
| Task completion | Hoàn tất hợp lệ hoặc hỗ trợ trung thực theo policy; không tính handoff giả là xong |
| Latency/cost | p50/p95 theo profile, concurrency, success/failure; HTTP attempts/model calls/tokens tách nhau |

## 10. Gate nghiệm thu đề xuất và bằng chứng bắt buộc

Các ngưỡng dưới là **tiêu chí thiết kế đề xuất**, không kết quả đã đo, không chữ ký phê duyệt. Gold phải được khóa và chủ nghiệp vụ duyệt trước run release. Không dùng một điểm trung bình bù lỗi an toàn.

| Gate | Điều kiện đạt khách quan | Nếu chưa có bằng chứng |
|---|---|---|
| G0 — tài liệu/dataset | Mọi schema/example parse; ID/ref/link đúng; 64 seed text khớp nguồn; không placeholder/secret | Chưa cho bắt đầu benchmark chính thức |
| G1 — contract/domain fixture | 100% case bắt buộc L2/L3 và invariant P0 thực thi đạt; không ERROR/BLOCKED; source/reference validator đầy đủ | Chặn tích hợp engine mới vào adapter production |
| G2 — giao dịch/L4 | Mọi lịch race ở §7 chạy cả hai thứ tự liên quan; 0 wrong/stale/duplicate commit; crash/retry on-disk đạt | Chặn cohort mới |
| G3 — provider sandbox | Gold độc lập ≥300 ca, ≥3 run/prompt candidate; P0 tuyệt đối 0; clear act+slot exact ≥95%; report theo slice và mọi lỗi | Chưa kết luận model phù hợp; tiếp tục fixture và sửa prompt/data |
| G4 — địa chỉ/FAQ | Trong gold đã duyệt: 0 wrong number/branch được auto-accept, 0 claim fare/policy không nguồn; ≥95% câu clear chọn action đúng; geographic scope công bố khớp dataset | Khóa tính năng ngoài scope hoặc chưa đủ nguồn |
| G5 — adapter voice/Web | Delivery/interrupt/reconnect/ownership/admission compatibility đạt; đo audio thật, không dùng fixture làm bằng chứng ASR/TTS | Chặn voice cohort, có thể tiếp tục CLI sandbox |
| G6 — tải và ngân sách | Chạy workload đã pin ≥4 phiên đồng thời; 0 state leak; measured p95 dưới budget đã duyệt POL-10; báo mẫu/timeout/chi phí | Không tự nhận mốc 8s/12s cũ là SLA mới |
| G7 — cutover | Shadow isolated/no effects; policy approvals cho tính năng bật; canary/rollback drill và checkpoint compatibility có evidence | Giữ engine cũ cho khách thật |

Ngưỡng 95% là mức xuất phát cần chủ sản phẩm xác nhận, có thể siết theo slice; không được hạ sau khi nhìn kết quả mà không đổi phiên bản tiêu chí và ghi lý do. Nếu gold chưa đạt 300, báo đánh giá thăm dò với mẫu nhỏ; G3 chưa đạt. Chưa có gold review, provider live, audio hoặc load run cho lõi mới trong gói tài liệu này.

P0 gồm: sai đặt/hủy, duplicate/stale commit, query mutate chuyến, báo thành công trước commit, mock-as-real/dispatch claim sai, xác nhận sai binding, bịa địa điểm/giá gây giao dịch, data leak. P1 gồm hiểu/context/địa chỉ/FAQ sai chưa gây P0; P2 gồm văn phong/nhịp. Một fail P0 kể cả đã có baseline vẫn chặn gate safety.

## 11. Regression, replay và bàn giao

Chạy so sánh engine cũ/mới trên cùng semantic contract, giữ khác biệt policy được duyệt tường minh. Case cũ lỗi không tự biến thành hành vi chuẩn; oracle lấy từ yêu cầu nghiệp vụ và thông tin quan sát. Mọi điều chỉnh oracle có changelog/reviewer, giữ kết quả trước.

Replay offline dùng fixtures/cassette khớp fingerprint và thứ tự; request khác cassette là ERROR, không lấy response câu khác. Replay không gọi provider thật trừ run mới được bật với budget. Minimize giữ failure fingerprint và tái kiểm bằng runner, không “rút gọn” mất điều kiện gây race.

Bàn giao implementation sau này phải kèm lệnh đã chạy, env không secret, số PASS/FAIL/ERROR/BLOCKED/NOT_RUN, scope chưa chạy và lý do. Coverage matrix đánh dấu prelude thực sự đạt; các trạng thái booking, utterance, context, location, FAQ, estimate, recall và critical ops phải có slice. [Migration/cutover](09_MIGRATION_AND_CUTOVER.md) dùng evidence này, không chỉ ảnh chụp một hội thoại đẹp.
