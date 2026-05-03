#!/usr/bin/env python3
"""Compare DQN actor greedy actions on the same RL transition observations."""

from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path

import rl_probe_server as rl


DX_BUCKETS = ("close", "mid", "far")
NON_ATTACK_ACTIONS = frozenset({"forward", "back", "guard-stand", "guard-crouch"}) | frozenset(
    getattr(rl, "JUMP_START_ACTION_NAMES", ())
)
ATTACK_ACTIONS = frozenset(action for action in rl.TABULAR_ACTION_NAMES if action not in NON_ATTACK_ACTIONS)
SHORYUKEN_ACTIONS = frozenset(action for action in rl.TABULAR_ACTION_NAMES if action.startswith("shoryuken-"))
FIREBALL_ACTIONS = frozenset(action for action in rl.TABULAR_ACTION_NAMES if action.startswith("fireball-"))
DEFENSE_ACTIONS = frozenset({"back", "guard-stand", "guard-crouch"})
THREAT_DX_BUCKETS = ("atk0_close", "atk0_mid", "atk0_far", "atk1_close", "atk1_mid", "atk1_far")


def model_path(value: str) -> Path:
    path = Path(value)
    if path.is_dir():
        return path / "current.json"
    return path


def parse_model_arg(value: str) -> tuple[str, Path]:
    if "=" in value:
        label, raw_path = value.split("=", 1)
        return label.strip() or Path(raw_path).stem, model_path(raw_path.strip())
    path = model_path(value)
    return path.parent.name if path.name == "current.json" else path.stem, path


def load_model(value: str) -> tuple[str, dict[str, object]]:
    label, path = parse_model_arg(value)
    with path.open("r", encoding="utf-8") as stream:
        model = json.load(stream)
    if model.get("policy") != "dqn":
        raise SystemExit(f"{label}: expected policy=dqn in {path}")
    action_set_version = int(model.get("action_set_version", 0) or 0)
    if action_set_version != rl.ACTION_SET_VERSION:
        raise SystemExit(
            f"{label}: action_set_version={action_set_version} expected={rl.ACTION_SET_VERSION} in {path}"
        )
    actions = model.get("actions")
    dqn_model = model.get("dqn")
    if not isinstance(actions, list) or not isinstance(dqn_model, dict):
        raise SystemExit(f"{label}: missing actions/dqn payload in {path}")
    model["_path"] = str(path)
    return label, model


def read_rows(paths: list[str], limit: int, tail_rows: int) -> list[dict[str, object]]:
    raw_rows: list[dict[str, object]] = []
    for path in paths:
        with open(path, "r", encoding="utf-8") as stream:
            for line_no, line in enumerate(stream, start=1):
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                try:
                    replay_row = rl.learner_replay_row(row)
                except ValueError as exc:
                    raise SystemExit(f"{path}:{line_no}: {exc}") from exc
                if replay_row is not None:
                    raw_rows.append(replay_row)
    if tail_rows > 0:
        raw_rows = raw_rows[-tail_rows:]
    if limit > 0:
        raw_rows = raw_rows[:limit]
    return raw_rows


def dx_bucket(row: dict[str, object]) -> str:
    return rl.bucket_range(int(row.get("obs_abs_dx", 0) or 0), (48, 144), DX_BUCKETS)


def threat_dx_bucket(row: dict[str, object]) -> str:
    attack = 1 if int(row.get("obs_opp_routine_attack_state", 0) or 0) else 0
    return f"atk{attack}_{dx_bucket(row)}"


def greedy_action(
    model: dict[str, object],
    row: dict[str, object],
    support_prior_config: rl.DQNSupportPriorConfig = rl.DQNSupportPriorConfig(),
    valid_action_mask_config: rl.DQNValidActionMaskConfig = rl.DQNValidActionMaskConfig(),
    shoryuken_context_prior_config: rl.DQNShoryukenContextPriorConfig = rl.DQNShoryukenContextPriorConfig(),
    ground_normal_context_prior_config: rl.DQNGroundNormalContextPriorConfig = rl.DQNGroundNormalContextPriorConfig(),
    fireball_zoning_prior_config: rl.DQNFireballZoningPriorConfig = rl.DQNFireballZoningPriorConfig(),
    threat_defense_prior_config: rl.DQNThreatDefensePriorConfig = rl.DQNThreatDefensePriorConfig(),
) -> tuple[str, float]:
    ranked = ranked_actions(
        model,
        row,
        support_prior_config,
        valid_action_mask_config,
        shoryuken_context_prior_config,
        ground_normal_context_prior_config,
        fireball_zoning_prior_config,
        threat_defense_prior_config,
    )
    if not ranked:
        return "none", 0.0
    return ranked[0]


