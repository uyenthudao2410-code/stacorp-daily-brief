# STACORP Daily Brief

Automated enterprise-news brief for STACORP. The project scans current business news, selects exactly five material items, renders a two-page 1120x1400 image brief, and can post both pages inline to Microsoft Teams.

## Design principles

- Image-first output: Teams receives two final PNG pages, so Teams does not reflow the newsletter typography.
- No permanent image archive: production images live only on the GitHub runner and are discarded after posting.
- Deterministic text rendering: Vietnamese text is rendered by HTML/CSS + Playwright, not generated inside an AI image.
- Publication guardrails: no publish unless exactly five items pass the editorial checks.
- Small persistent state only: article hashes are kept in `state/published_hashes.json` to prevent repeats. No newsletter PNGs are committed.

## Schedule

GitHub Actions uses `30 1 * * *`, which is 08:30 in Vietnam (UTC+7). Vietnam does not use daylight-saving time.

Scheduled publishing is OFF until repository variable `AUTOMATION_ENABLED` is set to `true`.

## Required GitHub Secrets and Variables

News selection:
- Secret `OPENAI_API_KEY`
- Optional variable `OPENAI_MODEL` (default: `gpt-5-mini`)

Microsoft Graph delegated publishing:
- Secret `MS_TENANT_ID`
- Secret `MS_CLIENT_ID`
- Secret `MS_REFRESH_TOKEN`
- Optional secret `MS_CLIENT_SECRET` if the Entra app is confidential

Current test group chat:
- Variable `TEAMS_TARGET_TYPE=chat`
- Secret `TEAMS_CHAT_ID=19:0e02d613cded448892f27d74cff19d63@thread.v2`

Official channel later:
- Variable `TEAMS_TARGET_TYPE=channel`
- Secret `TEAMS_TEAM_ID=85f93dd1-97df-43b4-88c2-a156e57b5223`
- Secret `TEAMS_CHANNEL_ID=19:ae875099856a42569438d9c056e1294f@thread.tacv2`

Never put tokens, secrets, or credentials in this public repository.

## First run

1. Create/configure a Microsoft Entra application with delegated permissions `ChatMessage.Send`, `ChannelMessage.Send`, and `offline_access`.
2. Enable public client flow if using the included device-code bootstrap script.
3. Run locally:
   ```bash
   python -m pip install -r requirements.txt
   python scripts/bootstrap_ms_refresh_token.py --tenant <tenant-id> --client-id <client-id>
   ```
4. Store the printed refresh token as GitHub secret `MS_REFRESH_TOKEN`.
5. Configure the remaining GitHub secrets and variables.
6. In GitHub Actions, run **STACORP Daily Brief** manually with `demo=true`, `publish=false`.
7. Download the 1-day preview artifact and review the two PNG pages.
8. Run again with `demo=true`, `publish=true` to test the Teams group chat.
9. Only after approval, set repository variable `AUTOMATION_ENABLED=true`.

## Local demo

```bash
python -m pip install -r requirements.txt
python -m playwright install chromium
python -m src.main --demo
```

Outputs are created under `/tmp/stacorp-daily-brief` and are not persisted by the repository.

## Teams delivery

The publisher uses Microsoft Graph chat messages with `hostedContents`. The two PNGs are Base64-encoded into the Teams message as inline images. They are not uploaded to SharePoint/OneDrive by this project.

Production flow:

```text
GitHub Actions
  -> collect 50-80 candidates
  -> editorial filter and select exactly 5
  -> render Page 1 + Page 2
  -> validate dimensions/file size
  -> POST to Teams as inline hosted images
  -> retain only article hashes for deduplication
  -> runner ends and temporary PNGs disappear
```

## Editorial rules

The production prompt enforces:
- NEW -> RELEVANT -> MATERIAL -> DISTINCT
- shortlist 12-18 internally
- exactly five final items, each >= 7/10
- balanced opportunity / market / cost-finance / worksite mix
- normally no more than three HIGH-impact items
- exactly two supported facts per item
- 2-5 genuinely relevant departments
- no default "Toàn công ty"
- source and publication date preserved
- legal/risk items require an official-source candidate
- no publication when fewer than five items pass the quality gate
- "VIỆC CẦN LÀM" only when a clear action follows from HIGH-impact news

## Repository layout

```text
.github/workflows/
  ci.yml
  daily-brief.yml
config/
  news_queries.json
sample/
  brief.sample.json
scripts/
  bootstrap_ms_refresh_token.py
src/
  collect_news.py
  main.py
  models.py
  publish_teams.py
  rank_news.py
  render.py
  state.py
  validate.py
state/
  published_hashes.json
templates/
  page1.html
  page2.html
  style.css
```
