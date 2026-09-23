# DocDiff HIZ · 文件比对专家

海致星图面试作业：上传两份 PDF，自动完成段落级比对、字符级 diff 高亮、结构化审阅报告，并支持基于差异内容的对话问答。

---

## 一、功能清单

| 能力 | 说明 |
|------|------|
| 双 PDF 上传 | 旧版 / 新版，点击或拖拽 |
| 段落级配对 | 滑动窗口 + 相似度匹配，输出「一致 / 修改 / 新增 / 删除」四类 |
| 字符级 diff | 修改段落逐字高亮（红删绿增），**参考实现没有这一层** |
| 结构化报告 | 综合审核结论 + 规则统计 + 规则引擎分析 + 逐条差异明细 |
| 大模型审阅意见 | 本地 Ollama 生成 200 字审阅意见，从「改了什么」上升到「风险在哪」 |
| 差异问答 | 针对比对结果追问，回答带 `[序号]` 引用溯源 |
| 会话历史持久化 | 每次比对自动建会话，消息、报告、结论全部落盘（`data/sessions/`，JSON + 原子写入），服务重启不丢；侧边栏「审核历史」可查看、关键词检索、一键恢复、删除 |
| 异源文档兜底 | 两份文档无对应关系时不给假结论，给出相关度与建议 |
| 离线可用 | 模型不在线时自动降级到规则引擎，系统不阻塞 |

## 二、技术选型

| 层 | 选型 | 理由 |
|---|---|---|
| Web | FastAPI + Pydantic v2 | 异步、类型安全，能快速把接口跑通 |
| PDF 解析 | Docling（优先）/ pypdf（兜底） | Docling 输出结构化 Markdown，保留标题层级；缺失时降级 pypdf 保证可用 |
| 比对 | difflib + 滑动窗口 | 纯本地计算，不依赖 embedding 模型，速度可控 |
| 大模型 | OpenAI 兼容接口，默认指向本地 Ollama | 无需联网、无需 Key，也能一行配置切到云端 |
| 前端 | 原生 HTML/CSS/JS | 零构建，打开即用 |

## 三、快速开始

### 1. 创建环境并安装

