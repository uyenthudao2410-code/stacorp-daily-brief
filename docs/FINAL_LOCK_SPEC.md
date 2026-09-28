# FINAL LOCK SPEC — STACORP DAILY BRIEF

Version: STACORP_EDITORIAL_3PAGE_FINAL_V1
Status: APPROVED / PRODUCTION / IMMUTABLE

## 1. Single source of truth
The only production source of truth is the locked GitHub renderer:
- templates/editorial_page1.html
- templates/editorial_page2.html
- templates/editorial_page3.html
- templates/approved-editorial-style.css
- config/approved_layout.json
- assets/stacorp-logo.png

Images created in ChatGPT are story illustrations only. They are NEVER the final newsletter page.

## 2. Final canvas
- 3 pages.
- 1080 x 1620 px each.
- Render at 2x with Playwright.
- Downsample to 1080 x 1620 using LANCZOS.
- Final Teams transport: JPEG quality 96, 4:4:4/subsampling 0.
- All 3 pages go into one Teams root post.

## 3. Immutable visual identity

### Header
Every page uses the exact same locked masthead:
- Approved STACORP logo on the left, 92 x 92 CSS px.
- Thin champagne-gold vertical divider.
- Georgia/Times-style navy editorial title.
- “STACORP” oversized on the second title line.
- Upper subtitle in spaced uppercase.
- Date lockup on the right in warm gold.
- Thin gold date rule.
- Small “BẢN TIN HÀNG NGÀY / KINH TẾ • ĐẦU TƯ • DOANH NGHIỆP”.
- Very light blue skyline/mountain motif behind the lower header.
- Masthead height locked at 164 px.

### Footer / bottom
Every page uses the exact same locked footer:
- Deep navy-to-blue gradient.
- Champagne-gold curved line/flourish on the bottom-left.
- Thin gold top accent line.
- Left brand line: “STACORP / KIẾN TẠO GIÁ TRỊ BỀN VỮNG / CÙNG DOANH NGHIỆP VIỆT”.
- Center motto with gold vertical divider: “CẬP NHẬT HÔM NAY / KIẾN TẠO CƠ HỘI NGÀY MAI”.
- Page number on the right: 1/3, 2/3, 3/3.
- Footer height locked at 98 px.

### Design tokens
- Navy: #062E62
- Dark navy: #021D42
- Corporate blue: #2A67A8
- Gold: #C38A1C
- Bright gold: #DDA82C
- Warm paper: #FFFDF8
- Headline font: Georgia, Times New Roman, serif
- Body font: Segoe UI, Arial, sans-serif

No daily task may change these values.

## 4. Page 1 — main cover
- Item 1 is the hero story.
- Hero image height locked at 540 px.
- Hero image receives subtle vignette only; no AI-generated text.
- Gold category pill at top-left.
- Impact pill at top-right.
- Large serif headline below hero.
- One concise fact/dek.
- Locked “STACORP CẦN LƯU Ý” callout:
  - gold left rule
  - circular gold icon
  - navy label
  - internal gold separator
  - short operational/business implication
- Items 2 and 3 appear as two equal cards below.
- Each small card height locked at 425 px.
- Each card uses image + category/impact + headline + one short fact.

## 5. Page 2 — deep-dive stories
- Item 4 appears first as a full-width editorial story.
- Item 4 image height locked at 430 px.
- Headline + one concise fact + locked STACORP note.
- Item 5 uses the approved split composition:
  - image left
  - headline/text right
  - STACORP note below
- Split main area height locked at 353 px.
- This page must NEVER revert to two identical stacked full-width cards.

## 6. Page 3 — executive summary
- Gold “TỔNG HỢP ĐIỀU HÀNH” ribbon.
- Right-side label: “3 ƯU TIÊN HÀNH ĐỘNG CHO STACORP”.
- One summary lede.
- Executive zone:
  - exactly 3 numbered action rows on the left
  - one premium editorial photo on the right
  - locked quote overlay: “Nắm bắt cơ hội / Kiến tạo giá trị bền vững”
- Five daily highlight cards with thumbnails.
- Reference zone:
  - source pills on the left
  - closing visual on the right
  - locked closing caption “Cập nhật để chủ động / Ra quyết định tốt hơn”
- Highlight card height locked at 240 px.

## 7. Story illustration rules
ChatGPT Images creates exactly 5 story visuals:
- photorealistic corporate editorial
- bright, elegant, professional
- Vietnamese industrial / infrastructure / logistics / business context
- no text
- no numbers
- no logo
- no watermark
- no readable signage
- no visible corporate brands
- no STACORP logo
- unbranded PPE, machinery, vehicles and buildings
- minimum long edge >= 1400 px
- minimum short edge >= 900 px
- no upscaling low-resolution images to pass validation

## 8. Content rules
- Exactly 5 stories.
- Item 1 is the most material story.
- Each story has exactly 2 source-supported facts.
- impact only: CAO / TRUNG BÌNH / THEO DÕI.
- Usually no more than 2–3 CAO stories.
- Each story has 2–5 genuinely relevant departments.
- “STACORP cần lưu ý” is practical implication, never an unsupported claim.
- summary_lede is required.
- executive_actions contains exactly 3 items.
- action_today is only populated when a clear action arises from at least one CAO item.

## 9. Daily data may change; layout may not
Daily task may change only:
- date
- five story images
- five story texts
- sources / dates / URLs
- summary_lede
- executive_actions
- action_today

Daily task must never modify:
- templates
- CSS
- logo
- approved layout config
- renderer lock
- Teams target
- footer/header identity
- canvas size/page count

## 10. Automatic hard-fail conditions
Production MUST stop before Teams posting if any condition fails:
- template git-blob SHA mismatch
- approved logo SHA mismatch
- wrong layout version
- wrong 1080 x 1620 output size
- wrong page count
- missing story image
- story image below minimum resolution
- broken image in HTML
- page overflow
- locked geometry drift > 1 CSS px
- footer not exactly flush with bottom
- workflow failure

There is no fallback layout.

## 11. Teams posting
Exactly one root post:
1. DD.MM.YYYY • ĐIỂM TIN CHO DOANH NGHIỆP STACORP
2. Page 1
3. Page 2
4. Page 3
5. Five compact clickable source links
6. “Ưu tiên hôm nay” only when action_today is non-empty

Do not repeat all headlines, facts or notes in Teams text.

Only report “đã đăng Teams” when:
- workflow conclusion = success
- log contains TEAMS_MESSAGE_ID=<id>

## 12. Change-control rule
Any future visual change requires:
1. explicit user approval
2. new layout version
3. new template/style SHA set
4. successful CI render
5. separate test post
6. only then may production switch versions

No silent layout edits are allowed.
