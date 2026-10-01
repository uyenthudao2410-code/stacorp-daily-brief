# STACORP Daily Brief

Automated enterprise-news brief for STACORP using **ChatGPT Scheduled Task + GitHub connected app**. Production does **not** use OpenAI API, OPENAI_API_KEY, Codex, Power Automate or Outlook.

## Production format

Approved layout:

`STACORP_EDITORIAL_3PAGE_FINAL_V3_REGIONAL_8NEWS`

- Exactly **8 qualified stories** per issue.
- Primary geography: **MIỀN BẮC + MIỀN TRUNG**.
- At least 3 North items and 3 Central items; at most 2 nationwide items.
- No standalone southern item unless the development is nationwide and materially affects North/Central operations.
- Page 1: story 1 hero + stories 2–4 as three horizontal rows.
- Page 2: stories 5–8 as a 2×2 grid.
- Page 3: cross-department synthesis only; it does not repeat the eight headlines.

## Page 3 synthesis

The final page is designed for multiple departments reading the same brief:

- 4 cross-functional digest cards:
  - Kinh doanh • Đấu thầu • Marketing
  - Dự án • Kỹ thuật • HSE
  - Cung ứng • Tài chính • Kế toán
  - Nhân sự • Pháp chế • Ban Giám đốc
- North/Central regional pulse.
- Exactly 3 watchpoints for the next 24–48 hours.
- 8 compact source references.

## Source visual quality lock

ChatGPT Images produces exactly 8 unbranded story illustrations.

Production accepts original PNG/JPEG only:

- long edge >= 1400 px
- short edge >= 900 px
- source bytes >= 250,000
- sharpness >= 18.0
- WEBP previews, screenshots and thumbnails are blocked

If original binary cannot be committed, `incoming/current/visual_sources.json` may contain exactly eight original `oaiusercontent.com/.../raw` URLs.

Any source visual failure blocks rendering, Teams posting and state update.

## Teams output

- 3 final pages, each 1080×1620.
- Teams master 1200×1800 derived from browser render 2x; never upscaled from final.
- JPEG 4:4:4, subsampling 0, deterministic quality ladder 97→90.
- <= 850,000 bytes per page and <= 2,550,000 bytes total.
- One root post only: Page 1 → Page 2 → Page 3 → 8 source links → optional action_today.
- Publication is successful only when GitHub Actions concludes `success` and logs `TEAMS_MESSAGE_ID=<id>`.

## Schedule

The ChatGPT Scheduled Task runs every day at **08:15 Asia/Ho_Chi_Minh**.

Official Teams destination:

- Team: `85f93dd1-97df-43b4-88c2-a156e57b5223`
- Channel: `19:ae875099856a42569438d9c056e1294f@thread.tacv2`
- Channel name: `2. Thông tin và tin tức`

## Deduplication

Only successful production runs update `state/published_hashes.json`. Published items are excluded for 120 days unless a materially new development occurs.

## Microsoft Entra

Required delegated permissions:

- `ChatMessage.Send`
- `ChannelMessage.Send`
- `offline_access`

Repository secrets:

- `MS_TENANT_ID`
- `MS_CLIENT_ID`
- `MS_REFRESH_TOKEN`
- optional `MS_CLIENT_SECRET`
