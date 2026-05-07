#!/usr/bin/env python3
"""Combat event journal helpers for opt-in DQN trainer adoption."""

from __future__ import annotations

import collections
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


COMBAT_EVENT_SCHEMA_VERSION = 1
COMBAT_EVENT_TRAINING_MODES = ("off", "validate")


def _counter_dict(counter: collections.Counter[object]) -> dict[str, int]:
    return {str(key): int(value) for key, value in sorted(counter.items(), key=lambda item: str(item[0]))}


def _int_field(row: dict[str, object], name: str) -> int:
    try:
        return int(row.get(name, 0) or 0)
    except (TypeError, ValueError):
        return 0


def _event_key(row: dict[str, object]) -> tuple[int, int, int]:
    return (
        _int_field(row, "run_id"),
        _int_field(row, "episode_id"),
        _int_field(row, "event_id"),
    )


def _run_event_key(row: dict[str, object], field_name: str) -> tuple[int, int]:
    return (_int_field(row, "run_id"), _int_field(row, field_name))


@dataclass
class CombatEventIndex:
    paths: tuple[str, ...]
    rows: list[dict[str, object]]
    malformed_json_rows: int = 0
    non_event_rows: int = 0
    unsupported_schema_rows: int = 0
    schema_counts: collections.Counter[object] = field(default_factory=collections.Counter)
    kind_counts: collections.Counter[str] = field(default_factory=collections.Counter)
    result_counts: collections.Counter[str] = field(default_factory=collections.Counter)
    attack_result_counts: collections.Counter[str] = field(default_factory=collections.Counter)
    attack_finalize_reason_counts: collections.Counter[str] = field(default_factory=collections.Counter)
    projectile_result_counts: collections.Counter[str] = field(default_factory=collections.Counter)
    throw_result_counts: collections.Counter[str] = field(default_factory=collections.Counter)
    attribution_defense_result_counts: collections.Counter[str] = field(default_factory=collections.Counter)
    attribution_failure_reason_counts: collections.Counter[str] = field(default_factory=collections.Counter)
    side_counts: collections.Counter[str] = field(default_factory=collections.Counter)
    source_side_counts: collections.Counter[str] = field(default_factory=collections.Counter)
    target_side_counts: collections.Counter[str] = field(default_factory=collections.Counter)
    duplicate_event_rows: int = 0
    event_id_non_increasing: int = 0
    missing_event_ids: int = 0
    event_id_min: int = 0
    event_id_max: int = 0
    source_ref_rows: int = 0
    missing_source_refs: int = 0
    parent_ref_rows: int = 0
    missing_parent_refs: int = 0
    punished_ref_rows: int = 0
    missing_punished_refs: int = 0
    by_event_key: dict[tuple[int, int, int], dict[str, object]] = field(default_factory=dict)
    by_start_decision: dict[tuple[int, int, int], list[dict[str, object]]] = field(default_factory=dict)
    by_end_decision: dict[tuple[int, int, int], list[dict[str, object]]] = field(default_factory=dict)

    @property
    def has_rows(self) -> bool:
        return bool(self.rows)

    def as_metadata(self) -> dict[str, object]:
        return {
            "paths": list(self.paths),
            "rows": len(self.rows),
            "malformed_json_rows": self.malformed_json_rows,
            "non_event_rows": self.non_event_rows,
            "unsupported_schema_rows": self.unsupported_schema_rows,
            "schema_counts": _counter_dict(self.schema_counts),
            "kind_counts": _counter_dict(self.kind_counts),
            "result_counts": _counter_dict(self.result_counts),
            "attack_result_counts": _counter_dict(self.attack_result_counts),
            "attack_finalize_reason_counts": _counter_dict(self.attack_finalize_reason_counts),
            "projectile_result_counts": _counter_dict(self.projectile_result_counts),
            "throw_result_counts": _counter_dict(self.throw_result_counts),
            "attribution_defense_result_counts": _counter_dict(self.attribution_defense_result_counts),
            "attribution_failure_reason_counts": _counter_dict(self.attribution_failure_reason_counts),
            "side_counts": _counter_dict(self.side_counts),
            "source_side_counts": _counter_dict(self.source_side_counts),
            "target_side_counts": _counter_dict(self.target_side_counts),
            "event_id": {
                "min": self.event_id_min,
                "max": self.event_id_max,
                "missing": self.missing_event_ids,
                "non_increasing": self.event_id_non_increasing,
                "duplicate_rows": self.duplicate_event_rows,
            },
            "references": {
                "source_ref_rows": self.source_ref_rows,
                "missing_source_refs": self.missing_source_refs,
                "parent_ref_rows": self.parent_ref_rows,
                "missing_parent_refs": self.missing_parent_refs,
                "punished_ref_rows": self.punished_ref_rows,
                "missing_punished_refs": self.missing_punished_refs,
            },
            "unknown_rows": {
                "attack": int(self.attack_result_counts.get("unknown", 0)),
                "projectile": int(self.projectile_result_counts.get("unknown", 0)),
                "throw": int(self.throw_result_counts.get("unknown", 0)),
                "attribution": int(self.attribution_defense_result_counts.get("unknown", 0)),
                "no_source_candidate": int(self.attribution_failure_reason_counts.get("no_source_candidate", 0)),
            },
        }