```bash
cd docdiff-hiz
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

> `-e .[dev]` 会自动装 FastAPI / pypdf / pytest / ruff 等轻量依赖。
> Docling 依赖较重（会拉 torch），单独安装：`.venv\Scripts\python.exe -m pip install -e ".[docling]"`

### 2. 配置大模型（默认本地 Ollama）

```bash
cp .env.example .env
```

`.env` 默认内容即为本地 Ollama：

```env
LLM_BASE_URL=http://localhost:11434/v1
LLM_API_KEY=ollama
LLM_MODEL=qwen3.5:9b
LLM_TIMEOUT=300
LLM_ENABLED=true
```

确认本地模型就绪：

```bash
ollama list
ollama pull qwen3.5:9b   # 如未拉取
```

切云端只要改这三行（示例）：

```env
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=sk-xxx
LLM_MODEL=gpt-4o-mini
```

### 3. 生成示例 PDF（可选，演示用）

```bash
.venv\Scripts\python.exe scripts\make_samples.py
```

会生成同一份技术规格说明书的新旧两个版本，直接拿去演示即可。

### 4. 离线自检（不启动服务，先确认链路通）

```bash
.venv\Scripts\python.exe scripts\verify_pipeline.py
```

### 5. 启动服务

```bash
.venv\Scripts\python.exe -m uvicorn docdiff.main:app --app-dir src --reload --port 8000
```

或直接双击 `run.bat`。打开 http://127.0.0.1:8000

### 6. 环境自检接口

```
GET http://127.0.0.1:8000/api/health
```

返回解析器与模型的可用状态，演示前先看一眼就绪情况。

## 四、项目结构

```
docdiff-hiz/
├── src/docdiff/
│   ├── main.py                  # FastAPI 入口
│   ├── config.py                # pydantic-settings 配置
│   ├── api/routes.py            # REST 路由
│   ├── models/schemas.py        # Pydantic 模型
│   ├── services/
│   │   ├── pdf_parser.py        # PDF 解析（Docling 优先，pypdf 兜底）
│   │   ├── diff_engine.py       # 段落配对 + 字符级 diff + 同源判定
│   │   ├── report_generator.py  # 规则引擎报告 + LLM 增强
│   │   ├── chat_service.py      # 差异问答
│   │   ├── llm_client.py        # OpenAI 兼容客户端 + Ollama 原生加速
│   │   └── history_store.py     # 会话历史持久化（JSON 文件 + 原子写入）
│   └── static/                  # 前端（index.html / style.css / app.js）
├── scripts/
│   ├── make_samples.py          # 生成示例 PDF
│   ├── verify_pipeline.py       # 离线全链路自检（后端）
│   ├── verify_history_api.py    # 会话持久化链路自检（进程内 TestClient）
│   ├── verify_demo.cjs          # 离线 Demo 内联引擎自检（两套场景）
│   └── verify_demo_ui.cjs       # 离线 Demo 交互自检（jsdom 点完整流程）
├── tests/                       # pytest 单元测试
├── data/sessions/               # 会话存档（自动生成，每会话一个 JSON）
├── samples/
│   ├── 技术规格说明书_Rev01.pdf  # 示例旧版
│   ├── 技术规格说明书_Rev03.pdf  # 示例新版
│   ├── 示例比对报告.md            # 后端真跑出来的报告样例
│   └── ui-demo.html             # ★ 可点击的离线前端 Demo（双击即用）
├── pyproject.toml
├── Makefile / run.bat
├── .env.example
├── 交付说明.md                   # 交付说明 + 已知不足 + 想请教的问题（对外）
└── implementation.md            # 实现思路（架构 / 选型 / 踩坑 / 扩展）
```

## 五、前端

前端是 `src/docdiff/static/` 下的原生三件套（`index.html` / `style.css` / `app.js`），由 FastAPI 直接托管，无构建步骤。
页面分三个视图：**上传区 → 结果概览（统计徽章 + 结论 + 差异问答）→ 详细报告**，与参考实现的多专家平台形态保持一致（左侧导航 + 面包屑 + 居中卡片）。

- **场景一，快速看界面**：直接双击 `samples/ui-demo.html`。这是自包含的单文件 Demo，不依赖后端、不依赖网络。内置两套示例场景（技术规格说明书 Rev01→Rev03、采购合同 v1→v2），点「开始对比」就能走完整个流程：统计徽章 → 综合结论 → 字符级红删绿增报告 → 差异问答（回答带 `[n]` 引用），侧边栏「审核历史」里的会话是真实存在浏览器本地的（刷新、关掉浏览器都不丢），支持搜索、恢复、删除。报告与问答都是实时算出来的，不是写死的假数据。
- **场景二，跑真实系统**：按第二节启动服务后访问 http://127.0.0.1:8000 ，此时上传的是真实 PDF，解析走 Docling/pypdf，报告走规则引擎 + 本地模型。

前端内联引擎与交互流程的自检（不需要浏览器）：

```bash
node scripts/verify_demo.cjs      # 引擎：两套场景各跑一遍，校验统计与报告
node scripts/verify_demo_ui.cjs   # 交互：用 jsdom 点完比对→问答→历史→恢复→删除
```

> `verify_demo_ui.cjs` 依赖 jsdom，未随项目安装。需要时在项目外单独装：
> `npm install jsdom`，运行时加 `NODE_PATH=<node_modules 路径>`。
> 只跑 `verify_demo.cjs` 不需要任何依赖。

## 六、接口一览

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查 + 环境自检 |
| POST | `/api/compare` | 上传两份 PDF，返回结构化差异（multipart），**自动创建持久化会话** |
| POST | `/api/report` | 传入比对结果，生成 HTML / Markdown 报告，并回存到会话 |
| POST | `/api/chat` | 基于差异上下文问答，问答双方（含时间戳）追加进会话 |
| GET | `/api/sessions?q=` | 会话列表（按更新时间倒序），`q` 按标题/结论/对话内容全文检索 |
| GET | `/api/sessions/{id}` | 会话完整内容（比对结果 + 报告 + 全部消息），用于恢复 |
| DELETE | `/api/sessions/{id}` | 删除会话 |
| POST | `/api/compare-and-report` | 上传后直接返回完整 HTML 报告页 |

## 七、测试

```bash
.venv\Scripts\python.exe -m pytest -v
```

覆盖：段落相似/修改/新增删除识别、同源版本对不误判、异源文档兜底、离线规则报告结构、会话持久化（创建/追加/检索/删除/非法 ID 拒绝/列表排序稳定性）。

会话链路端到端自检（进程内起应用，不起 Web 服务）：

```bash
.venv\Scripts\python.exe scripts\verify_history_api.py
```

离线 Demo 的自检见第五节（`verify_demo.cjs` / `verify_demo_ui.cjs`）。

## 八、注意事项

- **Docling 首次运行**会下载解析模型，需要几分钟；不想等可先不装，系统自动走 pypdf。
- **本地 9B 模型**：指向本机 Ollama 时自动走原生 `/api/chat` 并关闭思考模式（qwen3.5 这类思考型模型，问答从 ~40s 降到 ~2s）；换其他供应商自动回落 OpenAI 兼容接口。
- **模型不在线不会报错**：对话先做 3 秒快速探活，不在线直接返回规则检索结果，报告降级为规则引擎版本，主流程不阻塞。
- `.env` 含密钥，已在 `.gitignore` 中排除，不要提交。
