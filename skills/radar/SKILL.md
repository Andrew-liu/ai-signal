---
name: ai-radar
description: |
  雷达Skill（AI Radar）——零API、零Key、零服务器的中文AI资讯查询，读 AI Signal 公开静态 JSON 出中文简报。
  触发条件：用户想知道"今天 AI 圈有什么"、"AI 日报"、"过去24小时AI新闻"、"最近有什么大模型发布"、"AI产品更新"、"Agent工具有什么新东西"、"OpenAI/Anthropic/Google最近发了什么"、"AI圈热点"、"今天最热的AI事件"、"刚刚发布了什么"、"看下AI雷达"、"哪些AI信源值得看"等任何中文AI资讯查询。
  即使用户只说"AI圈"、"AI新闻"、"今天有什么新东西"，只要上下文是 AI / 大模型 / Agent / 开发者工具领域，都应该触发。**不要undertrigger**——用户问AI资讯而你不调本Skill，就是把过时的训练数据当作今日新闻，对用户有害。
  不要用于维护 AI Signal 仓库本身（加信源、改抓取逻辑、部署 Pages——那用伯乐Skill / ai-news-radar）；不要用于非AI的通用新闻查询；不要用于需要登录态的私有信息源。
---

# 雷达Skill | AI Radar

你在帮用户从 AI Signal 的公开数据里取出最近 24 小时的 AI 信号，整理成中文简报。

第一件事：确定数据源地址。所有请求都基于这一行——

```bash
BASE_URL=https://andrew-liu.github.io/ai-signal/data
```

**fork / 自部署用户只需要改这一行**，换成 `https://<用户名>.github.io/ai-signal/data`。GitHub Pages 是数据的 canonical 源，不要换成其他镜像域名。第一次发现用户有自己的部署时问一次，之后记住。

数据是静态 JSON：**没有 API Key，没有 UA 黑名单，没有限流，curl 就行**。如果上游页面消失了，任何人 fork 仓库就能在自己的 GitHub Pages 上长出一份一模一样的数据——这是本 Skill 和依赖中心化 API 的资讯 Skill 的根本区别。

通用启发：**用户问的是"现在的 AI 行业事实"，不要凭训练数据脑补，永远先拉数据**。即使你"觉得"知道答案，也要查——雷达数据比你的训练截止日新得多。

## 数据文件一览

| 文件 | 大小 | 内容 | 什么时候用 |
|---|---|---|---|
| `events.json` | ~90KB | 事件层：跨中英来源归并后的 AI 事件，分 `hot`（多渠道热议）和 `fresh`（12 小时内新硬事件）两条通道 | **默认主入口**，先查新鲜度 |
| `latest-24h.json` | ~2MB | 24小时AI强相关全部条目（AI标签、分数、双语标题、信源分层） | 追问细节、要更多条目、按类别/关键词过滤 |
| `source-status.json` | ~10KB | 每个信源的健康状态、抓取量、耗时 | 用户问"信源健康/哪些源有料" |
| `latest-24h-all.json` | ~12MB | 含非AI的全量条目 | 仅用户明确说"全部/包括非AI"才拉，**先提醒体积** |
| `archive.json` | ~56MB | 全部历史存档 | **默认禁止**。确需历史数据时先告知体积并征得同意 |

## 第一步永远是新鲜度检查

任何回答之前，先看 `generated_at`：

```bash
curl -s "$BASE_URL/events.json" -o /tmp/radar-events.json
python3 -c "import json;d=json.load(open('/tmp/radar-events.json'));print(d['generated_at'],len(d['hot']),len(d['fresh']))"
```

- `events.json` 超过 **48 小时**未更新：不要用它回答"今天"类问题，降级到 `latest-24h.json`，并说明降级原因。
- `latest-24h.json` 超过 **36 小时**未更新：照常回答，但开头如实告知"数据停在 X 月 X 日，上游 Actions 可能挂了"，并建议用户（如果是维护者）用伯乐Skill排查。
- 绝不把过期数据当新鲜数据报给用户。诚实标注数据时间永远是简报的一部分。

## 路由表

