#!/bin/sh
set -u

CHANNEL_URL="${CHANNEL_URL:?CHANNEL_URL is required}"
INTERVAL="${INTERVAL_SECONDS:-60}"
OUT_DIR="${OUTPUT_DIR:-/downloads}"
GOTIFY_URL="${GOTIFY_URL:-}"
GOTIFY_TOKEN="${GOTIFY_TOKEN:-}"

notify() {
  if [ -n "$GOTIFY_URL" ] && [ -n "$GOTIFY_TOKEN" ]; then
    curl -s -X POST "$GOTIFY_URL/message" \
      -H "X-Gotify-Key: $GOTIFY_TOKEN" \
      -F "title=$1" \
      -F "message=$2" \
      -F "priority=${3:-5}" > /dev/null
  fi
}

mkdir -p "$OUT_DIR"

echo "[watcher] Starting live monitor for $CHANNEL_URL"
echo "[watcher] Output directory: $OUT_DIR"
echo "[watcher] Check interval: ${INTERVAL}s"

while true; do
  echo "[watcher] Checking for live stream at $(date)..."

  # Detect metadata for start notification
  meta=$(yt-dlp --skip-download --print-json "$CHANNEL_URL" 2>/dev/null || true)
  title=$(echo "$meta" | jq -r '.title // empty')
  url=$(echo "$meta" | jq -r '.original_url // empty')

  if [ -n "$title" ] && [ -n "$url" ]; then
    notify "Stream started" \
"Title: $title
Link: $url" \
    3
  fi

  start_time=$(date +%s)

  # Record live stream
  metadata=$(yt-dlp \
    --newline \
    --print-json \
    --live-from-start \
    --merge-output-format mkv \
    -o "$OUT_DIR/%(upload_date)s_%(title)s_%(id)s.%(ext)s" \
    "$CHANNEL_URL" 2>/dev/null)

  exit_code=$?

  if [ "$exit_code" -eq 0 ]; then
    end_time=$(date +%s)
    runtime=$((end_time - start_time))

    filename=$(echo "$metadata" | jq -r 'select(.filename)|.filename' | tail -1)
    duration=$(echo "$metadata" | jq -r 'select(.duration)|.duration|tostring' | tail -1)
    filesize=$(stat -c%s "$filename" 2>/dev/null || echo 0)

    runtime_h=$(printf "%02d:%02d:%02d" $((runtime/3600)) $(((runtime%3600)/60)) $((runtime%60)))
    filesize_mb=$((filesize / 1024 / 1024))

    notify "Stream ended" \
"Recorded duration: ${runtime_h}
File: $(basename "$filename")
Video duration: ${duration}s
Size: ${filesize_mb} MB" \
    5

    echo "[watcher] Stream ended, saved $filename"

    echo "[watcher] Updating yt-dlp..."
    pip install --no-cache-dir -U yt-dlp >/dev/null 2>&1
    echo "[watcher] yt-dlp updated."
  else
    echo "[watcher] Not live. Will retry after ${INTERVAL}s."
  fi

  sleep "$INTERVAL"
done
