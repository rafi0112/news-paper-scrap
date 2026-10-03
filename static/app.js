/* =========================================================
   News — app
   ---------------------------------------------------------
   - Data:   /api/today (Bangladesh, last 24h) + /api/palestine
   - Ranking: on-device interest profile (sources, topics,
              regions, video) + freshness + trending + novelty,
              re-ranked for diversity. Nothing leaves the browser.
========================================================= */
"use strict";

/* ---------------------------------------------------------
   CONFIG
--------------------------------------------------------- */
const CONFIG = {
    API_BASE: location.protocol === "file:" ? "http://127.0.0.1:8000/api" : "/api",
    PAGE: 10,
    GRID_PAGE: 18,
    TODAY_REFRESH: 90_000,
    PAL_REFRESH: 600_000,
    PAL_WAIT: 7000,
    STORY_MS: 6500,
};

/* ---------------------------------------------------------
   UTILITIES
--------------------------------------------------------- */
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

function esc(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}

function safeUrl(value) {
    try {
        const url = new URL(value, location.href);
        return url.protocol === "http:" || url.protocol === "https:" ? url.href : "#";
    } catch {
        return "#";
    }
}

function sel(key) {
    return `[data-key="${CSS.escape(key)}"]`;
}

function hoursAgo(item) {
    return item.ts ? Math.max(0, (Date.now() - item.ts) / 3_600_000) : 12;
}

