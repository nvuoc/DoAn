# 06 — Địa chỉ Việt Nam, tri thức và ước lượng

Phiên bản thiết kế 3.0 • 19/10/2026 • **Đề xuất; dữ liệu và policy thật chưa được cấp bởi bộ tài liệu này**.

Hợp nhất `PLAN.md` §§9–11, 13 và BONUS về phonetic, tên nước ngoài, POI lớn, bất đối xứng đón/đến, manh mối tại chỗ. Các ví dụ tên thật minh họa cách xử lý ngôn ngữ, không chứng minh một chi nhánh, tọa độ hoặc chính sách hiện hành. Đọc cùng [NLU/context](05_NLU_AND_CONTEXT.md), [policy](04_CORE_POLICY_MATRIX.md) và [quyết định cần duyệt](../decisions/OPEN_DECISIONS.md).

## 1. Bốn câu hỏi tách biệt

1. Khách thực sự nói gì và với vai trò nào?
2. Hệ thống đang giả thuyết địa điểm nào?
3. Bằng chứng xác minh đến cấp nào?
4. Policy cho phép thực hiện hành động gì với bằng chứng đó?

Tọa độ, mức nổi tiếng, confidence và khách nói “đúng” không thay thế bốn lớp này. Khách có thể xác nhận **ý định muốn đến A** mà hệ thống chưa có bằng chứng A ở đâu. Giữ cả precision và coordinate role; không xóa chúng như BONUS đề xuất.

| Lớp dữ liệu | Nội dung bắt buộc |
|---|---|
| Customer description | Các utterance source bất biến; normalized components và các quan hệ gần/đối diện/vào ngõ |
| Resolution hypotheses | Query gốc, biến thể, ứng viên, alias/phonetic method, giải thích ranking |
| Evidence | Provider/catalog ID, record version, fetched_at, hiệu lực, role tọa độ, cấp chi tiết và phần chưa xác minh |
| Policy assessment | Origin sufficient, destination sufficient, route estimable, auto-book allowed, lý do và policy version |

`precision`: `ENTRANCE`, `EXACT_POI`, `ALLEY`, `STREET`, `WARD`, `AREA`, `TEXT_ONLY`, `UNKNOWN`, cộng mức chưa kiểm chứng nếu cần. `coordinate_role`: entrance/access_point/poi_point/area_representative/route_anchor. Một `route_anchor` không được hiển thị như vị trí chính xác của khách. Không phải mọi điểm gắn nhãn POI đều là lối ô tô đi vào được.

## 2. Bất đối xứng điểm đón và điểm đến

| Điều kiện | Điểm đón | Điểm đến |
|---|---|---|
| Chỉ có tên thành phố/vùng | Thường cần mốc/đường cụ thể để tìm khách | Có thể lưu ý định vùng và tính tuyến thô nếu có điểm đại diện hợp lệ |
| POI rộng | Cần xét lối đón/điểm tiếp cận, khả năng tài xế tìm khách | Không hỏi cổng/tòa nếu không cần cho nghiệp vụ; vẫn phân biệt đúng POI/chi nhánh |
| Tên đa chi nhánh | Hỏi khu vực hoặc dấu hiệu phân biệt | Cũng hỏi khi các chi nhánh đều hợp lý |
| Khách không biết chi tiết | Đổi chiến lược hỏi hoặc hỗ trợ theo khả năng thực | Không ép chi tiết không cần thiết; không tự bỏ required destination |
| Tọa độ chưa có | Không tự coi text là verified | Route có thể unavailable; giữ ý định và policy độc lập |

Không đồng nhất `PICKUP_VIABLE`, `DESTINATION_SUFFICIENT`, `ROUTE_ESTIMABLE` và `VERIFIED`. Mục tiêu giảm hỏi của BONUS được giữ, nhưng mặc định release bảo thủ: địa chỉ chưa xác minh chặn booking tự động; ghi yêu cầu hỗ trợ riêng chỉ khi tính năng đã được duyệt và có nhân viên thực nhận. `POL-02/03/04/06` chốt ngoại lệ. Điểm đến vẫn bắt buộc cho tới khi policy đổi được phê duyệt.

