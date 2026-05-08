#!/usr/bin/env python3
"""Dry-run delayed movement credit for paired combat event / transition logs."""

from __future__ import annotations

import argparse
import collections
from dataclasses import dataclass
from typing import Iterable

import rl_combat_event_training as combat_events
import train_dqn_learner as train


@dataclass
class DryRunExperience:
    action_name: str
    row: dict[str, object]
    combat_event_batch_group: str


@dataclass
class DryRunResult:
    scale: float
    stats: train.CombatEventMovementCreditStats
    reward_stats: combat_events.CombatEventRewardStats
    experiences: int
    action_start_rows: int
    selected_action_counts: collections.Counter[str]
    experience_group_counts: collections.Counter[str]
    cross_episode_candidate_rows: int
    cross_episode_applied_rows: int
    examples: list[dict[str, object]]


def parse_scales(text: str) -> list[float]:
    scales: list[float] = []
    for raw_item in text.split(","):
        item = raw_item.strip()
        if not item:
            continue
        try:
            value = float(item)
        except ValueError as exc:
            raise SystemExit(f"invalid --scales item {item!r}") from exc
        if value < 0.0:
            raise SystemExit("--scales values must be non-negative")
        scales.append(value)
    if not scales:
        raise SystemExit("--scales did not include any values")
    return scales


def parse_decay(text: str) -> tuple[float, ...]:
    return train.parse_positive_float_tuple(text, "--combat-event-movement-credit-decay")


def counter_text(counter: collections.Counter[str] | dict[str, int], *, limit: int = 0) -> str:
    items = sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    if limit > 0:
        items = items[:limit]
    return ", ".join(f"{key}={value}" for key, value in items) if items else "none"


def float_map_text(values: dict[str, float], *, limit: int = 0) -> str:
    items = sorted(values.items(), key=lambda item: (-abs(item[1]), item[0]))
    if limit > 0:
        items = items[:limit]
    return ", ".join(f"{key}={value:+.6f}" for key, value in items) if items else "none"


def int_map_text(values: dict[str, int], *, limit: int = 0) -> str:
    items = sorted(values.items(), key=lambda item: (-item[1], item[0]))
    if limit > 0:
        items = items[:limit]
    return ", ".join(f"{key}={value}" for key, value in items) if items else "none"


def rows_by_episode(rows: Iterable[dict[str, object]]) -> dict[tuple[int, int], list[dict[str, object]]]:
    grouped: dict[tuple[int, int], list[dict[str, object]]] = collections.defaultdict(list)
    for row in rows:
        grouped[train.episode_key(row)].append(row)
    for episode_rows in grouped.values():
        episode_rows.sort(key=train.row_order_key)
    return grouped


def episode_sort_key(key: tuple[int, int]) -> tuple[int, int]:
    return key


def select_action_name(row: dict[str, object], source: str) -> tuple[str | None, bool, str]:
    selection = train.rl.select_training_action(row, source)
    return selection.name, selection.step == 0, selection.source


