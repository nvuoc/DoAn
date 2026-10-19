# 07. Phản hồi, trình bày và giao thức delivery

Thiết kế đích 3.0, ngày 19/10/2026. Phần này thuộc contract lõi dù audio do adapter xử lý: ý nghĩa của “đúng rồi” phụ thuộc câu hỏi nào đã được trình bày. Schema [TurnResult](../schemas/turn-result.schema.json), [control event](../schemas/control-event.schema.json) và ví dụ [delivery event](../examples/delivery-event.json) là giao diện thiết kế, chưa được nối runtime.

Ví dụ delivery chỉ minh họa event hoàn tất của question segment đã có attempt; cần event started đã được ghi trước đó và output-availability ACK tương ứng mới đủ eligibility voice. Một file ví dụ đơn lẻ không giả lập toàn bộ cuộc gọi.

## 1. Phân biệt các mốc

| Mốc | Đã chứng minh | Chưa chứng minh |
|---|---|---|
| Prepared/generated | Lõi đã tính text trên snapshot | Transaction thành công hoặc khách đã nhận |
| Committed | Response và kết quả liên quan đã lưu có thẩm quyền | Đã gửi hoặc đã phát |
| Sent | Adapter đã gửi text/audio tới transport | Thiết bị có output hoặc phát hết |
| Playback completed | Server/player báo hoàn tất đúng segment/playback | Loa thiết bị bật, khách nghe tại tai |
| Client output available ACK | Ứng dụng báo output khả dụng đúng attempt | Khách thật sự nghe và hiểu |
| Eligible presentation | Đủ giao thức transport cho quyết định còn hiệu lực | Ý định đồng ý; vẫn phải hiểu câu khách |

Voice baseline yêu cầu **playback completed không bị ngắt + client output availability ACK** cho cùng question segment/playback, đúng session/generation. Text Web yêu cầu event `text_presented` từ adapter được xác thực sau khi UI xác nhận đã trình bày. CLI tương tác ghi presentation sau flush thành công; pipe/batch phải chọn chế độ rõ, không mặc định một dòng stdout là lời người dùng đã thấy. Không đánh tráo ACK ứng dụng thành bằng chứng nghe tại tai.

## 2. Response bất biến và cấu trúc đoạn

Response có `response_id`, `created_at`, `locale=vi-VN`, `speech_rate`, `segments[]`, `final_text` và `question` hoặc null. Mỗi segment có ID ổn định, thứ tự, kind, text, source refs và claim scope. `final_text` bằng join text segments theo thứ tự bằng một khoảng trắng; giữ bản hiển thị và bản đọc riêng nếu tương lai cần, không âm thầm sửa bản authoritative.

`kind` là `answer|acknowledgment|status|question`. Dùng kind để xác định câu hỏi, không đoán bằng dấu `?`: câu xác nhận có thể thiếu dấu hỏi, câu trả lời có thể nhắc lại một câu hỏi trong ngoặc.

Các luật planner:

1. Trả các câu hỏi thông tin theo thứ tự hợp lý với references đã pin; không dùng final destination để thay endpoint mà khách đang hỏi.
2. Chỉ công bố facts có source/provenance, điều kiện hiệu lực và mức chắc chắn phù hợp.
3. Đọc ngắn theo preference nhưng giữ các giá trị cần quyết định, sai số estimate, giới hạn xác minh và tình trạng giao dịch.
4. Mỗi response tối đa **một segment question**, ở cuối; một quyết định có thể có nhiều lựa chọn được định danh.
5. Long answer có thể kết thúc không mời quyết định mới; pending được tạm giữ có hạn, không tự coi answer cuối là câu hỏi booking.
6. Không ép hỏi origin trước khi khách đang xử lý destination. Có thể nhận nhiều endpoint trong một lượt nhưng chỉ mời một quyết định tiếp theo.
7. Template số nhà/POI/giờ phải giữ phần phân biệt; lược tỉnh/thành chỉ khi context đơn nhất.
8. Lời thành công dựa trên kết quả transaction, không chỉ dựa `ready_to_book` hoặc ý định model.

