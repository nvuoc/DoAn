# 03 — Giao thức giao dịch, chống lặp và phục hồi

Trạng thái: đặc tả đích đề xuất v3.0, ngày 19/10/2026 (UTC+7). Chưa triển khai vào ParrotGo. Tài liệu này thay phần giao dịch còn chưa rõ trong PLAN §8.4, §17.2 và mở rộng cho ngắt lời, operator, gọi lại. [Contract](01_CORE_CONTRACT.md), [state machine](02_CORE_STATE_MACHINE.md), [delivery](07_RESPONSE_AND_DELIVERY.md) và [chuyển lõi](09_MIGRATION_AND_CUTOVER.md) phải được thực hiện cùng nhau.

## 1. Quyền sở hữu và nguồn sự thật

SQLite domain store là nguồn sự thật về request, lượt đã commit, phiên bản, booking, task và phản hồi đã chốt. Graph chỉ điều phối việc chuẩn bị và giữ snapshot dẫn xuất; không tự persist booking, không được là nơi duy nhất giữ kết quả. Một transaction không được kéo dài qua NLU, map, FAQ, TTS, Redis hoặc dispatch HTTP.

Trong giai đoạn tương thích, booking/task/outbox hiện có được ghi qua cùng SQLite connection và cùng transaction với trạng thái lõi mới. Không được gọi một hàm DAL tự mở connection rồi coi đó là atomic với transaction bên ngoài. Admission vẫn ở store dùng chung Web/voice hiện hữu; không đặt admission counter vào lõi hoặc giả định có transaction xuyên hai file DB.

Định danh dùng thống nhất:

| Trường | Ý nghĩa và thời hạn |
|---|---|
| `session_id` | Một vòng đời kết nối/hội thoại; thay đổi khi gọi lại |
| `request_id` | Yêu cầu nghiệp vụ bền vững, có thể tiếp tục ở session khác |
| `draft_id` | Bản nháp thuộc request; không phải ID cuộc gọi |
| `turn_id` | UUID ổn định của nguyên lượt đã admission; gửi lại phải dùng lại |
| `input_id` | ID sự kiện adapter, duy nhất trong request; dùng chung quy tắc chống lặp cho user/control event |
| `operation_id` | Một thao tác có side effect bền vững |
| `response_id` | Một phản hồi bất biến đã được lưu |
| `question_id` | Quyết định đang được hỏi, gắn với target và phiên bản |
| `playback_id` | Một lần phát/presentation của một phản hồi |
| `owner_generation` | Fence bền vững; tiếp quản/resume hợp lệ tăng generation |
| `state_version` | CAS của aggregate; mọi thay đổi authoritative được tuần tự hóa |
| `booking_revision` | Phiên bản ngữ nghĩa chuyến; khác phiên bản kỹ thuật aggregate |
| `turn_epoch` | Fence cục bộ để hủy nhanh executor; không dùng thay durable ownership/cancellation |

Không lấy số điện thoại, địa chỉ hoặc text giống nhau làm khóa giao dịch. Hai câu “đúng rồi” có ID khác nhau có thể là hai lượt hợp lệ.

## 2. Bất biến giao dịch

1. Một `turn_id` chỉ có một kết quả nghiệp vụ cuối được commit. Cùng identity và cùng hash trả kết quả đã lưu; khác hash trả `INPUT_CONFLICT`, không thực thi lại.
2. Thành công local chỉ được công bố khi booking, task cần có, response và request state đã commit. “Đã ghi nhận yêu cầu” khác “đã có xe/tài xế nhận”.
3. Snapshot bị thay thế, hết deadline, hủy hoặc mất ownership không được sửa domain store. Provider trả muộn không khôi phục quyền ghi.
4. Xử lý toàn bộ acts và dependencies trước khi tạo side effect. “Đúng rồi nhưng đổi xe 7 chỗ” không đặt bản 4 chỗ rồi mới sửa.
5. Commit thắng trước interrupt giữ nguyên nghiệp vụ đã commit. Không tự hủy booking vì TTS bị ngắt.
6. Cùng request tiếp tục qua session khác giữ `operation_id` và idempotency key của thao tác chưa rõ kết quả. Không đưa `session_id` vào khóa nghiệp vụ.
7. Mất response transport không phải thất bại của transaction. Đọc lại kết quả trước khi quyết định retry.
8. Outbox vận chuyển thông báo ít nhất một lần; consumer phải chống lặp. Không tuyên bố exactly-once cho dịch vụ ngoài không có contract hỗ trợ.
9. Trạng thái graph sau lỗi cập nhật phải nạp lại từ domain store; không dùng graph cũ ghi đè SQLite.
10. Lời hứa handoff/task cũng là claim nghiệp vụ: phải có tiếp nhận bền vững và policy khả dụng, không chỉ có câu template.

