#!/usr/bin/env python3
"""Run cursor-based DQN incremental retraining and publish on success."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import tempfile
import time
from pathlib import Path


REWARD_PRESETS = (
    "none",
    "ground-specials-v24",
    "ground-specials-v35a",
    "projectile-response-v1",
    "projectile-response-v2",
    "projectile-response-v3",
)


def atomic_write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, sort_keys=True)
            stream.write("\n")
        os.replace(temp_path, path)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def load_json(path: Path) -> dict[str, object]:
    try:
        with path.open("r", encoding="utf-8") as stream:
            payload = json.load(stream)
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"{path}: failed to read JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise SystemExit(f"{path}: expected JSON object")
    return payload


def current_model_path(model_dir: str) -> Path:
    return Path(model_dir) / "current.json"


def list_from_model(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]


def replay_recipe(model: dict[str, object]) -> dict[str, object]:
    metadata = model.get("metadata")
    if not isinstance(metadata, dict):
        return {}
    recipe = metadata.get("replay_recipe")
    return recipe if isinstance(recipe, dict) else {}


def infer_hidden_sizes(model: dict[str, object]) -> str:
    dqn = model.get("dqn")
    if not isinstance(dqn, dict):
        return "64,64"
    layers = dqn.get("layers")
    if not isinstance(layers, list) or len(layers) <= 1:
        return "64,64"
    sizes: list[str] = []
    for layer in layers[:-1]:
        if not isinstance(layer, dict):
            return "64,64"
        weights = layer.get("weights")
        if not isinstance(weights, list) or not weights:
            return "64,64"
        sizes.append(str(len(weights)))
    return ",".join(sizes) if sizes else "64,64"


def ratios_to_text(value: object) -> str:
    if not isinstance(value, dict):
        return ""
    items: list[str] = []
    for key, raw_ratio in sorted(value.items()):
        try:
            ratio = float(raw_ratio)
        except (TypeError, ValueError):
            continue
        if ratio > 0.0:
            items.append(f"{key}={ratio:g}")
    return ",".join(items)


def reward_preset_args(name: str) -> list[str]:
    if name == "none":
        return [
            "--reward-risk-profile",
            "none",
            "--engine-outcome-training-mode",
            "off",
        ]
    if name not in {
        "ground-specials-v24",
        "ground-specials-v35a",
        "projectile-response-v1",
        "projectile-response-v2",
        "projectile-response-v3",
    }:
        raise SystemExit(f"unknown reward preset: {name}")
    original_name = name
    projectile_response_args: list[str] = []
    if name in {"projectile-response-v1", "projectile-response-v2", "projectile-response-v3"}:
        name = "ground-specials-v35a"
        safe_jump_bonus = "2.0" if original_name in {"projectile-response-v2", "projectile-response-v3"} else "1.2"
        projectile_response_args = [
            "--reward-projectile-response-profile",
            "incoming-v1",
            "--reward-projectile-response-window-decisions",
            "12",
            "--reward-projectile-threat-min-time-to-self",
            "2",
            "--reward-projectile-threat-max-time-to-self",
            "48",
            "--reward-projectile-threat-max-dx",
            "240",
            "--reward-projectile-threat-max-abs-y",
            "96",
            "--reward-projectile-close-max-dx",
            "96",
            "--reward-projectile-safe-jump-bonus",
            safe_jump_bonus,
            "--reward-projectile-late-jump-hit-cost",
            "1.5",
            "--reward-projectile-close-back-success-bonus",
            "0.6",
            "--reward-projectile-close-guard-success-bonus",
            "0.8",
            "--reward-projectile-back-escape-min-dx-delta",
            "8",
        ]
        if original_name in {"projectile-response-v2", "projectile-response-v3"}:
            projectile_response_args.extend(
                [
                    "--projectile-response-safe-jump-oversample",
                    "10",
                    "--projectile-response-late-jump-hit-oversample",
                    "4",
                    "--projectile-response-close-back-oversample",
                    "3",
                    "--projectile-response-close-guard-oversample",
                    "3",
                ]
            )
        if original_name == "projectile-response-v3":
            projectile_response_args.extend(
                [
                    "--projectile-expert-margin-loss",
                    "--projectile-expert-margin",
                    "0.1",
                    "--projectile-expert-margin-weight",
                    "1.0",
                    "--projectile-expert-margin-batch-size",
                    "32",
                    "--projectile-expert-margin-equivalent-jump-actions",
                    "--projectile-expert-margin-valid-action-mask",
                    "action-start-v1",
                ]
            )
    if name == "ground-specials-v35a":
        guard_costs = ("0.4", "0.6")
        engine_action_windows = "fireball-lp=45,fireball-mp=45,fireball-hp=45,tatsu-lk=25,tatsu-mk=25,tatsu-hk=25,throw=8"
        engine_action_oversamples = (
            "fireball-lp=4,fireball-mp=4,fireball-hp=4,"
            "shoryuken-lp=8,shoryuken-mp=10,shoryuken-hp=12,"
            "tatsu-lk=6,tatsu-mk=6,tatsu-hk=6,throw=8"
        )
        if original_name in {"projectile-response-v2", "projectile-response-v3"}:
            engine_action_oversamples = (
                "fireball-lp=4,fireball-mp=4,fireball-hp=4,"
                "shoryuken-lp=4,shoryuken-mp=5,shoryuken-hp=6,"
                "tatsu-lk=6,tatsu-mk=6,tatsu-hk=6,throw=8"
            )
        preset_args = [
            "--batch-sampling",
            "balanced",
            "--balanced-batch-ratios",
            "movement=0.25,normal=0.45,special=0.30",
        ]
    else:
        guard_costs = ("0.3", "0.5")
        engine_action_windows = "fireball-lp=45,fireball-mp=45,fireball-hp=45,tatsu-lk=25,tatsu-mk=25,tatsu-hk=25"
        engine_action_oversamples = (
            "fireball-lp=8,fireball-mp=8,fireball-hp=8,"
            "shoryuken-lp=4,shoryuken-mp=6,shoryuken-hp=8,"
            "tatsu-lk=6,tatsu-mk=6,tatsu-hk=6"
        )
        preset_args = []
    return [
        *preset_args,
        "--reward-risk-profile",
        "all-attacks",
        "--reward-risk-window-decisions",
        "15",
        "--reward-attack-no-damage-cost",
        "0.3",
        "--reward-attack-punished-cost",
        "1.0",
        "--reward-shoryuken-no-damage-extra-cost",
        "0.0",
        "--reward-shoryuken-punished-extra-cost",
        "0.5",
        "--reward-jump-attack-no-damage-extra-cost",
        "0.0",
        "--reward-jump-attack-punished-extra-cost",
        "0.0",
        "--reward-guard-success-bonus",
        "0.0",
        "--reward-guard-success-window-decisions",
        "6",
        "--reward-guard-threat-max-dx",
        "120",
        "--reward-passive-guard-cost",
        guard_costs[0],
        "--reward-far-guard-cost",
        guard_costs[1],
        "--reward-spacing-target-min-dx",
        "50",
        "--reward-spacing-target-max-dx",
        "120",
        "--reward-spacing-improve-bonus",
        "0.5",
        "--reward-spacing-worsen-cost",
        "0.2",
        "--reward-spacing-maintain-bonus",
        "0.1",
        "--reward-spacing-threat-back-bonus",
        "0.3",
        "--engine-outcome-training-mode",
        "prefer-engine-action",
        "--engine-outcome-window-decisions",
        "15",
        "--engine-outcome-action-windows",
        engine_action_windows,
        "--engine-outcome-hit-bonus",
        "1.0",
        "--engine-outcome-no-damage-cost",
        "0.2",
        "--engine-outcome-punished-cost",
        "1.0",
        "--engine-outcome-oversample",
        "1",
        "--engine-outcome-action-oversamples",
        engine_action_oversamples,
        *projectile_response_args,
    ]


def run_json_command(command: list[str], allow_status_2: bool = False) -> tuple[int, dict[str, object]]:
    completed = subprocess.run(command, text=True, capture_output=True)
    if completed.stderr:
        sys.stderr.write(completed.stderr)
    stdout = completed.stdout.strip()
    payload: dict[str, object] = {}
    if stdout:
        try:
            parsed = json.loads(stdout.splitlines()[-1])
        except json.JSONDecodeError as exc:
            raise SystemExit(f"command did not return JSON: {' '.join(command)}\n{stdout}") from exc
        if isinstance(parsed, dict):
            payload = parsed
    if completed.returncode != 0 and not (allow_status_2 and completed.returncode == 2):
        raise SystemExit(completed.returncode)
    return completed.returncode, payload


def run_snapshot(args: argparse.Namespace, source_log: str, state_path: str, chunk_label: str) -> tuple[str, dict[str, object]]:
    command = [
        str(args.python),
        "tools/rl_retrain_chunk.py",
        "snapshot",
        "--source-log",
        source_log,
        "--state-path",
        state_path,
        "--chunk-dir",
        str(args.chunk_dir),
        "--chunk-prefix",
        str(args.chunk_prefix),
        "--label",
        chunk_label,
        "--min-new-rows",
        str(max(0, int(args.min_new_rows))),
        "--max-new-rows",
        str(max(0, int(args.max_new_rows))),
    ]
    if args.replace_pending:
        command.append("--replace-pending")
    if args.allow_truncate_reset:
        command.append("--allow-truncate-reset")
    _returncode, payload = run_json_command(command, allow_status_2=True)
    status = str(payload.get("status", "") or "")
    return status, payload


def run_commit(args: argparse.Namespace, source_log: str, state_path: str, chunk_log: str) -> dict[str, object]:
    command = [
        str(args.python),
        "tools/rl_retrain_chunk.py",
        "commit",
        "--source-log",
        source_log,
        "--state-path",
        state_path,
        "--chunk-log",
        chunk_log,
    ]
    _returncode, payload = run_json_command(command, allow_status_2=True)
    status = str(payload.get("status", "") or "")
    if status != "committed":
        raise SystemExit(f"commit failed with status={status}")
    return payload


def build_train_command(
    args: argparse.Namespace,
    model: dict[str, object],
    source_log: str,
    base_logs: list[str],
    chunk_log: str,
    source_ratios: str,
    recipe_name: str,
) -> list[str]:
    actions = [str(action) for action in model.get("actions", []) if str(action)]
    if not actions:
        raise SystemExit("current model does not contain an action list")
    current_path = current_model_path(str(args.model_dir))
    command = [
        str(args.python),
        "tools/train_dqn_learner.py",
        *base_logs,
        chunk_log,
        "--model-dir",
        str(args.model_dir),
        "--init-model",
        str(current_path),
        "--steps",
        str(max(1, int(args.steps))),
        "--batch-size",
        str(max(1, int(args.batch_size))),
        "--learning-rate",
        str(max(1e-8, float(args.learning_rate))),
        "--gamma",
        str(float(args.gamma)),
        "--target-sync-steps",
        str(max(1, int(args.target_sync_steps))),
        "--dqn-target-mode",
        str(args.dqn_target_mode),
        "--replay-source-ratios",
        source_ratios,
        "--dqn-require-movable-state-sources",
        str(args.dqn_require_movable_state_sources),
        "--actions",
        ",".join(actions),
        "--hidden-sizes",
        infer_hidden_sizes(model),
        "--fallback-policy",
        str(args.fallback_policy),
        "--training-action-source",
        str(args.training_action_source),
        "--batch-sampling",
        str(args.batch_sampling),
        "--balanced-batch-ratios",
        str(args.balanced_batch_ratios),
        "--epsilon",
        str(float(args.epsilon)),
        "--seed",
        str(int(args.seed)),
        "--log-interval",
        str(max(0, int(args.log_interval))),
        "--eval-limit",
        str(max(0, int(args.eval_limit))),
        "--diagnostic-top-n",
        str(max(1, int(args.diagnostic_top_n))),
        "--replay-recipe-name",
        recipe_name,
        "--replay-recipe-base-logs",
        ",".join(base_logs),
        "--replay-recipe-live-log",
        source_log,
    ]
    command.extend(reward_preset_args(str(args.reward_preset)))
    if args.trainer_extra_args.strip():
        command.extend(shlex.split(str(args.trainer_extra_args)))
    return command


def annotate_current_model(
    model_dir: str,
    auto_retrain: dict[str, object],
) -> dict[str, object]:
    current_path = current_model_path(model_dir)
    payload = load_json(current_path)
    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
        payload["metadata"] = metadata
    metadata["auto_retrain"] = auto_retrain
    version = int(payload.get("version", 0) or 0)
    atomic_write_json(current_path, payload)
    version_path = Path(model_dir) / f"actor-v{version}.json"
    if version_path.exists():
        atomic_write_json(version_path, payload)
    return payload


def resolve_run_config(args: argparse.Namespace, model: dict[str, object]) -> tuple[list[str], str, str, str]:
    recipe = replay_recipe(model)
    base_logs = list(args.base_log)
    if not base_logs:
        base_logs = list_from_model(recipe.get("base_logs"))
    if not base_logs:
        raise SystemExit("no base logs configured; pass --base-log or write metadata.replay_recipe.base_logs")
    source_log = str(args.source_log).strip() or str(recipe.get("live_incremental_log", "") or "")
    if not source_log:
        raise SystemExit("no live source log configured; pass --source-log or write metadata.replay_recipe.live_incremental_log")
    source_ratios = str(args.replay_source_ratios).strip() or ratios_to_text(recipe.get("source_ratios"))
    if not source_ratios:
        source_ratios = "cpu-demo=0.50,human-demo=0.30,remote=0.20"
    recipe_name = str(args.replay_recipe_name).strip() or str(recipe.get("training_recipe", "") or "auto-incremental")
    return base_logs, source_log, source_ratios, recipe_name


def run_cycle(args: argparse.Namespace) -> str:
    started_at = time.time()
    model_dir = str(args.model_dir)
    model_before = load_json(current_model_path(model_dir))
    base_version = int(model_before.get("version", 0) or 0)
    base_logs, source_log, source_ratios, recipe_name = resolve_run_config(args, model_before)
    state_path = str(args.state_path) if str(args.state_path).strip() else str(Path(model_dir) / "retrain-cursor.json")
    chunk_label = str(args.chunk_label).strip() or f"v{base_version + 1}"
    if args.dry_run:
        train_command = build_train_command(
            args,
            model_before,
            source_log,
            base_logs,
            "<chunk-log>",
            source_ratios,
            recipe_name,
        )
        print(
            json.dumps(
                {
                    "status": "dry-run",
                    "base_model_version": base_version,
                    "base_logs": base_logs,
                    "source_log": source_log,
                    "source_ratios": source_ratios,
                    "state_path": state_path,
                    "chunk_dir": str(args.chunk_dir),
                    "train_command": train_command,
                },
                sort_keys=True,
            )
        )
        return "dry-run"

    snapshot_status, snapshot_payload = run_snapshot(args, source_log, state_path, chunk_label)
    if snapshot_status == "not-enough-rows":
        print(json.dumps(snapshot_payload, sort_keys=True))
        return "not-enough-rows"
    pending: object
    if snapshot_status == "snapshotted":
        pending = snapshot_payload.get("pending_chunk")
    elif snapshot_status == "pending-exists" and args.use_pending:
        pending = snapshot_payload.get("pending_chunk")
    elif snapshot_status == "pending-exists":
        print(json.dumps(snapshot_payload, sort_keys=True))
        return "pending-exists"
    else:
        raise SystemExit(f"unexpected snapshot status: {snapshot_status}")
    if not isinstance(pending, dict):
        raise SystemExit("snapshot did not return a pending chunk")
    chunk_log = str(pending.get("chunk_log", "") or "")
    if not chunk_log:
        raise SystemExit("pending chunk missing chunk_log")

    train_command = build_train_command(args, model_before, source_log, base_logs, chunk_log, source_ratios, recipe_name)
    print(
        json.dumps(
            {
                "status": "training",
                "base_model_version": base_version,
                "chunk_log": chunk_log,
                "row_count": pending.get("row_count"),
                "train_command": train_command,
            },
            sort_keys=True,
        ),
        flush=True,
    )
    completed = subprocess.run(train_command)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)

    finished_at = time.time()
    model_after = load_json(current_model_path(model_dir))
    new_version = int(model_after.get("version", 0) or 0)
    auto_retrain = {
        "enabled": True,
        "base_model_version": base_version,
        "new_model_version": new_version,
        "source_log": source_log,
        "chunk_log": chunk_log,
        "new_rows": int(pending.get("row_count", 0) or 0),
        "state_path": state_path,
        "source_ratios": source_ratios,
        "base_logs": base_logs,
        "reward_preset": str(args.reward_preset),
        "started_at_unix": started_at,
        "finished_at_unix": finished_at,
        "duration_sec": finished_at - started_at,
    }
    annotate_current_model(model_dir, auto_retrain)
    if args.commit:
        commit_payload = run_commit(args, source_log, state_path, chunk_log)
        print(json.dumps({"status": "published-and-committed", "auto_retrain": auto_retrain, "commit": commit_payload}, sort_keys=True))
        return "published-and-committed"
    print(json.dumps({"status": "published-not-committed", "auto_retrain": auto_retrain}, sort_keys=True))
    return "published-not-committed"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", required=True, help="Rolling DQN model dir containing current.json")
    parser.add_argument("--source-log", default="", help="Append-only live log; defaults to current metadata replay_recipe")
    parser.add_argument("--state-path", default="", help="Cursor state path; default is <model-dir>/retrain-cursor.json")
    parser.add_argument("--chunk-dir", default="logs/retrain-chunks", help="Directory for retrain chunk logs")
    parser.add_argument("--chunk-prefix", default="rl-retrain-chunk")
    parser.add_argument("--chunk-label", default="")
    parser.add_argument("--base-log", action="append", default=[], help="Base replay log; repeatable")
    parser.add_argument("--replay-source-ratios", default="", help="Override replay source ratios")
    parser.add_argument("--replay-recipe-name", default="", help="Override replay recipe name")
    parser.add_argument("--min-new-rows", type=int, default=5000)
    parser.add_argument("--max-new-rows", type=int, default=0, help="0 means no chunk row cap")
    parser.add_argument("--replace-pending", action="store_true")
    parser.add_argument("--allow-truncate-reset", action="store_true")
    parser.add_argument("--use-pending", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--commit", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--cycles", type=int, default=1, help="Number of cycles to run; 0 means forever")
    parser.add_argument("--interval-sec", type=float, default=600.0)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--steps", type=int, default=800)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--learning-rate", type=float, default=0.0003)
    parser.add_argument("--gamma", type=float, default=0.9)
    parser.add_argument("--target-sync-steps", type=int, default=200)
    parser.add_argument("--dqn-target-mode", choices=("standard", "double"), default="standard")
    parser.add_argument("--dqn-require-movable-state-sources", default="remote")
    parser.add_argument("--fallback-policy", default="stand-mk")
    parser.add_argument("--training-action-source", default="auto")
    parser.add_argument("--batch-sampling", default="balanced")
    parser.add_argument("--balanced-batch-ratios", default="movement=0.3,normal=0.3,special=0.4")
    parser.add_argument("--epsilon", type=float, default=0.05)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--log-interval", type=int, default=500)
    parser.add_argument("--eval-limit", type=int, default=5000)
    parser.add_argument("--diagnostic-top-n", type=int, default=12)
    parser.add_argument("--reward-preset", choices=REWARD_PRESETS, default="ground-specials-v24")
    parser.add_argument(
        "--trainer-extra-args",
        default="",
        help="Additional shell-like arguments appended to tools/train_dqn_learner.py; later duplicates override earlier options",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    cycle = 0
    while True:
        cycle += 1
        status = run_cycle(args)
        if args.dry_run or args.cycles == 1:
            return
        if args.cycles > 0 and cycle >= args.cycles:
            return
        if status in {"published-and-committed", "published-not-committed", "not-enough-rows", "pending-exists"}:
            time.sleep(max(0.0, float(args.interval_sec)))


if __name__ == "__main__":
    main()