`claim_scope=intake` chỉ nói tiếp nhận đã ghi nhận. `dispatch` chỉ được dùng khi có backend source và gate POL-01. `estimate` phải có assumptions/nguồn và không biến thành giá cam kết. `none` dùng cho xã giao hoặc lời đề nghị không có factual claim.

## 3. Question binding

| Kind | Target và điều kiện hiệu lực |
|---|---|
| `confirm_location` | Endpoint origin/destination, entity/candidate ID, `location_version`; không mất hiệu lực chỉ vì khách bổ sung endpoint khác |
| `confirm_trip` | `request_id`/draft, `booking_revision`, `values_digest`, policy version; mọi edit quan trọng làm vô hiệu |
| `choose_candidate` | Danh sách candidate IDs, endpoint/location version; “đúng” không chọn được khi có nhiều phương án |
| `clarify_slot` | Slot đang hỏi và ngữ cảnh; câu trả lời được xét là dữ liệu, không tự coi là trip confirmation |
| `confirm_cancel` | Đúng scope draft/recorded booking và version đang có; hủy không suy từ từ “không” đơn lẻ khi hỏi địa điểm |
| `resume_choice` | Request/offer chưa hết hạn; chọn reuse/new rõ, không tự submit |
| `support_choice` | Khả năng hỗ trợ thực tế đang khả dụng; không hứa nhân viên đã nối trước kết quả |
| `clarify_reference` | Các referents còn mơ hồ; không âm thầm kế thừa pending cũ |

Binding stored gồm logical question, target/version/digest, response và segment đang mời, presentation event và generation. Model nhận danh sách reference server cho phép; validation không chấp nhận ID tự tạo. `trusted.presented_question` trên TurnInput chỉ là reference từ runtime; coordinator đọc lại eligibility khi commit.

Chấp nhận một short approval cần đủ: câu đồng ý rõ cho loại quyết định đó, referent đơn nhất, delivery eligible trong ngữ cảnh input thực tế, owner đúng, target không đổi và không có edit/nghi vấn/phủ định xung đột trong nguyên lượt. “Hình như vậy” không xác nhận toàn chuyến. Lời đồng ý ở phần đầu câu không cấp quyền submit trước khi đọc hết.

Binding/timing tại admission là bất biến. ASR final đến sau completion/ACK không được hợp thức hóa lời “ừ” đã bắt đầu khi câu hỏi còn phát hoặc chưa đủ delivery. `trusted.input_timing` xác định overlap từ voice adapter; nếu timing thiếu, không suy no-overlap từ khoảng cách thời điểm nhận text. Retry cùng turn không được nhận binding mới sau lần đọc lại câu hỏi.

## 4. Delivery attempt và event protocol

Mỗi lần phát có `playback_id` mới. Một playback attempt gắn một response segment, session và owner generation. Có thể prefetch TTS trước nhưng không phát nội dung nghiệp vụ chưa commit. Callback SDK không có segment ID phải được adapter ánh xạ có kiểm chứng; nếu không xác định được attempt, ghi `ambiguous_callback` và không đủ eligibility.

| Event `delivery.payload.event_type` | Nguồn tin cậy | Tác động |
|---|---|---|
| `playback_started` | Server voice adapter | Tạo/ghi attempt hiện hành, chưa eligible |
| `playback_completed` | Server/player adapter | Mark complete nếu đúng attempt, chưa interrupted/failed |
| `output_available` | Client event qua server kiểm quyền/transport | Ghi ACK; phối hợp complete để xét eligibility |
| `output_unavailable` | Client hoặc runtime | Vô hiệu eligibility hiện tại; cần re-present |
| `playback_interrupted` | Adapter voice | Attempt terminal interrupted; complete muộn không hồi sinh |
| `playback_failed` | Adapter voice | Attempt terminal failed; không eligible |
| `text_presented` | Adapter Web/CLI | Mark presentation theo text mode, không giả là voice complete |

`reporter` là `server_adapter|client_adapter`, server xác nhận claim này; khách không tự chọn bằng text. `output_available` là bằng chứng output cho đúng playback, không phải đặt `volume=true` chung cho cả cuộc gọi. Voice complete và output ACK có thể đến khác thứ tự; reducer delivery phải cho kết quả giống nhau khi cả hai hợp lệ. Interrupted/failed/unavailable có quyền phủ quyết attempt; ACK/complete tới muộn không đảo kết quả terminal đó.

