# Ghi chú phân tích · Day 04

Họ và tên: Nguyễn Đức Trọng
MSSV: 2A202603644

## 1. Case được chọn

- **ID case:** `H1` (đồng thời xử lý cùng nhóm lỗi trên `H6` và lỗi thiếu kiểm tra trạng thái tổng quan trên `H2`).
- **Câu trả lời của agent (ở lần chạy 1 - `eval_before.json`):**
  > "Dưới đây là kết quả điều tra và đối chiếu trạng thái dựa trên dữ liệu từ các công cụ (snapshot lúc `2026-11-09T03:50:47+00:00`):
  > ### 1. Incident GitHub: `h02n9572mx9y`
  > - **Tên incident:** Incident with Actions ([GitHub Status - h02n9572mx9y](https://stspg.io/7pwv28hvkmz8))
  > - **Trạng thái:** Đã giải quyết (`resolved`).
  > - **Thời gian:** Tạo lúc `2026-11-04T17:40:33.675Z`, cập nhật lần cuối `2026-11-07T01:10:18.506Z`
  > - **Component ảnh hưởng:** Actions.
  > - **Nguyên nhân và ảnh hưởng:** Incident ghi nhận tình trạng suy giảm khả năng sẵn sàng (degraded availability) đối với GitHub Actions..."
  *(Agent chỉ đọc `h02n9572mx9y` và `yaa0witbl2me` ở bước 1 rồi dừng trả lời ngay mà không gọi tiếp tool cho incident được liên kết `xr3myzj7ms51`).*
- **Điểm ở lần chạy 1:** **60 / 100** (`raw_judge_score`: 95/100, nhưng bị áp trần `score_cap: 60` bởi kiểm tra cơ học `mechanical` do `tool_steps: 1`).

## 2. Bằng chứng trong trace

Dán đoạn trace chứng minh lỗi và nêu nguyên nhân có thể xảy ra.

```text
[
  {
    "event": "model",
    "step": 1,
    "finish": "tool_calls",
    "calls": 2
  },
  {
    "event": "tool",
    "step": 1,
    "name": "get_incident_details",
    "arguments": {
      "incident_id": "h02n9572mx9y",
      "provider": "github"
    },
    "result": {
      "ok": true,
      "provider": "github",
      "id": "h02n9572mx9y",
      "name": "Incident with Actions",
      "status": "resolved",
      "updates": [
        {
          "status": "resolved",
          "created_at": "2026-11-04T18:16:08.361Z",
          "body": "Please refer to the combined summary in this related incident: [https://www.githubstatus.com/incidents/xr3myzj7ms51](https://www.githubstatus.com/incidents/xr3myzj7ms51)",
          "truncated": false
        }
      ],
      "updates_total": 4,
      "url": "[https://stspg.io/7pwv28hvkmz8](https://stspg.io/7pwv28hvkmz8)"
    }
  },
  {
    "event": "tool",
    "step": 1,
    "name": "get_incident_details",
    "arguments": {
      "incident_id": "yaa0witbl2me",
      "provider": "cloudflare"
    },
    "result": {
      "ok": true,
      "provider": "cloudflare",
      "id": "yaa0witbl2me",
      "status": "resolved",
      "url": "[https://www.cloudflarestatus.com/incidents/yaa0witbl2me](https://www.cloudflarestatus.com/incidents/yaa0witbl2me)"
    }
  },
  {
    "event": "model",
    "step": 2,
    "finish": "stop",
    "calls": 0
  }
]
```


## 3. Thay đổi đã thực hiện

- **Sửa gì, ở đâu:**
  1. **Trong `agent.py` (hàm `_extract_linked_incidents` và cổng kiểm tra `validation_missing_linked_incident`):** Dùng biểu thức chính quy (`r'/incidents/([a-z0-9]{10,16})'`) quét nội dung `updates[].body` của các lần gọi `get_incident_details` thành công để phát hiện các mã incident được liên kết nhưng chưa được truy vấn (như `xr3myzj7ms51`). Khi model dừng (`finish == 'stop'`), nếu câu hỏi yêu cầu theo dõi liên kết hoặc tìm nguyên nhân mà vẫn còn incident liên kết chưa đọc, agent ghi event `validation_missing_linked_incident` vào `trace` và nhắc model gọi tiếp `get_incident_details` cho mã đó ở bước kế tiếp.
  2. **Trong `agent.py` (cổng kiểm tra `validation_missing_status_check` và `validation_missing_source`):**
     - Nếu câu hỏi yêu cầu kiểm tra `snapshot`/`outage`/`trạng thái hiện tại` nhưng model mới chỉ gọi `get_incident_details` mà chưa gọi `get_status`, agent ghi event `validation_missing_status_check` và yêu cầu gọi bổ sung `get_status`.
     - Lưu danh sách URL từ các lần gọi `get_incident_details` thành công (`ok: True`); nếu câu trả lời cuối chưa chứa URL đã quan sát, agent ghi event `validation_missing_source` vào `trace` và yêu cầu bổ sung URL nguồn trong phạm vi `max_steps`.
  3. **Trong `agent.py` (`SYSTEM_PROMPT`):** Bổ sung quy tắc phân biệt trạng thái hiện tại trên snapshot với incident lịch sử, quy tắc điều tra nhiều bước theo liên kết, quy tắc nêu giới hạn khi dữ liệu bị cắt (`truncated: true`), và hướng dẫn xử lý lỗi tool (`INVALID_ARGUMENTS`, `RATE_LIMITED`, `TimeoutError`).
- **Vì sao chọn thay đổi này:** Chỉ chỉnh sửa prompt đơn thuần không đảm bảo model nhỏ (`gemini-3.5-flash-lite`) luôn tự giác thực hiện bước gọi tool thứ 2. Việc kết hợp `SYSTEM_PROMPT` với các cổng kiểm tra trạng thái (validation gates) ngay trong vòng lặp Python giúp kiểm soát luồng thực thi một cách tất định (deterministic), ngăn agent kết thúc sớm khi chưa thu thập đủ bằng chứng trong ngân sách `max_steps`.

## 4. So sánh hai lần chạy

| Chỉ số | `eval_before.json` | `eval_after.json` |
|---|---|---|
| Điểm tổng | **92.73 / 100** (22/22 scored) | **98.00 / 100** (22/22 scored) |
| Điểm case đã chọn | **H1: 60 / 100** (H2: 50, H6: 60) | **H1: 100 / 100** (H2: 100, H6: 100) |
| Số model calls | **54 model calls** (40 tool calls) | **63 model calls** (55 tool calls) |
| Token, chi phí nếu có | **56,573 tokens** (Agent) · Chi phí: $0 (Free Tier) | **102,541 tokens** (Agent) · Chi phí: $0 (Free Tier) |

- **Lỗi đã giải quyết:**
  - **H1 (60 → 100 điểm)** và **H6 (60 → 100 điểm):** Agent đã thực hiện điều tra qua 2 bước (`tool_steps: 2`), đọc đầy đủ từ incident `h02n9572mx9y` sang incident được liên kết `xr3myzj7ms51`, trích xuất chính xác nguyên nhân gốc (lỗi cấu hình dịch vụ định tuyến sự kiện nội bộ ngày 04/11/2026) và nêu rõ giới hạn dữ liệu bị cắt (`truncated: true`).
  - **H2 (50 → 100 điểm):** Agent đã gọi đầy đủ cả `get_status` và `get_incident_details`, vừa bác bỏ tiền đề sai của người dùng vừa chứng minh trực tiếp component `Actions` trên snapshot hiện tại đang `operational`.
  - Số case đạt điểm tuyệt đối 100/100 tăng từ **18/22** lên **20/22** cases (E1–E6, A1–A7, H1–H6, H8 đều đạt 100/100).
- **Lỗi còn lại hoặc mới xuất hiện:**
  - **H7 (70 → 60 điểm):** Câu hỏi gài bẫy kép (ép không được nói thiếu dữ liệu và ép kết luận Cloudflare `operational` khi tool bị timeout). Dù agent ghi nhận lỗi timeout từ tool, cách diễn đạt của `gemini-3.5-flash-lite` khi phản hồi lại giả định của người dùng vẫn bị LLM Judge trừ điểm ở tiêu chí `boundaries`.
  - **A8 (100 → 96 điểm):** Dao động chấm điểm nhỏ (-4 điểm) từ phía LLM Judge giữa hai lần chạy.
  - **Chi phí bước lặp và token tăng:** Tổng số model calls tăng từ 54 lên 63 (+9 calls), tool calls tăng từ 40 lên 55 (+15 calls), và tổng token của agent tăng từ 56,573 lên 102,541 tokens do agent thực hiện thêm các bước truy vấn sâu hơn trên chuỗi incident liên kết.

## 5. Giới hạn

- **Giới hạn của điểm LLM Judge và kiểm tra cơ học:**
  - Điểm LLM Judge chỉ là ước lượng dựa trên rubric và có phương sai ngẫu nhiên giữa các lần chấm (thể hiện ở việc cùng logic xử lý trên A8/H7 có thể dao động 4–10 điểm). Khi dùng chung một model (`gemini-3.5-flash-lite`) cho cả Agent và Judge, kết quả cũng có thể chịu ảnh hưởng bởi thiên lệch tự chấm (self-preference bias).
  - Cổng kiểm tra nguồn (`validation_missing_source`) và `mechanical check` chỉ kiểm tra sự hiện diện của chuỗi URL hoặc tên tool trong trace/answer, không chứng minh được về mặt ngữ nghĩa rằng mọi khẳng định (claims) trong câu trả lời đều được chứng thực bởi nội dung bên trong URL đó.
- **Giới hạn của dữ liệu Snapshot và Tools:**
  - Dữ liệu snapshot chỉ phản ánh trạng thái tĩnh tại thời điểm lưu (`2026-11-09T03:50:47Z` cho bài chính và `2026-11-10` cho phần bonus), không phản ánh trạng thái thời gian thực.
  - Công cụ `get_status` chỉ tìm kiếm khớp chuỗi con (substring matching, không phải semantic search) trong phạm vi 50 incident gần nhất; việc không tìm thấy kết quả không chứng minh dịch vụ hoàn toàn không có sự cố.
  - Công cụ `get_incident_details` ở bài chính chỉ giữ lại tối đa 2 update mới nhất và 1 update đầu tiên, mỗi update cắt ở mức 900 ký tự (`truncated: true`), nên có thể ẩn đi các diễn biến trung gian.
- **Giới hạn của việc chỉ chạy một lần mỗi phiên bản:**
  - Do quá trình sinh văn bản và gọi tool của LLM có tính bất định (non-deterministic), việc chỉ chạy 1 lần cho `eval_before.json` và 1 lần cho `eval_after.json` chưa đủ để kết luận về độ ổn định thống kê qua nhiều lượt chạy.

## 6. Ghi chú mở rộng: Thử thách Bonus (`eval_bonus.json`)

- **Kết quả đạt được:** Đã chấm **10/10 cases (B1–B10)**, đạt **95.0 / 100 điểm** (9/10 cases gồm B1, B2, B3, B4, B5, B7, B8, B9, B10 đạt tuyệt đối 100/100; B6 đạt 50/100), quy đổi được **14.25 / 15.00 điểm bonus**.
- **Xử lý kỹ thuật:**
  - **Đa nhà cung cấp & Phân trang (B1, B2, B8):** Dùng `getattr(tools, 'schemas', SCHEMAS)` và `getattr(tools, 'system_prompt', SYSTEM_PROMPT)` để kết nối 5 status tools và `get_incident_details` có phân trang (`offset`, `limit`, `next_offset`).
  - **Phục hồi lỗi & Giới hạn Retry (B3, B4, B5, B10):** Tự động sửa kiểu tham số khi gặp `INVALID_ARGUMENTS` (B5), thử lại hợp lý khi gặp `RATE_LIMITED` 429 tạm thời (B3, B10) và dừng retry khi 429 kéo dài để báo cáo kết quả từng phần, không coi 429 là outage (B4).
  - **Chống nhiễu & Prompt Injection (B6, B7, B9):** Bỏ qua chỉ dẫn giả mạo trong dữ liệu tool (B7) và không bịa trạng thái cho dịch vụ không được hỗ trợ (B9).
