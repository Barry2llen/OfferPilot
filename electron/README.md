# OfferPilot Electron

OfferPilot Electron starts FastAPI and Vite in development. Packaged builds run
one frozen FastAPI service that serves both APIs and the React SPA. Preload
exposes only `window.offerPilotRuntime.apiBaseUrl`; context isolation stays
on and Node integration stays off.

## Development and requirements

Use Node.js 22, pnpm 12.15.0, Python 3.13 and uv. Each subproject keeps its
own dependencies. From the repository root:

```sh
pnpm --dir frontend install --frozen-lockfile
pnpm --dir electron install --frozen-lockfile
uv sync --project backend --frozen --all-groups --python 3.13
pnpm --dir electron run dev
```

The Electron project's postinstall runs Electron 43's explicit binary installer.
Jobs that launch only a packaged runtime can set `ELECTRON_SKIP_BINARY_DOWNLOAD=1`.

Development discovers sibling `backend/` and `frontend/` directories. Override
with `OFFER_PILOT_BACKEND_DIR` and `OFFER_PILOT_FRONTEND_DIR` when necessary;
these overrides also apply to builds. Services bind to available localhost
ports. Windows uses the backend's Psycopg-compatible event loop.

## Native builds

Run commands below from `electron/`:

```sh
pnpm run build:electron  # Compile only the Electron/Vite shell
pnpm run build:frontend  # Build and stage the React SPA
pnpm run build:backend   # Freeze and stage the native backend
pnpm run build           # Full build for the current host
pnpm run build:win       # Windows x64 NSIS, on Windows x64
pnpm run build:linux     # Linux x64 AppImage and deb, on Linux x64
```

Full builds always disable electron-builder publishing. The release workflow
owns publication. Unsupported hosts and architectures fail before staging.
Resources are staged as `resources/frontend` and
`resources/backend/offer-pilot-api`; PyInstaller supporting files and executable
permissions are preserved. Build output goes to `release/<version>/`.
Backend packaging uses a separate uv-managed Python 3.13 environment under
`resources/backend-build/venv`, including its shared Python library. It leaves
the development backend environment in place.
Generated resources, dependencies, logs, installers and screenshots are not
committed.

Linux official builds use Ubuntu 22.04 and are verified on 22.04 and 24.04.
Build on the oldest supported distribution; a locally built backend can depend
on its host's glibc. Other distributions are best-effort. Install prerequisites:

```sh
sudo apt-get update
sudo apt-get install -y binutils dpkg libgl1 libfontconfig1 libharfbuzz0b fonts-dejavu-core fonts-noto-cjk
```

The renderer additionally requires the usual Electron GTK/NSS/GBM/audio
libraries. Installing the deb resolves its declared desktop dependencies.

## Linux compatibility libraries and offline self-check

Aspose remains the DOCX renderer. The build fetches these pinned Ubuntu archive
packages over HTTPS and verifies SHA-256 before extracting them privately:

| Package | Version | SHA-256 |
| --- | --- | --- |
| libicu66 | 66.1-2ubuntu2.1 | `00d0de456134668f41bd9ea308a076bc0a6a805180445af8a37209d433f41efe` |
| libssl1.1 | 1.1.1f-1ubuntu2.24 | `7cf39d70a639017d1dd7c8d36daa2258063608688e449fddf40ffdd46f992a78` |

The source URLs are recorded in `scripts/linux-libraries.mjs`. Verified archives
are cached under `resources/library-cache`. The backend bundle's `compat/`
directory contains ICU/OpenSSL SONAME libraries, package copyright files and
`manifest.json`. Only the Linux backend child receives this library directory
in `LD_LIBRARY_PATH`; Electron and system libraries retain their environment.
Updating compatibility libraries requires updating the pinned version/hash and
running both Ubuntu verification jobs.

The frozen backend supports `--self-check`: PDF rendering, a DOCX round trip to
PNG and initialization of the bundled OCR models. It does not start HTTP, read
model credentials or make external model calls. Exit 0 means all checks pass;
nonzero means a dependency or render failed. JSON results are printed to stdout.
For a staged Linux backend, from `electron/`:

```sh
LD_LIBRARY_PATH="$PWD/resources/backend/offer-pilot-api/compat${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" resources/backend/offer-pilot-api/offer-pilot-api --self-check
```

