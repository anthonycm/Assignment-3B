# Uptime Monitor

A lightweight script that checks whether a website is reachable and posts a
Discord alert the moment its status changes (up → down or down → up). It's
meant to run unattended on a schedule (e.g. via GitHub Actions) — it does
**not** alert on every run, only when the status actually flips.

## How it works

- Sends an HTTP GET to `TARGET_URL` with a timeout.
- A non-2xx response, timeout, or connection error counts as a failed check.
- The site is only declared **down** after **2 consecutive failed checks**,
  to avoid a false alarm from a single flaky request.
- The last known status is stored in a local state file (`state.json` by
  default). A Discord alert is only sent when the status actually changes.
- On the very first run (no state file yet), the script just records the
  initial status — it won't send an alert unless a real transition happens
  on a later run.

## Configuration

All configuration is via environment variables — nothing is hardcoded.

| Variable | Required | Default | Description |
|---|---|---|---|
| `TARGET_URL` | No | `https://www.uwrf.edu/` | The website to monitor. |
| `DISCORD_WEBHOOK_URL` | **Yes** | — | Discord webhook URL to post alerts to. Never hardcode this — set it as a secret. |
| `SITE_NAME` | No | derived from `TARGET_URL` | Friendly name used in the alert message. |
| `STATE_FILE` | No | `state.json` | Path to the local state file. |
| `TIMEOUT_SECONDS` | No | `10` | Request timeout in seconds. |

## Local usage

```bash
pip install -r requirements.txt
export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."
export TARGET_URL="https://www.uwrf.edu/"
python uptime_monitor.py
```

Run it again after the site goes down (or comes back up) to see the alert
fire. `state.json` will be created next to the script — it's excluded from
git via `.gitignore` since it's local run state, not source.

## Running on a schedule with GitHub Actions

A workflow is included at `.github/workflows/uptime-check.yml` that runs the
check on a cron schedule.

1. Push this project to a GitHub repository.
2. In the repo, go to **Settings → Secrets and variables → Actions** and add
   a repository secret named `DISCORD_WEBHOOK_URL` with your Discord webhook
   URL as the value.
3. Adjust the `cron` schedule in the workflow file if you want a different
   check interval (GitHub Actions schedules are not guaranteed to run at
   exact times, especially at high frequency).
4. Since `state.json` is gitignored, the workflow uses `actions/cache` to
   persist it between scheduled runs so status changes are detected
   correctly across runs.

## Getting a Discord webhook URL

In Discord: **Server Settings → Integrations → Webhooks → New Webhook**,
pick the channel, then copy the webhook URL. Treat this URL as a secret —
anyone with it can post messages into that channel.

## Files

- `uptime_monitor.py` — the monitor script.
- `requirements.txt` — Python dependencies.
- `.gitignore` — excludes the state file and any local secrets files.
- `.github/workflows/uptime-check.yml` — scheduled GitHub Actions workflow.
