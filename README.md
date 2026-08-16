# LP Followup Bot

Slack bot that runs a 4-step chase cycle for tracked threads.

## How it works

1. Users type `@lp-followup-bot track` in a thread to start tracking
2. Bot sends escalating reminders:
   - Step 1: `@poster - Please check if this issue is resolved.`
   - Step 2: `@poster @tech-loopback - Followup: Is this resolved?`
   - Step 3: `@poster @tech-loopback @oncall-tech-support - Followup: Is this resolved?`
   - Step 4: `@poster @tech-loopback @oncall-tech-support - Final followup. Reply "resolve" to close.`
3. After step 4, cycle repeats from step 1
4. Reply "resolve" in thread to stop reminders

## Setup

### 1. Create GitHub repo
Create a new **private** repository on GitHub.

### 2. Add Slack bot token as secret
1. Go to repo Settings → Secrets and variables → Actions
2. Click "New repository secret"
3. Name: `SLACK_BOT_TOKEN`
4. Value: `xoxb-...` (your bot token)

### 3. Push code
```bash
cd ~/lp-followup-bot-github
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/lp-followup-bot.git
git push -u origin main
```

### 4. Enable GitHub Actions
1. Go to repo → Actions tab
2. Click "I understand my workflows, go ahead and enable them"

## Configuration

Edit `.github/workflows/bot.yml`:

- `cron`: Schedule (default: every 15 minutes)
- `TEST_MODE`: "true" for 10-min step intervals, "false" for production intervals
- `CHANNEL_IDS`: Comma-separated list of Slack channel IDs to monitor (e.g., `C0B0S9A3BLZ,C0129EFQPM2`)

## Manual trigger

Go to Actions → LP Followup Bot → Run workflow
