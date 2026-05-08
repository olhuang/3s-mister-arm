#!/usr/bin/env python3
"""Train a small stdlib-only DQN actor from RL transition NDJSON logs."""

from __future__ import annotations

import argparse
import collections
import copy
import hashlib
import json
import math
import os
import random
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

import rl_combat_event_training as combat_events
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
    row: dict[str, object] = field(default_factory=dict)
    next_row: dict[str, object] = field(default_factory=dict)
    projectile_expert_margin_eligible: bool = False
    special_expert_margin_eligible: bool = False
    projectile_late_defensive_margin_eligible: bool = False
    projectile_defensive_expert_margin_eligible: bool = False
    projectile_batch_eligible: bool = False
    projectile_batch_reason: str = ""
    grounded_normal_defense_eligible: bool = False
    grounded_normal_defense_bc_eligible: bool = False
    low_defense_margin_eligible: bool = False
    combat_event_batch_group: str = "unlabeled_passive"


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
class InitDQNModel:
    path: str
    version: int
    source: str
    metadata: dict[str, object]
    actions: tuple[str, ...]
    feature_names: tuple[str, ...]
    layers: list[dict[str, object]]
    action_mode: str = "exact"


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
    training_mode_hp_sanitized_rows: int = 0
    training_mode_self_heal_ignored: int = 0
    training_mode_opp_heal_ignored: int = 0

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
            "training_mode_hp_sanitized_rows": self.training_mode_hp_sanitized_rows,
            "training_mode_self_heal_ignored": self.training_mode_self_heal_ignored,
            "training_mode_opp_heal_ignored": self.training_mode_opp_heal_ignored,
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


JUMP_START_ACTIONS = frozenset(getattr(rl, "JUMP_START_ACTION_NAMES", ()))
AIR_ATTACK_RISK_ACTIONS = frozenset(getattr(rl, "AIR_NORMAL_ACTION_NAMES", ()))
NON_ATTACK_ACTIONS = frozenset({"forward", "back", "guard-stand", "guard-crouch"}) | JUMP_START_ACTIONS
ATTACK_RISK_ACTIONS = frozenset(action for action in rl.TABULAR_ACTION_NAMES if action not in NON_ATTACK_ACTIONS)
SHORYUKEN_ACTIONS = frozenset({"shoryuken-lp", "shoryuken-mp", "shoryuken-hp"})
REWARD_RISK_PROFILES = ("none", "shoryuken-only", "all-attacks")
ENGINE_OUTCOME_TRAINING_MODES = ("off", "prefer-engine-action")
ENGINE_OUTCOME_MODE_ALIASES = {"prefer-demo-action": "prefer-engine-action"}
REMOVED_ENGINE_OUTCOME_MODES = ("augment", "replace-demo")
TRAINING_ACTION_SOURCES = rl.TRAINING_ACTION_SOURCES
GUARD_ACTIONS = frozenset({"guard-stand", "guard-crouch"})
DEFENSIVE_PROJECTILE_ACTIONS = frozenset({"back", "guard-stand", "guard-crouch"})
PROJECTILE_DEFENSIVE_EXPERT_COMPETITOR_ACTIONS = (
    JUMP_START_ACTIONS
    | SHORYUKEN_ACTIONS
    | frozenset(action for action in rl.TABULAR_ACTION_NAMES if action.startswith("tatsu-"))
)
MOVEMENT_SPACING_ACTIONS = frozenset({"forward", "back"})
MOVEMENT_REGRESSION_MOVEMENT_ACTIONS = frozenset(
    {"forward", "back", "guard-stand", "guard-crouch"}
) | JUMP_START_ACTIONS
UNLABELED_MOVEMENT_FILTER_ACTIONS = frozenset(
    {"forward", "back", "guard-stand", "guard-crouch"}
) | JUMP_START_ACTIONS
COMBAT_EVENT_MOVEMENT_CREDIT_FORWARD_ACTIONS = frozenset({"forward", "jump-forward-start"})
COMBAT_EVENT_MOVEMENT_CREDIT_BACK_ACTIONS = frozenset({"back", "jump-back-start"})
COMBAT_EVENT_MOVEMENT_CREDIT_NEUTRAL_JUMP_ACTIONS = frozenset({"jump-neutral-start"})
COMBAT_EVENT_MOVEMENT_CREDIT_ACTIONS = (
    COMBAT_EVENT_MOVEMENT_CREDIT_FORWARD_ACTIONS
    | COMBAT_EVENT_MOVEMENT_CREDIT_BACK_ACTIONS
    | COMBAT_EVENT_MOVEMENT_CREDIT_NEUTRAL_JUMP_ACTIONS
)
MOVEMENT_REGRESSION_ACTION_GROUPS = frozenset(
    ("stand-normal", "crouch-normal", "air-normal", "fireball", "shoryuken", "tatsu")
)
MOVEMENT_REGRESSION_ACTION_GROUP_ACTIONS = {
    "stand-normal": frozenset(getattr(rl, "STAND_NORMAL_ACTION_NAMES", ())) | frozenset({"forward-hp"}),
    "crouch-normal": frozenset(getattr(rl, "CROUCH_NORMAL_ACTION_NAMES", ())),
    "air-normal": frozenset(getattr(rl, "AIR_NORMAL_ACTION_NAMES", ())),
    "fireball": frozenset(action for action in rl.TABULAR_ACTION_NAMES if action.startswith("fireball-")),
    "shoryuken": SHORYUKEN_ACTIONS,
    "tatsu": frozenset(action for action in rl.TABULAR_ACTION_NAMES if action.startswith("tatsu-")),
}
PROJECTILE_OWNER_OPPONENT = 2
REWARD_PROJECTILE_RESPONSE_PROFILES = ("off", "incoming-v1")
BATCH_SAMPLING_MODES = ("uniform", "balanced")
COMBAT_EVENT_BATCH_GROUPS = (
    "attack",
    "projectile",
    "defense",
    "punish_throw",
    "movement",
    "unlabeled_passive",
)
BATCH_GROUPS = ("projectile", "movement", "normal", "special")
SPECIAL_ACTION_PREFIXES = ("fireball-", "shoryuken-", "tatsu-")
SPECIAL_ACTIONS = frozenset(
    action for action in rl.TABULAR_ACTION_NAMES if action.startswith(SPECIAL_ACTION_PREFIXES)
)
GROUNDED_NORMAL_DEFENSE_SAFE_ACTIONS = frozenset({"back", "guard-stand", "guard-crouch"})
GROUNDED_NORMAL_DEFENSE_UNSAFE_ACTIONS = frozenset(
    {"forward", "forward-hp"}
    | frozenset(getattr(rl, "STAND_NORMAL_ACTION_NAMES", ()))
    | frozenset(getattr(rl, "CROUCH_NORMAL_ACTION_NAMES", ()))
)
LOW_DEFENSE_TARGET_ACTION = "guard-crouch"
LOW_DEFENSE_LOW_ATTACK_ACTIONS = frozenset({"crouch-lk", "crouch-mk", "crouch-hk"})
LOW_DEFENSE_BAD_ACTIONS = frozenset({"guard-stand", "back", "forward"})
DQN_TARGET_MODES = ("standard", "double")
BC_EVENT_WEIGHTING_MODES = ("off", "event-weighted-v1")
BC_LABEL_BALANCE_MODES = ("off", "inverse-sqrt", "inverse-frequency")
BC_FAMILY_MARGIN_MODES = ("off", "positive-event-v1")


@dataclass(frozen=True)
class BCEventWeightConfig:
    mode: str = "off"
    reward_profile: str = "event-damage-v1"
    reward_scale: float = 1.0
    positive_scale: float = 0.25
    negative_scale: float = 0.5
    min_weight: float = 0.25
    max_weight: float = 3.0

    @property
    def enabled(self) -> bool:
        return self.mode != "off"

    def as_reward_config(self) -> combat_events.CombatEventRewardConfig:
        return combat_events.CombatEventRewardConfig(
            enabled=self.enabled,
            profile=self.reward_profile,
            scale=self.reward_scale,
        )

    def as_metadata(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "enabled": self.enabled,
            "reward_profile": self.reward_profile,
            "reward_scale": self.reward_scale,
            "positive_scale": self.positive_scale,
            "negative_scale": self.negative_scale,
            "min_weight": self.min_weight,
            "max_weight": self.max_weight,
        }


@dataclass
class BCEventWeightStats:
    checked_labeled_rows: int = 0
    weighted_rows: int = 0
    positive_rows: int = 0
    negative_rows: int = 0
    neutral_rows: int = 0
    clamped_min_rows: int = 0
    clamped_max_rows: int = 0
    raw_adjustment_sum: float = 0.0
    weight_sum: float = 0.0
    label_weight_sum: dict[str, float] = field(default_factory=dict)
    label_weight_count: dict[str, int] = field(default_factory=dict)

    @property
    def avg_weight(self) -> float:
        return self.weight_sum / max(1, self.checked_labeled_rows)

    def record(self, action_name: str, raw_adjustment: float, weight: float, config: BCEventWeightConfig) -> None:
        self.checked_labeled_rows += 1
        self.raw_adjustment_sum += raw_adjustment
        self.weight_sum += weight
        self.label_weight_sum[action_name] = self.label_weight_sum.get(action_name, 0.0) + weight
        self.label_weight_count[action_name] = self.label_weight_count.get(action_name, 0) + 1
        if raw_adjustment > 0.0:
            self.positive_rows += 1
        elif raw_adjustment < 0.0:
            self.negative_rows += 1
        else:
            self.neutral_rows += 1
        if weight != 1.0:
            self.weighted_rows += 1
        if weight <= config.min_weight and raw_adjustment < 0.0:
            self.clamped_min_rows += 1
        if weight >= config.max_weight and raw_adjustment > 0.0:
            self.clamped_max_rows += 1

    def as_metadata(self) -> dict[str, object]:
        return {
            "checked_labeled_rows": self.checked_labeled_rows,
            "weighted_rows": self.weighted_rows,
            "positive_rows": self.positive_rows,
            "negative_rows": self.negative_rows,
            "neutral_rows": self.neutral_rows,
            "clamped_min_rows": self.clamped_min_rows,
            "clamped_max_rows": self.clamped_max_rows,
            "raw_adjustment_sum": self.raw_adjustment_sum,
            "weight_sum": self.weight_sum,
            "avg_weight": self.avg_weight,
            "label_weight_sum": dict(sorted(self.label_weight_sum.items())),
            "label_weight_count": dict(sorted(self.label_weight_count.items())),
        }


@dataclass(frozen=True)
class BCLabelBalanceConfig:
    mode: str = "off"
    min_weight: float = 0.25
    max_weight: float = 3.0

    @property
    def enabled(self) -> bool:
        return self.mode != "off"

    @property
    def exponent(self) -> float:
        if self.mode == "inverse-frequency":
            return 1.0
        if self.mode == "inverse-sqrt":
            return 0.5
        return 0.0

    def as_metadata(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "enabled": self.enabled,
            "min_weight": self.min_weight,
            "max_weight": self.max_weight,
            "exponent": self.exponent,
        }


@dataclass
class BCLabelBalanceStats:
    balanced_rows: int = 0
    factor_sum: float = 0.0
    label_factors: dict[str, float] = field(default_factory=dict)

    @property
    def avg_factor(self) -> float:
        return self.factor_sum / max(1, self.balanced_rows)

    def as_metadata(self) -> dict[str, object]:
        return {
            "balanced_rows": self.balanced_rows,
            "factor_sum": self.factor_sum,
            "avg_factor": self.avg_factor,
            "label_factors": dict(sorted(self.label_factors.items())),
        }


@dataclass(frozen=True)
class BCFamilyMarginConfig:
    mode: str = "off"
    loss_weight: float = 0.0
    target_q_margin: float = 0.5
    min_positive_adjustment: float = 0.05
    negative_actions: frozenset[str] = field(default_factory=frozenset)

    @property
    def enabled(self) -> bool:
        return self.mode != "off" and self.loss_weight > 0.0

    def as_metadata(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "enabled": self.enabled,
            "loss_weight": self.loss_weight,
            "target_q_margin": self.target_q_margin,
            "min_positive_adjustment": self.min_positive_adjustment,
            "negative_actions": sorted(self.negative_actions),
        }


@dataclass
class BCFamilyMarginStats:
    eligible_rows: int = 0
    sampled_rows: int = 0
    violation_rows: int = 0
    loss_total: float = 0.0
    target_action_counts: dict[str, int] = field(default_factory=dict)
    negative_action_counts: dict[str, int] = field(default_factory=dict)

    @property
    def avg_loss(self) -> float:
        return self.loss_total / max(1, self.sampled_rows)

    def as_metadata(self) -> dict[str, object]:
        return {
            "eligible_rows": self.eligible_rows,
            "sampled_rows": self.sampled_rows,
            "violation_rows": self.violation_rows,
            "loss_total": self.loss_total,
            "avg_loss": self.avg_loss,
            "target_action_counts": dict(sorted(self.target_action_counts.items())),
            "negative_action_counts": dict(sorted(self.negative_action_counts.items())),
        }


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
class DQNUnsupportedActionRegularizationConfig:
    requested: bool
    min_action_count: int
    q_ceiling: float
    loss_weight: float
    adaptive_ceiling: bool = False

    @property
    def enabled(self) -> bool:
        return self.requested and self.min_action_count > 0 and self.loss_weight > 0.0

    def as_metadata(self) -> dict[str, object]:
        return {
            "requested": self.requested,
            "enabled": self.enabled,
            "min_action_count": self.min_action_count,
            "q_ceiling": self.q_ceiling,
            "loss_weight": self.loss_weight,
            "adaptive_ceiling": self.adaptive_ceiling,
        }


@dataclass(frozen=True)
class MovementRegressionLossConfig:
    loss_weight: float
    target_q_margin: float
    far_dx_threshold: int
    action_groups: frozenset[str]
    exclude_special_expert_eligible: bool = False

    @property
    def enabled(self) -> bool:
        return self.loss_weight > 0.0 and self.target_q_margin >= 0.0 and self.far_dx_threshold > 0

    def as_metadata(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "loss_weight": self.loss_weight,
            "target_q_margin": self.target_q_margin,
            "far_dx_threshold": self.far_dx_threshold,
            "action_groups": sorted(self.action_groups),
            "exclude_special_expert_eligible": self.exclude_special_expert_eligible,
        }


@dataclass
class MovementRegressionLossStats:
    eligible_experiences: int = 0
    sampled_events: int = 0
    violation_events: int = 0
    loss_total: float = 0.0
    last_loss: float = 0.0
    avg_loss: float = 0.0

    def as_metadata(self) -> dict[str, object]:
        return {
            "eligible_experiences": self.eligible_experiences,
            "sampled_events": self.sampled_events,
            "violation_events": self.violation_events,
            "loss_total": self.loss_total,
            "last_loss": self.last_loss,
            "avg_loss": self.avg_loss,
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


@dataclass
class DQNUnsupportedActionRegularizationStats:
    eligible_action_count: int = 0
    zero_sample_actions: list[str] = field(default_factory=list)
    low_sample_actions: list[str] = field(default_factory=list)
    regularized_events: int = 0
    regularized_loss_total: float = 0.0
    last_loss: float = 0.0
    avg_loss: float = 0.0
    per_action_events: dict[str, int] = field(default_factory=dict)
    per_action_loss: dict[str, float] = field(default_factory=dict)

    def as_metadata(self) -> dict[str, object]:
        regularized_zero_sample_actions = [
            action for action in self.zero_sample_actions if self.per_action_events.get(action, 0) > 0
        ]
        regularized_low_sample_actions = [
            action for action in self.low_sample_actions if self.per_action_events.get(action, 0) > 0
        ]
        return {
            "eligible_action_count": self.eligible_action_count,
            "zero_sample_actions": self.zero_sample_actions,
            "low_sample_actions": self.low_sample_actions,
            "regularized_zero_sample_actions": regularized_zero_sample_actions,
            "regularized_low_sample_actions": regularized_low_sample_actions,
            "regularized_events": self.regularized_events,
            "regularized_loss_total": self.regularized_loss_total,
            "last_loss": self.last_loss,
            "avg_loss": self.avg_loss,
            "per_action_events": self.per_action_events,
            "per_action_loss": self.per_action_loss,
        }


@dataclass(frozen=True)
class DQNValidActionMaskTrainingConfig:
    mode: str

    @property
    def enabled(self) -> bool:
        return self.mode != "off"

    def as_shared_config(self) -> rl.DQNValidActionMaskConfig:
        return rl.parse_dqn_valid_action_mask_config(self.mode)

    def as_metadata(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "enabled": self.enabled,
        }


@dataclass
class DQNValidActionMaskTrainingStats:
    target_states: int = 0
    target_empty_masks: int = 0
    target_masked_action_total: int = 0
    target_valid_action_total: int = 0
    greedy_rows: int = 0
    greedy_empty_masks: int = 0
    greedy_masked_action_total: int = 0
    greedy_valid_action_total: int = 0
    target_masked_actions: dict[str, int] = field(default_factory=dict)
    greedy_masked_actions: dict[str, int] = field(default_factory=dict)

    def as_metadata(self) -> dict[str, object]:
        return {
            "target_states": self.target_states,
            "target_empty_masks": self.target_empty_masks,
            "target_masked_action_total": self.target_masked_action_total,
            "target_valid_action_total": self.target_valid_action_total,
            "greedy_rows": self.greedy_rows,
            "greedy_empty_masks": self.greedy_empty_masks,
            "greedy_masked_action_total": self.greedy_masked_action_total,
            "greedy_valid_action_total": self.greedy_valid_action_total,
            "target_masked_actions": dict(sorted(self.target_masked_actions.items())),
            "greedy_masked_actions": dict(sorted(self.greedy_masked_actions.items())),
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
class CombatEventBatchSamplingConfig:
    mode: str = "off"
    ratios: dict[str, float] = field(default_factory=dict)

    @property
    def enabled(self) -> bool:
        return self.mode != "off"

    def as_metadata(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "enabled": self.enabled,
            "ratios": {group: self.ratios.get(group, 0.0) for group in COMBAT_EVENT_BATCH_GROUPS},
            "groups": list(COMBAT_EVENT_BATCH_GROUPS),
        }


@dataclass(frozen=True)
class CombatEventBatchSamplingDiagnostics:
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
    throw_far_cost: float = 0.0
    throw_far_max_abs_dx: int = 64


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
    throw_far_cost_events: int = 0
    throw_far_cost_total: float = 0.0

    @property
    def total_cost(self) -> float:
        return (
            self.attack_no_damage_cost_total
            + self.attack_punished_cost_total
            + self.shoryuken_no_damage_extra_cost_total
            + self.shoryuken_punished_extra_cost_total
            + self.jump_attack_no_damage_extra_cost_total
            + self.jump_attack_punished_extra_cost_total
            + self.throw_far_cost_total
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
            "throw_far_cost_events": self.throw_far_cost_events,
            "throw_far_cost_total": self.throw_far_cost_total,
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
class RewardProjectileResponseConfig:
    profile: str
    window_decisions: int
    threat_min_time_to_self: int
    threat_max_time_to_self: int
    threat_max_dx: int
    threat_max_abs_y: int
    close_max_dx: int
    safe_jump_bonus: float
    late_jump_hit_cost: float
    close_back_success_bonus: float
    close_guard_success_bonus: float
    back_escape_min_dx_delta: int
    guard_require_contact: bool

    @property
    def enabled(self) -> bool:
        return self.profile != "off" and (
            self.safe_jump_bonus > 0.0
            or self.late_jump_hit_cost > 0.0
            or self.close_back_success_bonus > 0.0
            or self.close_guard_success_bonus > 0.0
        )


@dataclass(frozen=True)
class CombatEventUnlabeledMovementFilterConfig:
    policy: str = "keep"
    keep_ratio: float = 1.0
    seed: int = 20260507

    @property
    def enabled(self) -> bool:
        return self.policy != "keep"

    def as_metadata(self) -> dict[str, object]:
        return {
            "policy": self.policy,
            "enabled": self.enabled,
            "keep_ratio": self.keep_ratio,
            "seed": self.seed,
            "actions": sorted(UNLABELED_MOVEMENT_FILTER_ACTIONS),
        }


@dataclass
class CombatEventUnlabeledMovementFilterStats:
    checked_rows: int = 0
    protected_rows: int = 0
    eligible_rows: int = 0
    kept_unlabeled_rows: int = 0
    dropped_rows: int = 0
    protected_dropped_rows: int = 0
    by_action_checked: dict[str, int] = field(default_factory=dict)
    by_action_protected: dict[str, int] = field(default_factory=dict)
    by_action_eligible: dict[str, int] = field(default_factory=dict)
    by_action_kept_unlabeled: dict[str, int] = field(default_factory=dict)
    by_action_dropped: dict[str, int] = field(default_factory=dict)
    protected_by_reason: dict[str, int] = field(default_factory=dict)

    def _inc(self, counts: dict[str, int], key: str, amount: int = 1) -> None:
        counts[key] = counts.get(key, 0) + amount

    def add_checked(self, action_name: str) -> None:
        self.checked_rows += 1
        self._inc(self.by_action_checked, action_name)

    def add_protected(self, action_name: str, reasons: list[str]) -> None:
        self.protected_rows += 1
        self._inc(self.by_action_protected, action_name)
        for reason in reasons:
            self._inc(self.protected_by_reason, reason)

    def add_unlabeled(self, action_name: str, kept: bool) -> None:
        self.eligible_rows += 1
        self._inc(self.by_action_eligible, action_name)
        if kept:
            self.kept_unlabeled_rows += 1
            self._inc(self.by_action_kept_unlabeled, action_name)
        else:
            self.dropped_rows += 1
            self._inc(self.by_action_dropped, action_name)

    def as_metadata(self) -> dict[str, object]:
        return {
            "checked_rows": self.checked_rows,
            "protected_rows": self.protected_rows,
            "eligible_rows": self.eligible_rows,
            "kept_unlabeled_rows": self.kept_unlabeled_rows,
            "dropped_rows": self.dropped_rows,
            "protected_dropped_rows": self.protected_dropped_rows,
            "by_action_checked": dict(sorted(self.by_action_checked.items())),
            "by_action_protected": dict(sorted(self.by_action_protected.items())),
            "by_action_eligible": dict(sorted(self.by_action_eligible.items())),
            "by_action_kept_unlabeled": dict(sorted(self.by_action_kept_unlabeled.items())),
            "by_action_dropped": dict(sorted(self.by_action_dropped.items())),
            "protected_by_reason": dict(sorted(self.protected_by_reason.items())),
        }


@dataclass(frozen=True)
class CombatEventMovementCreditConfig:
    mode: str = "off"
    window_decisions: int = 6
    max_rows: int = 3
    scale: float = 0.35
    decay: tuple[float, ...] = (0.5, 0.3, 0.2)
    row_abs_cap: float = 0.0

    @property
    def enabled(self) -> bool:
        return (
            self.mode != "off"
            and self.window_decisions > 0
            and self.max_rows > 0
            and self.scale > 0.0
            and bool(self.decay)
        )

    def as_metadata(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "enabled": self.enabled,
            "window_decisions": self.window_decisions,
            "max_rows": self.max_rows,
            "scale": self.scale,
            "decay": list(self.decay),
            "row_abs_cap": self.row_abs_cap,
            "actions": sorted(COMBAT_EVENT_MOVEMENT_CREDIT_ACTIONS),
        }


@dataclass
class CombatEventMovementCreditStats:
    checked_anchor_rows: int = 0
    eligible_anchor_rows: int = 0
    applied_anchor_rows: int = 0
    candidate_rows: int = 0
    applied_rows: int = 0
    skipped_no_reward: int = 0
    skipped_no_label: int = 0
    skipped_direction_mismatch: int = 0
    skipped_no_candidate: int = 0
    skipped_cross_source_boundary: int = 0
    capped_rows: int = 0
    total_credit: float = 0.0
    total_positive_credit: float = 0.0
    total_negative_credit: float = 0.0
    by_action: dict[str, float] = field(default_factory=dict)
    by_reason: dict[str, float] = field(default_factory=dict)
    rows_by_action: dict[str, int] = field(default_factory=dict)
    rows_by_reason: dict[str, int] = field(default_factory=dict)
    credit_abs_by_exp_index: dict[int, float] = field(default_factory=dict, repr=False)

    @property
    def net_adjustment(self) -> float:
        return self.total_credit

    def add_credit(self, action_name: str, reason: str, credit: float) -> None:
        self.applied_rows += 1
        self.total_credit += credit
        if credit > 0.0:
            self.total_positive_credit += credit
        elif credit < 0.0:
            self.total_negative_credit += credit
        self.by_action[action_name] = self.by_action.get(action_name, 0.0) + credit
        self.by_reason[reason] = self.by_reason.get(reason, 0.0) + credit
        self.rows_by_action[action_name] = self.rows_by_action.get(action_name, 0) + 1
        self.rows_by_reason[reason] = self.rows_by_reason.get(reason, 0) + 1

    def as_metadata(self) -> dict[str, object]:
        return {
            "checked_anchor_rows": self.checked_anchor_rows,
            "eligible_anchor_rows": self.eligible_anchor_rows,
            "applied_anchor_rows": self.applied_anchor_rows,
            "candidate_rows": self.candidate_rows,
            "applied_rows": self.applied_rows,
            "skipped_no_reward": self.skipped_no_reward,
            "skipped_no_label": self.skipped_no_label,
            "skipped_direction_mismatch": self.skipped_direction_mismatch,
            "skipped_no_candidate": self.skipped_no_candidate,
            "skipped_cross_source_boundary": self.skipped_cross_source_boundary,
            "capped_rows": self.capped_rows,
            "total_credit": self.total_credit,
            "total_positive_credit": self.total_positive_credit,
            "total_negative_credit": self.total_negative_credit,
            "by_action": dict(sorted(self.by_action.items())),
            "by_reason": dict(sorted(self.by_reason.items())),
            "rows_by_action": dict(sorted(self.rows_by_action.items())),
            "rows_by_reason": dict(sorted(self.rows_by_reason.items())),
        }


@dataclass(frozen=True)
class ProjectileResponseOutcome:
    threat: bool = False
    safe_jump: bool = False
    late_jump_hit: bool = False
    close_back_success: bool = False
    close_guard_success: bool = False


@dataclass
class RewardProjectileResponseStats:
    threat_action_rows: int = 0
    safe_jump_bonus_events: int = 0
    late_jump_hit_cost_events: int = 0
    close_back_success_bonus_events: int = 0
    close_guard_success_bonus_events: int = 0
    safe_jump_bonus_total: float = 0.0
    late_jump_hit_cost_total: float = 0.0
    close_back_success_bonus_total: float = 0.0
    close_guard_success_bonus_total: float = 0.0

    @property
    def total_bonus(self) -> float:
        return (
            self.safe_jump_bonus_total
            + self.close_back_success_bonus_total
            + self.close_guard_success_bonus_total
        )

    @property
    def total_cost(self) -> float:
        return self.late_jump_hit_cost_total

    @property
    def net_adjustment(self) -> float:
        return self.total_bonus - self.total_cost

    def as_metadata(self) -> dict[str, object]:
        return {
            "threat_action_rows": self.threat_action_rows,
            "safe_jump_bonus_events": self.safe_jump_bonus_events,
            "late_jump_hit_cost_events": self.late_jump_hit_cost_events,
            "close_back_success_bonus_events": self.close_back_success_bonus_events,
            "close_guard_success_bonus_events": self.close_guard_success_bonus_events,
            "safe_jump_bonus_total": self.safe_jump_bonus_total,
            "late_jump_hit_cost_total": self.late_jump_hit_cost_total,
            "close_back_success_bonus_total": self.close_back_success_bonus_total,
            "close_guard_success_bonus_total": self.close_guard_success_bonus_total,
            "total_bonus": self.total_bonus,
            "total_cost": self.total_cost,
            "net_adjustment": self.net_adjustment,
        }


@dataclass(frozen=True)
class ProjectileResponseOversampleConfig:
    safe_jump: int = 1
    late_jump_hit: int = 1
    close_back_success: int = 1
    close_guard_success: int = 1

    @property
    def enabled(self) -> bool:
        return max(
            self.safe_jump,
            self.late_jump_hit,
            self.close_back_success,
            self.close_guard_success,
        ) > 1

    def multiplier_for(self, outcome: ProjectileResponseOutcome) -> int:
        multiplier = 1
        if outcome.safe_jump:
            multiplier = max(multiplier, self.safe_jump)
        if outcome.late_jump_hit:
            multiplier = max(multiplier, self.late_jump_hit)
        if outcome.close_back_success:
            multiplier = max(multiplier, self.close_back_success)
        if outcome.close_guard_success:
            multiplier = max(multiplier, self.close_guard_success)
        return max(1, multiplier)

    def as_metadata(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "safe_jump": self.safe_jump,
            "late_jump_hit": self.late_jump_hit,
            "close_back_success": self.close_back_success,
            "close_guard_success": self.close_guard_success,
        }


@dataclass
class ProjectileResponseOversampleStats:
    base_experiences: int = 0
    extra_experiences: int = 0
    safe_jump_base: int = 0
    safe_jump_extra: int = 0
    late_jump_hit_base: int = 0
    late_jump_hit_extra: int = 0
    close_back_success_base: int = 0
    close_back_success_extra: int = 0
    close_guard_success_base: int = 0
    close_guard_success_extra: int = 0
    by_action_base: dict[str, int] = field(default_factory=dict)
    by_action_extra: dict[str, int] = field(default_factory=dict)

    def add(self, action_name: str, outcome: ProjectileResponseOutcome, multiplier: int) -> None:
        safe_multiplier = max(1, int(multiplier))
        extra = safe_multiplier - 1
        if extra <= 0:
            return

        self.base_experiences += 1
        self.extra_experiences += extra
        self.by_action_base[action_name] = self.by_action_base.get(action_name, 0) + 1
        self.by_action_extra[action_name] = self.by_action_extra.get(action_name, 0) + extra
        if outcome.safe_jump:
            self.safe_jump_base += 1
            self.safe_jump_extra += extra
        if outcome.late_jump_hit:
            self.late_jump_hit_base += 1
            self.late_jump_hit_extra += extra
        if outcome.close_back_success:
            self.close_back_success_base += 1
            self.close_back_success_extra += extra
        if outcome.close_guard_success:
            self.close_guard_success_base += 1
            self.close_guard_success_extra += extra

    def as_metadata(self) -> dict[str, object]:
        return {
            "base_experiences": self.base_experiences,
            "extra_experiences": self.extra_experiences,
            "safe_jump_base": self.safe_jump_base,
            "safe_jump_extra": self.safe_jump_extra,
            "late_jump_hit_base": self.late_jump_hit_base,
            "late_jump_hit_extra": self.late_jump_hit_extra,
            "close_back_success_base": self.close_back_success_base,
            "close_back_success_extra": self.close_back_success_extra,
            "close_guard_success_base": self.close_guard_success_base,
            "close_guard_success_extra": self.close_guard_success_extra,
            "by_action_base": dict(sorted(self.by_action_base.items())),
            "by_action_extra": dict(sorted(self.by_action_extra.items())),
        }


@dataclass(frozen=True)
class ProjectileBatchConfig:
    requested: bool = False
    min_time_to_self: int = 0
    max_time_to_self: int = 12
    time_ranges: tuple[tuple[int, int], ...] = ()
    window_decisions: int = 12
    max_self_hp: int = 1
    eligible_sources: frozenset[str] = field(default_factory=lambda: frozenset({"human-demo"}))
    include_late_jump_hit: bool = True
    include_safe_jump: bool = False
    safe_jump_min_time_to_self: int = 13
    safe_jump_max_time_to_self: int = 48

    @property
    def enabled(self) -> bool:
        return self.requested

    def as_metadata(self) -> dict[str, object]:
        return {
            "requested": self.requested,
            "enabled": self.enabled,
            "min_time_to_self": self.min_time_to_self,
            "max_time_to_self": self.max_time_to_self,
            "time_ranges": format_time_ranges(self.time_ranges),
            "window_decisions": self.window_decisions,
            "max_self_hp": self.max_self_hp,
            "eligible_sources": sorted(self.eligible_sources),
            "include_late_jump_hit": self.include_late_jump_hit,
            "include_safe_jump": self.include_safe_jump,
            "safe_jump_min_time_to_self": self.safe_jump_min_time_to_self,
            "safe_jump_max_time_to_self": self.safe_jump_max_time_to_self,
            "defensive_actions": sorted(DEFENSIVE_PROJECTILE_ACTIONS),
            "jump_actions": sorted(JUMP_START_ACTIONS),
        }


@dataclass
class ProjectileBatchStats:
    eligible_experiences: int = 0
    defensive_experiences: int = 0
    late_jump_hit_experiences: int = 0
    safe_jump_experiences: int = 0
    by_reason: dict[str, int] = field(default_factory=dict)
    by_action: dict[str, int] = field(default_factory=dict)
    by_source: dict[str, int] = field(default_factory=dict)
    by_time_bucket: dict[str, int] = field(default_factory=dict)

    def add(self, exp: Experience, actions: tuple[str, ...]) -> None:
        if not exp.projectile_batch_eligible:
            return
        self.eligible_experiences += 1
        reason = exp.projectile_batch_reason or "unknown"
        action = actions[exp.action_index] if 0 <= exp.action_index < len(actions) else "unknown"
        bucket = projectile_time_to_self_bucket(exp.row)
        self.by_reason[reason] = self.by_reason.get(reason, 0) + 1
        self.by_action[action] = self.by_action.get(action, 0) + 1
        self.by_source[exp.source_name] = self.by_source.get(exp.source_name, 0) + 1
        self.by_time_bucket[bucket] = self.by_time_bucket.get(bucket, 0) + 1
        if reason == "defensive-clean":
            self.defensive_experiences += 1
        elif reason == "late-jump-hit":
            self.late_jump_hit_experiences += 1
        elif reason == "safe-jump":
            self.safe_jump_experiences += 1

    def as_metadata(self) -> dict[str, object]:
        return {
            "eligible_experiences": self.eligible_experiences,
            "defensive_experiences": self.defensive_experiences,
            "late_jump_hit_experiences": self.late_jump_hit_experiences,
            "safe_jump_experiences": self.safe_jump_experiences,
            "by_reason": dict(sorted(self.by_reason.items())),
            "by_action": dict(sorted(self.by_action.items())),
            "by_source": dict(sorted(self.by_source.items())),
            "by_time_bucket": dict(sorted(self.by_time_bucket.items())),
        }


@dataclass(frozen=True)
class ProjectileExpertMarginConfig:
    requested: bool = False
    margin: float = 0.1
    loss_weight: float = 0.05
    batch_size: int = 0
    require_safe_jump: bool = True
    equivalent_jump_actions: bool = True
    min_time_to_self: int = 0
    max_time_to_self: int = 32767
    time_ranges: tuple[tuple[int, int], ...] = ()
    eligible_sources: frozenset[str] = field(default_factory=lambda: frozenset({"human-demo"}))
    valid_action_mask_mode: str = "action-start-v1"

    @property
    def enabled(self) -> bool:
        return self.requested and self.margin > 0.0 and self.loss_weight > 0.0

    def as_shared_mask_config(self) -> rl.DQNValidActionMaskConfig:
        return rl.parse_dqn_valid_action_mask_config(self.valid_action_mask_mode)

    def as_metadata(self) -> dict[str, object]:
        return {
            "requested": self.requested,
            "enabled": self.enabled,
            "margin": self.margin,
            "loss_weight": self.loss_weight,
            "batch_size": self.batch_size,
            "require_safe_jump": self.require_safe_jump,
            "equivalent_jump_actions": self.equivalent_jump_actions,
            "min_time_to_self": self.min_time_to_self,
            "max_time_to_self": self.max_time_to_self,
            "time_ranges": format_time_ranges(self.time_ranges),
            "eligible_sources": sorted(self.eligible_sources),
            "valid_action_mask_mode": self.valid_action_mask_mode,
        }


@dataclass
class ProjectileExpertMarginStats:
    eligible_experiences: int = 0
    sampled_events: int = 0
    violation_events: int = 0
    empty_valid_events: int = 0
    expert_invalid_events: int = 0
    loss_total: float = 0.0
    last_loss: float = 0.0
    avg_loss: float = 0.0
    by_expert_action_events: dict[str, int] = field(default_factory=dict)
    by_expert_action_loss: dict[str, float] = field(default_factory=dict)
    blocker_counts: dict[str, int] = field(default_factory=dict)
    sampled_by_time_bucket: dict[str, int] = field(default_factory=dict)
    violation_by_time_bucket: dict[str, int] = field(default_factory=dict)

    def as_metadata(self) -> dict[str, object]:
        return {
            "eligible_experiences": self.eligible_experiences,
            "sampled_events": self.sampled_events,
            "violation_events": self.violation_events,
            "empty_valid_events": self.empty_valid_events,
            "expert_invalid_events": self.expert_invalid_events,
            "loss_total": self.loss_total,
            "last_loss": self.last_loss,
            "avg_loss": self.avg_loss,
            "by_expert_action_events": dict(sorted(self.by_expert_action_events.items())),
            "by_expert_action_loss": dict(sorted(self.by_expert_action_loss.items())),
            "blocker_counts": dict(sorted(self.blocker_counts.items())),
            "sampled_by_time_bucket": dict(sorted(self.sampled_by_time_bucket.items())),
            "violation_by_time_bucket": dict(sorted(self.violation_by_time_bucket.items())),
        }


@dataclass(frozen=True)
class SpecialExpertMarginConfig:
    requested: bool = False
    margin: float = 0.08
    loss_weight: float = 0.5
    batch_size: int = 0
    min_reward: float = 0.0
    eligible_sources: frozenset[str] = field(default_factory=lambda: frozenset({"human-demo", "cpu-demo"}))
    valid_action_mask_mode: str = "action-start-v1"
    context_gate: bool = False
    fireball_min_abs_dx: int = 120

    @property
    def enabled(self) -> bool:
        return self.requested and self.margin > 0.0 and self.loss_weight > 0.0

    def as_shared_mask_config(self) -> rl.DQNValidActionMaskConfig:
        return rl.parse_dqn_valid_action_mask_config(self.valid_action_mask_mode)

    def as_metadata(self) -> dict[str, object]:
        return {
            "requested": self.requested,
            "enabled": self.enabled,
            "margin": self.margin,
            "loss_weight": self.loss_weight,
            "batch_size": self.batch_size,
            "min_reward": self.min_reward,
            "eligible_sources": sorted(self.eligible_sources),
            "valid_action_mask_mode": self.valid_action_mask_mode,
            "context_gate": self.context_gate,
            "fireball_min_abs_dx": self.fireball_min_abs_dx,
            "special_actions": sorted(SPECIAL_ACTIONS),
        }


@dataclass(frozen=True)
class ProjectileLateDefensiveMarginConfig:
    requested: bool = False
    margin: float = 0.05
    loss_weight: float = 0.5
    batch_size: int = 0
    min_time_to_self: int = 0
    max_time_to_self: int = 12
    eligible_sources: frozenset[str] = field(default_factory=lambda: frozenset({"human-demo", "remote"}))
    valid_action_mask_mode: str = "action-start-v1"

    @property
    def enabled(self) -> bool:
        return self.requested and self.margin > 0.0 and self.loss_weight > 0.0

    def as_shared_mask_config(self) -> rl.DQNValidActionMaskConfig:
        return rl.parse_dqn_valid_action_mask_config(self.valid_action_mask_mode)

    def as_metadata(self) -> dict[str, object]:
        return {
            "requested": self.requested,
            "enabled": self.enabled,
            "margin": self.margin,
            "loss_weight": self.loss_weight,
            "batch_size": self.batch_size,
            "min_time_to_self": self.min_time_to_self,
            "max_time_to_self": self.max_time_to_self,
            "eligible_sources": sorted(self.eligible_sources),
            "defensive_actions": sorted(DEFENSIVE_PROJECTILE_ACTIONS),
            "jump_actions": sorted(JUMP_START_ACTIONS),
            "valid_action_mask_mode": self.valid_action_mask_mode,
        }


@dataclass
class ProjectileLateDefensiveMarginStats:
    eligible_experiences: int = 0
    sampled_events: int = 0
    violation_events: int = 0
    empty_valid_events: int = 0
    empty_defensive_events: int = 0
    empty_jump_events: int = 0
    loss_total: float = 0.0
    last_loss: float = 0.0
    avg_loss: float = 0.0
    defensive_action_events: dict[str, int] = field(default_factory=dict)
    jump_blocker_counts: dict[str, int] = field(default_factory=dict)
    sampled_by_time_bucket: dict[str, int] = field(default_factory=dict)
    violation_by_time_bucket: dict[str, int] = field(default_factory=dict)

    def as_metadata(self) -> dict[str, object]:
        return {
            "eligible_experiences": self.eligible_experiences,
            "sampled_events": self.sampled_events,
            "violation_events": self.violation_events,
            "empty_valid_events": self.empty_valid_events,
            "empty_defensive_events": self.empty_defensive_events,
            "empty_jump_events": self.empty_jump_events,
            "loss_total": self.loss_total,
            "last_loss": self.last_loss,
            "avg_loss": self.avg_loss,
            "defensive_action_events": dict(sorted(self.defensive_action_events.items())),
            "jump_blocker_counts": dict(sorted(self.jump_blocker_counts.items())),
            "sampled_by_time_bucket": dict(sorted(self.sampled_by_time_bucket.items())),
            "violation_by_time_bucket": dict(sorted(self.violation_by_time_bucket.items())),
        }


@dataclass(frozen=True)
class ProjectileDefensiveExpertMarginConfig:
    requested: bool = False
    margin: float = 0.08
    loss_weight: float = 1.0
    batch_size: int = 0
    min_time_to_self: int = 0
    max_time_to_self: int = 12
    time_ranges: tuple[tuple[int, int], ...] = ()
    window_decisions: int = 12
    max_self_hp: int = 1
    all_competitors: bool = False
    eligible_sources: frozenset[str] = field(default_factory=lambda: frozenset({"human-demo"}))
    valid_action_mask_mode: str = "action-start-v1"

    @property
    def enabled(self) -> bool:
        return self.requested and self.margin > 0.0 and self.loss_weight > 0.0

    def as_shared_mask_config(self) -> rl.DQNValidActionMaskConfig:
        return rl.parse_dqn_valid_action_mask_config(self.valid_action_mask_mode)

    def as_metadata(self) -> dict[str, object]:
        return {
            "requested": self.requested,
            "enabled": self.enabled,
            "margin": self.margin,
            "loss_weight": self.loss_weight,
            "batch_size": self.batch_size,
            "min_time_to_self": self.min_time_to_self,
            "max_time_to_self": self.max_time_to_self,
            "time_ranges": format_time_ranges(self.time_ranges),
            "window_decisions": self.window_decisions,
            "max_self_hp": self.max_self_hp,
            "all_competitors": self.all_competitors,
            "eligible_sources": sorted(self.eligible_sources),
            "defensive_actions": sorted(DEFENSIVE_PROJECTILE_ACTIONS),
            "competitor_actions": sorted(PROJECTILE_DEFENSIVE_EXPERT_COMPETITOR_ACTIONS),
            "valid_action_mask_mode": self.valid_action_mask_mode,
        }


@dataclass
class ProjectileDefensiveExpertMarginStats:
    eligible_experiences: int = 0
    sampled_events: int = 0
    violation_events: int = 0
    empty_valid_events: int = 0
    empty_defensive_events: int = 0
    empty_competitor_events: int = 0
    loss_total: float = 0.0
    last_loss: float = 0.0
    avg_loss: float = 0.0
    defensive_action_events: dict[str, int] = field(default_factory=dict)
    competitor_blocker_counts: dict[str, int] = field(default_factory=dict)
    sampled_by_time_bucket: dict[str, int] = field(default_factory=dict)
    violation_by_time_bucket: dict[str, int] = field(default_factory=dict)

    def as_metadata(self) -> dict[str, object]:
        return {
            "eligible_experiences": self.eligible_experiences,
            "sampled_events": self.sampled_events,
            "violation_events": self.violation_events,
            "empty_valid_events": self.empty_valid_events,
            "empty_defensive_events": self.empty_defensive_events,
            "empty_competitor_events": self.empty_competitor_events,
            "loss_total": self.loss_total,
            "last_loss": self.last_loss,
            "avg_loss": self.avg_loss,
            "defensive_action_events": dict(sorted(self.defensive_action_events.items())),
            "competitor_blocker_counts": dict(sorted(self.competitor_blocker_counts.items())),
            "sampled_by_time_bucket": dict(sorted(self.sampled_by_time_bucket.items())),
            "violation_by_time_bucket": dict(sorted(self.violation_by_time_bucket.items())),
        }


@dataclass(frozen=True)
class ProjectileTimingGroupMarginConfig:
    requested: bool = False
    margin: float = 0.08
    loss_weight: float = 1.0
    batch_size: int = 0
    defense_time_ranges: tuple[tuple[int, int], ...] = ()
    jump_time_ranges: tuple[tuple[int, int], ...] = ()
    eligible_sources: frozenset[str] = field(default_factory=lambda: frozenset({"remote"}))
    valid_action_mask_mode: str = "action-start-v1"
    threat_max_dx: int = 240
    threat_max_abs_y: int = 96

    @property
    def enabled(self) -> bool:
        return self.requested and self.margin > 0.0 and self.loss_weight > 0.0

    def as_shared_mask_config(self) -> rl.DQNValidActionMaskConfig:
        return rl.parse_dqn_valid_action_mask_config(self.valid_action_mask_mode)

    def as_metadata(self) -> dict[str, object]:
        return {
            "requested": self.requested,
            "enabled": self.enabled,
            "margin": self.margin,
            "loss_weight": self.loss_weight,
            "batch_size": self.batch_size,
            "defense_time_ranges": format_time_ranges(self.defense_time_ranges),
            "jump_time_ranges": format_time_ranges(self.jump_time_ranges),
            "eligible_sources": sorted(self.eligible_sources),
            "valid_action_mask_mode": self.valid_action_mask_mode,
            "threat_max_dx": self.threat_max_dx,
            "threat_max_abs_y": self.threat_max_abs_y,
            "defensive_actions": sorted(DEFENSIVE_PROJECTILE_ACTIONS),
            "jump_actions": sorted(JUMP_START_ACTIONS),
            "defensive_competitor_actions": sorted(PROJECTILE_DEFENSIVE_EXPERT_COMPETITOR_ACTIONS),
        }


@dataclass
class ProjectileTimingGroupMarginStats:
    eligible_experiences: int = 0
    sampled_events: int = 0
    violation_events: int = 0
    empty_valid_events: int = 0
    empty_target_events: int = 0
    empty_competitor_events: int = 0
    loss_total: float = 0.0
    last_loss: float = 0.0
    avg_loss: float = 0.0
    sampled_by_target: dict[str, int] = field(default_factory=dict)
    violation_by_target: dict[str, int] = field(default_factory=dict)
    sampled_by_time_bucket: dict[str, int] = field(default_factory=dict)
    violation_by_time_bucket: dict[str, int] = field(default_factory=dict)
    blocker_counts: dict[str, int] = field(default_factory=dict)

    def as_metadata(self) -> dict[str, object]:
        return {
            "eligible_experiences": self.eligible_experiences,
            "sampled_events": self.sampled_events,
            "violation_events": self.violation_events,
            "empty_valid_events": self.empty_valid_events,
            "empty_target_events": self.empty_target_events,
            "empty_competitor_events": self.empty_competitor_events,
            "loss_total": self.loss_total,
            "last_loss": self.last_loss,
            "avg_loss": self.avg_loss,
            "sampled_by_target": dict(sorted(self.sampled_by_target.items())),
            "violation_by_target": dict(sorted(self.violation_by_target.items())),
            "sampled_by_time_bucket": dict(sorted(self.sampled_by_time_bucket.items())),
            "violation_by_time_bucket": dict(sorted(self.violation_by_time_bucket.items())),
            "blocker_counts": dict(sorted(self.blocker_counts.items())),
        }


@dataclass(frozen=True)
class GroundedNormalDefenseMarginConfig:
    requested: bool = False
    margin: float = 0.1
    loss_weight: float = 0.5
    batch_size: int = 0
    eligible_sources: frozenset[str] = field(default_factory=lambda: frozenset({"human-demo"}))
    valid_action_mask_mode: str = "action-start-v1"
    max_abs_dx: int = 144

    @property
    def enabled(self) -> bool:
        return self.requested and self.margin > 0.0 and self.loss_weight > 0.0

    def as_shared_mask_config(self) -> rl.DQNValidActionMaskConfig:
        return rl.parse_dqn_valid_action_mask_config(self.valid_action_mask_mode)

    def as_metadata(self) -> dict[str, object]:
        return {
            "requested": self.requested,
            "enabled": self.enabled,
            "margin": self.margin,
            "loss_weight": self.loss_weight,
            "batch_size": self.batch_size,
            "eligible_sources": sorted(self.eligible_sources),
            "valid_action_mask_mode": self.valid_action_mask_mode,
            "max_abs_dx": self.max_abs_dx,
            "safe_actions": sorted(GROUNDED_NORMAL_DEFENSE_SAFE_ACTIONS),
            "unsafe_actions": sorted(GROUNDED_NORMAL_DEFENSE_UNSAFE_ACTIONS),
        }


@dataclass
class GroundedNormalDefenseMarginStats:
    eligible_experiences: int = 0
    sampled_events: int = 0
    violation_events: int = 0
    empty_valid_events: int = 0
    empty_safe_events: int = 0
    empty_unsafe_events: int = 0
    empty_context_events: int = 0
    loss_total: float = 0.0
    last_loss: float = 0.0
    avg_loss: float = 0.0
    sampled_by_time_bucket: dict[str, int] = field(default_factory=dict)
    violation_by_time_bucket: dict[str, int] = field(default_factory=dict)
    safe_top_actions: dict[str, int] = field(default_factory=dict)
    blocker_counts: dict[str, int] = field(default_factory=dict)

    def as_metadata(self) -> dict[str, object]:
        return {
            "eligible_experiences": self.eligible_experiences,
            "sampled_events": self.sampled_events,
            "violation_events": self.violation_events,
            "empty_valid_events": self.empty_valid_events,
            "empty_safe_events": self.empty_safe_events,
            "empty_unsafe_events": self.empty_unsafe_events,
            "empty_context_events": self.empty_context_events,
            "loss_total": self.loss_total,
            "last_loss": self.last_loss,
            "avg_loss": self.avg_loss,
            "sampled_by_time_bucket": dict(sorted(self.sampled_by_time_bucket.items())),
            "violation_by_time_bucket": dict(sorted(self.violation_by_time_bucket.items())),
            "safe_top_actions": dict(sorted(self.safe_top_actions.items())),
            "blocker_counts": dict(sorted(self.blocker_counts.items())),
        }


@dataclass(frozen=True)
class GroundedNormalDefenseBCConfig:
    requested: bool = False
    loss_weight: float = 0.1
    eligible_sources: frozenset[str] = field(default_factory=lambda: frozenset({"human-demo"}))
    max_abs_dx: int = 144

    @property
    def enabled(self) -> bool:
        return self.requested and self.loss_weight > 0.0

    def as_metadata(self) -> dict[str, object]:
        return {
            "requested": self.requested,
            "enabled": self.enabled,
            "loss_weight": self.loss_weight,
            "eligible_sources": sorted(self.eligible_sources),
            "max_abs_dx": self.max_abs_dx,
            "target_actions": sorted(GROUNDED_NORMAL_DEFENSE_SAFE_ACTIONS),
        }


@dataclass
class GroundedNormalDefenseBCStats:
    eligible_experiences: int = 0
    sampled_events: int = 0
    loss_total: float = 0.0
    last_loss: float = 0.0
    avg_loss: float = 0.0
    target_action_counts: dict[str, int] = field(default_factory=dict)
    sampled_by_time_bucket: dict[str, int] = field(default_factory=dict)

    def as_metadata(self) -> dict[str, object]:
        return {
            "eligible_experiences": self.eligible_experiences,
            "sampled_events": self.sampled_events,
            "loss_total": self.loss_total,
            "last_loss": self.last_loss,
            "avg_loss": self.avg_loss,
            "target_action_counts": dict(sorted(self.target_action_counts.items())),
            "sampled_by_time_bucket": dict(sorted(self.sampled_by_time_bucket.items())),
        }


@dataclass(frozen=True)
class LowDefenseConfig:
    reward_shaping: bool = False
    hit_penalty: float = 0.5
    block_bonus: float = 0.2
    margin_loss: bool = False
    margin: float = 0.08
    loss_weight: float = 0.5
    batch_size: int = 0
    eligible_sources: frozenset[str] = field(default_factory=lambda: frozenset({"cpu-demo", "human-demo", "remote"}))
    valid_action_mask_mode: str = "action-start-v1"
    max_abs_dx: int = 144

    @property
    def reward_enabled(self) -> bool:
        return self.reward_shaping and (self.hit_penalty > 0.0 or self.block_bonus > 0.0)

    @property
    def margin_enabled(self) -> bool:
        return self.margin_loss and self.margin > 0.0 and self.loss_weight > 0.0

    @property
    def enabled(self) -> bool:
        return self.reward_enabled or self.margin_enabled

    def as_shared_mask_config(self) -> rl.DQNValidActionMaskConfig:
        return rl.parse_dqn_valid_action_mask_config(self.valid_action_mask_mode)

    def as_metadata(self) -> dict[str, object]:
        return {
            "reward_shaping": self.reward_shaping,
            "reward_enabled": self.reward_enabled,
            "hit_penalty": self.hit_penalty,
            "block_bonus": self.block_bonus,
            "margin_loss": self.margin_loss,
            "margin_enabled": self.margin_enabled,
            "margin": self.margin,
            "loss_weight": self.loss_weight,
            "batch_size": self.batch_size,
            "eligible_sources": sorted(self.eligible_sources),
            "valid_action_mask_mode": self.valid_action_mask_mode,
            "max_abs_dx": self.max_abs_dx,
            "low_attack_actions": sorted(LOW_DEFENSE_LOW_ATTACK_ACTIONS),
            "target_action": LOW_DEFENSE_TARGET_ACTION,
            "bad_actions": sorted(LOW_DEFENSE_BAD_ACTIONS),
        }


@dataclass
class LowDefenseStats:
    checked_rows: int = 0
    low_event_rows: int = 0
    hit_penalty_events: int = 0
    no_action_hit_penalty_events: int = 0
    block_bonus_events: int = 0
    reward_total: float = 0.0
    by_source_action: dict[str, int] = field(default_factory=dict)
    rewarded_source_results: set[tuple[int, int, int, str, str]] = field(default_factory=set, repr=False)
    eligible_experiences: int = 0
    sampled_events: int = 0
    violation_events: int = 0
    empty_valid_events: int = 0
    empty_target_events: int = 0
    empty_competitor_events: int = 0
    empty_context_events: int = 0
    loss_total: float = 0.0
    last_loss: float = 0.0
    avg_loss: float = 0.0
    sampled_by_time_bucket: dict[str, int] = field(default_factory=dict)
    violation_by_time_bucket: dict[str, int] = field(default_factory=dict)
    blocker_counts: dict[str, int] = field(default_factory=dict)

    @property
    def net_adjustment(self) -> float:
        return self.reward_total

    def as_metadata(self) -> dict[str, object]:
        return {
            "checked_rows": self.checked_rows,
            "low_event_rows": self.low_event_rows,
            "hit_penalty_events": self.hit_penalty_events,
            "no_action_hit_penalty_events": self.no_action_hit_penalty_events,
            "block_bonus_events": self.block_bonus_events,
            "reward_total": self.reward_total,
            "by_source_action": dict(sorted(self.by_source_action.items())),
            "rewarded_source_results": len(self.rewarded_source_results),
            "eligible_experiences": self.eligible_experiences,
            "sampled_events": self.sampled_events,
            "violation_events": self.violation_events,
            "empty_valid_events": self.empty_valid_events,
            "empty_target_events": self.empty_target_events,
            "empty_competitor_events": self.empty_competitor_events,
            "empty_context_events": self.empty_context_events,
            "loss_total": self.loss_total,
            "last_loss": self.last_loss,
            "avg_loss": self.avg_loss,
            "sampled_by_time_bucket": dict(sorted(self.sampled_by_time_bucket.items())),
            "violation_by_time_bucket": dict(sorted(self.violation_by_time_bucket.items())),
            "blocker_counts": dict(sorted(self.blocker_counts.items())),
        }


@dataclass
class ProjectileExpertQGapDiagnostics:
    rows: int = 0
    unique_rows: int = 0
    top1_matches: int = 0
    top5_matches: int = 0
    positive_gap_rows: int = 0
    invalid_expert_rows: int = 0
    empty_valid_rows: int = 0
    gap_sum: float = 0.0
    positive_gap_sum: float = 0.0
    gap_min: float | None = None
    gap_max: float | None = None
    expert_rank_sum: int = 0
    by_expert_action: dict[str, int] = field(default_factory=dict)
    top_action_counts: dict[str, int] = field(default_factory=dict)
    blocker_counts: dict[str, int] = field(default_factory=dict)
    rows_by_time_bucket: dict[str, int] = field(default_factory=dict)
    top1_by_time_bucket: dict[str, int] = field(default_factory=dict)
    positive_gap_by_time_bucket: dict[str, int] = field(default_factory=dict)
    top_action_counts_by_time_bucket: dict[str, dict[str, int]] = field(default_factory=dict)
    blocker_counts_by_time_bucket: dict[str, dict[str, int]] = field(default_factory=dict)

    @property
    def mean_gap(self) -> float:
        return self.gap_sum / self.rows if self.rows else 0.0

    @property
    def mean_positive_gap(self) -> float:
        return self.positive_gap_sum / self.positive_gap_rows if self.positive_gap_rows else 0.0

    @property
    def mean_expert_rank(self) -> float:
        return self.expert_rank_sum / self.rows if self.rows else 0.0

    def as_metadata(self) -> dict[str, object]:
        return {
            "rows": self.rows,
            "unique_rows": self.unique_rows,
            "top1_matches": self.top1_matches,
            "top5_matches": self.top5_matches,
            "positive_gap_rows": self.positive_gap_rows,
            "invalid_expert_rows": self.invalid_expert_rows,
            "empty_valid_rows": self.empty_valid_rows,
            "gap_sum": self.gap_sum,
            "mean_gap": self.mean_gap,
            "positive_gap_sum": self.positive_gap_sum,
            "mean_positive_gap": self.mean_positive_gap,
            "gap_min": self.gap_min if self.gap_min is not None else 0.0,
            "gap_max": self.gap_max if self.gap_max is not None else 0.0,
            "expert_rank_sum": self.expert_rank_sum,
            "mean_expert_rank": self.mean_expert_rank,
            "by_expert_action": dict(sorted(self.by_expert_action.items())),
            "top_action_counts": dict(sorted(self.top_action_counts.items())),
            "blocker_counts": dict(sorted(self.blocker_counts.items())),
            "rows_by_time_bucket": dict(sorted(self.rows_by_time_bucket.items())),
            "top1_by_time_bucket": dict(sorted(self.top1_by_time_bucket.items())),
            "positive_gap_by_time_bucket": dict(sorted(self.positive_gap_by_time_bucket.items())),
            "top_action_counts_by_time_bucket": {
                bucket: dict(sorted(counts.items()))
                for bucket, counts in sorted(self.top_action_counts_by_time_bucket.items())
            },
            "blocker_counts_by_time_bucket": {
                bucket: dict(sorted(counts.items()))
                for bucket, counts in sorted(self.blocker_counts_by_time_bucket.items())
            },
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


def apply_training_mode_hp_delta_mode(
    row: dict[str, object],
    mode: str,
    stats: BuildDiagnostics,
) -> None:
    if mode != "damage-only" or not rl.is_training_mode_transition_row(row):
        return
    self_delta = int_field(row, "delta_self_hp")
    opp_delta = int_field(row, "delta_opp_hp")
    changed = False
    if self_delta < 0:
        row["delta_self_hp"] = 0
        stats.training_mode_self_heal_ignored += -self_delta
        changed = True
    if opp_delta < 0:
        row["delta_opp_hp"] = 0
        stats.training_mode_opp_heal_ignored += -opp_delta
        changed = True
    if changed:
        stats.training_mode_hp_sanitized_rows += 1


def movable_action_filter_reason(row: dict[str, object]) -> str:
    if rl.dqn_action_start_allowed(row):
        return ""
    if "obs_self_ground_action_start_allowed" in row or "obs_self_air_attack_allowed" in row:
        return "self_action_start_not_allowed"
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


def parse_time_ranges(value: str, flag_name: str) -> tuple[tuple[int, int], ...]:
    ranges: list[tuple[int, int]] = []
    if not value.strip():
        return ()
    for item in value.split(","):
        token = item.strip()
        if not token:
            continue
        if "-" in token:
            raw_start, raw_end = (part.strip() for part in token.split("-", 1))
        else:
            raw_start = token
            raw_end = token
        try:
            start = max(0, int(raw_start))
            end = max(start, int(raw_end))
        except ValueError as exc:
            raise SystemExit(f"Invalid {flag_name} time range: {item!r}; expected START-END") from exc
        ranges.append((start, end))
    return tuple(ranges)


def format_time_ranges(ranges: tuple[tuple[int, int], ...]) -> list[str]:
    return [f"{start}-{end}" if start != end else str(start) for start, end in ranges]


def time_to_self_in_ranges(time_to_self: int, ranges: tuple[tuple[int, int], ...]) -> bool:
    return any(start <= time_to_self <= end for start, end in ranges)


def time_to_self_allowed(
    time_to_self: int,
    min_time_to_self: int,
    max_time_to_self: int,
    ranges: tuple[tuple[int, int], ...],
) -> bool:
    if ranges:
        return time_to_self_in_ranges(time_to_self, ranges)
    return min_time_to_self <= time_to_self <= max_time_to_self


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


def bc_event_weight_config_from_args(args: argparse.Namespace) -> BCEventWeightConfig:
    mode = str(args.bc_event_weighting)
    if mode not in BC_EVENT_WEIGHTING_MODES:
        raise SystemExit(
            f"unknown --bc-event-weighting {mode!r}; expected one of {','.join(BC_EVENT_WEIGHTING_MODES)}"
        )
    profile = str(args.bc_event_reward_profile)
    if profile not in combat_events.COMBAT_EVENT_REWARD_PROFILES:
        raise SystemExit(
            "unknown --bc-event-reward-profile "
            f"{profile!r}; expected one of {','.join(combat_events.COMBAT_EVENT_REWARD_PROFILES)}"
        )
    min_weight = max(0.0, float(args.bc_event_weight_min))
    max_weight = max(min_weight, float(args.bc_event_weight_max))
    return BCEventWeightConfig(
        mode=mode,
        reward_profile=profile,
        reward_scale=max(0.0, float(args.bc_event_reward_scale)),
        positive_scale=max(0.0, float(args.bc_event_weight_positive_scale)),
        negative_scale=max(0.0, float(args.bc_event_weight_negative_scale)),
        min_weight=min_weight,
        max_weight=max_weight,
    )


def bc_label_balance_config_from_args(args: argparse.Namespace) -> BCLabelBalanceConfig:
    mode = str(args.bc_label_balance)
    if mode not in BC_LABEL_BALANCE_MODES:
        raise SystemExit(
            f"unknown --bc-label-balance {mode!r}; expected one of {','.join(BC_LABEL_BALANCE_MODES)}"
        )
    min_weight = max(0.0, float(args.bc_label_balance_min))
    max_weight = max(min_weight, float(args.bc_label_balance_max))
    return BCLabelBalanceConfig(mode=mode, min_weight=min_weight, max_weight=max_weight)


def bc_family_margin_config_from_args(args: argparse.Namespace) -> BCFamilyMarginConfig:
    mode = str(args.bc_family_margin)
    if mode not in BC_FAMILY_MARGIN_MODES:
        raise SystemExit(
            f"unknown --bc-family-margin {mode!r}; expected one of {','.join(BC_FAMILY_MARGIN_MODES)}"
        )
    return BCFamilyMarginConfig(
        mode=mode,
        loss_weight=max(0.0, float(args.bc_family_margin_weight)),
        target_q_margin=max(0.0, float(args.bc_family_margin_target_margin)),
        min_positive_adjustment=max(0.0, float(args.bc_family_margin_min_positive_adjustment)),
        negative_actions=parse_action_name_set(
            str(args.bc_family_margin_negative_actions),
            "--bc-family-margin-negative-actions",
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
        "projectile": "projectile",
        "projectiles": "projectile",
        "proj": "projectile",
        "projectile-defense": "projectile",
        "projectile-def": "projectile",
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


def canonical_combat_event_batch_group_name(raw_group: str) -> str | None:
    normalized = raw_group.strip().lower().replace("_", "-")
    aliases = {
        "attack": "attack",
        "attacks": "attack",
        "normal": "attack",
        "normals": "attack",
        "special": "attack",
        "specials": "attack",
        "projectile": "projectile",
        "projectiles": "projectile",
        "fireball": "projectile",
        "fireballs": "projectile",
        "proj": "projectile",
        "defense": "defense",
        "defence": "defense",
        "defensive": "defense",
        "punish": "punish_throw",
        "punishes": "punish_throw",
        "throw": "punish_throw",
        "throws": "punish_throw",
        "punish-throw": "punish_throw",
        "punish+throw": "punish_throw",
        "movement": "movement",
        "move": "movement",
        "spacing": "movement",
        "unlabeled": "unlabeled_passive",
        "unlabelled": "unlabeled_passive",
        "passive": "unlabeled_passive",
        "unlabeled-passive": "unlabeled_passive",
    }
    return aliases.get(normalized)


def parse_combat_event_batch_ratios(value: str, flag_name: str) -> dict[str, float]:
    ratios: dict[str, float] = {group: 0.0 for group in COMBAT_EVENT_BATCH_GROUPS}
    if not value.strip():
        return ratios
    for raw_item in value.split(","):
        item = raw_item.strip()
        if not item:
            continue
        if "=" not in item:
            raise SystemExit(f"Invalid {flag_name} item: {item!r}; expected group=ratio")
        raw_group, raw_ratio = (part.strip() for part in item.split("=", 1))
        group = canonical_combat_event_batch_group_name(raw_group)
        if group is None:
            raise SystemExit(f"Unknown combat-event batch group in {flag_name}: {raw_group}")
        try:
            ratio = float(raw_ratio)
        except ValueError as exc:
            raise SystemExit(f"Invalid ratio for {group}: {raw_ratio}") from exc
        ratios[group] = max(0.0, ratio)
    total = sum(ratios.values())
    if total <= 0.0:
        raise SystemExit(f"{flag_name} must contain at least one positive ratio")
    return {group: ratios[group] / total for group in COMBAT_EVENT_BATCH_GROUPS}


def parse_positive_float_tuple(value: str, flag_name: str) -> tuple[float, ...]:
    weights: list[float] = []
    if not value.strip():
        raise SystemExit(f"{flag_name} must contain at least one positive value")
    for raw_item in value.split(","):
        item = raw_item.strip()
        if not item:
            continue
        try:
            weight = float(item)
        except ValueError as exc:
            raise SystemExit(f"Invalid {flag_name} value: {item}") from exc
        if weight > 0.0:
            weights.append(weight)
    if not weights:
        raise SystemExit(f"{flag_name} must contain at least one positive value")
    return tuple(weights)


def batch_sampling_config_from_args(args: argparse.Namespace) -> BatchSamplingConfig:
    mode = str(args.batch_sampling)
    if mode not in BATCH_SAMPLING_MODES:
        raise SystemExit(f"unknown --batch-sampling {mode!r}; expected one of {','.join(BATCH_SAMPLING_MODES)}")
    ratios = parse_batch_ratios(str(args.balanced_batch_ratios), "--balanced-batch-ratios")
    return BatchSamplingConfig(mode=mode, ratios=ratios)


def combat_event_batch_sampling_config_from_args(args: argparse.Namespace) -> CombatEventBatchSamplingConfig:
    mode = str(args.combat_event_batch_sampling)
    if mode not in combat_events.COMBAT_EVENT_BATCH_SAMPLING_MODES:
        raise SystemExit(
            f"unknown --combat-event-batch-sampling {mode!r}; "
            f"expected one of {','.join(combat_events.COMBAT_EVENT_BATCH_SAMPLING_MODES)}"
        )
    ratios = (
        parse_combat_event_batch_ratios(str(args.combat_event_batch_ratios), "--combat-event-batch-ratios")
        if mode != "off"
        else {group: 0.0 for group in COMBAT_EVENT_BATCH_GROUPS}
    )
    return CombatEventBatchSamplingConfig(mode=mode, ratios=ratios)


def combat_event_movement_credit_config_from_args(args: argparse.Namespace) -> CombatEventMovementCreditConfig:
    mode = str(args.combat_event_movement_credit)
    if mode not in combat_events.COMBAT_EVENT_MOVEMENT_CREDIT_MODES:
        raise SystemExit(
            f"unknown --combat-event-movement-credit {mode!r}; "
            f"expected one of {','.join(combat_events.COMBAT_EVENT_MOVEMENT_CREDIT_MODES)}"
        )
    return CombatEventMovementCreditConfig(
        mode=mode,
        window_decisions=max(0, int(args.combat_event_movement_credit_window)),
        max_rows=max(0, int(args.combat_event_movement_credit_max_rows)),
        scale=max(0.0, float(args.combat_event_movement_credit_scale)),
        decay=parse_positive_float_tuple(
            str(args.combat_event_movement_credit_decay),
            "--combat-event-movement-credit-decay",
        ),
        row_abs_cap=max(0.0, float(args.combat_event_movement_credit_row_cap)),
    )


def projectile_batch_config_from_args(args: argparse.Namespace) -> ProjectileBatchConfig:
    min_time = max(0, int(args.projectile_batch_min_time_to_self))
    max_time = max(min_time, int(args.projectile_batch_max_time_to_self))
    safe_min_time = max(0, int(args.projectile_batch_safe_jump_min_time_to_self))
    safe_max_time = max(safe_min_time, int(args.projectile_batch_safe_jump_max_time_to_self))
    return ProjectileBatchConfig(
        requested=bool(args.projectile_batch_group),
        min_time_to_self=min_time,
        max_time_to_self=max_time,
        time_ranges=parse_time_ranges(str(args.projectile_batch_time_ranges), "--projectile-batch-time-ranges"),
        window_decisions=max(0, int(args.projectile_batch_window_decisions)),
        max_self_hp=max(0, int(args.projectile_batch_max_self_hp)),
        eligible_sources=parse_source_name_set(str(args.projectile_batch_sources), "--projectile-batch-sources"),
        include_late_jump_hit=bool(args.projectile_batch_include_late_jump_hit),
        include_safe_jump=bool(args.projectile_batch_include_safe_jump),
        safe_jump_min_time_to_self=safe_min_time,
        safe_jump_max_time_to_self=safe_max_time,
    )


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


def dqn_unsupported_action_regularization_config_from_args(
    args: argparse.Namespace,
) -> DQNUnsupportedActionRegularizationConfig:
    return DQNUnsupportedActionRegularizationConfig(
        requested=bool(args.dqn_unsupported_action_regularization),
        min_action_count=max(0, int(args.dqn_unsupported_action_min_count)),
        q_ceiling=float(args.dqn_unsupported_action_q_ceiling),
        loss_weight=max(0.0, float(args.dqn_unsupported_action_loss_weight)),
        adaptive_ceiling=bool(args.dqn_unsupported_action_adaptive_ceiling),
    )


def parse_movement_regression_action_groups(value: str) -> frozenset[str]:
    groups: set[str] = set()
    if not value.strip():
        return frozenset()
    invalid: list[str] = []
    for raw_item in value.split(","):
        group = raw_item.strip()
        if not group:
            continue
        if group not in MOVEMENT_REGRESSION_ACTION_GROUPS:
            invalid.append(group)
        else:
            groups.add(group)
    if invalid:
        raise SystemExit(
            "--movement-regression-action-groups contains unknown groups: "
            f"{','.join(invalid)}; expected {','.join(sorted(MOVEMENT_REGRESSION_ACTION_GROUPS))}"
        )
    return frozenset(groups)


def movement_regression_loss_config_from_args(args: argparse.Namespace) -> MovementRegressionLossConfig:
    return MovementRegressionLossConfig(
        loss_weight=max(0.0, float(args.movement_regression_loss_weight)),
        target_q_margin=max(0.0, float(args.movement_regression_target_q_margin)),
        far_dx_threshold=max(0, int(args.movement_regression_far_dx_threshold)),
        action_groups=parse_movement_regression_action_groups(str(args.movement_regression_action_groups)),
        exclude_special_expert_eligible=bool(args.movement_regression_exclude_special_expert_eligible),
    )


def dqn_valid_action_mask_training_config_from_args(args: argparse.Namespace) -> DQNValidActionMaskTrainingConfig:
    config = rl.parse_dqn_valid_action_mask_config(str(args.dqn_valid_action_mask))
    return DQNValidActionMaskTrainingConfig(mode=config.mode)


def action_batch_group(action_name: str) -> str:
    if action_name in NON_ATTACK_ACTIONS or action_name in JUMP_START_ACTIONS:
        return "movement"
    if action_name.startswith(SPECIAL_ACTION_PREFIXES):
        return "special"
    return "normal"


def experience_batch_group(exp: Experience, actions: tuple[str, ...]) -> str:
    if exp.projectile_batch_eligible:
        return "projectile"
    if 0 <= exp.action_index < len(actions):
        return action_batch_group(actions[exp.action_index])
    return "normal"


def combat_event_batch_group_for_transition(
    row: dict[str, object],
    action_name: str,
    action_start: bool,
    reward: float,
    projectile_response_outcome_result: ProjectileResponseOutcome,
    combat_event_validation: combat_events.CombatEventTrainingValidation | None,
) -> str:
    label = combat_events.transition_label_for_row(
        combat_event_validation.index if combat_event_validation is not None else None,
        row,
        action_start,
    )
    source_kinds = set(label.source_event_kinds)

    if "throw" in source_kinds or "punish" in source_kinds or action_name == "throw":
        return "punish_throw"
    if "projectile" in source_kinds or action_name.startswith("fireball-"):
        return "projectile"
    if "attack" in source_kinds:
        return "attack"

    if action_name not in UNLABELED_MOVEMENT_FILTER_ACTIONS:
        return "projectile" if action_name.startswith("fireball-") else "attack"

    if label.has_defensive_attribution:
        return "defense"
    if projectile_response_outcome_result.threat or incoming_projectile_threat_for_filter(row):
        return "defense"
    if label.has_source_event or reward != 0.0 or has_hp_or_stun_delta(row) or bool(row.get("done", False)):
        return "movement"
    return "unlabeled_passive"


def combat_event_movement_credit_kind(
    row: dict[str, object],
    action_name: str | None,
    action_start: bool,
    combat_event_reward_adjustment: float,
    combat_event_validation: combat_events.CombatEventTrainingValidation | None,
) -> tuple[str, frozenset[str]]:
    if combat_event_reward_adjustment == 0.0 or action_name is None:
        return "", frozenset()
    label = combat_events.transition_label_for_row(
        combat_event_validation.index if combat_event_validation is not None else None,
        row,
        action_start,
    )
    source_kinds = set(label.source_event_kinds)
    defensive_results = set(label.defensive_results)
    has_self_source = bool(source_kinds.intersection({"attack", "projectile", "throw"}))
    has_defense = bool(defensive_results)

    # Mixed offense/defense rows are valid combat rows, but too ambiguous for
    # this first delayed movement credit pass.
    if has_self_source and has_defense:
        return "", frozenset()

    if has_self_source and combat_event_reward_adjustment > 0.0:
        return "self_offense_success", COMBAT_EVENT_MOVEMENT_CREDIT_FORWARD_ACTIONS
    if defensive_results.intersection({"blocked", "parry", "evaded"}) and combat_event_reward_adjustment > 0.0:
        return (
            "defense_success",
            COMBAT_EVENT_MOVEMENT_CREDIT_BACK_ACTIONS | COMBAT_EVENT_MOVEMENT_CREDIT_NEUTRAL_JUMP_ACTIONS,
        )
    if defensive_results.intersection({"hit", "thrown", "blocked_chip"}) and combat_event_reward_adjustment < 0.0:
        return (
            "defense_failure",
            COMBAT_EVENT_MOVEMENT_CREDIT_FORWARD_ACTIONS | COMBAT_EVENT_MOVEMENT_CREDIT_NEUTRAL_JUMP_ACTIONS,
        )
    return "", frozenset()


def combat_event_movement_credit_weights(config: CombatEventMovementCreditConfig, count: int) -> list[float]:
    if count <= 0:
        return []
    weights = list(config.decay[:count])
    while len(weights) < count:
        weights.append(weights[-1] * 0.5)
    total = sum(weights)
    if total <= 0.0:
        return []
    return [weight / total for weight in weights]


def apply_combat_event_movement_credit(
    experiences: list[Experience],
    actions: tuple[str, ...],
    row: dict[str, object],
    action_name: str | None,
    action_start: bool,
    combat_event_reward_adjustment: float,
    reward_scale: float,
    combat_event_validation: combat_events.CombatEventTrainingValidation | None,
    config: CombatEventMovementCreditConfig,
    stats: CombatEventMovementCreditStats,
    action_rewards: dict[str, float],
    source_stats: SourceReplayDiagnostics | None = None,
) -> None:
    if not config.enabled:
        return
    stats.checked_anchor_rows += 1
    if combat_event_reward_adjustment == 0.0:
        stats.skipped_no_reward += 1
        return

    reason, allowed_actions = combat_event_movement_credit_kind(
        row,
        action_name,
        action_start,
        combat_event_reward_adjustment,
        combat_event_validation,
    )
    if not reason or not allowed_actions:
        stats.skipped_no_label += 1
        return

    anchor_decision_id = int_field(row, "decision_id")
    anchor_episode = episode_key(row)
    candidates: list[int] = []
    for exp_index in range(len(experiences) - 1, -1, -1):
        exp = experiences[exp_index]
        exp_row = exp.row
        if episode_key(exp_row) != anchor_episode:
            break
        prior_decision_id = int_field(exp_row, "decision_id")
        if anchor_decision_id - prior_decision_id > config.window_decisions:
            break
        prior_action = actions[exp.action_index]
        if exp.combat_event_batch_group in ("attack", "projectile", "punish_throw"):
            stats.skipped_cross_source_boundary += 1
            break
        if prior_action not in COMBAT_EVENT_MOVEMENT_CREDIT_ACTIONS:
            continue
        stats.candidate_rows += 1
        if prior_action not in allowed_actions:
            stats.skipped_direction_mismatch += 1
            continue
        candidates.append(exp_index)
        if len(candidates) >= config.max_rows:
            break

    if not candidates:
        stats.skipped_no_candidate += 1
        return

    weights = combat_event_movement_credit_weights(config, len(candidates))
    if not weights:
        stats.skipped_no_candidate += 1
        return

    budget = combat_event_reward_adjustment * reward_scale * config.scale
    if budget == 0.0:
        stats.skipped_no_reward += 1
        return

    applied_for_anchor = False
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
                credit = math.copysign(remaining_abs, credit)
                stats.capped_rows += 1
            stats.credit_abs_by_exp_index[exp_index] = used_abs + abs(credit)
        if add_delayed_reward(experiences, exp_index, credit, actions, action_rewards, source_stats):
            prior_action = actions[experiences[exp_index].action_index]
            stats.add_credit(prior_action, reason, credit)
            applied_for_anchor = True

    if applied_for_anchor:
        stats.applied_anchor_rows += 1


def build_batch_pools(
    experiences: list[Experience],
    actions: tuple[str, ...],
) -> dict[str, list[Experience]]:
    pools: dict[str, list[Experience]] = {group: [] for group in BATCH_GROUPS}
    for exp in experiences:
        if 0 <= exp.action_index < len(actions):
            pools[experience_batch_group(exp, actions)].append(exp)
    return pools


def build_combat_event_batch_pools(
    experiences: list[Experience],
) -> dict[str, list[Experience]]:
    pools: dict[str, list[Experience]] = {group: [] for group in COMBAT_EVENT_BATCH_GROUPS}
    for exp in experiences:
        group = exp.combat_event_batch_group
        if group not in pools:
            group = "unlabeled_passive"
        pools[group].append(exp)
    return pools


def projectile_batch_stats_from_experiences(
    experiences: list[Experience],
    actions: tuple[str, ...],
) -> ProjectileBatchStats:
    stats = ProjectileBatchStats()
    for exp in experiences:
        stats.add(exp, actions)
    return stats


def balanced_target_counts_for_groups(
    batch_size: int,
    ratios: dict[str, float],
    groups: tuple[str, ...],
) -> dict[str, int]:
    raw_counts = {group: max(0.0, ratios.get(group, 0.0)) * batch_size for group in groups}
    counts = {group: int(math.floor(raw_counts[group])) for group in groups}
    remaining = max(0, batch_size - sum(counts.values()))
    remainders = sorted(
        ((raw_counts[group] - counts[group], group) for group in groups),
        key=lambda item: (item[0], item[1]),
        reverse=True,
    )
    for index in range(remaining):
        counts[remainders[index % len(remainders)][1]] += 1
    return counts


def balanced_target_counts(batch_size: int, ratios: dict[str, float]) -> dict[str, int]:
    return balanced_target_counts_for_groups(batch_size, ratios, BATCH_GROUPS)


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


def combat_event_batch_sampling_diagnostics(
    experiences: list[Experience],
    batch_size: int,
    config: CombatEventBatchSamplingConfig,
) -> CombatEventBatchSamplingDiagnostics:
    pools = build_combat_event_batch_pools(experiences)
    return CombatEventBatchSamplingDiagnostics(
        mode=config.mode,
        ratios=dict(config.ratios),
        pool_counts={group: len(pools[group]) for group in COMBAT_EVENT_BATCH_GROUPS},
        target_counts=(
            balanced_target_counts_for_groups(batch_size, config.ratios, COMBAT_EVENT_BATCH_GROUPS)
            if config.enabled
            else {}
        ),
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


def sample_grouped_training_batch(
    experiences: list[Experience],
    pools: dict[str, list[Experience]],
    groups: tuple[str, ...],
    target_counts: dict[str, int],
    batch_size: int,
    rng: random.Random,
) -> list[Experience]:
    batch: list[Experience] = []
    fallback_pool = experiences
    for group in groups:
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
    apply_air_attack_cost = config.profile == "all-attacks" and action_name in AIR_ATTACK_RISK_ACTIONS
    if not apply_attack_cost and not apply_shoryuken_cost and not apply_air_attack_cost:
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

    fireball_made_contact = (
        action_name.startswith("fireball-")
        and (
            any(int_field(window_row, "obs_opp_contact_reaction_state") != 0 for window_row in lookahead)
            or any(int_field(window_row, "obs_projectile_owner") == PROJECTILE_OWNER_OPPONENT for window_row in lookahead)
        )
    )

    cost = 0.0
    if not fireball_made_contact:
        stats.no_damage_cost_events += 1

    if apply_attack_cost:
        if not fireball_made_contact:
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

    if apply_air_attack_cost:
        cost += config.jump_attack_no_damage_extra_cost
        stats.jump_attack_no_damage_extra_cost_total += config.jump_attack_no_damage_extra_cost
        if punished:
            cost += config.jump_attack_punished_extra_cost
            stats.jump_attack_punished_extra_cost_total += config.jump_attack_punished_extra_cost

    if punished:
        stats.punished_cost_events += 1

    if action_name == "throw" and config.throw_far_cost > 0.0:
        row = episode_rows[row_index]
        abs_dx = int_field(row, "obs_abs_dx")
        if abs_dx > config.throw_far_max_abs_dx:
            cost += config.throw_far_cost
            stats.throw_far_cost_events += 1
            stats.throw_far_cost_total += config.throw_far_cost

    return cost


def reward_guard_adjustment(
    episode_rows: list[dict[str, object]],
    row_index: int,
    action_name: str,
    action_start: bool,
    config: RewardGuardConfig,
    stats: RewardGuardStats,
) -> float:
    row = episode_rows[row_index]
    if action_name not in GUARD_ACTIONS or not action_start:
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


def incoming_projectile_threat(row: dict[str, object], config: RewardProjectileResponseConfig) -> bool:
    if not config.enabled:
        return False
    if int_field(row, "obs_projectile_active") == 0:
        return False
    if int_field(row, "obs_projectile_owner") != PROJECTILE_OWNER_OPPONENT:
        return False

    rel_x = int_field(row, "obs_projectile_rel_x")
    rel_y = int_field(row, "obs_projectile_rel_y")
    vel_x = int_field(row, "obs_projectile_vel_x")
    time_to_self = int_field(row, "obs_projectile_time_to_self")
    return (
        rel_x > 0
        and rel_x <= config.threat_max_dx
        and abs(rel_y) <= config.threat_max_abs_y
        and vel_x < 0
        and config.threat_min_time_to_self <= time_to_self <= config.threat_max_time_to_self
    )


def has_hp_or_stun_delta(row: dict[str, object]) -> bool:
    return any(
        int_field(row, field_name) != 0
        for field_name in ("delta_self_hp", "delta_opp_hp", "delta_self_stun", "delta_opp_stun")
    )


def incoming_projectile_threat_for_filter(row: dict[str, object]) -> bool:
    if int_field(row, "obs_projectile_active") == 0:
        return False
    if int_field(row, "obs_projectile_owner") != PROJECTILE_OWNER_OPPONENT:
        return False

    rel_x = int_field(row, "obs_projectile_rel_x")
    rel_y = int_field(row, "obs_projectile_rel_y")
    vel_x = int_field(row, "obs_projectile_vel_x")
    time_to_self = int_field(row, "obs_projectile_time_to_self")
    return (
        rel_x > 0
        and rel_x <= 240
        and abs(rel_y) <= 48
        and vel_x < 0
        and 1 <= time_to_self <= 24
    )


def movement_spacing_filter_reason(
    episode_rows: list[dict[str, object]],
    row_index: int,
    action_name: str,
) -> str:
    if action_name not in MOVEMENT_SPACING_ACTIONS:
        return ""
    next_boundary = next_decision_boundary_row(episode_rows, row_index)
    if next_boundary is None:
        return ""

    _, next_row = next_boundary
    current_dx = int_field(episode_rows[row_index], "obs_abs_dx")
    next_dx = int_field(next_row, "obs_abs_dx")
    window_rows = episode_rows[row_index : next_boundary[0] + 1]
    clean_window = not any(
        int_field(window_row, "delta_self_hp") != 0 or int_field(window_row, "delta_self_stun") != 0
        for window_row in window_rows
    )
    if not clean_window:
        return ""
    if action_name == "back" and next_dx >= current_dx + 8:
        return "back_spacing_success"
    if action_name == "forward" and next_dx <= current_dx - 8:
        return "forward_engage_success"
    return ""


def deterministic_keep_unlabeled_movement(
    row: dict[str, object],
    action_name: str,
    config: CombatEventUnlabeledMovementFilterConfig,
) -> bool:
    if config.policy == "keep":
        return True
    if config.policy == "drop":
        return False
    if config.keep_ratio >= 1.0:
        return True
    if config.keep_ratio <= 0.0:
        return False
    key = ":".join(
        str(value)
        for value in (
            config.seed,
            int_field(row, "run_id"),
            int_field(row, "episode_id"),
            int_field(row, "decision_id"),
            int_field(row, "obs_frame"),
            int_field(row, "input_action_id"),
            int_field(row, "policy_executed_action_id"),
            action_name,
        )
    )
    digest = hashlib.sha256(key.encode("ascii")).digest()
    value = int.from_bytes(digest[:8], "big") / float(1 << 64)
    return value < config.keep_ratio


def should_drop_unlabeled_movement_transition(
    episode_rows: list[dict[str, object]],
    row_index: int,
    row: dict[str, object],
    action_name: str,
    action_start: bool,
    reward: float,
    projectile_response_outcome_result: ProjectileResponseOutcome,
    combat_event_validation: combat_events.CombatEventTrainingValidation | None,
    config: CombatEventUnlabeledMovementFilterConfig,
    stats: CombatEventUnlabeledMovementFilterStats,
) -> bool:
    if not config.enabled:
        return False
    if not action_start or action_name not in UNLABELED_MOVEMENT_FILTER_ACTIONS:
        return False

    stats.add_checked(action_name)
    label = combat_events.transition_label_for_row(
        combat_event_validation.index if combat_event_validation is not None else None,
        row,
        action_start,
    )
    protected_reasons: list[str] = []
    if label.has_source_event:
        protected_reasons.append("source_event")
    if label.has_defensive_attribution:
        protected_reasons.append("defense_attribution")
    if reward != 0.0:
        protected_reasons.append("nonzero_reward")
    if has_hp_or_stun_delta(row):
        protected_reasons.append("hp_or_stun_delta")
    if bool(row.get("done", False)):
        protected_reasons.append("done")
    if projectile_response_outcome_result.threat or incoming_projectile_threat_for_filter(row):
        protected_reasons.append("incoming_projectile_threat")
    spacing_reason = movement_spacing_filter_reason(episode_rows, row_index, action_name)
    if spacing_reason:
        protected_reasons.append(spacing_reason)

    if protected_reasons:
        stats.add_protected(action_name, protected_reasons)
        return False

    kept = deterministic_keep_unlabeled_movement(row, action_name, config)
    stats.add_unlabeled(action_name, kept)
    return not kept


def projectile_cleared_or_passed(row: dict[str, object], config: RewardProjectileResponseConfig) -> bool:
    if not incoming_projectile_threat(row, config):
        return True
    return int_field(row, "obs_projectile_rel_x") <= 0


def projectile_response_outcome(
    episode_rows: list[dict[str, object]],
    row_index: int,
    action_name: str,
    config: RewardProjectileResponseConfig,
) -> ProjectileResponseOutcome:
    row = episode_rows[row_index]
    if not config.enabled or not is_action_start(row) or not incoming_projectile_threat(row, config):
        return ProjectileResponseOutcome()
    if action_name not in JUMP_START_ACTIONS and action_name != "back" and action_name not in GUARD_ACTIONS:
        return ProjectileResponseOutcome()

    window_end = min(len(episode_rows), row_index + max(0, config.window_decisions) + 1)
    lookahead = episode_rows[row_index:window_end]
    self_damage = sum(int_field(lookahead_row, "delta_self_hp") for lookahead_row in lookahead)
    clean_window = self_damage == 0

    if action_name in JUMP_START_ACTIONS:
        became_airborne = any(
            int_field(lookahead_row, "obs_self_airborne") != 0
            or int_field(lookahead_row, "obs_self_jump_phase") >= 2
            for lookahead_row in lookahead
        )
        projectile_cleared = any(projectile_cleared_or_passed(lookahead_row, config) for lookahead_row in lookahead[1:])
        return ProjectileResponseOutcome(
            threat=True,
            safe_jump=clean_window and became_airborne and projectile_cleared,
            late_jump_hit=self_damage > 0,
        )

    current_dx = int_field(row, "obs_abs_dx")
    if current_dx > config.close_max_dx:
        return ProjectileResponseOutcome(threat=True)

    close_back_success = False
    if action_name == "back" and clean_window:
        next_boundary = next_decision_boundary_row(episode_rows, row_index)
        next_row = next_boundary[1] if next_boundary is not None else lookahead[-1]
        next_dx = int_field(next_row, "obs_abs_dx")
        close_back_success = (
            next_dx >= current_dx + config.back_escape_min_dx_delta
            or any(projectile_cleared_or_passed(lookahead_row, config) for lookahead_row in lookahead[1:])
        )

    close_guard_success = False
    if action_name in GUARD_ACTIONS and clean_window:
        guard_contact = any(
            int_field(lookahead_row, "obs_self_contact_reaction_state") != 0 for lookahead_row in lookahead
        )
        close_guard_success = guard_contact or not config.guard_require_contact

    return ProjectileResponseOutcome(
        threat=True,
        close_back_success=close_back_success,
        close_guard_success=close_guard_success,
    )


def reward_projectile_response_adjustment(
    episode_rows: list[dict[str, object]],
    row_index: int,
    action_name: str,
    config: RewardProjectileResponseConfig,
    stats: RewardProjectileResponseStats,
) -> tuple[float, ProjectileResponseOutcome]:
    outcome = projectile_response_outcome(episode_rows, row_index, action_name, config)
    if not outcome.threat:
        return 0.0, outcome

    stats.threat_action_rows += 1
    adjustment = 0.0
    if outcome.safe_jump and config.safe_jump_bonus > 0.0:
        adjustment += config.safe_jump_bonus
        stats.safe_jump_bonus_events += 1
        stats.safe_jump_bonus_total += config.safe_jump_bonus
    if outcome.late_jump_hit and config.late_jump_hit_cost > 0.0:
        adjustment -= config.late_jump_hit_cost
        stats.late_jump_hit_cost_events += 1
        stats.late_jump_hit_cost_total += config.late_jump_hit_cost
    if outcome.close_back_success and config.close_back_success_bonus > 0.0:
        adjustment += config.close_back_success_bonus
        stats.close_back_success_bonus_events += 1
        stats.close_back_success_bonus_total += config.close_back_success_bonus
    if outcome.close_guard_success and config.close_guard_success_bonus > 0.0:
        adjustment += config.close_guard_success_bonus
        stats.close_guard_success_bonus_events += 1
        stats.close_guard_success_bonus_total += config.close_guard_success_bonus
    return adjustment, outcome


def projectile_expert_margin_eligible(
    row: dict[str, object],
    source_name: str,
    action_name: str,
    outcome: ProjectileResponseOutcome,
    config: ProjectileExpertMarginConfig,
) -> bool:
    if not config.requested:
        return False
    if source_name not in config.eligible_sources:
        return False
    if action_name not in JUMP_START_ACTIONS:
        return False
    if not outcome.threat:
        return False
    if config.require_safe_jump and not outcome.safe_jump:
        return False
    if outcome.late_jump_hit:
        return False
    time_to_self = int_field(row, "obs_projectile_time_to_self")
    if not time_to_self_allowed(
        time_to_self,
        config.min_time_to_self,
        config.max_time_to_self,
        config.time_ranges,
    ):
        return False
    return True


def special_expert_margin_eligible(
    action_name: str,
    source_name: str,
    reward: float,
    config: SpecialExpertMarginConfig,
) -> bool:
    if not config.requested:
        return False
    if source_name not in config.eligible_sources:
        return False
    if action_name not in SPECIAL_ACTIONS:
        return False
    return reward >= config.min_reward


def projectile_late_defensive_margin_eligible(
    row: dict[str, object],
    source_name: str,
    action_name: str,
    outcome: ProjectileResponseOutcome,
    config: ProjectileLateDefensiveMarginConfig,
) -> bool:
    if not config.requested:
        return False
    if source_name not in config.eligible_sources:
        return False
    if action_name not in JUMP_START_ACTIONS:
        return False
    if not outcome.threat or not outcome.late_jump_hit:
        return False
    time_to_self = int_field(row, "obs_projectile_time_to_self")
    if time_to_self < config.min_time_to_self or time_to_self > config.max_time_to_self:
        return False
    return True


def projectile_batch_reason(
    episode_rows: list[dict[str, object]],
    row_index: int,
    row: dict[str, object],
    source_name: str,
    action_name: str,
    outcome: ProjectileResponseOutcome,
    config: ProjectileBatchConfig,
) -> str:
    if not config.enabled:
        return ""
    if source_name not in config.eligible_sources:
        return ""
    if not outcome.threat:
        return ""
    time_to_self = int_field(row, "obs_projectile_time_to_self")

    if action_name in DEFENSIVE_PROJECTILE_ACTIONS:
        if not time_to_self_allowed(
            time_to_self,
            config.min_time_to_self,
            config.max_time_to_self,
            config.time_ranges,
        ):
            return ""
        window_end = min(len(episode_rows), row_index + max(0, config.window_decisions) + 1)
        lookahead = episode_rows[row_index:window_end]
        self_damage = sum(int_field(lookahead_row, "delta_self_hp") for lookahead_row in lookahead)
        if self_damage <= config.max_self_hp:
            return "defensive-clean"
        return ""

    if (
        config.include_late_jump_hit
        and action_name in JUMP_START_ACTIONS
        and outcome.late_jump_hit
        and time_to_self_allowed(
            time_to_self,
            config.min_time_to_self,
            config.max_time_to_self,
            config.time_ranges,
        )
    ):
        return "late-jump-hit"

    if (
        config.include_safe_jump
        and action_name in JUMP_START_ACTIONS
        and outcome.safe_jump
        and config.safe_jump_min_time_to_self <= time_to_self <= config.safe_jump_max_time_to_self
    ):
        return "safe-jump"

    return ""


def projectile_defensive_expert_margin_eligible(
    episode_rows: list[dict[str, object]],
    row_index: int,
    row: dict[str, object],
    source_name: str,
    action_name: str,
    outcome: ProjectileResponseOutcome,
    config: ProjectileDefensiveExpertMarginConfig,
) -> bool:
    if not config.requested:
        return False
    if source_name not in config.eligible_sources:
        return False
    if action_name not in DEFENSIVE_PROJECTILE_ACTIONS:
        return False
    if not outcome.threat:
        return False
    time_to_self = int_field(row, "obs_projectile_time_to_self")
    if not time_to_self_allowed(
        time_to_self,
        config.min_time_to_self,
        config.max_time_to_self,
        config.time_ranges,
    ):
        return False

    window_end = min(len(episode_rows), row_index + max(0, config.window_decisions) + 1)
    lookahead = episode_rows[row_index:window_end]
    self_damage = sum(int_field(lookahead_row, "delta_self_hp") for lookahead_row in lookahead)
    if self_damage > config.max_self_hp:
        return False
    return True


def is_grounded_normal_defense_context(row: dict[str, object], config: GroundedNormalDefenseMarginConfig) -> bool:
    """Return True if row is a grounded opponent-normal attack threat frame."""
    opp_r1 = int_field(row, "obs_opp_routine_1")
    opp_r2 = int_field(row, "obs_opp_routine_2")
    if opp_r1 != 4 or opp_r2 in (16, 17, 18):
        return False
    opp_contact = int_field(row, "obs_opp_contact_reaction_state")
    if opp_contact != 0:
        return False
    self_air = int_field(row, "obs_self_airborne")
    self_jump = int_field(row, "obs_self_jump_phase")
    if self_air != 0 or self_jump != 0:
        return False
    self_contact = int_field(row, "obs_self_contact_reaction_state")
    if self_contact != 0:
        return False
    abs_dx = int_field(row, "obs_abs_dx")
    if abs_dx > config.max_abs_dx:
        return False
    return True


def grounded_normal_defense_eligible(
    row: dict[str, object],
    source_name: str,
    action_name: str,
    config: GroundedNormalDefenseMarginConfig,
) -> bool:
    if not config.requested:
        return False
    if source_name not in config.eligible_sources:
        return False
    if action_name not in GROUNDED_NORMAL_DEFENSE_SAFE_ACTIONS and action_name not in GROUNDED_NORMAL_DEFENSE_UNSAFE_ACTIONS:
        return False
    return is_grounded_normal_defense_context(row, config)


def grounded_normal_defense_bc_eligible(
    row: dict[str, object],
    source_name: str,
    action_name: str,
    config: GroundedNormalDefenseBCConfig,
) -> bool:
    if not config.requested:
        return False
    if source_name not in config.eligible_sources:
        return False
    if action_name not in GROUNDED_NORMAL_DEFENSE_SAFE_ACTIONS:
        return False
    return is_grounded_normal_defense_context(row, GroundedNormalDefenseMarginConfig(max_abs_dx=config.max_abs_dx))


def combat_event_policy_action_name(event: dict[str, object]) -> str:
    for prefix in ("engine", "policy"):
        action_name = rl.action_name_from_policy_meta(
            int_field(event, f"{prefix}_action_id"),
            int_field(event, f"{prefix}_sub_action_id"),
        )
        if action_name:
            return action_name
    return ""


def low_defense_attributions_for_row(
    index: combat_events.CombatEventIndex | None,
    row: dict[str, object],
    max_abs_dx: int,
) -> list[tuple[dict[str, object], dict[str, object], str]]:
    if index is None:
        return []
    if int_field(row, "obs_abs_dx") > max_abs_dx:
        return []

    key = (
        int_field(row, "run_id"),
        int_field(row, "episode_id"),
        int_field(row, "decision_id"),
    )
    matches: list[tuple[dict[str, object], dict[str, object], str]] = []
    for attribution in index.by_decision.get(key, []):
        if str(attribution.get("event_kind", "")) != "attribution":
            continue
        if str(attribution.get("target_side", "")) != "self":
            continue
        if str(attribution.get("source_family", "")) != "attack":
            continue
        if str(attribution.get("failure_reason", "none")) != "none":
            continue
        defense_result = str(attribution.get("defense_result", "unknown"))
        if defense_result not in ("hit", "blocked", "blocked_chip"):
            continue
        source_event_id = int_field(attribution, "source_event_id")
        if source_event_id <= 0:
            continue
        source_event = index.by_event_key.get(
            (
                int_field(attribution, "run_id"),
                int_field(attribution, "episode_id"),
                source_event_id,
            )
        )
        if source_event is None or str(source_event.get("event_kind", "")) != "attack":
            continue
        source_action = combat_event_policy_action_name(source_event)
        if source_action not in LOW_DEFENSE_LOW_ATTACK_ACTIONS:
            continue
        matches.append((attribution, source_event, source_action))
    return matches


def low_defense_context_for_row(
    row: dict[str, object],
    combat_event_validation: combat_events.CombatEventTrainingValidation | None,
    config: LowDefenseConfig,
) -> bool:
    if combat_event_validation is None:
        return False
    return bool(low_defense_attributions_for_row(combat_event_validation.index, row, config.max_abs_dx))


def low_defense_reward_adjustment(
    row: dict[str, object],
    action_name: str | None,
    combat_event_validation: combat_events.CombatEventTrainingValidation | None,
    config: LowDefenseConfig,
    stats: LowDefenseStats,
) -> float:
    if not config.reward_enabled or combat_event_validation is None:
        return 0.0

    stats.checked_rows += 1
    adjustment = 0.0
    for attribution, _source_event, source_action in low_defense_attributions_for_row(
        combat_event_validation.index,
        row,
        config.max_abs_dx,
    ):
        stats.low_event_rows += 1
        stats.by_source_action[source_action] = stats.by_source_action.get(source_action, 0) + 1
        defense_result = str(attribution.get("defense_result", "unknown"))
        reward_key = (
            int_field(attribution, "run_id"),
            int_field(attribution, "episode_id"),
            int_field(attribution, "source_event_id"),
            defense_result,
            action_name or "none",
        )
        if reward_key in stats.rewarded_source_results:
            continue
        stats.rewarded_source_results.add(reward_key)

        if defense_result == "hit" and (action_name in LOW_DEFENSE_BAD_ACTIONS or action_name is None):
            adjustment -= config.hit_penalty
            stats.reward_total -= config.hit_penalty
            stats.hit_penalty_events += 1
            if action_name is None:
                stats.no_action_hit_penalty_events += 1
        elif defense_result in ("blocked", "blocked_chip") and action_name == LOW_DEFENSE_TARGET_ACTION:
            adjustment += config.block_bonus
            stats.reward_total += config.block_bonus
            stats.block_bonus_events += 1

    return adjustment


def low_defense_margin_eligible(
    row: dict[str, object],
    source_name: str,
    action_name: str,
    combat_event_validation: combat_events.CombatEventTrainingValidation | None,
    config: LowDefenseConfig,
) -> bool:
    if not config.margin_loss:
        return False
    if source_name not in config.eligible_sources:
        return False
    if action_name != LOW_DEFENSE_TARGET_ACTION and action_name not in LOW_DEFENSE_BAD_ACTIONS:
        return False
    return low_defense_context_for_row(row, combat_event_validation, config)


def apply_grounded_normal_defense_bc_loss(
    exp: Experience,
    values: list[float],
    actions: tuple[str, ...],
    output_grad: list[float],
    config: GroundedNormalDefenseBCConfig,
    stats: GroundedNormalDefenseBCStats,
) -> float:
    if not config.enabled or not exp.grounded_normal_defense_bc_eligible:
        return 0.0

    target_index = exp.action_index
    value_count = min(len(actions), len(values))
    if target_index >= value_count:
        return 0.0

    stats.sampled_events += 1
    time_bucket = _grounded_normal_defense_time_bucket(exp.row)
    stats.sampled_by_time_bucket[time_bucket] = stats.sampled_by_time_bucket.get(time_bucket, 0) + 1
    target_action = actions[target_index]
    stats.target_action_counts[target_action] = stats.target_action_counts.get(target_action, 0) + 1

    # Cross-entropy loss scaled by loss_weight
    max_q = max(values[:value_count])
    exp_q = [math.exp(v - max_q) for v in values[:value_count]]
    sum_exp = sum(exp_q)
    probs = [e / sum_exp for e in exp_q]
    ce_loss = -math.log(max(probs[target_index], 1e-15))
    weighted_loss = config.loss_weight * ce_loss

    # Gradient: softmax probs, subtract 1 from target
    for i in range(value_count):
        output_grad[i] += config.loss_weight * probs[i]
    output_grad[target_index] -= config.loss_weight

    stats.loss_total += weighted_loss
    return weighted_loss


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


def add_delayed_reward_to_indices(
    experiences: list[Experience],
    exp_indices: list[int],
    reward: float,
    actions: tuple[str, ...],
    action_rewards: dict[str, float],
    source_stats: SourceReplayDiagnostics | None = None,
) -> bool:
    if not exp_indices:
        return False
    added = False
    for exp_index in exp_indices:
        if add_delayed_reward(experiences, exp_index, reward, actions, action_rewards, source_stats):
            added = True
    return added


def set_experience_next_state(
    experiences: list[Experience],
    exp_index: int | None,
    row: dict[str, object],
    done: bool,
) -> None:
    if exp_index is None:
        return
    experiences[exp_index].next_state = rl.dqn_feature_vector(row)
    experiences[exp_index].next_row = dict(row)
    experiences[exp_index].done = done


def set_experience_next_state_for_indices(
    experiences: list[Experience],
    exp_indices: list[int],
    row: dict[str, object],
    done: bool,
) -> None:
    for exp_index in exp_indices:
        set_experience_next_state(experiences, exp_index, row, done)


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
    special_expert_margin_config: SpecialExpertMarginConfig,
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

    engine_fireball_made_contact = (
        action_name.startswith("fireball-")
        and (
            any(int_field(window_row, "obs_opp_contact_reaction_state") != 0 for window_row in window_rows)
            or any(int_field(window_row, "obs_projectile_owner") == PROJECTILE_OWNER_OPPONENT for window_row in window_rows)
        )
    )

    if opponent_damage > 0:
        stats.hit_events += 1
        adjustment += config.hit_bonus
        stats.hit_bonus_total += config.hit_bonus
    elif not engine_fireball_made_contact:
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
                row=dict(row),
                next_row=dict(next_row),
                special_expert_margin_eligible=special_expert_margin_eligible(
                    action_name,
                    source_name,
                    reward,
                    special_expert_margin_config,
                ),
                combat_event_batch_group=(
                    "punish_throw"
                    if action_name == "throw"
                    else "projectile"
                    if action_name.startswith("fireball-")
                    else "movement"
                    if action_name in UNLABELED_MOVEMENT_FILTER_ACTIONS
                    else "attack"
                ),
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
    training_mode_hp_delta_mode: str,
    training_action_source: str,
    reward_risk_config: RewardRiskConfig,
    reward_guard_config: RewardGuardConfig,
    reward_spacing_config: RewardSpacingConfig,
    reward_position_config: RewardPositionConfig,
    reward_projectile_response_config: RewardProjectileResponseConfig,
    projectile_response_oversample_config: ProjectileResponseOversampleConfig,
    projectile_batch_config: ProjectileBatchConfig,
    projectile_expert_margin_config: ProjectileExpertMarginConfig,
    special_expert_margin_config: SpecialExpertMarginConfig,
    projectile_late_defensive_margin_config: ProjectileLateDefensiveMarginConfig,
    projectile_defensive_expert_margin_config: ProjectileDefensiveExpertMarginConfig,
    grounded_normal_defense_margin_config: GroundedNormalDefenseMarginConfig,
    grounded_normal_defense_bc_config: GroundedNormalDefenseBCConfig,
    low_defense_config: LowDefenseConfig,
    engine_outcome_config: EngineOutcomeConfig,
    action_filter_config: DQNActionFilterConfig,
    combat_event_validation: combat_events.CombatEventTrainingValidation | None,
    combat_event_reward_config: combat_events.CombatEventRewardConfig,
    combat_event_unlabeled_movement_filter_config: CombatEventUnlabeledMovementFilterConfig,
    combat_event_movement_credit_config: CombatEventMovementCreditConfig,
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
    RewardProjectileResponseStats,
    ProjectileResponseOversampleStats,
    EngineOutcomeStats,
    combat_events.CombatEventRewardStats,
    CombatEventUnlabeledMovementFilterStats,
    CombatEventMovementCreditStats,
    LowDefenseStats,
]:
    action_to_index = {action: index for index, action in enumerate(actions)}
    build_stats = BuildDiagnostics()
    by_episode: dict[tuple[int, int], list[dict[str, object]]] = collections.defaultdict(list)
    for row in rows:
        replay_row = dict(row)
        apply_training_mode_hp_delta_mode(replay_row, training_mode_hp_delta_mode, build_stats)
        by_episode[episode_key(replay_row)].append(replay_row)

    experiences: list[Experience] = []
    action_counts = {action: 0 for action in actions}
    action_rewards = {action: 0.0 for action in actions}
    observed_action_counts = {action: 0 for action in rl.TABULAR_ACTION_NAMES}
    observed_action_rewards = {action: 0.0 for action in rl.TABULAR_ACTION_NAMES}
    source_stats = SourceReplayDiagnostics()
    risk_stats = RewardRiskStats()
    guard_stats = RewardGuardStats()
    spacing_stats = RewardSpacingStats()
    position_stats = RewardPositionStats()
    projectile_response_stats = RewardProjectileResponseStats()
    projectile_response_oversample_stats = ProjectileResponseOversampleStats()
    engine_outcome_stats = EngineOutcomeStats()
    combat_event_reward_stats = combat_events.CombatEventRewardStats()
    combat_event_unlabeled_movement_filter_stats = CombatEventUnlabeledMovementFilterStats()
    combat_event_movement_credit_stats = CombatEventMovementCreditStats()
    low_defense_stats = LowDefenseStats()

    for episode_rows in by_episode.values():
        episode_rows.sort(key=row_order_key)
        last_exp_indices: list[int] = []
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
                    special_expert_margin_config,
                    engine_outcome_stats,
                    experiences,
                    action_counts,
                    action_rewards,
                    source_stats,
                    source_name,
                    model_version,
                )
                if engine_outcome_added:
                    set_experience_next_state_for_indices(
                        experiences,
                        last_exp_indices,
                        row,
                        bool(row.get("done", False)),
                    )
                    last_exp_indices = []
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
            transition_hp_reward = rl.tabular_training_reward(row, training_mode_hp_delta_mode) * reward_scale
            base_reward = (
                transition_hp_reward
                if combat_events.uses_transition_hp_delta(combat_event_reward_config)
                else 0.0
            )
            if (
                action_start
                and action_name is not None
                and action_filter_config.requires_movable_state(source_name)
            ):
                build_stats.movable_filter_checked_rows += 1
                filter_reason = movable_action_filter_reason(row)
                if filter_reason:
                    set_experience_next_state_for_indices(
                        experiences,
                        last_exp_indices,
                        row,
                        bool(row.get("done", False)),
                    )
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
                        if add_delayed_reward_to_indices(
                            experiences,
                            last_exp_indices,
                            base_reward,
                            actions,
                            action_rewards,
                            source_stats,
                        ):
                            build_stats.movable_filter_delayed_rewards += 1
                        else:
                            build_stats.movable_filter_uncredited_reward_rows += 1
                    last_exp_indices = []
                    continue
                build_stats.movable_filter_included_rows += 1
            risk_cost = (
                reward_risk_cost(episode_rows, index, action_name, reward_risk_config, risk_stats)
                if action_name is not None
                else 0.0
            )
            guard_adjustment = (
                reward_guard_adjustment(episode_rows, index, action_name, action_start, reward_guard_config, guard_stats)
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
            if action_name is not None:
                projectile_response_adjustment, projectile_response_outcome_result = (
                    reward_projectile_response_adjustment(
                        episode_rows,
                        index,
                        action_name,
                        reward_projectile_response_config,
                        projectile_response_stats,
                    )
                )
            else:
                projectile_response_adjustment = 0.0
                projectile_response_outcome_result = ProjectileResponseOutcome()
            low_defense_adjustment = low_defense_reward_adjustment(
                row,
                action_name,
                combat_event_validation,
                low_defense_config,
                low_defense_stats,
            )
            reward = base_reward + (
                -risk_cost
                + guard_adjustment
                + spacing_adjustment
                + position_adjustment
                + projectile_response_adjustment
                + low_defense_adjustment
            ) * reward_scale
            combat_event_reward_adjustment = combat_events.reward_adjustment_for_transition(
                combat_event_validation.index if combat_event_validation is not None else None,
                row,
                action_name,
                action_start,
                combat_event_reward_config,
                combat_event_reward_stats,
            )
            if combat_event_reward_adjustment != 0.0:
                reward += combat_event_reward_adjustment * reward_scale
            apply_combat_event_movement_credit(
                experiences,
                actions,
                row,
                action_name,
                action_start,
                combat_event_reward_adjustment,
                reward_scale,
                combat_event_validation,
                combat_event_movement_credit_config,
                combat_event_movement_credit_stats,
                action_rewards,
                source_stats,
            )
            if action_name is None:
                if reward != 0.0:
                    if add_delayed_reward_to_indices(
                        experiences,
                        last_exp_indices,
                        reward,
                        actions,
                        action_rewards,
                        source_stats,
                    ):
                        build_stats.unrecognized_delayed_rewards += 1
                    else:
                        build_stats.unrecognized_uncredited_reward_rows += 1
                continue

            if action_name in observed_action_counts:
                observed_action_counts[action_name] += 1
                observed_action_rewards[action_name] += reward

            if action_start:
                set_experience_next_state_for_indices(
                    experiences,
                    last_exp_indices,
                    row,
                    bool(row.get("done", False)),
                )

            if action_name not in action_to_index:
                build_stats.excluded_action_rows += 1
                if reward != 0.0:
                    build_stats.excluded_action_reward_rows += 1
                    build_stats.excluded_action_reward_sum += reward
                last_exp_indices = []
                continue

            if should_drop_unlabeled_movement_transition(
                episode_rows,
                index,
                row,
                action_name,
                action_start,
                reward,
                projectile_response_outcome_result,
                combat_event_validation,
                combat_event_unlabeled_movement_filter_config,
                combat_event_unlabeled_movement_filter_stats,
            ):
                last_exp_indices = []
                continue

            if not action_start:
                build_stats.macro_continuation_rows += 1
                if reward != 0.0:
                    build_stats.macro_continuation_reward_rows += 1
                    build_stats.macro_continuation_reward_sum += reward
                    if add_delayed_reward_to_indices(
                        experiences,
                        last_exp_indices,
                        reward,
                        actions,
                        action_rewards,
                        source_stats,
                    ):
                        build_stats.macro_continuation_delayed_rewards += 1
                    else:
                        build_stats.macro_continuation_uncredited_reward_rows += 1
                continue

            projectile_batch_label = projectile_batch_reason(
                episode_rows,
                index,
                row,
                source_name,
                action_name,
                projectile_response_outcome_result,
                projectile_batch_config,
            )
            combat_event_batch_group = combat_event_batch_group_for_transition(
                row,
                action_name,
                action_start,
                reward,
                projectile_response_outcome_result,
                combat_event_validation,
            )
            exp = Experience(
                state=rl.dqn_feature_vector(row),
                action_index=action_to_index[action_name],
                reward=reward,
                next_state=rl.dqn_feature_vector(row),
                done=bool(row.get("done", False)),
                source_name=source_name,
                model_version=model_version,
                row=dict(row),
                next_row=dict(row),
                projectile_expert_margin_eligible=projectile_expert_margin_eligible(
                    row,
                    source_name,
                    action_name,
                    projectile_response_outcome_result,
                    projectile_expert_margin_config,
                ),
                special_expert_margin_eligible=special_expert_margin_eligible(
                    action_name,
                    source_name,
                    reward,
                    special_expert_margin_config,
                ),
                projectile_late_defensive_margin_eligible=projectile_late_defensive_margin_eligible(
                    row,
                    source_name,
                    action_name,
                    projectile_response_outcome_result,
                    projectile_late_defensive_margin_config,
                ),
                projectile_defensive_expert_margin_eligible=projectile_defensive_expert_margin_eligible(
                    episode_rows,
                    index,
                    row,
                    source_name,
                    action_name,
                    projectile_response_outcome_result,
                    projectile_defensive_expert_margin_config,
                ),
                projectile_batch_eligible=bool(projectile_batch_label),
                projectile_batch_reason=projectile_batch_label,
                grounded_normal_defense_eligible=grounded_normal_defense_eligible(
                    row,
                    source_name,
                    action_name,
                    grounded_normal_defense_margin_config,
                ),
                grounded_normal_defense_bc_eligible=grounded_normal_defense_bc_eligible(
                    row,
                    source_name,
                    action_name,
                    grounded_normal_defense_bc_config,
                ),
                low_defense_margin_eligible=low_defense_margin_eligible(
                    row,
                    source_name,
                    action_name,
                    combat_event_validation,
                    low_defense_config,
                ),
                combat_event_batch_group=combat_event_batch_group,
            )
            multiplier = projectile_response_oversample_config.multiplier_for(projectile_response_outcome_result)
            for _ in range(multiplier):
                experiences.append(copy.deepcopy(exp))
            last_exp_indices = list(range(len(experiences) - multiplier, len(experiences)))
            build_stats.included_action_rows += 1
            action_counts[action_name] += multiplier
            action_rewards[action_name] += reward * multiplier
            source_stats.add_experience(source_name, model_version, action_name, reward, multiplier)
            projectile_response_oversample_stats.add(
                action_name,
                projectile_response_outcome_result,
                multiplier,
            )

        if episode_rows:
            set_experience_next_state_for_indices(experiences, last_exp_indices, episode_rows[-1], True)

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
        projectile_response_stats,
        projectile_response_oversample_stats,
        engine_outcome_stats,
        combat_event_reward_stats,
        combat_event_unlabeled_movement_filter_stats,
        combat_event_movement_credit_stats,
        low_defense_stats,
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
        throw_far_cost=max(0.0, float(args.reward_throw_far_cost)),
        throw_far_max_abs_dx=max(0, int(args.reward_throw_far_max_abs_dx)),
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


def reward_projectile_response_config_from_args(args: argparse.Namespace) -> RewardProjectileResponseConfig:
    profile = str(args.reward_projectile_response_profile)
    if profile not in REWARD_PROJECTILE_RESPONSE_PROFILES:
        raise SystemExit(
            f"unknown --reward-projectile-response-profile {profile!r}; "
            f"expected one of {','.join(REWARD_PROJECTILE_RESPONSE_PROFILES)}"
        )
    min_time = max(0, int(args.reward_projectile_threat_min_time_to_self))
    max_time = max(min_time, int(args.reward_projectile_threat_max_time_to_self))
    return RewardProjectileResponseConfig(
        profile=profile,
        window_decisions=max(0, int(args.reward_projectile_response_window_decisions)),
        threat_min_time_to_self=min_time,
        threat_max_time_to_self=max_time,
        threat_max_dx=max(0, int(args.reward_projectile_threat_max_dx)),
        threat_max_abs_y=max(0, int(args.reward_projectile_threat_max_abs_y)),
        close_max_dx=max(0, int(args.reward_projectile_close_max_dx)),
        safe_jump_bonus=max(0.0, float(args.reward_projectile_safe_jump_bonus)),
        late_jump_hit_cost=max(0.0, float(args.reward_projectile_late_jump_hit_cost)),
        close_back_success_bonus=max(0.0, float(args.reward_projectile_close_back_success_bonus)),
        close_guard_success_bonus=max(0.0, float(args.reward_projectile_close_guard_success_bonus)),
        back_escape_min_dx_delta=max(0, int(args.reward_projectile_back_escape_min_dx_delta)),
        guard_require_contact=bool(args.reward_projectile_guard_require_contact),
    )


def combat_event_unlabeled_movement_filter_config_from_args(
    args: argparse.Namespace,
) -> CombatEventUnlabeledMovementFilterConfig:
    policy = str(args.combat_event_unlabeled_movement_policy)
    if policy not in combat_events.COMBAT_EVENT_UNLABELED_MOVEMENT_POLICIES:
        raise SystemExit(
            f"unknown --combat-event-unlabeled-movement-policy {policy!r}; "
            f"expected one of {','.join(combat_events.COMBAT_EVENT_UNLABELED_MOVEMENT_POLICIES)}"
        )
    return CombatEventUnlabeledMovementFilterConfig(
        policy=policy,
        keep_ratio=min(1.0, max(0.0, float(args.combat_event_unlabeled_movement_keep_ratio))),
        seed=int(args.combat_event_unlabeled_movement_seed),
    )


def projectile_response_oversample_config_from_args(args: argparse.Namespace) -> ProjectileResponseOversampleConfig:
    return ProjectileResponseOversampleConfig(
        safe_jump=max(1, int(args.projectile_response_safe_jump_oversample)),
        late_jump_hit=max(1, int(args.projectile_response_late_jump_hit_oversample)),
        close_back_success=max(1, int(args.projectile_response_close_back_oversample)),
        close_guard_success=max(1, int(args.projectile_response_close_guard_oversample)),
    )


def projectile_expert_margin_config_from_args(args: argparse.Namespace) -> ProjectileExpertMarginConfig:
    mode = str(args.projectile_expert_margin_valid_action_mask)
    if mode not in rl.DQN_VALID_ACTION_MASK_MODES:
        raise SystemExit(
            f"unknown --projectile-expert-margin-valid-action-mask {mode!r}; "
            f"expected one of {','.join(rl.DQN_VALID_ACTION_MASK_MODES)}"
        )
    min_time = max(0, int(args.projectile_expert_margin_min_time_to_self))
    max_time = max(min_time, int(args.projectile_expert_margin_max_time_to_self))
    return ProjectileExpertMarginConfig(
        requested=bool(args.projectile_expert_margin_loss),
        margin=max(0.0, float(args.projectile_expert_margin)),
        loss_weight=max(0.0, float(args.projectile_expert_margin_weight)),
        batch_size=max(0, int(args.projectile_expert_margin_batch_size)),
        require_safe_jump=bool(args.projectile_expert_margin_require_safe_jump),
        equivalent_jump_actions=bool(args.projectile_expert_margin_equivalent_jump_actions),
        min_time_to_self=min_time,
        max_time_to_self=max_time,
        time_ranges=parse_time_ranges(
            str(args.projectile_expert_margin_time_ranges),
            "--projectile-expert-margin-time-ranges",
        ),
        eligible_sources=parse_source_name_set(
            str(args.projectile_expert_margin_sources),
            "--projectile-expert-margin-sources",
        ),
        valid_action_mask_mode=mode,
    )


def special_expert_margin_config_from_args(args: argparse.Namespace) -> SpecialExpertMarginConfig:
    mode = str(args.special_expert_margin_valid_action_mask)
    if mode not in rl.DQN_VALID_ACTION_MASK_MODES:
        raise SystemExit(
            f"unknown --special-expert-margin-valid-action-mask {mode!r}; "
            f"expected one of {','.join(rl.DQN_VALID_ACTION_MASK_MODES)}"
        )
    return SpecialExpertMarginConfig(
        requested=bool(args.special_expert_margin_loss),
        margin=max(0.0, float(args.special_expert_margin)),
        loss_weight=max(0.0, float(args.special_expert_margin_weight)),
        batch_size=max(0, int(args.special_expert_margin_batch_size)),
        min_reward=float(args.special_expert_margin_min_reward),
        eligible_sources=parse_source_name_set(
            str(args.special_expert_margin_sources),
            "--special-expert-margin-sources",
        ),
        valid_action_mask_mode=mode,
        context_gate=bool(args.special_expert_margin_context_gate),
        fireball_min_abs_dx=max(0, int(args.special_expert_margin_fireball_min_abs_dx)),
    )


def projectile_late_defensive_margin_config_from_args(
    args: argparse.Namespace,
) -> ProjectileLateDefensiveMarginConfig:
    mode = str(args.projectile_late_defensive_margin_valid_action_mask)
    if mode not in rl.DQN_VALID_ACTION_MASK_MODES:
        raise SystemExit(
            f"unknown --projectile-late-defensive-margin-valid-action-mask {mode!r}; "
            f"expected one of {','.join(rl.DQN_VALID_ACTION_MASK_MODES)}"
        )
    min_time = max(0, int(args.projectile_late_defensive_margin_min_time_to_self))
    max_time = max(min_time, int(args.projectile_late_defensive_margin_max_time_to_self))
    return ProjectileLateDefensiveMarginConfig(
        requested=bool(args.projectile_late_defensive_margin_loss),
        margin=max(0.0, float(args.projectile_late_defensive_margin)),
        loss_weight=max(0.0, float(args.projectile_late_defensive_margin_weight)),
        batch_size=max(0, int(args.projectile_late_defensive_margin_batch_size)),
        min_time_to_self=min_time,
        max_time_to_self=max_time,
        eligible_sources=parse_source_name_set(
            str(args.projectile_late_defensive_margin_sources),
            "--projectile-late-defensive-margin-sources",
        ),
        valid_action_mask_mode=mode,
    )


def projectile_defensive_expert_margin_config_from_args(
    args: argparse.Namespace,
) -> ProjectileDefensiveExpertMarginConfig:
    mode = str(args.projectile_defensive_expert_margin_valid_action_mask)
    if mode not in rl.DQN_VALID_ACTION_MASK_MODES:
        raise SystemExit(
            f"unknown --projectile-defensive-expert-margin-valid-action-mask {mode!r}; "
            f"expected one of {','.join(rl.DQN_VALID_ACTION_MASK_MODES)}"
        )
    min_time = max(0, int(args.projectile_defensive_expert_margin_min_time_to_self))
    max_time = max(min_time, int(args.projectile_defensive_expert_margin_max_time_to_self))
    return ProjectileDefensiveExpertMarginConfig(
        requested=bool(args.projectile_defensive_expert_margin_loss),
        margin=max(0.0, float(args.projectile_defensive_expert_margin)),
        loss_weight=max(0.0, float(args.projectile_defensive_expert_margin_weight)),
        batch_size=max(0, int(args.projectile_defensive_expert_margin_batch_size)),
        min_time_to_self=min_time,
        max_time_to_self=max_time,
        time_ranges=parse_time_ranges(
            str(args.projectile_defensive_expert_margin_time_ranges),
            "--projectile-defensive-expert-margin-time-ranges",
        ),
        window_decisions=max(0, int(args.projectile_defensive_expert_margin_window_decisions)),
        max_self_hp=max(0, int(args.projectile_defensive_expert_margin_max_self_hp)),
        all_competitors=bool(args.projectile_defensive_expert_margin_all_competitors),
        eligible_sources=parse_source_name_set(
            str(args.projectile_defensive_expert_margin_sources),
            "--projectile-defensive-expert-margin-sources",
        ),
        valid_action_mask_mode=mode,
    )


def projectile_timing_group_margin_config_from_args(
    args: argparse.Namespace,
) -> ProjectileTimingGroupMarginConfig:
    mode = str(args.projectile_timing_group_margin_valid_action_mask)
    if mode not in rl.DQN_VALID_ACTION_MASK_MODES:
        raise SystemExit(
            f"unknown --projectile-timing-group-margin-valid-action-mask {mode!r}; "
            f"expected one of {','.join(rl.DQN_VALID_ACTION_MASK_MODES)}"
        )
    return ProjectileTimingGroupMarginConfig(
        requested=bool(args.projectile_timing_group_margin_loss),
        margin=max(0.0, float(args.projectile_timing_group_margin)),
        loss_weight=max(0.0, float(args.projectile_timing_group_margin_weight)),
        batch_size=max(0, int(args.projectile_timing_group_margin_batch_size)),
        defense_time_ranges=parse_time_ranges(
            str(args.projectile_timing_group_margin_defense_time_ranges),
            "--projectile-timing-group-margin-defense-time-ranges",
        ),
        jump_time_ranges=parse_time_ranges(
            str(args.projectile_timing_group_margin_jump_time_ranges),
            "--projectile-timing-group-margin-jump-time-ranges",
        ),
        eligible_sources=parse_source_name_set(
            str(args.projectile_timing_group_margin_sources),
            "--projectile-timing-group-margin-sources",
        ),
        valid_action_mask_mode=mode,
        threat_max_dx=max(0, int(args.projectile_timing_group_margin_threat_max_dx)),
        threat_max_abs_y=max(0, int(args.projectile_timing_group_margin_threat_max_abs_y)),
    )


def grounded_normal_defense_config_from_args(
    args: argparse.Namespace,
) -> GroundedNormalDefenseMarginConfig:
    mode = str(args.grounded_normal_defense_valid_action_mask)
    if mode not in rl.DQN_VALID_ACTION_MASK_MODES:
        raise SystemExit(
            f"unknown --grounded-normal-defense-valid-action-mask {mode!r}; "
            f"expected one of {','.join(rl.DQN_VALID_ACTION_MASK_MODES)}"
        )
    return GroundedNormalDefenseMarginConfig(
        requested=bool(args.grounded_normal_defense_margin_loss),
        margin=max(0.0, float(args.grounded_normal_defense_margin)),
        loss_weight=max(0.0, float(args.grounded_normal_defense_margin_weight)),
        batch_size=max(0, int(args.grounded_normal_defense_margin_batch_size)),
        eligible_sources=parse_source_name_set(
            str(args.grounded_normal_defense_margin_sources),
            "--grounded-normal-defense-margin-sources",
        ),
        valid_action_mask_mode=mode,
        max_abs_dx=max(0, int(args.grounded_normal_defense_margin_max_abs_dx)),
    )


def grounded_normal_defense_bc_config_from_args(
    args: argparse.Namespace,
) -> GroundedNormalDefenseBCConfig:
    return GroundedNormalDefenseBCConfig(
        requested=bool(args.grounded_normal_defense_bc_loss),
        loss_weight=max(0.0, float(args.grounded_normal_defense_bc_weight)),
        eligible_sources=parse_source_name_set(
            str(args.grounded_normal_defense_bc_sources),
            "--grounded-normal-defense-bc-sources",
        ),
        max_abs_dx=max(0, int(args.grounded_normal_defense_bc_max_abs_dx)),
    )


def low_defense_config_from_args(args: argparse.Namespace) -> LowDefenseConfig:
    mode = str(args.low_defense_valid_action_mask)
    if mode not in rl.DQN_VALID_ACTION_MASK_MODES:
        raise SystemExit(
            f"unknown --low-defense-valid-action-mask {mode!r}; "
            f"expected one of {','.join(rl.DQN_VALID_ACTION_MASK_MODES)}"
        )
    return LowDefenseConfig(
        reward_shaping=bool(args.low_defense_reward_shaping),
        hit_penalty=max(0.0, float(args.low_defense_hit_penalty)),
        block_bonus=max(0.0, float(args.low_defense_block_bonus)),
        margin_loss=bool(args.low_defense_margin_loss),
        margin=max(0.0, float(args.low_defense_margin)),
        loss_weight=max(0.0, float(args.low_defense_margin_weight)),
        batch_size=max(0, int(args.low_defense_margin_batch_size)),
        eligible_sources=parse_source_name_set(
            str(args.low_defense_margin_sources),
            "--low-defense-margin-sources",
        ),
        valid_action_mask_mode=mode,
        max_abs_dx=max(0, int(args.low_defense_max_abs_dx)),
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
            f"--engine-outcome-training-mode {training_mode!r} was removed for the current schema; "
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


def validate_dqn_layers(
    raw_layers: object,
    input_dim: int,
    hidden_sizes: list[int],
    output_dim: int,
    context: str,
) -> list[dict[str, object]]:
    if not isinstance(raw_layers, list):
        raise SystemExit(f"{context}: missing DQN layer list")
    expected_sizes = hidden_sizes + [output_dim]
    if len(raw_layers) != len(expected_sizes):
        raise SystemExit(f"{context}: layer count {len(raw_layers)} does not match expected {len(expected_sizes)}")
    clean_layers: list[dict[str, object]] = []
    prev_dim = input_dim
    for index, (raw_layer, expected_size) in enumerate(zip(raw_layers, expected_sizes)):
        if not isinstance(raw_layer, dict):
            raise SystemExit(f"{context}: layer {index} is not an object")
        weights = raw_layer.get("weights")
        bias = raw_layer.get("bias")
        expected_activation = "relu" if index + 1 < len(expected_sizes) else "linear"
        activation = str(raw_layer.get("activation", expected_activation) or expected_activation)
        if activation != expected_activation:
            raise SystemExit(
                f"{context}: layer {index} activation {activation!r} does not match expected {expected_activation!r}"
            )
        if not isinstance(weights, list) or len(weights) != expected_size:
            raise SystemExit(f"{context}: layer {index} output rows do not match expected {expected_size}")
        if not isinstance(bias, list) or len(bias) != expected_size:
            raise SystemExit(f"{context}: layer {index} bias length does not match expected {expected_size}")
        clean_weights: list[list[float]] = []
        for row_index, raw_row in enumerate(weights):
            if not isinstance(raw_row, list) or len(raw_row) != prev_dim:
                raise SystemExit(
                    f"{context}: layer {index} row {row_index} input width does not match expected {prev_dim}"
                )
            try:
                clean_weights.append([float(value) for value in raw_row])
            except (TypeError, ValueError) as exc:
                raise SystemExit(f"{context}: layer {index} row {row_index} contains a non-numeric weight") from exc
        try:
            clean_bias = [float(value) for value in bias]
        except (TypeError, ValueError) as exc:
            raise SystemExit(f"{context}: layer {index} contains a non-numeric bias") from exc
        clean_layers.append({"weights": clean_weights, "bias": clean_bias, "activation": activation})
        prev_dim = expected_size
    return clean_layers


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


def entropy_regularization_grad(values: list[float], weight: float) -> tuple[float, float, list[float]]:
    """Return loss delta, positive entropy bonus, and d(-weight*H)/d(values)."""
    if weight <= 0.0 or not values:
        return 0.0, 0.0, [0.0 for _ in values]
    max_value = max(values)
    exp_values = [math.exp(value - max_value) for value in values]
    sum_exp = sum(exp_values)
    if sum_exp <= 0.0:
        return 0.0, 0.0, [0.0 for _ in values]
    probs = [value / sum_exp for value in exp_values]
    entropy = -sum(prob * math.log(max(prob, 1e-15)) for prob in probs)
    grad = [
        weight * prob * (math.log(max(prob, 1e-15)) + entropy)
        for prob in probs
    ]
    bonus = weight * entropy
    return -bonus, bonus, grad


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


def _derive_segment_kw_map(rows: list[dict[str, object]]) -> dict[tuple[int, int, int], int]:
    """Build per-instance KW map from engine outcome rows.

    Engine outcome rows appear just BEFORE their corresponding attack segment
    in the transition log. Each outcome row has:
    - engine_action_id: 1229=fireball, 1228=shoryuken, 1230=tatsu
    - engine_kind_of_waza: 0x08=LP, 0x0A=MP, 0x0C=HP, 0x09=LK, 0x0B=MK, 0x0D=HK

    Algorithm:
    1. Find engine outcome rows with non-zero KW (anchors).
    2. For each anchor, scan forward to find the next contiguous attack segment
       (R1=4, matching family R2) in the same (run, episode).
    3. Map every (run_id, episode_id, decision_id) in that segment to the anchor's KW.

    Key uses (run_id, episode_id, decision_id) to avoid collisions across
    different runs that share the same episode/decision numbering.

    Only human-demo and cpu-demo rows have engine outcome data;
    remote/policy rows never populate these fields.
    """
    ENGINE_ACTION_TO_R2 = {1229: 16, 1228: 17, 1230: 18}
    SPECIAL_R2_VALUES = frozenset(ENGINE_ACTION_TO_R2.values())
    MAX_ANCHOR_TO_SEGMENT_ROWS = 8

    # Step 1: find engine outcome anchors
    anchors: list[tuple[int, int, int, int, int]] = []  # (row_index, run_id, episode_id, family_r2, kw)
    for i, row in enumerate(rows):
        eaid = int_row_field(row, "engine_action_id")
        kw = int_row_field(row, "engine_kind_of_waza")
        if kw != 0 and eaid in ENGINE_ACTION_TO_R2:
            anchors.append((
                i,
                int_row_field(row, "run_id"),
                int_row_field(row, "episode_id"),
                ENGINE_ACTION_TO_R2[eaid],
                kw,
            ))

    if not anchors:
        return {}

    # Step 2: for each anchor, find the next matching attack segment
    RowKey = tuple[int, int, int]  # (run_id, episode_id, decision_id)
    result: dict[RowKey, int] = {}
    used_segments: set[tuple[int, int, int]] = set()  # (run_id, episode_id, segment_start_did)

    for a_idx, a_rid, a_eid, a_r2, a_kw in anchors:
        for j in range(a_idx, min(len(rows), a_idx + MAX_ANCHOR_TO_SEGMENT_ROWS + 1)):
            row = rows[j]
            rid = int_row_field(row, "run_id")
            eid = int_row_field(row, "episode_id")

            if rid != a_rid or eid != a_eid:
                continue  # different run or episode

            if j > a_idx and int_row_field(row, "engine_kind_of_waza") != 0:
                next_eaid = int_row_field(row, "engine_action_id")
                if next_eaid in ENGINE_ACTION_TO_R2:
                    break

            r1 = int_row_field(row, "obs_self_routine_1")
            r2 = int_row_field(row, "obs_self_routine_2")

            if r1 == 4 and r2 == a_r2:
                seg_start_did = int_row_field(row, "decision_id")
                if (rid, eid, seg_start_did) in used_segments:
                    continue

                used_segments.add((rid, eid, seg_start_did))

                for k in range(j, len(rows)):
                    row2 = rows[k]
                    if int_row_field(row2, "run_id") != rid or int_row_field(row2, "episode_id") != eid:
                        break
                    r1k = int_row_field(row2, "obs_self_routine_1")
                    r2k = int_row_field(row2, "obs_self_routine_2")
                    if r1k == 4 and r2k == a_r2:
                        did = int_row_field(row2, "decision_id")
                        result[(rid, eid, did)] = a_kw
                    else:
                        break
                break
            if r1 == 4 and r2 in SPECIAL_R2_VALUES:
                break

    return result


# Segment-level KW cache, populated once per BC training run
_BC_SEGMENT_KW_MAP: dict[tuple[int, int, int], int] = {}


def derive_bc_label(row: dict[str, object], actions: tuple[str, ...]) -> int | None:
    """Derive a BC action label (index into actions) from engine state + input fields.

    Uses engine outcome rows as anchors to propagate correct strength KW to
    subsequent attack segments. See _derive_segment_kw_map for the algorithm.

    Returns the action index if a label can be derived, or None if the row
    represents a non-decision state (contact reaction, idle with no input, etc.).
    """
    global _BC_SEGMENT_KW_MAP
    r1 = int_row_field(row, "obs_self_routine_1")
    r2 = int_row_field(row, "obs_self_routine_2")
    kw = int_row_field(row, "engine_kind_of_waza")
    eid = int_row_field(row, "episode_id")

    # Attack state (R1=4): use engine routine to identify the special/normal
    if r1 == 4:
        action_name: str | None = None
        # Get KW from segment map if not set on this row
        rid = int_row_field(row, "run_id")
        did = int_row_field(row, "decision_id")
        if kw == 0:
            kw = _BC_SEGMENT_KW_MAP.get((rid, eid, did), 0)
        if r2 == 16:  # hadouken
            if kw == 0x08:
                action_name = "fireball-lp"
            elif kw == 0x0A:
                action_name = "fireball-mp"
            elif kw == 0x0C:
                action_name = "fireball-hp"
        elif r2 == 17:  # shoryuken
            if kw == 0x08:
                action_name = "shoryuken-lp"
            elif kw == 0x0A:
                action_name = "shoryuken-mp"
            elif kw == 0x0C:
                action_name = "shoryuken-hp"
        elif r2 == 18:  # tatsumaki
            if kw == 0x09:
                action_name = "tatsu-lk"
            elif kw == 0x0B:
                action_name = "tatsu-mk"
            elif kw == 0x0D:
                action_name = "tatsu-hk"
        if action_name is not None:
            for index, name in enumerate(actions):
                if name == action_name:
                    return index
        return None

    # Throw state (R1=3)
    if r1 == 3:
        for index, name in enumerate(actions):
            if name == "throw":
                return index
        return None

    # Non-attack states: use input label
    iid = int_row_field(row, "input_action_id")
    if 0 <= iid < len(actions) and int_row_field(row, "input_action_step") == 0:
        return iid

    # Standing or crouching with no attack input — no explicit action label
    return None

    return None


BC_OFFENSIVE_MARGIN_ACTIONS = (
    frozenset(getattr(rl, "STAND_NORMAL_ACTION_NAMES", ()))
    | frozenset(getattr(rl, "CROUCH_NORMAL_ACTION_NAMES", ()))
    | frozenset(getattr(rl, "AIR_NORMAL_ACTION_NAMES", ()))
    | frozenset(getattr(rl, "FIREBALL_ACTION_NAMES", ()))
    | frozenset(getattr(rl, "SHORYUKEN_ACTION_NAMES", ()))
    | frozenset(getattr(rl, "TATSU_ACTION_NAMES", ()))
    | frozenset({"forward-hp", "throw"})
)
BC_DEFENSIVE_MARGIN_ACTIONS = frozenset({"guard-crouch"})


@dataclass
class BCDatasetSample:
    features: list[float]
    label_index: int
    sample_weight: float
    raw_adjustment: float
    family_margin_eligible: bool


def bc_family_margin_eligible(action_name: str, raw_adjustment: float, config: BCFamilyMarginConfig) -> bool:
    if not config.enabled or raw_adjustment < config.min_positive_adjustment:
        return False
    return action_name in BC_OFFENSIVE_MARGIN_ACTIONS or action_name in BC_DEFENSIVE_MARGIN_ACTIONS


def apply_bc_family_margin_loss(
    values: list[float],
    output_grad: list[float],
    actions: tuple[str, ...],
    sample: BCDatasetSample,
    config: BCFamilyMarginConfig,
    stats: BCFamilyMarginStats,
) -> float:
    if not config.enabled or not sample.family_margin_eligible:
        return 0.0
    target_index = sample.label_index
    if target_index < 0 or target_index >= len(values) or target_index >= len(actions):
        return 0.0
    target_action = actions[target_index]
    negative_indices = [
        index
        for index, action in enumerate(actions[: len(values)])
        if action != target_action and action in config.negative_actions
    ]
    if not negative_indices:
        return 0.0
    stats.sampled_rows += 1
    stats.target_action_counts[target_action] = stats.target_action_counts.get(target_action, 0) + 1
    best_negative_index = max(negative_indices, key=lambda index: (values[index], actions[index]))
    best_negative_action = actions[best_negative_index]
    stats.negative_action_counts[best_negative_action] = stats.negative_action_counts.get(best_negative_action, 0) + 1
    violation = float(values[best_negative_index]) - float(values[target_index]) + config.target_q_margin
    if violation <= 0.0:
        return 0.0
    loss_weight = config.loss_weight * max(0.0, sample.raw_adjustment)
    loss = 0.5 * loss_weight * violation * violation
    output_grad[best_negative_index] += loss_weight * violation
    output_grad[target_index] -= loss_weight * violation
    stats.violation_rows += 1
    stats.loss_total += loss
    return loss


def train_bc(
    rows: list[dict[str, object]],
    actions: tuple[str, ...],
    hidden_sizes: list[int],
    steps: int,
    batch_size: int,
    learning_rate: float,
    seed: int,
    log_interval: int,
    entropy_reg_weight: float = 0.0,
    initial_layers: list[dict[str, object]] | None = None,
    combat_event_validation: combat_events.CombatEventTrainingValidation | None = None,
    bc_event_weight_config: BCEventWeightConfig = BCEventWeightConfig(),
    bc_label_balance_config: BCLabelBalanceConfig = BCLabelBalanceConfig(),
    bc_family_margin_config: BCFamilyMarginConfig = BCFamilyMarginConfig(),
) -> tuple[
    list[dict[str, object]],
    dict[str, object],
    dict[str, int],
    dict[str, int],
    BCEventWeightStats,
    combat_events.CombatEventRewardStats,
    BCLabelBalanceStats,
    BCFamilyMarginStats,
]:
    """Train a Behavior Cloning (supervised) model from labeled transition rows."""
    rng = random.Random(seed)

    # Build labeled dataset
    label_counts: dict[str, int] = {action: 0 for action in actions}
    skipped: dict[str, int] = collections.defaultdict(int)
    dataset: list[BCDatasetSample] = []
    bc_event_weight_stats = BCEventWeightStats()
    bc_event_reward_stats = combat_events.CombatEventRewardStats()
    bc_event_reward_config = combat_events.CombatEventRewardConfig(
        enabled=bc_event_weight_config.enabled or bc_family_margin_config.enabled,
        profile=bc_event_weight_config.reward_profile,
        scale=bc_event_weight_config.reward_scale,
    )
    bc_label_balance_stats = BCLabelBalanceStats()
    bc_family_margin_stats = BCFamilyMarginStats()

    # Populate per-instance segment KW map from engine outcome rows before labeling
    global _BC_SEGMENT_KW_MAP
    _BC_SEGMENT_KW_MAP = _derive_segment_kw_map(rows)

    for row in rows:
        label_index = derive_bc_label(row, actions)
        if label_index is None:
            reason = "contact-reaction"
            r1 = int_row_field(row, "obs_self_routine_1")
            if r1 == 1:
                reason = "contact-reaction"
            elif r1 == 4:
                reason = "attack-unknown"
            else:
                reason = "no-label"
            skipped[reason] += 1
            continue
        action_name = actions[label_index]
        sample_weight = 1.0
        raw_adjustment = 0.0
        if bc_event_weight_config.enabled or bc_family_margin_config.enabled:
            raw_adjustment = combat_events.reward_adjustment_for_transition(
                combat_event_validation.index if combat_event_validation is not None else None,
                row,
                action_name,
                True,
                bc_event_reward_config,
                bc_event_reward_stats,
            )
        if bc_event_weight_config.enabled:
            if raw_adjustment > 0.0:
                sample_weight = 1.0 + raw_adjustment * bc_event_weight_config.positive_scale
            elif raw_adjustment < 0.0:
                sample_weight = 1.0 + raw_adjustment * bc_event_weight_config.negative_scale
            sample_weight = max(
                bc_event_weight_config.min_weight,
                min(bc_event_weight_config.max_weight, sample_weight),
            )
            bc_event_weight_stats.record(action_name, raw_adjustment, sample_weight, bc_event_weight_config)
        features = rl.dqn_feature_vector(row)
        family_margin_eligible = bc_family_margin_eligible(action_name, raw_adjustment, bc_family_margin_config)
        if family_margin_eligible:
            bc_family_margin_stats.eligible_rows += 1
        dataset.append(
            BCDatasetSample(
                features=features,
                label_index=label_index,
                sample_weight=sample_weight,
                raw_adjustment=raw_adjustment,
                family_margin_eligible=family_margin_eligible,
            )
        )
        label_counts[action_name] += 1

    if not dataset:
        raise SystemExit("BC training: no labeled rows found")
    if bc_label_balance_config.enabled:
        nonzero_counts = [count for count in label_counts.values() if count > 0]
        mean_count = sum(nonzero_counts) / max(1, len(nonzero_counts))
        label_factors: dict[str, float] = {}
        for action_name, count in label_counts.items():
            if count <= 0:
                continue
            raw_factor = (mean_count / float(count)) ** bc_label_balance_config.exponent
            factor = max(
                bc_label_balance_config.min_weight,
                min(bc_label_balance_config.max_weight, raw_factor),
            )
            label_factors[action_name] = factor
        dataset = [
            BCDatasetSample(
                features=sample.features,
                label_index=sample.label_index,
                sample_weight=sample.sample_weight * label_factors.get(actions[sample.label_index], 1.0),
                raw_adjustment=sample.raw_adjustment,
                family_margin_eligible=sample.family_margin_eligible,
            )
            for sample in dataset
        ]
        bc_label_balance_stats = BCLabelBalanceStats(
            balanced_rows=len(dataset),
            factor_sum=sum(label_factors.get(actions[sample.label_index], 1.0) for sample in dataset),
            label_factors=label_factors,
        )

    # Initialize layers
    input_dim = len(rl.DQN_FEATURE_NAMES)
    output_dim = len(actions)
    if initial_layers is not None:
        layers = copy.deepcopy(initial_layers)
    else:
        layers = init_network(input_dim, hidden_sizes, output_dim, rng)
    target_layers = copy.deepcopy(layers)
    grads = zero_grads(layers)

    loss = 0.0
    avg_loss = 0.0
    last_entropy_reg_loss = 0.0

    for step in range(1, steps + 1):
        batch = rng.choices(dataset, k=min(batch_size, len(dataset)))
        loss = 0.0
        entropy_reg_loss = 0.0
        family_margin_loss = 0.0
        for sample in batch:
            target_index = sample.label_index
            sample_weight = sample.sample_weight
            values, activations, pre_activations = forward(layers, sample.features)
            # Cross-entropy: softmax + NLL
            max_q = max(values)
            exp_q = [math.exp(q - max_q) for q in values]
            sum_exp = sum(exp_q)
            log_probs = [math.log(max(e / sum_exp, 1e-15)) for e in exp_q]
            ce_loss = -log_probs[target_index]
            loss += sample_weight * ce_loss

            # Gradient for cross-entropy: softmax probs, subtract 1 from target
            output_grad = [(e / sum_exp) * sample_weight for e in exp_q]
            output_grad[target_index] -= sample_weight
            entropy_loss_delta, entropy_bonus, entropy_grad = entropy_regularization_grad(
                values,
                entropy_reg_weight,
            )
            if entropy_bonus > 0.0:
                loss += entropy_loss_delta
                entropy_reg_loss += entropy_bonus
                for index, grad_value in enumerate(entropy_grad):
                    output_grad[index] += grad_value
            sample_margin_loss = apply_bc_family_margin_loss(
                values,
                output_grad,
                actions,
                sample,
                bc_family_margin_config,
                bc_family_margin_stats,
            )
            loss += sample_margin_loss
            family_margin_loss += sample_margin_loss
            add_backward_grads(layers, grads, activations, pre_activations, output_grad)

        apply_grads(layers, grads, learning_rate, batch_size)
        grads = zero_grads(layers)

        last_loss = loss / max(1, batch_size)
        avg_loss = last_loss if step == 1 else (0.98 * avg_loss + 0.02 * last_loss)
        last_entropy_reg_loss = entropy_reg_loss / max(1, batch_size)
        last_family_margin_loss = family_margin_loss / max(1, batch_size)

        if log_interval > 0 and (step == 1 or step % log_interval == 0 or step == steps):
            print(
                f"BC step={step} loss={last_loss:.6f} avg_loss={avg_loss:.6f} "
                f"entropy_reg={last_entropy_reg_loss:.6f} "
                f"family_margin={last_family_margin_loss:.6f}",
                flush=True,
            )

    train_stats = {
        "last_loss": last_loss,
        "avg_loss": avg_loss,
        "entropy_reg_weight": entropy_reg_weight,
        "event_weighting": bc_event_weight_config.as_metadata(),
        "event_weight_stats": bc_event_weight_stats.as_metadata(),
        "event_reward_stats": bc_event_reward_stats.as_metadata(),
        "label_balance": bc_label_balance_config.as_metadata(),
        "label_balance_stats": bc_label_balance_stats.as_metadata(),
        "family_margin": bc_family_margin_config.as_metadata(),
        "family_margin_stats": bc_family_margin_stats.as_metadata(),
        "combined_sample_weight_sum": sum(sample.sample_weight for sample in dataset),
        "combined_avg_sample_weight": (
            sum(sample.sample_weight for sample in dataset) / max(1, len(dataset))
        ),
    }
    label_counts_typed: dict[str, int] = dict(label_counts)
    skipped_typed: dict[str, int] = dict(skipped)
    return (
        layers,
        train_stats,
        label_counts_typed,
        skipped_typed,
        bc_event_weight_stats,
        bc_event_reward_stats,
        bc_label_balance_stats,
        bc_family_margin_stats,
    )


def int_row_field(row: dict[str, object], name: str, default: int = 0) -> int:
    try:
        return int(row.get(name, default) or default)
    except (TypeError, ValueError):
        return default


def movement_regression_action_indices(
    actions: tuple[str, ...],
    config: MovementRegressionLossConfig,
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    if not config.enabled:
        return (), ()
    movement_indices = tuple(
        index for index, action in enumerate(actions) if action in MOVEMENT_REGRESSION_MOVEMENT_ACTIONS
    )
    attack_actions: set[str] = set()
    for group in config.action_groups:
        attack_actions.update(MOVEMENT_REGRESSION_ACTION_GROUP_ACTIONS.get(group, frozenset()))
    attack_indices = tuple(index for index, action in enumerate(actions) if action in attack_actions)
    return movement_indices, attack_indices


def is_movement_regression_context(exp: Experience, config: MovementRegressionLossConfig) -> bool:
    if not config.enabled:
        return False
    if config.exclude_special_expert_eligible and exp.special_expert_margin_eligible:
        return False
    row = exp.row
    if abs(int_row_field(row, "obs_abs_dx")) < config.far_dx_threshold:
        return False
    if int_row_field(row, "obs_self_airborne") != 0:
        return False
    if int_row_field(row, "obs_projectile_active") != 0:
        return False
    if int_row_field(row, "obs_opp_routine_1") == 4:
        return False
    if int_row_field(row, "obs_opp_routine_attack_state") != 0:
        return False
    return True


def is_fireball_zoning_context(row: dict[str, object], min_abs_dx: int) -> bool:
    if abs(int_row_field(row, "obs_abs_dx")) < min_abs_dx:
        return False
    if int_row_field(row, "obs_self_airborne") != 0:
        return False
    if int_row_field(row, "obs_projectile_active") != 0:
        return False
    if int_row_field(row, "obs_opp_routine_1") == 4:
        return False
    if int_row_field(row, "obs_opp_routine_attack_state") != 0:
        return False
    return True


def apply_movement_regression_loss(
    exp: Experience,
    values: list[float],
    actions: tuple[str, ...],
    output_grad: list[float],
    movement_indices: tuple[int, ...],
    attack_indices: tuple[int, ...],
    config: MovementRegressionLossConfig,
    stats: MovementRegressionLossStats,
) -> float:
    if not movement_indices or not attack_indices or not is_movement_regression_context(exp, config):
        return 0.0
    value_count = len(values)
    valid_movement_indices = tuple(index for index in movement_indices if index < value_count)
    valid_attack_indices = tuple(index for index in attack_indices if index < value_count)
    if is_fireball_zoning_context(exp.row, config.far_dx_threshold):
        valid_attack_indices = tuple(
            index for index in valid_attack_indices if not actions[index].startswith("fireball-")
        )
    if not valid_movement_indices or not valid_attack_indices:
        return 0.0
    stats.sampled_events += 1
    best_movement_index = max(valid_movement_indices, key=lambda index: (values[index], actions[index]))
    best_attack_index = max(valid_attack_indices, key=lambda index: (values[index], actions[index]))
    violation = float(values[best_attack_index]) - float(values[best_movement_index]) + config.target_q_margin
    if violation <= 0.0:
        return 0.0
    loss = config.loss_weight * 0.5 * violation * violation
    output_grad[best_attack_index] += config.loss_weight * violation
    output_grad[best_movement_index] -= config.loss_weight * violation
    stats.violation_events += 1
    stats.loss_total += loss
    return loss


def dqn_unsupported_action_indices(
    actions: tuple[str, ...],
    action_counts: dict[str, int],
    config: DQNUnsupportedActionRegularizationConfig,
) -> tuple[list[int], DQNUnsupportedActionRegularizationStats]:
    stats = DQNUnsupportedActionRegularizationStats()
    if not config.enabled:
        return [], stats

    indices: list[int] = []
    for index, action in enumerate(actions):
        count = int(action_counts.get(action, 0))
        if count >= config.min_action_count:
            continue
        indices.append(index)
        if count <= 0:
            stats.zero_sample_actions.append(action)
        else:
            stats.low_sample_actions.append(action)
    stats.eligible_action_count = len(indices)
    return indices, stats


def dqn_masked_indices_for_row(
    row: dict[str, object],
    actions: tuple[str, ...],
    value_count: int,
    config: rl.DQNValidActionMaskConfig,
    stats: DQNValidActionMaskTrainingStats,
    context: str,
) -> tuple[int, ...]:
    count = min(len(actions), max(0, int(value_count)))
    if count <= 0:
        return ()
    if not config.enabled:
        return tuple(range(count))

    indices = rl.dqn_valid_action_indices_for_row(row, actions, config, count)
    masked_actions = [actions[index] for index in range(count) if index not in indices]
    if context == "target":
        stats.target_states += 1
        stats.target_valid_action_total += len(indices)
        stats.target_masked_action_total += len(masked_actions)
        if not indices:
            stats.target_empty_masks += 1
        for action in masked_actions:
            stats.target_masked_actions[action] = stats.target_masked_actions.get(action, 0) + 1
    elif context == "greedy":
        stats.greedy_rows += 1
        stats.greedy_valid_action_total += len(indices)
        stats.greedy_masked_action_total += len(masked_actions)
        if not indices:
            stats.greedy_empty_masks += 1
        for action in masked_actions:
            stats.greedy_masked_actions[action] = stats.greedy_masked_actions.get(action, 0) + 1
    return indices


def projectile_time_to_self_bucket(row: dict[str, object]) -> str:
    time_to_self = int_field(row, "obs_projectile_time_to_self")
    if time_to_self < 0 or time_to_self >= 32767:
        return "sentinel"
    if time_to_self <= 6:
        return "0-6"
    if time_to_self <= 12:
        return "7-12"
    if time_to_self <= 24:
        return "13-24"
    if time_to_self <= 48:
        return "25-48"
    return ">48"


def projectile_expert_margin_group_indices(
    expert_index: int,
    valid_indices: tuple[int, ...],
    actions: tuple[str, ...],
    config: ProjectileExpertMarginConfig,
) -> tuple[int, ...]:
    if expert_index < 0 or expert_index >= len(actions):
        return ()
    expert_action = actions[expert_index]
    if config.equivalent_jump_actions and expert_action in JUMP_START_ACTIONS:
        return tuple(index for index in valid_indices if actions[index] in JUMP_START_ACTIONS)
    return (expert_index,)


def apply_projectile_expert_margin_loss(
    exp: Experience,
    values: list[float],
    actions: tuple[str, ...],
    output_grad: list[float],
    config: ProjectileExpertMarginConfig,
    shared_valid_action_mask_config: rl.DQNValidActionMaskConfig,
    stats: ProjectileExpertMarginStats,
) -> float:
    if not config.enabled or not exp.projectile_expert_margin_eligible:
        return 0.0

    value_count = min(len(actions), len(values))
    valid_indices = rl.dqn_valid_action_indices_for_row(
        exp.row,
        actions,
        shared_valid_action_mask_config,
        value_count,
    )
    if not valid_indices:
        stats.empty_valid_events += 1
        return 0.0
    expert_index = exp.action_index
    if expert_index >= value_count or expert_index not in valid_indices:
        stats.expert_invalid_events += 1
        return 0.0

    expert_group_indices = projectile_expert_margin_group_indices(
        expert_index,
        valid_indices,
        actions,
        config,
    )
    if not expert_group_indices:
        stats.expert_invalid_events += 1
        return 0.0

    competitor_indices = [index for index in valid_indices if index not in expert_group_indices]
    if not competitor_indices:
        return 0.0

    stats.sampled_events += 1
    time_bucket = projectile_time_to_self_bucket(exp.row)
    stats.sampled_by_time_bucket[time_bucket] = stats.sampled_by_time_bucket.get(time_bucket, 0) + 1
    best_expert_index = max(
        expert_group_indices,
        key=lambda index: (values[index], actions[index]),
    )
    best_competitor_index = max(
        competitor_indices,
        key=lambda index: (values[index], actions[index]),
    )
    gap = float(values[best_competitor_index]) + config.margin - float(values[best_expert_index])
    if gap <= 0.0:
        return 0.0

    clipped_gap = max(-10.0, min(10.0, gap))
    weighted_loss = config.loss_weight * 0.5 * clipped_gap * clipped_gap
    output_grad[best_competitor_index] += config.loss_weight * clipped_gap
    output_grad[best_expert_index] -= config.loss_weight * clipped_gap

    expert_action = actions[expert_index]
    blocker_action = actions[best_competitor_index]
    stats.violation_events += 1
    stats.loss_total += weighted_loss
    stats.by_expert_action_events[expert_action] = stats.by_expert_action_events.get(expert_action, 0) + 1
    stats.by_expert_action_loss[expert_action] = stats.by_expert_action_loss.get(expert_action, 0.0) + weighted_loss
    stats.blocker_counts[blocker_action] = stats.blocker_counts.get(blocker_action, 0) + 1
    stats.violation_by_time_bucket[time_bucket] = stats.violation_by_time_bucket.get(time_bucket, 0) + 1
    return weighted_loss


def special_margin_bucket(action_name: str) -> str:
    for prefix in SPECIAL_ACTION_PREFIXES:
        if action_name.startswith(prefix):
            return prefix.rstrip("-")
    return "special"


def is_special_expert_margin_context(
    row: dict[str, object],
    action_name: str,
    config: SpecialExpertMarginConfig,
) -> bool:
    if not config.context_gate:
        return True
    if action_name.startswith("fireball-"):
        return is_fireball_zoning_context(row, config.fireball_min_abs_dx)
    if action_name.startswith("shoryuken-"):
        opp_routine_1 = int_row_field(row, "obs_opp_routine_1")
        opp_routine_2 = int_row_field(row, "obs_opp_routine_2")
        return opp_routine_1 == 0 and 18 <= opp_routine_2 <= 26
    if action_name.startswith("tatsu-"):
        return int_row_field(row, "obs_abs_dx") <= 120
    return False


def apply_special_expert_margin_loss(
    exp: Experience,
    values: list[float],
    actions: tuple[str, ...],
    output_grad: list[float],
    config: SpecialExpertMarginConfig,
    shared_valid_action_mask_config: rl.DQNValidActionMaskConfig,
    stats: ProjectileExpertMarginStats,
) -> float:
    if not config.enabled or not exp.special_expert_margin_eligible:
        return 0.0

    value_count = min(len(actions), len(values))
    valid_indices = rl.dqn_valid_action_indices_for_row(
        exp.row,
        actions,
        shared_valid_action_mask_config,
        value_count,
    )
    if not valid_indices:
        stats.empty_valid_events += 1
        return 0.0

    expert_index = exp.action_index
    if expert_index >= value_count or expert_index not in valid_indices:
        stats.expert_invalid_events += 1
        return 0.0

    expert_action = actions[expert_index]
    if expert_action not in SPECIAL_ACTIONS:
        stats.expert_invalid_events += 1
        return 0.0
    if not is_special_expert_margin_context(exp.row, expert_action, config):
        stats.expert_invalid_events += 1
        return 0.0

    competitor_indices = [index for index in valid_indices if index != expert_index]
    if not competitor_indices:
        return 0.0

    stats.sampled_events += 1
    bucket = special_margin_bucket(expert_action)
    stats.sampled_by_time_bucket[bucket] = stats.sampled_by_time_bucket.get(bucket, 0) + 1
    best_competitor_index = max(
        competitor_indices,
        key=lambda index: (values[index], actions[index]),
    )
    gap = float(values[best_competitor_index]) + config.margin - float(values[expert_index])
    if gap <= 0.0:
        return 0.0

    clipped_gap = max(-10.0, min(10.0, gap))
    weighted_loss = config.loss_weight * 0.5 * clipped_gap * clipped_gap
    output_grad[best_competitor_index] += config.loss_weight * clipped_gap
    output_grad[expert_index] -= config.loss_weight * clipped_gap

    blocker_action = actions[best_competitor_index]
    stats.violation_events += 1
    stats.loss_total += weighted_loss
    stats.by_expert_action_events[expert_action] = stats.by_expert_action_events.get(expert_action, 0) + 1
    stats.by_expert_action_loss[expert_action] = stats.by_expert_action_loss.get(expert_action, 0.0) + weighted_loss
    stats.blocker_counts[blocker_action] = stats.blocker_counts.get(blocker_action, 0) + 1
    stats.violation_by_time_bucket[bucket] = stats.violation_by_time_bucket.get(bucket, 0) + 1
    return weighted_loss


def _grounded_normal_defense_time_bucket(row: dict[str, object]) -> str:
    abs_dx = int_field(row, "obs_abs_dx")
    if abs_dx <= 64:
        return "close"
    if abs_dx <= 144:
        return "mid"
    return "far"


def apply_grounded_normal_defense_margin_loss(
    exp: Experience,
    values: list[float],
    actions: tuple[str, ...],
    output_grad: list[float],
    config: GroundedNormalDefenseMarginConfig,
    shared_valid_action_mask_config: rl.DQNValidActionMaskConfig,
    stats: GroundedNormalDefenseMarginStats,
) -> float:
    if not config.enabled or not exp.grounded_normal_defense_eligible:
        return 0.0

    value_count = min(len(actions), len(values))
    valid_indices = rl.dqn_valid_action_indices_for_row(
        exp.row,
        actions,
        shared_valid_action_mask_config,
        value_count,
    )
    if not valid_indices:
        stats.empty_valid_events += 1
        return 0.0

    safe_indices = [
        i for i in valid_indices
        if actions[i] in GROUNDED_NORMAL_DEFENSE_SAFE_ACTIONS
    ]
    unsafe_indices = [
        i for i in valid_indices
        if actions[i] in GROUNDED_NORMAL_DEFENSE_UNSAFE_ACTIONS
    ]
    if not safe_indices:
        stats.empty_safe_events += 1
        return 0.0
    if not unsafe_indices:
        stats.empty_unsafe_events += 1
        return 0.0
    if not is_grounded_normal_defense_context(exp.row, config):
        stats.empty_context_events += 1
        return 0.0

    stats.sampled_events += 1
    time_bucket = _grounded_normal_defense_time_bucket(exp.row)
    stats.sampled_by_time_bucket[time_bucket] = stats.sampled_by_time_bucket.get(time_bucket, 0) + 1

    best_safe_index = max(safe_indices, key=lambda i: (values[i], actions[i]))
    best_unsafe_index = max(unsafe_indices, key=lambda i: (values[i], actions[i]))
    gap = float(values[best_unsafe_index]) + config.margin - float(values[best_safe_index])
    if gap <= 0.0:
        return 0.0

    clipped_gap = max(-10.0, min(10.0, gap))
    weighted_loss = config.loss_weight * 0.5 * clipped_gap * clipped_gap
    output_grad[best_unsafe_index] -= config.loss_weight * clipped_gap
    output_grad[best_safe_index] += config.loss_weight * clipped_gap

    blocker_action = actions[best_unsafe_index]
    safe_action = actions[best_safe_index]
    stats.violation_events += 1
    stats.loss_total += weighted_loss
    stats.blocker_counts[blocker_action] = stats.blocker_counts.get(blocker_action, 0) + 1
    stats.safe_top_actions[safe_action] = stats.safe_top_actions.get(safe_action, 0) + 1
    stats.violation_by_time_bucket[time_bucket] = stats.violation_by_time_bucket.get(time_bucket, 0) + 1
    return weighted_loss


def apply_low_defense_margin_loss(
    exp: Experience,
    values: list[float],
    actions: tuple[str, ...],
    output_grad: list[float],
    config: LowDefenseConfig,
    shared_valid_action_mask_config: rl.DQNValidActionMaskConfig,
    stats: LowDefenseStats,
) -> float:
    if not config.margin_enabled or not exp.low_defense_margin_eligible:
        return 0.0

    value_count = min(len(actions), len(values))
    valid_indices = rl.dqn_valid_action_indices_for_row(
        exp.row,
        actions,
        shared_valid_action_mask_config,
        value_count,
    )
    if not valid_indices:
        stats.empty_valid_events += 1
        return 0.0

    target_indices = [i for i in valid_indices if actions[i] == LOW_DEFENSE_TARGET_ACTION]
    competitor_indices = [i for i in valid_indices if actions[i] in LOW_DEFENSE_BAD_ACTIONS]
    if not target_indices:
        stats.empty_target_events += 1
        return 0.0
    if not competitor_indices:
        stats.empty_competitor_events += 1
        return 0.0

    stats.sampled_events += 1
    time_bucket = _grounded_normal_defense_time_bucket(exp.row)
    stats.sampled_by_time_bucket[time_bucket] = stats.sampled_by_time_bucket.get(time_bucket, 0) + 1

    target_index = target_indices[0]
    best_competitor_index = max(competitor_indices, key=lambda i: (values[i], actions[i]))
    gap = float(values[best_competitor_index]) + config.margin - float(values[target_index])
    if gap <= 0.0:
        return 0.0

    clipped_gap = max(-10.0, min(10.0, gap))
    weighted_loss = config.loss_weight * 0.5 * clipped_gap * clipped_gap
    output_grad[best_competitor_index] += config.loss_weight * clipped_gap
    output_grad[target_index] -= config.loss_weight * clipped_gap

    blocker_action = actions[best_competitor_index]
    stats.violation_events += 1
    stats.loss_total += weighted_loss
    stats.blocker_counts[blocker_action] = stats.blocker_counts.get(blocker_action, 0) + 1
    stats.violation_by_time_bucket[time_bucket] = stats.violation_by_time_bucket.get(time_bucket, 0) + 1
    return weighted_loss


def apply_projectile_late_defensive_margin_loss(
    exp: Experience,
    values: list[float],
    actions: tuple[str, ...],
    output_grad: list[float],
    config: ProjectileLateDefensiveMarginConfig,
    shared_valid_action_mask_config: rl.DQNValidActionMaskConfig,
    stats: ProjectileLateDefensiveMarginStats,
) -> float:
    if not config.enabled or not exp.projectile_late_defensive_margin_eligible:
        return 0.0

    value_count = min(len(actions), len(values))
    valid_indices = rl.dqn_valid_action_indices_for_row(
        exp.row,
        actions,
        shared_valid_action_mask_config,
        value_count,
    )
    if not valid_indices:
        stats.empty_valid_events += 1
        return 0.0

    defensive_indices = tuple(index for index in valid_indices if actions[index] in DEFENSIVE_PROJECTILE_ACTIONS)
    jump_indices = tuple(index for index in valid_indices if actions[index] in JUMP_START_ACTIONS)
    if not defensive_indices:
        stats.empty_defensive_events += 1
        return 0.0
    if not jump_indices:
        stats.empty_jump_events += 1
        return 0.0

    stats.sampled_events += 1
    time_bucket = projectile_time_to_self_bucket(exp.row)
    stats.sampled_by_time_bucket[time_bucket] = stats.sampled_by_time_bucket.get(time_bucket, 0) + 1
    best_defensive_index = max(
        defensive_indices,
        key=lambda index: (values[index], actions[index]),
    )
    best_jump_index = max(
        jump_indices,
        key=lambda index: (values[index], actions[index]),
    )
    gap = float(values[best_jump_index]) + config.margin - float(values[best_defensive_index])
    if gap <= 0.0:
        return 0.0

    clipped_gap = max(-10.0, min(10.0, gap))
    weighted_loss = config.loss_weight * 0.5 * clipped_gap * clipped_gap
    output_grad[best_jump_index] += config.loss_weight * clipped_gap
    output_grad[best_defensive_index] -= config.loss_weight * clipped_gap

    defensive_action = actions[best_defensive_index]
    jump_action = actions[best_jump_index]
    stats.violation_events += 1
    stats.loss_total += weighted_loss
    stats.defensive_action_events[defensive_action] = stats.defensive_action_events.get(defensive_action, 0) + 1
    stats.jump_blocker_counts[jump_action] = stats.jump_blocker_counts.get(jump_action, 0) + 1
    stats.violation_by_time_bucket[time_bucket] = stats.violation_by_time_bucket.get(time_bucket, 0) + 1
    return weighted_loss


def apply_projectile_defensive_expert_margin_loss(
    exp: Experience,
    values: list[float],
    actions: tuple[str, ...],
    output_grad: list[float],
    config: ProjectileDefensiveExpertMarginConfig,
    shared_valid_action_mask_config: rl.DQNValidActionMaskConfig,
    stats: ProjectileDefensiveExpertMarginStats,
) -> float:
    if not config.enabled or not exp.projectile_defensive_expert_margin_eligible:
        return 0.0

    value_count = min(len(actions), len(values))
    valid_indices = rl.dqn_valid_action_indices_for_row(
        exp.row,
        actions,
        shared_valid_action_mask_config,
        value_count,
    )
    if not valid_indices:
        stats.empty_valid_events += 1
        return 0.0

    defensive_indices = tuple(index for index in valid_indices if actions[index] in DEFENSIVE_PROJECTILE_ACTIONS)
    competitor_indices = tuple(
        index for index in valid_indices if actions[index] in PROJECTILE_DEFENSIVE_EXPERT_COMPETITOR_ACTIONS
    )
    if not defensive_indices:
        stats.empty_defensive_events += 1
        return 0.0
    if not competitor_indices:
        stats.empty_competitor_events += 1
        return 0.0

    stats.sampled_events += 1
    time_bucket = projectile_time_to_self_bucket(exp.row)
    stats.sampled_by_time_bucket[time_bucket] = stats.sampled_by_time_bucket.get(time_bucket, 0) + 1
    best_defensive_index = max(
        defensive_indices,
        key=lambda index: (values[index], actions[index]),
    )
    competitor_gaps: list[tuple[int, float]] = []
    if config.all_competitors:
        for competitor_index in competitor_indices:
            gap = float(values[competitor_index]) + config.margin - float(values[best_defensive_index])
            if gap > 0.0:
                competitor_gaps.append((competitor_index, max(-10.0, min(10.0, gap))))
    else:
        best_competitor_index = max(
            competitor_indices,
            key=lambda index: (values[index], actions[index]),
        )
        gap = float(values[best_competitor_index]) + config.margin - float(values[best_defensive_index])
        if gap > 0.0:
            competitor_gaps.append((best_competitor_index, max(-10.0, min(10.0, gap))))
    if not competitor_gaps:
        return 0.0

    competitor_scale = config.loss_weight / max(1, len(competitor_gaps)) if config.all_competitors else config.loss_weight
    weighted_loss = 0.0
    for competitor_index, clipped_gap in competitor_gaps:
        weighted_loss += competitor_scale * 0.5 * clipped_gap * clipped_gap
        output_grad[competitor_index] += competitor_scale * clipped_gap
        output_grad[best_defensive_index] -= competitor_scale * clipped_gap

    defensive_action = actions[best_defensive_index]
    blocker_index, _blocker_gap = max(competitor_gaps, key=lambda item: (item[1], actions[item[0]]))
    blocker_action = actions[blocker_index]
    stats.violation_events += 1
    stats.loss_total += weighted_loss
    stats.defensive_action_events[defensive_action] = stats.defensive_action_events.get(defensive_action, 0) + 1
    stats.competitor_blocker_counts[blocker_action] = stats.competitor_blocker_counts.get(blocker_action, 0) + 1
    stats.violation_by_time_bucket[time_bucket] = stats.violation_by_time_bucket.get(time_bucket, 0) + 1
    return weighted_loss


def projectile_timing_group_target(exp: Experience, config: ProjectileTimingGroupMarginConfig) -> str:
    if not config.enabled:
        return ""
    if exp.source_name not in config.eligible_sources:
        return ""
    row = exp.row
    if int_field(row, "obs_projectile_active") == 0:
        return ""
    if int_field(row, "obs_projectile_owner") != PROJECTILE_OWNER_OPPONENT:
        return ""
    rel_x = int_field(row, "obs_projectile_rel_x")
    rel_y = int_field(row, "obs_projectile_rel_y")
    vel_x = int_field(row, "obs_projectile_vel_x")
    if rel_x <= 0 or rel_x > config.threat_max_dx or abs(rel_y) > config.threat_max_abs_y or vel_x >= 0:
        return ""
    time_to_self = int_field(row, "obs_projectile_time_to_self")
    if time_to_self_in_ranges(time_to_self, config.defense_time_ranges):
        return "defense"
    if time_to_self_in_ranges(time_to_self, config.jump_time_ranges):
        return "jump"
    return ""


def apply_projectile_timing_group_margin_loss(
    exp: Experience,
    values: list[float],
    actions: tuple[str, ...],
    output_grad: list[float],
    config: ProjectileTimingGroupMarginConfig,
    shared_valid_action_mask_config: rl.DQNValidActionMaskConfig,
    stats: ProjectileTimingGroupMarginStats,
) -> float:
    target_group = projectile_timing_group_target(exp, config)
    if not target_group:
        return 0.0

    value_count = min(len(actions), len(values))
    valid_indices = rl.dqn_valid_action_indices_for_row(
        exp.row,
        actions,
        shared_valid_action_mask_config,
        value_count,
    )
    if not valid_indices:
        stats.empty_valid_events += 1
        return 0.0

    if target_group == "defense":
        target_indices = tuple(index for index in valid_indices if actions[index] in DEFENSIVE_PROJECTILE_ACTIONS)
        competitor_indices = tuple(
            index for index in valid_indices if actions[index] in PROJECTILE_DEFENSIVE_EXPERT_COMPETITOR_ACTIONS
        )
    else:
        target_indices = tuple(index for index in valid_indices if actions[index] in JUMP_START_ACTIONS)
        competitor_indices = tuple(index for index in valid_indices if actions[index] not in JUMP_START_ACTIONS)
    if not target_indices:
        stats.empty_target_events += 1
        return 0.0
    if not competitor_indices:
        stats.empty_competitor_events += 1
        return 0.0

    stats.sampled_events += 1
    stats.sampled_by_target[target_group] = stats.sampled_by_target.get(target_group, 0) + 1
    time_bucket = projectile_time_to_self_bucket(exp.row)
    stats.sampled_by_time_bucket[time_bucket] = stats.sampled_by_time_bucket.get(time_bucket, 0) + 1
    best_target_index = max(target_indices, key=lambda index: (values[index], actions[index]))
    best_target_value = float(values[best_target_index])
    competitor_gaps: list[tuple[int, float]] = []
    for competitor_index in competitor_indices:
        gap = float(values[competitor_index]) + config.margin - best_target_value
        if gap > 0.0:
            competitor_gaps.append((competitor_index, max(-10.0, min(10.0, gap))))
    if not competitor_gaps:
        return 0.0

    competitor_scale = config.loss_weight / max(1, len(competitor_gaps))
    weighted_loss = 0.0
    for competitor_index, clipped_gap in competitor_gaps:
        weighted_loss += competitor_scale * 0.5 * clipped_gap * clipped_gap
        output_grad[competitor_index] += competitor_scale * clipped_gap
        output_grad[best_target_index] -= competitor_scale * clipped_gap

    blocker_index, _blocker_gap = max(competitor_gaps, key=lambda item: (item[1], actions[item[0]]))
    blocker_action = actions[blocker_index]
    stats.violation_events += 1
    stats.loss_total += weighted_loss
    stats.violation_by_target[target_group] = stats.violation_by_target.get(target_group, 0) + 1
    stats.violation_by_time_bucket[time_bucket] = stats.violation_by_time_bucket.get(time_bucket, 0) + 1
    stats.blocker_counts[blocker_action] = stats.blocker_counts.get(blocker_action, 0) + 1
    return weighted_loss


def projectile_expert_q_gap_diagnostics(
    layers: list[dict[str, object]],
    experiences: list[Experience],
    actions: tuple[str, ...],
    config: ProjectileExpertMarginConfig,
) -> ProjectileExpertQGapDiagnostics:
    stats = ProjectileExpertQGapDiagnostics()
    if not config.requested:
        return stats

    shared_valid_action_mask_config = config.as_shared_mask_config()
    unique_rows: set[tuple[int, int, int, int]] = set()
    for exp in experiences:
        if not exp.projectile_expert_margin_eligible:
            continue
        values, _, _ = forward(layers, exp.state)
        value_count = min(len(actions), len(values))
        valid_indices = rl.dqn_valid_action_indices_for_row(
            exp.row,
            actions,
            shared_valid_action_mask_config,
            value_count,
        )
        if not valid_indices:
            stats.empty_valid_rows += 1
            continue
        expert_index = exp.action_index
        if expert_index >= value_count or expert_index not in valid_indices:
            stats.invalid_expert_rows += 1
            continue
        expert_group_indices = projectile_expert_margin_group_indices(
            expert_index,
            valid_indices,
            actions,
            config,
        )
        if not expert_group_indices:
            stats.invalid_expert_rows += 1
            continue

        ranked = sorted(
            valid_indices,
            key=lambda index: (values[index], actions[index]),
            reverse=True,
        )
        expert_rank = min(ranked.index(index) + 1 for index in expert_group_indices)
        top_index = ranked[0]
        top_action = actions[top_index]
        expert_action = actions[expert_index]
        best_expert_index = max(
            expert_group_indices,
            key=lambda index: (values[index], actions[index]),
        )
        competitor_indices = [index for index in valid_indices if index not in expert_group_indices]
        best_competitor_index = (
            max(competitor_indices, key=lambda index: (values[index], actions[index]))
            if competitor_indices
            else best_expert_index
        )
        gap = float(values[best_competitor_index]) - float(values[best_expert_index])
        time_bucket = projectile_time_to_self_bucket(exp.row)

        stats.rows += 1
        unique_rows.add(
            (
                int_field(exp.row, "run_id"),
                int_field(exp.row, "episode_id"),
                int_field(exp.row, "decision_id"),
                expert_index,
            )
        )
        stats.expert_rank_sum += expert_rank
        stats.rows_by_time_bucket[time_bucket] = stats.rows_by_time_bucket.get(time_bucket, 0) + 1
        stats.gap_sum += gap
        stats.gap_min = gap if stats.gap_min is None else min(stats.gap_min, gap)
        stats.gap_max = gap if stats.gap_max is None else max(stats.gap_max, gap)
        if gap > 0.0:
            stats.positive_gap_rows += 1
            stats.positive_gap_sum += gap
            stats.positive_gap_by_time_bucket[time_bucket] = (
                stats.positive_gap_by_time_bucket.get(time_bucket, 0) + 1
            )
        if expert_rank == 1:
            stats.top1_matches += 1
            stats.top1_by_time_bucket[time_bucket] = stats.top1_by_time_bucket.get(time_bucket, 0) + 1
        if expert_rank <= 5:
            stats.top5_matches += 1
        stats.by_expert_action[expert_action] = stats.by_expert_action.get(expert_action, 0) + 1
        stats.top_action_counts[top_action] = stats.top_action_counts.get(top_action, 0) + 1
        bucket_top_actions = stats.top_action_counts_by_time_bucket.setdefault(time_bucket, {})
        bucket_top_actions[top_action] = bucket_top_actions.get(top_action, 0) + 1
        if top_index not in expert_group_indices:
            stats.blocker_counts[top_action] = stats.blocker_counts.get(top_action, 0) + 1
            bucket_blockers = stats.blocker_counts_by_time_bucket.setdefault(time_bucket, {})
            bucket_blockers[top_action] = bucket_blockers.get(top_action, 0) + 1

    stats.unique_rows = len(unique_rows)
    return stats


def train_dqn(
    experiences: list[Experience],
    actions: tuple[str, ...],
    action_counts: dict[str, int],
    hidden_sizes: list[int],
    steps: int,
    batch_size: int,
    learning_rate: float,
    gamma: float,
    target_sync_steps: int,
    seed: int,
    log_interval: int,
    batch_sampling_config: BatchSamplingConfig,
    combat_event_batch_sampling_config: CombatEventBatchSamplingConfig,
    target_mode: str,
    unsupported_action_regularization_config: DQNUnsupportedActionRegularizationConfig,
    movement_regression_config: MovementRegressionLossConfig,
    projectile_expert_margin_config: ProjectileExpertMarginConfig,
    special_expert_margin_config: SpecialExpertMarginConfig,
    projectile_late_defensive_margin_config: ProjectileLateDefensiveMarginConfig,
    projectile_defensive_expert_margin_config: ProjectileDefensiveExpertMarginConfig,
    projectile_timing_group_margin_config: ProjectileTimingGroupMarginConfig,
    grounded_normal_defense_margin_config: GroundedNormalDefenseMarginConfig,
    grounded_normal_defense_bc_config: GroundedNormalDefenseBCConfig,
    low_defense_config: LowDefenseConfig,
    valid_action_mask_config: DQNValidActionMaskTrainingConfig,
    entropy_reg_weight: float = 0.0,
    initial_layers: list[dict[str, object]] | None = None,
) -> tuple[
    list[dict[str, object]],
    dict[str, object],
    DQNUnsupportedActionRegularizationStats,
    MovementRegressionLossStats,
    ProjectileExpertMarginStats,
    ProjectileExpertMarginStats,
    ProjectileLateDefensiveMarginStats,
    ProjectileDefensiveExpertMarginStats,
    ProjectileTimingGroupMarginStats,
    GroundedNormalDefenseMarginStats,
    GroundedNormalDefenseBCStats,
    LowDefenseStats,
    DQNValidActionMaskTrainingStats,
]:
    rng = random.Random(seed)
    layers = copy.deepcopy(initial_layers) if initial_layers is not None else init_network(
        len(rl.DQN_FEATURE_NAMES),
        hidden_sizes,
        len(actions),
        rng,
    )
    target_layers = copy.deepcopy(layers)
    batch_pools = build_batch_pools(experiences, actions)
    combat_event_batch_pools = build_combat_event_batch_pools(experiences)
    batch_target_counts = (
        balanced_target_counts(batch_size, batch_sampling_config.ratios)
        if batch_sampling_config.mode == "balanced"
        else {}
    )
    combat_event_batch_target_counts = (
        balanced_target_counts_for_groups(
            batch_size,
            combat_event_batch_sampling_config.ratios,
            COMBAT_EVENT_BATCH_GROUPS,
        )
        if combat_event_batch_sampling_config.enabled
        else {}
    )
    last_loss = 0.0
    avg_loss = 0.0
    last_unsupported_regularization_loss = 0.0
    avg_unsupported_regularization_loss = 0.0
    last_movement_regression_loss = 0.0
    avg_movement_regression_loss = 0.0
    last_entropy_reg_loss = 0.0
    avg_entropy_reg_loss = 0.0
    last_projectile_margin_loss = 0.0
    avg_projectile_margin_loss = 0.0
    last_special_margin_loss = 0.0
    avg_special_margin_loss = 0.0
    last_projectile_late_defensive_margin_loss = 0.0
    avg_projectile_late_defensive_margin_loss = 0.0
    last_projectile_defensive_expert_margin_loss = 0.0
    avg_projectile_defensive_expert_margin_loss = 0.0
    last_projectile_timing_group_margin_loss = 0.0
    avg_projectile_timing_group_margin_loss = 0.0
    last_grounded_normal_defense_margin_loss = 0.0
    avg_grounded_normal_defense_margin_loss = 0.0
    last_grounded_normal_defense_bc_loss = 0.0
    avg_grounded_normal_defense_bc_loss = 0.0
    last_low_defense_margin_loss = 0.0
    avg_low_defense_margin_loss = 0.0
    unsupported_action_indices, unsupported_action_regularization_stats = dqn_unsupported_action_indices(
        actions,
        action_counts,
        unsupported_action_regularization_config,
    )
    movement_regression_indices, movement_regression_attack_indices = movement_regression_action_indices(
        actions,
        movement_regression_config,
    )
    movement_regression_stats = MovementRegressionLossStats(
        eligible_experiences=sum(
            1 for exp in experiences if is_movement_regression_context(exp, movement_regression_config)
        )
    )
    projectile_expert_margin_stats = ProjectileExpertMarginStats(
        eligible_experiences=sum(1 for exp in experiences if exp.projectile_expert_margin_eligible)
    )
    projectile_expert_margin_pool = [
        exp for exp in experiences if exp.projectile_expert_margin_eligible
    ]
    special_expert_margin_stats = ProjectileExpertMarginStats(
        eligible_experiences=sum(1 for exp in experiences if exp.special_expert_margin_eligible)
    )
    special_expert_margin_pool = [
        exp for exp in experiences if exp.special_expert_margin_eligible
    ]
    projectile_late_defensive_margin_stats = ProjectileLateDefensiveMarginStats(
        eligible_experiences=sum(1 for exp in experiences if exp.projectile_late_defensive_margin_eligible)
    )
    projectile_late_defensive_margin_pool = [
        exp for exp in experiences if exp.projectile_late_defensive_margin_eligible
    ]
    projectile_defensive_expert_margin_stats = ProjectileDefensiveExpertMarginStats(
        eligible_experiences=sum(1 for exp in experiences if exp.projectile_defensive_expert_margin_eligible)
    )
    projectile_defensive_expert_margin_pool = [
        exp for exp in experiences if exp.projectile_defensive_expert_margin_eligible
    ]
    projectile_timing_group_margin_stats = ProjectileTimingGroupMarginStats(
        eligible_experiences=sum(
            1 for exp in experiences if projectile_timing_group_target(exp, projectile_timing_group_margin_config)
        )
    )
    projectile_timing_group_margin_pool = [
        exp for exp in experiences if projectile_timing_group_target(exp, projectile_timing_group_margin_config)
    ]
    grounded_normal_defense_stats = GroundedNormalDefenseMarginStats(
        eligible_experiences=sum(1 for exp in experiences if exp.grounded_normal_defense_eligible)
    )
    grounded_normal_defense_pool = [
        exp for exp in experiences if exp.grounded_normal_defense_eligible
    ]
    grounded_normal_defense_bc_stats = GroundedNormalDefenseBCStats(
        eligible_experiences=sum(1 for exp in experiences if exp.grounded_normal_defense_bc_eligible)
    )
    grounded_normal_defense_bc_pool = [
        exp for exp in experiences if exp.grounded_normal_defense_bc_eligible
    ]
    low_defense_stats = LowDefenseStats(
        eligible_experiences=sum(1 for exp in experiences if exp.low_defense_margin_eligible)
    )
    low_defense_pool = [
        exp for exp in experiences if exp.low_defense_margin_eligible
    ]
    shared_valid_action_mask_config = valid_action_mask_config.as_shared_config()
    projectile_expert_margin_mask_config = projectile_expert_margin_config.as_shared_mask_config()
    special_expert_margin_mask_config = special_expert_margin_config.as_shared_mask_config()
    projectile_late_defensive_margin_mask_config = projectile_late_defensive_margin_config.as_shared_mask_config()
    projectile_defensive_expert_margin_mask_config = projectile_defensive_expert_margin_config.as_shared_mask_config()
    projectile_timing_group_margin_mask_config = projectile_timing_group_margin_config.as_shared_mask_config()
    grounded_normal_defense_mask_config = grounded_normal_defense_margin_config.as_shared_mask_config()
    low_defense_mask_config = low_defense_config.as_shared_mask_config()
    valid_action_mask_stats = DQNValidActionMaskTrainingStats()

    for step in range(1, steps + 1):
        if combat_event_batch_sampling_config.enabled:
            batch = sample_grouped_training_batch(
                experiences,
                combat_event_batch_pools,
                COMBAT_EVENT_BATCH_GROUPS,
                combat_event_batch_target_counts,
                batch_size,
                rng,
            )
        else:
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
        unsupported_regularization_loss = 0.0
        movement_regression_loss = 0.0
        projectile_margin_loss = 0.0
        special_margin_loss = 0.0
        projectile_late_defensive_margin_loss = 0.0
        projectile_defensive_expert_margin_loss = 0.0
        projectile_timing_group_margin_loss = 0.0
        grounded_normal_defense_margin_loss = 0.0
        grounded_normal_defense_bc_loss = 0.0
        low_defense_margin_loss = 0.0
        entropy_reg_loss = 0.0
        for exp in batch:
            values, activations, pre_activations = forward(layers, exp.state)
            next_values, _, _ = forward(target_layers, exp.next_state)
            if exp.done:
                target = exp.reward
            elif target_mode == "double":
                online_next_values, _, _ = forward(layers, exp.next_state)
                next_count = min(len(actions), len(online_next_values), len(next_values))
                valid_next_indices = dqn_masked_indices_for_row(
                    exp.next_row,
                    actions,
                    next_count,
                    shared_valid_action_mask_config,
                    valid_action_mask_stats,
                    "target",
                )
                if valid_next_indices:
                    best_next_index = max(
                        valid_next_indices,
                        key=lambda index: (online_next_values[index], actions[index]),
                    )
                    target = exp.reward + gamma * next_values[best_next_index]
                else:
                    target = exp.reward
            else:
                next_count = min(len(actions), len(next_values))
                valid_next_indices = dqn_masked_indices_for_row(
                    exp.next_row,
                    actions,
                    next_count,
                    shared_valid_action_mask_config,
                    valid_action_mask_stats,
                    "target",
                )
                if valid_next_indices:
                    target = exp.reward + gamma * max(next_values[index] for index in valid_next_indices)
                else:
                    target = exp.reward
            error = max(-10.0, min(10.0, values[exp.action_index] - target))
            loss += 0.5 * error * error
            output_grad = [0.0 for _ in values]
            output_grad[exp.action_index] = error
            if unsupported_action_indices:
                regularization_denom = max(1, len(unsupported_action_indices))
                effective_ceiling = unsupported_action_regularization_config.q_ceiling
                if unsupported_action_regularization_config.adaptive_ceiling:
                    movement_q = [
                        float(values[idx]) for idx in movement_regression_indices if idx < len(values)
                    ]
                    if movement_q:
                        movement_mean = sum(movement_q) / len(movement_q)
                        effective_ceiling = min(effective_ceiling, movement_mean)
                for action_index in unsupported_action_indices:
                    if action_index >= len(values):
                        continue
                    excess_q = float(values[action_index]) - effective_ceiling
                    if excess_q <= 0.0:
                        continue
                    weighted_loss = (
                        unsupported_action_regularization_config.loss_weight
                        * 0.5
                        * excess_q
                        * excess_q
                        / regularization_denom
                    )
                    output_grad[action_index] += (
                        unsupported_action_regularization_config.loss_weight
                        * excess_q
                        / regularization_denom
                    )
                    loss += weighted_loss
                    unsupported_regularization_loss += weighted_loss
                    action = actions[action_index]
                    unsupported_action_regularization_stats.regularized_events += 1
                    unsupported_action_regularization_stats.regularized_loss_total += weighted_loss
                    unsupported_action_regularization_stats.per_action_events[action] = (
                        unsupported_action_regularization_stats.per_action_events.get(action, 0) + 1
                    )
                    unsupported_action_regularization_stats.per_action_loss[action] = (
                        unsupported_action_regularization_stats.per_action_loss.get(action, 0.0) + weighted_loss
                    )
            exp_movement_regression_loss = apply_movement_regression_loss(
                exp,
                values,
                actions,
                output_grad,
                movement_regression_indices,
                movement_regression_attack_indices,
                movement_regression_config,
                movement_regression_stats,
            )
            movement_regression_loss += exp_movement_regression_loss
            loss += exp_movement_regression_loss
            exp_projectile_margin_loss = apply_projectile_expert_margin_loss(
                exp,
                values,
                actions,
                output_grad,
                projectile_expert_margin_config,
                projectile_expert_margin_mask_config,
                projectile_expert_margin_stats,
            )
            projectile_margin_loss += exp_projectile_margin_loss
            loss += exp_projectile_margin_loss
            exp_special_margin_loss = apply_special_expert_margin_loss(
                exp,
                values,
                actions,
                output_grad,
                special_expert_margin_config,
                special_expert_margin_mask_config,
                special_expert_margin_stats,
            )
            special_margin_loss += exp_special_margin_loss
            loss += exp_special_margin_loss
            exp_late_defensive_margin_loss = apply_projectile_late_defensive_margin_loss(
                exp,
                values,
                actions,
                output_grad,
                projectile_late_defensive_margin_config,
                projectile_late_defensive_margin_mask_config,
                projectile_late_defensive_margin_stats,
            )
            projectile_late_defensive_margin_loss += exp_late_defensive_margin_loss
            loss += exp_late_defensive_margin_loss
            exp_defensive_expert_margin_loss = apply_projectile_defensive_expert_margin_loss(
                exp,
                values,
                actions,
                output_grad,
                projectile_defensive_expert_margin_config,
                projectile_defensive_expert_margin_mask_config,
                projectile_defensive_expert_margin_stats,
            )
            projectile_defensive_expert_margin_loss += exp_defensive_expert_margin_loss
            loss += exp_defensive_expert_margin_loss
            exp_timing_group_margin_loss = apply_projectile_timing_group_margin_loss(
                exp,
                values,
                actions,
                output_grad,
                projectile_timing_group_margin_config,
                projectile_timing_group_margin_mask_config,
                projectile_timing_group_margin_stats,
            )
            projectile_timing_group_margin_loss += exp_timing_group_margin_loss
            loss += exp_timing_group_margin_loss
            exp_grounded_normal_defense_loss = apply_grounded_normal_defense_margin_loss(
                exp,
                values,
                actions,
                output_grad,
                grounded_normal_defense_margin_config,
                grounded_normal_defense_mask_config,
                grounded_normal_defense_stats,
            )
            grounded_normal_defense_margin_loss += exp_grounded_normal_defense_loss
            loss += exp_grounded_normal_defense_loss
            exp_grounded_defense_bc_loss = apply_grounded_normal_defense_bc_loss(
                exp,
                values,
                actions,
                output_grad,
                grounded_normal_defense_bc_config,
                grounded_normal_defense_bc_stats,
            )
            grounded_normal_defense_bc_loss += exp_grounded_defense_bc_loss
            loss += exp_grounded_defense_bc_loss
            exp_low_defense_loss = apply_low_defense_margin_loss(
                exp,
                values,
                actions,
                output_grad,
                low_defense_config,
                low_defense_mask_config,
                low_defense_stats,
            )
            low_defense_margin_loss += exp_low_defense_loss
            loss += exp_low_defense_loss
            entropy_loss_delta, entropy_bonus, entropy_grad = entropy_regularization_grad(
                values,
                entropy_reg_weight,
            )
            if entropy_bonus > 0.0:
                loss += entropy_loss_delta
                entropy_reg_loss += entropy_bonus
                for index, grad_value in enumerate(entropy_grad):
                    output_grad[index] += grad_value
            add_backward_grads(layers, grads, activations, pre_activations, output_grad)
        if projectile_expert_margin_config.enabled and projectile_expert_margin_pool:
            for _ in range(max(0, projectile_expert_margin_config.batch_size)):
                exp = rng.choice(projectile_expert_margin_pool)
                values, activations, pre_activations = forward(layers, exp.state)
                output_grad = [0.0 for _ in values]
                exp_projectile_margin_loss = apply_projectile_expert_margin_loss(
                    exp,
                    values,
                    actions,
                    output_grad,
                    projectile_expert_margin_config,
                    projectile_expert_margin_mask_config,
                    projectile_expert_margin_stats,
                )
                projectile_margin_loss += exp_projectile_margin_loss
                loss += exp_projectile_margin_loss
                if exp_projectile_margin_loss > 0.0:
                    add_backward_grads(layers, grads, activations, pre_activations, output_grad)
        if special_expert_margin_config.enabled and special_expert_margin_pool:
            for _ in range(max(0, special_expert_margin_config.batch_size)):
                exp = rng.choice(special_expert_margin_pool)
                values, activations, pre_activations = forward(layers, exp.state)
                output_grad = [0.0 for _ in values]
                exp_special_margin_loss = apply_special_expert_margin_loss(
                    exp,
                    values,
                    actions,
                    output_grad,
                    special_expert_margin_config,
                    special_expert_margin_mask_config,
                    special_expert_margin_stats,
                )
                special_margin_loss += exp_special_margin_loss
                loss += exp_special_margin_loss
                if exp_special_margin_loss > 0.0:
                    add_backward_grads(layers, grads, activations, pre_activations, output_grad)
        if projectile_late_defensive_margin_config.enabled and projectile_late_defensive_margin_pool:
            for _ in range(max(0, projectile_late_defensive_margin_config.batch_size)):
                exp = rng.choice(projectile_late_defensive_margin_pool)
                values, activations, pre_activations = forward(layers, exp.state)
                output_grad = [0.0 for _ in values]
                exp_late_defensive_margin_loss = apply_projectile_late_defensive_margin_loss(
                    exp,
                    values,
                    actions,
                    output_grad,
                    projectile_late_defensive_margin_config,
                    projectile_late_defensive_margin_mask_config,
                    projectile_late_defensive_margin_stats,
                )
                projectile_late_defensive_margin_loss += exp_late_defensive_margin_loss
                loss += exp_late_defensive_margin_loss
                if exp_late_defensive_margin_loss > 0.0:
                    add_backward_grads(layers, grads, activations, pre_activations, output_grad)
        if projectile_defensive_expert_margin_config.enabled and projectile_defensive_expert_margin_pool:
            for _ in range(max(0, projectile_defensive_expert_margin_config.batch_size)):
                exp = rng.choice(projectile_defensive_expert_margin_pool)
                values, activations, pre_activations = forward(layers, exp.state)
                output_grad = [0.0 for _ in values]
                exp_defensive_expert_margin_loss = apply_projectile_defensive_expert_margin_loss(
                    exp,
                    values,
                    actions,
                    output_grad,
                    projectile_defensive_expert_margin_config,
                    projectile_defensive_expert_margin_mask_config,
                    projectile_defensive_expert_margin_stats,
                )
                projectile_defensive_expert_margin_loss += exp_defensive_expert_margin_loss
                loss += exp_defensive_expert_margin_loss
                if exp_defensive_expert_margin_loss > 0.0:
                    add_backward_grads(layers, grads, activations, pre_activations, output_grad)
        if projectile_timing_group_margin_config.enabled and projectile_timing_group_margin_pool:
            for _ in range(max(0, projectile_timing_group_margin_config.batch_size)):
                exp = rng.choice(projectile_timing_group_margin_pool)
                values, activations, pre_activations = forward(layers, exp.state)
                output_grad = [0.0 for _ in values]
                exp_timing_group_margin_loss = apply_projectile_timing_group_margin_loss(
                    exp,
                    values,
                    actions,
                    output_grad,
                    projectile_timing_group_margin_config,
                    projectile_timing_group_margin_mask_config,
                    projectile_timing_group_margin_stats,
                )
                projectile_timing_group_margin_loss += exp_timing_group_margin_loss
                loss += exp_timing_group_margin_loss
                if exp_timing_group_margin_loss > 0.0:
                    add_backward_grads(layers, grads, activations, pre_activations, output_grad)
        if grounded_normal_defense_margin_config.enabled and grounded_normal_defense_pool:
            for _ in range(max(0, grounded_normal_defense_margin_config.batch_size)):
                exp = rng.choice(grounded_normal_defense_pool)
                values, activations, pre_activations = forward(layers, exp.state)
                output_grad = [0.0 for _ in values]
                exp_grounded_normal_defense_loss = apply_grounded_normal_defense_margin_loss(
                    exp,
                    values,
                    actions,
                    output_grad,
                    grounded_normal_defense_margin_config,
                    grounded_normal_defense_mask_config,
                    grounded_normal_defense_stats,
                )
                grounded_normal_defense_margin_loss += exp_grounded_normal_defense_loss
                loss += exp_grounded_normal_defense_loss
                if exp_grounded_normal_defense_loss > 0.0:
                    add_backward_grads(layers, grads, activations, pre_activations, output_grad)
        if grounded_normal_defense_bc_config.enabled and grounded_normal_defense_bc_pool:
            for _ in range(max(0, 4)):
                exp = rng.choice(grounded_normal_defense_bc_pool)
                values, activations, pre_activations = forward(layers, exp.state)
                output_grad = [0.0 for _ in values]
                exp_defense_bc_loss = apply_grounded_normal_defense_bc_loss(
                    exp,
                    values,
                    actions,
                    output_grad,
                    grounded_normal_defense_bc_config,
                    grounded_normal_defense_bc_stats,
                )
                grounded_normal_defense_bc_loss += exp_defense_bc_loss
                loss += exp_defense_bc_loss
                if exp_defense_bc_loss > 0.0:
                    add_backward_grads(layers, grads, activations, pre_activations, output_grad)
        if low_defense_config.margin_enabled and low_defense_pool:
            for _ in range(max(0, low_defense_config.batch_size)):
                exp = rng.choice(low_defense_pool)
                values, activations, pre_activations = forward(layers, exp.state)
                output_grad = [0.0 for _ in values]
                exp_low_defense_loss = apply_low_defense_margin_loss(
                    exp,
                    values,
                    actions,
                    output_grad,
                    low_defense_config,
                    low_defense_mask_config,
                    low_defense_stats,
                )
                low_defense_margin_loss += exp_low_defense_loss
                loss += exp_low_defense_loss
                if exp_low_defense_loss > 0.0:
                    add_backward_grads(layers, grads, activations, pre_activations, output_grad)
        apply_grads(layers, grads, learning_rate, batch_size)
        last_loss = loss / max(1, batch_size)
        avg_loss = last_loss if step == 1 else (0.98 * avg_loss + 0.02 * last_loss)
        last_unsupported_regularization_loss = unsupported_regularization_loss / max(1, batch_size)
        avg_unsupported_regularization_loss = (
            last_unsupported_regularization_loss
            if step == 1
            else (0.98 * avg_unsupported_regularization_loss + 0.02 * last_unsupported_regularization_loss)
        )
        last_entropy_reg_loss = entropy_reg_loss / max(1, batch_size)
        avg_entropy_reg_loss = (
            last_entropy_reg_loss
            if step == 1
            else (0.98 * avg_entropy_reg_loss + 0.02 * last_entropy_reg_loss)
        )
        last_movement_regression_loss = movement_regression_loss / max(1, batch_size)
        avg_movement_regression_loss = (
            last_movement_regression_loss
            if step == 1
            else (0.98 * avg_movement_regression_loss + 0.02 * last_movement_regression_loss)
        )
        last_projectile_margin_loss = projectile_margin_loss / max(1, batch_size)
        avg_projectile_margin_loss = (
            last_projectile_margin_loss
            if step == 1
            else (0.98 * avg_projectile_margin_loss + 0.02 * last_projectile_margin_loss)
        )
        last_special_margin_loss = special_margin_loss / max(1, batch_size)
        avg_special_margin_loss = (
            last_special_margin_loss
            if step == 1
            else (0.98 * avg_special_margin_loss + 0.02 * last_special_margin_loss)
        )
        last_projectile_late_defensive_margin_loss = projectile_late_defensive_margin_loss / max(1, batch_size)
        avg_projectile_late_defensive_margin_loss = (
            last_projectile_late_defensive_margin_loss
            if step == 1
            else (
                0.98 * avg_projectile_late_defensive_margin_loss
                + 0.02 * last_projectile_late_defensive_margin_loss
            )
        )
        last_projectile_defensive_expert_margin_loss = projectile_defensive_expert_margin_loss / max(1, batch_size)
        avg_projectile_defensive_expert_margin_loss = (
            last_projectile_defensive_expert_margin_loss
            if step == 1
            else (
                0.98 * avg_projectile_defensive_expert_margin_loss
                + 0.02 * last_projectile_defensive_expert_margin_loss
            )
        )
        last_projectile_timing_group_margin_loss = projectile_timing_group_margin_loss / max(1, batch_size)
        avg_projectile_timing_group_margin_loss = (
            last_projectile_timing_group_margin_loss
            if step == 1
            else (
                0.98 * avg_projectile_timing_group_margin_loss
                + 0.02 * last_projectile_timing_group_margin_loss
            )
        )
        last_grounded_normal_defense_margin_loss = grounded_normal_defense_margin_loss / max(1, batch_size)
        avg_grounded_normal_defense_margin_loss = (
            last_grounded_normal_defense_margin_loss
            if step == 1
            else (
                0.98 * avg_grounded_normal_defense_margin_loss
                + 0.02 * last_grounded_normal_defense_margin_loss
            )
        )
        last_grounded_normal_defense_bc_loss = grounded_normal_defense_bc_loss / max(1, batch_size)
        avg_grounded_normal_defense_bc_loss = (
            last_grounded_normal_defense_bc_loss
            if step == 1
            else (
                0.98 * avg_grounded_normal_defense_bc_loss
                + 0.02 * last_grounded_normal_defense_bc_loss
            )
        )
        last_low_defense_margin_loss = low_defense_margin_loss / max(1, batch_size)
        avg_low_defense_margin_loss = (
            last_low_defense_margin_loss
            if step == 1
            else (0.98 * avg_low_defense_margin_loss + 0.02 * last_low_defense_margin_loss)
        )
        if target_sync_steps > 0 and step % target_sync_steps == 0:
            target_layers = copy.deepcopy(layers)
        if log_interval > 0 and (step == 1 or step % log_interval == 0 or step == steps):
            print(
                f"TRAIN step={step} loss={last_loss:.6f} avg_loss={avg_loss:.6f} "
                f"unsupported_reg={last_unsupported_regularization_loss:.6f} "
                f"movement_reg={last_movement_regression_loss:.6f} "
                f"entropy_reg={last_entropy_reg_loss:.6f} "
                f"projectile_margin={last_projectile_margin_loss:.6f} "
                f"special_margin={last_special_margin_loss:.6f} "
                f"projectile_late_def_margin={last_projectile_late_defensive_margin_loss:.6f} "
                f"projectile_def_expert_margin={last_projectile_defensive_expert_margin_loss:.6f} "
                f"projectile_timing_group_margin={last_projectile_timing_group_margin_loss:.6f} "
                f"grounded_def_margin={last_grounded_normal_defense_margin_loss:.6f} "
                f"grounded_def_bc={last_grounded_normal_defense_bc_loss:.6f} "
                f"low_def_margin={last_low_defense_margin_loss:.6f}",
                flush=True,
            )

    batch_diag = BatchSamplingDiagnostics(
        mode=batch_sampling_config.mode,
        ratios=dict(batch_sampling_config.ratios),
        pool_counts={group: len(batch_pools[group]) for group in BATCH_GROUPS},
        target_counts=dict(batch_target_counts),
    )
    combat_event_batch_diag = CombatEventBatchSamplingDiagnostics(
        mode=combat_event_batch_sampling_config.mode,
        ratios=dict(combat_event_batch_sampling_config.ratios),
        pool_counts={group: len(combat_event_batch_pools[group]) for group in COMBAT_EVENT_BATCH_GROUPS},
        target_counts=dict(combat_event_batch_target_counts),
    )
    unsupported_action_regularization_stats.last_loss = last_unsupported_regularization_loss
    unsupported_action_regularization_stats.avg_loss = avg_unsupported_regularization_loss
    movement_regression_stats.last_loss = last_movement_regression_loss
    movement_regression_stats.avg_loss = avg_movement_regression_loss
    projectile_expert_margin_stats.last_loss = last_projectile_margin_loss
    projectile_expert_margin_stats.avg_loss = avg_projectile_margin_loss
    special_expert_margin_stats.last_loss = last_special_margin_loss
    special_expert_margin_stats.avg_loss = avg_special_margin_loss
    projectile_late_defensive_margin_stats.last_loss = last_projectile_late_defensive_margin_loss
    projectile_late_defensive_margin_stats.avg_loss = avg_projectile_late_defensive_margin_loss
    projectile_defensive_expert_margin_stats.last_loss = last_projectile_defensive_expert_margin_loss
    projectile_defensive_expert_margin_stats.avg_loss = avg_projectile_defensive_expert_margin_loss
    projectile_timing_group_margin_stats.last_loss = last_projectile_timing_group_margin_loss
    projectile_timing_group_margin_stats.avg_loss = avg_projectile_timing_group_margin_loss
    grounded_normal_defense_stats.last_loss = last_grounded_normal_defense_margin_loss
    grounded_normal_defense_stats.avg_loss = avg_grounded_normal_defense_margin_loss
    grounded_normal_defense_bc_stats.last_loss = last_grounded_normal_defense_bc_loss
    grounded_normal_defense_bc_stats.avg_loss = avg_grounded_normal_defense_bc_loss
    low_defense_stats.last_loss = last_low_defense_margin_loss
    low_defense_stats.avg_loss = avg_low_defense_margin_loss
    return (
        layers,
        {
            "last_loss": last_loss,
            "avg_loss": avg_loss,
            "entropy_reg_weight": entropy_reg_weight,
            "batch_sampling": batch_diag.as_metadata(),
            "combat_event_batch_sampling": combat_event_batch_diag.as_metadata(),
        },
        unsupported_action_regularization_stats,
        movement_regression_stats,
        projectile_expert_margin_stats,
        special_expert_margin_stats,
        projectile_late_defensive_margin_stats,
        projectile_defensive_expert_margin_stats,
        projectile_timing_group_margin_stats,
        grounded_normal_defense_stats,
        grounded_normal_defense_bc_stats,
        low_defense_stats,
        valid_action_mask_stats,
    )


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
    policy: str = "dqn",
) -> None:
    os.makedirs(model_dir, exist_ok=True)
    dqn_model = {
        "feature_names": list(rl.DQN_FEATURE_NAMES),
        "feature_scales": dict(rl.DQN_FEATURE_SCALES),
        "layers": layers,
    }
    source = "offline-bc" if policy == "bc" else "offline-dqn"
    payload = {
        "version": version,
        "policy": policy,
        "source": source,
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


def parse_path_list(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def actor_model_path(value: str) -> Path:
    path = Path(value)
    if path.is_dir():
        return path / "current.json"
    return path


def expand_init_dqn_layers(
    init_layers: list[dict[str, object]],
    init_actions: tuple[str, ...],
    actions: tuple[str, ...],
    rng: random.Random,
) -> list[dict[str, object]]:
    init_action_to_index = {action: index for index, action in enumerate(init_actions)}
    init_output = init_layers[-1]
    init_weights = init_output["weights"]
    init_bias = init_output["bias"]
    assert isinstance(init_weights, list)
    assert isinstance(init_bias, list)
    if not init_weights:
        raise SystemExit("--init-model expand: init model has an empty output layer")
    row_width = len(init_weights[0])
    mean_weights = [
        sum(float(row[col]) for row in init_weights) / max(1, len(init_weights))
        for col in range(row_width)
    ]
    min_bias = min(float(value) for value in init_bias) if init_bias else 0.0
    expanded_layers = copy.deepcopy(init_layers)
    expanded_weights: list[list[float]] = []
    expanded_bias: list[float] = []
    for action in actions:
        init_index = init_action_to_index.get(action)
        if init_index is not None:
            expanded_weights.append([float(value) for value in init_weights[init_index]])
            expanded_bias.append(float(init_bias[init_index]))
        else:
            expanded_weights.append([value + rng.gauss(0.0, 0.01) for value in mean_weights])
            expanded_bias.append(min_bias)
    expanded_layers[-1] = {
        "weights": expanded_weights,
        "bias": expanded_bias,
        "activation": str(init_output.get("activation", "linear") or "linear"),
    }
    return expanded_layers


def expand_init_dqn_input_features(
    init_layers: list[dict[str, object]],
    init_feature_names: tuple[str, ...],
    feature_names: tuple[str, ...],
) -> list[dict[str, object]]:
    init_feature_to_index = {name: index for index, name in enumerate(init_feature_names)}
    missing_features = [name for name in init_feature_names if name not in set(feature_names)]
    if missing_features:
        raise SystemExit(
            "--init-model feature expansion requires init features to be a subset of the current schema; "
            f"missing from current={','.join(missing_features)}"
        )
    expanded_layers = copy.deepcopy(init_layers)
    first_layer = expanded_layers[0]
    weights = first_layer["weights"]
    assert isinstance(weights, list)
    expanded_weights: list[list[float]] = []
    for raw_row in weights:
        assert isinstance(raw_row, list)
        expanded_row: list[float] = []
        for feature_name in feature_names:
            init_index = init_feature_to_index.get(feature_name)
            expanded_row.append(float(raw_row[init_index]) if init_index is not None else 0.0)
        expanded_weights.append(expanded_row)
    first_layer["weights"] = expanded_weights
    return expanded_layers


def load_init_dqn_model(
    value: str,
    actions: tuple[str, ...],
    hidden_sizes: list[int],
    action_mode: str,
    seed: int,
) -> InitDQNModel:
    path = actor_model_path(value)
    try:
        with path.open("r", encoding="utf-8") as stream:
            payload = json.load(stream)
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"--init-model failed to read {path}: {exc}") from exc

    policy = str(payload.get("policy", "") or "")
    if policy not in {"dqn", "bc"}:
        raise SystemExit(f"--init-model {path}: expected policy=dqn or bc, got {policy or 'missing'}")
    try:
        action_set_version = int(payload.get("action_set_version", 0) or 0)
    except (TypeError, ValueError):
        action_set_version = 0
    if action_set_version != rl.ACTION_SET_VERSION:
        raise SystemExit(
            f"--init-model {path}: action_set_version={action_set_version} expected={rl.ACTION_SET_VERSION}"
        )
    raw_actions = payload.get("actions")
    if not isinstance(raw_actions, list):
        raise SystemExit(f"--init-model {path}: missing actions list")
    init_actions = tuple(str(action) for action in raw_actions)
    clean_action_mode = str(action_mode or "exact")
    if clean_action_mode not in {"exact", "expand"}:
        raise SystemExit(f"--init-model-action-mode expected exact or expand, got {clean_action_mode!r}")
    if clean_action_mode == "exact" and init_actions != actions:
        raise SystemExit("--init-model actions do not exactly match --actions order")
    if clean_action_mode == "expand":
        missing_actions = [action for action in init_actions if action not in set(actions)]
        if missing_actions:
            raise SystemExit(
                "--init-model expand requires init actions to be a subset of --actions; "
                f"missing from target={','.join(missing_actions)}"
            )

    raw_dqn = payload.get("dqn")
    if not isinstance(raw_dqn, dict):
        raise SystemExit(f"--init-model {path}: missing dqn payload")
    raw_feature_names = raw_dqn.get("feature_names")
    if not isinstance(raw_feature_names, list):
        raise SystemExit(f"--init-model {path}: missing dqn.feature_names")
    feature_names = rl.sanitized_dqn_feature_names(raw_feature_names, f"--init-model {path}")
    if not feature_names:
        feature_names = tuple(rl.DQN_FEATURE_NAMES)
    expected_feature_names = tuple(rl.DQN_FEATURE_NAMES)
    feature_expansion_required = feature_names != expected_feature_names
    if feature_expansion_required and not set(feature_names).issubset(set(expected_feature_names)):
        raise SystemExit(
            f"--init-model {path}: feature schema mismatch "
            f"got={len(feature_names)} expected={len(expected_feature_names)}"
        )
    init_output_dim = len(init_actions) if clean_action_mode == "expand" else len(actions)
    layers = validate_dqn_layers(
        raw_dqn.get("layers"),
        len(feature_names) if feature_expansion_required else len(expected_feature_names),
        hidden_sizes,
        init_output_dim,
        f"--init-model {path}",
    )
    if feature_expansion_required:
        layers = expand_init_dqn_input_features(layers, feature_names, expected_feature_names)
        layers = validate_dqn_layers(
            layers,
            len(expected_feature_names),
            hidden_sizes,
            init_output_dim,
            f"--init-model {path} feature-expanded",
        )
    if clean_action_mode == "expand" and init_actions != actions:
        layers = expand_init_dqn_layers(layers, init_actions, actions, random.Random(seed))
        layers = validate_dqn_layers(
            layers,
            len(expected_feature_names),
            hidden_sizes,
            len(actions),
            f"--init-model {path} expanded",
        )
    try:
        version = max(0, int(payload.get("version", 0) or 0))
    except (TypeError, ValueError):
        version = 0
    metadata = payload.get("metadata")
    return InitDQNModel(
        path=str(path),
        version=version,
        source=str(payload.get("source", "") or ""),
        metadata=metadata if isinstance(metadata, dict) else {},
        actions=init_actions,
        feature_names=expected_feature_names,
        layers=layers,
        action_mode=clean_action_mode,
    )


def build_replay_recipe_metadata(
    args: argparse.Namespace,
    replay_source_mix_config: ReplaySourceMixConfig,
    init_model: InitDQNModel | None,
) -> dict[str, object]:
    inherited = init_model.metadata.get("replay_recipe") if init_model is not None else None
    inherited_recipe = inherited if isinstance(inherited, dict) else {}
    base_logs = parse_path_list(str(args.replay_recipe_base_logs))
    if not base_logs:
        raw_base_logs = inherited_recipe.get("base_logs")
        if isinstance(raw_base_logs, list):
            base_logs = [str(path) for path in raw_base_logs if str(path)]
    live_log = str(args.replay_recipe_live_log).strip()
    if not live_log:
        live_log = str(inherited_recipe.get("live_incremental_log", "") or "")
    recipe_name = str(args.replay_recipe_name).strip()
    if not recipe_name:
        recipe_name = str(inherited_recipe.get("training_recipe", "") or "")
    source_ratios = dict(sorted(replay_source_mix_config.target_ratios.items()))
    if not source_ratios:
        raw_source_ratios = inherited_recipe.get("source_ratios")
        if isinstance(raw_source_ratios, dict):
            try:
                source_ratios = {
                    str(source): float(ratio)
                    for source, ratio in raw_source_ratios.items()
                    if isinstance(source, str)
                }
            except (TypeError, ValueError):
                source_ratios = {}
    return {
        "training_recipe": recipe_name,
        "base_logs": base_logs,
        "live_incremental_log": live_log,
        "source_ratios": source_ratios,
    }


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


def format_float_counts(values: dict[str, float], limit: int) -> str:
    ordered = sorted(values.items(), key=lambda item: (abs(item[1]), item[0]), reverse=True)
    parts = [f"{key}:{value:.3f}" for key, value in ordered[: max(1, limit)] if value != 0.0]
    if len(ordered) > limit:
        remaining = sum(value for _, value in ordered[max(1, limit) :])
        if remaining != 0.0:
            parts.append(f"...{remaining:+.3f}")
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
    valid_action_mask_config: DQNValidActionMaskTrainingConfig = DQNValidActionMaskTrainingConfig("off"),
    valid_action_mask_stats: DQNValidActionMaskTrainingStats | None = None,
) -> GreedyDiagnostics:
    eval_experiences = experiences[: max(0, limit)]
    shared_valid_action_mask_config = valid_action_mask_config.as_shared_config()
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
        valid_indices = dqn_masked_indices_for_row(
            exp.row,
            actions,
            count,
            shared_valid_action_mask_config,
            valid_action_mask_stats if valid_action_mask_stats is not None else DQNValidActionMaskTrainingStats(),
            "greedy",
        )
        if not valid_indices:
            continue
        ranked = sorted(valid_indices, key=lambda index: (float(values[index]), actions[index]), reverse=True)
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
    parser.add_argument(
        "--init-model",
        default="",
        help="Optional DQN actor JSON or model directory whose layers are used as the training warm-start",
    )
    parser.add_argument(
        "--init-model-action-mode",
        choices=("exact", "expand"),
        default="exact",
        help=(
            "How --init-model handles action-list differences. exact requires identical order; "
            "expand allows init actions to be a subset of --actions and expands only the output layer"
        ),
    )
    parser.add_argument(
        "--replay-recipe-name",
        default="",
        help="Optional stable name written to metadata.replay_recipe.training_recipe",
    )
    parser.add_argument(
        "--replay-recipe-base-logs",
        default="",
        help=(
            "Comma-separated replay anchor logs written to metadata.replay_recipe.base_logs; "
            "when omitted during --init-model training, the value is inherited from the init model"
        ),
    )
    parser.add_argument(
        "--replay-recipe-live-log",
        default="",
        help=(
            "Optional append-only live log path written to metadata.replay_recipe.live_incremental_log; "
            "cursor-based auto retrain will use this later"
        ),
    )
    parser.add_argument("--limit", type=int, default=0, help="Maximum rows to read across all transition logs; 0 means all")
    parser.add_argument(
        "--combat-event-logs",
        nargs="*",
        default=[],
        help=(
            "Optional combat-events NDJSON logs paired with the transition logs. "
            "Phase 9B supports validation-only and opt-in reward-shaping ingestion."
        ),
    )
    parser.add_argument(
        "--combat-event-training-mode",
        choices=combat_events.COMBAT_EVENT_TRAINING_MODES,
        default="off",
        help=(
            "Combat event trainer adoption mode. off preserves existing training; "
            "validate records join/schema diagnostics without changing rewards; "
            "reward-shaping adds a fixed event-outcome reward table on top of transition rewards."
        ),
    )
    parser.add_argument(
        "--combat-event-reward-profile",
        choices=combat_events.COMBAT_EVENT_REWARD_PROFILES,
        default="safe-v1",
        help="Combat event reward table profile used only with --combat-event-training-mode reward-shaping.",
    )
    parser.add_argument(
        "--combat-event-reward-scale",
        type=float,
        default=1.0,
        help="Additional multiplier for combat event reward shaping before the global --reward-scale.",
    )
    parser.add_argument(
        "--bc-event-weighting",
        choices=BC_EVENT_WEIGHTING_MODES,
        default="off",
        help=(
            "Opt-in Phase 10A event-weighted Behavior Cloning. "
            "event-weighted-v1 turns paired combat-event outcomes into supervised CE sample weights."
        ),
    )
    parser.add_argument(
        "--bc-event-reward-profile",
        choices=combat_events.COMBAT_EVENT_REWARD_PROFILES,
        default="event-damage-v1",
        help="Combat-event reward profile used to derive BC sample weights.",
    )
    parser.add_argument(
        "--bc-event-reward-scale",
        type=float,
        default=1.0,
        help="Multiplier applied while deriving event-weighted BC raw adjustments.",
    )
    parser.add_argument(
        "--bc-event-weight-positive-scale",
        type=float,
        default=0.25,
        help="Weight multiplier for positive event adjustment: weight = 1 + adjustment * scale.",
    )
    parser.add_argument(
        "--bc-event-weight-negative-scale",
        type=float,
        default=0.5,
        help="Weight multiplier for negative event adjustment: weight = 1 + adjustment * scale.",
    )
    parser.add_argument(
        "--bc-event-weight-min",
        type=float,
        default=0.25,
        help="Minimum CE sample weight for event-weighted BC.",
    )
    parser.add_argument(
        "--bc-event-weight-max",
        type=float,
        default=3.0,
        help="Maximum CE sample weight for event-weighted BC.",
    )
    parser.add_argument(
        "--bc-label-balance",
        choices=BC_LABEL_BALANCE_MODES,
        default="off",
        help=(
            "Opt-in BC class-balance CE weighting. inverse-sqrt is the recommended first pass "
            "for human logs dominated by forward/back/standing light rows."
        ),
    )
    parser.add_argument(
        "--bc-label-balance-min",
        type=float,
        default=0.35,
        help="Minimum per-label balance multiplier for BC.",
    )
    parser.add_argument(
        "--bc-label-balance-max",
        type=float,
        default=3.0,
        help="Maximum per-label balance multiplier for BC.",
    )
    parser.add_argument(
        "--bc-family-margin",
        choices=BC_FAMILY_MARGIN_MODES,
        default="off",
        help=(
            "Opt-in Phase 10C BC margin objective. positive-event-v1 uses positive combat-event "
            "adjustments to make meaningful attack/projectile/throw/guard-crouch labels outrank "
            "generic movement/defense choices."
        ),
    )
    parser.add_argument(
        "--bc-family-margin-weight",
        type=float,
        default=0.2,
        help="BC family-margin loss weight multiplier applied to positive event reward adjustment.",
    )
    parser.add_argument(
        "--bc-family-margin-target-margin",
        type=float,
        default=0.5,
        help="Required logit margin between the positive-event BC target and the best configured negative action.",
    )
    parser.add_argument(
        "--bc-family-margin-min-positive-adjustment",
        type=float,
        default=0.05,
        help="Minimum positive combat-event reward adjustment required before a BC row is margin-eligible.",
    )
    parser.add_argument(
        "--bc-family-margin-negative-actions",
        default="forward,back,guard-stand,guard-crouch",
        help="Comma-separated actions treated as generic negatives for --bc-family-margin positive-event-v1.",
    )
    parser.add_argument(
        "--combat-event-unlabeled-movement-policy",
        choices=combat_events.COMBAT_EVENT_UNLABELED_MOVEMENT_POLICIES,
        default="keep",
        help=(
            "Event-aware replay filter for zero-reward unlabeled passive movement rows. "
            "keep preserves all rows, downsample keeps --combat-event-unlabeled-movement-keep-ratio, "
            "drop removes all eligible unlabeled rows. Protected event/threat/damage/done rows are never dropped."
        ),
    )
    parser.add_argument(
        "--combat-event-unlabeled-movement-keep-ratio",
        type=float,
        default=1.0,
        help="Deterministic keep ratio used only when --combat-event-unlabeled-movement-policy downsample.",
    )
    parser.add_argument(
        "--combat-event-unlabeled-movement-seed",
        type=int,
        default=20260507,
        help="Stable seed for deterministic unlabeled movement downsampling.",
    )
    parser.add_argument(
        "--combat-event-batch-sampling",
        choices=combat_events.COMBAT_EVENT_BATCH_SAMPLING_MODES,
        default="off",
        help=(
            "Opt-in combat-event source-family batch sampler. off uses the normal replay sampler; "
            "balanced-v1 samples each DQN batch by combat-event groups."
        ),
    )
    parser.add_argument(
        "--combat-event-batch-ratios",
        default="movement=0.30,attack=0.25,projectile=0.20,defense=0.15,punish_throw=0.10,unlabeled_passive=0.00",
        help=(
            "Comma-separated group ratios used by --combat-event-batch-sampling balanced-v1. "
            "Groups: attack,projectile,defense,punish_throw,movement,unlabeled_passive."
        ),
    )
    parser.add_argument(
        "--combat-event-movement-credit",
        choices=combat_events.COMBAT_EVENT_MOVEMENT_CREDIT_MODES,
        default="off",
        help=(
            "Opt-in delayed movement credit from later combat-event rewards. "
            "delayed-v1 allocates a capped fraction of resolved event reward to recent forward/back/jump starts."
        ),
    )
    parser.add_argument(
        "--combat-event-movement-credit-window",
        type=int,
        default=6,
        help="Maximum prior decision gap eligible for delayed movement credit.",
    )
    parser.add_argument(
        "--combat-event-movement-credit-max-rows",
        type=int,
        default=3,
        help="Maximum prior movement action-start rows credited by one combat event anchor.",
    )
    parser.add_argument(
        "--combat-event-movement-credit-scale",
        type=float,
        default=0.35,
        help="Fraction of the scaled combat-event reward budget allocated to prior movement rows.",
    )
    parser.add_argument(
        "--combat-event-movement-credit-decay",
        default="0.50,0.30,0.20",
        help="Comma-separated positive weights from nearest to oldest prior movement row.",
    )
    parser.add_argument(
        "--combat-event-movement-credit-row-cap",
        type=float,
        default=0.0,
        help="Optional absolute cap for total delayed movement credit per experience; 0 disables the cap.",
    )
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
            "movement=0.4,normal=0.3,special=0.3 or "
            "projectile=0.4,movement=0.2,normal=0.25,special=0.15; movement includes "
            "forward/back/guard, normal includes normals and throw, special includes "
            "fireball/shoryuken/tatsu"
        ),
    )
    parser.add_argument(
        "--projectile-batch-group",
        action=argparse.BooleanOptionalAction,
        default=False,
        help=(
            "Mark selected projectile-defense experiences for the optional projectile balanced-batch group. "
            "Use with --batch-sampling balanced and a projectile=... ratio."
        ),
    )
    parser.add_argument(
        "--projectile-batch-min-time-to-self",
        type=int,
        default=0,
        help="Minimum obs_projectile_time_to_self for urgent projectile batch rows",
    )
    parser.add_argument(
        "--projectile-batch-max-time-to-self",
        type=int,
        default=12,
        help="Maximum obs_projectile_time_to_self for urgent projectile batch rows",
    )
    parser.add_argument(
        "--projectile-batch-time-ranges",
        default="",
        help=(
            "Optional comma-separated obs_projectile_time_to_self ranges for defensive/late-hit projectile "
            "batch rows, e.g. 0-22,31-48. Overrides min/max when set."
        ),
    )
    parser.add_argument(
        "--projectile-batch-window-decisions",
        type=int,
        default=12,
        help="Lookahead decision window used to accept low-damage defensive projectile batch rows",
    )
    parser.add_argument(
        "--projectile-batch-max-self-hp",
        type=int,
        default=1,
        help="Maximum self HP damage allowed for defensive projectile batch rows",
    )
    parser.add_argument(
        "--projectile-batch-sources",
        default="human-demo",
        help="Comma-separated execution sources eligible for projectile batch rows",
    )
    parser.add_argument(
        "--projectile-batch-include-late-jump-hit",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Include urgent/borderline late jump-hit projectile rows in the projectile batch group",
    )
    parser.add_argument(
        "--projectile-batch-include-safe-jump",
        action=argparse.BooleanOptionalAction,
        default=False,
        help=(
            "Also include clean safe-jump projectile rows in the projectile batch group. "
            "Default is off so oversampled safe jumps do not drown out urgent defensive rows."
        ),
    )
    parser.add_argument(
        "--projectile-batch-safe-jump-min-time-to-self",
        type=int,
        default=13,
        help="Minimum obs_projectile_time_to_self for safe-jump projectile batch rows",
    )
    parser.add_argument(
        "--projectile-batch-safe-jump-max-time-to-self",
        type=int,
        default=48,
        help="Maximum obs_projectile_time_to_self for safe-jump projectile batch rows",
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
        "--training-mode-hp-delta-mode",
        choices=("raw", "damage-only"),
        default="raw",
        help=(
            "How to treat HP deltas on mode_type=training rows. raw preserves logged deltas; "
            "damage-only ignores negative HP deltas caused by training-mode recovery/reset effects"
        ),
    )
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
        "--dqn-unsupported-action-regularization",
        action=argparse.BooleanOptionalAction,
        default=False,
        help=(
            "Add an auxiliary DQN loss that pushes zero/low replay-support action heads below "
            "--dqn-unsupported-action-q-ceiling; disabled by default"
        ),
    )
    parser.add_argument(
        "--dqn-unsupported-action-min-count",
        type=int,
        default=1,
        help=(
            "Actions with fewer than this many post-build DQN training examples are regularized when "
            "--dqn-unsupported-action-regularization is enabled; 1 targets only zero-sample actions"
        ),
    )
    parser.add_argument(
        "--dqn-unsupported-action-q-ceiling",
        type=float,
        default=0.0,
        help="Scaled-Q ceiling used by --dqn-unsupported-action-regularization",
    )
    parser.add_argument(
        "--dqn-unsupported-action-loss-weight",
        type=float,
        default=0.1,
        help="Auxiliary loss weight used by --dqn-unsupported-action-regularization",
    )
    parser.add_argument(
        "--dqn-unsupported-action-adaptive-ceiling",
        action=argparse.BooleanOptionalAction,
        default=False,
        help=(
            "When enabled, the unsupported-action Q ceiling is set to min(static_ceiling, "
            "mean Q of movement actions) per batch instead of a fixed value"
        ),
    )
    parser.add_argument(
        "--dqn-entropy-reg-weight",
        type=float,
        default=0.0,
        help=(
            "Entropy regularization bonus weight applied to softmax policy over batch Q-values; "
            "0 disables entropy reg"
        ),
    )
    parser.add_argument(
        "--movement-regression-loss-weight",
        type=float,
        default=0.0,
        help=(
            "Auxiliary loss weight that pushes normal-attack Q below movement Q in far, grounded, "
            "non-threat contexts; 0 disables the loss"
        ),
    )
    parser.add_argument(
        "--movement-regression-target-q-margin",
        type=float,
        default=0.5,
        help="Required Q margin between best movement action and best attack action for movement regression loss",
    )
    parser.add_argument(
        "--movement-regression-far-dx-threshold",
        type=int,
        default=120,
        help="Minimum obs_abs_dx considered a far movement context for movement regression loss",
    )
    parser.add_argument(
        "--movement-regression-action-groups",
        default="stand-normal,crouch-normal,air-normal",
        help=(
            "Comma-separated attack groups regularized by movement regression loss: "
            "stand-normal,crouch-normal,air-normal,fireball,shoryuken,tatsu"
        ),
    )
    parser.add_argument(
        "--movement-regression-exclude-special-expert-eligible",
        action=argparse.BooleanOptionalAction,
        default=False,
        help=(
            "Exclude positive special-expert-margin rows from movement regression so successful "
            "special examples do not receive conflicting anti-attack margin"
        ),
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
        help="Additional positive raw reward cost subtracted from no-damage air attacks in all-attacks profile",
    )
    parser.add_argument(
        "--reward-jump-attack-punished-extra-cost",
        type=float,
        default=0.0,
        help="Additional positive raw reward cost when a no-damage air attack is followed by self HP damage",
    )
    parser.add_argument(
        "--reward-throw-far-cost",
        type=float,
        default=0.0,
        help="Raw reward cost applied when throw is selected at abs_dx > --reward-throw-far-max-abs-dx",
    )
    parser.add_argument(
        "--reward-throw-far-max-abs-dx",
        type=int,
        default=64,
        help="Maximum obs_abs_dx where throw is considered close-range and not penalized",
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
        "--reward-projectile-response-profile",
        choices=REWARD_PROJECTILE_RESPONSE_PROFILES,
        default="off",
        help="Optional incoming projectile response shaping; off leaves existing reward recipes unchanged",
    )
    parser.add_argument(
        "--reward-projectile-response-window-decisions",
        type=int,
        default=12,
        help="Lookahead decisions used to score jump/back/guard responses to incoming opponent projectiles",
    )
    parser.add_argument(
        "--reward-projectile-threat-min-time-to-self",
        type=int,
        default=1,
        help="Minimum obs_projectile_time_to_self for incoming projectile response shaping",
    )
    parser.add_argument(
        "--reward-projectile-threat-max-time-to-self",
        type=int,
        default=24,
        help="Maximum obs_projectile_time_to_self for incoming projectile response shaping",
    )
    parser.add_argument(
        "--reward-projectile-threat-max-dx",
        type=int,
        default=240,
        help="Maximum obs_projectile_rel_x considered an incoming projectile threat",
    )
    parser.add_argument(
        "--reward-projectile-threat-max-abs-y",
        type=int,
        default=48,
        help="Maximum absolute obs_projectile_rel_y considered jump/guard relevant",
    )
    parser.add_argument(
        "--reward-projectile-close-max-dx",
        type=int,
        default=96,
        help="Maximum obs_abs_dx considered close range for back/guard projectile response bonuses",
    )
    parser.add_argument(
        "--reward-projectile-safe-jump-bonus",
        type=float,
        default=0.0,
        help="Positive raw reward bonus for jump-start actions that safely clear an incoming opponent projectile",
    )
    parser.add_argument(
        "--reward-projectile-late-jump-hit-cost",
        type=float,
        default=0.0,
        help="Positive raw reward cost subtracted when a jump-start response to an incoming projectile takes self HP damage",
    )
    parser.add_argument(
        "--reward-projectile-close-back-success-bonus",
        type=float,
        default=0.0,
        help="Positive raw reward bonus for clean close-range back movement against an incoming projectile",
    )
    parser.add_argument(
        "--reward-projectile-close-guard-success-bonus",
        type=float,
        default=0.0,
        help="Positive raw reward bonus for clean close-range guard against an incoming projectile",
    )
    parser.add_argument(
        "--reward-projectile-back-escape-min-dx-delta",
        type=int,
        default=8,
        help="Minimum obs_abs_dx increase needed to treat close-range back as successful projectile spacing",
    )
    parser.add_argument(
        "--reward-projectile-guard-require-contact",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Require obs_self_contact_reaction_state before awarding close guard projectile success",
    )
    parser.add_argument(
        "--projectile-response-safe-jump-oversample",
        type=int,
        default=1,
        help=(
            "Replay copies to emit for safe jump-start responses to incoming projectiles; "
            "1 keeps baseline sampling"
        ),
    )
    parser.add_argument(
        "--projectile-response-late-jump-hit-oversample",
        type=int,
        default=1,
        help=(
            "Replay copies to emit for jump-start responses that get hit by incoming projectiles; "
            "1 keeps baseline sampling"
        ),
    )
    parser.add_argument(
        "--projectile-response-close-back-oversample",
        type=int,
        default=1,
        help="Replay copies to emit for clean close back responses to incoming projectiles",
    )
    parser.add_argument(
        "--projectile-response-close-guard-oversample",
        type=int,
        default=1,
        help="Replay copies to emit for clean close guard responses to incoming projectiles",
    )
    parser.add_argument(
        "--projectile-expert-margin-loss",
        action=argparse.BooleanOptionalAction,
        default=False,
        help=(
            "Add a valid-action-masked large-margin loss on safe human-demo jump-start responses "
            "to incoming projectiles"
        ),
    )
    parser.add_argument(
        "--projectile-expert-margin",
        type=float,
        default=0.1,
        help="Q margin required between the expert jump action and the best valid competitor",
    )
    parser.add_argument(
        "--projectile-expert-margin-weight",
        type=float,
        default=0.05,
        help="Auxiliary loss weight for --projectile-expert-margin-loss",
    )
    parser.add_argument(
        "--projectile-expert-margin-batch-size",
        type=int,
        default=0,
        help=(
            "Extra safe human-demo projectile jump rows sampled per DQN step for margin-only updates; "
            "0 keeps margin loss limited to the normal replay batch"
        ),
    )
    parser.add_argument(
        "--projectile-expert-margin-require-safe-jump",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Require the projectile response classifier to mark a clean safe jump before applying margin loss",
    )
    parser.add_argument(
        "--projectile-expert-margin-equivalent-jump-actions",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Treat jump-forward/jump-neutral/jump-back starts as one acceptable expert group when "
            "ranking safe projectile jump responses"
        ),
    )
    parser.add_argument(
        "--projectile-expert-margin-min-time-to-self",
        type=int,
        default=0,
        help=(
            "Minimum obs_projectile_time_to_self required for safe human-demo "
            "projectile jump rows to receive expert margin loss"
        ),
    )
    parser.add_argument(
        "--projectile-expert-margin-max-time-to-self",
        type=int,
        default=32767,
        help=(
            "Maximum obs_projectile_time_to_self allowed for safe human-demo "
            "projectile jump rows to receive expert margin loss"
        ),
    )
    parser.add_argument(
        "--projectile-expert-margin-time-ranges",
        default="",
        help=(
            "Optional comma-separated obs_projectile_time_to_self ranges for projectile jump expert margin, "
            "e.g. 23-30. Overrides min/max when set."
        ),
    )
    parser.add_argument(
        "--projectile-expert-margin-sources",
        default="human-demo",
        help=(
            "Comma-separated execution sources eligible for projectile jump expert margin; "
            "default keeps the legacy human-demo-only behavior"
        ),
    )
    parser.add_argument(
        "--projectile-expert-margin-valid-action-mask",
        choices=rl.DQN_VALID_ACTION_MASK_MODES,
        default="action-start-v1",
        help="Valid-action mask used for projectile expert margin competitors",
    )
    parser.add_argument(
        "--special-expert-margin-loss",
        action=argparse.BooleanOptionalAction,
        default=False,
        help=(
            "Add a valid-action-masked large-margin loss on positive fireball/shoryuken/tatsu "
            "engine-labeled experiences"
        ),
    )
    parser.add_argument(
        "--special-expert-margin",
        type=float,
        default=0.08,
        help="Q margin required between the expert special action and the best valid competitor",
    )
    parser.add_argument(
        "--special-expert-margin-weight",
        type=float,
        default=0.5,
        help="Auxiliary loss weight for --special-expert-margin-loss",
    )
    parser.add_argument(
        "--special-expert-margin-batch-size",
        type=int,
        default=0,
        help=(
            "Extra positive special rows sampled per DQN step for margin-only updates; "
            "0 keeps margin loss limited to the normal replay batch"
        ),
    )
    parser.add_argument(
        "--special-expert-margin-min-reward",
        type=float,
        default=0.0,
        help="Minimum scaled reward required for a special experience to receive expert margin loss",
    )
    parser.add_argument(
        "--special-expert-margin-sources",
        default="human-demo,cpu-demo",
        help="Comma-separated execution sources eligible for special expert margin",
    )
    parser.add_argument(
        "--special-expert-margin-valid-action-mask",
        choices=rl.DQN_VALID_ACTION_MASK_MODES,
        default="action-start-v1",
        help="Valid-action mask used for special expert margin competitors",
    )
    parser.add_argument(
        "--special-expert-margin-context-gate",
        action=argparse.BooleanOptionalAction,
        default=False,
        help=(
            "Only apply special expert margin in coarse move-family contexts: "
            "far grounded zoning for fireball, opponent jump/air routine for shoryuken, "
            "and close/mid range for tatsu"
        ),
    )
    parser.add_argument(
        "--special-expert-margin-fireball-min-abs-dx",
        type=int,
        default=120,
        help="Minimum obs_abs_dx required for fireball rows when --special-expert-margin-context-gate is enabled",
    )
    parser.add_argument(
        "--projectile-late-defensive-margin-loss",
        action=argparse.BooleanOptionalAction,
        default=False,
        help=(
            "Add a valid-action-masked margin loss on late jump-hit projectile rows "
            "so guard/back defensive actions rank above jump-start actions"
        ),
    )
    parser.add_argument(
        "--projectile-late-defensive-margin",
        type=float,
        default=0.05,
        help="Q margin required between the best defensive action and the best jump action",
    )
    parser.add_argument(
        "--projectile-late-defensive-margin-weight",
        type=float,
        default=0.5,
        help="Auxiliary loss weight for --projectile-late-defensive-margin-loss",
    )
    parser.add_argument(
        "--projectile-late-defensive-margin-batch-size",
        type=int,
        default=0,
        help=(
            "Extra late jump-hit projectile rows sampled per DQN step for defensive "
            "margin-only updates; 0 keeps loss limited to the normal replay batch"
        ),
    )
    parser.add_argument(
        "--projectile-late-defensive-margin-min-time-to-self",
        type=int,
        default=0,
        help="Minimum obs_projectile_time_to_self for late jump-hit defensive margin rows",
    )
    parser.add_argument(
        "--projectile-late-defensive-margin-max-time-to-self",
        type=int,
        default=12,
        help="Maximum obs_projectile_time_to_self for late jump-hit defensive margin rows",
    )
    parser.add_argument(
        "--projectile-late-defensive-margin-sources",
        default="human-demo,remote",
        help=(
            "Comma-separated execution sources eligible for late defensive margin rows; "
            "default uses human demo and live remote failures"
        ),
    )
    parser.add_argument(
        "--projectile-late-defensive-margin-valid-action-mask",
        choices=rl.DQN_VALID_ACTION_MASK_MODES,
        default="action-start-v1",
        help="Valid-action mask used for late jump-hit defensive margin competitors",
    )
    parser.add_argument(
        "--projectile-defensive-expert-margin-loss",
        action=argparse.BooleanOptionalAction,
        default=False,
        help=(
            "Add a valid-action-masked margin loss on clean/low-damage human-demo "
            "projectile back/guard rows so defensive actions rank above jump and high-risk specials"
        ),
    )
    parser.add_argument(
        "--projectile-defensive-expert-margin",
        type=float,
        default=0.08,
        help="Q margin required between the best defensive action and the best projectile competitor",
    )
    parser.add_argument(
        "--projectile-defensive-expert-margin-weight",
        type=float,
        default=1.0,
        help="Auxiliary loss weight for --projectile-defensive-expert-margin-loss",
    )
    parser.add_argument(
        "--projectile-defensive-expert-margin-batch-size",
        type=int,
        default=0,
        help=(
            "Extra clean/low-damage human-demo projectile defense rows sampled per DQN step "
            "for margin-only updates; 0 keeps loss limited to the normal replay batch"
        ),
    )
    parser.add_argument(
        "--projectile-defensive-expert-margin-min-time-to-self",
        type=int,
        default=0,
        help="Minimum obs_projectile_time_to_self for defensive expert margin rows",
    )
    parser.add_argument(
        "--projectile-defensive-expert-margin-max-time-to-self",
        type=int,
        default=12,
        help="Maximum obs_projectile_time_to_self for defensive expert margin rows",
    )
    parser.add_argument(
        "--projectile-defensive-expert-margin-time-ranges",
        default="",
        help=(
            "Optional comma-separated obs_projectile_time_to_self ranges for defensive expert margin, "
            "e.g. 0-22,31-48. Overrides min/max when set."
        ),
    )
    parser.add_argument(
        "--projectile-defensive-expert-margin-window-decisions",
        type=int,
        default=12,
        help="Lookahead decision window used to reject defensive expert rows with too much self HP damage",
    )
    parser.add_argument(
        "--projectile-defensive-expert-margin-max-self-hp",
        type=int,
        default=1,
        help="Maximum self HP damage allowed in the projectile defense window before excluding the row",
    )
    parser.add_argument(
        "--projectile-defensive-expert-margin-all-competitors",
        action=argparse.BooleanOptionalAction,
        default=False,
        help=(
            "Apply defensive expert margin to every violating jump/special competitor in the row; "
            "the gradient is averaged across violating competitors to avoid scaling with action count"
        ),
    )
    parser.add_argument(
        "--projectile-defensive-expert-margin-sources",
        default="human-demo",
        help="Comma-separated execution sources eligible for defensive expert margin rows",
    )
    parser.add_argument(
        "--projectile-defensive-expert-margin-valid-action-mask",
        choices=rl.DQN_VALID_ACTION_MASK_MODES,
        default="action-start-v1",
        help="Valid-action mask used for defensive expert margin competitors",
    )
    parser.add_argument(
        "--projectile-timing-group-margin-loss",
        action=argparse.BooleanOptionalAction,
        default=False,
        help=(
            "Add a filtered group margin loss for incoming projectile timing: defense group wins in "
            "configured defensive timing ranges, jump-start group wins in configured safe-jump timing ranges"
        ),
    )
    parser.add_argument(
        "--projectile-timing-group-margin",
        type=float,
        default=0.08,
        help="Q margin required between the selected projectile timing group and its competitors",
    )
    parser.add_argument(
        "--projectile-timing-group-margin-weight",
        type=float,
        default=1.0,
        help="Auxiliary loss weight for --projectile-timing-group-margin-loss",
    )
    parser.add_argument(
        "--projectile-timing-group-margin-batch-size",
        type=int,
        default=0,
        help=(
            "Extra incoming-projectile rows sampled per DQN step for timing group margin-only updates; "
            "0 keeps loss limited to the normal replay batch"
        ),
    )
    parser.add_argument(
        "--projectile-timing-group-margin-defense-time-ranges",
        default="",
        help=(
            "Comma-separated obs_projectile_time_to_self ranges where guard/back should rank above "
            "jump-start and high-risk special competitors, e.g. 0-22,31-48"
        ),
    )
    parser.add_argument(
        "--projectile-timing-group-margin-jump-time-ranges",
        default="",
        help=(
            "Comma-separated obs_projectile_time_to_self ranges where jump-start actions should rank "
            "above other valid actions, e.g. 23-30"
        ),
    )
    parser.add_argument(
        "--projectile-timing-group-margin-sources",
        default="remote",
        help="Comma-separated execution sources eligible for projectile timing group margin rows",
    )
    parser.add_argument(
        "--projectile-timing-group-margin-valid-action-mask",
        choices=rl.DQN_VALID_ACTION_MASK_MODES,
        default="action-start-v1",
        help="Valid-action mask used for projectile timing group margin targets and competitors",
    )
    parser.add_argument(
        "--projectile-timing-group-margin-threat-max-dx",
        type=int,
        default=240,
        help="Maximum positive obs_projectile_rel_x for projectile timing group margin rows",
    )
    parser.add_argument(
        "--projectile-timing-group-margin-threat-max-abs-y",
        type=int,
        default=96,
        help="Maximum absolute obs_projectile_rel_y for projectile timing group margin rows",
    )
    parser.add_argument(
        "--grounded-normal-defense-margin-loss",
        action="store_true",
        help="Apply a grounded normal defense margin loss that pushes guard/back above forward/normals in opponent normal attack threat rows",
    )
    parser.add_argument(
        "--grounded-normal-defense-margin",
        type=float,
        default=0.1,
        help="Margin that guard/back Q should exceed forward/stand-normals Q in opponent grounded normal threat rows",
    )
    parser.add_argument(
        "--grounded-normal-defense-margin-weight",
        type=float,
        default=0.5,
        help="Auxiliary loss weight for --grounded-normal-defense-margin-loss",
    )
    parser.add_argument(
        "--grounded-normal-defense-margin-batch-size",
        type=int,
        default=0,
        help="Additional margin samples per training step (0 = only sample from the main batch)",
    )
    parser.add_argument(
        "--grounded-normal-defense-margin-sources",
        default="human-demo",
        help="Comma-separated execution sources eligible for grounded normal defense margin rows",
    )
    parser.add_argument(
        "--grounded-normal-defense-valid-action-mask",
        choices=rl.DQN_VALID_ACTION_MASK_MODES,
        default="action-start-v1",
        help="Valid-action mask used for grounded normal defense safe and unsafe action filtering",
    )
    parser.add_argument(
        "--grounded-normal-defense-margin-max-abs-dx",
        type=int,
        default=144,
        help="Maximum obs_abs_dx for opponent grounded normal threat rows to be eligible for defense margin",
    )
    parser.add_argument(
        "--grounded-normal-defense-bc-loss",
        action="store_true",
        help="Apply a BC cross-entropy loss toward human-demo guard/back actions in opponent grounded normal threat rows",
    )
    parser.add_argument(
        "--grounded-normal-defense-bc-weight",
        type=float,
        default=0.1,
        help="Loss weight for --grounded-normal-defense-bc-loss",
    )
    parser.add_argument(
        "--grounded-normal-defense-bc-sources",
        default="human-demo",
        help="Comma-separated execution sources eligible for grounded normal defense BC rows",
    )
    parser.add_argument(
        "--grounded-normal-defense-bc-max-abs-dx",
        type=int,
        default=144,
        help="Maximum obs_abs_dx for grounded normal defense BC loss rows",
    )
    parser.add_argument(
        "--low-defense-reward-shaping",
        action="store_true",
        help=(
            "Apply event-log low attack defense shaping: penalize guard-stand/back/forward/no-label "
            "when crouch-lk/mk/hk hits self, and reward guard-crouch when it blocks low"
        ),
    )
    parser.add_argument(
        "--low-defense-hit-penalty",
        type=float,
        default=0.5,
        help="Raw reward penalty for failing to crouch-guard an event-log low attack",
    )
    parser.add_argument(
        "--low-defense-block-bonus",
        type=float,
        default=0.2,
        help="Raw reward bonus when guard-crouch blocks an event-log low attack",
    )
    parser.add_argument(
        "--low-defense-margin-loss",
        action="store_true",
        help="Add a valid-action-masked margin loss so guard-crouch ranks above guard-stand/back/forward in low-threat rows",
    )
    parser.add_argument(
        "--low-defense-margin",
        type=float,
        default=0.08,
        help="Q margin required between guard-crouch and the best guard-stand/back/forward competitor",
    )
    parser.add_argument(
        "--low-defense-margin-weight",
        type=float,
        default=0.5,
        help="Auxiliary loss weight for --low-defense-margin-loss",
    )
    parser.add_argument(
        "--low-defense-margin-batch-size",
        type=int,
        default=0,
        help="Additional low-threat rows sampled per training step for low-defense margin-only updates",
    )
    parser.add_argument(
        "--low-defense-margin-sources",
        default="cpu-demo,human-demo,remote",
        help="Comma-separated execution sources eligible for low-defense margin rows",
    )
    parser.add_argument(
        "--low-defense-valid-action-mask",
        choices=rl.DQN_VALID_ACTION_MASK_MODES,
        default="action-start-v1",
        help="Valid-action mask used for low-defense margin target and competitors",
    )
    parser.add_argument(
        "--low-defense-max-abs-dx",
        type=int,
        default=144,
        help="Maximum obs_abs_dx for event-log low-defense reward and margin rows",
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
            "current-schema demo rows and policy labels for current-schema remote rows"
        ),
    )
    parser.add_argument(
        "--training-mode",
        choices=("dqn", "bc"),
        default="dqn",
        help=(
            "Training algorithm: dqn for Q-learning (default), bc for Behavioral Cloning "
            "(supervised cross-entropy from engine+input labels)"
        ),
    )
    parser.add_argument("--target-sync-steps", type=int, default=200, help="Steps between target-network syncs")
    parser.add_argument(
        "--dqn-target-mode",
        choices=DQN_TARGET_MODES,
        default="standard",
        help="DQN bootstrapping target: standard uses max target-network value; double selects with online network and evaluates with target network",
    )
    parser.add_argument(
        "--dqn-valid-action-mask",
        choices=rl.DQN_VALID_ACTION_MASK_MODES,
        default="off",
        help=(
            "Optional train-time DQN valid-action mask for target max and greedy diagnostics. "
            "self-routine-v1 gates from legacy routine fields; action-start-v1 gates from schema-backed "
            "ground/jump/air action-start flags"
        ),
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
    hidden_sizes = parse_hidden_sizes(args.hidden_sizes)
    init_model = (
        load_init_dqn_model(
            str(args.init_model),
            actions,
            hidden_sizes,
            str(args.init_model_action_mode),
            int(args.seed),
        )
        if str(args.init_model).strip()
        else None
    )
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
    combat_event_training_mode = str(args.combat_event_training_mode)
    combat_event_validation: combat_events.CombatEventTrainingValidation | None = None
    combat_event_log_paths = [str(path) for path in args.combat_event_logs]
    combat_event_reward_config = combat_events.CombatEventRewardConfig(
        enabled=combat_event_training_mode == "reward-shaping",
        profile=str(args.combat_event_reward_profile),
        scale=max(0.0, float(args.combat_event_reward_scale)),
    )
    bc_event_weight_config = bc_event_weight_config_from_args(args)
    bc_label_balance_config = bc_label_balance_config_from_args(args)
    bc_family_margin_config = bc_family_margin_config_from_args(args)
    combat_event_unlabeled_movement_filter_config = (
        combat_event_unlabeled_movement_filter_config_from_args(args)
    )
    combat_event_batch_sampling_config = combat_event_batch_sampling_config_from_args(args)
    combat_event_movement_credit_config = combat_event_movement_credit_config_from_args(args)
    low_defense_requested = bool(args.low_defense_reward_shaping or args.low_defense_margin_loss)
    if combat_event_training_mode == "off" and combat_event_log_paths:
        raise SystemExit("--combat-event-logs requires --combat-event-training-mode validate or reward-shaping")
    if bc_event_weight_config.enabled:
        if str(args.training_mode) != "bc":
            raise SystemExit("--bc-event-weighting is only supported with --training-mode bc")
        if combat_event_training_mode != "validate":
            raise SystemExit("--bc-event-weighting requires --combat-event-training-mode validate")
        if not combat_event_log_paths:
            raise SystemExit("--bc-event-weighting requires --combat-event-logs")
    if bc_family_margin_config.enabled:
        if str(args.training_mode) != "bc":
            raise SystemExit("--bc-family-margin is only supported with --training-mode bc")
        if combat_event_training_mode != "validate":
            raise SystemExit("--bc-family-margin requires --combat-event-training-mode validate")
        if not combat_event_log_paths:
            raise SystemExit("--bc-family-margin requires --combat-event-logs")
        if not bc_event_weight_config.enabled:
            raise SystemExit("--bc-family-margin currently requires --bc-event-weighting event-weighted-v1")
    if combat_event_unlabeled_movement_filter_config.enabled and combat_event_training_mode != "reward-shaping":
        raise SystemExit(
            "--combat-event-unlabeled-movement-policy requires "
            "--combat-event-training-mode reward-shaping"
        )
    if combat_event_batch_sampling_config.enabled:
        if combat_event_training_mode != "reward-shaping":
            raise SystemExit(
                "--combat-event-batch-sampling requires --combat-event-training-mode reward-shaping"
            )
        if str(args.batch_sampling) != "uniform":
            raise SystemExit("--combat-event-batch-sampling currently requires --batch-sampling uniform")
    if combat_event_movement_credit_config.enabled and combat_event_training_mode != "reward-shaping":
        raise SystemExit("--combat-event-movement-credit requires --combat-event-training-mode reward-shaping")
    if low_defense_requested and combat_event_training_mode != "reward-shaping":
        raise SystemExit("--low-defense-* options require --combat-event-training-mode reward-shaping")
    if combat_event_training_mode != "off":
        if not combat_event_log_paths:
            raise SystemExit(f"--combat-event-training-mode {combat_event_training_mode} requires --combat-event-logs")
        combat_event_validation = combat_events.validate_combat_event_training_logs(
            combat_event_log_paths,
            [str(path) for path in args.transition_logs],
            rows,
            mode=combat_event_training_mode,
        )
        if combat_event_validation.fatal_errors:
            raise SystemExit(
                "combat event validation failed: " + "; ".join(combat_event_validation.fatal_errors)
            )
    if str(args.training_mode) == "bc":
        if combat_event_reward_config.enabled:
            raise SystemExit("--combat-event-training-mode reward-shaping is only supported for DQN training")
        if combat_event_unlabeled_movement_filter_config.enabled:
            raise SystemExit("--combat-event-unlabeled-movement-policy is only supported for DQN training")
        if combat_event_batch_sampling_config.enabled:
            raise SystemExit("--combat-event-batch-sampling is only supported for DQN training")
        if combat_event_movement_credit_config.enabled:
            raise SystemExit("--combat-event-movement-credit is only supported for DQN training")
        if low_defense_requested:
            raise SystemExit("--low-defense-* options are only supported for DQN training")
        # --- BC training path ---
        (
            bc_layers,
            bc_train_stats,
            bc_label_counts,
            bc_skipped,
            bc_event_weight_stats,
            bc_event_reward_stats,
            bc_label_balance_stats,
            bc_family_margin_stats,
        ) = train_bc(
            rows,
            actions,
            hidden_sizes,
            max(1, args.steps),
            max(1, args.batch_size),
            max(1e-8, args.learning_rate),
            args.seed,
            args.log_interval,
            max(0.0, float(args.dqn_entropy_reg_weight)),
            init_model.layers if init_model is not None else None,
            combat_event_validation,
            bc_event_weight_config,
            bc_label_balance_config,
            bc_family_margin_config,
        )
        replay_source_mix_summary = dict(replay_source_mix_stats.as_metadata()) if hasattr(replay_source_mix_stats, "as_metadata") else {}
        bc_metadata: dict[str, object] = {
            "actions": list(actions),
            "hidden_sizes": hidden_sizes,
            "steps": max(1, args.steps),
            "batch_size": max(1, args.batch_size),
            "learning_rate": max(1e-8, args.learning_rate),
            "entropy_reg_weight": max(0.0, float(args.dqn_entropy_reg_weight)),
            "label_counts": {str(k): int(v) for k, v in bc_label_counts.items()},
            "skipped_labels": {str(k): int(v) for k, v in bc_skipped.items()},
            "total_labeled": sum(bc_label_counts.values()),
            "total_rows": len(rows),
            "bc_event_weighting_config": bc_event_weight_config.as_metadata(),
            "bc_event_weight_stats": bc_event_weight_stats.as_metadata(),
            "bc_event_reward_stats": bc_event_reward_stats.as_metadata(),
            "bc_label_balance_config": bc_label_balance_config.as_metadata(),
            "bc_label_balance_stats": bc_label_balance_stats.as_metadata(),
            "bc_family_margin_config": bc_family_margin_config.as_metadata(),
            "bc_family_margin_stats": bc_family_margin_stats.as_metadata(),
            **bc_train_stats,
        }
        if combat_event_validation is not None:
            bc_metadata["combat_event_training"] = combat_event_validation.as_metadata()
        total_labeled = sum(bc_label_counts.values())
        if total_labeled <= 0:
            raise SystemExit("BC training: no labeled rows after parsing all transition logs")
        version = next_model_version(args.model_dir, args.model_version)
        publish_model(
            args.model_dir,
            version,
            actions,
            bc_layers,
            min(1.0, max(0.0, args.epsilon)),
            args.fallback_policy,
            total_labeled,
            bc_metadata,
            policy="bc",
        )
        label_parts = ",".join(
            f"{action}:{bc_label_counts.get(action, 0)}"
            for action in sorted(actions)
            if bc_label_counts.get(action, 0) > 0
        )
        print(
            f"BC published version={version} model_dir={args.model_dir} "
            f"rows={len(rows)} labeled={total_labeled} "
            f"actions={len(actions)} "
            f"loss={bc_train_stats.get('last_loss', 0.0):.6f} "
            f"avg_loss={bc_train_stats.get('avg_loss', 0.0):.6f} "
            f"entropy_reg={max(0.0, float(args.dqn_entropy_reg_weight))} "
            f"event_weighted={int(bc_event_weight_config.enabled)} "
            f"weighted_rows={bc_event_weight_stats.weighted_rows} "
            f"avg_weight={bc_event_weight_stats.avg_weight:.3f} "
            f"label_balance={bc_label_balance_config.mode} "
            f"label_balance_avg={bc_label_balance_stats.avg_factor:.3f} "
            f"family_margin={bc_family_margin_config.mode} "
            f"family_margin_eligible={bc_family_margin_stats.eligible_rows} "
            f"skipped={dict(bc_skipped)} "
            f"top_labels=({label_parts[:300]})",
            flush=True,
        )
        if combat_event_validation is not None:
            print(f"BC diagnostics combat_event={combat_event_validation.summary_line()}", flush=True)
        if bc_event_weight_config.enabled:
            print(
                "BC diagnostics event_weight="
                f"checked:{bc_event_weight_stats.checked_labeled_rows} "
                f"weighted:{bc_event_weight_stats.weighted_rows} "
                f"pos:{bc_event_weight_stats.positive_rows} "
                f"neg:{bc_event_weight_stats.negative_rows} "
                f"neutral:{bc_event_weight_stats.neutral_rows} "
                f"clamp_min:{bc_event_weight_stats.clamped_min_rows} "
                f"clamp_max:{bc_event_weight_stats.clamped_max_rows} "
                f"raw_sum:{bc_event_weight_stats.raw_adjustment_sum:.3f} "
                f"weight_sum:{bc_event_weight_stats.weight_sum:.3f}",
                flush=True,
            )
        if bc_label_balance_config.enabled:
            top_factors = ",".join(
                f"{action}:{factor:.2f}"
                for action, factor in sorted(
                    bc_label_balance_stats.label_factors.items(),
                    key=lambda item: (-item[1], item[0]),
                )[: args.diagnostic_top_n]
            )
            print(
                "BC diagnostics label_balance="
                f"mode:{bc_label_balance_config.mode} "
                f"rows:{bc_label_balance_stats.balanced_rows} "
                f"avg_factor:{bc_label_balance_stats.avg_factor:.3f} "
                f"top_factors:{top_factors}",
                flush=True,
            )
        if bc_family_margin_config.enabled:
            top_targets = ",".join(
                f"{action}:{count}"
                for action, count in sorted(
                    bc_family_margin_stats.target_action_counts.items(),
                    key=lambda item: (-item[1], item[0]),
                )[: args.diagnostic_top_n]
            )
            top_negatives = ",".join(
                f"{action}:{count}"
                for action, count in sorted(
                    bc_family_margin_stats.negative_action_counts.items(),
                    key=lambda item: (-item[1], item[0]),
                )[: args.diagnostic_top_n]
            )
            print(
                "BC diagnostics family_margin="
                f"mode:{bc_family_margin_config.mode} "
                f"eligible:{bc_family_margin_stats.eligible_rows} "
                f"sampled:{bc_family_margin_stats.sampled_rows} "
                f"violations:{bc_family_margin_stats.violation_rows} "
                f"loss:{bc_family_margin_stats.loss_total:.6f} "
                f"avg_loss:{bc_family_margin_stats.avg_loss:.6f} "
                f"targets:{top_targets} "
                f"negatives:{top_negatives}",
                flush=True,
            )
        return

    dqn_action_filter_config = dqn_action_filter_config_from_args(args)
    reward_risk_config = reward_risk_config_from_args(args)
    reward_guard_config = reward_guard_config_from_args(args)
    reward_spacing_config = reward_spacing_config_from_args(args)
    reward_position_config = reward_position_config_from_args(args)
    reward_projectile_response_config = reward_projectile_response_config_from_args(args)
    projectile_response_oversample_config = projectile_response_oversample_config_from_args(args)
    projectile_batch_config = projectile_batch_config_from_args(args)
    projectile_expert_margin_config = projectile_expert_margin_config_from_args(args)
    special_expert_margin_config = special_expert_margin_config_from_args(args)
    projectile_late_defensive_margin_config = projectile_late_defensive_margin_config_from_args(args)
    projectile_defensive_expert_margin_config = projectile_defensive_expert_margin_config_from_args(args)
    projectile_timing_group_margin_config = projectile_timing_group_margin_config_from_args(args)
    grounded_normal_defense_margin_config = grounded_normal_defense_config_from_args(args)
    grounded_normal_defense_bc_config = grounded_normal_defense_bc_config_from_args(args)
    low_defense_config = low_defense_config_from_args(args)
    engine_outcome_config = engine_outcome_config_from_args(args)
    conservative_action_penalty_config = conservative_action_penalty_config_from_args(args)
    unsupported_action_regularization_config = dqn_unsupported_action_regularization_config_from_args(args)
    movement_regression_config = movement_regression_loss_config_from_args(args)
    valid_action_mask_config = dqn_valid_action_mask_training_config_from_args(args)
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
        reward_projectile_response_stats,
        projectile_response_oversample_stats,
        engine_outcome_stats,
        combat_event_reward_stats,
        combat_event_unlabeled_movement_filter_stats,
        combat_event_movement_credit_stats,
        low_defense_reward_stats,
    ) = build_experiences(
        rows,
        actions,
        args.reward_scale,
        str(args.training_mode_hp_delta_mode),
        str(args.training_action_source),
        reward_risk_config,
        reward_guard_config,
        reward_spacing_config,
        reward_position_config,
        reward_projectile_response_config,
        projectile_response_oversample_config,
        projectile_batch_config,
        projectile_expert_margin_config,
        special_expert_margin_config,
        projectile_late_defensive_margin_config,
        projectile_defensive_expert_margin_config,
        grounded_normal_defense_margin_config,
        grounded_normal_defense_bc_config,
        low_defense_config,
        engine_outcome_config,
        dqn_action_filter_config,
        combat_event_validation,
        combat_event_reward_config,
        combat_event_unlabeled_movement_filter_config,
        combat_event_movement_credit_config,
    )
    if not experiences:
        raise SystemExit("No DQN experiences built from transition logs")
    projectile_batch_stats = projectile_batch_stats_from_experiences(experiences, actions)
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

    (
        layers,
        train_stats,
        unsupported_action_regularization_stats,
        movement_regression_stats,
        projectile_expert_margin_stats,
        special_expert_margin_stats,
        projectile_late_defensive_margin_stats,
        projectile_defensive_expert_margin_stats,
        projectile_timing_group_margin_stats,
        grounded_normal_defense_stats,
        grounded_normal_defense_bc_stats,
        low_defense_margin_stats,
        valid_action_mask_stats,
    ) = train_dqn(
        experiences,
        actions,
        action_counts,
        hidden_sizes,
        max(1, args.steps),
        max(1, args.batch_size),
        max(1e-8, args.learning_rate),
        min(0.999, max(0.0, args.gamma)),
        max(1, args.target_sync_steps),
        args.seed,
        args.log_interval,
        batch_sampling_config,
        combat_event_batch_sampling_config,
        args.dqn_target_mode,
        unsupported_action_regularization_config,
        movement_regression_config,
        projectile_expert_margin_config,
        special_expert_margin_config,
        projectile_late_defensive_margin_config,
        projectile_defensive_expert_margin_config,
        projectile_timing_group_margin_config,
        grounded_normal_defense_margin_config,
        grounded_normal_defense_bc_config,
        low_defense_config,
        valid_action_mask_config,
        max(0.0, float(args.dqn_entropy_reg_weight)),
        init_model.layers if init_model is not None else None,
    )
    batch_sampling_diag = batch_sampling_diagnostics(
        experiences,
        actions,
        max(1, args.batch_size),
        batch_sampling_config,
    )
    combat_event_batch_sampling_diag = combat_event_batch_sampling_diagnostics(
        experiences,
        max(1, args.batch_size),
        combat_event_batch_sampling_config,
    )
    greedy_diag = evaluate_greedy_actions(
        layers,
        experiences,
        actions,
        args.eval_limit,
        valid_action_mask_config,
        valid_action_mask_stats,
    )
    projectile_expert_q_gap_diag = projectile_expert_q_gap_diagnostics(
        layers,
        experiences,
        actions,
        projectile_expert_margin_config,
    )
    version = next_model_version(args.model_dir, args.model_version)
    reward_sources = []
    if combat_events.uses_transition_hp_delta(combat_event_reward_config):
        reward_sources.append("hp-delta")
    if reward_risk_config.profile != "none":
        reward_sources.append("risk-cost")
    if reward_guard_stats.net_adjustment != 0.0:
        reward_sources.append("guard-shaping")
    if reward_spacing_stats.net_adjustment != 0.0:
        reward_sources.append("spacing-shaping")
    if reward_position_stats.net_adjustment != 0.0:
        reward_sources.append("position-shaping")
    if reward_projectile_response_stats.net_adjustment != 0.0:
        reward_sources.append("projectile-response-shaping")
    if engine_outcome_config.training_mode != "off":
        reward_sources.append("engine-outcome")
    if conservative_action_penalty_stats.adjusted_experiences > 0:
        reward_sources.append("conservative-action-penalty")
    if projectile_expert_margin_config.enabled:
        reward_sources.append("projectile-expert-margin")
    if special_expert_margin_config.enabled:
        reward_sources.append("special-expert-margin")
    if projectile_late_defensive_margin_config.enabled:
        reward_sources.append("projectile-late-defensive-margin")
    if projectile_defensive_expert_margin_config.enabled:
        reward_sources.append("projectile-defensive-expert-margin")
    if projectile_timing_group_margin_config.enabled:
        reward_sources.append("projectile-timing-group-margin")
    if low_defense_reward_stats.net_adjustment != 0.0:
        reward_sources.append("low-defense-shaping")
    if low_defense_config.margin_enabled:
        reward_sources.append("low-defense-margin")
    if movement_regression_config.enabled:
        reward_sources.append("movement-regression-loss")
    if combat_events.uses_transition_hp_delta(combat_event_reward_config) and str(args.training_mode_hp_delta_mode) == "damage-only":
        reward_sources.append("training-mode-damage-only-hp")
    if combat_event_reward_stats.applied_event_rewards > 0:
        reward_sources.append(f"combat-event-{combat_event_reward_config.profile}")
    if combat_event_unlabeled_movement_filter_stats.dropped_rows > 0:
        reward_sources.append("event-unlabeled-movement-filter")
    if combat_event_batch_sampling_config.enabled:
        reward_sources.append(f"combat-event-batch-{combat_event_batch_sampling_config.mode}")
    if combat_event_movement_credit_stats.applied_rows > 0:
        reward_sources.append(f"combat-event-movement-credit-{combat_event_movement_credit_config.mode}")
    reward_source = "+".join(reward_sources) if reward_sources else "none"
    metadata = {
        "transition_logs": args.transition_logs,
        "incremental_training": init_model is not None,
        "init_model_path": init_model.path if init_model is not None else "",
        "init_model_version": init_model.version if init_model is not None else 0,
        "init_model_source": init_model.source if init_model is not None else "",
        "init_model_feature_count": len(init_model.feature_names) if init_model is not None else 0,
        "init_model_action_count": len(init_model.actions) if init_model is not None else 0,
        "init_model_action_mode": init_model.action_mode if init_model is not None else str(args.init_model_action_mode),
        "init_model_validation": (
            f"{init_model.action_mode}-action-feature-layer-match" if init_model is not None else "none"
        ),
        "replay_recipe": build_replay_recipe_metadata(args, replay_source_mix_config, init_model),
        "rows_read": len(rows),
        "rows_read_before_episode_drop": rows_read_before_episode_drop,
        "drop_initial_episodes_per_run": max(0, int(args.drop_initial_episodes_per_run)),
        "dropped_initial_episode_rows": dropped_initial_episode_rows,
        "dropped_initial_episodes": dropped_initial_episodes,
        "rows_read_before_source_mix": rows_read_before_source_mix,
        "replay_source_mix_config": replay_source_mix_config.as_metadata(),
        "replay_source_mix_stats": replay_source_mix_stats.as_metadata(),
        "dqn_action_filter_config": dqn_action_filter_config.as_metadata(),
        "combat_event_unlabeled_movement_filter_config": (
            combat_event_unlabeled_movement_filter_config.as_metadata()
        ),
        "combat_event_unlabeled_movement_filter_stats": (
            combat_event_unlabeled_movement_filter_stats.as_metadata()
        ),
        "combat_event_batch_sampling_config": combat_event_batch_sampling_config.as_metadata(),
        "combat_event_batch_sampling_stats": combat_event_batch_sampling_diag.as_metadata(),
        "combat_event_movement_credit_config": combat_event_movement_credit_config.as_metadata(),
        "combat_event_movement_credit_stats": combat_event_movement_credit_stats.as_metadata(),
        "experiences": len(experiences),
        "actions_subset": list(actions),
        "actions_subset_size": len(actions),
        "build_diagnostics": build_stats.as_metadata(),
        "source_replay_diagnostics": source_stats.as_metadata(),
        "delayed_rewards": build_stats.unrecognized_delayed_rewards + build_stats.macro_continuation_delayed_rewards,
        "reward_source": reward_source,
        "reward_scale": args.reward_scale,
        "training_mode_hp_delta_mode": str(args.training_mode_hp_delta_mode),
        "reward_scale_applied_after_risk_cost": True,
        "reward_scale_applied_after_raw_adjustments": True,
        "conservative_action_penalty_config": conservative_action_penalty_config.as_metadata(),
        "conservative_action_penalty_stats": conservative_action_penalty_stats.as_metadata(),
        "dqn_unsupported_action_regularization_config": unsupported_action_regularization_config.as_metadata(),
        "dqn_unsupported_action_regularization_stats": unsupported_action_regularization_stats.as_metadata(),
        "movement_regression_loss_config": movement_regression_config.as_metadata(),
        "movement_regression_loss_stats": movement_regression_stats.as_metadata(),
        "training_action_source": str(args.training_action_source),
        "reward_risk_profile": reward_risk_config.profile,
        "reward_risk_window_decisions": reward_risk_config.window_decisions,
        "reward_attack_no_damage_cost": reward_risk_config.attack_no_damage_cost,
        "reward_attack_punished_cost": reward_risk_config.attack_punished_cost,
        "reward_shoryuken_no_damage_extra_cost": reward_risk_config.shoryuken_no_damage_extra_cost,
        "reward_shoryuken_punished_extra_cost": reward_risk_config.shoryuken_punished_extra_cost,
        "reward_jump_attack_no_damage_extra_cost": reward_risk_config.jump_attack_no_damage_extra_cost,
        "reward_jump_attack_punished_extra_cost": reward_risk_config.jump_attack_punished_extra_cost,
        "reward_throw_far_cost": reward_risk_config.throw_far_cost,
        "reward_throw_far_max_abs_dx": reward_risk_config.throw_far_max_abs_dx,
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
        "reward_projectile_response_profile": reward_projectile_response_config.profile,
        "reward_projectile_response_window_decisions": reward_projectile_response_config.window_decisions,
        "reward_projectile_threat_min_time_to_self": (
            reward_projectile_response_config.threat_min_time_to_self
        ),
        "reward_projectile_threat_max_time_to_self": (
            reward_projectile_response_config.threat_max_time_to_self
        ),
        "reward_projectile_threat_max_dx": reward_projectile_response_config.threat_max_dx,
        "reward_projectile_threat_max_abs_y": reward_projectile_response_config.threat_max_abs_y,
        "reward_projectile_close_max_dx": reward_projectile_response_config.close_max_dx,
        "reward_projectile_safe_jump_bonus": reward_projectile_response_config.safe_jump_bonus,
        "reward_projectile_late_jump_hit_cost": reward_projectile_response_config.late_jump_hit_cost,
        "reward_projectile_close_back_success_bonus": (
            reward_projectile_response_config.close_back_success_bonus
        ),
        "reward_projectile_close_guard_success_bonus": (
            reward_projectile_response_config.close_guard_success_bonus
        ),
        "reward_projectile_back_escape_min_dx_delta": (
            reward_projectile_response_config.back_escape_min_dx_delta
        ),
        "reward_projectile_guard_require_contact": reward_projectile_response_config.guard_require_contact,
        "reward_projectile_response_stats": reward_projectile_response_stats.as_metadata(),
        "projectile_response_oversample_config": projectile_response_oversample_config.as_metadata(),
        "projectile_response_oversample_stats": projectile_response_oversample_stats.as_metadata(),
        "projectile_batch_config": projectile_batch_config.as_metadata(),
        "projectile_batch_stats": projectile_batch_stats.as_metadata(),
        "projectile_expert_margin_config": projectile_expert_margin_config.as_metadata(),
        "projectile_expert_margin_stats": projectile_expert_margin_stats.as_metadata(),
        "projectile_expert_q_gap_diagnostics": projectile_expert_q_gap_diag.as_metadata(),
        "special_expert_margin_config": special_expert_margin_config.as_metadata(),
        "special_expert_margin_stats": special_expert_margin_stats.as_metadata(),
        "projectile_late_defensive_margin_config": projectile_late_defensive_margin_config.as_metadata(),
        "projectile_late_defensive_margin_stats": projectile_late_defensive_margin_stats.as_metadata(),
        "projectile_defensive_expert_margin_config": projectile_defensive_expert_margin_config.as_metadata(),
        "projectile_defensive_expert_margin_stats": projectile_defensive_expert_margin_stats.as_metadata(),
        "projectile_timing_group_margin_config": projectile_timing_group_margin_config.as_metadata(),
        "projectile_timing_group_margin_stats": projectile_timing_group_margin_stats.as_metadata(),
        "grounded_normal_defense_margin_config": grounded_normal_defense_margin_config.as_metadata(),
        "grounded_normal_defense_margin_stats": grounded_normal_defense_stats.as_metadata(),
        "grounded_normal_defense_bc_config": grounded_normal_defense_bc_config.as_metadata(),
        "grounded_normal_defense_bc_stats": grounded_normal_defense_bc_stats.as_metadata(),
        "low_defense_config": low_defense_config.as_metadata(),
        "low_defense_reward_stats": low_defense_reward_stats.as_metadata(),
        "low_defense_margin_stats": low_defense_margin_stats.as_metadata(),
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
        "hidden_sizes": hidden_sizes,
        "batch_sampling": batch_sampling_diag.as_metadata(),
        "gamma": min(0.999, max(0.0, args.gamma)),
        "learning_rate": max(1e-8, args.learning_rate),
        "target_sync_steps": max(1, args.target_sync_steps),
        "dqn_target_mode": args.dqn_target_mode,
        "dqn_valid_action_mask_config": valid_action_mask_config.as_metadata(),
        "dqn_valid_action_mask_stats": valid_action_mask_stats.as_metadata(),
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
    if combat_event_validation is not None:
        metadata["combat_event_training"] = combat_event_validation.as_metadata()
        metadata["combat_event_reward_config"] = combat_event_reward_config.as_metadata()
        metadata["combat_event_reward_stats"] = combat_event_reward_stats.as_metadata()
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
        f"valid_mask={valid_action_mask_config.mode} "
        f"init={'warm-start:' + str(init_model.version) if init_model is not None else 'random'} "
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
        f"projectile_bonus={reward_projectile_response_stats.total_bonus:.1f} "
        f"projectile_cost={reward_projectile_response_stats.total_cost:.1f} "
        f"projectile_net={reward_projectile_response_stats.net_adjustment:.1f} "
        f"projectile_oversample={projectile_response_oversample_stats.base_experiences}/"
        f"+{projectile_response_oversample_stats.extra_experiences} "
        f"projectile_batch={projectile_batch_stats.eligible_experiences} "
        f"projectile_margin={projectile_expert_margin_stats.violation_events}/"
        f"{projectile_expert_margin_stats.sampled_events} "
        f"projectile_margin_loss={projectile_expert_margin_stats.last_loss:.6f} "
        f"special_margin={special_expert_margin_stats.violation_events}/"
        f"{special_expert_margin_stats.sampled_events} "
        f"special_margin_loss={special_expert_margin_stats.last_loss:.6f} "
        f"projectile_late_def_margin={projectile_late_defensive_margin_stats.violation_events}/"
        f"{projectile_late_defensive_margin_stats.sampled_events} "
        f"projectile_late_def_margin_loss={projectile_late_defensive_margin_stats.last_loss:.6f} "
        f"projectile_def_expert_margin={projectile_defensive_expert_margin_stats.violation_events}/"
        f"{projectile_defensive_expert_margin_stats.sampled_events} "
        f"projectile_def_expert_margin_loss={projectile_defensive_expert_margin_stats.last_loss:.6f} "
        f"projectile_timing_group_margin={projectile_timing_group_margin_stats.violation_events}/"
        f"{projectile_timing_group_margin_stats.sampled_events} "
        f"projectile_timing_group_margin_loss={projectile_timing_group_margin_stats.last_loss:.6f} "
        f"engine_outcome={engine_outcome_config.training_mode}:{engine_outcome_stats.included_events}/"
        f"{engine_outcome_stats.event_rows} "
        f"engine_outcome_net={engine_outcome_stats.net_adjustment:.1f} "
        f"engine_oversample={engine_outcome_stats.training_experiences}/"
        f"+{engine_outcome_stats.oversample_extra_experiences} "
        f"conservative_cost={conservative_action_penalty_stats.raw_cost_total:.1f} "
        f"unsupported_reg={unsupported_action_regularization_stats.regularized_events}/"
        f"{unsupported_action_regularization_stats.eligible_action_count} "
        f"unsupported_loss={unsupported_action_regularization_stats.last_loss:.6f} "
        f"movement_reg={movement_regression_stats.violation_events}/"
        f"{movement_regression_stats.sampled_events} "
        f"movement_loss={movement_regression_stats.last_loss:.6f} "
        f"event_move_credit={combat_event_movement_credit_stats.applied_rows}/"
        f"{combat_event_movement_credit_stats.total_credit:.3f} "
        f"low_defense={low_defense_reward_stats.hit_penalty_events}/"
        f"{low_defense_reward_stats.block_bonus_events}/"
        f"{low_defense_reward_stats.reward_total:.3f} "
        f"low_def_margin={low_defense_margin_stats.violation_events}/"
        f"{low_defense_margin_stats.sampled_events} "
        f"low_def_margin_loss={low_defense_margin_stats.last_loss:.6f} "
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
        f"training_mode_hp=mode:{args.training_mode_hp_delta_mode} "
        f"sanitized_rows:{build_stats.training_mode_hp_sanitized_rows} "
        f"self_heal_ignored:{build_stats.training_mode_self_heal_ignored} "
        f"opp_heal_ignored:{build_stats.training_mode_opp_heal_ignored}",
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
    if combat_event_validation is not None:
        print(f"DQN diagnostics combat_event={combat_event_validation.summary_line()}", flush=True)
        print(
            "DQN diagnostics "
            f"combat_event_reward=enabled:{int(combat_event_reward_config.enabled)} "
            f"profile:{combat_event_reward_config.profile} "
            f"scale:{combat_event_reward_config.scale:.3f} "
            f"checked:{combat_event_reward_stats.checked_transition_rows} "
            f"matched_rows:{combat_event_reward_stats.matched_transition_rows} "
            f"matched_events:{combat_event_reward_stats.matched_event_rows} "
            f"off_rows:{combat_event_reward_stats.offensive_matched_transition_rows} "
            f"def_rows:{combat_event_reward_stats.defensive_matched_transition_rows} "
            f"adjusted_rows:{combat_event_reward_stats.adjusted_transition_rows} "
            f"applied:{combat_event_reward_stats.applied_event_rewards} "
            f"capped:{combat_event_reward_stats.capped_duplicate_outcome_rows} "
            f"low_conf:{combat_event_reward_stats.skipped_low_confidence_events} "
            f"def_attr:{combat_event_reward_stats.defensive_attribution_rows_seen} "
            f"hp:{combat_event_reward_stats.grouped_hp_delta_sum} "
            f"stun:{combat_event_reward_stats.grouped_stun_delta_sum} "
            f"event_dmg:{combat_event_reward_stats.event_damage_reward_sum:.3f} "
            f"raw_sum:{combat_event_reward_stats.raw_reward_sum:.3f} "
            f"outcomes:{format_float_counts(combat_event_reward_stats.raw_reward_by_outcome, args.diagnostic_top_n)}",
            flush=True,
        )
    if combat_event_unlabeled_movement_filter_config.enabled:
        print(
            "DQN diagnostics "
            f"combat_event_unlabeled_movement_filter="
            f"policy:{combat_event_unlabeled_movement_filter_config.policy} "
            f"keep:{combat_event_unlabeled_movement_filter_config.keep_ratio:.3f} "
            f"checked:{combat_event_unlabeled_movement_filter_stats.checked_rows} "
            f"protected:{combat_event_unlabeled_movement_filter_stats.protected_rows} "
            f"eligible:{combat_event_unlabeled_movement_filter_stats.eligible_rows} "
            f"kept_unlabeled:{combat_event_unlabeled_movement_filter_stats.kept_unlabeled_rows} "
            f"dropped:{combat_event_unlabeled_movement_filter_stats.dropped_rows} "
            f"protected_dropped:{combat_event_unlabeled_movement_filter_stats.protected_dropped_rows} "
            f"drop_actions:{format_counts(combat_event_unlabeled_movement_filter_stats.by_action_dropped, combat_event_unlabeled_movement_filter_stats.dropped_rows, args.diagnostic_top_n)} "
            f"protected_reasons:{format_counts(combat_event_unlabeled_movement_filter_stats.protected_by_reason, combat_event_unlabeled_movement_filter_stats.protected_rows, args.diagnostic_top_n)}",
            flush=True,
        )
    if combat_event_movement_credit_config.enabled:
        print(
            "DQN diagnostics "
            f"combat_event_movement_credit=mode:{combat_event_movement_credit_config.mode} "
            f"window:{combat_event_movement_credit_config.window_decisions} "
            f"max_rows:{combat_event_movement_credit_config.max_rows} "
            f"scale:{combat_event_movement_credit_config.scale:.3f} "
            f"checked:{combat_event_movement_credit_stats.checked_anchor_rows} "
            f"eligible:{combat_event_movement_credit_stats.eligible_anchor_rows} "
            f"applied_anchors:{combat_event_movement_credit_stats.applied_anchor_rows} "
            f"applied_rows:{combat_event_movement_credit_stats.applied_rows} "
            f"credit:{combat_event_movement_credit_stats.total_credit:.3f} "
            f"pos:{combat_event_movement_credit_stats.total_positive_credit:.3f} "
            f"neg:{combat_event_movement_credit_stats.total_negative_credit:.3f} "
            f"by_action:{format_float_counts(combat_event_movement_credit_stats.by_action, args.diagnostic_top_n)} "
            f"by_reason:{format_float_counts(combat_event_movement_credit_stats.by_reason, args.diagnostic_top_n)} "
            f"skip_no_label:{combat_event_movement_credit_stats.skipped_no_label} "
            f"skip_no_candidate:{combat_event_movement_credit_stats.skipped_no_candidate} "
            f"direction_mismatch:{combat_event_movement_credit_stats.skipped_direction_mismatch}",
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
    if combat_event_batch_sampling_config.enabled:
        print(
            "DQN diagnostics "
            f"combat_event_batch_sampling=mode:{combat_event_batch_sampling_diag.mode} "
            f"ratios:{','.join(f'{group}:{combat_event_batch_sampling_diag.ratios.get(group, 0.0):.2f}' for group in COMBAT_EVENT_BATCH_GROUPS)} "
            f"target:{','.join(f'{group}:{combat_event_batch_sampling_diag.target_counts.get(group, 0)}' for group in COMBAT_EVENT_BATCH_GROUPS)} "
            f"pools:{','.join(f'{group}:{combat_event_batch_sampling_diag.pool_counts.get(group, 0)}' for group in COMBAT_EVENT_BATCH_GROUPS)}",
            flush=True,
        )
    print(
        "DQN diagnostics "
        f"projectile_batch=enabled:{int(projectile_batch_config.enabled)} "
        f"sources:{','.join(sorted(projectile_batch_config.eligible_sources)) or 'none'} "
        f"time_to_self:{projectile_batch_config.min_time_to_self}-"
        f"{projectile_batch_config.max_time_to_self} "
        f"ranges:{','.join(format_time_ranges(projectile_batch_config.time_ranges)) or 'none'} "
        f"window:{projectile_batch_config.window_decisions} "
        f"max_self_hp:{projectile_batch_config.max_self_hp} "
        f"include_late_jump_hit:{int(projectile_batch_config.include_late_jump_hit)} "
        f"include_safe_jump:{int(projectile_batch_config.include_safe_jump)} "
        f"safe_t:{projectile_batch_config.safe_jump_min_time_to_self}-"
        f"{projectile_batch_config.safe_jump_max_time_to_self} "
        f"eligible:{projectile_batch_stats.eligible_experiences} "
        f"defensive:{projectile_batch_stats.defensive_experiences} "
        f"late_jump_hit:{projectile_batch_stats.late_jump_hit_experiences} "
        f"safe_jump:{projectile_batch_stats.safe_jump_experiences} "
        f"reason:{format_counts(projectile_batch_stats.by_reason, projectile_batch_stats.eligible_experiences, args.diagnostic_top_n)} "
        f"action:{format_counts(projectile_batch_stats.by_action, projectile_batch_stats.eligible_experiences, args.diagnostic_top_n)} "
        f"time:{format_counts(projectile_batch_stats.by_time_bucket, projectile_batch_stats.eligible_experiences, args.diagnostic_top_n)}",
        flush=True,
    )
    print(
        "DQN diagnostics "
        f"valid_action_mask=mode:{valid_action_mask_config.mode} "
        f"target_states:{valid_action_mask_stats.target_states} "
        f"target_empty:{valid_action_mask_stats.target_empty_masks} "
        f"target_valid_total:{valid_action_mask_stats.target_valid_action_total} "
        f"target_masked_total:{valid_action_mask_stats.target_masked_action_total} "
        f"greedy_rows:{valid_action_mask_stats.greedy_rows} "
        f"greedy_empty:{valid_action_mask_stats.greedy_empty_masks} "
        f"greedy_valid_total:{valid_action_mask_stats.greedy_valid_action_total} "
        f"greedy_masked_total:{valid_action_mask_stats.greedy_masked_action_total} "
        f"target_masked:{format_counts(valid_action_mask_stats.target_masked_actions, valid_action_mask_stats.target_masked_action_total, args.diagnostic_top_n)} "
        f"greedy_masked:{format_counts(valid_action_mask_stats.greedy_masked_actions, valid_action_mask_stats.greedy_masked_action_total, args.diagnostic_top_n)}",
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
        f"unsupported_action_regularization=enabled:{int(unsupported_action_regularization_config.enabled)} "
        f"min_count:{unsupported_action_regularization_config.min_action_count} "
        f"q_ceiling:{unsupported_action_regularization_config.q_ceiling:.6f} "
        f"loss_weight:{unsupported_action_regularization_config.loss_weight:.6f} "
        f"eligible:{unsupported_action_regularization_stats.eligible_action_count} "
        f"zero_sample:{','.join(unsupported_action_regularization_stats.zero_sample_actions) or 'none'} "
        f"low_sample:{','.join(unsupported_action_regularization_stats.low_sample_actions) or 'none'} "
        f"events:{unsupported_action_regularization_stats.regularized_events} "
        f"loss:{unsupported_action_regularization_stats.regularized_loss_total:.6f} "
        f"last:{unsupported_action_regularization_stats.last_loss:.6f} "
        f"avg:{unsupported_action_regularization_stats.avg_loss:.6f} "
        f"by_action=count/loss/mean "
        f"{format_action_scores(unsupported_action_regularization_stats.per_action_events, unsupported_action_regularization_stats.per_action_loss, actions, args.diagnostic_top_n)}",
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
        f"{reward_risk_stats.jump_attack_punished_extra_cost_total:.1f} "
        f"throw_far:{reward_risk_stats.throw_far_cost_events}/{reward_risk_stats.throw_far_cost_total:.1f}",
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
        f"projectile_shape=profile:{reward_projectile_response_config.profile} "
        f"threat_t:{reward_projectile_response_config.threat_min_time_to_self}-"
        f"{reward_projectile_response_config.threat_max_time_to_self} "
        f"threat_dx<={reward_projectile_response_config.threat_max_dx} "
        f"close_dx<={reward_projectile_response_config.close_max_dx} "
        f"threat_rows:{reward_projectile_response_stats.threat_action_rows} "
        f"safe_jump:{reward_projectile_response_stats.safe_jump_bonus_events}/"
        f"{reward_projectile_response_stats.safe_jump_bonus_total:.1f} "
        f"late_jump_hit:{reward_projectile_response_stats.late_jump_hit_cost_events}/"
        f"{reward_projectile_response_stats.late_jump_hit_cost_total:.1f} "
        f"close_back:{reward_projectile_response_stats.close_back_success_bonus_events}/"
        f"{reward_projectile_response_stats.close_back_success_bonus_total:.1f} "
        f"close_guard:{reward_projectile_response_stats.close_guard_success_bonus_events}/"
        f"{reward_projectile_response_stats.close_guard_success_bonus_total:.1f} "
        f"net:{reward_projectile_response_stats.net_adjustment:.1f}",
        flush=True,
    )
    print(
        "DQN diagnostics "
        f"projectile_oversample=enabled:{int(projectile_response_oversample_config.enabled)} "
        f"multipliers:safe_jump={projectile_response_oversample_config.safe_jump},"
        f"late_jump_hit={projectile_response_oversample_config.late_jump_hit},"
        f"close_back={projectile_response_oversample_config.close_back_success},"
        f"close_guard={projectile_response_oversample_config.close_guard_success} "
        f"base:{projectile_response_oversample_stats.base_experiences} "
        f"extra:{projectile_response_oversample_stats.extra_experiences} "
        f"safe_jump:{projectile_response_oversample_stats.safe_jump_base}/"
        f"+{projectile_response_oversample_stats.safe_jump_extra} "
        f"late_jump_hit:{projectile_response_oversample_stats.late_jump_hit_base}/"
        f"+{projectile_response_oversample_stats.late_jump_hit_extra} "
        f"close_back:{projectile_response_oversample_stats.close_back_success_base}/"
        f"+{projectile_response_oversample_stats.close_back_success_extra} "
        f"close_guard:{projectile_response_oversample_stats.close_guard_success_base}/"
        f"+{projectile_response_oversample_stats.close_guard_success_extra} "
        f"by_action_base:{format_counts(projectile_response_oversample_stats.by_action_base, projectile_response_oversample_stats.base_experiences, args.diagnostic_top_n)} "
        f"by_action_extra:{format_counts(projectile_response_oversample_stats.by_action_extra, projectile_response_oversample_stats.extra_experiences, args.diagnostic_top_n)}",
        flush=True,
    )
    print(
        "DQN diagnostics "
        f"projectile_expert_margin=enabled:{int(projectile_expert_margin_config.enabled)} "
        f"requested:{int(projectile_expert_margin_config.requested)} "
        f"margin:{projectile_expert_margin_config.margin:.6f} "
        f"weight:{projectile_expert_margin_config.loss_weight:.6f} "
        f"batch_size:{projectile_expert_margin_config.batch_size} "
        f"require_safe_jump:{int(projectile_expert_margin_config.require_safe_jump)} "
        f"equivalent_jump:{int(projectile_expert_margin_config.equivalent_jump_actions)} "
        f"valid_mask:{projectile_expert_margin_config.valid_action_mask_mode} "
        f"sources:{','.join(sorted(projectile_expert_margin_config.eligible_sources)) or 'none'} "
        f"time_to_self:{projectile_expert_margin_config.min_time_to_self}-"
        f"{projectile_expert_margin_config.max_time_to_self} "
        f"ranges:{','.join(format_time_ranges(projectile_expert_margin_config.time_ranges)) or 'none'} "
        f"eligible:{projectile_expert_margin_stats.eligible_experiences} "
        f"sampled:{projectile_expert_margin_stats.sampled_events} "
        f"violations:{projectile_expert_margin_stats.violation_events} "
        f"empty_valid:{projectile_expert_margin_stats.empty_valid_events} "
        f"expert_invalid:{projectile_expert_margin_stats.expert_invalid_events} "
        f"loss:{projectile_expert_margin_stats.loss_total:.6f} "
        f"last:{projectile_expert_margin_stats.last_loss:.6f} "
        f"avg:{projectile_expert_margin_stats.avg_loss:.6f} "
        f"by_expert:{format_counts(projectile_expert_margin_stats.by_expert_action_events, projectile_expert_margin_stats.sampled_events, args.diagnostic_top_n)} "
        f"sampled_t:{format_counts(projectile_expert_margin_stats.sampled_by_time_bucket, projectile_expert_margin_stats.sampled_events, args.diagnostic_top_n)} "
        f"violation_t:{format_counts(projectile_expert_margin_stats.violation_by_time_bucket, projectile_expert_margin_stats.violation_events, args.diagnostic_top_n)} "
        f"blockers:{format_counts(projectile_expert_margin_stats.blocker_counts, projectile_expert_margin_stats.violation_events, args.diagnostic_top_n)}",
        flush=True,
    )
    print(
        "DQN diagnostics "
        f"projectile_expert_qgap=rows:{projectile_expert_q_gap_diag.rows} "
        f"unique:{projectile_expert_q_gap_diag.unique_rows} "
        f"top1:{projectile_expert_q_gap_diag.top1_matches} "
        f"top5:{projectile_expert_q_gap_diag.top5_matches} "
        f"positive_gap:{projectile_expert_q_gap_diag.positive_gap_rows} "
        f"mean_gap:{projectile_expert_q_gap_diag.mean_gap:.6f} "
        f"mean_positive_gap:{projectile_expert_q_gap_diag.mean_positive_gap:.6f} "
        f"gap_min:{(projectile_expert_q_gap_diag.gap_min if projectile_expert_q_gap_diag.gap_min is not None else 0.0):.6f} "
        f"gap_max:{(projectile_expert_q_gap_diag.gap_max if projectile_expert_q_gap_diag.gap_max is not None else 0.0):.6f} "
        f"mean_rank:{projectile_expert_q_gap_diag.mean_expert_rank:.2f} "
        f"invalid_expert:{projectile_expert_q_gap_diag.invalid_expert_rows} "
        f"empty_valid:{projectile_expert_q_gap_diag.empty_valid_rows} "
        f"by_expert:{format_counts(projectile_expert_q_gap_diag.by_expert_action, projectile_expert_q_gap_diag.rows, args.diagnostic_top_n)} "
        f"rows_t:{format_counts(projectile_expert_q_gap_diag.rows_by_time_bucket, projectile_expert_q_gap_diag.rows, args.diagnostic_top_n)} "
        f"top1_t:{format_counts(projectile_expert_q_gap_diag.top1_by_time_bucket, projectile_expert_q_gap_diag.rows, args.diagnostic_top_n)} "
        f"positive_gap_t:{format_counts(projectile_expert_q_gap_diag.positive_gap_by_time_bucket, projectile_expert_q_gap_diag.positive_gap_rows, args.diagnostic_top_n)} "
        f"top:{format_counts(projectile_expert_q_gap_diag.top_action_counts, projectile_expert_q_gap_diag.rows, args.diagnostic_top_n)} "
        f"blockers:{format_counts(projectile_expert_q_gap_diag.blocker_counts, projectile_expert_q_gap_diag.positive_gap_rows, args.diagnostic_top_n)}",
        flush=True,
    )
    print(
        "DQN diagnostics "
        f"special_expert_margin=enabled:{int(special_expert_margin_config.enabled)} "
        f"requested:{int(special_expert_margin_config.requested)} "
        f"margin:{special_expert_margin_config.margin:.6f} "
        f"weight:{special_expert_margin_config.loss_weight:.6f} "
        f"batch_size:{special_expert_margin_config.batch_size} "
        f"min_reward:{special_expert_margin_config.min_reward:.6f} "
        f"valid_mask:{special_expert_margin_config.valid_action_mask_mode} "
        f"sources:{','.join(sorted(special_expert_margin_config.eligible_sources)) or 'none'} "
        f"eligible:{special_expert_margin_stats.eligible_experiences} "
        f"sampled:{special_expert_margin_stats.sampled_events} "
        f"violations:{special_expert_margin_stats.violation_events} "
        f"empty_valid:{special_expert_margin_stats.empty_valid_events} "
        f"expert_invalid:{special_expert_margin_stats.expert_invalid_events} "
        f"loss:{special_expert_margin_stats.loss_total:.6f} "
        f"last:{special_expert_margin_stats.last_loss:.6f} "
        f"avg:{special_expert_margin_stats.avg_loss:.6f} "
        f"by_expert:{format_counts(special_expert_margin_stats.by_expert_action_events, special_expert_margin_stats.sampled_events, args.diagnostic_top_n)} "
        f"sampled_group:{format_counts(special_expert_margin_stats.sampled_by_time_bucket, special_expert_margin_stats.sampled_events, args.diagnostic_top_n)} "
        f"violation_group:{format_counts(special_expert_margin_stats.violation_by_time_bucket, special_expert_margin_stats.violation_events, args.diagnostic_top_n)} "
        f"blockers:{format_counts(special_expert_margin_stats.blocker_counts, special_expert_margin_stats.violation_events, args.diagnostic_top_n)}",
        flush=True,
    )
    print(
        "DQN diagnostics "
        f"projectile_late_def_margin=enabled:{int(projectile_late_defensive_margin_config.enabled)} "
        f"requested:{int(projectile_late_defensive_margin_config.requested)} "
        f"margin:{projectile_late_defensive_margin_config.margin:.6f} "
        f"weight:{projectile_late_defensive_margin_config.loss_weight:.6f} "
        f"batch_size:{projectile_late_defensive_margin_config.batch_size} "
        f"valid_mask:{projectile_late_defensive_margin_config.valid_action_mask_mode} "
        f"sources:{','.join(sorted(projectile_late_defensive_margin_config.eligible_sources))} "
        f"time_to_self:{projectile_late_defensive_margin_config.min_time_to_self}-"
        f"{projectile_late_defensive_margin_config.max_time_to_self} "
        f"eligible:{projectile_late_defensive_margin_stats.eligible_experiences} "
        f"sampled:{projectile_late_defensive_margin_stats.sampled_events} "
        f"violations:{projectile_late_defensive_margin_stats.violation_events} "
        f"empty_valid:{projectile_late_defensive_margin_stats.empty_valid_events} "
        f"empty_def:{projectile_late_defensive_margin_stats.empty_defensive_events} "
        f"empty_jump:{projectile_late_defensive_margin_stats.empty_jump_events} "
        f"loss:{projectile_late_defensive_margin_stats.loss_total:.6f} "
        f"last:{projectile_late_defensive_margin_stats.last_loss:.6f} "
        f"avg:{projectile_late_defensive_margin_stats.avg_loss:.6f} "
        f"defensive:{format_counts(projectile_late_defensive_margin_stats.defensive_action_events, projectile_late_defensive_margin_stats.violation_events, args.diagnostic_top_n)} "
        f"jump_blockers:{format_counts(projectile_late_defensive_margin_stats.jump_blocker_counts, projectile_late_defensive_margin_stats.violation_events, args.diagnostic_top_n)} "
        f"sampled_t:{format_counts(projectile_late_defensive_margin_stats.sampled_by_time_bucket, projectile_late_defensive_margin_stats.sampled_events, args.diagnostic_top_n)} "
        f"violation_t:{format_counts(projectile_late_defensive_margin_stats.violation_by_time_bucket, projectile_late_defensive_margin_stats.violation_events, args.diagnostic_top_n)}",
        flush=True,
    )
    print(
        "DQN diagnostics "
        f"projectile_defensive_expert_margin=enabled:{int(projectile_defensive_expert_margin_config.enabled)} "
        f"requested:{int(projectile_defensive_expert_margin_config.requested)} "
        f"margin:{projectile_defensive_expert_margin_config.margin:.6f} "
        f"weight:{projectile_defensive_expert_margin_config.loss_weight:.6f} "
        f"batch_size:{projectile_defensive_expert_margin_config.batch_size} "
        f"valid_mask:{projectile_defensive_expert_margin_config.valid_action_mask_mode} "
        f"sources:{','.join(sorted(projectile_defensive_expert_margin_config.eligible_sources))} "
        f"time_to_self:{projectile_defensive_expert_margin_config.min_time_to_self}-"
        f"{projectile_defensive_expert_margin_config.max_time_to_self} "
        f"ranges:{','.join(format_time_ranges(projectile_defensive_expert_margin_config.time_ranges)) or 'none'} "
        f"window:{projectile_defensive_expert_margin_config.window_decisions} "
        f"max_self_hp:{projectile_defensive_expert_margin_config.max_self_hp} "
        f"all_competitors:{int(projectile_defensive_expert_margin_config.all_competitors)} "
        f"eligible:{projectile_defensive_expert_margin_stats.eligible_experiences} "
        f"sampled:{projectile_defensive_expert_margin_stats.sampled_events} "
        f"violations:{projectile_defensive_expert_margin_stats.violation_events} "
        f"empty_valid:{projectile_defensive_expert_margin_stats.empty_valid_events} "
        f"empty_def:{projectile_defensive_expert_margin_stats.empty_defensive_events} "
        f"empty_competitor:{projectile_defensive_expert_margin_stats.empty_competitor_events} "
        f"loss:{projectile_defensive_expert_margin_stats.loss_total:.6f} "
        f"last:{projectile_defensive_expert_margin_stats.last_loss:.6f} "
        f"avg:{projectile_defensive_expert_margin_stats.avg_loss:.6f} "
        f"defensive:{format_counts(projectile_defensive_expert_margin_stats.defensive_action_events, projectile_defensive_expert_margin_stats.violation_events, args.diagnostic_top_n)} "
        f"blockers:{format_counts(projectile_defensive_expert_margin_stats.competitor_blocker_counts, projectile_defensive_expert_margin_stats.violation_events, args.diagnostic_top_n)} "
        f"sampled_t:{format_counts(projectile_defensive_expert_margin_stats.sampled_by_time_bucket, projectile_defensive_expert_margin_stats.sampled_events, args.diagnostic_top_n)} "
        f"violation_t:{format_counts(projectile_defensive_expert_margin_stats.violation_by_time_bucket, projectile_defensive_expert_margin_stats.violation_events, args.diagnostic_top_n)}",
        flush=True,
    )
    print(
        "DQN diagnostics "
        f"projectile_timing_group_margin=enabled:{int(projectile_timing_group_margin_config.enabled)} "
        f"requested:{int(projectile_timing_group_margin_config.requested)} "
        f"margin:{projectile_timing_group_margin_config.margin:.6f} "
        f"weight:{projectile_timing_group_margin_config.loss_weight:.6f} "
        f"batch_size:{projectile_timing_group_margin_config.batch_size} "
        f"valid_mask:{projectile_timing_group_margin_config.valid_action_mask_mode} "
        f"sources:{','.join(sorted(projectile_timing_group_margin_config.eligible_sources)) or 'none'} "
        f"def_t:{','.join(format_time_ranges(projectile_timing_group_margin_config.defense_time_ranges)) or 'none'} "
        f"jump_t:{','.join(format_time_ranges(projectile_timing_group_margin_config.jump_time_ranges)) or 'none'} "
        f"threat_dx<={projectile_timing_group_margin_config.threat_max_dx} "
        f"threat_abs_y<={projectile_timing_group_margin_config.threat_max_abs_y} "
        f"eligible:{projectile_timing_group_margin_stats.eligible_experiences} "
        f"sampled:{projectile_timing_group_margin_stats.sampled_events} "
        f"violations:{projectile_timing_group_margin_stats.violation_events} "
        f"empty_valid:{projectile_timing_group_margin_stats.empty_valid_events} "
        f"empty_target:{projectile_timing_group_margin_stats.empty_target_events} "
        f"empty_competitor:{projectile_timing_group_margin_stats.empty_competitor_events} "
        f"loss:{projectile_timing_group_margin_stats.loss_total:.6f} "
        f"last:{projectile_timing_group_margin_stats.last_loss:.6f} "
        f"avg:{projectile_timing_group_margin_stats.avg_loss:.6f} "
        f"sampled_target:{format_counts(projectile_timing_group_margin_stats.sampled_by_target, projectile_timing_group_margin_stats.sampled_events, args.diagnostic_top_n)} "
        f"violation_target:{format_counts(projectile_timing_group_margin_stats.violation_by_target, projectile_timing_group_margin_stats.violation_events, args.diagnostic_top_n)} "
        f"blockers:{format_counts(projectile_timing_group_margin_stats.blocker_counts, projectile_timing_group_margin_stats.violation_events, args.diagnostic_top_n)} "
        f"sampled_t:{format_counts(projectile_timing_group_margin_stats.sampled_by_time_bucket, projectile_timing_group_margin_stats.sampled_events, args.diagnostic_top_n)} "
        f"violation_t:{format_counts(projectile_timing_group_margin_stats.violation_by_time_bucket, projectile_timing_group_margin_stats.violation_events, args.diagnostic_top_n)}",
        flush=True,
    )
    print(
        "DQN diagnostics "
        f"grounded_normal_defense=enabled:{int(grounded_normal_defense_margin_config.enabled)} "
        f"requested:{int(grounded_normal_defense_margin_config.requested)} "
        f"margin:{grounded_normal_defense_margin_config.margin:.6f} "
        f"weight:{grounded_normal_defense_margin_config.loss_weight:.6f} "
        f"batch_size:{grounded_normal_defense_margin_config.batch_size} "
        f"max_abs_dx<={grounded_normal_defense_margin_config.max_abs_dx} "
        f"sources:{','.join(sorted(grounded_normal_defense_margin_config.eligible_sources)) or 'none'} "
        f"eligible:{grounded_normal_defense_stats.eligible_experiences} "
        f"sampled:{grounded_normal_defense_stats.sampled_events} "
        f"violations:{grounded_normal_defense_stats.violation_events} "
        f"empty_valid:{grounded_normal_defense_stats.empty_valid_events} "
        f"empty_safe:{grounded_normal_defense_stats.empty_safe_events} "
        f"empty_unsafe:{grounded_normal_defense_stats.empty_unsafe_events} "
        f"empty_context:{grounded_normal_defense_stats.empty_context_events} "
        f"loss:{grounded_normal_defense_stats.loss_total:.6f} "
        f"last:{grounded_normal_defense_stats.last_loss:.6f} "
        f"avg:{grounded_normal_defense_stats.avg_loss:.6f} "
        f"safe_top:{format_counts(grounded_normal_defense_stats.safe_top_actions, grounded_normal_defense_stats.violation_events, args.diagnostic_top_n)} "
        f"blockers:{format_counts(grounded_normal_defense_stats.blocker_counts, grounded_normal_defense_stats.violation_events, args.diagnostic_top_n)} "
        f"sampled_t:{format_counts(grounded_normal_defense_stats.sampled_by_time_bucket, grounded_normal_defense_stats.sampled_events, args.diagnostic_top_n)} "
        f"violation_t:{format_counts(grounded_normal_defense_stats.violation_by_time_bucket, grounded_normal_defense_stats.violation_events, args.diagnostic_top_n)}",
        flush=True,
    )
    print(
        "DQN diagnostics "
        f"grounded_normal_defense_bc=enabled:{int(grounded_normal_defense_bc_config.enabled)} "
        f"requested:{int(grounded_normal_defense_bc_config.requested)} "
        f"weight:{grounded_normal_defense_bc_config.loss_weight:.6f} "
        f"max_abs_dx<={grounded_normal_defense_bc_config.max_abs_dx} "
        f"sources:{','.join(sorted(grounded_normal_defense_bc_config.eligible_sources)) or 'none'} "
        f"eligible:{grounded_normal_defense_bc_stats.eligible_experiences} "
        f"sampled:{grounded_normal_defense_bc_stats.sampled_events} "
        f"loss:{grounded_normal_defense_bc_stats.loss_total:.6f} "
        f"last:{grounded_normal_defense_bc_stats.last_loss:.6f} "
        f"avg:{grounded_normal_defense_bc_stats.avg_loss:.6f} "
        f"targets:{format_counts(grounded_normal_defense_bc_stats.target_action_counts, grounded_normal_defense_bc_stats.sampled_events, args.diagnostic_top_n)} "
        f"sampled_t:{format_counts(grounded_normal_defense_bc_stats.sampled_by_time_bucket, grounded_normal_defense_bc_stats.sampled_events, args.diagnostic_top_n)}",
        flush=True,
    )
    print(
        "DQN diagnostics "
        f"low_defense=reward_enabled:{int(low_defense_config.reward_enabled)} "
        f"margin_enabled:{int(low_defense_config.margin_enabled)} "
        f"hit_penalty:{low_defense_config.hit_penalty:.6f} "
        f"block_bonus:{low_defense_config.block_bonus:.6f} "
        f"margin:{low_defense_config.margin:.6f} "
        f"weight:{low_defense_config.loss_weight:.6f} "
        f"batch_size:{low_defense_config.batch_size} "
        f"valid_mask:{low_defense_config.valid_action_mask_mode} "
        f"max_abs_dx<={low_defense_config.max_abs_dx} "
        f"sources:{','.join(sorted(low_defense_config.eligible_sources)) or 'none'} "
        f"checked:{low_defense_reward_stats.checked_rows} "
        f"low_rows:{low_defense_reward_stats.low_event_rows} "
        f"hit_penalty_events:{low_defense_reward_stats.hit_penalty_events} "
        f"no_action_hits:{low_defense_reward_stats.no_action_hit_penalty_events} "
        f"block_bonus_events:{low_defense_reward_stats.block_bonus_events} "
        f"reward:{low_defense_reward_stats.reward_total:.6f} "
        f"source_actions:{format_counts(low_defense_reward_stats.by_source_action, low_defense_reward_stats.low_event_rows, args.diagnostic_top_n)} "
        f"eligible:{low_defense_margin_stats.eligible_experiences} "
        f"sampled:{low_defense_margin_stats.sampled_events} "
        f"violations:{low_defense_margin_stats.violation_events} "
        f"empty_valid:{low_defense_margin_stats.empty_valid_events} "
        f"empty_target:{low_defense_margin_stats.empty_target_events} "
        f"empty_competitor:{low_defense_margin_stats.empty_competitor_events} "
        f"empty_context:{low_defense_margin_stats.empty_context_events} "
        f"loss:{low_defense_margin_stats.loss_total:.6f} "
        f"last:{low_defense_margin_stats.last_loss:.6f} "
        f"avg:{low_defense_margin_stats.avg_loss:.6f} "
        f"blockers:{format_counts(low_defense_margin_stats.blocker_counts, low_defense_margin_stats.violation_events, args.diagnostic_top_n)} "
        f"sampled_t:{format_counts(low_defense_margin_stats.sampled_by_time_bucket, low_defense_margin_stats.sampled_events, args.diagnostic_top_n)} "
        f"violation_t:{format_counts(low_defense_margin_stats.violation_by_time_bucket, low_defense_margin_stats.violation_events, args.diagnostic_top_n)}",
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
