# Repository Guidelines

## Project Structure & Module Organization

This repository is the Electron desktop shell for OfferPilot. `electron/main.ts` enforces a single instance, starts managed backend/frontend child processes, logs under Electron `userData`, and opens the app URL. `electron/preload.ts` exposes the minimal `window.offerPilotRuntime.apiBaseUrl` bridge. Renderer code is in `src/`; `src/main.tsx` mounts React and `src/App.tsx` still uses the Vite sample UI. Public files live in `public/`, imported assets in `src/assets/`, packaging scripts in `scripts/`, and installer config in `electron-builder.json5`. `dist/`, `dist-electron/`, `release/`, `resources/`, `logs/`, and `node_modules/` are generated or local-only outputs.

## Architecture & Runtime Notes

Development resolves sibling projects at `../backend` and `../frontend`, unless `OFFER_PILOT_BACKEND_DIR` or `OFFER_PILOT_FRONTEND_DIR` is set. Production expects `resources/backend/offer-pilot-api` and `resources/frontend`, then serves both on available localhost ports. Preserve `contextIsolation: true` and `nodeIntegration: false`.

## Build, Test, and Development Commands

- `npm install`: install dependencies from `package-lock.json`.
- `npm run dev`: run the Vite/Electron development shell.
- `npm run lint`: run ESLint with zero warnings allowed.
- `npm run build:electron`: run `tsc` and build `dist/` plus `dist-electron/`.
- `npm run build:frontend`: build `../frontend`, then stage the Next standalone bundle.
- `npm run build:backend`: package `../backend` with `uv` and PyInstaller, then stage the executable.
- `npm run build` / `npm run build:win`: build assets and the Windows x64 NSIS installer.
- `npm run preview`: preview the Vite renderer build.

## Coding Style & Naming Conventions

Use TypeScript, ES modules, React function components, and hooks. Follow two-space indentation, single quotes, and no-semicolon style. Strict TypeScript is enabled; unused locals and parameters fail compilation. Name components in `PascalCase`, hooks with `useX`, variables/functions in `camelCase`, and Node scripts in kebab-case, for example `prepare-backend.mjs`.

## Testing Guidelines

No test runner is configured. Validate changes with `npm run lint` and the narrowest relevant build command. When adding tests, use `*.test.ts` or `*.test.tsx` near the code, or `tests/` for cross-module behavior. Prioritize Electron startup, managed-process lifecycle behavior, preload contracts, and renderer state changes.

## Commit & Pull Request Guidelines

Recent history uses short imperative subjects such as `Integrate app into Electron shell`. Keep commits focused and action-oriented. Pull requests should include purpose, commands run, linked issues when applicable, and screenshots for UI changes. Call out packaging, resource staging, environment variable, or installer changes.

## Security & Configuration Tips

Do not commit secrets, logs, packaged binaries, or generated `resources/` contents. Production writes `config.yaml` under Electron `userData`; keep defaults local-safe. Never expose Node primitives directly through preload.
