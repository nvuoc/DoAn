# Biên bản kiểm tra gói vanuoc v3.0

Ngày 19/10/2026, UTC+7. Kết quả máy đọc: [package-check.json](package-check.json) và [storage-contract-check.json](storage-contract-check.json). Đây là kiểm tra artifact thiết kế, không phải nghiệm thu runtime mới.

## Phạm vi đã kiểm

- Gói có README, kế hoạch hợp nhất, 13 chuyên đề, registry, nguồn gốc/checksum, schema, ví dụ và công cụ kiểm tra.
- Hai bản kế hoạch gốc khớp SHA-256 với lúc chụp, giữ nguyên byte. Toàn bộ **186 heading** nguồn được ánh xạ một lần sang tài liệu mới; đây là độ phủ cấu trúc, không tự chứng minh hợp nhất ngữ nghĩa tuyệt đối.
- **64 phát ngôn** được đối chiếu nguyên văn và thứ tự với Phụ lục A, giữ cả câu lặp theo ngữ cảnh.
- **4 JSON Schema**, **29 ví dụ** (3 contract và 26 scenario) hợp lệ; **11 trường hợp sai** bị từ chối, gồm control injection shape, timestamp, channel/timing, response và playback identity.
- **26 scenario tổng hợp / 93 assertions** có IDs, event/proposal/seed references nhất quán. Chúng có nhãn design review only, chưa gold và chưa chạy lõi mới.
- Tất cả liên kết Markdown nội bộ thuộc tài liệu chuẩn được kiểm; archive nguồn được giữ nguyên và không buộc sửa các URL/anchor lịch sử.
- UTF-8, replacement characters, dấu hiệu placeholder và lỗi mất chữ Việt trong fixtures được kiểm. Input hash khớp text UTF-8; final_text ghép đúng segments; question/delivery trỏ đúng response/segment.
- SQL minh họa tạo được **17 bảng** trong SQLite RAM; **16 kiểm tra** constraint/rollback/retry/CAS/owner/cancel/handoff/support và integrity/FK đạt.
- Manifest kiểm đầy đủ các file, trừ chính manifest và hai file kết quả kiểm tra sinh sau checksum đã được nêu rõ trong manifest.

Số liên kết, assertions kiểm gói và thời điểm lần chạy cuối được ghi trực tiếp trong JSON kết quả; nếu tái biên soạn, dùng kết quả máy mới thay vì giữ số cũ.

## Lệnh đã chạy từ E:\ParrotGo

```powershell
.\.venv\Scripts\python.exe -B -X utf8 .tmp/vanuoc-package-20261019/tools/check_storage_contract.py --output .tmp/vanuoc-package-20261019/validation/storage-contract-check.json
.\.venv\Scripts\python.exe -B -X utf8 .tmp/vanuoc-package-20261019/tools/build_manifests.py
.\.venv\Scripts\python.exe -B -X utf8 .tmp/vanuoc-package-20261019/tools/validate_package.py --require-schema-validation --output .tmp/vanuoc-package-20261019/validation/package-check.json
```

Sau khi xuất gói, chạy lại validator trên bản `E:\vanuoc` để kiểm checksum đường dẫn bàn giao. Công cụ không cài dependency, không gọi mạng, không import app và không chạm DB vận hành. `.venv` đang có jsonschema; validator tự đăng ký kiểm RFC3339 bằng thư viện chuẩn để không phụ thuộc format plugin tùy chọn bị thiếu.

## Các vấn đề phát hiện và đã sửa trước bàn giao

Lần kiểm đầu phát hiện BOM nằm giữa file harness được sao chép và date-time FormatChecker mặc định thiếu plugin, làm negative timestamp chưa bị từ chối. Đã bỏ BOM, dùng checker RFC3339 thực và chạy lại thành công. Đã sửa Unicode ở ví dụ JSON, đồng bộ stale-terminal/retry xuyên session/availability, thu hẹp đối soát vào read-model không authoritative, và tách handoff intent để không gộp mãi các yêu cầu hỗ trợ cùng revision.

Rà soát chéo tập trung contract/state/transaction/policy, giới hạn quyền, giả thuyết địa chỉ và các tuyên bố test/live. Không có claim rằng code/schema minh họa đã trở thành runtime hoặc policy đã được doanh nghiệp duyệt.

## Phần chưa chạy và lý do

- Không chạy runtime mới vì chưa được triển khai; không chạy 26 scenario trên một engine chưa tồn tại.
- Không chạy lại toàn suite repo trong tác vụ tài liệu; kiểm chứng 281 test của lượt phân tích trước được ghi riêng ở baseline, không cộng vào kết quả gói.
- Không gọi provider live, audio, self-host model hoặc dịch vụ bản đồ; đây là bước chuẩn bị tài liệu.
- Không chạy migration/triển khai, không commit/push và không thay cấu hình production.
- Không kiểm mạng toàn bộ URL nguồn/API hoặc phê duyệt dữ liệu/giá/retention thay doanh nghiệp; registry ghi gate còn mở.

Checksum đảm bảo toàn vẹn bản bàn giao, không phải chữ ký phê duyệt hay bằng chứng tính đúng nghiệp vụ ngoài phạm vi kiểm tra.