@dataclass(frozen=True)
class CombatEventTrainingValidation:
    mode: str
    index: CombatEventIndex | None = None
    transition_scan: dict[str, object] = field(default_factory=dict)
    join_stats: dict[str, object] = field(default_factory=dict)
    fatal_errors: tuple[str, ...] = ()

    @property
    def enabled(self) -> bool:
        return self.mode != "off"

    def as_metadata(self) -> dict[str, object]:
        metadata: dict[str, object] = {
            "mode": self.mode,
            "enabled": self.enabled,
            "fatal_errors": list(self.fatal_errors),
        }
        if self.index is not None:
            metadata["event_index"] = self.index.as_metadata()
        if self.transition_scan:
            metadata["transition_scan"] = dict(self.transition_scan)
        if self.join_stats:
            metadata["join_stats"] = dict(self.join_stats)
        return metadata

    def summary_line(self) -> str:
        if self.index is None:
            return f"mode:{self.mode} enabled:0"
        unknown_rows = self.index.as_metadata()["unknown_rows"]
        join = self.join_stats
        return (
            f"mode:{self.mode} events:{len(self.index.rows)} "
            f"schemas:{_counter_dict(self.index.schema_counts)} "
            f"kinds:{_counter_dict(self.index.kind_counts)} "
            f"start_join:{join.get('start_decision_joined_rows', 0)}/"
            f"{join.get('start_decision_ref_rows', 0)} "
            f"end_join:{join.get('end_decision_joined_rows', 0)}/"
            f"{join.get('end_decision_ref_rows', 0)} "
            f"missing_refs:{self.index.missing_source_refs + self.index.missing_parent_refs + self.index.missing_punished_refs} "
            f"unknown:{unknown_rows} "
            f"errors:{len(self.fatal_errors)}"
        )


def read_combat_event_index(paths: list[str]) -> CombatEventIndex:
    rows: list[dict[str, object]] = []
    schema_counts: collections.Counter[object] = collections.Counter()
    malformed_json_rows = 0
    non_event_rows = 0
    unsupported_schema_rows = 0
    last_event_id_by_run: dict[int, int] = {}
    event_id_non_increasing = 0

    for path_text in paths:
        path = Path(path_text)
        with path.open("r", encoding="utf-8") as stream:
            for line in stream:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    row = json.loads(stripped)
                except json.JSONDecodeError:
                    malformed_json_rows += 1
                    continue
                if not isinstance(row, dict):
                    non_event_rows += 1
                    continue
                schema = row.get("combat_event_schema_version")
                if schema is None:
                    non_event_rows += 1
                    continue
                schema_counts[schema] += 1
                if schema != COMBAT_EVENT_SCHEMA_VERSION:
                    unsupported_schema_rows += 1
                    continue
                rows.append(row)
                run_id = _int_field(row, "run_id")
                event_id = _int_field(row, "event_id")
                last_event_id = last_event_id_by_run.get(run_id)
                if last_event_id is not None and event_id <= last_event_id:
                    event_id_non_increasing += 1
                last_event_id_by_run[run_id] = event_id

    index = CombatEventIndex(
        paths=tuple(paths),
        rows=rows,
        malformed_json_rows=malformed_json_rows,
        non_event_rows=non_event_rows,
        unsupported_schema_rows=unsupported_schema_rows,
        schema_counts=schema_counts,
        event_id_non_increasing=event_id_non_increasing,
    )
    _populate_index(index)
    return index


