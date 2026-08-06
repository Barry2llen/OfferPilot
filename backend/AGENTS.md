# OfferPilot Backend Agent Guide

## Repository structure

This directory contains the Python FastAPI application. The entry point is
`main.py`. `create_app()` loads configuration, initializes the synchronous
and asynchronous database managers, creates tables, initializes the
`DatabaseCheckpointer`, and assembles the `SupervisorAgent`.

Core directories:

- `agent/`: Agent graphs, state, model calls, tools, supervisors, workflows,
  interrupts, and database checkpoints.
- `api/`: FastAPI routes. `api/routes/resume.py` handles resume upload,
  replacement, lookup, deletion, and original-file preview.
  `api/routes/model_config.py` handles model-provider and model-selection
  CRUD. `api/routes/ai.py` handles synchronous and SSE chat.
- `db/`: SQLAlchemy engines, sessions, ORM models, repositories, and
  LangGraph checkpoint persistence.
- `schemas/`: Pydantic and TypedDict structures for configuration, AI,
  commands, model configuration, and resume documents.
- `services/`: Business services for resume files, model providers,
  selections, resume extraction, and job-description analysis.
- `exceptions/`: Domain exceptions grouped by agent, database, model, and
  resume concerns.
- `utils/`: Shared utilities, including logging, document parsing, stream
  events, encoding checks, static hosting, and locale translation.
- `sql/`: Database snapshots or initialization SQL. SQL must remain
  compatible with both SQLite and PostgreSQL.
- `tests/unit/`: Unit tests; shared fixtures live in `tests/conftest.py`.
- `docs/` and `tasks/`: Design notes, technical documentation, and task
  records.

Generated data, logs, and temporary development files under `data/`,
`logs/`, and `dev/test-tmp/` must not become business-logic dependencies or
be committed.

Keep responsibilities separated: configuration parsing must not be mixed into
services, database access must not leak into routes or Agent nodes, and Agent
nodes must not handle HTTP details directly.

`create_app(config=None, frontend_dist=None)` registers the business APIs,
`/docs`, `/openapi.json`, and `/health` before mounting the React
production build. `utils/frontend_static.py` handles static assets, SPA
deep-route fallback, and API-path content negotiation. A missing build
directory must not prevent the API from starting. The frontend directory may
be overridden with `OFFER_PILOT_FRONTEND_DIST` or Electron's
`--frontend-dist`.

## Build, test, and development commands

Use `uv` for dependency management and command execution:

- `uv sync`: install and lock dependencies.
- `uv run python run_server.py --reload`: start the local FastAPI server with the Windows-compatible Psycopg event loop.
- `uv run pytest`: run the complete test suite.
- `uv run pytest tests/unit/test_resume_api.py`: test resume APIs and
  OpenAPI documentation.
- `uv run pytest tests/unit/test_model_config_api.py`: test provider and
  selection CRUD and documentation.
- `uv run pytest tests/unit/test_ai_api.py`: test synchronous/SSE chat,
  events, interrupts, retries, and tool events.
- `uv run pytest tests/unit/test_model_call_graph.py`: test model calls,
  tool calls, retries, interrupts, and exception branches.
- `uv run pytest tests/unit/test_database_engine.py tests/unit/test_database_checkpointer.py`:
  test database engines, table creation, and checkpoint behavior.
- `uv run pytest tests/unit/test_chat_model.py`: test model loading errors.
- `uv run pytest tests/unit/test_frontend_static.py`: test the React build,
  SPA deep routes, and API route precedence.

When configuration, database compatibility, model loading, Agent graphs, SSE
protocols, API documentation, or SQL changes, run the narrowest relevant
tests before submitting. When changing `sql/*.sql`, also perform a
cross-database compatibility check.

## Coding style and naming

The target Python version is `>=3.13`. Use complete type annotations, PEP 8,
four-space indentation, `snake_case` for modules/functions, and
`PascalCase` for classes.

- Use Pydantic v2 validators, `ConfigDict`, and
  `Field(description=..., examples=...)`.
- Use SQLAlchemy 2.x ORM syntax with explicit `Mapped` annotations.
- Prefer `TypedDict` for Agent state and keep node functions focused.
- Use `BaseInterrupt` for public LangGraph interrupt payloads and
  `schemas.command.BaseCommand` with `Command(resume=...)` for recovery.
