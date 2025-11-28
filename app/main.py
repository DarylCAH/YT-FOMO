import os
import subprocess
import json
from typing import List, Optional, Dict, Any
import time
import threading

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, AnyHttpUrl

from .models import Channel, generate_id
from .storage import ChannelStore
from .watcher import WatchManager
import re


APP_TITLE = "YT-FOMO"

OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "/downloads")
DATA_DIR = os.environ.get("DATA_DIR", "/data")
INTERVAL_SECONDS = int(os.environ.get("INTERVAL_SECONDS", "60"))
STARTED_AT = int(time.time())

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

store = ChannelStore(DATA_DIR)
watch = WatchManager(OUTPUT_DIR, INTERVAL_SECONDS)

app = FastAPI(title=APP_TITLE)

# Serve downloads and static assets
app.mount("/downloads", StaticFiles(directory=OUTPUT_DIR), name="downloads")
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")


def _channel_folder_name(title: str, channel_id: str, fallback_id: str) -> str:
	"""
	Generate the same folder name as the watcher uses for a channel.
	"""
	base = (title or channel_id or fallback_id).strip()
	if not base:
		base = fallback_id
	# Mirror watcher.ensure_channel_output_dir
	return re.sub(r"[^a-zA-Z0-9._-]+", "_", base)


class ResolveResponse(BaseModel):
	title: str
	channel_id: str
	url: AnyHttpUrl
	thumbnail_url: Optional[str] = None


class AddChannelRequest(BaseModel):
	url: AnyHttpUrl
	title: Optional[str] = None
	channel_id: Optional[str] = None
	thumbnail_url: Optional[str] = None


class ChannelResponse(BaseModel):
	id: str
	url: AnyHttpUrl
	title: str
	channel_id: str
	active: bool
	thumbnail_url: Optional[str] = None

	@staticmethod
	def from_channel(c: Channel) -> "ChannelResponse":
		return ChannelResponse(
			id=c.id, url=c.url, title=c.title, channel_id=c.channel_id, active=c.active, thumbnail_url=c.thumbnail_url
		)


def _resolve_channel_info(url: str) -> Dict[str, Any]:
	"""
	Resolve channel metadata with resilient strategy:
	1) Try fast single-json, flat playlist with short timeout
	2) Fallback to full print-json with longer timeout
	3) Retry variants of the URL (append /live, /videos) if needed
	"""
	def parse_info_from_obj(obj: Dict[str, Any]) -> Optional[Dict[str, str]]:
		title = obj.get("channel") or obj.get("uploader") or obj.get("title") or ""
		channel_id = obj.get("channel_id") or obj.get("uploader_id") or ""
		# On channel playlists, sometimes 'id' is UC... and title has channel name
		if (not channel_id) and isinstance(obj.get("id"), str) and obj.get("id", "").startswith("UC"):
			channel_id = obj["id"]
		# Try thumbnails in multiple shapes
		thumb = None
		if isinstance(obj.get("channel_thumbnails"), list) and obj["channel_thumbnails"]:
			thumbs = obj["channel_thumbnails"]
			try:
				thumb = sorted(thumbs, key=lambda t: (t.get("width", 0) or 0, t.get("height", 0) or 0))[-1].get("url")
			except Exception:
				thumb = thumbs[-1].get("url") if isinstance(thumbs[-1], dict) else None
		if not thumb and isinstance(obj.get("thumbnails"), list) and obj["thumbnails"]:
			try:
				thumb = sorted(obj["thumbnails"], key=lambda t: (t.get("width", 0) or 0, t.get("height", 0) or 0))[-1].get("url")
			except Exception:
				thumb = obj["thumbnails"][-1].get("url") if isinstance(obj["thumbnails"][-1], dict) else None
		if not thumb:
			thumb = obj.get("thumbnail")
		if title and channel_id:
			return {"title": title, "channel_id": channel_id, "thumbnail_url": thumb}
		return None

	def try_fast(u: str) -> Optional[Dict[str, str]]:
		# Fast attempt: dump single JSON of playlist/channel without fetching entries
		try:
			res = subprocess.run(
				["yt-dlp", "--dump-single-json", "--flat-playlist", "--playlist-end", "1", u],
				stdout=subprocess.PIPE,
				stderr=subprocess.DEVNULL,
				text=True,
				timeout=20,
				check=False,
			)
		except subprocess.TimeoutExpired:
			return None
		if not res.stdout.strip():
			return None
		try:
			obj = json.loads(res.stdout)
		except Exception:
			return None
		# Try top-level first
		info = parse_info_from_obj(obj)
		if info:
			return info
		# Try first entry if present
		entries = obj.get("entries") or []
		if entries:
			info = parse_info_from_obj(entries[0] or {})
			if info:
				return info
		return None

	def try_full(u: str) -> Optional[Dict[str, str]]:
		try:
			res = subprocess.run(
				["yt-dlp", "--skip-download", "--print-json", u],
				stdout=subprocess.PIPE,
				stderr=subprocess.DEVNULL,
				text=True,
				timeout=90,
				check=False,
			)
		except subprocess.TimeoutExpired:
			return None
		title = ""
		channel_id = ""
		for line in res.stdout.splitlines():
			try:
				obj = json.loads(line)
			except Exception:
				continue
			info = parse_info_from_obj(obj)
			if info:
				return info
		return None

	candidates = [url]
	if not url.rstrip("/").endswith("/live"):
		candidates.append(url.rstrip("/") + "/live")
	if not url.rstrip("/").endswith("/videos"):
		candidates.append(url.rstrip("/") + "/videos")

	for u in candidates:
		info = try_fast(u)
		if info:
			return info
	for u in candidates:
		info = try_full(u)
		if info:
			return info
	raise HTTPException(status_code=400, detail="Failed to resolve URL: unable to extract channel info")


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
	# Serve the SPA
	static_dir = os.path.join(os.path.dirname(__file__), "static")
	index_path = os.path.join(static_dir, "index.html")
	if not os.path.exists(index_path):
		return HTMLResponse("<h1>UI not found</h1>", status_code=500)
	return HTMLResponse(open(index_path, "r", encoding="utf-8").read())


