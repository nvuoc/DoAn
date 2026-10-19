# Backlog triển khai và Definition of Ready

Phiên bản 3.0 · Tài liệu phân công việc, chưa phải các việc đã thực hiện. Các mốc R0–R8 trong [kế hoạch](../PLAN_HOP_NHAT.md) được chia thành lát dọc có acceptance và rollback. Không ước lượng ngày công khi chưa khóa policy/đội ngũ/phần cứng; dependency/gate là tiêu chí lập lịch.

## 1. Definition of Ready trước code

- Reviewer kỹ thuật chấp nhận contract/schema, identity, state machine, transaction/recovery và compatibility boundaries.
- Mỗi POL mở có baseline và feature gate; registry owner được gán trong tác vụ thực tế, không tự suy policy.
- Baseline commit/worktree/env/data/prompt/provider được chụp, full suite và các failure nền được lưu.
- Corpus P0 có oracle độc lập, chia dev/holdout theo family trước tuning; missing setup được đánh dấu.
- Chốt nơi tạo module/core facade, các writer SQLite và ownership authority; không có hai coordinator cùng quyền.
- Phạm vi tác vụ ghi rõ có cho live/migration/deploy/commit hay không; mặc định triển khai prototype offline.

## 2. Backlog có phụ thuộc và gate

| ID | Mức/mốc | Việc và bàn giao | Phụ thuộc | Acceptance | Hoàn tác |
|---|---|---|---|---|---|
| B01 | P0/R0 | Khóa glossary/DTO/error codes/schema versions | Review gói | Parse/validate samples, negative validation, no trusted-field injection | Chưa đổi runtime |
| B02 | P0/R0 | Lập legacy behavior map và characterization suite | B01, baseline | HTTP/voice/dashboard/CLI contracts, capture failures nguyên trạng | Chỉ gỡ adapter thử |
| B03 | P0/R0 | Corpus safety và engine port cho harness | B01 | L2/L3/L4 setup audit, no oracle peeking, deterministic fixture | Giữ corpus/history |
| B04 | P0/R1 | Domain objects/versions/availability | B01 | Immutability, type/range, location/revision independence | Chưa đổi caller |
| B05 | P0/R1 | Semantic fold/causal dependencies/reference resolver | B04, B03 | Confirm+edit, ask B/change A, uncertain, clear/refine, pure inquiry | Facade vẫn legacy |
| B06 | P0/R1 | Policy/readiness/confirmation evaluator | B05, policy baseline | All POL-T tests; no guessed verified/no early submit | Feature flag off |
| B07 | P0/R2 | Atomic store/repository + schema migration rehearsal | B04, writer inventory | SQLite real unique/CAS/fence, rollback crash, constraints | Synthetic DB bỏ riêng, no prod migration |
| B08 | P0/R2 | Dedup/result replay/turn ledger/cancel barrier | B07, B01 | Same key replay, changed payload conflict, cancel/commit winner, superseded replay no delivery | New engine off |
| B09 | P0/R2 | Ownership/resume/time revalidation/operator fence | B08 | Two owner race, stale worker, cross-session same operation, post-booking restore truthful | Pin old engine requests |
| B10 | P0/R3 | NLU provider port/prompt/source/schema validation | B05, B03 | SDK mock errors, full utterance, hidden candidate rejected, no legacy fallback | Provider flags not changed |
| B11 | P1/R3 | Context budget/focus/suspended decision/recall | B10 | Exact prior user/delivered bot; scope override; bounded pending no loop | New context builder behind engine |
| B12 | P0/R4 | Geo port + evidence verification + aliases baseline | B06, B10 | Number/alley/parent/branch/multicity tests, unknown not nonexistent | Existing provider config intact |
| B13 | P1/R4 | Spoken numbers/dialect/foreign aliases and refinement | B12 | M1/M2/M5 dev ablation, raw immutable, changes revalidate | Disable added hypothesis feature |
| B14 | P1/R4 | FAQ/policy/temporal data typed port | B06 | Approved/scope/effective/conflict/injection cases | Existing approved bundle |
| B15 | P1/R4 | Estimate model, route/tariff adapter | B12, POL-07 | Missing tariff no fare, units, cache invalidate, broad anchor uncertainty | Unavailable branch |
| B16 | P0/R5 | Renderer/claim validation/typed segments | B06, B14 | Missing placeholder blocked, result-driven terminal copy, one offered decision | Compatibility renderer |
| B17 | P0/R5 | Delivery and interruption contract | B08, B16 | Partial/old playback ACK, mute/resume, terminal TTS fail, no unheard confirm | New voice bridge disabled |
| B18 | P1/R6 | CLI shell/doctor/session/export | B09, B16 | Same core; commands not NLU; fixture vs sandbox truthful; PII redact | Old CLI entry retained |
| B19 | P0/R6 | Web/LiveKit/dashboard compatibility | B09, B17 | Public response fields, admission shared, operator tasks/generation, no graph reads | Pin engine to legacy for new requests |
| B20 | P0/R7 | Offline full regression + fault/concurrency/crash | B19 | All safety target situations executed, no new unexplained regressions | Candidate not rolled out |
| B21 | P1/R7 | Provider/live model/geo benchmark with simulated effects | B20, budget approved | Locked holdout, all attempts/timeout costs, no best-of retry hidden | Stop live run preserving evidence |
| B22 | P0/R7 | Audio integration1/4, cold/warm and takeover | B19, B21 | Delivery callbacks, actual final handling, useful audio timings, no unsafe commits | Staging/candidate only |
| B23 | P0/R7 | Migration/rollback rehearsal | B07, B19 | Legacy/new schema compatibility, current data preserved, old worker fenced | Rehearsal DB only |
| B24 | P0/R8 | Shadow then canary per request, metrics/stopping | B20–B23, POL gates | No dual side effects, cohort pin, rollback exercise, approved evidence | Stop new allocation, drain in-flight |
| B25 | P2/R8 | Dọn legacy code và docs/runtime diagram | B24 + no caller proof | Imports/commands/sessions fully handled, final full suite, release report | Separate revertable cleanup |

