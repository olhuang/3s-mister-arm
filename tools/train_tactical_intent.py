#!/usr/bin/env python3
"""Phase 12 tactical intent dataset, classifier, and gate tool.

This trains only the high-level `observation -> recommended_intent` model.  It
does not train direct game actions.  The live probe still decodes intent through
the conservative tactical decoder in `rl_probe_server.py`.
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

import label_rl_tactical_states as tactical_labels
import rl_combat_event_training as combat_events
import rl_probe_server as rl
import train_dqn_learner as dqn


TACTICAL_INTENT_SCHEMA_VERSION = 1
TACTICAL_INTENT_ALGORITHM_VERSION = "phase12-intent-mlp-v1"
TACTICAL_INTENT_NAMES = (
    "hold_guard",
    "wait",
    "fireball_zoning",
    "approach",
    "poke",
    "escape",
    "air_poke",
    "anti_air",
    "pressure",
    "throw",
    "punish",
    "low_guard",
    "adjust_spacing",
    "retreat",
)
CONFIDENCE_RANK = {"low": 1, "medium": 2, "high": 3}


@dataclass
class IntentSample:
    features: list[float]
    intent_index: int
    intent_name: str
    run_id: int
    episode_id: int
    decision_id: int
    label_confidence: str
    spacing_bucket: str
    threat_type: str
    opportunity_type: str
    event_reward: float = 0.0


@dataclass
class IntentDatasetStats:
    transition_rows: int = 0
    labeled_rows: int = 0
    skipped_rows: int = 0
    skipped_reasons: collections.Counter[str] = field(default_factory=collections.Counter)
    intent_counts: collections.Counter[str] = field(default_factory=collections.Counter)
    spacing_counts: collections.Counter[str] = field(default_factory=collections.Counter)
    threat_counts: collections.Counter[str] = field(default_factory=collections.Counter)
    opportunity_counts: collections.Counter[str] = field(default_factory=collections.Counter)
    confidence_counts: collections.Counter[str] = field(default_factory=collections.Counter)
    event_reward_rows: int = 0
    event_reward_sum: float = 0.0
    event_reward_by_intent: dict[str, float] = field(default_factory=dict)

    def as_metadata(self) -> dict[str, object]:
        top_intent_count = max(self.intent_counts.values(), default=0)
        return {
            "transition_rows": self.transition_rows,
            "labeled_rows": self.labeled_rows,
            "skipped_rows": self.skipped_rows,
            "skipped_reasons": dict(sorted(self.skipped_reasons.items())),
            "intent_counts": dict(sorted(self.intent_counts.items())),
            "spacing_counts": dict(sorted(self.spacing_counts.items())),
            "threat_counts": dict(sorted(self.threat_counts.items())),
            "opportunity_counts": dict(sorted(self.opportunity_counts.items())),
            "confidence_counts": dict(sorted(self.confidence_counts.items())),
            "event_reward_rows": self.event_reward_rows,
            "event_reward_sum": self.event_reward_sum,
            "event_reward_by_intent": dict(sorted(self.event_reward_by_intent.items())),
            "top_intent_ratio": top_intent_count / max(1, self.labeled_rows),
        }


@dataclass
class IntentTrainStats:
    steps: int = 0
    sampled_rows: int = 0
    loss_last: float = 0.0
    loss_avg: float = 0.0

    def as_metadata(self) -> dict[str, object]:
        return {
            "steps": self.steps,
            "sampled_rows": self.sampled_rows,
            "loss_last": self.loss_last,
            "loss_avg": self.loss_avg,
        }


@dataclass
class IntentEvalStats:
    rows: int = 0
    top1_rows: int = 0
    top3_rows: int = 0
    label_counts: collections.Counter[str] = field(default_factory=collections.Counter)
    pred_counts: collections.Counter[str] = field(default_factory=collections.Counter)
    confusion: dict[str, collections.Counter[str]] = field(default_factory=lambda: collections.defaultdict(collections.Counter))
    target_prob_sum: float = 0.0
    entropy_sum: float = 0.0

    def as_metadata(self) -> dict[str, object]:
        top_pred_count = max(self.pred_counts.values(), default=0)
        return {
            "rows": self.rows,
            "top1_rows": self.top1_rows,
            "top1_rate": self.top1_rows / max(1, self.rows),
            "top3_rows": self.top3_rows,
            "top3_rate": self.top3_rows / max(1, self.rows),
            "label_counts": dict(sorted(self.label_counts.items())),
            "pred_counts": dict(sorted(self.pred_counts.items())),
            "top_pred_ratio": top_pred_count / max(1, self.rows),
            "target_prob_avg": self.target_prob_sum / max(1, self.rows),
            "entropy_avg": self.entropy_sum / max(1, self.rows),
            "confusion": {
                label: dict(sorted(counter.items()))
                for label, counter in sorted(self.confusion.items())
            },
        }


def parse_path_list(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def parse_hidden_sizes(value: str) -> list[int]:
    sizes = [int(item) for item in value.split(",") if item.strip()]
    return [max(1, size) for size in sizes] or [64, 64]


def min_confidence_rank(value: str) -> int:
    return CONFIDENCE_RANK.get(str(value).strip().lower(), 1)


def selected_action_name(row: dict[str, object]) -> str | None:
    selection = rl.action_selection_from_fields(
        row,
        "policy_executed_action_id",
        "policy_executed_sub_action_id",
        "policy_executed_action_step",
        "policy",
    )
    return selection.name


def is_action_start(row: dict[str, object]) -> bool:
    action_step = rl.row_int_field(row, "policy_executed_action_step")
    return action_step == 0


def build_intent_samples(
    rows: list[dict[str, object]],
    context: tactical_labels.CombatEventContext,
    intent_names: tuple[str, ...],
    min_confidence: str,
    reward_validation: combat_events.CombatEventTrainingValidation,
    reward_config: combat_events.CombatEventRewardConfig,
) -> tuple[list[IntentSample], IntentDatasetStats, combat_events.CombatEventRewardStats]:
    stats = IntentDatasetStats(transition_rows=len(rows))
    reward_stats = combat_events.CombatEventRewardStats()
    intent_index = {name: index for index, name in enumerate(intent_names)}
    min_rank = min_confidence_rank(min_confidence)
    samples: list[IntentSample] = []

    for row in rows:
        if not rl.is_current_transition_schema_row(row):
            stats.skipped_rows += 1
            stats.skipped_reasons["unsupported_schema"] += 1
            continue
        labels = tactical_labels.label_row(row, context)
        if CONFIDENCE_RANK.get(labels.label_confidence, 1) < min_rank:
            stats.skipped_rows += 1
            stats.skipped_reasons[f"confidence_{labels.label_confidence}"] += 1
            continue
        intent = labels.recommended_intent
        if intent not in intent_index:
            stats.skipped_rows += 1
            stats.skipped_reasons[f"unsupported_intent_{intent}"] += 1
            continue
        action_name = selected_action_name(row)
        event_reward = combat_events.reward_adjustment_for_transition(
            reward_validation.index,
            row,
            action_name,
            is_action_start(row),
            reward_config,
            reward_stats,
        )
        sample = IntentSample(
            features=rl.dqn_feature_vector(row),
            intent_index=intent_index[intent],
            intent_name=intent,
            run_id=rl.row_int_field(row, "run_id"),
            episode_id=rl.row_int_field(row, "episode_id"),
            decision_id=rl.row_int_field(row, "decision_id"),
            label_confidence=labels.label_confidence,
            spacing_bucket=labels.spacing_bucket,
            threat_type=labels.threat_type,
            opportunity_type=labels.opportunity_type,
            event_reward=event_reward,
        )
        samples.append(sample)
        stats.labeled_rows += 1
        stats.intent_counts[intent] += 1
        stats.spacing_counts[labels.spacing_bucket] += 1
        stats.threat_counts[labels.threat_type] += 1
        stats.opportunity_counts[labels.opportunity_type] += 1
        stats.confidence_counts[labels.label_confidence] += 1
        if event_reward != 0.0:
            stats.event_reward_rows += 1
        stats.event_reward_sum += event_reward
        stats.event_reward_by_intent[intent] = stats.event_reward_by_intent.get(intent, 0.0) + event_reward

    return samples, stats, reward_stats


def softmax(values: list[float]) -> list[float]:
    if not values:
        return []
    max_value = max(values)
    exp_values = [math.exp(max(-80.0, min(80.0, value - max_value))) for value in values]
    total = sum(exp_values)
    if total <= 0.0:
        return [1.0 / len(values) for _ in values]
    return [value / total for value in exp_values]


def class_weights(samples: list[IntentSample], class_count: int, power: float) -> list[float]:
    counts = collections.Counter(sample.intent_index for sample in samples)
    weights = [1.0 for _ in range(class_count)]
    if not counts or power <= 0.0:
        return weights
    total = sum(counts.values())
    present_class_count = max(1, len(counts))
    for index in range(class_count):
        count = counts.get(index, 0)
        if count > 0:
            weights[index] = (total / (present_class_count * count)) ** power
    present_mean = sum(weights[index] for index in counts) / max(1, len(counts))
    for index in counts:
        weights[index] /= max(1e-6, present_mean)
    return weights


def initialize_output_bias(layers: list[dict[str, object]], samples: list[IntentSample], class_count: int) -> None:
    if not layers or class_count <= 0:
        return
    counts = collections.Counter(sample.intent_index for sample in samples)
    total = sum(counts.values())
    if total <= 0:
        return
    smoothing = 1.0
    log_priors = [
        math.log((counts.get(index, 0) + smoothing) / (total + smoothing * class_count))
        for index in range(class_count)
    ]
    mean_log_prior = sum(log_priors) / max(1, len(log_priors))
    output_layer = layers[-1]
    bias = output_layer.get("bias")
    if not isinstance(bias, list) or len(bias) != class_count:
        return
    for index, value in enumerate(log_priors):
        bias[index] = value - mean_log_prior


def train_intent_classifier(
    train_samples: list[IntentSample],
    intent_names: tuple[str, ...],
    hidden_sizes: list[int],
    seed: int,
    steps: int,
    batch_size: int,
    learning_rate: float,
    balanced_loss: bool,
    class_weight_power: float,
    log_interval: int,
) -> tuple[list[dict[str, object]], IntentTrainStats]:
    if not train_samples:
        raise SystemExit("tactical intent training: no training samples")
    rng = random.Random(seed)
    layers = dqn.init_network(len(rl.DQN_FEATURE_NAMES), hidden_sizes, len(intent_names), rng)
    initialize_output_bias(layers, train_samples, len(intent_names))
    grads = dqn.zero_grads(layers)
    stats = IntentTrainStats()
    weights = (
        class_weights(train_samples, len(intent_names), max(0.0, float(class_weight_power)))
        if balanced_loss
        else [1.0 for _ in intent_names]
    )

    for step in range(1, max(0, steps) + 1):
        batch = rng.choices(train_samples, k=min(max(1, batch_size), len(train_samples)))
        loss = 0.0
        for sample in batch:
            logits, activations, pre_activations = dqn.forward(layers, sample.features)
            probs = softmax(logits)
            target_prob = max(probs[sample.intent_index], 1e-15)
            weight = weights[sample.intent_index]
            loss += -math.log(target_prob) * weight
            output_grad = [prob * weight for prob in probs]
            output_grad[sample.intent_index] -= weight
            dqn.add_backward_grads(layers, grads, activations, pre_activations, output_grad)
            stats.sampled_rows += 1
        dqn.apply_grads(layers, grads, learning_rate, max(1, len(batch)))
        grads = dqn.zero_grads(layers)
        stats.steps = step
        stats.loss_last = loss / max(1, len(batch))
        stats.loss_avg = stats.loss_last if step == 1 else 0.98 * stats.loss_avg + 0.02 * stats.loss_last
        if log_interval > 0 and (step == 1 or step % log_interval == 0 or step == steps):
            print(
                f"Tactical Intent 12C step={step} loss={stats.loss_last:.6f} avg={stats.loss_avg:.6f}",
                flush=True,
            )
    return layers, stats


def evaluate_intent_classifier(
    layers: list[dict[str, object]],
    samples: list[IntentSample],
    intent_names: tuple[str, ...],
) -> IntentEvalStats:
    stats = IntentEvalStats()
    for sample in samples:
        logits, _activations, _pre = dqn.forward(layers, sample.features)
        probs = softmax(logits)
        if not probs:
            continue
        ranked = sorted(range(min(len(probs), len(intent_names))), key=lambda index: (probs[index], intent_names[index]), reverse=True)
        if not ranked:
            continue
        top_index = ranked[0]
        top_name = intent_names[top_index]
        label_name = sample.intent_name
        stats.rows += 1
        stats.label_counts[label_name] += 1
        stats.pred_counts[top_name] += 1
        stats.confusion[label_name][top_name] += 1
        stats.target_prob_sum += probs[sample.intent_index]
        stats.entropy_sum += -sum(prob * math.log(max(prob, 1e-15)) for prob in probs)
        if top_index == sample.intent_index:
            stats.top1_rows += 1
        if sample.intent_index in ranked[:3]:
            stats.top3_rows += 1
    return stats


def split_samples(
    samples: list[IntentSample],
    seed: int,
    eval_ratio: float,
) -> tuple[list[IntentSample], list[IntentSample]]:
    rng = random.Random(seed)
    shuffled = list(samples)
    rng.shuffle(shuffled)
    eval_count = min(len(shuffled) - 1, max(1, int(round(len(shuffled) * eval_ratio)))) if len(shuffled) > 1 else 0
    eval_samples = shuffled[:eval_count]
    train_samples = shuffled[eval_count:]
    return train_samples, eval_samples


def write_json_atomic(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, sort_keys=True, indent=2)
            stream.write("\n")
        rl.replace_with_retries(temp_path, str(path))
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


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


def publish_tactical_artifact(
    output_dir: str,
    version: int,
    intent_names: tuple[str, ...],
    layers: list[dict[str, object]],
    metadata: dict[str, object],
    updated_rows: int,
) -> None:
    payload = {
        "version": version,
        "policy": "tactical",
        "source": "offline-tactical-intent",
        "action_set_version": rl.ACTION_SET_VERSION,
        "created_at_unix": time.time(),
        "metadata": metadata,
        "actions": list(rl.TABULAR_DEFAULT_ACTIONS),
        "fallback_policy": "forward",
        "tactical_intent": {
            "schema_version": TACTICAL_INTENT_SCHEMA_VERSION,
            "algorithm_version": TACTICAL_INTENT_ALGORITHM_VERSION,
            "intent_names": list(intent_names),
            "feature_names": list(rl.DQN_FEATURE_NAMES),
            "feature_scales": dict(rl.DQN_FEATURE_SCALES),
            "layers": layers,
        },
        "updated_rows": updated_rows,
    }
    output = Path(output_dir)
    for path in (output / f"tactical-intent-v{version}.json", output / f"actor-v{version}.json", output / "current.json"):
        write_json_atomic(path, payload)


def gate_report(
    dataset_stats: IntentDatasetStats,
    train_eval: IntentEvalStats,
    holdout_eval: IntentEvalStats,
    min_rows: int,
    min_holdout_top1: float,
    max_top_pred_ratio: float,
) -> dict[str, object]:
    failures: list[str] = []
    if dataset_stats.labeled_rows < min_rows:
        failures.append(f"labeled_rows<{min_rows}")
    if holdout_eval.rows > 0 and holdout_eval.top1_rows / max(1, holdout_eval.rows) < min_holdout_top1:
        failures.append(f"holdout_top1<{min_holdout_top1:.3f}")
    top_ratio = max(holdout_eval.pred_counts.values(), default=0) / max(1, holdout_eval.rows)
    if top_ratio > max_top_pred_ratio:
        failures.append(f"top_pred_ratio>{max_top_pred_ratio:.3f}")
    if len(holdout_eval.pred_counts) < 3 and holdout_eval.rows > 0:
        failures.append("predicted_intent_diversity<3")
    return {
        "passed": not failures,
        "failures": failures,
        "min_rows": min_rows,
        "min_holdout_top1": min_holdout_top1,
        "max_top_pred_ratio": max_top_pred_ratio,
        "train_top1": train_eval.top1_rows / max(1, train_eval.rows),
        "holdout_top1": holdout_eval.top1_rows / max(1, holdout_eval.rows),
        "holdout_top_pred_ratio": top_ratio,
    }


def top_counts(counter: collections.Counter[str], limit: int = 10) -> str:
    total = sum(counter.values())
    if total <= 0:
        return "none"
    return ", ".join(f"{key}={value}/{100.0 * value / total:.1f}%" for key, value in counter.most_common(limit))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transitions", required=True, help="Comma-separated transition NDJSON logs")
    parser.add_argument("--combat-event-logs", default="", help="Optional comma-separated combat-event NDJSON logs")
    parser.add_argument("--output-dir", default="", help="Optional tactical intent artifact directory")
    parser.add_argument("--summary-path", default="", help="Optional summary JSON path")
    parser.add_argument("--labeled-output", default="", help="Optional intent dataset NDJSON path")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--hidden-sizes", default="64,64")
    parser.add_argument("--steps", type=int, default=1000)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--learning-rate", type=float, default=0.0007)
    parser.add_argument("--seed", type=int, default=12)
    parser.add_argument("--eval-ratio", type=float, default=0.2)
    parser.add_argument("--min-label-confidence", choices=("low", "medium", "high"), default="low")
    parser.add_argument("--balanced-loss", action="store_true", help="Use inverse-frequency class weights")
    parser.add_argument("--class-weight-power", type=float, default=0.25, help="Class balancing strength when --balanced-loss is enabled")
    parser.add_argument("--reward-profile", choices=combat_events.COMBAT_EVENT_REWARD_PROFILES, default="event-damage-v1")
    parser.add_argument("--reward-scale", type=float, default=1.0)
    parser.add_argument("--version", type=int, default=None)
    parser.add_argument("--log-interval", type=int, default=200)
    parser.add_argument("--gate-min-rows", type=int, default=1000)
    parser.add_argument("--gate-min-holdout-top1", type=float, default=0.55)
    parser.add_argument("--gate-max-top-pred-ratio", type=float, default=0.80)
    parser.add_argument("--fail-on-gate", action="store_true")
    args = parser.parse_args()

    transition_paths = parse_path_list(args.transitions)
    event_paths = parse_path_list(args.combat_event_logs)
    if not transition_paths:
        raise SystemExit("--transitions did not include any paths")

    rows = dqn.read_transition_rows(transition_paths, max(0, int(args.limit)))
    context = tactical_labels.load_combat_event_context([Path(path) for path in event_paths])
    if event_paths:
        validation = combat_events.validate_combat_event_training_logs(
            event_paths,
            transition_paths,
            rows,
            mode="tactical-intent",
        )
    else:
        validation = combat_events.CombatEventTrainingValidation(mode="off")
    reward_config = combat_events.CombatEventRewardConfig(
        enabled=bool(event_paths),
        profile=str(args.reward_profile),
        scale=max(0.0, float(args.reward_scale)),
    )
    samples, dataset_stats, reward_stats = build_intent_samples(
        rows,
        context,
        TACTICAL_INTENT_NAMES,
        str(args.min_label_confidence),
        validation,
        reward_config,
    )
    train_samples, holdout_samples = split_samples(samples, int(args.seed), max(0.0, min(0.9, float(args.eval_ratio))))
    layers, train_stats = train_intent_classifier(
        train_samples,
        TACTICAL_INTENT_NAMES,
        parse_hidden_sizes(args.hidden_sizes),
        int(args.seed),
        max(0, int(args.steps)),
        max(1, int(args.batch_size)),
        max(0.0, float(args.learning_rate)),
        bool(args.balanced_loss),
        max(0.0, float(args.class_weight_power)),
        max(0, int(args.log_interval)),
    )
    train_eval = evaluate_intent_classifier(layers, train_samples, TACTICAL_INTENT_NAMES)
    holdout_eval = evaluate_intent_classifier(layers, holdout_samples, TACTICAL_INTENT_NAMES)
    gate = gate_report(
        dataset_stats,
        train_eval,
        holdout_eval,
        max(0, int(args.gate_min_rows)),
        max(0.0, min(1.0, float(args.gate_min_holdout_top1))),
        max(0.0, min(1.0, float(args.gate_max_top_pred_ratio))),
    )
    metadata: dict[str, object] = {
        "phase": "12B/12C/12F/12G",
        "tactical_intent_schema_version": TACTICAL_INTENT_SCHEMA_VERSION,
        "algorithm_version": TACTICAL_INTENT_ALGORITHM_VERSION,
        "transition_paths": transition_paths,
        "combat_event_paths": event_paths,
        "intent_names": list(TACTICAL_INTENT_NAMES),
        "hidden_sizes": parse_hidden_sizes(args.hidden_sizes),
        "training_config": {
            "steps": max(0, int(args.steps)),
            "batch_size": max(1, int(args.batch_size)),
            "learning_rate": max(0.0, float(args.learning_rate)),
            "seed": int(args.seed),
            "eval_ratio": max(0.0, min(0.9, float(args.eval_ratio))),
            "min_label_confidence": str(args.min_label_confidence),
            "balanced_loss": bool(args.balanced_loss),
            "class_weight_power": max(0.0, float(args.class_weight_power)),
        },
        "combat_event_training": validation.as_metadata(),
        "combat_event_reward_config": reward_config.as_metadata(),
        "combat_event_reward_stats": reward_stats.as_metadata(),
        "dataset_stats": dataset_stats.as_metadata(),
        "train_stats": train_stats.as_metadata(),
        "train_eval": train_eval.as_metadata(),
        "holdout_eval": holdout_eval.as_metadata(),
        "phase12g_gate": gate,
    }
    if args.labeled_output:
        output_path = Path(args.labeled_output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as stream:
            for sample in samples:
                stream.write(
                    json.dumps(
                        {
                            "run_id": sample.run_id,
                            "episode_id": sample.episode_id,
                            "decision_id": sample.decision_id,
                            "recommended_intent": sample.intent_name,
                            "intent_index": sample.intent_index,
                            "label_confidence": sample.label_confidence,
                            "spacing_bucket": sample.spacing_bucket,
                            "threat_type": sample.threat_type,
                            "opportunity_type": sample.opportunity_type,
                            "event_reward": sample.event_reward,
                        },
                        sort_keys=True,
                    )
                )
                stream.write("\n")
    if args.output_dir:
        version = next_model_version(str(args.output_dir), args.version)
        metadata["published_model_dir"] = str(args.output_dir)
        metadata["published_version"] = version
        publish_tactical_artifact(str(args.output_dir), version, TACTICAL_INTENT_NAMES, layers, metadata, len(samples))
    if args.summary_path:
        write_json_atomic(Path(args.summary_path), metadata)
    print(
        "Tactical Intent 12G "
        f"rows={dataset_stats.transition_rows} labeled={dataset_stats.labeled_rows} "
        f"skipped={dataset_stats.skipped_rows} "
        f"train_top1={train_eval.top1_rows / max(1, train_eval.rows):.3f} "
        f"holdout_top1={holdout_eval.top1_rows / max(1, holdout_eval.rows):.3f} "
        f"gate={'PASS' if gate['passed'] else 'FAIL'} "
        f"failures={','.join(gate['failures']) if gate['failures'] else 'none'}",
        flush=True,
    )
    print(f"Tactical Intent labels={top_counts(dataset_stats.intent_counts)}", flush=True)
    print(f"Tactical Intent predictions={top_counts(holdout_eval.pred_counts)}", flush=True)
    if args.fail_on_gate and not gate["passed"]:
        raise SystemExit(3)


if __name__ == "__main__":
    main()
