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
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

import rl_probe_server as rl


@dataclass
class Experience:
    state: list[float]
    action_index: int
    reward: float
    next_state: list[float]
    done: bool
    source_name: str = "unknown"
    model_version: int = 0


EXECUTION_SOURCE_NAMES = {
    0: "none",
    1: "remote",
    2: "repeated-last-action",
    3: "neutral-fallback",
    4: "human-demo",
    5: "cpu-demo",
}


SOURCE_NAME_ALIASES = {
    "none": "none",
    "remote": "remote",
    "remote-agent": "remote",
    "repeated-last-action": "repeated-last-action",
    "repeated-last": "repeated-last-action",
    "repeated": "repeated-last-action",
    "repeat": "repeated-last-action",
    "neutral-fallback": "neutral-fallback",
    "neutral": "neutral-fallback",
    "fallback": "neutral-fallback",
    "human-demo": "human-demo",
    "human": "human-demo",
    "cpu-demo": "cpu-demo",
    "cpu": "cpu-demo",
}


@dataclass
class SourceReplayDiagnostics:
    row_counts: dict[str, int] = field(default_factory=dict)
    row_model_version_counts: dict[str, int] = field(default_factory=dict)
    row_model_version_counts_by_source: dict[str, dict[str, int]] = field(default_factory=dict)
    experience_counts: dict[str, int] = field(default_factory=dict)
    experience_reward_sum: dict[str, float] = field(default_factory=dict)
    experience_model_version_counts: dict[str, int] = field(default_factory=dict)
    experience_model_version_counts_by_source: dict[str, dict[str, int]] = field(default_factory=dict)
    experience_action_counts: dict[str, dict[str, int]] = field(default_factory=dict)
    experience_action_reward_sum: dict[str, dict[str, float]] = field(default_factory=dict)

    def add_row(self, source_name: str, model_version: int) -> None:
        version_key = str(model_version)
        self.row_counts[source_name] = self.row_counts.get(source_name, 0) + 1
        self.row_model_version_counts[version_key] = self.row_model_version_counts.get(version_key, 0) + 1
        source_versions = self.row_model_version_counts_by_source.setdefault(source_name, {})
        source_versions[version_key] = source_versions.get(version_key, 0) + 1

    def add_experience(
        self,
        source_name: str,
        model_version: int,
        action_name: str,
        reward: float,
        count: int = 1,
    ) -> None:
        safe_count = max(0, int(count))
        if safe_count <= 0:
            return
        version_key = str(model_version)
        scaled_reward = reward * safe_count
        self.experience_counts[source_name] = self.experience_counts.get(source_name, 0) + safe_count
        self.experience_reward_sum[source_name] = self.experience_reward_sum.get(source_name, 0.0) + scaled_reward
        self.experience_model_version_counts[version_key] = (
            self.experience_model_version_counts.get(version_key, 0) + safe_count
        )
        source_versions = self.experience_model_version_counts_by_source.setdefault(source_name, {})
        source_versions[version_key] = source_versions.get(version_key, 0) + safe_count
        source_actions = self.experience_action_counts.setdefault(source_name, {})
        source_actions[action_name] = source_actions.get(action_name, 0) + safe_count
        source_rewards = self.experience_action_reward_sum.setdefault(source_name, {})
        source_rewards[action_name] = source_rewards.get(action_name, 0.0) + scaled_reward

    def add_reward(self, source_name: str, action_name: str, reward: float) -> None:
        self.experience_reward_sum[source_name] = self.experience_reward_sum.get(source_name, 0.0) + reward
        source_rewards = self.experience_action_reward_sum.setdefault(source_name, {})
        source_rewards[action_name] = source_rewards.get(action_name, 0.0) + reward

    def as_metadata(self) -> dict[str, object]:
        return {
            "execution_source_labels": {str(key): value for key, value in sorted(EXECUTION_SOURCE_NAMES.items())},
            "row_counts": dict(sorted(self.row_counts.items())),
            "row_model_version_counts": dict(sorted(self.row_model_version_counts.items())),
            "row_model_version_counts_by_source": {
                source: dict(sorted(counts.items()))
                for source, counts in sorted(self.row_model_version_counts_by_source.items())
            },
            "experience_counts": dict(sorted(self.experience_counts.items())),
            "experience_reward_sum": dict(sorted(self.experience_reward_sum.items())),
            "experience_model_version_counts": dict(sorted(self.experience_model_version_counts.items())),
            "experience_model_version_counts_by_source": {
                source: dict(sorted(counts.items()))
                for source, counts in sorted(self.experience_model_version_counts_by_source.items())
            },
            "experience_action_counts": {
                source: dict(sorted(counts.items()))
                for source, counts in sorted(self.experience_action_counts.items())
            },
            "experience_action_reward_sum": {
                source: dict(sorted(rewards.items()))
                for source, rewards in sorted(self.experience_action_reward_sum.items())
            },
        }


@dataclass(frozen=True)
class ReplaySourceMixConfig:
    include_sources: frozenset[str]
    exclude_sources: frozenset[str]
    max_rows_by_source: dict[str, int]
    target_ratios: dict[str, float]

    @property
    def enabled(self) -> bool:
        return bool(
            self.include_sources
            or self.exclude_sources
            or self.max_rows_by_source
            or self.target_ratios
        )

    def as_metadata(self) -> dict[str, object]:
        return {
            "include_sources": sorted(self.include_sources),
            "exclude_sources": sorted(self.exclude_sources),
            "max_rows_by_source": dict(sorted(self.max_rows_by_source.items())),
            "target_ratios": dict(sorted(self.target_ratios.items())),
        }


@dataclass(frozen=True)
class ReplaySourceMixStats:
    mode: str
    raw_rows: int
    mixed_rows: int
    dropped_rows: int
    pre_counts: dict[str, int]
    post_counts: dict[str, int]
    dropped_counts: dict[str, int]
    target_counts: dict[str, int]

    def as_metadata(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "raw_rows": self.raw_rows,
            "mixed_rows": self.mixed_rows,
            "dropped_rows": self.dropped_rows,
            "pre_counts": dict(sorted(self.pre_counts.items())),
            "post_counts": dict(sorted(self.post_counts.items())),
            "dropped_counts": dict(sorted(self.dropped_counts.items())),
            "target_counts": dict(sorted(self.target_counts.items())),
        }


