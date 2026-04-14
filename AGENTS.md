# Repository Guidelines

## Project Structure & Module Organization
`main.py` exposes the FastAPI app and wires application startup. Core database code lives under `db/`, with engine management in `db/engine/` and ORM models in `db/models/`. Typed configuration schemas live in `schemas/config/`. Domain models and shared helpers are in `models/` and `utils/`. SQL bootstrap scripts live in `sql/`, sample data and local SQLite files belong in `data/`, and design notes belong in `docs/`. Tests are organized under `tests/unit/`; add new fixtures to `tests/conftest.py`.

## Build, Test, and Development Commands
Use `uv` for environment and command execution.

- `uv sync` installs and locks project dependencies from `pyproject.toml` and `uv.lock`.
- `uv run uvicorn main:app --reload` starts the local API server with auto-reload.
- `uv run pytest` runs the full test suite.
- `uv run pytest tests/unit/test_config.py` runs a focused test module during iteration.

Run commands from the repository root so relative paths like `config.yaml` and `sql/tables.sql` resolve correctly.

## Coding Style & Naming Conventions
Target Python `>=3.13` and keep code type-annotated. Follow PEP 8 with 4-space indentation, `snake_case` for modules/functions, `PascalCase` for classes, and explicit, descriptive names such as `build_database_url`. Keep config schemas and database utilities separated by responsibility. Prefer small functions, early validation, and `Path` for filesystem work. Match the existing style of short docstrings and straightforward control flow.

## Testing Guidelines
Tests use `pytest`. Name files `test_*.py`, keep unit tests under `tests/unit/`, and prefer fixtures over inline setup for temporary databases or config payloads. Cover both SQLite defaults and optional PostgreSQL behavior when touching database code. For config changes, test both root-level and legacy `offer_pilot` YAML shapes.

## Commit & Pull Request Guidelines
Current history uses short prefix-based messages such as `feat:初始化数据源`, `feat:多数据源`, and `init:初始化项目结构`. Keep that pattern: `<type>:<summary>`, with concise Chinese summaries and a single focus per commit. Pull requests should include purpose, affected modules, test results, and any config or schema changes. Add request/response examples when API behavior changes.

## Configuration & Security Tips
Do not commit real secrets in `config.yaml`; use `config.example.yaml` as the template. PostgreSQL integration tests depend on `TEST_POSTGRES_*` environment variables, so document any new variables in the example config or PR description.
