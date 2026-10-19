# Registry quyết định — Không tự suy chính sách doanh nghiệp

Ngày 19/10/2026 · Không có phê duyệt sản xuất mới trong gói này. Người phụ trách được ghi theo **vai trò**, chưa gán danh tính hoặc chữ ký giả. Các baseline là quyết định thiết kế đề xuất cho phát triển, không phải bản policy vận hành hiện tại.

## 1. Cách sử dụng

Trạng thái business của POL-01…POL-10: `PENDING_BUSINESS_APPROVAL`. Các tính năng có rủi ro liên quan giữ disabled/giới hạn theo [policy matrix](../docs/04_CORE_POLICY_MATRIX.md); không chặn dựng core, fixtures, schema và sandbox synthetic. Trước connected rollout phải gán người chịu trách nhiệm thực tế, nguồn bằng chứng và phê duyệt có ngày hiệu lực; không thay trạng thái chỉ vì code hoặc test đạt.

Một quyết định được chốt cần: ID và version, câu hỏi được trả lời, lựa chọn, lý do, phạm vi/ngoại lệ, owner/reviewer, ngày hiệu lực, tài liệu nguồn, acceptance IDs và rollback. Có thể có phê duyệt tách tính năng thay vì chờ toàn bộ roadmap.

## 2. Danh sách quyết định nghiệp vụ

| ID | Quyết định cần chốt | Baseline để phát triển | Người quyết định theo vai trò | Feature bị gate và bằng chứng cần |
|---|---|---|---|---|
| POL-01 | “Thành công” là intake hay có dispatch? | request_recorded; dispatch disabled | Chủ sản phẩm + vận hành | Bật lời hứa điều xe: contract backend, states, reconcile và approved copy |
| POL-02 | Required slots, destination bắt buộc và vehicle selection | Pickup/destination/xe4 hoặc7/giờ hợp lệ; contact theo flow; passengers optional hợp lệ | Vận hành hãng | Nới required: policy bằng văn bản và tests availability/capacity/contact |
| POL-03 | Có nhận pickup chưa map verified? | Không auto booking; support request nếu có queue thật | Vận hành + điều phối | Mở text-only intake: trách nhiệm xác minh/callback, status, SLA, cách hiển thị |
| POL-04 | Mức đủ của destination vùng rộng và anchor | Giữ draft, làm rõ khi cần; chưa tự tâm vùng | Vận hành + phụ trách bản đồ | Bật broad booking/rough estimate: dataset, error ranges, approved scope |
| POL-05 | Bot được sửa/hủy sau commit tới đâu? | Tạo operator tasks, chờ authoritative result | Vận hành + phụ trách quyền | Bật mutate trực tiếp: permission, transition, fee/cancel rules, audit/retry tests |
| POL-06 | Khi nào transfer thật, callback, hay không có người? | Dựa availability adapter; không hứa khi chưa tạo thật | Quản lý tổng đài | Mở handoff: giờ trực, queue/callback path, timeout và thông báo truthful |
| POL-07 | Biểu giá, phí, cước đồng hồ và estimate có ràng buộc? | Fare unavailable khi chưa có tariff approved | Vận hành + tài chính | Mở fare: tariff version/effective date/vehicle/surcharge/thuế, source và sample tính |
| POL-08 | Lưu PII/transcript bao lâu, ai được đọc/xóa/export? | Không thêm raw operational logs; debug thật tắt; synthetic only trong gói | Chủ dữ liệu + vận hành + security | Lưu dữ liệu mới: retention/access/consent/delete/backup policy phù hợp |
| POL-09 | Scope dịch vụ và dữ liệu địa lý đủ ở đâu? | Tôn trọng config/catalog hiện có, hỏi khi thiếu tỉnh | Vận hành + phụ trách bản đồ | Mở rộng scope: danh mục/địa giới hiệu lực, provider support, ambiguity holdout |
| POL-10 | Budget, SLO, số clarification và trần chi phí | Giữ budget hiện tại làm benchmark; proposed clarification2 không tiến triển | Chủ sản phẩm + hạ tầng | Mở rollout/tăng budget: measured cold/warm1/4 load, usage/đơn giá, limit/stopping |

