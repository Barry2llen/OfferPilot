# OfferPilot

OfferPilot 是一个本地运行的 AI 求职助手单仓库项目，包含 FastAPI 后端、Next.js 前端和 Electron 桌面壳。当前能力覆盖简历文件上传与预览、模型供应商和模型选择配置、AI 同步/流式对话、LangGraph checkpoint 会话恢复，以及 Windows 桌面安装包构建。

**!!!项目还在开发当中!!!**

## 项目结构

```text
OfferPilot/
├── backend/   # FastAPI API、Agent、数据库、简历解析、pytest 测试
├── frontend/  # Next.js 16 Web UI、SSE 聊天、简历和设置页面
├── electron/  # Electron 桌面壳、托管进程、资源 staging、安装包构建
├── docs/      # 跨项目技术文档
└── LICENSE
```

三个子项目目前保持依赖和命令独立：

- `backend/` 使用 Python `>=3.13` 和 `uv`。
- `frontend/` 使用 Node.js、npm、Next.js 16、React 19。
- `electron/` 使用 Node.js、npm、Electron、Vite、Electron Builder。

## 核心功能

- 简历管理：上传解析、替换解析、列表、详情、删除和原文件预览；支持 PDF、DOCX、PNG、JPG、JPEG。
- 模型配置：维护模型供应商、API Key、Base URL 和具体模型选择；响应不回显 API Key 明文。
- AI 对话：提供 `/ai/chat` 同步对话和 `/ai/chat/stream` SSE 流式对话。
- Agent 运行：基于 LangChain/LangGraph，支持工具调用、失败 interrupt/retry 和数据库 checkpoint。
- 桌面运行：Electron 开发模式自动启动后端和前端，打包后从 Electron resources 启动本地服务。

## 环境要求

- Python `>=3.13`
- `uv`
- Node.js 和 npm
- Windows 安装包构建需要 Electron Builder 与后端 PyInstaller 打包依赖

后端默认使用 SQLite，不需要额外数据库服务。PostgreSQL 配置已预留，可在 `backend/config.yaml` 中启用。

## 本地开发

### 1. 启动后端

```sh
cd backend
uv sync
uv run uvicorn main:app --reload --host 127.0.0.1 --port 8080
```

后端默认读取 `backend/config.yaml`。如果需要新建本地配置，可参考 `backend/config.example.yaml`。默认 SQLite 数据库位于 `backend/data/offer_pilot.db`，简历文件位于 `backend/data/resumes`。

启动后可访问：

- API 探活：`http://127.0.0.1:8080/`
- Swagger 文档：`http://127.0.0.1:8080/docs`
- OpenAPI JSON：`http://127.0.0.1:8080/openapi.json`

### 2. 启动前端

```sh
cd frontend
npm install
npm run dev
```

前端默认访问 `NEXT_PUBLIC_API_URL`，未配置时使用 `http://localhost:8080`。本地访问地址通常是 `http://localhost:3000`。

### 3. 启动 Electron 桌面壳

```sh
cd electron
npm install
npm run dev
```

Electron 开发模式会自动查找相邻的 `backend/` 和 `frontend/`，选择可用 localhost 端口启动两个子进程，并把后端 API 地址注入给前端。

如果子项目不在默认位置，可设置：

```sh
OFFER_PILOT_BACKEND_DIR=/path/to/backend
OFFER_PILOT_FRONTEND_DIR=/path/to/frontend
```

PowerShell 示例：

```powershell
$env:OFFER_PILOT_BACKEND_DIR="C:\projects\OfferPilot\backend"
$env:OFFER_PILOT_FRONTEND_DIR="C:\projects\OfferPilot\frontend"
npm run dev
```

## 常用命令

后端：

```sh
cd backend
uv sync
uv run pytest
uv run pytest tests/unit/test_ai_api.py
uv run pytest tests/unit/test_resume_api.py
```

前端：

```sh
cd frontend
npm run lint
npm run build
```

Electron：

```sh
cd electron
npm run lint
npm run build:electron
npm run build
```

在 `electron/` 目录运行 `npm run build` 会依次构建前端 standalone bundle、用 PyInstaller 打包后端、构建 Electron/Vite 输出，并生成 Windows x64 NSIS 安装包。

## 运行配置

后端主要配置项位于 `backend/config.example.yaml`：

- `database`：默认 SQLite，路径 `./data/offer_pilot.db`；可切换 PostgreSQL。
- `resume_upload_dir`：默认 `./data/resumes`。
- `cors`：本地开发默认允许跨域。
- `exa_api_key`：存在时启用 Exa Web Search 工具；缺失时禁用相关工具。
- `web_search`、`model_call_retry_attempts`、`debug`：用于 Agent 工具、重试和调试行为。

前端运行时配置：

- `NEXT_PUBLIC_API_URL`：后端 API 基础地址。
- `window.offerPilotRuntime.apiBaseUrl`：Electron preload 注入的运行时覆盖地址。

Electron 打包后会在 Electron `userData` 下创建后端运行时目录，包括 `config.yaml`、SQLite 数据库、简历上传目录和日志。

## API 概览

- `/resumes`：简历上传解析、列表、详情、替换解析、删除和预览。
- `/model-providers`：模型供应商配置 CRUD。
- `/model-selections`：模型选择配置 CRUD。
- `/ai/chat`：同步 AI 对话。
- `/ai/chat/stream`：SSE 流式 AI 对话。

AI 对话流式事件包括 `thread`、`token`、`tool_start`、`tool_end`、`tool_error`、`interrupt`、`final`、`error`。前端当前也支持展示 `reasoning` 类型事件。

简历上传和替换接口使用 `text/event-stream` 返回解析进度，事件包括 `resume`、`progress`、`model_error`、`final`、`error`，请求必须携带 `selection_id`。

客户端收到 `interrupt` 后，应使用同一个 `thread_id` 发送 `command.type="retry"` 恢复执行。

## 开发约定

- 根目录 `AGENTS.md` 描述总仓库规则；进入具体子项目后继续遵守对应子目录的 `AGENTS.md`。
- 后端接口或 schema 变化时，同步更新前端 `app/lib/api/` 类型和调用。
- SSE 协议变化时，同步更新后端事件输出、前端 `useChatStream()` 和相关 UI。
- 打包或资源目录变化时，同步更新 Electron scripts、Electron README 和本文件。
- 不要提交真实密钥、本地配置、数据库、日志、依赖目录或构建产物。

## 许可证

见 `LICENSE`。
