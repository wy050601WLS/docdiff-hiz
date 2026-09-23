# DocDiff HIZ 文件比对专家

海致星图面试作业。上传两份 PDF，自动完成段落级比对、字符级 diff 高亮、结构化审阅报告，并支持基于差异内容的对话问答。

## 功能

- 双 PDF 上传，点击或拖拽都行
- 段落级配对，滑动窗口加相似度匹配，输出一致、修改、新增、删除四类
- 字符级 diff，修改段落逐字高亮，红删绿增。参考实现没有这一层
- 原文对照与定位，每个差异项标出新旧版所在页码，双栏对回原文，问答里的 [序号] 点了直接跳到该条
- 结构化报告，包含综合审核结论、规则统计、规则引擎分析、逐条差异明细
- 大模型审阅意见，本地 Ollama 生成约 200 字，从改了什么上升到风险在哪
- 差异问答，回答带 [序号] 引用，可以回溯到具体的差异项
- 会话历史持久化。每次比对自动建会话，消息、报告、结论全部落盘到 data/sessions，JSON 加原子写入，服务重启不丢。侧边栏的审核历史可以查看、按关键词检索、一键恢复、删除
- 异源文档兜底，两份文档没有对应关系时不给假结论，给出相关度与建议
- 离线可用，模型不在线时自动降级到规则引擎，系统不阻塞

## 技术选型

Web 层用 FastAPI 加 Pydantic v2，异步、类型安全，接口能很快跑通。

PDF 解析优先用 Docling，它能输出结构化 Markdown、保留标题层级。缺失时降级到 pypdf，保证可用。

比对用 difflib 加滑动窗口，纯本地计算，不依赖 embedding 模型，速度可控。

大模型走 OpenAI 兼容接口，默认指向本地 Ollama，无需联网、无需 Key，也能一行配置切到云端。

前端是原生 HTML/CSS/JS，零构建，打开即用。

## Docker 部署

一条命令起全套，应用加本地大模型一起编排，不用在本机装 Python 和 Ollama。

```bash
docker compose up -d --build
docker compose exec ollama ollama pull qwen3.5:9b   # 首次拉模型，几分钟
```

打开 http://127.0.0.1:8000 。会话存档挂在 `session-data` 卷上，容器重建不丢。

不想要大模型就只起应用（`--no-deps` 不拉 Ollama），并在 environment 里加 `LLM_ENABLED: "false"`，报告自动走规则引擎版本。

```bash
docker compose up -d --build --no-deps app
```

默认镜像只装轻量依赖（pypdf 解析）。要 Docling 结构化解析就带构建参数，镜像会大很多，因为要拉 torch。

```bash
docker compose build --build-arg WITH_DOCLING=true app
```

常用操作：

```bash
docker compose logs -f app       # 看日志
docker compose exec app python -c "import httpx;print(httpx.get('http://127.0.0.1:8000/api/health').json())"
docker compose down              # 停掉，卷保留
```

## 快速开始（本地）

### 创建环境并安装

