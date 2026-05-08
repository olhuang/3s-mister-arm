#!/usr/bin/env python3
"""Label transition rows with Phase 12 tactical fighting-game state.

This is an offline diagnostic tool. It intentionally does not train a model or
change reward values. The first goal is to make high-level tactical labels
inspectable before they become a supervised intent target.
"""

from __future__ import annotations

import argparse
import collections
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import rl_probe_server as rl


TACTICAL_STATE_SCHEMA_VERSION = 1

THROW_RANGE_MAX_DX = 32
CLOSE_RANGE_MAX_DX = 64
POKE_RANGE_MAX_DX = 120
FIREBALL_RANGE_MAX_DX = 260
CORNER_EDGE_MAX_DIST = 48
INCOMING_PROJECTILE_MAX_TIME = 24
INCOMING_PROJECTILE_MAX_DX = 220
INCOMING_PROJECTILE_MAX_ABS_Y = 96
JUMP_IN_MAX_DX = 128
PUNISH_EVENT_WINDOW_DECISIONS = 6

LOW_ATTACKS = frozenset({"crouch-lk", "crouch-mk", "crouch-hk"})
FIREBALL_ACTIONS = frozenset(rl.FIREBALL_ACTION_NAMES)
SHORYUKEN_ACTIONS = frozenset(rl.SHORYUKEN_ACTION_NAMES)
TATSU_ACTIONS = frozenset(rl.TATSU_ACTION_NAMES)
NORMAL_ACTIONS = (
    frozenset(rl.STAND_NORMAL_ACTION_NAMES)
    | frozenset(rl.CROUCH_NORMAL_ACTION_NAMES)
    | frozenset(rl.AIR_NORMAL_ACTION_NAMES)
    | frozenset({"forward-hp"})
)


@dataclass(frozen=True)
class TacticalLabels:
    spacing_bucket: str
    corner_context: str
    self_phase: str
    opponent_phase: str
    threat_type: str
    opportunity_type: str
    recommended_intent: str
    intent_reason: str
    label_confidence: str

    def as_dict(self) -> dict[str, str | int]:
        return {
            "tactical_state_schema_version": TACTICAL_STATE_SCHEMA_VERSION,
            "spacing_bucket": self.spacing_bucket,
            "corner_context": self.corner_context,
            "self_phase": self.self_phase,
            "opponent_phase": self.opponent_phase,
            "threat_type": self.threat_type,
            "opportunity_type": self.opportunity_type,
            "recommended_intent": self.recommended_intent,
            "intent_reason": self.intent_reason,
            "label_confidence": self.label_confidence,
        }


@dataclass(frozen=True)
class EventWindow:
    run_id: int
    episode_id: int
    start_decision_id: int
    end_decision_id: int
    event_id: int
    side: str
    kind: str
    result: str
    reason: str
    action_name: str


@dataclass
class CombatEventContext:
    opponent_punish_windows: dict[tuple[int, int], list[EventWindow]] = field(default_factory=dict)
    self_punish_windows: dict[tuple[int, int], list[EventWindow]] = field(default_factory=dict)
    event_rows: int = 0
    parse_errors: list[str] = field(default_factory=list)


@dataclass
class LabelStats:
    rows: int = 0
    emitted_rows: int = 0
    transition_errors: list[str] = field(default_factory=list)
    spacing: collections.Counter[str] = field(default_factory=collections.Counter)
    corner: collections.Counter[str] = field(default_factory=collections.Counter)
    self_phase: collections.Counter[str] = field(default_factory=collections.Counter)
    opponent_phase: collections.Counter[str] = field(default_factory=collections.Counter)
    threat: collections.Counter[str] = field(default_factory=collections.Counter)
    opportunity: collections.Counter[str] = field(default_factory=collections.Counter)
    intent: collections.Counter[str] = field(default_factory=collections.Counter)
    reason: collections.Counter[str] = field(default_factory=collections.Counter)
    confidence: collections.Counter[str] = field(default_factory=collections.Counter)
    examples: dict[str, list[dict[str, Any]]] = field(default_factory=lambda: collections.defaultdict(list))


