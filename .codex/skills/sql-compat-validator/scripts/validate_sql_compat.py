#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class Statement:
    text: str
    start_line: int


@dataclass(slots=True)
class Finding:
    path: Path
    line: int
    level: str
    message: str


RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"`"), "Use standard SQL identifiers instead of MySQL-style backticks."),
    (re.compile(r"\bENUM\s*\(", re.IGNORECASE), "Replace ENUM with VARCHAR/TEXT plus CHECK constraint."),
    (re.compile(r"\bAUTO_INCREMENT\b", re.IGNORECASE), "AUTO_INCREMENT is MySQL-specific."),
    (re.compile(r"\bUNSIGNED\b", re.IGNORECASE), "UNSIGNED is not portable across SQLite/PostgreSQL."),
    (re.compile(r"\bENGINE\s*=", re.IGNORECASE), "ENGINE=... is MySQL-specific."),
    (re.compile(r"\bDEFAULT\s+CHARSET\b", re.IGNORECASE), "DEFAULT CHARSET is MySQL-specific."),
    (
        re.compile(r"\bON\s+UPDATE\s+CURRENT_TIMESTAMP\b", re.IGNORECASE),
        "ON UPDATE CURRENT_TIMESTAMP is MySQL-specific.",
    ),
    (re.compile(r"\bSERIAL\b", re.IGNORECASE), "SERIAL is PostgreSQL-specific."),
    (re.compile(r"\bJSONB\b", re.IGNORECASE), "JSONB is PostgreSQL-specific."),
    (re.compile(r",\s*\)", re.MULTILINE), "Trailing comma before ')' is invalid SQL for SQLite/PostgreSQL."),
)


def discover_sql_files(targets: list[str]) -> list[Path]:
    if not targets:
        targets = ["backend/sql", "backend/dev"]

    files: list[Path] = []
    for raw_target in targets:
        target = Path(raw_target)
        if target.is_file() and target.suffix.lower() == ".sql":
            files.append(target)
            continue
        if target.is_dir():
            files.extend(sorted(target.rglob("*.sql")))
            continue
        for matched in sorted(Path().glob(raw_target)):
            if matched.is_file() and matched.suffix.lower() == ".sql":
                files.append(matched)

    deduped: list[Path] = []
    seen: set[Path] = set()
    for file_path in files:
        resolved = file_path.resolve()
        if resolved not in seen:
            deduped.append(file_path)
            seen.add(resolved)
    return deduped


def split_statements(sql_text: str) -> list[Statement]:
    statements: list[Statement] = []
    buffer: list[str] = []
    start_line = 1
    current_line = 1
    in_single_quote = False
    in_double_quote = False

    for index, char in enumerate(sql_text):
        if not buffer and not char.isspace():
            start_line = current_line

        buffer.append(char)

        if char == "\n":
            current_line += 1
            continue

        previous = sql_text[index - 1] if index > 0 else ""
        if char == "'" and not in_double_quote and previous != "\\":
            in_single_quote = not in_single_quote
        elif char == '"' and not in_single_quote and previous != "\\":
            in_double_quote = not in_double_quote
        elif char == ";" and not in_single_quote and not in_double_quote:
            statement = "".join(buffer).strip().rstrip(";").strip()
            if statement:
                statements.append(Statement(text=statement, start_line=start_line))
            buffer = []

    remainder = "".join(buffer).strip()
    if remainder:
        statements.append(Statement(text=remainder, start_line=start_line))

    return statements


def line_number(sql_text: str, offset: int) -> int:
    return sql_text.count("\n", 0, offset) + 1


def lint_patterns(path: Path, sql_text: str) -> list[Finding]:
    findings: list[Finding] = []
    for pattern, message in RULES:
        for match in pattern.finditer(sql_text):
            findings.append(
                Finding(
                    path=path,
                    line=line_number(sql_text, match.start()),
                    level="error",
                    message=message,
                )
            )
    return findings


def validate_with_sqlite(path: Path, statements: list[Statement]) -> list[Finding]:
    findings: list[Finding] = []
    connection = sqlite3.connect(":memory:")
    try:
        for statement in statements:
            try:
                connection.execute(statement.text)
            except sqlite3.DatabaseError as error:
                findings.append(
                    Finding(
                        path=path,
                        line=statement.start_line,
                        level="error",
                        message=f"SQLite execution failed: {error}",
                    )
                )
    finally:
        connection.close()
    return findings


def validate_file(path: Path) -> list[Finding]:
    sql_text = path.read_text(encoding="utf-8")
    statements = split_statements(sql_text)
    findings = lint_patterns(path, sql_text)

    if not statements:
        findings.append(Finding(path=path, line=1, level="warning", message="No SQL statements found."))
        return findings

    findings.extend(validate_with_sqlite(path, statements))
    findings.sort(key=lambda item: (str(item.path), item.line, item.message))
    return findings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate SQL files for SQLite/PostgreSQL portability."
    )
    parser.add_argument(
        "targets",
        nargs="*",
        help="SQL files, directories, or globs to validate. Defaults to: backend/sql backend/dev",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    files = discover_sql_files(args.targets)
    if not files:
        print("No SQL files found.", file=sys.stderr)
        return 1

    findings: list[Finding] = []
    for file_path in files:
        findings.extend(validate_file(file_path))

    if findings:
        for finding in findings:
            print(f"{finding.path}:{finding.line}: {finding.level}: {finding.message}")
        return 1

    for file_path in files:
        print(f"{file_path}: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
