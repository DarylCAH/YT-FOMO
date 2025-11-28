# YT-FOMO: Never Miss a Live Stream Again

Have you ever gone back to watch a live broadcast only to find it’s gone private? That “uh oh” feeling has a name:
YT FOMO - the fear of missing out on a live stream.

YT‑FOMO solves it. The moment a channel goes live, YT‑FOMO records the broadcast for you and saves it to your own storage. No more “video unavailable” surprises after the stream ends.

Dark‑mode web UI (only, not an option) · Multi‑channel ready · Per‑channel folders · Real‑time progress · One‑click downloads · Lightweight API · Runs great in Docker

---

## Why you’ll love it

- **Catch every live, automatically** — YT‑FOMO polls each channel’s “live” endpoint and only records when a broadcast is actually live. No wasted disk on replays.
- **Your archive, your rules** — Recordings are written straight to your disk as `.mkv` files under `./downloads/<channel_name>/…`, so you can watch on your terms.
- **Stay in the loop** — Optional Gotify notifications when a stream starts and when it ends (with duration and size). No more babysitting tabs.
- **See progress at a glance** — Clear “Live” / “Not recording” badges, percent complete, ETA, and current filename in a clean, dark UI.
- **Handles hiccups** — If a stream drops and restarts, YT‑FOMO quickly re‑checks and starts a new recording so you don’t miss the rest.
- **Self‑updating recorder** — The capture backend is updated after every successful recording and once per day to keep up with platform changes.
- **Ops‑friendly** — Per‑channel logs, a simple `/api/status`, `/metrics` for Prometheus, and `/healthz` for uptime checks.

What it looks like:

![Screenshot](./screenshot/Screenshot.png)

---

## Quickstart (Docker Compose)

You can run this on your own machine and visit `http://localhost:8090`, or deploy it on a home server/VPS and access it via `http://<your-server-ip>:8090`. There’s no built‑in login; if you expose it to the internet, put it behind a reverse proxy with auth.

Prerequisites: `git` and `docker` (or Docker Desktop).

```bash
# 1) Clone the repo (or your fork)
git clone https://github.com/DarylCAH/YT-FOMO.git
cd YT-FOMO

# 2) Configure and create local folders
cp .env.example .env     # edit .env (HOST_PORT, GOTIFY_URL/GOTIFY_TOKEN, retention, etc.)
mkdir -p downloads data  # local storage mounts for recordings and app state

# 3) Build & run
docker compose up -d --build

# 4) Open the UI
# On this machine:   http://localhost:8090
# On your LAN/Server: http://<your-server-ip>:8090
```

Add a channel URL (or its `/live` link), click **Resolve** to confirm the channel and avatar, then **Add**. When the channel goes live, recording starts automatically. Finished files appear under `./downloads/<channel_name>/…`. Use **Download** / **Delete** from the UI.

---

## Configuration (via `.env`)

These map directly to the `environment:` section in `docker-compose.yml`:

- `HOST_PORT` (default `8090`) — host port for the web UI and API
- `INTERVAL_SECONDS` (default `60`) — how often to probe each channel when idle
- `GOTIFY_URL`, `GOTIFY_TOKEN` — optional push notifications on start/end
- `TZ` — container timezone (affects timestamps)
- Retention (optional):
  - `RETAIN_MAX_DAYS` (default `0`) — delete recordings older than N days
  - `RETAIN_MAX_SIZE_GB` (default `0`) — per‑channel size cap in GB; prunes oldest files when exceeded
  - `CLEAN_PART_AGE_HOURS` (default `0`) — remove stale partial segments older than N hours

### Volumes

- `./downloads:/downloads` — where recordings are stored
- `./data:/data` — channel list and app state

---

## Endpoints (for power users)

- `GET /` — Web UI  
- `GET /downloads/...` — Serve recorded files  
- `GET /api/resolve?url=...` — Resolve a channel/live URL to name/id/avatar  
- `GET /api/channels` — List channels  
- `POST /api/channels` — Add a channel (`{ url, title?, channel_id?, thumbnail_url? }`)  
- `DELETE /api/channels/{id}` — Remove a channel (stops watcher)  
- `GET /api/status` — Current per‑channel status (live/recording/ETA/filename)  
- `GET /api/recordings?channel_id=...` — List recent recordings (`?all=true` includes older files)  
- `DELETE /api/recordings?path=...` — Delete a recording by relative path  
- `GET /api/logs?channel_id=...` — Recent per‑channel log lines  
- `GET /api/metrics` — Lightweight status metrics  
- `GET /healthz` — Health check for load balancers and uptime monitors

---

## Notes

- Only “live now” broadcasts are recorded.
- After a successful recording ends, YT‑FOMO briefly re‑checks to catch immediate restarts.
- Audio and video are merged on completion into a single `.mkv`.
- The recording backend auto‑updates after each success and once per day to stay compatible.
- There is no built‑in authentication; use a reverse proxy if you expose this publicly.

---

## License

MIT — contributions welcome.


