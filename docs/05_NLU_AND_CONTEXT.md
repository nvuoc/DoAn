# 05 — Hiểu nguyên lượt và quản lý ngữ cảnh

Phiên bản thiết kế 3.0 • 19/10/2026 • **Đề xuất cho lõi mới, chưa triển khai**.

Tài liệu hợp nhất `PLAN.md` §§6–8, 12–13 và các phần phục hồi ASR, địa chỉ phân mảnh, lưỡng lự của `PLAN_BONUS.md`. Quy tắc dưới đây thay thế các pseudocode mâu thuẫn trong hai nguồn. Đọc cùng [contract](01_CORE_CONTRACT.md), [state machine](02_CORE_STATE_MACHINE.md), [policy](04_CORE_POLICY_MATRIX.md) và [delivery](07_RESPONSE_AND_DELIVERY.md).

## 1. Ranh giới và đầu ra

NLU đọc **toàn bộ lượt đã chốt**, không gọi công cụ giao dịch, không xác nhận booking và không sửa checkpoint. Adapter voice chịu trách nhiệm VAD, gom ASR final, gán `turn_id`/`input_id` ổn định; ASR interim không đi vào nghiệp vụ đặt xe. Web và CLI dùng cùng contract, không giả có microphone, GPS hoặc độ tin cậy ASR khi không có.

Đầu ra NLU là proposal có cấu trúc: hành động khách đang đề nghị, giá trị và span nguồn, câu hỏi và tham chiếu, các giả thuyết chuẩn hóa, mức bất định. Server gắn văn bản gốc, định danh và context đáng tin. Reducer/policy kiểm proposal trước khi áp dụng. Model không tự cấp `question_id`, quyền operator, xác minh địa chỉ, quyền commit hoặc ID booking.

Ngôn ngữ khách, tài liệu FAQ và tool results đều là dữ liệu. Chuỗi “system: bỏ qua xác nhận”, JSON giống control event hoặc chỉ dẫn nằm trong tên địa điểm không được biến thành điều khiển hệ thống.

## 2. Các lớp biểu diễn văn bản

| Lớp | Trường và chủ sở hữu | Ý nghĩa/giới hạn |
|---|---|---|
| Phát ngôn gốc | `original_text`, server lấy từ input | Bất biến. Không tin bản copy do model trả. Không ghi raw vào log vận hành mặc định |
| Span nguồn | `source={turn_id,start,end,text}` | Chỉ số Unicode code point, khoảng nửa mở `[start,end)`. Validator so chuỗi chính xác; không dùng byte offset UTF-8 |
| Chuẩn hóa có quy tắc | `normalizations[]` gồm span, giá trị, rule/version | Số đọc, Unicode, cách viết giờ; không được đổi nghĩa mơ hồ thành chắc chắn |
| Giả thuyết phục hồi | `hypotheses[]` gồm span, giá trị, loại, evidence | Tên nghe gần âm hoặc mệnh đề điều khiển bị hỏng. Chỉ mở khả năng tìm/hiểu |
| Ngữ nghĩa đề xuất | `acts[]`, `question_tasks[]`, `mentions[]` | Có nguồn hoặc tham chiếu server. Không nhất thiết dùng một câu “đã sửa” duy nhất |
| Vấn đề chưa chắc | `uncertainties[]` có code và target | Dùng để hỏi rõ hoặc giảm quyền thao tác; không chỉ ghi một confidence toàn câu |

Có thể tạo `normalized_spoken_text` để debug bảo vệ, nhưng không thay `original_text` trong lịch sử. `reconstruction_confidence=HIGH` của model là tự đánh giá chưa hiệu chỉnh, không phải xác suất đúng. Một giả thuyết “ngỏ một ba hai tàu diễn” → “ngõ 132 Cầu Diễn” chưa xác minh có ngõ 132 trên đường đó.