def read_ndjson(path: Path, limit: int = 0) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    with path.open("rb") as stream:
        for line_no, raw in enumerate(stream, 1):
            if limit > 0 and len(rows) >= limit:
                break
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


def as_int(row: dict[str, Any], field_name: str) -> int:
    return rl.row_int_field(row, field_name)


def event_action_name(row: dict[str, Any]) -> str:
    action_id = as_int(row, "engine_action_id") or as_int(row, "policy_action_id")
    sub_action_id = as_int(row, "engine_sub_action_id") or as_int(row, "policy_sub_action_id")
    name = rl.action_name_from_policy_meta(action_id, sub_action_id)
    return name or "unknown"


def load_combat_event_context(paths: Iterable[Path], limit: int = 0) -> CombatEventContext:
    context = CombatEventContext()
    for path in paths:
        rows, errors = read_ndjson(path, limit)
        context.parse_errors.extend(errors)
        for row in rows:
            context.event_rows += 1
            if row.get("event_kind") != "attack":
                continue
            side = str(row.get("side", "unknown"))
            result = str(row.get("result", "unknown"))
            reason = str(row.get("finalize_reason", "unknown"))
            if side not in {"self", "opponent"}:
                continue
            if result not in {"whiff", "interrupted"} and reason not in {
                "basic_whiff_window",
                "basic_interrupted",
                "superseded_by_new_start",
            }:
                continue
            run_id = as_int(row, "run_id")
            episode_id = as_int(row, "episode_id")
            end_decision_id = as_int(row, "end_decision_id")
            if run_id == 0 or episode_id == 0 or end_decision_id < 0:
                continue
            window = EventWindow(
                run_id=run_id,
                episode_id=episode_id,
                start_decision_id=end_decision_id,
                end_decision_id=end_decision_id + PUNISH_EVENT_WINDOW_DECISIONS,
                event_id=as_int(row, "event_id"),
                side=side,
                kind="attack",
                result=result,
                reason=reason,
                action_name=event_action_name(row),
            )
            key = (run_id, episode_id)
            if side == "opponent":
                context.opponent_punish_windows.setdefault(key, []).append(window)
            else:
                context.self_punish_windows.setdefault(key, []).append(window)
    for windows in context.opponent_punish_windows.values():
        windows.sort(key=lambda item: (item.start_decision_id, item.event_id))
    for windows in context.self_punish_windows.values():
        windows.sort(key=lambda item: (item.start_decision_id, item.event_id))
    return context


def spacing_bucket(row: dict[str, Any]) -> str:
    abs_dx = abs(as_int(row, "obs_abs_dx"))
    if abs_dx <= THROW_RANGE_MAX_DX:
        return "throw_range"
    if abs_dx <= CLOSE_RANGE_MAX_DX:
        return "close"
    if abs_dx <= POKE_RANGE_MAX_DX:
        return "poke"
    if abs_dx <= FIREBALL_RANGE_MAX_DX:
        return "fireball"
    return "too_far"


def corner_context(row: dict[str, Any]) -> str:
    self_cornered = min(
        as_int(row, "obs_self_front_edge_dist"),
        as_int(row, "obs_self_back_edge_dist"),
    ) <= CORNER_EDGE_MAX_DIST
    opponent_cornered = min(
        as_int(row, "obs_opp_front_edge_dist"),
        as_int(row, "obs_opp_back_edge_dist"),
    ) <= CORNER_EDGE_MAX_DIST
    if self_cornered and opponent_cornered:
        return "both_cornered"
    if self_cornered:
        return "self_cornered"
    if opponent_cornered:
        return "opponent_cornered"
    return "mid_screen"


def contact_phase(row: dict[str, Any], side: str) -> str:
    delta_hp_field = "delta_self_hp" if side == "self" else "delta_opp_hp"
    return "hitstun" if as_int(row, delta_hp_field) > 0 else "blockstun"


