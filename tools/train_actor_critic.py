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


@dataclass
class ActorCriticDatasetStats:
    transition_rows: int = 0
    labeled_rows: int = 0
    skipped_rows: int = 0
    skipped_reasons: collections.Counter[str] = field(default_factory=collections.Counter)
    action_counts: collections.Counter[str] = field(default_factory=collections.Counter)
    family_counts: collections.Counter[str] = field(default_factory=collections.Counter)
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

    def as_metadata(self) -> dict[str, object]:
        return {
            "transition_rows": self.transition_rows,
            "labeled_rows": self.labeled_rows,
            "skipped_rows": self.skipped_rows,
            "skipped_reasons": dict(sorted(self.skipped_reasons.items())),
            "action_counts": dict(sorted(self.action_counts.items())),
            "family_counts": dict(sorted(self.family_counts.items())),
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
        }


def parse_hidden_sizes(value: str) -> list[int]:
    sizes = [int(item) for item in value.split(",") if item.strip()]
    return [max(1, size) for size in sizes] or [64, 64]


def parse_path_list(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


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
            )
        )
        stats.labeled_rows += 1
        stats.action_counts[action_name] += 1
        stats.family_counts[family] += 1
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
    hidden_sizes: list[int],
    fallback_policy: str,
    metadata: dict[str, object],
    seed: int,
    updated_rows: int,
) -> None:
    os.makedirs(model_dir, exist_ok=True)
    rng = random.Random(seed)
    input_dim = len(rl.DQN_FEATURE_NAMES)
    actor_layers = dqn.init_network(input_dim, hidden_sizes, len(actions), rng)
    value_layers = dqn.init_network(input_dim, hidden_sizes, 1, rng)
    payload = {
        "version": version,
        "policy": "actor-critic",
        "source": "offline-actor-critic-bootstrap",
        "action_set_version": rl.ACTION_SET_VERSION,
        "created_at_unix": time.time(),
        "metadata": metadata,
        "actions": list(actions),
        "fallback_policy": fallback_policy,
        "actor_critic": {
            "schema_version": ACTOR_CRITIC_SCHEMA_VERSION,
            "algorithm_version": ACTOR_CRITIC_ALGORITHM_VERSION,
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
    samples, dataset_stats, reward_stats = build_actor_critic_samples(rows, actions, validation, return_config)
    metadata: dict[str, Any] = {
        "phase": "11A/11B",
        "actor_critic_schema_version": ACTOR_CRITIC_SCHEMA_VERSION,
        "algorithm_version": ACTOR_CRITIC_ALGORITHM_VERSION,
        "return_config": return_config.as_metadata(),
        "transition_paths": transition_paths,
        "combat_event_paths": event_paths,
        "combat_event_training": validation.as_metadata(),
        "combat_event_reward_stats": reward_stats.as_metadata(),
        "dataset_stats": dataset_stats.as_metadata(),
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
            hidden_sizes,
            str(args.fallback_policy),
            metadata,
            int(args.seed),
            len(samples),
        )
        metadata["published_model_dir"] = str(args.output_dir)
        metadata["published_version"] = version

    print(
        "Actor-Critic 11B "
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
        "Actor-Critic 11B "
        f"families={top_counts(dataset_stats.family_counts, int(args.diagnostic_top_n))} "
        f"actions={top_counts(dataset_stats.action_counts, int(args.diagnostic_top_n))}",
        flush=True,
    )


if __name__ == "__main__":
    main()
