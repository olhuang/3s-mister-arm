#!/usr/bin/env python3
"""Snapshot append-only RL live logs into cursor-tracked retrain chunks."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
import time
from pathlib import Path


STATE_SCHEMA_VERSION = 1


def source_key(path: str) -> str:
    return str(Path(path).resolve())


def load_state(path: Path) -> dict[str, object]:
    try:
        with path.open("r", encoding="utf-8") as stream:
            state = json.load(stream)
    except FileNotFoundError:
        return {"schema_version": STATE_SCHEMA_VERSION, "sources": {}}
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{path}: invalid retrain cursor state JSON: {exc}") from exc
    if not isinstance(state, dict):
        raise SystemExit(f"{path}: retrain cursor state root must be an object")
    sources = state.get("sources")
    if not isinstance(sources, dict):
        state["sources"] = {}
    state["schema_version"] = STATE_SCHEMA_VERSION
    return state


def save_state(path: Path, state: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(state, stream, sort_keys=True)
            stream.write("\n")
        os.replace(temp_path, path)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def source_state(state: dict[str, object], source_log: str) -> dict[str, object]:
    sources = state.setdefault("sources", {})
    if not isinstance(sources, dict):
        raise SystemExit("retrain cursor state sources must be an object")
    key = source_key(source_log)
    raw = sources.get(key)
    if isinstance(raw, dict):
        entry = raw
    else:
        entry = {}
        sources[key] = entry
    entry.setdefault("source_log", source_log)
    entry.setdefault("source_log_abs", key)
    entry.setdefault("last_trained_byte_offset", 0)
    entry.setdefault("last_trained_row_count", 0)
    entry.setdefault("last_trained_run_id", 0)
    entry.setdefault("last_trained_episode_id", 0)
    entry.setdefault("last_trained_decision_id", 0)
    return entry


def int_entry(entry: dict[str, object], name: str) -> int:
    try:
        return max(0, int(entry.get(name, 0) or 0))
    except (TypeError, ValueError):
        return 0


def row_identity(row: dict[str, object]) -> dict[str, int]:
    identity: dict[str, int] = {}
    for key in ("run_id", "episode_id", "decision_id"):
        try:
            identity[key] = int(row.get(key, 0) or 0)
        except (TypeError, ValueError):
            identity[key] = 0
    return identity


def chunk_name(prefix: str, label: str) -> str:
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime())
    suffix = f"{time.time_ns() % 1_000_000_000:09d}"
    clean_label = "".join(ch if ch.isalnum() or ch in ("-", "_") else "-" for ch in label.strip())
    if clean_label:
        return f"{prefix}-{clean_label}-{stamp}-{suffix}.ndjson"
    return f"{prefix}-{stamp}-{suffix}.ndjson"


def read_complete_new_rows(
    source_path: Path,
    start_offset: int,
    max_rows: int,
) -> tuple[list[bytes], int, dict[str, int], int, int]:
    rows: list[bytes] = []
    last_identity = {"run_id": 0, "episode_id": 0, "decision_id": 0}
    complete_lines = 0
    invalid_lines = 0
    end_offset = start_offset
    with source_path.open("rb") as stream:
        stream.seek(start_offset)
        while True:
            line_start = stream.tell()
            raw_line = stream.readline()
            if not raw_line:
                end_offset = line_start
                break
            if not raw_line.endswith(b"\n"):
                end_offset = line_start
                break
            complete_lines += 1
            end_offset = stream.tell()
            if not raw_line.strip():
                continue
            try:
                row = json.loads(raw_line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                invalid_lines += 1
                continue
            if not isinstance(row, dict):
                invalid_lines += 1
                continue
            rows.append(raw_line)
            last_identity = row_identity(row)
            if max_rows > 0 and len(rows) >= max_rows:
                end_offset = stream.tell()
                break
    return rows, end_offset, last_identity, complete_lines, invalid_lines


def command_status(args: argparse.Namespace) -> int:
    state = load_state(Path(args.state_path))
    entry = source_state(state, str(args.source_log))
    result = {
        "status": "ok",
        "source_log": str(args.source_log),
        "state_path": str(args.state_path),
        "cursor": entry,
    }
    print(json.dumps(result, sort_keys=True))
    return 0


def command_init(args: argparse.Namespace) -> int:
    source_path = Path(args.source_log)
    try:
        source_size = source_path.stat().st_size
    except OSError as exc:
        raise SystemExit(f"{source_path}: cannot stat source log: {exc}") from exc
    offset = source_size if args.at == "eof" else 0
    state_path = Path(args.state_path)
    state = load_state(state_path)
    entry = source_state(state, str(args.source_log))
    entry.update(
        {
            "last_trained_byte_offset": offset,
            "last_trained_row_count": 0,
            "last_trained_run_id": 0,
            "last_trained_episode_id": 0,
            "last_trained_decision_id": 0,
            "pending_chunk": None,
            "last_updated_at_unix": time.time(),
        }
    )
    save_state(state_path, state)
    print(json.dumps({"status": "initialized", "offset": offset, "source_log": str(args.source_log)}, sort_keys=True))
    return 0


def command_snapshot(args: argparse.Namespace) -> int:
    state_path = Path(args.state_path)
    source_path = Path(args.source_log)
    state = load_state(state_path)
    entry = source_state(state, str(args.source_log))
    pending = entry.get("pending_chunk")
    if isinstance(pending, dict) and not args.replace_pending:
        print(
            json.dumps(
                {
                    "status": "pending-exists",
                    "source_log": str(args.source_log),
                    "pending_chunk": pending,
                },
                sort_keys=True,
            )
        )
        return 2
    try:
        source_size = source_path.stat().st_size
    except OSError as exc:
        raise SystemExit(f"{source_path}: cannot stat source log: {exc}") from exc
    start_offset = int_entry(entry, "last_trained_byte_offset")
    if start_offset > source_size:
        if not args.allow_truncate_reset:
            raise SystemExit(
                f"{source_path}: cursor offset {start_offset} is beyond current file size {source_size}; "
                "use --allow-truncate-reset to restart from byte 0"
            )
        start_offset = 0
    rows, end_offset, last_identity, complete_lines, invalid_lines = read_complete_new_rows(
        source_path,
        start_offset,
        max(0, int(args.max_new_rows)),
    )
    min_new_rows = max(0, int(args.min_new_rows))
    if len(rows) < min_new_rows:
        print(
            json.dumps(
                {
                    "status": "not-enough-rows",
                    "source_log": str(args.source_log),
                    "start_byte_offset": start_offset,
                    "end_byte_offset": end_offset,
                    "new_rows": len(rows),
                    "min_new_rows": min_new_rows,
                    "complete_lines": complete_lines,
                    "invalid_lines": invalid_lines,
                },
                sort_keys=True,
            )
        )
        return 0
    chunk_dir = Path(args.chunk_dir)
    chunk_dir.mkdir(parents=True, exist_ok=True)
    chunk_path = chunk_dir / chunk_name(str(args.chunk_prefix), str(args.label))
    with chunk_path.open("wb") as stream:
        for raw_row in rows:
            stream.write(raw_row)
    pending_chunk = {
        "chunk_log": str(chunk_path),
        "source_log": str(args.source_log),
        "source_log_abs": source_key(str(args.source_log)),
        "source_log_size": source_size,
        "start_byte_offset": start_offset,
        "end_byte_offset": end_offset,
        "row_count": len(rows),
        "complete_lines": complete_lines,
        "invalid_lines": invalid_lines,
        "last_run_id": last_identity["run_id"],
        "last_episode_id": last_identity["episode_id"],
        "last_decision_id": last_identity["decision_id"],
        "created_at_unix": time.time(),
    }
    entry["pending_chunk"] = pending_chunk
    entry["last_updated_at_unix"] = time.time()
    save_state(state_path, state)
    print(json.dumps({"status": "snapshotted", "pending_chunk": pending_chunk}, sort_keys=True))
    return 0


def command_commit(args: argparse.Namespace) -> int:
    state_path = Path(args.state_path)
    state = load_state(state_path)
    entry = source_state(state, str(args.source_log))
    pending = entry.get("pending_chunk")
    if not isinstance(pending, dict):
        print(json.dumps({"status": "no-pending", "source_log": str(args.source_log)}, sort_keys=True))
        return 2
    if args.chunk_log and str(pending.get("chunk_log", "")) != str(args.chunk_log):
        raise SystemExit(
            f"pending chunk {pending.get('chunk_log')} does not match requested --chunk-log {args.chunk_log}"
        )
    previous_rows = int_entry(entry, "last_trained_row_count")
    row_count = max(0, int(pending.get("row_count", 0) or 0))
    entry.update(
        {
            "last_trained_byte_offset": max(0, int(pending.get("end_byte_offset", 0) or 0)),
            "last_trained_row_count": previous_rows + row_count,
            "last_trained_run_id": max(0, int(pending.get("last_run_id", 0) or 0)),
            "last_trained_episode_id": max(0, int(pending.get("last_episode_id", 0) or 0)),
            "last_trained_decision_id": max(0, int(pending.get("last_decision_id", 0) or 0)),
            "last_chunk_log": str(pending.get("chunk_log", "") or ""),
            "last_chunk_rows": row_count,
            "last_committed_at_unix": time.time(),
            "last_updated_at_unix": time.time(),
            "pending_chunk": None,
        }
    )
    save_state(state_path, state)
    print(json.dumps({"status": "committed", "source_log": str(args.source_log), "chunk_log": entry["last_chunk_log"]}, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_common(subparser: argparse.ArgumentParser) -> None:
        subparser.add_argument("--source-log", required=True, help="Append-only live transition NDJSON log")
        subparser.add_argument("--state-path", required=True, help="JSON file storing retrain cursor state")

    status_parser = subparsers.add_parser("status", help="Print cursor status for a source log")
    add_common(status_parser)
    status_parser.set_defaults(func=command_status)

    init_parser = subparsers.add_parser("init", help="Initialize cursor at start or EOF")
    add_common(init_parser)
    init_parser.add_argument("--at", choices=("start", "eof"), default="eof")
    init_parser.set_defaults(func=command_init)

    snapshot_parser = subparsers.add_parser("snapshot", help="Create a pending retrain chunk from new rows")
    add_common(snapshot_parser)
    snapshot_parser.add_argument("--chunk-dir", required=True, help="Directory where chunk NDJSON files are written")
    snapshot_parser.add_argument("--chunk-prefix", default="rl-retrain-chunk")
    snapshot_parser.add_argument("--label", default="")
    snapshot_parser.add_argument("--min-new-rows", type=int, default=1)
    snapshot_parser.add_argument("--max-new-rows", type=int, default=0, help="0 means no row cap")
    snapshot_parser.add_argument("--replace-pending", action="store_true", help="Replace an existing pending chunk")
    snapshot_parser.add_argument("--allow-truncate-reset", action="store_true", help="Reset cursor to 0 if log shrank")
    snapshot_parser.set_defaults(func=command_snapshot)

    commit_parser = subparsers.add_parser("commit", help="Mark the pending chunk as successfully trained")
    add_common(commit_parser)
    commit_parser.add_argument("--chunk-log", default="", help="Optional expected pending chunk path")
    commit_parser.set_defaults(func=command_commit)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    raise SystemExit(args.func(args))


if __name__ == "__main__":
    main()
