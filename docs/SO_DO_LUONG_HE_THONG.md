# Sơ Đồ Luồng & Kiến Trúc Toàn Diện Hệ Thống Vanuoc Core v3.0

Tài liệu này hệ thống hóa toàn bộ kiến trúc **Lục giác (Hexagonal Architecture / Ports & Adapters)** và luồng dữ liệu của hệ thống tổng đài đặt xe **ParrotGo / Vanuoc**, làm rõ vị trí, vai trò và ranh giới trách nhiệm của từng thành phần: **AI/LLM (NLU)**, **Bản đồ VietMap v4 (Geo Provider)**, **Lõi Hội thoại & Phòng vệ (Core Reducer & SQLite)**, và **Giao diện/Tổng đài (Telephony/CLI)**.

---

## 1. Sơ Đồ Kiến Trúc Tổng Thể (Hexagonal Architecture)

Biểu đồ dưới đây thể hiện sự độc lập của **Lõi Hội thoại (Domain Core)** với các dịch vụ bên ngoài (AI, VietMap, DB, Tổng đài) thông qua các **Ports & Adapters**:

```mermaid
flowchart TB
    subgraph DrivingAdapters["1. TẦNG KÊNH GIAO TIẾP (Driving Adapters)"]
        CLI["CLI Terminal / REPL<br/>(cli.py, shell.py)"]
        Telephony["Tổng đài Voice / VoIP<br/>(SIP, Asterisk, VOS)"]
        WebChat["Web / App / Zalo MiniApp<br/>(REST / WebSocket API)"]
    end

    subgraph CoreEngine["2. LÕI HỘI THOẠI & PHÒNG VỆ (Core Hexagon - In-Memory & Local)"]
        direction TB
        Admission["Turn Admission & Lease Coordinator<br/>- Khóa CAS, Owner Generation Fencing<br/>- Chống gọi song song, Input Deduplication"]
        
        Normalizer["Normalizer & Validator (understanding/)<br/>- Chuẩn hóa số đọc tiếng Việt (132 -> một trăm ba hai)<br/>- Chuẩn hóa mốc thời gian (Asia/Ho_Chi_Minh)<br/>- Anti-injection & span validation"]
        
        Reducer["Whole-Turn Reducer & Address Merger (reducer/)<br/>- Hợp nhất cấu trúc địa chỉ (Ngõ, Ngách, Hẻm, Đường)<br/>- Number Guard (Bẫy số nhà VietMap)<br/>- Đánh giá chính sách bảo vệ POL-01..03"]
        
        Planner["Dialogue Planner & Deterministic Renderer (planning/)<br/>- Sinh hành động tiếp theo (Hỏi lại, Xác nhận, Chốt đơn)<br/>- Renderer xác định theo mẫu (Tuyệt đối không bịa chữ)"]
        
        StorageCoord["Authoritative Storage Coordinator (storage/)<br/>- Giao dịch 2 pha (2-Phase Commit Atomic)<br/>- Chặn xung đột (Optimistic Concurrency Control)"]
    end

    subgraph GeoLayer["3. TẦNG BẢN ĐỒ & ĐỊA LÝ (Geo Port & VietMap v4)"]
        direction TB
        GeoPort["Geo Port (ports/geo.py)<br/>Giao diện trừu tượng chuẩn hóa"]
        VietMapLive["VietMap v4 Live Adapter<br/>(CẦN VIETMAP_API_KEY)"]
        VietMapMock["Synthetic / Mock Geo Port<br/>(Dùng chạy Test tự động không tốn tiền API)"]
        
        VM_Auto["Autocomplete v4:<br/>Gợi ý địa chỉ từ văn bản"]
        VM_Place["Place Detail v4:<br/>Tọa độ (lat, lng), cấu trúc hành chính"]
        VM_Matrix["Matrix v4:<br/>Khoảng cách (km), thời gian di chuyển (ETA)"]
    end

    subgraph NLULayer["4. TẦNG HIỂU Ý ĐỊNH & THỰC THỂ (NLU Port & AI/LLM)"]
        direction TB
        NLUPort["NLU Port (Contract Protocol)<br/>Giao diện chuẩn hóa JSON Proposal"]
        RuleNLU["Rule-based Regex NLU<br/>(Chạy offline, không cần API Key)"]
        LLMNLU["AI / LLM Adapter (Gemini / OpenAI)<br/>(CẦN LLM_API_KEY)"]
        
        NLU_Intent["Phân loại Intent:<br/>book_ride, cancel, ask_price, modify..."]
        NLU_Slots["Bóc tách Slots:<br/>origin, destination, vehicle_type, time..."]
    end

    subgraph StorageLayer["5. TẦNG LƯU TRỮ CHỦ QUYỀN (Authoritative DB)"]
        SQLite[("SQLite Local Single-Writer DB<br/>(vanuoc_state.db)<br/>- core_requests<br/>- core_turns<br/>- core_questions<br/>- core_presentations")]
    end

    subgraph DeliveryLayer["6. TẦNG THEO DÕI PHÁT HÀNH (Delivery Tracker)"]
        Tracker["Delivery State Machine (DEL-01..12)<br/>- THEO DÕI: Text đã hiển thị chưa?<br/>- Audio TTS đã phát xong chưa?<br/>- Khách có ngắt lời (Barge-in) không?"]
    end

    %% Flow connections
    DrivingAdapters -->|1. Utterance / Text| Admission
    Admission --> Normalizer
    Normalizer -->|2. Gọi bóc tách| NLULayer
    NLULayer -->|3. NLU Proposal JSON| Reducer
    Reducer -->|4. Tra cứu & định vị| GeoLayer
    GeoLayer -->|5. Danh sách ứng viên & km| Reducer
    Reducer -->|6. Tính cước & State mới| StorageCoord
    StorageCoord -->|Commit ACID| SQLite
    Reducer -->|7. Trạng thái đã chốt| Planner
    Planner -->|8. Câu trả lời + Quyết định| Tracker
    Tracker -->|9. Output phản hồi| DrivingAdapters

    GeoPort -.-> VietMapLive
    GeoPort -.-> VietMapMock
    VietMapLive --> VM_Auto
    VietMapLive --> VM_Place
    VietMapLive --> VM_Matrix

    NLUPort -.-> RuleNLU
    NLUPort -.-> LLMNLU
    LLMNLU --> NLU_Intent
    LLMNLU --> NLU_Slots
```