def _populate_index(index: CombatEventIndex) -> None:
    key_counts: collections.Counter[tuple[int, int, int]] = collections.Counter(_event_key(row) for row in index.rows)
    index.duplicate_event_rows = sum(count - 1 for count in key_counts.values() if count > 1)
    index.by_event_key = {}
    for row in index.rows:
        key = _event_key(row)
        if key not in index.by_event_key:
            index.by_event_key[key] = row
    run_event_ids: dict[int, set[int]] = collections.defaultdict(set)
    run_event_keys: set[tuple[int, int]] = set()

    for row in index.rows:
        run_id, _episode_id, event_id = _event_key(row)
        if event_id > 0:
            run_event_ids[run_id].add(event_id)
            run_event_keys.add((run_id, event_id))
        event_kind = str(row.get("event_kind", "unknown"))
        result = str(row.get("result", "unknown"))
        index.kind_counts[event_kind] += 1
        index.result_counts[result] += 1
        if row.get("side") is not None:
            index.side_counts[str(row.get("side"))] += 1
        if row.get("owner_side") is not None:
            index.side_counts[str(row.get("owner_side"))] += 1
        if row.get("source_side") is not None:
            index.source_side_counts[str(row.get("source_side"))] += 1
        if row.get("target_side") is not None:
            index.target_side_counts[str(row.get("target_side"))] += 1
        if event_kind == "attack":
            index.attack_result_counts[result] += 1
            index.attack_finalize_reason_counts[str(row.get("finalize_reason", "unknown"))] += 1
        elif event_kind == "projectile":
            index.projectile_result_counts[result] += 1
        elif event_kind == "throw":
            index.throw_result_counts[result] += 1
        elif event_kind == "attribution":
            index.attribution_defense_result_counts[str(row.get("defense_result", "unknown"))] += 1
            index.attribution_failure_reason_counts[str(row.get("failure_reason", "unknown"))] += 1

        start_decision_id = _int_field(row, "start_decision_id")
        if start_decision_id > 0:
            index.by_start_decision.setdefault((run_id, _episode_id, start_decision_id), []).append(row)
        end_decision_id = _int_field(row, "end_decision_id")
        if end_decision_id > 0:
            index.by_end_decision.setdefault((run_id, _episode_id, end_decision_id), []).append(row)

    event_ids = [event_id for ids in run_event_ids.values() for event_id in ids]
    if event_ids:
        index.event_id_min = min(event_ids)
        index.event_id_max = max(event_ids)
    for event_ids_for_run in run_event_ids.values():
        if not event_ids_for_run:
            continue
        expected = max(event_ids_for_run) - min(event_ids_for_run) + 1
        index.missing_event_ids += max(0, expected - len(event_ids_for_run))

    for row in index.rows:
        source_event_id = _int_field(row, "source_event_id")
        if source_event_id > 0:
            index.source_ref_rows += 1
            if _run_event_key(row, "source_event_id") not in run_event_keys:
                index.missing_source_refs += 1
        parent_attack_event_id = _int_field(row, "parent_attack_event_id")
        if parent_attack_event_id > 0:
            index.parent_ref_rows += 1
            if _run_event_key(row, "parent_attack_event_id") not in run_event_keys:
                index.missing_parent_refs += 1
        punished_attack_event_id = _int_field(row, "punished_attack_event_id")
        if punished_attack_event_id > 0:
            index.punished_ref_rows += 1
            if _run_event_key(row, "punished_attack_event_id") not in run_event_keys:
                index.missing_punished_refs += 1