function timeAgo(ts) {
    if (!ts) return "";
    const s = Math.max(0, Math.floor((Date.now() - ts) / 1000));
    if (s < 60) return "just now";
    const m = Math.floor(s / 60);
    if (m < 60) return `${m}m ago`;
    const h = Math.floor(m / 60);
    if (h < 24) return `${h}h ago`;
    const d = Math.floor(h / 24);
    return d < 7 ? `${d}d ago` : new Date(ts).toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

function hashNum(str) {
    let h = 2166136261;
    for (let i = 0; i < str.length; i++) {
        h ^= str.charCodeAt(i);
        h = Math.imul(h, 16777619);
    }
    return h >>> 0;
}

const rand01 = (str) => (hashNum(str) % 10000) / 10000;
const hue = (name) => hashNum(name || "") % 360;

function initials(name) {
    return String(name || "").replace(/[^\p{L}\p{N} ]/gu, "").split(/\s+/).filter(Boolean)
        .slice(0, 2).map((w) => w[0]).join("").toUpperCase() || "N";
}

function avatarHTML(source, cls = "avatar") {
    return `<span class="${cls}" style="--h:${hue(source)}" aria-hidden="true">${esc(initials(source))}</span>`;
}

function debounce(fn, ms) {
    let t;
    return (...args) => {
        clearTimeout(t);
        t = setTimeout(() => fn(...args), ms);
    };
}

const store = {
    get(key, fallback) {
        try {
            const raw = localStorage.getItem(key);
            return raw ? JSON.parse(raw) : fallback;
        } catch {
            return fallback;
        }
    },
    set(key, value) {
        try {
            localStorage.setItem(key, JSON.stringify(value));
        } catch { /* storage full or blocked */ }
    },
};

async function api(path) {
    const response = await fetch(`${CONFIG.API_BASE}/${path}`, { cache: "no-store" });
    if (!response.ok) throw new Error(`${path}: ${response.status}`);
    return response.json();
}

function withTimeout(promise, ms) {
    return Promise.race([promise, new Promise((_, reject) => setTimeout(() => reject(new Error("timeout")), ms))]);
}

function withTransition(update) {
    if (!document.startViewTransition || matchMedia("(prefers-reduced-motion: reduce)").matches) {
        update();
        return;
    }
    // The callback can be deferred while the page isn't painting; never let navigation wait on it.
    let done = false;
    const run = () => {
        if (done) return;
        done = true;
        update();
    };
    const t = document.startViewTransition(run);
    t.ready.catch(() => { });
    t.finished.catch(() => { });
    setTimeout(run, 300);
}

/* ---------------------------------------------------------
   ICONS
--------------------------------------------------------- */
const I = {
    home: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l2.4 5.6L20 11l-5.6 2.4L12 19l-2.4-5.6L4 11l5.6-2.4z"/></svg>`,
    bd: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="5" width="18" height="14" rx="2.5"/><circle cx="10.5" cy="12" r="3.2" fill="currentColor" stroke="none"/></svg>`,
    pal: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"><path d="M12 3l4 4-4 4-4-4zM12 13l4 4-4 4-4-4zM3 12l4-4 4 4-4 4zM13 12l4-4 4 4-4 4z"/></svg>`,
    shorts: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="6" y="2.5" width="12" height="19" rx="3"/><path d="M10.5 9.5v5l4-2.5z" fill="currentColor"/></svg>`,
    lib: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"><path d="M6 3h12v18l-6-4.5L6 21z"/></svg>`,
    bookmark: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"><path d="M6 3h12v18l-6-4.5L6 21z"/></svg>`,
    share: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12v7a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-7M16 6l-4-4-4 4M12 2v14"/></svg>`,
    x: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M6 6l12 12M18 6 6 18"/></svg>`,
    play: `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M7 4.5v15l13-7.5z"/></svg>`,
    spark: `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2l2.2 6.6L21 11l-6.8 2.4L12 20l-2.2-6.6L3 11l6.8-2.4z"/></svg>`,
    flame: `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2s5 4.2 5 9.3c0 1.6-.6 3-1.5 4 .2-2.1-1-3.8-2.5-4.8.3 2.4-1.2 3.6-2.4 4.3-.9-1.1-1.1-2.6-.6-4.1C7.6 12 6 14.3 6 17c0 .6.1 1.2.3 1.7C4.9 17.4 4 15.6 4 13.5 4 8.6 9.5 6.5 12 2z"/></svg>`,
    yt: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/></svg>`,
    thumbDown: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M5.6 5.6l12.8 12.8"/></svg>`,
    up: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 15l-6-6-6 6"/></svg>`,
    down: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9l6 6 6-6"/></svg>`,
};

/* ---------------------------------------------------------
   TOKENS (topics)
--------------------------------------------------------- */
const STOP = new Set(`
about above after again against amid among also another around because been before being below between both
calls came come comes could does doing down during each even every from further gets give given goes going
have having here hers herself himself into itself just know known last later latest least less like made make
makes many more most much must near need never news next only other ours over part people really said same
says seen should show shows since some still such take takes than that their theirs them then there these
they this those though three through told tells today under until upon very video videos want wants watch
week were what when where which while whom whose will with within without would year years your yours live
update updates full first second report reports reported says amid says shorts episode exclusive breaking
world told days time times back call called asks asked minister ministry release released government official
officials country president state public plan plans says
এবং করে করা হয়ে থেকে জন্য নিয়ে বলে হবে তার এই সেই একটি কথা বিষয়ে পর দিকে মধ্যে করেন বলেন তিনি তারা আমরা
ছিল শুরু হচ্ছে দেওয়া দিয়ে আরও কোনো সব যে যা না নেই ছাড়া করতে হলে হলো হয়েছে হয়েছেন রয়েছে দেশের
নতুন বিভিন্ন প্রথম আজ গত বছর দিন সময় পরে আগে প্রতি বলেছেন জানিয়েছেন জানান সরকার সরকারের খবর ভিডিও দেখুন
january february march april may june july august september october november december
monday tuesday wednesday thursday friday saturday sunday
`.normalize("NFC").split(/\s+/).filter(Boolean));

// Topics never surfaced as hashtags (trending, interests, "why" labels). Stories themselves still appear.
const HIDDEN_TOPICS = new Set(["israel"]);

const LABELS = new Map();
// How often a word is capitalised mid-headline: proper nouns make better topics.
const CAPS = new Map();

// Demonyms and plurals collapse into one topic ("Israeli" -> "Israel").
const ALIAS = {
    israeli: "israel", israelis: "israel", palestinian: "palestine", palestinians: "palestine",
    gazan: "gaza", gazans: "gaza", bangladeshi: "bangladesh", bangladeshis: "bangladesh",
    iranian: "iran", lebanese: "lebanon", syrian: "syria",
};

function stem(word) {
    if (ALIAS[word]) return ALIAS[word];
    if (word.length > 5 && word.endsWith("ies")) return word.slice(0, -3) + "y";
    if (word.length > 4 && word.endsWith("s") && !word.endsWith("ss")) return word.slice(0, -1);
    return word;
}

// Multi-word place names stay one topic ("West Bank", not "West").
const PHRASES = [
    [/\bwest bank\b/gi, "West-Bank"],
    [/\bw\.\s?bank\b/gi, "West-Bank"],
    [/\bgaza city\b/gi, "Gaza-City"],
    [/\beast jerusalem\b/gi, "East-Jerusalem"],
    [/\bal[- ]aqsa\b/gi, "Al-Aqsa"],
    [/\bkhan you?nis\b/gi, "Khan-Younis"],
];

function tokenize(text) {
    const out = new Set();
    for (const [re, joined] of PHRASES) text = String(text || "").replace(re, joined);
    // NFC keeps Bangla letters like "য়" in one form so stopwords match.
    for (const m of String(text || "").normalize("NFC").matchAll(/[\p{L}\p{M}][\p{L}\p{M}\p{N}'’-]{3,}/gu)) {
        const raw = m[0].replace(/['’]s$/u, "").replace(/^-+|-+$/g, "");
        const lower = raw.toLowerCase();
        if (lower.length < 4 || STOP.has(lower)) continue;
        const t = stem(lower);
        if (STOP.has(t)) continue;
        const shown = t !== lower && ALIAS[lower] ? t.charAt(0).toUpperCase() + t.slice(1) : raw;
        if (!LABELS.has(t) || (/^\p{Lu}/u.test(shown) && !/^\p{Lu}/u.test(LABELS.get(t)))) LABELS.set(t, shown);
        if (m.index > 0 && /^[A-Za-z]/.test(raw)) {
            const c = CAPS.get(t) || [0, 0];
            c[0] += /^[A-Z]/.test(raw) ? 1 : 0;
            c[1] += 1;
            CAPS.set(t, c);
        }
        out.add(t);
    }
    return [...out];
}

const label = (t) => (LABELS.get(t) || t).replaceAll("-", " ");

/* ---------------------------------------------------------
   DATA
--------------------------------------------------------- */
const DATA = {
    bd: [],
    pal: null,
    articles: [],
    videos: [],
    all: [],
    byKey: new Map(),
    trending: [],
    todayAt: 0,
    palAt: 0,
};

function normalize(raw, region) {
    const ts = raw.published_at ? Date.parse(raw.published_at) : 0;
    const isVideo = raw.kind === "video" && /^[\w-]{11}$/.test(raw.video_id || "");
    const title = raw.title || "";
    return {
        key: raw.url,
        url: raw.url,
        title,
        description: raw.description || "",
        image: raw.image || null,
        source: raw.source || "Unknown",
        published_at: raw.published_at || null,
        ts: Number.isNaN(ts) ? 0 : ts,
        kind: isVideo ? "video" : "article",
        video_id: isVideo ? raw.video_id : null,
        isShort: isVideo && /\/shorts\//.test(raw.url || ""),
        lang: raw.lang || (/[ঀ-৿]/.test(title) ? "bn" : "en"),
        region,
        tokens: tokenize(title),
    };
}

function rebuild() {
    const pal = DATA.pal || { articles: [], videos: [] };
    DATA.articles = [...DATA.bd, ...pal.articles];
    DATA.videos = pal.videos;
    DATA.all = [...DATA.articles, ...DATA.videos].sort((a, b) => b.ts - a.ts);
    DATA.byKey = new Map(DATA.all.map((i) => [i.key, i]));
    DATA.trending = computeTrending(DATA.all);
}

function setToday(payload) {
    DATA.bd = (payload.news || []).filter((n) => n.url && n.title).map((n) => normalize(n, "bd"));
    DATA.todayAt = Date.now();
}

function setPalestine(payload) {
    DATA.pal = {
        raw: payload,
        articles: (payload.articles || []).map((a) => normalize(a, "pal")),
        videos: (payload.videos || []).map((v) => normalize(v, "pal")).filter((v) => v.kind === "video"),
    };
    DATA.palAt = Date.now();
}

function getItem(key) {
    return DATA.byKey.get(key) || saved.find((s) => s.key === key) || P.history.find((h) => h.key === key) || null;
}

function slim(item) {
    const { key, url, title, description, image, source, published_at, ts, kind, video_id, isShort, lang, region, tokens } = item;
    return { key, url, title, description, image, source, published_at, ts, kind, video_id, isShort, lang, region, tokens };
}

/* ---------------------------------------------------------
   TRENDING
--------------------------------------------------------- */
function isProperish(token) {
    if (!/^[a-z]/.test(token)) return true;
    const c = CAPS.get(token);
    return !!c && c[1] >= 2 && c[0] / c[1] >= 0.6;
}

function computeTrending(items) {
    const map = new Map();
    for (const it of items) {
        for (const t of it.tokens) {
            let e = map.get(t);
            if (!e) map.set(t, (e = { token: t, items: [], sources: new Set(), heat: 0 }));
            e.items.push(it);
            e.sources.add(it.source);
            e.heat += Math.exp(-hoursAgo(it) / 10);
        }
    }

    const n = Math.max(items.length, 1);
    const ranked = [...map.values()]
        .filter((e) => e.items.length >= 3 && e.sources.size >= 2 && e.items.length < n * 0.45 && isProperish(e.token) && !HIDDEN_TOPICS.has(e.token))
        .map((e) => ({ ...e, score: e.heat * Math.sqrt(e.sources.size) }))
        .sort((a, b) => b.score - a.score);

    // Drop topics that are mostly the same stories as a stronger topic.
    const picked = [];
    for (const e of ranked) {
        const keys = new Set(e.items.map((i) => i.key));
        const dup = picked.some((p) => {
            const overlap = p.items.filter((i) => keys.has(i.key)).length;
            return overlap / Math.min(keys.size, p.items.length) > 0.7;
        });
        if (!dup) picked.push(e);
        if (picked.length >= 12) break;
    }
    return picked;
}

/* ---------------------------------------------------------
   PROFILE (on-device personalisation)
--------------------------------------------------------- */
const DAY = 86_400_000;

const P = Object.assign({
    v: 1,
    src: {}, kw: {}, region: {}, kind: {},
    seen: {}, read: {}, hidden: {},
    history: [],
    storySeen: {},
    lastVisit: 0, prevVisit: 0,
    streak: { n: 0, day: "" },
    decayDay: "",
    onboarded: false,
    hintShorts: false,
}, store.get("bn-profile-v1", {}));

let saved = store.get("bn-saved-v2", []);

const saveProfile = debounce(() => store.set("bn-profile-v1", P), 400);

function bump(map, key, w) {
    map[key] = Math.max(-20, Math.min(60, (map[key] || 0) + w));
}

function learn(item, w) {
    if (!item) return;
    bump(P.src, item.source, w);
    bump(P.region, item.region, w * 0.6);
    bump(P.kind, item.kind, w * 0.5);
    for (const t of (item.tokens || []).slice(0, 8)) bump(P.kw, t, w * 0.55);
    saveProfile();
    renderInterests();
}

function maintainProfile() {
    const today = new Date().toDateString();
    const now = Date.now();

    // Daily decay so interests drift with you.
    if (P.decayDay && P.decayDay !== today) {
        const days = Math.min(30, Math.round((Date.parse(today) - Date.parse(P.decayDay)) / DAY)) || 1;
        const f = Math.pow(0.92, days);
        for (const map of [P.src, P.kw, P.region, P.kind]) {
            for (const k in map) {
                map[k] *= f;
                if (Math.abs(map[k]) < 0.05) delete map[k];
            }
        }
    }
    P.decayDay = today;

    // News older than a day is deleted server-side, so per-item state only needs ~2 days.
    for (const map of [P.seen, P.read, P.hidden]) {
        for (const k in map) if (now - map[k] > 2 * DAY) delete map[k];
    }
    const kw = Object.entries(P.kw).sort((a, b) => Math.abs(b[1]) - Math.abs(a[1])).slice(0, 300);
    P.kw = Object.fromEntries(kw);
    P.history = P.history.slice(0, 100);

    // Visits & streak.
    if (now - P.lastVisit > 30 * 60_000) P.prevVisit = P.lastVisit;
    P.lastVisit = now;

    if (P.streak.day !== today) {
        const yesterday = new Date(now - DAY).toDateString();
        P.streak = { n: P.streak.day === yesterday ? P.streak.n + 1 : 1, day: today };
    }
    saveProfile();
}

function markSeen(item) {
    if (!item || P.seen[item.key]) return;
    P.seen[item.key] = Date.now();
    saveProfile();
}

function markRead(item) {
    if (!item) return;
    P.read[item.key] = Date.now();
    P.seen[item.key] = P.seen[item.key] || Date.now();
    P.history = [slim(item), ...P.history.filter((h) => h.key !== item.key)].slice(0, 100);
    saveProfile();
    $$(sel(item.key)).forEach((el) => el.classList.add("is-read"));
}

const isNew = (item) => P.prevVisit && item.ts > P.prevVisit && !P.seen[item.key];

/* ---------------------------------------------------------
   RANKING
--------------------------------------------------------- */
const SESSION_SEED = String(Math.floor(Date.now() / (20 * 60_000)));

function scoreItem(item, trendSet) {
    const age = hoursAgo(item);
    const parts = {};

    parts.fresh = 2.4 * Math.exp(-age / 9);
    parts.src = 1.8 * Math.tanh((P.src[item.source] || 0) / 8);

    let kwSum = 0, topT = null, topV = 0;
    for (const t of item.tokens) {
        const v = P.kw[t] || 0;
        kwSum += v;
        if (v > topV && !HIDDEN_TOPICS.has(t)) { topV = v; topT = t; }
    }
    parts.kw = 2 * Math.tanh(kwSum / 10);
    parts.region = 0.9 * Math.tanh((P.region[item.region] || 0) / 8);
    parts.kind = item.kind === "video" ? 0.2 + 0.9 * Math.tanh((P.kind.video || 0) / 6) : 0;

    let trend = 0, trendT = null;
    for (const t of item.tokens) if (trendSet.has(t)) { trend += 0.45; trendT = trendT || t; }
    parts.trend = Math.min(trend, 1.1);

    const novelty = P.read[item.key] ? -3.5 : P.seen[item.key] ? -0.9 : 0.4;
    const image = item.image ? 0.35 : -0.4;
    const explore = rand01(item.key + SESSION_SEED) * 0.7;

    const score = parts.fresh + parts.src + parts.kw + parts.region + parts.kind + parts.trend + novelty + image + explore;

    let why = null;
    const best = Math.max(parts.src, parts.kw, parts.trend);
    if (best > 0.55) {
        if (best === parts.kw && topT) why = { text: `Because you follow #${label(topT)}` };
        else if (best === parts.src) why = { text: `Because you read ${item.source}` };
        else if (trendT) why = { text: `Trending · #${label(trendT)}`, hot: true };
    }
    if (!why && age < 1.2) why = { text: "Just in", hot: true };

    return { item, score, why };
}

function rank(items) {
    const trendSet = new Set(DATA.trending.slice(0, 8).map((t) => t.token));
    const pool = items.filter((i) => !P.hidden[i.key]).map((i) => scoreItem(i, trendSet)).sort((a, b) => b.score - a.score);

    // Greedy re-rank for variety: avoid runs of one source or of videos.
    const out = [];
    while (pool.length) {
        let bestI = 0, best = -Infinity;
        const recent = out.slice(-3);
        for (let i = 0; i < Math.min(pool.length, 40); i++) {
            const c = pool[i];
            let adj = c.score - 0.9 * recent.filter((r) => r.item.source === c.item.source).length;
            if (c.item.kind === "video" && out.slice(-4).some((r) => r.item.kind === "video")) adj -= 1.2;
            if (adj > best) { best = adj; bestI = i; }
        }
        out.push(pool.splice(bestI, 1)[0]);
    }
    return out;
}

/* ---------------------------------------------------------
   CARD RENDERING
--------------------------------------------------------- */
function mediaHTML(item, { tags = true } = {}) {
    const img = item.image
        ? `<img src="${esc(safeUrl(item.image))}" alt="" loading="lazy" decoding="async" referrerpolicy="no-referrer" class="loading">`
        : "";
    const tagList = [];
    if (tags && isNew(item)) tagList.push(`<span class="tag new">New</span>`);
    else if (tags && item.kind === "video") tagList.push(`<span class="tag">${item.isShort ? "Short" : "Video"}</span>`);

    return `
        <div class="media${item.image ? "" : " no-img"}">
            ${img}
            <span class="ph" aria-hidden="true">${esc(initials(item.source))}</span>
            ${tagList.join("")}
            ${item.lang === "bn" && item.region === "pal" ? `<span class="tag right">বাংলা</span>` : ""}
            ${item.kind === "video" ? `<button class="play" data-watch="${esc(item.key)}" aria-label="Play: ${esc(item.title)}"><span>${I.play}</span></button>` : ""}
        </div>`;
}

function cardHTML(item, { variant = "", why = null, i = 0, dismiss = false } = {}) {
    if (!item) return "";
    const isSaved = saved.some((s) => s.key === item.key);
    const video = item.kind === "video";
    const link = video
        ? `<a href="${esc(safeUrl(item.url))}" data-watch="${esc(item.key)}">${esc(item.title)}</a>`
        : `<a class="stretched" href="${esc(safeUrl(item.url))}" target="_blank" rel="noopener noreferrer" data-open="${esc(item.key)}">${esc(item.title)}</a>`;

    const cls = ["card", variant, video ? "video" : "", item.image ? "" : "no-media", P.read[item.key] ? "is-read" : ""].join(" ");

    return `
        <article class="${cls}" style="--i:${i % 10}" data-key="${esc(item.key)}">
            ${mediaHTML(item)}
            <div class="card-body">
                <div class="kicker">${avatarHTML(item.source)}<span class="src">${esc(item.source)}</span><time datetime="${esc(item.published_at || "")}">${timeAgo(item.ts)}</time></div>
                <h3 class="headline">${link}</h3>
                ${item.description && variant !== "brief" ? `<p class="dek">${esc(item.description)}</p>` : ""}
                ${why ? `<span class="why${why.hot ? " hot" : ""}">${why.hot ? I.flame : I.spark}${esc(why.text)}</span>` : ""}
                <div class="card-foot">
                    ${video
            ? `<a class="read" href="${esc(safeUrl(item.url))}" data-watch="${esc(item.key)}">Watch</a>`
            : `<a class="read" href="${esc(safeUrl(item.url))}" target="_blank" rel="noopener noreferrer" data-open="${esc(item.key)}">Read at source</a>`}
                    <button class="mini-btn" type="button" data-share="${esc(item.key)}" aria-label="Share">${I.share}</button>
                    <button class="mini-btn" type="button" data-save="${esc(item.key)}" aria-pressed="${isSaved}" aria-label="${isSaved ? "Remove from library" : "Save to library"}">${I.bookmark}</button>
                    ${dismiss ? `<button class="mini-btn" type="button" data-hide="${esc(item.key)}" aria-label="Not interested">${I.x}</button>` : ""}
                </div>
            </div>
        </article>`;
}

function leadHTML(items) {
    if (!items.length) return "";
    const [lead, ...rest] = items;
    return `
        <div class="lead-grid">
            ${cardHTML(lead, { variant: "lead" })}
            <div class="side-list">${rest.map((it, i) => cardHTML(it, { variant: "brief", i: i + 1 })).join("")}</div>
        </div>`;
}

function shortTileHTML(v) {
    return `
        <button class="short-tile" type="button" data-short="${esc(v.video_id)}" aria-label="Play short: ${esc(v.title)}">
            <img src="https://i.ytimg.com/vi/${esc(v.video_id)}/hqdefault.jpg" alt="" loading="lazy">
            <small>${esc(v.source)}</small>
            <span>${esc(v.title)}</span>
        </button>`;
}

function shelfModuleHTML(videos) {
    if (!videos.length) return "";
    return `
        <section class="shelf-block module" aria-label="Shorts">
            <div class="shelf-head"><h3>${I.shorts}Shorts</h3><a href="#/shorts">Watch all →</a></div>
            <div class="shelf">${videos.map(shortTileHTML).join("")}</div>
        </section>`;
}

function developingHTML(topic) {
    const bySource = new Map();
    for (const it of [...topic.items].sort((a, b) => b.ts - a.ts)) {
        if (it.kind !== "article" || bySource.has(it.source)) continue;
        bySource.set(it.source, it);
    }
    const list = [...bySource.values()].slice(0, 4);
    if (list.length < 2) return "";
    return `
        <section class="developing module">
            <p class="eyebrow">● Developing story</p>
            <h3>#${esc(label(topic.token))}</h3>
            <ol>${list.map((it) => `
                <li><div>
                    <a href="${esc(safeUrl(it.url))}" target="_blank" rel="noopener noreferrer" data-open="${esc(it.key)}">${esc(it.title)}</a>
                    <small>${esc(it.source)} · ${timeAgo(it.ts)}</small>
                </div></li>`).join("")}
            </ol>
            <button class="more-link" type="button" data-topic="${esc(topic.token)}">See all ${topic.items.length} reports from ${topic.sources.size} outlets →</button>
        </section>`;
}

function skeletonHTML(n, h = 320) {
    return Array.from({ length: n }, () => `<div class="skeleton" style="height:${h}px"></div>`).join("");
}

function emptyHTML(title, text) {
    return `<div class="empty"><b>${esc(title)}</b>${esc(text)}</div>`;
}

function chipsHTML(options, active, attr) {
    return options.map(({ value, text, count }) =>
        `<button class="chip" type="button" ${attr}="${esc(value)}" aria-pressed="${value === active}">${esc(text)}${count != null ? ` <small>${count}</small>` : ""}</button>`
    ).join("");
}

function countBy(items, fn) {
    const m = new Map();
    items.forEach((i) => m.set(fn(i), (m.get(fn(i)) || 0) + 1));
    return [...m.entries()].sort((a, b) => b[1] - a[1]);
}

// Images: fade in on load, fall back to the pattern placeholder on error.
document.addEventListener("load", (e) => {
    if (e.target.tagName === "IMG") e.target.classList.remove("loading");
}, true);

document.addEventListener("error", (e) => {
    const media = e.target.tagName === "IMG" && e.target.closest(".media");
    if (media) {
        media.classList.add("no-img");
        media.closest(".card")?.classList.add("no-media");
    }
}, true);

/* ---------------------------------------------------------
   PAGERS (infinite scroll)
--------------------------------------------------------- */
const pagers = {};

// Cards are grouped into decks of this size; each deck stacks on its own (mobile).
const DECK_SIZE = 8;

function setPager(name, { container, entries, render, size, sentinel, onEnd, isCard = () => true }) {
    const totalCards = entries.filter(isCard).length;
    pagers[name] = { container, entries, render, size, shown: 0, sentinel, onEnd, isCard, cards: 0, totalCards };
    $(container).innerHTML = "";
    pageMore(name);
}

function deckBreakHTML(from, to, total) {
    return `<div class="deck-break" aria-hidden="true"><i></i><span>${from}–${to} of ${total}</span><i></i></div>`;
}

function pageMore(name) {
    const p = pagers[name];
    if (!p || p.shown >= p.entries.length) return;
    const box = $(p.container);
    const chunk = p.entries.slice(p.shown, p.shown + p.size);

    chunk.forEach((e, i) => {
        const html = p.render(e, p.shown + i);
        if (!html) return;

        if (!p.isCard(e)) {
            box.insertAdjacentHTML("beforeend", html);
            return;
        }

        let deck = box.lastElementChild;
        if (!deck?.classList.contains("deck") || deck.childElementCount >= DECK_SIZE) {
            if (deck?.classList.contains("deck")) {
                box.insertAdjacentHTML("beforeend", deckBreakHTML(p.cards + 1, Math.min(p.cards + DECK_SIZE, p.totalCards), p.totalCards));
            }
            box.insertAdjacentHTML("beforeend", `<div class="deck"></div>`);
            deck = box.lastElementChild;
        }
        deck.insertAdjacentHTML("beforeend", html);
        p.cards++;
    });

    p.shown += chunk.length;
    observeCards($(p.container));
    scheduleStack();
    if (p.shown >= p.entries.length) {
        p.onEnd?.();
        return;
    }

    // The observer won't fire again if the sentinel never left the viewport, so keep filling.
    requestAnimationFrame(() => {
        const s = $(`#${name}-sentinel`);
        if (s && !s.closest(".view")?.hidden && s.getBoundingClientRect().top < innerHeight + 900) pageMore(name);
    });
}

const pageObserver = "IntersectionObserver" in window && new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        const name = entry.target.dataset.pager;
        if (name && !entry.target.closest(".view")?.hidden) pageMore(name);
    });
}, { rootMargin: "900px 0px" });

/* ---------------------------------------------------------
   MOBILE CARD DECK
   Cards are sticky (see app.css). Here each card gets a depth:
   how many of the following cards have slid over it. Depth drives
   shrink / lift / tilt / dim, so the deck reacts to scrolling both ways.
--------------------------------------------------------- */
const stackMQ = matchMedia("(max-width: 639px) and (prefers-reduced-motion: no-preference)");
let stackFrame = 0;

function scheduleStack() {
    if (!stackFrame) stackFrame = requestAnimationFrame(() => { stackFrame = 0; updateStack(); });
}

function resetStack(el) {
    el.style.removeProperty("transform");
    el.style.removeProperty("--dim");
    el.classList.remove("is-front", "is-buried");
    delete el.dataset.depth;
}

function updateStack() {
    const containers = $$(".deck").filter((c) => !c.closest(".view")?.hidden);

    if (!stackMQ.matches) {
        $$(".deck > [data-depth]").forEach(resetStack);
        return;
    }

    for (const c of containers) {
        const kids = [...c.children];
        if (!kids.length) continue;

        const stickTop = parseFloat(getComputedStyle(kids[0]).top) || 0;

        // Read everything first, then write, to avoid layout thrash.
        // Only translateY moves a card's top edge (scale uses a top origin),
        // and covered cards only move up, so coverage maths stays correct.
        const tops = kids.map((k) => k.getBoundingClientRect().top);
        const heights = kids.map((k) => k.offsetHeight);

        const depths = kids.map((_, i) => {
            let d = 0;
            for (let j = i + 1; j < Math.min(kids.length, i + 6); j++) {
                const cover = (stickTop + heights[i] - tops[j]) / Math.max(heights[i], 1);
                if (cover <= 0) break;
                d += Math.min(1, cover);
            }
            return d;
        });

        kids.forEach((el, i) => {
            const d = Math.round(depths[i] * 1000) / 1000;
            if (el.dataset.depth === String(d)) return;
            el.dataset.depth = d;

            if (d >= 3.6) {
                el.classList.add("is-buried");
                return;
            }
            el.classList.remove("is-buried");

            const tilt = (i % 2 ? 1 : -1) * Math.min(d, 2) * 0.7;
            el.style.transform = d > 0.001
                ? `translateY(${(-d * 10).toFixed(2)}px) scale(${(1 - d * 0.05).toFixed(4)}) rotate(${tilt.toFixed(2)}deg)`
                : "";
            el.style.setProperty("--dim", Math.min(d * 0.2, 0.6).toFixed(3));

            const stuck = Math.abs(tops[i] - stickTop) < 2 || tops[i] < stickTop;
            el.classList.toggle("is-front", stuck && d < 0.35);
        });
    }
}

window.addEventListener("scroll", scheduleStack, { passive: true });
window.addEventListener("resize", scheduleStack);
stackMQ.addEventListener?.("change", scheduleStack);

/* ---------------------------------------------------------
   IMPRESSIONS (marks cards as seen after ~1s on screen)
--------------------------------------------------------- */
const impressionTimers = new Map();

const impressionObserver = "IntersectionObserver" in window && new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
        const key = entry.target.dataset.key;
        if (entry.isIntersecting) {
            impressionTimers.set(key, setTimeout(() => markSeen(getItem(key)), 1100));
        } else {
            clearTimeout(impressionTimers.get(key));
            impressionTimers.delete(key);
        }
    });
}, { threshold: 0.6 });