def ranked_actions(
    model: dict[str, object],
    row: dict[str, object],
    support_prior_config: rl.DQNSupportPriorConfig = rl.DQNSupportPriorConfig(),
    valid_action_mask_config: rl.DQNValidActionMaskConfig = rl.DQNValidActionMaskConfig(),
    shoryuken_context_prior_config: rl.DQNShoryukenContextPriorConfig = rl.DQNShoryukenContextPriorConfig(),
    ground_normal_context_prior_config: rl.DQNGroundNormalContextPriorConfig = rl.DQNGroundNormalContextPriorConfig(),
    fireball_zoning_prior_config: rl.DQNFireballZoningPriorConfig = rl.DQNFireballZoningPriorConfig(),
    threat_defense_prior_config: rl.DQNThreatDefensePriorConfig = rl.DQNThreatDefensePriorConfig(),
) -> list[tuple[str, float]]:
    actions = [str(action) for action in model.get("actions", [])]
    dqn_model = model.get("dqn")
    if not isinstance(dqn_model, dict) or not actions:
        return []
    metadata = model.get("metadata")
    return rl.dqn_ranked_action_scores(
        tuple(actions),
        dqn_model,
        metadata if isinstance(metadata, dict) else {},
        row,
        support_prior_config,
        valid_action_mask_config,
        rl.DQNProjectileTimingPriorConfig(),
        shoryuken_context_prior_config,
        ground_normal_context_prior_config,
        fireball_zoning_prior_config,
        threat_defense_prior_config,
    )


def parse_focus_actions(value: str) -> tuple[str, ...]:
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
        raise SystemExit(f"Unknown focus action(s): {','.join(invalid)}")
    return tuple(actions)


def print_action_source_summary(rows: list[dict[str, object]], training_action_source: str, top_n: int) -> None:
    source_counts: collections.Counter[str] = collections.Counter()
    source_action_counts: dict[str, collections.Counter[str]] = collections.defaultdict(collections.Counter)
    for row in rows:
        selection = rl.select_training_action(row, training_action_source)
        source_counts[selection.source] += 1
        if selection.name is not None:
            source_action_counts[selection.source][selection.name] += 1

    print(
        f"\nLOG_ACTION_SOURCE training_action_source={training_action_source} rows={len(rows)} "
        f"counts={','.join(f'{source}:{count}' for source, count in source_counts.most_common()) or 'none'}"
    )
    for source in sorted(source_action_counts):
        print(f"  {source:<13} {format_counts(source_action_counts[source], sum(source_action_counts[source].values()), top_n)}")


def format_counts(counts: collections.Counter[str], total: int, limit: int) -> str:
    if not counts:
        return "none"
    parts: list[str] = []
    for action, count in counts.most_common(limit):
        pct = 100.0 * count / max(1, total)
        parts.append(f"{action}:{count}/{pct:.1f}%")
    return ",".join(parts)


def format_selected_q(counts: collections.Counter[str], q_sum: collections.Counter[str], limit: int) -> str:
    if not counts:
        return "none"
    parts: list[str] = []
    for action, count in counts.most_common(limit):
        if count <= 0:
            continue
        parts.append(f"{action}:{q_sum[action] / count:.3f}")
    return ",".join(parts) if parts else "none"


def format_rank_counts(counts: collections.Counter[str], total: int) -> str:
    labels = ("top1", "top2", "top3", "top4plus")
    parts: list[str] = []
    for label in labels:
        count = counts.get(label, 0)
        pct = 100.0 * count / max(1, total)
        parts.append(f"{label}:{count}/{pct:.1f}%")
    return " ".join(parts)


def rank_label(rank: int) -> str:
    if rank <= 1:
        return "top1"
    if rank == 2:
        return "top2"
    if rank == 3:
        return "top3"
    return "top4plus"


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = int(round((len(ordered) - 1) * max(0.0, min(1.0, pct))))
    return ordered[index]