- Serialize SSE data through the route helpers; do not concatenate complex
  objects directly.
- Load tools through `agent.tools.get_all_tools(config)`. Missing Exa keys
  must safely disable remote tools without connecting during import.
- Prefer small functions and early validation.
- Prefer `Path` for filesystem paths.
- FastAPI routes must document `summary`, `description`,
  `response_description`, and the main error responses.
- Public schema fields must provide `Field(..., description=..., examples=...)`
  so Swagger does not expose bare field names.

Keep comments concise. Explain only non-obvious constraints, state
transitions, or compatibility decisions.

## API, locale, and Agent behavior

- Resume endpoints handle file-based resumes. Do not restore removed text-resume
  endpoints unless a task explicitly requires them.
- `/model-providers` and `/model-selections` are the AI model configuration
  sources. Never return API keys in plaintext.
- `/` is served by the React build. Health checks use `/health`, preserving
  the existing `{"message":"Hello World!"}` shape. Business APIs, Swagger,
  and OpenAPI routes take precedence over static hosting.
- `/ai/chat` returns the final text response and persists conversation state
  by `thread_id` through `DatabaseCheckpointer`.
- `/ai/chat/stream` returns `text/event-stream`. Keep event names stable:
  `thread`, `token`, `tool_start`, `tool_end`, `tool_error`,
  `interrupt`, `final`, and `error`.
- Stream retries use the LangGraph checkpoint. After an `interrupt`, the
  client must send the same `thread_id` with
  `command.type="retry"`.
- The supported request languages are `Accept-Language: en-US` and
  `Accept-Language: zh-CN`. Missing or unrecognized values fall back to
  `zh-CN`; localized responses set the matching `Content-Language`.
- Localize known API errors, validation errors, model-configuration errors,
  file-processing errors, and temporary resume/job-description SSE messages.
  Preserve event names and payload shapes. Do not translate AI output, user
  input, resume or job-description source text, or persisted technical error
  details.
- OpenAPI titles, descriptions, response descriptions, and field
  documentation must be written in English.
- When changing request bodies, response fields, SSE event payloads, retry
  semantics, or locale behavior, update the OpenAPI documentation and the
  relevant tests.

## Testing guidelines

Use `pytest`, with new files named `test_*.py` under `tests/unit/`.
Add coverage for:

- configuration parsing, including current and legacy configuration shapes;
- SQLite defaults and optional PostgreSQL configuration;
- schema creation, important columns, unique constraints, and foreign keys;
- synchronous/asynchronous checkpoint round trips, writes, copy/delete, and
  pruning;
- Agent tool calls, isolated tool errors, model retries, interrupts, recovery,
  and exception branches;
- tool loading with and without an Exa key, without accidental remote
  connections in tests;
- service conversions between schemas and ORM objects;
- successful API responses, important error codes, locale negotiation,
  `Content-Language`, and key OpenAPI metadata;
- PDF, DOCX, image OCR, preview conversion, missing dependencies, and
  unsupported file formats;
- resume and job-description SSE progress/error messages while confirming
  event names remain unchanged.

## Configuration and security

Never commit real secrets to `config.yaml`, `.env`, or example files. The
default template is `config.example.yaml`.

Current configuration includes:

- `database`: SQLite by default at `./data/offer_pilot.db`, with optional
  PostgreSQL support;
- `resume_upload_dir`: defaults to `./data/resumes`;
- `model_call_retry_attempts`: internal model-call retry count;
- `graph_recursion_limit`: LangGraph runtime recursion limit, default 100;
- `web_search`: Exa search type, result length, and guiding query;
- `exa_api_key`: enables Exa web-search tools when present; missing keys
  disable tools and emit a warning;
- `debug`: controls debug logging.

When API behavior, configuration formats, database structure, or model
integration changes, update `config.example.yaml`, OpenAPI documentation,
tests, and necessary project docs.

## Commits and pull requests

Keep commits focused and action-oriented, for example
`feat: add model selection service tests` or
`fix: correct model provider mapping`. Do not combine unrelated refactors,
features, and documentation changes in one commit.

Pull requests must state:

- the purpose of the change;
- affected modules;
- commands run and their results;
- whether configuration, database structure, API protocol, SSE events, or
  model integration changed.

If request bodies, response structures, SSE events, configuration formats, or
database schemas change, include examples or migration notes.