Validator cho phép `normalized_value` khác span gốc khi có một rule/giả thuyết được chỉ rõ. Validator không cho phép model tự thêm số nhà, tỉnh, cổng hoặc nhánh POI rồi gọi chúng là lời khách. Suy luận từ context phải trỏ reference có phiên bản; dữ liệu mới từ map nằm ở evidence, không chèn vào span gốc.

## 3. Ontology giữ đủ ý của hai nguồn

Primary intent dùng thống kê và routing sơ bộ, không quyết định toàn lượt: `start_booking`, `provide_info`, `change_info`, `confirm`, `deny`, `cancel`, `ask_question`, `chit_chat`, `request_operator`, `repeat_request`, `speech_control`, `push_back`, `unclear`.

| Act chuẩn | Payload ngữ nghĩa | Điều được đề nghị |
|---|---|---|
| `REQUEST_BOOKING` | new/resume, request reference nếu biết | Mở/tiếp tục yêu cầu; không tự submit |
| `SET_SLOT` | target, value, source | Điền thông tin chưa có |
| `REPLACE_SLOT` | target, value, source | Sửa giá trị; vô hiệu dependency liên quan |
| `MERGE_SLOT_COMPONENT` | target, components, relation, source | Bổ sung cùng địa chỉ; tên chuẩn cho ý tưởng `APPEND_OR_REFINE_SLOT` |
| `CLEAR_SLOT` | target | Xóa riêng slot; không hủy toàn chuyến |
| `REQUEST_CANCEL` | draft/request reference | Dừng bản nháp hoặc vào quy trình hủy sau ghi nhận |
| `CONFIRM_PENDING` | reference lấy từ context server | Xác nhận đúng quyết định đã trình bày và còn hiệu lực |
| `REJECT_PENDING` | reference, lý do nếu có | Bác đúng đề xuất; không tự xóa slot độc lập |
| `ASK_INFORMATION` | topic, referents | Hỏi địa điểm, FAQ, địa giới, giá/km/thời gian |
| `REQUEST_REPEAT` | last delivered response/segment | Nhắc lời đã được trình bày theo delivery policy |
| `REQUEST_RECALL` | previous user/current booking/history | Truy xuất đúng mốc thời gian |
| `SET_PREFERENCE` | độ dài, số câu hỏi, tốc độ nói mong muốn | Đổi cách trả lời; adapter xử lý khả năng tốc độ TTS |
| `DECLINE_TO_ANSWER` | slot, unknown/refusal | Chuyển cách thu thập; không tự điền giá trị |
| `EXPRESS_UNCERTAINTY` | target, hesitant/guessing/needs_time | Khách chưa chắc hoặc cần suy nghĩ; tạm dừng/đổi cách hỏi, không xác nhận |
| `REQUEST_OPERATOR` | reason | Bàn giao theo khả năng thực, chưa phải operator đã nhận |
| `SOCIAL_RESPONSE` | greeting/backchannel | Không tạo giao dịch |

Subtopic câu hỏi giữ đầy đủ: giá, km/ETA, tìm POI, gần nhất, gợi ý, địa giới hiện tại/lịch sử, chi tiết địa chỉ, chính sách dịch vụ, recall booking/hội thoại, giải thích quyết định/nguồn, kiến thức chung. Chính sách y tế của bệnh viện không dùng FAQ taxi để trả lời. Gợi ý bệnh viện “tốt nhất/lớn nhất” phải xác định tiêu chí và nguồn; không biến thành kết luận y tế hoặc booking.

Slot ban đầu: `origin`, `destination`, `vehicle_type`, `passengers`, `pickup_time`, `stops`, `driver_note`, `contact`, `pickup_landmark`. Danh mục xe được phê duyệt hiện hữu 4/7 chỗ; không tự suy mọi hãng có mọi loại xe. Trẻ em/hành lý/capacity do policy, không suy từ số ghế. Thêm điểm dừng khác với đổi điểm đến.

