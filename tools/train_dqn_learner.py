#!/usr/bin/env python3
"""Train a small stdlib-only DQN actor from RL transition NDJSON logs."""

from __future__ import annotations

import argparse
import collections
import copy
import json
import math
import os
import random
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

import rl_probe_server as rl


@dataclass
class Experience:
    state: list[float]
    action_index: int
    reward: float
    next_state: list[float]
    done: bool


@dataclass
class BuildDiagnostics:
    included_action_rows: int = 0
    excluded_action_rows: int = 0
    excluded_action_reward_rows: int = 0
    excluded_action_reward_sum: float = 0.0
    macro_continuation_rows: int = 0
    macro_continuation_reward_rows: int = 0
    macro_continuation_reward_sum: float = 0.0
    macro_continuation_delayed_rewards: int = 0
    macro_continuation_uncredited_reward_rows: int = 0
    unrecognized_delayed_rewards: int = 0
    unrecognized_uncredited_reward_rows: int = 0

    def as_metadata(self) -> dict[str, object]:
        return {
            "included_action_rows": self.included_action_rows,
            "excluded_action_rows": self.excluded_action_rows,
            "excluded_action_reward_rows": self.excluded_action_reward_rows,
            "excluded_action_reward_sum": self.excluded_action_reward_sum,
            "macro_continuation_rows": self.macro_continuation_rows,
            "macro_continuation_reward_rows": self.macro_continuation_reward_rows,
            "macro_continuation_reward_sum": self.macro_continuation_reward_sum,
            "macro_continuation_delayed_rewards": self.macro_continuation_delayed_rewards,
            "macro_continuation_uncredited_reward_rows": self.macro_continuation_uncredited_reward_rows,
            "unrecognized_delayed_rewards": self.unrecognized_delayed_rewards,
            "unrecognized_uncredited_reward_rows": self.unrecognized_uncredited_reward_rows,
        }


@dataclass
class GreedyDiagnostics:
    counts: dict[str, int]
    top2_counts: dict[str, int]
    top3_counts: dict[str, int]
    q_mean: dict[str, float]
    evaluated: int
    top_action: str
    top_action_rate: float

    def as_metadata(self) -> dict[str, object]:
        return {
            "counts": self.counts,
            "top2_counts": self.top2_counts,
            "top3_counts": self.top3_counts,
            "q_mean": self.q_mean,
            "evaluated": self.evaluated,
            "top_action": self.top_action,
            "top_action_rate": self.top_action_rate,
        }


NON_ATTACK_ACTIONS = frozenset({"forward", "back", "guard-stand", "guard-crouch"})
ATTACK_RISK_ACTIONS = frozenset(action for action in rl.TABULAR_ACTION_NAMES if action not in NON_ATTACK_ACTIONS)
SHORYUKEN_ACTION = "shoryuken-mp"
JUMP_ATTACK_RISK_ACTIONS = frozenset(action for action in rl.TABULAR_ACTION_NAMES if action.startswith("jump-"))
REWARD_RISK_PROFILES = ("none", "shoryuken-only", "all-attacks")
DEMO_ATTRIBUTION_TRAINING_MODES = ("off", "augment", "replace-demo")
GUARD_ACTIONS = frozenset({"guard-stand", "guard-crouch"})
MOVEMENT_SPACING_ACTIONS = frozenset({"forward", "back"})
DEMO_EXECUTION_SOURCES = frozenset({4, 5})


@dataclass(frozen=True)
class RewardRiskConfig:
    profile: str
    window_decisions: int
    attack_no_damage_cost: float
    attack_punished_cost: float
    shoryuken_no_damage_extra_cost: float
    shoryuken_punished_extra_cost: float
    jump_attack_no_damage_extra_cost: float
    jump_attack_punished_extra_cost: float


@dataclass
class RewardRiskStats:
    no_damage_cost_events: int = 0
    punished_cost_events: int = 0
    attack_no_damage_cost_total: float = 0.0
    attack_punished_cost_total: float = 0.0
    shoryuken_no_damage_extra_cost_total: float = 0.0
    shoryuken_punished_extra_cost_total: float = 0.0
    jump_attack_no_damage_extra_cost_total: float = 0.0
    jump_attack_punished_extra_cost_total: float = 0.0

    @property
    def total_cost(self) -> float:
        return (
            self.attack_no_damage_cost_total
            + self.attack_punished_cost_total
            + self.shoryuken_no_damage_extra_cost_total
            + self.shoryuken_punished_extra_cost_total
            + self.jump_attack_no_damage_extra_cost_total
            + self.jump_attack_punished_extra_cost_total
        )

    def as_metadata(self) -> dict[str, object]:
        return {
            "no_damage_cost_events": self.no_damage_cost_events,
            "punished_cost_events": self.punished_cost_events,
            "attack_no_damage_cost_total": self.attack_no_damage_cost_total,
            "attack_punished_cost_total": self.attack_punished_cost_total,
            "shoryuken_no_damage_extra_cost_total": self.shoryuken_no_damage_extra_cost_total,
            "shoryuken_punished_extra_cost_total": self.shoryuken_punished_extra_cost_total,
            "jump_attack_no_damage_extra_cost_total": self.jump_attack_no_damage_extra_cost_total,
            "jump_attack_punished_extra_cost_total": self.jump_attack_punished_extra_cost_total,
            "total_cost": self.total_cost,
        }


@dataclass(frozen=True)
class RewardGuardConfig:
    success_bonus: float
    success_window_decisions: int
    threat_max_dx: int
    passive_guard_cost: float
    far_guard_cost: float


@dataclass
class RewardGuardStats:
    success_bonus_events: int = 0
    passive_guard_cost_events: int = 0
    far_guard_cost_events: int = 0
    success_bonus_total: float = 0.0
    passive_guard_cost_total: float = 0.0
    far_guard_cost_total: float = 0.0

    @property
    def total_bonus(self) -> float:
        return self.success_bonus_total

    @property
    def total_cost(self) -> float:
        return self.passive_guard_cost_total + self.far_guard_cost_total

    @property
    def net_adjustment(self) -> float:
        return self.total_bonus - self.total_cost

    def as_metadata(self) -> dict[str, object]:
        return {
            "success_bonus_events": self.success_bonus_events,
            "passive_guard_cost_events": self.passive_guard_cost_events,
            "far_guard_cost_events": self.far_guard_cost_events,
            "success_bonus_total": self.success_bonus_total,
            "passive_guard_cost_total": self.passive_guard_cost_total,
            "far_guard_cost_total": self.far_guard_cost_total,
            "total_bonus": self.total_bonus,
            "total_cost": self.total_cost,
            "net_adjustment": self.net_adjustment,
        }


@dataclass(frozen=True)
class RewardSpacingConfig:
    target_min_dx: int
    target_max_dx: int
    improve_bonus: float
    worsen_cost: float
    maintain_bonus: float
    threat_back_bonus: float


@dataclass
class RewardSpacingStats:
    improve_events: int = 0
    worsen_events: int = 0
    maintain_events: int = 0
    threat_back_events: int = 0
    improve_bonus_total: float = 0.0
    worsen_cost_total: float = 0.0
    maintain_bonus_total: float = 0.0
    threat_back_bonus_total: float = 0.0

    @property
    def total_bonus(self) -> float:
        return self.improve_bonus_total + self.maintain_bonus_total + self.threat_back_bonus_total

    @property
    def total_cost(self) -> float:
        return self.worsen_cost_total

    @property
    def net_adjustment(self) -> float:
        return self.total_bonus - self.total_cost

    def as_metadata(self) -> dict[str, object]:
        return {
            "improve_events": self.improve_events,
            "worsen_events": self.worsen_events,
            "maintain_events": self.maintain_events,
            "threat_back_events": self.threat_back_events,
            "improve_bonus_total": self.improve_bonus_total,
            "worsen_cost_total": self.worsen_cost_total,
            "maintain_bonus_total": self.maintain_bonus_total,
            "threat_back_bonus_total": self.threat_back_bonus_total,
            "total_bonus": self.total_bonus,
            "total_cost": self.total_cost,
            "net_adjustment": self.net_adjustment,
        }


@dataclass(frozen=True)
class RewardPositionConfig:
    corner_back_edge_threshold: int
    corner_guard_cost: float
    corner_back_cost: float
    corner_escape_bonus: float
    corner_escape_min_delta: int


@dataclass
class RewardPositionStats:
    corner_guard_cost_events: int = 0
    corner_back_cost_events: int = 0
    corner_escape_bonus_events: int = 0
    corner_guard_cost_total: float = 0.0
    corner_back_cost_total: float = 0.0
    corner_escape_bonus_total: float = 0.0

    @property
    def total_bonus(self) -> float:
        return self.corner_escape_bonus_total

    @property
    def total_cost(self) -> float:
        return self.corner_guard_cost_total + self.corner_back_cost_total

    @property
    def net_adjustment(self) -> float:
        return self.total_bonus - self.total_cost

    def as_metadata(self) -> dict[str, object]:
        return {
            "corner_guard_cost_events": self.corner_guard_cost_events,
            "corner_back_cost_events": self.corner_back_cost_events,
            "corner_escape_bonus_events": self.corner_escape_bonus_events,
            "corner_guard_cost_total": self.corner_guard_cost_total,
            "corner_back_cost_total": self.corner_back_cost_total,
            "corner_escape_bonus_total": self.corner_escape_bonus_total,
            "total_bonus": self.total_bonus,
            "total_cost": self.total_cost,
            "net_adjustment": self.net_adjustment,
        }