function observeCards(root) {
    if (!impressionObserver) return;
    $$(".card[data-key]:not([data-observed])", root).forEach((el) => {
        el.dataset.observed = "1";
        impressionObserver.observe(el);
    });
}

/* ---------------------------------------------------------
   STATE
--------------------------------------------------------- */
const state = {
    view: null,
    topic: "",
    bd: { source: "", sort: "latest" },
    pal: { source: "", lang: "" },
    lib: "saved",
    ready: false,
};

/* ---------------------------------------------------------
   FOR YOU
--------------------------------------------------------- */
function greeting() {
    const h = new Date().getHours();
    return h < 5 ? "Up late" : h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
}

function renderHello() {
    $("#hello-date").textContent = new Date().toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" });
    $("#hello-title").innerHTML = `${greeting()}, <em>here's your feed</em>`;

    const fresh = DATA.all.filter(isNew).length;
    $("#hello-sub").innerHTML = fresh
        ? `<b>${fresh} new ${fresh === 1 ? "story" : "stories"}</b> since your last visit · ${DATA.all.length} in the last 24 hours, ranked for you.`
        : `${DATA.all.length || "All the"} stories from the last 24 hours, ranked for you.`;
}

function renderTopicRow() {
    const topics = DATA.trending.slice(0, 10);
    $("#topic-row").innerHTML = (state.topic ? `<button class="chip" type="button" data-topic="">✕ Clear</button>` : "") +
        topics.map((t, i) => `<button class="topic${i < 3 ? " hot" : ""}" type="button" data-topic="${esc(t.token)}" aria-pressed="${state.topic === t.token}">${esc(label(t.token))} <small>${t.items.length}</small></button>`).join("");
}