@app.get("/api/resolve", response_model=ResolveResponse)
def resolve(url: AnyHttpUrl) -> ResolveResponse:
	info = _resolve_channel_info(str(url))
	return ResolveResponse(title=info["title"], channel_id=info["channel_id"], url=url, thumbnail_url=info.get("thumbnail_url"))


@app.get("/api/channels", response_model=List[ChannelResponse])
def list_channels() -> List[ChannelResponse]:
	return [ChannelResponse.from_channel(c) for c in store.list_channels()]


@app.post("/api/channels", response_model=ChannelResponse)
def add_channel(body: AddChannelRequest) -> ChannelResponse:
	title = body.title
	channel_id = body.channel_id
	thumbnail_url = body.thumbnail_url
	if not title or not channel_id:
		info = _resolve_channel_info(str(body.url))
		title = title or info["title"]
		channel_id = channel_id or info["channel_id"]
		if not thumbnail_url:
			thumbnail_url = info.get("thumbnail_url")
	channel = Channel(
		id=generate_id(),
		url=str(body.url),
		title=title,
		channel_id=channel_id,
		thumbnail_url=thumbnail_url,
		active=True,
	)
	store.upsert(channel)
	# start watcher
	watch.start_for_channel(channel)
	return ChannelResponse.from_channel(channel)


@app.delete("/api/channels/{channel_id}")
def delete_channel(channel_id: str) -> Dict[str, str]:
	if not store.get(channel_id):
		raise HTTPException(status_code=404, detail="Channel not found")
	watch.stop_for_channel(channel_id)
	store.delete(channel_id)
	return {"status": "ok"}


@app.get("/api/status")
def status() -> Dict[str, Any]:
	statuses = watch.list_statuses()
	return {
		"channels": [s.to_dict() for s in statuses],
	}


@app.get("/api/logs")
def get_logs(channel_id: str, limit: int = 200) -> Dict[str, Any]:
	lines = watch.get_logs(channel_id, limit)
	return {"channel_id": channel_id, "lines": lines}


@app.get("/api/metrics")
def metrics() -> Dict[str, Any]:
	stats = []
	for s in watch.list_statuses():
		stats.append({
			"channel_id": s.channel.id,
			"title": s.channel.title,
			"is_live": s.is_live,
			"live_status": s.live_status,
			"last_check_at": s.last_check_at,
			"is_recording": s.progress.is_recording,
		})
	return {"channels": stats}


@app.get("/healthz")
def healthz() -> Dict[str, str]:
	return {"status": "ok"}


