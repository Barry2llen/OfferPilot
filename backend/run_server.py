from __future__ import annotations

import argparse

from utils.asyncio_windows import resolve_uvicorn_loop


def main() -> None:
    args = parse_args()

    import uvicorn

    uvicorn.run(
        "main:app",
        host=args.host,
        port=args.port,
        log_level=args.log_level,
        loop=resolve_uvicorn_loop(),
        reload=args.reload,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the OfferPilot API server.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--log-level", default="info")
    parser.add_argument("--reload", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    main()