@dataclass(frozen=True)
class DemoAttributionConfig:
    training_mode: str
    window_decisions: int
    action_windows: dict[str, int]
    stop_at_next_event: bool
    hit_bonus: float
    no_damage_cost: float
    punished_cost: float


@dataclass
class DemoAttributionStats:
    event_rows: int = 0
    included_events: int = 0
    excluded_events: int = 0
    hit_events: int = 0
    no_damage_events: int = 0
    punished_events: int = 0
    trade_events: int = 0
    opp_hp_sum: int = 0
    self_hp_sum: int = 0
    base_reward_sum: float = 0.0
    hit_bonus_total: float = 0.0
    no_damage_cost_total: float = 0.0
    punished_cost_total: float = 0.0
    scaled_reward_sum: float = 0.0

    @property
    def total_bonus(self) -> float:
        return self.hit_bonus_total

    @property
    def total_cost(self) -> float:
        return self.no_damage_cost_total + self.punished_cost_total

    @property
    def net_adjustment(self) -> float:
        return self.total_bonus - self.total_cost

    def as_metadata(self) -> dict[str, object]:
        return {
            "event_rows": self.event_rows,
            "included_events": self.included_events,
            "excluded_events": self.excluded_events,
            "hit_events": self.hit_events,
            "no_damage_events": self.no_damage_events,
            "punished_events": self.punished_events,
            "trade_events": self.trade_events,
            "opp_hp_sum": self.opp_hp_sum,
            "self_hp_sum": self.self_hp_sum,
            "base_reward_sum": self.base_reward_sum,
            "hit_bonus_total": self.hit_bonus_total,
            "no_damage_cost_total": self.no_damage_cost_total,
            "punished_cost_total": self.punished_cost_total,
            "total_bonus": self.total_bonus,
            "total_cost": self.total_cost,
            "net_adjustment": self.net_adjustment,
            "scaled_reward_sum": self.scaled_reward_sum,
        }


def read_transition_rows(paths: list[str], limit: int) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for path in paths:
        with open(path, "r", encoding="utf-8") as stream:
            for line in stream:
                if limit > 0 and len(rows) >= limit:
                    return rows
                line = line.strip()
                if not line:
                    continue
                try:
                    raw_row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                replay_row = rl.learner_replay_row(raw_row)
                if replay_row is not None:
                    rows.append(replay_row)
    return rows


def drop_initial_episodes_per_run(rows: list[dict[str, object]], drop_count: int) -> tuple[list[dict[str, object]], int, int]:
    if drop_count <= 0:
        return rows, 0, 0
    seen: set[tuple[int, int]] = set()
    episodes_by_run: dict[int, list[int]] = collections.defaultdict(list)
    for row in rows:
        run_id, episode_id = episode_key(row)
        key = (run_id, episode_id)
        if key in seen:
            continue
        seen.add(key)
        episodes_by_run[run_id].append(episode_id)

    dropped_keys: set[tuple[int, int]] = set()
    for run_id, episode_ids in episodes_by_run.items():
        for episode_id in episode_ids[:drop_count]:
            dropped_keys.add((run_id, episode_id))

    filtered = [row for row in rows if episode_key(row) not in dropped_keys]
    return filtered, len(rows) - len(filtered), len(dropped_keys)


def episode_key(row: dict[str, object]) -> tuple[int, int]:
    return (int(row.get("run_id", 0) or 0), int(row.get("episode_id", 0) or 0))


def row_order_key(row: dict[str, object]) -> tuple[int, int]:
    return (int(row.get("decision_id", 0) or 0), int(row.get("obs_frame", 0) or 0))


def int_field(row: dict[str, object], name: str) -> int:
    return int(row.get(name, 0) or 0)


def is_action_start(row: dict[str, object]) -> bool:
    return int_field(row, "executed_policy_action_step") == 0


def is_demo_row(row: dict[str, object]) -> bool:
    return int_field(row, "execution_source") in DEMO_EXECUTION_SOURCES


def demo_attribution_present(row: dict[str, object]) -> bool:
    return (
        int_field(row, "demo_attribution_source") != 0
        or int_field(row, "demo_attributed_policy_action_id") != 0
        or int_field(row, "demo_attributed_policy_sub_action_id") != 0
    )


def policy_meta_action_name(action_id: int, sub_action_id: int) -> str | None:
    return rl.TABULAR_ACTION_NAMES_BY_POLICY_META.get((action_id, sub_action_id))


def demo_attributed_action_name(row: dict[str, object]) -> str | None:
    action_id = int_field(row, "demo_attributed_policy_action_id")
    sub_action_id = int_field(row, "demo_attributed_policy_sub_action_id")
    action_name = policy_meta_action_name(action_id, sub_action_id)
    if action_name is not None and action_name in rl.TABULAR_ACTION_NAMES:
        return action_name

    # The runtime can observe strength variants that are not separate live DQN
    # macro actions yet. Collapse those families onto the current learner action.
    if action_id == rl.RL_POLICY_ACTION_RYU_FIREBALL:
        return "fireball"
    if action_id == rl.RL_POLICY_ACTION_RYU_SHORYUKEN:
        return "shoryuken-mp"
    if action_id == rl.RL_POLICY_ACTION_RYU_TATSU:
        return "tatsu-mk"
    if action_id == rl.RL_POLICY_ACTION_THROW:
        return "throw"
    return action_name


def parse_demo_attribution_action_windows(value: str) -> dict[str, int]:
    windows: dict[str, int] = {}
    if not value.strip():
        return windows
    valid = set(rl.TABULAR_ACTION_NAMES)
    for raw_item in value.split(","):
        item = raw_item.strip()
        if not item:
            continue
        if "=" not in item:
            raise SystemExit(f"Invalid --demo-attribution-action-windows item: {item!r}; expected action=N")
        action, raw_window = (part.strip() for part in item.split("=", 1))
        if action not in valid:
            raise SystemExit(f"Unknown action in --demo-attribution-action-windows: {action}")
        try:
            window = int(raw_window)
        except ValueError as exc:
            raise SystemExit(f"Invalid window for {action}: {raw_window}") from exc
        windows[action] = max(0, window)
    return windows


def is_terminal_win(row: dict[str, object]) -> bool:
    return (
        bool(row.get("done", False))
        and int_field(row, "final_opp_hp") <= 0
        and int_field(row, "final_self_hp") > 0
    )


def dx_distance_to_target_band(dx: int, min_dx: int, max_dx: int) -> int:
    if dx < min_dx:
        return min_dx - dx
    if dx > max_dx:
        return dx - max_dx
    return 0


def next_decision_boundary_row(
    episode_rows: list[dict[str, object]],
    row_index: int,
) -> tuple[int, dict[str, object]] | None:
    for next_index, lookahead_row in enumerate(episode_rows[row_index + 1 :], start=row_index + 1):
        if is_action_start(lookahead_row) or bool(lookahead_row.get("done", False)):
            return next_index, lookahead_row
    return None


def reward_risk_cost(
    episode_rows: list[dict[str, object]],
    row_index: int,
    action_name: str,
    config: RewardRiskConfig,
    stats: RewardRiskStats,
) -> float:
    if config.profile == "none" or not is_action_start(episode_rows[row_index]):
        return 0.0

    apply_attack_cost = config.profile == "all-attacks" and action_name in ATTACK_RISK_ACTIONS
    apply_shoryuken_cost = action_name == SHORYUKEN_ACTION and config.profile in {"shoryuken-only", "all-attacks"}
    apply_jump_attack_cost = config.profile == "all-attacks" and action_name in JUMP_ATTACK_RISK_ACTIONS
    if not apply_attack_cost and not apply_shoryuken_cost and not apply_jump_attack_cost:
        return 0.0

    window_end = min(len(episode_rows), row_index + max(0, config.window_decisions) + 1)
    lookahead = episode_rows[row_index:window_end]
    if any(is_terminal_win(row) for row in lookahead):
        return 0.0

    opponent_damage = sum(int_field(row, "delta_opp_hp") for row in lookahead)
    if opponent_damage > 0:
        return 0.0

    self_damage = sum(int_field(row, "delta_self_hp") for row in lookahead)
    punished = self_damage > 0
    cost = 0.0
    stats.no_damage_cost_events += 1

    if apply_attack_cost:
        cost += config.attack_no_damage_cost
        stats.attack_no_damage_cost_total += config.attack_no_damage_cost
        if punished:
            cost += config.attack_punished_cost
            stats.attack_punished_cost_total += config.attack_punished_cost

    if apply_shoryuken_cost:
        cost += config.shoryuken_no_damage_extra_cost
        stats.shoryuken_no_damage_extra_cost_total += config.shoryuken_no_damage_extra_cost
        if punished:
            cost += config.shoryuken_punished_extra_cost
            stats.shoryuken_punished_extra_cost_total += config.shoryuken_punished_extra_cost

    if apply_jump_attack_cost:
        cost += config.jump_attack_no_damage_extra_cost
        stats.jump_attack_no_damage_extra_cost_total += config.jump_attack_no_damage_extra_cost
        if punished:
            cost += config.jump_attack_punished_extra_cost
            stats.jump_attack_punished_extra_cost_total += config.jump_attack_punished_extra_cost

    if punished:
        stats.punished_cost_events += 1
    return cost


