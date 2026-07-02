/* YT-FOMO Pokémon motif — Bellibolt's belly (Iono's ace).
   A faint always-on "bellybutton" glow with 7 lightning bolts radiating out
   (2 fork, giving 9 outer tips), fading in/out calmly like a distant storm.
   Kept very low-opacity — pure background. Tune BOLT_MAX / GLOW to taste. */
(function () {
	var host = document.getElementById('belly');
	if (!host) return;
	var NS = 'http://www.w3.org/2000/svg';
	var SIZE = 800, C = SIZE / 2, R = 355;
	var BOLT_MAX = 0.13;   /* peak opacity of a lit bolt */
	var GLOW = 0.11;       /* constant bellybutton glow */
	var N = 7, FORK = [2, 5];   /* 7 roots; #2 and #5 split -> 9 tips */
	var reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

	function rnd(a, b) { return a + Math.random() * (b - a); }
	function pts(angle, r0, r1, segs, jit) {
		var ax = Math.cos(angle), ay = Math.sin(angle), px = -ay, py = ax, out = [];
		for (var i = 0; i <= segs; i++) {
			var t = i / segs, r = r0 + (r1 - r0) * t;
			var j = (i === 0 || i === segs) ? 0 : rnd(-jit, jit) * (1 - Math.abs(0.5 - t));
			out.push([C + ax * r + px * j, C + ay * r + py * j]);
		}
		return out;
	}
	function d(p) { return 'M' + p.map(function (q) { return q[0].toFixed(1) + ' ' + q[1].toFixed(1); }).join(' L'); }
	function bolt(path) {
		var el = document.createElementNS(NS, 'path');
		el.setAttribute('d', d(path));
		el.setAttribute('fill', 'none');
		el.setAttribute('stroke', '#fcd34d');
		el.setAttribute('stroke-width', '2.2');
		el.setAttribute('stroke-linecap', 'round');
		el.setAttribute('stroke-linejoin', 'round');
		el.setAttribute('filter', 'url(#bsoft)');
		return el;
	}

	var svg = document.createElementNS(NS, 'svg');
	svg.setAttribute('viewBox', '0 0 ' + SIZE + ' ' + SIZE);
	svg.setAttribute('width', '100%'); svg.setAttribute('height', '100%');
	svg.innerHTML =
		'<defs>' +
		'<filter id="bsoft" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="1.5"/></filter>' +
		'<radialGradient id="bcore"><stop offset="0%" stop-color="#fff7e0"/><stop offset="40%" stop-color="#fcd34d"/><stop offset="100%" stop-color="#fcd34d" stop-opacity="0"/></radialGradient>' +
		'</defs>';

	var glow = document.createElementNS(NS, 'circle');
	glow.setAttribute('cx', C); glow.setAttribute('cy', C); glow.setAttribute('r', 40);
	glow.setAttribute('fill', 'url(#bcore)'); glow.setAttribute('opacity', GLOW);
	glow.setAttribute('filter', 'url(#bsoft)');
	svg.appendChild(glow);

	var groups = [];
	for (var i = 0; i < N; i++) {
		var angle = (-90 + i * (360 / N)) * Math.PI / 180 + rnd(-0.08, 0.08);
		var g = document.createElementNS(NS, 'g');
		g.setAttribute('opacity', '0');
		if (FORK.indexOf(i) !== -1) {
			var forkR = R * 0.58;
			var stem = pts(angle, 34, forkR, 4, 24);
			var tip = stem[stem.length - 1];
			g.appendChild(bolt(stem));
			[-0.32, 0.32].forEach(function (da) {
				var br = pts(angle + da, forkR, R, 4, 28);
				br[0] = tip;
				g.appendChild(bolt(br));
			});
		} else {
			g.appendChild(bolt(pts(angle, 34, R, 6, 30)));
		}
		svg.appendChild(g); groups.push(g);
	}
	host.appendChild(svg);

	if (reduce) { groups.forEach(function (g) { g.style.opacity = (BOLT_MAX * 0.5).toFixed(3); }); return; }

	function flash(idxs) {
		idxs.forEach(function (i) {
			var g = groups[i];
			g.style.transition = 'opacity ' + rnd(0.8, 1.1).toFixed(2) + 's ease-in';
			g.style.opacity = (BOLT_MAX * rnd(0.7, 1)).toFixed(3);
			setTimeout(function () {
				g.style.transition = 'opacity ' + rnd(1.4, 2.0).toFixed(2) + 's ease-out';
				g.style.opacity = '0';
			}, rnd(500, 1100));
		});
	}
	function tick() {
		var roll = Math.random();
		if (roll < 0.55) {
			flash([Math.floor(rnd(0, N))]);                     /* a single bolt */
		} else if (roll < 0.88) {
			var s = Math.floor(rnd(0, N)), len = Math.random() < 0.5 ? 2 : 3, grp = [];
			for (var k = 0; k < len; k++) grp.push((s + k) % N); /* an adjacent group */
			flash(grp);
		} else {
			var all = []; for (var m = 0; m < N; m++) all.push(m);
			flash(all);                                          /* the whole storm */
		}
		setTimeout(tick, rnd(1700, 3300));
	}
	glow.style.transition = 'opacity 4s ease-in-out';
	(function pulse() { glow.style.opacity = (GLOW * rnd(0.65, 1.25)).toFixed(3); setTimeout(pulse, rnd(3600, 5600)); })();
	setTimeout(tick, 900);
})();