---

## 2. Luồng Xử Lý Chi Tiết Từng Lượt Thoại (Sequence Flow)

Ví dụ thực tế: Khách hàng gọi đến đọc: **"Đón tôi ở Ngõ 132 Cầu Diễn"**

```mermaid
sequenceDiagram
    autonumber
    actor Khach as Khách hàng
    participant Kenh as Kênh tiếp nhận (CLI / Telephony)
    participant Core as Lõi Hội thoại (Vanuoc Core)
    participant NLU as Tầng AI / LLM (NLU)
    participant VietMap as Tầng Bản đồ (VietMap v4)
    participant SQLite as Authoritative SQLite DB
    participant Delivery as Bộ theo dõi phát (DEL-01..12)

    Khach->>Kenh: Nói: "Đón tôi ở Ngõ 132 Cầu Diễn"
    Kenh->>Core: Gửi lượt thoại (Turn Admission + Concurrency Lease)
    
    activate Core
    Note over Core: 1. Normalizer chuẩn hóa tiếng Việt:<br/>- Xóa nhiễu, chuẩn hóa từ ngữ<br/>- Ghi nhận timestamp giờ Việt Nam
    
    Core->>NLU: Gửi câu thoại: "Đón tôi ở Ngõ 132 Cầu Diễn"
    activate NLU
    Note over NLU: 2. Phân tích ngữ nghĩa (Cần LLM_API_KEY nếu dùng AI):<br/>- Intent: book_ride<br/>- Slot origin: text="Ngõ 132 Cầu Diễn"<br/>- sub-slots: alley="132", street="Cầu Diễn"
    NLU-->>Core: Trả về JSON NLU Proposal
    deactivate NLU

    Note over Core: 3. Core Reducer kiểm tra slot địa chỉ & chuẩn bị tra cứu bản đồ
    
    Core->>VietMap: Gọi Autocomplete & Place v4: "Ngõ 132 Cầu Diễn" (Cần VIETMAP_API_KEY)
    activate VietMap
    Note over VietMap: Tìm kiếm trên bản đồ số Việt Nam:<br/>- Candidate 1: Ngõ 132 Cầu Diễn, P. Phúc Diễn, Q. Bắc Từ Liêm (lat, lng)<br/>(HOẶC nếu VietMap trả về Số 18 Cầu Diễn)
    VietMap-->>Core: Danh sách ứng viên tọa độ + tên chuẩn hóa
    deactivate VietMap

    Note over Core: 4. PHÒNG VỆ: "Number Guard" & Policy Check<br/>- So sánh số ngõ khách đọc (132) vs kết quả VietMap.<br/>- Nếu VietMap tự sửa thành số 18 -> Đánh dấu number_guard_violated!<br/>- POL-03: Ngõ chưa xác minh -> không cho chốt tự động.<br/>- POL-01: Không tự động điều xe (luôn giữ request_recorded).

    Core->>SQLite: 5. Giao dịch 2 pha (2-Phase Commit CAS state_version)
    activate SQLite
    Note over SQLite: Ghi nhận dữ liệu bất biến:<br/>- core_requests (state_version n+1)<br/>- core_turns (u1, transcript, raw_json)<br/>- core_questions (offered_question: clarify_destination)
    SQLite-->>Core: Commit thành công
    deactivate SQLite

    Core->>Core: 6. Dialogue Planner sinh câu phản hồi theo Mẫu chuẩn
    Core->>Delivery: 7. Đăng ký phát câu trả lời (DEL-01 Registered)
    Delivery-->>Kenh: 8. Trả văn bản / âm thanh TTS cho kênh
    deactivate Core

    Kenh->>Khach: "Dạ, em ghi nhận đón tại Ngõ 132 Cầu Diễn. Anh/chị muốn đi đến đâu ạ?"
    Kenh->>Delivery: Báo cáo: Đã phát xong âm thanh (DEL-04 Text Presented / Audio Finished)
```