def self_phase(row: dict[str, Any]) -> str:
    if as_int(row, "done") != 0:
        return "knockdown_or_round_boundary"
    if as_int(row, "obs_self_contact_reaction_state") != 0:
        return contact_phase(row, "self")
    if as_int(row, "obs_self_airborne") != 0 or as_int(row, "obs_self_jump_phase") != 0:
        return "airborne"
    if as_int(row, "obs_self_routine_attack_state") != 0 or as_int(row, "obs_self_routine_1") == 4:
        if as_int(row, "self_engine_current_attack") != 0 or as_int(row, "engine_current_attack") != 0:
            return "active"
        if as_int(row, "self_engine_lag_frames") > 0 or as_int(row, "engine_lag_frames") > 0:
            return "recovery"
        return "startup"
    if as_int(row, "obs_self_ground_action_start_allowed") != 0:
        return "actionable"
    return "unknown"


def opponent_action_name(row: dict[str, Any]) -> str:
    action_id = as_int(row, "opp_engine_action_id")
    sub_action_id = as_int(row, "opp_engine_sub_action_id")
    name = rl.action_name_from_policy_meta(action_id, sub_action_id)
    return name or "unknown"


def opponent_phase(row: dict[str, Any]) -> str:
    if as_int(row, "done") != 0:
        return "knockdown_or_round_boundary"
    if as_int(row, "obs_opp_contact_reaction_state") != 0:
        return contact_phase(row, "opponent")
    if (
        as_int(row, "obs_projectile_active") != 0
        and as_int(row, "obs_projectile_owner") == 2
        and as_int(row, "obs_opp_routine_attack_state") == 0
    ):
        return "projectile_active"
    if as_int(row, "obs_opp_airborne") != 0 or as_int(row, "obs_opp_jump_phase") != 0:
        return "jumping"
    if as_int(row, "obs_opp_routine_attack_state") != 0 or as_int(row, "obs_opp_routine_1") == 4:
        action = opponent_action_name(row)
        if action in FIREBALL_ACTIONS:
            return "fireball_startup"
        if as_int(row, "opp_engine_current_attack") != 0:
            return "active"
        if as_int(row, "opp_engine_lag_frames") > 0:
            return "recovery"
        return "startup"
    return "neutral"


def incoming_projectile_threat(row: dict[str, Any]) -> bool:
    if as_int(row, "obs_projectile_active") == 0 or as_int(row, "obs_projectile_owner") != 2:
        return False
    rel_x = as_int(row, "obs_projectile_rel_x")
    rel_y = as_int(row, "obs_projectile_rel_y")
    vel_x = as_int(row, "obs_projectile_vel_x")
    time_to_self = as_int(row, "obs_projectile_time_to_self")
    return (
        1 <= time_to_self <= INCOMING_PROJECTILE_MAX_TIME
        and 0 < rel_x <= INCOMING_PROJECTILE_MAX_DX
        and abs(rel_y) <= INCOMING_PROJECTILE_MAX_ABS_Y
        and vel_x < 0
    )


def threat_type(row: dict[str, Any], spacing: str, self_phase_value: str, opponent_phase_value: str) -> str:
    abs_dx = abs(as_int(row, "obs_abs_dx"))
    if self_phase_value in {"hitstun", "blockstun"} and as_int(row, "obs_opp_routine_attack_state") != 0:
        return "multi_hit_pressure"
    if incoming_projectile_threat(row):
        return "incoming_projectile"
    action = opponent_action_name(row)
    if action in LOW_ATTACKS and as_int(row, "obs_opp_routine_attack_state") != 0 and abs_dx <= POKE_RANGE_MAX_DX:
        return "low_attack"
    if opponent_phase_value == "jumping" and abs_dx <= JUMP_IN_MAX_DX:
        return "jump_in"
    if as_int(row, "opp_throw_started") != 0 or (spacing == "throw_range" and as_int(row, "obs_opp_routine_attack_state") != 0):
        return "throw_range"
    if as_int(row, "obs_opp_routine_attack_state") != 0 and abs_dx <= POKE_RANGE_MAX_DX:
        return "close_attack"
    if corner_context(row) == "self_cornered" and abs_dx <= POKE_RANGE_MAX_DX:
        return "corner_pressure"
    return "none"


def event_punish_window(
    row: dict[str, Any],
    context: CombatEventContext,
    side: str,
) -> EventWindow | None:
    run_id = as_int(row, "run_id")
    episode_id = as_int(row, "episode_id")
    decision_id = as_int(row, "decision_id")
    windows_by_side = context.opponent_punish_windows if side == "opponent" else context.self_punish_windows
    for window in windows_by_side.get((run_id, episode_id), []):
        if window.start_decision_id <= decision_id <= window.end_decision_id:
            return window
    return None