@dataclass
class BuildDiagnostics:
    included_action_rows: int = 0
    excluded_action_rows: int = 0
    excluded_action_reward_rows: int = 0
    excluded_action_reward_sum: float = 0.0
    engine_outcome_input_fallback_rows: int = 0
    macro_continuation_rows: int = 0
    macro_continuation_reward_rows: int = 0
    macro_continuation_reward_sum: float = 0.0
    macro_continuation_delayed_rewards: int = 0
    macro_continuation_uncredited_reward_rows: int = 0
    unrecognized_delayed_rewards: int = 0
    unrecognized_uncredited_reward_rows: int = 0
    action_source_counts: dict[str, int] = field(default_factory=dict)
    movable_filter_checked_rows: int = 0
    movable_filter_included_rows: int = 0
    movable_filter_filtered_rows: int = 0
    movable_filter_reward_rows: int = 0
    movable_filter_reward_sum: float = 0.0
    movable_filter_delayed_rewards: int = 0
    movable_filter_uncredited_reward_rows: int = 0
    movable_filter_by_source: dict[str, int] = field(default_factory=dict)
    movable_filter_by_action: dict[str, int] = field(default_factory=dict)
    movable_filter_by_reason: dict[str, int] = field(default_factory=dict)

    def as_metadata(self) -> dict[str, object]:
        return {
            "included_action_rows": self.included_action_rows,
            "excluded_action_rows": self.excluded_action_rows,
            "excluded_action_reward_rows": self.excluded_action_reward_rows,
            "excluded_action_reward_sum": self.excluded_action_reward_sum,
            "engine_outcome_input_fallback_rows": self.engine_outcome_input_fallback_rows,
            "macro_continuation_rows": self.macro_continuation_rows,
            "macro_continuation_reward_rows": self.macro_continuation_reward_rows,
            "macro_continuation_reward_sum": self.macro_continuation_reward_sum,
            "macro_continuation_delayed_rewards": self.macro_continuation_delayed_rewards,
            "macro_continuation_uncredited_reward_rows": self.macro_continuation_uncredited_reward_rows,
            "unrecognized_delayed_rewards": self.unrecognized_delayed_rewards,
            "unrecognized_uncredited_reward_rows": self.unrecognized_uncredited_reward_rows,
            "action_source_counts": self.action_source_counts,
            "movable_filter_checked_rows": self.movable_filter_checked_rows,
            "movable_filter_included_rows": self.movable_filter_included_rows,
            "movable_filter_filtered_rows": self.movable_filter_filtered_rows,
            "movable_filter_reward_rows": self.movable_filter_reward_rows,
            "movable_filter_reward_sum": self.movable_filter_reward_sum,
            "movable_filter_delayed_rewards": self.movable_filter_delayed_rewards,
            "movable_filter_uncredited_reward_rows": self.movable_filter_uncredited_reward_rows,
            "movable_filter_by_source": dict(sorted(self.movable_filter_by_source.items())),
            "movable_filter_by_action": dict(sorted(self.movable_filter_by_action.items())),
            "movable_filter_by_reason": dict(sorted(self.movable_filter_by_reason.items())),
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
SHORYUKEN_ACTIONS = frozenset({"shoryuken-lp", "shoryuken-mp", "shoryuken-hp"})
JUMP_ATTACK_RISK_ACTIONS = frozenset(action for action in rl.TABULAR_ACTION_NAMES if action.startswith("jump-"))
REWARD_RISK_PROFILES = ("none", "shoryuken-only", "all-attacks")
ENGINE_OUTCOME_TRAINING_MODES = ("off", "prefer-engine-action")
ENGINE_OUTCOME_MODE_ALIASES = {"prefer-demo-action": "prefer-engine-action"}
REMOVED_ENGINE_OUTCOME_MODES = ("augment", "replace-demo")
TRAINING_ACTION_SOURCES = rl.TRAINING_ACTION_SOURCES
GUARD_ACTIONS = frozenset({"guard-stand", "guard-crouch"})
MOVEMENT_SPACING_ACTIONS = frozenset({"forward", "back"})
BATCH_SAMPLING_MODES = ("uniform", "balanced")
BATCH_GROUPS = ("movement", "normal", "special")
SPECIAL_ACTION_PREFIXES = ("fireball-", "shoryuken-", "tatsu-")
DQN_TARGET_MODES = ("standard", "double")


@dataclass(frozen=True)
class ConservativeActionPenaltyConfig:
    action_penalty: float
    min_action_count: int
    negative_mean_extra: float
    exempt_actions: frozenset[str]

    @property
    def enabled(self) -> bool:
        return (
            (self.action_penalty > 0.0 and self.min_action_count > 0)
            or self.negative_mean_extra > 0.0
        )

    def as_metadata(self) -> dict[str, object]:
        return {
            "action_penalty": self.action_penalty,
            "min_action_count": self.min_action_count,
            "negative_mean_extra": self.negative_mean_extra,
            "exempt_actions": sorted(self.exempt_actions),
        }


@dataclass(frozen=True)
class DQNActionFilterConfig:
    require_movable_state_sources: frozenset[str] = field(default_factory=frozenset)

    @property
    def enabled(self) -> bool:
        return bool(self.require_movable_state_sources)

    def requires_movable_state(self, source_name: str) -> bool:
        return source_name in self.require_movable_state_sources

    def as_metadata(self) -> dict[str, object]:
        return {
            "require_movable_state_sources": sorted(self.require_movable_state_sources),
        }


@dataclass
class ConservativeActionPenaltyStats:
    adjusted_experiences: int = 0
    raw_cost_total: float = 0.0
    scaled_cost_total: float = 0.0
    per_action_events: dict[str, int] = field(default_factory=dict)
    per_action_raw_cost: dict[str, float] = field(default_factory=dict)
    low_count_actions: list[str] = field(default_factory=list)
    nonpositive_mean_actions: list[str] = field(default_factory=list)

    def as_metadata(self) -> dict[str, object]:
        return {
            "adjusted_experiences": self.adjusted_experiences,
            "raw_cost_total": self.raw_cost_total,
            "scaled_cost_total": self.scaled_cost_total,
            "per_action_events": self.per_action_events,
            "per_action_raw_cost": self.per_action_raw_cost,
            "low_count_actions": self.low_count_actions,
            "nonpositive_mean_actions": self.nonpositive_mean_actions,
        }


@dataclass(frozen=True)
class BatchSamplingConfig:
    mode: str
    ratios: dict[str, float]


@dataclass(frozen=True)
class BatchSamplingDiagnostics:
    mode: str
    ratios: dict[str, float]
    pool_counts: dict[str, int]
    target_counts: dict[str, int]

    def as_metadata(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "ratios": self.ratios,
            "pool_counts": self.pool_counts,
            "target_counts": self.target_counts,
        }


@dataclass(frozen=True)
class RewardRiskConfig:
    profile: str
    window_decisions: int
    action_windows: dict[str, int]
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
    success_require_contact: bool
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
class EngineOutcomeConfig:
    training_mode: str
    window_decisions: int
    action_windows: dict[str, int]
    stop_at_next_event: bool
    hit_bonus: float
    no_damage_cost: float
    punished_cost: float
    oversample: int
    action_oversamples: dict[str, int]


@dataclass
class EngineOutcomeStats:
    event_rows: int = 0
    included_events: int = 0
    excluded_events: int = 0
    training_experiences: int = 0
    oversample_extra_experiences: int = 0
    early_outcome_events: int = 0
    hit_events: int = 0
    no_damage_events: int = 0
    punished_events: int = 0
    trade_events: int = 0
    claimed_hp_events: int = 0
    opp_hp_sum: int = 0
    self_hp_sum: int = 0
    claimed_opp_hp_sum: int = 0
    claimed_self_hp_sum: int = 0
    base_reward_sum: float = 0.0
    hit_bonus_total: float = 0.0
    no_damage_cost_total: float = 0.0
    punished_cost_total: float = 0.0
    scaled_reward_sum: float = 0.0
    training_scaled_reward_sum: float = 0.0

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
            "training_experiences": self.training_experiences,
            "oversample_extra_experiences": self.oversample_extra_experiences,
            "early_outcome_events": self.early_outcome_events,
            "hit_events": self.hit_events,
            "no_damage_events": self.no_damage_events,
            "punished_events": self.punished_events,
            "trade_events": self.trade_events,
            "claimed_hp_events": self.claimed_hp_events,
            "opp_hp_sum": self.opp_hp_sum,
            "self_hp_sum": self.self_hp_sum,
            "claimed_opp_hp_sum": self.claimed_opp_hp_sum,
            "claimed_self_hp_sum": self.claimed_self_hp_sum,
            "base_reward_sum": self.base_reward_sum,
            "hit_bonus_total": self.hit_bonus_total,
            "no_damage_cost_total": self.no_damage_cost_total,
            "punished_cost_total": self.punished_cost_total,
            "total_bonus": self.total_bonus,
            "total_cost": self.total_cost,
            "net_adjustment": self.net_adjustment,
            "scaled_reward_sum": self.scaled_reward_sum,
            "training_scaled_reward_sum": self.training_scaled_reward_sum,
        }


def read_transition_rows(paths: list[str], limit: int) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for path in paths:
        with open(path, "r", encoding="utf-8") as stream:
            for line_no, line in enumerate(stream, start=1):
                if limit > 0 and len(rows) >= limit:
                    return rows
                line = line.strip()
                if not line:
                    continue
                try:
                    raw_row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                try:
                    replay_row = rl.learner_replay_row(raw_row)
                except ValueError as exc:
                    raise SystemExit(f"{path}:{line_no}: {exc}") from exc
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


def execution_source_name(row: dict[str, object]) -> str:
    source = int_field(row, "execution_source")
    return EXECUTION_SOURCE_NAMES.get(source, f"unknown-{source}")


def model_version_executed(row: dict[str, object]) -> int:
    return int_field(row, "model_version_executed")


def movable_action_filter_reason(row: dict[str, object]) -> str:
    routine1 = int_field(row, "obs_self_routine_1")
    if routine1 != 0:
        return f"self_routine_1:{routine1}"
    if int_field(row, "obs_self_routine_attack_state") != 0:
        return "self_attack_state"
    if int_field(row, "obs_self_contact_reaction_state") != 0:
        return "self_contact_reaction"
    return ""


def canonical_execution_source_name(raw_source: str, flag_name: str) -> str:
    normalized = raw_source.strip().lower().replace("_", "-")
    if not normalized:
        raise SystemExit(f"Invalid empty source in {flag_name}")
    try:
        source_id = int(normalized)
    except ValueError:
        source_id = -1
    if source_id >= 0:
        return EXECUTION_SOURCE_NAMES.get(source_id, f"unknown-{source_id}")
    source_name = SOURCE_NAME_ALIASES.get(normalized)
    if source_name is None:
        valid = ",".join(sorted(SOURCE_NAME_ALIASES))
        raise SystemExit(f"Unknown execution source in {flag_name}: {raw_source}; expected one of {valid} or a numeric id")
    return source_name


def parse_source_name_set(value: str, flag_name: str) -> frozenset[str]:
    sources: set[str] = set()
    if not value.strip():
        return frozenset()
    for raw_item in value.split(","):
        item = raw_item.strip()
        if not item:
            continue
        sources.add(canonical_execution_source_name(item, flag_name))
    return frozenset(sources)


