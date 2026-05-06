#!/usr/bin/env python3
"""Summarize combat event journal NDJSON logs."""

from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path
from typing import Any


SUPPORTED_SCHEMA = 1


def read_ndjson(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    with path.open("rb") as stream:
        for line_no, raw in enumerate(stream, 1):
            if not raw.strip():
                continue
            try:
                row = json.loads(raw)
            except json.JSONDecodeError as exc:
                errors.append(f"{path}:{line_no}: JSONDecodeError: {exc}")
                continue
            if not isinstance(row, dict):
                errors.append(f"{path}:{line_no}: row is not a JSON object")
                continue
            rows.append(row)
    return rows, errors


def format_counter(counter: collections.Counter[Any], limit: int = 12) -> str:
    if not counter:
        return "(none)"
    parts: list[str] = []
    for key, value in counter.most_common(limit):
        parts.append(f"{key}={value}")
    remaining = len(counter) - limit
    if remaining > 0:
        parts.append(f"...(+{remaining})")
    return ", ".join(parts)


def row_episode(row: dict[str, Any]) -> tuple[Any, Any]:
    return row.get("run_id"), row.get("episode_id")


def combat_event_key(row: dict[str, Any]) -> tuple[Any, Any, Any, Any]:
    return row.get("run_id"), row.get("episode_id"), row.get("event_kind"), row.get("event_id")


def attack_bucket(row: dict[str, Any]) -> str:
    result = str(row.get("result", "unknown"))
    reason = str(row.get("finalize_reason", "unknown"))
    projectile_like = int(row.get("projectile_like") or 0)

    if reason == "projectile_claimed":
        return "delegated_to_projectile"
    if result == "whiff":
        return "whiff"
    if result == "interrupted":
        return "interrupted"
    if reason == "episode_flush":
        return "round_boundary_unknown"
    if reason == "basic_unknown_timeout":
        if projectile_like:
            return "timeout_projectile_like_unknown"
        return "timeout_unknown"
    if reason == "superseded_by_new_start":
        return "rollover_unknown"
    if result == "unknown":
        return "true_unknown_other"
    return result


def is_true_attack_unknown_bucket(bucket: str) -> bool:
    return bucket in {
        "rollover_unknown",
        "timeout_unknown",
        "timeout_projectile_like_unknown",
        "true_unknown_other",
    }


def make_summary(event_rows: list[dict[str, Any]], transition_rows: list[dict[str, Any]]) -> dict[str, Any]:
    schema_counts: collections.Counter[Any] = collections.Counter()
    kind_counts: collections.Counter[Any] = collections.Counter()
    episode_counts: collections.Counter[tuple[Any, Any]] = collections.Counter()
    duplicate_keys: collections.Counter[tuple[Any, Any, Any, Any]] = collections.Counter()
    event_ids: list[int] = []
    unsupported_rows = 0
    transition_event_rows = 0

    for row in event_rows:
        schema = row.get("combat_event_schema_version")
        schema_counts[schema] += 1
        if schema != SUPPORTED_SCHEMA:
            unsupported_rows += 1
        if row.get("transition_schema_version") is not None:
            transition_event_rows += 1
        kind_counts[row.get("event_kind")] += 1
        episode_counts[row_episode(row)] += 1
        duplicate_keys[combat_event_key(row)] += 1
        event_id = row.get("event_id")
        if isinstance(event_id, int):
            event_ids.append(event_id)

    non_increasing_edges: list[tuple[int, int, int]] = []
    for index, (left, right) in enumerate(zip(event_ids, event_ids[1:]), 1):
        if right <= left:
            non_increasing_edges.append((index, left, right))

    duplicate_rows = sum(count - 1 for count in duplicate_keys.values() if count > 1)
    event_id_missing: list[int] = []
    if event_ids:
        event_id_missing = sorted(set(range(min(event_ids), max(event_ids) + 1)) - set(event_ids))

    by_kind: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for row in event_rows:
        by_kind[str(row.get("event_kind"))].append(row)

    attacks = by_kind.get("attack", [])
    attack_bucket_counts: collections.Counter[str] = collections.Counter(attack_bucket(row) for row in attacks)
    true_attack_unknown_rows = [row for row in attacks if is_true_attack_unknown_bucket(attack_bucket(row))]

    source_ref_rows = [
        row
        for row in event_rows
        if row.get("source_event_id") not in (None, 0)
    ]
    event_id_set = {row.get("event_id") for row in event_rows}
    missing_source_refs = [
        row for row in source_ref_rows if row.get("source_event_id") not in event_id_set
    ]
    punish_rows = by_kind.get("punish", [])
    missing_punished_refs = [
        row for row in punish_rows if row.get("punished_attack_event_id") not in event_id_set
    ]

    transition_summary: dict[str, Any] = {}
    if transition_rows:
        transition_keys = {
            (row.get("run_id"), row.get("episode_id"), row.get("decision_id"))
            for row in transition_rows
        }
        transition_frame_keys = {
            (row.get("run_id"), row.get("episode_id"), row.get("obs_frame"))
            for row in transition_rows
        }
        with_decision = [row for row in event_rows if row.get("decision_id") is not None]
        with_start = [row for row in event_rows if row.get("start_decision_id") is not None]
        with_end = [row for row in event_rows if row.get("end_decision_id") is not None]
        transition_duplicate_keys = collections.Counter(
            (row.get("run_id"), row.get("episode_id"), row.get("decision_id"))
            for row in transition_rows
        )
        transition_episode_last: dict[tuple[Any, Any], dict[str, Any]] = {}
        for row in transition_rows:
            transition_episode_last[row_episode(row)] = row
        projectile_event_counts: dict[str, dict[str, int]] = {}
        for episode, last in sorted(transition_episode_last.items(), key=lambda item: str(item[0])):
            projectile_rows = [
                row for row in by_kind.get("projectile", []) if row_episode(row) == episode
            ]
            event_result_counts = collections.Counter(str(row.get("result")) for row in projectile_rows)
            counter_result_counts = {
                "hit": int(last.get("combat_projectile_hit_self_count") or 0)
                + int(last.get("combat_projectile_hit_opp_count") or 0),
                "blocked": int(last.get("combat_projectile_blocked_self_count") or 0)
                + int(last.get("combat_projectile_blocked_opp_count") or 0),
                "expired": int(last.get("combat_projectile_expired_self_count") or 0)
                + int(last.get("combat_projectile_expired_opp_count") or 0),
                "unknown": int(last.get("combat_projectile_unknown_self_count") or 0)
                + int(last.get("combat_projectile_unknown_opp_count") or 0),
            }
            projectile_event_counts[str(episode)] = {
                "event_rows": len(projectile_rows),
                "counter_started": int(last.get("combat_projectile_started_self_count") or 0)
                + int(last.get("combat_projectile_started_opp_count") or 0),
                "event_hit": event_result_counts.get("hit", 0),
                "event_blocked": event_result_counts.get("blocked", 0),
                "event_expired": event_result_counts.get("expired", 0),
                "event_unknown": event_result_counts.get("unknown", 0),
                "counter_hit": counter_result_counts["hit"],
                "counter_blocked": counter_result_counts["blocked"],
                "counter_expired": counter_result_counts["expired"],
                "counter_unknown": counter_result_counts["unknown"],
            }

        transition_summary = {
            "rows": len(transition_rows),
            "schema_counts": dict(collections.Counter(row.get("transition_schema_version") for row in transition_rows)),
            "combat_event_rows_inside_transition": sum(
                1 for row in transition_rows if row.get("combat_event_schema_version") is not None
            ),
            "duplicate_transition_rows": sum(
                count - 1 for count in transition_duplicate_keys.values() if count > 1
            ),
            "decision_id_joinable": sum(
                (row.get("run_id"), row.get("episode_id"), row.get("decision_id")) in transition_keys
                for row in with_decision
            ),
            "decision_id_total": len(with_decision),
            "start_decision_id_joinable": sum(
                (row.get("run_id"), row.get("episode_id"), row.get("start_decision_id")) in transition_keys
                for row in with_start
            ),
            "start_decision_id_total": len(with_start),
            "end_decision_id_joinable": sum(
                (row.get("run_id"), row.get("episode_id"), row.get("end_decision_id")) in transition_keys
                for row in with_end
            ),
            "end_decision_id_total": len(with_end),
            "frame_id_exact_joinable": sum(
                (row.get("run_id"), row.get("episode_id"), row.get("frame_id")) in transition_frame_keys
                for row in with_decision
            ),
            "frame_id_exact_total": len(with_decision),
            "projectile_event_counter_check": projectile_event_counts,
        }

    return {
        "rows": len(event_rows),
        "schema_counts": dict(schema_counts),
        "unsupported_rows": unsupported_rows,
        "transition_schema_rows_inside_event_log": transition_event_rows,
        "kind_counts": dict(kind_counts),
        "episode_counts": {str(key): value for key, value in episode_counts.items()},
        "duplicate_rows": duplicate_rows,
        "unique_event_keys": len(duplicate_keys),
        "event_id_min": min(event_ids) if event_ids else None,
        "event_id_max": max(event_ids) if event_ids else None,
        "event_id_non_increasing_edges": len(non_increasing_edges),
        "event_id_missing_count": len(event_id_missing),
        "event_id_missing_first": event_id_missing[:20],
        "attack": {
            "rows": len(attacks),
            "result_counts": dict(collections.Counter(str(row.get("result")) for row in attacks)),
            "finalize_reason_counts": dict(collections.Counter(str(row.get("finalize_reason")) for row in attacks)),
            "effective_bucket_counts": dict(attack_bucket_counts),
            "true_unknown_rows": len(true_attack_unknown_rows),
            "true_unknown_examples": [
                {
                    "event_id": row.get("event_id"),
                    "episode_id": row.get("episode_id"),
                    "side": row.get("side"),
                    "bucket": attack_bucket(row),
                    "result": row.get("result"),
                    "finalize_reason": row.get("finalize_reason"),
                    "start_decision_id": row.get("start_decision_id"),
                    "end_decision_id": row.get("end_decision_id"),
                    "projectile_like": row.get("projectile_like"),
                }
                for row in true_attack_unknown_rows[:12]
            ],
        },
        "projectile": {
            "rows": len(by_kind.get("projectile", [])),
            "owner_counts": dict(collections.Counter(str(row.get("owner_side")) for row in by_kind.get("projectile", []))),
            "result_counts": dict(collections.Counter(str(row.get("result")) for row in by_kind.get("projectile", []))),
            "finalize_reason_counts": dict(
                collections.Counter(str(row.get("finalize_reason")) for row in by_kind.get("projectile", []))
            ),
        },
        "throw": {
            "rows": len(by_kind.get("throw", [])),
            "result_counts": dict(collections.Counter(str(row.get("result")) for row in by_kind.get("throw", []))),
            "finalize_reason_counts": dict(
                collections.Counter(str(row.get("finalize_reason")) for row in by_kind.get("throw", []))
            ),
        },
        "attribution": {
            "rows": len(by_kind.get("attribution", [])),
            "source_family_counts": dict(collections.Counter(str(row.get("source_family")) for row in by_kind.get("attribution", []))),
            "edge_type_counts": dict(collections.Counter(str(row.get("edge_type")) for row in by_kind.get("attribution", []))),
            "confidence_counts": dict(collections.Counter(str(row.get("confidence")) for row in by_kind.get("attribution", []))),
            "failure_reason_counts": dict(collections.Counter(str(row.get("failure_reason")) for row in by_kind.get("attribution", []))),
            "defense_result_counts": dict(collections.Counter(str(row.get("defense_result")) for row in by_kind.get("attribution", []))),
        },
        "punish": {
            "rows": len(by_kind.get("punish", [])),
            "source_family_counts": dict(collections.Counter(str(row.get("source_family")) for row in by_kind.get("punish", []))),
            "reason_counts": dict(collections.Counter(str(row.get("reason")) for row in by_kind.get("punish", []))),
            "path_counts": dict(collections.Counter(str(row.get("path")) for row in by_kind.get("punish", []))),
        },
        "refs": {
            "source_refs": len(source_ref_rows),
            "missing_source_refs": len(missing_source_refs),
            "punish_refs": len(punish_rows),
            "missing_punished_attack_refs": len(missing_punished_refs),
        },
        "transition": transition_summary,
    }


def print_text_report(summary: dict[str, Any], examples: int) -> None:
    print("Combat Event Journal Summary")
    print(
        f"rows={summary['rows']} schemas={summary['schema_counts']} "
        f"kinds={summary['kind_counts']}"
    )
    print(
        f"event_id=min:{summary['event_id_min']} max:{summary['event_id_max']} "
        f"non_increasing={summary['event_id_non_increasing_edges']} "
        f"missing={summary['event_id_missing_count']} duplicate_rows={summary['duplicate_rows']}"
    )
    print(f"episodes={summary['episode_counts']}")
    print()

    attack = summary["attack"]
    print("Attack")
    print(f"  rows={attack['rows']}")
    print(f"  result={format_counter(collections.Counter(attack['result_counts']))}")
    print(f"  finalize_reason={format_counter(collections.Counter(attack['finalize_reason_counts']))}")
    print(f"  effective_bucket={format_counter(collections.Counter(attack['effective_bucket_counts']))}")
    print(f"  true_unknown_rows={attack['true_unknown_rows']}")
    for row in attack["true_unknown_examples"][:examples]:
        print(
            "    unknown_example "
            f"event_id={row['event_id']} ep={row['episode_id']} side={row['side']} "
            f"bucket={row['bucket']} reason={row['finalize_reason']} "
            f"start={row['start_decision_id']} end={row['end_decision_id']} "
            f"projectile_like={row['projectile_like']}"
        )
    print()

    for section_name in ("projectile", "throw", "attribution", "punish"):
        section = summary[section_name]
        print(section_name.title())
        print(f"  rows={section['rows']}")
        for key, value in section.items():
            if key == "rows":
                continue
            print(f"  {key}={format_counter(collections.Counter(value))}")
        print()

    refs = summary["refs"]
    print("References")
    print(
        f"  source_refs={refs['source_refs']} missing_source_refs={refs['missing_source_refs']} "
        f"punish_refs={refs['punish_refs']} missing_punished_attack_refs={refs['missing_punished_attack_refs']}"
    )

    transition = summary.get("transition") or {}
    if transition:
        print()
        print("Transition Join")
        print(
            f"  rows={transition['rows']} schemas={transition['schema_counts']} "
            f"combat_rows_inside_transition={transition['combat_event_rows_inside_transition']} "
            f"duplicate_transition_rows={transition['duplicate_transition_rows']}"
        )
        print(
            f"  decision_id={transition['decision_id_joinable']}/{transition['decision_id_total']} "
            f"start_decision_id={transition['start_decision_id_joinable']}/{transition['start_decision_id_total']} "
            f"end_decision_id={transition['end_decision_id_joinable']}/{transition['end_decision_id_total']} "
            f"frame_id_exact={transition['frame_id_exact_joinable']}/{transition['frame_id_exact_total']}"
        )
        print("  Projectile Counter Check")
        for episode, check in transition["projectile_event_counter_check"].items():
            print(
                f"    {episode}: event_rows={check['event_rows']} counter_started={check['counter_started']} "
                f"event H/B/X/U={check['event_hit']}/{check['event_blocked']}/{check['event_expired']}/{check['event_unknown']} "
                f"counter H/B/X/U={check['counter_hit']}/{check['counter_blocked']}/{check['counter_expired']}/{check['counter_unknown']}"
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("event_logs", nargs="+", type=Path, help="combat-events.ndjson file(s)")
    parser.add_argument("--transition-log", type=Path, default=None, help="Optional matching transition log")
    parser.add_argument("--json-output", type=Path, default=None, help="Write machine-readable summary JSON")
    parser.add_argument("--examples", type=int, default=8, help="Number of unknown attack examples to print")
    parser.add_argument(
        "--allow-unsupported-schema",
        action="store_true",
        help="Summarize rows with unsupported combat_event_schema_version instead of failing fast",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    event_rows: list[dict[str, Any]] = []
    transition_rows: list[dict[str, Any]] = []
    errors: list[str] = []

    for path in args.event_logs:
        rows, path_errors = read_ndjson(path)
        event_rows.extend(rows)
        errors.extend(path_errors)
    if args.transition_log is not None:
        transition_rows, path_errors = read_ndjson(args.transition_log)
        errors.extend(path_errors)

    if errors:
        for error in errors[:20]:
            print(error, file=sys.stderr)
        if len(errors) > 20:
            print(f"... {len(errors) - 20} more parse errors", file=sys.stderr)
        return 2

    summary = make_summary(event_rows, transition_rows)
    if summary["unsupported_rows"] and not args.allow_unsupported_schema:
        print(
            f"unsupported combat_event_schema_version rows: {summary['unsupported_rows']} "
            f"schema_counts={summary['schema_counts']}",
            file=sys.stderr,
        )
        return 3
    print_text_report(summary, max(0, args.examples))
    if args.json_output is not None:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
