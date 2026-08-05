# OfferPilot

[English](README.md) · [简体中文](README.zh-CN.md)

OfferPilot is a locally hosted AI job-search assistant monorepo with a
FastAPI backend, a Vite + React SPA frontend, and an Electron desktop shell.
It supports resume upload and preview, model-provider and model-selection
configuration, synchronous and streaming AI conversations, reusable chat
attachments, LangGraph checkpoint recovery, and Windows desktop packaging.

## Project structure

```text
OfferPilot/
├── backend/   # FastAPI APIs, Agents, database, resume parsing, pytest tests
├── frontend/  # Vite + React web UI, SSE chat, resume and settings pages
├── electron/  # Electron shell, managed processes, resource staging, packaging
├── docs/      # Cross-project technical documentation
└── LICENSE
```

The three subprojects keep their dependencies and commands independent:

- `backend/` uses Python `>=3.13` and `uv`.
- `frontend/` uses Node.js, npm, Vite, React 19, and React Router.
- `electron/` uses Node.js, npm, Electron, Vite, and Electron Builder.

## Core features

- Resume management: upload, parse, replace, list, inspect, delete, and
  preview original files. PDF, DOCX, PNG, JPG, and JPEG are supported.
  Parsing runs in the backend so changing frontend routes does not cancel a
  task that has already started.
- Model configuration: manage providers, API keys, base URLs, and model
  selections without returning API keys in plaintext.
- AI conversations: `/ai/chat` for synchronous responses and
  `/ai/chat/stream` for SSE streaming, with text, image, PDF, DOCX, and common
  text-file attachments.
- File library: the frontend provides a file-library page and the backend
  exposes `/ai/files` endpoints for viewing and reusing historical chat
  attachments across conversations.
- Agent runtime: LangChain/LangGraph tool calls, interrupt/retry handling,
  and database checkpoints.
- Desktop runtime: Electron starts the backend and frontend in development and
  starts the local packaged service from Electron resources after packaging.

## Requirements

- Python `>=3.13`
- `uv`
- Node.js and npm
- Electron Builder and backend PyInstaller packaging dependencies for Windows
  installer builds

The backend uses SQLite by default and needs no additional database service.
PostgreSQL configuration is available in `backend/config.yaml`.

## Local development

### 1. Start the backend

```sh
cd backend
uv sync
uv run python run_server.py --reload --host 127.0.0.1 --port 8080
```

The backend reads `backend/config.yaml` by default. Use
`backend/config.example.yaml` as a template for a local configuration. The
default SQLite database is `backend/data/offer_pilot.db`; resumes are stored
under `backend/data/resumes`, and chat attachments under
`backend/data/chat_files`.

Once started:

- Health check: [http://127.0.0.1:8080/health](http://127.0.0.1:8080/health)
- Swagger UI: [http://127.0.0.1:8080/docs](http://127.0.0.1:8080/docs)
- OpenAPI JSON: [http://127.0.0.1:8080/openapi.json](http://127.0.0.1:8080/openapi.json)

If `frontend/dist` has been built, FastAPI also serves the React application
and deep-route fallback from [http://127.0.0.1:8080/](http://127.0.0.1:8080/).

### 2. Start the frontend

```sh
cd frontend
npm install
npm run dev
```

The frontend uses the current page's same-origin relative API path by default.
Without `VITE_API_URL`, Vite proxies API requests to
`VITE_API_PROXY_TARGET`, which defaults to `http://127.0.0.1:8080`.
The local frontend is usually available at
[http://127.0.0.1:3000](http://127.0.0.1:3000).

### 3. Start the Electron shell

```sh
cd electron
npm install
npm run dev
```

Electron development discovers sibling `backend/` and `frontend/`
directories, starts both processes on available localhost ports, and injects
the backend API address into the frontend.

If the subprojects are elsewhere, set:

```sh
OFFER_PILOT_BACKEND_DIR=/path/to/backend
OFFER_PILOT_FRONTEND_DIR=/path/to/frontend
```

PowerShell example:

```powershell
$env:OFFER_PILOT_BACKEND_DIR="C:\projects\OfferPilot\backend"
$env:OFFER_PILOT_FRONTEND_DIR="C:\projects\OfferPilot\frontend"
npm run dev
```

## Common commands

Backend:

```sh
cd backend
uv sync
uv run pytest
uv run pytest tests/unit/test_ai_api.py
uv run pytest tests/unit/test_resume_api.py
```

Frontend:

```sh
cd frontend
npm run lint
npm run typecheck
npm run build
```

Electron:

```sh
cd electron
npm run lint
npm run build:electron
npm run build
```

Running `npm run build` in `electron/` builds and stages `frontend/dist`,
packages the backend with PyInstaller, builds the Electron/Vite output, and
generates a Windows x64 NSIS installer. The packaged application starts only
FastAPI; FastAPI serves the frontend static files.

## Windows releases

Windows releases are managed by
`.github/workflows/build-windows-release.yml` through the `Release` workflow.
Run version bumps from the `main` branch in GitHub Actions:

1. Select `bump-patch`, `bump-minor`, or `bump-major`.
2. Review and merge the generated `release/vX.Y.Z` pull request.
3. The merge creates tag `vX.Y.Z`, builds the Windows x64 NSIS installer, and
   publishes a GitHub Release with automatically generated notes.

The bump keeps the root project, frontend, Electron shell, lockfiles, and
sidebar version labels synchronized. The backend package version is managed
independently. To rebuild an existing release asset, run the same workflow with
`build-windows` and enter the existing version as `X.Y.Z` without the leading
`v`. The uploaded asset is named `OfferPilot-Windows-x64-vX.Y.Z.exe`.

## Runtime configuration

Backend configuration is documented in `backend/config.example.yaml`:

- `database`: SQLite by default at `./data/offer_pilot.db`, with optional
  PostgreSQL support.
- `resume_upload_dir`: defaults to `./data/resumes`.
- `chat_file_upload_dir`: defaults to `./data/chat_files` for AI
  attachments and the file library.
- `cors`: cross-origin requests are allowed by default for local development.
- `exa_api_key`: enables the Exa Web Search tool when present; related tools
  are disabled when it is absent.
- `web_search`, `model_call_retry_attempts`,
  `graph_recursion_limit`, and `debug`: configure Agent tools, retries,
  LangGraph recursion limits, and debugging.

Frontend and static-hosting runtime settings:

- `VITE_API_URL`: backend API base URL at build time; same-origin relative
  paths are used when unset.
- `VITE_API_PROXY_TARGET`: Vite development API proxy target, defaulting to
  `http://127.0.0.1:8080`.
- `window.offerPilotRuntime.apiBaseUrl`: runtime override injected by the
  Electron preload bridge.
- `OFFER_PILOT_FRONTEND_DIST`: FastAPI frontend directory override. It
  defaults to the repository's `frontend/dist`; Electron production passes
  `resources/frontend` with `--frontend-dist`.

After packaging, Electron reads backend configuration from
`~/.offerpilot/config.yaml`. On first launch it creates default
configuration, SQLite data, resume-upload, and backend runtime-log
directories under `~/.offerpilot`. Managed-process stdout/stderr remains
under Electron's `userData/logs`.

## API overview

- `/resumes`: resume upload/parsing, list, detail, replacement, deletion,
  and preview.
- `/model-providers`: model-provider configuration CRUD.
- `/model-selections`: model-selection configuration CRUD.
- `/ai/chat`: synchronous AI conversation.
- `/ai/chat/stream`: streaming AI conversation over SSE.
- `/ai/files`: chat-attachment library list, detail, and original-file
  access.

AI streaming events include `thread`, `token`, `tool_start`,
`tool_end`, `tool_error`, `interrupt`, `final`, and `error`. The
frontend also supports `reasoning` events. A `thread` event can include
`resolved_attachments`, `attachment_count`, and
`requires_image_input`, which let the frontend restore formal file IDs and
show a non-blocking notice when an image-attachment thread switches to a
text-only model.

Resume upload and replacement endpoints return parsing progress as
`text/event-stream` events: `resume`, `progress`, `model_error`,
`final`, and `error`. Requests must include `selection_id`. Disconnecting
an SSE connection does not cancel parsing; the persisted parsing status from
the list/detail endpoints is authoritative.

After receiving an `interrupt`, the client should send
`command.type="retry"` with the same `thread_id` to resume execution.

The frontend supports Simplified Chinese and English. The initial locale uses
the persisted user choice, then the browser/system language, and falls back to
Simplified Chinese. REST and SSE requests send `Accept-Language`; the backend
returns matching `Content-Language` and localizes known errors and temporary
progress messages. AI output, user input, and source documents remain
unchanged.

## Development conventions

- The root `AGENTS.md` contains repository-wide rules; follow the relevant
  subproject guide after entering a subproject.
- When backend APIs or schemas change, update frontend types and calls under
  `app/lib/api/`.
- When the SSE protocol changes, update backend event output,
  `useChatStream()`, and related UI together.
- When packaging or resource directories change, update Electron scripts,
  Electron documentation, and this README.
- Never commit real keys, local configuration, databases, logs, dependency
  directories, or build artifacts.

## License

See `LICENSE`.