def reward_guard_adjustment(
    episode_rows: list[dict[str, object]],
    row_index: int,
    action_name: str,
    config: RewardGuardConfig,
    stats: RewardGuardStats,
) -> float:
    row = episode_rows[row_index]
    if action_name not in GUARD_ACTIONS or not is_action_start(row):
        return 0.0

    opponent_attacking = int_field(row, "obs_opp_routine_attack_state") != 0
    abs_dx = int_field(row, "obs_abs_dx")
    in_threat_range = abs_dx <= config.threat_max_dx
    window_end = min(len(episode_rows), row_index + max(0, config.success_window_decisions) + 1)
    lookahead = episode_rows[row_index:window_end]
    self_damage = sum(int_field(lookahead_row, "delta_self_hp") for lookahead_row in lookahead)
    clean_guard_window = self_damage == 0
    adjustment = 0.0

    if config.success_bonus > 0.0 and opponent_attacking and in_threat_range and clean_guard_window:
        adjustment += config.success_bonus
        stats.success_bonus_events += 1
        stats.success_bonus_total += config.success_bonus

    if config.passive_guard_cost > 0.0 and clean_guard_window and not opponent_attacking:
        adjustment -= config.passive_guard_cost
        stats.passive_guard_cost_events += 1
        stats.passive_guard_cost_total += config.passive_guard_cost

    if config.far_guard_cost > 0.0 and clean_guard_window and not in_threat_range:
        adjustment -= config.far_guard_cost
        stats.far_guard_cost_events += 1
        stats.far_guard_cost_total += config.far_guard_cost

    return adjustment


def reward_spacing_adjustment(
    episode_rows: list[dict[str, object]],
    row_index: int,
    action_name: str,
    config: RewardSpacingConfig,
    stats: RewardSpacingStats,
) -> float:
    row = episode_rows[row_index]
    if action_name not in MOVEMENT_SPACING_ACTIONS or not is_action_start(row):
        return 0.0
    if (
        config.improve_bonus <= 0.0
        and config.worsen_cost <= 0.0
        and config.maintain_bonus <= 0.0
        and config.threat_back_bonus <= 0.0
    ):
        return 0.0

    next_boundary = next_decision_boundary_row(episode_rows, row_index)
    if next_boundary is None:
        return 0.0
    next_index, next_row = next_boundary

    current_dx = int_field(row, "obs_abs_dx")
    next_dx = int_field(next_row, "obs_abs_dx")
    current_distance = dx_distance_to_target_band(current_dx, config.target_min_dx, config.target_max_dx)
    next_distance = dx_distance_to_target_band(next_dx, config.target_min_dx, config.target_max_dx)
    current_in_target = current_distance == 0
    next_in_target = next_distance == 0
    window_rows = episode_rows[row_index : next_index + 1]
    self_damage = sum(int_field(lookahead_row, "delta_self_hp") for lookahead_row in window_rows)
    clean_spacing_window = self_damage == 0
    adjustment = 0.0

    if clean_spacing_window and config.improve_bonus > 0.0 and next_distance < current_distance:
        adjustment += config.improve_bonus
        stats.improve_events += 1
        stats.improve_bonus_total += config.improve_bonus
    elif clean_spacing_window and config.maintain_bonus > 0.0 and current_in_target and next_in_target:
        adjustment += config.maintain_bonus
        stats.maintain_events += 1
        stats.maintain_bonus_total += config.maintain_bonus
    elif clean_spacing_window and config.worsen_cost > 0.0 and next_distance > current_distance:
        adjustment -= config.worsen_cost
        stats.worsen_events += 1
        stats.worsen_cost_total += config.worsen_cost

    opponent_attacking = int_field(row, "obs_opp_routine_attack_state") != 0
    if (
        clean_spacing_window
        and config.threat_back_bonus > 0.0
        and action_name == "back"
        and opponent_attacking
        and current_dx < config.target_min_dx
        and next_dx > current_dx
    ):
        adjustment += config.threat_back_bonus
        stats.threat_back_events += 1
        stats.threat_back_bonus_total += config.threat_back_bonus

    return adjustment


def reward_position_adjustment(
    episode_rows: list[dict[str, object]],
    row_index: int,
    action_name: str,
    config: RewardPositionConfig,
    stats: RewardPositionStats,
) -> float:
    row = episode_rows[row_index]
    if not is_action_start(row) or "obs_self_back_edge_dist" not in row:
        return 0.0
    if (
        config.corner_guard_cost <= 0.0
        and config.corner_back_cost <= 0.0
        and config.corner_escape_bonus <= 0.0
    ):
        return 0.0

    current_back_edge = int_field(row, "obs_self_back_edge_dist")
    if current_back_edge > config.corner_back_edge_threshold:
        return 0.0

    next_boundary = next_decision_boundary_row(episode_rows, row_index)
    if next_boundary is None:
        next_index = row_index
        next_row = row
    else:
        next_index, next_row = next_boundary

    window_rows = episode_rows[row_index : next_index + 1]
    self_damage = sum(int_field(lookahead_row, "delta_self_hp") for lookahead_row in window_rows)
    clean_position_window = self_damage == 0
    if not clean_position_window:
        return 0.0

    adjustment = 0.0
    if action_name in GUARD_ACTIONS and config.corner_guard_cost > 0.0:
        adjustment -= config.corner_guard_cost
        stats.corner_guard_cost_events += 1
        stats.corner_guard_cost_total += config.corner_guard_cost

    if action_name == "back" and config.corner_back_cost > 0.0:
        adjustment -= config.corner_back_cost
        stats.corner_back_cost_events += 1
        stats.corner_back_cost_total += config.corner_back_cost

    next_back_edge = int_field(next_row, "obs_self_back_edge_dist")
    if (
        action_name == "forward"
        and config.corner_escape_bonus > 0.0
        and next_back_edge >= current_back_edge + config.corner_escape_min_delta
    ):
        adjustment += config.corner_escape_bonus
        stats.corner_escape_bonus_events += 1
        stats.corner_escape_bonus_total += config.corner_escape_bonus

    return adjustment


def add_delayed_reward(
    experiences: list[Experience],
    exp_index: int | None,
    reward: float,
    actions: tuple[str, ...],
    action_rewards: dict[str, float],
) -> bool:
    if exp_index is None:
        return False
    experiences[exp_index].reward += reward
    action_rewards[actions[experiences[exp_index].action_index]] += reward
    return True


def set_experience_next_state(
    experiences: list[Experience],
    exp_index: int | None,
    row: dict[str, object],
    done: bool,
) -> None:
    if exp_index is None:
        return
    experiences[exp_index].next_state = rl.dqn_feature_vector(row)
    experiences[exp_index].done = done


def demo_attribution_window_for_action(action_name: str, config: DemoAttributionConfig) -> int:
    return max(0, int(config.action_windows.get(action_name, config.window_decisions)))


def add_demo_attribution_experience(
    episode_rows: list[dict[str, object]],
    row_index: int,
    actions: tuple[str, ...],
    action_to_index: dict[str, int],
    reward_scale: float,
    config: DemoAttributionConfig,
    stats: DemoAttributionStats,
    experiences: list[Experience],
    action_counts: dict[str, int],
    action_rewards: dict[str, float],
) -> bool:
    if config.training_mode == "off":
        return False
    row = episode_rows[row_index]
    if not is_demo_row(row) or not demo_attribution_present(row):
        return False

    stats.event_rows += 1
    action_name = demo_attributed_action_name(row)
    if action_name is None or action_name not in action_to_index:
        stats.excluded_events += 1
        return False

    window_end = min(len(episode_rows), row_index + demo_attribution_window_for_action(action_name, config) + 1)
    if config.stop_at_next_event:
        for next_index in range(row_index + 1, window_end):
            if demo_attribution_present(episode_rows[next_index]):
                window_end = next_index
                break
    window_rows = episode_rows[row_index:window_end]
    if not window_rows:
        window_rows = [row]

    opponent_damage = sum(int_field(window_row, "delta_opp_hp") for window_row in window_rows)
    self_damage = sum(int_field(window_row, "delta_self_hp") for window_row in window_rows)
    base_reward = float(opponent_damage - self_damage)
    adjustment = 0.0

    if opponent_damage > 0:
        stats.hit_events += 1
        adjustment += config.hit_bonus
        stats.hit_bonus_total += config.hit_bonus
    else:
        stats.no_damage_events += 1
        adjustment -= config.no_damage_cost
        stats.no_damage_cost_total += config.no_damage_cost

    if self_damage > 0:
        stats.punished_events += 1
        adjustment -= config.punished_cost
        stats.punished_cost_total += config.punished_cost
    if opponent_damage > 0 and self_damage > 0:
        stats.trade_events += 1

    reward = (base_reward + adjustment) * reward_scale
    next_row = window_rows[-1]
    done = any(bool(window_row.get("done", False)) for window_row in window_rows)
    experiences.append(
        Experience(
            state=rl.dqn_feature_vector(row),
            action_index=action_to_index[action_name],
            reward=reward,
            next_state=rl.dqn_feature_vector(next_row),
            done=done,
        )
    )
    stats.included_events += 1
    stats.opp_hp_sum += opponent_damage
    stats.self_hp_sum += self_damage
    stats.base_reward_sum += base_reward
    stats.scaled_reward_sum += reward
    action_counts[action_name] += 1
    action_rewards[action_name] += reward
    return True