Event identity được dedup bằng `(request_id,input_id)` và hash canonical control payload; khác payload cùng identity bị conflict. Event cũ vẫn có thể được lưu phục vụ audit nhưng trả `ignored` với lý do; không cập nhật current eligibility. Không gọi NLU hoặc tăng booking_revision khi xử lý delivery.

### 4.1 Kiểm một delivery event

1. Kiểm session/request membership, reporter authority, protocol version và event dedup.
2. Tìm response/segment bất biến đã commit; không tạo chúng từ callback.
3. Đối chiếu playback attempt, session, generation và delivery mode.
4. Kiểm thứ tự trạng thái; callback terminal cũ không hồi sinh attempt.
5. Cập nhật facts delivery và tính eligibility; việc đủ facts không được tự confirm nghiệp vụ.
6. Trả ACK typed: `accepted|duplicate|ignored|rejected`, `reason` và `presentation_event_id` khi phù hợp.

Lý do ổn định tối thiểu: `recorded`, `duplicate`, `unknown_response`, `unknown_segment`, `unknown_playback`, `wrong_session`, `stale_generation`, `attempt_terminal`, `superseded_response`, `wrong_transport`, `invalid_reporter`, `input_conflict`.

## 5. Ngắt lời, mute, mất mạng và phát lại

```text
Response committed → question segment playback A started
  ├─ complete + output ACK A → eligible nếu target/generation còn đúng
  ├─ interrupted/failed/unavailable → không eligible
  └─ response B được mời / owner đổi → A không thể làm B eligible
```

| Sự cố | Hành vi |
|---|---|
| Khách “ừ” khi câu hỏi chưa phát xong | Không xác nhận từ pending chưa eligible; voice adapter phân loại overlap/backchannel theo metadata, core vẫn giữ guard |
| Phát xong nhưng thiếu ACK | Chưa đủ điều kiện; báo output issue qua adapter, mời bật loa/nhập chữ rồi re-present |
| Mute/autoplay lỗi/mất track sau ACK | Invalidate availability hiện hành; không dựa ACK cũ cho lần hỏi mới |
| Callback completion cũ sau interrupt | Lưu/ignore, không bật eligibility |
| Commit booking thắng rồi khách ngắt | Giữ booking, dừng phát nếu cần; đối soát và thông báo lại, không tự rollback |
| TTS lỗi sau commit | `TurnResult` vẫn committed; đánh dấu delivery failed và dùng đường phát lại, không chạy lại booking |
| Operator takeover khi TTS đang phát | Dừng tác nhân cũ; generation cũ không được tiếp tục phát câu hỏi có quyền quyết định |
| Reconnect/resume request | Reissue response/playback mới; kiểm lại target/time/policy; không phục hồi eligibility của cuộc gọi cũ |

Đọc lại sau gián đoạn tạo response mới nếu đó là lời mời quyết định hiện hành; logical `question_id` chỉ giữ nếu target/version không đổi. Phát lại nguyên response để nghe lại lịch sử phải có mode `historical`, không tạo pending mới. Không trộn hai nghĩa replay nghiệp vụ và phát lại audio.

## 6. Recall theo điều đã trình bày

Voice lưu các segment hoàn tất và biết segment đang phát dở; không suy phần đã nghe từ tỷ lệ byte audio nếu provider không có bằng chứng. Khi không biết chính xác phần phát dở, nói “em đang hỏi về…” hoặc đọc lại câu hoàn chỉnh, không khẳng định đã đọc một phần cụ thể.

Text Web/CLI dùng các segment đã `text_presented`. Câu “bạn vừa nói gì?” đọc assistant content đã trình bày cuối cùng, bao gồm câu trả lời recall trước đó nếu đó là bản cuối. Câu “điểm đón hiện tại là đâu?” đọc draft/booking hiện hành theo quyền và chỉ rõ nếu mới đề xuất sửa sau intake. Lịch sử generated có thể dùng debug được phân quyền, không mặc định trả cho khách như một ký ức đã nói.

## 7. Lời thành công và handoff