“Đi Hạ Long” không tự gán tâm Hồng Gai/Bãi Cháy. Có thể lưu destination vùng; nếu dùng đại diện để estimate phải có record area/anchor được duyệt, nêu khoảng sai số và không coi đó là điểm thả đã chọn. Khách nói “sân bay” không chứng minh sân bay nào.

## 3. Pipeline resolver có giới hạn

```text
Nguồn gốc + usage + endpoint/version + scope có nguồn
 → parse components/constraints
 → sinh truy vấn nguyên văn và giả thuyết có phiên bản
 → catalog được phép + provider adapter
 → chuẩn hóa evidence/dedupe theo định danh thực thể
 → lọc xung đột cứng và rejections
 → rank mềm + đánh giá ambiguity/coverage/precision
 → đề xuất một ứng viên, một câu phân biệt, chưa xác minh hoặc hỗ trợ
```

Resolver chỉ trả dữ liệu; reducer quyết định cập nhật. Mỗi request tool pin `request_id`, `target`, `location_version`, query fingerprint, deadline và provider/catalog version. Kết quả muộn không được áp vào địa chỉ mới. Cache key bao gồm query chuẩn, usage khi ảnh hưởng, vùng, profile/provider/data version và các cờ liên quan; không dùng chung cache giả và live.

Số query/Place lookup/nhánh song song do budget `POL-10`. Khởi điểm phát triển: query gốc trước, mở rộng có điều kiện khi chưa đủ bằng chứng; cap hữu hạn và deadline chung. Không hardcode budget thử nghiệm thành SLA. Timeout/rate-limit/auth/no-results/coverage-gap/schema-error phân biệt rõ; live lỗi không biến thành mock.

## 4. Ràng buộc cứng trước điểm nổi tiếng

Ràng buộc cứng gồm: tỉnh/vùng tường minh, số nhà/ngõ/ngách, quan hệ cha/con cần thiết, loại địa điểm khách nói rõ, branch, rejections và yêu cầu phủ định. Không xếp cao một kết quả vi phạm chỉ vì tên giống hoặc nổi tiếng. Việc provider không có kết quả **không chứng minh địa chỉ ngoài đời không tồn tại**.

Prominence, độ gần âm, độ phổ biến, độ khớp context, khoảng cách hợp lệ và coverage là tín hiệu mềm sau ràng buộc cứng. Không áp “POI lớn khớp 85% luôn thắng POI nhỏ exact”. Không giữ trọng số 1.0/0.75/0.4/0.1 như fact. Chúng là tham số thử nghiệm phải benchmark trên gold độc lập, có lỗi wrong-parent/wrong-branch/wrong-number.

| Tình huống | Quyết định an toàn |
|---|---|
| Khách gọi tên khu đô thị, provider trả cửa hàng cùng tên bên trong | Giữ ứng viên khu đô thị nếu evidence đúng; không tự chọn cửa hàng |
| Khách nói rõ phòng khám nhỏ, phonetic gần bệnh viện lớn | Không nâng bệnh viện lớn lên như kết luận; giữ ứng viên phù hợp loại đã nêu |
| Brand đa cơ sở | Hỏi một dấu hiệu địa bàn; không map cứng brand thành một branch |
| Candidate đã bị bác | Loại thực thể theo endpoint, kể cả alias khác; chỉ xem lại khi khách đổi ý rõ |
| Hai provider có cùng tên | Dedupe bằng ID/geometry/hierarchy có bằng chứng; không tên-only |
| POI cha và con | Lưu `CONTAINS/PART_OF/HAS_ENTRANCE`; không gộp thành một thực thể |

Thời gian/TTL của rejection có lý do: cùng location version thì giữ; khách chủ động mở lại ứng viên hoặc đổi phạm vi cần xét lại rõ ràng. Không để một từ “không” vô hiệu cả catalog toàn session.

## 5. Phonetic, tên ngoại ngữ và thực thể ngắn

Ba kênh sinh ứng viên được giữ từ BONUS: alias phiên âm đã review, phonetic index, LLM guess. Chúng không cấp verification.

