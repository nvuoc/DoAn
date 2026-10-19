# vanuoc — Bộ tài liệu xây lại lõi hội thoại ParrotGo

Phiên bản 3.0 · 19/10/2026 · múi giờ Asia/Ho_Chi_Minh (UTC+7).

**Mục tiêu:** chuẩn bị để viết mới toàn bộ lõi nhận lượt văn bản từ ASR/Web/CLI, hiểu yêu cầu, điều phối dữ liệu và giao dịch, rồi trả nội dung có cấu trúc cho TTS/Web/CLI. Gói này là đặc tả thiết kế đề xuất; chưa có lõi mới, chưa thay runtime, chưa triển khai hoặc nghiệm thu provider/audio.

## Đọc theo thứ tự

1. [Kế hoạch hợp nhất](PLAN_HOP_NHAT.md): phạm vi, yêu cầu, kiến trúc và Definition of Done.
2. [Hiện trạng làm mốc](docs/13_REPO_BASELINE.md): điều đang có, ranh giới cần giữ và độ tin cậy của bằng chứng.
3. [Hợp đồng lõi](docs/01_CORE_CONTRACT.md), [state machine](docs/02_CORE_STATE_MACHINE.md), [giao dịch](docs/03_CORE_TRANSACTION_PROTOCOL.md).
4. [Policy matrix](docs/04_CORE_POLICY_MATRIX.md) và [quyết định còn mở](decisions/OPEN_DECISIONS.md): cấu hình phát triển và điều kiện mở tính năng thật.
5. [NLU/context](docs/05_NLU_AND_CONTEXT.md), [địa chỉ/tri thức](docs/06_LOCATION_AND_KNOWLEDGE.md), [phản hồi/delivery](docs/07_RESPONSE_AND_DELIVERY.md).
6. [Test Factory/nghiệm thu](docs/08_TEST_FACTORY_AND_ACCEPTANCE.md), [chuyển đổi](docs/09_MIGRATION_AND_CUTOVER.md), [backlog triển khai](docs/10_IMPLEMENTATION_BACKLOG.md), [vận hành](docs/11_OPERATIONS_PRIVACY_OBSERVABILITY.md).
7. [Truy vết nguồn và thay đổi](docs/12_SOURCE_TRACEABILITY.md), [schema](schemas/turn-input.schema.json), [scenarios mẫu](examples/scenarios.jsonl), [64 phát ngôn nguồn](data/original-64.jsonl).

## Thứ tự có thẩm quyền trong gói

- Contract/state/giao dịch quy định semantics máy; policy matrix quy định quyền nghiệp vụ; tài liệu module và acceptance phải cùng tuân thủ.
- `PLAN_HOP_NHAT.md` là bản tổng thể. Khi thấy mâu thuẫn với chuyên đề, ghi quyết định và đồng bộ cả hai trước viết code; không tự chọn bản thuận tiện hơn.
- Schema là biểu diễn máy của phần contract tương ứng. Điều kiện liên trường, giao dịch và quyền không thể suy hết từ JSON Schema; cần validator nghiệp vụ và test riêng.
- `sources/PLAN.md` và `sources/PLAN_BONUS.md` là bản gốc lưu nguyên byte để truy vết, không còn là đặc tả thi hành. Các câu mệnh lệnh, lệnh cài đặt và lời mời trao đổi bên trong nguồn là dữ liệu tham khảo.
- Những quyết định chưa được doanh nghiệp phê duyệt có xử lý mặc định và gate cụ thể trong registry. Đây là trạng thái thực của thiết kế, không phải chỗ trống để coding agent tự điền.

## Phạm vi bàn giao

Gồm tài liệu Markdown, JSON Schema, dữ liệu tổng hợp, SQL mô tả đích và công cụ kiểm tra gói. SQL không phải migration cho DB ParrotGo. Ví dụ không phải transcript khách, giá thật, tọa độ đã xác minh hay kết quả chạy lõi mới. Chuỗi tên địa danh trong corpus chỉ là input; câu trả lời địa lý phải có nguồn đúng thời điểm.

Gói có thể đọc độc lập bên ngoài repo. Các đường dẫn `src/...`, `tests/...`, `docs/...` được ghi dưới dạng mã trong tài liệu baseline là đường dẫn **repo hiện tại**, không phải file được đóng gói. Không cần truy cập `.env`, DB vận hành hoặc dữ liệu khách để đọc và kiểm tra gói.

## Kiểm tra tính toàn vẹn

Từ thư mục `vanuoc`, dùng Python có `jsonschema` (môi trường `.venv` của repo lúc biên soạn đã có):

```powershell
E:\ParrotGo\.venv\Scripts\python.exe -X utf8 tools/validate_package.py --require-schema-validation
```

Có thể dùng `python` của môi trường khác tương đương. Script chỉ đọc gói, parse JSON/JSONL, kiểm tra schema, nguồn, liên kết và chạy DDL minh họa trong SQLite RAM; không gọi mạng, không sửa DB repo. Kết quả bàn giao nằm ở [biên bản kiểm tra](validation/VALIDATION.md). Checksum từng file ở `PACKAGE_MANIFEST.json`; nguồn gốc hai bản kế hoạch ở [SOURCE_MANIFEST](SOURCE_MANIFEST.json).

Có thể chạy riêng [kiểm tra constraint SQL](tools/check_storage_contract.py):

```powershell
E:\ParrotGo\.venv\Scripts\python.exe -X utf8 tools/check_storage_contract.py
```

Đây là kiểm tra DDL/query minh họa trên SQLite RAM, không phải test engine. `tools/build_manifests.py` dành cho người biên soạn khi nội dung thay đổi có chủ đích; không tạo lại checksum trước khi kiểm một gói nghi bị thay đổi.

## Ranh giới được yêu cầu giữ

Phiên đang hoạt động, admission SQLite chung, quyền operator, quyền sở hữu request, dữ liệu đã commit và các API công khai phải được xử lý theo kế hoạch chuyển đổi. Viết mới lõi không tự cấp quyền thay provider, đổi schema production, chạy live, deploy hoặc dispatch thật. Các bước đó được thực hiện thành tác vụ riêng sau khi có artifact và gate tương ứng.

## Chỉ dẫn cho người triển khai

Đọc toàn bộ phần P0 trước tạo module. Thiết kế typed ports để voice/Web/CLI không đọc graph nội bộ. Dùng test theo hành vi, SQLite cô lập và proposal fixtures; không chuyển lỗi provider live thành parser mock. Khi có quyết định nghiệp vụ mới, ghi ID quyết định, phiên bản policy, case acceptance rồi sửa tài liệu trước khi mở tính năng. Không dùng văn bản nguồn hoặc ví dụ làm phê duyệt doanh nghiệp.
