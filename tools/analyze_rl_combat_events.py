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
RL_POLICY_ACTION_STAND_NORMAL = 6
RL_POLICY_ACTION_COMMAND_NORMAL = 7
RL_POLICY_ACTION_THROW = 8
RL_POLICY_ACTION_CROUCH_NORMAL = 15
RL_POLICY_ACTION_AIR_NORMAL = 16
RL_POLICY_ACTION_RYU_SHINKUU_HADOUKEN = 1220
RL_POLICY_ACTION_RYU_DENJIN_HADOUKEN = 1221
RL_POLICY_ACTION_RYU_SHIN_SHORYUKEN = 1222
RL_POLICY_ACTION_RYU_SHORYUKEN = 1228
RL_POLICY_ACTION_RYU_FIREBALL = 1229
RL_POLICY_ACTION_RYU_TATSU = 1230
RL_POLICY_ACTION_RYU_JOUDAN = 1231
RL_POLICY_ACTION_RYU_AIR_TATSU = 1246

PUNCH_SUB_ACTIONS = {1, 2, 3}
KICK_SUB_ACTIONS = {4, 5, 6}
BUTTON_NAME_BY_SUB_ACTION = {
    1: "lp",
    2: "mp",
    3: "hp",
    4: "lk",
    5: "mk",
    6: "hk",
}
STRENGTH_TAG_BY_SUB_ACTION = {
    1: "light",
    2: "medium",
    3: "heavy",
    4: "light",
    5: "medium",
    6: "heavy",
}
SUPER_ACTION_IDS = {
    RL_POLICY_ACTION_RYU_SHINKUU_HADOUKEN,
    RL_POLICY_ACTION_RYU_DENJIN_HADOUKEN,
    RL_POLICY_ACTION_RYU_SHIN_SHORYUKEN,
}
PROJECTILE_ACTION_IDS = {
    RL_POLICY_ACTION_RYU_FIREBALL,
    RL_POLICY_ACTION_RYU_SHINKUU_HADOUKEN,
    RL_POLICY_ACTION_RYU_DENJIN_HADOUKEN,
}
SPECIAL_ACTION_IDS = {
    RL_POLICY_ACTION_RYU_FIREBALL,
    RL_POLICY_ACTION_RYU_SHORYUKEN,
    RL_POLICY_ACTION_RYU_TATSU,
    RL_POLICY_ACTION_RYU_JOUDAN,
    RL_POLICY_ACTION_RYU_AIR_TATSU,
}
NORMAL_ACTION_IDS = {
    RL_POLICY_ACTION_STAND_NORMAL,
    RL_POLICY_ACTION_COMMAND_NORMAL,
    RL_POLICY_ACTION_CROUCH_NORMAL,
    RL_POLICY_ACTION_AIR_NORMAL,
}


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


def event_lookup_key(row: dict[str, Any]) -> tuple[Any, Any]:
    return row.get("run_id"), row.get("event_id")


def source_lookup_key(row: dict[str, Any]) -> tuple[Any, Any]:
    return row.get("run_id"), row.get("source_event_id")


def attribution_source_target_key(row: dict[str, Any]) -> tuple[Any, Any, Any, Any]:
    return row.get("run_id"), row.get("episode_id"), row.get("source_event_id"), row.get("target_side")


def transition_lookup_key(row: dict[str, Any], decision_field: str = "decision_id") -> tuple[Any, Any, Any]:
    return row.get("run_id"), row.get("episode_id"), row.get(decision_field)


def side_sort_key(side: str) -> tuple[int, str]:
    if side == "self":
        return 0, side
    if side == "opponent":
        return 1, side
    return 2, side


def attack_bucket(row: dict[str, Any]) -> str:
    result = str(row.get("result", "unknown"))
    reason = str(row.get("finalize_reason", "unknown"))
    projectile_like = int(row.get("projectile_like") or 0)

    if reason == "projectile_claimed":
        return "delegated_to_projectile"
    if result == "contact" or reason == "contact_resolved":
        return "contact_resolved"
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


