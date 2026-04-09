# RSS Web

> 将任意网页转换为可订阅的双语 RSS Feed

[English](#english) | [中文](#中文)

---

## 中文

### 项目简介

RSS Web 是一个个人自用的 RSS 转换服务。输入任意网页 URL 并配置抓取规则，系统会定时抓取文章列表与正文，支持 AI 双语翻译，生成标准 Atom RSS，可直接导入任意 RSS 阅读器订阅。

### 功能特性

- **双模式订阅**：支持网页抓取和标准 RSS/Atom 源两种订阅类型
- **自由订阅**：输入目标页面 URL + CSS Selector，抓取任意网站的文章列表
- **智能 Selector 推导**：粘贴两个示例文章的 Selector，自动推导通用规则
- **AI 双语翻译**：原文与译文段落交替排列，一眼读懂外文内容
- **多 AI 提供方**：支持 OpenRouter（推荐）、OpenAI、Google Gemini、Anthropic Claude、DeepSeek、Google 翻译（免费），可自定义模型
- **订阅导入导出**：支持 JSON 格式批量导入导出订阅配置
- **管理界面认证**：支持登录密码保护，默认密码 admin
- **标准 Atom RSS**：生成的 Feed 兼容所有主流阅读器（Reeder、NetNewsWire、Inoreader 等）
- **单容器部署**：SQLite 存储，零外部依赖，`docker compose up -d` 一键启动

### 快速开始

**使用 Docker（推荐）**

```bash
# 1. 创建 data 目录（存储数据库）
mkdir -p data

# 2. 启动服务
docker compose up -d

# 3. 访问
open http://localhost:8000
```

**本地开发**

```bash
pip install -r requirements-dev.txt
DATABASE_URL="sqlite:///./data/feeds.db" uvicorn app.main:app --reload --port 8000
```

**测试**

```bash
python -m pytest tests/ -v
```

### 使用方式

1. 打开 `http://localhost:8000`，点击「新建订阅」
2. 填入目标页面 URL，从浏览器开发者工具复制文章的 CSS Selector
3. 可选：在「AI 设置」中填入 API Key，启用双语翻译
4. 保存后，复制订阅链接添加到 RSS 阅读器

### 技术栈

| 层次 | 技术 |
|------|------|
| Web 框架 | FastAPI + Jinja2 + HTMX |
| 定时任务 | APScheduler |
| 数据库 | SQLite + SQLAlchemy |
| 页面抓取 | httpx + trafilatura + BeautifulSoup4 |
| RSS 生成 | feedgen（Atom 格式）|
| AI 翻译 | OpenAI / Gemini / Claude / DeepSeek |
| 部署 | Docker + docker-compose |

### 配置说明

所有配置通过页面「AI 设置」管理，无需修改配置文件：

- **API Key**：各 AI 提供方的密钥（保存后加密显示）
- **Base URL**：支持自定义代理地址，方便国内访问
- **翻译目标语言**：支持简体中文、繁体中文、日语、英语

---

## English

### Overview

RSS Web is a personal RSS conversion service. Provide a target page URL and CSS selector rules — the system periodically fetches article lists and content, optionally translates them with AI into bilingual format, and generates a standard Atom RSS feed compatible with any reader.

### Features

- **Dual subscription modes**: Web scraping or standard RSS/Atom sources
- **Subscribe to anything**: Fetch article lists from any website using URL + CSS selector
- **Smart selector derivation**: Paste two example selectors, auto-derive a universal rule
- **AI bilingual translation**: Original and translated paragraphs interleaved — read foreign content at a glance
- **Multiple AI providers**: OpenRouter (recommended), OpenAI, Google Gemini, Anthropic Claude, DeepSeek, Google Translate (free) — with custom model support
- **Import/Export**: Batch import/export feed configurations in JSON format
- **Authentication**: Password-protected admin interface (default: admin)
- **Standard Atom RSS**: Compatible with all major readers (Reeder, NetNewsWire, Inoreader, etc.)
- **Single-container deploy**: SQLite storage, zero external dependencies, one-command startup

### Quick Start

**Docker (recommended)**

```bash
# 1. Create the data directory
mkdir -p data

# 2. Start the service
docker compose up -d

# 3. Open in browser
open http://localhost:8000
```

**Or pull from Docker Hub**

```bash
docker run -d \
  -p 8000:8000 \
  -v $(pwd)/data:/data \
  --name rssweb \
  jxswcy/rssweb:latest
```

**Local development**

```bash
pip install -r requirements-dev.txt
DATABASE_URL="sqlite:///./data/feeds.db" uvicorn app.main:app --reload --port 8000
```

**Run tests**

```bash
python -m pytest tests/ -v
```

### Usage

1. Open `http://localhost:8000`, click "新建订阅" (New Feed)
2. Enter the target page URL and paste the CSS selector from browser DevTools
3. Optional: Go to "AI 设置" (AI Settings) and enter your API key to enable bilingual translation
4. Save and copy the RSS link into your feed reader

### Tech Stack

| Layer | Technology |
|-------|-----------|
| Web framework | FastAPI + Jinja2 + HTMX |
| Scheduler | APScheduler |
| Database | SQLite + SQLAlchemy |
| Scraping | httpx + trafilatura + BeautifulSoup4 |
| RSS generation | feedgen (Atom) |
| AI translation | OpenAI / Gemini / Claude / DeepSeek |
| Deployment | Docker + docker-compose |

### Configuration

All configuration is managed through the "AI 设置" page — no config files to edit:

- **API Keys**: Provider keys (masked after saving)
- **Base URL**: Custom proxy endpoints for each provider
- **Target language**: Simplified Chinese, Traditional Chinese, Japanese, English

### Privacy

- All data (feeds, articles, API keys) is stored locally in `./data/feeds.db`
- No telemetry, no external services beyond the AI APIs you configure
- API keys are stored in the local SQLite database only

---

## License

MIT

---

Built by [jxswcy](https://github.com/jxswcy)