def parse_source_max_rows(value: str, flag_name: str) -> dict[str, int]:
    max_rows: dict[str, int] = {}
    if not value.strip():
        return max_rows
    for raw_item in value.split(","):
        item = raw_item.strip()
        if not item:
            continue
        if "=" not in item:
            raise SystemExit(f"Invalid {flag_name} item: {item!r}; expected source=N")
        raw_source, raw_count = (part.strip() for part in item.split("=", 1))
        source = canonical_execution_source_name(raw_source, flag_name)
        try:
            count = int(raw_count)
        except ValueError as exc:
            raise SystemExit(f"Invalid max row count for {source}: {raw_count}") from exc
        max_rows[source] = max(0, count)
    return max_rows


def parse_source_ratios(value: str, flag_name: str) -> dict[str, float]:
    ratios: dict[str, float] = {}
    if not value.strip():
        return ratios
    for raw_item in value.split(","):
        item = raw_item.strip()
        if not item:
            continue
        if "=" not in item:
            raise SystemExit(f"Invalid {flag_name} item: {item!r}; expected source=ratio")
        raw_source, raw_ratio = (part.strip() for part in item.split("=", 1))
        source = canonical_execution_source_name(raw_source, flag_name)
        try:
            ratio = float(raw_ratio)
        except ValueError as exc:
            raise SystemExit(f"Invalid source ratio for {source}: {raw_ratio}") from exc
        ratios[source] = max(0.0, ratio)
    total = sum(ratios.values())
    if total <= 0.0:
        raise SystemExit(f"{flag_name} must contain at least one positive source ratio")
    return {source: ratio / total if ratio > 0.0 else 0.0 for source, ratio in ratios.items()}


def replay_source_mix_config_from_args(args: argparse.Namespace) -> ReplaySourceMixConfig:
    return ReplaySourceMixConfig(
        include_sources=parse_source_name_set(str(args.replay_source_include), "--replay-source-include"),
        exclude_sources=parse_source_name_set(str(args.replay_source_exclude), "--replay-source-exclude"),
        max_rows_by_source=parse_source_max_rows(str(args.replay_source_max_rows), "--replay-source-max-rows"),
        target_ratios=parse_source_ratios(str(args.replay_source_ratios), "--replay-source-ratios"),
    )


def dqn_action_filter_config_from_args(args: argparse.Namespace) -> DQNActionFilterConfig:
    return DQNActionFilterConfig(
        require_movable_state_sources=parse_source_name_set(
            str(args.dqn_require_movable_state_sources),
            "--dqn-require-movable-state-sources",
        ),
    )