function renderForYou() {
    renderHello();
    renderStories();
    renderTopicRow();
    renderOnboarding();

    if (!state.ready) {
        $("#feed").innerHTML = skeletonHTML(4, 360);
        return;
    }

    let items = DATA.all;
    if (state.topic) items = items.filter((i) => i.tokens.includes(state.topic));

    const ranked = rank(items);
    const videos = rank(DATA.videos).map((r) => r.item);
    const topics = DATA.trending.filter((t) => t.token !== state.topic);

    // Plan the feed: cards with modules woven in, like a social feed.
    const plan = [];
    const whyCount = new Map();
    let shelfUsed = 0, devUsed = 0;
    ranked.forEach((r, idx) => {
        // Keep the "why" labels varied: each reason shows at most twice.
        if (r.why) {
            const n = (whyCount.get(r.why.text) || 0) + 1;
            whyCount.set(r.why.text, n);
            if (n > 2) r = { ...r, why: null };
        }
        if (idx === 5 && videos.length && !state.topic) plan.push({ type: "shelf", videos: videos.slice(0, 10) });
        if ((idx === 12 || idx === 30) && topics[devUsed] && !state.topic) plan.push({ type: "dev", topic: topics[devUsed++] });
        if (idx === 22 && videos.length > 10 && !state.topic && !shelfUsed++) plan.push({ type: "shelf", videos: videos.slice(10, 20) });
        plan.push({ type: "card", r, wide: r.item.image && (idx === 0 || idx % 9 === 0) && r.item.kind !== "video" });
    });

    $("#caught-up").hidden = true;

    if (!plan.length) {
        $("#feed").innerHTML = emptyHTML("Nothing here yet", state.topic ? "No stories on this topic right now." : "Fresh stories will appear soon.");
        return;
    }

    setPager("feed", {
        container: "#feed",
        entries: plan,
        size: CONFIG.PAGE,
        render: (e, i) => {
            if (e.type === "shelf") return shelfModuleHTML(e.videos);
            if (e.type === "dev") return developingHTML(e.topic);
            return cardHTML(e.r.item, { variant: e.wide ? "wide" : "", why: e.r.why, i, dismiss: true });
        },
        isCard: (e) => e.type === "card",
        onEnd: () => { $("#caught-up").hidden = false; },
    });
}

/* ---------------------------------------------------------
   ONBOARDING
--------------------------------------------------------- */
const onboardPicks = new Set();

function renderOnboarding() {
    const show = state.ready && !P.onboarded && P.history.length === 0;
    $("#onboard").hidden = !show;
    if (!show) return;

    const options = [
        { id: "region:bd", text: "Bangladesh" },
        { id: "region:pal", text: "Palestine" },
        { id: "kind:video", text: "Videos & Shorts" },
        ...DATA.trending.slice(0, 7).map((t) => ({ id: `kw:${t.token}`, text: `#${label(t.token)}` })),
    ];
    $("#onboard-chips").innerHTML = options.map((o) =>
        `<button type="button" data-onboard="${esc(o.id)}" aria-pressed="${onboardPicks.has(o.id)}">${esc(o.text)}</button>`).join("");
}

function finishOnboarding() {
    for (const pick of onboardPicks) {
        const [type, value] = pick.split(":");
        if (type === "region") bump(P.region, value, 8);
        if (type === "kind") bump(P.kind, value, 8);
        if (type === "kw") bump(P.kw, value, 6);
    }
    P.onboarded = true;
    saveProfile();
    renderInterests();
    renderForYou();
    toast(onboardPicks.size ? "Your feed is ready. It keeps learning as you read." : "Got it. Your feed will learn as you read.");
}

/* ---------------------------------------------------------
   STORIES BAR + VIEWER
--------------------------------------------------------- */
let storyGroups = [];

function buildStoryGroups() {
    const groups = new Map();
    for (const it of DATA.articles) {
        if (!groups.has(it.source)) groups.set(it.source, []);
        groups.get(it.source).push(it);
    }
    return [...groups.entries()].map(([source, items]) => {
        items.sort((a, b) => b.ts - a.ts);
        const list = items.slice(0, 8);
        const unseen = list.some((i) => !P.seen[i.key]);
        const rankScore = (unseen ? 100 : 0) + (P.src[source] || 0) * 2 + Math.exp(-hoursAgo(list[0]) / 6) * 10;
        return { source, items: list, unseen, rankScore };
    }).sort((a, b) => b.rankScore - a.rankScore).slice(0, 18);
}

function renderStories() {
    if (!state.ready) {
        $("#stories").innerHTML = Array.from({ length: 7 }, () => `<div class="story-bubble"><span class="story-ring skeleton"></span></div>`).join("");
        return;
    }
    storyGroups = buildStoryGroups();
    $("#stories").innerHTML = storyGroups.map((g, gi) => {
        const cover = g.items.find((i) => i.image);
        return `
            <button class="story-bubble${g.unseen ? "" : " seen"}" type="button" data-story="${gi}" aria-label="${esc(g.source)} stories">
                <span class="story-ring">
                    ${avatarHTML(g.source)}
                    ${cover ? `<img src="${esc(safeUrl(cover.image))}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.remove()">` : ""}
                    ${hoursAgo(g.items[0]) < 1 ? `<span class="live-tag">NEW</span>` : ""}
                </span>
                <span class="name">${esc(g.source)}</span>
            </button>`;
    }).join("");
}

const sv = { gi: 0, ii: 0, elapsed: 0, last: 0, paused: false, raf: 0, held: false, holdTimer: 0, downY: 0 };
const storyDlg = $("#story-viewer");

function openStory(gi) {
    sv.gi = gi;
    const g = storyGroups[gi];
    sv.ii = Math.max(0, g.items.findIndex((i) => !P.seen[i.key]));
    storyDlg.showModal();
    showStory();
}

function showStory() {
    const g = storyGroups[sv.gi];
    const it = g?.items[sv.ii];
    if (!it) return closeStory();

    $("#story-bars").innerHTML = g.items.map((_, i) => `<i class="${i < sv.ii ? "done" : ""}"><b></b></i>`).join("");
    const av = $("#story-avatar");
    av.style.setProperty("--h", hue(g.source));
    av.textContent = initials(g.source);
    $("#story-source").textContent = g.source;
    $("#story-time").textContent = timeAgo(it.ts);
    $("#story-title").textContent = it.title;
    $("#story-dek").textContent = it.description;
    const link = $("#story-link");
    link.href = safeUrl(it.url);
    link.dataset.open = it.key;

    const media = $("#story-media");
    media.classList.toggle("no-img", !it.image);
    media.style.backgroundImage = it.image ? `url("${safeUrl(it.image).replace(/"/g, "%22")}")` : "";

    markSeen(it);
    learn(it, 0.25);

    sv.elapsed = 0;
    sv.last = performance.now();
    cancelAnimationFrame(sv.raf);
    sv.raf = requestAnimationFrame(storyTick);
}

function storyTick(t) {
    if (!storyDlg.open) return;
    if (!sv.paused) sv.elapsed += t - sv.last;
    sv.last = t;
    const bar = $("#story-bars").children[sv.ii]?.firstElementChild;
    if (bar) bar.style.width = `${Math.min(100, (sv.elapsed / CONFIG.STORY_MS) * 100)}%`;
    if (sv.elapsed >= CONFIG.STORY_MS) return storyNext();
    sv.raf = requestAnimationFrame(storyTick);
}

function storyNext() {
    const g = storyGroups[sv.gi];
    if (sv.ii < g.items.length - 1) sv.ii++;
    else if (sv.gi < storyGroups.length - 1) {
        sv.gi++;
        sv.ii = 0;
        replayAnim($("#story-frame"), "slide-in");
    } else return closeStory();
    showStory();
}

function storyPrev() {
    if (sv.ii > 0) sv.ii--;
    else if (sv.gi > 0) { sv.gi--; sv.ii = 0; }
    showStory();
}

function closeStory() {
    cancelAnimationFrame(sv.raf);
    if (storyDlg.open) storyDlg.close();
}

function replayAnim(el, cls) {
    el.classList.remove(cls);
    void el.offsetWidth;
    el.classList.add(cls);
}

storyDlg.addEventListener("close", () => {
    cancelAnimationFrame(sv.raf);
    if (state.view === "foryou") renderStories();
});

