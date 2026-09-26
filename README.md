# STACORP Daily Brief

Automated enterprise-news brief for STACORP. The project scans current business news, selects exactly five material items, renders a two-page 1120x1400 executive brief, and can post both pages inline to Microsoft Teams.

## V3 design and brand rules

- Light, elegant, professional visual system approved for daily use.
- Page 1: executive header, four KPI tiles, one lead story, two supporting stories, optional action strip.
- Page 2: two follow-up stories plus an impact-summary panel.
- Vietnamese text is rendered deterministically with HTML/CSS + Playwright.
- Story photography can be generated separately with the OpenAI Image API.
- Generated story images are strictly unbranded: no text, no signage, no logos, no STACORP marks.
- The STACORP logo is the approved local asset at `assets/stacorp-logo.png`.
- Rendering verifies the exact approved Git blob identity of the logo and refuses to build if that file is modified or replaced.

## Storage

- Final PNG pages and AI story visuals exist only on the GitHub runner.
- They are not committed to the repository and are not archived in SharePoint/OneDrive.
- After posting, Teams retains the inline message content; the runner's temporary files disappear.
- Only lightweight article hashes are committed to `state/published_hashes.json` to prevent duplicate news.

## Schedule

GitHub Actions uses `30 1 * * *`, which is 08:30 in Vietnam (UTC+7).

Scheduled production is OFF until repository variable:

```text
AUTOMATION_ENABLED=true
```

## Required GitHub configuration

### Secrets

- `OPENAI_API_KEY`
- `MS_TENANT_ID`
- `MS_CLIENT_ID`
- `MS_REFRESH_TOKEN`
- optional `MS_CLIENT_SECRET`
- `TEAMS_CHAT_ID` for test chat
- later: `TEAMS_TEAM_ID`, `TEAMS_CHANNEL_ID` for the official channel

### Variables

- `OPENAI_MODEL=gpt-5.6-terra`
- `OPENAI_IMAGE_MODEL=gpt-image-2.5-flare`
- `TEAMS_TARGET_TYPE=chat`
- `AUTOMATION_ENABLED=false` until final approval

Keep all credentials and tenant-specific identifiers in GitHub Secrets/Variables, never in this public repository.

## Manual preview

In **Actions -> STACORP Daily Brief -> Run workflow**:

For a zero-cost layout preview:

```text
demo=true
visuals=false
publish=false
preview_artifact=true
```

For the approved photo-rich V3 look after `OPENAI_API_KEY` is configured:

```text
demo=true
visuals=true
publish=false
preview_artifact=true
```

For a Teams test:

```text
demo=true
visuals=true
publish=true
preview_artifact=false
```

Only a successful Microsoft Graph response containing a Teams message ID is treated as a successful publication.

## Production pipeline

```text
GitHub Actions 08:30
  -> collect 50-80 candidates
  -> filter NEW -> RELEVANT -> MATERIAL -> DISTINCT
  -> select exactly 5 stories >= 7/10
  -> generate five unbranded editorial visuals
  -> verify approved STACORP logo identity
  -> render V3 Page 1 + Page 2
  -> validate dimensions and file size
  -> POST both PNGs to Teams as inline hosted content
  -> save only deduplication hashes
  -> temporary images disappear with the runner
```

## Editorial rules

- shortlist 12-18 internally
- exactly five final items, each >= 7/10
- balanced opportunity / market / cost-finance / worksite mix
- normally no more than three HIGH-impact items
- exactly two supported facts per item
- 2-5 genuinely relevant departments
- never default to "Toàn công ty"
- preserve source and publication date
- legal/risk items require an official-source candidate
- do not publish when fewer than five items pass
- only show "VIỆC CẦN LÀM" when a clear action follows from HIGH-impact news

## Microsoft Entra

The included helper `scripts/bootstrap_ms_refresh_token.py` uses delegated Microsoft Graph permissions.

Required delegated permissions:

- `ChatMessage.Send`
- `ChannelMessage.Send`
- `offline_access`

After the app is configured and public-client flow is enabled, run:

```bash
python -m pip install -r requirements.txt
python scripts/bootstrap_ms_refresh_token.py --tenant <tenant-id> --client-id <client-id>
```

Store the resulting refresh token as GitHub secret `MS_REFRESH_TOKEN`.

## Repository layout

```text
.github/workflows/
  ci.yml
  daily-brief.yml
assets/
  stacorp-logo.png
config/
  news_queries.json
sample/
  brief.sample.json
scripts/
  bootstrap_ms_refresh_token.py
src/
  collect_news.py
  generate_visuals.py
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
