#!/usr/bin/env python3
"""Phase 11 actor-critic / AWAC dataset and artifact foundation.

This is intentionally a small stdlib-only bridge, not a full PPO trainer yet.
It validates paired transition/combat-event logs, derives the same action
labels and DQN feature vectors used by the current trainer, then builds
event-return/advantage targets for the next AWAC/PPO phase.
"""

from __future__ import annotations

import argparse
import collections
import json
import math
import os
import random
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import rl_combat_event_training as combat_events
import rl_probe_server as rl
import train_dqn_learner as dqn


ACTOR_CRITIC_SCHEMA_VERSION = 1
ACTOR_CRITIC_ALGORITHM_VERSION = "offline-awac-bootstrap-v1"
ACTOR_CRITIC_AWAC_ALGORITHM_VERSION = "offline-awac-v1"
AWAC_SAMPLING_MODES = ("uniform", "family-balanced-v1")
DEFAULT_AWAC_FAMILY_RATIOS = (
    "positive-event=0.25,projectile=0.20,normal=0.20,"
    "special=0.15,throw=0.10,movement-defense=0.10"
)


@dataclass(frozen=True)
class ActorCriticReturnConfig:
    reward_profile: str = "event-damage-v1"
    reward_scale: float = 1.0
    gamma: float = 0.95
    horizon: int = 16
    baseline: str = "episode-mean"

    def as_metadata(self) -> dict[str, object]:
        return {
            "reward_profile": self.reward_profile,
            "reward_scale": self.reward_scale,
            "gamma": self.gamma,
            "horizon": self.horizon,
            "baseline": self.baseline,
        }


@dataclass
class ActorCriticSample:
    features: list[float]
    action_index: int
    action_name: str
    run_id: int
    episode_id: int
    decision_id: int
    event_reward: float
    event_return: float = 0.0
    advantage: float = 0.0
    family: str = "other"
    movement_bucket: str = ""
    mask_phase: str = ""
    valid_action_indices: tuple[int, ...] = ()


@dataclass
class ActorCriticDatasetStats:
    transition_rows: int = 0
    labeled_rows: int = 0
    skipped_rows: int = 0
    skipped_reasons: collections.Counter[str] = field(default_factory=collections.Counter)
    action_counts: collections.Counter[str] = field(default_factory=collections.Counter)
    family_counts: collections.Counter[str] = field(default_factory=collections.Counter)
    movement_bucket_counts: collections.Counter[str] = field(default_factory=collections.Counter)
    mask_phase_counts: collections.Counter[str] = field(default_factory=collections.Counter)
    event_reward_rows: int = 0
    positive_reward_rows: int = 0
    negative_reward_rows: int = 0
    neutral_reward_rows: int = 0
    event_reward_sum: float = 0.0
    event_return_sum: float = 0.0
    positive_return_rows: int = 0
    negative_return_rows: int = 0
    neutral_return_rows: int = 0
    advantage_sum: float = 0.0
    positive_advantage_rows: int = 0
    negative_advantage_rows: int = 0
    neutral_advantage_rows: int = 0
    max_return: float = 0.0
    min_return: float = 0.0
    max_advantage: float = 0.0
    min_advantage: float = 0.0
    episodes: int = 0
    target_masked_rows: int = 0

    def as_metadata(self) -> dict[str, object]:
        return {
            "transition_rows": self.transition_rows,
            "labeled_rows": self.labeled_rows,
            "skipped_rows": self.skipped_rows,
            "skipped_reasons": dict(sorted(self.skipped_reasons.items())),
            "action_counts": dict(sorted(self.action_counts.items())),
            "family_counts": dict(sorted(self.family_counts.items())),
            "movement_bucket_counts": dict(sorted(self.movement_bucket_counts.items())),
            "mask_phase_counts": dict(sorted(self.mask_phase_counts.items())),
            "event_reward_rows": self.event_reward_rows,
            "positive_reward_rows": self.positive_reward_rows,
            "negative_reward_rows": self.negative_reward_rows,
            "neutral_reward_rows": self.neutral_reward_rows,
            "event_reward_sum": self.event_reward_sum,
            "event_return_sum": self.event_return_sum,
            "positive_return_rows": self.positive_return_rows,
            "negative_return_rows": self.negative_return_rows,
            "neutral_return_rows": self.neutral_return_rows,
            "advantage_sum": self.advantage_sum,
            "positive_advantage_rows": self.positive_advantage_rows,
            "negative_advantage_rows": self.negative_advantage_rows,
            "neutral_advantage_rows": self.neutral_advantage_rows,
            "max_return": self.max_return,
            "min_return": self.min_return,
            "max_advantage": self.max_advantage,
            "min_advantage": self.min_advantage,
            "episodes": self.episodes,
            "target_masked_rows": self.target_masked_rows,
        }


