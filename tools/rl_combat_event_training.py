#!/usr/bin/env python3
"""Combat event journal helpers for opt-in DQN trainer adoption."""

from __future__ import annotations

import collections
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


COMBAT_EVENT_SCHEMA_VERSION = 1
COMBAT_EVENT_TRAINING_MODES = ("off", "validate", "reward-shaping")
COMBAT_EVENT_REWARD_PROFILES = ("safe-v1",)


SAFE_V1_REWARD_TABLE: dict[tuple[str, str], float] = {
    ("attack", "hit"): 0.5,
    ("attack", "blocked"): 0.1,
    ("attack", "blocked_chip"): 0.15,
    ("attack", "parry"): -0.25,
    ("attack", "evaded"): 0.0,
    ("attack", "whiff"): -0.25,
    ("attack", "interrupted"): -0.4,
    ("projectile", "hit"): 0.4,
    ("projectile", "blocked"): 0.1,
    ("projectile", "blocked_chip"): 0.1,
    ("projectile", "parry"): -0.25,
    ("projectile", "expired"): 0.0,
    ("projectile", "evaded"): 0.0,
    ("throw", "success"): 0.5,
    ("throw", "whiff"): -0.35,
    ("punish", "caused"): 0.7,
}


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


@dataclass(frozen=True)
class CombatEventRewardConfig:
    enabled: bool = False
    profile: str = "safe-v1"
    scale: float = 1.0

    def as_metadata(self) -> dict[str, object]:
        table = SAFE_V1_REWARD_TABLE if self.profile == "safe-v1" else {}
        return {
            "enabled": self.enabled,
            "profile": self.profile,
            "scale": self.scale,
            "table": {f"{kind}:{result}": value for (kind, result), value in sorted(table.items())},
        }


@dataclass
class CombatEventRewardStats:
    checked_transition_rows: int = 0
    matched_transition_rows: int = 0
    matched_event_rows: int = 0
    adjusted_transition_rows: int = 0
    attribution_rows_seen: int = 0
    grouped_attribution_source_events: int = 0
    grouped_projectile_parent_events: int = 0
    applied_event_rewards: int = 0
    skipped_non_self_events: int = 0
    skipped_low_confidence_events: int = 0
    skipped_unknown_events: int = 0
    skipped_no_reward_events: int = 0
    skipped_child_projectile_events: int = 0
    capped_duplicate_outcome_rows: int = 0
    grouped_hp_delta_sum: int = 0
    grouped_stun_delta_sum: int = 0
    raw_reward_sum: float = 0.0
    raw_reward_by_action: dict[str, float] = field(default_factory=dict)
    raw_reward_by_outcome: dict[str, float] = field(default_factory=dict)
    event_count_by_outcome: dict[str, int] = field(default_factory=dict)
    capped_duplicate_rows_by_outcome: dict[str, int] = field(default_factory=dict)

    def add_reward(self, action_name: str, outcome_key: str, raw_reward: float) -> None:
        self.applied_event_rewards += 1
        self.raw_reward_sum += raw_reward
        self.raw_reward_by_action[action_name] = self.raw_reward_by_action.get(action_name, 0.0) + raw_reward
        self.raw_reward_by_outcome[outcome_key] = self.raw_reward_by_outcome.get(outcome_key, 0.0) + raw_reward
        self.event_count_by_outcome[outcome_key] = self.event_count_by_outcome.get(outcome_key, 0) + 1

    def as_metadata(self) -> dict[str, object]:
        return {
            "checked_transition_rows": self.checked_transition_rows,
            "matched_transition_rows": self.matched_transition_rows,
            "matched_event_rows": self.matched_event_rows,
            "adjusted_transition_rows": self.adjusted_transition_rows,
            "attribution_rows_seen": self.attribution_rows_seen,
            "grouped_attribution_source_events": self.grouped_attribution_source_events,
            "grouped_projectile_parent_events": self.grouped_projectile_parent_events,
            "applied_event_rewards": self.applied_event_rewards,
            "skipped_non_self_events": self.skipped_non_self_events,
            "skipped_low_confidence_events": self.skipped_low_confidence_events,
            "skipped_unknown_events": self.skipped_unknown_events,
            "skipped_no_reward_events": self.skipped_no_reward_events,
            "skipped_child_projectile_events": self.skipped_child_projectile_events,
            "capped_duplicate_outcome_rows": self.capped_duplicate_outcome_rows,
            "grouped_hp_delta_sum": self.grouped_hp_delta_sum,
            "grouped_stun_delta_sum": self.grouped_stun_delta_sum,
            "raw_reward_sum": self.raw_reward_sum,
            "raw_reward_by_action": dict(sorted(self.raw_reward_by_action.items())),
            "raw_reward_by_outcome": dict(sorted(self.raw_reward_by_outcome.items())),
            "event_count_by_outcome": dict(sorted(self.event_count_by_outcome.items())),
            "capped_duplicate_rows_by_outcome": dict(sorted(self.capped_duplicate_rows_by_outcome.items())),
        }


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
    attributions_by_source_event: dict[tuple[int, int], list[dict[str, object]]] = field(default_factory=dict)
    projectiles_by_parent_attack: dict[tuple[int, int], list[dict[str, object]]] = field(default_factory=dict)
    punishes_by_source_event: dict[tuple[int, int], list[dict[str, object]]] = field(default_factory=dict)

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
            parent_attack_event_id = _int_field(row, "parent_attack_event_id")
            if parent_attack_event_id > 0:
                index.projectiles_by_parent_attack.setdefault((run_id, parent_attack_event_id), []).append(row)
        elif event_kind == "throw":
            index.throw_result_counts[result] += 1
        elif event_kind == "attribution":
            index.attribution_defense_result_counts[str(row.get("defense_result", "unknown"))] += 1
            index.attribution_failure_reason_counts[str(row.get("failure_reason", "unknown"))] += 1
            source_event_id = _int_field(row, "source_event_id")
            if source_event_id > 0:
                index.attributions_by_source_event.setdefault((run_id, source_event_id), []).append(row)
        elif event_kind == "punish":
            source_event_id = _int_field(row, "source_event_id")
            if source_event_id > 0:
                index.punishes_by_source_event.setdefault((run_id, source_event_id), []).append(row)

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