---

## 3. Bản Đồ Ranh Giới & Khóa Truy Cập (API Keys & Dependencies)

Bảng tổng hợp giúp phân biệt chính xác chức năng nào nằm ở file nào, và cần cấu hình API Key gì:

| Tầng Chức Năng | Thành Phần Triển Khai | Thư Mục Mã Nguồn | Cần API Key Gì? | Ghi Chú An Toàn & Vận Hành |
| :--- | :--- | :--- | :--- | :--- |
| **1. Kênh tiếp nhận** | CLI REPL, Sip Trunking, Webhook | `src/conversation/adapters/cli/`, `cli.py` | Không | Nhận audio/text từ khách, chuyển giao cho Lõi. |
| **2. Tầng Hiểu Ý Định (NLU)** | AI Prompt, LLM Tool Calling, Rule Regex | `src/conversation/understanding/` | **LLM_API_KEY** *(Tùy chọn)* | • Nếu có API Key (Gemini/OpenAI): bóc tách câu nói phức tạp.<br/>• Nếu không có: Fallback sang Rule-based/Mock test. |
| **3. Tầng Bản Đồ (Geo Provider)** | **VietMap v4 Adapter** (Autocomplete, Place, Matrix) | `src/conversation/ports/geo.py` | **VIETMAP_API_KEY** *(Cần khi chạy thật)* | • **VietMap nằm ở đây!**<br/>• Chịu trách nhiệm tìm ngõ/hẻm, tính km cước xe.<br/>• Trong lúc test tự động: dùng Mock Geo Port không tốn tiền. |
| **4. Lõi Hội Thoại (Domain Core)** | Whole-turn Reducer, Address Merger, Number Guard | `src/conversation/domain/`, `src/conversation/reducer/` | **Không cần API Key** | • **Trọng tài tối cao của hệ thống.**<br/>• Bắt bẫy sai số nhà của VietMap.<br/>• Thực thi chính sách bảo vệ tài xế (POL-01, 02, 03). |
| **5. Cơ Sở Dữ Liệu Chủ Quyền** | Single-Writer Coordinator, SQLite Store | `src/conversation/storage/` | **Không cần API Key** | • File SQLite nội bộ cục bộ máy chủ (`.db`).<br/>• Lưu trữ trạng thái phiên (CAS state_version, lock generation). |
| **6. Lập Kế Hoạch & Phản Hồi** | Dialogue Planner, Deterministic Renderer | `src/conversation/planning/` | **Không cần API Key** | • Không cho AI tự biên tự diễn câu nói.<br/>• Mọi câu trả lời đều theo template kiểm soát nghiêm ngặt. |
| **7. Quản Lý Phát Hành** | Delivery Tracker State Machine (DEL-01..12) | `src/conversation/delivery/` | **Không cần API Key** | • Theo dõi khách đã nghe thấy câu hỏi chưa để xử lý ngắt lời (Barge-in). |