$("#story-next").addEventListener("click", () => { if (!sv.held) storyNext(); });
$("#story-prev").addEventListener("click", () => { if (!sv.held) storyPrev(); });

const frame = $("#story-frame");
frame.addEventListener("pointerdown", (e) => {
    if (e.target.closest("a, .story-close")) return;
    sv.held = false;
    sv.downY = e.clientY;
    sv.holdTimer = setTimeout(() => { sv.held = true; sv.paused = true; }, 220);
});
frame.addEventListener("pointerup", (e) => {
    clearTimeout(sv.holdTimer);
    sv.paused = false;
    if (e.clientY - sv.downY > 90) closeStory();
    setTimeout(() => { sv.held = false; }, 0);
});
frame.addEventListener("pointercancel", () => { clearTimeout(sv.holdTimer); sv.paused = false; });

/* ---------------------------------------------------------
   YOUTUBE PLAYER
--------------------------------------------------------- */
let ytPromise = null;

function loadYT() {
    if (window.YT?.Player) return Promise.resolve(window.YT);
    if (ytPromise) return ytPromise;
    ytPromise = new Promise((resolve, reject) => {
        const prev = window.onYouTubeIframeAPIReady;
        window.onYouTubeIframeAPIReady = () => { prev?.(); resolve(window.YT); };
        const s = document.createElement("script");
        s.src = "https://www.youtube.com/iframe_api";
        s.async = true;
        s.onerror = () => { ytPromise = null; reject(new Error("YouTube API blocked")); };
        document.head.appendChild(s);
        setTimeout(() => reject(new Error("YouTube API timeout")), 8000);
    });
    return ytPromise;
}

function fallbackIframe(el, videoId) {
    const iframe = document.createElement("iframe");
    iframe.src = `https://www.youtube-nocookie.com/embed/${videoId}?autoplay=1&playsinline=1&rel=0`;
    iframe.allow = "autoplay; encrypted-media; picture-in-picture; fullscreen";
    iframe.allowFullscreen = true;
    iframe.title = "Video";
    el.replaceWith(iframe);
    return null;
}

async function makePlayer(el, videoId, events = {}) {
    try {
        const YT = await loadYT();
        if (!el.isConnected) return null;
        return new YT.Player(el, {
            host: "https://www.youtube-nocookie.com",
            videoId,
            playerVars: { autoplay: 1, playsinline: 1, rel: 0, modestbranding: 1, origin: location.origin },
            events,
        });
    } catch {
        return el.isConnected ? fallbackIframe(el, videoId) : null;
    }
}

/* ---------------------------------------------------------
   WATCH (video modal with Up next)
--------------------------------------------------------- */
const watchDlg = $("#watch");
const watch = { item: null, player: null, queue: [], countdown: 0, token: 0 };

function relatedVideos(item) {
    const tokens = new Set(item.tokens);
    const trendSet = new Set(DATA.trending.slice(0, 8).map((t) => t.token));
    return DATA.videos
        .filter((v) => v.key !== item.key && !P.hidden[v.key])
        .map((v) => {
            const overlap = v.tokens.filter((t) => tokens.has(t)).length;
            const base = scoreItem(v, trendSet).score;
            return { v, s: base + overlap * 0.8 + (v.source === item.source ? 0.4 : 0) - (P.read[v.key] ? 2 : 0) };
        })
        .sort((a, b) => b.s - a.s)
        .slice(0, 14)
        .map((x) => x.v);
}

function openWatch(item) {
    if (!item?.video_id) return;
    watch.item = item;
    watch.queue = relatedVideos(item);
    clearInterval(watch.countdown);
    $("#up-next-overlay").hidden = true;

    $("#watch-kicker").innerHTML = `${avatarHTML(item.source)}<span class="src">${esc(item.source)}</span><time>${timeAgo(item.ts)}</time>`;
    $("#watch-title").textContent = item.title;
    $("#watch-dek").textContent = item.description;
    const isSaved = saved.some((s) => s.key === item.key);
    $("#watch-actions").innerHTML = `
        <button class="btn ghost" type="button" data-save="${esc(item.key)}" aria-pressed="${isSaved}">${I.bookmark} Save</button>
        <button class="btn ghost" type="button" data-share="${esc(item.key)}">${I.share} Share</button>
        <a class="btn ghost" href="${esc(safeUrl(item.url))}" target="_blank" rel="noopener noreferrer">YouTube ↗</a>`;
    $$("#watch-actions svg").forEach((s) => { s.style.width = "16px"; s.style.height = "16px"; });

    $("#watch-next-list").innerHTML = watch.queue.map((v) => `
        <button class="next-item" type="button" data-next="${esc(v.key)}">
            <span class="thumb"><img src="https://i.ytimg.com/vi/${esc(v.video_id)}/mqdefault.jpg" alt="" loading="lazy"></span>
            <span><b>${esc(v.title)}</b><small>${esc(v.source)} · ${timeAgo(v.ts)}</small></span>
        </button>`).join("") || `<p class="hello-sub">More videos will appear here as they're published.</p>`;

    if (!watchDlg.open) watchDlg.showModal();
    watchDlg.scrollTop = 0;

    mountWatchPlayer(item);
    markRead(item);
    learn(item, 2.5);
}

function destroyWatchPlayer() {
    watch.token++;
    try { watch.player?.destroy?.(); } catch { /* already gone */ }
    watch.player = null;
    $("#watch-player").innerHTML = "";
}

function mountWatchPlayer(item) {
    destroyWatchPlayer();
    const token = watch.token;
    const host = document.createElement("div");
    $("#watch-player").appendChild(host);
    makePlayer(host, item.video_id, {
        onStateChange: (e) => { if (e.data === 0) onWatchEnded(); },
    }).then((p) => {
        if (token !== watch.token) { try { p?.destroy?.(); } catch { } return; }
        watch.player = p;
    });
}

function onWatchEnded() {
    learn(watch.item, 2);
    const next = watch.queue[0];
    if (!next || !$("#autoplay-toggle").checked) return;

    let n = 5;
    $("#up-next-title").textContent = next.title;
    $("#up-next-count").textContent = n;
    $("#up-next-overlay").hidden = false;
    clearInterval(watch.countdown);
    watch.countdown = setInterval(() => {
        n--;
        $("#up-next-count").textContent = n;
        if (n <= 0) {
            clearInterval(watch.countdown);
            openWatch(next);
        }
    }, 1000);
}

$("#up-next-play").addEventListener("click", () => { clearInterval(watch.countdown); if (watch.queue[0]) openWatch(watch.queue[0]); });
$("#up-next-cancel").addEventListener("click", () => { clearInterval(watch.countdown); $("#up-next-overlay").hidden = true; });
watchDlg.addEventListener("close", () => { clearInterval(watch.countdown); destroyWatchPlayer(); });
watchDlg.addEventListener("click", (e) => { if (e.target === watchDlg) watchDlg.close(); });

/* ---------------------------------------------------------
   SHORTS (vertical swipe feed)
--------------------------------------------------------- */
const shorts = { list: [], active: -1, player: null, token: 0, since: 0, progress: 0, observer: null };

function renderShorts(startId) {
    deactivateShort();
    const box = $("#shorts");

    if (!DATA.videos.length) {
        box.innerHTML = `<div class="short"><div class="empty" style="color:#bbb;border-color:#333">${state.ready ? "<b style='color:#fff'>No videos yet</b>New videos are added throughout the day." : "<b style='color:#fff'>Loading videos…</b>"}</div></div>`;
        return;
    }

    const ranked = rank(DATA.videos).map((r) => r.item);
    const startIdx = startId ? ranked.findIndex((v) => v.video_id === startId) : -1;
    if (startIdx > 0) ranked.unshift(...ranked.splice(startIdx, 1));
    shorts.list = ranked;

    box.innerHTML = ranked.map((v, i) => {
        const isSaved = saved.some((s) => s.key === v.key);
        const thumb = `https://i.ytimg.com/vi/${v.video_id}/hqdefault.jpg`;
        return `
            <div class="short${v.isShort ? " is-vertical" : ""}" data-i="${i}" data-key="${esc(v.key)}">
                <div class="short-bg" style="background-image:url('${thumb}')"></div>
                <div class="short-frame">
                    <div class="short-stage">
                        <img src="${thumb}" alt="" loading="${i < 2 ? "eager" : "lazy"}">
                        <button class="start" type="button" data-short-start="${i}" aria-label="Play">${`<span>${I.play}</span>`}</button>
                    </div>
                    <div class="short-info">
                        <div class="who">${avatarHTML(v.source)}${esc(v.source)} <time>${timeAgo(v.ts)}</time></div>
                        <h3>${esc(v.title)}</h3>
                    </div>
                    <div class="short-actions">
                        <button type="button" data-save="${esc(v.key)}" aria-pressed="${isSaved}"><span class="circle">${I.bookmark}</span>Save</button>
                        <button type="button" data-share="${esc(v.key)}"><span class="circle">${I.share}</span>Share</button>
                        <a href="${esc(safeUrl(v.url))}" target="_blank" rel="noopener noreferrer"><span class="circle">${I.yt}</span>YouTube</a>
                        <button type="button" data-hide="${esc(v.key)}"><span class="circle">${I.thumbDown}</span>Less</button>
                    </div>
                    <div class="short-progress"><i></i></div>
                </div>
                ${i === 0 && !P.hintShorts ? `<div class="shorts-hint">${I.up}Swipe up for more</div>` : ""}
            </div>`;
    }).join("") + `<div class="shorts-nav"><button class="icon-btn" type="button" data-shorts-step="-1" aria-label="Previous video">${I.up}</button><button class="icon-btn" type="button" data-shorts-step="1" aria-label="Next video">${I.down}</button></div>`;

    box.scrollTop = 0;

    shorts.observer?.disconnect();
    shorts.observer = new IntersectionObserver((entries) => {
        entries.forEach((entry) => {
            if (entry.isIntersecting && entry.intersectionRatio >= 0.6) activateShort(Number(entry.target.dataset.i));
        });
    }, { root: box, threshold: [0.6] });
    $$(".short", box).forEach((el) => shorts.observer.observe(el));
    box.focus({ preventScroll: true });
}

