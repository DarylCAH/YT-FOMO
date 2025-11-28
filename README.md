# YT‑FOMO — Never Miss a Live Stream Again

Have you ever gone back to watch a live broadcast only to find its gone private? That sinking feeling  thats YT FOMO: the fear of missing out on a live stream.

YT‑FOMO fixes that by automatically recording live broadcasts from your favourite channels the moment they go live, saving a copy to your own storage. No more video unavailable after the fact.

Dark‑mode web UI  Multi‑channel ready  Per‑channel folders  Real‑time progress  One‑click downloads  Lightweight API  Docker‑native

---

## Why youll love it

- **Catch every live, automatically**  Polls channel live endpoints and only records when a broadcast is truly live. No wasted disk on replays.
- **Your archive, your rules**  Saves directly to your disk as resilient `.mkv` files under `/downloads/<channel_name>/...` so you can watch, trim, or back up on your own terms.
- **Stay in the loop**  Optional Gotify pings when a stream starts and when it ends (with duration & size), so you dont have to babysit tabs.
- **See progress at a glance**  Clear Live/Not recording badges, % complete, ETA, and current filename.
- **Handles hiccups for you**  If a stream drops and restarts, YT‑FOMO re‑probes quickly and begins a new recording, so you dont miss what comes next.
- **Self‑updating recorder**  The capture backend auto‑updates after each successful recording and once per day to stay compatible with platform changes.
- **Ops‑friendly**  Per‑channel logs, a `/api/status` feed, `/metrics` for Prometheus, and a `/healthz` endpoint for load balancers.

**What it looks like:**

![Screenshot](./screenshot/Screenshot.png)

---

## Quickstart (Docker Compose)

> You can run this on your device and visit `http://localhost:8090`, or deploy it on a home server/VPS and browse via `http://<your-server-ip>:8090` behind a reverse proxy. No built‑in auth is provided; secure public deployments accordingly.

**Prerequisites:** `git` and `docker` (or Docker Desktop).

```bash
# 1) Clone your (fork of the) repo
git clone https://github.com/DarylCAH/YT-FOMO.git
cd YT-FOMO

# 2) Prepare config and storage
cp .\u007Benvironment,env\u007D  # or: cp .env.example .env
# Edit .env to set HOST_PORT (default 8090), GOTIFY_URL/GOTIFY_TOKEN, retention, etc.
mkdir -p downloads data

# 3) Build & run
docker compose up -d --build

# 4) Open the UI
# On the same machine:
#   http://localhost:8080  (or the port you configured)
# From another device on your LAN:
#   http://<server-ip>:8080
```

Paste a channel (or a `/live` link), click **Resolve** to confirm the channel and avatar, then **Add**. When the channel goes live, recording starts automatically. Finished files appear under `./downloads/<channel_name>/...`. Use the **Download**/**Delete** buttons in the UI.

---

## Configuration (`.env`)

These map directly to the `environment:` entries in `docker-compose.yml`:

- **`HOST_PORT`** (default `8090`)  Port to expose the web UI & API on your host.
- **`INTERVAL_SECONDS`** (default `60`)  How often to probe each channel when idle.
- **`GOTIFY_URL` / `GOTIFY_TOKEN`**  Optional push notifications on start/end.
- **`TZ`**  Container timezone; affects timestamps.
- **Retention (optional)**
  - `RETAIN_{MAX\_}DAYS` (default `0`)  delete recordings older than N days.
  - `RETAIN_MAX_\u200bSIZE_\u200bGB` (default `0`)  per‑channel cap in GB; oldest files pruned when exceeded.
  - `CLEAN_\u200bPART_\u200bAGE_\u200bHOURS` (default `0`)  remove stale partial `.part` segments older than N hours.

**Volumes**

- `./downloads:/downloads`  where recordings are stored
- `./data:/data`  channel list and internal state

---

## Power‑user endpoints

- `GET /`  Web UI
- `GET /downloads/...`  Serve recorded files
- `GET /api/resolve?url=...`  Resolve a channel/live URL to name/id/avatar
- `GET /api/channels`  List channels
- `POST /api/channels`  Add a channel (`{ url, title?, channel_id?, thumbnail_url? }`)
- `DELETE /api/channels/{id}`  Remove a channel (stops watcher)
- `GET /api/status`  Current per‑channel status (live/recording/ETA/filename)
- `GET /api/recordings?channel_id=...`  List recordings (`?all=true` to include older files)
- `DELETE /api/recordings?path=...`  Delete a recording by relative path
- `GET /api/logs?channel_id=...`  Recent per‑channel log lines
- `GET /api/metrics`  Lightweight status metrics (Prometheus‑friendly)
- `GET /healthz`  Health check for load balancers/probes

---

## Notes & behaviour

- Only truly live now broadcasts are recorded.
- After a successful recording ends, YT‑FOMO briefly fast‑retries to catch immediate restarts.
- Audio & video are merged on completion into a single `.mkv`.
- The recording backend auto‑updates after each success and once per day to stay compatible.
- Theres no built‑in authentication; use a reverse proxy if you expose it beyond your LAN.

---

## License

MIT  contributions welcome!
