(() => {
  "use strict";

  // AI Signal 首页：赛道看板 / 全部动态 / 社区 三个视图共用一套 DOM 和 6 套主题。
  // body[data-skin] 切换主题，body[data-lane] 给海报主题上色。
  // 只用安全 DOM API（textContent / setAttribute），不拼接 HTML 字符串。
  const PAGE = 12;
  const SKINS = ["terminal", "editorial", "doodle", "ticker", "poster", "notebook"];
  const DEFAULT_SKIN = "editorial";
  const VIEWS = ["board", "all", "community", "privacy", "policy"];
  // 隐私说明 / 内容与版权：正文写在 index.html 的 <article>，这里只给标题。
  const DOCS = {
    privacy: { id: "doc-privacy", code: "POLICY / PRIVACY", name: "隐私说明", stat: "AI Signal 如何处理数据" },
    policy: { id: "doc-policy", code: "POLICY / CONTENT", name: "内容与版权", stat: "AI Signal 的内容来源与版权立场" },
  };
  const ROLE_LABEL = { primary: "官方", report: "媒体", signal: "热度", reference: "参考" };
  const TIER_LABEL = { 1: "一级·官方", 2: "二级", 3: "三级·参考" };
  const EVENTS_PATH = "data/events.json";
  const ITEMS_PATH = "data/latest-24h.json";
  const FULL_PATH = "data/latest-24h-all.json";
  const COMMUNITY_PATH = "data/waytoagi-7d.json";
  // 每个视图自己的筛选按钮：[值, 文案]，第一个是默认值。
  const SEGS = {
    board: [["all", "全部"], ["hot", "热"], ["new", "新"]],
    all: [["all", "全部"], ["official", "官方一手"], ["zh", "中文"], ["en", "英文"]],
    community: [["recent", "最近更新日"], ["week", "近 7 日"]],
    privacy: [],
    policy: [],
  };
  const RANGES = [["ai", "AI 相关"], ["full", "全量（含非 AI）"]];
  // 最后一道内容安全闸：全量模式含未过滤的聚合源，和旧检索页保持同一套规则。
  const UNSAFE_HARD_PATTERNS = [
    /\bcreampie\b/i,
    /\bblowjob\b/i,
    /\bsuck (?:your|my) (?:dick|cock)\b/i,
    /中出|婊子|吸你的鸡鸡|操虚拟女友/i,
  ];
  const UNSAFE_PROMO_PATTERNS = [
    /\b(?:nsfw|nudes?|porn(?:ography)?)\b/i,
    /\buncensored pictures?\b/i,
    /\bvirtual girlfriends?\b/i,
    /\bknock her up\b/i,
    /未经审查的图片|虚拟女友|色情内容|成人内容/i,
  ];
  const TRUSTED_DATA_HOSTS = new Set([
    window.location.hostname,
    "andrew-liu.github.io",
    "raw.githubusercontent.com",
    "localhost",
    "127.0.0.1",
  ]);
  // 卡片左侧的「主体」只是展示用的规则猜测，顺序即优先级。
  const WHO_RULES = [
    [/openai|chatgpt|\bgpt-?\d|sora|codex/i, "OpenAI"],
    [/\bxai\b|grok|马斯克|musk/i, "xAI"],
    [/qwen|通义|阿里/i, "阿里"],
    [/anthropic|claude|\bopus\b|\bsonnet\b|\bhaiku\b/i, "Anthropic"],
    [/deepmind|gemini|google|谷歌/i, "Google"],
    [/\bmeta\b|\bllama\b|扎克伯格/i, "Meta"],
    [/deepseek|深度求索/i, "DeepSeek"],
    [/智谱|\bglm|z\.ai|zhipu/i, "智谱"],
    [/nvidia|英伟达/i, "NVIDIA"],
    [/microsoft|微软|copilot/i, "Microsoft"],
    [/字节|豆包|bytedance|doubao/i, "字节"],
    [/腾讯|混元|tencent/i, "腾讯"],
    [/\bapple\b|苹果/i, "Apple"],
    [/mistral/i, "Mistral"],
    [/cursor/i, "Cursor"],
    [/hugging ?face/i, "Hugging Face"],
    [/tesla|特斯拉|optimus|robotaxi|cybercab/i, "Tesla"],
  ];

  const params = new URLSearchParams(location.search);
  const state = {
    view: VIEWS.includes(params.get("view")) ? params.get("view") : "board",
    lane: params.get("lane") || "model",
    filter: "all",
    shown: PAGE,
    data: null,
    byId: new Map(),
    items: null,
    full: null,
    community: null,
    errors: {},
    q: String(params.get("q") || "").replace(/\s+/g, " ").trim().slice(0, 80),
    site: String(params.get("site") || "").trim(),
    range: params.get("range") === "full" ? "full" : "ai",
  };
  state.filter = (SEGS[state.view][0] || [""])[0];

  const $ = (id) => document.getElementById(id);
  const clean = (s) => String(s || "").replace(/[\u200b-\u200d\ufeff]/g, "").replace(/\s+/g, " ").trim();
  const hasCjk = (s) => /[\u3400-\u9fff]/.test(String(s || ""));
  const safeUrl = (u) => {
    try {
      const x = new URL(String(u || ""), location.href);
      return /^https?:$/.test(x.protocol) ? x.href : "#";
    } catch {
      return "#";
    }
  };
  const el = (tag, cls, text) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  };
  const extLink = (cls, href) => {
    const a = el("a", cls);
    a.href = safeUrl(href);
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    return a;
  };
  const fmt = (n) => (n >= 1000 ? `${(n / 1000).toFixed(n >= 10000 ? 0 : 1)}k` : String(n));
  const pad = (n) => String(n).padStart(2, "0");
  const store = {
    get(k) {
      try { return localStorage.getItem(k); } catch { return null; }
    },
    set(k, v) {
      try { localStorage.setItem(k, v); } catch {}
    },
  };

  // dataBaseUrl 覆盖开关只接受可信 https 域名，其余一律回退到同源数据。
  function dataUrl(path) {
    const raw = store.get("dataBaseUrl");
    if (!raw) return path;
    try {
      const url = new URL(raw, location.href);
      if (url.protocol !== "https:" || !TRUSTED_DATA_HOSTS.has(url.hostname)) return path;
      return `${url.origin}${url.pathname.replace(/\/+$/, "")}/${path.split("/").pop()}`;
    } catch {
      return path;
    }
  }

  const pending = new Map();
  function loadJson(path) {
    if (!pending.has(path)) {
      pending.set(path, fetch(dataUrl(path), { cache: "no-store" }).then((r) => {
        if (!r.ok) throw new Error(`${path.split("/").pop()} 返回 HTTP ${r.status}`);
        return r.json();
      }));
    }
    return pending.get(path);
  }

  function ago(iso, ref) {
    if (!iso) return "";
    const h = (ref - new Date(iso)) / 36e5;
    if (h < 1) return `${Math.max(1, Math.round(h * 60))} 分钟前`;
    if (h < 24) return `${Math.round(h)} 小时前`;
    return `${Math.round(h / 24)} 天前`;
  }

  function clock(iso) {
    if (!iso) return "--:--";
    const d = new Date(iso);
    return `${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }

  function titles(s) {
    const gh = s.github;
    if (gh && gh.repo) {
      return { main: gh.repo, sub: clean(s.title_zh && s.title_zh !== s.title ? s.title_zh : gh.description) };
    }
    const zh = clean(s.title_zh || s.title);
    const en = clean(s.title_en);
    return { main: zh, sub: en && en !== zh ? en : "" };
  }

  // 「FT：OpenAI 年化营收…」这类标题拆出冒号前的短引语，涂鸦主题用红色马克笔突出。
  function splitLead(text) {
    const m = /^(.{2,14}?)\s*([:：])\s*(.+)$/.exec(text);
    if (!m || /^https?$/i.test(m[1])) return null;
    return { lead: m[1], sep: m[2], rest: m[3] };
  }

  function who(s) {
    if (s.github && s.github.repo) return String(s.github.repo).split("/")[0];
    const text = `${s.title_zh || ""} ${s.title || ""} ${s.title_en || ""} ${s.url || ""}`;
    for (const [re, name] of WHO_RULES) if (re.test(text)) return name;
    return clean(s.category_label) || clean(s.source_name) || "AI";
  }

  function summaryOf(s) {
    const pick = (s.sources || []).find((r) => clean(r.summary)) || s.primary_item || {};
    const text = clean(pick.summary);
    return text.length > 160 ? `${text.slice(0, 158)}…` : text;
  }

  function originLabel(r) {
    try {
      const u = new URL(String(r.url || ""));
      const host = u.hostname.replace(/^(www|m|mobile)\./, "");
      if (host === "x.com" || host === "twitter.com") {
        const handle = u.pathname.split("/").filter(Boolean)[0];
        return handle ? `@${handle}` : "X";
      }
      if (host === "news.ycombinator.com") return "Hacker News";
      if (host === "github.com") return "GitHub";
      if (host.endsWith("feishu.cn")) return "WaytoAGI";
      return host.split(".").slice(-2)[0] === "co" ? host : host.replace(/\.(com|org|net|io|ai|co|cn|dev)$/, "");
    } catch {
      return clean(r.source_name || r.source);
    }
  }

  function bar(score) {
    // 终端/行情主题用字符条，其它主题用 CSS 宽度条；两者都放进 DOM，由主题决定显示哪一个。
    const wrap = el("span", "heat");
    wrap.setAttribute("role", "img");
    wrap.setAttribute("aria-label", `热度 ${Math.round(score)}`);
    const filled = Math.max(1, Math.min(10, Math.round(score / 10)));
    wrap.append(el("span", "heat-ascii", `${"█".repeat(filled)}${"░".repeat(10 - filled)}`));
    const track = el("span", "heat-track");
    const fill = el("span", "heat-fill");
    fill.style.width = `${Math.max(0, Math.min(100, score))}%`;
    track.append(fill);
    wrap.append(track, el("b", "heat-num", String(Math.round(score))));
    return wrap;
  }

  // 全部动态和社区的条目没有热度分，统一转成和事件同形的对象，复用同一个 row() 和全部主题样式。
  function itemStory(it) {
    const original = clean(it.title_original || it.title);
    const official = it.source_tier === "official";
    // 有的源拿不到发布时间，管线会用抓取时间兜底；两者几乎相同就当作「时间未知」，排到末尾并注明抓取时间。
    const pub = Date.parse(it.published_at || "");
    const seen = Date.parse(it.first_seen_at || "");
    const guessed = !Number.isFinite(pub) || (Number.isFinite(seen) && Math.abs(pub - seen) < 120000);
    const story = {
      story_id: it.id,
      title: original,
      title_zh: hasCjk(original) ? original : clean(it.title_zh) || original,
      title_en: clean(it.title_en),
      url: it.url,
      earliest_at: guessed ? null : it.published_at,
      seen_at: it.first_seen_at || it.published_at,
      date_label: guessed ? `抓取于 ${clock(it.first_seen_at || it.published_at)}` : "",
      source_name: clean(it.source || it.site_name),
      category_label: clean(it.site_name),
      tier: official ? 1 : 2,
      badge: clean(it.source_tier_label) || (official ? "官方" : ""),
      sources: [{ url: it.url, source: it.source || it.site_name, summary: it.summary }],
      plain: true,
      site_id: clean(it.site_id),
      site_name: clean(it.site_name || it.source),
      haystack: [original, it.title_zh, it.title_en, it.source, it.site_name, it.summary].map(clean).join(" ").toLowerCase(),
    };
    const gh = it.site_id === "github_trending" && /^([\w.-]+\/[\w.-]+)\s*:\s*(.*)$/.exec(original);
    if (gh) story.github = { repo: gh[1], description: gh[2] };
    return story;
  }

  function isUnsafe(it) {
    const text = [it.title, it.title_original, it.title_zh, it.title_en, it.summary].map(clean).join(" ");
    if (UNSAFE_HARD_PATTERNS.some((p) => p.test(text))) return true;
    return UNSAFE_PROMO_PATTERNS.filter((p) => p.test(text)).length >= 2;
  }

  function toStories(raw) {
    const stories = raw.filter((it) => it && it.url && (it.title || it.title_original) && !isUnsafe(it)).map(itemStory);
    const at = (s) => new Date(s.earliest_at || 0).getTime();
    const seenAt = (s) => new Date(s.seen_at || 0).getTime();
    stories.sort((a, b) => (Boolean(b.earliest_at) - Boolean(a.earliest_at)) || at(b) - at(a) || seenAt(b) - seenAt(a));
    const sites = new Map();
    for (const s of stories) if (s.site_id) sites.set(s.site_id, { name: s.site_name || s.site_id, count: (sites.get(s.site_id)?.count || 0) + 1 });
    return { stories, sites };
  }

  function communityStory(u, i) {
    return {
      story_id: `waytoagi-${i}`,
      title: clean(u.title),
      url: u.url,
      date_label: clean(u.date),
      source_name: "WaytoAGI",
      tier: 2,
      badge: "WaytoAGI",
      sources: [{ url: u.url, source: "WaytoAGI", summary: u.summary }],
      plain: true,
    };
  }

  function row(s, rank, ref) {
    const t = titles(s);
    const score = Number(s.hot_score) || 0;
    const li = el("li", "row");
    li.dataset.hot = String(Boolean(s.is_hot));
    li.dataset.new = String(Boolean(s.is_fresh));
    li.dataset.tier = String(s.tier || 2);
    if (s.plain) li.dataset.plain = "true";
    li.style.setProperty("--heat", s.plain ? "100%" : `${Math.max(0, Math.min(100, score))}%`);

    const name = who(s);
    const whoEl = el("span", "who");
    whoEl.append(el("span", "who-mark", name.slice(0, 1).toUpperCase()), el("span", "who-name", name));
    li.append(whoEl, el("span", "rank", pad(rank)));

    const body = el("div", "row-body");
    const kicker = el("p", "kicker");
    if (s.is_hot) kicker.append(el("span", "tag tag-hot", "HOT"));
    if (s.is_fresh) kicker.append(el("span", "tag tag-new", "NEW"));
    kicker.append(el("span", "tag tag-tier", s.badge || TIER_LABEL[s.tier] || "二级"));
    const at = s.earliest_at || s.latest_at;
    let when;
    if (s.date_label) when = s.date_label;
    else if (s.time_known === false) when = "时间未知";
    else when = `${clock(at)} · ${ago(at, ref)}`;
    kicker.append(el("span", "time", when));
    body.append(kicker);

    const link = extLink("title", s.url);
    const hl = el("span", "hl");
    const parts = splitLead(t.main);
    if (parts) hl.append(el("span", "lead", parts.lead), el("span", "lead-sep", parts.sep), document.createTextNode(parts.rest));
    else hl.textContent = t.main;
    link.append(hl);
    body.append(link);
    if (t.sub) body.append(el("p", "sub", t.sub));
    const summary = summaryOf(s);
    if (summary && summary !== t.main) body.append(el("p", "summary", summary));

    const meta = el("p", "meta");
    const gh = s.github;
    if (gh && gh.repo) {
      if (gh.stars_today) meta.append(el("span", "m-star", `+${fmt(gh.stars_today)} ★ 今日`));
      if (gh.stars) meta.append(el("span", null, `${fmt(gh.stars)} ★`));
      if (gh.language) meta.append(el("span", null, gh.language));
    } else {
      meta.append(el("span", "m-src", clean(s.source_name || s.source)));
    }
    if (s.source_count > 1) meta.append(el("span", "m-count", `${s.source_count} 个独立来源`));
    body.append(meta);

    const refs = (s.sources || []).slice(0, 10);
    // 涂鸦主题直接平铺来源链接：按原文出处命名（@账号 或站点名）并去重，避免一排同名聚合源。
    const inline = el("p", "src-links");
    const seen = new Set();
    let extra = 0;
    for (const r of s.sources || []) {
      const label = originLabel(r);
      if (!label || seen.has(label)) continue;
      seen.add(label);
      if (seen.size > 4) { extra += 1; continue; }
      const a = extLink(null, r.url);
      a.textContent = label;
      inline.append(a);
    }
    if (extra) inline.append(el("span", "src-more", `+${extra}`));
    if (seen.size) body.append(inline);

    if (refs.length > 1) {
      const d = el("details", "sources");
      d.append(el("summary", null, `展开 ${refs.length} 条报道`));
      const ul = el("ul");
      for (const r of refs) {
        const item = el("li");
        const a = extLink(null, r.url);
        a.append(el("span", "role", ROLE_LABEL[r.role] || ""), el("span", null, clean(r.source || r.source_name)));
        item.append(a);
        ul.append(item);
      }
      d.append(ul);
      body.append(d);
    }
    li.append(body);
    if (!s.plain) li.append(bar(score));
    return li;
  }

  function setHead(code, name, stat) {
    $("view-code").textContent = code;
    $("view-name").textContent = name;
    $("view-stat").textContent = stat;
  }

  function renderList(stories, ref, emptyText) {
    const feed = $("feed");
    feed.replaceChildren();
    stories.slice(0, state.shown).forEach((s, i) => feed.append(row(s, i + 1, ref)));
    if (!stories.length) feed.append(el("li", "empty", emptyText));
    const more = $("more");
    more.hidden = stories.length <= state.shown;
    more.textContent = `再看 ${stories.length - state.shown} 条`;
  }

  function renderSeg() {
    const seg = $("seg");
    seg.replaceChildren();
    for (const [value, label] of SEGS[state.view]) {
      const b = el("button", null, label);
      b.type = "button";
      b.dataset.filter = value;
      b.setAttribute("aria-pressed", String(value === state.filter));
      b.addEventListener("click", () => {
        state.filter = value;
        state.shown = PAGE;
        renderSeg();
        render();
      });
      seg.append(b);
    }
  }

  // ---------- 赛道看板 ----------
  function laneStories(key) {
    const lane = state.data.lanes.find((l) => l.key === key);
    return lane ? lane.stories.map((id) => state.byId.get(id)).filter(Boolean) : [];
  }

  function passBoard(s) {
    if (state.filter === "hot") return s.is_hot;
    if (state.filter === "new") return s.is_fresh;
    return true;
  }

  function renderTabs() {
    const nav = $("lanes");
    nav.replaceChildren();
    state.data.lanes.forEach((lane, idx) => {
      const b = el("button", "lane-tab");
      b.type = "button";
      b.setAttribute("role", "tab");
      b.dataset.lane = lane.key;
      b.setAttribute("aria-selected", String(lane.key === state.lane));
      b.append(el("span", "tab-code", pad(idx + 1)), el("span", "tab-name", lane.label));
      const badge = el("span", "tab-count", String(lane.count));
      if (lane.hot_count) badge.dataset.hot = "true";
      b.append(badge);
      b.addEventListener("click", () => select(lane.key));
      nav.append(b);
    });
  }

  function renderBoard() {
    const d = state.data;
    const ref = new Date(d.generated_at);
    const idx = d.lanes.findIndex((l) => l.key === state.lane);
    const lane = d.lanes[idx];
    document.body.dataset.lane = lane.key;
    setHead(`CH ${pad(idx + 1)} / ${pad(d.lanes.length)}`, lane.label,
      `近 ${d.window_hours} 小时 ${lane.count} 条 · 热 ${lane.hot_count} · 新 ${lane.fresh_count}`);
    renderList(laneStories(lane.key).filter(passBoard), ref,
      state.filter === "all" ? "过去 24 小时这条线很安静" : "当前筛选下没有事件，切回「全部」看看");
  }

  // ---------- 全部动态 + 高级检索 ----------
  function passItem(s) {
    if (state.filter === "official" && s.tier !== 1) return false;
    if (state.filter === "zh" && !hasCjk(s.title)) return false;
    if (state.filter === "en" && hasCjk(s.title)) return false;
    if (state.site && s.site_id !== state.site) return false;
    if (state.q) {
      for (const word of state.q.toLowerCase().split(" ")) if (word && !s.haystack.includes(word)) return false;
    }
    return true;
  }

  function currentList() {
    return state.range === "full" ? state.full : state.items;
  }

  function toggleGroup(box, options, current, onPick) {
    box.replaceChildren();
    for (const [value, label] of options) {
      const b = el("button", null, label);
      b.type = "button";
      b.dataset.filter = value || "any";
      b.setAttribute("aria-pressed", String(value === current));
      b.addEventListener("click", () => onPick(value));
      box.append(b);
    }
  }

  function renderTools() {
    const d = currentList();
    toggleGroup($("range"), RANGES, state.range, (value) => {
      state.range = value;
      state.shown = PAGE;
      syncUrl();
      ensureData("all");
      render();
    });
    const sites = d ? Array.from(d.sites.entries()).sort((a, b) => b[1].count - a[1].count) : [];
    if (state.site && d && !d.sites.has(state.site)) state.site = "";
    toggleGroup($("sites"), [["", "全部站点"], ...sites.map(([id, v]) => [id, `${v.name} ${v.count}`])], state.site, (value) => {
      state.site = value;
      state.shown = PAGE;
      syncUrl();
      render();
    });
    if ($("q").value !== state.q) $("q").value = state.q;
    $("tools-clear").hidden = !(state.q || state.site || state.filter !== "all" || state.range !== "ai");
  }

  function renderAll() {
    const d = currentList();
    document.body.dataset.lane = "all";
    renderTools();
    const stories = d.stories.filter(passItem);
    const filtered = stories.length !== d.stories.length;
    setHead(state.range === "full" ? "ALL / 24H / FULL" : "ALL / 24H", "全部动态",
      `近 ${d.window_hours || 24} 小时 ${d.stories.length} 条 · ${d.sites.size} 个站点${filtered ? ` · 命中 ${stories.length} 条` : ""} · 按发布时间倒序`);
    renderList(stories, d.ref, state.q ? `没有找到包含「${state.q}」的条目` : "当前筛选下没有条目");
  }

  // ---------- 社区 ----------
  function renderCommunity() {
    const c = state.community;
    document.body.dataset.lane = "community";
    const list = state.filter === "week" ? c.week : c.recent;
    setHead("COMMUNITY / WAYTOAGI", "社区",
      `WaytoAGI 最近更新日 ${c.latestDate || "--"} · ${c.recent.length} 条 · 近 7 日 ${c.week.length} 条`);
    renderList(list, c.ref, c.error || (state.filter === "week" ? "近 7 日没有更新" : "最近更新日没有内容，切到「近 7 日」看看"));
  }

  function renderLoading(name, text) {
    setHead("", name, text);
    $("feed").replaceChildren(el("li", "empty", text));
    $("more").hidden = true;
  }

  function renderDoc(view) {
    const doc = DOCS[view];
    document.body.dataset.lane = "doc";
    setHead(doc.code, doc.name, doc.stat);
    for (const [key, d] of Object.entries(DOCS)) $(d.id).hidden = key !== view;
  }

  function render() {
    const view = state.view;
    const isDoc = Boolean(DOCS[view]);
    $("lanes").hidden = view !== "board";
    $("tools").hidden = view !== "all";
    $("seg").hidden = isDoc;
    $("feed").hidden = isDoc;
    if (isDoc) {
      $("more").hidden = true;
      return renderDoc(view);
    }
    for (const d of Object.values(DOCS)) $(d.id).hidden = true;
    if (view === "board") {
      if (state.errors.board) return renderLoading("赛道看板", `看板没有加载出来：${state.errors.board}`);
      if (!state.data) return renderLoading("赛道看板", "正在读取数据");
      return renderBoard();
    }
    if (view === "all") {
      const key = state.range === "full" ? "full" : "all";
      if (state.errors[key]) return renderLoading("全部动态", `全部动态没有加载出来：${state.errors[key]}`);
      if (!currentList()) {
        renderTools();
        return renderLoading("全部动态", "正在读取数据");
      }
      return renderAll();
    }
    if (state.errors.community) return renderLoading("社区", `社区没有加载出来：${state.errors.community}`);
    if (!state.community) return renderLoading("社区", "正在读取数据");
    return renderCommunity();
  }

  function ensureData(view) {
    if (view === "all" && state.range === "ai" && !state.items && !state.errors.all) {
      loadJson(ITEMS_PATH).then((d) => {
        const raw = Array.isArray(d.items) ? d.items : Array.isArray(d.items_ai) ? d.items_ai : [];
        state.items = { ...toStories(raw), ref: new Date(d.generated_at || Date.now()), window_hours: d.window_hours };
      }).catch((err) => { state.errors.all = err.message; })
        .finally(() => { if (state.view === "all") render(); });
    }
    if (view === "all" && state.range === "full" && !state.full && !state.errors.full) {
      loadJson(FULL_PATH).then((d) => {
        const raw = Array.isArray(d.items_all) ? d.items_all : Array.isArray(d.items) ? d.items : [];
        state.full = { ...toStories(raw), ref: new Date(d.generated_at || Date.now()), window_hours: d.window_hours };
      }).catch((err) => { state.errors.full = err.message; })
        .finally(() => { if (state.view === "all") render(); });
    }
    if (view === "community" && !state.community && !state.errors.community) {
      loadJson(COMMUNITY_PATH).then((w) => {
        const week = Array.isArray(w.updates_7d) ? w.updates_7d : [];
        const latestDate = w.latest_date || (week.length ? week[0].date : null);
        const today = Array.isArray(w.updates_today) && w.updates_today.length
          ? w.updates_today
          : (latestDate ? week.filter((u) => u.date === latestDate) : []);
        const pick = (list) => list.filter((u) => u && u.url && u.title).map(communityStory);
        state.community = {
          recent: pick(today),
          week: pick(week),
          latestDate,
          ref: new Date(w.generated_at || Date.now()),
          error: w.has_error ? clean(w.error) || "WaytoAGI 数据抓取失败" : "",
        };
      }).catch((err) => { state.errors.community = err.message; })
        .finally(() => { if (state.view === "community") render(); });
    }
  }

  function syncUrl() {
    const url = new URL(location.href);
    url.hash = "";
    url.searchParams.set("view", state.view);
    if (state.view === "board") url.searchParams.set("lane", state.lane);
    else url.searchParams.delete("lane");
    const searching = state.view === "all";
    for (const [key, value, fallback] of [["q", state.q, ""], ["site", state.site, ""], ["range", state.range, "ai"]]) {
      if (searching && value && value !== fallback) url.searchParams.set(key, value);
      else url.searchParams.delete(key);
    }
    history.replaceState(null, "", url);
  }

  function setView(view, focusId) {
    if (!VIEWS.includes(view)) return;
    if (view !== state.view) {
      state.filter = (SEGS[view][0] || [""])[0];
      state.shown = PAGE;
    }
    state.view = view;
    document.body.dataset.view = view;
    document.querySelectorAll("[data-view]").forEach((a) => {
      if (a.dataset.view === view && !a.dataset.focus) a.setAttribute("aria-current", "page");
      else a.removeAttribute("aria-current");
    });
    syncUrl();
    renderSeg();
    ensureData(view);
    render();
    if (view === "board" && state.data) centerTab(state.lane);
    if (focusId && $(focusId)) $(focusId).focus();
    else if (DOCS[view]) window.scrollTo({ top: 0 });
  }

  function centerTab(key) {
    const nav = $("lanes");
    const tab = nav.querySelector(`.lane-tab[data-lane="${CSS.escape(key)}"]`);
    if (!tab) return;
    const target = nav.scrollLeft + tab.getBoundingClientRect().left - nav.getBoundingClientRect().left - (nav.clientWidth - tab.offsetWidth) / 2;
    nav.scrollTo({ left: Math.max(0, Math.min(target, nav.scrollWidth - nav.clientWidth)), behavior: "smooth" });
  }

  function select(key) {
    if (!state.data.lanes.some((l) => l.key === key)) return;
    state.lane = key;
    state.shown = PAGE;
    syncUrl();
    renderTabs();
    renderBoard();
    centerTab(key);
  }

  function step(delta) {
    const keys = state.data.lanes.map((l) => l.key);
    const i = keys.indexOf(state.lane);
    select(keys[(i + delta + keys.length) % keys.length]);
  }

  // ---------- 主题菜单：自绘 listbox，样式跟随当前主题，不用浏览器原生下拉 ----------
  const skinBtn = $("skin");
  const skinMenu = $("skin-menu");
  const skinOptions = () => Array.from(skinMenu.querySelectorAll("[role=option]"));

  function applySkin(name, persist) {
    const skin = SKINS.includes(name) ? name : DEFAULT_SKIN;
    document.body.dataset.skin = skin;
    for (const opt of skinOptions()) {
      const on = opt.dataset.theme === skin;
      opt.setAttribute("aria-selected", String(on));
      if (on) $("skin-current").textContent = opt.lastChild.textContent;
    }
    if (persist) {
      store.set("boardSkin", skin);
      const url = new URL(location.href);
      url.searchParams.set("skin", skin);
      history.replaceState(null, "", url);
    }
  }

  function focusOption(opt) {
    for (const o of skinOptions()) o.classList.toggle("is-active", o === opt);
    if (opt) {
      skinMenu.setAttribute("aria-activedescendant", opt.id);
      opt.scrollIntoView({ block: "nearest" });
    }
  }

  function openMenu() {
    skinMenu.hidden = false;
    skinBtn.setAttribute("aria-expanded", "true");
    skinMenu.focus();
    focusOption(skinOptions().find((o) => o.getAttribute("aria-selected") === "true"));
  }

  function closeMenu(refocus) {
    if (skinMenu.hidden) return;
    skinMenu.hidden = true;
    skinBtn.setAttribute("aria-expanded", "false");
    if (refocus) skinBtn.focus();
  }

  skinOptions().forEach((opt) => {
    opt.id = `skin-opt-${opt.dataset.theme}`;
    opt.addEventListener("click", () => {
      applySkin(opt.dataset.theme, true);
      closeMenu(true);
    });
    opt.addEventListener("mousemove", () => focusOption(opt));
  });
  skinBtn.addEventListener("click", () => (skinMenu.hidden ? openMenu() : closeMenu(false)));
  skinBtn.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      openMenu();
    }
  });
  skinMenu.addEventListener("keydown", (e) => {
    const opts = skinOptions();
    const cur = opts.findIndex((o) => o.classList.contains("is-active"));
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      const next = (cur + (e.key === "ArrowDown" ? 1 : -1) + opts.length) % opts.length;
      focusOption(opts[next]);
    } else if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      if (opts[cur]) applySkin(opts[cur].dataset.theme, true);
      closeMenu(true);
    } else if (e.key === "Escape" || e.key === "Tab") {
      closeMenu(e.key === "Escape");
    }
  });
  document.addEventListener("click", (e) => {
    if (!e.target.closest || !e.target.closest(".skin-pick")) closeMenu(false);
  });

  // ---------- 启动 ----------
  // 顶部导航、页脚的高级检索/隐私/版权、文档内互链都在页内切换，不再跳去旧页面。
  document.addEventListener("click", (e) => {
    const a = e.target.closest && e.target.closest("a[data-view]");
    if (!a || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    e.preventDefault();
    setView(a.dataset.view, a.dataset.focus);
  });
  let typing = 0;
  $("q").addEventListener("input", () => {
    clearTimeout(typing);
    typing = setTimeout(() => {
      state.q = clean($("q").value).slice(0, 80);
      state.shown = PAGE;
      syncUrl();
      render();
    }, 160);
  });
  $("q").addEventListener("keydown", (e) => {
    if (e.key === "Escape" && $("q").value) {
      $("q").value = "";
      $("q").dispatchEvent(new Event("input"));
    }
  });
  $("tools-clear").addEventListener("click", () => {
    Object.assign(state, { q: "", site: "", filter: "all", range: "ai", shown: PAGE });
    $("q").value = "";
    syncUrl();
    renderSeg();
    ensureData("all");
    render();
    $("q").focus();
  });
  $("more").addEventListener("click", () => {
    state.shown += PAGE;
    render();
  });
  applySkin(params.get("skin") || store.get("boardSkin") || DEFAULT_SKIN, false);
  document.addEventListener("keydown", (e) => {
    if (state.view !== "board" || !state.data || e.altKey || e.ctrlKey || e.metaKey) return;
    if (e.target.closest && e.target.closest("input, textarea, [role=listbox]")) return;
    if (e.key === "ArrowRight") step(1);
    if (e.key === "ArrowLeft") step(-1);
  });

  setView(state.view);

  loadJson(EVENTS_PATH)
    .then((d) => {
      if (!d || !Array.isArray(d.lanes) || !d.lanes.length || !Array.isArray(d.stories)) {
        throw new Error("events.json 缺少 lanes 或 stories 字段");
      }
      state.data = d;
      state.byId = new Map(d.stories.map((s) => [s.story_id, s]));
      if (!d.lanes.some((l) => l.key === state.lane)) state.lane = d.lanes[0].key;
      const ref = new Date(d.generated_at);
      $("stamp").textContent =
        `${ref.toLocaleString("zh-CN", { hour12: false })} 更新 · 热榜 ${d.stats?.hot_count ?? 0} · 最新 ${d.stats?.fresh_count ?? 0}`;
      renderTabs();
      if (state.view === "board") {
        render();
        centerTab(state.lane);
      }
    })
    .catch((err) => {
      state.errors.board = err.message;
      $("stamp").textContent = "数据读取失败";
      if (state.view === "board") render();
    });
})();