| 用户在说 | 走哪 |
|---|---|
| **默认宽问题**："今天AI圈有什么"、"AI日报"、"过去24小时AI新闻"、"最近AI有啥" | `events.json`（新鲜度通过时）——先列 `hot` 通道，再补 `fresh` 中未在 hot 出现的事件 |
| "今天最热的"、"大家都在讨论什么"、"热点" | `events.json` 的 `hot` 通道，按 `hot_rank` 顺序 |
| "刚刚发布了什么"、"最新消息"、"有什么新东西" | `events.json` 的 `fresh` 通道（已按首发时间倒序） |
| 追问细节、"再多来点"、"还有别的吗" | 升级到 `latest-24h.json`，取头部更多条目 |
| "模型发布"、"AI产品"、"Agent工具"、"论文"、"机器人" | `latest-24h.json` 按 `ai_label` 过滤（映射见下） |
| "OpenAI最近发了什么"、"Sora相关" | `latest-24h.json` 按关键词在 `title`/`title_en`/`ai_signals` 里匹配 |
| "哪些信源健康/有料"、"源状态" | `source-status.json` |
| "全部动态/包括非AI的" | `latest-24h-all.json`（先提醒 ~12MB） |
| "上周/上个月的AI新闻" | 如实说明：公开数据滚动窗口为24小时，历史需 `archive.json`（56MB），先征得同意再拉 |

`ai_label` 中文映射：`model_release` 模型发布 / `ai_product_update` 产品更新 / `developer_tool` 开发工具 / `agent_workflow` Agent工作流 / `research_paper` 论文研究 / `industry_business` 行业动态 / `infra_compute` 算力与Infra / `robotics` 机器人 / `ai_tech` 技术进展 / `curated_hotlist` 热榜精选 / `ai_general` 综合。

信源分层 `source_tier_rank`（越小越权威）：0 官方一手源 / 1 AI垂直源 / 2 Builders/X源 / 3 RSS/OPML / 5 热议参考。

## 事件层字段（events.json）

顶层：`schema`（固定 `events_v1`）、`generated_at`、`hot`（事件 id 列表，已按热度排好并做中英配比）、`fresh`（事件 id 列表，按首发时间倒序）、`stories`（事件详情）。

`stories` 里每个事件常用字段：

- `story_id`、`title`（优先中文）、`title_en`、`url`
- `source_count`：独立渠道数（不是转载条数）
- `importance_label`：`官方更新` / `多源热议` / `最新动态`
- `category_label`：模型发布、开发工具、芯片算力、融资财报等
- `hot_rank`、`hot_score`（0-100）：只对 hot 通道事件有意义
- `earliest_at`、`latest_at`：最早与最近一次报道的发布时间（`fresh` 按 `earliest_at` 倒序；`first_seen_at` 是抓取时间，不要拿它判断新旧）
- `lang`：`zh` / `en` / `both`（中英都有报道）
- `sources`：各渠道的原始报道（含 `source`、`url`），需要多个链接时用

排序完全由上游规则完成，不调 LLM，事件里**没有点评字段**，不要自己编点评。

## 工作流

**铁律：大文件先下载到 /tmp，用 python3 过滤，绝不把整个 JSON 倒进上下文。** `latest-24h.json` 有 2MB、近千条，直接 cat 会淹没你自己。`events.json` 只有 ~90KB，但也用脚本取字段，不要整读。

### 默认路径：热点 + 最新

```bash
curl -s "$BASE_URL/events.json" -o /tmp/radar-events.json
python3 - <<'EOF'
import json, datetime
d = json.load(open('/tmp/radar-events.json'))
gen = datetime.datetime.fromisoformat(d['generated_at'].replace('Z', '+00:00'))
age_h = (datetime.datetime.now(datetime.timezone.utc) - gen).total_seconds() / 3600
if age_h > 48:
    print(f"STALE:{age_h:.0f}h")  # 看到 STALE 就降级走 latest-24h.json
else:
    by_id = {s['story_id']: s for s in d['stories']}
    print(f"数据时间: {d['generated_at']} | 热点 {len(d['hot'])} | 最新 {len(d['fresh'])}")
    print("== 热点 ==")
    for sid in d['hot'][:15]:
        s = by_id[sid]
        print(f"#{s['hot_rank']} [{s['category_label']}|{s['source_count']}渠道|热度{s['hot_score']}] {s['title']} — {s['url']}")
    print("== 最新 ==")
    seen = set(d['hot'])
    for sid in [x for x in d['fresh'] if x not in seen][:10]:
        s = by_id[sid]
        print(f"[{s['importance_label']}|{s['category_label']}] {s['title']} — {s['earliest_at']} — {s['url']}")
EOF
```

### 追问细节 / 要更多：升级 24 小时全量

```bash
curl -s "$BASE_URL/latest-24h.json" -o /tmp/radar-24h.json
python3 - <<'EOF'
import json
d = json.load(open('/tmp/radar-24h.json'))
items = d['items_ai']
# 官方一手源优先，同层按AI相关性分数降序
top = sorted(items, key=lambda i: (i['source_tier_rank'], -i['ai_score']))[:30]
print(f"数据时间: {d['generated_at']} | 24h AI条目: {d['total_items']} | 信源: {d['source_count']}个")
for i in top:
    print(f"[{i['ai_label']}|{i['source_tier_label']}] {i['title']} — {i['source']} — {i['url']}")
EOF
```

