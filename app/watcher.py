import json
import os
import re
import shlex
import threading
import time
from subprocess import Popen, PIPE, STDOUT
from typing import Dict, Optional, List
from urllib import request, parse
from collections import deque

from .models import Channel, ChannelStatus, Progress


def ensure_channel_output_dir(base_output_dir: str, channel: Channel) -> str:
	# Create a subfolder per channel using its title or id
	folder_name = channel.title.strip() or channel.channel_id or channel.id
	# Sanitize file system unfriendly chars
	folder_name = re.sub(r"[^a-zA-Z0-9._-]+", "_", folder_name)
	path = os.path.join(base_output_dir, folder_name)
	os.makedirs(path, exist_ok=True)
	return path


def _normalize_live_url(url: str) -> str:
	"""
	For YT channels, force the '/live' variant to avoid grabbing non-live content.
	"""
	u = url.strip().rstrip("/")
	if "youtube.com" in u:
		if "/watch" in u:
			# direct video links are left as-is (could be scheduled live)
			return u
		if not u.endswith("/live"):
			# Handle channel vanity and id urls
			if re.search(r"/@(?!.*/)", u) or re.search(r"/channel/[^/]+$", u) or re.search(r"/c/[^/]+$", u):
				return u + "/live"
	return u


class ChannelWatcher(threading.Thread):
	def __init__(self, channel: Channel, output_dir: str, interval_seconds: int, log_sink: Optional[callable] = None, update_lock: Optional[threading.Lock] = None):
		super().__init__(daemon=True, name=f"watcher-{channel.id}")
		self.channel = channel
		self.interval_seconds = max(10, int(interval_seconds))
		self.output_dir = ensure_channel_output_dir(output_dir, channel)
		self._stop_event = threading.Event()
		self.status = ChannelStatus(channel=channel)
		self._proc: Optional[Popen] = None
		# Optional notifications and auto-update
		self.gotify_url = os.environ.get("GOTIFY_URL", "").strip().rstrip("/")
		self.gotify_token = os.environ.get("GOTIFY_TOKEN", "").strip()
		# Always keep yt-dlp up to date after each completed recording
		self.autoupdate_ytdlp = True
		# Reliability helpers
		self._consecutive_failures = 0
		self._fast_retry_until: float = 0.0
		self._log_sink = log_sink
		self._update_lock = update_lock or threading.Lock()

	def _log(self, msg: str) -> None:
		print(msg, flush=True)
		try:
			if self._log_sink:
				self._log_sink(self.channel.id, msg)
		except Exception:
			pass

	def stop(self) -> None:
		self._stop_event.set()
		# Try to gently terminate yt-dlp if running
		if self._proc and self._proc.poll() is None:
			try:
				self._proc.terminate()
			except Exception:
				pass

	def is_stopped(self) -> bool:
		return self._stop_event.is_set()

	def run(self) -> None:
		while not self.is_stopped() and self.channel.active:
			self.status.last_check_at = time.time()
			try:
				self._log(f"[watcher] Checking for live: {self.channel.title} ({self.channel.url}) at {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self.status.last_check_at))}")
				self._record_once()
				self._consecutive_failures = 0
			except Exception as e:
				self._consecutive_failures += 1
				self._log(f"[watcher] Error in watcher for {self.channel.title}: {e}")
			# If not recording (no live), sleep; if finished recording, loop and check again
			if not self.status.progress.is_recording and not self.is_stopped():
				now = time.time()
				if now < self._fast_retry_until:
					sleep_for = 10
					self._log(f"[watcher] Fast-retry window active for {self.channel.title}. Sleeping {sleep_for}s")
				else:
					backoff = min(300, self.interval_seconds * (2 ** max(0, self._consecutive_failures - 1)))
					sleep_for = backoff if self._consecutive_failures > 0 else self.interval_seconds
					self._log(f"[watcher] Not live: {self.channel.title}. Sleeping {sleep_for}s")
				time.sleep(sleep_for)

	def _record_once(self) -> None:
		if self.is_stopped():
			return

		# Decide effective URL
		effective_url = _normalize_live_url(self.channel.url)

		# Quick probe to see if live before spawning recorder
		probe = self._probe(effective_url)
		is_live_now = probe.get("live_status") == "is_live"
		self.status.is_live = bool(is_live_now)
		self.status.live_status = probe.get("live_status")
		self.status.stream_title = probe.get("title")
		self.status.stream_thumbnail = probe.get("thumbnail")
		self.status.progress.is_recording = False
		self.status.progress.updated_at = time.time()
		if not is_live_now:
			# Not live; nothing to do this cycle
			return

		print(f"[watcher] Live detected: {self.channel.title}. Starting recording…", flush=True)
		self._notify("Stream started", f"Channel: {self.channel.title}\nLink: {effective_url}", priority=3)

		# Build output template
		output_template = os.path.join(
			self.output_dir, "%(upload_date)s_%(title)s_%(id)s.%(ext)s"
		)
		cmd = [
			"yt-dlp",
			"--newline",
			"--print-json",
			"--live-from-start",
			"--merge-output-format",
			"mkv",
			"-o",
			output_template,
			effective_url,
		]

		self.status.progress.is_recording = True
		self.status.progress.updated_at = time.time()

		start_time = time.time()
		self._proc = Popen(cmd, stdout=PIPE, stderr=STDOUT, text=True, bufsize=1)
		assert self._proc.stdout is not None
		try:
			for line in self._proc.stdout:
				if self.is_stopped():
					break
				line = line.rstrip("\n")
				self._handle_output_line(line)
		finally:
			rc = self._proc.poll()
			self._proc = None
			self.status.progress.is_recording = False
			self.status.progress.updated_at = time.time()
			# Non-zero return is typically "not live"
			if rc and rc != 0:
				self.status.is_live = False
			self._log(f"[watcher] Recording finished for {self.channel.title} (rc={rc})")
			# If completed successfully, send end notification, include duration and filesize
			if rc == 0:
				end_time = time.time()
				runtime = int(end_time - start_time)
				h = runtime // 3600
				m = (runtime % 3600) // 60
				s = runtime % 60
				filename = self.status.progress.filename or ""
				try:
					filesize = os.path.getsize(filename) if filename and os.path.isfile(filename) else 0
				except OSError:
					filesize = 0
				filesize_mb = filesize // (1024 * 1024)
				msg = f"Recorded duration: {h:02d}:{m:02d}:{s:02d}\nFile: {os.path.basename(filename) if filename else 'unknown'}\nSize: {filesize_mb} MB"
				self._notify("Stream ended", msg, priority=5)
				# Mandatory yt-dlp update after each completed recording
				self._log("[watcher] Updating yt-dlp...")
				try:
					with self._update_lock:
						up = Popen(["pip", "install", "--no-cache-dir", "-U", "yt-dlp"], stdout=PIPE, stderr=STDOUT, text=True)
						_ = up.communicate(timeout=120)
					self._log("[watcher] yt-dlp updated.")
				except Exception as e:
					self._log(f"[watcher] yt-dlp update failed: {e}")
				# Enable fast-retry window for quick restarts
				self._fast_retry_until = time.time() + 180

	def _probe(self, url: str) -> Dict[str, Optional[str]]:
		"""
		Run a quick, low-cost probe using yt-dlp to determine live state and details.
		Returns dict: {live_status, title, thumbnail}
		"""
		try:
			proc = Popen(
				[
					"yt-dlp",
					"--dump-single-json",
					"--flat-playlist",
					"--playlist-end",
					"1",
					url,
				],
				stdout=PIPE,
				stderr=STDOUT,
				text=True,
			)
			assert proc.stdout is not None
			out, _ = proc.communicate(timeout=20)
			obj = json.loads(out)
			def extract(entry: Dict[str, any]) -> Dict[str, Optional[str]]:
				status = "is_live" if entry.get("is_live") else entry.get("live_status") or "not_live"
				title = entry.get("title")
				thumb = None
				thumbs = entry.get("thumbnails") or entry.get("thumbnail")
				if isinstance(thumbs, list) and thumbs:
					try:
						thumb = sorted(thumbs, key=lambda t: (t.get("width", 0) or 0, t.get("height", 0) or 0))[-1].get("url")
					except Exception:
						thumb = thumbs[-1].get("url") if isinstance(thumbs[-1], dict) else None
				elif isinstance(thumbs, str):
					thumb = thumbs
				return {"live_status": status, "title": title, "thumbnail": thumb}
			if isinstance(obj, dict):
				info = extract(obj)
				if info.get("title") or info.get("live_status"):
					return info
				entries = obj.get("entries") or []
				if entries and isinstance(entries[0], dict):
					return extract(entries[0])
			return {"live_status": "not_live", "title": None, "thumbnail": None}
		except Exception:
			return {"live_status": "error", "title": None, "thumbnail": None}

	def _notify(self, title: str, message: str, priority: int = 5) -> None:
		"""
		Send a Gotify notification if configured.
		"""
		if not self.gotify_url or not self.gotify_token:
			return
		try:
			url = f"{self.gotify_url}/message"
			data = parse.urlencode({"title": title, "message": message, "priority": str(priority)}).encode("utf-8")
			req = request.Request(url, data=data, method="POST")
			req.add_header("X-Gotify-Key", self.gotify_token)
			req.add_header("Content-Type", "application/x-www-form-urlencoded")
			with request.urlopen(req, timeout=10) as resp:
				_ = resp.read()
		except Exception as e:
			print(f"[watcher] Gotify notify failed: {e}", flush=True)

	def _handle_output_line(self, line: str) -> None:
		# Try JSON first
		try:
			obj = json.loads(line)
		except Exception:
			obj = None

		if isinstance(obj, dict):
			# Look for filename assignment and other metadata
			filename = obj.get("filename")
			if filename:
				self.status.progress.filename = filename
				self.status.progress.updated_at = time.time()
			# Some yt-dlp JSON messages may include progress-like info; keep the last printable line
			self.status.progress.last_line = obj.get("status", "info")
			self.status.progress.updated_at = time.time()
			return

		# Fallback: parse textual progress line
		self.status.progress.last_line = line
		self.status.progress.updated_at = time.time()
		# Example: "[download]  45.0% of ~2.17GiB at  3.10MiB/s ETA 10:15"
		m = re.search(r"(\d{1,3}(?:\.\d+)?)%", line)
		if m:
			try:
				self.status.progress.percent = float(m.group(1))
			except ValueError:
				self.status.progress.percent = None
		speed_m = re.search(r"at\s+([0-9.]+[KMG]iB/s)", line)
		if speed_m:
			self.status.progress.speed_text = speed_m.group(1)
		eta_m = re.search(r"ETA\s+(\d+):(\d+)", line)
		if eta_m:
			try:
				mins = int(eta_m.group(1))
				secs = int(eta_m.group(2))
				self.status.progress.eta_seconds = mins * 60 + secs
			except ValueError:
				self.status.progress.eta_seconds = None