function activateShort(i) {
    if (i === shorts.active || state.view !== "shorts") return;
    deactivateShort();
    shorts.active = i;
    shorts.since = Date.now();
    const item = shorts.list[i];
    const slide = $(`.short[data-i="${i}"]`);
    if (!item || !slide) return;

    if (i > 0 && !P.hintShorts) { P.hintShorts = true; saveProfile(); }
    markSeen(item);

    const stage = $(".short-stage", slide);
    const host = document.createElement("div");
    host.className = "yt-host";
    stage.appendChild(host);
    $(".start", stage).hidden = true;

    const token = ++shorts.token;
    makePlayer(host, item.video_id, {
        onReady: (e) => {
            e.target.playVideo();
            // Browsers may block autoplay with sound; fall back to muted playback.
            setTimeout(() => {
                try {
                    if (token === shorts.token && ![1, 3].includes(e.target.getPlayerState())) {
                        e.target.mute();
                        e.target.playVideo();
                    }
                } catch { /* player gone */ }
            }, 1500);
        },
        onStateChange: (e) => { if (e.data === 0) stepShort(1); },
    }).then((p) => {
        if (token !== shorts.token) { try { p?.destroy?.(); } catch { } return; }
        shorts.player = p;
    });

    const bar = $(".short-progress i", slide);
    clearInterval(shorts.progress);
    shorts.progress = setInterval(() => {
        try {
            const d = shorts.player?.getDuration?.();
            if (d) bar.style.width = `${(shorts.player.getCurrentTime() / d) * 100}%`;
        } catch { /* not ready */ }
    }, 300);
}

function deactivateShort() {
    clearInterval(shorts.progress);
    if (shorts.active >= 0) {
        const item = shorts.list[shorts.active];
        const dwell = Date.now() - shorts.since;
        if (item) learn(item, dwell < 2500 ? -0.4 : dwell > 10000 ? 1.5 : 0.3);
        const slide = $(`.short[data-i="${shorts.active}"]`);
        if (slide) {
            $$(".yt-host, iframe", slide).forEach((n) => n.remove());
            const start = $(".start", slide);
            if (start) start.hidden = false;
        }
    }
    shorts.token++;
    try { shorts.player?.destroy?.(); } catch { /* already gone */ }
    shorts.player = null;
    shorts.active = -1;
}

function stepShort(dir) {
    const next = $(`.short[data-i="${Math.max(0, shorts.active + dir)}"]`);
    next?.scrollIntoView({ behavior: "smooth", block: "start" });
}

/* ---------------------------------------------------------
   BANGLADESH
--------------------------------------------------------- */
function renderBangladesh() {
    const all = DATA.bd;

    if (!state.ready) {
        $("#bd-lead").innerHTML = `<div class="lead-grid"><div class="skeleton" style="height:440px"></div><div class="side-list">${skeletonHTML(4, 110)}</div></div>`;
        return;
    }

    $("#bd-total").textContent = all.length;
    $("#bd-sources").textContent = new Set(all.map((i) => i.source)).size;
    $("#bd-hour").textContent = all.filter((i) => hoursAgo(i) <= 1).length;

    const counts = countBy(all, (i) => i.source);
    $("#bd-chips").innerHTML = chipsHTML([{ value: "", text: "All papers", count: all.length },
    ...counts.map(([s, c]) => ({ value: s, text: s, count: c }))], state.bd.source, "data-bd-source");
    $$("[data-bd-sort]").forEach((b) => b.setAttribute("aria-pressed", b.dataset.bdSort === state.bd.sort));

    let list = all.filter((i) => !state.bd.source || i.source === state.bd.source);
    list = state.bd.sort === "foryou" ? rank(list).map((r) => r.item) : [...list].sort((a, b) => b.ts - a.ts);

    if (!list.length) {
        $("#bd-lead").innerHTML = "";
        $("#bd-grid").innerHTML = emptyHTML("No stories right now", "Bangladesh headlines from the last 24 hours will appear here.");
        return;
    }

    $("#bd-lead").innerHTML = leadHTML(list.slice(0, 5));
    observeCards($("#bd-lead"));
    setPager("bd", { container: "#bd-grid", entries: list.slice(5), size: CONFIG.GRID_PAGE, render: (it, i) => cardHTML(it, { i }) });
}

/* ---------------------------------------------------------
   PALESTINE
--------------------------------------------------------- */
function renderPalestine() {
    if (!DATA.pal) {
        $("#pal-lead").innerHTML = `<div class="lead-grid"><div class="skeleton" style="height:440px"></div><div class="side-list">${skeletonHTML(4, 110)}</div></div>`;
        $("#pal-shelf").innerHTML = Array.from({ length: 6 }, () => `<div class="skeleton" style="aspect-ratio:9/16"></div>`).join("");
        return;
    }

    const { articles, videos, raw } = DATA.pal;
    $$(".band-pal").forEach((b) => sizeFlag(b, true));
    const live = (raw.sources || []).filter((s) => s.ok && s.count > 0);

    $("#pal-updated").textContent = timeAgo(Date.parse(raw.updated_at)) || "now";
    $("#pal-articles").textContent = articles.length;
    $("#pal-videos").textContent = videos.length;
    $("#pal-sources").textContent = new Set(live.map((s) => s.name)).size;

    $("#pal-lang").hidden = !articles.some((a) => a.lang === "bn");
    $$("[data-pal-lang]").forEach((b) => b.setAttribute("aria-pressed", b.dataset.palLang === state.pal.lang));

    const counts = countBy(articles, (i) => i.source);
    $("#pal-chips").innerHTML = chipsHTML([{ value: "", text: "All outlets", count: articles.length },
    ...counts.map(([s, c]) => ({ value: s, text: s, count: c }))], state.pal.source, "data-pal-source");

    const list = articles
        .filter((a) => (!state.pal.source || a.source === state.pal.source) && (!state.pal.lang || a.lang === state.pal.lang))
        .sort((a, b) => b.ts - a.ts);

    const leadCount = state.pal.source || state.pal.lang ? 0 : 5;
    $("#pal-lead").innerHTML = leadCount ? leadHTML(list.slice(0, leadCount)) : "";
    observeCards($("#pal-lead"));
    $("#pal-count").textContent = `${list.length} reports`;

    $("#pal-watch-h").hidden = !videos.length;
    $("#pal-shelf").innerHTML = rank(videos).slice(0, 14).map((r) => shortTileHTML(r.item)).join("");

    if (!list.length) $("#pal-grid").innerHTML = emptyHTML("No matching reports", "Try another outlet.");
    else setPager("pal", { container: "#pal-grid", entries: list.slice(leadCount), size: CONFIG.GRID_PAGE, render: (it, i) => cardHTML(it, { i }) });

    const sources = raw.sources || [];
    $("#pal-sources-summary").textContent = `${sources.filter((s) => s.ok).length}/${sources.length} feeds live`;
    $("#pal-sources-body").innerHTML = sources.map((s) => `
        <tr>
            <td><span class="status-dot${s.ok ? "" : " off"}"></span><a href="${esc(safeUrl(s.site))}" target="_blank" rel="noopener noreferrer">${esc(s.name)}</a></td>
            <td>${s.kind === "video" ? "YouTube" : "News"} · ${s.lang === "bn" ? "বাংলা" : "EN"}</td>
            <td class="hide-xs"><a href="${esc(safeUrl(s.feed))}" target="_blank" rel="noopener noreferrer">RSS ↗</a></td>
            <td>${s.ok ? s.count : "offline"}</td>
        </tr>`).join("");
}

/* ---------------------------------------------------------
   LIBRARY
--------------------------------------------------------- */
function renderLibrary() {
    $$("[data-lib]").forEach((b) => b.setAttribute("aria-pressed", b.dataset.lib === state.lib));
    const list = state.lib === "saved" ? saved : P.history;
    const decks = [];
    for (let i = 0; i < list.length; i += DECK_SIZE) {
        decks.push(`<div class="deck">${list.slice(i, i + DECK_SIZE).map((it, j) => cardHTML(it, { i: i + j })).join("")}</div>`);
    }
    $("#lib-grid").innerHTML = list.length
        ? decks.join("")
        : state.lib === "saved"
            ? emptyHTML("Nothing saved yet", "Tap the bookmark on any story or video to keep it here, even after it leaves the live feed.")
            : emptyHTML("No history yet", "Stories you open and videos you watch will show up here.");
}

/* ---------------------------------------------------------
   SIDEBARS, TICKER, INTERESTS, LIVE PILL
--------------------------------------------------------- */
function renderSide() {
    $("#trend-list").innerHTML = DATA.trending.slice(0, 7).map((t) =>
        `<li><button type="button" data-topic="${esc(t.token)}"><b>#${esc(label(t.token))}</b><small>${t.items.length} stories · ${t.sources.size} outlets</small></button></li>`
    ).join("") || `<li><small>Trending topics appear as news comes in.</small></li>`;

    const recent = DATA.all.filter((i) => hoursAgo(i) <= 3);
    $("#active-list").innerHTML = countBy(recent, (i) => i.source).slice(0, 6).map(([s, c]) =>
        `<div class="active-row">${avatarHTML(s)}<span>${esc(s)}</span><small>${c} in 3h</small></div>`
    ).join("") || `<small class="hello-sub">Quiet right now.</small>`;
}

function shortAgo(ts) {
    return timeAgo(ts).replace(" ago", "").replace("just now", "now");
}

function renderTicker() {
    const items = (DATA.pal?.articles || []).slice(0, 14);
    if (!items.length) return;
    const html = items.map((i) => `
        <a href="${esc(safeUrl(i.url))}" target="_blank" rel="noopener noreferrer" data-open="${esc(i.key)}">
            <time>${esc(shortAgo(i.ts))}</time><b>${esc(i.source)}</b><span>${esc(i.title)}</span>
        </a>`).join("");
    const track = $("#ticker-items");
    // Duplicated once so the -50% marquee loops seamlessly; the copy is hidden from screen readers.
    track.innerHTML = html + html.replaceAll("<a ", `<a tabindex="-1" aria-hidden="true" `);
    track.style.setProperty("--ticker-duration", `${items.length * 8}s`);
    $("#ticker").hidden = false;
}

$("#ticker-toggle").addEventListener("click", (e) => {
    const paused = $("#ticker").classList.toggle("paused");
    e.currentTarget.setAttribute("aria-pressed", paused);
    e.currentTarget.setAttribute("aria-label", paused ? "Play headlines" : "Pause headlines");
});

