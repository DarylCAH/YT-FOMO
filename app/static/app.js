window.App = (function () {
	const $ = (sel) => document.querySelector(sel);
	const $$ = (sel) => Array.from(document.querySelectorAll(sel));

	async function api(path, opts = {}) {
		const res = await fetch(path, opts);
		if (!res.ok) {
			const txt = await res.text();
			throw new Error(txt || res.statusText);
		}
		const ct = res.headers.get("content-type") || "";
		if (ct.includes("application/json")) return res.json();
		return res.text();
	}

	function formatBytes(bytes) {
		if (!bytes && bytes !== 0) return "";
		const units = ["B", "KB", "MB", "GB", "TB"];
		let i = 0;
		let n = bytes;
		while (n >= 1024 && i < units.length - 1) {
			n /= 1024;
			i++;
		}
		return `${n.toFixed(1)} ${units[i]}`;
	}

	let resolveData = null;

	async function handleResolve() {
		const url = $("#urlInput").value.trim();
		const infoBox = $("#resolveInfo");
		infoBox.textContent = "Resolving...";
		infoBox.classList.remove("error");
		try {
			const info = await api(`/api/resolve?url=${encodeURIComponent(url)}`);
			resolveData = info;
			const thumb = info.thumbnail_url ? `<img class="avatar" src="${escapeAttr(info.thumbnail_url)}" alt="">` : `<div class="avatar placeholder"></div>`;
			infoBox.innerHTML = `
				<div class="row" style="align-items:center; gap:12px;">
					${thumb}
					<div style="flex:1;">
						<div class="title">${escapeHtml(info.title)}</div>
						<div class="muted small">Channel ID: ${escapeHtml(info.channel_id)}</div>
					</div>
					<button id="addBtn">Add</button>
				</div>
			`;
			$("#addBtn").addEventListener("click", handleAddChannel);
		} catch (e) {
			infoBox.textContent = `Failed to resolve: ${e.message || e}`;
		}
	}

	async function handleAddChannel() {
		const url = $("#urlInput").value.trim();
		if (!resolveData) return;
		const btn = $("#addBtn");
		btn.disabled = true;
		try {
			await api("/api/channels", {
				method: "POST",
				headers: { "content-type": "application/json" },
				body: JSON.stringify({
					url,
					title: resolveData.title,
					channel_id: resolveData.channel_id,
					thumbnail_url: resolveData.thumbnail_url || null,
				}),
			});
			$("#resolveInfo").textContent = "Added.";
			$("#urlInput").value = "";
			await refreshChannels();
			await refreshRecordings();
		} catch (e) {
			alert(`Add failed: ${e.message || e}`);
		} finally {
			btn.disabled = false;
		}
	}

	function renderChannels(channels, statuses) {
		const container = $("#channels");
		container.innerHTML = "";
		// build filter options
		const filter = $("#channelFilter");
		filter.innerHTML = `<option value="">All channels</option>`;
		channels.forEach((c) => {
			const opt = document.createElement("option");
			opt.value = c.id;
			opt.textContent = c.title || c.channel_id;
			filter.appendChild(opt);
		});

		channels.forEach((c) => {
			const s = statuses.find((x) => x.channel.id === c.id);
			const div = document.createElement("div");
			div.className = "channel";
			const isLive = !!(s && s.is_live);
			const isRec = !!(s && s.progress && s.progress.is_recording);
			const percent = s?.progress?.percent || 0;
			const lastLine = s?.progress?.last_line || "";
			const filename = s?.progress?.filename || "";
			const lastCheck = s?.last_check_at ? new Date(s.last_check_at * 1000).toLocaleString() : "";
			const thumb = c.thumbnail_url ? `<img class="avatar" src="${escapeAttr(c.thumbnail_url)}" alt="">` : `<div class="avatar placeholder"></div>`;
			const liveStatus = s?.live_status || (isLive ? "is_live" : "not_live");
			const streamTitle = s?.stream_title || "";
			const statusLabel = liveStatus === "is_upcoming" ? "Scheduled" : (isLive ? "Live" : "Idle");
			const statusClass = liveStatus === "is_upcoming" ? "" : (isLive ? "live" : "");
			div.innerHTML = `
				<div class="row" style="gap:12px; align-items:center;">
					${thumb}
					<div style="flex:1; min-width:0;">
						<div class="title">${escapeHtml(c.title || c.channel_id)}</div>
						<div class="meta">
							<span class="chip ${statusClass}"><span class="dot"></span>${escapeHtml(statusLabel)}</span>
							<span class="chip ${isRec ? "rec" : ""}"><span class="dot"></span>${isRec ? "Recording" : "Not recording"}</span>
							<a class="muted" href="${escapeAttr(c.url)}" target="_blank" rel="noreferrer">Open</a>
							<button class="danger" data-del="${c.id}">Remove</button>
						</div>
						${streamTitle ? `<div class="muted small">Stream: ${escapeHtml(streamTitle)}</div>` : ``}
						${lastCheck ? `<div class="muted small">Last check: ${escapeHtml(lastCheck)}</div>` : ``}
					</div>
				</div>
				<div class="progress"><div style="width: ${percent || 0}%;"></div></div>
				<div class="muted small">${escapeHtml(lastLine)}</div>
				${isRec && filename ? `<div class="muted small">${escapeHtml(filename)}</div>` : ``}
			`;
			container.appendChild(div);
		});
		$$("button[data-del]").forEach((btn) =>
			btn.addEventListener("click", async (e) => {
				const id = e.currentTarget.getAttribute("data-del");
				if (!confirm("Remove this channel?")) return;
				try {
					await api(`/api/channels/${id}`, { method: "DELETE" });
					await refreshChannels();
					await refreshRecordings();
				} catch (err) {
					alert(`Delete failed: ${err.message || err}`);
				}
			 })
		);
	}

	function renderRecordings(list) {
		const ul = $("#recordings");
		ul.innerHTML = "";
		list.forEach((r) => {
			const li = document.createElement("li");
			li.innerHTML = `
				<span class="muted small">${new Date(r.mtime * 1000).toLocaleString()}</span>
				<a class="name" href="/downloads/${escapeAttr(r.path)}" download>${escapeHtml(r.name)}</a>
				<span class="muted small">${formatBytes(r.size)}</span>
				<span class="actions">
					<a class="button small" href="/downloads/${escapeAttr(r.path)}" download>Download</a>
					<button class="button small danger rec-del" data-path="${escapeAttr(r.path)}">Delete</button>
				</span>
			`;
			ul.appendChild(li);
		});
		$$(".rec-del").forEach((btn) => {
			btn.addEventListener("click", async (e) => {
				const path = e.currentTarget.getAttribute("data-path");
				if (!confirm("Delete this recording?")) return;
				try {
					await api(`/api/recordings?path=${encodeURIComponent(path)}`, { method: "DELETE" });
					await refreshRecordings();
				} catch (err) {
					alert(`Delete failed: ${err.message || err}`);
				}
			});
		});
	}

	async function refreshChannels() {
		const [channels, status] = await Promise.all([
			api("/api/channels"),
			api("/api/status"),
		]);
		renderChannels(channels, status.channels || []);
	}

	async function refreshRecordings() {
		const sel = $("#channelFilter");
		const id = sel.value || "";
		const url = id ? `/api/recordings?channel_id=${encodeURIComponent(id)}` : "/api/recordings";
		const list = await api(url);
		renderRecordings(list);
	}

	function escapeHtml(s) {
		return (s || "").toString().replace(/[&<>"']/g, (c) => ({
			"&": "&amp;",
			"<": "&lt;",
			">": "&gt;",
			'"': "&quot;",
			"'": "&#039;",
		}[c]));
	}
	function escapeAttr(s) {
		return encodeURI((s || "").toString());
	}

	function init() {
		$("#resolveBtn").addEventListener("click", handleResolve);
		$("#refreshRecs").addEventListener("click", refreshRecordings);
		$("#channelFilter").addEventListener("change", refreshRecordings);
		refreshChannels();
		refreshRecordings();
		setInterval(refreshChannels, 4000);
	}

	return { init };
})(); 


