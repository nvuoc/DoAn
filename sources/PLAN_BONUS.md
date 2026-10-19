Bản kế hoạch `TAXI-AI-SRS-002` (v2.0) có nền tảng kiến trúc kỹ thuật rất vững chắc: tách biệt rõ ràng giữa NLU (Qwen3.8-27B), bộ suy diễn trạng thái tất định (`StateReducer`), `Policy Engine` và các adapter ngoại vi. Việc giữ nguyên `raw_text` làm nguồn dữ liệu gốc cho tài xế, dùng `Dialogue Acts` thay vì đơn thuần phân loại Intent, và thiết kế `Test Factory` 3 tầng theo hướng *sinh ngữ nghĩa trước, câu chữ sau* là những quyết định hoàn toàn chính xác cho bài toán tổng đài.

Tuy nhiên, đặt trong bối cảnh **khẩu ngữ tiếng Việt đa dạng và văn bản đầu vào bị biến dạng nặng do lỗi ASR (phát âm sai, nhiễu nền, tiếng ồn, cắt câu sai)**, bản thiết kế hiện tại đang giả định văn bản đầu vào tương đối "sạch" về mặt cấu trúc câu. Để hệ thống đạt độ mượt tối đa trước hàng vạn biến thể thực tế, bạn cần tối ưu **6 điểm cốt lõi** dưới đây.

---

## 1. Bổ sung cơ chế "Phục hồi ngữ âm theo ngữ cảnh" (Contextual ASR Recovery) ngay tại tầng NLU

Hiện tại, luồng xử lý đưa thẳng `user_text` vào bước `2. UNDERSTAND (Qwen -> NLUResult)`, còn việc xử lý `phonetic_variant` (như *"tình tiền"* → *"tính tiền"*) đang đặt chủ yếu ở `LocationResolver` (§9.2, §9.3). Trong thực tế, ASR nghe nhầm ở **mọi thành phần câu** (động từ điều khiển, số lượng, thời gian, phủ định) chứ không chỉ tên địa danh.

**Vấn đề thực tế:**

* **Lỗi đồng âm/cận âm làm đảo ngược hoặc mất hành động:** *"hủy chuyến"* → ASR ra *"quỷ chiến"* / *"thủy chiến"*; *"đặt xe"* → *"đập xế"*; *"bốn chỗ"* → *"bốn rổ"* / *"bố chỗ"*; *"không đi nữa"* → *"hông đi nửa"* / *"xông đi nữa"*.
* **Xung đột với quy tắc kiểm tra Span (§7.8):** Tài liệu quy định *"kiểm `raw_value` gắn với span người dùng"*. Nếu ASR trả về *"đón ở ngỏ một ba hai cầu diễn"* hoặc *"bịnh diện một không tám"*, việc ép `raw_value` bám chặt vào chuỗi lỗi mà không có trường chuẩn hóa ngữ âm sẽ làm giảm khả năng hiểu của bước sau, hoặc ngược lại, nếu LLM tự sửa sẽ bị Validator chặn vì cho là bịa (hallucination).



**Giải pháp tối ưu:**

* **Tách 3 lớp văn bản trong `NLUResult` và `LocationInput`:**
1. `asr_raw_text`: Chuỗi nguyên gốc từ ASR/CLI (server tự gán, bất biến để lưu log/audit).


2. `phonetic_reconstructed_text`: Chuỗi đã được Qwen khôi phục dựa trên âm vị tiếng Việt và ngữ cảnh hội thoại (ví dụ: *"ngỏ một ba hai cầu diễn"* → *"ngõ 132 Cầu Diễn"*).
3. `reconstruction_confidence`: Mức độ chắc chắn khi khôi phục (`HIGH` | `MEDIUM` | `LOW`).


* **Đưa `dialogue_context` làm "mỏ neo ngữ âm" cho Qwen:** Khi `last_bot_action = ASK_VEHICLE`, nếu ASR trả về *"bố chỗ"* hoặc *"bảy chổ"*, prompt của NLU phải cho phép suy diễn ngữ âm có trọng số cao về `"4 chỗ"` / `"7 chỗ"` thay vì đẩy vào `unclear`.



---

## 2. Xử lý đặc thù "Ngôn ngữ nói thực tế" của người Việt (Side-talk, Cắt câu, Phương ngữ)

Trong giao tiếp đặt xe hằng ngày, người Việt có 3 thói quen nói chuyện khiến pipeline xử lý theo lượt đơn lẻ (single-turn reducer) dễ bị gãy:

### 2.1. Lời nói ngoài luồng / Nói với người bên cạnh (Side-talk & Background Speech)

Khách đang gọi điện thường nói vọng ra ngoài hoặc ti vi/người bên cạnh nói xen vào, ASR thu luôn vào một câu:

> *"Mình ơi lấy hộ cái áo mưa cái, đóng cửa vào... alo ừ đón anh ở viện 108 nhé"*
> hoặc: *"Con kia im để mẹ đặt xe nào, cho chị đi Bách Khoa em ơi"*

* **Rủi ro hiện tại:** Qwen có thể trích xuất nhầm *"đóng cửa"* hoặc bị nhiễu dẫn đến đánh nhãn `unclear` / `needs_clarification`.


* **Tối ưu:** Thêm một bước lọc hoặc thuộc tính trong `NLUResult`: `ignored_spans` (các đoạn hội thoại ngoài luồng/tiếng ồn nền như tiếng rao, tiếng TV, nói chuyện với người thứ ba). Hướng dẫn rõ trong NLU Prompt: chỉ trích xuất `dialogue_acts` từ phần văn bản hướng tới tổng đài viên.

### 2.2. Câu nói bị cắt làm đôi (Fragmented Utterances / Incremental Slot)

Dù V1 là CLI text-to-text, người dùng chat nhanh (hoặc giả lập luồng streaming ASR bị VAD ngắt giữa chừng khi khách ngập ngừng nghĩ số nhà) sẽ tạo ra các lượt liên tiếp bổ sung cho nhau:

* Lượt 1: *"Đón anh ở số 18 ngách 16"*
* Lượt 2: *"ngõ 51 đường Nguyễn Khánh Toàn nhé"*
* Lượt 3: *"à đối diện quán phở Lý Quốc Sư ấy"*
* **Rủi ro hiện tại:** Bộ `Dialogue Acts` hiện chỉ có `SET_SLOT`, `REPLACE_SLOT`, `CLEAR_SLOT` (§7.2). Nếu ở Lượt 2 model phát sinh `SET_SLOT` hoặc `REPLACE_SLOT(origin)`, `StateReducer` sẽ **ghi đè** mất *"số 18 ngách 16"* ở Lượt 1 và làm mất hiệu lực các xác nhận liên quan.


* **Tối ưu:** Bổ sung bắt buộc hành động **`APPEND_OR_REFINE_SLOT`** (hoặc `MERGE_SLOT_COMPONENT`) vào Ontology (§7.2) và `StateReducer` (§18.2). Khi khách bổ sung cấp hành chính/ngõ/mốc cho cùng một địa điểm, hệ thống hợp nhất các thành phần (`house_number` + `sub_alley` + `alley` + `street` + `landmark`) thay vì xóa cũ ghi mới.



### 2.3. Chuẩn hóa Số đếm, Giờ giấc và Phương ngữ 3 miền

Người Việt nói số nhà, số điện thoại, thời gian và địa chỉ cực kỳ linh hoạt, cộng thêm lỗi ASR:

* **Số khẩu ngữ:** *"một ba hai"* (132), *"hai mốt"* (21), *"hai lăm/hai nhăm"* (25), *"chục người"* (10), *"rưỡi"*, *"kém mười"*, *"hơn tiếng"*.
* **Từ vựng vùng miền:**
* Miền Bắc: *ngõ, ngách, hẻm, nút giao, bến*.
* Miền Trung: *kiệt, hẻm, bùng binh, mô, tê, răng, rứa, chừ (bây giờ)*.
* Miền Nam: *hẻm, xuyệt (`/` - ví dụ "hẻm một hai ba xuyệt bốn" = 123/4), vòng xoay, cầu vượt, trển, bển, hông (không), nghen*.


* **Tối ưu:** Xây dựng một module **Deterministic Vietnamese Spoken Normalizer** chạy song song với NLU để quy đổi từ chỉ phân số/địa chỉ (đặc biệt là cấu trúc *"xuyệt"* `/`, số đọc rời từng chữ số, giờ giấc tương đối) về dạng chuẩn cấu trúc trước khi đưa vào `GeoResolver` hay `Validator`.

---

## 3. Nâng cấp `LocationResolver`: Tìm kiếm bất biến theo Âm vị (Phonetic & Sub-word Search)

Trong §9.2, pipeline của `LocationResolver` đã có bước `alias / historical / phonetic / fuzzy / typo variants`. Tuy nhiên, với địa danh Việt Nam khi qua ASR lỗi, fuzzy matching thông thường (như Levenshtein distance / `rapidfuzz` trên mặt chữ Latin) **sẽ thất bại nặng** vì một âm tiết tiếng Việt nghe nhầm có thể khác hoàn toàn mặt chữ:

* *Ví dụ:* *"Khuất Duy Tiến"* → ASR nghe thành *"Quất Duy Tuyến"* hoặc *"Phất Duy Tiến"*; *"Keangnam"* → *"Kang Nam"* / *"Canh Nam"* / *"Căng Nam"*; *"Cầu Diễn"* → *"Cầu Diện"* / *"Tàu Diễn"*.

**Giải pháp tối ưu cho §9.2 & §9.7:**

1. **Mã hóa âm vị tiếng Việt (Vietnamese Phonetic Indexing / Vni-Soundex):** Chuyển đổi cả query và catalog nội bộ sang dạng mã âm vị (quy chuẩn hóa các phụ âm đầu dễ lẫn như `c/k/qu`, `d/gi/r`, `ch/tr`, `s/x`, `l/n`, `v/d`; nguyên âm và thanh điệu gần nhau như `hỏi/ngã`, `sắc/nặng`).
2. **Cơ chế "Anchor + Phonetic Match":** Khi khách nói *"đón ở ngõ 132 tàu diễn"*, hệ thống nhận diện `ngõ 132` là mỏ neo cấu trúc cứng (structural anchor), sau đó tìm các con đường có âm tiết gần với `"tàu diễn"` mà thực tế có `ngõ 132` (hoặc nằm trong vùng địa lý đang xét), từ đó khớp chính xác ra **Cầu Diễn**.
3. **Tách biệt lỗi ASR tên đường vs. địa chỉ không có trên Map:** Khi Vietmap Autocomplete trả về rỗng cho *"ngõ 132 tàu diễn"*, đừng vội chuyển sang `TEXT_ONLY` ngay; hãy thử truy vấn lại Vietmap bằng các biến thể âm vị của tên đường (`"Cầu Diễn"`), nhưng **vẫn giữ nguyên ghi chú gốc** cho tài xế nếu khách không xác nhận.