function renderInterests() {
    const trendTokens = new Set(DATA.trending.map((t) => t.token));
    const topics = Object.entries(P.kw).filter(([k, v]) => v > 0.8 && !HIDDEN_TOPICS.has(k) && (trendTokens.has(k) || /^\p{Lu}/u.test(label(k)))).sort((a, b) => b[1] - a[1]).slice(0, 4).map(([k, v]) => ({ k, v, t: `#${label(k)}`, topic: k }));
    const srcs = Object.entries(P.src).filter(([, v]) => v > 1).sort((a, b) => b[1] - a[1]).slice(0, 3).map(([k, v]) => ({ k, v, t: k }));
    const list = [...topics, ...srcs].sort((a, b) => b.v - a.v);
    $("#rail-interests").hidden = !list.length;
    if (!list.length) return;
    const max = list[0].v;
    $("#interest-list").innerHTML = list.map((x) => `
        <button class="interest" type="button" ${x.topic ? `data-topic="${esc(x.topic)}"` : ""}>
            <span>${esc(x.t)}</span><small>${Math.round((x.v / max) * 100)}%</small>
            <span class="bar"><i style="width:${Math.max(8, (x.v / max) * 100)}%"></i></span>
        </button>`).join("");
}

function updateLive() {
    const at = Math.max(DATA.todayAt, DATA.palAt);
    $("#live-text").textContent = at ? `Live · ${timeAgo(at)}` : "Live";
}

function updateBadges() {
    const n = (DATA.pal?.articles || []).filter(isNew).length;
    $$('[data-badge="palestine"]').forEach((b) => { b.hidden = !n; b.textContent = n > 99 ? "99+" : n; });
}

/* ---------------------------------------------------------
   NAV + ROUTER
--------------------------------------------------------- */
const NAV = [
    { view: "foryou", href: "#/", text: "For You", icon: I.home },
    { view: "bangladesh", href: "#/bangladesh", text: "Bangladesh", icon: `<img class="nav-flag" src="/static/flag-bangladesh.webp" alt="" width="42" height="24">` },
    { view: "palestine", href: "#/palestine", text: "Palestine", icon: `<img class="nav-flag" src="/static/flag-palestine.webp" alt="" width="42" height="24">` },
    { view: "shorts", href: "#/shorts", text: "Shorts", icon: I.shorts },
    { view: "saved", href: "#/saved", text: "Library", icon: I.lib },
];

$$("[data-nav]").forEach((nav) => {
    nav.innerHTML = NAV.map((n) => `<a class="nav-item" href="${n.href}" data-view="${n.view}">${n.icon}<span>${n.text}</span>${n.view === "palestine" ? `<span class="badge-count" data-badge="palestine" hidden></span>` : ""}</a>`).join("");
});

function parseRoute() {
    const [view, arg] = location.hash.replace(/^#\/?/, "").split("/");
    return { view: NAV.some((n) => n.view === view) ? view : "foryou", arg };
}

function renderView(view, arg) {
    if (view === "foryou") renderForYou();
    if (view === "bangladesh") renderBangladesh();
    if (view === "palestine") renderPalestine();
    if (view === "shorts") renderShorts(arg);
    if (view === "saved") renderLibrary();
}

function route() {
    const { view, arg } = parseRoute();
    const changed = view !== state.view;

    const swap = () => {
        if (state.view === "shorts" && view !== "shorts") deactivateShort();
        state.view = view;
        document.body.dataset.view = view;
        $$(".view").forEach((v) => { v.hidden = v.dataset.view !== view; });
        $$(".nav-item").forEach((a) => a.toggleAttribute("aria-current", a.dataset.view === view));
        $$(".nav-item[aria-current]").forEach((a) => a.setAttribute("aria-current", "page"));
        renderView(view, arg);
        scheduleStack();
        document.title = {
            foryou: "News — Your live feed",
            bangladesh: "Bangladesh — News",
            palestine: "Palestine today — News",
            shorts: "Shorts — News",
            saved: "Library — News",
        }[view];
    };

    if (changed && state.view !== null) {
        withTransition(swap);
        window.scrollTo({ top: 0 });
    } else swap();
}

window.addEventListener("hashchange", route);

function goTopic(token) {
    state.topic = token;
    if (state.view !== "foryou") location.hash = "#/";
    else renderForYou();
    window.scrollTo({ top: 0, behavior: "smooth" });
}

/* ---------------------------------------------------------
   SAVE / SHARE / HIDE
--------------------------------------------------------- */
function toggleSave(key) {
    const idx = saved.findIndex((s) => s.key === key);
    const item = getItem(key);
    if (idx >= 0) saved.splice(idx, 1);
    else if (item) {
        saved.unshift(slim(item));
        learn(item, 4);
    }
    store.set("bn-saved-v2", saved);

    const on = idx < 0;
    $$(`[data-save="${CSS.escape(key)}"]`).forEach((b) => {
        b.setAttribute("aria-pressed", on);
        if (b.classList.contains("mini-btn")) replayAnim(b, "pop");
    });
    toast(on ? "Saved to your library" : "Removed from library", on ? { text: "View", run: () => { location.hash = "#/saved"; } } : null);
    if (state.view === "saved") { renderLibrary(); scheduleStack(); }
}

async function share(key) {
    const item = getItem(key);
    if (!item) return;
    learn(item, 2);
    try {
        if (navigator.share) await navigator.share({ title: item.title, url: item.url });
        else {
            await navigator.clipboard.writeText(item.url);
            toast("Link copied");
        }
    } catch { /* cancelled */ }
}

function hideItem(key) {
    const item = getItem(key);
    if (!item) return;
    P.hidden[key] = Date.now();
    learn(item, -5);

    if (state.view === "shorts") {
        toast("You'll see fewer videos like this");
        stepShort(1);
        return;
    }

    const card = $(`#feed ${sel(key)}`);
    if (card) {
        const note = document.createElement("div");
        note.className = "dismiss-note";
        note.dataset.noteFor = key;
        note.innerHTML = `<span>Hidden. You'll see less from <b>${esc(item.source)}</b>.</span><button type="button" data-undo="${esc(key)}">Undo</button>`;
        card.replaceWith(note);
        scheduleStack();
    }
}

function undoHide(key) {
    const item = getItem(key);
    delete P.hidden[key];
    learn(item, 5);
    const note = $(`[data-note-for="${CSS.escape(key)}"]`);
    if (note && item) {
        note.insertAdjacentHTML("afterend", cardHTML(item, { dismiss: true }));
        note.remove();
        observeCards($("#feed"));
        scheduleStack();
    }
}

/* ---------------------------------------------------------
   SEARCH PALETTE
--------------------------------------------------------- */
const paletteDlg = $("#palette");
const paletteInput = $("#palette-input");
let paletteSel = 0;
let paletteItems = [];

function openPalette(q = "") {
    if (!paletteDlg.open) paletteDlg.showModal();
    paletteInput.value = q;
    renderPalette();
    paletteInput.focus();
}

function highlight(text, words) {
    let html = esc(text);
    for (const w of words) {
        if (w.length < 2) continue;
        html = html.replace(new RegExp(`(${w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})`, "gi"), "<mark>$1</mark>");
    }
    return html;
}

function renderPalette() {
    const q = paletteInput.value.trim().toLowerCase();
    const box = $("#palette-results");
    paletteSel = 0;

    if (!q) {
        paletteItems = P.history.slice(0, 6);
        box.innerHTML = `
            <div class="palette-label">Trending topics</div>
            <div class="palette-topics">${DATA.trending.slice(0, 8).map((t) => `<button class="topic" type="button" data-ptopic="${esc(label(t.token))}">${esc(label(t.token))}</button>`).join("") || "<small>Loading…</small>"}</div>
            ${paletteItems.length ? `<div class="palette-label">Recently opened</div>${paletteItems.map((it, i) => resultHTML(it, [], i)).join("")}` : ""}`;
        return;
    }

    const words = q.split(/\s+/).filter(Boolean);
    const pool = new Map([...DATA.all, ...saved].map((i) => [i.key, i]));
    paletteItems = [...pool.values()]
        .map((it) => {
            const title = it.title.toLowerCase();
            const hay = `${title} ${it.description.toLowerCase()} ${it.source.toLowerCase()}`;
            if (!words.every((w) => hay.includes(w))) return null;
            const s = words.filter((w) => title.includes(w)).length * 3 + 2 * Math.exp(-hoursAgo(it) / 24);
            return { it, s };
        })
        .filter(Boolean)
        .sort((a, b) => b.s - a.s)
        .slice(0, 40)
        .map((x) => x.it);

    box.innerHTML = paletteItems.length
        ? `<div class="palette-label">${paletteItems.length} result${paletteItems.length === 1 ? "" : "s"}</div>${paletteItems.map((it, i) => resultHTML(it, words, i)).join("")}`
        : `<div class="empty" style="margin:8px"><b>No matches</b>Try a different word.</div>`;
}

function resultHTML(it, words, i) {
    const thumb = it.kind === "video" ? `https://i.ytimg.com/vi/${it.video_id}/mqdefault.jpg` : it.image;
    return `
        <button class="result" type="button" role="option" data-result="${esc(it.key)}" aria-selected="${i === paletteSel}">
            <span class="thumb">${thumb ? `<img src="${esc(safeUrl(thumb))}" alt="" loading="lazy" referrerpolicy="no-referrer">` : ""}</span>
            <span><b>${highlight(it.title, words)}</b><small>${it.kind === "video" ? "▶ " : ""}${esc(it.source)} · ${timeAgo(it.ts)}</small></span>
        </button>`;
}

function openResult(key) {
    const item = getItem(key);
    if (!item) return;
    paletteDlg.close();
    if (item.kind === "video") openWatch(item);
    else {
        window.open(safeUrl(item.url), "_blank", "noopener");
        markRead(item);
        learn(item, 3);
    }
}

paletteInput.addEventListener("input", debounce(renderPalette, 120));
paletteInput.addEventListener("keydown", (e) => {
    const n = paletteItems.length;
    if (!n) return;
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        paletteSel = (paletteSel + (e.key === "ArrowDown" ? 1 : -1) + n) % n;
        $$(".result").forEach((r, i) => r.setAttribute("aria-selected", i === paletteSel));
        $$(".result")[paletteSel]?.scrollIntoView({ block: "nearest" });
    } else if (e.key === "Enter") {
        e.preventDefault();
        openResult(paletteItems[paletteSel].key);
    }
});
paletteDlg.addEventListener("click", (e) => { if (e.target === paletteDlg) paletteDlg.close(); });

/* ---------------------------------------------------------
   PALESTINE FLAG PROPORTIONS
   The red triangle reaches 2/3 of the flag's height into it (official
   1:2 flag, triangle = 1/3 of the length). Recomputed only when the
   width changes, so the text reflow it causes can't loop.
--------------------------------------------------------- */
const flagWidths = new WeakMap();

function sizeFlag(el, force = false) {
    const { width, height } = el.getBoundingClientRect();
    if (!width || (!force && flagWidths.get(el) === Math.round(width))) return;
    flagWidths.set(el, Math.round(width));
    const cap = width * (width < 640 ? 0.24 : 0.36);
    el.style.setProperty("--tri", `${Math.min((height * 2) / 3, cap).toFixed(1)}px`);
}