EXP-01…EXP-06 trong registry là tracks thử nghiệm, không nằm trên critical path trừ khi acceptance sản phẩm phụ thuộc chúng. Phonetic ranker tổng quát, self-host GPU, spatial intersection và dispatch thật cần PR/tác vụ riêng có measurement; core phải vẫn chạy với baseline conservative.

## 3. Các lát dọc nên bàn giao

1. **Thin core fixture:** một lượt set slot → summary → confirm → local simulated intake, có CAS/dedup/delivery giả và SQLite thật. Không cần map live để kiểm critical workflow.
2. **Mixed conversation:** hỏi FAQ + sửa slot + recall + cancel/resume, toàn pipeline cùng engine port, source/reference validation.
3. **Geo evidence:** nguyên địa chỉ, refinement, tên sai âm, rejected candidates và safe support; engine chưa live vẫn replay được.
4. **Voice protocol:** controlled timeline cho interrupt/delivery/stale callbacks/takeover, rồi mới audio staging.
5. **Compatibility rollout:** API mapping, engine pin, durable resume và operator paths, sau đó mới cohort.

Không chạy R1 hoàn chỉnh rồi đợi đến R7 mới có oracle. Mỗi slice phải có scenario, resulting DB state, trace/redaction và rollback scope.

## 4. Definition of Done cho một task

- Hành vi được mô tả bằng trigger và expected state/effect/delivery, có mã yêu cầu/test.
- Diff chỉ trong scope; bảo toàn file người dùng và không gọi live ngầm.
- Tests thật được chạy bằng `.venv`/DB cô lập, ghi lệnh/số pass-fail/chưa chạy/lý do; không skip assertion cho xanh.
- Error paths/race quan trọng có kiểm tra, không chỉ happy path và implementation mirrors.
- Schema/prompt/policy/docs/compatibility mapping khớp; có source version và không fake approval.
- Báo cáo mới theo AGENTS của repo; chưa commit/push/deploy nếu không được yêu cầu.
- Nếu có migration/config/rollout phải có rehearsal và authorization tương ứng; cập nhật registry thực tế.

## 5. Bảng đánh giá một candidate trước release

| Cổng | Bằng chứng cần | Nếu chưa có |
|---|---|---|
| Contract | Schema và cả positive/negative tests, compatibility clients | Chưa nối caller production |
| Transaction | Crash/race/CAS/ownership/replay SQLite và operator tests | Không mở effects |
| Domain | Frozen oracle P0, query/confirmation/address safeguards | Không mở request_recorded |
| Model | Live holdout có budget, không nhầm fixture accuracy | Giữ sandbox, không tự đổi model production |
| Voice | Current playback ACK/interruption + captured useful audio | Không tuyên bố trải nghiệm/audio đạt |
| Business | POL features approved và data/version/source | Feature đó disabled |
| Cutover | Engine pin/drain, schema/backward compatibility, rollback rehearsal | Candidate giữ staging |

Review độc lập các lỗi safety nghi ngờ dù tổng pass rate cao. Một nghìn ca filler dễ không bù một wrong booking. Mọi blocked/not-run giữ trong mẫu số assigned và có lý do.