def dry_run_apply_movement_credit(
    experiences: list[DryRunExperience],
    row: dict[str, object],
    action_name: str | None,
    action_start: bool,
    combat_event_reward_adjustment: float,
    reward_scale: float,
    combat_event_validation: combat_events.CombatEventTrainingValidation,
    config: train.CombatEventMovementCreditConfig,
    stats: train.CombatEventMovementCreditStats,
    examples: list[dict[str, object]],
    example_limit: int,
) -> tuple[int, int]:
    if not config.enabled:
        return 0, 0

    stats.checked_anchor_rows += 1
    if combat_event_reward_adjustment == 0.0:
        stats.skipped_no_reward += 1
        return 0, 0

    reason, allowed_actions = train.combat_event_movement_credit_kind(
        row,
        action_name,
        action_start,
        combat_event_reward_adjustment,
        combat_event_validation,
    )
    if not reason or not allowed_actions:
        stats.skipped_no_label += 1
        return 0, 0

    anchor_decision_id = train.int_field(row, "decision_id")
    anchor_episode = train.episode_key(row)
    candidates: list[int] = []
    cross_episode_candidates = 0
    for exp_index in range(len(experiences) - 1, -1, -1):
        exp = experiences[exp_index]
        exp_row = exp.row
        if train.episode_key(exp_row) != anchor_episode:
            break
        prior_decision_id = train.int_field(exp_row, "decision_id")
        if anchor_decision_id - prior_decision_id > config.window_decisions:
            break
        if exp.combat_event_batch_group in ("attack", "projectile", "punish_throw"):
            stats.skipped_cross_source_boundary += 1
            break
        if exp.action_name not in train.COMBAT_EVENT_MOVEMENT_CREDIT_ACTIONS:
            continue
        stats.candidate_rows += 1
        if train.episode_key(exp_row) != anchor_episode:
            cross_episode_candidates += 1
        if exp.action_name not in allowed_actions:
            stats.skipped_direction_mismatch += 1
            continue
        candidates.append(exp_index)
        if len(candidates) >= config.max_rows:
            break

    if not candidates:
        stats.skipped_no_candidate += 1
        return cross_episode_candidates, 0

    weights = train.combat_event_movement_credit_weights(config, len(candidates))
    if not weights:
        stats.skipped_no_candidate += 1
        return cross_episode_candidates, 0

    budget = combat_event_reward_adjustment * reward_scale * config.scale
    if budget == 0.0:
        stats.skipped_no_reward += 1
        return cross_episode_candidates, 0

    applied_for_anchor = False
    applied_rows: list[dict[str, object]] = []
    cross_episode_applied = 0
    stats.eligible_anchor_rows += 1
    for exp_index, weight in zip(candidates, weights):
        credit = budget * weight
        if credit == 0.0:
            continue
        if config.row_abs_cap > 0.0:
            used_abs = stats.credit_abs_by_exp_index.get(exp_index, 0.0)
            remaining_abs = max(0.0, config.row_abs_cap - used_abs)
            if remaining_abs <= 0.0:
                stats.capped_rows += 1
                continue
            if abs(credit) > remaining_abs:
                credit = remaining_abs if credit > 0.0 else -remaining_abs
                stats.capped_rows += 1
            stats.credit_abs_by_exp_index[exp_index] = used_abs + abs(credit)

        exp = experiences[exp_index]
        if train.episode_key(exp.row) != anchor_episode:
            cross_episode_applied += 1
        stats.add_credit(exp.action_name, reason, credit)
        applied_for_anchor = True
        if len(examples) < example_limit:
            applied_rows.append(
                {
                    "decision_id": train.int_field(exp.row, "decision_id"),
                    "obs_frame": train.int_field(exp.row, "obs_frame"),
                    "action": exp.action_name,
                    "group": exp.combat_event_batch_group,
                    "credit": credit,
                    "same_episode": train.episode_key(exp.row) == anchor_episode,
                }
            )

    if applied_for_anchor:
        stats.applied_anchor_rows += 1
        if len(examples) < example_limit:
            examples.append(
                {
                    "anchor": {
                        "run_id": train.int_field(row, "run_id"),
                        "episode_id": train.int_field(row, "episode_id"),
                        "decision_id": anchor_decision_id,
                        "obs_frame": train.int_field(row, "obs_frame"),
                        "action": action_name,
                        "reason": reason,
                        "raw_event_reward": combat_event_reward_adjustment,
                        "movement_budget": budget,
                    },
                    "credited_rows": applied_rows,
                }
            )

    return cross_episode_candidates, cross_episode_applied