| Kênh | Dữ liệu và cách dùng | Rủi ro phải đo |
|---|---|---|
| Spoken aliases | Original name, canonical ID/branch, kiểu nói, vùng, nguồn, review/version | Alias rộng “siêu thị Nhật” có thể nhiều nơi; không map duy nhất |
| Vietnamese phonetic key | Quy tắc âm đầu/vần/thanh có phiên bản; giữ raw song song | Gộp l/n, d/gi/r/v hoặc thanh quá mạnh làm tăng false positives |
| Viet-lish/G2P | Sinh alias dự thảo cho `mall`, `park`, `city`... | Không tự publish alias sinh cho toàn catalog |
| Entity chữ cái | Loại bệnh viện/tòa/cổng + E/K/B... theo context | “em” có thể đại từ thật, “ca” không luôn là K |
| LLM inverse guess | Candidate canonical name + source span và lý do | Không thêm tỉnh/branch hoặc gọi đó là đã xác minh |

Ví dụ “e on mô”, “ô sừn bắc”, “canh nam”, “bệnh viện em” tạo candidates cho Aeon Mall/Ocean Park/Keangnam/Bệnh viện E khi phù hợp context. Query cả raw và candidate trong budget; kết quả phải kiểm địa bàn/branch. Không cam kết mọi tên nước ngoài mới đều tự giải được. Một candidate duy nhất trong catalog thiếu coverage chưa phải duy nhất ngoài đời.

Structural anchor như “ngõ 132” giúp lọc, nhưng phải có dữ liệu chứng minh ngõ đó thuộc đường. Phonetic match “tàu diễn” gần “Cầu Diễn” không tự chứng minh quan hệ địa chỉ. Chuẩn hóa số đọc theo [NLU](05_NLU_AND_CONTEXT.md), bảo toàn thứ tự slash và đường dẫn ngõ/ngách.

## 6. Number guard và địa chỉ chi tiết hơn map

So sánh house/alley/branch bằng chuỗi chuẩn có cấu trúc, không chỉ tìm chữ số trong address label. `18`, `18A`, `18/2`, ngõ 18 và số nhà 18 có nghĩa khác nhau. Provider không nêu một component thì trạng thái là thiếu evidence; không coi match toàn bộ.

| Kết quả tìm với “ngõ 185 đường X” | Hành vi |
|---|---|
| Đúng ngõ 185, đúng đường/vùng, nguồn đủ | Đề nghị xác nhận phù hợp role; vẫn kiểm lối/chi tiết cần thiết |
| Chỉ có ngõ 18/85/180 | Không chấp nhận thay; có thể hỏi một câu nếu có dấu hiệu ASR hợp lý |
| Chỉ có đường X | Giữ số ngõ chưa xác minh; precision STREET, không EXACT/ALLEY |
| Khách khẳng định 185 | Lưu customer assertion, chưa nâng provider verification; hỗ trợ theo policy |
| Có ngõ gần số | Không suy tọa độ theo thứ tự số; không lấy ngõ “liền kề” như đại diện có căn cứ |
| Kết quả rỗng | Giữ raw/components, phân biệt coverage-gap với sai địa chỉ |

Fallback cấp địa chỉ đi từ chi tiết sang cấp có thể kiểm chứng; giữ phần thiếu ở `unverified_components`. Một route anchor của đường chỉ dùng khi policy/estimate cho phép và nguồn/uncertainty rõ. Không chuyển sang `request_recorded` nếu điều kiện booking vẫn bị chặn; hỗ trợ có thể là operator task riêng.

## 7. Khách đứng nơi xa lạ và tìm mốc giao nhau

Giữ ý tưởng hướng dẫn tìm manh mối tại chỗ: hỏi một thông tin khách có thể nhìn thấy mà không bắt di chuyển nguy hiểm; tên cửa hàng/địa chỉ ở biển hiệu, tên đường, giao lộ hoặc mốc lớn. Không khẳng định mọi biển hiệu đều có địa chỉ. Nếu khách không biết/không muốn, đổi hướng hoặc giải thích lựa chọn hỗ trợ; không lặp “xin địa chỉ” vô hạn.

`CO_LOCATED_POI_SEARCH` là thử nghiệm có kiểm chứng, chưa release mặc định. Đầu vào là ít nhất hai mốc, quan hệ gần/đối diện/bên cạnh, scope có nguồn và các branch candidates. Spatial intersection chỉ tạo **cụm giả thuyết**; bán kính 100m là tham số thử, không fact. Hai chuỗi lớn nằm gần nhau có thể lặp ở nhiều nơi hoặc dữ liệu thiếu. Phải nêu nhiều cụm/mất coverage, kiểm độ tươi/độ chính xác tọa độ rồi hỏi xác nhận. Không nói “đã xác định ngay tuyến đường” chỉ vì có một cụm trong dữ liệu đang có.