const flagObserver = "ResizeObserver" in window && new ResizeObserver((entries) => entries.forEach((e) => sizeFlag(e.target)));
$$(".band-pal").forEach((band) => flagObserver?.observe(band));
window.addEventListener("resize", debounce(() => $$(".band-pal").forEach((b) => sizeFlag(b)), 150));

/* ---------------------------------------------------------
   BACK TO TOP
--------------------------------------------------------- */
function toTop() {
    window.scrollTo({ top: 0, behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
}

const toTopBtn = $("#to-top");
const phoneMQ = matchMedia("(max-width: 639px)");
let lastScrollY = window.scrollY;

// Desktop: shown once you're far down. Phones: only while scrolling up,
// so it never sits on top of the card you're reading.
window.addEventListener("scroll", () => {
    const y = window.scrollY;
    const delta = y - lastScrollY;
    if (Math.abs(delta) < 6) return;
    lastScrollY = y;
    const far = y > innerHeight * 1.5 && state.view !== "shorts";
    toTopBtn.classList.toggle("show", far && (!phoneMQ.matches || delta < 0));
}, { passive: true });
toTopBtn.addEventListener("click", toTop);
$("#back-top").addEventListener("click", toTop);

// Tapping the tab you're already on scrolls back to the top, like native apps.
$$("[data-nav]").forEach((nav) => nav.addEventListener("click", (e) => {
    const item = e.target.closest(".nav-item");
    if (item && item.dataset.view === state.view) {
        e.preventDefault();
        toTop();
    }
}));

/* ---------------------------------------------------------
   TOAST
--------------------------------------------------------- */
let toastTimer;

function toast(text, action = null) {
    const el = $("#toast");
    $("#toast-text").textContent = text;
    const btn = $("#toast-action");
    btn.hidden = !action;
    if (action) {
        btn.textContent = action.text;
        btn.onclick = () => { action.run(); el.classList.remove("show"); };
    }
    el.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.remove("show"), 3200);
}

/* ---------------------------------------------------------
   DELEGATED EVENTS
--------------------------------------------------------- */
document.addEventListener("click", (e) => {
    const t = e.target.closest(`[data-watch],[data-open],[data-save],[data-share],[data-hide],[data-undo],[data-short],
        [data-short-start],[data-shorts-step],[data-story],[data-topic],[data-bd-source],[data-bd-sort],[data-pal-source],
        [data-pal-lang],[data-lib],[data-ptopic],[data-result],[data-onboard],[data-next],[data-close]`);
    if (!t) return;
    const d = t.dataset;

    if (d.watch !== undefined) {
        e.preventDefault();
        openWatch(getItem(d.watch));
    } else if (d.open !== undefined) {
        const item = getItem(d.open);
        markRead(item);
        learn(item, 3);
    } else if (d.save !== undefined) toggleSave(d.save);
    else if (d.share !== undefined) share(d.share);
    else if (d.hide !== undefined) hideItem(d.hide);
    else if (d.undo !== undefined) undoHide(d.undo);
    else if (d.short !== undefined) location.hash = `#/shorts/${d.short}`;
    else if (d.shortStart !== undefined) { shorts.active = -1; activateShort(Number(d.shortStart)); }
    else if (d.shortsStep !== undefined) stepShort(Number(d.shortsStep));
    else if (d.story !== undefined) openStory(Number(d.story));
    else if (d.topic !== undefined) goTopic(state.topic === d.topic ? "" : d.topic);
    else if (d.bdSource !== undefined) { state.bd.source = d.bdSource; renderBangladesh(); }
    else if (d.bdSort !== undefined) { state.bd.sort = d.bdSort; renderBangladesh(); }
    else if (d.palSource !== undefined) { state.pal.source = d.palSource; renderPalestine(); }
    else if (d.palLang !== undefined) { state.pal.lang = d.palLang; renderPalestine(); }
    else if (d.lib !== undefined) { state.lib = d.lib; renderLibrary(); }
    else if (d.ptopic !== undefined) { paletteInput.value = d.ptopic; renderPalette(); paletteInput.focus(); }
    else if (d.result !== undefined) openResult(d.result);
    else if (d.onboard !== undefined) {
        onboardPicks.has(d.onboard) ? onboardPicks.delete(d.onboard) : onboardPicks.add(d.onboard);
        t.setAttribute("aria-pressed", onboardPicks.has(d.onboard));
    } else if (d.next !== undefined) openWatch(getItem(d.next));
    else if (d.close !== undefined) t.closest("dialog")?.close();
});

$("#onboard-done").addEventListener("click", finishOnboarding);
$("#replay-feed").addEventListener("click", () => {
    P.seen = {};
    saveProfile();
    renderForYou();
    window.scrollTo({ top: 0, behavior: "smooth" });
});
$("#reset-profile").addEventListener("click", () => {
    if (!confirm("Reset your personalisation? Your saved stories are kept.")) return;
    Object.assign(P, { src: {}, kw: {}, region: {}, kind: {}, seen: {}, read: {}, hidden: {}, onboarded: false });
    onboardPicks.clear();
    saveProfile();
    renderInterests();
    if (state.view === "foryou") renderForYou();
    toast("Personalisation reset");
});
$("#search-trigger").addEventListener("click", () => openPalette());
$("#search-icon").addEventListener("click", () => openPalette());

document.addEventListener("keydown", (e) => {
    const typing = ["INPUT", "TEXTAREA"].includes(document.activeElement?.tagName);

    if ((e.key === "k" && (e.ctrlKey || e.metaKey)) || (e.key === "/" && !typing && !document.querySelector("dialog[open]"))) {
        e.preventDefault();
        openPalette();
        return;
    }
    if (storyDlg.open) {
        if (e.key === "ArrowRight") storyNext();
        if (e.key === "ArrowLeft") storyPrev();
        return;
    }
    if (state.view === "shorts" && !document.querySelector("dialog[open]") && !typing) {
        if (["ArrowDown", "j", "PageDown"].includes(e.key)) { e.preventDefault(); stepShort(1); }
        if (["ArrowUp", "k", "PageUp"].includes(e.key)) { e.preventDefault(); stepShort(-1); }
    }
});

/* ---------------------------------------------------------
   THEME
--------------------------------------------------------- */
function currentTheme() {
    return document.documentElement.dataset.theme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
}

function syncThemeColor() {
    $('meta[name="theme-color"]').setAttribute("content", currentTheme() === "dark" ? "#0D0F0C" : "#F3F0E8");
}

$("#theme-btn").addEventListener("click", () => {
    const next = currentTheme() === "dark" ? "light" : "dark";
    withTransition(() => {
        document.documentElement.dataset.theme = next;
        syncThemeColor();
    });
    store.set("bn-theme", next);
});

/* ---------------------------------------------------------
   DATA LOADING + LIVE REFRESH
--------------------------------------------------------- */
let pending = null;

function showFreshPill(count, apply) {
    pending = apply;
    $("#fresh-text").textContent = `${count} new ${count === 1 ? "story" : "stories"}`;
    $("#fresh-pill").hidden = false;
}

$("#fresh-pill").addEventListener("click", () => {
    $("#fresh-pill").hidden = true;
    pending?.();
    pending = null;
    rebuild();
    refreshAll();
    window.scrollTo({ top: 0, behavior: "smooth" });
});

function refreshAll() {
    renderSide();
    renderTicker();
    renderInterests();
    updateBadges();
    updateLive();
    renderView(state.view, parseRoute().arg);
}

async function pollToday() {
    if (document.hidden) return;
    try {
        const payload = await api("today");
        const known = new Set(DATA.bd.map((i) => i.key));
        const fresh = (payload.news || []).filter((n) => !known.has(n.url));
        if (!fresh.length) { DATA.todayAt = Date.now(); updateLive(); return; }

        // Don't reshuffle under the reader: offer the update instead.
        if (state.view === "shorts" || window.scrollY > 300) showFreshPill(fresh.length, () => setToday(payload));
        else {
            setToday(payload);
            rebuild();
            refreshAll();
        }
    } catch (error) {
        console.warn("Refresh failed", error);
    }
}

async function pollPalestine() {
    if (document.hidden) return;
    try {
        const payload = await api("palestine");
        const known = new Set((DATA.pal?.articles || []).concat(DATA.pal?.videos || []).map((i) => i.key));
        const fresh = [...(payload.articles || []), ...(payload.videos || [])].filter((n) => !known.has(n.url));
        if (!fresh.length) return;
        showFreshPill(fresh.length, () => setPalestine(payload));
    } catch (error) {
        console.warn("Palestine refresh failed", error);
    }
}

async function boot() {
    maintainProfile();

    const streak = P.streak.n;
    $("#streak").hidden = streak < 2;
    $("#streak-count").textContent = streak;
    $("#year").textContent = new Date().getFullYear();
    syncThemeColor();

    route();
    renderInterests();

    $$(".sentinel").forEach((s) => {
        s.dataset.pager = s.id.replace("-sentinel", "");
        pageObserver?.observe(s);
    });

    const today = api("today").then(setToday).catch((e) => console.error("Today API", e));
    const pal = api("palestine").then(setPalestine).catch((e) => console.error("Palestine API", e));

    // Show the feed as soon as Bangladesh news is in; Palestine joins when ready.
    await Promise.allSettled([today, withTimeout(pal, CONFIG.PAL_WAIT)]);
    state.ready = true;
    rebuild();
    refreshAll();

    pal.then(() => {
        if (!DATA.pal || DATA.all.some((i) => i.region === "pal")) return;
        if (state.view === "foryou" && window.scrollY > 300) showFreshPill(DATA.pal.articles.length, () => { });
        else { rebuild(); refreshAll(); }
    });

    setInterval(pollToday, CONFIG.TODAY_REFRESH);
    setInterval(pollPalestine, CONFIG.PAL_REFRESH);
    setInterval(updateLive, 30_000);
}

/* ---------------------------------------------------------
   PWA
--------------------------------------------------------- */
if ("serviceWorker" in navigator && (location.protocol === "https:" || location.hostname === "localhost" || location.hostname === "127.0.0.1")) {
    window.addEventListener("load", () => navigator.serviceWorker.register("/sw.js").catch(() => { }));
}

let installEvent = null;
window.addEventListener("beforeinstallprompt", (e) => {
    e.preventDefault();
    installEvent = e;
    $("#install-btn").hidden = false;
});
$("#install-btn").addEventListener("click", async () => {
    if (!installEvent) return;
    installEvent.prompt();
    await installEvent.userChoice.catch(() => { });
    installEvent = null;
    $("#install-btn").hidden = true;
});

boot();