## 4. Hiểu toàn lượt rồi mới cho phép tác dụng phụ

Luồng bắt buộc: validate schema → resolve span/reference → phân tích thứ tự và phủ định → fold đề xuất trên snapshot bất biến → tính dependency/invalidation → kiểm invariant/policy → lập hành động → commit theo [giao thức](03_CORE_TRANSACTION_PROTOCOL.md).

Acts giữ thứ tự xuất hiện. “Giữ thứ tự” không có nghĩa thực thi submit khi vừa đọc tiền tố `CONFIRM`. Phải biết hết câu trước khi cấp quyền giao dịch. Các câu hỏi ghim referent tại vị trí phát ngôn, không được viết lại endpoint bằng booking cuối lượt một cách máy móc.

| Lời khách và tiền đề | Fold đúng | Điều cấm |
|---|---|---|
| Đang xác nhận toàn chuyến; “Đúng rồi, nhưng đổi xe 7 chỗ” | Đổi xe, tăng revision, đọc tóm tắt mới | Đặt xe 4 chỗ trước rồi sửa |
| Đang xác nhận origin A; “Đúng, đi đến B nữa” | Có thể xác nhận origin A nếu đã delivered và không bị sửa; thêm destination B chưa xác minh | Tự coi B đã xác nhận hoặc submit |
| Đang xác nhận origin A; “Đúng, nhưng đón ở B” | B thay A, confirmation A không hợp lệ | Giữ origin A confirmed |
| “Từ A đến B bao xa, à đổi điểm đến C” | Câu hỏi vẫn về A→B; booking chuyển C; estimate đó không gắn cho chuyến C | Trả estimate A→C như lời khách hỏi |
| “Đổi sang C rồi từ đây đến đó bao xa?” | `đó` có thể trỏ C sau sửa; `đây` phải có nguồn hợp lệ | Tự tạo vị trí GPS |
| “Thôi không đi A nữa, đi B” | Sửa destination B | Hủy toàn yêu cầu |
| “Không đặt nữa, mà A có gì chơi?” | Dừng draft theo policy; trả thông tin A | Tạo chuyến do câu hỏi có địa danh |
| “À thôi đặt đi” sau draft đã dừng | Xác định resume/new, rồi xác nhận phiên bản hiện hành | Tự submit bản đã hủy |
| “Hạ Long khỉ gió Hải Phòng” thiếu quan hệ rõ | Gắn `CORRUPTED_CONNECTOR`, hỏi một ý phân biệt | Luôn lấy địa danh cuối |

Trong lượt có câu hỏi thông tin, repeat/recall, social hoặc preference thuần, booking slots và booking revision không thay đổi. Thông tin focus hoặc lịch sử có thể thay đổi. Với lượt nhiều ý, chỉ slot có chỉ dẫn nghiệp vụ mới được cập nhật.

## 5. Tham chiếu, focus và câu trả lời ngắn

Mỗi place mention có `usage`: `BOOKING_ORIGIN`, `BOOKING_DESTINATION`, `BOOKING_STOP`, `INFORMATION_LOOKUP`, `ESTIMATE_ENDPOINT`, `SEARCH_REGION`, `DIALOGUE_FOCUS_ONLY`, `UNRESOLVED`. Không suy `destination` chỉ vì thấy động từ “đi” trong câu hỏi.

Context gửi model gồm snapshot booking cần thiết, focus theo vai trò, câu hỏi đã thực sự trình bày, các quyết định tạm dừng có giới hạn, recent events đã lọc PII và quyền/khả năng công cụ. Không gửi toàn bộ lịch sử vô hạn hoặc mọi session của khách. Tham chiếu cần ID, role, version, turn gốc và provenance.