def opportunity_type(
    row: dict[str, Any],
    spacing: str,
    self_phase_value: str,
    opponent_phase_value: str,
    threat: str,
    context: CombatEventContext,
) -> tuple[str, str]:
    if self_phase_value != "actionable":
        return "none", "self_not_actionable"
    if threat != "none":
        if threat == "jump_in":
            return "anti_air", "jump_in_threat"
        return "none", f"threat_{threat}"
    punish_window = event_punish_window(row, context, "opponent")
    if punish_window is not None and spacing in {"throw_range", "close", "poke", "fireball"}:
        if punish_window.result == "whiff":
            return "punish_whiff", f"event_whiff_{punish_window.action_name}"
        return "punish_recovery", f"event_interrupted_{punish_window.action_name}"
    if opponent_phase_value == "recovery" and spacing in {"throw_range", "close", "poke"}:
        return "punish_recovery", "opponent_recovery"
    if opponent_phase_value == "jumping" and spacing in {"close", "poke", "fireball"}:
        return "anti_air", "opponent_jumping"
    if opponent_phase_value in {"hitstun", "blockstun"} and spacing in {"throw_range", "close", "poke"}:
        return "pressure", f"opponent_{opponent_phase_value}"
    if spacing == "throw_range":
        return "throw_mixup", "throw_range_no_threat"
    if spacing == "poke":
        return "poke", "poke_range_no_threat"
    if spacing == "fireball":
        return "fireball_zoning", "fireball_range_no_threat"
    if spacing == "too_far":
        return "none", "too_far_no_threat"
    return "none", "neutral_no_clear_opportunity"


def recommended_intent(
    row: dict[str, Any],
    spacing: str,
    corner: str,
    self_phase_value: str,
    threat: str,
    opportunity: str,
    opportunity_reason: str,
) -> tuple[str, str, str]:
    if self_phase_value not in {"actionable", "airborne"}:
        return "hold_guard", "self_not_actionable", "medium"
    if threat == "low_attack":
        return "low_guard", "low_threat", "high"
    if threat == "incoming_projectile":
        return "hold_guard", "incoming_projectile", "high"
    if threat == "jump_in":
        return ("anti_air" if self_phase_value == "actionable" else "hold_guard"), "jump_in_threat", "high"
    if threat in {"close_attack", "multi_hit_pressure"}:
        return "hold_guard", threat, "high"
    if threat == "throw_range":
        return "escape", "throw_range_threat", "medium"
    if threat == "corner_pressure":
        return "escape", "corner_pressure", "medium"

    if opportunity in {"punish_whiff", "punish_recovery"}:
        return "punish", opportunity_reason, "high"
    if opportunity == "anti_air":
        return "anti_air", opportunity_reason, "high"
    if opportunity == "pressure":
        return "pressure", opportunity_reason, "medium"
    if opportunity == "throw_mixup":
        return "throw", opportunity_reason, "medium"
    if opportunity == "poke":
        return "poke", opportunity_reason, "medium"
    if opportunity == "fireball_zoning":
        return "fireball_zoning", opportunity_reason, "medium"

    if spacing == "too_far":
        return "approach", "too_far_no_threat", "medium"
    if spacing == "fireball":
        return "adjust_spacing", "fireball_range_no_clear_opportunity", "low"
    if corner == "self_cornered":
        return "escape", "self_cornered_no_clear_opportunity", "low"
    return "wait", "neutral_no_clear_opportunity", "low"


def label_row(row: dict[str, Any], context: CombatEventContext) -> TacticalLabels:
    spacing = spacing_bucket(row)
    corner = corner_context(row)
    self_phase_value = self_phase(row)
    opponent_phase_value = opponent_phase(row)
    threat = threat_type(row, spacing, self_phase_value, opponent_phase_value)
    opportunity, opportunity_reason = opportunity_type(
        row,
        spacing,
        self_phase_value,
        opponent_phase_value,
        threat,
        context,
    )
    intent, reason, confidence = recommended_intent(
        row,
        spacing,
        corner,
        self_phase_value,
        threat,
        opportunity,
        opportunity_reason,
    )
    return TacticalLabels(
        spacing_bucket=spacing,
        corner_context=corner,
        self_phase=self_phase_value,
        opponent_phase=opponent_phase_value,
        threat_type=threat,
        opportunity_type=opportunity,
        recommended_intent=intent,
        intent_reason=reason,
        label_confidence=confidence,
    )