def count_rows_by_source(rows: list[dict[str, object]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        source = execution_source_name(row)
        counts[source] = counts.get(source, 0) + 1
    return counts


def sample_rows_by_source_counts(
    rows: list[dict[str, object]],
    target_counts: dict[str, int],
    seed: int,
) -> list[dict[str, object]]:
    indices_by_source: dict[str, list[int]] = collections.defaultdict(list)
    for index, row in enumerate(rows):
        indices_by_source[execution_source_name(row)].append(index)

    rng = random.Random(seed)
    selected_indices: set[int] = set()
    for source, indices in indices_by_source.items():
        target_count = max(0, int(target_counts.get(source, len(indices))))
        if target_count >= len(indices):
            selected_indices.update(indices)
        elif target_count > 0:
            selected_indices.update(rng.sample(indices, target_count))
    return [row for index, row in enumerate(rows) if index in selected_indices]


def apply_replay_source_mix(
    rows: list[dict[str, object]],
    config: ReplaySourceMixConfig,
    seed: int,
) -> tuple[list[dict[str, object]], ReplaySourceMixStats]:
    pre_counts = count_rows_by_source(rows)
    target_counts = dict(pre_counts)

    if config.include_sources:
        target_counts = {
            source: count for source, count in target_counts.items() if source in config.include_sources
        }
    if config.exclude_sources:
        target_counts = {
            source: count for source, count in target_counts.items() if source not in config.exclude_sources
        }
    for source, max_rows in config.max_rows_by_source.items():
        target_counts[source] = min(target_counts.get(source, 0), max_rows)

    if config.target_ratios:
        positive_ratio_sources = {
            source: ratio for source, ratio in config.target_ratios.items() if ratio > 0.0
        }
        for source in positive_ratio_sources:
            if target_counts.get(source, 0) <= 0:
                raise SystemExit(f"--replay-source-ratios requested source {source!r}, but no rows are available")
        scale = min(target_counts[source] / ratio for source, ratio in positive_ratio_sources.items())
        ratio_target_counts: dict[str, int] = {}
        for source, ratio in config.target_ratios.items():
            available = target_counts.get(source, 0)
            if ratio <= 0.0 or available <= 0:
                ratio_target_counts[source] = 0
            else:
                ratio_target_counts[source] = min(available, max(1, int(math.floor(scale * ratio))))
        target_counts = {
            source: ratio_target_counts.get(source, 0)
            for source in set(target_counts) | set(config.target_ratios)
        }

    mixed_rows = sample_rows_by_source_counts(rows, target_counts, seed) if config.enabled else list(rows)
    post_counts = count_rows_by_source(mixed_rows)
    dropped_counts = {
        source: count - post_counts.get(source, 0)
        for source, count in pre_counts.items()
        if count - post_counts.get(source, 0) > 0
    }
    stats = ReplaySourceMixStats(
        mode="configured" if config.enabled else "raw",
        raw_rows=len(rows),
        mixed_rows=len(mixed_rows),
        dropped_rows=len(rows) - len(mixed_rows),
        pre_counts=pre_counts,
        post_counts=post_counts,
        dropped_counts=dropped_counts,
        target_counts={source: count for source, count in target_counts.items() if count > 0},
    )
    return mixed_rows, stats


def is_action_start(row: dict[str, object]) -> bool:
    if is_demo_row(row):
        return int_field(row, "input_action_step") == 0
    return int_field(row, "policy_executed_action_step") == 0


def is_demo_row(row: dict[str, object]) -> bool:
    return rl.is_demo_transition_row(row)


def parse_action_windows(value: str, flag_name: str) -> dict[str, int]:
    windows: dict[str, int] = {}
    if not value.strip():
        return windows
    for raw_item in value.split(","):
        item = raw_item.strip()
        if not item:
            continue
        if "=" not in item:
            raise SystemExit(f"Invalid {flag_name} item: {item!r}; expected action=N")
        raw_action, raw_window = (part.strip() for part in item.split("=", 1))
        action = rl.canonical_tabular_action_name(raw_action)
        if action is None:
            raise SystemExit(f"Unknown action in {flag_name}: {raw_action}")
        try:
            window = int(raw_window)
        except ValueError as exc:
            raise SystemExit(f"Invalid window for {action}: {raw_window}") from exc
        windows[action] = max(0, window)
    return windows


def parse_action_multipliers(value: str, flag_name: str) -> dict[str, int]:
    multipliers: dict[str, int] = {}
    if not value.strip():
        return multipliers
    for raw_item in value.split(","):
        item = raw_item.strip()
        if not item:
            continue
        if "=" not in item:
            raise SystemExit(f"Invalid {flag_name} item: {item!r}; expected action=N")
        raw_action, raw_multiplier = (part.strip() for part in item.split("=", 1))
        action = rl.canonical_tabular_action_name(raw_action)
        if action is None:
            raise SystemExit(f"Unknown action in {flag_name}: {raw_action}")
        try:
            multiplier = int(raw_multiplier)
        except ValueError as exc:
            raise SystemExit(f"Invalid multiplier for {action}: {raw_multiplier}") from exc
        multipliers[action] = max(1, multiplier)
    return multipliers


def canonical_batch_group_name(raw_group: str) -> str | None:
    normalized = raw_group.strip().lower().replace("_", "-")
    aliases = {
        "movement": "movement",
        "move": "movement",
        "guard": "movement",
        "movement-guard": "movement",
        "movement+guard": "movement",
        "normal": "normal",
        "normals": "normal",
        "normal-throw": "normal",
        "normals-throw": "normal",
        "normal+throw": "normal",
        "normals+throw": "normal",
        "special": "special",
        "specials": "special",
    }
    return aliases.get(normalized)


def parse_batch_ratios(value: str, flag_name: str) -> dict[str, float]:
    ratios: dict[str, float] = {group: 0.0 for group in BATCH_GROUPS}
    if not value.strip():
        return ratios
    for raw_item in value.split(","):
        item = raw_item.strip()
        if not item:
            continue
        if "=" not in item:
            raise SystemExit(f"Invalid {flag_name} item: {item!r}; expected group=ratio")
        raw_group, raw_ratio = (part.strip() for part in item.split("=", 1))
        group = canonical_batch_group_name(raw_group)
        if group is None:
            raise SystemExit(f"Unknown batch group in {flag_name}: {raw_group}")
        try:
            ratio = float(raw_ratio)
        except ValueError as exc:
            raise SystemExit(f"Invalid ratio for {group}: {raw_ratio}") from exc
        ratios[group] = max(0.0, ratio)
    total = sum(ratios.values())
    if total <= 0.0:
        raise SystemExit(f"{flag_name} must contain at least one positive ratio")
    return {group: ratios[group] / total for group in BATCH_GROUPS}


def batch_sampling_config_from_args(args: argparse.Namespace) -> BatchSamplingConfig:
    mode = str(args.batch_sampling)
    if mode not in BATCH_SAMPLING_MODES:
        raise SystemExit(f"unknown --batch-sampling {mode!r}; expected one of {','.join(BATCH_SAMPLING_MODES)}")
    ratios = parse_batch_ratios(str(args.balanced_batch_ratios), "--balanced-batch-ratios")
    return BatchSamplingConfig(mode=mode, ratios=ratios)


def parse_action_name_set(value: str, flag_name: str) -> frozenset[str]:
    actions: set[str] = set()
    if not value.strip():
        return frozenset()
    invalid: list[str] = []
    for raw_item in value.split(","):
        raw_action = raw_item.strip()
        if not raw_action:
            continue
        action = rl.canonical_tabular_action_name(raw_action)
        if action is None:
            invalid.append(raw_action)
        else:
            actions.add(action)
    if invalid:
        raise SystemExit(f"Unknown action in {flag_name}: {','.join(invalid)}")
    return frozenset(actions)


def conservative_action_penalty_config_from_args(args: argparse.Namespace) -> ConservativeActionPenaltyConfig:
    return ConservativeActionPenaltyConfig(
        action_penalty=max(0.0, float(args.conservative_action_penalty)),
        min_action_count=max(0, int(args.conservative_min_action_count)),
        negative_mean_extra=max(0.0, float(args.conservative_negative_mean_extra)),
        exempt_actions=parse_action_name_set(str(args.conservative_exempt_actions), "--conservative-exempt-actions"),
    )


def action_batch_group(action_name: str) -> str:
    if action_name in NON_ATTACK_ACTIONS:
        return "movement"
    if action_name.startswith(SPECIAL_ACTION_PREFIXES):
        return "special"
    return "normal"


def build_batch_pools(
    experiences: list[Experience],
    actions: tuple[str, ...],
) -> dict[str, list[Experience]]:
    pools: dict[str, list[Experience]] = {group: [] for group in BATCH_GROUPS}
    for exp in experiences:
        if 0 <= exp.action_index < len(actions):
            pools[action_batch_group(actions[exp.action_index])].append(exp)
    return pools


def balanced_target_counts(batch_size: int, ratios: dict[str, float]) -> dict[str, int]:
    raw_counts = {group: max(0.0, ratios.get(group, 0.0)) * batch_size for group in BATCH_GROUPS}
    counts = {group: int(math.floor(raw_counts[group])) for group in BATCH_GROUPS}
    remaining = max(0, batch_size - sum(counts.values()))
    remainders = sorted(
        ((raw_counts[group] - counts[group], group) for group in BATCH_GROUPS),
        key=lambda item: (item[0], item[1]),
        reverse=True,
    )
    for index in range(remaining):
        counts[remainders[index % len(remainders)][1]] += 1
    return counts


def batch_sampling_diagnostics(
    experiences: list[Experience],
    actions: tuple[str, ...],
    batch_size: int,
    config: BatchSamplingConfig,
) -> BatchSamplingDiagnostics:
    pools = build_batch_pools(experiences, actions)
    return BatchSamplingDiagnostics(
        mode=config.mode,
        ratios=dict(config.ratios),
        pool_counts={group: len(pools[group]) for group in BATCH_GROUPS},
        target_counts=balanced_target_counts(batch_size, config.ratios) if config.mode == "balanced" else {},
    )


def sample_training_batch(
    experiences: list[Experience],
    pools: dict[str, list[Experience]],
    target_counts: dict[str, int],
    batch_size: int,
    rng: random.Random,
    config: BatchSamplingConfig,
) -> list[Experience]:
    if config.mode == "uniform":
        return rng.choices(experiences, k=batch_size)

    batch: list[Experience] = []
    fallback_pool = experiences
    for group in BATCH_GROUPS:
        count = max(0, int(target_counts.get(group, 0)))
        if count <= 0:
            continue
        pool = pools.get(group) or fallback_pool
        batch.extend(rng.choices(pool, k=count))
    if len(batch) < batch_size:
        batch.extend(rng.choices(fallback_pool, k=batch_size - len(batch)))
    elif len(batch) > batch_size:
        batch = batch[:batch_size]
    rng.shuffle(batch)
    return batch


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
    apply_shoryuken_cost = action_name in SHORYUKEN_ACTIONS and config.profile in {"shoryuken-only", "all-attacks"}
    apply_jump_attack_cost = config.profile == "all-attacks" and action_name in JUMP_ATTACK_RISK_ACTIONS
    if not apply_attack_cost and not apply_shoryuken_cost and not apply_jump_attack_cost:
        return 0.0

    window_length = config.action_windows.get(action_name, config.window_decisions)
    window_end = min(len(episode_rows), row_index + max(0, window_length) + 1)
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
    guard_contact = any(int_field(lookahead_row, "obs_self_contact_reaction_state") != 0 for lookahead_row in lookahead)
    clean_guard_window = self_damage == 0
    confirmed_guard_window = clean_guard_window and (guard_contact or not config.success_require_contact)
    adjustment = 0.0

    if config.success_bonus > 0.0 and opponent_attacking and in_threat_range and confirmed_guard_window:
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
    source_stats: SourceReplayDiagnostics | None = None,
) -> bool:
    if exp_index is None:
        return False
    experiences[exp_index].reward += reward
    exp = experiences[exp_index]
    action_name = actions[exp.action_index]
    action_rewards[action_name] += reward
    if source_stats is not None:
        source_stats.add_reward(exp.source_name, action_name, reward)
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


def engine_outcome_window_for_action(action_name: str, config: EngineOutcomeConfig) -> int:
    return max(0, int(config.action_windows.get(action_name, config.window_decisions)))


def engine_outcome_oversample_for_action(action_name: str, config: EngineOutcomeConfig) -> int:
    return max(1, int(config.action_oversamples.get(action_name, config.oversample)))


def add_engine_outcome_experience(
    episode_rows: list[dict[str, object]],
    row_index: int,
    actions: tuple[str, ...],
    action_to_index: dict[str, int],
    reward_scale: float,
    config: EngineOutcomeConfig,
    stats: EngineOutcomeStats,
    experiences: list[Experience],
    action_counts: dict[str, int],
    action_rewards: dict[str, float],
    source_stats: SourceReplayDiagnostics,
    source_name: str,
    model_version: int,
) -> bool:
    if config.training_mode == "off":
        return False
    row = episode_rows[row_index]
    if not is_demo_row(row) or not rl.engine_outcome_present(row):
        return False

    stats.event_rows += 1
    action_name = rl.engine_outcome_action_name(row)
    if action_name is None or action_name not in action_to_index:
        stats.excluded_events += 1
        return False

    window_end = min(len(episode_rows), row_index + engine_outcome_window_for_action(action_name, config) + 1)
    if config.stop_at_next_event:
        for next_index in range(row_index + 1, window_end):
            if rl.engine_outcome_present(episode_rows[next_index]):
                window_end = next_index
                break
    for next_index in range(row_index, window_end):
        window_row = episode_rows[next_index]
        if int_field(window_row, "delta_opp_hp") > 0 or int_field(window_row, "delta_self_hp") > 0:
            window_end = next_index + 1
            stats.early_outcome_events += 1
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

    if opponent_damage > 0 or self_damage > 0:
        stats.claimed_hp_events += 1
        stats.claimed_opp_hp_sum += opponent_damage
        stats.claimed_self_hp_sum += self_damage
        for window_row in window_rows:
            if int_field(window_row, "delta_opp_hp") > 0:
                window_row["delta_opp_hp"] = 0
            if int_field(window_row, "delta_self_hp") > 0:
                window_row["delta_self_hp"] = 0

    reward = (base_reward + adjustment) * reward_scale
    next_row = window_rows[-1]
    done = any(bool(window_row.get("done", False)) for window_row in window_rows)
    multiplier = engine_outcome_oversample_for_action(action_name, config)
    state = rl.dqn_feature_vector(row)
    next_state = rl.dqn_feature_vector(next_row)
    action_index = action_to_index[action_name]
    for _ in range(multiplier):
        experiences.append(
            Experience(
                state=list(state),
                action_index=action_index,
                reward=reward,
                next_state=list(next_state),
                done=done,
                source_name=source_name,
                model_version=model_version,
            )
        )
    stats.included_events += 1
    stats.training_experiences += multiplier
    stats.oversample_extra_experiences += max(0, multiplier - 1)
    stats.opp_hp_sum += opponent_damage
    stats.self_hp_sum += self_damage
    stats.base_reward_sum += base_reward
    stats.scaled_reward_sum += reward
    stats.training_scaled_reward_sum += reward * multiplier
    action_counts[action_name] += multiplier
    action_rewards[action_name] += reward * multiplier
    source_stats.add_experience(source_name, model_version, action_name, reward, multiplier)
    return True


def build_experiences(
    rows: list[dict[str, object]],
    actions: tuple[str, ...],
    reward_scale: float,
    training_action_source: str,
    reward_risk_config: RewardRiskConfig,
    reward_guard_config: RewardGuardConfig,
    reward_spacing_config: RewardSpacingConfig,
    reward_position_config: RewardPositionConfig,
    engine_outcome_config: EngineOutcomeConfig,
    action_filter_config: DQNActionFilterConfig,
) -> tuple[
    list[Experience],
    dict[str, int],
    dict[str, float],
    dict[str, int],
    dict[str, float],
    BuildDiagnostics,
    SourceReplayDiagnostics,
    RewardRiskStats,
    RewardGuardStats,
    RewardSpacingStats,
    RewardPositionStats,
    EngineOutcomeStats,
]:
    action_to_index = {action: index for index, action in enumerate(actions)}
    by_episode: dict[tuple[int, int], list[dict[str, object]]] = collections.defaultdict(list)
    for row in rows:
        by_episode[episode_key(row)].append(dict(row))

    experiences: list[Experience] = []
    action_counts = {action: 0 for action in actions}
    action_rewards = {action: 0.0 for action in actions}
    observed_action_counts = {action: 0 for action in rl.TABULAR_ACTION_NAMES}
    observed_action_rewards = {action: 0.0 for action in rl.TABULAR_ACTION_NAMES}
    build_stats = BuildDiagnostics()
    source_stats = SourceReplayDiagnostics()
    risk_stats = RewardRiskStats()
    guard_stats = RewardGuardStats()
    spacing_stats = RewardSpacingStats()
    position_stats = RewardPositionStats()
    engine_outcome_stats = EngineOutcomeStats()

    for episode_rows in by_episode.values():
        episode_rows.sort(key=row_order_key)
        last_exp_index: int | None = None
        for index, row in enumerate(episode_rows):
            source_name = execution_source_name(row)
            model_version = model_version_executed(row)
            source_stats.add_row(source_name, model_version)
            force_input_after_engine_outcome_excluded = False
            if (
                engine_outcome_config.training_mode == "prefer-engine-action"
                and is_demo_row(row)
                and rl.engine_outcome_present(row)
            ):
                engine_outcome_added = add_engine_outcome_experience(
                    episode_rows,
                    index,
                    actions,
                    action_to_index,
                    reward_scale,
                    engine_outcome_config,
                    engine_outcome_stats,
                    experiences,
                    action_counts,
                    action_rewards,
                    source_stats,
                    source_name,
                    model_version,
                )
                if engine_outcome_added:
                    set_experience_next_state(experiences, last_exp_index, row, bool(row.get("done", False)))
                    last_exp_index = None
                    continue
                force_input_after_engine_outcome_excluded = True
                build_stats.engine_outcome_input_fallback_rows += 1

            action_selection = rl.select_training_action(
                row,
                "input" if force_input_after_engine_outcome_excluded else training_action_source,
            )
            action_name = action_selection.name
            action_start = action_selection.step == 0
            build_stats.action_source_counts[action_selection.source] = (
                build_stats.action_source_counts.get(action_selection.source, 0) + 1
            )
            base_reward = rl.tabular_training_reward(row) * reward_scale
            if (
                action_start
                and action_name is not None
                and action_filter_config.requires_movable_state(source_name)
            ):
                build_stats.movable_filter_checked_rows += 1
                filter_reason = movable_action_filter_reason(row)
                if filter_reason:
                    set_experience_next_state(experiences, last_exp_index, row, bool(row.get("done", False)))
                    build_stats.movable_filter_filtered_rows += 1
                    build_stats.movable_filter_by_source[source_name] = (
                        build_stats.movable_filter_by_source.get(source_name, 0) + 1
                    )
                    build_stats.movable_filter_by_action[action_name] = (
                        build_stats.movable_filter_by_action.get(action_name, 0) + 1
                    )
                    build_stats.movable_filter_by_reason[filter_reason] = (
                        build_stats.movable_filter_by_reason.get(filter_reason, 0) + 1
                    )
                    if base_reward != 0.0:
                        build_stats.movable_filter_reward_rows += 1
                        build_stats.movable_filter_reward_sum += base_reward
                        if add_delayed_reward(
                            experiences,
                            last_exp_index,
                            base_reward,
                            actions,
                            action_rewards,
                            source_stats,
                        ):
                            build_stats.movable_filter_delayed_rewards += 1
                        else:
                            build_stats.movable_filter_uncredited_reward_rows += 1
                    last_exp_index = None
                    continue
                build_stats.movable_filter_included_rows += 1
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
            reward = base_reward + (
                -risk_cost + guard_adjustment + spacing_adjustment + position_adjustment
            ) * reward_scale
            if action_name is None:
                if reward != 0.0:
                    if add_delayed_reward(experiences, last_exp_index, reward, actions, action_rewards, source_stats):
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
                    if add_delayed_reward(experiences, last_exp_index, reward, actions, action_rewards, source_stats):
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
                source_name=source_name,
                model_version=model_version,
            )
            experiences.append(exp)
            last_exp_index = len(experiences) - 1
            build_stats.included_action_rows += 1
            action_counts[action_name] += 1
            action_rewards[action_name] += reward
            source_stats.add_experience(source_name, model_version, action_name, reward)

        if episode_rows:
            set_experience_next_state(experiences, last_exp_index, episode_rows[-1], True)

    return (
        experiences,
        action_counts,
        action_rewards,
        observed_action_counts,
        observed_action_rewards,
        build_stats,
        source_stats,
        risk_stats,
        guard_stats,
        spacing_stats,
        position_stats,
        engine_outcome_stats,
    )