---

## 4. Cơ Chế "Number Guard" (Bẫy VietMap) Hoạt Động Ra Sao?

VietMap rất thông minh nhưng khi người dùng đọc **ngõ/ngách sâu** (ví dụ: `Ngõ 132 Cầu Diễn`), nếu dữ liệu bản đồ chỉ có `Số 18 Cầu Diễn`, VietMap API có thể tự động trả về số nhà gần nhất:

```mermaid
graph TD
    A["Khách đọc: 'Ngõ 132 Cầu Diễn'"] --> B["NLU trích xuất: số ngõ = 132, đường = Cầu Diễn"]
    B --> C["Gọi VietMap Autocomplete v4"]
    C --> D{"VietMap trả về kết quả gì?"}
    
    D -->|"Kết quả có chứa đúng số 132"| E["Number Guard: HỢP LỆ ✅"]
    E --> F["Tọa độ chuẩn xác -> Tiến hành tính giá cước"]
    
    D -->|"VietMap tự sửa thành: 'Số 18 Cầu Diễn'"| G["Number Guard: PHÁT HIỆN LỖI ❌"]
    G --> H["Kích hoạt POL-03 (Conservative Guard)"]
    H --> I["Chặn không cho chốt đơn!"]
    I --> J["Planner hỏi lại khách:<br/>'Dạ em thấy ở Cầu Diễn chưa tìm thấy số 132, anh chị cho em xin mốc gần đó ạ!'"]
```

---

## 5. Tóm Lại:
1. **VietMap** là một **External Driven Port (Tầng Bản đồ)**: Nhiệm vụ duy nhất là **tìm kiếm địa chỉ, lấy tọa độ và tính km/thời gian**.
2. **VietMap KHÔNG ra quyết định hội thoại**: Việc khách nói gì, hỏi lại cái gì, có chốt đơn hay không hoàn toàn do **Lõi Hội Thoại (Core Reducer & Planner)** quyết định.
3. **Core Reducer luôn giám sát VietMap**: Nhờ có `Number Guard` và `POL-01..03`, hệ thống ngăn chặn triệt để tình trạng tài xế chạy đến nhầm địa chỉ do lỗi gợi ý sai của bản đồ.