## 3. Admission và chống lặp đầu vào

Adapter xác thực quyền truy cập trước khi gọi lõi. Core kiểm tra request/session association và ownership từ envelope tin cậy; text người dùng không được tạo `ownership_changed` hay delivery ACK.

Canonical input hash chỉ bao gồm immutable business/source payload theo contract: nguyên văn, nguồn và các source identity có thật. Binding quyết định được lưu bất biến riêng tại lần admission đầu, không nằm trong hash do client retry tính lại. Các trường do server tạo có thể thay giữa retries như CAS expectation, deadline, thời điểm nhận lại hoặc metadata transport không làm thành lượt mới. Không chụp lại delivery binding mạnh hơn cho cùng input sau khi ACK tới muộn.

Admission có thể là transaction ngắn riêng: ghi `input_id`, hash, `turn_id`, snapshot version, ownership, thời hạn UTC và trạng thái `admitted/preparing`. Đây là biên nhận xử lý, chưa phải domain commit; chưa được phát câu hỏi hoặc lời thành công. Đầu vào đã tồn tại xử lý như sau:

| Trường hợp | Hành vi |
|---|---|
| Cùng request/input/turn/hash, đã committed | Trả durable result với `status=replayed` |
| Cùng identity/hash, đang preparing, executor vẫn có lease | Join/chờ có hạn hoặc trả trạng thái retry; không tạo executor song song |
| Cùng identity/hash, executor chết | Recovery claim có fence mới, đọc trạng thái trước khi tính lại |
| Cùng identity, payload khác | `rejected` với mã `INPUT_CONFLICT`; không sửa bản cũ |
| `turn_id` gắn request hoặc input khác | `INPUT_CONFLICT`, kể cả text giống nhau |
| Text giống nhau, identity khác | Xử lý như lượt mới; guard revision/delivery vẫn áp dụng |
| Không có stable source ID | Không tuyên bố đã chống được duplicate do ASR; adapter cần ghi rõ giới hạn |

Result replay giữ `state_version` của lần commit gốc, thêm `observed_state_version` hiện tại. Nếu result đã bị thay thế bởi các thay đổi mới, `delivery.allowed=false`; chỉ dùng để trả biên nhận, không autoplay lời cũ hoặc kích hoạt lại câu hỏi.

## 4. Chuẩn bị trên snapshot bất biến

Coordinator đọc aggregate cùng `state_version=n`, generation `g`, draft revision `r`, question/delivery binding đủ điều kiện và policy bundle đã pin. NLU và read-only tools chỉ nhận snapshot riêng. Prepared result gồm:

- Snapshot identity/version/fence và source turn.
- Proposal đã kiểm schema, references và semantic conflicts của toàn lượt.
- Delta domain; invalidation của location/question/estimate.
- Read-set nghiệp vụ cần kiểm lại khi commit: revision, policy, question eligibility, contact, vùng phục vụ, ownership.
- Operation intent hoặc local booking intent; canonical payload và hash.
- Exact response text/segments đã render từ dữ liệu có bằng chứng.
- Deadline còn lại và timestamps phục vụ chẩn đoán; không có quyền ghi ẩn trong object.

Side effect không được chạy trong graph preparation. In-memory graph runner phải tắt persistence hoặc dùng interface chỉ đọc. Retry NLU vẫn thuộc cùng turn, không tạo operation mới. Lỗi provider live giữ loại lỗi thật; không chuyển sang parser mock.

## 5. Thuật toán commit local có thẩm quyền

Pseudocode sau mô tả giao thức cần lập trình và kiểm thử, chưa phải API hiện có:

```text
prepare(snapshot) -> candidate
acquire per-request coordinator serialization
    reject if local turn_epoch invalidated
    BEGIN IMMEDIATE on authoritative domain connection
        load current request, admitted input and turn
        if committed same input: read original result; end without mutations
        require input hash/turn identity unchanged
        require turn.phase = preparing and no durable cancellation
        require owner_generation = g and authorized owner/session unchanged
        require state_version = n and draft/question read-set still valid
        require persisted expiry not elapsed and current monotonic deadline valid
        recheck safety prerequisites against current authoritative state
        apply CAS update: state_version n -> n+1; require affected_rows = 1
        apply domain delta, history and confirmation invalidations
        if local intake authorized:
            insert/reuse booking by durable operation identity
            create/reuse required operator task on same connection
            store booking link, truthful local outcome and operation result
        append outbox invalidation events, containing references/version only
        insert immutable response and its question binding, not delivery eligibility
        set turn committed and store exact durable result
    COMMIT
release serialization
return durable result; only now may adapter present response
```