@app.get("/api/recordings")
def recordings(
	channel_id: Optional[str] = Query(default=None),
	all: bool = Query(default=False, description="Include files from before the service start"),
) -> List[Dict[str, Any]]:
	"""
	List recorded files. If channel_id provided, scope to that channel's subfolder.
	"""
	base = OUTPUT_DIR
	result: List[Dict[str, Any]] = []

	def add_record(path: str) -> None:
		# Only include real, readable, non-empty files
		if not os.path.isfile(path):
			return
		if not os.access(path, os.R_OK):
			return
		try:
			size = os.path.getsize(path)
			mtime = int(os.path.getmtime(path))
		except OSError:
			return
		if size <= 0:
			return
		if not all and mtime < STARTED_AT:
			return
		result.append(
			{
				"path": os.path.relpath(path, base),
				"name": os.path.basename(path),
				"size": size,
				"mtime": mtime,
			}
		)

	if channel_id:
		ch = store.get(channel_id)
		if not ch:
			raise HTTPException(status_code=404, detail="Channel not found")
		# Look under this channel folder
		folder = os.path.join(base, _channel_folder_name(ch.title, ch.channel_id, ch.id))
		if os.path.isdir(folder):
			for root, _, files in os.walk(folder):
				for f in files:
					if f.lower().endswith((".mkv", ".mp4", ".webm")):
						add_record(os.path.join(root, f))
	else:
		for root, _, files in os.walk(base):
			for f in files:
				if f.lower().endswith((".mkv", ".mp4", ".webm")):
					add_record(os.path.join(root, f))

	# Newest first
	result.sort(key=lambda x: x["mtime"], reverse=True)
	return result


@app.delete("/api/recordings")
def delete_recording(path: str) -> Dict[str, str]:
	"""
	Delete a recording by its relative path under OUTPUT_DIR.
	"""
	# Normalize and validate path is within OUTPUT_DIR
	target = os.path.normpath(os.path.join(OUTPUT_DIR, path))
	if not target.startswith(os.path.abspath(OUTPUT_DIR) + os.sep) and os.path.abspath(target) != os.path.abspath(OUTPUT_DIR):
		raise HTTPException(status_code=400, detail="Invalid path")
	if not os.path.isfile(target):
		raise HTTPException(status_code=404, detail="File not found")
	try:
		os.remove(target)
	except OSError as e:
		raise HTTPException(status_code=500, detail=f"Delete failed: {e}")
	return {"status": "ok"}


@app.on_event("startup")
def on_start() -> None:
	# Start watchers for all active channels
	for c in store.list_channels():
		if c.active:
			watch.start_for_channel(c)

	# Background retention and cleanup scheduler (optional via env)
	def retention_job() -> None:
		max_days = int(os.environ.get("RETAIN_MAX_DAYS", "0") or "0")
		max_size_gb = int(os.environ.get("RETAIN_MAX_SIZE_GB", "0") or "0")
		part_age_hours = int(os.environ.get("CLEAN_PART_AGE_HOURS", "0") or "0")
		while True:
			try:
				# Cleanup orphaned *.part files
				if part_age_hours > 0:
					cutoff = time.time() - part_age_hours * 3600
					for root, _, files in os.walk(OUTPUT_DIR):
						for f in files:
							if f.endswith(".part"):
								p = os.path.join(root, f)
								try:
									if os.path.getmtime(p) < cutoff:
										os.remove(p)
								except OSError:
									pass
				# Retention by days
				if max_days > 0:
					cutoff = time.time() - max_days * 86400
					for root, _, files in os.walk(OUTPUT_DIR):
						for f in files:
							if f.lower().endswith((".mkv", ".mp4", ".webm")):
								p = os.path.join(root, f)
								try:
									if os.path.getmtime(p) < cutoff:
										os.remove(p)
								except OSError:
									pass
				# Retention by size (approximate, per channel folder)
				if max_size_gb > 0:
					max_bytes = max_size_gb * 1024 * 1024 * 1024
					for root, dirs, _ in os.walk(OUTPUT_DIR):
						# Only operate on leaf channel folders
						for d in dirs:
							folder = os.path.join(root, d)
							files = []
							for r2, _, fs in os.walk(folder):
								for f in fs:
									if f.lower().endswith((".mkv", ".mp4", ".webm")):
										p = os.path.join(r2, f)
										try:
											files.append((p, os.path.getmtime(p), os.path.getsize(p)))
										except OSError:
											pass
							total = sum(sz for _, _, sz in files)
							if total > max_bytes:
								# Delete oldest first
								files.sort(key=lambda x: x[1])  # by mtime ascending
								while total > max_bytes and files:
                                    # pop oldest
									p, _, sz = files.pop(0)
									try:
										os.remove(p)
										total -= sz
									except OSError:
										pass
				# Sleep 30 minutes between passes
				time.sleep(1800)
			except Exception:
				time.sleep(1800)
	threading.Thread(target=retention_job, daemon=True).start()

	# Daily yt-dlp update when idle (no active recordings)
	def daily_update_job() -> None:
		while True:
			try:
				# Sleep until next day boundary roughly (24h)
				time.sleep(24 * 3600)
				# Skip if any recording is active
				any_recording = any(s.progress.is_recording for s in watch.list_statuses())
				if any_recording:
					continue
				# Perform update
				subprocess.run(["pip", "install", "--no-cache-dir", "-U", "yt-dlp"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
			except Exception:
				pass
	threading.Thread(target=daily_update_job, daemon=True).start()