```bash
cd docdiff-hiz
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

`-e .[dev]` 会装 FastAPI、pypdf、pytest、ruff 这些轻量依赖。Docling 依赖较重，会拉 torch，需要单独安装。

```bash
.venv\Scripts\python.exe -m pip install -e ".[docling]"
```

### 配置大模型

默认配置就是本机 Ollama，复制一份即可。

```bash
cp .env.example .env
```

默认内容如下。

```env
LLM_BASE_URL=http://localhost:11434/v1
LLM_API_KEY=ollama
LLM_MODEL=qwen3.5:9b
LLM_TIMEOUT=300
LLM_ENABLED=true
```

确认本地模型就绪。

```bash
ollama list
ollama pull qwen3.5:9b
```

要切云端就改这三行，例如：

```env
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=sk-xxx
LLM_MODEL=gpt-4o-mini
```

### 生成示例 PDF（可选，演示用）

```bash
.venv\Scripts\python.exe scripts\make_samples.py
```

会生成同一份技术规格说明书的新旧两个版本，直接拿去演示即可。

### 先跑一遍离线自检

不启动服务，先确认链路是通的。

```bash
.venv\Scripts\python.exe scripts\verify_pipeline.py
```

### 启动服务

```bash
.venv\Scripts\python.exe -m uvicorn docdiff.main:app --app-dir src --reload --port 8000
```

或者直接双击 run.bat，然后打开 http://127.0.0.1:8000 。

演示前可以先看一眼环境自检接口，它会返回解析器与模型的可用状态。

```
GET http://127.0.0.1:8000/api/health
```

## 项目结构

```
docdiff-hiz/
├── src/docdiff/
│   ├── main.py                  # FastAPI 入口
│   ├── config.py                # pydantic-settings 配置
│   ├── api/routes.py            # REST 路由
│   ├── models/schemas.py        # Pydantic 模型
│   ├── services/
│   │   ├── pdf_parser.py        # PDF 解析，Docling 优先，pypdf 兜底
│   │   ├── diff_engine.py       # 段落配对 + 字符级 diff + 同源判定
│   │   ├── report_generator.py  # 规则引擎报告 + LLM 增强
│   │   ├── chat_service.py      # 差异问答
│   │   ├── llm_client.py        # OpenAI 兼容客户端 + Ollama 原生加速
│   │   └── history_store.py     # 会话历史持久化，JSON 文件 + 原子写入
│   └── static/                  # 前端，index.html / style.css / app.js
├── scripts/
│   ├── make_samples.py          # 生成示例 PDF
│   ├── verify_pipeline.py       # 离线全链路自检，后端
│   ├── verify_history_api.py    # 会话持久化链路自检，进程内 TestClient
│   ├── verify_demo.cjs          # 离线 Demo 内联引擎自检，两套场景
│   └── verify_demo_ui.cjs       # 离线 Demo 交互自检，jsdom 点完整流程
├── tests/                       # pytest 单元测试
├── data/sessions/               # 会话存档，自动生成，每会话一个 JSON
├── samples/
│   ├── 技术规格说明书_Rev01.pdf  # 示例旧版
│   ├── 技术规格说明书_Rev03.pdf  # 示例新版
│   ├── 示例比对报告.md            # 后端真跑出来的报告样例
│   └── ui-demo.html             # 可点击的离线前端 Demo，双击即用
├── pyproject.toml
├── Dockerfile / docker-compose.yml / .dockerignore
├── Makefile / run.bat
├── .env.example
├── 交付说明.md                   # 交付说明与已知不足，对外
└── implementation.md            # 实现思路，架构 / 选型 / 踩坑 / 扩展
```

## 前端

前端是 src/docdiff/static 下的原生三件套，由 FastAPI 直接托管，没有构建步骤。页面分三个视图，上传区、结果概览（统计徽章加结论加差异问答）、详细报告。形态上与参考实现的多专家平台保持一致，左侧导航加面包屑加居中卡片。

有两种看法。

一种是直接双击 samples/ui-demo.html，快速看界面。这是自包含的单文件 Demo，不依赖后端，也不依赖网络。内置两套示例场景，技术规格说明书 Rev01 到 Rev03，采购合同 v1 到 v2。点开始对比就能走完整个流程，统计徽章、综合结论、字符级红删绿增报告、差异问答，回答里带 [n] 引用。侧边栏审核历史里的会话是真实存在浏览器本地的，刷新、关掉浏览器都不丢，支持搜索、恢复、删除。报告与问答都是实时算出来的，不是写死的假数据。

另一种是按上面的步骤启动服务，访问 http://127.0.0.1:8000 。这时上传的是真实 PDF，解析走 Docling 或 pypdf，报告走规则引擎加本地模型。

前端内联引擎与交互流程的自检不需要浏览器。

```bash
node scripts/verify_demo.cjs      # 引擎，两套场景各跑一遍，校验统计与报告
node scripts/verify_demo_ui.cjs   # 交互，用 jsdom 点完比对、问答、历史、恢复、删除
```

verify_demo_ui.cjs 依赖 jsdom，没有随项目安装，需要时在项目外单独安装，运行时把 NODE_PATH 指到对应的 node_modules 上。只跑 verify_demo.cjs 不需要任何依赖。

## 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查与环境自检 |
| POST | `/api/compare` | 上传两份 PDF，返回结构化差异，multipart，同时自动创建持久化会话 |
| POST | `/api/report` | 传入比对结果，生成 HTML / Markdown 报告，并回存到会话 |
| POST | `/api/chat` | 基于差异上下文问答，问答双方连时间戳一起追加进会话 |
| GET | `/api/sessions?q=` | 会话列表，按更新时间倒序。q 按标题、结论、对话内容全文检索 |
| GET | `/api/sessions/{id}` | 会话完整内容，含比对结果、报告、全部消息，用于恢复 |
| DELETE | `/api/sessions/{id}` | 删除会话 |
| POST | `/api/compare-and-report` | 上传后直接返回完整 HTML 报告页 |

## 测试

```bash
.venv\Scripts\python.exe -m pytest -v
```

覆盖了段落相似、修改、新增删除识别，同源版本对不误判，异源文档兜底，离线规则报告结构，以及会话持久化的创建、追加、检索、删除、非法 ID 拒绝、列表排序稳定性。

会话链路也可以端到端自检，进程内起应用，不用起 Web 服务。

```bash
.venv\Scripts\python.exe scripts\verify_history_api.py
```

离线 Demo 的自检见上面前端那一节。

## 注意事项

- Docling 首次运行会下载解析模型，需要几分钟。不想等可以先不装，系统自动走 pypdf。
- 指向本机 Ollama 时会自动走原生 /api/chat 并关闭思考模式，qwen3.5 这类思考型模型的问答从约 40 秒降到约 2 秒。换其他供应商会自动回落 OpenAI 兼容接口。
- 模型不在线不会报错。对话前先做 3 秒快速探活，不在线直接返回规则检索结果，报告降级为规则引擎版本，主流程不阻塞。
- .env 含密钥，已在 .gitignore 里排除，不要提交。