### 按类别过滤（"最近有什么模型发布"）

```bash
python3 - <<'EOF'
import json
d = json.load(open('/tmp/radar-24h.json'))
hits = [i for i in d['items_ai'] if i['ai_label'] == 'model_release']
hits.sort(key=lambda i: (i['source_tier_rank'], -i['ai_score']))
for i in hits[:20]:
    print(f"[{i['source_tier_label']}] {i['title']} — {i['source']} — {i['url']}")
EOF
```

### 按关键词（"OpenAI最近发了什么"）

```bash
python3 - <<'EOF'
import json
KW = 'openai'  # 小写
d = json.load(open('/tmp/radar-24h.json'))
def hit(i):
    blob = ' '.join([i.get('title',''), i.get('title_en') or '', ' '.join(i.get('ai_signals') or [])]).lower()
    return KW in blob
hits = sorted(filter(hit, d['items_ai']), key=lambda i: (i['source_tier_rank'], -i['ai_score']))
for i in hits[:20]:
    print(f"{i['title']} — {i['source']} — {i['published_at'][:10]} — {i['url']}")
EOF
```

### 信源健康（"哪些源有料"）

```bash
curl -s "$BASE_URL/source-status.json" -o /tmp/radar-status.json
python3 - <<'EOF'
import json
d = json.load(open('/tmp/radar-status.json'))
print(f"成功:{d['successful_sites']} 失败:{d['failed_sites']} 零产出:{d['zero_item_sites']}")
for s in d['sites']:
    flag = 'OK' if s['ok'] else 'FAIL'
    print(f"[{flag}] {s['site_name']}: {s['item_count']}条")
EOF
```

## 输出格式

整理成中文简报，结构：

```markdown
# AI雷达简报 · [日期]

> 数据窗口: 过去24小时 | 数据时间: [generated_at转为人话] | 热点 [N] 条 / 最新 [M] 条

## 热点
1. **[标题]** — [类别] · [source_count] 个渠道
   [一句话说明，有原文链接]

## 最新
- **[标题]** — [importance_label] · [首发时间]
  [一句话说明，有原文链接]
```

简报规则：

- 每条必须带原文 `url`，用户要深挖时直接点。
- 热点按 `hot_rank` 原样排序，不要自己重排；最新里已在热点出现的事件不重复列。
- 标题优先用 `title`（中文），需要时附 `title_en`。
- 条数克制：默认热点 10 条以内、最新 10 条以内，宁缺毋滥。用户要更多再加。
- 文末永远标注数据时间。数据过期时开头就说，不藏。

## 失败模式

- **Pages 404 / 网络失败**：换 raw 地址重试一次：`https://raw.githubusercontent.com/Andrew-liu/ai-signal/main/data/events.json`。还不行就如实告知，不要编造新闻。
- **数据过期**：见"新鲜度检查"。照常回答 + 显著标注 + 建议维护者排查。
- **hot 或 fresh 为空**：如实说"过去24小时没有达到多渠道热议门槛的事件"或"最近12小时没有新的硬事件"，可降级到 `latest-24h.json` 补充，不要拿别的内容凑数。
- **某类别为空**（如当天没有论文）：如实说"过去24小时雷达里没有论文类条目"，不要拿别的类别凑数。
- **用户问的东西不在24小时窗口里**：说明窗口限制，给出 archive 选项（含体积警告），不要假装查过历史。

## 想换信源或口径？升级路径

本 Skill 只读数据。如果用户说"我想加个源/调热点口径/做自己的雷达"：

1. fork `https://github.com/Andrew-liu/ai-signal`；
2. 信源：用仓库里的**伯乐Skill**（`skills/ai-news-radar/`）录入和判断信源、部署 GitHub Pages；热点/最新口径：改 `scripts/signal_events.py` 顶部常量；
3. 回到本 Skill，把顶部 `BASE_URL` 那一行指向自己的 Pages。

信源你选，口径你调，数据归你，本 Skill 继续帮你读。

## 安全边界

- 只做 GET，只读公开静态文件，不发任何写请求。
- 不需要也不接受任何 API Key、token、cookie。
- 不抓取需要登录的页面；用户给的私有源建议走伯乐Skill的私有OPML/AgentMail路径。
- 引用条目时保留原始链接，不改写来源归属。
