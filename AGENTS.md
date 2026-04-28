# OfferPilot 总仓库协作指南

## 基本要求

- 始终用中文回复用户。
- 修改代码前先阅读相关源码、配置和子项目文档，不要只凭经验改动。
- 工作区可能已有用户改动；不要回退、覆盖或格式化非本次任务涉及的内容。
- 本仓库由三个原独立项目合并而来，根目录只提供统一入口；进入具体子项目后，继续遵守该子目录下的 `AGENTS.md`。

## 仓库结构

- `backend/`：Python FastAPI 后端，负责简历文件管理、模型配置、AI 对话、LangGraph Agent、数据库和 checkpoint。
- `frontend/`：Next.js 16 前端，负责 Web UI、SSE 流式聊天、简历管理和模型配置页面。
- `electron/`：Electron 桌面壳，负责本地托管后端和前端进程、注入运行时 API 地址、构建桌面安装包。
- `docs/`：跨项目技术说明和设计记录。
- `.github/`、`.vscode/`：仓库级开发辅助配置。

生成目录、依赖目录、本地数据、日志和打包产物不应作为业务代码依赖，也不应提交：`.venv/`、`node_modules/`、`.next/`、`dist/`、`dist-electron/`、`release/`、`resources/`、`logs/`、`data/` 等。

## 后端约定

后端位于 `backend/`，技术栈是 Python `>=3.13`、FastAPI、Pydantic v2、SQLAlchemy 2.x、LangChain、LangGraph、SQLite/PostgreSQL、pytest。

- 使用 `uv` 管理依赖和执行命令。
- 应用入口是 `main.py`，`create_app()` 在 lifespan 中加载配置、初始化数据库、建表、创建 `DatabaseCheckpointer` 并装配 `SupervisorAgent`。
- API 路由位于 `api/routes/`，服务逻辑位于 `services/`，数据访问位于 `db/repositories/`，ORM 位于 `db/models/`，对外结构位于 `schemas/`。
- API 层不要直接写 ORM 逻辑；Agent 节点不要直接处理 HTTP 细节；配置解析不要混入业务服务。
- FastAPI 路由应维护 `summary`、`description`、`response_description` 和主要错误响应说明。
- 对外 Pydantic schema 的公开字段应补充 `Field(..., description=..., examples=...)`。
- `/ai/chat/stream` 的 SSE 事件名需要保持稳定：`thread`、`token`、`tool_start`、`tool_end`、`tool_error`、`interrupt`、`final`、`error`。前端当前也处理 `reasoning` 事件，修改流式协议时必须同步前端类型和解析逻辑。
- 修改接口、请求体、响应体、SSE 事件、配置结构、数据库结构或模型接入方式时，同步更新 OpenAPI 描述、测试和必要文档。

常用命令：

```sh
cd backend
uv sync
uv run uvicorn main:app --reload --host 127.0.0.1 --port 8080
uv run pytest
```

## 前端约定

前端位于 `frontend/`，技术栈是 Next.js `16.2.3` App Router、React 19、TypeScript strict、Tailwind CSS v4。

- 涉及 Next.js 行为时，先查 `node_modules/next/dist/docs/` 中对应文档；不要按旧版 Next.js 经验直接改。
- 入口和路由在 `app/` 下，没有 `src/` 或 `pages/` 目录。
- 默认保留服务端组件；只有使用 state、effect、事件处理、浏览器 API、React context 或客户端 hook 时才加 `"use client"`。
- 共享 UI 优先复用 `app/components/ui/`，业务组件按 `chat/`、`resumes/`、`settings/` 分组。
- 后端 API 封装位于 `app/lib/api/`；新增或修改后端字段时，同步更新 `app/lib/api/types.ts` 和对应 API 模块。
- 全局应用状态通过 `AppProvider` 管理，不要为当前线程、模型选择、Agent 状态另建平行全局状态。
- SSE 聊天由 `aiChatApi.streamChat()` 和 `useChatStream()` 处理，不要在页面中重复实现解析。
- UI 文案以中文为主，保持后台工具风格：紧凑、清晰、可扫描。

常用命令：

```sh
cd frontend
npm install
npm run dev
npm run lint
npm run build
```

## Electron 约定

Electron 项目位于 `electron/`，技术栈是 Electron、Vite、React 18、TypeScript、Electron Builder。

- `electron/main.ts` 负责单实例、托管后端/前端子进程、日志、窗口生命周期和打包运行时配置。
- `electron/preload.ts` 只暴露最小运行时桥接：`window.offerPilotRuntime.apiBaseUrl`。
- 开发模式默认查找相邻 `../backend` 和 `../frontend`；如目录不在默认位置，使用 `OFFER_PILOT_BACKEND_DIR` 和 `OFFER_PILOT_FRONTEND_DIR`。
- 生产模式期望资源位于 `resources/backend/offer-pilot-api` 和 `resources/frontend`，由 `scripts/prepare-backend.mjs` 与 `scripts/prepare-frontend.mjs` staging。
- 必须保留 `contextIsolation: true` 和 `nodeIntegration: false`，不要通过 preload 暴露 Node 原语。
- 修改打包、资源 staging、运行时配置或端口发现逻辑时，同步更新 Electron README 和根 README。

常用命令：

```sh
cd electron
npm install
npm run dev
npm run lint
npm run build:electron
npm run build
```

## 跨项目变更规则

- 后端接口变化：同步后端 schema/OpenAPI、前端 `app/lib/api/*` 类型与调用、相关页面状态处理和测试。
- SSE 协议变化：同步后端事件输出、前端 `SSEEventType`、`useChatStream()`、聊天 UI 状态和相关测试。
- 模型配置变化：同步后端模型 provider/selection schema、服务层、前端设置页和 Electron 运行时配置说明。
- 简历能力变化：同步后端解析/预览服务、前端简历页、上传/替换/删除交互和文档。
- 打包流程变化：同步 Electron scripts、`electron-builder.json5`、资源目录约定和 README。
- 仅修改文档时不强制运行构建；修改代码时运行对应子项目最窄必要检查。

## 配置与安全

- 不要提交真实 API Key、`.env`、本地 `config.yaml`、数据库文件、日志或打包二进制。
- 后端默认配置模板是 `backend/config.example.yaml`，默认 SQLite 路径为 `./data/offer_pilot.db`，简历上传目录为 `./data/resumes`。
- 前端 API 地址来自 `NEXT_PUBLIC_API_URL`，浏览器运行时可由 `window.offerPilotRuntime?.apiBaseUrl` 覆盖。
- Electron 打包后会在 Electron `userData` 下创建后端运行时配置、SQLite 数据、简历上传目录和日志。

## 提交与验证

- 后端代码修改后优先运行相关定向 `uv run pytest ...`，跨模块或基础设施变更运行 `uv run pytest`。
- 前端 TypeScript/React 修改后至少运行 `npm run lint`；涉及路由、构建配置或服务端/客户端边界时运行 `npm run build`。
- Electron 修改后至少运行 `npm run lint`；涉及打包或托管进程时运行对应 build 命令。
- PR 或变更说明应包含目的、影响模块、运行过的命令，以及是否涉及配置、数据库、接口协议、SSE 或打包流程。
