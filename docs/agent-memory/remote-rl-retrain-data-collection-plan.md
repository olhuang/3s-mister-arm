# Remote RL Full Retrain Data Collection Plan

This document is the collection plan for restarting the remote RL DQN training
from a clean curriculum instead of relying on a few free-form gameplay logs.

The main lesson from V41 through V62 is that scalar reward shaping cannot rescue
missing data. The replay buffer must intentionally cover the skills the model is
expected to learn: movement, attacks, specials, defense, jumping, anti-air,
projectile timing, corner behavior, and natural match integration.

## Scope

Initial scope:

- Ryu as the controlled agent.
- Ryu or simple CPU opponent first.
- schema-v5/v6 style transition logs with projectile fields.
- training-mode and versus-mode logs are both allowed, but their purpose must be
  explicit in the log name and metadata.

Out of scope for the first reboot:

- multi-character generalization.
- throw-tech as a hard target unless the labels are verified.
- using overlay attack-outcome labels as hard truth before move-family
  validation proves they are stable.

## Measurement Rule

Use effective experiences, not raw rows, as the quota.

Every collected log should be summarized by:

- action-start experiences.
- clean success events.
- failure events.
- distance bucket:
  - close: `0-60`.
  - mid: `60-150`.
  - far: `150+`.
- projectile `time_to_self` bucket, when relevant:
  - `0-6`.
  - `7-12`.
  - `13-22`.
  - `23-30`.
  - `31-48`.
  - `49+`.
- execution source:
  - `human-demo`.
  - `cpu-demo`.
  - `remote`.
- outcome labels available for the row:
  - HP delta.
  - engine-attributed action, when validated.
  - guard/contact/whiff/punished indicators, when validated.
- detector dry-run results for the phase:
  - threat detectors.
  - success/failure detectors.
  - oversample/margin eligibility counts.

Target scale for the first useful reboot:

- minimum: about `60K` effective experiences.
- preferred: `80K-120K` effective experiences.
- expected raw rows: about `120K-250K`, depending on action cadence, macro
  continuation rows, and episode length.

## Detector Dry-Run Gate

Do not train directly after collecting a phase log. First run analyzer/detector
dry-runs and compare detector counts against what was intentionally recorded.

The important lesson from V55-V60 is that a behavior can be present in the log
while the detector still misses it because the selector is too narrow. If the
detector misses most of the intended rows, fix the detector or selector before
training.

For every phase log, record:

- rows and action-start experiences.
- selected execution source counts.
- action distribution.
- detector hit counts for the phase.
- detector misses that appear visually/semantically wrong.

For projectile logs, specifically check:

- incoming projectile threat rows.
- close guard success.
- close back success.
- safe jump.
- late jump hit.
- too-early jump failure.
- timing-bucket distribution after log collection.

If expected detector hit rates are far below the collection intent, stop and
repair the detector/selector. Do not compensate by only increasing reward
weights.

## Log Naming

Use descriptive names that encode source, phase, and purpose:

- `logs/rl-transitions-retrain-p0-sanity-human-v1.ndjson`
- `logs/rl-transitions-retrain-p1-movement-human-v1.ndjson`
- `logs/rl-transitions-retrain-p2-normals-human-v1.ndjson`
- `logs/rl-transitions-retrain-p3-specials-human-v1.ndjson`
- `logs/rl-transitions-retrain-p4-defense-human-v1.ndjson`
- `logs/rl-transitions-retrain-p5-projectile-human-v1.ndjson`
- `logs/rl-transitions-retrain-p6-antiair-human-v1.ndjson`
- `logs/rl-transitions-retrain-p7-corner-human-v1.ndjson`
- `logs/rl-transitions-retrain-p8-natural-cpudemo-v1.ndjson`
- `logs/rl-transitions-retrain-p8-natural-human-v1.ndjson`
- `logs/rl-transitions-retrain-p8-onpolicy-v1.ndjson`

Do not merge unrelated collection phases into one file unless the analyzer can
recover a reliable scenario label from rows. Prefer many clear logs over one
ambiguous log.

## Global Collection Rules

- Record both correct actions and nearby wrong actions for each skill.
- Balance close, mid, and far distances.
- Record both sides of timing-sensitive choices:
  - what should be done.
  - what fails in the same state family.
- Keep training-mode HP healing out of reward with
  `--training-mode-hp-delta-mode damage-only`.
- Preserve raw transition deltas for analysis.
- Prefer engine-attributed action labels for specials and longer moves.
- Use `human-demo` for curriculum choices that must reflect expert intent.
- Use `cpu-demo` for broad natural match distribution.
- Use `remote` only after a candidate model exists and we need on-policy
  correction data.
- Keep a small amount of natural match data in every training stage so the
  model does not overfit fixed training-mode setups.

## Operator Collection Runbook

This section is the practical checklist for recording the full-retrain logs.
Keep phase logs separate. Do not append unrelated drills into the same file
just because the probe command is already running.

### Common Probe Command Shape

Run the probe server from Windows PowerShell when collecting from the MiSTer:

```powershell
python \\wsl.localhost\Ubuntu\home\olhua\src\3s-mister-arm\tools\rl_probe_server.py --host 0.0.0.0 --port 37330 --action-port 37331 --action-mode off --transition-log \\wsl.localhost\Ubuntu\home\olhua\src\3s-mister-arm\logs\<LOG_NAME>.ndjson --transition-port 37332 --learner-stats-interval-sec 10 --verbose --verbose-ping-interval 20
```

Replace `<LOG_NAME>` with the exact phase filename below.

Common MiSTer RL config:

```text
rl-network = on
rl-agent-remote-ip = 192.168.0.46
rl-agent-obs-port = 37330
rl-agent-action-port = 37331
rl-agent-delay-frames = 4
rl-agent-decision-interval = 3
rl-agent-action-hold = 3
```

Set `rl-control-source` per log:

- `human-demo` for human-controlled curriculum and natural human logs.
- `cpu-demo` for CPU-demo natural logs.
- `remote` only for on-policy candidate correction logs after a model exists.

Recommended CPU difficulty:

- Phase 1 movement: CPU `3-4`.
- Phase 8 natural CPU/human: CPU `4-5`.
- Later on-policy regression: CPU `5-6` only after the lower-difficulty
  baseline is stable.
- If only one value is available, use CPU `4` for the first reboot.

### After Every Collection

Run the general analyzer:

```bash
python3 tools/analyze_rl_transitions.py logs/<LOG_NAME>.ndjson --training-mode-hp-delta-mode damage-only --limit 20
```

Record at least:

- row count, episode count, schema version, `execution_source`, and `mode_type`.
- action distribution.
- HP delta signs.
- projectile summary, if relevant.
- engine action/outcome counts, if relevant.
- detector hit counts for the phase.

