#!/usr/bin/env python3
"""
Slack Escalation Automation - 4-step chase cycle for tracked Slack threads.
Runs via GitHub Actions on schedule.
"""

import os
import json
import time
import requests
from datetime import datetime

# Configuration
SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
TEST_MODE = os.environ.get("TEST_MODE", "false").lower() == "true"
AI_ENABLED = bool(GROQ_API_KEY)
CHANNEL_IDS = [
    c.strip()
    for c in os.environ.get("CHANNEL_IDS", "").split(",")
    if c.strip()
]

# User group IDs
ESCALATION_GROUP_ID = os.environ.get("ESCALATION_GROUP_ID", "")
ONCALL_GROUP_ID = os.environ.get("ONCALL_GROUP_ID", "")

# Bot user ID used to detect direct Slack mentions
BOT_USER_ID = os.environ.get("BOT_USER_ID", "")
BOT_NAME = os.environ.get("BOT_NAME", "slack-escalation-bot")

# Timing (seconds) - per step delays
# Using 10 min (600s) to ensure cron (every 15 min) always catches it
if TEST_MODE:
    STEP_DELAYS = {1: 600, 2: 600, 3: 600, 4: 600}  # 10 min each in test
    CYCLE_DELAY = 600  # 10 min to restart loop
else:
    STEP_DELAYS = {1: 14400, 2: 600, 3: 600, 4: 600}  # 4hrs, 10min, 10min, 10min
    CYCLE_DELAY = 86400  # 24 hrs to restart loop

# State file (stored as GitHub artifact or in repo)
STATE_FILE = "state.json"


def call_groq(prompt, max_tokens=200):
    """Call Groq AI API for analysis."""
    if not GROQ_API_KEY:
        return None

    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "llama-3.1-8b-instant",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
                "temperature": 0.1
            },
            timeout=10
        )
        data = response.json()
        return data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
    except Exception as e:
        print(f"Groq API error: {e}")
        return None


def ai_check_resolved(thread_messages):
    """Use AI to detect if thread indicates issue is resolved."""
    if not AI_ENABLED or not thread_messages:
        return False, None

    conversation = "\n".join([f"- {m}" for m in thread_messages[-10:]])
    prompt = f"""Analyze this Slack thread and determine if the issue has been resolved.

Thread messages:
{conversation}

Reply with ONLY "YES" if the issue is clearly resolved (e.g., "fixed", "thanks it works", "all good", "sorted", "done"), or "NO" if not resolved or unclear."""

    result = call_groq(prompt, max_tokens=10)
    if result and "YES" in result.upper():
        return True, "AI detected resolution"
    return False, None


def ai_summarize_thread(thread_messages):
    """Use AI to summarize the thread issue."""
    if not AI_ENABLED or not thread_messages:
        return None

    conversation = "\n".join([f"- {m}" for m in thread_messages[:10]])
    prompt = f"""Summarize this Slack thread in ONE short sentence (max 15 words).

Rules:
- Focus on the operational impact to passenger, driver, or merchant
- Use plain language, zero technical jargon
- Be specific about what's affected (e.g., "Driver unable to receive bookings" not "API timeout issue")

Thread:
{conversation}

Summary:"""

    return call_groq(prompt, max_tokens=30)


def ai_summarize_resolution(thread_messages):
    """Use AI to summarize issue + resolution for client reply."""
    if not AI_ENABLED or not thread_messages:
        return None

    conversation = "\n".join([f"- {m}" for m in thread_messages[-15:]])
    prompt = f"""Summarize this resolved support thread for the support team to provide a resolution update to the requester.

Thread:
{conversation}

Provide in this format (2-3 lines max, plain language, no jargon):
Issue: [what the client experienced]
Resolution: [what was done / answer to give client]"""

    return call_groq(prompt, max_tokens=200)


def slack_api_get(method, **kwargs):
    """Make Slack API GET call with query params (for read operations)."""
    url = f"https://slack.com/api/{method}"
    headers = {"Authorization": f"Bearer {SLACK_BOT_TOKEN}"}
    response = requests.get(url, headers=headers, params=kwargs)
    data = response.json()
    if not data.get("ok"):
        print(f"Slack API error ({method}): {data.get('error')}")
    return data


def slack_api_post(method, **kwargs):
    """Make Slack API POST call with JSON body (for write operations)."""
    url = f"https://slack.com/api/{method}"
    headers = {
        "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
        "Content-Type": "application/json; charset=utf-8"
    }
    response = requests.post(url, headers=headers, json=kwargs)
    data = response.json()
    if not data.get("ok"):
        print(f"Slack API error ({method}): {data.get('error')} - response: {data}")
    return data