def as_int(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    return 0


def opposite_side(side: str) -> str:
    if side == "self":
        return "opponent"
    if side == "opponent":
        return "self"
    return "unknown"


def button_name(sub_action_id: int) -> str:
    return BUTTON_NAME_BY_SUB_ACTION.get(sub_action_id, f"sub{sub_action_id}")


def action_name(action_id: int, sub_action_id: int, event_kind: str) -> str:
    button = button_name(sub_action_id)
    if event_kind == "throw" or action_id == RL_POLICY_ACTION_THROW:
        return "throw"
    if action_id == RL_POLICY_ACTION_STAND_NORMAL:
        return f"stand-{button}"
    if action_id == RL_POLICY_ACTION_COMMAND_NORMAL:
        if sub_action_id == 3:
            return "forward-hp"
        return f"command-{button}"
    if action_id == RL_POLICY_ACTION_CROUCH_NORMAL:
        return f"crouch-{button}"
    if action_id == RL_POLICY_ACTION_AIR_NORMAL:
        return f"air-{button}"
    if action_id == RL_POLICY_ACTION_RYU_FIREBALL:
        return f"fireball-{button}"
    if action_id == RL_POLICY_ACTION_RYU_SHORYUKEN:
        return f"shoryuken-{button}"
    if action_id == RL_POLICY_ACTION_RYU_TATSU:
        return f"tatsu-{button}"
    if action_id == RL_POLICY_ACTION_RYU_JOUDAN:
        return f"joudan-{button}"
    if action_id == RL_POLICY_ACTION_RYU_AIR_TATSU:
        return f"air-tatsu-{button}"
    if action_id == RL_POLICY_ACTION_RYU_SHINKUU_HADOUKEN:
        return "shinkuu-hadouken"
    if action_id == RL_POLICY_ACTION_RYU_DENJIN_HADOUKEN:
        return "denjin-hadouken"
    if action_id == RL_POLICY_ACTION_RYU_SHIN_SHORYUKEN:
        return "shin-shoryuken"
    if action_id == 0:
        return f"unknown-{event_kind}"
    return f"action-{action_id}/{sub_action_id}"


def action_tags(action_id: int, sub_action_id: int, event_kind: str) -> list[str]:
    tags: set[str] = {event_kind}
    if event_kind == "throw" or action_id == RL_POLICY_ACTION_THROW:
        tags.update({"throw", "ground"})
        return sorted(tags)

    button = BUTTON_NAME_BY_SUB_ACTION.get(sub_action_id)
    if button is not None:
        tags.add(button)
        tags.add(STRENGTH_TAG_BY_SUB_ACTION[sub_action_id])
        if sub_action_id in PUNCH_SUB_ACTIONS:
            tags.add("punch")
        elif sub_action_id in KICK_SUB_ACTIONS:
            tags.add("kick")

    if event_kind == "projectile" or action_id in PROJECTILE_ACTION_IDS:
        tags.add("projectile")
    if action_id in SUPER_ACTION_IDS:
        tags.update({"super", "special_or_super"})
    if action_id in SPECIAL_ACTION_IDS:
        tags.update({"special", "special_or_super"})
    if action_id in NORMAL_ACTION_IDS:
        tags.add("normal")

    if action_id == RL_POLICY_ACTION_STAND_NORMAL:
        tags.update({"ground", "stand"})
    elif action_id == RL_POLICY_ACTION_COMMAND_NORMAL:
        tags.update({"ground", "stand", "command_normal"})
    elif action_id == RL_POLICY_ACTION_CROUCH_NORMAL:
        tags.update({"ground", "crouch"})
    elif action_id in (RL_POLICY_ACTION_AIR_NORMAL, RL_POLICY_ACTION_RYU_AIR_TATSU):
        tags.add("air")
    elif action_id != 0:
        tags.add("ground")

    return sorted(tags)


def source_action_meta(row: dict[str, Any], event_kind: str) -> tuple[int, int]:
    if event_kind == "throw":
        return RL_POLICY_ACTION_THROW, as_int(row.get("kind_of_waza"))
    action_id = as_int(row.get("engine_action_id"))
    sub_action_id = as_int(row.get("engine_sub_action_id"))
    if action_id == 0:
        action_id = as_int(row.get("policy_action_id"))
        sub_action_id = as_int(row.get("policy_sub_action_id"))
    return action_id, sub_action_id


def projectile_result_bucket(projectile: dict[str, Any]) -> str:
    result = str(projectile.get("result", "unknown"))
    return f"projectile_{result}"


def resolved_attack_bucket(
    row: dict[str, Any],
    projectiles_by_parent: dict[tuple[Any, Any, Any], list[dict[str, Any]]],
) -> str:
    bucket = attack_bucket(row)
    if bucket != "delegated_to_projectile":
        return bucket

    key = (row.get("run_id"), row.get("episode_id"), row.get("event_id"))
    projectiles = projectiles_by_parent.get(key, [])
    if not projectiles:
        return "projectile_missing"
    if len(projectiles) > 1:
        return "projectile_multi"
    return projectile_result_bucket(projectiles[0])


def summarize_side_rows(
    rows: list[dict[str, Any]],
    side_field: str,
    counter_fields: list[str],
) -> dict[str, dict[str, Any]]:
    summary: dict[str, dict[str, Any]] = {}
    sides = sorted({str(row.get(side_field, "unknown")) for row in rows}, key=side_sort_key)
    for side in sides:
        side_rows = [row for row in rows if str(row.get(side_field, "unknown")) == side]
        side_summary: dict[str, Any] = {"rows": len(side_rows)}
        for field in counter_fields:
            side_summary[f"{field}_counts"] = dict(collections.Counter(str(row.get(field)) for row in side_rows))
        summary[side] = side_summary
    return summary


def attribution_unknown_bucket(
    row: dict[str, Any],
    events_by_id: dict[tuple[Any, Any], dict[str, Any]],
) -> str:
    if str(row.get("defense_result")) != "unknown":
        return str(row.get("defense_result"))

    failure_reason = str(row.get("failure_reason", "none"))
    if failure_reason != "none":
        return f"unknown_failure_{failure_reason}"

    source_event_id = row.get("source_event_id")
    if source_event_id in (None, 0):
        return "unknown_missing_source_ref"

    source = events_by_id.get(source_lookup_key(row))
    if source is None:
        return "unknown_missing_source_ref"

    if as_int(row.get("target_hp_delta")) > 0 or as_int(row.get("target_stun_delta")) > 0:
        return "unknown_has_damage_delta"
    if as_int(row.get("target_block_reaction")) > 0:
        return "unknown_has_block_reaction"
    if as_int(row.get("target_parry_started")) > 0:
        return "unknown_has_parry"
    if as_int(row.get("target_throw_caught")) > 0:
        return "unknown_has_throw_caught"

    source_kind = str(source.get("event_kind", "unknown"))
    source_result = str(source.get("result", "unknown"))
    source_reason = str(source.get("finalize_reason", "unknown"))
    if source_kind == "attack":
        if source_reason == "superseded_by_new_start":
            return "unknown_source_rollover"
        if source_reason == "basic_unknown_timeout":
            return "unknown_source_timeout"
        if source_reason == "episode_flush":
            return "unknown_source_episode_flush"
        if source_result == "whiff":
            return "unknown_source_whiff_later"

    edge_type = str(row.get("edge_type", "unknown"))
    if edge_type == "hit_stop":
        return "unknown_hitstop_no_damage"
    if as_int(row.get("target_airborne")) > 0 or str(row.get("target_state")) == "air":
        return "unknown_target_air"
    if as_int(row.get("target_attack_state_active")) > 0 or str(row.get("target_state")) == "attacking":
        return "unknown_target_attacking"
    if edge_type == "contact_state":
        return "unknown_contact_no_damage"
    return "unknown_other"


def summarize_attribution_unknown_side_rows(
    rows: list[dict[str, Any]],
    side_field: str,
    events_by_id: dict[tuple[Any, Any], dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    summary: dict[str, dict[str, Any]] = {}
    sides = sorted({str(row.get(side_field, "unknown")) for row in rows}, key=side_sort_key)
    for side in sides:
        side_rows = [row for row in rows if str(row.get(side_field, "unknown")) == side]
        summary[side] = {
            "rows": len(side_rows),
            "bucket_counts": dict(collections.Counter(attribution_unknown_bucket(row, events_by_id) for row in side_rows)),
            "edge_type_counts": dict(collections.Counter(str(row.get("edge_type")) for row in side_rows)),
            "target_state_counts": dict(collections.Counter(str(row.get("target_state")) for row in side_rows)),
        }
    return summary


def attribution_unknown_reconciliation_record(
    row: dict[str, Any],
    events_by_id: dict[tuple[Any, Any], dict[str, Any]],
    resolved_by_source_target: dict[tuple[Any, Any, Any, Any], list[dict[str, Any]]],
    transition_by_decision: dict[tuple[Any, Any, Any], dict[str, Any]] | None,
) -> dict[str, Any]:
    resolved_rows = sorted(
        resolved_by_source_target.get(attribution_source_target_key(row), []),
        key=lambda item: (as_int(item.get("event_id")), as_int(item.get("decision_id"))),
    )
    resolved_results = sorted({str(item.get("defense_result")) for item in resolved_rows})
    if not resolved_rows:
        status = "unresolved_no_same_source_target_result"
        final_result = "unresolved"
    elif len(resolved_results) == 1:
        status = "resolved_same_source_target"
        final_result = resolved_results[0]
    else:
        status = "ambiguous_same_source_target"
        final_result = "/".join(resolved_results)

    unknown_transition = None
    resolved_transitions: list[dict[str, Any]] = []
    if transition_by_decision is not None:
        unknown_transition = transition_by_decision.get(transition_lookup_key(row))
        resolved_transitions = [
            transition
            for transition in (
                transition_by_decision.get(transition_lookup_key(item))
                for item in resolved_rows[:8]
            )
            if transition is not None
        ]
        if unknown_transition is None:
            transition_join_status = "unknown_event_missing_transition"
        elif not resolved_rows:
            transition_join_status = "unknown_joined_no_resolved_event"
        elif len(resolved_transitions) == len(resolved_rows[:8]):
            transition_join_status = "unknown_and_resolved_events_joined"
        else:
            transition_join_status = "unknown_joined_resolved_partial_transition"
    else:
        transition_join_status = "transition_log_absent"

    source = events_by_id.get(source_lookup_key(row), {})
    return {
        "run_id": row.get("run_id"),
        "event_id": row.get("event_id"),
        "episode_id": row.get("episode_id"),
        "source_event_id": row.get("source_event_id"),
        "source_side": row.get("source_side"),
        "target_side": row.get("target_side"),
        "unknown_bucket": attribution_unknown_bucket(row, events_by_id),
        "reconciliation_status": status,
        "final_result": final_result,
        "edge_type": row.get("edge_type"),
        "target_state": row.get("target_state"),
        "source_kind": source.get("event_kind"),
        "source_result": source.get("result"),
        "source_finalize_reason": source.get("finalize_reason"),
        "transition_join_status": transition_join_status,
        "transition_decision_id": unknown_transition.get("decision_id") if unknown_transition else None,
        "transition_obs_frame": unknown_transition.get("obs_frame") if unknown_transition else None,
        "resolved_event_ids": [item.get("event_id") for item in resolved_rows[:8]],
        "resolved_results": [item.get("defense_result") for item in resolved_rows[:8]],
        "resolved_edge_types": [item.get("edge_type") for item in resolved_rows[:8]],
        "resolved_transition_decision_ids": [item.get("decision_id") for item in resolved_transitions],
        "resolved_transition_obs_frames": [item.get("obs_frame") for item in resolved_transitions],
    }


def summarize_reconciliation_side_records(
    records: list[dict[str, Any]],
    side_field: str,
) -> dict[str, dict[str, Any]]:
    summary: dict[str, dict[str, Any]] = {}
    sides = sorted({str(record.get(side_field, "unknown")) for record in records}, key=side_sort_key)
    for side in sides:
        side_records = [record for record in records if str(record.get(side_field, "unknown")) == side]
        summary[side] = {
            "rows": len(side_records),
            "status_counts": dict(collections.Counter(str(record.get("reconciliation_status")) for record in side_records)),
            "transition_join_counts": dict(
                collections.Counter(str(record.get("transition_join_status")) for record in side_records)
            ),
            "final_result_counts": dict(collections.Counter(str(record.get("final_result")) for record in side_records)),
            "unknown_bucket_counts": dict(collections.Counter(str(record.get("unknown_bucket")) for record in side_records)),
        }
    return summary


def effective_attribution_record(
    row: dict[str, Any],
    reconciliation_by_event: dict[tuple[Any, Any], dict[str, Any]],
) -> dict[str, Any]:
    raw_result = str(row.get("defense_result", "unknown"))
    reconciliation = reconciliation_by_event.get(event_lookup_key(row), {})
    reconciliation_status = str(reconciliation.get("reconciliation_status", "raw_non_unknown"))
    if raw_result != "unknown":
        effective_result = raw_result
        effective_source = "raw_non_unknown"
    elif reconciliation_status == "resolved_same_source_target":
        effective_result = str(reconciliation.get("final_result", "unknown"))
        effective_source = "derived_from_unknown"
    elif reconciliation_status == "ambiguous_same_source_target":
        effective_result = "ambiguous"
        effective_source = "ambiguous_unknown"
    else:
        effective_result = "unknown"
        effective_source = "unresolved_unknown"

    return {
        "run_id": row.get("run_id"),
        "event_id": row.get("event_id"),
        "episode_id": row.get("episode_id"),
        "source_event_id": row.get("source_event_id"),
        "source_side": row.get("source_side"),
        "target_side": row.get("target_side"),
        "source_family": row.get("source_family"),
        "edge_type": row.get("edge_type"),
        "confidence": row.get("confidence"),
        "raw_defense_result": raw_result,
        "effective_defense_result": effective_result,
        "effective_source": effective_source,
        "reconciliation_status": reconciliation_status,
    }


def summarize_effective_attribution_side_records(
    records: list[dict[str, Any]],
    side_field: str,
) -> dict[str, dict[str, Any]]:
    summary: dict[str, dict[str, Any]] = {}
    sides = sorted({str(record.get(side_field, "unknown")) for record in records}, key=side_sort_key)
    for side in sides:
        side_records = [record for record in records if str(record.get(side_field, "unknown")) == side]
        summary[side] = {
            "rows": len(side_records),
            "effective_defense_result_counts": dict(
                collections.Counter(str(record.get("effective_defense_result")) for record in side_records)
            ),
            "effective_source_counts": dict(
                collections.Counter(str(record.get("effective_source")) for record in side_records)
            ),
            "raw_defense_result_counts": dict(
                collections.Counter(str(record.get("raw_defense_result")) for record in side_records)
            ),
        }
    return summary


def new_move_stat() -> dict[str, int]:
    return {
        "uses": 0,
        "hit": 0,
        "blocked": 0,
        "whiff": 0,
        "parry": 0,
        "clash": 0,
        "interrupted": 0,
        "unknown": 0,
    }


def move_outcome_from_attack(
    row: dict[str, Any],
    effective_by_source: dict[tuple[Any, Any], list[dict[str, Any]]],
) -> dict[str, bool]:
    effective_results = {
        str(record.get("effective_defense_result"))
        for record in effective_by_source.get(event_lookup_key(row), [])
    }
    result = str(row.get("result", "unknown"))
    return {
        "hit": bool(effective_results & {"hit", "thrown"}),
        "blocked": bool(effective_results & {"blocked", "blocked_chip"}),
        "whiff": result == "whiff" and not bool(effective_results & {"hit", "blocked", "blocked_chip", "thrown"}),
        "parry": "parry" in effective_results,
        "clash": "evaded" in effective_results,
        "interrupted": result == "interrupted",
        "unknown": result == "unknown" and not bool(effective_results - {"unknown"}),
    }


def move_outcome_from_projectile(row: dict[str, Any]) -> dict[str, bool]:
    result = str(row.get("result", "unknown"))
    saw_opposing_projectile = as_int(row.get("saw_opposing_projectile")) > 0
    return {
        "hit": result == "hit",
        "blocked": result == "blocked",
        "whiff": result == "expired" and not saw_opposing_projectile,
        "parry": False,
        "clash": result == "expired" and saw_opposing_projectile,
        "interrupted": False,
        "unknown": result == "unknown",
    }


def move_outcome_from_throw(row: dict[str, Any]) -> dict[str, bool]:
    result = str(row.get("result", "unknown"))
    reason = str(row.get("finalize_reason", "unknown"))
    return {
        "hit": result == "success",
        "blocked": False,
        "whiff": result == "whiff",
        "parry": False,
        "clash": reason == "tech_escape",
        "interrupted": False,
        "unknown": result == "unknown" and reason != "tech_escape",
    }


def source_move_record(
    row: dict[str, Any],
    event_kind: str,
    effective_by_source: dict[tuple[Any, Any], list[dict[str, Any]]],
) -> dict[str, Any]:
    side = str(row.get("side") if event_kind == "attack" else row.get("owner_side", "unknown"))
    action_id, sub_action_id = source_action_meta(row, event_kind)
    if event_kind == "attack":
        outcome = move_outcome_from_attack(row, effective_by_source)
    elif event_kind == "projectile":
        outcome = move_outcome_from_projectile(row)
    else:
        outcome = move_outcome_from_throw(row)
    return {
        "event_id": row.get("event_id"),
        "episode_id": row.get("episode_id"),
        "event_kind": event_kind,
        "side": side,
        "target_side": opposite_side(side),
        "move_name": action_name(action_id, sub_action_id, event_kind),
        "action_id": action_id,
        "sub_action_id": sub_action_id,
        "tags": action_tags(action_id, sub_action_id, event_kind),
        "outcome": outcome,
    }


def add_move_stat(stats: dict[str, int], outcome: dict[str, bool]) -> None:
    stats["uses"] += 1
    for key in ("hit", "blocked", "whiff", "parry", "clash", "interrupted", "unknown"):
        if outcome.get(key):
            stats[key] += 1


def finalize_move_stat(stats: dict[str, int]) -> dict[str, Any]:
    uses = stats["uses"]
    finalized: dict[str, Any] = dict(stats)
    for key in ("hit", "blocked", "whiff", "parry", "clash", "interrupted", "unknown"):
        finalized[f"{key}_rate"] = round(stats[key] / uses, 4) if uses else 0.0
    return finalized


def summarize_move_records_for_side(records: list[dict[str, Any]]) -> dict[str, Any]:
    by_move: dict[str, dict[str, int]] = collections.defaultdict(new_move_stat)
    by_tag: dict[str, dict[str, int]] = collections.defaultdict(new_move_stat)
    for record in records:
        outcome = record["outcome"]
        add_move_stat(by_move[str(record["move_name"])], outcome)
        for tag in record["tags"]:
            add_move_stat(by_tag[str(tag)], outcome)

    return {
        "rows": len(records),
        "by_move": {
            key: finalize_move_stat(value)
            for key, value in sorted(by_move.items())
        },
        "by_tag": {
            key: finalize_move_stat(value)
            for key, value in sorted(by_tag.items())
        },
    }


def summarize_move_records(records: list[dict[str, Any]], side_field: str) -> dict[str, dict[str, Any]]:
    summary: dict[str, dict[str, Any]] = {}
    sides = sorted({str(record.get(side_field, "unknown")) for record in records}, key=side_sort_key)
    for side in sides:
        side_records = [record for record in records if str(record.get(side_field, "unknown")) == side]
        summary[side] = summarize_move_records_for_side(side_records)
    return summary


def sorted_stat_items(stats: dict[str, dict[str, Any]]) -> list[tuple[str, dict[str, Any]]]:
    return sorted(stats.items(), key=lambda item: (-as_int(item[1].get("uses")), item[0]))


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
    events_by_id = {event_lookup_key(row): row for row in event_rows}
    transition_by_decision: dict[tuple[Any, Any, Any], dict[str, Any]] | None = None
    if transition_rows:
        transition_by_decision = {
            transition_lookup_key(row): row
            for row in transition_rows
            if row.get("decision_id") is not None
        }

    attacks = by_kind.get("attack", [])
    projectile_rows = by_kind.get("projectile", [])
    projectiles_by_parent: dict[tuple[Any, Any, Any], list[dict[str, Any]]] = collections.defaultdict(list)
    for row in projectile_rows:
        parent_attack_event_id = row.get("parent_attack_event_id")
        if parent_attack_event_id in (None, 0):
            continue
        key = (row.get("run_id"), row.get("episode_id"), parent_attack_event_id)
        projectiles_by_parent[key].append(row)

    raw_attack_bucket_counts: collections.Counter[str] = collections.Counter(attack_bucket(row) for row in attacks)
    attack_bucket_counts: collections.Counter[str] = collections.Counter(
        resolved_attack_bucket(row, projectiles_by_parent) for row in attacks
    )
    true_attack_unknown_rows = [row for row in attacks if is_true_attack_unknown_bucket(attack_bucket(row))]
    delegated_attacks = [row for row in attacks if attack_bucket(row) == "delegated_to_projectile"]
    delegated_projectile_links: list[tuple[dict[str, Any], dict[str, Any]]] = []
    delegated_missing: list[dict[str, Any]] = []
    delegated_multi: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []
    for row in delegated_attacks:
        key = (row.get("run_id"), row.get("episode_id"), row.get("event_id"))
        linked_projectiles = projectiles_by_parent.get(key, [])
        if not linked_projectiles:
            delegated_missing.append(row)
        elif len(linked_projectiles) > 1:
            delegated_multi.append((row, linked_projectiles))
            delegated_projectile_links.extend((row, projectile) for projectile in linked_projectiles)
        else:
            delegated_projectile_links.append((row, linked_projectiles[0]))

    delegated_projectiles = [projectile for _, projectile in delegated_projectile_links]
    delegated_expired = [
        projectile for projectile in delegated_projectiles if str(projectile.get("result")) == "expired"
    ]
    delegated_unknown = [
        (attack, projectile)
        for attack, projectile in delegated_projectile_links
        if str(projectile.get("result")) == "unknown"
    ]
    delegated_by_owner: dict[str, dict[str, Any]] = {}
    delegated_owners = sorted(
        {str(projectile.get("owner_side")) for projectile in delegated_projectiles},
        key=side_sort_key,
    )
    for owner in delegated_owners:
        owner_links = [
            (attack, projectile)
            for attack, projectile in delegated_projectile_links
            if str(projectile.get("owner_side")) == owner
        ]
        owner_projectiles = [projectile for _, projectile in owner_links]
        owner_expired = [
            projectile for projectile in owner_projectiles if str(projectile.get("result")) == "expired"
        ]
        delegated_by_owner[owner] = {
            "linked_projectiles": len(owner_links),
            "result_counts": dict(collections.Counter(str(row.get("result")) for row in owner_projectiles)),
            "finalize_reason_counts": dict(
                collections.Counter(str(row.get("finalize_reason")) for row in owner_projectiles)
            ),
            "expired_saw_opposing_projectile": sum(
                int(row.get("saw_opposing_projectile") or 0) for row in owner_expired
            ),
            "expired_no_opposing_projectile": sum(
                1 for row in owner_expired if not int(row.get("saw_opposing_projectile") or 0)
            ),
        }

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
    throw_rows = by_kind.get("throw", [])
    attribution_rows = by_kind.get("attribution", [])
    attribution_unknown_rows = [
        row for row in attribution_rows if str(row.get("defense_result")) == "unknown"
    ]
    resolved_attributions_by_source_target: dict[tuple[Any, Any, Any, Any], list[dict[str, Any]]] = collections.defaultdict(list)
    for row in attribution_rows:
        if str(row.get("defense_result")) == "unknown":
            continue
        resolved_attributions_by_source_target[attribution_source_target_key(row)].append(row)
    attribution_unknown_reconciliation_records = [
        attribution_unknown_reconciliation_record(
            row,
            events_by_id,
            resolved_attributions_by_source_target,
            transition_by_decision,
        )
        for row in attribution_unknown_rows
    ]
    attribution_reconciliation_by_event = {
        event_lookup_key(row): row
        for row in attribution_unknown_reconciliation_records
    }
    effective_attribution_records = [
        effective_attribution_record(row, attribution_reconciliation_by_event)
        for row in attribution_rows
    ]
    effective_attributions_by_source: dict[tuple[Any, Any], list[dict[str, Any]]] = collections.defaultdict(list)
    for record in effective_attribution_records:
        effective_attributions_by_source[(record.get("run_id"), record.get("source_event_id"))].append(record)
    source_move_records: list[dict[str, Any]] = []
    for row in attacks:
        action_id, _ = source_action_meta(row, "attack")
        if str(row.get("finalize_reason")) == "projectile_claimed":
            continue
        if action_id == RL_POLICY_ACTION_THROW:
            continue
        source_move_records.append(source_move_record(row, "attack", effective_attributions_by_source))
    source_move_records.extend(
        source_move_record(row, "projectile", effective_attributions_by_source)
        for row in projectile_rows
    )
    source_move_records.extend(
        source_move_record(row, "throw", effective_attributions_by_source)
        for row in throw_rows
    )
    attribution_unknown_examples: list[dict[str, Any]] = []
    for row in attribution_unknown_rows[:12]:
        source = events_by_id.get(source_lookup_key(row), {})
        attribution_unknown_examples.append(
            {
                "event_id": row.get("event_id"),
                "episode_id": row.get("episode_id"),
                "source_side": row.get("source_side"),
                "target_side": row.get("target_side"),
                "bucket": attribution_unknown_bucket(row, events_by_id),
                "edge_type": row.get("edge_type"),
                "source_event_id": row.get("source_event_id"),
                "source_kind": source.get("event_kind"),
                "source_result": source.get("result"),
                "source_finalize_reason": source.get("finalize_reason"),
                "target_state": row.get("target_state"),
                "actual_guard_state": row.get("actual_guard_state"),
                "target_attack_state_active": row.get("target_attack_state_active"),
                "target_airborne": row.get("target_airborne"),
            }
        )
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
            episode_projectile_rows = [
                row for row in by_kind.get("projectile", []) if row_episode(row) == episode
            ]
            event_result_counts = collections.Counter(str(row.get("result")) for row in episode_projectile_rows)
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
                "event_rows": len(episode_projectile_rows),
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
            "raw_lifecycle_bucket_counts": dict(raw_attack_bucket_counts),
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
            "delegated_projectile": {
                "delegated_attacks": len(delegated_attacks),
                "linked_projectiles": len(delegated_projectile_links),
                "missing_projectile_links": len(delegated_missing),
                "multi_projectile_links": len(delegated_multi),
                "result_counts": dict(collections.Counter(str(row.get("result")) for row in delegated_projectiles)),
                "finalize_reason_counts": dict(
                    collections.Counter(str(row.get("finalize_reason")) for row in delegated_projectiles)
                ),
                "owner_counts": dict(collections.Counter(str(row.get("owner_side")) for row in delegated_projectiles)),
                "expired_saw_opposing_projectile": sum(
                    int(row.get("saw_opposing_projectile") or 0) for row in delegated_expired
                ),
                "expired_no_opposing_projectile": sum(
                    1 for row in delegated_expired if not int(row.get("saw_opposing_projectile") or 0)
                ),
                "by_owner": delegated_by_owner,
                "unknown_examples": [
                    {
                        "attack_event_id": attack.get("event_id"),
                        "projectile_event_id": projectile.get("event_id"),
                        "episode_id": attack.get("episode_id"),
                        "side": attack.get("side"),
                        "projectile_result": projectile.get("result"),
                        "projectile_finalize_reason": projectile.get("finalize_reason"),
                        "attack_start_decision_id": attack.get("start_decision_id"),
                        "projectile_start_decision_id": projectile.get("start_decision_id"),
                        "projectile_end_decision_id": projectile.get("end_decision_id"),
                    }
                    for attack, projectile in delegated_unknown[:12]
                ],
                "missing_examples": [
                    {
                        "attack_event_id": row.get("event_id"),
                        "episode_id": row.get("episode_id"),
                        "side": row.get("side"),
                        "start_decision_id": row.get("start_decision_id"),
                        "end_decision_id": row.get("end_decision_id"),
                    }
                    for row in delegated_missing[:12]
                ],
            },
        },
        "projectile": {
            "rows": len(projectile_rows),
            "owner_counts": dict(collections.Counter(str(row.get("owner_side")) for row in projectile_rows)),
            "result_counts": dict(collections.Counter(str(row.get("result")) for row in projectile_rows)),
            "finalize_reason_counts": dict(
                collections.Counter(str(row.get("finalize_reason")) for row in projectile_rows)
            ),
        },
        "throw": {
            "rows": len(throw_rows),
            "result_counts": dict(collections.Counter(str(row.get("result")) for row in throw_rows)),
            "finalize_reason_counts": dict(
                collections.Counter(str(row.get("finalize_reason")) for row in throw_rows)
            ),
            "by_owner_side": summarize_side_rows(throw_rows, "owner_side", ["result", "finalize_reason"]),
        },
        "attribution": {
            "rows": len(attribution_rows),
            "source_family_counts": dict(collections.Counter(str(row.get("source_family")) for row in attribution_rows)),
            "edge_type_counts": dict(collections.Counter(str(row.get("edge_type")) for row in attribution_rows)),
            "confidence_counts": dict(collections.Counter(str(row.get("confidence")) for row in attribution_rows)),
            "failure_reason_counts": dict(collections.Counter(str(row.get("failure_reason")) for row in attribution_rows)),
            "defense_result_counts": dict(collections.Counter(str(row.get("defense_result")) for row in attribution_rows)),
            "defense_unknown": {
                "rows": len(attribution_unknown_rows),
                "bucket_counts": dict(
                    collections.Counter(attribution_unknown_bucket(row, events_by_id) for row in attribution_unknown_rows)
                ),
                "edge_type_counts": dict(collections.Counter(str(row.get("edge_type")) for row in attribution_unknown_rows)),
                "target_state_counts": dict(collections.Counter(str(row.get("target_state")) for row in attribution_unknown_rows)),
                "source_family_counts": dict(collections.Counter(str(row.get("source_family")) for row in attribution_unknown_rows)),
                "by_source_side": summarize_attribution_unknown_side_rows(
                    attribution_unknown_rows, "source_side", events_by_id
                ),
                "by_target_side": summarize_attribution_unknown_side_rows(
                    attribution_unknown_rows, "target_side", events_by_id
                ),
                "examples": attribution_unknown_examples,
                "reconciliation": {
                    "rows": len(attribution_unknown_reconciliation_records),
                    "status_counts": dict(
                        collections.Counter(
                            str(record.get("reconciliation_status"))
                            for record in attribution_unknown_reconciliation_records
                        )
                    ),
                    "transition_join_counts": dict(
                        collections.Counter(
                            str(record.get("transition_join_status"))
                            for record in attribution_unknown_reconciliation_records
                        )
                    ),
                    "final_result_counts": dict(
                        collections.Counter(
                            str(record.get("final_result"))
                            for record in attribution_unknown_reconciliation_records
                            if str(record.get("reconciliation_status")) != "unresolved_no_same_source_target_result"
                        )
                    ),
                    "by_source_side": summarize_reconciliation_side_records(
                        attribution_unknown_reconciliation_records, "source_side"
                    ),
                    "by_target_side": summarize_reconciliation_side_records(
                        attribution_unknown_reconciliation_records, "target_side"
                    ),
                    "examples": attribution_unknown_reconciliation_records[:12],
                },
            },
            "by_source_side": summarize_side_rows(
                attribution_rows,
                "source_side",
                ["source_family", "edge_type", "confidence", "failure_reason", "defense_result"],
            ),
            "by_target_side": summarize_side_rows(
                attribution_rows,
                "target_side",
                ["source_family", "edge_type", "confidence", "failure_reason", "defense_result"],
            ),
            "derived": {
                "rows": len(effective_attribution_records),
                "effective_defense_result_counts": dict(
                    collections.Counter(
                        str(record.get("effective_defense_result"))
                        for record in effective_attribution_records
                    )
                ),
                "effective_source_counts": dict(
                    collections.Counter(
                        str(record.get("effective_source"))
                        for record in effective_attribution_records
                    )
                ),
                "raw_defense_result_counts": dict(
                    collections.Counter(
                        str(record.get("raw_defense_result"))
                        for record in effective_attribution_records
                    )
                ),
                "derived_from_unknown_counts": dict(
                    collections.Counter(
                        str(record.get("effective_defense_result"))
                        for record in effective_attribution_records
                        if str(record.get("effective_source")) == "derived_from_unknown"
                    )
                ),
                "unresolved_unknown_rows": sum(
                    1
                    for record in effective_attribution_records
                    if str(record.get("effective_source")) == "unresolved_unknown"
                ),
                "ambiguous_unknown_rows": sum(
                    1
                    for record in effective_attribution_records
                    if str(record.get("effective_source")) == "ambiguous_unknown"
                ),
                "by_source_side": summarize_effective_attribution_side_records(
                    effective_attribution_records, "source_side"
                ),
                "by_target_side": summarize_effective_attribution_side_records(
                    effective_attribution_records, "target_side"
                ),
            },
        },
        "punish": {
            "rows": len(punish_rows),
            "source_family_counts": dict(collections.Counter(str(row.get("source_family")) for row in punish_rows)),
            "reason_counts": dict(collections.Counter(str(row.get("reason")) for row in punish_rows)),
            "path_counts": dict(collections.Counter(str(row.get("path")) for row in punish_rows)),
            "by_punisher_side": summarize_side_rows(
                punish_rows,
                "punisher_side",
                ["source_family", "reason", "path"],
            ),
            "by_punished_side": summarize_side_rows(
                punish_rows,
                "punished_side",
                ["source_family", "reason", "path"],
            ),
        },
        "refs": {
            "source_refs": len(source_ref_rows),
            "missing_source_refs": len(missing_source_refs),
            "punish_refs": len(punish_rows),
            "missing_punished_attack_refs": len(missing_punished_refs),
        },
        "move_stats": {
            "rows": len(source_move_records),
            "offense_by_side": summarize_move_records(source_move_records, "side"),
            "defense_by_side": summarize_move_records(source_move_records, "target_side"),
        },
        "transition": transition_summary,
    }


def print_side_summary(title: str, summary: dict[str, dict[str, Any]]) -> None:
    if not summary:
        return
    print(f"  {title}")
    for side, section in sorted(summary.items(), key=lambda item: side_sort_key(item[0])):
        print(f"    {side}: rows={section['rows']}")
        for key, value in section.items():
            if key == "rows":
                continue
            print(f"      {key}={format_counter(collections.Counter(value))}")


def print_attribution_unknown_summary(summary: dict[str, Any], examples: int) -> None:
    if not summary or summary["rows"] == 0:
        return
    print("  defense_unknown")
    print(f"    rows={summary['rows']}")
    print(f"    bucket_counts={format_counter(collections.Counter(summary['bucket_counts']))}")
    print(f"    edge_type_counts={format_counter(collections.Counter(summary['edge_type_counts']))}")
    print(f"    target_state_counts={format_counter(collections.Counter(summary['target_state_counts']))}")
    print(f"    source_family_counts={format_counter(collections.Counter(summary['source_family_counts']))}")
    print_side_summary("defense_unknown_by_source_side", summary["by_source_side"])
    print_side_summary("defense_unknown_by_target_side", summary["by_target_side"])
    reconciliation = summary["reconciliation"]
    print("  defense_unknown_reconciliation")
    print(f"    rows={reconciliation['rows']}")
    print(f"    status_counts={format_counter(collections.Counter(reconciliation['status_counts']))}")
    print(f"    transition_join_counts={format_counter(collections.Counter(reconciliation['transition_join_counts']))}")
    print(f"    final_result_counts={format_counter(collections.Counter(reconciliation['final_result_counts']))}")
    print_side_summary("reconciliation_by_source_side", reconciliation["by_source_side"])
    print_side_summary("reconciliation_by_target_side", reconciliation["by_target_side"])
    for row in reconciliation["examples"][:examples]:
        print(
            "    reconciliation_example "
            f"event_id={row['event_id']} ep={row['episode_id']} "
            f"source={row['source_side']} target={row['target_side']} "
            f"status={row['reconciliation_status']} final={row['final_result']} "
            f"unknown_bucket={row['unknown_bucket']} source_event_id={row['source_event_id']} "
            f"transition={row['transition_join_status']} "
            f"unknown_decision={row['transition_decision_id']} unknown_obs={row['transition_obs_frame']} "
            f"resolved_event_ids={row['resolved_event_ids']} "
            f"resolved_results={row['resolved_results']} "
            f"resolved_edges={row['resolved_edge_types']} "
            f"resolved_decisions={row['resolved_transition_decision_ids']}"
        )
    for row in summary["examples"][:examples]:
        print(
            "    defense_unknown_example "
            f"event_id={row['event_id']} ep={row['episode_id']} "
            f"source={row['source_side']} target={row['target_side']} bucket={row['bucket']} "
            f"edge={row['edge_type']} source_event_id={row['source_event_id']} "
            f"source_kind={row['source_kind']} source_result={row['source_result']} "
            f"source_reason={row['source_finalize_reason']} target_state={row['target_state']} "
            f"guard={row['actual_guard_state']} target_attack={row['target_attack_state_active']} "
            f"target_air={row['target_airborne']}"
        )


def print_derived_attribution_summary(summary: dict[str, Any]) -> None:
    if not summary or summary["rows"] == 0:
        return
    print("  derived")
    print(f"    rows={summary['rows']}")
    print(
        "    effective_defense_result_counts="
        f"{format_counter(collections.Counter(summary['effective_defense_result_counts']))}"
    )
    print(
        "    effective_source_counts="
        f"{format_counter(collections.Counter(summary['effective_source_counts']))}"
    )
    print(
        "    derived_from_unknown_counts="
        f"{format_counter(collections.Counter(summary['derived_from_unknown_counts']))}"
    )
    print(
        f"    unresolved_unknown_rows={summary['unresolved_unknown_rows']} "
        f"ambiguous_unknown_rows={summary['ambiguous_unknown_rows']}"
    )
    print_side_summary("derived_by_source_side", summary["by_source_side"])
    print_side_summary("derived_by_target_side", summary["by_target_side"])


def print_single_move_stat(name: str, stats: dict[str, Any]) -> None:
    print(
        f"      {name}: uses={stats['uses']} "
        f"hit={stats['hit']}({stats['hit_rate']:.2%}) "
        f"blocked={stats['blocked']}({stats['blocked_rate']:.2%}) "
        f"whiff={stats['whiff']}({stats['whiff_rate']:.2%}) "
        f"parry={stats['parry']} clash={stats['clash']} "
        f"interrupted={stats['interrupted']} unknown={stats['unknown']}"
    )


def print_move_stats_group(title: str, summary: dict[str, dict[str, Any]], limit: int) -> None:
    if not summary:
        return
    print(title)
    for side, section in sorted(summary.items(), key=lambda item: side_sort_key(item[0])):
        print(f"  {side}: rows={section['rows']}")
        print("    by_tag")
        for name, stats in sorted_stat_items(section["by_tag"])[:limit]:
            print_single_move_stat(name, stats)
        print("    by_move")
        for name, stats in sorted_stat_items(section["by_move"])[:limit]:
            print_single_move_stat(name, stats)


def print_move_stats_summary(summary: dict[str, Any], examples: int) -> None:
    if not summary or summary["rows"] == 0:
        return
    limit = max(12, examples)
    print("Move Stats")
    print(f"  rows={summary['rows']}")
    print_move_stats_group("  offense_by_side", summary["offense_by_side"], limit)
    print_move_stats_group("  defense_by_side", summary["defense_by_side"], limit)
    print()


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
    print(f"  raw_lifecycle_bucket={format_counter(collections.Counter(attack['raw_lifecycle_bucket_counts']))}")
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

    delegated = attack["delegated_projectile"]
    print("Delegated Projectile Outcome")
    print(
        f"  delegated_attacks={delegated['delegated_attacks']} "
        f"linked_projectiles={delegated['linked_projectiles']} "
        f"missing_links={delegated['missing_projectile_links']} "
        f"multi_links={delegated['multi_projectile_links']}"
    )
    print(f"  result={format_counter(collections.Counter(delegated['result_counts']))}")
    print(f"  finalize_reason={format_counter(collections.Counter(delegated['finalize_reason_counts']))}")
    print(f"  owner={format_counter(collections.Counter(delegated['owner_counts']))}")
    print(
        f"  expired_saw_opposing_projectile={delegated['expired_saw_opposing_projectile']} "
        f"expired_no_opposing_projectile={delegated['expired_no_opposing_projectile']}"
    )
    if delegated["by_owner"]:
        print("  by_owner")
        for owner, section in sorted(delegated["by_owner"].items(), key=lambda item: side_sort_key(item[0])):
            print(
                f"    {owner}: linked_projectiles={section['linked_projectiles']} "
                f"result={format_counter(collections.Counter(section['result_counts']))}"
            )
            print(
                f"      finalize_reason={format_counter(collections.Counter(section['finalize_reason_counts']))} "
                f"expired_saw_opposing_projectile={section['expired_saw_opposing_projectile']} "
                f"expired_no_opposing_projectile={section['expired_no_opposing_projectile']}"
            )
    for row in delegated["unknown_examples"][:examples]:
        print(
            "    projectile_unknown_example "
            f"attack_event_id={row['attack_event_id']} projectile_event_id={row['projectile_event_id']} "
            f"ep={row['episode_id']} side={row['side']} "
            f"reason={row['projectile_finalize_reason']} "
            f"attack_start={row['attack_start_decision_id']} "
            f"projectile_start={row['projectile_start_decision_id']} "
            f"projectile_end={row['projectile_end_decision_id']}"
        )
    for row in delegated["missing_examples"][:examples]:
        print(
            "    missing_projectile_example "
            f"attack_event_id={row['attack_event_id']} ep={row['episode_id']} side={row['side']} "
            f"start={row['start_decision_id']} end={row['end_decision_id']}"
        )
    print()

    for section_name in ("projectile", "throw", "attribution", "punish"):
        section = summary[section_name]
        print(section_name.title())
        print(f"  rows={section['rows']}")
        for key, value in section.items():
            if key == "rows":
                continue
            if key.startswith("by_"):
                continue
            if key == "defense_unknown":
                continue
            if key == "derived":
                continue
            print(f"  {key}={format_counter(collections.Counter(value))}")
        if section_name == "throw":
            print_side_summary("by_owner_side", section["by_owner_side"])
        elif section_name == "attribution":
            print_attribution_unknown_summary(section["defense_unknown"], examples)
            print_side_summary("by_source_side", section["by_source_side"])
            print_side_summary("by_target_side", section["by_target_side"])
            print_derived_attribution_summary(section["derived"])
        elif section_name == "punish":
            print_side_summary("by_punisher_side", section["by_punisher_side"])
            print_side_summary("by_punished_side", section["by_punished_side"])
        print()

    print_move_stats_summary(summary["move_stats"], examples)

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
