# Phaze Usage Dashboard

A single-file HTML dashboard that shows how a Phaze enterprise is actually used: who connects when, how busy each machine is, peak load, session lengths, fleet and relay health. A second tab turns the same data into savings suggestions, such as sessions left open overnight and workstations that could be pooled, with an editable price model.

It's built only on the Phaze Enterprise API, with one read-only API key and no agent on the machines. This is a sales-engineering tool, not a product feature.

## What's in it

Usage tab:
- Key numbers: session hours, active people, machines used, peak concurrency, median session, connect success rate, sessions live right now
- Heatmap of simultaneous sessions per hour of the week, plus the busiest hours
- Session hours per day, per organization
- Session length distribution
- People and machine utilization tables
- Fleet (online state, assignment, OS, Phaze version, release channel) and relay health

Savings & suggestions tab:
- Monthly and yearly bill today versus after the suggested changes
- Sessions that ran longer than a cutoff (default 8 hours), with the hours they added
- Rarely used workstations that could move into a shared pool
- Idle seats compared with per-seat pricing elsewhere
- An assumptions panel (hourly rate, monthly cap, cutoff, commit discount, workstation cost) that recalculates every figure. Values are saved in the browser.

Filters for organization, period (all time, 90, 30 or 7 days) and time zone apply across the page.

## Try it without an API key

The repo ships a synthetic studio (`sample_data.json`: 3 organizations, 27 people, 34 machines, about 2,300 sessions), so you can build and open the dashboard straight away:

```bash
git clone https://github.com/phazemichael/phaze-usage-dashboard.git
cd phaze-usage-dashboard
python build.py
```

Then open `Phaze Usage Dashboard.html` in a browser. It's fully self-contained (data, fonts, scripts), so you can also send the file to someone.

`python make_sample.py` regenerates the sample. It's seeded, so the output stays the same unless you change the script.

## Use your own data

Requirements: Python 3.10+ (standard library only) and a Phaze Enterprise API key.

Create a `.env` file next to `fetch.py` (never commit it):

```
PHAZE_API_KEY=your_phaze_enterprise_api_key
# optional
PHAZE_API_BASE=https://public-api.phaze.app/enterprise/v1
```

Then:

```bash
python fetch.py    # read-only snapshot of every organization the key can see
python build.py    # embeds data.json into the HTML
```

`fetch.py` writes two files:
- `raw.json`: the API responses as they came back, with real names and emails. It stays on your machine.
- `data.json`: the pseudonymized version the dashboard embeds. People become "Artist 01", "Artist 02", ... and machines "WS-01", "WS-02", ..., ranked by usage. Groups, locations and relays get neutral labels too. Organization names are kept.

`python fetch.py --offline` rebuilds `data.json` from an existing `raw.json` without calling the API.

`build.py` uses `data.json` when it exists and falls back to the sample. Use `python build.py --sample` to force the sample.

Organizations without any connections are skipped (`SKIP_EMPTY_ORGS` in `fetch.py`).

## API calls

All GET, all read-only:

```
GET /orgs
GET /orgs/{org_id}/connections
GET /orgs/{org_id}/machines
GET /orgs/{org_id}/members
GET /orgs/{org_id}/groups
GET /locations
GET /relays
```

Locations and relays moved to the enterprise level in November 2026. `fetch.py` gives each organization the locations its machines are in and the relays at those locations, and falls back to the older per-org routes if the new ones aren't there.

## How the numbers are calculated

- A session runs from `connected_at` to `disconnected_at`. If there's no disconnect, it ends at the last heartbeat. A session with a heartbeat in the last 3 minutes counts as live.
- A connection record without `connected_at` counts as a failed attempt. That's the basis for the connect success rate.
- Machine utilization is session hours divided by the hours in the selected period.
- "Removed" machines had sessions but are no longer enrolled.
- The bill uses the hourly rate and monthly cap per user from the assumptions panel (default $0.20 an hour, capped at $20 a month). Hours from users already at the cap cost nothing extra, which is why trimming long sessions saves less than hours × rate. Only complete calendar months (UTC) count towards the yearly figures.

## Project layout

```
fetch.py           Pulls the snapshot from the API, writes raw.json and pseudonymized data.json
build.py           Embeds fonts and data into template.html -> Phaze Usage Dashboard.html
make_sample.py     Generates the synthetic sample_data.json
sample_data.json   Synthetic studio for trying the dashboard without a key
template.html      The dashboard (HTML, CSS and vanilla JS, no dependencies)
fonts.css          Phaze brand fonts as embedded web fonts
```

`.env`, `raw.json`, `data.json` and the built HTML are gitignored.