def dry_run_scale(
    rows: list[dict[str, object]],
    actions: tuple[str, ...],
    validation: combat_events.CombatEventTrainingValidation,
    *,
    training_action_source: str,
    reward_profile: str,
    combat_event_reward_scale: float,
    reward_scale: float,
    movement_scale: float,
    window_decisions: int,
    max_rows: int,
    decay: tuple[float, ...],
    row_abs_cap: float,
    example_limit: int,
) -> DryRunResult:
    action_set = set(actions)
    experiences: list[DryRunExperience] = []
    stats = train.CombatEventMovementCreditStats()
    reward_stats = combat_events.CombatEventRewardStats()
    reward_config = combat_events.CombatEventRewardConfig(
        enabled=True,
        profile=reward_profile,
        scale=combat_event_reward_scale,
    )
    movement_config = train.CombatEventMovementCreditConfig(
        mode="delayed-v1",
        window_decisions=max(0, window_decisions),
        max_rows=max(0, max_rows),
        scale=max(0.0, movement_scale),
        decay=decay,
        row_abs_cap=max(0.0, row_abs_cap),
    )
    selected_action_counts: collections.Counter[str] = collections.Counter()
    experience_group_counts: collections.Counter[str] = collections.Counter()
    examples: list[dict[str, object]] = []
    action_start_rows = 0
    cross_episode_candidate_rows = 0
    cross_episode_applied_rows = 0

    grouped = rows_by_episode(rows)
    for episode_key_value in sorted(grouped, key=episode_sort_key):
        for row in grouped[episode_key_value]:
            action_name, action_start, _source = select_action_name(row, training_action_source)
            selected_action_counts[action_name or "none"] += 1
            if action_name is not None and action_start:
                action_start_rows += 1

            combat_event_reward_adjustment = combat_events.reward_adjustment_for_transition(
                validation.index,
                row,
                action_name,
                action_start,
                reward_config,
                reward_stats,
            )
            cross_candidates, cross_applied = dry_run_apply_movement_credit(
                experiences,
                row,
                action_name,
                action_start,
                combat_event_reward_adjustment,
                reward_scale,
                validation,
                movement_config,
                stats,
                examples,
                example_limit,
            )
            cross_episode_candidate_rows += cross_candidates
            cross_episode_applied_rows += cross_applied

            if action_name is None or not action_start or action_name not in action_set:
                continue

            combat_scaled_reward = combat_event_reward_adjustment * reward_scale
            group = train.combat_event_batch_group_for_transition(
                row,
                action_name,
                action_start,
                combat_scaled_reward,
                train.ProjectileResponseOutcome(),
                validation,
            )
            experiences.append(DryRunExperience(action_name=action_name, row=row, combat_event_batch_group=group))
            experience_group_counts[group] += 1

    return DryRunResult(
        scale=movement_scale,
        stats=stats,
        reward_stats=reward_stats,
        experiences=len(experiences),
        action_start_rows=action_start_rows,
        selected_action_counts=selected_action_counts,
        experience_group_counts=experience_group_counts,
        cross_episode_candidate_rows=cross_episode_candidate_rows,
        cross_episode_applied_rows=cross_episode_applied_rows,
        examples=examples,
    )


def guard_diagnostics(
    rows: list[dict[str, object]],
    *,
    training_action_source: str,
    success_window_decisions: int,
    threat_max_dx: int,
) -> dict[str, object]:
    counts: collections.Counter[str] = collections.Counter()
    grouped = rows_by_episode(rows)
    for episode_rows in grouped.values():
        for index, row in enumerate(episode_rows):
            action_name, action_start, _source = select_action_name(row, training_action_source)
            if action_name not in train.GUARD_ACTIONS or not action_start:
                continue
            counts["guard_start"] += 1
            if train.int_field(row, "obs_opp_routine_attack_state") != 0:
                counts["opponent_attacking"] += 1
            abs_dx = train.int_field(row, "obs_abs_dx")
            if abs_dx <= threat_max_dx:
                counts["in_threat_range"] += 1
            else:
                counts["far_guard_cost_candidate"] += 1
            window_end = min(len(episode_rows), index + max(0, success_window_decisions) + 1)
            lookahead = episode_rows[index:window_end]
            self_damage = sum(train.int_field(lookahead_row, "delta_self_hp") for lookahead_row in lookahead)
            guard_contact = any(
                train.int_field(lookahead_row, "obs_self_contact_reaction_state") != 0 for lookahead_row in lookahead
            )
            if self_damage == 0:
                counts["clean_window"] += 1
                if train.int_field(row, "obs_opp_routine_attack_state") == 0:
                    counts["passive_guard_cost_candidate"] += 1
            else:
                counts["damaged_window"] += 1
            if guard_contact:
                counts["guard_contact_window"] += 1
    return dict(counts)


