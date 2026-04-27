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
    unrecognized_delayed_rewards: int = 0
    unrecognized_uncredited_reward_rows: int = 0

    def as_metadata(self) -> dict[str, object]:
        return {
            "included_action_rows": self.included_action_rows,
            "excluded_action_rows": self.excluded_action_rows,
            "excluded_action_reward_rows": self.excluded_action_reward_rows,
            "excluded_action_reward_sum": self.excluded_action_reward_sum,
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


ATTACK_RISK_ACTIONS = frozenset(
    {
        "stand-lp",
        "stand-mp",
        "stand-hp",
        "stand-lk",
        "stand-mk",
        "stand-hk",
        "forward-hp",
        "crouch-lk",
        "crouch-mk",
        "crouch-hk",
        "fireball",
        "throw",
        "jump-forward-mk",
        "jump-forward-hk",
        "jump-neutral-hk",
        "jump-back-hk",
        "shoryuken-mp",
        "tatsu-mk",
    }
)
SHORYUKEN_ACTION = "shoryuken-mp"
REWARD_RISK_PROFILES = ("none", "shoryuken-only", "all-attacks")


@dataclass(frozen=True)
class RewardRiskConfig:
    profile: str
    window_decisions: int
    attack_no_damage_cost: float
    attack_punished_cost: float
    shoryuken_no_damage_extra_cost: float
    shoryuken_punished_extra_cost: float


@dataclass
class RewardRiskStats:
    no_damage_cost_events: int = 0
    punished_cost_events: int = 0
    attack_no_damage_cost_total: float = 0.0
    attack_punished_cost_total: float = 0.0
    shoryuken_no_damage_extra_cost_total: float = 0.0
    shoryuken_punished_extra_cost_total: float = 0.0

    @property
    def total_cost(self) -> float:
        return (
            self.attack_no_damage_cost_total
            + self.attack_punished_cost_total
            + self.shoryuken_no_damage_extra_cost_total
            + self.shoryuken_punished_extra_cost_total
        )

    def as_metadata(self) -> dict[str, object]:
        return {
            "no_damage_cost_events": self.no_damage_cost_events,
            "punished_cost_events": self.punished_cost_events,
            "attack_no_damage_cost_total": self.attack_no_damage_cost_total,
            "attack_punished_cost_total": self.attack_punished_cost_total,
            "shoryuken_no_damage_extra_cost_total": self.shoryuken_no_damage_extra_cost_total,
            "shoryuken_punished_extra_cost_total": self.shoryuken_punished_extra_cost_total,
            "total_cost": self.total_cost,
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


def episode_key(row: dict[str, object]) -> tuple[int, int]:
    return (int(row.get("run_id", 0) or 0), int(row.get("episode_id", 0) or 0))


def row_order_key(row: dict[str, object]) -> tuple[int, int]:
    return (int(row.get("decision_id", 0) or 0), int(row.get("obs_frame", 0) or 0))


def int_field(row: dict[str, object], name: str) -> int:
    return int(row.get(name, 0) or 0)


def is_action_start(row: dict[str, object]) -> bool:
    return int_field(row, "executed_policy_action_step") == 0


def is_terminal_win(row: dict[str, object]) -> bool:
    return (
        bool(row.get("done", False))
        and int_field(row, "final_opp_hp") <= 0
        and int_field(row, "final_self_hp") > 0
    )


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
    if not apply_attack_cost and not apply_shoryuken_cost:
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

    if punished:
        stats.punished_cost_events += 1
    return cost


def build_experiences(
    rows: list[dict[str, object]],
    actions: tuple[str, ...],
    reward_scale: float,
    reward_risk_config: RewardRiskConfig,
) -> tuple[
    list[Experience],
    dict[str, int],
    dict[str, float],
    dict[str, int],
    dict[str, float],
    BuildDiagnostics,
    RewardRiskStats,
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

    for episode_rows in by_episode.values():
        episode_rows.sort(key=row_order_key)
        last_exp_index: int | None = None
        for index, row in enumerate(episode_rows):
            action_name = rl.transition_action_name(row)
            risk_cost = (
                reward_risk_cost(episode_rows, index, action_name, reward_risk_config, risk_stats)
                if action_name is not None
                else 0.0
            )
            reward = (rl.tabular_training_reward(row) - risk_cost) * reward_scale
            if action_name is None:
                if reward != 0.0 and last_exp_index is not None:
                    experiences[last_exp_index].reward += reward
                    action_rewards[actions[experiences[last_exp_index].action_index]] += reward
                    build_stats.unrecognized_delayed_rewards += 1
                elif reward != 0.0:
                    build_stats.unrecognized_uncredited_reward_rows += 1
                continue

            if action_name in observed_action_counts:
                observed_action_counts[action_name] += 1
                observed_action_rewards[action_name] += reward

            if action_name not in action_to_index:
                build_stats.excluded_action_rows += 1
                if reward != 0.0:
                    build_stats.excluded_action_reward_rows += 1
                    build_stats.excluded_action_reward_sum += reward
                last_exp_index = None
                continue

            next_row = episode_rows[index + 1] if index + 1 < len(episode_rows) else row
            done = bool(row.get("done", False)) or index + 1 >= len(episode_rows)
            exp = Experience(
                state=rl.dqn_feature_vector(row),
                action_index=action_to_index[action_name],
                reward=reward,
                next_state=rl.dqn_feature_vector(next_row),
                done=done,
            )
            experiences.append(exp)
            last_exp_index = len(experiences) - 1
            build_stats.included_action_rows += 1
            action_counts[action_name] += 1
            action_rewards[action_name] += reward

    return (
        experiences,
        action_counts,
        action_rewards,
        observed_action_counts,
        observed_action_rewards,
        build_stats,
        risk_stats,
    )


def reward_risk_config_from_args(args: argparse.Namespace) -> RewardRiskConfig:
    return RewardRiskConfig(
        profile=str(args.reward_risk_profile),
        window_decisions=max(0, int(args.reward_risk_window_decisions)),
        attack_no_damage_cost=max(0.0, float(args.reward_attack_no_damage_cost)),
        attack_punished_cost=max(0.0, float(args.reward_attack_punished_cost)),
        shoryuken_no_damage_extra_cost=max(0.0, float(args.reward_shoryuken_no_damage_extra_cost)),
        shoryuken_punished_extra_cost=max(0.0, float(args.reward_shoryuken_punished_extra_cost)),
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
    reward_risk_config = reward_risk_config_from_args(args)
    (
        experiences,
        action_counts,
        action_rewards,
        observed_action_counts,
        observed_action_rewards,
        build_stats,
        reward_risk_stats,
    ) = build_experiences(
        rows,
        actions,
        args.reward_scale,
        reward_risk_config,
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
    metadata = {
        "transition_logs": args.transition_logs,
        "rows_read": len(rows),
        "experiences": len(experiences),
        "actions_subset": list(actions),
        "actions_subset_size": len(actions),
        "build_diagnostics": build_stats.as_metadata(),
        "delayed_rewards": build_stats.unrecognized_delayed_rewards,
        "reward_source": "hp-delta+risk-cost" if reward_risk_config.profile != "none" else "hp-delta",
        "reward_scale": args.reward_scale,
        "reward_scale_applied_after_risk_cost": True,
        "reward_risk_profile": reward_risk_config.profile,
        "reward_risk_window_decisions": reward_risk_config.window_decisions,
        "reward_attack_no_damage_cost": reward_risk_config.attack_no_damage_cost,
        "reward_attack_punished_cost": reward_risk_config.attack_punished_cost,
        "reward_shoryuken_no_damage_extra_cost": reward_risk_config.shoryuken_no_damage_extra_cost,
        "reward_shoryuken_punished_extra_cost": reward_risk_config.shoryuken_punished_extra_cost,
        "reward_risk_stats": reward_risk_stats.as_metadata(),
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
        f"version={version} model_dir={args.model_dir} rows={len(rows)} experiences={len(experiences)} "
        f"actions={len(actions)} "
        f"risk={reward_risk_config.profile} risk_cost={reward_risk_stats.total_cost:.1f} "
        f"loss={train_stats['last_loss']:.6f} avg_loss={train_stats['avg_loss']:.6f} "
        f"included={build_stats.included_action_rows} excluded={build_stats.excluded_action_rows} "
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
