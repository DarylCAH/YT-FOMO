import json
import os
import threading
from typing import Dict, List, Optional

from .models import Channel


class ChannelStore:
	"""
	Thread-safe persistence for channels in a single JSON file.
	"""

	def __init__(self, data_dir: str):
		self._data_dir = data_dir
		self._path = os.path.join(self._data_dir, "channels.json")
		self._lock = threading.RLock()
		os.makedirs(self._data_dir, exist_ok=True)
		if not os.path.exists(self._path):
			with open(self._path, "w", encoding="utf-8") as f:
				json.dump({"channels": []}, f)

	def list_channels(self) -> List[Channel]:
		with self._lock:
			try:
				with open(self._path, "r", encoding="utf-8") as f:
					raw = json.load(f)
			except (IOError, json.JSONDecodeError):
				raw = {"channels": []}
			return [Channel.from_dict(c) for c in raw.get("channels", [])]

	def save_channels(self, channels: List[Channel]) -> None:
		with self._lock:
			tmp_path = f"{self._path}.tmp"
			data = {"channels": [c.to_dict() for c in channels]}
			with open(tmp_path, "w", encoding="utf-8") as f:
				json.dump(data, f, indent=2)
			os.replace(tmp_path, self._path)

	def get(self, channel_id: str) -> Optional[Channel]:
		for c in self.list_channels():
			if c.id == channel_id:
				return c
		return None

	def upsert(self, channel: Channel) -> None:
		with self._lock:
			channels = self.list_channels()
			found = False
			for i, c in enumerate(channels):
				if c.id == channel.id:
					channels[i] = channel
					found = True
					break
			if not found:
				channels.append(channel)
			self.save_channels(channels)

	def delete(self, channel_id: str) -> None:
		with self._lock:
			channels = [c for c in self.list_channels() if c.id != channel_id]
			self.save_channels(channels)


