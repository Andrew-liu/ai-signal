<div align="center">
  <h1>AI Signal</h1>
  <p>
    <a href="https://github.com/Andrew-liu/ai-signal/stargazers"><img src="https://img.shields.io/github/stars/Andrew-liu/ai-signal?style=flat-square&amp;color=f5c542" alt="GitHub stars"></a>
    <a href="https://andrew-liu.github.io/ai-signal/"><img src="https://img.shields.io/badge/Live-AI%20Signal-green?style=flat-square" alt="Live site"></a>
    <a href="https://github.com/Andrew-liu/ai-signal/actions/workflows/update-news.yml"><img src="https://img.shields.io/github/actions/workflow/status/Andrew-liu/ai-signal/update-news.yml?branch=main&amp;label=update&amp;style=flat-square" alt="Update workflow"></a>
    <a href="skills/ai-news-radar/README.md"><img src="https://img.shields.io/badge/Agent%20Skill-AI%20News%20Radar-blueviolet?style=flat-square" alt="AI News Radar Agent Skill"></a>
    <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green.svg?style=flat-square" alt="MIT License"></a>
  </p>
  <p>面向中文 AI 从业者与内容创作者的开源资讯聚合站。</p>
  <p>
    <a href="https://andrew-liu.github.io/ai-signal/">在线站点</a> ·
    <a href="README.en.md">English</a> ·
    <a href="docs/SOURCE_COVERAGE.md">信息源策略</a>
  </p>
</div>

AI Signal 自动采集官方博客、技术媒体、RSS、开发者社区及可选社交信源，完成 AI 相关性过滤、中文标题处理、重复内容去除、同事件合并和重要性排序，最终生成可直接部署的静态网站。

## 核心能力

- 聚合官方更新、AI 媒体、RSS/OPML、Hacker News、GitHub 与可选社交平台
- 使用可解释规则过滤 AI 强相关内容
- 将重复报道合并成同一事件，并保留多个原始来源
- 生成中文标题、短摘要、推荐理由与每日精选
- 展示来源健康、AI 内容占比和采集异常
- 每小时通过 GitHub Actions 更新并部署 GitHub Pages
- 候选数据通过测试、脱敏和质量门禁后才会发布

## 技术结构

```text
公开信源 / RSS / 可选 API
          ↓
抓取与标准化 RawItem
          ↓
AI 相关性评分与内容增强
          ↓
去重、事件合并、重要性排序
          ↓
data/*.json
          ↓
静态响应式网站 / Agent Skill
```

主要目录：

```text
scripts/        数据采集、聚类、评分和发布脚本
assets/         单一响应式前端资源
data/           网站读取的静态 JSON
feeds/          OPML 示例与私有订阅入口
personas/       Persona 评分提示词
tests/          数据管线与安全测试
skills/         Agent 消费和维护 Skill
```

## 本地运行

Windows PowerShell：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m pytest -q
python scripts\quality_gate.py --data-dir data
python scripts\build_public_site.py --data-dir data --output-dir dist
python -m http.server 8080 --directory dist
```

打开 `http://127.0.0.1:8080/`。

## 更新数据

免费公开源可以直接运行：

```powershell
python scripts\update_news.py `
  --output-dir data `
  --window-hours 24 `
  --archive-days 21 `
  --rss-opml feeds\follow.example.opml `
  --rss-max-feeds 10

python scripts\persona_score.py --data-dir data
python scripts\sanitize_public_data.py --data-dir data
python scripts\quality_gate.py --data-dir data --max-age-hours 6
python scripts\build_public_site.py --data-dir data --output-dir dist
```

私人订阅请复制 `feeds/follow.example.opml` 为 `feeds/follow.opml`。该文件已被 Git 忽略。

## 可选配置

以下能力通过环境变量或 GitHub Secrets 开启：

- `DEEPSEEK_API_KEY`：中文翻译、标题增强、推荐理由和 Persona 点评
- `SOCIALDATA_API_KEY`：X 搜索与账号列表
- `TIKHUB_API_KEY`：抖音与小红书搜索
- `X_BEARER_TOKEN`：X 官方 API
- `AGENTMAIL_API_KEY`、`AGENTMAIL_INBOX_ID`：Newsletter 邮箱摘要
- `FOLLOW_OPML_B64`：GitHub Actions 中的私有 OPML

密钥不得写入代码、公开 OPML 或 `data/*.json`。

## 部署

仓库内的 `.github/workflows/update-news.yml` 默认每小时第 17 分钟运行。GitHub Pages 设置为：

```text
Settings → Pages → Source → GitHub Actions
```

也可以导入 Vercel；构建流程只发布 `dist/` 白名单产物。

## License

[MIT](LICENSE)。第三方资讯、文章、帖子和图片版权归原发布者所有，本站仅展示必要摘要与原文链接。