Thứ tự giải tham chiếu: thực thể được nêu tường minh tại mệnh đề hiện tại → focus phù hợp role và thời điểm → câu hỏi đã trình bày còn hiệu lực → booking phù hợp nghĩa → hỏi lại. Một pending cũ không được ghi đè referent mới mà khách vừa chỉ rõ. “Đây” không chứng minh khách ở origin đã lưu và không tự cấp GPS. Focus origin/destination/inquiry tách biệt để đổi địa bàn điểm đến không kéo theo đổi điểm đón.

“Vâng/đúng” chỉ có quyền xác nhận khi có một quyết định rõ, đã delivered theo mode, đúng target/version và quyền sở hữu còn hiệu lực. “Thế á”, “ừ ha”, “để xem”, “chắc thế”, “không rõ” không được mặc định là đồng ý giao dịch. NLU phân biệt `SOCIAL_RESPONSE`, `EXPRESS_UNCERTAINTY` và `DECLINE_TO_ANSWER`; server kiểm các điều kiện còn lại. Cần thêm thời gian khác với từ chối cung cấp dữ liệu và khác với không biết giá trị.

Binding và timing của lượt được lưu bất biến khi admit. `trusted.input_timing` do adapter tin cậy lập, gồm `started_at`, `ended_at`, `overlap`, `basis` theo contract. Nếu khách bắt đầu nói “ừ” trước khi câu hỏi đủ delivery nhưng ASR final đến sau ACK, lời đó chưa được dùng để submit. Không suy timing từ text và không mở rộng quyền của lượt cũ bằng ACK mới; retry vẫn dùng context/binding đã admit.

Ví dụ: đang chờ chọn viện 108; khách hỏi viện 103; bot hỏi “Giữ 108 hay đổi 103?”; “ừ đúng rồi” **chưa chọn được phương án**. Cần hỏi tên viện, không xác nhận pending cũ. Điều này sửa ví dụ `ON_HOLD` quá rộng trong BONUS.

## 6. Pending tạm dừng và lưỡng lự

Chỉ có một quyết định đang được mời trả lời; context tạm dừng là hàng đợi hữu hạn có lý do, target/version, created/expiry, dependency và nguồn. `ON_HOLD` là trạng thái context, không phải đã xác nhận. Tạm dừng khi khách hỏi xen ngang hoặc cần suy nghĩ; không giữ quyết định vô hạn qua thay đổi chuyến, takeover hoặc đổi quyền.

| Sự kiện | Xử lý pending |
|---|---|
| Hỏi FAQ không đổi target | Trả FAQ, có thể mời lại cùng quyết định bằng response mới |
| Thêm địa chỉ cùng target | Tính lại location/version; quyết định cũ hết hiệu lực |
| Đổi slot độc lập | Chỉ location decision không phụ thuộc có thể còn; trip summary hết hiệu lực nếu nội dung chuyến đổi |
| Đề cập POI khác để hỏi | Đổi inquiry focus, không tự đổi booking; pending chưa chắc là referent của “đó” |
| Playback bị ngắt | Quyết định chưa đủ delivery; reissue theo contract |
| Reconnect/resume | Đọc durable state, phát response mới; không dùng playback cũ làm bằng chứng |
| Hết hạn/ownership đổi | Vô hiệu hoặc bắt buộc đánh giá lại |

Sau một lần nói không biết, thay loại câu hỏi. Ngưỡng thử nghiệm hai lần trên **cùng vấn đề** chỉ là budget ban đầu: hỏi vùng/đường → đề nghị một ứng viên có bằng chứng hoặc hỏi mốc khác → hướng dẫn đọc biển hiệu nếu phù hợp → hỗ trợ theo policy. Không reset bộ đếm bằng cách paraphrase cùng câu. Không ép origin trước khi khách đang hỏi rõ destination. Mỗi response tối đa một câu hỏi quyết định.

## 7. Địa chỉ chia lượt: merge có nguồn và chống lặp