def build_experiences(
    rows: list[dict[str, object]],
    actions: tuple[str, ...],
    reward_scale: float,
    reward_risk_config: RewardRiskConfig,
    reward_guard_config: RewardGuardConfig,
    reward_spacing_config: RewardSpacingConfig,
    reward_position_config: RewardPositionConfig,
    demo_attribution_config: DemoAttributionConfig,
) -> tuple[
    list[Experience],
    dict[str, int],
    dict[str, float],
    dict[str, int],
    dict[str, float],
    BuildDiagnostics,
    RewardRiskStats,
    RewardGuardStats,
    RewardSpacingStats,
    RewardPositionStats,
    DemoAttributionStats,
]:
    action_to_index = {action: index for index, action in enumerate(actions)}
    by_episode: dict[tuple[int, int], list[dict[str, object]]] = collections.defaultdict(list)
    for row in rows:
        by_episode[episode_key(row)].append(row)

    experiences: list[Experience] = []
    action_counts = {action: 0 for action in actions}
    action_rewards = {action: 0.0 for action in actions}
    observed_action_counts = {action: 0 for action in rl.TABULAR_ACTION_NAMES}
    observed_action_rewards = {action: 0.0 for action in rl.TABULAR_ACTION_NAMES}
    build_stats = BuildDiagnostics()
    risk_stats = RewardRiskStats()
    guard_stats = RewardGuardStats()
    spacing_stats = RewardSpacingStats()
    position_stats = RewardPositionStats()
    demo_attribution_stats = DemoAttributionStats()

    for episode_rows in by_episode.values():
        episode_rows.sort(key=row_order_key)
        last_exp_index: int | None = None
        for index, row in enumerate(episode_rows):
            if demo_attribution_config.training_mode != "off":
                if demo_attribution_config.training_mode == "replace-demo" and is_demo_row(row):
                    set_experience_next_state(experiences, last_exp_index, row, bool(row.get("done", False)))
                    last_exp_index = None
                    add_demo_attribution_experience(
                        episode_rows,
                        index,
                        actions,
                        action_to_index,
                        reward_scale,
                        demo_attribution_config,
                        demo_attribution_stats,
                        experiences,
                        action_counts,
                        action_rewards,
                    )
                    continue
                add_demo_attribution_experience(
                    episode_rows,
                    index,
                    actions,
                    action_to_index,
                    reward_scale,
                    demo_attribution_config,
                    demo_attribution_stats,
                    experiences,
                    action_counts,
                    action_rewards,
                )

            action_name = rl.transition_action_name(row)
            action_start = is_action_start(row)
            risk_cost = (
                reward_risk_cost(episode_rows, index, action_name, reward_risk_config, risk_stats)
                if action_name is not None
                else 0.0
            )
            guard_adjustment = (
                reward_guard_adjustment(episode_rows, index, action_name, reward_guard_config, guard_stats)
                if action_name is not None
                else 0.0
            )
            spacing_adjustment = (
                reward_spacing_adjustment(episode_rows, index, action_name, reward_spacing_config, spacing_stats)
                if action_name is not None
                else 0.0
            )
            position_adjustment = (
                reward_position_adjustment(episode_rows, index, action_name, reward_position_config, position_stats)
                if action_name is not None
                else 0.0
            )
            reward = (
                rl.tabular_training_reward(row)
                - risk_cost
                + guard_adjustment
                + spacing_adjustment
                + position_adjustment
            ) * reward_scale
            if action_name is None:
                if reward != 0.0:
                    if add_delayed_reward(experiences, last_exp_index, reward, actions, action_rewards):
                        build_stats.unrecognized_delayed_rewards += 1
                    else:
                        build_stats.unrecognized_uncredited_reward_rows += 1
                continue

            if action_name in observed_action_counts:
                observed_action_counts[action_name] += 1
                observed_action_rewards[action_name] += reward

            if action_start:
                set_experience_next_state(experiences, last_exp_index, row, bool(row.get("done", False)))

            if action_name not in action_to_index:
                build_stats.excluded_action_rows += 1
                if reward != 0.0:
                    build_stats.excluded_action_reward_rows += 1
                    build_stats.excluded_action_reward_sum += reward
                last_exp_index = None
                continue

            if not action_start:
                build_stats.macro_continuation_rows += 1
                if reward != 0.0:
                    build_stats.macro_continuation_reward_rows += 1
                    build_stats.macro_continuation_reward_sum += reward
                    if add_delayed_reward(experiences, last_exp_index, reward, actions, action_rewards):
                        build_stats.macro_continuation_delayed_rewards += 1
                    else:
                        build_stats.macro_continuation_uncredited_reward_rows += 1
                continue

            exp = Experience(
                state=rl.dqn_feature_vector(row),
                action_index=action_to_index[action_name],
                reward=reward,
                next_state=rl.dqn_feature_vector(row),
                done=bool(row.get("done", False)),
            )
            experiences.append(exp)
            last_exp_index = len(experiences) - 1
            build_stats.included_action_rows += 1
            action_counts[action_name] += 1
            action_rewards[action_name] += reward

        if episode_rows:
            set_experience_next_state(experiences, last_exp_index, episode_rows[-1], True)

    return (
        experiences,
        action_counts,
        action_rewards,
        observed_action_counts,
        observed_action_rewards,
        build_stats,
        risk_stats,
        guard_stats,
        spacing_stats,
        position_stats,
        demo_attribution_stats,
    )


def reward_risk_config_from_args(args: argparse.Namespace) -> RewardRiskConfig:
    return RewardRiskConfig(
        profile=str(args.reward_risk_profile),
        window_decisions=max(0, int(args.reward_risk_window_decisions)),
        attack_no_damage_cost=max(0.0, float(args.reward_attack_no_damage_cost)),
        attack_punished_cost=max(0.0, float(args.reward_attack_punished_cost)),
        shoryuken_no_damage_extra_cost=max(0.0, float(args.reward_shoryuken_no_damage_extra_cost)),
        shoryuken_punished_extra_cost=max(0.0, float(args.reward_shoryuken_punished_extra_cost)),
        jump_attack_no_damage_extra_cost=max(0.0, float(args.reward_jump_attack_no_damage_extra_cost)),
        jump_attack_punished_extra_cost=max(0.0, float(args.reward_jump_attack_punished_extra_cost)),
    )


def reward_guard_config_from_args(args: argparse.Namespace) -> RewardGuardConfig:
    return RewardGuardConfig(
        success_bonus=max(0.0, float(args.reward_guard_success_bonus)),
        success_window_decisions=max(0, int(args.reward_guard_success_window_decisions)),
        threat_max_dx=max(0, int(args.reward_guard_threat_max_dx)),
        passive_guard_cost=max(0.0, float(args.reward_passive_guard_cost)),
        far_guard_cost=max(0.0, float(args.reward_far_guard_cost)),
    )


def reward_spacing_config_from_args(args: argparse.Namespace) -> RewardSpacingConfig:
    target_min_dx = max(0, int(args.reward_spacing_target_min_dx))
    target_max_dx = max(target_min_dx, int(args.reward_spacing_target_max_dx))
    return RewardSpacingConfig(
        target_min_dx=target_min_dx,
        target_max_dx=target_max_dx,
        improve_bonus=max(0.0, float(args.reward_spacing_improve_bonus)),
        worsen_cost=max(0.0, float(args.reward_spacing_worsen_cost)),
        maintain_bonus=max(0.0, float(args.reward_spacing_maintain_bonus)),
        threat_back_bonus=max(0.0, float(args.reward_spacing_threat_back_bonus)),
    )


def reward_position_config_from_args(args: argparse.Namespace) -> RewardPositionConfig:
    return RewardPositionConfig(
        corner_back_edge_threshold=max(0, int(args.reward_corner_back_edge_threshold)),
        corner_guard_cost=max(0.0, float(args.reward_corner_guard_cost)),
        corner_back_cost=max(0.0, float(args.reward_corner_back_cost)),
        corner_escape_bonus=max(0.0, float(args.reward_corner_escape_bonus)),
        corner_escape_min_delta=max(0, int(args.reward_corner_escape_min_delta)),
    )


