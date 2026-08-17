# Slack Escalation Automation

A Python-based Slack automation that tracks escalation threads and sends scheduled follow-up reminders through a configurable multi-step chase cycle.

## How It Works

1. A user mentions the configured bot with `track` in a Slack thread.
2. The bot starts tracking the thread.
3. The bot sends escalating follow-up reminders through four steps.
4. After Step 4, the cycle repeats according to the configured behavior.
5. A `resolve` command stops the follow-up cycle.
6. A `pause` command can temporarily pause follow-ups.

The bot is configurable through environment variables, so Slack workspace-specific IDs and credentials are not hard-coded into the source code.

## Follow-up Cycle

- **Step 1:** Ask the requester to check whether the issue is resolved.
- **Step 2:** Notify the requester and escalation group.
- **Step 3:** Notify the requester, escalation group, and on-call group.
- **Step 4:** Send a final follow-up and request resolution confirmation.

## Project Structure

```text
slack-escalation-automation/
├── .github/
│   └── workflows/
│       └── bot.yml
├── .gitignore
├── README.md
├── bot.py
├── requirements.txt
└── state.json

```
## Configuration

The following environment variables are supported.

## Secrets
SLACK_BOT_TOKEN
GROQ_API_KEY

## Variables
BOT_USER_ID
BOT_NAME
CHANNEL_IDS
ESCALATION_GROUP_ID
ONCALL_GROUP_ID
TEST_MODE

Workspace-specific values should be stored in environment variables or GitHub Secrets/Variables rather than committed to the source code.

## Variable Descriptions
Variable	Type	Description
SLACK_BOT_TOKEN	Secret	Slack bot OAuth token
GROQ_API_KEY	Secret	Optional API key for AI-assisted summaries
BOT_USER_ID	Variable	Slack user ID of the bot
BOT_NAME	Variable	Slack bot display name
CHANNEL_IDS	Variable	Comma-separated Slack channel IDs
ESCALATION_GROUP_ID	Variable	Slack user group ID for escalation
ONCALL_GROUP_ID	Variable	Slack user group ID for on-call escalation
TEST_MODE	Variable	Enables shortened test intervals when set to true
Local Setup
Clone the repository
git clone https://github.com/phyominhtet-dev/slack-escalation-automation.git
cd slack-escalation-automation
Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate
Install dependencies
pip install -r requirements.txt
Configure environment variables

Before running the bot locally, configure the required environment variables.

At minimum:

SLACK_BOT_TOKEN
BOT_USER_ID
BOT_NAME
CHANNEL_IDS
ESCALATION_GROUP_ID
ONCALL_GROUP_ID

GROQ_API_KEY is optional.

Local Testing
Check Python syntax
python -m py_compile bot.py
Check Git formatting
git diff --check
Run the bot
python bot.py

If SLACK_BOT_TOKEN is not configured, the bot exits safely without making Slack API requests.

GitHub Actions

The bot runs through GitHub Actions on a scheduled interval.

The workflow:

Checks out the repository.
Sets up Python.
Installs dependencies from requirements.txt.
Loads configuration from GitHub Secrets and Variables.
Runs bot.py.

The default schedule is every 15 minutes.

The workflow can also be triggered manually from:

GitHub → Actions → Slack Escalation Automation → Run workflow

GitHub Secrets

Configure secrets under:

Repository → Settings → Secrets and variables → Actions → Secrets

Add:

SLACK_BOT_TOKEN
GROQ_API_KEY

GROQ_API_KEY is optional if AI-assisted summaries are not required.

GitHub Variables

Configure variables under:

Repository → Settings → Secrets and variables → Actions → Variables

Add:

BOT_USER_ID
BOT_NAME
CHANNEL_IDS
ESCALATION_GROUP_ID
ONCALL_GROUP_ID

TEST_MODE is configured by the workflow and can be changed there when required for testing.

Security

Do not commit:

Slack bot tokens
API keys
Workspace-specific credentials
Sensitive runtime data

Store secrets in GitHub Secrets or environment variables.

The .gitignore file also excludes local virtual environments and environment files.

Purpose

This project demonstrates:

Python automation
Slack API integration
Environment-based configuration
Scheduled GitHub Actions
Multi-step escalation workflows
Git and GitHub workflow management
Optional AI-assisted resolution summaries