def compact_row_example(row: dict[str, Any], labels: TacticalLabels) -> dict[str, Any]:
    selected = rl.action_selection_from_fields(
        row,
        "policy_executed_action_id",
        "policy_executed_sub_action_id",
        "policy_executed_action_step",
        "policy",
    )
    return {
        "run_id": as_int(row, "run_id"),
        "episode_id": as_int(row, "episode_id"),
        "decision_id": as_int(row, "decision_id"),
        "obs_frame": as_int(row, "obs_frame"),
        "abs_dx": abs(as_int(row, "obs_abs_dx")),
        "self_r1": as_int(row, "obs_self_routine_1"),
        "self_r2": as_int(row, "obs_self_routine_2"),
        "opp_r1": as_int(row, "obs_opp_routine_1"),
        "opp_r2": as_int(row, "obs_opp_routine_2"),
        "opp_action": opponent_action_name(row),
        "selected_action": selected.name or "none",
        "spacing": labels.spacing_bucket,
        "self_phase": labels.self_phase,
        "opponent_phase": labels.opponent_phase,
        "threat": labels.threat_type,
        "opportunity": labels.opportunity_type,
        "intent": labels.recommended_intent,
        "reason": labels.intent_reason,
    }


def update_stats(
    stats: LabelStats,
    row: dict[str, Any],
    labels: TacticalLabels,
    examples_per_bucket: int,
) -> None:
    stats.rows += 1
    stats.spacing[labels.spacing_bucket] += 1
    stats.corner[labels.corner_context] += 1
    stats.self_phase[labels.self_phase] += 1
    stats.opponent_phase[labels.opponent_phase] += 1
    stats.threat[labels.threat_type] += 1
    stats.opportunity[labels.opportunity_type] += 1
    stats.intent[labels.recommended_intent] += 1
    stats.reason[labels.intent_reason] += 1
    stats.confidence[labels.label_confidence] += 1

    for prefix, value in (
        ("spacing", labels.spacing_bucket),
        ("threat", labels.threat_type),
        ("opportunity", labels.opportunity_type),
        ("intent", labels.recommended_intent),
        ("reason", labels.intent_reason),
    ):
        key = f"{prefix}:{value}"
        if len(stats.examples[key]) < examples_per_bucket:
            stats.examples[key].append(compact_row_example(row, labels))


def counter_text(counter: collections.Counter[str], limit: int = 16) -> str:
    if not counter:
        return "(none)"
    total = sum(counter.values())
    parts: list[str] = []
    for key, value in counter.most_common(limit):
        pct = 100.0 * value / max(1, total)
        parts.append(f"{key}={value}/{pct:.1f}%")
    remaining = len(counter) - limit
    if remaining > 0:
        parts.append(f"...(+{remaining})")
    return ", ".join(parts)


def print_summary(stats: LabelStats, context: CombatEventContext, example_limit: int) -> None:
    print("Tactical State Label Summary")
    print(f"rows={stats.rows} emitted_rows={stats.emitted_rows} combat_event_rows={context.event_rows}")
    print(f"spacing={counter_text(stats.spacing)}")
    print(f"corner={counter_text(stats.corner)}")
    print(f"self_phase={counter_text(stats.self_phase)}")
    print(f"opponent_phase={counter_text(stats.opponent_phase)}")
    print(f"threat={counter_text(stats.threat)}")
    print(f"opportunity={counter_text(stats.opportunity)}")
    print(f"intent={counter_text(stats.intent)}")
    print(f"confidence={counter_text(stats.confidence)}")
    if stats.transition_errors or context.parse_errors:
        print(f"errors transition={len(stats.transition_errors)} combat={len(context.parse_errors)}")
        for error in (stats.transition_errors + context.parse_errors)[:8]:
            print(f"  {error}")
    print("Examples")
    interesting_keys = [
        "intent:approach",
        "intent:hold_guard",
        "intent:low_guard",
        "intent:anti_air",
        "intent:punish",
        "intent:fireball_zoning",
        "threat:incoming_projectile",
        "threat:close_attack",
        "threat:low_attack",
        "opportunity:punish_whiff",
        "opportunity:punish_recovery",
    ]
    for key in interesting_keys:
        examples = stats.examples.get(key, [])
        if not examples:
            continue
        print(f"  {key}")
        for example in examples[:example_limit]:
            print(f"    {json.dumps(example, sort_keys=True)}")