Mọi lỗi trước `COMMIT` rollback toàn bộ domain delta. Input admission có thể còn để retry/recovery; không được biến nó thành bằng chứng đã nhận booking. Kiểm tra guard và các writes phải nằm trong một write transaction, không đọc guard ở connection A rồi ghi ở B.

Transaction timeout/busy là lỗi hạ tầng; nếu chắc chắn rollback trả `retryable_error` với `response=null`. Adapter có thể phát mẫu lỗi tĩnh được phê duyệt, không tạo câu hỏi confirmation hoặc thông báo đã lưu. Nếu kết quả commit chưa xác định được do mất process/connection, đọc lại `turn_id`/operation trên connection mới trước khi quyết định kết quả. Nếu storage vẫn không đọc được thì giữ kết quả chưa biết cho điều tra, không nói “chưa đặt” hoặc “đã đặt” như sự thật.

## 6. Interrupt, timeout và takeover phải có điểm phân xử

Nhận sự kiện interrupt và xác nhận “đã hủy” là hai mốc khác nhau. Adapter có thể dừng TTS ngay; việc mất quyền commit cần được tuần tự hóa.

- Trong process: tăng `turn_epoch` dưới coordinator; executor cũ bị vô hiệu. Coordinator dùng cùng thứ tự khóa cho invalidate/commit để không có khe kiểm tra rồi ghi.
- Durable path: transaction ngắn cập nhật turn còn `preparing` thành `cancelled`/`deadline_exceeded`, ghi control event và fence. Commit transaction phải kiểm trạng thái này. Hai transaction được SQLite phân xử; không suy từ thứ tự log mạng.
- Cross-process: owner generation và durable turn phase là thẩm quyền. Một volatile epoch không truyền được quyền sở hữu cho worker mới.
- Sau restart, tuyệt đối không phục hồi monotonic timestamp của process cũ. Dùng UTC expiry đã lưu, clock kiểm soát, rồi tạo budget monotonic mới không vượt phần còn lại.

| Cuộc đua | Bên thắng | Hành vi còn lại |
|---|---|---|
| Interrupt vs commit | Turn đã durable cancelled trước | Commit cũ bị từ chối; không booking/task/response nghiệp vụ |
| Interrupt vs commit | Domain commit trước | Giữ booking; dừng playback nếu cần; đọc kết quả để thông báo tiếp |
| Deadline vs provider result | Hết budget trước commit | Không áp dụng kết quả; late callback chỉ cập nhật metrics |
| Hai lượt cùng snapshot | Một CAS thắng | Lượt còn lại `stale`; không tự áp proposal cũ vào state mới |
| Operator claim vs AI commit | Takeover generation trước | AI bị `stale`; không phát prepared response |
| Operator claim vs AI commit | AI đã commit trước | Operator đọc revision mới; không xóa booking đã tồn tại |
| Resume vs worker cũ | Resume tăng generation trước | Worker cũ không commit hoặc ACK question mới |
| Delivery ACK cũ vs câu hỏi mới | Binding đã đổi | ACK lưu audit nếu hợp lệ nguồn; không cấp eligibility mới |
| HTTP retry vs response mất | Turn đã committed | Replay exact result, không chạy lại graph |

Turn đã bị classified/persisted/publish là `stale`, `cancelled` hoặc hết hạn là terminal; không chuẩn bị lại cùng turn trên snapshot mới và không sửa expected version để hồi sinh quyền ghi. Chỉ lỗi transient trước khi thành terminal, với snapshot/binding admission vẫn hợp lệ và còn deadline, mới có thể retry attempt nội bộ qua coordinator, không mở executor thứ hai. Nếu state/binding đã thay đổi thì trả stale không response; một lượt mới có chủ đích được đánh giá theo câu hỏi hiện hành, không biến đồng ý cũ thành xác nhận mới.

Retry transport giữ payload/session/source ban đầu theo hash contract. Sau resume ở session mới, caller đọc kết quả hoặc đối soát request bằng quyền mới, rồi tạo input/turn mới cho phát ngôn mới; không resend input cũ với session_id bị thay. Operation key vẫn theo durable request/draft/revision/kind nên cross-session recovery không tạo đơn mới.

## 7. Local intake hiện tại và dispatch tương lai