def apply_conservative_action_penalty(
    experiences: list[Experience],
    actions: tuple[str, ...],
    action_counts: dict[str, int],
    action_rewards: dict[str, float],
    observed_action_counts: dict[str, int],
    observed_action_rewards: dict[str, float],
    reward_scale: float,
    config: ConservativeActionPenaltyConfig,
    source_stats: SourceReplayDiagnostics | None = None,
) -> ConservativeActionPenaltyStats:
    stats = ConservativeActionPenaltyStats()
    if not config.enabled:
        return stats

    raw_penalty_by_index: dict[int, float] = {}
    low_count_actions: list[str] = []
    nonpositive_mean_actions: list[str] = []
    for action_index, action in enumerate(actions):
        if action in config.exempt_actions:
            continue
        count = int(action_counts.get(action, 0))
        if count <= 0:
            continue

        observed_count = int(observed_action_counts.get(action, 0))
        if observed_count > 0:
            mean_reward = float(observed_action_rewards.get(action, 0.0)) / observed_count
        else:
            mean_reward = float(action_rewards.get(action, 0.0)) / count

        raw_penalty = 0.0
        if config.action_penalty > 0.0 and config.min_action_count > 0 and count < config.min_action_count:
            raw_penalty += config.action_penalty
            low_count_actions.append(action)
        if config.negative_mean_extra > 0.0 and mean_reward <= 0.0:
            raw_penalty += config.negative_mean_extra
            nonpositive_mean_actions.append(action)
        if raw_penalty > 0.0:
            raw_penalty_by_index[action_index] = raw_penalty

    if not raw_penalty_by_index:
        return stats

    stats.low_count_actions = low_count_actions
    stats.nonpositive_mean_actions = nonpositive_mean_actions
    for exp in experiences:
        raw_penalty = raw_penalty_by_index.get(exp.action_index, 0.0)
        if raw_penalty <= 0.0:
            continue
        scaled_penalty = raw_penalty * reward_scale
        exp.reward -= scaled_penalty
        action = actions[exp.action_index]
        action_rewards[action] -= scaled_penalty
        if source_stats is not None:
            source_stats.add_reward(exp.source_name, action, -scaled_penalty)
        stats.adjusted_experiences += 1
        stats.raw_cost_total += raw_penalty
        stats.scaled_cost_total += scaled_penalty
        stats.per_action_events[action] = stats.per_action_events.get(action, 0) + 1
        stats.per_action_raw_cost[action] = stats.per_action_raw_cost.get(action, 0.0) + raw_penalty
    return stats