def get_channel_history(channel_id, oldest=None, limit=100):
    """Get channel messages."""
    params = {"channel": channel_id, "limit": limit}
    if oldest:
        params["oldest"] = str(oldest)
    return slack_api_get("conversations.history", **params)


def get_thread_replies(channel_id, thread_ts):
    """Get thread replies."""
    return slack_api_get("conversations.replies", channel=channel_id, ts=thread_ts)


def post_message(channel_id, text, thread_ts=None):
    """Post message to channel or thread."""
    params = {"channel": channel_id, "text": text}
    if thread_ts:
        params["thread_ts"] = thread_ts
    return slack_api_post("chat.postMessage", **params)


def load_state():
    """Load tracking state from file."""
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {"threads": {}, "config": {"test_mode": TEST_MODE}}


def save_state(state):
    """Save tracking state to file."""
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def get_step_message(step, poster_id, summary=None):
    """Get message for each chase step."""
    summary_line = f"\n> _{summary}_\n" if summary else ""
    messages = {
        1: f"<@{poster_id}> - Please check if this issue is resolved.{summary_line}",
        2: f"<@{poster_id}> <!subteam^{ESCALATION_GROUP_ID}> - Followup: Is this resolved?{summary_line}",
        3: f"<@{poster_id}> <!subteam^{ESCALATION_GROUP_ID}> <!subteam^{ONCALL_GROUP_ID}> - Followup: Is this resolved?{summary_line}",
        4: f"<@{poster_id}> <!subteam^{ESCALATION_GROUP_ID}> <!subteam^{ONCALL_GROUP_ID}> - Final followup. Reply \"resolve\" to close.{summary_line}",
    }
    return messages.get(step, messages[1])


def is_bot_mentioned(text):
    """Check if bot is mentioned in text."""
    text_lower = text.lower()
    bot_mention = f"<@{BOT_USER_ID.lower()}>"
    return bot_mention in text_lower or f"@{BOT_NAME.lower()}" in text_lower


def find_track_commands(state):
    """Find new bot track commands in all channels and threads."""
    now = time.time()
    oldest = int(now - (7 * 86400))  # Last 7 days (integer timestamp)
    new_threads = []

    for channel_id in CHANNEL_IDS:
        result = get_channel_history(channel_id, oldest=oldest, limit=200)
        if not result.get("ok"):
            print(f"Failed to get channel history for {channel_id}: {result.get('error')}")
            continue

        messages = result.get("messages", [])
        print(f"DEBUG: Channel {channel_id} returned {len(messages)} messages")

        # Check main channel messages AND their thread replies
        for msg in messages:
            thread_ts = msg.get("thread_ts", msg.get("ts"))
            thread_key = f"{channel_id}_{thread_ts}"
            original_poster_id = msg.get("user")  # Always the thread starter

            # Skip if already tracked
            if thread_key in state["threads"]:
                continue

            # Check if this main message has a track command
            text = msg.get("text", "").lower()
            raw_text = msg.get("text", "")
            if "track" in text:
                print(f"DEBUG: Found 'track' in message: {raw_text[:100]}")
            if is_bot_mentioned(msg.get("text", "")) and "track" in text:
                new_threads.append({
                    "thread_key": thread_key,
                    "channel_id": channel_id,
                    "thread_ts": thread_ts,
                    "poster_id": original_poster_id,  # Original thread poster
                    "tracked_by": msg.get("user"),  # Who called track
                    "track_command_ts": msg.get("ts"),
                })
                continue

            # Check thread replies for track command
            reply_count = msg.get("reply_count", 0)
            if reply_count > 0:
                replies_result = get_thread_replies(channel_id, msg.get("ts"))
                if replies_result.get("ok"):
                    for reply in replies_result.get("messages", []):
                        reply_text = reply.get("text", "")
                        if is_bot_mentioned(reply_text) and "track" in reply_text.lower():
                            new_threads.append({
                                "thread_key": thread_key,
                                "channel_id": channel_id,
                                "thread_ts": msg.get("ts"),  # Parent message ts
                                "poster_id": original_poster_id,  # Original thread poster
                                "tracked_by": reply.get("user"),  # Who called track
                                "track_command_ts": reply.get("ts"),
                            })
                            break  # Found track command, no need to check more replies

    return new_threads


