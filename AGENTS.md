# OfferPilot Repository Collaboration Guide

## General requirements

- Read the relevant source, configuration, and subproject documentation before changing code.
- The worktree may contain user changes. Do not revert, overwrite, or format changes outside the current task.
- This repository combines three formerly independent projects. The root provides shared entry points; after entering a subproject, continue following that directory's `AGENTS.md`.

## Repository structure

- `backend/`: Python FastAPI backend for resume files, model configuration, AI chat, LangGraph agents, database access, and checkpoints.
- `frontend/`: Vite + React SPA for the web UI, SSE chat, resume management, and model configuration.
- `electron/`: Electron desktop shell that hosts the backend and frontend processes, injects the runtime API URL, and builds installers.
- `docs/`: Cross-project technical documentation and design notes.
- `.github/` and `.vscode/`: Repository development helpers.

Generated directories, dependency directories, local data, logs, and packaging output must not be committed: `.venv/`, `node_modules/`, `dist/`, `dist-electron/`, `release/`, `resources/`, `logs/`, `data/`, and similar paths.

## Backend conventions

The backend is under `backend/` and uses Python `>=3.13`, FastAPI, Pydantic v2, SQLAlchemy 2.x, LangChain, LangGraph, SQLite/PostgreSQL, and pytest.

- Use `uv` to manage dependencies and run commands.
- The application entry point is `main.py`. `create_app()` loads configuration, initializes databases, creates tables, creates `DatabaseCheckpointer`, and assembles `SupervisorAgent` during the lifespan.
- API routes live in `api/routes/`, business logic in `services/`, data access in `db/repositories/`, ORM models in `db/models/`, and public contracts in `schemas/`.
- Do not put ORM logic directly in API routes. Agent nodes must not handle HTTP details, and configuration parsing must stay out of business services.
- FastAPI routes must maintain `summary`, `description`, `response_description`, and important error responses.
- Public Pydantic fields should provide `Field(..., description=..., examples=...)`.
- `/ai/chat/stream` event names must remain stable: `thread`, `token`, `tool_start`, `tool_end`, `tool_error`, `interrupt`, `final`, and `error`. The frontend also handles `reasoning`; update the frontend types and parser when changing the stream protocol.
- API, request/response, SSE, configuration, database, or model integration changes must update OpenAPI descriptions, tests, and necessary documentation.
- In production FastAPI registers the business API, `/docs`, `/openapi.json`, and `/health`, then mounts `frontend/dist`. Deep-page navigation returns the SPA entry, missing static assets remain 404, and the API still starts when build output is absent.
- User-facing API and SSE messages must use the request locale. `Accept-Language` supports `en-US` and `zh-CN`; unknown or missing values fall back to `zh-CN`. Preserve user/model content and persisted technical details.

Common commands:

```sh
cd backend
uv sync
uv run uvicorn main:app --reload --host 127.0.0.1 --port 8080
uv run pytest
```

## Frontend conventions

The frontend is under `frontend/` and uses Vite, React 19, React Router, TypeScript strict mode, and Tailwind CSS v4.

- The static HTML entry is `index.html`, the application entry is `main.tsx`, and routes are centralized in `app/router.tsx`. `app/**/page.tsx` contains ordinary React page components rather than Next.js file conventions.
- Use `React.lazy` and `Suspense` for route loading; global errors use `app/components/layout/app-error-boundary.tsx`.
- Use React Router's `Link`, `useNavigate`, `useLocation`, and `useParams`; do not introduce Next.js routing or components.
- Reuse shared UI from `app/components/ui/`; group business components under `chat/`, `resumes/`, and `settings/`.
- Backend API wrappers live in `app/lib/api/`. Update `app/lib/api/types.ts` and the relevant API module when backend fields change.
- Keep global application state in `AppProvider`; do not create parallel global state for the current thread, model selection, or Agent status.
- SSE chat is handled by `aiChatApi.streamChat()` and `useChatStream()`; do not duplicate parsing in pages.
- API URL precedence is `window.offerPilotRuntime.apiBaseUrl`, `VITE_API_URL`, then a same-origin relative path. Vite proxies API calls in development and FastAPI serves same-origin requests in production.
- All visible UI copy, accessibility labels, dates, and counts must use the bilingual i18n resources. Keep the interface compact, clear, and scannable in both locales.

Common commands:

```sh
cd frontend
npm install
npm run dev
npm run lint
npm run typecheck
npm run build
```

## Electron conventions

The Electron project is under `electron/` and uses Electron, Vite, React 18, TypeScript, and Electron Builder.

- `electron/main.ts` owns single-instance behavior, backend/frontend child processes, logging, window lifecycle, and packaged runtime configuration.
- `electron/preload.ts` exposes only the minimal runtime bridge: `window.offerPilotRuntime.apiBaseUrl`.
- Development mode looks for adjacent `../backend` and `../frontend`; use `OFFER_PILOT_BACKEND_DIR` and `OFFER_PILOT_FRONTEND_DIR` when they are elsewhere.
- Development starts FastAPI and Vite. Production starts only FastAPI and serves the Vite output through `--frontend-dist resources/frontend`.
- Packaged resources are expected at `resources/backend/offer-pilot-api` and `resources/frontend`, staged by `scripts/prepare-backend.mjs` and `scripts/prepare-frontend.mjs`.
- Preserve `contextIsolation: true` and `nodeIntegration: false`; never expose Node primitives through preload.
- Packaging, staging, runtime configuration, or port discovery changes must update the Electron README and root README.

Common commands:

```sh
cd electron
npm install
npm run dev
npm run lint
npm run build:electron
npm run build
```

## Cross-project change rules

- Backend API changes must update backend schemas/OpenAPI, frontend `app/lib/api/*` types and calls, related page state, and tests.
- SSE protocol changes must update backend event output, frontend `SSEEventType`, `useChatStream()`, chat UI state, and tests.
- Model configuration changes must update backend provider/selection schemas and services, the frontend settings page, and Electron runtime documentation.
- Resume changes must update backend parsing/preview services, the resume pages, upload/replace/delete interactions, and documentation.
- Packaging changes must update Electron scripts, `electron-builder.json5`, resource conventions, and README files.
- Documentation-only changes do not require a build; code changes require the narrowest necessary checks for the affected subproject.

## Configuration and security

- Never commit real API keys, `.env`, local `config.yaml`, database files, logs, or packaged binaries.
- The backend configuration template is `backend/config.example.yaml`. The default SQLite path is `./data/offer_pilot.db`, and resumes are stored under `./data/resumes`.
- `VITE_API_URL` may set the backend base URL at build time. When unset, the frontend uses a same-origin relative path; `window.offerPilotRuntime?.apiBaseUrl` can override it at runtime.
- `OFFER_PILOT_FRONTEND_DIST` overrides the backend's default `frontend/dist` lookup; Electron production explicitly passes its resource directory with `--frontend-dist`.
- Packaged Electron builds read backend configuration from `~/.offerpilot/config.yaml` and create SQLite data, resume uploads, and backend runtime logs there. Managed process stdout/stderr remains under Electron `userData/logs`.

## Submission and verification

- After backend code changes, run focused `uv run pytest ...`; run the full suite for cross-module or infrastructure changes.
- After frontend TypeScript/React changes, run at least `npm run lint` and `npm run typecheck`; run `npm run build` for routing, build configuration, or server/client boundary changes.
- After Electron changes, run at least `npm run lint`; run the relevant build command for packaging or managed-process changes.
- Change or PR notes should state the purpose, affected modules, commands run, and whether configuration, database, API, SSE, or packaging behavior changed.