---

## 4. Chiến lược "Làm rõ thích ứng" (Adaptive Clarification) thay vì chỉ đếm lượt

Mục §8.6, §9.6 và §11.6 đặt `max_location_clarification_attempts: 2`. Nếu môi trường của khách đang ồn hoặc khách nói ngọng/phát âm địa phương đặc trưng, việc hỏi lại câu tương tự lần 2 chỉ khiến ASR lặp lại đúng lỗi cũ, làm khách bực mình (*"đã bảo là...", "nghe kém thế"*).

**Giải pháp tối ưu cho §12.5 & §8.2:**
Thiết kế ma trận chuyển đổi cách hỏi theo từng bậc (Progressive Escalation):

* **Lần 1 (Khi thiếu hoặc ASR độ tin cậy thấp):** Hỏi mở hoặc hỏi thu hẹp vùng (*"Anh/chị cho em xin lại tên đường hoặc phường ở khu vực đó ạ?"*).


* **Lần 2 (Khi vẫn nhiễu trên cùng một thực thể):**
* Nếu có ứng viên âm vị gần đúng: Chuyển sang **câu hỏi đóng Có/Không** (*"Do đường truyền hơi ồn, có phải anh/chị nói đường **Cầu Diễn** không ạ?"*) — vì ASR nhận diện từ *"Đúng/Phải/Không"* chính xác hơn nhiều so với nhận diện lại tên riêng.
* Nếu không có ứng viên nào: Đổi sang hỏi **mốc lớn/loại địa điểm** (*"Chỗ mình đứng có gần chợ, trường học hay tòa nhà lớn nào không ạ?"*).




* **Khi chấp nhận `TEXT_ONLY` để điều xe (§9.1, §13.4):** Nếu ASR có dấu hiệu nhiễu âm thanh (câu văn rời rạc, vô nghĩa một phần), trước khi lưu `TEXT_ONLY` cho tài xế, bot nên đọc nhẩm lại địa chỉ đã nghe được trong câu tóm tắt xác nhận cuối cùng để khách kiểm tra, tránh lưu một chuỗi ASR sai hoàn toàn (*"đón ở ngõ 132 tàu chiến"*) gửi cho tài xế.

---

## 5. Tinh chỉnh Luật phân biệt "Phủ định / Sửa ý / Từ ngữ đệm" khi ASR mất từ

Mục §7.5 đã xử lý tốt các câu chuẩn như *"Thôi không đi Hạ Long nữa, đi Ocean Park"*. Nhưng trong khẩu ngữ kết hợp ASR lỗi, từ phủ định và từ đệm rất dễ bị nuốt hoặc biến dạng:

* *"Thôi khi đi nữa đi chơi đi"* (Seed #2 trong Phụ lục A — chữ *"không"* bị ASR biến thành *"khi"*).


* *"Đón ở viện 108... à quên... viện 103"* (không dùng từ *"không"* hay *"đổi"*, chỉ dùng từ cảm thán *"à quên"*, *"nhầm"*, *"ý lộn"*, *"à nhầm"*).
* *"Không, đi Ocean Park cơ"* (sau khi bot hỏi xác nhận đi Hạ Long).

**Giải pháp tối ưu:**

* Mở rộng bộ dấu hiệu tự sửa lỗi (Self-repair markers) trong NLU và Test Generator: ngoài *"à không"*, *"thôi"*, cần bao phủ *"à quên"*, *"nhầm"*, *"ý anh là"*, *"lộn"*, *"đính chính lại"*, *"cơ"*, *"chứ không phải"*.
* **Cảnh báo xung đột Slot ngầm (Implicit Slot Collision):** Nếu trong cùng một lượt hoặc hai lượt sát nhau, khách nêu hai địa điểm cùng đóng vai trò điểm đón (hoặc điểm đến) mà từ nối giữa chúng bị ASR làm hỏng (ví dụ: *"đi Hạ Long khỉ gió đi Hải Phòng"*), `Validator` không được tự ý lấy cái cuối nếu mức độ bất định cao (`uncertainty_flags` có `ASR_CORRUPTED_CONNECTOR`), mà phải hỏi xác nhận ngắn: *"Anh/chị muốn đi Hải Phòng thay vì Hạ Long đúng không ạ?"*.

---

## 6. Nâng cấp `Test Factory` (§14, §15): Phá bỏ giới hạn của Mutator hiện tại

Bạn đã lưu ý rất đúng rằng 64 câu mẫu chỉ là hạt cát so với thực tế. Nhìn vào thiết kế `Test Factory` ở §14.2 và §15.2, có **2 điểm đang tự trói tay bộ sinh test** khiến nó chưa tạo ra được các ca khó nhất của ASR:

1. **Gỡ bỏ ràng buộc quá an toàn của `TYPO_ASR_SIM`:**
* Trong bảng §15.2, quy tắc của `TYPO_ASR_SIM` đang ghi: *"Bảo toàn entity số/ngõ, đánh dấu noise"*.


* **Thực tế:** Lỗi nguy hiểm nhất của ASR chính là nghe nhầm số và ngõ (*"ngõ 51"* → *"ngỏ năm mốt"*, *"ngõ 15"*, *"mõ 51"*; *"4 chỗ"* → *"bố chỗ"*). Nếu cấm Mutator chạm vào entity số/ngõ, hệ thống sẽ không bao giờ được test khả năng khôi phục hoặc hỏi lại khi địa chỉ/số lượng bị méo!


2. **Tách `ASR_NOISE_MUTATOR` thành 5 cấp độ biến dạng độc lập:**
Thay vì một `TYPO_ASR_SIM` chung chung, bạn nên thiết kế bộ sinh lỗi âm thanh/văn bản thành các phép biến đổi chuyên biệt có gắn nhãn kỳ vọng (`Oracle Policy`) rõ ràng:



| Cấp độ Mutator mới | Mô tả kỹ thuật mô phỏng lỗi nói/ASR Việt Nam | Kỳ vọng hành vi hệ thống (Expected Oracle) |
| --- | --- | --- |
| **`M1_DIALECT_COLLOQUIAL`** | Thay từ vựng vùng miền, số đếm khẩu ngữ (*"ngõ"* $\leftrightarrow$ *"hẻm/kiệt/xuyệt"*, *"55"* $\leftrightarrow$ *"năm nhăm"*, *"không"* $\leftrightarrow$ *"hông"*). | **Hiểu chính xác 100%** như câu chuẩn, không được hỏi lại. |
| **`M2_PHONETIC_CONFUSION`** | Thay thế âm tiết đồng âm/cận âm trên cả động từ lệnh và tên POI (*"Việt Yên"* $\rightarrow$ *"Diệt Yên"*, *"tính tiền"* $\rightarrow$ *"tình tiền"*, *"viện"* $\rightarrow$ *"diện"*).

 | Khôi phục được qua ngữ cảnh + Phonetic Index; nếu là địa điểm thì tạo candidate để `CONFIRM_GEO_CANDIDATE`.

 |
| **`M3_WORD_DROP_TRUNCATION`** | Rơi từ đầu/cuối câu hoặc mất từ phủ định do VAD cắt sớm (*"không đặt nữa"* $\rightarrow$ *"đặt nữa"* hoặc *"thôi khi đi nữa"*).

 | Khi mất từ khóa làm đảo nghĩa hoặc câu gãy ngữ pháp: kích hoạt `needs_clarification=true`, **tuyệt đối không tự submit/cancel**.

 |
| **`M4_BACKGROUND_SIDETALK`** | Chèn câu nói chuyện với người thứ 3, tiếng TV, tiếng chửi thề/cảm thán vào đầu/giữa câu đặt xe. | Lọc bỏ nhiễu (`ignored_spans`), chỉ trích xuất đúng `dialogue_acts` của việc đặt xe. |
| **`M5_SPLIT_TURN_VAD`** | Tách 1 câu cung cấp địa chỉ dài thành 2–3 lượt liên tiếp (mô phỏng khách vừa nói vừa nghĩ). | Sử dụng `APPEND_OR_REFINE_SLOT` để ghép đủ số nhà + ngách + ngõ + đường + mốc mà không ghi đè mất dữ liệu lượt trước. |

---

## Tóm tắt các chỉnh sửa cần cập nhật ngay vào `PLAN.md`

Để đội kỹ thuật (hoặc AI Coding Agent) có thể code ngay mà không bị vướng:

1. **Tại §6.2 & §7.8 (Schemas):** Thêm `asr_raw_text`, `normalized_spoken_text`, `phonetic_confidence`, và `ignored_spans` vào `NLUResult`; cho phép `LocationInput` lưu song song chuỗi gốc và chuỗi đã chuẩn hóa số/âm vị.


2. **Tại §7.2 & §18.2 (Acts & Reducer):** Thêm act `APPEND_OR_REFINE_SLOT` (gộp thông tin địa chỉ/ghi chú qua nhiều lượt) bên cạnh `SET_SLOT` và `REPLACE_SLOT`.


3. **Tại §9.2 (LocationResolver):** Bắt buộc tích hợp bộ mã hóa âm vị tiếng Việt (Vietnamese Phonetic Key) và chuẩn hóa cấu trúc địa chỉ khẩu ngữ (*"xuyệt"*, số đọc rời) trước khi gọi Vietmap hoặc tìm trong catalog.


4. **Tại §12.2 & §12.5 (Templates & Clarification):** Phân cấp template hỏi lại theo nguyên tắc: *Hỏi mở $\rightarrow$ Hỏi đóng xác nhận âm vị (Yes/No) $\rightarrow$ Hỏi mốc lân cận $\rightarrow$ Ghi nhận mô tả/Handoff*.


5. **Tại §15.2 (Test Factory Mutators):** Nâng cấp `TYPO_ASR_SIM` thành 5 mutator chuyên biệt (`M1` đến `M5` như bảng trên) và cho phép biến đổi cả số nhà/ngõ/từ phủ định để kiểm thử khả năng phòng vệ của hệ thống.



Bạn có muốn tôi viết chi tiết **bộ quy tắc chuyển đổi âm vị & chuẩn hóa khẩu ngữ tiếng Việt** (dưới dạng đặc tả thuật toán hoặc cấu hình YAML) cùng **cập nhật schema `NLUResult` / `Mutators**` để bạn chèn trực tiếp vào bản `PLAN.md` này không?


Phần **đánh giá tổng thể** ở câu trả lời trước đã hoàn tất. Để bạn có thể áp dụng ngay mà không mất thêm bước chờ đợi, dưới đây là **bản đặc tả kỹ thuật chi tiết (dạng drop-in dùng để chèn thẳng vào `PLAN.md`)** cho toàn bộ 6 hạng mục tối ưu đã nêu, giúp coding agent lập trình chính xác khả năng chống nhiễu ASR và xử lý khẩu ngữ tiếng Việt.

---

## BẢN BỔ SUNG ĐẶC TẢ KỸ THUẬT (PATCH CHO `PLAN.md` LÊN V2.1)

### 1. Cập nhật §6.2 & §7.8: Schema `NLUResult` và `LocationInput` hỗ trợ phục hồi lỗi ASR

Thay vì chỉ lưu `raw_user_text` và kiểm tra span cứng trên bề mặt chữ, schema NLU và Location được mở rộng để tách bạch **văn bản ASR thô** và **văn bản đã khôi phục âm vị**:

```json
{
  "schema_version": "2.1",
  "primary_intent": "provide_info",
  "sub_intent": null,
  "asr_raw_text": "ừ con kia im nào đón anh ở ngỏ một ba hai tàu diễn nhé",
  "ignored_spans": [
    {"text": "con kia im nào", "reason": "BACKGROUND_SIDETALK"}
  ],
  "phonetic_reconstructed_text": "ừ đón anh ở ngõ 132 Cầu Diễn nhé",
  "reconstruction_confidence": "HIGH",
  "dialogue_acts": [
    {
      "type": "SET_SLOT",
      "slot": "origin",
      "raw_value": "ngỏ một ba hai tàu diễn",
      "normalized_value": "ngõ 132 Cầu Diễn",
      "phonetic_candidates": ["ngõ 132 Cầu Diễn"],
      "confidence": "MEDIUM"
    }
  ],
  "place_mentions": [
    {
      "raw_text": "ngỏ một ba hai tàu diễn",
      "reconstructed_text": "ngõ 132 Cầu Diễn",
      "usage": "BOOKING_ORIGIN",
      "resolution": "UNRESOLVED"
    }
  ],
  "needs_clarification": false,
  "uncertainty_flags": ["PHONETIC_RECONSTRUCTED_PLACE"]
}

```

Quy tắc cho `VALIDATE_NLU` (bổ sung §3.1 & §7.8):

* `asr_raw_text` luôn do server gán trực tiếp từ đầu vào, không tin chuỗi do LLM chép lại.


* Cho phép `normalized_value` khác mặt chữ với `raw_value` nếu và chỉ nếu: (1) khoảng cách âm vị tiếng Việt (`vni_phonetic_distance`) nhỏ hơn ngưỡng cấu hình, hoặc (2) nằm trong bộ quy tắc chuẩn hóa số/địa chỉ khẩu ngữ.
* Mọi đoạn nằm trong `ignored_spans` (nói chuyện với người bên cạnh, tiếng TV/nhạc/tiếng rao lọt vào mic) bị loại bỏ hoàn toàn trước khi kiểm tra xung đột slot.
* Cập nhật các cờ `uncertainty_flags` chuẩn:
* `PHONETIC_RECONSTRUCTED_PLACE`: Địa danh đã được khôi phục từ âm gần giống (cần xác nhận nhẹ hoặc đối chiếu catalog).
* `ASR_CORRUPTED_CONNECTOR`: Câu có 2 thực thể cùng loại slot nhưng từ nối/từ phủ định ở giữa bị nhiễu (ví dụ: *"đi Hạ Long khỉ gió đi Hải Phòng"*).
* `TRUNCATED_UTTERANCE`: Câu có dấu hiệu bị cắt cụt đầu/cuối làm mất chủ ngữ/vị ngữ quan trọng hoặc mất từ phủ định.



---

### 2. Cập nhật §7.2 & §18.2: Bổ sung `APPEND_OR_REFINE_SLOT` và Hợp nhất Địa chỉ phân mảnh

Để xử lý trường hợp khách nói ngắt quãng qua nhiều lượt (hoặc VAD cắt câu sớm) mà không làm mất thông tin đã cung cấp ở lượt trước như khi dùng `REPLACE_SLOT`:

#### 2.1. Bổ sung vào bảng Dialogue Acts (§7.2)



| Act | Payload | Hệ quả |
| --- | --- | --- |
| `APPEND_OR_REFINE_SLOT` | `slot`, `component_type`, `raw_value`, `normalized_value` | Bổ sung thành phần còn thiếu (số nhà, ngách, ngõ, đường, phường, mốc `driver_note`) vào `origin` hoặc `destination` hiện tại; **giữ nguyên các thành phần đã có** nếu không mâu thuẫn cấp hành chính. |

#### 2.2. Cập nhật thuật toán `StateReducer` (§18.2)



```python
# Bổ sung vào pseudo: dialogue/reducer.py
def apply_slot_refinement(state, act):
    target_loc = getattr(state.booking, act.slot)  # origin hoặc destination
    # 1. Nối raw_text có dấu phân cách để bảo toàn nguyên văn lời khách cho tài xế
    if target_loc.raw_text:
        target_loc.raw_text = f"{target_loc.raw_text}, {act.raw_value}"
    else:
        target_loc.raw_text = act.raw_value

    # 2. Hợp nhất từng thành phần địa chỉ (house_number, sub_alley, alley, street, ward, district, landmark)
    for comp_key, comp_val in act.extracted_components.items():
        if comp_val is not None:
            target_loc.address_components[comp_key] = comp_val

    # 3. Nếu chỉ bổ sung chi tiết nhỏ (số nhà, ngách, mốc đón) trong cùng khu vực đã khớp:
    # KHÔNG xóa vùng địa lý cha đã xác minh, chỉ yêu cầu re-rank precision_level
    if act.component_type in {"HOUSE_NUMBER", "LANDMARK", "DRIVER_NOTE"}:
        target_loc.driver_note = merge_notes(target_loc.driver_note, act.raw_value)
    else:
        target_loc.geo_resolution_status = "NEEDS_RECHECK"
        invalidate_dependent_estimate_and_confirmations(state, act)

```

---

### 3. Bổ sung §9.2 & §9.3: Bộ Chuẩn hóa Khẩu ngữ 3 Miền & Mã hóa Âm vị Tiếng Việt (`VniPhonetic`)

Trước khi đưa văn bản vào tìm kiếm ứng viên trên Vietmap hoặc Catalog nội bộ, `LocationResolver` chạy qua 2 tầng tiền xử lý tất định (deterministic):

#### 3.1. Cấu hình Chuẩn hóa Khẩu ngữ Tiếng Việt (`config/spoken_normalizer.vi.yaml`)

```yaml
address_structure_rules:
  # Miền Nam / Miền Trung: "hẻm 123 xuyệt 4 xuyệt 5" -> "hẻm 123/4/5"
  - pattern: '(?i)\b(hẻm|kiệt|ngõ|số)\s+(\d+(?:\s+xuyệt\s+\d+)+)\b'
    transform: "SLASH_JOIN"
  # Đọc rời từng số nhà/ngõ: "ngõ một ba hai" -> "ngõ 132", "ăm mốt" -> "51", "hai nhăm" -> "25"
  - pattern: 'SPOKEN_VIETNAMESE_DIGITS'
    transform: "VI_WORDS_TO_NUMBER"

regional_synonyms:
  alley: ["ngõ", "hẻm", "kiệt"]
  sub_alley: ["ngách", "hẻm phụ", "xuyệt"]
  roundabout: ["vòng xuyến", "bùng binh", "vòng xoay", "ngã sáu", "nút giao"]
  negation: ["không", "hông", "kô", "chả", "chẳng", "khỏi", "đừng"]
  self_repair: ["à không", "à quên", "à nhầm", "ý lộn", "nhầm", "đổi lại", "chứ không phải"]

asr_command_homophones:
  cancel_intent: ["hủy chuyến", "quỷ chiến", "thủy chiến", "hỉ chuyến", "không đặt nữa", "hông đặt nửa", "thôi khi đi nữa"]
  fare_query: ["tính tiền", "tình tiền", "tín tiền", "nhiêu tiền", "bao nhiêu lúa", "hết nhiêu"]
  vehicle_4_seat: ["4 chỗ", "bốn chỗ", "bố chỗ", "bốn rổ", "xe nhỏ"]
  vehicle_7_seat: ["7 chỗ", "bảy chỗ", "bẩy chỗ", "bảy rổ", "xe rộng", "xe to"]

```

#### 3.2. Thuật toán Mã hóa Âm vị Tiếng Việt (`src/taxi_ai/geo/phonetic.py`)

Dùng để đánh chỉ mục (index) toàn bộ tên đường, phường/xã, POI trong catalog và so khớp khi ASR trả về từ sai chính tả hoặc sai âm vùng miền:

```python
# Thuật toán quy chuẩn âm vị tiếng Việt về khóa đại diện (Phonetic Skeleton)
INITIAL_CONSONANT_GROUPS = {
    "c": "K", "k": "K", "qu": "K",
    "d": "Z", "gi": "Z", "r": "Z", "v": "Z",     # Gộp d/gi/r/v (lỗi phát âm phổ biến Bắc/Nam)
    "ch": "C", "tr": "C",                        # Gộp ch/tr
    "s": "S", "x": "S",                          # Gộp s/x
    "l": "N", "n": "N",                          # Gộp l/n
    "ng": "NG", "ngh": "NG",
    "g": "G", "gh": "G",
    "ph": "F", "th": "T", "t": "T", "nh": "NH", "kh": "KH", "h": "H", "b": "B", "m": "M", "đ": "D"
}

RHYME_CONFUSION_GROUPS = {
    # Gộp các vần đuôi n/ng, t/c, t/ch thường bị lẫn trong ASR và phương ngữ
    "inh": "IN", "in": "IN", "ênh": "EN", "ên": "EN",
    "ang": "AN", "an": "AN", "ăng": "ĂN", "ăn": "ĂN", "âng": "ÂN", "ân": "ÂN",
    "ông": "ÔN", "ôn": "ÔN", "ung": "UN", "un": "UN",
    "ương": "ƯƠN", "ươn": "ƯƠN", "iêng": "IÊN", "iên": "IÊN", "uông": "UÔN", "uôn": "UÔN",
    "ac": "AT", "at": "AT", "ăc": "ĂT", "ăt": "ĂT", "âc": "ÂT", "ât": "ÂT",
    "oc": "OT", "ot": "OT", "ôc": "ÔT", "ôt": "ÔT", "uc": "UT", "ut": "UT",
    "ich": "IT", "it": "IT", "êch": "ÊT", "êt": "ÊT", "ach": "AT"
}

TONE_GROUPS = {
    "ngang": "1", "huyền": "2",
    "hỏi": "3", "ngã": "3",      # Gộp hỏi/ngã
    "sắc": "4", "nặng": "4"      # Gộp sắc/nặng khi so khớp nới lỏng
}

```

* **Ví dụ hoạt động:**
* `"Cầu Diễn"` và `"Tàu Diễn"` / `"Cầu Diện"` có độ tương đồng âm vị rất cao trên âm tiết thứ 2 (`Z-IÊN-3` vs `Z-IÊN-4`), kết hợp với mỏ neo cấu trúc `"ngõ 132"` sẽ giúp `LocationResolver` tìm ra ứng viên `"Ngõ 132 Cầu Diễn"` dù Vietmap tìm chính xác chữ `"Tàu Diễn"` trả về rỗng.



---

### 4. Cập nhật §8.2, §12.2 & §12.5: Chiến lược Làm rõ Thích ứng (Progressive Escalation)

Thay vì hỏi lặp lại câu hỏi mở tối đa 2 lần rồi chuyển người thật, `ActionPlanner` (§8.2) và `Templates` (§12.2) chuyển đổi hình thức câu hỏi theo mức độ nhiễu của ASR:

#### 4.1. Bảng điều phối làm rõ theo bậc

| Bậc | Tình huống kích hoạt | Hành động của Planner | Mục tiêu chống lỗi ASR |
| --- | --- | --- | --- |
| **Bậc 1** | Thiếu thông tin khu vực hoặc có nhiều chi nhánh trùng tên (`Vincom`).

 | `ASK_LOCATION_DISCRIMINATOR`: Hỏi thêm tên quận/phường hoặc đường lớn.

 | Thu hẹp không gian tìm kiếm. |
| **Bậc 2A** | ASR bị nhiễu âm nhưng `PhoneticResolver` tìm được 1 ứng viên có điểm khớp cao (ví dụ nghe *"tàu diễn"* đoán là *"Cầu Diễn"*). | `CONFIRM_PHONETIC_CANDIDATE`: Hỏi câu đóng **Đúng/Không**. | Khách chỉ cần nói *"Đúng/Ừ/Phải"*, tránh bắt khách phát âm lại tên đường khó nghe. |
| **Bậc 2B** | Hai địa điểm xung đột trong 1 câu do từ nối bị nhiễu (`ASR_CORRUPTED_CONNECTOR`). | `CLARIFY_SLOT_COLLISION`: Hỏi chọn 1 trong 2. | Tránh ghi đè sai điểm đón/đến. |
| **Bậc 2C** | Không tìm được ứng viên nào sau lần hỏi 1. | `ASK_NEARBY_LANDMARK`: Hỏi mốc lớn (chợ, trường, ủy ban, sân bóng).

 | Chuyển từ tên riêng khó nghe sang danh từ chung + mốc phổ biến. |
| **Bậc 3** | Vẫn không khớp tọa độ nhưng hãng cho phép `allow_text_only_pickup_request=true`.

 | `ACCEPT_TEXT_WITH_READBACK`: Ghi nhận mô tả và đọc lại chuỗi đã nghe trong bước xác nhận chuyến. | Đảm bảo chuỗi văn bản gửi cho tài xế không phải là chuỗi rác do ASR bịa. |

#### 4.2. Bổ sung vào `config/templates.vi.yaml` (§12.2)



```yaml
CONFIRM_PHONETIC_CANDIDATE:
  short: ["Ý anh/chị là {candidate_name} đúng không ạ?"]
  normal: ["Do tín hiệu hơi nhiễu, có phải anh/chị muốn nói đến {candidate_name} ở {verified_area} không ạ?"]
CLARIFY_SLOT_COLLISION:
  short: ["Anh/chị chốt đi {place_b} hay {place_a} ạ?"]
  normal: ["Em nghe chưa rõ lắm, anh/chị muốn đặt xe đến {place_b} thay cho {place_a} đúng không ạ?"]
ACCEPT_TEXT_WITH_READBACK:
  normal: ["Em xin ghi nhận điểm đón theo mô tả là “{reconstructed_address}” để tài xế liên hệ trực tiếp khi tới khu vực nhé."]

```

---

### 5. Cập nhật §15.2: Đặc tả 5 Mutators chuyên biệt cho `Test Factory`

Thay thế dòng `TYPO_ASR_SIM` đơn giản trong bảng §15.2 bằng 5 nhóm Mutator sinh dữ liệu kiểm thử tự động có kiểm soát chặt chẽ về `Oracle`:

| Mã Mutator | Biến đổi trên dữ liệu đầu vào | Giữ nguyên nghĩa gốc? | Quy tắc cập nhật Oracle (Expected Behavior) |
| --- | --- | --- | --- |
| **`M1_DIALECT_AND_SPOKEN_NUM`** | Chuyển số thành chữ đọc rời/khẩu ngữ (*"132"* $\rightarrow$ *"một ba hai"*, *"25"* $\rightarrow$ *"hai nhăm"*), thay *"ngõ/ngách"* bằng *"hẻm/kiệt/xuyệt"*, thêm từ đệm 3 miền (*"nghen", "rứa", "nhá"*). | **Có** | `expected_state_delta` giữ nguyên 100% giá trị chuẩn hóa; cấm sinh hành động hỏi lại không cần thiết. |
| **`M2_PHONETIC_ASR_CORRUPTION`** | Thay thế 1–2 âm tiết trong động từ lệnh hoặc tên địa danh bằng âm tiết cùng nhóm `VniPhonetic` (*"Cầu Diễn"* $\rightarrow$ *"Tàu Diễn"*, *"Việt Yên"* $\rightarrow$ *"Diệt Yên"*, *"tính tiền"* $\rightarrow$ *"tình tiền"*).

 | **Có (cần xác minh)** | Nếu biến đổi trên câu lệnh: giữ nguyên Act. Nếu biến đổi trên địa danh: cho phép `LocationResolver` trả về đúng ứng viên gốc nhưng bắt buộc qua bước `CONFIRM_PHONETIC_CANDIDATE` hoặc giữ `uncertainty_flags`. |
| **`M3_VAD_TRUNCATION_AND_DROP`** | Cắt mất 1–2 từ đầu/cuối câu hoặc làm hỏng từ phủ định (*"không đặt nữa"* $\rightarrow$ *"khi đặt nữa"* / *"đặt nữa"*). | **Không (Mơ hồ)** | Oracle tự động chuyển sang `needs_clarification=true`; `forbidden_actions` bắt buộc chứa `[SUBMIT_BOOKING, CANCEL_BOOKING]`.

 |
| **`M4_SIDETALK_INJECTION`** | Ghép ngẫu nhiên một câu hội thoại gia đình/tiếng rao/tiếng ồn văn bản vào đầu hoặc giữa câu gốc (ví dụ: *"Alo con lấy cho mẹ cái túi, cho chị đặt xe đi Hạ Long"*). | **Có** | Oracle giữ nguyên các `dialogue_acts` của câu gốc; kiểm tra hệ thống không trích xuất nhầm danh từ trong câu nhiễu vào bất kỳ slot nào. |
| **`M5_MULTI_TURN_FRAGMENTATION`** | Tách một câu cung cấp địa chỉ đầy đủ (`số nhà + ngách + ngõ + đường + mốc`) thành 2 hoặc 3 lượt liên tiếp trong kịch bản L3.

 | **Có (sau khi ghép)** | Ở lượt cuối, `booking.origin.address_components` phải chứa đầy đủ tất cả thành phần của các lượt trước cộng lại thông qua `APPEND_OR_REFINE_SLOT`, không bị mất số nhà/ngõ của lượt đầu. |

---

### 6. Bổ sung vào Checklist nghiệm thu (§19.1)



Bạn có thể chép thêm 5 gạch đầu dòng này vào cuối mục **§19.1 Acceptance checklist (MUST)** trong `PLAN.md`:

* [ ] Câu có hội thoại người thứ ba xen vào (*"con đóng cửa vào đi, đón anh ở viện 108"*) chỉ trích xuất slot đặt xe, bỏ qua phần nói chuyện bên ngoài (`ignored_spans`).
* [ ] Khách đọc địa chỉ ngắt làm nhiều lượt liên tiếp (lượt 1 nói số nhà/ngõ, lượt 2 nói tên đường/phường, lượt 3 nói mốc) được hợp nhất đầy đủ bằng `APPEND_OR_REFINE_SLOT`, không bị ghi đè mất thông tin lượt trước.
* [ ] Địa chỉ khẩu ngữ 3 miền (*"hẻm một hai ba xuyệt bốn"*, *"kiệt năm mốt"*, *"ngõ một ba hai"*) được chuẩn hóa chính xác về cấu trúc số (`123/4`, `51`, `132`) đồng thời vẫn giữ nguyên `raw_text`.


* [ ] Khi tên đường bị lỗi âm vị ASR (*"ngõ 132 tàu diễn"*), `LocationResolver` tìm ra ứng viên âm vị (`Cầu Diễn`) và hỏi xác nhận đóng (`CONFIRM_PHONETIC_CANDIDATE`), không trả lời trắng là không biết cũng không tự ý đổi ngầm mà không báo khách.
* [ ] Bộ sinh kiểm thử (`Test Factory`) chạy đủ 5 mutators `M1`–`M5` với seed cố định, đảm bảo các ca mất từ phủ định hoặc nhiễu từ nối không bao giờ gây tự động đặt/hủy chuyến.


Đối chiếu với các yêu cầu nghiệp vụ và 3 ví dụ thực tế bạn vừa nêu, bản kế hoạch `PLAN.md` hiện tại (kể cả sau bản patch trước) **mới giải quyết được khoảng 50–60% bài toán** và vẫn còn những "điểm mù" thiết kế khiến bot hành xử cứng nhắc hoặc xử lý sai trong thực tế.

Dưới đây là đánh giá thẳng thắn từng điểm chưa đạt trong kế hoạch hiện tại và **phương án thiết kế tối ưu** để giải quyết triệt để mọi trường hợp bạn đặt ra.

---

## PHẦN 1: ĐÁNH GIÁ HIỆN TRẠNG & CÁC ĐIỂM CẦN ĐẬP ĐI XÂY LẠI TRONG KẾ HOẠCH

### 1.1. Loại bỏ hoàn toàn "tọa độ chính xác" & Áp dụng "Bất đối xứng Điểm Đón – Điểm Đến"

* **Điểm nghẽn trong `PLAN.md` hiện tại:**
* Đang dùng chung một cấu trúc đánh giá độ chính xác (`precision_level`: `EXACT_POI`, `ENTRANCE`, `ALLEY`...) cho cả Điểm Đón (`origin`) và Điểm Đến (`destination`).


* Ở §13.1 và Phụ lục A (câu #1, #4), khi khách nói *"Cho tôi đi Hạ Long"* hoặc *"đi Ocean Park"*, kế hoạch vẫn ghi chú *"Hạ Long là vùng rộng"*, *"xác minh dự án/khu vực"*. Điều này trái với thực tế: với **Điểm Đến**, khách gọi tổng đài chỉ cần nói *"đi Hạ Long"*, *"đi sân bay"*, *"đi Ocean Park"*, *"đi Viện 108"* là **ĐỦ** — lên xe khách sẽ tự bảo tài xế đỗ ở cổng nào hay phường nào.




* **Thiết kế tối ưu cần cập nhật (Asymmetric Location Policy):**
* **Xóa bỏ khái niệm tọa độ chính xác của khách:** Mọi tọa độ lấy từ Vietmap chỉ mang vai trò duy nhất là **`anchor_coordinate` (Tọa độ mỏ neo đại diện)** để tính khoảng cách/giá ước lượng.
* **Tách 2 thước đo hoàn toàn khác nhau cho Điểm Đón và Điểm Đến:**



| Tiêu chí | Điểm Đón (`origin` — Cần `PICKUP_VIABLE`) | Điểm Đến (`destination` — Chỉ cần `ROUTE_ESTIMABLE`) |
| --- | --- | --- |
| **Mục tiêu thực tế** | Tài xế phải chạy xe tới gần đó và nhìn thấy khách hoặc gọi điện đón được.

 | Chỉ cần biết vùng đích/tâm điểm để ước lượng km và biết có thuộc vùng phục vụ không.

 |
| **Mức độ chi tiết yêu cầu** | **Cần chi tiết vừa đủ:** Tên đường + đoạn/ngõ/số nhà HOẶC Tên POI cụ thể + mốc/cổng (nếu POI quá rộng như cả khu đô thị). Không chấp nhận chỉ nói tên Quận/Phường/Thành phố. | **Chấp nhận điểm lớn / vùng đại diện:** Chấp nhận ngay tên Thành phố/Thị xã/Khu du lịch (*"Hạ Long", "Nha Trang", "Đồ Sơn"*), Khu đô thị (*"Ocean Park"*), Sân bay, Bệnh viện mà **không hỏi vặn cổng/tòa/phường**. |
| **Xử lý địa danh cũ sau sáp nhập (Hạ Long, Nha Trang...)** | Nếu khách nói *"Đón tôi ở Hạ Long"* $\rightarrow$ **Phải hỏi thêm** đường/phường/khách sạn nào vì quá rộng, tài xế không biết đón ở đâu. | Nếu khách nói *"Cho tôi đi Hạ Long"* $\rightarrow$ **Chốt luôn điểm đến**, tự động gắn `anchor_coordinate` vào tâm hành chính/du lịch của TP. Hạ Long cũ (ví dụ khu vực Hồng Gai/Bãi Cháy) để tính km dự kiến. |
| **Xử lý POI khổng lồ (Sân bay, Ocean Park, Viện 108)** | Hỏi thêm 1 mốc đón dễ tìm (*"Anh/chị đứng ở sảnh/cổng nào hoặc gần tòa nào để tài xế dễ đón ạ?"*). Nếu khách không biết $\rightarrow$ hướng dẫn cách nhìn xung quanh hoặc ghi chú tài xế gọi điện.

 | **Không hỏi cổng/tòa.** Chỉ hỏi khi tên đó trùng ở 2 khu vực địa lý cách xa nhau (ví dụ: *Ocean Park 1 Gia Lâm* vs *Ocean Park 2 Hưng Yên* nếu cần báo giá; còn nếu khách chỉ nói *"đi viện 108"* thì chốt luôn). |

---

### 1.2. Nguyên tắc "1 Lượt = 1 Địa chỉ" & Lược bỏ ngữ cảnh thừa (Contextual Ellipsis) như người thật

* **Điểm nghẽn trong `PLAN.md` hiện tại:**
* Template ở §12.2 đang gắn cứng: `"Có phải {verified_name} ở {verified_area} không ạ?"`. Nếu `{verified_area}` từ API trả về `"Phường Bách Khoa, Hai Bà Trưng, Hà Nội"`, câu nói của bot sẽ rất máy móc và lặp lại chữ `"Hà Nội"` dù cả cuộc hội thoại đã biết khách đang ở Hà Nội.


* Chưa có luật cấm hỏi gộp khi cả điểm đón và điểm đến đều mơ hồ trong cùng 1 câu (ví dụ: *"Cho anh đi từ Vincom ra sân bay"*).


* **Thiết kế tối ưu cần cập nhật:**
1. **Luật `SINGLE_LOCATION_FOCUS_PER_TURN` (Bắt buộc trong `ActionPlanner`):**
* Trong bất kỳ lượt trả lời nào, bot **chỉ được phép hỏi hoặc xác nhận tối đa 1 địa chỉ**.
* Thứ tự ưu tiên cứng: **Khóa xong Điểm Đón (`origin`) $\rightarrow$ rồi mới hỏi/làm rõ Điểm Đến (`destination`)** (trừ khi khách đang chủ động hỏi thông tin về điểm đến trước).


2. **Cơ chế Khấu trừ Ngữ cảnh (`ContextDiffFormatter` trong `Renderer`):**
* Hệ thống lưu `session_geo_scope` (ví dụ: `province = "Hà Nội"`, `district_or_area = "Cầu Giấy"`).
* Khi hỏi phân biệt giữa 2 ứng viên hoặc xác nhận địa chỉ, `Renderer` thực hiện phép trừ tập hợp `(Candidate_Admin_Hierarchy - Session_Geo_Scope)` để **chỉ đọc phần khác biệt nhỏ nhất**:
* *Đã biết ở Hà Nội:* Chỉ hỏi *"Anh/chị ở Dịch Vọng hay Dịch Vọng Hậu ạ?"* (Tuyệt đối không đọc *"Phường Dịch Vọng, Hà Nội hay Phường Dịch Vọng Hậu, Hà Nội"*).
* *Đã biết trên đường Cầu Diễn:* Chỉ hỏi *"Ngõ 132 phải không ạ?"*.


* **Cơ chế tự bẻ lái (Graceful Scope Override):** Nếu bot giả định đang ở Hà Nội mà khách phản hồi *"Không, ở Bắc Ninh cơ"* hoặc đọc một địa danh thuộc tỉnh khác, `StateReducer` lập tức cập nhật lại `session_geo_scope = "Bắc Ninh"` và tìm lại từ đầu mà không báo lỗi.





---

## PHẦN 2: PHƯƠNG ÁN XỬ LÝ CHI TIẾT CHO 3 VÍ DỤ THỰC TẾ CỦA BẠN

### Ví dụ 1: Khách đứng ở nơi xa lạ, không biết là đâu, chỉ nhìn xung quanh và mô tả bằng lời

> **Hiện trạng `PLAN.md`:** Mới chỉ dừng ở việc hỏi *"Anh có nhớ gần đường hoặc chợ nào không ạ?"* (§12.2). Nếu khách ở nơi hoàn toàn xa lạ, họ không biết tên đường hay tên chợ nên câu hỏi này sẽ đi vào ngõ cụt.
> 
> 

**Giải pháp bổ sung vào kế hoạch — Nghiệp vụ "Hướng dẫn tìm manh mối tại chỗ" (`VISUAL_CLUE_COACHING`):**
Khi khách nói *"Tôi không biết chỗ này là đâu / Lạ lắm / Xung quanh toàn nhà là nhà"*, bot sẽ đóng vai một tổng đài viên kinh nghiệm, hướng dẫn khách tìm thông tin theo **3 cách thực tế nhất ở Việt Nam**:

1. **Cách 1 — Hướng dẫn đọc chân biển hiệu (Hiệu quả nhất ở Việt Nam):**
* *Lời bot:* *"Anh/chị nhìn thử xung quanh xem có biển hiệu cửa hàng, hiệu thuốc hay quán ăn nào gần nhất không ạ? Thường ở góc dưới biển hiệu sẽ có ghi sẵn số nhà và tên đường đấy ạ."*


2. **Cách 2 — Định vị bằng Giao cắt 2 biển hiệu cạnh nhau (`CO_LOCATED_POI_SEARCH`):**
* Nếu khách chỉ nhìn thấy tên quán mà không đọc được chữ nhỏ ghi địa chỉ (ví dụ: *"Trước mặt tôi có cái Điện Máy Xanh, bên cạnh là ngân hàng Agribank"*).
* `LocationResolver` không tìm từng cái riêng lẻ mà chạy truy vấn **Giao cắt không gian (Spatial Intersection)**: Tìm trong vùng/thành phố đang xét điểm nào có *Điện Máy Xanh* nằm trong bán kính `< 100m` so với *Agribank*. Nếu chỉ có 1 cụm như vậy $\rightarrow$ xác định được ngay tuyến đường để báo khách xác nhận!


3. **Cách 3 — Nhờ người xung quanh hoặc chốt mô tả + Tài xế gọi điện:**
* Nếu khách đứng ở đoạn đường trống không có biển hiệu: *"Anh/chị có thể hỏi nhanh người đi đường gần đó tên đường hoặc tên thôn/xóm giúp em được không ạ? Hoặc anh/chị nói sơ qua đặc điểm chỗ mình đứng để tài xế gọi điện trao đổi trực tiếp nhé."*



---

### Ví dụ 2: Khách đọc nhầm số ngõ không có thật trên một con đường có thật (Bẫy Vietmap Autocomplete)

> **Hiện trạng `PLAN.md`:** Đang mặc định rằng nếu địa chỉ không có thì API trả về rỗng (§9.4).
> **Thực tế bạn chỉ ra hoàn toàn chính xác:** Nếu đường Cầu Diễn không có "Ngõ 185", nhưng khách đọc *"Ngõ 185 Cầu Diễn"*, Vietmap Autocomplete v4 **vẫn trả về danh sách kết quả** là các ngõ có thật gần giống trên đường Cầu Diễn (như *Ngõ 18, Ngõ 85, Ngõ 180 Cầu Diễn*) hoặc trả về tâm đường *Cầu Diễn*! Nếu lấy kết quả đầu tiên của Vietmap thì bot sẽ điều xe sai ngõ.
> 
> 

**Giải pháp bổ sung vào kế hoạch — Kiểm tra đối xứng số hiệu & Chế độ "Tin khách có cảnh báo" (`ALLEY_MISMATCH_POLICY`):**

Thiết kế một bước kiểm tra bắt buộc sau khi gọi Vietmap trong `LocationResolver`:

```text
Khách nói: "Ngõ [X] Đường [Y]"
   │
   ├─► Vietmap trả về các ứng viên trên Đường [Y]
   │
   ├─► BƯỚC KIỂM TRA SỐ NGÕ (Deterministic Number Guard):
   │     So sánh chính xác chuỗi số [X] của khách với số ngõ trong kết quả Vietmap.
   │
   ├── TH1: Có ứng viên khớp đúng Ngõ [X] Đường [Y]
   │        -> Chấp nhận bình thường.
   │
   ├── TH2: Đường [Y] khớp, nhưng KHÔNG có Ngõ [X] trên Vietmap:
   │    │
   │    ├─► Nhánh 2A (Nghi ngờ ASR nghe nhầm hoặc khách nói líu lưỡi):
   │    │   Nếu trên Đường [Y] của Vietmap có ngõ [X'] rất gần về âm đọc hoặc đảo số
   │    │   (VD: khách nói "ngõ 123" hoặc "một hai ba", map chỉ có "ngõ 132"; hoặc nói "58" map có "85"):
   │    │   -> Bot hỏi nhẹ 1 câu:
   │    │      "Trên đường [Y] bản đồ bên em đang hiện ngõ [X'] chứ chưa thấy ngõ [X],
   │    │       anh/chị kiểm tra giúp em là ngõ [X] hay [X'] ạ?"
   │    │
   │    └─► Nhánh 2B (Khách khẳng định đúng Ngõ [X] HOẶC không có ngõ nào gần âm):
   │        -> TUYỆT ĐỐI TIN KHÁCH (vì bản đồ số thường thiếu ngõ mới/ngõ phụ ngoài đời).
   │        -> Xử lý 3 việc cùng lúc:
   │           1. Giữ nguyên `origin.raw_text = "Ngõ [X] Đường [Y]"` để gửi cho tài xế.
   │           2. Lấy tọa độ của `Đường [Y]` (hoặc ngõ liền kề gần nhất theo số thứ tự) làm tọa độ ước lượng km.
   │           3. Gắn cờ cảnh báo vào cuốc xe: `dispatch_warnings = ["UNVERIFIED_ALLEY_ON_MAP"]`
   │              (Ghi chú cho tài xế: "Khách báo ngõ [X] đường [Y] - chưa có trên map, tài xế lưu ý gọi khách khi tới đường [Y]").

```

---

### Ví dụ 3: Khách phát âm sai tên nước ngoài ("Aeon Mall" $\rightarrow$ "e on mô", "Ocean Park" $\rightarrow$ "ô sừn bắc") hoặc ASR nghe nhầm tên ngắn ("Bệnh viện E" $\rightarrow$ "bệnh viện em")

> **Hiện trạng `PLAN.md` (và bản patch trước):** Thuật toán `VniPhonetic` ở bản patch trước chỉ quy đổi âm vị dựa trên **mặt chữ tiếng Việt**. Nó giải quyết được *"Cầu Diễn"* $\leftrightarrow$ *"Tàu Diễn"*, nhưng **sẽ thất bại** với:
> 1. **Tên tiếng Anh đọc theo kiểu Việt hóa:** Mặt chữ `"Aeon Mall"` không có bất kỳ sự tương đồng chữ cái nào với `"e on mô"`, `"Ocean Park"` khác hẳn `"ô sừn bắc"`, `"Royal City"` khác hẳn `"roi ồ xi ti"`.
> 2. **Tên chữ cái đơn bị ASR "tự sửa lưng" (ASR Hallucination):** Các bộ ASR tiếng Việt thường được huấn luyện để ưu tiên từ có nghĩa trong câu. Khi khách nói *"Bệnh viện E"*, chữ *"E"* đứng cuối rất dễ bị mô hình ngôn ngữ của ASR tự sửa thành *"Bệnh viện em"* / *"Bệnh viện đê"*; hoặc *"Bệnh viện K"* thành *"Bệnh viện ca"* / *"Bệnh viện cá"*.
> 
> 

**Giải pháp bổ sung vào kế hoạch — 3 Lớp Giải mã Tên riêng Đặc thù (`Foreign & Short-Entity Phonetic Resolver`):**

#### Lớp 1: Đánh chỉ mục "Phiên âm bồi tiếng Việt" (Viet-lish Transliteration Index) cho mọi POI tên nước ngoài

Khi khởi tạo Catalog POI hoặc đồng bộ địa điểm nổi tiếng, hệ thống không chỉ lưu tên gốc (`name: "Aeon Mall"`) mà tự động chạy qua một bộ **Chuyển đổi cách đọc tiếng Anh sang âm tiết tiếng Việt (G2P Viet-lish Generator)** để lưu vào trường `spoken_aliases`:

| Tên gốc trên bản đồ | Các biến thể âm đọc người Việt / ASR thường sinh ra (`spoken_aliases`) |
| --- | --- |
| **Aeon Mall** | `e on mô`, `i on mô`, `ê on môn`, `a e on`, `i ông mô`, `siêu thị nhật` |
| **Ocean Park** | `ô sừn bắc`, `ô sần pác`, `âu sừn pác`, `ô sin bắc`, `ô sừn pắc` |
| **Keangnam** | `keng nam`, `căng nam`, `canh nam`, `khang nam`, `tòa nhà 72 tầng` |
| **Royal City** | `roi ồ xi ti`, `rôi ồ`, `rô i an xi ti`, `khu hoàng gia` |
| **Times City** | `tham xi ti`, `tham si ti`, `thời đại` |
| **Big C (GO!)** | `bích xi`, `bíc si`, `bi xi` |
| **Lotte (Center/Mall)** | `lót te`, `lốt te`, `nót te` |
| **TechnoPark** | `tếch nô bắc`, `tách nô pác`, `téc nô pắc` |
| **Smart City** | `sờ mát xi ti`, `xì mát xi ti`, `mát xi ti` |

*Cách chạy:* Ngay cả với một tòa nhà tiếng Anh mới tinh chưa có trong từ điển viết tay, bộ chuyển đổi quy tắc phát âm tiếng Anh sang tiếng Việt (ví dụ: `park` $\rightarrow$ `pác/bắc`, `mall` $\rightarrow$ `mô/môn`, `city` $\rightarrow$ `xi ti`, `tower` $\rightarrow$ `thao ơ`, `building` $\rightarrow$ `biu đinh`, `plaza` $\rightarrow$ `pờ la da`, `garden` $\rightarrow$ `ga đừn`) sẽ tự động sinh khóa âm vị tiếng Việt để bắt trúng văn bản lỗi từ ASR!

#### Lớp 2: Bộ bắt lỗi "Từ đơn âm & Chữ cái" bị ASR biến dạng (`Single-Letter Entity Guard`)

Dành riêng cho các địa danh Việt Nam dùng chữ cái hoặc từ ngắn: *Bệnh viện E, Bệnh viện K, Cổng A/B/C, Tòa S1/S2, Khu D...*

* **Quy tắc nhận diện:** Khi NLU bắt được cụm `[Danh từ loại địa điểm: bệnh viện / viện / tòa / cổng / khu / nhà] + [Từ thông thường vô lý trong ngữ cảnh địa danh: em, anh, ca, cá, cờ, đê, bi, bê, ép...]`.
* **Cơ chế khôi phục:** Hệ thống tra bảng tương đương âm thanh chữ cái tiếng Việt:
* `"bệnh viện em"` / `"bệnh viện e"` / `"viện e"` $\xrightarrow{\text{khớp âm đầu /e/}}$ **`Bệnh viện E`**
* `"bệnh viện ca"` / `"bệnh viện cá"` $\xrightarrow{\text{khớp âm /ka/}}$ **`Bệnh viện K`**
* `"tòa bi"` / `"tòa bê"` $\xrightarrow{\text{khớp âm /b/}}$ **`Tòa B`**


* **Hành vi của Bot:**
* Nếu độ tin cậy ngữ cảnh rất cao (hoặc là Điểm Đến và chỉ có 1 Bệnh viện E ở Hà Nội): Tự động hiểu là **Bệnh viện E**, khi tóm tắt chuyến đi thì đọc lại tên chuẩn (*"Dạ đi Bệnh viện E..."*) để khách nghe và yên tâm.
* Nếu là Điểm Đón hoặc có khả năng nhầm với nơi khác: Hỏi nhẹ *"Ý anh/chị là Bệnh viện E ở Trần Cung phải không ạ?"*.



#### Lớp 3: Tận dụng chính LLM (Qwen3.8-27B) làm bộ giải mã ngữ âm ngược trong Prompt NLU

Thay vì để `LocationResolver` tự bơi một mình với chuỗi lỗi, ta đưa nhiệm vụ **"Đọc thành tiếng trong đầu để đoán tên địa danh"** vào thẳng bước `2. UNDERSTAND` của Qwen:

* Trong JSON schema của `place_mentions` (§7.8), yêu cầu Qwen xuất thêm trường `phonetic_guess_canonical_name`:


* Khi khách/ASR nhập: `"cho tôi đi ô sừn bắc"` $\rightarrow$ Qwen dễ dàng suy luận theo ngữ cảnh đặt xe tại Việt Nam và trả về:
* `raw_text`: `"ô sừn bắc"`
* `phonetic_guess_canonical_name`: `"Vinhomes Ocean Park"`


* Sau đó `LocationResolver` sẽ tìm kiếm trên Vietmap bằng cả `"Vinhomes Ocean Park"` lẫn `"ô sừn bắc"`. Điều này giúp giải quyết hàng ngàn tên địa danh tiếng nước ngoài hoặc tên nói lái mà không cần hardcode từng từ một!



---

## TÓM TẮT: BẠN CẦN CẬP NHẬT GÌ VÀO `PLAN.md`?

Nếu bạn đồng ý với hướng xử lý này, bản kế hoạch của bạn chỉ cần chốt thêm **5 quy tắc vàng** sau vào mục **§9 (Bài toán địa chỉ Việt Nam)** và **§12 (Template & Câu hỏi làm rõ)**:

1. **Quy tắc Bất đối xứng (`PICKUP_VIABLE` vs `ROUTE_ESTIMABLE`):**
* **Điểm đến (`destination`):** Chấp nhận ngay các POI lớn, thành phố/vùng du lịch quen thuộc (kể cả tên cũ trước sáp nhập như *Hạ Long, Nha Trang*), khu đô thị, sân bay, bệnh viện mà **không hỏi cổng/tòa/phường**. Tự gán vào tâm đại diện (`anchor_coordinate`) chỉ để tính khoảng cách tương đối.
* **Điểm đón (`origin`):** Cần đủ chi tiết để tài xế tìm được (đường + ngõ/đoạn/mốc, hoặc POI + cổng/tòa/mốc).


2. **Quy tắc Hỏi tự nhiên như người thật (`SINGLE_FOCUS` & `CONTEXT_ELLIPSIS`):**
* Mỗi lượt chỉ hỏi làm rõ **1 địa chỉ** (ưu tiên xong Điểm Đón mới hỏi Điểm Đến).
* Lược bỏ toàn bộ tên Tỉnh/Thành phố/Quận đã biết trong ngữ cảnh khi đặt câu hỏi (chỉ hỏi phần xã/phường/đường khác biệt). Nếu khách sửa lại tỉnh/thành khác thì mới mở rộng lại phạm vi.


3. **Quy tắc Hướng dẫn khách ở nơi xa lạ (`VISUAL_CLUE_COACHING`):**
* Khi khách không biết mình đang ở đâu: hướng dẫn khách nhìn **địa chỉ ghi ở dòng dưới cùng của biển hiệu cửa hàng/quán ăn/hiệu thuốc trước mặt**, hoặc đọc tên **2 biển hiệu cạnh nhau** để hệ thống tìm điểm giao cắt, hoặc chốt mô tả để tài xế gọi điện.


4. **Quy tắc Đối chiếu Số ngõ & Tin tưởng khách (`ALLEY_MISMATCH_POLICY`):**
* Không lấy bừa kết quả Autocomplete của Vietmap khi số ngõ trả về khác số ngõ khách đọc.
* Nếu có số ngõ gần âm/đảo số trên cùng con đường $\rightarrow$ hỏi khách kiểm tra lại 1 lần. Nếu khách khẳng định đúng số ngõ đó (hoặc không có số gần âm) $\rightarrow$ **tin khách**, giữ nguyên văn bản số ngõ cho tài xế, lấy tọa độ đường làm mốc ước lượng km và gắn cờ `UNVERIFIED_ALLEY_ON_MAP` cho cuốc xe.


5. **Quy tắc Giải mã Phiên âm bồi & Chữ cái đơn (`VIET_LISH_AND_LETTER_GUARD`):**
* Kết hợp Qwen `phonetic_guess_canonical_name` + bộ quy tắc phiên âm tiếng Anh sang tiếng Việt (*"e on mô"* $\rightarrow$ *Aeon Mall*, *"ô sừn bắc"* $\rightarrow$ *Ocean Park*) + bộ bảo vệ tên chữ cái đơn (*"bệnh viện em"* $\rightarrow$ *Bệnh viện E*, *"bệnh viện ca"* $\rightarrow$ *Bệnh viện K*).



Bạn thấy phương án xử lý cho các trường hợp trên đã sát với đúng mong muốn vận hành thực tế của bạn chưa, hay cần điều chỉnh thêm ở chi tiết nào nữa?


Hai nỗi sợ của bạn đánh trúng vào **hai điểm dễ gãy nhất** khi kết hợp tìm kiếm bản đồ (Search/Map API) với xử lý lỗi ASR và quản lý hội thoại (Dialogue Management):

1. **Bẫy "Khớp chữ chính xác nhưng sai độ phổ biến" (Exact-Text Trap):** ASR nghe nhầm một địa điểm lớn thành một từ có thật nhưng là ngõ nhỏ/cửa hàng nhỏ, rồi Map API ưu tiên kết quả khớp 100% mặt chữ đó thay vì địa điểm lớn.
2. **Bẫy "Đứt gãy ngữ cảnh khi khách lưỡng lự / hỏi ngược lại" (Context Loss on Hesitation/Counter-Question):** Khi bot đang chờ khách trả lời *"Đúng/Không"* cho một địa điểm mà khách lại ngập ngừng (*"ờ khoan đã, chỗ đấy ở quận nào nhỉ?"*) thì bot có bị quên mất việc xác nhận trước đó không.

Dưới đây là câu trả lời chi tiết về hiện trạng và **cơ chế thiết kế bổ sung** để khóa chặt hai trường hợp này.

---

## VẤN ĐỀ 1: Làm sao để Bot luôn ưu tiên Địa điểm lớn/phổ biến, không bị ASR đánh lừa sang địa điểm nhỏ có tên gần giống?

### 1.1. Hiện trạng trong kế hoạch (Vì sao vẫn có nguy cơ chọn sai?)

Trong `PLAN.md` (§9.2 & §9.7), hệ thống đã có khái niệm ưu tiên `PARENT_POI` (khu đô thị, bệnh viện, trường đại học) hơn `CHILD_POI` (cửa hàng bên trong) và có tín hiệu `độ phổ biến`.
**Tuy nhiên, lỗ hổng nằm ở chỗ:** Nếu thuẫn túy gọi Vietmap Autocomplete bằng chuỗi ASR lỗi, hoặc nếu xếp hạng theo kiểu *"Khớp chính xác mặt chữ (Exact Match) luôn thắng Khớp gần đúng âm vị (Phonetic Match)"*, hệ thống sẽ bị dính bẫy sau:

* **Ví dụ thực tế 1:** Khách nói *"Cho tôi đi **Viện K**"*, ASR nghe nhầm thành *"Cho tôi đi **Viện Ca**"*. Trên bản đồ hoặc dữ liệu địa điểm có một cơ sở nhỏ tên là *"Thẩm mỹ viện Ca"* hoặc *"Phòng khám Viện Ca"*. Vì chữ `"Viện Ca"` khớp 100% mặt chữ với câu ASR, bộ xếp hạng thông thường sẽ chọn *"Thẩm mỹ viện Ca"* thay vì **Bệnh viện K** (dù Bệnh viện K lớn gấp vạn lần).
* **Ví dụ thực tế 2:** Khách hỏi *"Trường **Bách Khoa** ở đâu?"*, ASR nghe thành *"Đường **Bách Hoa** ở đâu?"*. Nếu trên bản đồ có một con ngõ/cửa hàng nhỏ tên *Bách Hoa*, bot sẽ trả lời về con ngõ đó thay vì hiểu khách đang hỏi **Đại học Bách Khoa**.
* **Ví dụ thực tế 3 (Địa giới sáp nhập):** Khách hỏi *"Phường **Bích Động** giờ thành gì?"*, ASR nghe thành *"Đường **Bích Động**"*. Bot lại đi tìm tên đường thay vì tra cứu đơn vị hành chính cấp Phường/Thị trấn vừa sáp nhập.



### 1.2. Giải pháp tối ưu: Thuật toán "Trọng số Độ nổi tiếng đè bẹp Khớp mặt chữ" (Prominence-Weighted Phonetic Ranking)

Để bot luôn hành xử giống não bộ của một tài xế taxi lâu năm, bộ `Ranker` trong `src/taxi_ai/geo/ranker.py` và `KnowledgeService` phải chấm điểm ứng viên theo công thức **Ưu tiên Phân tầng (Tiered Prominence)** thay vì chỉ dựa vào độ giống mặt chữ:

#### Bước 1: Phân hạng Địa điểm thành 4 Cấp độ Phổ biến (`Prominence Tier`)

Mọi địa điểm trong Catalog nội bộ và kết quả phân loại từ Map được gắn cứng hệ số trọng số phổ biến ($W_{\text{tier}}$):

* **Tier 1 — Cấp Quốc gia / Tỉnh / Thành phố / Điểm nóng Taxi ($W = 1.0$):** Sân bay, Bến xe lớn, Ga tàu, Bệnh viện tuyến TW/Tỉnh (Viện 108, Viện K, Bạch Mai, Chợ Rẫy...), Đại học lớn, Khu đô thị lớn (Ocean Park, Smart City, Royal City...), Danh lam thắng cảnh/Thành phố du lịch (Hạ Long, Nha Trang, Lăng Bác...), và các **Đơn vị hành chính (Quận/Huyện/Phường/Xã cũ & mới)**.


* **Tier 2 — Cấp Khu vực / Thương hiệu Chuỗi lớn ($W = 0.75$):** Trung tâm thương mại (Aeon Mall, Vincom, Lotte, Big C/GO!), Khách sạn lớn, Tòa nhà văn phòng nổi tiếng (Keangnam, TechnoPark), Trục đường chính.


* **Tier 3 — Cấp Địa phương ($W = 0.4$):** Trường tiểu học/THCS, Chợ dân sinh, Ủy ban phường, Sân bóng làng, Ngõ lớn.


* **Tier 4 — Cấp Vi mô / Cửa hàng nhỏ lẻ ($W = 0.1$):** Quán ăn nhỏ, tiệm tạp hóa, công ty TNHH tư nhân trong ngõ, ngách nhỏ.

#### Bước 2: Quy tắc "Vượt cấp Âm vị" (Phonetic Promotion Rule)

Khi khách hỏi thông tin (*"ở đâu", "thuộc phường nào", "sau sáp nhập thế nào"*) hoặc đặt điểm đến:

1. Hệ thống luôn tìm kiếm **đồng thời** trên cả 2 luồng: (A) Khớp mặt chữ (`raw_text`) và (B) Khớp âm vị/phiên âm (`phonetic_reconstructed_text` trên tập `Tier 1 + Tier 2`).
2. Tính điểm tổng hợp cho mỗi ứng viên $c$:

$$\text{Score}(c) = \alpha \cdot \text{PhoneticSim}(u, c) + \beta \cdot W_{\text{tier}}(c) + \gamma \cdot \text{ContextMatch}(c)$$


3. **Luật quyết định cứng (Anti-Noise Rule):**
* Nếu một ứng viên **Tier 4 (nhỏ lẻ)** khớp 100% mặt chữ với chuỗi ASR (ví dụ `"Phòng khám Viện Ca"`), NHƯNG có một ứng viên **Tier 1 (địa điểm lớn)** khớp $\ge 85\%$ về mặt âm vị (ví dụ `"Bệnh viện K"`): **Ứng viên Tier 1 luôn được xếp số 1!**
* **Cách bot trả lời khách:**
* *Nếu khách đang hỏi thông tin / địa giới sáp nhập:* Bot trả lời thẳng vào địa điểm lớn (hoặc đơn vị hành chính lớn) kèm câu dẫn tự nhiên: *"Với **Bệnh viện K**, hiện tại viện có cơ sở chính ở..."* hoặc *"Nếu anh/chị đang hỏi **phường Bích Động** (Việt Yên, Bắc Ninh), thì sau sáp nhập..."*.
* *Nếu khách đang đặt xe mà âm bị lệch:* Bot hỏi xác nhận ưu tiên điểm lớn trước: *"Ý anh/chị là **Bệnh viện K** đúng không ạ?"*. Chỉ khi khách bảo *"Không, tôi đi thẩm mỹ viện Ca cơ"* thì bot mới hạ xuống chọn ứng viên Tier 4 (nhờ cơ chế `rejected_candidate_ids` đã có trong §9.3).







---

## VẤN ĐỀ 2: Khi Bot đang hỏi xác nhận mà khách lưỡng lự hoặc hỏi ngược lại ("ở đâu", "quận nào"...), Bot có bị mất ngữ cảnh không?

### 2.1. Hiện trạng trong kế hoạch (Lỗ hổng ở đâu?)

Trong `PLAN.md` hiện tại:

* Đã có quy tắc rất tốt là: Câu hỏi thông tin (`ASK_INFORMATION`) không được làm thay đổi các slot đã lưu trong `booking` (§7.4 & §8.6 Invariant 1).


* NHƯNG còn 2 điểm mù khi đang ở trạng thái `pending_confirmation` (§6.3, §7.6, §8.3):


1. **Thiếu hành động cho sự "Lưỡng lự / Chưa chắc chắn" (`HESITATION / UNCERTAIN`):** Ở §7.6 mới chỉ chia ra `"vâng/đúng"` (`CONFIRM_PENDING`), `"không đúng"` (`REJECT_PENDING`), và `"tôi không biết/chịu"` (`DECLINE_TO_ANSWER`). Thực tế khách hay nói: *"Ờ... hình như thế"*, *"Tôi cũng không rõ có phải cơ sở đấy không"*, *"Khoan đã, để xem lại"*, *"Ủa chỗ đó nằm ở đường nào nhỉ?"*. Nếu ép vào `REJECT` hay `DECLINE` thì sẽ làm hỏng mất ứng viên đúng đang chờ xác nhận!


2. **Mất nhịp quay lại xác nhận sau khi giải đáp thắc mắc (Missing Re-prompt Hook):** Khi bot đang hỏi *"Anh muốn đi Vincom Bà Triệu đúng không ạ?"* (`pending_confirmation` đang mở), khách không trả lời Đúng/Sai mà hỏi ngược lại: *"Vincom Bà Triệu giờ thuộc phường nào thế?"* hoặc *"Chỗ đấy cách đây bao xa?"*. Theo luồng hiện tại (§8.2), bot trả lời xong câu hỏi của khách nhưng **chưa có quy tắc bắt buộc giữ nguyên `pending_confirmation` và khéo léo nối lại câu hỏi xác nhận ở cuối câu trả lời**.





### 2.2. Giải pháp tối ưu: Cơ chế "Ngăn xếp Tạm dừng & Nối mạch" (`Pending Confirmation Hold & Resume`)

Để hội thoại mượt như người thật khi khách ngập ngừng hoặc hỏi xen ngang, cần bổ sung 3 quy tắc sau vào `DialogueContext` (§6.2) và `ActionPlanner` (§8.2):

#### Quy tắc 1: Bổ sung Act `EXPRESS_UNCERTAINTY` (Khách lưỡng lự về ứng viên bot đưa ra)

Khi bot hỏi: *"Ý anh/chị là Bệnh viện K cơ sở Tân Triều phải không ạ?"*, nếu khách trả lời lưỡng lự:

* *"Ơ tôi cũng không chắc nữa, chỉ biết người nhà bảo ở gần Hà Đông ấy"*
* *"Hình như thế, chỗ nào mà to to ấy"*
* **Xử lý của StateReducer:**
* **Tuyệt đối không hủy (`REJECT`)** ứng viên `Bệnh viện K Tân Triều`.
* Giữ nguyên `pending_confirmation`, đồng thời lấy thông tin phụ khách vừa lẩm bẩm (*"gần Hà Đông"*, *"to to"*) để kiểm chứng chéo với ứng viên đang chờ.
* Vì *Tân Triều* thực tế nằm sát *Hà Đông*, bot sẽ **củng cố niềm tin cho khách**: *"Dạ gần Hà Đông thì đúng là Bệnh viện K cơ sở Tân Triều rồi đấy ạ. Em đặt xe cho anh/chị đến đây nhé?"*



#### Quy tắc 2: Bảo toàn `pending_confirmation` khi khách hỏi ngược (Side-Question on Pending Target)

Khi đang có `pending_confirmation` (ví dụ xác nhận địa điểm A hoặc xác nhận đặt chuyến) mà khách đặt câu hỏi (`ASK_INFORMATION` về địa chỉ, địa giới sáp nhập, khoảng cách, giá tiền của chính điểm đó hoặc một điểm khác):

1. **Trạng thái `pending_confirmation` chuyển sang `ON_HOLD` (Tạm giữ), KHÔNG bị xóa và KHÔNG bị `INVALIDATED**` (vì chưa có slot nào bị sửa đổi).


2. **Quy chiếu đại từ tự động:** Nếu khách hỏi *"Thế chỗ đấy ở đường nào?"*, *"Trước sáp nhập nó là xã nào?"*, bộ giải tham chiếu (§7.7) tự động trỏ chữ *"chỗ đấy / nó"* vào thẳng `pending_confirmation.candidate` đang treo.


3. **Cấu trúc câu trả lời "Trả lời trước – Nối mạch sau" (Answer & Bridge Back):**
`Renderer` sẽ ghép kết quả tra cứu với một vế nhắc nhẹ lại việc đang dang dở:

> **Ví dụ minh họa luồng hội thoại mượt mà:**
> * **KHÁCH:** Cho anh đi Bích Động nhé.
> * **BOT:** Dạ anh muốn đi khu vực phường Bích Động ở Việt Yên phải không ạ? *(Đang mở `pending_confirmation` cho điểm đến)*
> * **KHÁCH:** Ủa khoan, tôi tưởng Bích Động là thị trấn chứ, mới đổi thành phường hay sao? *(Khách lưỡng lự + hỏi kiến thức địa giới)*
> * **BOT:** Dạ trước đây là thị trấn Bích Động, sau đợt sắp xếp đơn vị hành chính thì nâng lên thành phường Bích Động thuộc thị xã Việt Yên rồi ạ. **Vậy anh chốt đi đến đây đúng không ạ, để em xin điểm đón nhé?** *(Trả lời đúng kiến thức + Giữ nguyên mạch xác nhận!)*
> * **KHÁCH:** À thế à, ừ đúng rồi, đón anh ở Keangnam.
> * **BOT:** *(Hiểu ngay `"ừ đúng rồi"` là xác nhận `pending_confirmation` của Bích Động đang `ON_HOLD`, đồng thời điền luôn `origin = Keangnam`!)*
> 
> 

#### Quy tắc 3: Phân biệt khách "Hỏi thăm dò địa điểm mới" vs "Đổi ý ngầm"

Giả sử bot đang hỏi xác nhận: *"Anh chốt đi **Viện 108** nhé?"*, nhưng khách lại hỏi: *"À mà **Viện 103** thì ở chỗ nào em nhỉ?"*.

* **Xử lý:**
1. `booking.destination` vẫn giữ là `Viện 108`.


2. `focused_entity` tạm thời chuyển sang `Viện 103` để bot trả lời địa chỉ của Viện 103 (ở Hà Đông).


3. Sau khi trả lời xong địa chỉ Viện 103, vì khách vừa nhắc đến một bệnh viện khác cùng loại với điểm đến đang chờ xác nhận, bot sẽ hỏi câu chuyển tiếp thông minh:
*"Dạ Viện 103 thì ở đường Phùng Hưng, Hà Đông ạ. Anh vẫn giữ lịch đi **Viện 108** hay muốn đổi sang **Viện 103** ạ?"*



---

## TÓM TẮT CẬP NHẬT VÀO KẾ HOẠCH

Với bổ sung này, hệ thống của bạn sẽ giải quyết trọn vẹn cả 2 nỗi lo:

1. **Không bao giờ lấy ngõ/quán nhỏ đè lên địa điểm lớn do lỗi ASR:** Nhờ bảng phân tầng độ phổ biến (`Prominence Tier 1 -> 4`) và quy tắc **Ưu tiên Khớp âm vị Tier 1 hơn Khớp mặt chữ Tier 4** trong `LocationResolver` & `KnowledgeService`.
2. **Không bao giờ mất ngữ cảnh khi khách lưỡng lự hoặc hỏi ngang:** Nhờ trạng thái `pending_confirmation = ON_HOLD`, hành động `EXPRESS_UNCERTAINTY` (dùng lời khách ngập ngừng để kiểm chứng thêm giúp khách), và mẫu phản hồi **Trả lời + Nối mạch (Answer & Bridge Back)**.

Bạn có muốn tôi tổng hợp toàn bộ các điều chỉnh từ đầu buổi thảo luận đến giờ (gồm Chống nhiễu ASR, Bất đối xứng Đón/Đến, Ưu tiên POI lớn, và Giữ mạch xác nhận) thành một mục **Phụ lục E (hoặc cập nhật thẳng vào các mục tương ứng)** để bạn lưu vào file `PLAN.md` không?