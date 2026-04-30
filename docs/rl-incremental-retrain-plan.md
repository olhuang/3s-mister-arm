# RL Incremental Retrain Plan

This plan defines a rolling DQN retrain flow for live RL experiments.

## Goal

Enable this loop:

```text
live probe collects transition rows
-> auto retrain snapshots only new live rows
-> trainer warm-starts from the current model
-> trainer publishes a new current.json
-> probe server hot-swaps to the new model
```

The first implementation is intentionally permissive: it records retrain
diagnostics, but it does not block publishing with hard safety gates.

## Stage 1: Trainer Warm-Start

`tools/train_dqn_learner.py` gains:

```bash
--init-model model/.../current.json
```

When present, the trainer:

- loads the existing DQN actor JSON.
- verifies `policy == dqn`.
- verifies `action_set_version` matches the current action set.
- verifies `actions` exactly match `--actions`, including order.
- verifies `dqn.feature_names` exactly match the current DQN feature schema.
- verifies layer shapes match the requested `--hidden-sizes`, feature count, and action count.
- uses the loaded layers as the starting network instead of random `init_network(...)`.

The published model metadata records:

```json
{
  "incremental_training": true,
  "init_model_path": "model/.../current.json",
  "init_model_version": 25,
  "init_model_validation": "exact-action-feature-layer-match"
}
```

No `--init-model` keeps the old full-retrain behavior.

## Stage 2: Replay Recipe Metadata

Full-train candidates should write a replay recipe into model metadata:

```json
{
  "replay_recipe": {
    "training_recipe": "ground-specials-r1r2",
    "base_logs": [
      "logs/rl-transitions-cpu-demo-schema-v3-4-3-3.ndjson",
      "logs/rl-transitions-human-demo-schema-v3-4-3-3.ndjson",
      "logs/rl-transitions-live-dqn-v21a-20260430-124456.ndjson",
      "logs/rl-transitions-live-dqn-v23-20260430-135148.ndjson"
    ],
    "live_incremental_log": "logs/rl-transitions-live-dqn-v24-....ndjson",
    "source_ratios": {
      "cpu-demo": 0.5,
      "human-demo": 0.3,
      "remote": 0.2
    }
  }
}
```

`base_logs` are replay anchors that each incremental train should reuse to
reduce catastrophic forgetting. The live append-only log is handled separately
with a cursor.

## Stage 3: Live Cursor And Chunk Snapshot

Auto retrain should not reread the same append-only live log rows forever.
Use `tools/rl_retrain_chunk.py` to keep a cursor such as:

```json
{
  "source_log": "logs/rl-transitions-live-dqn-v24-....ndjson",
  "last_trained_byte_offset": 123456,
  "last_trained_row_count": 5000,
  "last_trained_run_id": 1,
  "last_trained_episode_id": 12,
  "last_trained_decision_id": 345
}
```

The tool has four subcommands:

```bash
python3 tools/rl_retrain_chunk.py init \
  --source-log logs/rl-transitions-live-dqn-v24-....ndjson \
  --state-path model/dqn-live-ground-specials-current/retrain-cursor.json \
  --at eof

python3 tools/rl_retrain_chunk.py snapshot \
  --source-log logs/rl-transitions-live-dqn-v24-....ndjson \
  --state-path model/dqn-live-ground-specials-current/retrain-cursor.json \
  --chunk-dir logs/retrain-chunks \
  --label v25 \
  --min-new-rows 5000

python3 tools/rl_retrain_chunk.py commit \
  --source-log logs/rl-transitions-live-dqn-v24-....ndjson \
  --state-path model/dqn-live-ground-specials-current/retrain-cursor.json

python3 tools/rl_retrain_chunk.py status \
  --source-log logs/rl-transitions-live-dqn-v24-....ndjson \
  --state-path model/dqn-live-ground-specials-current/retrain-cursor.json
```

On each retrain:

1. Read only rows after the cursor.
2. Write those rows to a stable chunk file, for example:
   `logs/retrain-chunks/rl-retrain-chunk-v25-20260430-143000.ndjson`.
3. Leave the chunk in `pending_chunk` without advancing `last_trained_*`.
4. Train on `base_logs + newest chunk`.
5. After the trainer successfully publishes, run `commit` to advance the cursor.

Do not automatically add every chunk to `base_logs`. A chunk should become a
base log only after a manual quality review.

This two-phase snapshot/commit flow avoids losing live rows if training fails
after a chunk is created.

## Stage 4: Auto Retrain Runner

`tools/rl_auto_retrain.py` wires the cursor/chunk tool to the DQN trainer:

```bash
python3 tools/rl_auto_retrain.py \
  --model-dir model/dqn-live-ground-specials-current \
  --source-log logs/rl-transitions-live-dqn-v24-....ndjson \
  --base-log logs/rl-transitions-cpu-demo-schema-v3-4-3-3.ndjson \
  --base-log logs/rl-transitions-human-demo-schema-v3-4-3-3.ndjson \
  --replay-source-ratios cpu-demo=0.50,human-demo=0.30,remote=0.20 \
  --min-new-rows 5000 \
  --steps 800
```

The runner:

1. Read the current model metadata.
2. Resolve `replay_recipe.base_logs`.
3. Resolve the live append-only log and cursor.
4. Snapshot new rows into a chunk when `--min-new-rows` is satisfied.
5. Invoke `tools/train_dqn_learner.py --init-model <current.json>`.
6. Let the trainer publish a new `current.json`.
7. Annotate the new model with `metadata.auto_retrain`.
8. Commit the cursor only after train and annotation succeed.

The existing probe server already watches `model-dir/current.json`, so a
published model can be hot-swapped without restarting the probe server.

Useful options:

- `--cycles 0 --interval-sec 600` keeps polling forever.
- `--dry-run` prints the resolved training command without snapshotting.
- `--no-commit` leaves the chunk pending after publish for manual inspection.
- `--reward-preset ground-specials-v24` applies the current v24-style reward
  and engine-outcome knobs.
- `--trainer-extra-args "..."` appends advanced trainer flags without changing
  the runner.

## First Suggested Auto-Retrain Parameters

```text
trigger: 5000 new live rows or 10 minutes
steps: 800
learning_rate: 0.0003
source ratios: cpu-demo=0.50,human-demo=0.30,remote=0.20
publish: always publish
hard gates: off for the first implementation
```

The first version records diagnostics only. Later versions can add hard gates
for action collapse, `stand-hk` regression, or unwanted replacement actions.

## Validation Plan

1. `python3 -m py_compile tools/train_dqn_learner.py`
2. Full-retrain smoke without `--init-model`.
3. Warm-start smoke from a schema-compatible model such as v24.
4. Negative warm-start smoke from an incompatible model such as v9; this should
   fail because the feature schema differs.
5. Cursor/chunk smoke:
   - snapshot writes a chunk without advancing the cursor.
   - `not-enough-rows` exits without training.
   - commit advances the cursor only after a pending chunk is accepted.
6. Auto retrain smoke:
   - `--dry-run` prints the intended command.
   - a tiny warm-start train publishes the next model version.
   - `metadata.auto_retrain` records base version, new version, source log,
     chunk log, row count, source ratios, and duration.
   - cursor `pending_chunk` is cleared only after successful publish.
7. Compare base and warm-start candidate on CPU/human and live replay slices.
