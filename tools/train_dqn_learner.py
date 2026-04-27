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


def build_experiences(
    rows: list[dict[str, object]],
    actions: tuple[str, ...],
    reward_scale: float,
) -> tuple[list[Experience], dict[str, int], dict[str, float], int]:
    action_to_index = {action: index for index, action in enumerate(actions)}
    by_episode: dict[tuple[int, int], list[dict[str, object]]] = collections.defaultdict(list)
    for row in rows:
        by_episode[episode_key(row)].append(row)

    experiences: list[Experience] = []
    action_counts = {action: 0 for action in actions}
    action_rewards = {action: 0.0 for action in actions}
    delayed_rewards = 0

    for episode_rows in by_episode.values():
        episode_rows.sort(key=row_order_key)
        last_exp_index: int | None = None
        for index, row in enumerate(episode_rows):
            reward = rl.tabular_training_reward(row) * reward_scale
            action_name = rl.tabular_action_name(int(row.get("executed_action_wire", 0) or 0))
            if action_name is None or action_name not in action_to_index:
                if reward != 0.0 and last_exp_index is not None:
                    experiences[last_exp_index].reward += reward
                    action_rewards[actions[experiences[last_exp_index].action_index]] += reward
                    delayed_rewards += 1
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
            action_counts[action_name] += 1
            action_rewards[action_name] += reward

    return experiences, action_counts, action_rewards, delayed_rewards


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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("transition_logs", nargs="+", help="Transition NDJSON logs used as offline replay data")
    parser.add_argument("--model-dir", required=True, help="Directory where DQN actor manifests will be published")
    parser.add_argument("--model-version", type=int, default=None, help="Explicit model version; defaults to current+1")
    parser.add_argument("--limit", type=int, default=0, help="Maximum rows to read across all transition logs; 0 means all")
    parser.add_argument("--steps", type=int, default=2000, help="Gradient steps")
    parser.add_argument("--batch-size", type=int, default=64, help="Replay batch size")
    parser.add_argument("--hidden-sizes", default="64,64", help="Comma-separated hidden layer sizes")
    parser.add_argument("--learning-rate", type=float, default=0.001, help="MLP learning rate")
    parser.add_argument("--gamma", type=float, default=0.95, help="DQN discounted future reward")
    parser.add_argument("--reward-scale", type=float, default=0.01, help="Scale applied to HP-delta reward during training")
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
    args = parser.parse_args()

    actions = rl.TABULAR_DEFAULT_ACTIONS
    rows = read_transition_rows(args.transition_logs, args.limit)
    experiences, action_counts, action_rewards, delayed_rewards = build_experiences(rows, actions, args.reward_scale)
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
    greedy_counts = count_greedy_actions(layers, experiences, actions, args.eval_limit)
    version = next_model_version(args.model_dir, args.model_version)
    metadata = {
        "transition_logs": args.transition_logs,
        "rows_read": len(rows),
        "experiences": len(experiences),
        "delayed_rewards": delayed_rewards,
        "reward_source": "hp-delta",
        "reward_scale": args.reward_scale,
        "steps": max(1, args.steps),
        "batch_size": max(1, args.batch_size),
        "gamma": min(0.999, max(0.0, args.gamma)),
        "learning_rate": max(1e-8, args.learning_rate),
        "action_counts": action_counts,
        "action_rewards": action_rewards,
        "greedy_counts": greedy_counts,
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
        f"loss={train_stats['last_loss']:.6f} avg_loss={train_stats['avg_loss']:.6f} "
        f"greedy={','.join(f'{action}:{count}' for action, count in greedy_counts.items() if count)}",
        flush=True,
    )


if __name__ == "__main__":
    main()
