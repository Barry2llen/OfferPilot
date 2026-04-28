# OfferPilot Electron

OfferPilot Electron is the desktop shell for OfferPilot. It starts the local backend and frontend services, waits for them to become ready, and opens the application in an Electron window.

The main process lives in `electron/main.ts`. In development it locates sibling projects at `../backend` and `../frontend`, starts them on available localhost ports, and injects the API URL into the frontend environment. In packaged builds it runs the staged backend executable and Next.js standalone server from Electron resources.

## Project Layout

- `electron/main.ts` - Electron main process, service startup, logging, window lifecycle, and packaged runtime config.
- `electron/preload.ts` - safe preload bridge exposing `window.offerPilotRuntime.apiBaseUrl`.
- `src/` - Vite/React renderer shell. The current `App.tsx` is still the starter UI.
- `scripts/prepare-frontend.mjs` - copies the Next.js standalone build into `resources/frontend`.
- `scripts/prepare-backend.mjs` - copies the PyInstaller backend output into `resources/backend/offer-pilot-api`.
- `electron-builder.json5` - installer and extra resource configuration.

Generated directories such as `dist/`, `dist-electron/`, `release/`, `resources/`, `logs/`, and `node_modules/` are ignored by Git.

## Prerequisites

- Node.js and npm
- `uv` for backend packaging
- A sibling `../frontend` project with a Next.js standalone build configuration
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

The development shell starts the backend with `uv run uvicorn main:app` and the frontend with `npm run dev`. Both services bind to `127.0.0.1` on available ports.

## Build

Build only the Electron/Vite outputs:

```sh
npm run build:electron
```

Build the full Windows package:

```sh
npm run build
```

The full build runs frontend staging, backend packaging, Electron compilation, and `electron-builder --win --x64`.

## Quality Checks

Run linting before submitting changes:

```sh
npm run lint
```

No test runner is currently configured in this package. For behavior changes, validate with the narrowest relevant build command and add focused tests when introducing a runner.

## Runtime Notes

Packaged builds create backend runtime data under Electron `userData`, including `backend/config.yaml`, SQLite data, resume uploads, and logs. Keep preload APIs minimal; the renderer should not receive direct Node.js access.