@dataclass(frozen=True)
class OfflineAwacConfig:
    enabled: bool = False
    steps: int = 1000
    batch_size: int = 128
    actor_learning_rate: float = 0.0005
    value_learning_rate: float = 0.0005
    advantage_temperature: float = 2.0
    advantage_weight_min: float = 0.2
    advantage_weight_max: float = 5.0
    positive_advantage_only: bool = True
    entropy_reg_weight: float = 0.001
    value_loss_weight: float = 1.0
    valid_action_mask: str = "action-start-v1"
    sampling_mode: str = "uniform"
    family_ratios: dict[str, float] = field(default_factory=dict)
    log_interval: int = 200

    def as_metadata(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "steps": self.steps,
            "batch_size": self.batch_size,
            "actor_learning_rate": self.actor_learning_rate,
            "value_learning_rate": self.value_learning_rate,
            "advantage_temperature": self.advantage_temperature,
            "advantage_weight_min": self.advantage_weight_min,
            "advantage_weight_max": self.advantage_weight_max,
            "positive_advantage_only": self.positive_advantage_only,
            "entropy_reg_weight": self.entropy_reg_weight,
            "value_loss_weight": self.value_loss_weight,
            "valid_action_mask": self.valid_action_mask,
            "sampling_mode": self.sampling_mode,
            "family_ratios": dict(sorted(self.family_ratios.items())),
            "log_interval": self.log_interval,
        }


@dataclass
class OfflineAwacStats:
    steps: int = 0
    sampled_rows: int = 0
    target_masked_rows: int = 0
    positive_advantage_samples: int = 0
    nonpositive_advantage_samples: int = 0
    clamped_min_samples: int = 0
    clamped_max_samples: int = 0
    actor_loss_last: float = 0.0
    actor_loss_avg: float = 0.0
    value_loss_last: float = 0.0
    value_loss_avg: float = 0.0
    entropy_bonus_last: float = 0.0
    entropy_bonus_avg: float = 0.0
    advantage_weight_sum: float = 0.0
    pool_sample_counts: collections.Counter[str] = field(default_factory=collections.Counter)
    empty_pool_counts: collections.Counter[str] = field(default_factory=collections.Counter)

    def as_metadata(self) -> dict[str, object]:
        avg_weight = self.advantage_weight_sum / max(1, self.sampled_rows)
        return {
            "steps": self.steps,
            "sampled_rows": self.sampled_rows,
            "target_masked_rows": self.target_masked_rows,
            "positive_advantage_samples": self.positive_advantage_samples,
            "nonpositive_advantage_samples": self.nonpositive_advantage_samples,
            "clamped_min_samples": self.clamped_min_samples,
            "clamped_max_samples": self.clamped_max_samples,
            "actor_loss_last": self.actor_loss_last,
            "actor_loss_avg": self.actor_loss_avg,
            "value_loss_last": self.value_loss_last,
            "value_loss_avg": self.value_loss_avg,
            "entropy_bonus_last": self.entropy_bonus_last,
            "entropy_bonus_avg": self.entropy_bonus_avg,
            "advantage_weight_avg": avg_weight,
            "pool_sample_counts": dict(sorted(self.pool_sample_counts.items())),
            "empty_pool_counts": dict(sorted(self.empty_pool_counts.items())),
        }


@dataclass
class ActorPolicyEvalStats:
    rows: int = 0
    top1_match_rows: int = 0
    top3_match_rows: int = 0
    top_action_counts: collections.Counter[str] = field(default_factory=collections.Counter)
    top_family_counts: collections.Counter[str] = field(default_factory=collections.Counter)
    label_action_counts: collections.Counter[str] = field(default_factory=collections.Counter)
    target_prob_sum: float = 0.0
    entropy_sum: float = 0.0
    value_prediction_sum: float = 0.0

    def as_metadata(self) -> dict[str, object]:
        return {
            "rows": self.rows,
            "top1_match_rows": self.top1_match_rows,
            "top1_match_rate": self.top1_match_rows / max(1, self.rows),
            "top3_match_rows": self.top3_match_rows,
            "top3_match_rate": self.top3_match_rows / max(1, self.rows),
            "top_action_counts": dict(sorted(self.top_action_counts.items())),
            "top_family_counts": dict(sorted(self.top_family_counts.items())),
            "label_action_counts": dict(sorted(self.label_action_counts.items())),
            "target_prob_avg": self.target_prob_sum / max(1, self.rows),
            "entropy_avg": self.entropy_sum / max(1, self.rows),
            "value_prediction_avg": self.value_prediction_sum / max(1, self.rows),
        }


def parse_hidden_sizes(value: str) -> list[int]:
    sizes = [int(item) for item in value.split(",") if item.strip()]
    return [max(1, size) for size in sizes] or [64, 64]


