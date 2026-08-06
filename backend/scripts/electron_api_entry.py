from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import uvicorn

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))


def main() -> None:
    args = parse_args()
    runtime_dir = Path(args.runtime_dir).expanduser().resolve()
    runtime_dir.mkdir(parents=True, exist_ok=True)
    os.chdir(runtime_dir)

    from main import create_app
    from utils.asyncio_windows import resolve_uvicorn_loop

    fastapi_app = create_app(frontend_dist=args.frontend_dist)

    uvicorn.run(
        fastapi_app,
        host=args.host,
        port=args.port,
        log_level=args.log_level,
        loop=resolve_uvicorn_loop(),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run OfferPilot API for Electron.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--log-level", default="info")
    parser.add_argument(
        "--runtime-dir",
        default=".",
        help="Directory that contains config.yaml and runtime data.",
    )
    parser.add_argument(
        "--frontend-dist",
        help="Directory containing the built React frontend to serve.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    main()