def check_resolve_commands(state):
    """Check for resolve, pause, and retrack commands in tracked threads."""
    resolved = []
    paused = []
    retracked = []

    for thread_key, thread in state["threads"].items():
        status = thread.get("status")

        # Check RESOLVED threads for retrack command
        if status == "RESOLVED":
            result = get_thread_replies(thread["channel_id"], thread["thread_ts"])
            if not result.get("ok"):
                continue

            resolved_at = float(thread.get("resolved_at", 0))

            for reply in result.get("messages", []):
                reply_ts = float(reply.get("ts", 0))
                user = reply.get("user", "")

                # Only check messages AFTER resolution
                if reply_ts <= resolved_at:
                    continue

                # Ignore bot's own messages
                if user == BOT_USER_ID:
                    continue

                text = reply.get("text", "").lower()

                # Check for retrack command
                if "retrack" in text:
                    thread["status"] = "OPEN"
                    thread["current_step"] = 0
                    thread["last_prompt_time"] = 0
                    thread["retracked_at"] = int(time.time())
                    thread["retracked_by"] = user
                    thread["retrack_count"] = thread.get("retrack_count", 0) + 1
                    retracked.append(thread)

                    post_message(
                        thread["channel_id"],
                        f"Noted. Case retracked (#{thread['retrack_count']}). Follow-up will resume.",
                        thread["thread_ts"]
                    )
                    break
            continue

        if status != "OPEN":
            continue

        result = get_thread_replies(thread["channel_id"], thread["thread_ts"])
        if not result.get("ok"):
            continue

        track_ts = float(thread.get("track_command_ts", 0))
        last_pause_ts = float(thread.get("last_pause_ts", 0))
        last_ai_check_ts = float(thread.get("last_ai_check_ts", 0))

        thread_messages = []
        found_command = False

        for reply in result.get("messages", []):
            reply_ts = float(reply.get("ts", 0))
            user = reply.get("user", "")

            # Only consider messages AFTER the track command
            if reply_ts <= track_ts:
                continue

            # Ignore bot's own messages
            if user == BOT_USER_ID:
                continue

            # Collect messages for AI analysis
            thread_messages.append(reply.get("text", ""))

            # Only consider messages AFTER last pause (if any)
            if reply_ts <= last_pause_ts:
                continue

            text = reply.get("text", "").lower()

            # Check for resolve command (case-insensitive)
            # Match: "resolve", "resolved", "Resolved", etc.
            if "resolve" in text:
                thread["status"] = "RESOLVED"
                thread["resolved_at"] = int(time.time())
                thread["resolved_by"] = user
                thread["resolved_method"] = "command"
                resolved.append(thread)

                # Generate AI summary for client reply
                resolution_summary = ai_summarize_resolution(thread_messages)
                if resolution_summary:
                    close_msg = f"Noted. Case Closed\n\n{resolution_summary}"
                else:
                    close_msg = "Noted. Case Closed"

                # Post confirmation
                post_message(
                    thread["channel_id"],
                    close_msg,
                    thread["thread_ts"]
                )
                found_command = True
                break

            # Check for pause command
            # Match: "@<BOT_NAME> pause"
            if is_bot_mentioned(reply.get("text", "")) and "pause" in text:
                # Reset to step 0 and set last_prompt_time to now - will wait 24h
                thread["current_step"] = 0
                thread["last_prompt_time"] = int(time.time())
                thread["last_pause_ts"] = reply_ts
                thread["paused_by"] = user
                found_command = True
                paused.append(thread)

                # Post confirmation
                post_message(
                    thread["channel_id"],
                    "Noted. Follow-up paused for 24 hours.",
                    thread["thread_ts"]
                )
                break

        # AI resolution detection (only if no command found and AI enabled)
        if not found_command and AI_ENABLED and thread_messages:
            # Only run AI check once per hour to save API calls
            now = time.time()
            if now - last_ai_check_ts > 3600:
                thread["last_ai_check_ts"] = int(now)
                is_resolved, reason = ai_check_resolved(thread_messages)
                if is_resolved:
                    thread["status"] = "RESOLVED"
                    thread["resolved_at"] = int(now)
                    thread["resolved_by"] = "AI"
                    thread["resolved_method"] = "ai_detected"
                    resolved.append(thread)
                    print(f"AI detected resolution for {thread_key}")

                    # Generate AI summary for client reply
                    resolution_summary = ai_summarize_resolution(thread_messages)
                    if resolution_summary:
                        close_msg = f"Issue appears resolved. Closing follow-up.\n\n{resolution_summary}\n\n_(Reply 'retrack' if needed)_"
                    else:
                        close_msg = "Issue appears resolved. Closing follow-up. (Reply 'retrack' if needed)"

                    post_message(
                        thread["channel_id"],
                        close_msg,
                        thread["thread_ts"]
                    )

    return resolved


