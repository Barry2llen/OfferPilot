# OfferPilot Electron

OfferPilot Electron is the desktop shell for OfferPilot. It starts the local FastAPI and Vite services in development, or a single FastAPI service that serves the React build in production, waits for readiness, and opens the application in an Electron window.

The main process lives in `electron/main.ts`. In development it locates sibling projects at `../backend` and `../frontend`, starts FastAPI and Vite on available localhost ports, and exposes the backend URL through the preload bridge. In packaged builds it runs only the staged backend executable and passes `resources/frontend` as `--frontend-dist`; FastAPI serves both the API and the React SPA.

## Project Layout

- `electron/main.ts` - Electron main process, service startup, logging, window lifecycle, and packaged runtime config.
- `electron/preload.ts` - safe preload bridge exposing `window.offerPilotRuntime.apiBaseUrl`.
- `src/` - Vite/React renderer shell used by the Electron development window.
- `scripts/prepare-frontend.mjs` - copies the Vite `frontend/dist` build into `resources/frontend`.
- `scripts/prepare-backend.mjs` - copies the PyInstaller backend output into `resources/backend/offer-pilot-api`.
- `electron-builder.json5` - installer and extra resource configuration.

Generated directories such as `dist/`, `dist-electron/`, `release/`, `resources/`, `logs/`, and `node_modules/` are ignored by Git.

## Prerequisites

- Node.js and npm
- `uv` for backend packaging
- A sibling `../frontend` project with a Vite build (`npm run build` must produce `dist/index.html`)
- A sibling `../backend` project with `pyproject.toml` and `packaging/offer_pilot_api.spec`

Use `OFFER_PILOT_FRONTEND_DIR` and `OFFER_PILOT_BACKEND_DIR` if those projects are not located beside this repository.

## Development

Install dependencies:

```sh
npm install
```

Start the Electron development shell:

```sh
npm run dev
```

The development shell starts the backend with `uv run uvicorn main:app` and the frontend with Vite's `npm run dev`. Both services bind to `127.0.0.1` on available ports. The frontend uses the runtime API URL exposed by preload; an independently started Vite server falls back to its API proxy.

## Build

Build only the Electron/Vite outputs:

```sh
npm run build:electron
```

Build the full Windows package:

```sh
npm run build
```

The full build runs the Vite frontend build and staging, backend packaging, Electron compilation, and `electron-builder --win --x64`. The packaged app starts only FastAPI; it does not require a Node frontend server.

## Quality Checks

Run linting before submitting changes:

```sh
npm run lint
```

No test runner is currently configured in this package. For behavior changes, validate with the narrowest relevant build command and add focused tests when introducing a runner.

## Runtime Notes

Packaged builds read and create backend runtime data under `~/.offerpilot`, including `config.yaml`, SQLite data, resume uploads, chat attachment uploads, and backend runtime logs. `config.yaml` now also supports `chat_file_upload_dir`, which defaults to `./data/chat_files` in the backend runtime working directory. Managed process stdout/stderr logs are still written under Electron `userData/logs`. Keep preload APIs minimal; the renderer should not receive direct Node.js access.