def demo_attribution_config_from_args(args: argparse.Namespace) -> DemoAttributionConfig:
    return DemoAttributionConfig(
        training_mode=str(args.demo_attribution_training_mode),
        window_decisions=max(0, int(args.demo_attribution_window_decisions)),
        action_windows=parse_demo_attribution_action_windows(str(args.demo_attribution_action_windows)),
        stop_at_next_event=bool(args.demo_attribution_stop_at_next_event),
        hit_bonus=max(0.0, float(args.demo_attribution_hit_bonus)),
        no_damage_cost=max(0.0, float(args.demo_attribution_no_damage_cost)),
        punished_cost=max(0.0, float(args.demo_attribution_punished_cost)),
    )


def init_network(input_dim: int, hidden_sizes: list[int], output_dim: int, rng: random.Random) -> list[dict[str, object]]:
    layers: list[dict[str, object]] = []
    prev_dim = input_dim
    layer_sizes = hidden_sizes + [output_dim]
    for index, size in enumerate(layer_sizes):
        scale = math.sqrt(2.0 / max(1, prev_dim))
        weights = [[rng.uniform(-scale, scale) for _ in range(prev_dim)] for _ in range(size)]
        bias = [0.0 for _ in range(size)]
        activation = "relu" if index + 1 < len(layer_sizes) else "linear"
        layers.append({"weights": weights, "bias": bias, "activation": activation})
        prev_dim = size
    return layers


def forward(layers: list[dict[str, object]], inputs: list[float]) -> tuple[list[float], list[list[float]], list[list[float]]]:
    activations = [inputs]
    pre_activations: list[list[float]] = []
    current = inputs
    for layer in layers:
        weights = layer["weights"]
        bias = layer["bias"]
        assert isinstance(weights, list)
        assert isinstance(bias, list)
        z_values = [
            float(raw_bias) + sum(float(weight) * value for weight, value in zip(raw_row, current))
            for raw_row, raw_bias in zip(weights, bias)
        ]
        if str(layer.get("activation", "linear")) == "relu":
            current = [max(0.0, value) for value in z_values]
        else:
            current = z_values
        pre_activations.append(z_values)
        activations.append(current)
    return current, activations, pre_activations


def zero_grads(layers: list[dict[str, object]]) -> list[dict[str, object]]:
    grads: list[dict[str, object]] = []
    for layer in layers:
        weights = layer["weights"]
        bias = layer["bias"]
        assert isinstance(weights, list)
        assert isinstance(bias, list)
        grads.append(
            {
                "weights": [[0.0 for _ in raw_row] for raw_row in weights],
                "bias": [0.0 for _ in bias],
            }
        )
    return grads


def add_backward_grads(
    layers: list[dict[str, object]],
    grads: list[dict[str, object]],
    activations: list[list[float]],
    pre_activations: list[list[float]],
    output_grad: list[float],
) -> None:
    grad = output_grad
    for layer_index in range(len(layers) - 1, -1, -1):
        layer = layers[layer_index]
        weights = layer["weights"]
        assert isinstance(weights, list)
        if str(layer.get("activation", "linear")) == "relu":
            grad_z = [value if pre_activations[layer_index][i] > 0.0 else 0.0 for i, value in enumerate(grad)]
        else:
            grad_z = grad

        layer_grads = grads[layer_index]
        weight_grads = layer_grads["weights"]
        bias_grads = layer_grads["bias"]
        assert isinstance(weight_grads, list)
        assert isinstance(bias_grads, list)
        prev_activation = activations[layer_index]
        for out_index, grad_value in enumerate(grad_z):
            bias_grads[out_index] += grad_value
            for in_index, prev_value in enumerate(prev_activation):
                weight_grads[out_index][in_index] += grad_value * prev_value

        next_grad = [0.0 for _ in prev_activation]
        for out_index, grad_value in enumerate(grad_z):
            for in_index, weight in enumerate(weights[out_index]):
                next_grad[in_index] += grad_value * float(weight)
        grad = next_grad


def apply_grads(layers: list[dict[str, object]], grads: list[dict[str, object]], lr: float, batch_size: int) -> None:
    scale = lr / max(1, batch_size)
    for layer, layer_grads in zip(layers, grads):
        weights = layer["weights"]
        bias = layer["bias"]
        weight_grads = layer_grads["weights"]
        bias_grads = layer_grads["bias"]
        assert isinstance(weights, list)
        assert isinstance(bias, list)
        assert isinstance(weight_grads, list)
        assert isinstance(bias_grads, list)
        for out_index in range(len(weights)):
            bias[out_index] = float(bias[out_index]) - scale * max(-10.0, min(10.0, bias_grads[out_index]))
            for in_index in range(len(weights[out_index])):
                grad = max(-10.0, min(10.0, weight_grads[out_index][in_index]))
                weights[out_index][in_index] = float(weights[out_index][in_index]) - scale * grad


def train_dqn(
    experiences: list[Experience],
    actions: tuple[str, ...],
    hidden_sizes: list[int],
    steps: int,
    batch_size: int,
    learning_rate: float,
    gamma: float,
    target_sync_steps: int,
    seed: int,
    log_interval: int,
) -> tuple[list[dict[str, object]], dict[str, float]]:
    rng = random.Random(seed)
    layers = init_network(len(rl.DQN_FEATURE_NAMES), hidden_sizes, len(actions), rng)
    target_layers = copy.deepcopy(layers)
    last_loss = 0.0
    avg_loss = 0.0

    for step in range(1, steps + 1):
        batch = rng.choices(experiences, k=batch_size)
        grads = zero_grads(layers)
        loss = 0.0
        for exp in batch:
            values, activations, pre_activations = forward(layers, exp.state)
            next_values, _, _ = forward(target_layers, exp.next_state)
            target = exp.reward if exp.done else exp.reward + gamma * max(next_values)
            error = max(-10.0, min(10.0, values[exp.action_index] - target))
            loss += 0.5 * error * error
            output_grad = [0.0 for _ in values]
            output_grad[exp.action_index] = error
            add_backward_grads(layers, grads, activations, pre_activations, output_grad)
        apply_grads(layers, grads, learning_rate, batch_size)
        last_loss = loss / max(1, batch_size)
        avg_loss = last_loss if step == 1 else (0.98 * avg_loss + 0.02 * last_loss)
        if target_sync_steps > 0 and step % target_sync_steps == 0:
            target_layers = copy.deepcopy(layers)
        if log_interval > 0 and (step == 1 or step % log_interval == 0 or step == steps):
            print(f"TRAIN step={step} loss={last_loss:.6f} avg_loss={avg_loss:.6f}", flush=True)

    return layers, {"last_loss": last_loss, "avg_loss": avg_loss}


def count_greedy_actions(layers: list[dict[str, object]], experiences: list[Experience], actions: tuple[str, ...], limit: int) -> dict[str, int]:
    counts = {action: 0 for action in actions}
    for exp in experiences[: max(0, limit)]:
        values, _, _ = forward(layers, exp.state)
        best_index = max(range(min(len(actions), len(values))), key=lambda index: (values[index], actions[index]))
        counts[actions[best_index]] += 1
    return counts


def next_model_version(model_dir: str, requested: int | None) -> int:
    if requested is not None:
        return max(0, requested)
    current_path = Path(model_dir) / "current.json"
    try:
        with current_path.open("r", encoding="utf-8") as stream:
            current = json.load(stream)
        return max(0, int(current.get("version", 0) or 0)) + 1
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return 1


def publish_model(
    model_dir: str,
    version: int,
    actions: tuple[str, ...],
    layers: list[dict[str, object]],
    epsilon: float,
    fallback_policy: str,
    updated_rows: int,
    metadata: dict[str, object],
) -> None:
    os.makedirs(model_dir, exist_ok=True)
    dqn_model = {
        "feature_names": list(rl.DQN_FEATURE_NAMES),
        "feature_scales": dict(rl.DQN_FEATURE_SCALES),
        "layers": layers,
    }
    payload = {
        "version": version,
        "policy": "dqn",
        "source": "offline-dqn",
        "action_set_version": rl.ACTION_SET_VERSION,
        "created_at_unix": time.time(),
        "metadata": metadata,
        "actions": list(actions),
        "epsilon": epsilon,
        "fallback_policy": fallback_policy,
        "dqn": dqn_model,
        "updated_rows": updated_rows,
    }
    version_path = Path(model_dir) / f"actor-v{version}.json"
    current_path = Path(model_dir) / "current.json"
    for path in (version_path, current_path):
        fd, temp_path = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=model_dir)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(payload, stream, sort_keys=True)
                stream.write("\n")
            rl.replace_with_retries(temp_path, str(path))
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)


def parse_hidden_sizes(value: str) -> list[int]:
    sizes = [int(item) for item in value.split(",") if item.strip()]
    return [max(1, size) for size in sizes] or [64, 64]