def parse_path_list(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def parse_ratio_map(value: str, flag_name: str) -> dict[str, float]:
    ratios: dict[str, float] = {}
    if not value.strip():
        return ratios
    for raw_item in value.split(","):
        item = raw_item.strip()
        if not item:
            continue
        if "=" not in item:
            raise SystemExit(f"{flag_name}: expected name=value item, got {item!r}")
        name, raw_value = item.split("=", 1)
        key = name.strip()
        if not key:
            raise SystemExit(f"{flag_name}: empty pool name")
        try:
            ratio = float(raw_value)
        except ValueError as exc:
            raise SystemExit(f"{flag_name}: ratio for {key!r} is not numeric") from exc
        if ratio < 0.0:
            raise SystemExit(f"{flag_name}: ratio for {key!r} must be >= 0")
        if ratio > 0.0:
            ratios[key] = ratios.get(key, 0.0) + ratio
    return ratios


def int_field(row: dict[str, object], name: str, default: int = 0) -> int:
    return dqn.int_row_field(row, name, default)


def action_family(action_name: str) -> str:
    if action_name in rl.STAND_NORMAL_ACTION_NAMES or action_name in rl.CROUCH_NORMAL_ACTION_NAMES:
        return "normal"
    if action_name in rl.AIR_NORMAL_ACTION_NAMES:
        return "air-normal"
    if action_name in rl.FIREBALL_ACTION_NAMES:
        return "projectile"
    if action_name in rl.SHORYUKEN_ACTION_NAMES or action_name in rl.TATSU_ACTION_NAMES:
        return "special"
    if action_name == "throw":
        return "throw"
    if action_name in rl.DQN_MOVEMENT_GUARD_ACTIONS or action_name in rl.JUMP_START_ACTION_NAMES:
        return "movement-defense"
    return "other"


def movement_bucket(action_name: str) -> str:
    if action_name == "back":
        return "move-back"
    if action_name == "forward":
        return "move-forward"
    if action_name in ("guard-stand", "guard-crouch"):
        return "move-guard"
    if action_name in rl.JUMP_START_ACTION_NAMES:
        return "move-jump-start"
    return ""


def skip_reason_for_unlabeled_row(row: dict[str, object]) -> str:
    r1 = int_field(row, "obs_self_routine_1")
    if r1 == 1:
        return "contact-reaction"
    if r1 == 4:
        return "attack-unknown"
    return "no-label"


def build_actor_critic_samples(
    rows: list[dict[str, object]],
    actions: tuple[str, ...],
    event_validation: combat_events.CombatEventTrainingValidation,
    config: ActorCriticReturnConfig,
    valid_action_mask: rl.DQNValidActionMaskConfig,
) -> tuple[list[ActorCriticSample], ActorCriticDatasetStats, combat_events.CombatEventRewardStats]:
    stats = ActorCriticDatasetStats(transition_rows=len(rows))
    reward_stats = combat_events.CombatEventRewardStats()
    reward_config = combat_events.CombatEventRewardConfig(
        enabled=True,
        profile=config.reward_profile,
        scale=config.reward_scale,
    )

    # Keep Phase 11 labels exactly aligned with Phase 10 BC labels.
    dqn._BC_SEGMENT_KW_MAP = dqn._derive_segment_kw_map(rows)  # noqa: SLF001 - deliberate shared trainer contract.

    samples: list[ActorCriticSample] = []
    for row in rows:
        label_index = dqn.derive_bc_label(row, actions)
        if label_index is None:
            stats.skipped_rows += 1
            stats.skipped_reasons[skip_reason_for_unlabeled_row(row)] += 1
            continue
        action_name = actions[label_index]
        action_start = dqn.is_action_start(row)
        event_reward = combat_events.reward_adjustment_for_transition(
            event_validation.index,
            row,
            action_name,
            action_start,
            reward_config,
            reward_stats,
        )
        family = action_family(action_name)
        sample_movement_bucket = movement_bucket(action_name)
        mask_phase = rl.dqn_self_mask_phase(row)
        valid_action_indices = rl.dqn_valid_action_indices_for_row(row, actions, valid_action_mask, len(actions))
        if label_index not in valid_action_indices:
            stats.target_masked_rows += 1
            valid_action_indices = tuple(sorted(set(valid_action_indices) | {label_index}))
        samples.append(
            ActorCriticSample(
                features=rl.dqn_feature_vector(row),
                action_index=label_index,
                action_name=action_name,
                run_id=int_field(row, "run_id"),
                episode_id=int_field(row, "episode_id"),
                decision_id=int_field(row, "decision_id"),
                event_reward=event_reward,
                family=family,
                movement_bucket=sample_movement_bucket,
                mask_phase=mask_phase,
                valid_action_indices=valid_action_indices,
            )
        )
        stats.labeled_rows += 1
        stats.action_counts[action_name] += 1
        stats.family_counts[family] += 1
        if sample_movement_bucket:
            stats.movement_bucket_counts[sample_movement_bucket] += 1
        stats.mask_phase_counts[mask_phase] += 1
        if event_reward != 0.0:
            stats.event_reward_rows += 1
        if event_reward > 0.0:
            stats.positive_reward_rows += 1
        elif event_reward < 0.0:
            stats.negative_reward_rows += 1
        else:
            stats.neutral_reward_rows += 1
        stats.event_reward_sum += event_reward

    apply_event_returns(samples, config, stats)
    return samples, stats, reward_stats


def apply_event_returns(
    samples: list[ActorCriticSample],
    config: ActorCriticReturnConfig,
    stats: ActorCriticDatasetStats,
) -> None:
    if not samples:
        return

    indices_by_episode: dict[tuple[int, int], list[int]] = collections.defaultdict(list)
    for index, sample in enumerate(samples):
        indices_by_episode[(sample.run_id, sample.episode_id)].append(index)
    stats.episodes = len(indices_by_episode)

    returns = [0.0 for _ in samples]
    for indices in indices_by_episode.values():
        for local_index, sample_index in enumerate(indices):
            value = 0.0
            discount = 1.0
            end_index = min(len(indices), local_index + config.horizon + 1)
            for future_local_index in range(local_index, end_index):
                value += discount * samples[indices[future_local_index]].event_reward
                discount *= config.gamma
            returns[sample_index] = value
            samples[sample_index].event_return = value

    if config.baseline == "zero":
        baselines = [0.0 for _ in samples]
    elif config.baseline == "mean":
        mean_return = sum(returns) / max(1, len(returns))
        baselines = [mean_return for _ in samples]
    else:
        baselines = [0.0 for _ in samples]
        for indices in indices_by_episode.values():
            episode_mean = sum(returns[index] for index in indices) / max(1, len(indices))
            for index in indices:
                baselines[index] = episode_mean

    stats.event_return_sum = sum(returns)
    stats.max_return = max(returns)
    stats.min_return = min(returns)
    for sample, event_return, baseline in zip(samples, returns, baselines):
        advantage = event_return - baseline
        sample.advantage = advantage
        stats.advantage_sum += advantage
        if event_return > 0.0:
            stats.positive_return_rows += 1
        elif event_return < 0.0:
            stats.negative_return_rows += 1
        else:
            stats.neutral_return_rows += 1
        if advantage > 0.0:
            stats.positive_advantage_rows += 1
        elif advantage < 0.0:
            stats.negative_advantage_rows += 1
        else:
            stats.neutral_advantage_rows += 1
    stats.max_advantage = max(sample.advantage for sample in samples)
    stats.min_advantage = min(sample.advantage for sample in samples)


def awac_sample_weight(sample: ActorCriticSample, config: OfflineAwacConfig, stats: OfflineAwacStats) -> float:
    advantage = sample.advantage
    if advantage > 0.0:
        stats.positive_advantage_samples += 1
    else:
        stats.nonpositive_advantage_samples += 1
        if config.positive_advantage_only:
            advantage = 0.0
    raw_weight = math.exp(max(-20.0, min(20.0, advantage / max(1e-6, config.advantage_temperature))))
    weight = max(config.advantage_weight_min, min(config.advantage_weight_max, raw_weight))
    if weight <= config.advantage_weight_min and raw_weight < config.advantage_weight_min:
        stats.clamped_min_samples += 1
    if weight >= config.advantage_weight_max and raw_weight > config.advantage_weight_max:
        stats.clamped_max_samples += 1
    stats.advantage_weight_sum += weight
    return weight


def masked_policy_grad(
    logits: list[float],
    sample: ActorCriticSample,
    weight: float,
) -> tuple[float, list[float]]:
    if not logits:
        return 0.0, []
    valid_indices = tuple(index for index in sample.valid_action_indices if 0 <= index < len(logits))
    if sample.action_index not in valid_indices:
        valid_indices = tuple(sorted(set(valid_indices) | {sample.action_index}))
    if not valid_indices:
        valid_indices = tuple(range(len(logits)))
    max_logit = max(logits[index] for index in valid_indices)
    exp_values = {index: math.exp(logits[index] - max_logit) for index in valid_indices}
    sum_exp = sum(exp_values.values())
    probs = {index: value / max(sum_exp, 1e-15) for index, value in exp_values.items()}
    target_prob = max(probs.get(sample.action_index, 0.0), 1e-15)
    loss = -math.log(target_prob) * weight
    output_grad = [0.0 for _ in logits]
    for index, prob in probs.items():
        output_grad[index] = prob * weight
    if 0 <= sample.action_index < len(output_grad):
        output_grad[sample.action_index] -= weight
    return loss, output_grad


def masked_entropy_grad(logits: list[float], valid_indices: tuple[int, ...], weight: float) -> tuple[float, float, list[float]]:
    if weight <= 0.0 or not logits:
        return 0.0, 0.0, [0.0 for _ in logits]
    indices = tuple(index for index in valid_indices if 0 <= index < len(logits)) or tuple(range(len(logits)))
    max_logit = max(logits[index] for index in indices)
    exp_values = {index: math.exp(logits[index] - max_logit) for index in indices}
    sum_exp = sum(exp_values.values())
    if sum_exp <= 0.0:
        return 0.0, 0.0, [0.0 for _ in logits]
    probs = {index: value / sum_exp for index, value in exp_values.items()}
    entropy = -sum(prob * math.log(max(prob, 1e-15)) for prob in probs.values())
    grad = [0.0 for _ in logits]
    for index, prob in probs.items():
        grad[index] = weight * prob * (math.log(max(prob, 1e-15)) + entropy)
    bonus = weight * entropy
    return -bonus, bonus, grad


def build_awac_sample_pools(samples: list[ActorCriticSample]) -> dict[str, list[ActorCriticSample]]:
    pools: dict[str, list[ActorCriticSample]] = collections.defaultdict(list)
    for sample in samples:
        pools["all"].append(sample)
        pools[sample.family].append(sample)
        pools[f"action-{sample.action_name}"].append(sample)
        if sample.movement_bucket:
            pools[sample.movement_bucket].append(sample)
        if sample.mask_phase:
            pools[f"phase-{sample.mask_phase}"].append(sample)
        if sample.event_reward > 0.0:
            pools["positive-event"].append(sample)
            if sample.movement_bucket != "move-back":
                pools["positive-event-nonback"].append(sample)
            if sample.family != "movement-defense":
                pools["positive-event-nonmovement"].append(sample)
        elif sample.event_reward < 0.0:
            pools["negative-event"].append(sample)
            if sample.movement_bucket == "move-back":
                pools["negative-event-back"].append(sample)
        if sample.advantage > 0.0:
            pools["positive-advantage"].append(sample)
            if sample.movement_bucket != "move-back":
                pools["positive-advantage-nonback"].append(sample)
        elif sample.advantage < 0.0:
            pools["negative-advantage"].append(sample)
    return pools


def balanced_pool_counts(
    batch_size: int,
    ratios: dict[str, float],
    pools: dict[str, list[ActorCriticSample]],
    stats: OfflineAwacStats,
) -> dict[str, int]:
    available: list[tuple[str, float]] = []
    for name, ratio in sorted(ratios.items()):
        if ratio <= 0.0:
            continue
        if not pools.get(name):
            stats.empty_pool_counts[name] += 1
            continue
        available.append((name, ratio))
    if not available:
        return {"all": batch_size}
    total_ratio = sum(ratio for _name, ratio in available)
    if total_ratio <= 0.0:
        return {"all": batch_size}

    counts: dict[str, int] = {}
    fractions: list[tuple[float, str]] = []
    assigned = 0
    for name, ratio in available:
        raw_count = batch_size * ratio / total_ratio
        count = int(math.floor(raw_count))
        counts[name] = count
        assigned += count
        fractions.append((raw_count - count, name))
    for _fraction, name in sorted(fractions, reverse=True)[: max(0, batch_size - assigned)]:
        counts[name] += 1
    return {name: count for name, count in counts.items() if count > 0}


def sample_awac_batch(
    samples: list[ActorCriticSample],
    pools: dict[str, list[ActorCriticSample]],
    rng: random.Random,
    config: OfflineAwacConfig,
    stats: OfflineAwacStats,
) -> list[ActorCriticSample]:
    batch_size = min(config.batch_size, len(samples))
    if config.sampling_mode == "uniform":
        stats.pool_sample_counts["uniform"] += batch_size
        return rng.choices(samples, k=batch_size)
    if config.sampling_mode != "family-balanced-v1":
        stats.pool_sample_counts["uniform-fallback"] += batch_size
        return rng.choices(samples, k=batch_size)

    batch: list[ActorCriticSample] = []
    counts = balanced_pool_counts(batch_size, config.family_ratios, pools, stats)
    for pool_name, count in counts.items():
        pool = pools.get(pool_name) or samples
        batch.extend(rng.choices(pool, k=count))
        stats.pool_sample_counts[pool_name] += count
    if len(batch) < batch_size:
        fill_count = batch_size - len(batch)
        batch.extend(rng.choices(samples, k=fill_count))
        stats.pool_sample_counts["fill"] += fill_count
    if len(batch) > batch_size:
        batch = batch[:batch_size]
    rng.shuffle(batch)
    return batch


def train_offline_awac(
    samples: list[ActorCriticSample],
    actions: tuple[str, ...],
    hidden_sizes: list[int],
    seed: int,
    config: OfflineAwacConfig,
) -> tuple[list[dict[str, object]], list[dict[str, object]], OfflineAwacStats]:
    if not samples:
        raise SystemExit("offline AWAC training: no labeled samples found")
    rng = random.Random(seed)
    input_dim = len(rl.DQN_FEATURE_NAMES)
    actor_layers = dqn.init_network(input_dim, hidden_sizes, len(actions), rng)
    value_layers = dqn.init_network(input_dim, hidden_sizes, 1, rng)
    actor_grads = dqn.zero_grads(actor_layers)
    value_grads = dqn.zero_grads(value_layers)
    stats = OfflineAwacStats()
    pools = build_awac_sample_pools(samples)

    for step in range(1, config.steps + 1):
        batch = sample_awac_batch(samples, pools, rng, config, stats)
        actor_loss = 0.0
        value_loss = 0.0
        entropy_bonus_total = 0.0
        for sample in batch:
            weight = awac_sample_weight(sample, config, stats)
            logits, actor_activations, actor_pre_activations = dqn.forward(actor_layers, sample.features)
            policy_loss, actor_output_grad = masked_policy_grad(logits, sample, weight)
            entropy_loss, entropy_bonus, entropy_output_grad = masked_entropy_grad(
                logits,
                sample.valid_action_indices,
                config.entropy_reg_weight,
            )
            for index, grad_value in enumerate(entropy_output_grad):
                actor_output_grad[index] += grad_value
            dqn.add_backward_grads(actor_layers, actor_grads, actor_activations, actor_pre_activations, actor_output_grad)
            actor_loss += policy_loss + entropy_loss
            entropy_bonus_total += entropy_bonus

            value_values, value_activations, value_pre_activations = dqn.forward(value_layers, sample.features)
            prediction = float(value_values[0]) if value_values else 0.0
            error = prediction - sample.event_return
            value_loss += 0.5 * config.value_loss_weight * error * error
            dqn.add_backward_grads(
                value_layers,
                value_grads,
                value_activations,
                value_pre_activations,
                [config.value_loss_weight * error],
            )
            stats.sampled_rows += 1
            if sample.action_index not in sample.valid_action_indices:
                stats.target_masked_rows += 1

        batch_size = max(1, len(batch))
        dqn.apply_grads(actor_layers, actor_grads, config.actor_learning_rate, batch_size)
        dqn.apply_grads(value_layers, value_grads, config.value_learning_rate, batch_size)
        actor_grads = dqn.zero_grads(actor_layers)
        value_grads = dqn.zero_grads(value_layers)

        stats.steps = step
        stats.actor_loss_last = actor_loss / batch_size
        stats.value_loss_last = value_loss / batch_size
        stats.entropy_bonus_last = entropy_bonus_total / batch_size
        stats.actor_loss_avg = (
            stats.actor_loss_last if step == 1 else 0.98 * stats.actor_loss_avg + 0.02 * stats.actor_loss_last
        )
        stats.value_loss_avg = (
            stats.value_loss_last if step == 1 else 0.98 * stats.value_loss_avg + 0.02 * stats.value_loss_last
        )
        stats.entropy_bonus_avg = (
            stats.entropy_bonus_last
            if step == 1
            else 0.98 * stats.entropy_bonus_avg + 0.02 * stats.entropy_bonus_last
        )
        if config.log_interval > 0 and (step == 1 or step % config.log_interval == 0 or step == config.steps):
            print(
                "Actor-Critic 11C "
                f"step={step} "
                f"actor_loss={stats.actor_loss_last:.6f} "
                f"actor_avg={stats.actor_loss_avg:.6f} "
                f"value_loss={stats.value_loss_last:.6f} "
                f"value_avg={stats.value_loss_avg:.6f} "
                f"entropy={stats.entropy_bonus_last:.6f}",
                flush=True,
            )

    return actor_layers, value_layers, stats


def masked_policy_probs(
    logits: list[float],
    valid_indices: tuple[int, ...],
) -> dict[int, float]:
    if not logits:
        return {}
    indices = tuple(index for index in valid_indices if 0 <= index < len(logits)) or tuple(range(len(logits)))
    max_logit = max(logits[index] for index in indices)
    exp_values = {index: math.exp(logits[index] - max_logit) for index in indices}
    sum_exp = sum(exp_values.values())
    if sum_exp <= 0.0:
        uniform = 1.0 / max(1, len(indices))
        return {index: uniform for index in indices}
    return {index: value / sum_exp for index, value in exp_values.items()}


def evaluate_actor_policy(
    actor_layers: list[dict[str, object]],
    value_layers: list[dict[str, object]],
    samples: list[ActorCriticSample],
    actions: tuple[str, ...],
    limit: int,
) -> ActorPolicyEvalStats:
    stats = ActorPolicyEvalStats()
    for sample in samples[: max(0, limit)]:
        logits, _, _ = dqn.forward(actor_layers, sample.features)
        probs = masked_policy_probs(logits, sample.valid_action_indices)
        if not probs:
            continue
        ranked_indices = sorted(probs, key=lambda index: (probs[index], actions[index]), reverse=True)
        top_index = ranked_indices[0]
        top_action = actions[top_index]
        value_prediction, _, _ = dqn.forward(value_layers, sample.features)
        stats.rows += 1
        stats.top_action_counts[top_action] += 1
        stats.top_family_counts[action_family(top_action)] += 1
        stats.label_action_counts[sample.action_name] += 1
        stats.target_prob_sum += probs.get(sample.action_index, 0.0)
        stats.entropy_sum += -sum(prob * math.log(max(prob, 1e-15)) for prob in probs.values())
        stats.value_prediction_sum += float(value_prediction[0]) if value_prediction else 0.0
        if top_index == sample.action_index:
            stats.top1_match_rows += 1
        if sample.action_index in ranked_indices[:3]:
            stats.top3_match_rows += 1
    return stats


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


def publish_actor_critic_artifact(
    model_dir: str,
    version: int,
    actions: tuple[str, ...],
    fallback_policy: str,
    metadata: dict[str, object],
    updated_rows: int,
    actor_layers: list[dict[str, object]],
    value_layers: list[dict[str, object]],
    algorithm_version: str,
) -> None:
    os.makedirs(model_dir, exist_ok=True)
    payload = {
        "version": version,
        "policy": "actor-critic",
        "source": "offline-actor-critic",
        "action_set_version": rl.ACTION_SET_VERSION,
        "created_at_unix": time.time(),
        "metadata": metadata,
        "actions": list(actions),
        "fallback_policy": fallback_policy,
        "actor_critic": {
            "schema_version": ACTOR_CRITIC_SCHEMA_VERSION,
            "algorithm_version": algorithm_version,
            "architecture": "independent-mlp-v1",
            "feature_names": list(rl.DQN_FEATURE_NAMES),
            "feature_scales": dict(rl.DQN_FEATURE_SCALES),
            "actor_layers": actor_layers,
            "value_layers": value_layers,
        },
        "updated_rows": updated_rows,
    }
    for path in (Path(model_dir) / f"actor-critic-v{version}.json", Path(model_dir) / "current.json"):
        fd, temp_path = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=model_dir)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(payload, stream, sort_keys=True)
                stream.write("\n")
            rl.replace_with_retries(temp_path, str(path))
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)


