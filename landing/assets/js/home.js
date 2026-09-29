// Landing page: live activity feed + Spotify player.
//
// Data comes from the feed service (feed/ in the repo root), proxied by nginx at /api/.
//   GET /api/feed?limit=&before=&source=  -> { events: [...], has_more }
//   GET /api/music                         -> { enabled, now_playing, recent: [...] }
// Append ?demo to the URL to render bundled sample data instead (useful while the API is offline).
(function () {
    const DEMO = new URLSearchParams(location.search).has('demo');
    const API = {
        feed: DEMO ? '/assets/demo/feed.json' : '/api/feed',
        music: DEMO ? '/assets/demo/music.json' : '/api/music',
    };
    const PAGE_SIZE = 30;
    const FEED_POLL_MS = 60_000;
    const MUSIC_POLL_MS = 30_000;

    const ICONS = {
        github: '/assets/icons/github.svg',
        leetcode: '/assets/icons/leetcode.svg',
        letterboxd: '/assets/icons/letterboxd.svg',
        status: '/assets/icons/status.svg',
    };

    // ---------- helpers ----------

    const $ = (id) => document.getElementById(id);

    function el(tag, attrs = {}, ...children) {
        const node = document.createElement(tag);
        for (const [k, v] of Object.entries(attrs)) {
            if (v == null) continue;
            if (k === 'class') node.className = v;
            else node.setAttribute(k, v);
        }
        for (const child of children) {
            if (child == null || child === false) continue;
            node.append(child instanceof Node ? child : document.createTextNode(String(child)));
        }
        return node;
    }

    // Only allow http(s) links from the API.
    function safeUrl(url) {
        if (!url) return null;
        try {
            const u = new URL(url, location.origin);
            return u.protocol === 'https:' || u.protocol === 'http:' ? u.href : null;
        } catch {
            return null;
        }
    }

    const rtf = new Intl.RelativeTimeFormat('en', { numeric: 'auto', style: 'short' });
    function relativeTime(date) {
        const s = Math.round((date - Date.now()) / 1000);
        const abs = Math.abs(s);
        if (abs < 60) return 'just now';
        if (abs < 3600) return rtf.format(Math.round(s / 60), 'minute');
        if (abs < 86400) return rtf.format(Math.round(s / 3600), 'hour');
        if (abs < 86400 * 7) return rtf.format(Math.round(s / 86400), 'day');
        return date.toLocaleDateString([], { day: 'numeric', month: 'short' });
    }

    function dayLabel(date) {
        const start = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
        const diff = Math.round((start(new Date()) - start(date)) / 86400000);
        if (diff === 0) return 'Today';
        if (diff === 1) return 'Yesterday';
        return date.toLocaleDateString([], {
            weekday: 'short', day: 'numeric', month: 'short',
            year: date.getFullYear() === new Date().getFullYear() ? undefined : 'numeric',
        });
    }

    // Demo data carries fixed timestamps; shift them so they always look recent.
    const DEMO_EPOCH = Date.parse('2026-09-28T14:30:00Z');
    function shiftDemo(value) {
        if (Array.isArray(value)) return value.map(shiftDemo);
        if (value && typeof value === 'object') {
            const out = {};
            for (const [k, v] of Object.entries(value)) {
                out[k] = (k === 'ts' || k === 'played_at') && v
                    ? new Date(Date.parse(v) + (Date.now() - DEMO_EPOCH)).toISOString()
                    : shiftDemo(v);
            }
            return out;
        }
        return value;
    }

    async function getJSON(url) {
        const res = await fetch(url, { headers: { Accept: 'application/json' } });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        return DEMO ? shiftDemo(data) : data;
    }

    // ---------- feed ----------

    const timeline = $('timeline');
    const loadMoreBtn = $('load-more');
    const feedStatus = $('feed-status');
    const feedCount = $('feed-count');

    const state = {
        events: new Map(),   // id -> event
        source: 'all',
        hasMore: false,
        firstLoad: true,
    };

    function detailFor(ev) {
        const m = ev.meta || {};
        if (ev.source === 'leetcode' && m.difficulty) {
            const d = String(m.difficulty).toLowerCase();
            return el('span', { class: 'event-detail' },
                el('span', { class: `diff-${d}` }, m.difficulty),
                m.lang ? ` · ${m.lang}` : null);
        }
        if (ev.source === 'letterboxd' && m.rating != null) {
            const full = Math.floor(m.rating || 0);
            const half = (m.rating || 0) % 1 >= 0.5;
            return el('span', { class: 'event-detail' },
                el('span', { class: 'stars', title: `${m.rating} / 5` }, '★'.repeat(full) + (half ? '½' : '')),
                ev.detail ? ` · ${ev.detail}` : null);
        }
        if (ev.detail) {
            return el('span', { class: 'event-detail' },
                ev.source === 'github' ? el('code', {}, ev.detail) : ev.detail);
        }
        return null;
    }

    function renderEvent(ev, isNew) {
        const date = new Date(ev.ts);
        const url = safeUrl(ev.url);
        return el('li', { class: 'event' + (isNew ? ' new' : ''), 'data-id': ev.id },
            el('span', { class: 'event-icon' }, el('img', { src: ICONS[ev.source] || ICONS.status, alt: ev.source })),
            el('span', { class: 'event-text' },
                url ? el('a', { href: url, target: '_blank', rel: 'noopener' }, ev.title) : ev.title,
                detailFor(ev)),
            el('time', { class: 'event-time', datetime: date.toISOString(), title: date.toLocaleString() }, relativeTime(date)),
        );
    }

    function visibleEvents() {
        return [...state.events.values()]
            .filter((e) => state.source === 'all' || e.source === state.source)
            .sort((a, b) => new Date(b.ts) - new Date(a.ts));
    }

    function renderTimeline(newIds = new Set()) {
        const events = visibleEvents();
        timeline.replaceChildren();
        timeline.setAttribute('aria-busy', 'false');
        if (!events.length) {
            timeline.append(el('li', { class: 'timeline-empty' },
                state.source === 'all' ? 'No activity yet. Check back soon.' : 'Nothing from this source yet.'));
        }
        let lastDay = null;
        let prev = null;
        for (const ev of events) {
            const label = dayLabel(new Date(ev.ts));
            if (label !== lastDay) {
                if (prev) prev.classList.add('last-of-day');
                timeline.append(el('li', { class: 'timeline-day', 'aria-hidden': 'true' }, label));
                lastDay = label;
            }
            prev = renderEvent(ev, newIds.has(ev.id));
            timeline.append(prev);
        }
        loadMoreBtn.hidden = !state.hasMore;
        feedCount.textContent = `${events.length} event${events.length === 1 ? '' : 's'}`;
    }

    function renderFeedError(err) {
        timeline.setAttribute('aria-busy', 'false');
        if (state.events.size) {
            feedStatus.textContent = 'Connection lost, showing cached activity';
            return;
        }
        const retry = el('button', { class: 'btn', type: 'button' }, 'Retry');
        retry.addEventListener('click', () => {
            timeline.replaceChildren(el('li', { class: 'timeline-loading' }, 'Loading activity', el('span', { class: 'dots' })));
            loadFeed();
        });
        timeline.replaceChildren(el('li', {},
            el('div', { class: 'feed-error', role: 'alert' },
                el('div', { class: 'title-bar' }, el('div', { class: 'title-bar-text' }, 'live_feed.log')),
                el('div', { class: 'dialog' },
                    el('img', { class: 'dialog-icon', src: '/assets/icons/error.svg', alt: '' }),
                    el('p', {}, 'The activity service is not responding. It may be restarting, so try again in a minute.')),
                el('div', { class: 'dialog-actions' }, retry))));
        feedStatus.textContent = `Offline (${err.message})`;
    }

    async function loadFeed({ before } = {}) {
        const params = new URLSearchParams({ limit: PAGE_SIZE });
        if (before) params.set('before', before);
        try {
            const data = await getJSON(DEMO ? API.feed : `${API.feed}?${params}`);
            const newIds = new Set();
            for (const ev of data.events || []) {
                if (!state.events.has(ev.id) && !state.firstLoad && !before) newIds.add(ev.id);
                state.events.set(ev.id, ev);
            }
            if (before || state.firstLoad) state.hasMore = Boolean(data.has_more);
            state.firstLoad = false;
            renderTimeline(newIds);
            feedStatus.textContent = `Updated ${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
        } catch (err) {
            renderFeedError(err);
        }
    }

    loadMoreBtn.addEventListener('click', async () => {
        const oldest = [...state.events.values()].sort((a, b) => new Date(a.ts) - new Date(b.ts))[0];
        if (!oldest) return;
        loadMoreBtn.disabled = true;
        await loadFeed({ before: oldest.ts });
        loadMoreBtn.disabled = false;
    });

    document.querySelectorAll('.feed .toolbar [data-source]').forEach((btn) => {
        btn.addEventListener('click', () => {
            state.source = btn.dataset.source;
            document.querySelectorAll('.feed .toolbar [data-source]').forEach((b) =>
                b.setAttribute('aria-pressed', String(b === btn)));
            renderTimeline();
        });
    });

    // Refresh relative timestamps without refetching.
    setInterval(() => {
        timeline.querySelectorAll('.event-time').forEach((t) => {
            t.textContent = relativeTime(new Date(t.getAttribute('datetime')));
        });
    }, 30_000);

    // ---------- music ----------

    const player = $('player');
    const npTitle = $('np-title');
    const npArtist = $('np-artist');
    const npState = $('np-state');
    const npArt = $('np-art');
    const npLink = $('np-link');
    const npProgress = $('np-progress');
    const playlist = $('playlist');
    const musicStatus = $('music-status');
    let progressTimer = null;

    function setMarquee(text) {
        npTitle.textContent = text;
        const box = npTitle.parentElement;
        box.classList.remove('scroll');
        // Only scroll when the title overflows.
        requestAnimationFrame(() => {
            if (npTitle.scrollWidth > box.clientWidth) box.classList.add('scroll');
        });
    }

    function fmt(ms) {
        const s = Math.max(0, Math.floor(ms / 1000));
        return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
    }

    function renderMusic(data) {
        clearInterval(progressTimer);
        const np = data.now_playing;
        const last = (data.recent || [])[0];
        const shown = np || last;

        player.classList.toggle('playing', Boolean(np && np.is_playing));
        if (shown) {
            setMarquee(shown.title);
            npArtist.textContent = shown.artist || ' ';
            const art = safeUrl(shown.art);
            npArt.src = art || '/assets/icons/cd.svg';
            const link = safeUrl(shown.url);
            npLink.hidden = !link;
            if (link) npLink.href = link;
        } else {
            setMarquee('Nothing playing');
            npArtist.textContent = ' ';
            npArt.src = '/assets/icons/cd.svg';
            npLink.hidden = true;
        }

        if (np && np.is_playing) {
            npState.textContent = '▶ NOW PLAYING';
            let progress = np.progress_ms || 0;
            const duration = np.duration_ms || 0;
            const paint = () => {
                npProgress.style.width = duration ? `${Math.min(100, (progress / duration) * 100)}%` : '0';
                npState.textContent = duration ? `▶ NOW PLAYING  ${fmt(progress)}/${fmt(duration)}` : '▶ NOW PLAYING';
            };
            paint();
            progressTimer = setInterval(() => {
                progress += 1000;
                if (duration && progress > duration) {
                    clearInterval(progressTimer);
                    loadMusic();
                    return;
                }
                paint();
            }, 1000);
            musicStatus.textContent = 'playing';
        } else if (np) {
            npState.textContent = '❚❚ PAUSED';
            npProgress.style.width = np.duration_ms ? `${(np.progress_ms / np.duration_ms) * 100}%` : '0';
            musicStatus.textContent = 'paused';
        } else {
            npState.textContent = last ? `■ LAST PLAYED ${relativeTime(new Date(last.played_at)).toUpperCase()}` : '■ STOPPED';
            npProgress.style.width = '0';
            musicStatus.textContent = data.enabled === false ? 'not connected' : 'idle';
        }

        const recent = data.recent || [];
        playlist.replaceChildren(...(recent.length
            ? recent.map((t) => {
                const url = safeUrl(t.url);
                const label = `${t.artist} – ${t.title}`;
                const when = new Date(t.played_at);
                return el('li', {},
                    url ? el('a', { href: url, target: '_blank', rel: 'noopener', title: label }, label) : el('span', { title: label }, label),
                    el('time', { datetime: when.toISOString(), title: when.toLocaleString() },
                        when.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })));
            })
            : [el('li', { class: 'playlist-empty' }, 'no history')]));
    }

    async function loadMusic() {
        try {
            renderMusic(await getJSON(API.music));
        } catch {
            musicStatus.textContent = 'offline';
        }
    }

    // ---------- boot ----------

    loadFeed();
    loadMusic();
    if (!DEMO) {
        setInterval(() => { if (!document.hidden) loadFeed(); }, FEED_POLL_MS);
        setInterval(() => { if (!document.hidden) loadMusic(); }, MUSIC_POLL_MS);
        document.addEventListener('visibilitychange', () => {
            if (!document.hidden) { loadFeed(); loadMusic(); }
        });
    }
})();