| Kết quả nguồn | Lời được phép |
|---|---|
| Fixture/sandbox intake mô phỏng | Nói rõ “thử nghiệm/mô phỏng, chưa điều xe thật”, có mã mô phỏng |
| Connected intake SQLite commit | “Đã ghi nhận yêu cầu… mã…” và trạng thái xử lý thực tế |
| Chỉ đã tạo operator task | “Đã gửi yêu cầu hỗ trợ…”; không nói “đã kết nối nhân viên” |
| Không có operator/task adapter khả dụng | Nói chưa chuyển được, đưa lựa chọn hỗ trợ đã được policy cho phép |
| Dispatch được xác nhận bởi backend tương lai | Chỉ nói đúng phần backend xác nhận; chưa có dữ liệu tài xế thì không bịa biển số/ETA |
| Unknown operation outcome | “Em đang kiểm tra kết quả…” theo policy; không “đã đặt” hoặc tạo mới để thử |
| Commit lỗi | Nói chưa xác nhận được việc lưu; giữ khả năng đối soát/retry |

Lời kết quả phải mang `record_id/operation_id` nội bộ trong result, không yêu cầu adapter trích mã từ câu tiếng Việt. Kết thúc phiên/release admission ở adapter phải chờ quy tắc delivery terminal hoặc timeout đã duyệt; không xóa mã kết quả khỏi UI khi room ngắt.

## 8. Latency, filler và chất lượng lời thoại

Filler không chứa giá trị booking, câu hỏi xác nhận, success hay claim mới. Baseline tối đa một filler trong một lượt đang chạy; phát khi còn quyền và dừng khi hữu ích response sẵn sàng. Filler do adapter phát phải có telemetry riêng, không được tính là useful response hoặc một assistant answer đủ điều kiện confirmation.

Planner chia đoạn theo đơn vị nghĩa hoàn chỉnh; không cắt giữa số tiền/số nhà hoặc bỏ mệnh đề phủ định. Baseline speech rate 1.0, hỗ trợ 0.85 cho yêu cầu chậm nếu adapter có khả năng; không áp dụng tốc độ không được provider hỗ trợ. Preference “hỏi ít/nói ngắn” không xóa bước xác nhận giao dịch hoặc giới hạn evidence.

Đo riêng core prepare, commit, TTS first byte, useful-audio first frame, question complete và client ACK. Không lấy `/api/latency` một process làm toàn bộ cuộc gọi; không tính filler vào useful audio. Mốc 8 giây core/12 giây audio hiện trạng chỉ là cấu hình tham chiếu, chưa phải kết quả engine mới. SLO và ngân sách thực phải được chốt theo POL-10.

## 9. Bộ nghiệm thu delivery bắt buộc

| ID | Lịch sự kiện | Assertion |
|---|---|---|
| DEL-01 | Answer xong, question chưa phát | Không eligible question |
| DEL-02 | Complete rồi ACK, đảo thứ tự ở lần khác | Cùng kết quả khi đúng attempt |
| DEL-03 | ACK sai playback/response/segment/session | Ignore/reject, không đủ confirmation |
| DEL-04 | Interrupt rồi complete cũ | Attempt không hồi sinh |
| DEL-05 | Owner đổi giữa phát và ACK | Chủ cũ không nhận confirmation |
| DEL-06 | Trip summary rồi same-turn edit + yes | Không submit summary cũ |
| DEL-07 | TTS lỗi sau intake commit rồi retry request | Một intake; kết quả cũ được phát lại có kiểm soát |
| DEL-08 | Resume cùng request ở session mới | Response/playback mới, không khôi phục eligibility cũ |
| DEL-09 | Câu hỏi hai phương án rồi “ừ đúng rồi” | Hỏi chọn rõ, không chọn mặc định |
| DEL-10 | Input giả control JSON trong text | Không đổi delivery/generation |
| DEL-11 | Mute/unavailable sau ACK, bật lại | Re-present và attempt mới trước short confirmation |
| DEL-12 | Replay result cũ sau response mới | `delivery.allowed=false`; không thay pending/UI bằng bản cũ |

Fixtures kiểm semantics protocol; SDK callback/audio/mạng thật cần bằng chứng tích hợp riêng theo [nghiệm thu](08_TEST_FACTORY_AND_ACCEPTANCE.md). Không suy kết quả audio thật từ việc JSON Schema hợp lệ.