def scan_transition_logs_for_combat_events(paths: list[str]) -> dict[str, object]:
    scanned_rows = 0
    combat_event_rows = 0
    malformed_combat_event_rows = 0
    schema_counts: collections.Counter[object] = collections.Counter()
    marker = b'"combat_event_schema_version"'
    for path_text in paths:
        with Path(path_text).open("rb") as stream:
            for raw_line in stream:
                stripped = raw_line.strip()
                if not stripped:
                    continue
                scanned_rows += 1
                if marker not in stripped:
                    continue
                combat_event_rows += 1
                try:
                    row = json.loads(stripped.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    malformed_combat_event_rows += 1
                    continue
                if isinstance(row, dict):
                    schema_counts[row.get("combat_event_schema_version")] += 1
    return {
        "paths": list(paths),
        "scanned_rows": scanned_rows,
        "combat_event_rows": combat_event_rows,
        "malformed_combat_event_rows": malformed_combat_event_rows,
        "schema_counts": _counter_dict(schema_counts),
    }


def build_transition_join_stats(
    index: CombatEventIndex,
    transition_rows: list[dict[str, object]],
) -> dict[str, object]:
    transition_decisions: set[tuple[int, int, int]] = set()
    episodes: set[tuple[int, int]] = set()
    for row in transition_rows:
        run_id = _int_field(row, "run_id")
        episode_id = _int_field(row, "episode_id")
        decision_id = _int_field(row, "decision_id")
        episodes.add((run_id, episode_id))
        if decision_id > 0:
            transition_decisions.add((run_id, episode_id, decision_id))

    start_ref_rows = 0
    start_joined_rows = 0
    end_ref_rows = 0
    end_joined_rows = 0
    decision_ref_rows = 0
    decision_joined_rows = 0
    episode_rows = 0
    episode_joined_rows = 0

    for row in index.rows:
        run_id = _int_field(row, "run_id")
        episode_id = _int_field(row, "episode_id")
        if run_id != 0 or episode_id != 0:
            episode_rows += 1
            if (run_id, episode_id) in episodes:
                episode_joined_rows += 1
        if (run_id, episode_id) not in episodes:
            continue
        start_decision_id = _int_field(row, "start_decision_id")
        if start_decision_id > 0:
            start_ref_rows += 1
            if (run_id, episode_id, start_decision_id) in transition_decisions:
                start_joined_rows += 1
        end_decision_id = _int_field(row, "end_decision_id")
        if end_decision_id > 0:
            end_ref_rows += 1
            if (run_id, episode_id, end_decision_id) in transition_decisions:
                end_joined_rows += 1
        decision_id = _int_field(row, "decision_id")
        if decision_id > 0:
            decision_ref_rows += 1
            if (run_id, episode_id, decision_id) in transition_decisions:
                decision_joined_rows += 1

    return {
        "transition_rows": len(transition_rows),
        "transition_episodes": len(episodes),
        "transition_decisions": len(transition_decisions),
        "event_episode_rows": episode_rows,
        "event_episode_joined_rows": episode_joined_rows,
        "start_decision_ref_rows": start_ref_rows,
        "start_decision_joined_rows": start_joined_rows,
        "start_decision_missing_rows": start_ref_rows - start_joined_rows,
        "end_decision_ref_rows": end_ref_rows,
        "end_decision_joined_rows": end_joined_rows,
        "end_decision_missing_rows": end_ref_rows - end_joined_rows,
        "decision_ref_rows": decision_ref_rows,
        "decision_joined_rows": decision_joined_rows,
        "decision_missing_rows": decision_ref_rows - decision_joined_rows,
    }


def validate_combat_event_training_logs(
    event_paths: list[str],
    transition_paths: list[str],
    transition_rows: list[dict[str, object]],
) -> CombatEventTrainingValidation:
    index = read_combat_event_index(event_paths)
    transition_scan = scan_transition_logs_for_combat_events(transition_paths)
    join_stats = build_transition_join_stats(index, transition_rows)
    fatal_errors: list[str] = []

    if not index.has_rows:
        fatal_errors.append("no combat event rows found")
    if index.malformed_json_rows:
        fatal_errors.append(f"event log malformed JSON rows={index.malformed_json_rows}")
    if index.non_event_rows:
        fatal_errors.append(f"event log non-combat rows={index.non_event_rows}")
    if index.unsupported_schema_rows:
        fatal_errors.append(f"unsupported combat event schema rows={index.unsupported_schema_rows}")
    if index.duplicate_event_rows:
        fatal_errors.append(f"duplicate event rows={index.duplicate_event_rows}")
    if index.event_id_non_increasing:
        fatal_errors.append(f"non-increasing event ids={index.event_id_non_increasing}")
    if index.missing_source_refs:
        fatal_errors.append(f"missing source refs={index.missing_source_refs}")
    if index.missing_parent_refs:
        fatal_errors.append(f"missing parent projectile refs={index.missing_parent_refs}")
    if index.missing_punished_refs:
        fatal_errors.append(f"missing punished attack refs={index.missing_punished_refs}")
    if int(transition_scan.get("combat_event_rows", 0) or 0) > 0:
        fatal_errors.append(f"transition log combat event rows={transition_scan.get('combat_event_rows', 0)}")
    if index.has_rows and int(join_stats.get("event_episode_joined_rows", 0) or 0) <= 0:
        fatal_errors.append("no combat event episodes overlap transition rows")
    if int(join_stats.get("start_decision_missing_rows", 0) or 0) > 0:
        fatal_errors.append(f"missing start decision joins={join_stats.get('start_decision_missing_rows', 0)}")
    if int(join_stats.get("decision_missing_rows", 0) or 0) > 0:
        fatal_errors.append(f"missing attribution decision joins={join_stats.get('decision_missing_rows', 0)}")

    return CombatEventTrainingValidation(
        mode="validate",
        index=index,
        transition_scan=transition_scan,
        join_stats=join_stats,
        fatal_errors=tuple(fatal_errors),
    )
