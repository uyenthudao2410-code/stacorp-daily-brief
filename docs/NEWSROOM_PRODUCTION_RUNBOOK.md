# STACORP Newsroom Production Runbook

## 1. Purpose
Publish exactly one daily **ĐIỂM TIN CHO DOANH NGHIỆP STACORP** to Microsoft Teams with a deterministic 3-page V4 newsroom layout. The workflow must be idempotent: never create a second Teams post for the same date after a successful production post already exists.

## 2. Fixed production target
- Repository: `uyenthudao2410-code/stacorp-daily-brief`
- Delivery branch: `chatgpt-delivery`
- Workflow: `Publish ChatGPT Daily Brief`
- Layout: `STACORP_EDITORIAL_3PAGE_FINAL_V4_NEWSROOM_8NEWS`
- Team ID: `85f93dd1-97df-43b4-88c2-a156e57b5223`
- Channel ID: `19:ae875099856a42569438d9c056e1294f@thread.tacv2`
- Target type: `channel`

Do not use OpenAI API, OPENAI_API_KEY, Codex, Power Automate or Outlook.

## 3. Idempotency preflight
Before any research or write:
1. Check today's `chatgpt-delivery` commit and GitHub Actions runs.
2. If today's newsroom workflow is queued/in_progress, follow that run instead of starting another.
3. If today's workflow is completed/success and logs contain `TEAMS_MESSAGE_ID=<id>`, stop. Do not repost.
4. If a workflow failed, inspect the failed stage. Retry only when the issue is recoverable and the production constraints remain valid.

## 4. Editorial contract
- Research 24–72 hours of fresh, material news.
- Read `state/published_hashes.json` and avoid duplicates within 120 days unless there is a material new development.
- Select exactly 8 items, each >=7/10.
- Regional balance: >=3 MIỀN BẮC, >=3 MIỀN TRUNG, <=2 TOÀN QUỐC. No South-only story.
- Maximum 3 items with impact `CAO`.
- Prefer official/primary sources, then official company/project sources, then major business press.
- Legal, public investment, weather and safety claims require an official source.
- Keep newsroom language neutral and useful for all STACORP staff; do not turn Page 3 into a departmental checklist.
- `brief.json` must comply with the V4 schema already enforced by `src/render.py`: exactly 8 items, exactly 2 facts/item, 2–5 departments/item, `summary_lede` 140–240 characters, exactly 4 `news_themes`, exactly 2 `regional_pulse`, exactly 4 `news_numbers`, and `action_today` normally empty.

## 5. Visual policy: fresh-first, certified fallback
### Primary
Create 8 fresh ChatGPT Images originals matching the 8 stories:
- photorealistic corporate editorial
- no text, numbers, logo, watermark or readable signage
- PNG/JPEG original only
- long edge >=1400 px
- short edge >=900 px
- bytes >=250000
- sharpness >=18.0
- never use preview, thumbnail, screenshot or WEBP

### Automatic fallback
If fresh originals cannot be transferred intact during the current run, **do not stop publication only because of image handoff**. Reuse the eight original `incoming/current/story-1..8.png` blobs from the latest successful `chatgpt-delivery` production run, provided:
1. the prior run completed successfully,
2. its logs contained `SOURCE_VISUAL_QUALITY_GATE=PASS`,
3. all eight source files remain present,
4. the current workflow's source visual quality gate passes again.

Fresh images are preferred. Fallback visuals are only a resilience path; the daily news text and sources must still be current and accurate.

## 6. Delivery construction
1. Fetch latest `main` HEAD and its tree immediately before creating the delivery.
2. Create a blob for today's `incoming/current/brief.json`.
3. Add today's fresh 8 source visuals or the certified fallback source-visual blobs.
4. Create a tree using the latest `main` tree as `base_tree_sha`.
5. Create the delivery commit with parent exactly equal to the latest `main` HEAD.
6. Compare `main...delivery`; require `ahead_by=1` and `behind_by=0`.
7. Force-update `chatgpt-delivery` to the delivery commit.
8. Never change templates, CSS, `config/approved_layout.json`, or logo during a daily run.

## 7. GitHub Actions gates
The workflow must pass:
- approved production layout verification
- `SOURCE_VISUAL_QUALITY_GATE=PASS`
- `LAYOUT_GEOMETRY_LOCK=PASS`
- render exactly 3 pages
- publish to the fixed production Teams target

If a fixable content-validation error occurs, correct the brief and rebuild one new delivery from the latest `main` HEAD. Do not disable the recurring schedule because a single run failed.

## 8. Success definition
A production day is successful only when:
1. the exact delivery workflow is `completed/success`, and
2. its logs contain `TEAMS_MESSAGE_ID=<id>`.

Only after that should `state/published_hashes.json` be updated by the workflow.

## 9. Watchdog behavior
The watchdog must:
- first perform the idempotency preflight,
- follow an existing in-progress run rather than starting another,
- automatically produce a missing daily delivery if no run exists,
- use certified visual fallback when image handoff is the only blocker,
- never create a duplicate Teams root post,
- never disable the 08:15 production schedule.

This runbook is the single source of truth for the daily newsroom automation.