def print_focus_diagnostics(
    label: str,
    model: dict[str, object],
    rows: list[dict[str, object]],
    focus_actions: tuple[str, ...],
    focus_rank_limit: int,
    top_n: int,
    support_prior_config: rl.DQNSupportPriorConfig,
    valid_action_mask_config: rl.DQNValidActionMaskConfig,
    shoryuken_context_prior_config: rl.DQNShoryukenContextPriorConfig,
    ground_normal_context_prior_config: rl.DQNGroundNormalContextPriorConfig,
    fireball_zoning_prior_config: rl.DQNFireballZoningPriorConfig,
    threat_defense_prior_config: rl.DQNThreatDefensePriorConfig,
) -> None:
    model_actions = {str(action) for action in model.get("actions", [])}
    available_actions = tuple(action for action in focus_actions if action in model_actions)
    missing_actions = tuple(action for action in focus_actions if action not in model_actions)
    if not focus_actions:
        return
    if not available_actions:
        print(f"  focus {','.join(focus_actions)} missing_in_model={','.join(missing_actions) or 'none'}")
        return

    rank_counts: collections.Counter[str] = collections.Counter()
    focus_action_counts: collections.Counter[str] = collections.Counter()
    blocked_by_topn: collections.Counter[str] = collections.Counter()
    bucket_rank_counts: dict[str, collections.Counter[str]] = collections.defaultdict(collections.Counter)
    bucket_focus_counts: dict[str, collections.Counter[str]] = collections.defaultdict(collections.Counter)
    bucket_blocked_by: dict[str, collections.Counter[str]] = collections.defaultdict(collections.Counter)
    q_gaps: list[float] = []

    for row in rows:
        ranked = ranked_actions(
            model,
            row,
            support_prior_config,
            valid_action_mask_config,
            shoryuken_context_prior_config,
            ground_normal_context_prior_config,
            fireball_zoning_prior_config,
            threat_defense_prior_config,
        )
        if not ranked:
            continue
        top_action, top_value = ranked[0]
        focus_ranked = [
            (rank, action, value)
            for rank, (action, value) in enumerate(ranked, start=1)
            if action in available_actions
        ]
        if not focus_ranked:
            continue
        best_focus_rank, best_focus_action, best_focus_value = min(
            focus_ranked,
            key=lambda item: (item[0], -item[2], item[1]),
        )
        label_name = rank_label(best_focus_rank)
        bucket = threat_dx_bucket(row)
        rank_counts[label_name] += 1
        focus_action_counts[best_focus_action] += 1
        bucket_rank_counts[bucket][label_name] += 1
        q_gaps.append(top_value - best_focus_value)
        if best_focus_rank <= focus_rank_limit:
            bucket_focus_counts[bucket][best_focus_action] += 1
            if best_focus_rank > 1:
                blocked_by_topn[top_action] += 1
                bucket_blocked_by[bucket][top_action] += 1

    total = sum(rank_counts.values())
    q_gap_mean = sum(q_gaps) / len(q_gaps) if q_gaps else 0.0
    missing_text = f" missing_in_model={','.join(missing_actions)}" if missing_actions else ""
    print(f"  focus {','.join(available_actions)}{missing_text}")
    print(f"    rank {format_rank_counts(rank_counts, total)}")
    print(f"    best_focus {format_counts(focus_action_counts, max(1, total), max(1, top_n))}")
    print(
        f"    blocked_by_top{focus_rank_limit} "
        f"{format_counts(blocked_by_topn, max(1, sum(blocked_by_topn.values())), max(1, top_n))}"
    )
    print(f"    q_gap mean:{q_gap_mean:.3f} p90:{percentile(q_gaps, 0.90):.3f}")
    for bucket in THREAT_DX_BUCKETS:
        bucket_total = sum(bucket_rank_counts[bucket].values())
        if bucket_total <= 0:
            continue
        print(
            f"    {bucket:<10} rank {format_rank_counts(bucket_rank_counts[bucket], bucket_total)} "
            f"top{focus_rank_limit}_focus={format_counts(bucket_focus_counts[bucket], bucket_total, max(1, top_n))} "
            f"blocked_by={format_counts(bucket_blocked_by[bucket], max(1, sum(bucket_blocked_by[bucket].values())), max(1, top_n))}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("transition_logs", nargs="+", help="Transition NDJSON logs used as evaluation observations")
    parser.add_argument(
        "--model",
        action="append",
        required=True,
        help="DQN model as LABEL=path, path/current.json, or model directory. Repeat for A/B/C.",
    )
    parser.add_argument("--limit", type=int, default=0, help="Maximum rows to evaluate after optional tail filtering")
    parser.add_argument("--tail-rows", type=int, default=0, help="Evaluate only the last N rows across all logs")
    parser.add_argument("--top-n", type=int, default=8, help="Top actions to print per distribution")
    parser.add_argument(
        "--focus-actions",
        default="",
        help=(
            "Comma-separated actions to inspect by rank, e.g. "
            "fireball-lp,fireball-mp,fireball-hp or shoryuken-lp,shoryuken-mp,shoryuken-hp"
        ),
    )
    parser.add_argument(
        "--focus-rank-limit",
        type=int,
        default=3,
        help="Rank threshold used for focus top-N and blocker diagnostics",
    )
    parser.add_argument(
        "--training-action-source",
        choices=rl.TRAINING_ACTION_SOURCES,
        default="auto",
        help=(
            "Canonical log action label source to summarize before model evaluation. auto uses engine/input "
            "labels for current-schema demo rows and policy labels for current-schema remote rows."
        ),
    )
    parser.add_argument(
        "--collapse-warning-threshold",
        type=float,
        default=0.70,
        help="Print WARN when one greedy action exceeds this fraction of evaluated rows",
    )
    parser.add_argument(
        "--dqn-support-prior-min-count",
        type=int,
        default=0,
        help="Minimum replay action count before DQN support-prior count penalty is skipped; 0 disables count penalty",
    )
    parser.add_argument(
        "--dqn-support-prior-count-penalty",
        type=float,
        default=0.0,
        help="Q-score penalty applied proportionally to missing replay support below --dqn-support-prior-min-count",
    )
    parser.add_argument(
        "--dqn-support-prior-negative-mean-penalty",
        type=float,
        default=0.0,
        help="Q-score penalty applied when an action's replay mean reward is non-positive",
    )
    parser.add_argument(
        "--dqn-support-prior-exempt-actions",
        default="",
        help="Comma-separated DQN actions exempt from support-prior penalties",
    )
    parser.add_argument(
        "--dqn-support-prior-models",
        default="",
        help=(
            "Comma-separated model labels to rerank with the support prior; "
            "empty applies the prior to every model when prior flags are enabled"
        ),
    )
    parser.add_argument(
        "--dqn-valid-action-mask",
        choices=rl.DQN_VALID_ACTION_MASK_MODES,
        default="off",
        help="Optional shared DQN valid-action mask applied before ranking every compared model",
    )
    parser.add_argument(
        "--dqn-shoryuken-context-prior",
        action="store_true",
        help="Apply a soft Shoryuken Q penalty outside coarse anti-air contexts before DQN argmax",
    )
    parser.add_argument(
        "--dqn-shoryuken-prior-models",
        default="",
        help=(
            "Comma-separated model labels to rerank with the Shoryuken context prior; "
            "empty applies the prior to every model when --dqn-shoryuken-context-prior is enabled"
        ),
    )
    parser.add_argument(
        "--dqn-shoryuken-prior-penalty",
        type=float,
        default=0.04,
        help="Shoryuken Q penalty outside the anti-air context when --dqn-shoryuken-context-prior is enabled",
    )
    parser.add_argument(
        "--dqn-shoryuken-prior-min-abs-dx",
        type=int,
        default=24,
        help="Minimum obs_abs_dx considered a plausible anti-air Shoryuken context",
    )
    parser.add_argument(
        "--dqn-shoryuken-prior-max-abs-dx",
        type=int,
        default=150,
        help="Maximum obs_abs_dx considered a plausible anti-air Shoryuken context",
    )
    parser.add_argument(
        "--dqn-ground-normal-context-prior",
        action="store_true",
        help="Apply a soft grounded normal Q penalty outside close or threat/contact poke contexts before DQN argmax",
    )
    parser.add_argument(
        "--dqn-ground-normal-prior-models",
        default="",
        help=(
            "Comma-separated model labels to rerank with the ground-normal context prior; "
            "empty applies the prior to every model when --dqn-ground-normal-context-prior is enabled"
        ),
    )
    parser.add_argument(
        "--dqn-ground-normal-prior-penalty",
        type=float,
        default=0.04,
        help="Grounded normal Q penalty outside close or threat/contact poke contexts",
    )
    parser.add_argument(
        "--dqn-ground-normal-prior-close-max-abs-dx",
        type=int,
        default=48,
        help="Maximum obs_abs_dx where stand/crouch normals are not penalized by the ground-normal prior",
    )
    parser.add_argument(
        "--dqn-ground-normal-prior-poke-max-abs-dx",
        type=int,
        default=120,
        help="Maximum obs_abs_dx for threat/contact poke contexts before normals are penalized as too far",
    )
    parser.add_argument(
        "--dqn-fireball-zoning-prior",
        action="store_true",
        help="Apply a soft fireball Q bonus in far grounded zoning contexts before DQN argmax",
    )
    parser.add_argument(
        "--dqn-fireball-zoning-prior-models",
        default="",
        help=(
            "Comma-separated model labels to rerank with the fireball zoning prior; "
            "empty applies the prior to every model when --dqn-fireball-zoning-prior is enabled"
        ),
    )
    parser.add_argument(
        "--dqn-fireball-zoning-prior-bonus",
        type=float,
        default=0.03,
        help="Fireball Q bonus in eligible far grounded zoning contexts",
    )
    parser.add_argument(
        "--dqn-fireball-zoning-prior-min-abs-dx",
        type=int,
        default=120,
        help="Minimum obs_abs_dx considered an eligible fireball zoning context",
    )
    parser.add_argument(
        "--dqn-fireball-zoning-prior-max-abs-dx",
        type=int,
        default=260,
        help="Maximum obs_abs_dx considered an eligible fireball zoning context",
    )
    parser.add_argument(
        "--dqn-threat-defense-prior",
        action="store_true",
        help="Apply a soft guard/back Q bonus when the opponent is attacking at close/mid range",
    )
    parser.add_argument(
        "--dqn-threat-defense-prior-models",
        default="",
        help=(
            "Comma-separated model labels to rerank with the threat-defense prior; "
            "empty applies the prior to every model when --dqn-threat-defense-prior is enabled"
        ),
    )
    parser.add_argument(
        "--dqn-threat-defense-prior-guard-bonus",
        type=float,
        default=0.03,
        help="Guard Q bonus in eligible opponent-attack close/mid contexts",
    )
    parser.add_argument(
        "--dqn-threat-defense-prior-back-bonus",
        type=float,
        default=0.02,
        help="Back Q bonus in eligible opponent-attack close/mid contexts",
    )
    parser.add_argument(
        "--dqn-threat-defense-prior-unsafe-penalty",
        type=float,
        default=0.0,
        help="Forward and grounded-normal Q penalty in eligible opponent-attack close/mid contexts",
    )
    parser.add_argument(
        "--dqn-threat-defense-prior-max-abs-dx",
        type=int,
        default=144,
        help="Maximum obs_abs_dx considered an eligible opponent-attack defense context",
    )
    args = parser.parse_args()

    models = [load_model(value) for value in args.model]
    support_prior_config = rl.DQNSupportPriorConfig(
        min_action_count=max(0, int(args.dqn_support_prior_min_count)),
        count_penalty=max(0.0, float(args.dqn_support_prior_count_penalty)),
        negative_mean_penalty=max(0.0, float(args.dqn_support_prior_negative_mean_penalty)),
        exempt_actions=rl.parse_action_name_set(
            str(args.dqn_support_prior_exempt_actions),
            option_name="--dqn-support-prior-exempt-actions",
        ),
    )
    prior_model_labels = {
        item.strip()
        for item in str(args.dqn_support_prior_models).split(",")
        if item.strip()
    }
    valid_action_mask_config = rl.parse_dqn_valid_action_mask_config(str(args.dqn_valid_action_mask))
    shoryuken_prior_model_labels = {
        item.strip()
        for item in str(args.dqn_shoryuken_prior_models).split(",")
        if item.strip()
    }
    shoryuken_prior_min_dx = max(0, int(args.dqn_shoryuken_prior_min_abs_dx))
    shoryuken_prior_max_dx = max(shoryuken_prior_min_dx, int(args.dqn_shoryuken_prior_max_abs_dx))
    shoryuken_context_prior_config = rl.DQNShoryukenContextPriorConfig(
        enabled=bool(args.dqn_shoryuken_context_prior),
        penalty=max(0.0, float(args.dqn_shoryuken_prior_penalty)),
        min_abs_dx=shoryuken_prior_min_dx,
        max_abs_dx=shoryuken_prior_max_dx,
    )
    ground_normal_prior_model_labels = {
        item.strip()
        for item in str(args.dqn_ground_normal_prior_models).split(",")
        if item.strip()
    }
    fireball_zoning_prior_model_labels = {
        item.strip()
        for item in str(args.dqn_fireball_zoning_prior_models).split(",")
        if item.strip()
    }
    threat_defense_prior_model_labels = {
        item.strip()
        for item in str(args.dqn_threat_defense_prior_models).split(",")
        if item.strip()
    }
    ground_normal_prior_close_max_dx = max(0, int(args.dqn_ground_normal_prior_close_max_abs_dx))
    ground_normal_prior_poke_max_dx = max(
        ground_normal_prior_close_max_dx,
        int(args.dqn_ground_normal_prior_poke_max_abs_dx),
    )
    ground_normal_context_prior_config = rl.DQNGroundNormalContextPriorConfig(
        enabled=bool(args.dqn_ground_normal_context_prior),
        penalty=max(0.0, float(args.dqn_ground_normal_prior_penalty)),
        close_max_abs_dx=ground_normal_prior_close_max_dx,
        poke_max_abs_dx=ground_normal_prior_poke_max_dx,
    )
    fireball_zoning_prior_min_dx = max(0, int(args.dqn_fireball_zoning_prior_min_abs_dx))
    fireball_zoning_prior_max_dx = max(
        fireball_zoning_prior_min_dx,
        int(args.dqn_fireball_zoning_prior_max_abs_dx),
    )
    fireball_zoning_prior_config = rl.DQNFireballZoningPriorConfig(
        enabled=bool(args.dqn_fireball_zoning_prior),
        bonus=max(0.0, float(args.dqn_fireball_zoning_prior_bonus)),
        min_abs_dx=fireball_zoning_prior_min_dx,
        max_abs_dx=fireball_zoning_prior_max_dx,
    )
    threat_defense_prior_config = rl.DQNThreatDefensePriorConfig(
        enabled=bool(args.dqn_threat_defense_prior),
        guard_bonus=max(0.0, float(args.dqn_threat_defense_prior_guard_bonus)),
        back_bonus=max(0.0, float(args.dqn_threat_defense_prior_back_bonus)),
        unsafe_penalty=max(0.0, float(args.dqn_threat_defense_prior_unsafe_penalty)),
        max_abs_dx=max(0, int(args.dqn_threat_defense_prior_max_abs_dx)),
    )
    rows = read_rows(args.transition_logs, max(0, args.limit), max(0, args.tail_rows))
    if not rows:
        raise SystemExit("No evaluation rows loaded")
    focus_actions = parse_focus_actions(args.focus_actions)
    print_action_source_summary(rows, args.training_action_source, max(1, args.top_n))

    choices_by_label: dict[str, list[str]] = {}
    first_label = models[0][0]

    for label, model in models:
        model_support_prior_config = (
            support_prior_config
            if support_prior_config.enabled and (not prior_model_labels or label in prior_model_labels)
            else rl.DQNSupportPriorConfig()
        )
        model_shoryuken_context_prior_config = (
            shoryuken_context_prior_config
            if shoryuken_context_prior_config.enabled
            and (not shoryuken_prior_model_labels or label in shoryuken_prior_model_labels)
            else rl.DQNShoryukenContextPriorConfig()
        )
        model_ground_normal_context_prior_config = (
            ground_normal_context_prior_config
            if ground_normal_context_prior_config.enabled
            and (not ground_normal_prior_model_labels or label in ground_normal_prior_model_labels)
            else rl.DQNGroundNormalContextPriorConfig()
        )
        model_fireball_zoning_prior_config = (
            fireball_zoning_prior_config
            if fireball_zoning_prior_config.enabled
            and (not fireball_zoning_prior_model_labels or label in fireball_zoning_prior_model_labels)
            else rl.DQNFireballZoningPriorConfig()
        )
        model_threat_defense_prior_config = (
            threat_defense_prior_config
            if threat_defense_prior_config.enabled
            and (not threat_defense_prior_model_labels or label in threat_defense_prior_model_labels)
            else rl.DQNThreatDefensePriorConfig()
        )
        counts: collections.Counter[str] = collections.Counter()
        by_threat_dx: dict[str, collections.Counter[str]] = collections.defaultdict(collections.Counter)
        q_sum: collections.Counter[str] = collections.Counter()
        choices: list[str] = []
        for row in rows:
            action, value = greedy_action(
                model,
                row,
                model_support_prior_config,
                valid_action_mask_config,
                model_shoryuken_context_prior_config,
                model_ground_normal_context_prior_config,
                model_fireball_zoning_prior_config,
                model_threat_defense_prior_config,
            )
            choices.append(action)
            counts[action] += 1
            by_threat_dx[threat_dx_bucket(row)][action] += 1
            q_sum[action] += value
        choices_by_label[label] = choices
        metadata = model.get("metadata")
        profile = "unknown"
        if isinstance(metadata, dict):
            profile = str(metadata.get("reward_risk_profile", "unknown") or "unknown")
        attack_total = sum(count for action, count in counts.items() if action in ATTACK_ACTIONS)
        shoryuken_total = sum(counts.get(action, 0) for action in SHORYUKEN_ACTIONS)
        fireball_total = sum(counts.get(action, 0) for action in FIREBALL_ACTIONS)
        defense_total = sum(counts.get(action, 0) for action in DEFENSE_ACTIONS)
        top_action, top_count = counts.most_common(1)[0] if counts else ("none", 0)
        top_rate = top_count / max(1, len(rows))
        collapse = "WARN" if top_rate >= max(0.0, min(1.0, args.collapse_warning_threshold)) else "ok"
        actions = model.get("actions")
        action_count = len(actions) if isinstance(actions, list) else 0
        print(
            f"\nMODEL {label} version={model.get('version')} profile={profile} actions={action_count} rows={len(rows)} "
            f"attack_rate={100.0 * attack_total / len(rows):.1f}% "
            f"shoryuken_rate={100.0 * shoryuken_total / len(rows):.1f}% "
            f"fireball_rate={100.0 * fireball_total / len(rows):.1f}% "
            f"defense_rate={100.0 * defense_total / len(rows):.1f}% "
            f"top={top_action}:{top_rate * 100.0:.1f}% collapse={collapse} "
            f"support_prior={model_support_prior_config.label()} "
            f"valid_mask={valid_action_mask_config.label()} "
            f"shoryuken_prior={model_shoryuken_context_prior_config.label()} "
            f"ground_normal_prior={model_ground_normal_context_prior_config.label()} "
            f"fireball_prior={model_fireball_zoning_prior_config.label()} "
            f"threat_defense_prior={model_threat_defense_prior_config.label()}"
        )
        print(f"  overall {format_counts(counts, len(rows), max(1, args.top_n))}")
        print(f"  selected_q_mean {format_selected_q(counts, q_sum, max(1, args.top_n))}")
        for bucket in THREAT_DX_BUCKETS:
            bucket_counts = by_threat_dx.get(bucket, collections.Counter())
            print(f"  {bucket:<10} {format_counts(bucket_counts, sum(bucket_counts.values()), max(1, args.top_n))}")
        print_focus_diagnostics(
            label,
            model,
            rows,
            focus_actions,
            max(1, args.focus_rank_limit),
            max(1, args.top_n),
            model_support_prior_config,
            valid_action_mask_config,
            model_shoryuken_context_prior_config,
            model_ground_normal_context_prior_config,
            model_fireball_zoning_prior_config,
            model_threat_defense_prior_config,
        )

    baseline_choices = choices_by_label[first_label]
    for label, choices in choices_by_label.items():
        if label == first_label:
            continue
        changed = sum(1 for base, other in zip(baseline_choices, choices) if base != other)
        base_shoryu_to_other = sum(
            1
            for base, other in zip(baseline_choices, choices)
            if base in SHORYUKEN_ACTIONS and other not in SHORYUKEN_ACTIONS
        )
        other_to_shoryu = sum(
            1
            for base, other in zip(baseline_choices, choices)
            if base not in SHORYUKEN_ACTIONS and other in SHORYUKEN_ACTIONS
        )
        print(
            f"\nCOMPARE {first_label} -> {label} "
            f"changed={changed}/{len(rows)} "
            f"base_shoryuken_to_other={base_shoryu_to_other} "
            f"other_to_shoryuken={other_to_shoryu}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