Mốc “gần sân bóng thôn Tự, Việt Yên” cần định danh thôn/xã/vùng và thời điểm; `near` không đồng nghĩa `at`. Khách ở đối diện POI không được pin tọa độ bên trong POI như vị trí chính xác. Ghi chú “tài xế gọi khi tới” chỉ được hứa nếu quy trình và liên hệ thực sự hỗ trợ.

## 8. Địa giới cũ–mới, nguồn và scope

Record địa giới tối thiểu: stable ID, tên/loại đơn vị, cấp/parent ở từng thời kỳ, `valid_from/valid_to`, mapping many-to-many, nguồn có thẩm quyền, thời điểm thu thập, phạm vi geometry/area, review status và version. Không ép mọi tên cũ thành đúng một tên mới. Hiệu lực tại `as_of` của câu hỏi khác với thời điểm provider trả kết quả.

“Hà Nội có những quận nào”, “Việt Yên”, “Bích Động”, “Xuân Lộc giờ là phường à?” cần kiểm tra phạm vi và giả định. Có thể giải thích cách gọi lịch sử; không sửa nguyên văn lịch sử booking thành tên hành chính mới. Lõi không dùng trí nhớ model làm bảng địa giới chính thức. Khi dữ liệu chỉ phủ Hà Nội, báo đúng phạm vi; chưa được tuyên bố xử lý địa chỉ toàn quốc.

Scope không là một tỉnh áp cho mọi vai trò. Origin scope, destination scope, search region và inquiry focus độc lập. Khách sửa “ở Bắc Ninh cơ” chỉ đổi target liên quan; không kéo điểm đón Hà Nội sang Bắc Ninh. Renderer lược phần lặp khi hai bên đã chia sẻ scope chắc chắn và không làm mất phân biệt; không lược tên tỉnh khi hai ứng viên trùng tên nằm khác tỉnh.

## 9. Knowledge service và policy có nguồn

Bốn lớp giữ từ PLAN: luật bắt buộc trong code/policy; FAQ hãng đã duyệt; tri thức địa lý/địa điểm có nguồn; lịch sử hội thoại/booking. Các lớp không tự thay thế nhau.

`KnowledgeRecord` cần: ID/version, topic/scope, question variants, answer facts, điều kiện/ngoại lệ có cấu trúc khi là rule, source, `effective_from/to`, review_status, owner/reviewed_at và quyền sử dụng. Chỉ `APPROVED` và còn hiệu lực, đúng hãng/scope mới dùng làm chính sách chính thức. Chưa có người duyệt thì record là draft, không tự ký tên người duyệt.

Pipeline: chuẩn hóa câu hỏi và referents → kiểm hard policy → retrieve candidate documents → lọc scope/hiệu lực/status → kiểm đủ bằng chứng và xung đột → exact/template hoặc grounded answer → lưu source IDs/version trong response metadata. Source xung đột không lấy điểm retrieval cao nhất làm chân lý; dùng thứ tự thẩm quyền đã duyệt hoặc nói chưa đủ chắc/handoff. Không có nguồn thì nói thiếu thông tin, không tự tạo FAQ.

Grounded generator chỉ diễn đạt facts được cấp, không thêm cước, giờ mở cửa, xe sẵn có hoặc ngoại lệ. Câu hỏi bệnh viện có cho thú cưng vào không cần nguồn của bệnh viện, không dùng chính sách thú cưng trên taxi. “Sao bạn biết” chỉ nêu nguồn đã thực sự dùng; không bịa một lượt tra cứu chưa chạy.

Cập nhật bundle tri thức gồm version/checksum, hiệu lực, review, gold regression và rollback bundle; request đang chạy pin version để tái tạo. Điều khoản provider/caching phải được xác minh ở thời điểm tích hợp, không mặc định dữ liệu API được phép lưu vĩnh viễn hoặc trộn vào catalog khác.

## 10. Route, ETA và giá đồng hồ

