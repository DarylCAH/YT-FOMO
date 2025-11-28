from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Dict, Optional, List, Any


def generate_id() -> str:
	"""
	Generate a stable unique id for channels.
	"""
	return uuid.uuid4().hex


@dataclass
class Channel:
	id: str
	url: str
	title: str
	channel_id: str
	thumbnail_url: Optional[str] = None
	created_at: float = field(default_factory=lambda: time.time())
	active: bool = True

	@staticmethod
	def from_dict(data: Dict[str, Any]) -> "Channel":
		return Channel(
			id=data["id"],
			url=data["url"],
			title=data.get("title", ""),
			channel_id=data.get("channel_id", ""),
			thumbnail_url=data.get("thumbnail_url"),
			created_at=data.get("created_at", time.time()),
			active=bool(data.get("active", True)),
		)

	def to_dict(self) -> Dict[str, Any]:
		return asdict(self)


@dataclass
class Progress:
	# Raw last line of progress from yt-dlp (human readable)
	last_line: str = ""
	# Percentage 0-100 if parsed, else None
	percent: Optional[float] = None
	# Bytes downloaded if parsed
	downloaded_bytes: Optional[int] = None
	# Approx total size in bytes if parsed
	total_bytes: Optional[int] = None
	# Estimated time remaining in seconds if parsed
	eta_seconds: Optional[int] = None
	# Download speed textual representation if parsed (e.g., "3.1MiB/s")
	speed_text: Optional[str] = None
	# Current output filename if known
	filename: Optional[str] = None
	# Whether a recording process is active
	is_recording: bool = False
	# Last state update time
	updated_at: float = field(default_factory=lambda: time.time())

	def to_dict(self) -> Dict[str, Any]:
		return {
			"last_line": self.last_line,
			"percent": self.percent,
			"downloaded_bytes": self.downloaded_bytes,
			"total_bytes": self.total_bytes,
			"eta_seconds": self.eta_seconds,
			"speed_text": self.speed_text,
			"filename": self.filename,
			"is_recording": self.is_recording,
			"updated_at": self.updated_at,
		}


@dataclass
class ChannelStatus:
	channel: Channel
	is_live: bool = False
	progress: Progress = field(default_factory=Progress)
	last_check_at: float = field(default_factory=lambda: time.time())
	# Additional live details
	live_status: Optional[str] = None  # "is_live", "is_upcoming", "not_live"
	stream_title: Optional[str] = None
	stream_thumbnail: Optional[str] = None

	def to_dict(self) -> Dict[str, Any]:
		return {
			"channel": self.channel.to_dict(),
			"is_live": self.is_live,
			"live_status": self.live_status,
			"stream_title": self.stream_title,
			"stream_thumbnail": self.stream_thumbnail,
			"progress": self.progress.to_dict(),
			"last_check_at": self.last_check_at,
		}