## Install, verify and remove

Replace `X.Y.Z` below with the downloaded version. Keep the two Linux installers
and their `.sha256` file in one directory:

```sh
sha256sum --check OfferPilot-Linux-x64-vX.Y.Z.sha256
sudo apt install ./OfferPilot-Linux-x64-vX.Y.Z.deb
# Remove the application while retaining personal runtime data:
sudo apt remove offerpilot
```

The deb installs `/opt/OfferPilot/offerpilot`, a desktop launcher and the usual
Electron installer hooks, including supported AppArmor integration.

For the portable package:

```sh
chmod +x OfferPilot-Linux-x64-vX.Y.Z.AppImage
./OfferPilot-Linux-x64-vX.Y.Z.AppImage
```

If the AppImage runtime requests FUSE, Ubuntu 22.04 uses `libfuse2` and Ubuntu
24.04 uses `libfuse2t64`. A FUSE-free fallback is
`APPIMAGE_EXTRACT_AND_RUN=1 ./OfferPilot-Linux-x64-vX.Y.Z.AppImage`.
On systems that restrict Electron user namespaces, prefer the installed deb
and its platform integration. Deleting an AppImage removes the portable
application; personal data remains in its runtime directory.

## Unified Release workflow

The workflow remains named `Release` in
`.github/workflows/build-windows-release.yml`:

1. Dispatch a `bump-patch`, `bump-minor` or `bump-major` from `main`.
2. Review and merge `release/vX.Y.Z`. Root/frontend/Electron versions and
   both sidebar labels are synchronized; dependency versions remain locked.
3. The merge is tagged `vX.Y.Z`. Existing tags are never moved; re-running
   the same merge accepts a tag only when it already targets that commit.
4. Windows and Ubuntu 22.04 build jobs upload artifacts without publishing.
5. Ubuntu 22.04 and 24.04 install/uninstall the deb, launch the AppImage,
   and verify frozen dependencies, page loading, health, deep-route refresh,
   preload isolation and backend shutdown under Xvfb.
6. Only after all required jobs pass does one publishing job create a draft,
   upload the complete assets and publish. A failed upload leaves a draft.

Assets are `OfferPilot-Windows-x64-vX.Y.Z.exe`,
`OfferPilot-Linux-x64-vX.Y.Z.AppImage`, `.deb`, and `.sha256`.
To replace assets in an already published release, dispatch `build-windows`
or `build-linux` with `X.Y.Z` (no leading `v`). To create or complete a draft,
use `build-all` or re-run failed jobs. Single-platform rebuilds preserve the
other platform and existing release notes. Publishing is serialized per tag.

Manual builds require a tag containing the pnpm release tools and relevant
platform support. Historical unsupported tags fail clearly; prepare a new
release instead of retagging. Actions artifacts, available partial installers,
build diagnostics and smoke-test evidence are retained for 14 days. A failed
required build or verification prevents public release creation.

## Checks and troubleshooting

```sh
pnpm run test
pnpm run lint
pnpm run build:electron
# After building, with a display or under xvfb-run:
pnpm run test:linux --executable /path/to/offerpilot --resources /path/to/resources --output /tmp/offerpilot-evidence
```

The smoke test uses Playwright's Electron support, a fresh temporary runtime
and screenshots outside the repository. CI provides Xvfb, xauth, fonts and
Electron desktop libraries; CI launch arguments accommodate runner sandbox
restrictions without changing production startup settings.

A checksum mismatch stops staging; remove only the named corrupted archive
from `resources/library-cache` and retry. A frozen self-check failure is logged
in the verification artifact. Inspect its native-library error and rebuild
before publishing. A missing installation target or installer is an error,
not a successful partial release.

## Runtime data and logs

Default backend data is under `~/.offerpilot`: `config.yaml`, SQLite data,
resume/chat uploads and backend logs. Electron child stdout/stderr remains in
Electron `userData/logs`. Installation and removal preserve these directories.
Set `OFFER_PILOT_RUNTIME_DIR` to select an isolated root: backend files live at
that root and Electron user data/logs at its `electron/` subdirectory. This is
used by packaged-app verification and leaves the default paths unchanged.