def parse_action_subset(value: str) -> tuple[str, ...]:
    if not value.strip():
        return rl.TABULAR_DEFAULT_ACTIONS
    valid = set(rl.TABULAR_ACTION_NAMES)
    actions: list[str] = []
    invalid: list[str] = []
    for raw_item in value.split(","):
        action = raw_item.strip()
        if not action:
            continue
        if action not in valid:
            invalid.append(action)
            continue
        if action not in actions:
            actions.append(action)
    if invalid:
        raise SystemExit(f"Unknown DQN action(s): {','.join(invalid)}")
    if not actions:
        raise SystemExit("DQN action subset is empty")
    return tuple(actions)


def format_action_scores(counts: dict[str, int], rewards: dict[str, float], actions: tuple[str, ...], limit: int) -> str:
    rows: list[tuple[str, int, float, float]] = []
    for action in actions:
        count = int(counts.get(action, 0))
        reward = float(rewards.get(action, 0.0))
        mean = reward / count if count else 0.0
        rows.append((action, count, reward, mean))
    rows.sort(key=lambda item: (item[1], abs(item[2]), item[0]), reverse=True)
    parts = [f"{action}:{count}/{reward:.2f}/{mean:.3f}" for action, count, reward, mean in rows[: max(1, limit)]]
    if len(rows) > limit:
        parts.append(f"...+{len(rows) - limit}")
    return ",".join(parts) if parts else "none"


def format_counts(counts: dict[str, int], total: int, limit: int) -> str:
    ordered = sorted(counts.items(), key=lambda item: (item[1], item[0]), reverse=True)
    parts: list[str] = []
    for action, count in ordered[: max(1, limit)]:
        if count <= 0:
            continue
        pct = 100.0 * count / max(1, total)
        parts.append(f"{action}:{count}/{pct:.1f}%")
    if len(ordered) > limit:
        remaining = sum(count for _, count in ordered[max(1, limit) :])
        if remaining > 0:
            parts.append(f"...+{remaining}")
    return ",".join(parts) if parts else "none"