Tách ba kết quả: đường/quãng đường, thời gian hành trình, ước tính cước. ETA xe đến đón cần nguồn fleet/dispatch riêng; thời gian chạy A→B không phải thời gian xe tới khách. Không hứa có xe chỉ vì tính được route.

| Điều kiện | Kết quả được phép |
|---|---|
| Hai endpoint có anchor hợp lệ và routing thành công | Distance/duration với basis và độ thô của anchor |
| Có traffic timestamp/nguồn phù hợp | Nêu dựa traffic đó; không gọi live khi chỉ tuyến tĩnh |
| Có tariff được duyệt, đúng loại xe/vùng/hiệu lực | Fare estimate theo phương pháp và các khoản đã biết |
| Thiếu tariff | Không tạo số tiền; có thể trả km/thời gian đã có |
| Thiếu phí chờ/phụ phí | Đánh dấu unknown, không mặc định 0 |
| Endpoint thay đổi | Vô hiệu quote/route phụ thuộc; tool result cũ không gắn cho chuyến mới |

Tariff model cần opening fare/distance, bands, tiền chờ, tối thiểu, phụ phí, làm tròn, đơn vị, currency, khu vực, vehicle, version/hiệu lực và nguồn. Các demo 10.000/15.000/12.000 trong PLAN chỉ để thử thuật toán; không đưa thành giá hãng. Giá thật theo đồng hồ/quy trình đã duyệt; estimate không là giá cố định. Khoảng sai số phải có căn cứ, không tùy đặt ±20%.

Adapter route chuyển đơn vị m→km, s→phút có test; giữ dữ liệu gốc có nguồn để audit. Cache key bao gồm endpoints/version, vehicle, route options, time bucket/traffic basis, provider/tariff versions. Ghi `UNAVAILABLE` khi route không có; không đường chim bay tự biến thành quãng đường chạy xe. Dữ liệu route/tariff ngoài scope không ngăn công việc core khác, nhưng khóa tính năng estimate tương ứng.

## 11. Bộ nghiệm thu domain

| Nhóm | Bằng chứng cần có |
|---|---|
| Number/structure | Không accept sai ngõ/số nhà/slash trong gold; thiếu component vẫn unverified |
| Parent/branch | Gold gồm POI lớn, cửa hàng nhỏ thật sự được hỏi, nhiều branch và rejections |
| Phonetic | So exact/fuzzy baseline với alias/index mới bằng cùng tập holdout; báo recall và false accept riêng |
| Asymmetry | Bớt hỏi destination khi không cần nhưng không dùng anchor làm verified pickup |
| Scope/time | Đổi tỉnh một endpoint không đổi endpoint khác; địa giới many-to-many theo thời điểm |
| Knowledge | Draft/expired/sai hãng/nguồn xung đột không được nói như policy chính thức |
| Estimate | Thiếu tariff không có fare claim; đổi chuyến vô hiệu quote; không nhầm duration với pickup ETA |
| Failure | Timeout/auth/no-results khác nhau; không fallback mock; tool stale không ghi state |

Các gate số lượng và pass/fail ở [Test Factory](08_TEST_FACTORY_AND_ACCEPTANCE.md). Chưa có benchmark mới cho phonetic, co-location, model hoặc map live trong gói này. API cụ thể và SDK phải đọc tài liệu chính thức lúc thực hiện tích hợp; bộ tài liệu không chứng nhận endpoint/giá/terms đang còn nguyên.

## 12. Nơi đọc hiện trạng khi triển khai

`src/services/maps/`, `src/services/address_refinement.py`, `src/services/qa_dispatcher.py`, `src/services/rag_runtime.py`, `src/core/validators.py`, `src/core/nodes/persistence.py` và `docs/ADDRESSBRIDGE.md`, `docs/RAG_SERVICE.md` là các điểm đối chiếu theo module; kiểm lại đường dẫn thực bằng repo map trước sửa. Facade `vietmap_client.py` tiếp tục tương thích tới khi migration được duyệt. Repo hiện có guard số nhà/ngõ và AddressBridge tùy chọn; rewrite phải giữ kết quả an toàn, không cần giữ nguyên graph/heuristic. [Traceability](12_SOURCE_TRACEABILITY.md) phân biệt phần kế thừa và phần thử nghiệm.