### 7.1 Profile connected hiện tại

ParrotGo ghi booking vào SQLite và giao operator; field legacy `bookings.dispatch_status=not_integrated` không phải xe đã nhận. Core đích dùng `booking_status=request_recorded`, `business_outcome.kind=request_recorded`, `business_outcome.dispatch_status=not_requested`. `not_integrated` chỉ thuộc compatibility DB legacy, không phải enum contract core mới. Adapter tương thích có thể ánh xạ legacy `booked/confirmed` để giữ HTTP/UI, đồng thời giữ rõ dispatch chưa tích hợp. Câu trả lời phải tuân [POL-01](04_CORE_POLICY_MATRIX.md).

Một local operation hoàn tất cùng transaction booking. Không cần tạo chuỗi `sending/unknown` giả cho một insert SQLite có thể đối soát bằng turn ID. Duy trì khóa duy nhất chống hai booking cho cùng draft/operation và task `new_booking` duy nhất cho booking.

Handoff/support trước khi có booking có operation và queue record riêng, không ép tạo booking giả để lấy task ID. SQL minh họa dùng `sample_support_requests` để biểu diễn đường này; compatibility thực phải ánh xạ queue/request hiện hành có quyền và cùng transaction. Handoff dùng `action_intent_id` bền vững: retry giữ ID, một yêu cầu hỗ trợ mới có chủ đích sau lần trước kết thúc có ID mới dù booking_revision chưa đổi. Unique trip-operation tuple chỉ áp cho local_intake/external trip operations; không gộp mọi handoff cùng revision thành một yêu cầu mãi mãi.

### 7.2 Dispatch bên ngoài — tính năng chưa được bật

Khi có backend thật và policy được duyệt, cần operation protocol sau, tách khỏi commit local:

```text
PREPARED -> SENDING -> SUCCEEDED
                 -> FAILED   (chắc chắn không nhận, hoặc từ chối có mã)
                 -> UNKNOWN  (timeout/mất kết nối sau lúc có thể đã nhận)
UNKNOWN -> reconcile/query -> SUCCEEDED | FAILED | vẫn UNKNOWN
PREPARED -> CANCELLED      (chưa gửi và intent bị vô hiệu)
```

1. Commit `PREPARED` với exact payload/hash, key và target revision trước khi gọi ngoài. Outbox chỉ chứa intent tham chiếu operation.
2. Worker claim operation có lease/fence, kiểm state và policy trước khi gửi. Persist `SENDING` trước network; không giữ DB lock khi gọi.
3. Dùng cùng key theo dạng versioned canonical tuple `(request_id, draft_id, booking_revision, operation_kind)`, hoặc opaque UUID được lưu một lần cho tuple đó. Không lấy session, retry count, timestamp gửi hoặc random mới mỗi lần retry làm key.
4. Lưu kết quả trả về trong transaction, liên kết external ID, cập nhật outcome và outbox. Khách chỉ được nghe claim tương ứng với kết quả có thẩm quyền.
5. Timeout không chứng minh thất bại. Chuyển `UNKNOWN`, query theo external reference/idempotency key. Chỉ retry submit cùng key khi contract provider cho phép; không tạo operation mới để né unknown.
6. Nếu provider không có idempotency hoặc status lookup đủ tin cậy, submit không được retry tự động sau ambiguous send; chuyển đối soát/operator. “Exactly once” không phải cam kết khả thi chỉ bằng SQLite.

Sửa/hủy sau khi submit đang `UNKNOWN` là yêu cầu phụ thuộc: ghi intent hỗ trợ, làm rõ trạng thái, không giả vờ đã hủy. Compensation cần thao tác riêng đã được cho phép, không rollback một booking ngoài bằng cách xóa dòng local. Core phase `submitting` chỉ biểu thị operation đang xử lý; không đồng nghĩa thành công.

## 8. Outbox, delivery và sự nhất quán quan sát

Outbox nằm cùng file/transaction với domain update; broker chỉ đánh thức consumer. Payload tối thiểu gồm event ID, request/booking reference, revision/generation và topic; không phát transcript, cookie hoặc contact ra broker.

Consumer đánh dấu đã xử lý theo event ID; publish xong nhưng chưa ghi `published_at` có thể phát lặp. Poller/reconcile vẫn dựa SQLite khi Redis lỗi. Chỉ đánh dấu hoàn thành sau consumer làm xong công việc cần ACK; “broker nhận” không phải “operator đã tiếp quản”. Outbox backlog không đảo kết quả booking đã commit.