def _reward_table_for_profile(profile: str) -> dict[tuple[str, str], float]:
    if profile == "safe-v1":
        return SAFE_V1_REWARD_TABLE
    return {}


def _record_event_reward(
    config: CombatEventRewardConfig,
    stats: CombatEventRewardStats,
    action_name: str,
    kind: str,
    result: str,
) -> float:
    normalized_result = str(result)
    outcome_key = f"{kind}:{normalized_result}"
    if normalized_result == "unknown":
        stats.skipped_unknown_events += 1
        stats.event_count_by_outcome[outcome_key] = stats.event_count_by_outcome.get(outcome_key, 0) + 1
        return 0.0
    raw_reward = _reward_table_for_profile(config.profile).get((kind, normalized_result))
    if raw_reward is None:
        stats.skipped_no_reward_events += 1
        stats.event_count_by_outcome[outcome_key] = stats.event_count_by_outcome.get(outcome_key, 0) + 1
        return 0.0
    scaled_raw_reward = raw_reward * config.scale
    if scaled_raw_reward != 0.0:
        stats.add_reward(action_name, outcome_key, scaled_raw_reward)
    else:
        stats.skipped_no_reward_events += 1
        stats.event_count_by_outcome[outcome_key] = stats.event_count_by_outcome.get(outcome_key, 0) + 1
    return scaled_raw_reward


def _record_capped_duplicate(stats: CombatEventRewardStats, kind: str, result: str) -> None:
    outcome_key = f"{kind}:{result}"
    stats.capped_duplicate_outcome_rows += 1
    stats.capped_duplicate_rows_by_outcome[outcome_key] = (
        stats.capped_duplicate_rows_by_outcome.get(outcome_key, 0) + 1
    )
    stats.event_count_by_outcome[outcome_key] = stats.event_count_by_outcome.get(outcome_key, 0) + 1


def _same_self_side_event(row: dict[str, object]) -> bool:
    kind = str(row.get("event_kind", ""))
    if kind == "attack":
        return str(row.get("side", "")) == "self"
    if kind in ("projectile", "throw"):
        return str(row.get("owner_side", "")) == "self"
    if kind in ("attribution", "punish"):
        return str(row.get("source_side", row.get("punisher_side", ""))) == "self"
    return False


