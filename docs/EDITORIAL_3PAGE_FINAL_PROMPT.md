STACORP DAILY BRIEF — FINAL APPROVED PROMPT
VERSION: STACORP_EDITORIAL_3PAGE_V1

MỤC TIÊU
Tạo bản tin doanh nghiệp STACORP dạng tạp chí biên tập cao cấp, mobile-first nhưng vẫn đẹp trên PC. Mỗi ngày phải giữ NGUYÊN bố cục 3 trang đã khóa; chỉ thay nội dung tin, ảnh minh họa, ngày, nguồn và hành động điều hành.

A. NGHIÊN CỨU TIN
- Quét 50–80 tiêu đề từ khoảng 10–15 nguồn tin cậy liên quan Việt Nam.
- Ưu tiên tin trong 24–72 giờ gần nhất; tin cũ hơn chỉ dùng nếu tác động vượt trội.
- Chủ đề: cơ hội/khách hàng, FDI, khu công nghiệp, dự án, hạ tầng, xây dựng công nghiệp, logistics, vật liệu/chi phí, tài chính/dòng tiền, công trường/HSE/con người, công nghệ/năng suất, pháp lý/rủi ro.
- Ưu tiên nguồn theo thứ tự:
  1) Chính phủ/Bộ/ngành/cơ quan quản lý/chủ đầu tư chính thức
  2) Doanh nghiệp/dự án chính thức
  3) Báo chí kinh tế lớn
  4) Nguồn thứ cấp chỉ dùng bổ trợ
- Đọc state/published_hashes.json trên main và tránh lặp tin trong 120 ngày trừ khi có diễn biến mới đáng kể.
- Lọc NEW → RELEVANT → MATERIAL → DISTINCT.
- Final đúng 5 tin; mỗi tin >=7/10.
- Nếu không đủ 5 tin đạt chuẩn: DỪNG, không tạo ảnh, không push GitHub, không đăng Teams.
- Thông thường tối đa 2–3 tin CAO.

B. NỘI DUNG MỖI TIN
Mỗi item bắt buộc:
- category
- impact: CAO | TRUNG BÌNH | THEO DÕI
- headline: ngắn, rõ “điều gì vừa thay đổi”
- facts: đúng 2 fact có nguồn, ưu tiên số liệu/quy mô/mốc thời gian
- note: hàm ý thực tế “STACORP cần lưu ý”, không khẳng định cơ hội đã thuộc STACORP
- departments: đúng 2–5 nhóm thật sự liên quan
- source
- source_date
- url

C. TỔNG HỢP ĐIỀU HÀNH
Ngoài 5 items, brief.json phải có:
- summary_lede: 1 đoạn 140–210 ký tự tóm tắt bức tranh trong ngày
- executive_actions: đúng 3 phần tử, mỗi phần tử gồm:
  - title: hành động điều hành ngắn, cụ thể
  - detail: 1–2 câu chỉ rõ việc cần theo dõi/kiểm soát/thực hiện
- action_today: chỉ điền khi phát sinh hành động rõ từ ít nhất một tin CAO; nếu không để chuỗi rỗng.

D. ẢNH MINH HỌA
- ChatGPT Images chỉ tạo 5 ảnh minh họa story-1 → story-5.
- Tuyệt đối KHÔNG tạo chữ, số, logo, watermark, signage đọc được, nhãn hiệu hoặc badge trên ảnh minh họa.
- Không vẽ lại logo STACORP.
- Người/PPE/xe/máy/tòa nhà phải unbranded.
- Phong cách: photorealistic corporate editorial, sáng, sang trọng, xanh-neutral, phù hợp công nghiệp/hạ tầng/logistics/xây dựng/business.
- Ảnh phải có chủ thể rõ, dễ crop.
- Production minimum: long edge >=1400 px và short edge >=900 px. Không upscale ảnh nhỏ để qua chuẩn.

E. BỐ CỤC ĐÃ KHÓA
APPROVED_LAYOUT_VERSION=STACORP_EDITORIAL_3PAGE_V1
- Canvas mỗi trang: 1080×1620 px.
- Page 1: header thương hiệu + item 1 hero rất lớn + note STACORP + item 2 và item 3 là 2 card bên dưới.
- Page 2: item 4 full-width + note STACORP; item 5 full-width + note STACORP.
- Page 3: “Tổng hợp điều hành” + 3 executive_actions + 5 điểm nhấn với thumbnail + nguồn tham khảo + closing visual.
- Footer/navy/gold/logo/typography phải giữ nguyên.
- Production KHÔNG được dùng template khác.
- Không sửa templates/editorial_page1.html, templates/editorial_page2.html, templates/editorial_page3.html, templates/approved-editorial-style.css hoặc config/approved_layout.json trong tác vụ hằng ngày.
- Renderer phải kiểm tra SHA của template và logo; sai SHA thì fail.

F. GITHUB DELIVERY
- Repo: uyenthudao2410-code/stacorp-daily-brief.
- Lấy HEAD/tree mới nhất của main.
- Delivery commit luôn có parent là HEAD hiện tại của main.
- Tree delivery chỉ ghi/ghi đè brief.json + 5 ảnh story.
- Force-update chatgpt-delivery.
- Không commit ảnh story hoặc ảnh final vào main.

G. TEAMS
- Giữ kênh General hiện tại.
- Đúng 1 post Teams.
- Trong post: tiêu đề ngắn → Page 1 → Page 2 → Page 3 → 5 link nguồn → action_today nếu có.
- Không lặp toàn bộ facts/note trong text Teams.
- Chỉ báo “đã đăng Teams” khi GitHub workflow conclusion=success và log có TEAMS_MESSAGE_ID=<id>.