Response rows bất biến. Delivery là sự kiện riêng theo đúng `response_id`, session, generation, `segment_id`/`playback_id`; voice cần hoàn thành phát và output-availability ACK của lần phát hiện hành. Replay hoặc resume không tái dùng eligibility đã nghe. Xem [giao thức delivery](07_RESPONSE_AND_DELIVERY.md).

## 9. Recovery theo điểm crash

| Điểm crash | Dữ liệu bền vững | Recovery được phép |
|---|---|---|
| Trước admission | Chưa có input | Adapter retry cùng ID |
| Sau admission, trước prepare xong | Input + turn preparing | Claim executor mới có fence; đọc snapshot, tính lại nếu còn deadline/quyền |
| Sau prepare, trước domain commit | Không có domain delta | Bỏ prepared object; tính lại từ store khi phù hợp |
| Trong transaction trước commit | Rollback, hoặc cần xác minh trạng thái DB | Đọc lại turn/operation; không dựa vào response đang giữ RAM |
| Sau commit, trước trả HTTP | Result/booking/task/outbox tồn tại | Replay durable result; không chèn booking lần hai |
| Sau trả text, trước playback | Response tồn tại, chưa eligible | Gửi lại theo presentation mới nếu chưa superseded |
| Sau playback, trước ACK | Chưa đủ evidence xác nhận | Hỏi lại khi cần; không suy từ generated text |
| Sau local booking, trước publish outbox | Booking + outbox pending | Publish lại; không rollback booking |
| Sau external send, trước lưu result | Operation SENDING | Chuyển unknown và reconcile theo cùng key |
| Sau operator chỉnh đơn | Booking revision/generation mới | AI cũ bị fence; resume đọc current booking hoặc chuyển hỗ trợ |

Recovery chạy có hạn, có metric và audit. Không replay toàn transcript để tự sinh lại giao dịch lịch sử. Nếu event sequence/snapshot version không khớp, cho read-only diagnostics và repair có quy trình; không tự lấy graph snapshot thắng domain store.

## 10. SQL minh họa và giới hạn

[storage-target.sql](../examples/storage-target.sql) chạy được trên SQLite trống để kiểm tra cấu trúc target, foreign keys, unique keys và rollback. Các bảng `sample_bookings`, `sample_operator_tasks`, `sample_dashboard_outbox` chỉ đóng vai các bảng hiện hữu trong mô hình atomicity; không phải tên đích bắt buộc và không phải migration production.

Trong giai đoạn coexist, `agent_requests.generation` hiện có vẫn là authority fence cho cả AI và dashboard cho đến khi tất cả writer cùng chuyển sang coordinator. Không giữ `core_requests.owner_generation` như một authority độc lập cạnh generation legacy. Migration thật phải ánh xạ/reuse một authority, dùng cùng connection và có test takeover từ cả hai engine. DDL này không thực thi CAS, policy, state schema validation, bảo vệ bí mật hoặc dispatcher; ứng dụng phải kiểm chúng.

Các cột JSON chỉ là container có `json_valid`, không chứng minh field-level contract. Timestamps persisted là UTC ISO-8601 hoặc UTC epoch theo cột; không lưu monotonic. Mọi request phải pin engine/schema/policy bundle. SQL chỉ được thử trên DB tạm/synthetic; không chạy file vào DB hiện tại.

## 11. Gate nghiệm thu bắt buộc

Bộ test tại [08](08_TEST_FACTORY_AND_ACCEPTANCE.md) phải chứng minh ít nhất:

- N request retry cùng turn tạo đúng một booking/task, kết quả replay giống bản gốc; hash conflict không mutation.
- Rollback khi chèn response/task/outbox lỗi không để booking riêng lẻ; sau retry vẫn thực hiện được.
- Các lịch interrupt/commit, takeover/commit, deadline/commit và resume/late callback đều có kết quả duy nhất hợp lệ.
- Lỗi sau commit nhưng trước HTTP/TTS trả đúng outcome khi đọc lại.
- Same request ở session mới giữ operation key; confirmation cũ không phục hồi delivery eligibility.
- External fake provider mô phỏng “đã nhận nhưng timeout”: không có submit key mới, đối soát ra đúng external ID.
- Outbox delivery trùng không tạo lại task/command; broker ngừng không mất domain commit.
- Hai request trên cùng hoặc khác session không lẫn state, ownership, operation hoặc response.

Các kiểm tra trên là yêu cầu cho implementation tương lai. Việc SQL parse thành công và tài liệu có bảng race không phải bằng chứng lõi mới đã đạt chúng.