def reward_risk_config_from_args(args: argparse.Namespace) -> RewardRiskConfig:
    return RewardRiskConfig(
        profile=str(args.reward_risk_profile),
        window_decisions=max(0, int(args.reward_risk_window_decisions)),
        action_windows=parse_action_windows(str(args.reward_risk_action_windows), "--reward-risk-action-windows"),
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
        success_require_contact=bool(args.reward_guard_success_require_contact),
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


def resolved_engine_outcome_arg(args: argparse.Namespace, name: str, default: object) -> object:
    new_value = getattr(args, f"engine_outcome_{name}")
    old_value = getattr(args, f"deprecated_demo_attribution_{name}")
    if new_value is not None and old_value is not None:
        raise SystemExit(
            f"Use only one of --engine-outcome-{name.replace('_', '-')} "
            f"or deprecated --demo-attribution-{name.replace('_', '-')}"
        )
    if old_value is not None:
        print(
            f"warning: --demo-attribution-{name.replace('_', '-')} is deprecated; "
            f"use --engine-outcome-{name.replace('_', '-')}",
            file=sys.stderr,
        )
        return old_value
    if new_value is not None:
        return new_value
    return default


def engine_outcome_config_from_args(args: argparse.Namespace) -> EngineOutcomeConfig:
    training_mode = str(resolved_engine_outcome_arg(args, "training_mode", "off"))
    training_mode = ENGINE_OUTCOME_MODE_ALIASES.get(training_mode, training_mode)
    if training_mode in REMOVED_ENGINE_OUTCOME_MODES:
        raise SystemExit(
            f"--engine-outcome-training-mode {training_mode!r} was removed for schema v3; "
            "use 'prefer-engine-action' so engine-labeled rows replace only matching input rows"
        )
    if training_mode not in ENGINE_OUTCOME_TRAINING_MODES:
        raise SystemExit(
            "unknown --engine-outcome-training-mode "
            f"{training_mode!r}; expected one of {','.join(ENGINE_OUTCOME_TRAINING_MODES)}"
        )

    action_windows_text = str(resolved_engine_outcome_arg(args, "action_windows", ""))
    return EngineOutcomeConfig(
        training_mode=training_mode,
        window_decisions=max(0, int(resolved_engine_outcome_arg(args, "window_decisions", 10))),
        action_windows=parse_action_windows(action_windows_text, "--engine-outcome-action-windows"),
        stop_at_next_event=bool(resolved_engine_outcome_arg(args, "stop_at_next_event", False)),
        hit_bonus=max(0.0, float(resolved_engine_outcome_arg(args, "hit_bonus", 0.0))),
        no_damage_cost=max(0.0, float(resolved_engine_outcome_arg(args, "no_damage_cost", 0.0))),
        punished_cost=max(0.0, float(resolved_engine_outcome_arg(args, "punished_cost", 0.0))),
        oversample=max(1, int(args.engine_outcome_oversample)),
        action_oversamples=parse_action_multipliers(
            str(args.engine_outcome_action_oversamples),
            "--engine-outcome-action-oversamples",
        ),
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
    batch_sampling_config: BatchSamplingConfig,
    target_mode: str,
) -> tuple[list[dict[str, object]], dict[str, float]]:
    rng = random.Random(seed)
    layers = init_network(len(rl.DQN_FEATURE_NAMES), hidden_sizes, len(actions), rng)
    target_layers = copy.deepcopy(layers)
    batch_pools = build_batch_pools(experiences, actions)
    batch_target_counts = (
        balanced_target_counts(batch_size, batch_sampling_config.ratios)
        if batch_sampling_config.mode == "balanced"
        else {}
    )
    last_loss = 0.0
    avg_loss = 0.0

    for step in range(1, steps + 1):
        batch = sample_training_batch(
            experiences,
            batch_pools,
            batch_target_counts,
            batch_size,
            rng,
            batch_sampling_config,
        )
        grads = zero_grads(layers)
        loss = 0.0
        for exp in batch:
            values, activations, pre_activations = forward(layers, exp.state)
            next_values, _, _ = forward(target_layers, exp.next_state)
            if exp.done:
                target = exp.reward
            elif target_mode == "double":
                online_next_values, _, _ = forward(layers, exp.next_state)
                next_count = min(len(actions), len(online_next_values), len(next_values))
                best_next_index = max(
                    range(next_count),
                    key=lambda index: (online_next_values[index], actions[index]),
                )
                target = exp.reward + gamma * next_values[best_next_index]
            else:
                target = exp.reward + gamma * max(next_values)
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

    batch_diag = BatchSamplingDiagnostics(
        mode=batch_sampling_config.mode,
        ratios=dict(batch_sampling_config.ratios),
        pool_counts={group: len(batch_pools[group]) for group in BATCH_GROUPS},
        target_counts=dict(batch_target_counts),
    )
    return layers, {"last_loss": last_loss, "avg_loss": avg_loss, "batch_sampling": batch_diag.as_metadata()}


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
    actions: list[str] = []
    invalid: list[str] = []
    for raw_item in value.split(","):
        raw_action = raw_item.strip()
        if not raw_action:
            continue
        action = rl.canonical_tabular_action_name(raw_action)
        if action is None:
            invalid.append(raw_action)
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


def format_source_action_scores(
    source_stats: SourceReplayDiagnostics,
    actions: tuple[str, ...],
    source_limit: int,
    action_limit: int,
) -> str:
    source_count_limit = max(1, source_limit)
    ordered_sources = sorted(
        source_stats.experience_counts.items(),
        key=lambda item: (item[1], item[0]),
        reverse=True,
    )
    parts: list[str] = []
    for source_name, count in ordered_sources[:source_count_limit]:
        if count <= 0:
            continue
        counts = source_stats.experience_action_counts.get(source_name, {})
        rewards = source_stats.experience_action_reward_sum.get(source_name, {})
        parts.append(f"{source_name}{{{format_action_scores(counts, rewards, actions, action_limit)}}}")
    if len(ordered_sources) > source_count_limit:
        remaining = sum(count for _, count in ordered_sources[source_count_limit:])
        if remaining > 0:
            parts.append(f"...+{remaining}")
    return " ".join(parts) if parts else "none"


def format_source_model_versions(
    counts_by_source: dict[str, dict[str, int]],
    total_counts_by_source: dict[str, int],
    source_limit: int,
    version_limit: int,
) -> str:
    source_count_limit = max(1, source_limit)
    ordered_sources = sorted(
        total_counts_by_source.items(),
        key=lambda item: (item[1], item[0]),
        reverse=True,
    )
    parts: list[str] = []
    for source_name, count in ordered_sources[:source_count_limit]:
        if count <= 0:
            continue
        version_counts = counts_by_source.get(source_name, {})
        parts.append(f"{source_name}{{{format_counts(version_counts, count, version_limit)}}}")
    if len(ordered_sources) > source_count_limit:
        remaining = sum(count for _, count in ordered_sources[source_count_limit:])
        if remaining > 0:
            parts.append(f"...+{remaining}")
    return " ".join(parts) if parts else "none"


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
    parser.add_argument(
        "--replay-source-include",
        default="",
        help=(
            "Optional comma-separated execution sources to keep before DQN replay building, "
            "e.g. remote,human-demo,cpu-demo. Empty keeps every source unless other source-mix flags drop it"
        ),
    )
    parser.add_argument(
        "--replay-source-exclude",
        default="",
        help=(
            "Optional comma-separated execution sources to drop before DQN replay building, "
            "e.g. repeated-last-action,neutral-fallback"
        ),
    )
    parser.add_argument(
        "--replay-source-max-rows",
        default="",
        help=(
            "Optional comma-separated per-source row caps applied before DQN replay building, "
            "e.g. remote=10000,human-demo=4000,cpu-demo=4000"
        ),
    )
    parser.add_argument(
        "--replay-source-ratios",
        default="",
        help=(
            "Optional comma-separated target source ratios applied by deterministic undersampling, "
            "e.g. remote=0.7,human-demo=0.3. When set, sources not listed are dropped"
        ),
    )
    parser.add_argument(
        "--dqn-require-movable-state-sources",
        default="",
        help=(
            "Comma-separated execution sources whose action-start rows must be in a movable self state "
            "before they can create DQN experiences, e.g. remote. Filtered rows can still delay-credit "
            "their HP delta to the previous valid experience"
        ),
    )
    parser.add_argument("--steps", type=int, default=2000, help="Gradient steps")
    parser.add_argument("--batch-size", type=int, default=64, help="Replay batch size")
    parser.add_argument(
        "--batch-sampling",
        choices=BATCH_SAMPLING_MODES,
        default="uniform",
        help="Replay batch sampler: uniform keeps raw replay sampling, balanced samples by action family ratios",
    )
    parser.add_argument(
        "--balanced-batch-ratios",
        default="movement=0.4,normal=0.3,special=0.3",
        help=(
            "Comma-separated group ratios used when --batch-sampling balanced, e.g. "
            "movement=0.4,normal=0.3,special=0.3; movement includes forward/back/guard, "
            "normal includes normals and throw, special includes fireball/shoryuken/tatsu"
        ),
    )
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
        "--conservative-action-penalty",
        type=float,
        default=0.0,
        help=(
            "Positive raw reward cost subtracted from each replay experience whose action has fewer than "
            "--conservative-min-action-count training examples; 0 disables this low-support cost"
        ),
    )
    parser.add_argument(
        "--conservative-min-action-count",
        type=int,
        default=0,
        help="Minimum post-build training examples required before --conservative-action-penalty is skipped",
    )
    parser.add_argument(
        "--conservative-negative-mean-extra",
        type=float,
        default=0.0,
        help=(
            "Additional positive raw reward cost subtracted from each replay experience whose action has "
            "non-positive observed mean reward; 0 disables this cost"
        ),
    )
    parser.add_argument(
        "--conservative-exempt-actions",
        default="",
        help="Comma-separated action names exempt from conservative action penalties",
    )
    parser.add_argument(
        "--reward-risk-profile",
        choices=REWARD_RISK_PROFILES,
        default="none",
        help=(
            "Optional no-damage action cost profile: none=HP-delta baseline, "
            "shoryuken-only=only Shoryuken variant extra costs, all-attacks=generic attack costs plus Shoryuken extra costs"
        ),
    )
    parser.add_argument(
        "--reward-risk-window-decisions",
        type=int,
        default=10,
        help="Lookahead decisions used to decide whether an action produced no opponent HP damage",
    )
    parser.add_argument(
        "--reward-risk-action-windows",
        default="",
        help="Comma-separated overrides for risk window by action (e.g., fireball-lp=30)",
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
        help="Positive raw reward cost subtracted from no-damage Shoryuken variants in shoryuken-only/all-attacks profiles",
    )
    parser.add_argument(
        "--reward-shoryuken-punished-extra-cost",
        type=float,
        default=4.0,
        help="Additional positive raw reward cost when a no-damage Shoryuken variant is followed by self HP damage",
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
        "--reward-guard-success-require-contact",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Require obs_self_contact_reaction_state inside the guard-success window before awarding "
            "the guard success bonus"
        ),
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
        "--engine-outcome-training-mode",
        default=None,
        help=(
            "Optional engine-observed move outcome training: off=use normal selected action rows, "
            "prefer-engine-action=use engine-labeled rows when present and keep input rows for other demo rows"
        ),
    )
    parser.add_argument(
        "--demo-attribution-training-mode",
        dest="deprecated_demo_attribution_training_mode",
        default=None,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--engine-outcome-window-decisions",
        type=int,
        default=None,
        help=(
            "Maximum lookahead decisions used to credit delayed HP deltas to engine-labeled move events; "
            "the effective window stops early at the first self/opponent HP delta"
        ),
    )
    parser.add_argument(
        "--demo-attribution-window-decisions",
        dest="deprecated_demo_attribution_window_decisions",
        type=int,
        default=None,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--engine-outcome-action-windows",
        default=None,
        help=(
            "Optional comma-separated per-action delayed-credit windows, e.g. "
            "fireball-lp=15,throw=8; omitted actions use --engine-outcome-window-decisions; "
            "all windows still stop early at the first self/opponent HP delta"
        ),
    )
    parser.add_argument(
        "--demo-attribution-action-windows",
        dest="deprecated_demo_attribution_action_windows",
        default=None,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--engine-outcome-stop-at-next-event",
        action="store_true",
        default=None,
        help="Stop an engine-outcome delayed-credit window at the next engine-labeled move event in the same episode",
    )
    parser.add_argument(
        "--demo-attribution-stop-at-next-event",
        dest="deprecated_demo_attribution_stop_at_next_event",
        action="store_true",
        default=None,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--engine-outcome-hit-bonus",
        type=float,
        default=None,
        help="Additional positive raw reward added when an engine-labeled move causes opponent HP damage in its window",
    )
    parser.add_argument(
        "--demo-attribution-hit-bonus",
        dest="deprecated_demo_attribution_hit_bonus",
        type=float,
        default=None,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--engine-outcome-no-damage-cost",
        type=float,
        default=None,
        help="Positive raw reward cost subtracted when an engine-labeled move causes no opponent HP damage in its window",
    )
    parser.add_argument(
        "--demo-attribution-no-damage-cost",
        dest="deprecated_demo_attribution_no_damage_cost",
        type=float,
        default=None,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--engine-outcome-punished-cost",
        type=float,
        default=None,
        help="Positive raw reward cost subtracted when an engine-labeled move window includes self HP damage",
    )
    parser.add_argument(
        "--demo-attribution-punished-cost",
        dest="deprecated_demo_attribution_punished_cost",
        type=float,
        default=None,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--engine-outcome-oversample",
        type=int,
        default=1,
        help=(
            "Total replay copies to emit for each included engine-outcome experience; "
            "1 keeps the baseline one-copy behavior"
        ),
    )
    parser.add_argument(
        "--engine-outcome-action-oversamples",
        default="",
        help=(
            "Optional comma-separated per-action engine-outcome replay copy counts, e.g. "
            "fireball-lp=10,shoryuken-hp=6; omitted actions use --engine-outcome-oversample"
        ),
    )
    parser.add_argument(
        "--training-action-source",
        choices=TRAINING_ACTION_SOURCES,
        default="auto",
        help=(
            "Action label source for normal DQN replay rows. auto uses engine/input labels for "
            "schema-v3 demo rows and policy labels for schema-v3 remote rows"
        ),
    )
    parser.add_argument("--target-sync-steps", type=int, default=200, help="Steps between target-network syncs")
    parser.add_argument(
        "--dqn-target-mode",
        choices=DQN_TARGET_MODES,
        default="standard",
        help="DQN bootstrapping target: standard uses max target-network value; double selects with online network and evaluates with target network",
    )
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
    rows_read_before_source_mix = len(rows)
    replay_source_mix_config = replay_source_mix_config_from_args(args)
    rows, replay_source_mix_stats = apply_replay_source_mix(
        rows,
        replay_source_mix_config,
        int(args.seed),
    )
    dqn_action_filter_config = dqn_action_filter_config_from_args(args)
    reward_risk_config = reward_risk_config_from_args(args)
    reward_guard_config = reward_guard_config_from_args(args)
    reward_spacing_config = reward_spacing_config_from_args(args)
    reward_position_config = reward_position_config_from_args(args)
    engine_outcome_config = engine_outcome_config_from_args(args)
    conservative_action_penalty_config = conservative_action_penalty_config_from_args(args)
    batch_sampling_config = batch_sampling_config_from_args(args)
    (
        experiences,
        action_counts,
        action_rewards,
        observed_action_counts,
        observed_action_rewards,
        build_stats,
        source_stats,
        reward_risk_stats,
        reward_guard_stats,
        reward_spacing_stats,
        reward_position_stats,
        engine_outcome_stats,
    ) = build_experiences(
        rows,
        actions,
        args.reward_scale,
        str(args.training_action_source),
        reward_risk_config,
        reward_guard_config,
        reward_spacing_config,
        reward_position_config,
        engine_outcome_config,
        dqn_action_filter_config,
    )
    if not experiences:
        raise SystemExit("No DQN experiences built from transition logs")
    conservative_action_penalty_stats = apply_conservative_action_penalty(
        experiences,
        actions,
        action_counts,
        action_rewards,
        observed_action_counts,
        observed_action_rewards,
        args.reward_scale,
        conservative_action_penalty_config,
        source_stats,
    )

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
        batch_sampling_config,
        args.dqn_target_mode,
    )
    batch_sampling_diag = batch_sampling_diagnostics(
        experiences,
        actions,
        max(1, args.batch_size),
        batch_sampling_config,
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
    if engine_outcome_config.training_mode != "off":
        reward_sources.append("engine-outcome")
    if conservative_action_penalty_stats.adjusted_experiences > 0:
        reward_sources.append("conservative-action-penalty")
    reward_source = "+".join(reward_sources)
    metadata = {
        "transition_logs": args.transition_logs,
        "rows_read": len(rows),
        "rows_read_before_episode_drop": rows_read_before_episode_drop,
        "drop_initial_episodes_per_run": max(0, int(args.drop_initial_episodes_per_run)),
        "dropped_initial_episode_rows": dropped_initial_episode_rows,
        "dropped_initial_episodes": dropped_initial_episodes,
        "rows_read_before_source_mix": rows_read_before_source_mix,
        "replay_source_mix_config": replay_source_mix_config.as_metadata(),
        "replay_source_mix_stats": replay_source_mix_stats.as_metadata(),
        "dqn_action_filter_config": dqn_action_filter_config.as_metadata(),
        "experiences": len(experiences),
        "actions_subset": list(actions),
        "actions_subset_size": len(actions),
        "build_diagnostics": build_stats.as_metadata(),
        "source_replay_diagnostics": source_stats.as_metadata(),
        "delayed_rewards": build_stats.unrecognized_delayed_rewards + build_stats.macro_continuation_delayed_rewards,
        "reward_source": reward_source,
        "reward_scale": args.reward_scale,
        "reward_scale_applied_after_risk_cost": True,
        "reward_scale_applied_after_raw_adjustments": True,
        "conservative_action_penalty_config": conservative_action_penalty_config.as_metadata(),
        "conservative_action_penalty_stats": conservative_action_penalty_stats.as_metadata(),
        "training_action_source": str(args.training_action_source),
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
        "reward_guard_success_require_contact": reward_guard_config.success_require_contact,
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
        "engine_outcome_training_mode": engine_outcome_config.training_mode,
        "engine_outcome_window_decisions": engine_outcome_config.window_decisions,
        "engine_outcome_action_windows": engine_outcome_config.action_windows,
        "engine_outcome_stop_at_next_event": engine_outcome_config.stop_at_next_event,
        "engine_outcome_hit_bonus": engine_outcome_config.hit_bonus,
        "engine_outcome_no_damage_cost": engine_outcome_config.no_damage_cost,
        "engine_outcome_punished_cost": engine_outcome_config.punished_cost,
        "engine_outcome_oversample": engine_outcome_config.oversample,
        "engine_outcome_action_oversamples": engine_outcome_config.action_oversamples,
        "engine_outcome_stats": engine_outcome_stats.as_metadata(),
        "steps": max(1, args.steps),
        "batch_size": max(1, args.batch_size),
        "batch_sampling": batch_sampling_diag.as_metadata(),
        "gamma": min(0.999, max(0.0, args.gamma)),
        "learning_rate": max(1e-8, args.learning_rate),
        "target_sync_steps": max(1, args.target_sync_steps),
        "dqn_target_mode": args.dqn_target_mode,
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
        f"source_mix={replay_source_mix_stats.mode}:{rows_read_before_source_mix}->{len(rows)} "
        f"experiences={len(experiences)} "
        f"actions={len(actions)} "
        f"action_source={args.training_action_source} "
        f"target_mode={args.dqn_target_mode} "
        f"batch_sampling={batch_sampling_diag.mode} "
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
        f"engine_outcome={engine_outcome_config.training_mode}:{engine_outcome_stats.included_events}/"
        f"{engine_outcome_stats.event_rows} "
        f"engine_outcome_net={engine_outcome_stats.net_adjustment:.1f} "
        f"engine_oversample={engine_outcome_stats.training_experiences}/"
        f"+{engine_outcome_stats.oversample_extra_experiences} "
        f"conservative_cost={conservative_action_penalty_stats.raw_cost_total:.1f} "
        f"loss={train_stats['last_loss']:.6f} avg_loss={train_stats['avg_loss']:.6f} "
        f"included={build_stats.included_action_rows} excluded={build_stats.excluded_action_rows} "
        f"engine_input_fallback={build_stats.engine_outcome_input_fallback_rows} "
        f"cont={build_stats.macro_continuation_rows} "
        f"cont_rew={build_stats.macro_continuation_reward_sum:.3f} "
        f"excluded_rew={build_stats.excluded_action_reward_sum:.3f} "
        f"top={greedy_diag.top_action}:{greedy_diag.top_action_rate * 100.0:.1f}% "
        f"greedy={format_counts(greedy_diag.counts, greedy_diag.evaluated, args.diagnostic_top_n)}",
        flush=True,
    )
    print(
        "DQN diagnostics "
        f"action_source_counts="
        f"{','.join(f'{key}:{value}' for key, value in sorted(build_stats.action_source_counts.items()))}",
        flush=True,
    )
    print(
        "DQN diagnostics "
        f"replay_source_mix=mode:{replay_source_mix_stats.mode} "
        f"rows:{replay_source_mix_stats.raw_rows}->{replay_source_mix_stats.mixed_rows} "
        f"dropped:{replay_source_mix_stats.dropped_rows} "
        f"pre:{format_counts(replay_source_mix_stats.pre_counts, replay_source_mix_stats.raw_rows, args.diagnostic_top_n)} "
        f"post:{format_counts(replay_source_mix_stats.post_counts, replay_source_mix_stats.mixed_rows, args.diagnostic_top_n)} "
        f"target:{format_counts(replay_source_mix_stats.target_counts, sum(replay_source_mix_stats.target_counts.values()), args.diagnostic_top_n)}",
        flush=True,
    )
    print(
        "DQN diagnostics "
        f"action_filter=movable_sources:{','.join(sorted(dqn_action_filter_config.require_movable_state_sources)) or 'none'} "
        f"checked:{build_stats.movable_filter_checked_rows} "
        f"included:{build_stats.movable_filter_included_rows} "
        f"filtered:{build_stats.movable_filter_filtered_rows} "
        f"reward_rows:{build_stats.movable_filter_reward_rows} "
        f"reward_sum:{build_stats.movable_filter_reward_sum:.3f} "
        f"delayed:{build_stats.movable_filter_delayed_rewards} "
        f"uncredited:{build_stats.movable_filter_uncredited_reward_rows} "
        f"by_source:{format_counts(build_stats.movable_filter_by_source, build_stats.movable_filter_filtered_rows, args.diagnostic_top_n)} "
        f"by_action:{format_counts(build_stats.movable_filter_by_action, build_stats.movable_filter_filtered_rows, args.diagnostic_top_n)} "
        f"by_reason:{format_counts(build_stats.movable_filter_by_reason, build_stats.movable_filter_filtered_rows, args.diagnostic_top_n)}",
        flush=True,
    )
    print(
        "DQN diagnostics "
        f"replay_sources=rows:{format_counts(source_stats.row_counts, len(rows), args.diagnostic_top_n)} "
        f"experiences:{format_counts(source_stats.experience_counts, len(experiences), args.diagnostic_top_n)} "
        f"row_model_versions:{format_counts(source_stats.row_model_version_counts, len(rows), args.diagnostic_top_n)} "
        f"experience_model_versions:"
        f"{format_counts(source_stats.experience_model_version_counts, len(experiences), args.diagnostic_top_n)}",
        flush=True,
    )
    print(
        "DQN diagnostics "
        f"replay_source_versions=rows "
        f"{format_source_model_versions(source_stats.row_model_version_counts_by_source, source_stats.row_counts, args.diagnostic_top_n, args.diagnostic_top_n)} "
        f"experiences "
        f"{format_source_model_versions(source_stats.experience_model_version_counts_by_source, source_stats.experience_counts, args.diagnostic_top_n, args.diagnostic_top_n)}",
        flush=True,
    )
    print(
        "DQN diagnostics "
        f"replay_source_actions=count/reward/mean "
        f"{format_source_action_scores(source_stats, actions, args.diagnostic_top_n, args.diagnostic_top_n)}",
        flush=True,
    )
    print(
        "DQN diagnostics "
        f"batch_sampling=mode:{batch_sampling_diag.mode} "
        f"ratios:{','.join(f'{group}:{batch_sampling_diag.ratios.get(group, 0.0):.2f}' for group in BATCH_GROUPS)} "
        f"target:{','.join(f'{group}:{batch_sampling_diag.target_counts.get(group, 0)}' for group in BATCH_GROUPS)} "
        f"pools:{','.join(f'{group}:{batch_sampling_diag.pool_counts.get(group, 0)}' for group in BATCH_GROUPS)}",
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
        f"conservative_penalty=events:{conservative_action_penalty_stats.adjusted_experiences} "
        f"raw_cost:{conservative_action_penalty_stats.raw_cost_total:.1f} "
        f"scaled_cost:{conservative_action_penalty_stats.scaled_cost_total:.3f} "
        f"low_count:{','.join(conservative_action_penalty_stats.low_count_actions) or 'none'} "
        f"nonpositive_mean:{','.join(conservative_action_penalty_stats.nonpositive_mean_actions) or 'none'} "
        f"by_action=count/raw/mean "
        f"{format_action_scores(conservative_action_penalty_stats.per_action_events, conservative_action_penalty_stats.per_action_raw_cost, actions, args.diagnostic_top_n)}",
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
        f"require_contact:{int(reward_guard_config.success_require_contact)} "
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
        f"engine_outcome=mode:{engine_outcome_config.training_mode} "
        f"events:{engine_outcome_stats.event_rows} "
        f"included:{engine_outcome_stats.included_events} "
        f"excluded:{engine_outcome_stats.excluded_events} "
        f"train_exp:{engine_outcome_stats.training_experiences} "
        f"extra:{engine_outcome_stats.oversample_extra_experiences} "
        f"oversample:{engine_outcome_config.oversample} "
        f"early:{engine_outcome_stats.early_outcome_events} "
        f"window:{engine_outcome_config.window_decisions} "
        f"stop_next:{int(engine_outcome_config.stop_at_next_event)} "
        f"hit:{engine_outcome_stats.hit_events} "
        f"no_damage:{engine_outcome_stats.no_damage_events} "
        f"punished:{engine_outcome_stats.punished_events} "
        f"trade:{engine_outcome_stats.trade_events} "
        f"claimed:{engine_outcome_stats.claimed_hp_events}/"
        f"{engine_outcome_stats.claimed_opp_hp_sum}/"
        f"{engine_outcome_stats.claimed_self_hp_sum} "
        f"hp:{engine_outcome_stats.opp_hp_sum}/{engine_outcome_stats.self_hp_sum} "
        f"bonus:{engine_outcome_stats.total_bonus:.1f} "
        f"cost:{engine_outcome_stats.total_cost:.1f} "
        f"net:{engine_outcome_stats.net_adjustment:.1f} "
        f"scaled_reward:{engine_outcome_stats.scaled_reward_sum:.3f} "
        f"training_scaled_reward:{engine_outcome_stats.training_scaled_reward_sum:.3f}",
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