class WatchManager:
	"""
	Manages multiple channel watchers.
	"""

	def __init__(self, output_dir: str, interval_seconds: int):
		self.output_dir = output_dir
		self.interval_seconds = interval_seconds
		self._lock = threading.RLock()
		self._watchers: Dict[str, ChannelWatcher] = {}
		self._logs: Dict[str, deque] = {}
		self._update_lock = threading.Lock()

	def start_for_channel(self, channel: Channel) -> None:
		with self._lock:
			existing = self._watchers.get(channel.id)
			if existing and existing.is_alive():
				return
			if channel.id not in self._logs:
				self._logs[channel.id] = deque(maxlen=200)
			def sink(cid: str, line: str) -> None:
				buf = self._logs.get(cid)
				if buf is not None:
					buf.append(f"{time.strftime('%H:%M:%S')} {line}")
			w = ChannelWatcher(channel, self.output_dir, self.interval_seconds, log_sink=sink, update_lock=self._update_lock)
			self._watchers[channel.id] = w
			w.start()

	def stop_for_channel(self, channel_id: str) -> None:
		with self._lock:
			w = self._watchers.get(channel_id)
			if not w:
				return
			w.stop()
			self._watchers.pop(channel_id, None)

	def get_status(self, channel_id: str) -> Optional[ChannelStatus]:
		with self._lock:
			w = self._watchers.get(channel_id)
			if w:
				return w.status
		return None

	def list_statuses(self) -> List[ChannelStatus]:
		with self._lock:
			return [w.status for w in self._watchers.values()]

	def get_logs(self, channel_id: str, limit: int = 200) -> List[str]:
		with self._lock:
			buf = self._logs.get(channel_id)
			if not buf:
				return []
			if limit <= 0:
				return list(buf)
			return list(buf)[-limit:]