def evaluate_greedy_actions(
    layers: list[dict[str, object]],
    experiences: list[Experience],
    actions: tuple[str, ...],
    limit: int,
) -> GreedyDiagnostics:
    eval_experiences = experiences[: max(0, limit)]
    counts = {action: 0 for action in actions}
    top2_counts = {action: 0 for action in actions}
    top3_counts = {action: 0 for action in actions}
    q_sums = {action: 0.0 for action in actions}
    q_seen = {action: 0 for action in actions}
    for exp in eval_experiences:
        values, _, _ = forward(layers, exp.state)
        count = min(len(actions), len(values))
        if count <= 0:
            continue
        ranked = sorted(range(count), key=lambda index: (float(values[index]), actions[index]), reverse=True)
        counts[actions[ranked[0]]] += 1
        for rank, action_index in enumerate(ranked[:3]):
            action = actions[action_index]
            if rank < 2:
                top2_counts[action] += 1
            top3_counts[action] += 1
        for index in range(count):
            action = actions[index]
            q_sums[action] += float(values[index])
            q_seen[action] += 1
    evaluated = len(eval_experiences)
    top_action = ""
    top_count = 0
    for action, count in counts.items():
        if count > top_count:
            top_action = action
            top_count = count
    q_mean = {action: q_sums[action] / q_seen[action] for action in actions if q_seen[action] > 0}
    top_action_rate = top_count / evaluated if evaluated else 0.0
    return GreedyDiagnostics(
        counts=counts,
        top2_counts=top2_counts,
        top3_counts=top3_counts,
        q_mean=q_mean,
        evaluated=evaluated,
        top_action=top_action,
        top_action_rate=top_action_rate,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("transition_logs", nargs="+", help="Transition NDJSON logs used as offline replay data")
    parser.add_argument("--model-dir", required=True, help="Directory where DQN actor manifests will be published")
    parser.add_argument("--model-version", type=int, default=None, help="Explicit model version; defaults to current+1")
    parser.add_argument("--limit", type=int, default=0, help="Maximum rows to read across all transition logs; 0 means all")
    parser.add_argument(
        "--drop-initial-episodes-per-run",
        type=int,
        default=0,
        help="Drop the first N episodes from each run before building DQN experiences",
    )
    parser.add_argument("--steps", type=int, default=2000, help="Gradient steps")
    parser.add_argument("--batch-size", type=int, default=64, help="Replay batch size")
    parser.add_argument("--hidden-sizes", default="64,64", help="Comma-separated hidden layer sizes")
    parser.add_argument(
        "--actions",
        default=",".join(rl.TABULAR_DEFAULT_ACTIONS),
        help="Comma-separated DQN action subset; default is the full current action set",
    )
    parser.add_argument("--learning-rate", type=float, default=0.001, help="MLP learning rate")
    parser.add_argument("--gamma", type=float, default=0.95, help="DQN discounted future reward")
    parser.add_argument("--reward-scale", type=float, default=0.01, help="Scale applied to HP-delta reward during training")
    parser.add_argument(
        "--reward-risk-profile",
        choices=REWARD_RISK_PROFILES,
        default="none",
        help=(
            "Optional no-damage action cost profile: none=HP-delta baseline, "
            "shoryuken-only=only Shoryuken extra costs, all-attacks=generic attack costs plus Shoryuken extra costs"
        ),
    )
    parser.add_argument(
        "--reward-risk-window-decisions",
        type=int,
        default=10,
        help="Lookahead decisions used to decide whether an action produced no opponent HP damage",
    )
    parser.add_argument(
        "--reward-attack-no-damage-cost",
        type=float,
        default=0.5,
        help="Positive raw reward cost subtracted from all attack actions with no opponent HP damage in all-attacks profile",
    )
    parser.add_argument(
        "--reward-attack-punished-cost",
        type=float,
        default=2.0,
        help="Additional positive raw reward cost when a no-damage attack is followed by self HP damage in all-attacks profile",
    )
    parser.add_argument(
        "--reward-shoryuken-no-damage-extra-cost",
        type=float,
        default=1.0,
        help="Positive raw reward cost subtracted from no-damage shoryuken-mp in shoryuken-only/all-attacks profiles",
    )
    parser.add_argument(
        "--reward-shoryuken-punished-extra-cost",
        type=float,
        default=4.0,
        help="Additional positive raw reward cost when no-damage shoryuken-mp is followed by self HP damage",
    )
    parser.add_argument(
        "--reward-jump-attack-no-damage-extra-cost",
        type=float,
        default=0.0,
        help="Additional positive raw reward cost subtracted from no-damage jump attacks in all-attacks profile",
    )
    parser.add_argument(
        "--reward-jump-attack-punished-extra-cost",
        type=float,
        default=0.0,
        help="Additional positive raw reward cost when a no-damage jump attack is followed by self HP damage",
    )
    parser.add_argument(
        "--reward-guard-success-bonus",
        type=float,
        default=0.0,
        help=(
            "Positive raw reward bonus for guard-stand/guard-crouch starts when the opponent is attacking, "
            "the spacing is within --reward-guard-threat-max-dx, and no self HP damage occurs in the guard window"
        ),
    )
    parser.add_argument(
        "--reward-guard-success-window-decisions",
        type=int,
        default=15,
        help="Lookahead decisions used to decide whether a guard action avoided self HP damage",
    )
    parser.add_argument(
        "--reward-guard-threat-max-dx",
        type=int,
        default=144,
        help="Maximum obs_abs_dx treated as close/mid threat range for guard success; farther guard can be penalized",
    )
    parser.add_argument(
        "--reward-passive-guard-cost",
        type=float,
        default=0.0,
        help="Positive raw reward cost subtracted from guard starts when the opponent is not attacking",
    )
    parser.add_argument(
        "--reward-far-guard-cost",
        type=float,
        default=0.0,
        help="Positive raw reward cost subtracted from guard starts with obs_abs_dx above --reward-guard-threat-max-dx",
    )
    parser.add_argument(
        "--reward-spacing-target-min-dx",
        type=int,
        default=50,
        help="Minimum obs_abs_dx for the preferred spacing band used by movement reward shaping",
    )
    parser.add_argument(
        "--reward-spacing-target-max-dx",
        type=int,
        default=120,
        help="Maximum obs_abs_dx for the preferred spacing band used by movement reward shaping",
    )
    parser.add_argument(
        "--reward-spacing-improve-bonus",
        type=float,
        default=0.0,
        help="Positive raw reward bonus when forward/back moves obs_abs_dx closer to the preferred spacing band",
    )
    parser.add_argument(
        "--reward-spacing-worsen-cost",
        type=float,
        default=0.0,
        help="Positive raw reward cost when forward/back moves obs_abs_dx farther from the preferred spacing band",
    )
    parser.add_argument(
        "--reward-spacing-maintain-bonus",
        type=float,
        default=0.0,
        help="Positive raw reward bonus when forward/back keeps obs_abs_dx inside the preferred spacing band",
    )
    parser.add_argument(
        "--reward-spacing-threat-back-bonus",
        type=float,
        default=0.0,
        help="Additional positive raw reward bonus when back increases close spacing while the opponent is attacking",
    )
    parser.add_argument(
        "--reward-corner-back-edge-threshold",
        type=int,
        default=60,
        help="obs_self_back_edge_dist threshold treated as trapped near own corner for position reward shaping",
    )
    parser.add_argument(
        "--reward-corner-guard-cost",
        type=float,
        default=0.0,
        help="Positive raw reward cost subtracted from clean guard starts near own corner",
    )
    parser.add_argument(
        "--reward-corner-back-cost",
        type=float,
        default=0.0,
        help="Positive raw reward cost subtracted from clean back starts near own corner",
    )
    parser.add_argument(
        "--reward-corner-escape-bonus",
        type=float,
        default=0.0,
        help="Positive raw reward bonus when forward increases obs_self_back_edge_dist near own corner",
    )
    parser.add_argument(
        "--reward-corner-escape-min-delta",
        type=int,
        default=8,
        help="Minimum obs_self_back_edge_dist increase needed for --reward-corner-escape-bonus",
    )
    parser.add_argument(
        "--demo-attribution-training-mode",
        choices=DEMO_ATTRIBUTION_TRAINING_MODES,
        default="off",
        help=(
            "Optional engine-attributed demo training: off=use input/executed action rows, "
            "augment=add extra demo_attributed_* experiences, replace-demo=use demo_attributed_* "
            "instead of input/executed rows for demo sources"
        ),
    )
    parser.add_argument(
        "--demo-attribution-window-decisions",
        type=int,
        default=10,
        help="Global lookahead decisions used to credit delayed HP deltas to demo-attributed move events",
    )
    parser.add_argument(
        "--demo-attribution-action-windows",
        default="",
        help=(
            "Optional comma-separated per-action delayed-credit windows, e.g. "
            "fireball=15,throw=8; omitted actions use --demo-attribution-window-decisions"
        ),
    )
    parser.add_argument(
        "--demo-attribution-stop-at-next-event",
        action="store_true",
        help="Stop a demo-attribution delayed-credit window at the next demo-attributed move event in the same episode",
    )
    parser.add_argument(
        "--demo-attribution-hit-bonus",
        type=float,
        default=0.0,
        help="Additional positive raw reward added when a demo-attributed move causes opponent HP damage in its window",
    )
    parser.add_argument(
        "--demo-attribution-no-damage-cost",
        type=float,
        default=0.0,
        help="Positive raw reward cost subtracted when a demo-attributed move causes no opponent HP damage in its window",
    )
    parser.add_argument(
        "--demo-attribution-punished-cost",
        type=float,
        default=0.0,
        help="Positive raw reward cost subtracted when a demo-attributed move window includes self HP damage",
    )
    parser.add_argument("--target-sync-steps", type=int, default=200, help="Steps between target-network syncs")
    parser.add_argument("--epsilon", type=float, default=0.05, help="Exploration probability stamped into the published actor")
    parser.add_argument(
        "--fallback-policy",
        choices=rl.SCRIPTED_POLICY_CHOICES,
        default="hp",
        help="Scripted fallback if DQN inference has no valid observation/model",
    )
    parser.add_argument("--seed", type=int, default=7, help="Random seed")
    parser.add_argument("--log-interval", type=int, default=200, help="Training progress print interval")
    parser.add_argument("--eval-limit", type=int, default=5000, help="Rows used for greedy action distribution summary")
    parser.add_argument("--diagnostic-top-n", type=int, default=8, help="Top actions printed in DQN diagnostic summaries")
    parser.add_argument(
        "--collapse-warning-threshold",
        type=float,
        default=0.70,
        help="Warn when one greedy action exceeds this fraction of evaluated rows",
    )
    args = parser.parse_args()

    actions = parse_action_subset(args.actions)
    rows = read_transition_rows(args.transition_logs, args.limit)
    rows_read_before_episode_drop = len(rows)
    rows, dropped_initial_episode_rows, dropped_initial_episodes = drop_initial_episodes_per_run(
        rows,
        max(0, int(args.drop_initial_episodes_per_run)),
    )
    reward_risk_config = reward_risk_config_from_args(args)
    reward_guard_config = reward_guard_config_from_args(args)
    reward_spacing_config = reward_spacing_config_from_args(args)
    reward_position_config = reward_position_config_from_args(args)
    demo_attribution_config = demo_attribution_config_from_args(args)
    (
        experiences,
        action_counts,
        action_rewards,
        observed_action_counts,
        observed_action_rewards,
        build_stats,
        reward_risk_stats,
        reward_guard_stats,
        reward_spacing_stats,
        reward_position_stats,
        demo_attribution_stats,
    ) = build_experiences(
        rows,
        actions,
        args.reward_scale,
        reward_risk_config,
        reward_guard_config,
        reward_spacing_config,
        reward_position_config,
        demo_attribution_config,
    )
    if not experiences:
        raise SystemExit("No DQN experiences built from transition logs")

    layers, train_stats = train_dqn(
        experiences,
        actions,
        parse_hidden_sizes(args.hidden_sizes),
        max(1, args.steps),
        max(1, args.batch_size),
        max(1e-8, args.learning_rate),
        min(0.999, max(0.0, args.gamma)),
        max(1, args.target_sync_steps),
        args.seed,
        args.log_interval,
    )
    greedy_diag = evaluate_greedy_actions(layers, experiences, actions, args.eval_limit)
    version = next_model_version(args.model_dir, args.model_version)
    reward_sources = ["hp-delta"]
    if reward_risk_config.profile != "none":
        reward_sources.append("risk-cost")
    if reward_guard_stats.net_adjustment != 0.0:
        reward_sources.append("guard-shaping")
    if reward_spacing_stats.net_adjustment != 0.0:
        reward_sources.append("spacing-shaping")
    if reward_position_stats.net_adjustment != 0.0:
        reward_sources.append("position-shaping")
    if demo_attribution_config.training_mode != "off":
        reward_sources.append("demo-attribution")
    reward_source = "+".join(reward_sources)
    metadata = {
        "transition_logs": args.transition_logs,
        "rows_read": len(rows),
        "rows_read_before_episode_drop": rows_read_before_episode_drop,
        "drop_initial_episodes_per_run": max(0, int(args.drop_initial_episodes_per_run)),
        "dropped_initial_episode_rows": dropped_initial_episode_rows,
        "dropped_initial_episodes": dropped_initial_episodes,
        "experiences": len(experiences),
        "actions_subset": list(actions),
        "actions_subset_size": len(actions),
        "build_diagnostics": build_stats.as_metadata(),
        "delayed_rewards": build_stats.unrecognized_delayed_rewards + build_stats.macro_continuation_delayed_rewards,
        "reward_source": reward_source,
        "reward_scale": args.reward_scale,
        "reward_scale_applied_after_risk_cost": True,
        "reward_scale_applied_after_raw_adjustments": True,
        "reward_risk_profile": reward_risk_config.profile,
        "reward_risk_window_decisions": reward_risk_config.window_decisions,
        "reward_attack_no_damage_cost": reward_risk_config.attack_no_damage_cost,
        "reward_attack_punished_cost": reward_risk_config.attack_punished_cost,
        "reward_shoryuken_no_damage_extra_cost": reward_risk_config.shoryuken_no_damage_extra_cost,
        "reward_shoryuken_punished_extra_cost": reward_risk_config.shoryuken_punished_extra_cost,
        "reward_jump_attack_no_damage_extra_cost": reward_risk_config.jump_attack_no_damage_extra_cost,
        "reward_jump_attack_punished_extra_cost": reward_risk_config.jump_attack_punished_extra_cost,
        "reward_risk_stats": reward_risk_stats.as_metadata(),
        "reward_guard_success_bonus": reward_guard_config.success_bonus,
        "reward_guard_success_window_decisions": reward_guard_config.success_window_decisions,
        "reward_guard_threat_max_dx": reward_guard_config.threat_max_dx,
        "reward_passive_guard_cost": reward_guard_config.passive_guard_cost,
        "reward_far_guard_cost": reward_guard_config.far_guard_cost,
        "reward_guard_stats": reward_guard_stats.as_metadata(),
        "reward_spacing_target_min_dx": reward_spacing_config.target_min_dx,
        "reward_spacing_target_max_dx": reward_spacing_config.target_max_dx,
        "reward_spacing_improve_bonus": reward_spacing_config.improve_bonus,
        "reward_spacing_worsen_cost": reward_spacing_config.worsen_cost,
        "reward_spacing_maintain_bonus": reward_spacing_config.maintain_bonus,
        "reward_spacing_threat_back_bonus": reward_spacing_config.threat_back_bonus,
        "reward_spacing_stats": reward_spacing_stats.as_metadata(),
        "reward_corner_back_edge_threshold": reward_position_config.corner_back_edge_threshold,
        "reward_corner_guard_cost": reward_position_config.corner_guard_cost,
        "reward_corner_back_cost": reward_position_config.corner_back_cost,
        "reward_corner_escape_bonus": reward_position_config.corner_escape_bonus,
        "reward_corner_escape_min_delta": reward_position_config.corner_escape_min_delta,
        "reward_position_stats": reward_position_stats.as_metadata(),
        "demo_attribution_training_mode": demo_attribution_config.training_mode,
        "demo_attribution_window_decisions": demo_attribution_config.window_decisions,
        "demo_attribution_action_windows": demo_attribution_config.action_windows,
        "demo_attribution_stop_at_next_event": demo_attribution_config.stop_at_next_event,
        "demo_attribution_hit_bonus": demo_attribution_config.hit_bonus,
        "demo_attribution_no_damage_cost": demo_attribution_config.no_damage_cost,
        "demo_attribution_punished_cost": demo_attribution_config.punished_cost,
        "demo_attribution_stats": demo_attribution_stats.as_metadata(),
        "steps": max(1, args.steps),
        "batch_size": max(1, args.batch_size),
        "gamma": min(0.999, max(0.0, args.gamma)),
        "learning_rate": max(1e-8, args.learning_rate),
        "action_counts": action_counts,
        "action_rewards": action_rewards,
        "observed_action_counts": observed_action_counts,
        "observed_action_rewards": observed_action_rewards,
        "greedy_counts": greedy_diag.counts,
        "greedy_top2_counts": greedy_diag.top2_counts,
        "greedy_top3_counts": greedy_diag.top3_counts,
        "greedy_q_mean": greedy_diag.q_mean,
        "greedy_top_action": greedy_diag.top_action,
        "greedy_top_action_rate": greedy_diag.top_action_rate,
        **train_stats,
    }
    publish_model(
        args.model_dir,
        version,
        actions,
        layers,
        min(1.0, max(0.0, args.epsilon)),
        args.fallback_policy,
        len(experiences),
        metadata,
    )
    print(
        "DQN published "
        f"version={version} model_dir={args.model_dir} rows={len(rows)} "
        f"raw_rows={rows_read_before_episode_drop} "
        f"drop_ep={dropped_initial_episodes}/{dropped_initial_episode_rows} "
        f"experiences={len(experiences)} "
        f"actions={len(actions)} "
        f"risk={reward_risk_config.profile} risk_cost={reward_risk_stats.total_cost:.1f} "
        f"guard_bonus={reward_guard_stats.total_bonus:.1f} "
        f"guard_cost={reward_guard_stats.total_cost:.1f} "
        f"guard_net={reward_guard_stats.net_adjustment:.1f} "
        f"spacing_bonus={reward_spacing_stats.total_bonus:.1f} "
        f"spacing_cost={reward_spacing_stats.total_cost:.1f} "
        f"spacing_net={reward_spacing_stats.net_adjustment:.1f} "
        f"position_bonus={reward_position_stats.total_bonus:.1f} "
        f"position_cost={reward_position_stats.total_cost:.1f} "
        f"position_net={reward_position_stats.net_adjustment:.1f} "
        f"demo_attr={demo_attribution_config.training_mode}:{demo_attribution_stats.included_events}/"
        f"{demo_attribution_stats.event_rows} "
        f"demo_attr_net={demo_attribution_stats.net_adjustment:.1f} "
        f"loss={train_stats['last_loss']:.6f} avg_loss={train_stats['avg_loss']:.6f} "
        f"included={build_stats.included_action_rows} excluded={build_stats.excluded_action_rows} "
        f"cont={build_stats.macro_continuation_rows} "
        f"cont_rew={build_stats.macro_continuation_reward_sum:.3f} "
        f"excluded_rew={build_stats.excluded_action_reward_sum:.3f} "
        f"top={greedy_diag.top_action}:{greedy_diag.top_action_rate * 100.0:.1f}% "
        f"greedy={format_counts(greedy_diag.counts, greedy_diag.evaluated, args.diagnostic_top_n)}",
        flush=True,
    )
    print(
        "DQN diagnostics "
        f"action_stats=count/reward/mean {format_action_scores(action_counts, action_rewards, actions, args.diagnostic_top_n)}",
        flush=True,
    )
    print(
        "DQN diagnostics "
        f"observed_all=count/reward/mean "
        f"{format_action_scores(observed_action_counts, observed_action_rewards, rl.TABULAR_ACTION_NAMES, args.diagnostic_top_n)}",
        flush=True,
    )
    print(
        "DQN diagnostics "
        f"risk_shape=no_damage:{reward_risk_stats.no_damage_cost_events} "
        f"punished:{reward_risk_stats.punished_cost_events} "
        f"attack:{reward_risk_stats.attack_no_damage_cost_total:.1f}/{reward_risk_stats.attack_punished_cost_total:.1f} "
        f"shoryuken:{reward_risk_stats.shoryuken_no_damage_extra_cost_total:.1f}/"
        f"{reward_risk_stats.shoryuken_punished_extra_cost_total:.1f} "
        f"jump:{reward_risk_stats.jump_attack_no_damage_extra_cost_total:.1f}/"
        f"{reward_risk_stats.jump_attack_punished_extra_cost_total:.1f}",
        flush=True,
    )
    print(
        "DQN diagnostics "
        f"guard_shape=success:{reward_guard_stats.success_bonus_events}/{reward_guard_stats.success_bonus_total:.1f} "
        f"passive:{reward_guard_stats.passive_guard_cost_events}/{reward_guard_stats.passive_guard_cost_total:.1f} "
        f"far:{reward_guard_stats.far_guard_cost_events}/{reward_guard_stats.far_guard_cost_total:.1f} "
        f"net:{reward_guard_stats.net_adjustment:.1f}",
        flush=True,
    )
    print(
        "DQN diagnostics "
        f"spacing_shape=target:{reward_spacing_config.target_min_dx}-{reward_spacing_config.target_max_dx} "
        f"improve:{reward_spacing_stats.improve_events}/{reward_spacing_stats.improve_bonus_total:.1f} "
        f"maintain:{reward_spacing_stats.maintain_events}/{reward_spacing_stats.maintain_bonus_total:.1f} "
        f"worsen:{reward_spacing_stats.worsen_events}/{reward_spacing_stats.worsen_cost_total:.1f} "
        f"threat_back:{reward_spacing_stats.threat_back_events}/{reward_spacing_stats.threat_back_bonus_total:.1f} "
        f"net:{reward_spacing_stats.net_adjustment:.1f}",
        flush=True,
    )
    print(
        "DQN diagnostics "
        f"position_shape=corner_back_edge<={reward_position_config.corner_back_edge_threshold} "
        f"corner_guard:{reward_position_stats.corner_guard_cost_events}/"
        f"{reward_position_stats.corner_guard_cost_total:.1f} "
        f"corner_back:{reward_position_stats.corner_back_cost_events}/"
        f"{reward_position_stats.corner_back_cost_total:.1f} "
        f"escape:{reward_position_stats.corner_escape_bonus_events}/"
        f"{reward_position_stats.corner_escape_bonus_total:.1f} "
        f"net:{reward_position_stats.net_adjustment:.1f}",
        flush=True,
    )
    print(
        "DQN diagnostics "
        f"demo_attr=mode:{demo_attribution_config.training_mode} "
        f"events:{demo_attribution_stats.event_rows} "
        f"included:{demo_attribution_stats.included_events} "
        f"excluded:{demo_attribution_stats.excluded_events} "
        f"window:{demo_attribution_config.window_decisions} "
        f"stop_next:{int(demo_attribution_config.stop_at_next_event)} "
        f"hit:{demo_attribution_stats.hit_events} "
        f"no_damage:{demo_attribution_stats.no_damage_events} "
        f"punished:{demo_attribution_stats.punished_events} "
        f"trade:{demo_attribution_stats.trade_events} "
        f"hp:{demo_attribution_stats.opp_hp_sum}/{demo_attribution_stats.self_hp_sum} "
        f"bonus:{demo_attribution_stats.total_bonus:.1f} "
        f"cost:{demo_attribution_stats.total_cost:.1f} "
        f"net:{demo_attribution_stats.net_adjustment:.1f} "
        f"scaled_reward:{demo_attribution_stats.scaled_reward_sum:.3f}",
        flush=True,
    )
    print(
        "DQN diagnostics "
        f"top2={format_counts(greedy_diag.top2_counts, greedy_diag.evaluated, args.diagnostic_top_n)} "
        f"top3={format_counts(greedy_diag.top3_counts, greedy_diag.evaluated, args.diagnostic_top_n)}",
        flush=True,
    )
    if greedy_diag.top_action_rate >= max(0.0, min(1.0, args.collapse_warning_threshold)):
        print(
            "DQN warning "
            f"greedy action collapse candidate: {greedy_diag.top_action} "
            f"{greedy_diag.top_action_rate * 100.0:.1f}% >= "
            f"{max(0.0, min(1.0, args.collapse_warning_threshold)) * 100.0:.1f}%",
            flush=True,
        )


if __name__ == "__main__":
    main()