`MERGE_SLOT_COMPONENT` nhận component patch, không nối chuỗi trực tiếp. Lưu các utterance event bất biến; `search_label` được sinh từ components khác với lời gốc. Mỗi patch gắn `turn_id`/`act_id` và source. Retry cùng input/hash trả outcome cũ; không áp dụng patch hai lần. Hai lượt hợp lệ có cùng text vẫn là hai sự kiện, không loại chỉ bằng so nội dung.

| Patch | Quy tắc |
|---|---|
| Thêm `ngõ 51 đường X` vào `số 18 ngách 16` cùng origin | Hợp nhất khi quan hệ rõ; phần chưa xác minh vẫn chưa xác minh |
| Sửa số nhà 18→20 | Thay component, tăng `location_version` và revision nghiệp vụ; bỏ confirmation/estimate phụ thuộc |
| Đổi đường X→Y | Xóa hoặc giữ treo để hỏi lại house/alley/branch cũ; không mang ngõ X sang Y như fact |
| Đổi tỉnh | Vô hiệu khu vực phụ thuộc nếu không còn bằng chứng; giữ utterance lịch sử |
| Thêm mốc “đối diện quán P” | Quan hệ mô tả, không suy tọa độ chính xác |
| Bổ sung mơ hồ sau hai endpoint | Hỏi patch thuộc origin hay destination; không gộp tùy tiện |
| Patch map trả sau lúc khách đổi địa chỉ | Chỉ áp dụng khi snapshot target/version còn khớp |

Ví dụ ba lượt “số 18 ngách 16” → “ngõ 51 đường X” → “đối diện quán P” phải giữ tất cả thành phần, nhưng không coi ba mảnh là một địa chỉ đã được provider xác minh. Repo hiện có `src/services/address_refinement.py` và operation `augment`: giữ hành vi có ích, dùng test làm hợp đồng, tránh chép nguyên thuật toán cũ làm đặc tả mới.

## 8. Chuẩn hóa tiếng Việt và phục hồi ASR

Normalizer deterministic chạy với từ điển/quy tắc có phiên bản, không cạnh tranh quyền sửa nghĩa với model. Nó đề xuất candidate theo loại trường:

| Đầu vào | Xử lý |
|---|---|
| `một ba hai` trong số ngõ | Đề xuất `132`; giữ token gốc và kiểu đọc từng chữ số |
| `hai mốt`, `hai lăm/hai nhăm` | Chuẩn hóa 21/25 khi role rõ; không áp quy tắc như vậy cho tên POI |
| `một hai ba xuyệt bốn` trong số nhà | Đề xuất `123/4`; slash có thứ tự, không tương đương ngách/ngõ tùy tiện |
| `chục người` | 10 người và kiểm capacity; không suy loại xe hãng chưa có |
| `bảy rưỡi`, `kém mười`, `sáng mai` | Dùng `received_at` và `Asia/Ho_Chi_Minh`; hỏi AM/PM/ngày nếu thiếu; không phụ thuộc giờ máy chạy test |
| `hông`, `chừ`, `bển`, `mô` | Dùng context và lexicon vùng; không thay mọi lần xuất hiện như một từ khóa toàn cục |
| `ngõ`, `hẻm`, `kiệt`, `xuyệt` | Có thể là từ chỉ cấu trúc khác nhau, không blanket replace bảo toàn nghĩa |

Giả thuyết phonetic có thể áp dụng cho động từ điều khiển, số, giờ, phủ định và tên riêng. “quỷ chiến” gần “hủy chuyến” chỉ là nghi vấn; tác dụng phụ hủy vẫn phải đủ điều kiện. `không/hông` có bằng chứng khác với từ “không” đã mất hoàn toàn. Nếu text sau mất từ vẫn hợp nghĩa và không có metadata, không thể chứng minh ý định ẩn; không đặt mục tiêu khôi phục 100%.

