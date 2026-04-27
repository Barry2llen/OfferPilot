from __future__ import annotations

import argparse
import os
from pathlib import Path

import uvicorn


def main() -> None:
    args = parse_args()
    runtime_dir = Path(args.runtime_dir).expanduser().resolve()
    runtime_dir.mkdir(parents=True, exist_ok=True)
    os.chdir(runtime_dir)

    from main import app as fastapi_app

    uvicorn.run(
        fastapi_app,
        host=args.host,
        port=args.port,
        log_level=args.log_level,
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
    return parser.parse_args()


if __name__ == "__main__":
    main()