def write_summary_json(path: Path, stats: LabelStats, context: CombatEventContext) -> None:
    payload = {
        "tactical_state_schema_version": TACTICAL_STATE_SCHEMA_VERSION,
        "rows": stats.rows,
        "emitted_rows": stats.emitted_rows,
        "combat_event_rows": context.event_rows,
        "spacing": dict(sorted(stats.spacing.items())),
        "corner": dict(sorted(stats.corner.items())),
        "self_phase": dict(sorted(stats.self_phase.items())),
        "opponent_phase": dict(sorted(stats.opponent_phase.items())),
        "threat": dict(sorted(stats.threat.items())),
        "opportunity": dict(sorted(stats.opportunity.items())),
        "intent": dict(sorted(stats.intent.items())),
        "reason": dict(sorted(stats.reason.items())),
        "confidence": dict(sorted(stats.confidence.items())),
        "transition_errors": stats.transition_errors,
        "combat_event_errors": context.parse_errors,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        json.dump(payload, stream, sort_keys=True, indent=2)
        stream.write("\n")


def label_transitions(
    transition_paths: list[Path],
    context: CombatEventContext,
    output_path: Path | None,
    limit: int,
    examples_per_bucket: int,
) -> LabelStats:
    stats = LabelStats()
    output_stream = None
    try:
        if output_path is not None:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_stream = output_path.open("w", encoding="utf-8")
        for path in transition_paths:
            rows, errors = read_ndjson(path, max(0, limit - stats.rows) if limit > 0 else 0)
            stats.transition_errors.extend(errors)
            for row in rows:
                if limit > 0 and stats.rows >= limit:
                    break
                if not rl.is_current_transition_schema_row(row):
                    stats.transition_errors.append(
                        f"{path}: transition_schema_version={row.get('transition_schema_version')} unsupported"
                    )
                    continue
                labels = label_row(row, context)
                update_stats(stats, row, labels, examples_per_bucket)
                if output_stream is not None:
                    labeled = dict(row)
                    for key, value in labels.as_dict().items():
                        if key == "tactical_state_schema_version":
                            labeled[key] = value
                        else:
                            labeled[f"tactical_{key}"] = value
                    output_stream.write(json.dumps(labeled, sort_keys=True))
                    output_stream.write("\n")
                    stats.emitted_rows += 1
    finally:
        if output_stream is not None:
            output_stream.close()
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transitions", nargs="+", required=True, help="Transition NDJSON file(s)")
    parser.add_argument("--combat-events", nargs="*", default=(), help="Optional sibling combat-event NDJSON file(s)")
    parser.add_argument("--output", default=None, help="Optional labeled transition NDJSON output path")
    parser.add_argument("--summary-json", default=None, help="Optional machine-readable summary JSON path")
    parser.add_argument("--limit", type=int, default=0, help="Maximum transition rows to label; 0 means all rows")
    parser.add_argument("--examples", type=int, default=3, help="Examples to print per interesting bucket")
    args = parser.parse_args()

    transition_paths = [Path(path) for path in args.transitions]
    combat_event_paths = [Path(path) for path in args.combat_events]
    context = load_combat_event_context(combat_event_paths)
    stats = label_transitions(
        transition_paths,
        context,
        Path(args.output) if args.output else None,
        max(0, int(args.limit)),
        max(0, int(args.examples)),
    )
    print_summary(stats, context, max(0, int(args.examples)))
    if args.summary_json:
        write_summary_json(Path(args.summary_json), stats, context)


if __name__ == "__main__":
    main()