Do not train from a log until the analyzer output matches the collection
intent. If the behavior is visible during recording but not selected by the
detector, fix the detector/selector before adding more data.

### Phase 0: Sanity Logs

Purpose:

- verify schema, transition upload, action labels, HP deltas, projectile fields,
  action-start masks, and detector dry-runs before large collection.

Log files:

- `logs/rl-transitions-retrain-p0-sanity-human-v1.ndjson`
- `logs/rl-transitions-retrain-p0-sanity-cpudemo-v1.ndjson`
- `logs/rl-transitions-retrain-p0-fixed-hp-v1.ndjson`
- `logs/rl-transitions-retrain-p0-fixed-fireball-v1.ndjson`
- `logs/rl-transitions-retrain-p0-fixed-shoryuken-v1.ndjson`
- `logs/rl-transitions-retrain-p0-fixed-jump-v1.ndjson`
- `logs/rl-transitions-retrain-p0-projectile-human-v1.ndjson`

MiSTer config:

- human sanity: `rl-control-source = human-demo`.
- CPU sanity: `rl-control-source = cpu-demo`.
- fixed policy: use the probe policy/action path only for the named smoke, not
  for human-demo curriculum logs.

Collection content:

- 2-3 short human-demo free-play rounds.
- 2-3 short CPU-demo rounds.
- 300-500 rows each for `hp`, `fireball`, `shoryuken`, and `jump` fixed-policy
  smoke.
- 1K-2K projectile sanity rows with the opponent repeatedly throwing fireballs.

Allowed actions:

- free play is allowed only for sanity.
- fixed-policy logs should contain only the named policy plus unavoidable game
  state transitions.
- projectile sanity may include guard, back, jump, and mistakes.

Pass gates:

- schema is current and accepted by tooling.
- `execution_source` is correct: `human-demo` rows are `4`, `cpu-demo` rows are
  `5`, remote rows are `1`.
- projectile owner/sign semantics are plausible.
- action-start masks and action labels are populated.
- detector dry-runs hit the intentionally recorded events.

### Phase 1: Movement And Spacing

Purpose:

- teach spacing before attacks dominate the replay buffer.

Primary log:

- `logs/rl-transitions-retrain-p1-movement-human-v1.ndjson`

Optional split logs if a recording session needs to be separated:

- `logs/rl-transitions-retrain-p1-movement-approach-human-v1.ndjson`
- `logs/rl-transitions-retrain-p1-movement-retreat-human-v1.ndjson`
- `logs/rl-transitions-retrain-p1-movement-corner-human-v1.ndjson`
- `logs/rl-transitions-retrain-p1-movement-crouch-wait-human-v1.ndjson`

PowerShell probe command:

```powershell
python \\wsl.localhost\Ubuntu\home\olhua\src\3s-mister-arm\tools\rl_probe_server.py --host 0.0.0.0 --port 37330 --action-port 37331 --action-mode off --transition-log \\wsl.localhost\Ubuntu\home\olhua\src\3s-mister-arm\logs\rl-transitions-retrain-p1-movement-human-v1.ndjson --transition-port 37332 --learner-stats-interval-sec 10 --verbose --verbose-ping-interval 20
```

MiSTer config:

```text
rl-control-source = human-demo
rl-network = on
```

Collection content:

- far-to-mid forward approach.
- close-to-safe-range back retreat.
- mid-range micro-spacing.
- corner escape movement.
- crouch / stand / wait context.
- pressured spacing recovery without attacking.

Action requirements:

- Allowed: forward, back, short spacing adjustments, crouch/stand, wait,
  occasional jump out of corner or side-switch escape.
- Avoid: deliberate normals, fireball, shoryuken, tatsu, throw, repeated jump-in
  attacks, projectile drills, anti-air drills.
- If no explicit `neutral` action exists, keep no-input rows as state context
  only; do not force them into supervised action targets.

Suggested collection mix:

- agent approaches CPU/dummy: about `30%`.
- CPU/dummy approaches agent: about `40%`.
- corner/pressure recovery: about `30%`.

Pass gates:

- no HP-delta pollution.
- no projectile rows.
- no meaningful attack labels.
- forward approach target met.
- close/mid back retreat target met.
- mid micro-spacing target met.
- corner movement target met.
- crouch/wait context exists as engine state or explicit action context.

Current accepted Phase 1 source:

- `logs/rl-transitions-retrain-p1-movement-human-v1.ndjson`
  - `12,533` rows.
  - schema v6.
  - `execution_source = 4`.
  - `mode_type = 3`.
  - clean HP/projectile/attack profile.
  - movement gates passed.

### Phase 2: Basic Normals

Purpose:

- teach grounded normals and jump attacks in hit, whiff, blocked, and punished
  contexts.

Primary log:

- `logs/rl-transitions-retrain-p2-normals-human-v1.ndjson`

Optional split logs:

- `logs/rl-transitions-retrain-p2-normals-stand-human-v1.ndjson`
- `logs/rl-transitions-retrain-p2-normals-crouch-human-v1.ndjson`
- `logs/rl-transitions-retrain-p2-normals-jump-human-v1.ndjson`
- `logs/rl-transitions-retrain-p2-normals-punish-human-v1.ndjson`

PowerShell probe command:

```powershell
python \\wsl.localhost\Ubuntu\home\olhua\src\3s-mister-arm\tools\rl_probe_server.py --host 0.0.0.0 --port 37330 --action-port 37331 --action-mode off --transition-log \\wsl.localhost\Ubuntu\home\olhua\src\3s-mister-arm\logs\rl-transitions-retrain-p2-normals-human-v1.ndjson --transition-port 37332 --learner-stats-interval-sec 10 --verbose --verbose-ping-interval 20
```

MiSTer config:

```text
rl-control-source = human-demo
rl-network = on
```

Collection content:

- standing LP/MP/HP and LK/MK/HK at close, mid, and whiff ranges.
- crouching LK/MK/HK and the most useful crouching punches.
- jump-in attacks that hit.
- jump-ins that are blocked or punished.
- punish after opponent whiff.

Action requirements:

- Allowed: selected normal attacks, jump attacks, movement needed to set the
  range, and guard only when setting up blocked/punished examples.
- Avoid: specials, projectile drills, long fireball exchanges, random DP, corner
  pressure drills, throw-tech drills.
- Include intentional failures: whiff at the wrong range, blocked normal, and
  punished jump-in.

Pass gates:

- engine-attributed or input-attributed normal labels are plausible.
- hit/whiff/blocked/punished detectors select rows that match the recording.
- no special-move leakage large enough to dominate the log.
- distance buckets cover close, mid, and far/whiff contexts.

Current accepted Phase 2 source:

- `logs/rl-transitions-retrain-p2-normals-human-v1.ndjson`
  - `38,801` rows.
  - `execution_source = 4`.
  - `mode_type = 1` for `33,947` rows and `mode_type = 3` for `4,854`
    rows.
  - engine-labeled rows: `1,713`.
  - projectile active rate: `5.6%`, acceptable for a natural normals log.
  - special leakage is negligible.
  - normal coverage includes hit, whiff, and punished examples for the main
    standing, crouching, and air normals.

Current M2 candidate:

- preferred offline candidate:
  `model/dqn-retrain-m2-normals-baseline-v4c`.
- version: `206`.
- M2 v4c action set:
  movement, guard, jump-start, standing normals, crouching normals,
  `forward-hp`, and air normals; `throw` and specials are excluded.
- Important deployment condition:
  raw model evaluation no longer requires support-prior reranking. Keep
  `--dqn-valid-action-mask action-start-v1`.
- Why this candidate is preferred:
  M2 v4c was initialized from the attack-capable M2 v2 candidate, then retrained
  with the far-whiff negative log plus the new trainer movement-regression
  auxiliary loss. It internalizes the support-prior behavior enough to pass the
  M1 replay gate without support-prior while preserving normals on P2 replay.
- Validation summary without support-prior:
  - M1 replay comparison:
    `forward 63.1%`, `back 31.9%`, `air-lp 4.2%`,
    `stand-hk 0.5%`, `attack_rate 4.7%`, no collapse.
  - P2 replay comparison:
    `forward 56.4%`, `back 31.1%`, `air-lp 6.0%`,
    `crouch-lp 2.0%`, `air-hk 1.7%`, `stand-hk 1.2%`,
    `attack_rate 11.2%`, no collapse.
  - Far-whiff negative replay:
    `attack_rate 8.0%`, mostly `air-lp`; this is acceptable as a residual risk
    for M2 v4c because the primary M1/P2 gates pass, but should be watched in
    live probe and after finer distance-bucket work.
- Rejected candidates:
  - `model/dqn-retrain-m2-normals-baseline-v1`: raw model used normals too
    often in M1 movement-only states.
  - `model/dqn-retrain-m2-normals-baseline-v3`: conservative penalty reduced
    reward but did not solve movement regression.
  - `model/dqn-retrain-m2-ground-normals-baseline-v1`: excluding air normals
    caused ground normals, especially `crouch-hp`, to overgeneralize into far
    movement states.
  - `model/dqn-retrain-m2-normals-baseline-v4`: M1 attack rate dropped to
    `0.0%`, but P2 attack rate also collapsed to `0.0%`.
  - `model/dqn-retrain-m2-normals-baseline-v4b`: light M1-expand warm-start
    remained too conservative; P2 attack rate stayed `0.0%`.

#### M2 Training Recipe And Quality Gates

Goal:

- add normal-attack knowledge on top of the M1 movement baseline without
  destroying movement-only behavior.
- keep specials and throw out of M2 so Phase 3 can add specials deliberately.
- accept M2 only if it passes both a normals replay check and an M1 movement
  regression check.

Replay inputs:

- `/tmp/rl-retrain-m1-mix-70-20-10.ndjson`
  - deterministic M1 mix: Phase 1 movement `70%`, natural CPU-demo `20%`,
    natural human-demo `10%`.
- `logs/rl-transitions-retrain-p2-normals-human-v1.ndjson`
  - accepted P2 normals log.
- `logs/rl-transitions-retrain-p2-far-whiff-negative-human-v1.ndjson`
  - accepted far-whiff negative log: `13,999` rows, schema `6`,
    `execution_source = human-demo`, `mode_type = 3`, projectile active
    `0.0%`, engine outcome events `921`, all whiff/no-damage.

Accepted model:

- `model/dqn-retrain-m2-normals-baseline-v4c`.
- `--model-version 206`.
- warm-started from `model/dqn-retrain-m2-normals-baseline-v2` with exact
  action-list match, then retrained with far-whiff negative data and
  movement-regression loss.

Action set:

```text
forward,back,guard-stand,guard-crouch,
jump-forward-start,jump-neutral-start,jump-back-start,
stand-lp,stand-mp,stand-hp,stand-lk,stand-mk,stand-hk,
forward-hp,
crouch-lp,crouch-mp,crouch-hp,crouch-lk,crouch-mk,crouch-hk,
air-lp,air-mp,air-hp,air-lk,air-mk,air-hk
```

Excluded from M2:

- `throw`, because the first smoke collapsed to throw.
- fireball, shoryuken, and tatsu, because they belong to Phase 3.

Accepted training command:

```bash
python3 tools/train_dqn_learner.py /tmp/rl-retrain-m1-mix-70-20-10.ndjson logs/rl-transitions-retrain-p2-normals-human-v1.ndjson logs/rl-transitions-retrain-p2-far-whiff-negative-human-v1.ndjson --model-dir model/dqn-retrain-m2-normals-baseline-v4c --model-version 206 --init-model model/dqn-retrain-m2-normals-baseline-v2 --init-model-action-mode exact --steps 3500 --batch-size 64 --hidden-sizes 64,64 --actions forward,back,guard-stand,guard-crouch,jump-forward-start,jump-neutral-start,jump-back-start,stand-lp,stand-mp,stand-hp,stand-lk,stand-mk,stand-hk,forward-hp,crouch-lp,crouch-mp,crouch-hp,crouch-lk,crouch-mk,crouch-hk,air-lp,air-mp,air-hp,air-lk,air-mk,air-hk --learning-rate 0.0003 --gamma 0.95 --target-sync-steps 100 --dqn-target-mode double --training-mode-hp-delta-mode damage-only --training-action-source auto --reward-risk-profile all-attacks --reward-risk-window-decisions 20 --reward-attack-no-damage-cost 0.5 --reward-attack-punished-cost 1.0 --reward-jump-attack-no-damage-extra-cost 0.8 --reward-jump-attack-punished-extra-cost 1.0 --reward-guard-success-bonus 0.0 --reward-guard-success-window-decisions 6 --reward-guard-threat-max-dx 120 --reward-passive-guard-cost 0.3 --reward-far-guard-cost 0.5 --reward-spacing-target-min-dx 50 --reward-spacing-target-max-dx 120 --reward-spacing-improve-bonus 0.5 --reward-spacing-worsen-cost 0.2 --reward-spacing-maintain-bonus 0.1 --reward-spacing-threat-back-bonus 0.3 --engine-outcome-training-mode prefer-engine-action --engine-outcome-window-decisions 10 --engine-outcome-action-windows forward-hp=12 --engine-outcome-hit-bonus 1.0 --engine-outcome-no-damage-cost 0.3 --engine-outcome-punished-cost 1.0 --engine-outcome-oversample 1 --batch-sampling balanced --balanced-batch-ratios movement=0.50,normal=0.50,special=0.0 --dqn-valid-action-mask action-start-v1 --dqn-unsupported-action-regularization --dqn-unsupported-action-min-count 150 --dqn-unsupported-action-q-ceiling 0.0 --dqn-unsupported-action-loss-weight 0.05 --movement-regression-loss-weight 0.02 --movement-regression-target-q-margin 0.5 --movement-regression-far-dx-threshold 120 --movement-regression-action-groups stand-normal,crouch-normal,air-normal --epsilon 0.05 --fallback-policy back --seed 7 --log-interval 500 --eval-limit 5000 --diagnostic-top-n 12 --replay-recipe-name retrain-m2v4c-m2v2-init-far-whiff-regression --replay-recipe-base-logs logs/rl-transitions-retrain-p1-movement-human-v1.ndjson,logs/rl-transitions-retrain-p8-natural-cpudemo-v1.ndjson,logs/rl-transitions-retrain-p8-natural-human-v1.ndjson,logs/rl-transitions-retrain-p2-normals-human-v1.ndjson,logs/rl-transitions-retrain-p2-far-whiff-negative-human-v1.ndjson
```