def _attack_event_reward(
    index: CombatEventIndex,
    event: dict[str, object],
    action_name: str,
    config: CombatEventRewardConfig,
    stats: CombatEventRewardStats,
) -> float:
    run_id, _episode_id, event_id = _event_key(event)
    result = str(event.get("result", "unknown"))
    finalize_reason = str(event.get("finalize_reason", "unknown"))
    raw_reward = 0.0

    if result == "whiff":
        raw_reward += _record_event_reward(config, stats, action_name, "attack", "whiff")
    elif result == "interrupted":
        raw_reward += _record_event_reward(config, stats, action_name, "attack", "interrupted")
    elif result == "contact":
        attribution_candidates = [
            row
            for row in index.attributions_by_source_event.get((run_id, event_id), [])
            if str(row.get("source_side", "")) == "self"
            and str(row.get("failure_reason", "none")) == "none"
        ]
        if attribution_candidates:
            stats.attribution_rows_seen += len(attribution_candidates)
            stats.grouped_attribution_source_events += 1
            stats.grouped_hp_delta_sum += sum(_int_field(row, "target_hp_delta") for row in attribution_candidates)
            stats.grouped_stun_delta_sum += sum(_int_field(row, "target_stun_delta") for row in attribution_candidates)
        attributions = [
            row
            for row in attribution_candidates
            if str(row.get("confidence", "unknown")) == "high"
        ]
        for attribution in attribution_candidates:
            if str(attribution.get("confidence", "unknown")) != "high":
                stats.skipped_low_confidence_events += 1
                outcome_key = f"attack:{attribution.get('defense_result', 'unknown')}"
                stats.event_count_by_outcome[outcome_key] = stats.event_count_by_outcome.get(outcome_key, 0) + 1
        if not attributions:
            if not attribution_candidates:
                raw_reward += _record_event_reward(config, stats, action_name, "attack", "contact")
        rewarded_results: set[str] = set()
        for attribution in attributions:
            attribution_result = str(attribution.get("defense_result", "unknown"))
            if attribution_result in rewarded_results:
                _record_capped_duplicate(stats, "attack", attribution_result)
                continue
            rewarded_results.add(attribution_result)
            raw_reward += _record_event_reward(
                config,
                stats,
                action_name,
                "attack",
                attribution_result,
            )
    elif result == "unknown" and finalize_reason == "projectile_claimed":
        projectiles = [
            row
            for row in index.projectiles_by_parent_attack.get((run_id, event_id), [])
            if str(row.get("owner_side", "")) == "self"
        ]
        if not projectiles:
            raw_reward += _record_event_reward(config, stats, action_name, "attack", "unknown")
        if projectiles:
            stats.grouped_projectile_parent_events += 1
        rewarded_projectile_results: set[str] = set()
        for projectile in projectiles:
            projectile_result = str(projectile.get("result", "unknown"))
            if projectile_result in rewarded_projectile_results:
                _record_capped_duplicate(stats, "projectile", projectile_result)
                continue
            rewarded_projectile_results.add(projectile_result)
            raw_reward += _record_event_reward(
                config,
                stats,
                action_name,
                "projectile",
                projectile_result,
            )
    else:
        raw_reward += _record_event_reward(config, stats, action_name, "attack", result)

    self_punishes = [
        punish
        for punish in index.punishes_by_source_event.get((run_id, event_id), [])
        if str(punish.get("punisher_side", "")) == "self"
    ]
    if self_punishes:
        raw_reward += _record_event_reward(config, stats, action_name, "punish", "caused")
        for _punish in self_punishes[1:]:
            _record_capped_duplicate(stats, "punish", "caused")

    return raw_reward


def reward_adjustment_for_transition(
    index: CombatEventIndex | None,
    row: dict[str, object],
    action_name: str | None,
    action_start: bool,
    config: CombatEventRewardConfig,
    stats: CombatEventRewardStats,
) -> float:
    if index is None or not config.enabled or action_name is None or not action_start:
        return 0.0
    stats.checked_transition_rows += 1
    key = (
        _int_field(row, "run_id"),
        _int_field(row, "episode_id"),
        _int_field(row, "decision_id"),
    )
    events = index.by_start_decision.get(key, [])
    if not events:
        return 0.0
    stats.matched_transition_rows += 1
    stats.matched_event_rows += len(events)

    raw_adjustment = 0.0
    for event in events:
        if not _same_self_side_event(event):
            stats.skipped_non_self_events += 1
            continue
        event_kind = str(event.get("event_kind", "unknown"))
        if event_kind == "attack":
            raw_adjustment += _attack_event_reward(index, event, action_name, config, stats)
        elif event_kind == "throw":
            raw_adjustment += _record_event_reward(
                config,
                stats,
                action_name,
                "throw",
                str(event.get("result", "unknown")),
            )
        elif event_kind == "projectile":
            parent_attack_event_id = _int_field(event, "parent_attack_event_id")
            if parent_attack_event_id > 0:
                stats.skipped_child_projectile_events += 1
                continue
            raw_adjustment += _record_event_reward(
                config,
                stats,
                action_name,
                "projectile",
                str(event.get("result", "unknown")),
            )
        else:
            stats.skipped_no_reward_events += 1

    if raw_adjustment != 0.0:
        stats.adjusted_transition_rows += 1
    return raw_adjustment


def validate_combat_event_training_logs(
    event_paths: list[str],
    transition_paths: list[str],
    transition_rows: list[dict[str, object]],
    mode: str = "validate",
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
        mode=mode,
        index=index,
        transition_scan=transition_scan,
        join_stats=join_stats,
        fatal_errors=tuple(fatal_errors),
    )
