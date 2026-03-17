---
name: linkedin-publish
description: "Guardrailed LinkedIn publishing skill. Posts approved content to LinkedIn via OAuth 2.0 REST API. Requires explicit user approval ('Approve Option X') before execution."
---

# LinkedIn Publish Skill

## Token Efficiency Rules
- Do not repeat full drafts during approval validation; check only the selected option.
- Keep status replies short and outcome-first (success/failure + next action).
- Avoid routine operational narration unless needed to explain an error.
- Keep active publishing context minimal (option number + final text + hashtags).

## ⚠️ CRITICAL GUARDRAIL ⚠️
**NEVER execute any publishing action unless the user has sent the EXACT phrase:**
- `Approve Option 1`
- `Approve Option 2`
- `Approve Option 3`

If the user says anything else that implies they want to publish (e.g., "ok", "send it", "lgtm", "publish it"),
reply with:
> "To confirm publication, please reply exactly: **Approve Option X** (X = 1, 2, or 3)"

## Prerequisites
1. LinkedIn Developer App with **"Share on LinkedIn"** product enabled
2. OAuth 2.0 access token stored in `.env` as `LINKEDIN_ACCESS_TOKEN`
3. User's LinkedIn Person URN stored in `.env` as `LINKEDIN_PERSON_URN`
4. Python 3.10+ with dependencies installed:
   ```bash
   uv sync
   ```

## Initial OAuth Setup
If the user hasn't authenticated yet, run the OAuth flow:
```bash
python skills/linkedin-publish/scripts/linkedin_oauth.py
```
This will:
1. Print an authorization URL → user opens in browser
2. Start a local callback server on `http://localhost:3000/callback`
3. Exchange the auth code for an access token
4. Save the token to `.env`
5. Fetch and save the user's Person URN

## Publishing Workflow

### Step 1: Validate Approval
Confirm that:
- [x] User sent "Approve Option X" (exact match)
- [x] The referenced option exists in the current conversation
- [x] No revision was requested after the last draft

### Step 2: Prepare Content
Extract from the approved option:
- **Post text**: The full draft body
- **Hashtags**: As a space-separated string

### Step 3: Execute Publish Script
```bash
python skills/linkedin-publish/scripts/linkedin_post.py \
  --text "Full post text here..." \
  --hashtags "#AI #DataEngineering #Python"
```

### Step 4: Report Result
Parse the script's stdout:
- **On success (exit code 0)**: Report the post URL to the user
  > "Post published successfully! 🎉 [link]"
- **On failure (exit code 1)**: Report the error
  > "Failed to publish: [error]. Please verify the LinkedIn token."

Use concise reporting format; provide deeper technical details only on request.

## Dry-Run Mode
For testing without actually posting:
```bash
python skills/linkedin-publish/scripts/linkedin_post.py \
  --text "Test post" \
  --hashtags "#test" \
  --dry-run
```
This prints the API payload without calling the LinkedIn API.

## Troubleshooting
| Error | Cause | Solution |
|---|---|---|
| `401 Unauthorized` | Token expired | Re-run `linkedin_oauth.py` |
| `403 Forbidden` | Missing `w_member_social` scope | Enable "Share on LinkedIn" in dev portal |
| `422 Unprocessable` | Post too long or invalid format | Check character limit (3000 chars) |
