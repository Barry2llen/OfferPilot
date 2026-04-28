---
name: sql-compat-validator
description: Validate SQL files in this project for cross-database compatibility, especially when schema or migration SQL must run on both SQLite and PostgreSQL. Use when Codex needs to review, fix, or gate `.sql` files such as `backend/sql/tables.sql`, detect dialect-specific syntax, or verify that SQL remains portable before startup execution.
---

# SQL Compat Validator

Use this skill when the task is to check whether project SQL can run on both SQLite and PostgreSQL.

## Workflow

1. Run `scripts/validate_sql_compat.py` against the target SQL file or directory.
2. Read the findings before editing anything.
3. Prefer neutral SQL that works in both engines.
4. Re-run the script after changes until it exits cleanly.

## What The Script Checks

- SQLite parse/execution errors by replaying statements against an in-memory SQLite database
- Dialect-specific syntax that is likely to break cross-database portability
- Common DDL footguns such as backticks, `ENUM`, `AUTO_INCREMENT`, `ENGINE=`, `UNSIGNED`, and trailing commas before `)`

## Recommended Usage

Validate the common schema locations first:

```powershell
uv run python .codex/skills/sql-compat-validator/scripts/validate_sql_compat.py backend/sql backend/dev
```

Validate a specific file:

```powershell
uv run python .codex/skills/sql-compat-validator/scripts/validate_sql_compat.py backend/sql/tables.sql
```

## Interpretation

- If the script reports SQLite execution failures, fix those first. Startup initialization will fail otherwise.
- If it reports portability warnings, replace dialect-specific syntax with shared SQL unless the project has explicitly chosen a single dialect for that file.
- If a construct is intentionally database-specific, keep it out of shared startup schema files and document the dialect boundary in the change summary.