def run_chase_cycle(state):
    """Run chase cycle for open threads."""
    now = int(time.time())
    prompts_sent = []

    for thread_key, thread in state["threads"].items():
        if thread.get("status") != "OPEN":
            continue

        current_step = thread.get("current_step", 0)
        last_prompt_time = thread.get("last_prompt_time", 0)
        time_since_last = now - last_prompt_time

        # Determine required delay based on current step
        # After step N, wait STEP_DELAYS[N] before sending step N+1
        if current_step == 0:
            # Check if this was paused - if so, wait 24 hours
            if thread.get("last_pause_ts"):
                required_delay = 86400  # 24 hours after pause
            else:
                required_delay = 0  # First prompt immediately
        elif current_step == 4:
            required_delay = CYCLE_DELAY  # Wait before restarting cycle
        else:
            required_delay = STEP_DELAYS.get(current_step, 900)  # Wait after current step

        print(f"DEBUG: {thread_key} - step={current_step}, time_since={time_since_last}s, required={required_delay}s, ready={time_since_last >= required_delay}")

        # Check if it's time for next prompt
        if time_since_last >= required_delay:
            next_step = current_step + 1 if current_step < 4 else 1

            # If cycling back to step 1, increment cycle count
            if current_step == 4:
                thread["cycle_count"] = thread.get("cycle_count", 1) + 1

            # Get AI summary for first message of each cycle (optional)
            summary = None
            if AI_ENABLED and next_step == 1:
                replies = get_thread_replies(thread["channel_id"], thread["thread_ts"])
                if replies.get("ok"):
                    thread_messages = [m.get("text", "") for m in replies.get("messages", [])[:10]]
                    summary = ai_summarize_thread(thread_messages)
                    if summary:
                        thread["ai_summary"] = summary

            # Get and send message
            message = get_step_message(next_step, thread["poster_id"], summary)
            result = post_message(thread["channel_id"], message, thread["thread_ts"])

            if result.get("ok"):
                thread["current_step"] = next_step
                thread["last_prompt_time"] = now
                prompts_sent.append({
                    "thread_key": thread_key,
                    "step": next_step,
                    "cycle": thread.get("cycle_count", 1)
                })
                print(f"Sent step {next_step} to thread {thread_key}")
            else:
                print(f"Failed to send message: {result.get('error')}")

    return prompts_sent


def main():

    print(f"Channels: {CHANNEL_IDS}")
    print(f"{BOT_NAME} starting... (TEST_MODE={TEST_MODE})")
    if not SLACK_BOT_TOKEN:
        print("ERROR: SLACK_BOT_TOKEN not set")
        return

    # Load state
    state = load_state()

    # Step 1: Find new track commands
    new_threads = find_track_commands(state)
    for thread in new_threads:
        thread_key = thread["thread_key"]
        state["threads"][thread_key] = {
            "status": "OPEN",
            "channel_id": thread["channel_id"],
            "thread_ts": thread["thread_ts"],
            "poster_id": thread["poster_id"],  # Original thread poster (who to tag)
            "tracked_by": thread.get("tracked_by"),  # Who called track command
            "track_command_ts": thread["track_command_ts"],
            "first_seen": int(time.time()),
            "current_step": 0,
            "last_prompt_time": 0,
            "cycle_count": 1,
        }
        print(f"New thread tracked: {thread_key}")

    # Step 2: Check for resolve commands
    resolved = check_resolve_commands(state)
    for r in resolved:
        print(f"Thread resolved: {r['thread_ts']} by {r['resolved_by']}")

    # Step 3: Run chase cycle
    prompts_sent = run_chase_cycle(state)

    # Step 4: Save state
    save_state(state)

    # Summary
    open_count = sum(1 for t in state["threads"].values() if t.get("status") == "OPEN")
    resolved_count = sum(1 for t in state["threads"].values() if t.get("status") == "RESOLVED")

    print(f"\n=== Summary ===")
    print(f"New threads tracked: {len(new_threads)}")
    print(f"Prompts sent: {len(prompts_sent)}")
    print(f"Threads resolved: {len(resolved)}")
    print(f"Total open: {open_count}, Total resolved: {resolved_count}")


if __name__ == "__main__":
    main()