def write_summary(path_text: str, metadata: dict[str, object]) -> None:
    path = Path(path_text)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(metadata, stream, sort_keys=True, indent=2)
            stream.write("\n")
        rl.replace_with_retries(temp_path, str(path))
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def top_counts(counter: collections.Counter[str], limit: int) -> str:
    if not counter:
        return "none"
    total = sum(counter.values())
    parts = []
    for key, value in counter.most_common(max(1, limit)):
        pct = (100.0 * value / total) if total else 0.0
        parts.append(f"{key}={value}/{pct:.1f}%")
    return ", ".join(parts)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transitions", required=True, help="Comma-separated transition NDJSON logs")
    parser.add_argument("--combat-event-logs", required=True, help="Comma-separated combat event NDJSON logs")
    parser.add_argument("--output-dir", default="", help="Optional actor-critic artifact output directory")
    parser.add_argument("--summary-path", default="", help="Optional dataset summary JSON path")
    parser.add_argument(
        "--training-mode",
        default="validate",
        choices=("validate", "offline-awac"),
        help="validate builds 11B diagnostics; offline-awac also trains actor/value heads.",
    )
    parser.add_argument("--actions", default="", help="Optional comma-separated action subset")
    parser.add_argument("--hidden-sizes", default="64,64", help="Actor/value MLP hidden sizes")
    parser.add_argument("--limit", type=int, default=0, help="Maximum transition rows to read")
    parser.add_argument("--version", type=int, default=None, help="Optional model version override")
    parser.add_argument("--seed", type=int, default=7, help="Random seed for initial artifact weights")
    parser.add_argument("--fallback-policy", default="hp", help="Runtime fallback policy metadata")
    parser.add_argument(
        "--reward-profile",
        default="event-damage-v1",
        choices=combat_events.COMBAT_EVENT_REWARD_PROFILES,
        help="Combat event reward profile used to build actor-critic returns",
    )
    parser.add_argument("--reward-scale", type=float, default=1.0, help="Combat event reward scale")
    parser.add_argument("--return-gamma", type=float, default=0.95, help="Discount factor for event returns")
    parser.add_argument("--return-horizon", type=int, default=16, help="Labeled-sample horizon for event returns")
    parser.add_argument(
        "--return-baseline",
        default="episode-mean",
        choices=("zero", "mean", "episode-mean"),
        help="Baseline subtracted from event returns to produce advantages",
    )
    parser.add_argument(
        "--valid-action-mask",
        default="action-start-v1",
        choices=rl.DQN_VALID_ACTION_MASK_MODES,
        help="Valid-action mask used by the AWAC actor softmax.",
    )
    parser.add_argument("--awac-steps", type=int, default=1000, help="Offline AWAC update steps")
    parser.add_argument("--awac-batch-size", type=int, default=128, help="Offline AWAC batch size")
    parser.add_argument("--awac-actor-lr", type=float, default=0.0005, help="Actor learning rate")
    parser.add_argument("--awac-value-lr", type=float, default=0.0005, help="Value learning rate")
    parser.add_argument("--awac-advantage-temperature", type=float, default=2.0, help="AWAC advantage temperature")
    parser.add_argument("--awac-weight-min", type=float, default=0.2, help="Minimum AWAC advantage weight")
    parser.add_argument("--awac-weight-max", type=float, default=5.0, help="Maximum AWAC advantage weight")
    parser.add_argument(
        "--awac-use-negative-advantages",
        action="store_true",
        help="Let negative advantages downweight actions instead of treating them as neutral imitation weight.",
    )
    parser.add_argument("--awac-entropy", type=float, default=0.001, help="Masked policy entropy regularization")
    parser.add_argument("--awac-value-loss-weight", type=float, default=1.0, help="Value regression loss weight")
    parser.add_argument(
        "--awac-sampling",
        default="uniform",
        choices=AWAC_SAMPLING_MODES,
        help="Offline AWAC batch sampler. family-balanced-v1 samples from configured action/event pools.",
    )
    parser.add_argument(
        "--awac-family-ratios",
        default=DEFAULT_AWAC_FAMILY_RATIOS,
        help=(
            "Comma-separated pool ratios for --awac-sampling family-balanced-v1. "
            "Pools include movement-defense, projectile, normal, special, throw, "
            "air-normal, move-back, move-forward, move-guard, move-jump-start, "
            "phase-<mask-phase>, action-<action-name>, positive-event, "
            "positive-event-nonback, positive-event-nonmovement, negative-event, "
            "positive-advantage, positive-advantage-nonback, negative-advantage."
        ),
    )
    parser.add_argument("--awac-log-interval", type=int, default=200, help="Offline AWAC progress print interval")
    parser.add_argument("--eval-limit", type=int, default=5000, help="Samples used for local actor policy diagnostics")
    parser.add_argument(
        "--allow-validation-errors",
        action="store_true",
        help="Build diagnostics even when paired combat-event validation reports errors",
    )
    parser.add_argument("--diagnostic-top-n", type=int, default=10)
    args = parser.parse_args()

    transition_paths = parse_path_list(args.transitions)
    event_paths = parse_path_list(args.combat_event_logs)
    if not transition_paths:
        raise SystemExit("--transitions did not include any paths")
    if not event_paths:
        raise SystemExit("--combat-event-logs did not include any paths")

    actions = dqn.parse_action_subset(args.actions)
    hidden_sizes = parse_hidden_sizes(args.hidden_sizes)
    rows = dqn.read_transition_rows(transition_paths, max(0, int(args.limit)))
    validation = combat_events.validate_combat_event_training_logs(
        event_paths,
        transition_paths,
        rows,
        mode="actor-critic-validate",
    )
    if validation.fatal_errors and not args.allow_validation_errors:
        for error in validation.fatal_errors:
            print(f"Actor-Critic validation error: {error}", flush=True)
        raise SystemExit(2)

    return_config = ActorCriticReturnConfig(
        reward_profile=str(args.reward_profile),
        reward_scale=max(0.0, float(args.reward_scale)),
        gamma=max(0.0, min(1.0, float(args.return_gamma))),
        horizon=max(0, int(args.return_horizon)),
        baseline=str(args.return_baseline),
    )
    valid_action_mask = rl.DQNValidActionMaskConfig(str(args.valid_action_mask))
    samples, dataset_stats, reward_stats = build_actor_critic_samples(
        rows,
        actions,
        validation,
        return_config,
        valid_action_mask,
    )
    awac_config = OfflineAwacConfig(
        enabled=str(args.training_mode) == "offline-awac",
        steps=max(0, int(args.awac_steps)),
        batch_size=max(1, int(args.awac_batch_size)),
        actor_learning_rate=max(0.0, float(args.awac_actor_lr)),
        value_learning_rate=max(0.0, float(args.awac_value_lr)),
        advantage_temperature=max(1e-6, float(args.awac_advantage_temperature)),
        advantage_weight_min=max(0.0, float(args.awac_weight_min)),
        advantage_weight_max=max(float(args.awac_weight_min), float(args.awac_weight_max)),
        positive_advantage_only=not bool(args.awac_use_negative_advantages),
        entropy_reg_weight=max(0.0, float(args.awac_entropy)),
        value_loss_weight=max(0.0, float(args.awac_value_loss_weight)),
        valid_action_mask=str(args.valid_action_mask),
        sampling_mode=str(args.awac_sampling),
        family_ratios=parse_ratio_map(str(args.awac_family_ratios), "--awac-family-ratios"),
        log_interval=max(0, int(args.awac_log_interval)),
    )
    if awac_config.enabled:
        actor_layers, value_layers, awac_stats = train_offline_awac(
            samples,
            actions,
            hidden_sizes,
            int(args.seed),
            awac_config,
        )
        algorithm_version = ACTOR_CRITIC_AWAC_ALGORITHM_VERSION
    else:
        rng = random.Random(int(args.seed))
        actor_layers = dqn.init_network(len(rl.DQN_FEATURE_NAMES), hidden_sizes, len(actions), rng)
        value_layers = dqn.init_network(len(rl.DQN_FEATURE_NAMES), hidden_sizes, 1, rng)
        awac_stats = OfflineAwacStats()
        algorithm_version = ACTOR_CRITIC_ALGORITHM_VERSION
    actor_eval_stats = evaluate_actor_policy(
        actor_layers,
        value_layers,
        samples,
        actions,
        max(0, int(args.eval_limit)),
    )
    metadata: dict[str, Any] = {
        "phase": "11C" if awac_config.enabled else "11A/11B",
        "actor_critic_schema_version": ACTOR_CRITIC_SCHEMA_VERSION,
        "algorithm_version": algorithm_version,
        "training_mode": str(args.training_mode),
        "return_config": return_config.as_metadata(),
        "awac_config": awac_config.as_metadata(),
        "awac_stats": awac_stats.as_metadata(),
        "transition_paths": transition_paths,
        "combat_event_paths": event_paths,
        "combat_event_training": validation.as_metadata(),
        "combat_event_reward_stats": reward_stats.as_metadata(),
        "dataset_stats": dataset_stats.as_metadata(),
        "actor_eval_stats": actor_eval_stats.as_metadata(),
        "hidden_sizes": hidden_sizes,
    }

    if args.summary_path:
        write_summary(str(args.summary_path), metadata)
    if args.output_dir:
        version = next_model_version(str(args.output_dir), args.version)
        publish_actor_critic_artifact(
            str(args.output_dir),
            version,
            actions,
            str(args.fallback_policy),
            metadata,
            len(samples),
            actor_layers,
            value_layers,
            algorithm_version,
        )
        metadata["published_model_dir"] = str(args.output_dir)
        metadata["published_version"] = version

    print(
        f"Actor-Critic {'11C' if awac_config.enabled else '11B'} "
        f"transitions={dataset_stats.transition_rows} "
        f"labeled={dataset_stats.labeled_rows} "
        f"skipped={dataset_stats.skipped_rows} "
        f"event_reward_rows={dataset_stats.event_reward_rows} "
        f"reward_sum={dataset_stats.event_reward_sum:.6f} "
        f"return_sum={dataset_stats.event_return_sum:.6f} "
        f"adv_pos/neg/zero={dataset_stats.positive_advantage_rows}/"
        f"{dataset_stats.negative_advantage_rows}/{dataset_stats.neutral_advantage_rows} "
        f"validation_errors={len(validation.fatal_errors)}",
        flush=True,
    )
    print(
        f"Actor-Critic {'11C' if awac_config.enabled else '11B'} "
        f"families={top_counts(dataset_stats.family_counts, int(args.diagnostic_top_n))} "
        f"actions={top_counts(dataset_stats.action_counts, int(args.diagnostic_top_n))}",
        flush=True,
    )
    print(
        f"Actor-Critic {'11C' if awac_config.enabled else '11B'} "
        f"eval_rows={actor_eval_stats.rows} "
        f"top1_match={actor_eval_stats.top1_match_rows}/{actor_eval_stats.rows} "
        f"top3_match={actor_eval_stats.top3_match_rows}/{actor_eval_stats.rows} "
        f"target_prob={actor_eval_stats.as_metadata()['target_prob_avg']:.6f} "
        f"entropy={actor_eval_stats.as_metadata()['entropy_avg']:.6f} "
        f"top_families={top_counts(actor_eval_stats.top_family_counts, int(args.diagnostic_top_n))} "
        f"top_actions={top_counts(actor_eval_stats.top_action_counts, int(args.diagnostic_top_n))}",
        flush=True,
    )
    if awac_config.enabled:
        print(
            "Actor-Critic 11C "
            f"awac_steps={awac_stats.steps} "
            f"actor_loss_avg={awac_stats.actor_loss_avg:.6f} "
            f"value_loss_avg={awac_stats.value_loss_avg:.6f} "
            f"entropy_avg={awac_stats.entropy_bonus_avg:.6f} "
            f"adv_weight_avg={awac_stats.as_metadata()['advantage_weight_avg']:.6f} "
            f"pools={top_counts(awac_stats.pool_sample_counts, int(args.diagnostic_top_n))}",
            flush=True,
        )


if __name__ == "__main__":
    main()