Side-talk được đánh dấu `possibly_background_spans`, không cắt vĩnh viễn khỏi nguồn. Một đoạn có “không”, số nhà hoặc sửa ý có khả năng ảnh hưởng giao dịch phải được giữ trong phân tích hoặc gây bất định. “Con im để mẹ đặt xe… đón ở viện…” có thể bỏ tác vụ không liên quan; “không phải chỗ đó… alo đổi…” không được bỏ vì tưởng tiếng nền. Không có diarization metadata thì không khẳng định ai nói câu nào.

## 9. Validator, lỗi và budget

| Nhóm kiểm | Ví dụ thất bại | Hành vi |
|---|---|---|
| Schema/size | field lạ, enum lạ, quá nhiều acts | `NLU_SCHEMA_ERROR`; retry hữu hạn nếu budget còn |
| Source | span sai, raw value bịa | `NLU_SOURCE_ERROR`; không áp dụng dữ liệu lỗi |
| Reference | question/version không có, focus sai role | `NLU_REFERENCE_ERROR`; hỏi lại hoặc đọc context hiện hành |
| Semantics | confirm và edit cùng target, hai giá trị xung đột | Fold theo luật nếu rõ; còn mơ hồ thì không giao dịch |
| Provider | timeout, rate-limit, auth, malformed response | Mã lỗi riêng; không âm thầm gọi parser mock |
| Deadline/ownership | kết quả về sau hạn/đổi owner | Loại proposal, không sửa state |

Model adapter cấu hình timeout, retry, cooldown, structured output và prompt version tường minh. Lõi mới vẫn cần đo so với thứ tự fast path của legacy và đường hiểu nguyên lượt `model_v2`; không mặc định thêm ba tầng model là tốt hơn. Mọi retry nằm trong deadline toàn lượt; không network dưới DB transaction.

Context giới hạn theo token/event budget đã pin. Tóm tắt context là dữ liệu dẫn xuất, không thay ledger sự kiện, confirmation binding hoặc trạng thái giao dịch. Thiếu history do retention phải nói không còn dữ liệu; không dựng lại lời khách. Recall “nãy tôi nói gì” lấy user turn trước, loại câu hỏi hiện tại; “trước đó định đi đâu” truy lịch sử theo mốc; “nói lại” lấy nội dung đã trình bày phù hợp delivery.

## 10. Điều kiện nghiệm thu riêng

1. Mọi case thuần inquiry/preference/recall không đổi booking; case nhiều ý chỉ đổi slot tường minh.
2. Bộ truth table confirm/edit/cancel hoạt động cả thứ tự thuận và ngược; không có submit sớm.
3. Merge ba lượt đủ components; replay cùng input không thêm patch/lặp ghi chú; đổi đường không mang chi tiết sai theo.
4. Không xác nhận bằng question chưa delivered, stale version hoặc referent mơ hồ; “ừ” sau lựa chọn hai nơi không tự chọn.
5. Những normalization có thể giữ nghĩa được kiểm bằng gold review; ca ambiguous/irrecoverable chấm hành vi an toàn theo [Test Factory](08_TEST_FACTORY_AND_ACCEPTANCE.md).
6. Test fixture đạt chỉ chứng minh luật sau proposal. Chất lượng model thật, ASR và latency phải đo riêng; gói tài liệu này chưa chạy các phép đo đó.

## 11. Mapping hiện trạng và giới hạn

Điểm đọc code khi triển khai: `src/services/nlu/model.py`, `src/services/nlu/rules.py`, `src/services/address_refinement.py`, `src/core/state.py`, `src/core/nodes/state_reducer.py`, `src/services/response_planner.py`; đường dẫn thực tế phải xác nhận bằng repo snapshot trước sửa. Tài liệu đối chiếu: `docs/MODEL_UNDERSTANDING.md`, `docs/CONVERSATION_BEHAVIOR.md`, `docs/AGENT_RESILIENCE.md`. Đây là các địa chỉ nguồn hiện hữu, không có nghĩa lõi mới phải giữ cấu trúc trong chúng. Mapping source đầy đủ ở [traceability](12_SOURCE_TRACEABILITY.md).