Không ghi một giá/địa chỉ/địa giới thật được model kể lại như bằng chứng. Không coi tên customer_reference hoặc booking ID là cấp quyền đọc đơn.

## 3. Quyết định kỹ thuật đã được đề xuất trong v3

Trạng thái nhóm này `PROPOSED_TECHNICAL_BASELINE`: đủ cụ thể để triển khai prototype, vẫn cần technical review khi bắt đầu coding. Thay khác phải có ADR và cập nhật các schema/tests phụ thuộc.

| ID | Quyết định | Lý do và điều kiện thay |
|---|---|---|
| ADR-01 | Domain SQLite transaction là authority, graph snapshot là derived | Tránh booking/checkpoint split; thay storage cần giữ atomicity/fence/rollback |
| ADR-02 | Request identity sống xuyên session; key side effect loại session ngắn hạn | Resume không tạo operation mới; thay key cần migration/dedup proof |
| ADR-03 | Whole-turn validation trước irreversible effect | Chặn confirm prefix rồi edit; thứ tự ngữ nghĩa vẫn được giữ |
| ADR-04 | Generated/committed/delivered tách; confirmation có version/delivery binding | Chặn “vâng” cho câu chưa trình bày hoặc stale |
| ADR-05 | Prepare ngoài DB lock, commit có CAS+owner+turn fence | Provider muộn không ghi; không giữ transaction khi network |
| ADR-06 | Hypothesis khác verification, prominence soft rank | Giảm ASR trap mà không làm mất POI nhỏ đúng |
| ADR-07 | Core ports typed, adapter không đọc graph/DB nội bộ | Một pipeline cho CLI/Web/voice, test/routing thay được |
| ADR-08 | Engine/config pinned theo durable request | Không đổi semantics giữa lượt/resume; new request có rollout cohort |
| ADR-09 | Shadow effect-disabled với store riêng | So sánh không tạo đơn/task/outbox trùng; live read calls vẫn cần budget |
| ADR-10 | JSON Schema chỉ kiểm shape, business validator độc lập | Không nhầm schema pass với quyền giao dịch hoặc hiểu đúng |

## 4. Những lựa chọn kỹ thuật phải đo trước chốt production

| ID | Lựa chọn | Cách tiến hành không chặn prototype |
|---|---|---|
| EXP-01 | Self-host Qwen hay provider hiện có | Giữ adapter; benchmark cùng holdout/prompt/context, latency/cost1/4; không tự đổi mode |
| EXP-02 | Phonetic skeleton/ranker/G2P tổng quát | Bắt đầu aliases reviewed; ablation exact/alias/phonetic, false auto-accept/POI nhỏ/đa vùng |
| EXP-03 | Tìm hai biển hiệu gần nhau | Fixture spatial và budget; cần dataset/recall/error trước live feature |
| EXP-04 | Grounded response generation | Template-first; thử riêng claims verifier/latency, không sinh transaction summary tùy ý |
| EXP-05 | Store schema mới và projection legacy | SQL mẫu chỉ design; rehearsal trên DB synthetic, review all writers và migration plan |
| EXP-06 | Threshold/ranking weights | Chọn bằng dev set, freeze trước holdout; không dùng 85% hay tiers như fact khoa học |

Các thử nghiệm không phải yêu cầu bật production V1. Kết quả âm hoặc thiếu bằng chứng vẫn được lưu; không đổi oracle để hợp giải pháp đã chọn.

## 5. Checklist một quyết định được chốt

1. Owner thực tế và reviewer được xác định trong tác vụ triển khai.
2. Nguồn policy/dữ liệu có version, scope, effective time và quyền sử dụng.
3. Schema/transition/response copy được cập nhật đồng bộ.
4. Gold và P0 invariant liên quan được review độc lập; tests thật chạy có manifest.
5. Compatibility/cutover/rollback có bằng chứng theo ảnh hưởng.
6. Config enable chỉ áp dụng đúng request/cohort mới; không mở giữa lượt.
7. Báo cáo tác vụ nêu điều đã/chưa kiểm chứng, không sửa báo cáo lịch sử.
