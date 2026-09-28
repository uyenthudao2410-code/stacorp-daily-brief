STACORP DAILY BRIEF — FINAL DESIGN/CONTENT PROMPT V8

GOAL
Create one premium, magazine-style news cover for Microsoft Teams that is immediately readable on both mobile and desktop. The post must feel like a high-end business publication, not a dashboard or internal draft.

OUTPUT
- Exactly 1 final image per daily post.
- Canvas: 1080x1350 px, 4:5.
- Render master at 2x, then downsample with LANCZOS.
- One Teams post only: title + one image + compact source links + action_today.
- Keep the approved STACORP logo from assets/stacorp-logo.png; verify its locked hash; never redraw or regenerate it.

EDITORIAL HIERARCHY
1. One hero story occupies roughly the top 40% of the visual.
2. Hero uses a full-bleed high-resolution image, restrained dark gradient, large headline.
3. Four remaining stories appear as a clean 2x2 editorial grid.
4. Each secondary story contains: category, impact, headline, one short factual summary, source.
5. A dark navy “ƯU TIÊN HÔM NAY” strip closes the page.
6. Do not place URLs, long department lists, or two full facts on the image.

COPY LIMITS
- Hero headline: <= 90 characters preferred, <= 3 lines.
- Hero fact/dek: <= 140 characters.
- Hero STACORP note: <= 160 characters.
- Secondary headline: <= 78 characters preferred, <= 2 lines.
- Secondary fact/dek: <= 92 characters.
- Source: publisher name only.
- action_today: <= 230 characters.
- Never shrink fonts to make copy fit; shorten copy instead.

VISUAL LANGUAGE
- Premium corporate editorial.
- Navy #0B2342, warm ivory, white, muted steel blue, champagne gold #C7A16A.
- Minimal borders, generous white space, subtle shadows.
- Headline hierarchy must dominate small metadata.
- Avoid dashboard-like widgets, oversized badges, heavy gradients, cluttered icons, and tiny text.

IMAGE REQUIREMENTS
- ChatGPT-generated editorial visuals; no text, numbers, logos, brands, watermarks, signs, labels, or readable signage.
- Photorealistic, bright, elegant, credible Vietnamese industrial/infrastructure/business context.
- Minimum production resolution for each visual: long edge >= 1400 px and short edge >= 900 px.
- Never upscale a low-resolution image for production.
- Hero image must have a clear focal point and enough negative space for overlaid copy.

DAILY RESEARCH/EDITORIAL GATE
- Scan broadly across current Vietnamese business, government, industrial, logistics, construction, finance, safety, technology and legal sources.
- Prefer sources published in the last 24–72 hours; use older items only when impact materially exceeds recency.
- Read state/published_hashes.json before selection and avoid repeating any story published in the previous 120 days unless there is a materially new development.
- Final selection must contain exactly 5 items and every item must score >= 7/10 on NEW + RELEVANT + MATERIAL + DISTINCT.
- Prefer official/primary sources for policy, legal, weather, public-investment and regulatory claims.
- Never infer legal obligations, effective dates or penalties beyond the official text.
- action_today is populated only when a clear action follows from at least one CAO item.

TEAMS POST
- One root post only.
- Title: “ĐIỂM TIN STACORP | DD.MM.YYYY”
- Insert the single final image at full available width.
- Under the image, list only five source names as clickable links.
- Add “Ưu tiên hôm nay” only if action_today is non-empty.
- Do not repeat the five headlines/facts in the Teams text.