Parameter intent:

- `--init-model model/dqn-retrain-m2-normals-baseline-v2`: start from an
  attack-capable M2 policy, then correct movement regression.
- `movement=0.50,normal=0.50`: keep M1 movement present while still sampling
  normals heavily enough.
- `reward-risk-profile all-attacks`: penalize no-damage and punished normals.
- `reward-attack-no-damage-cost 0.5` and `reward-attack-punished-cost 1.0`:
  avoid random normals in neutral/movement states.
- jump-attack extra costs `0.8/1.0`: reduce air-normal overgeneralization.
- engine outcome mode `prefer-engine-action`: use validated engine labels for
  normal outcome credit where available.
- `engine-outcome-hit-bonus 1.0`, `no-damage 0.3`, `punished 1.0`: reward
  confirmed hits without making every normal attractive.
- `movement-regression-loss-weight 0.02`: directly penalize attack Q exceeding
  movement Q in far, grounded, non-threat contexts.
- support-prior is no longer required during comparison or probe/inference for
  this M2 candidate.

Required validation commands:

```bash
python3 tools/compare_dqn_models.py /tmp/rl-retrain-m1-mix-70-20-10.ndjson --model M2v4c=model/dqn-retrain-m2-normals-baseline-v4c --limit 10000 --top-n 12 --focus-actions forward,back,guard-stand,guard-crouch,jump-forward-start,stand-mp,stand-hp,stand-mk,stand-hk,forward-hp,crouch-mp,crouch-hp,crouch-mk,crouch-hk --focus-rank-limit 3 --training-action-source auto --dqn-valid-action-mask action-start-v1
```

```bash
python3 tools/compare_dqn_models.py logs/rl-transitions-retrain-p2-normals-human-v1.ndjson --model M2v4c=model/dqn-retrain-m2-normals-baseline-v4c --limit 12000 --top-n 12 --focus-actions forward,back,guard-stand,guard-crouch,jump-forward-start,stand-mp,stand-hp,stand-mk,stand-hk,forward-hp,crouch-mp,crouch-hp,crouch-mk,crouch-hk --focus-rank-limit 3 --training-action-source auto --dqn-valid-action-mask action-start-v1
```

Quality gates:

- training must complete and publish `current.json`.
- no top-1 greedy action may exceed the `70%` collapse threshold.
- M1 replay attack rate without support-prior should stay under about `5%`.
- P2 replay attack rate without support-prior should stay in the `5%-15%`
  range; current accepted value is `11.2%`.
- M1 replay must not be dominated by normals in close/mid/far movement-only
  rows.
- P2 replay should still rank some normals in plausible contexts, while keeping
  movement/guard available.
- rejected if a raw or reranked candidate restores throw/specials, collapses to
  one normal, or pushes attack rate high on M1 movement replay.

Live/probe condition for M2:

- Probe M2 v4c with `--dqn-valid-action-mask action-start-v1`; support-prior is
  no longer required for this candidate.
- Treat live results as an M2 smoke only; M2 is not a final fighting policy and
  still lacks specials, projectile defense, anti-air, corner, and oki stages.

### Phase 3: Specials

Purpose:

- teach fireball, shoryuken, and tatsu in good and bad contexts.

Primary log:

- `logs/rl-transitions-retrain-p3-specials-human-v1.ndjson`

Optional split logs:

- `logs/rl-transitions-retrain-p3-specials-fireball-human-v1.ndjson`
- `logs/rl-transitions-retrain-p3-specials-shoryuken-human-v1.ndjson`
- `logs/rl-transitions-retrain-p3-specials-tatsu-human-v1.ndjson`

PowerShell probe command:

```powershell
python \\wsl.localhost\Ubuntu\home\olhua\src\3s-mister-arm\tools\rl_probe_server.py --host 0.0.0.0 --port 37330 --action-port 37331 --action-mode off --transition-log \\wsl.localhost\Ubuntu\home\olhua\src\3s-mister-arm\logs\rl-transitions-retrain-p3-specials-human-v1.ndjson --transition-port 37332 --learner-stats-interval-sec 10 --verbose --verbose-ping-interval 20
```

MiSTer config:

```text
rl-control-source = human-demo
rl-network = on
```

Collection content:

- fireball hits from useful range.
- fireballs that are blocked.
- fireballs that are jumped or punished.
- close-range bad fireballs.
- shoryuken anti-air hits.
- shoryuken whiffs and punished shoryukens.
- tatsu hits, blocked tatsu, and punished tatsu.

Action requirements:

- Allowed: LP/MP/HP fireball, LP/MP/HP shoryuken, LK/MK/HK tatsu, movement
  needed to set range, and occasional normals only to restore scenario flow.
- Avoid: normal-heavy training, corner/oki drills, projectile-defense timing
  drill goals, throw-tech targets.
- Record both good and bad examples for every special; do not record only
  successful specials.

Pass gates:

- engine-attributed action labels are present for specials where possible.
- long reward/risk windows capture delayed projectile and recovery punishment.
- shoryuken/tatsu whiff punish rows are visible to the analyzer.
- close bad fireball rows are distinguishable from good-range fireballs.

### Phase 4: Basic Defense

Purpose:

- teach guard, back-evade, and post-block punish behavior.

Primary log:

- `logs/rl-transitions-retrain-p4-defense-human-v1.ndjson`

Optional split logs:

- `logs/rl-transitions-retrain-p4-defense-guard-human-v1.ndjson`
- `logs/rl-transitions-retrain-p4-defense-back-evade-human-v1.ndjson`
- `logs/rl-transitions-retrain-p4-defense-post-block-punish-human-v1.ndjson`
- `logs/rl-transitions-retrain-p4-defense-wakeup-human-v1.ndjson`

PowerShell probe command:

```powershell
python \\wsl.localhost\Ubuntu\home\olhua\src\3s-mister-arm\tools\rl_probe_server.py --host 0.0.0.0 --port 37330 --action-port 37331 --action-mode off --transition-log \\wsl.localhost\Ubuntu\home\olhua\src\3s-mister-arm\logs\rl-transitions-retrain-p4-defense-human-v1.ndjson --transition-port 37332 --learner-stats-interval-sec 10 --verbose --verbose-ping-interval 20
```

MiSTer config:

```text
rl-control-source = human-demo
rl-network = on
```

Collection content:

- stand guard against high/mid attacks.
- crouch guard against low attacks.
- back-evade that makes opponent whiff.
- block then punish.
- guard jump-in.
- throw hit against agent as negative data.
- wakeup defense and meaty pressure blocks.

Action requirements:

- Allowed: guard-stand, guard-crouch, back, post-block punish normal/special,
  wakeup block, occasional reversal as positive/negative examples.
- Avoid: turning the log into a normal offense drill, projectile timing drill,
  random DP spam, or natural free play.
- Throw-tech rows are optional until labels are proven reliable.

Pass gates:

- guard/back success selectors hit the intended rows.
- passive/far guard rows are not overrepresented.
- post-block punish has delayed credit evidence.
- wakeup/oki defense rows are identifiable.

### Phase 5: Projectile Defense

Purpose:

- explicitly teach when to guard, back, wait, or jump against incoming
  fireballs.

Primary log:

- `logs/rl-transitions-retrain-p5-projectile-human-v1.ndjson`

Existing usable targeted log:

- `logs/rl-transitions-training-human-demo-v55.ndjson`
  - schema v6.
  - `execution_source = 4`.
  - `mode_type = 3`.
  - targeted projectile-defense human-demo data.

Optional split logs:

- `logs/rl-transitions-retrain-p5-projectile-close-human-v1.ndjson`
- `logs/rl-transitions-retrain-p5-projectile-mid-human-v1.ndjson`
- `logs/rl-transitions-retrain-p5-projectile-far-human-v1.ndjson`

PowerShell probe command:

```powershell
python \\wsl.localhost\Ubuntu\home\olhua\src\3s-mister-arm\tools\rl_probe_server.py --host 0.0.0.0 --port 37330 --action-port 37331 --action-mode off --transition-log \\wsl.localhost\Ubuntu\home\olhua\src\3s-mister-arm\logs\rl-transitions-retrain-p5-projectile-human-v1.ndjson --transition-port 37332 --learner-stats-interval-sec 10 --verbose --verbose-ping-interval 20
```

MiSTer config:

```text
rl-control-source = human-demo
rl-network = on
```

Collection content:

- close fireball cue: fireball is about to hit, record guard/back and some
  jump-hit negative data.
- mid fireball cue: readable fireball, record guard, wait, delayed jump, and
  safe jump examples.
- far fireball cue: just released fireball, record wait/walk-forward and only
  jump-forward punish when opponent is still in recovery.

Action requirements:

- Allowed: guard-stand, guard-crouch, back, wait/crouch, walk-forward,
  jump-forward punish, jump-neutral safe jump, intentional bad jump examples.
- Avoid: blanket "never jump at 31-48"; outcome depends on opponent recovery.
- Avoid: treating all `13-22` as safe-jump; it is mixed and often risky.
- Keep a few opponent jump-in rows in the regression set so projectile defense
  does not become global guard bias.

Pass gates:

- analyzer splits rows into `0-6`, `7-12`, `13-22`, `23-30`, `31-48`, and
  `49+`.
- `0-12` has clean guard/back examples and jump-hit negatives.
- `23-30` has clean safe-jump / jump-forward punish examples.
- `31-48` separates too-early jump failures from valid fireball-recovery
  punish examples.

### Phase 6: Anti-Air And Jump Defense

Purpose:

- teach responses to opponent jump-ins and prevent projectile-defense training
  from becoming a global guard policy.

Primary log:

- `logs/rl-transitions-retrain-p6-antiair-human-v1.ndjson`

Optional split logs:

- `logs/rl-transitions-retrain-p6-antiair-shoryuken-human-v1.ndjson`
- `logs/rl-transitions-retrain-p6-antiair-normal-human-v1.ndjson`
- `logs/rl-transitions-retrain-p6-jump-defense-human-v1.ndjson`

PowerShell probe command:

```powershell
python \\wsl.localhost\Ubuntu\home\olhua\src\3s-mister-arm\tools\rl_probe_server.py --host 0.0.0.0 --port 37330 --action-port 37331 --action-mode off --transition-log \\wsl.localhost\Ubuntu\home\olhua\src\3s-mister-arm\logs\rl-transitions-retrain-p6-antiair-human-v1.ndjson --transition-port 37332 --learner-stats-interval-sec 10 --verbose --verbose-ping-interval 20
```

MiSTer config:

```text
rl-control-source = human-demo
rl-network = on
```

Collection content:

- shoryuken anti-air success.
- crouch HP / stand HP anti-air success.
- guarding jump-ins.
- bad anti-air whiffs that get punished.
- grounded states where shoryuken should not be chosen.

Action requirements:

- Allowed: anti-air shoryuken, anti-air normals, jump-in guard, movement to set
  jump range, explicit bad anti-air attempts.
- Avoid: projectile drills, normal offense drill, random DP outside jump-in
  context except as negative examples.

Pass gates:

- opponent airborne/jump-in detector is reliable.
- anti-air success and bad-DP punish selectors match visual intent.
- M5 projectile model/regression does not rank guard for all opponent jump-ins.

### Phase 7: Corner, Pressure, And Oki

Purpose:

- teach corner trap behavior, pressure defense, escape, and wakeup/oki choices.

Primary log:

- `logs/rl-transitions-retrain-p7-corner-human-v1.ndjson`

Optional split logs:

- `logs/rl-transitions-retrain-p7-corner-defense-human-v1.ndjson`
- `logs/rl-transitions-retrain-p7-corner-escape-human-v1.ndjson`
- `logs/rl-transitions-retrain-p7-oki-human-v1.ndjson`
- `logs/rl-transitions-retrain-p7-wakeup-human-v1.ndjson`

PowerShell probe command:

```powershell
python \\wsl.localhost\Ubuntu\home\olhua\src\3s-mister-arm\tools\rl_probe_server.py --host 0.0.0.0 --port 37330 --action-port 37331 --action-mode off --transition-log \\wsl.localhost\Ubuntu\home\olhua\src\3s-mister-arm\logs\rl-transitions-retrain-p7-corner-human-v1.ndjson --transition-port 37332 --learner-stats-interval-sec 10 --verbose --verbose-ping-interval 20
```

MiSTer config:

```text
rl-control-source = human-demo
rl-network = on
```

Collection content:

- corner guard.
- corner back failure against the stage edge.
- timed corner escape.
- pressure defense without random DP.
- post-block escape or punish.
- agent knocks opponent down, then meaty/throw/retreat oki choice.
- agent wakes up under pressure, then block/reversal/escape choice.

Action requirements:

- Allowed: guard, back, forward escape, jump escape, throw/meaty/retreat oki,
  wakeup block, occasional reversal positive/negative examples.
- Avoid: only walking backward, only random DP, turning the log into normal
  offense or projectile drill.

Pass gates:

- corner distance buckets show near-corner and tight-corner coverage.
- corner-back negative examples are present.
- escape and post-block punish examples are detectable.
- wakeup/oki rows are explicitly represented.

### Phase 8: Natural Match Integration

Purpose:

- restore normal match distribution after curriculum phases and collect
  on-policy correction data once candidate models exist.

Log files:

- `logs/rl-transitions-retrain-p8-natural-cpudemo-v1.ndjson`
- `logs/rl-transitions-retrain-p8-natural-human-v1.ndjson`
- `logs/rl-transitions-retrain-p8-natural-structured-v1.ndjson`
- `logs/rl-transitions-retrain-p8-onpolicy-v1.ndjson`

CPU-demo PowerShell probe command:

```powershell
python \\wsl.localhost\Ubuntu\home\olhua\src\3s-mister-arm\tools\rl_probe_server.py --host 0.0.0.0 --port 37330 --action-port 37331 --action-mode off --transition-log \\wsl.localhost\Ubuntu\home\olhua\src\3s-mister-arm\logs\rl-transitions-retrain-p8-natural-cpudemo-v1.ndjson --transition-port 37332 --learner-stats-interval-sec 10 --verbose --verbose-ping-interval 20
```

Human-demo PowerShell probe command:

```powershell
python \\wsl.localhost\Ubuntu\home\olhua\src\3s-mister-arm\tools\rl_probe_server.py --host 0.0.0.0 --port 37330 --action-port 37331 --action-mode off --transition-log \\wsl.localhost\Ubuntu\home\olhua\src\3s-mister-arm\logs\rl-transitions-retrain-p8-natural-human-v1.ndjson --transition-port 37332 --learner-stats-interval-sec 10 --verbose --verbose-ping-interval 20
```

On-policy probe command:

```powershell
python \\wsl.localhost\Ubuntu\home\olhua\src\3s-mister-arm\tools\rl_probe_server.py --host 0.0.0.0 --port 37330 --action-port 37331 --action-mode valid --policy dqn --model-dir \\wsl.localhost\Ubuntu\home\olhua\src\3s-mister-arm\model\<MODEL_DIR> --transition-log \\wsl.localhost\Ubuntu\home\olhua\src\3s-mister-arm\logs\rl-transitions-retrain-p8-onpolicy-v1.ndjson --transition-port 37332 --learner-stats-interval-sec 10 --verbose --verbose-ping-interval 20
```

MiSTer config:

```text
rl-control-source = cpu-demo      # for natural CPU-demo
rl-control-source = human-demo    # for natural human-demo
rl-control-source = remote        # for on-policy candidate logs
rl-network = on
```

Collection content:

- CPU-demo normal matches.
- serious human-demo normal matches.
- structured mixed natural rounds such as neutral, fireball/DP, defense, and
  corner pressure, each named or split clearly.
- remote/on-policy candidate matches after each model needs correction.

Action requirements:

- CPU-demo: no human restrictions; let the CPU create broad natural match
  distribution.
- Human-demo natural: normal serious play is allowed, including all moves, but
  do not intentionally drill only one skill.
- On-policy: let the model play normally; collect its real mistakes.
- Keep projectile/anti-air/corner drills out of natural logs unless they are in
  a clearly named structured natural file.

Phase 1 / M1 natural mix:

- keep natural logs separate from Phase 1 curriculum logs.
- suggested M1 replay mix:
  - `70%` Phase 1 movement human-demo.
  - `20%` natural CPU-demo.
  - `10%` natural human-demo.
- do not use `logs/rl-transitions-training-human-demo-v55.ndjson` for M1; it is
  Phase 5 projectile curriculum data.

Current M1 candidate:

- combined replay:
  `/tmp/rl-retrain-m1-mix-70-20-10.ndjson`.
- deterministic mix seed: `7`.
- mix rows:
  - Phase 1 movement:
    `logs/rl-transitions-retrain-p1-movement-human-v1.ndjson`, `12,533`
    rows, `70.0%`.
  - Phase 8 natural CPU-demo:
    `logs/rl-transitions-retrain-p8-natural-cpudemo-v1.ndjson`, sampled
    `3,581` rows, `20.0%`.
  - Phase 8 natural human-demo:
    `logs/rl-transitions-retrain-p8-natural-human-v1.ndjson`, sampled `1,790`
    rows, `10.0%`.
- model:
  `model/dqn-retrain-m1-movement-baseline-v1`.
- M1 uses a movement-only action set:
  `forward`, `back`, `guard-stand`, `guard-crouch`, `jump-forward-start`,
  `jump-neutral-start`, `jump-back-start`.
- Do not use this as a fighting policy yet. It is only the first movement and
  spacing base before Phase 2 attacks are added.
- Validation summary:
  - training experiences: `8,269`.
  - training greedy top action: `forward 51.6%`, below the `70%` collapse gate.
  - natural-log greedy distribution:
    `back 44.6%`, `guard-crouch 26.2%`, `forward 25.9%`,
    `jump-forward-start 1.8%`.
  - natural close non-attacking rows prefer guard/back more often:
    `guard-crouch 64.5%`, `back 16.7%`, `forward 15.7%`.
  - Phase 1 curriculum-only rows still skew forward:
    `forward 58.1%`, `guard-crouch 23.1%`, `back 15.0%`.
    Treat this as acceptable for M1 but re-check after Phase 2 and before any
    live promotion.

Pass gates:

- CPU-demo, human-demo, and on-policy rows are separable by file and
  `execution_source`.
- natural logs do not drown the curriculum when training M1-M4.
- on-policy logs are used for correction, not as the only data source.

## Phase 0: Schema And Label Sanity

Purpose:

- confirm the collection path, labels, HP deltas, projectile fields, and action
  masks are healthy before collecting large logs.

Collection setup:

- short human-demo versus CPU.
- short cpu-demo.
- fixed-policy smoke passes for representative actions.
- projectile smoke with the opponent repeatedly throwing fireballs.

Targets:

| Source | Scenario | Target |
| --- | --- | ---: |
| human-demo | short free play | 2-3 rounds |
| cpu-demo | CPU controls the agent side | 2-3 rounds |
| fixed policy | `hp`, `fireball`, `shoryuken`, `jump` | 300-500 rows each |
| human-demo | projectile sanity | 1K-2K rows |

Pass gates:

- `execution_source` is correct.
- `input_*` and `engine_*` labels are plausible.
- projectile fields have correct owner/sign semantics:
  - opponent projectile in front and incoming has `owner=2`, `rel_x > 0`,
    `vel_x < 0`.
- action-start flags are populated.
- damage-only training-mode replay does not turn healing into positive reward.
- detector dry-runs produce plausible counts for the intentionally recorded
  scenarios. If a collected skill is visible in the log but not detected, fix
  the detector before training on that phase.

## Phase 1: Movement And Spacing

Purpose:

- teach basic forward/back movement, spacing, and corner escape before attacks
  dominate the value function.

Collection setup:

- training mode.
- human-demo controls the agent.
- opponent dummy or CPU walks forward slowly and does not intentionally attack.
- no deliberate attacks from the agent.

Targets:

| Skill | Target effective experiences |
| --- | ---: |
| forward approach from far to mid | 800-1200 |
| back retreat from close to safe range | 800-1200 |
| mid-range micro-spacing | 1000-1500 |
| corner escape movement | 500-800 |
| crouch or wait context | 300-500 |
| pressured spacing recovery | 800-1200 |

Notes:

- if the action set has no explicit `neutral` action, do not treat no-input
  rows as a supervised action target. Keep them as state context only.
- training should not rely on HP delta alone. Use spacing reward and, if needed,
  movement BC or margin loss.

## Phase 2: Basic Normals

Purpose:

- teach grounded normals and jump attacks with hit, whiff, blocked, and
  punished outcomes.

Collection setup:

- training mode.
- human-demo controls the agent.
- opponent alternates between standing, guarding, and walking forward.

Targets:

| Skill family | Target effective experiences |
| --- | ---: |
| `stand-lp`, `stand-mp`, `stand-hp` | 400-700 each |
| `crouch-lk`, `crouch-mk`, `crouch-hk` | 400-700 each |
| hit examples per main normal | at least 150 |
| whiff examples per main normal | at least 150 |
| blocked examples per main normal | at least 100 |
| jump-in attack success | 600-1000 |
| jump-in blocked or punished | 300-500 |
| punish after opponent whiff | 500-800 |

Training notes:

- use HP delta and validated engine outcomes.
- add hit bonus, whiff cost, and punished cost.
- keep valid-action mask enabled.

## Phase 3: Specials

Purpose:

- teach fireball, shoryuken, and tatsu in both good and bad contexts.

Collection setup:

- training mode and some versus CPU.
- human-demo controls the agent.
- opponent behavior changes per scenario.

Targets:

| Scenario | Target effective experiences |
| --- | ---: |
| fireball hit from good range | 600-900 |
| fireball blocked | 400-700 |
| fireball jumped or punished | 300-600 |
| close-range bad fireball punished | 300-500 |
| shoryuken anti-air hit | 500-800 |
| shoryuken whiff punished | 400-700 |
| tatsu hit | 300-600 |
| tatsu blocked or punished | 300-600 |

Training notes:

- prefer engine-attributed action labels for specials.
- use longer reward/risk windows for projectile and long-animation moves.
- keep strong risk costs for shoryuken and tatsu whiffs.

## Phase 4: Basic Defense

Purpose:

- teach guard, back-evade, and post-block punish behavior.

Collection setup:

- training mode.
- opponent attacks with simple normals, jump-ins, throws, and fireballs.
- human-demo controls the agent.

Targets:

| Defensive skill | Target effective experiences |
| --- | ---: |
| `guard-stand` success | 700-1000 |
| `guard-crouch` success | 500-800 |
| post-guard punish | 600-900 |
| back evade into opponent whiff | 500-800 |
| guard jump-in | 400-700 |
| throw hit against agent as negative data | 200-400 |
| throw tech, only if labels are reliable | 200-400 |
| wakeup defense after agent knockdown | 300-500 |
| wakeup reversal/no-reversal negative mix | 200-400 |
| meaty pressure blocked on wakeup | 300-500 |

Training notes:

- keep guard success bonus.
- keep passive/far guard cost, but do not make it so large that guard cannot
  win in real threats.
- use delayed credit for post-block punish.
- include wakeup/oki rows here or in Phase 7; do not leave knockdown pressure
  entirely to natural match data.

## Phase 5: Projectile Defense Curriculum

Purpose:

- explicitly teach when to guard, back, wait, or jump against incoming
  opponent fireballs.

This is the most important controlled data phase. It must not be replaced by
free-form gameplay.

Collection setup:

- training mode.
- opponent repeatedly throws LP, MP, and HP fireballs.
- human-demo controls the agent.
- collect by visual cue, not by trying to target exact `time_to_self` values
  during play. Split into exact buckets after collection with the analyzer.

Operator-facing visual cues:

| Visual cue during recording | Approximate `time_to_self` | Recording intent |
| --- | --- | --- |
| fireball is very close / about to hit | about `0-12` | guard/back, do not jump |
| fireball is mid-screen / readable | about `13-30` | mix guard, wait, delayed jump, and safe jump |
| fireball was just released / still far | about `31-48+` | wait, walk-forward, or jump-forward only if opponent is still punishable |

Post-collection analysis must still split the log into the five `time_to_self`
buckets below. If a bucket is underrepresented, collect another targeted visual
cue pass.

Targets:

| `time_to_self` bucket | Desired behavior | Target effective experiences |
| --- | --- | ---: |
| `0-6` | `guard-stand` / `guard-crouch` success | 400-600 |
| `0-6` | `back` escape success | 150-250 |
| `0-6` | jump gets hit, negative data | 80-150 |
| `7-12` | guard/back success | 500-800 |
| `7-12` | rare clean jump only when truly safe | 100-200 |
| `7-12` | jump gets hit, negative data | 80-150 |
| `13-22` | guard, wait, or delayed jump setup | 400-700 |
| `13-22` | jump-forward punish only if opponent is still in fireball recovery | 150-300 |
| `13-22` | early jump gets hit, negative data | 100-200 |
| `23-30` | safe jump or jump-forward punish | 600-900 |
| `23-30` | jump blocked or mistimed, negative data | 100-200 |
| `31-48` | wait, walk-forward, or later guard | 300-600 |
| `31-48` | jump-forward punish if opponent is still in fireball recovery | 300-600 |
| `31-48` | too-early jump failure | 150-250 |

Current timing lesson from V61/V62:

- `0-12`: prefer guard/back.
- `13-22`: still risky. Do not label this as a universal safe-jump window, but
  do keep jump-forward punish examples when the opponent is still in fireball
  recovery.
- `23-30`: current best live safe-jump window in V61/V62 logs.
- `31-48`: V61/V62 exposed many too-early jump failures, but this bucket is not
  globally "never jump." The correct label depends on whether the opponent is
  still in fireball recovery and punishable.

Important unresolved feature:

- the real split for `20-48` is not only projectile timing; it is opponent
  actionability. A future schema/detector should expose or infer
  `obs_opp_can_act` / fireball recovery from existing opponent routine/action
  fields. Until then, do not use a blanket "no jump in 31-48" training target.

Training notes:

- use projectile batch group.
- use timing group margin only with selectors that match the intended labels:
  - defense group wins for `0-12`.
  - `13-22` is mixed and should be filtered by recovery/outcome.
  - jump-forward punish should be allowed across `23-48` when the opponent is
    still in fireball recovery.
  - recovered-opponent `31-48` early jumps remain negative data.
- keep a small policy-time prior for bootstrap if needed.
- avoid hard masking jump, because the safe jump window must remain available.
- mix a small set of opponent jump-in rows into the M5 regression set so
  projectile defense does not turn into a global guard policy.

## Phase 6: Anti-Air And Jump Defense

Purpose:

- prevent the model from only learning projectile defense while ignoring
  opponent jump-ins.

Collection setup:

- training mode and short versus CPU.
- opponent repeatedly jumps in or approaches into jump range.
- human-demo controls the agent.

Targets:

| Scenario | Target effective experiences |
| --- | ---: |
| shoryuken anti-air success | 500-800 |
| `crouch-hp` / `stand-hp` anti-air success | 400-700 |
| guard jump-in | 400-700 |
| bad anti-air whiff punished | 200-400 |
| ground states where shoryuken should not be chosen | 300-500 |

Training notes:

- use anti-air margin or BC only after labels are visually validated.
- include negative DP examples so shoryuken does not become the universal
  answer.
- treat Phase 6 as the required patch after Phase 5, not as optional polish.
  If M5 starts ranking guard for opponent jump-ins, run Phase 6 immediately
  before collecting more projectile rows.

## Phase 7: Corner And Pressure

Purpose:

- teach behavior that free-form logs often underrepresent: being trapped,
  blocking, escaping, and not walking backward forever.

Collection setup:

- training mode and short versus CPU.
- start near corners when possible.
- human-demo controls the agent.

Targets:

| Scenario | Target effective experiences |
| --- | ---: |
| corner guard | 500-800 |
| corner back is blocked by edge, negative data | 300-500 |
| timed corner escape | 500-800 |
| pressure defense without random DP | 300-500 |
| post-block escape or punish | 500-800 |
| agent knocks opponent down, then meaty/throw/retreat oki choice | 500-800 |
| agent wakes up under pressure, then block/reversal/escape choice | 500-800 |

Training notes:

- use corner position reward carefully.
- keep general movement replay mixed in so the model does not treat back as
  always bad.
- oki/wakeup should be explicit curriculum data, not only natural match data.

## Phase 8: Natural Match Integration

Purpose:

- restore natural state distribution and combine all skills into real matches.

Collection setup:

- CPU-demo normal matches.
- human-demo normal matches.
- remote/on-policy matches after each candidate model.

Targets:

| Source | Target raw rows |
| --- | ---: |
| high-quality CPU-demo normal matches | about 10K |
| serious human-demo normal matches | about 10K |
| structured mixed natural matches | about 10K |
| remote/on-policy candidate logs | 20K-50K per correction loop |

Training notes:

- do not let natural match data drown the curriculum.
- use source ratios and, when available, log-level boosts for targeted logs.
- use on-policy logs for the model's real mistakes, not as the only data
  source.
- prefer higher-density natural data over low-quality volume. A useful 30K-row
  natural set should be split across CPU-demo, serious human-demo, and
  semi-structured theme rounds such as neutral, fireball/DP, defense, and
  corner pressure.

## Training Schedule

Use cumulative warm-start training. Do not train each phase in isolation and
discard the earlier data.

Recommended schedule:

1. `M1`: Phase 1 plus a small amount of Phase 8 natural data.
2. `M2`: `M1` data plus Phase 2.
3. `M3`: `M1-M2` data plus Phase 3.
4. `M4`: `M1-M3` data plus Phase 4.
5. `M5`: `M1-M4` data plus Phase 5 projectile curriculum.
6. `M6`: `M1-M5` data plus Phase 6 anti-air.
7. `M7`: `M1-M6` data plus Phase 7 corner/pressure.
8. `M8`: all curriculum plus Phase 8 natural and on-policy correction data.

Suggested source mix:

Early:

- curriculum: `70%`.
- natural CPU/human: `30%`.

Middle:

- curriculum: `50%`.
- natural CPU/human: `35%`.
- on-policy: `15%`.

Late:

- on-policy: `45%`.
- human correction: `30%`.
- curriculum replay: `15%`.
- CPU-demo: `10%`.

## Regression Checks Per Model

Every candidate model needs these checks before live promotion:

- movement:
  - forward/back/spacing distribution by distance bucket.
- attacks:
  - hit/whiff/punished ranks for normals.
- specials:
  - fireball, shoryuken, and tatsu risk behavior.
- defense:
  - guard/back success rows rank defensive actions.
- projectile:
  - `time_to_self` bucket top-1 distribution.
  - `0-12` does not mostly jump.
  - `23-30` preserves safe jump.
  - `23-48` allows jump-forward punish when opponent fireball recovery is
    still punishable.
  - recovered-opponent `31-48` does not jump too early.
- anti-air:
  - opponent airborne/jump-in response ranks anti-air, movement, or a validated
    guard response; it must not become a generic guard-only answer.
- oki:
  - wakeup defense and post-knockdown pressure do not collapse to random DP or
    passive guard.
- global:
  - no single greedy action collapse.
  - non-projectile behavior does not become global guard/back bias.

## Minimum Viable Reboot

If the full plan is too large, collect this first:

| Phase | Minimum effective experiences |
| --- | ---: |
| Phase 1 movement | 5K |
| Phase 2 normals | 8K |
| Phase 3 specials | 8K |
| Phase 4 defense | 6K |
| Phase 5 projectile | 10K |
| Phase 8 natural matches | 30K, split into CPU-demo/human-demo/structured mixed |

Total minimum:

- about `60K` effective experiences.

This is enough to train a more coherent base model than the current free-form
gameplay logs, because each row family is intentionally collected to teach a
specific behavior.

## Immediate Next Collection Step

Phase 1/M1 and Phase 2/M2 are now complete enough to move on. The next
collection phase is Phase 3 specials:
`logs/rl-transitions-retrain-p3-specials-human-v1.ndjson`.

Before collecting the next phase:

1. keep `model/dqn-retrain-m2-normals-baseline-v2` as the current M2 candidate,
   with support-prior enabled for evaluation/probes.
2. collect `logs/rl-transitions-retrain-p3-specials-human-v1.ndjson`.
3. include good and bad examples for fireball, shoryuken, and tatsu.
4. keep the Phase 1/P8 M1 replay and Phase 2 normals log in the cumulative
   training mix.
5. train `M3` after analyzer and detector checks pass.