def print_result(result: DryRunResult) -> None:
    stats = result.stats
    reward_stats = result.reward_stats
    print(f"\nMovement Credit Dry Run scale={result.scale:g}")
    print(f"  experiences={result.experiences} action_start_rows={result.action_start_rows}")
    print(f"  experience_groups={counter_text(result.experience_group_counts)}")
    print(
        "  event_reward "
        f"checked={reward_stats.checked_transition_rows} matched={reward_stats.matched_transition_rows} "
        f"adjusted={reward_stats.adjusted_transition_rows} raw_sum={reward_stats.raw_reward_sum:+.3f} "
        f"event_damage_sum={reward_stats.event_damage_reward_sum:+.3f}"
    )
    print(
        "  anchors "
        f"checked={stats.checked_anchor_rows} eligible={stats.eligible_anchor_rows} "
        f"applied={stats.applied_anchor_rows} candidate_rows={stats.candidate_rows} "
        f"applied_rows={stats.applied_rows}"
    )
    print(
        "  credit "
        f"net={stats.total_credit:+.6f} positive={stats.total_positive_credit:+.6f} "
        f"negative={stats.total_negative_credit:+.6f} capped_rows={stats.capped_rows}"
    )
    print(
        "  skips "
        f"no_reward={stats.skipped_no_reward} no_label={stats.skipped_no_label} "
        f"direction_mismatch={stats.skipped_direction_mismatch} "
        f"no_candidate={stats.skipped_no_candidate} "
        f"cross_source_boundary={stats.skipped_cross_source_boundary}"
    )
    print(
        "  cross_episode "
        f"candidate_rows={result.cross_episode_candidate_rows} applied_rows={result.cross_episode_applied_rows}"
    )
    print(f"  by_action={float_map_text(stats.by_action)}")
    print(f"  rows_by_action={int_map_text(stats.rows_by_action)}")
    print(f"  by_reason={float_map_text(stats.by_reason)}")
    print(f"  rows_by_reason={int_map_text(stats.rows_by_reason)}")
    print(f"  event_reward_by_outcome={float_map_text(reward_stats.raw_reward_by_outcome, limit=12)}")
    print(f"  selected_actions_top={counter_text(result.selected_action_counts, limit=12)}")
    for index, example in enumerate(result.examples, start=1):
        anchor = example["anchor"]
        print(
            "  example "
            f"{index}: anchor run={anchor['run_id']} ep={anchor['episode_id']} "
            f"dec={anchor['decision_id']} frame={anchor['obs_frame']} "
            f"action={anchor['action']} reason={anchor['reason']} "
            f"raw={anchor['raw_event_reward']:+.3f} budget={anchor['movement_budget']:+.6f}"
        )
        for credited in example["credited_rows"]:
            print(
                "    <- "
                f"dec={credited['decision_id']} frame={credited['obs_frame']} "
                f"action={credited['action']} group={credited['group']} "
                f"credit={credited['credit']:+.6f} same_episode={int(bool(credited['same_episode']))}"
            )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Dry-run Phase 9E delayed movement credit on paired transition/event logs. "
            "This prints diagnostics only; it does not train or write a model."
        )
    )
    parser.add_argument("transition_logs", nargs="+", help="Transition NDJSON log(s)")
    parser.add_argument("--combat-event-logs", nargs="+", required=True, help="Combat event NDJSON log(s)")
    parser.add_argument("--limit", type=int, default=0, help="Maximum transition rows to read; 0 reads all")
    parser.add_argument(
        "--actions",
        default=",".join(train.rl.TABULAR_DEFAULT_ACTIONS),
        help="Comma-separated action set, matching train_dqn_learner.py --actions",
    )
    parser.add_argument(
        "--training-action-source",
        choices=train.TRAINING_ACTION_SOURCES,
        default="auto",
        help="Action label source, matching train_dqn_learner.py --training-action-source",
    )
    parser.add_argument(
        "--combat-event-reward-profile",
        choices=combat_events.COMBAT_EVENT_REWARD_PROFILES,
        default="event-damage-v1",
        help="Event reward profile used as the anchor budget source",
    )
    parser.add_argument(
        "--combat-event-reward-scale",
        type=float,
        default=1.0,
        help="Additional combat event reward multiplier before the global reward scale",
    )
    parser.add_argument(
        "--reward-scale",
        type=float,
        default=0.01,
        help="Global reward scale, matching train_dqn_learner.py --reward-scale",
    )
    parser.add_argument(
        "--scales",
        default="0.35,1.0,2.0",
        help="Comma-separated delayed movement credit scales to compare",
    )
    parser.add_argument(
        "--combat-event-movement-credit-window",
        type=int,
        default=6,
        help="Maximum prior decision gap eligible for delayed movement credit",
    )
    parser.add_argument(
        "--combat-event-movement-credit-max-rows",
        type=int,
        default=3,
        help="Maximum prior movement rows credited by one anchor event",
    )
    parser.add_argument(
        "--combat-event-movement-credit-decay",
        default="0.50,0.30,0.20",
        help="Comma-separated weights from nearest to oldest prior movement row",
    )
    parser.add_argument(
        "--combat-event-movement-credit-row-cap",
        type=float,
        default=0.0,
        help="Optional absolute cap for delayed credit per experience; 0 disables the cap",
    )
    parser.add_argument("--examples", type=int, default=0, help="Print up to N credited-anchor examples per scale")
    parser.add_argument(
        "--allow-validation-errors",
        action="store_true",
        help="Print diagnostics even if paired log validation reports fatal errors",
    )
    parser.add_argument(
        "--reward-guard-success-window-decisions",
        type=int,
        default=15,
        help="Lookahead decisions for guard-cost candidate diagnostics",
    )
    parser.add_argument(
        "--reward-guard-threat-max-dx",
        type=int,
        default=144,
        help="Threat max dx for far-guard candidate diagnostics",
    )
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    actions = train.rl.parse_action_names(str(args.actions), option_name="--actions")
    rows = train.read_transition_rows([str(path) for path in args.transition_logs], max(0, int(args.limit)))
    validation = combat_events.validate_combat_event_training_logs(
        [str(path) for path in args.combat_event_logs],
        [str(path) for path in args.transition_logs],
        rows,
        "reward-shaping",
    )

    print("Combat Event Validation")
    print(f"  {validation.summary_line()}")
    if validation.fatal_errors:
        print("  fatal_errors:")
        for error in validation.fatal_errors:
            print(f"    - {error}")
        if not args.allow_validation_errors:
            raise SystemExit(2)

    print("Input")
    print(f"  transition_rows={len(rows)} actions={len(actions)} training_action_source={args.training_action_source}")
    print(
        "  reward "
        f"profile={args.combat_event_reward_profile} "
        f"combat_event_reward_scale={float(args.combat_event_reward_scale):g} "
        f"global_reward_scale={float(args.reward_scale):g}"
    )
    guard = guard_diagnostics(
        rows,
        training_action_source=str(args.training_action_source),
        success_window_decisions=max(0, int(args.reward_guard_success_window_decisions)),
        threat_max_dx=max(0, int(args.reward_guard_threat_max_dx)),
    )
    print(f"  guard_cost_candidates={counter_text(collections.Counter(guard))}")

    decay = parse_decay(str(args.combat_event_movement_credit_decay))
    for scale in parse_scales(str(args.scales)):
        result = dry_run_scale(
            rows,
            actions,
            validation,
            training_action_source=str(args.training_action_source),
            reward_profile=str(args.combat_event_reward_profile),
            combat_event_reward_scale=max(0.0, float(args.combat_event_reward_scale)),
            reward_scale=float(args.reward_scale),
            movement_scale=scale,
            window_decisions=int(args.combat_event_movement_credit_window),
            max_rows=int(args.combat_event_movement_credit_max_rows),
            decay=decay,
            row_abs_cap=float(args.combat_event_movement_credit_row_cap),
            example_limit=max(0, int(args.examples)),
        )
        print_result(result)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
