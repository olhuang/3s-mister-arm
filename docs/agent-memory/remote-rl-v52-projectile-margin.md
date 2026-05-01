# Remote RL V52 Projectile Expert Margin Reference

Date: 2026-05-01

Status:
- V52 is the first offline DQN candidate that fixes the original
  anti-fireball failure mode: safe human jump responses no longer lose the Q
  ranking to `shoryuken-hp`.
- V52 is a validated offline and live-probe candidate, not yet the default
  promoted remote actor.

Use this document when revisiting:
- `projectile-response-v3`
- V52 / V53 anti-fireball training
- projectile expert margin loss
- safe-jump versus Shoryuken regression checks
- projectile timing bucket experiments

## Problem

V46 and V47 showed that reward shaping and replay oversampling were not enough
to make the DQN choose jump against incoming fireballs. The human demo rows had
safe jump labels, but the trained Q network still ranked `shoryuken-hp` or
other competing actions above jump on the same projectile observations.

The important diagnosis was:
- TD reward can raise `Q(s, jump)`.
- It does not explicitly push down `Q(s, shoryuken-hp)` or other competitors.
- With function approximation and sparse full-action replay, those competitor
  heads can stay overestimated.

The fix was to add a valid-action-masked large-margin classification objective
for safe human projectile jump rows.

## V52 Model Artifact

Model:
- `model/dqn-projectile-schema-v5-full-actions-v52-margin-batch32-jumpgroup-candidate`

Current manifest:
- `model/dqn-projectile-schema-v5-full-actions-v52-margin-batch32-jumpgroup-candidate/current.json`

Source replay:
- `logs/rl-transitions-human-demo-projectile-schema-v5-smoke-4-3-3.ndjson`

Manifest summary:
- model version: `52`
- source: `offline-dqn`
- action set version: `5`
- action count: `36`
- rows read: `59117`
- DQN experiences: `30844`
- epsilon: `0.05`
- fallback policy: `hp`

## Training Recipe

Core DQN:
- `--steps 3000`
- `--batch-size 64`
- `--hidden-sizes 64,64`
- `--learning-rate 0.001`
- `--gamma 0.95`
- `--target-sync-steps 200`
- `--dqn-target-mode standard`
- `--training-action-source auto`
- `--dqn-valid-action-mask action-start-v1`
- `--dqn-unsupported-action-regularization`
- `--epsilon 0.05`
- `--fallback-policy hp`
- `--seed 7`

Balanced batch sampling:
- `--batch-sampling balanced`
- `--balanced-batch-ratios movement=0.25,normal=0.45,special=0.30`
- actual target counts per 64-row batch:
  - movement: `16`
  - normal: `29`
  - special: `19`

Risk shaping:
- `--reward-risk-profile all-attacks`
- `--reward-risk-window-decisions 15`
- `--reward-attack-no-damage-cost 0.3`
- `--reward-attack-punished-cost 1.0`
- `--reward-shoryuken-no-damage-extra-cost 0.0`
- `--reward-shoryuken-punished-extra-cost 0.5`
- `--reward-jump-attack-no-damage-extra-cost 0.0`
- `--reward-jump-attack-punished-extra-cost 0.0`

Guard and spacing shaping:
- `--reward-guard-success-bonus 0.0`
- `--reward-guard-success-window-decisions 6`
- `--reward-guard-threat-max-dx 120`
- `--reward-passive-guard-cost 0.4`
- `--reward-far-guard-cost 0.6`
- `--reward-spacing-target-min-dx 50`
- `--reward-spacing-target-max-dx 120`
- `--reward-spacing-improve-bonus 0.5`
- `--reward-spacing-worsen-cost 0.2`
- `--reward-spacing-maintain-bonus 0.1`
- `--reward-spacing-threat-back-bonus 0.3`

Projectile response shaping:
- `--reward-projectile-response-profile incoming-v1`
- `--reward-projectile-response-window-decisions 12`
- `--reward-projectile-threat-min-time-to-self 2`
- `--reward-projectile-threat-max-time-to-self 48`
- `--reward-projectile-threat-max-dx 240`
- `--reward-projectile-threat-max-abs-y 96`
- `--reward-projectile-close-max-dx 96`
- `--reward-projectile-safe-jump-bonus 2.0`
- `--reward-projectile-late-jump-hit-cost 1.5`
- `--reward-projectile-close-back-success-bonus 0.6`
- `--reward-projectile-close-guard-success-bonus 0.8`
- `--reward-projectile-back-escape-min-dx-delta 8`

Projectile replay oversampling:
- `--projectile-response-safe-jump-oversample 10`
- `--projectile-response-late-jump-hit-oversample 4`
- `--projectile-response-close-back-oversample 3`
- `--projectile-response-close-guard-oversample 3`

Projectile expert margin:
- `--projectile-expert-margin-loss`
- `--projectile-expert-margin 0.1`
- `--projectile-expert-margin-weight 1.0`
- `--projectile-expert-margin-batch-size 32`
- `--projectile-expert-margin-equivalent-jump-actions`
- `--projectile-expert-margin-valid-action-mask action-start-v1`

Engine outcome training:
- `--engine-outcome-training-mode prefer-engine-action`
- `--engine-outcome-window-decisions 15`
- `--engine-outcome-action-windows fireball-lp=45,fireball-mp=45,fireball-hp=45,tatsu-lk=25,tatsu-mk=25,tatsu-hk=25,throw=8`
- `--engine-outcome-hit-bonus 1.0`
- `--engine-outcome-no-damage-cost 0.2`
- `--engine-outcome-punished-cost 1.0`
- `--engine-outcome-oversample 1`
- `--engine-outcome-action-oversamples fireball-lp=4,fireball-mp=4,fireball-hp=4,shoryuken-lp=4,shoryuken-mp=5,shoryuken-hp=6,tatsu-lk=6,tatsu-mk=6,tatsu-hk=6,throw=8`

## Repro Command

```bash
python3 tools/train_dqn_learner.py logs/rl-transitions-human-demo-projectile-schema-v5-smoke-4-3-3.ndjson --model-dir model/dqn-projectile-schema-v5-full-actions-v52-margin-batch32-jumpgroup-candidate --model-version 52 --steps 3000 --batch-size 64 --hidden-sizes 64,64 --learning-rate 0.001 --gamma 0.95 --target-sync-steps 200 --reward-scale 0.01 --reward-risk-profile all-attacks --reward-risk-window-decisions 15 --reward-attack-no-damage-cost 0.3 --reward-attack-punished-cost 1.0 --reward-shoryuken-no-damage-extra-cost 0.0 --reward-shoryuken-punished-extra-cost 0.5 --reward-jump-attack-no-damage-extra-cost 0.0 --reward-jump-attack-punished-extra-cost 0.0 --reward-guard-success-bonus 0.0 --reward-guard-success-window-decisions 6 --reward-guard-threat-max-dx 120 --reward-passive-guard-cost 0.4 --reward-far-guard-cost 0.6 --reward-spacing-target-min-dx 50 --reward-spacing-target-max-dx 120 --reward-spacing-improve-bonus 0.5 --reward-spacing-worsen-cost 0.2 --reward-spacing-maintain-bonus 0.1 --reward-spacing-threat-back-bonus 0.3 --reward-projectile-response-profile incoming-v1 --reward-projectile-response-window-decisions 12 --reward-projectile-threat-min-time-to-self 2 --reward-projectile-threat-max-time-to-self 48 --reward-projectile-threat-max-dx 240 --reward-projectile-threat-max-abs-y 96 --reward-projectile-close-max-dx 96 --reward-projectile-safe-jump-bonus 2.0 --reward-projectile-late-jump-hit-cost 1.5 --reward-projectile-close-back-success-bonus 0.6 --reward-projectile-close-guard-success-bonus 0.8 --reward-projectile-back-escape-min-dx-delta 8 --projectile-response-safe-jump-oversample 10 --projectile-response-late-jump-hit-oversample 4 --projectile-response-close-back-oversample 3 --projectile-response-close-guard-oversample 3 --projectile-expert-margin-loss --projectile-expert-margin 0.1 --projectile-expert-margin-weight 1.0 --projectile-expert-margin-batch-size 32 --projectile-expert-margin-equivalent-jump-actions --projectile-expert-margin-valid-action-mask action-start-v1 --engine-outcome-training-mode prefer-engine-action --engine-outcome-window-decisions 15 --engine-outcome-action-windows fireball-lp=45,fireball-mp=45,fireball-hp=45,tatsu-lk=25,tatsu-mk=25,tatsu-hk=25,throw=8 --engine-outcome-hit-bonus 1.0 --engine-outcome-no-damage-cost 0.2 --engine-outcome-punished-cost 1.0 --engine-outcome-oversample 1 --engine-outcome-action-oversamples fireball-lp=4,fireball-mp=4,fireball-hp=4,shoryuken-lp=4,shoryuken-mp=5,shoryuken-hp=6,tatsu-lk=6,tatsu-mk=6,tatsu-hk=6,throw=8 --batch-sampling balanced --balanced-batch-ratios movement=0.25,normal=0.45,special=0.30 --dqn-target-mode standard --dqn-valid-action-mask action-start-v1 --dqn-unsupported-action-regularization --epsilon 0.05 --fallback-policy hp --seed 7 --log-interval 200 --eval-limit 5000
```

Equivalent auto-retrain preset:
- `tools/rl_auto_retrain.py --reward-preset projectile-response-v3`

## Why Jump-Group Equivalence Matters

V51 used the same margin batch idea, but forced the exact human jump direction
to beat all other actions. That made `jump-forward-start`,
`jump-neutral-start`, and `jump-back-start` compete against each other.

For anti-fireball defense the behavioral objective is not exact directional
imitation. The first-order objective is:
- any valid jump-start should beat non-jump competitors on clean safe-jump
  expert rows.

V52 therefore treats all jump-start variants as an equivalent expert group
when applying projectile expert margin:
- expert group:
  - `jump-forward-start`
  - `jump-neutral-start`
  - `jump-back-start`
- competitor group:
  - valid non-jump actions under `action-start-v1`

This resolves the original Shoryuken blocker without making jump directions
fight each other.

## Offline Findings

Baseline failure:
- V47 incoming projectile + jump-start-allowed:
  - `shoryuken-hp`: `85.6%`
  - jump top-1: `0.0%`

V48:
- normal replay batch only
- margin weight `0.05`
- too weak; safe expert top-1 stayed at `0/1830`

V50:
- normal replay batch only
- margin weight `5.0`
- direction was right, but still under-sampled:
  - safe expert top-1: `120/1830`
  - mean gap: `0.044`

V51:
- margin weight `1.0`
- expert margin batch size `32`
- exact action margin
- made jump viable but exposed jump-direction conflicts:
  - safe-jump unique rows any-jump top-1: `151/181` (`83.4%`)
  - remaining blockers included `tatsu-mk` and `shoryuken-hp`

V52:
- margin weight `1.0`
- expert margin batch size `32`
- jump-start equivalence
- model metadata safe-jump group Q-gap:
  - rows: `1830`
  - unique rows: `183`
  - top-1: `1820/1830` (`99.5%`)
  - top-5: `1830/1830`
  - positive gap: `10/1830`
  - mean gap: `-0.097`
  - only remaining blocker: `shoryuken-hp` on `10` rows

Targeted same-log comparison:
- incoming projectile + jump-start-allowed:
  - V47: jump top-1 `0/1533`, `shoryuken-hp` top-1 `1313/1533` (`85.6%`)
  - V52: jump top-1 `1508/1533` (`98.4%`), `shoryuken-hp` top-1 `11/1533`
    (`0.7%`)
- safe-jump unique rows:
  - V47: jump top-1 `0/181`
  - V52: jump top-1 `180/181` (`99.4%`)

## Live Probe Findings

Probe log:
- `logs/rl-transitions-v52-live-probe.ndjson`

Probe summary:
- rows: `8292`
- episodes: `9`
- result: `4 win / 5 loss`
- total HP deltas:
  - opponent HP damage: `1218`
  - self HP damage: `1267`
  - net reward: `-49`
- all rows executed model version `52`
- schema version `5`
- wire mismatches: `6`, all `execution_source=2` repeated-last-action rows

Fresh action-start distribution:
- `forward`: `3539/6961` (`50.8%`)
- `back`: `2551/6961` (`36.6%`)
- `forward-hp`: `227/6961` (`3.3%`)
- `crouch-mp`: `166/6961` (`2.4%`)
- `jump-neutral-start`: `43/6961` (`0.6%`)
- `shoryuken-hp`: `41/6961` (`0.6%`)

This means V52 did not become a general over-jump policy.

Incoming projectile + jump-start-allowed + fresh action-start:
- rows: `43`
- `jump-neutral-start`: `41/43` (`95.3%`)
- `shoryuken-hp`: `1/43` (`2.3%`)
- `throw`: `1/43` (`2.3%`)

This is the key live-probe pass: V52 chooses jump in the situation that V47
handled with Shoryuken.

Jump outcome on same-row incoming projectile threats:
- jump starts: `41`
- safe including current row damage: `28/41`
- damaged including current row damage: `13/41`
- self HP lost in the 16-decision window: `108`

If same-row damage is excluded because the hit may already be unavoidable on
the action decision row:
- safe: `33/41` (`80.5%`)
- damaged after current row: `8/41` (`19.5%`)
- self HP lost after current row: `69`

Damage timing pattern:
- first damage offset:
  - current row: `5`
  - +1 decision: `4`
  - +2 decisions: `1`
  - +10 to +12 decisions: `3`
- damaged buckets after current row:
  - `time_to_self=7..12`: `2`
  - `time_to_self=13..24`: `3`
  - `time_to_self=25..48`: `3`

Conclusion from live probe:
- V52 fixes action selection: it jumps instead of using Shoryuken against
  jumpable incoming fireballs.
- V52 does not fully solve timing and spacing: some jumps are late or otherwise
  get hit.
- Overall policy strength is not yet promote-ready: 4 wins, 5 losses, net
  reward `-49`.

## V52 Decision

Keep:
- `projectile-response-v3`
- V52 as the current offline/live candidate for anti-fireball jump behavior.

Do not yet promote:
- V52 should not become the default remote actor until the timing bucket issue
  is addressed or live A/B shows it improves net behavior.

Do not use:
- V48, V49, V50, V51 as candidates.

## V53 Direction: Projectile Timing Split

V53 should keep the V52 jump-group margin. The next problem is no longer
"jump loses to Shoryuken". The next problem is "jump is selected too broadly
across projectile timing buckets".

### Main Idea

Split incoming projectile rows by `obs_projectile_time_to_self` and train
different preferences by bucket:

- too short: do not force jump; prefer guard/back.
- reliable: keep V52 safe-jump margin.
- late-hit examples: add negative pressure against jump or a dedicated
  diagnostic so we can see exactly where jump is still unsafe.

### Proposed Timing Buckets

Initial buckets for diagnostics and training:

- urgent: `time_to_self=0..6`
  - Interpretation: likely too late to start a jump.
  - Desired behavior: guard first; back only if spacing/edge state makes it
    plausible.
  - Training: do not apply safe-jump margin. Consider a defensive margin that
    ranks `guard-stand`, `guard-crouch`, or `back` above jump.

- borderline: `time_to_self=7..12`
  - Interpretation: jump can work sometimes but is sensitive to state,
    jump-start latency, current routine, and projectile height.
  - Desired behavior: conservative. Use guard/back unless demo/live evidence
    proves this exact state is safe.
  - Training: reduce or disable safe-jump margin by default; add stronger
    late-jump-hit negatives.

- reliable jump: `time_to_self=13..24`
  - Interpretation: likely the main safe-jump range, but live V52 still had
    some damage here.
  - Desired behavior: jump if the row is a clean safe-jump expert row and
    action-start is valid.
  - Training: keep jump-group margin, but track late-hit exceptions by
    `rel_x`, `rel_y`, `obs_abs_dx`, self routine, and current jump-start state.

- setup jump: `time_to_self=25..48`
  - Interpretation: enough time to jump, but may be early enough that later
    projectile or opponent behavior can still punish.
  - Desired behavior: jump is acceptable, but do not let it become automatic
    if spacing or opponent state makes guard/back better.
  - Training: keep safe-jump margin for proven safe rows; monitor delayed-hit
    rows separately.

These cutoffs are starting points, not final truths. V53 should record all
metrics by bucket so future runs can move the thresholds.

### Training Changes To Consider

1. Timing-filtered safe-jump margin

Add flags such as:
- `--projectile-expert-margin-min-time-to-self`
- `--projectile-expert-margin-max-time-to-self`
- or `--projectile-expert-margin-time-buckets reliable,setup`

First V53 candidate:
- keep jump-group margin only for `time_to_self >= 13`
- keep max at `48`
- continue requiring clean safe jump and valid `action-start-v1`

Expected effect:
- preserve V52's jump behavior in reliable buckets.
- avoid training the network to jump on urgent/borderline rows where live
  results show damage risk.

2. Late-jump-hit negative objective

For rows classified as incoming projectile + jump-start + late jump hit:
- define jump group:
  - `jump-forward-start`
  - `jump-neutral-start`
  - `jump-back-start`
- define defensive group:
  - `guard-stand`
  - `guard-crouch`
  - `back`
- apply a group margin in the opposite direction:
  - best defensive action should rank above best jump action by a small margin.

This is safer than only increasing the reward cost because it directly pushes
down the jump Q values in the states where jump got hit.

Suggested conservative start:
- negative margin: `0.05` to `0.1`
- loss weight: `0.5` to `1.0`
- apply only to `time_to_self <= 12` at first
- record blockers and Q gaps by time bucket

3. Timing-specific reward shaping

Possible adjustments:
- increase `reward_projectile_late_jump_hit_cost` for urgent/borderline buckets.
- do not increase global late-jump cost without bucket diagnostics; it may
  suppress genuinely good jumps in reliable buckets.
- add or increase guard/back success bonus for urgent/borderline projectile
  rows if clean windows show those actions avoid damage.

4. Diagnostics before and after training

V53 should print and store:
- projectile threat rows by `time_to_self` bucket.
- action distribution by bucket.
- jump safe/damaged counts by bucket.
- after-current-row damage counts so unavoidable same-frame hits do not pollute
  the decision metric.
- jump-group-vs-nonjump Q gap by bucket.
- blocker action counts by bucket.
- live-probe summary using the same metrics.

### V53 Candidate Acceptance Criteria

Offline:
- reliable/setup safe-jump expert rows keep jump-group top-1 near V52 levels.
- urgent/borderline rows no longer blindly rank jump above guard/back.
- `shoryuken-hp` must remain suppressed on projectile rows.
- no new `tatsu-mk` or other special-action blocker should appear.

Live:
- incoming projectile + jump-start-allowed fresh decisions should still avoid
  Shoryuken.
- jump rate should remain high in reliable buckets, lower in urgent buckets.
- after-current-row damaged jump rate should improve from V52's `8/41`
  (`19.5%`).
- overall net reward and win/loss should not regress.

### Main Risks

- Overcorrecting can produce a passive guard/back policy and lose the V52
  anti-fireball improvement.
- `time_to_self` is derived and not a full hitbox truth; projectile height,
  self routine, jump startup, and spacing matter too.
- Some same-row damage is already unavoidable by the time the decision is
  logged, so training on it as a jump failure can teach the wrong lesson.
- The live V52 sample is small. V53 should use targeted collection or at least
  repeated probes before final thresholds are treated as stable.

### Recommended V53 First Experiment

Keep all V52 parameters except:
- apply safe-jump expert margin only for `time_to_self >= 13`.
- add a diagnostic-only report for late-jump-hit rows by bucket.
- if diagnostics confirm the live pattern, add a negative defensive margin for
  late jump hits with `time_to_self <= 12`.

Suggested naming:
- model dir: `model/dqn-projectile-schema-v5-full-actions-v53-timing-split-candidate`
- auto-retrain preset later: `projectile-response-v4`

## V53 Timing Split Result

Date: 2026-05-01

Model:
- `model/dqn-projectile-schema-v5-full-actions-v53-timing-split-candidate`

Auto-retrain preset:
- `projectile-response-v4`

V53 kept all V52 parameters except the expert margin was only applied to clean
safe-jump human-demo projectile rows with:
- `--projectile-expert-margin-min-time-to-self 13`
- `--projectile-expert-margin-max-time-to-self 48`

Implementation changes:
- added margin timing-window flags to `tools/train_dqn_learner.py`.
- added margin sampled/violation bucket diagnostics.
- added expert Q-gap bucket diagnostics.
- added `projectile-response-v4` as a reproducible auto-retrain preset.

Validation:
- `python3 -m py_compile tools/train_dqn_learner.py tools/rl_auto_retrain.py`
- smoke train with `--steps 8`.
- full train with `--steps 3000`.

Training diagnostics:
- margin eligible experiences: `1740`
- sampled timing buckets:
  - `13-24`: `73610/99251` (`74.2%`)
  - `25-48`: `25641/99251` (`25.8%`)
- final margin loss: `0.000091`
- expert Q-gap rows: `1740`
- expert top-1: `1730/1740` (`99.4%`)
- positive gaps: `10/1740`
- remaining blocker: `shoryuken-hp`, `10` rows, all in `13-24`

Targeted offline comparison on
`logs/rl-transitions-human-demo-projectile-schema-v5-smoke-4-3-3.ndjson`:
- V53 did not materially change greedy behavior versus V52.
- incoming projectile + jump-start-allowed:
  - `0-6`: jump `52/55`, `shoryuken-hp` `3/55`
  - `7-12`: jump `315/323`, `shoryuken-hp` `2/323`, `tatsu-mk` `5/323`
  - `13-24`: jump `672/685`
  - `25-48`: jump `469/470`
- safe-jump proxy rows remained jump-dominant in all buckets.

Targeted comparison on `logs/rl-transitions-v52-live-probe.ndjson`:
- V53 predicted the same actions as V52 on the 43 incoming projectile fresh
  decisions.
- V53 still predicted jump on the damaged live rows:
  - `7-12`: `2/2` damaged rows predicted `jump-neutral-start`
  - `13-24`: `3/3` damaged rows predicted `jump-neutral-start`
  - `25-48`: `3/3` damaged rows predicted `jump-neutral-start`

Conclusion:
- V53 is a diagnostic/reproducibility milestone, not a promotable behavior
  improvement.
- Removing safe-jump margin from `time_to_self < 13` is not enough to make
  urgent/borderline rows prefer guard/back. The V52 projectile reward,
  oversampling, and neighboring bucket generalization still rank jump high.
- Keep V52 as the current anti-fireball candidate.
- The next experiment should be V54: add an explicit late-jump-hit defensive
  group margin so `guard-stand`, `guard-crouch`, or `back` can beat jump on
  damaged urgent/borderline projectile rows.

## V54/V55 Execution Plan: Late Defensive Margin And Human Demo Loop

Date: 2026-05-01

Goal:
- preserve V52/V53's reliable safe-jump anti-projectile behavior.
- teach the policy not to hard-jump when projectile timing is urgent or
  borderline.
- get to a candidate and preset that are safe enough for live incremental
  retrain.

### Phase 1: V54 Trainer Support

Add a late-jump defensive margin objective:
- eligible rows:
  - incoming projectile threat.
  - jump-start action.
  - projectile outcome is late jump hit.
  - `obs_projectile_time_to_self <= 12`.
- defensive group:
  - `back`
  - `guard-stand`
  - `guard-crouch`
- jump group:
  - `jump-forward-start`
  - `jump-neutral-start`
  - `jump-back-start`
- margin rule:
  - `Q(best_defensive) >= Q(best_jump) + margin`

Initial conservative parameters:
- `--projectile-late-defensive-margin-loss`
- `--projectile-late-defensive-margin 0.05`
- `--projectile-late-defensive-margin-weight 0.5`
- `--projectile-late-defensive-margin-batch-size 16`
- `--projectile-late-defensive-margin-max-time-to-self 12`
- `--projectile-late-defensive-margin-valid-action-mask action-start-v1`

Keep V53 safe-jump margin:
- clean safe-jump rows with `time_to_self 13..48`.
- jump group beats valid non-jump actions.

### Phase 2: Offline V54 Candidate

Train first on:
- `logs/rl-transitions-human-demo-projectile-schema-v5-smoke-4-3-3.ndjson`

Suggested model:
- `model/dqn-projectile-schema-v5-full-actions-v54-late-def-margin-candidate`

Offline gate:
- `13-24` / `25-48` safe-jump rows should remain near V52/V53 jump top-1.
- `0-6` / `7-12` damaged late-jump rows should show lower jump top-1 and
  higher guard/back top-1.
- `shoryuken-hp` and `tatsu-mk` must not return as projectile blockers.
- non-projectile greedy action distribution should not swing strongly toward
  guard/back.

If this gate fails, tune V54 before any live retrain.

### Phase 3: Targeted Human Demo Collection

After V54 trainer support exists, collect a focused projectile-defense demo:
- `0-6`: show guard/back, avoid jump.
- `7-12`: show guard/back, with only clean intentional jumps if they really
  work.
- `13-24`: show successful jump-over.
- `25-48`: show jump/walk/reposition.

Suggested log naming:
- `logs/rl-transitions-human-demo-projectile-defense-v54-*.ndjson`

Important: the log must remain `execution_source=human-demo` so trainer
expert objectives can use it.

### Phase 4: V55 With Demo Mix

V55 should combine:
- old projectile human demo.
- new targeted projectile-defense human demo.
- live failure/probe logs from V52/V53/V54 if useful.

Training objective:
- reliable clean jump rows: jump group beats non-jump.
- urgent/borderline defensive demo rows: guard/back beats jump.
- urgent/borderline late-hit rows: guard/back beats jump.

### Phase 5: Live Incremental Retrain Readiness

Only after V54 or V55 passes offline gates:
- add/use the corresponding auto-retrain preset.
- run a live probe.
- then use live incremental retrain with the same preset.

The live incremental retrain gate should report:
- incoming projectile fresh decisions by timing bucket.
- jump rate by bucket.
- guard/back rate by bucket.
- late jump damaged rate.
- `shoryuken-hp` and `tatsu-mk` blocker rate.
- non-projectile action mix and overall net HP.

## V54 Implementation Result

Date: 2026-05-01

Status:
- trainer support is implemented.
- auto-retrain preset `projectile-response-v5` is implemented.
- old-demo-only V54 candidates are not promotable.
- targeted human-demo projectile defense data is the next required input before
  live incremental retrain should be trusted.

Implemented trainer objective:
- late jump-hit projectile rows can receive a defensive margin loss.
- defensive group:
  - `back`
  - `guard-stand`
  - `guard-crouch`
- jump group:
  - `jump-forward-start`
  - `jump-neutral-start`
  - `jump-back-start`
- rule:
  - `Q(best_defensive) >= Q(best_jump) + margin`

New CLI flags:
- `--projectile-late-defensive-margin-loss`
- `--projectile-late-defensive-margin`
- `--projectile-late-defensive-margin-weight`
- `--projectile-late-defensive-margin-batch-size`
- `--projectile-late-defensive-margin-min-time-to-self`
- `--projectile-late-defensive-margin-max-time-to-self`
- `--projectile-late-defensive-margin-sources`
- `--projectile-late-defensive-margin-valid-action-mask`

Preset:
- `projectile-response-v5`
- base: V53 / `projectile-response-v4`
- adds conservative late defensive margin:
  - margin `0.05`
  - weight `0.25`
  - batch size `8`
  - max `time_to_self` `12`
  - valid mask `action-start-v1`

Validation:
- `python3 -m py_compile tools/train_dqn_learner.py tools/rl_auto_retrain.py`
- preset check for `projectile-response-v5`.
- smoke train to `/tmp/rl-v54-late-def-smoke`.
- full trains:
  - `model/dqn-projectile-schema-v5-full-actions-v54-late-def-margin-candidate`
  - `model/dqn-projectile-schema-v5-full-actions-v54-late-def-finetune-candidate`
  - `model/dqn-projectile-schema-v5-full-actions-v54-late-def-conservative-candidate`

Smoke finding:
- late defensive eligible experiences: `168`
- sampled mostly `7-12`, plus some `0-6`
- no empty valid/defensive/jump mask events.

Old-demo-only candidate findings:
- random-init V54 was too disruptive:
  - expert Q-gap top-1 fell to `1650/1740` (`94.8%`)
  - `tatsu-mk` returned as a projectile blocker.
- V53 warm-start full-strength V54 was safer but still not promotable:
  - expert Q-gap top-1 `1710/1740` (`98.3%`)
  - late-hit rows still mostly predicted jump.
- V53 warm-start conservative V54 preserved V53 projectile ranking:
  - expert Q-gap top-1 `1730/1740` (`99.4%`)
  - remaining blocker: `shoryuken-hp` on `10` rows
  - late-hit rows still mostly predicted jump.

Interpretation:
- the objective is wired and ready, but the old log does not contain enough
  clean "what to do instead" data for urgent/borderline projectile defense.
- late-hit rows say jump was wrong, but they do not provide a clean positive
  target for guard/back.
- targeted human demo is required before this should be used for live
  incremental retrain with confidence.

Next data collection target:
- record `execution_source=human-demo` rows for projectile defense:
  - `0-6`: guard/back success; avoid jump.
  - `7-12`: guard/back success; only jump if visibly clean.
  - `13-24`: successful jump-over.
  - `25-48`: successful jump/walk/reposition.

Live incremental retrain readiness:
- code path: ready.
- preset: ready.
- old-demo-only actor: not ready for promotion.
- next step: collect targeted human demo, then retrain with
  `projectile-response-v5` and compare again before live probe.

## V55/V57/V58 Training-Mode Human Demo Results

Date: 2026-05-01

New targeted demo log:
- `logs/rl-transitions-training-human-demo-v55.ndjson`
- rows: `23190`
- episodes: `333`
- schema: v6
- source: `human-demo`
- mode: training mode

V55 model:
- `model/dqn-projectile-schema-v5-full-actions-v55-training-demo-candidate`
- base: V54 conservative
- replay:
  - `logs/rl-transitions-human-demo-projectile-schema-v5-smoke-4-3-3.ndjson`
  - `logs/rl-transitions-training-human-demo-v55.ndjson`
- steps: `1500`
- batch size: `64`
- learning rate: `0.0005`
- HP mode: `--training-mode-hp-delta-mode damage-only`
- safe-jump margin:
  - `time_to_self=13..48`
  - jump-start group equivalence
  - batch size `32`
- late defensive margin:
  - margin `0.05`
  - weight `0.25`
  - batch size `8`
  - max `time_to_self=12`

V55 finding:
- safe-jump expert Q-gap stayed strong:
  - top-1: `2770/2780`
  - positive gap: `10/2780`
- urgent/borderline rows still ranked jump too broadly on the new training log:
  - `0-6`: jump `110/110`
  - `7-12`: jump `467/481`, special `14/481`
- human defense rows were still not selected:
  - `0-6` human-defense subset: jump `46/46`
  - `7-12` human-defense subset: jump `151/155`, special `4/155`

Conclusion:
- adding the training-mode demo log and conservative late defensive margin did
  not make `guard`/`back` top-1 for urgent projectile defense.
- more explicit positive pressure on successful defensive demo rows was needed.

### V57 Defensive Expert Margin

Trainer change:
- added `--projectile-defensive-expert-margin-loss`.
- eligible rows:
  - source in `--projectile-defensive-expert-margin-sources`, default
    `human-demo`.
  - incoming projectile threat.
  - expert action is `back`, `guard-stand`, or `guard-crouch`.
  - `obs_projectile_time_to_self` inside the configured window, default
    `0..12`.
  - lookahead damage is at most
    `--projectile-defensive-expert-margin-max-self-hp`, default `1`.
- objective:
  - `Q(best_defensive) >= Q(best_projectile_competitor) + margin`
  - defensive group: `back`, `guard-stand`, `guard-crouch`
  - competitor group: jump-start, Shoryuken, and Tatsu actions
- metadata/stat diagnostics record eligible rows, sampled rows, blockers,
  losses, and timing buckets.

V57 model:
- `model/dqn-projectile-schema-v5-full-actions-v57-defensive-expert-candidate`
- base: V54 conservative
- defensive expert margin:
  - margin `0.08`
  - weight `1.0`
  - batch size `32`
  - max `time_to_self=12`
  - max self HP `1`

V57 finding:
- defensive Q-gap improved on human-defense incoming rows:
  - V55 `0-6` mean competitor-minus-defense gap: `0.1924`
  - V57 `0-6` mean competitor-minus-defense gap: `0.0395`
  - V55 `7-12` mean competitor-minus-defense gap: `0.1874`
  - V57 `7-12` mean competitor-minus-defense gap: `0.0375`
- however V57 did not make defense top-1. It often moved the top action from
  jump to `tatsu-mk` or `shoryuken-hp`.
- projectile bucket comparison on the new training log:
  - `0-6`: jump `82/110`, special `28/110`
  - `7-12`: jump `374/481`, special `107/481`
  - `13-24`: jump `639/863`, special `222/863`
  - `25-48`: special `297/445`, jump `148/445`
- safe-jump expert Q-gap regressed:
  - top-1: `2620/2780`
  - positive gap: `160/2780`

Conclusion:
- V57 is not promotable.
- The defensive objective moved Q values in the right direction, but the
  single-best-competitor hinge let other specials become blockers and damaged
  reliable safe-jump behavior.

### V58 All-Competitor Defensive Expert Margin

Trainer change:
- added `--projectile-defensive-expert-margin-all-competitors`.
- in this mode, every violating jump/Shoryuken/Tatsu competitor in the row
  receives a margin gradient.
- gradients are averaged across violating competitors so total force does not
  scale with the number of action heads.

Auto-retrain preset:
- `projectile-response-v6`
- base: `projectile-response-v5`
- adds defensive expert margin:
  - margin `0.08`
  - weight `1.0`
  - batch size `64`
  - max `time_to_self=12`
  - max self HP `1`
  - all-competitor mode enabled
  - overrides safe-jump expert margin batch size to `64`

V58 model:
- `model/dqn-projectile-schema-v5-full-actions-v58-defensive-allcomp-candidate`
- base: V54 conservative
- differences from V57 training:
  - defensive expert all-competitor mode enabled.
  - defensive expert margin batch size `64`.
  - safe-jump expert margin batch size `64`.

V58 finding:
- safe-jump expert Q-gap recovered:
  - top-1: `2770/2780`
  - positive gap: `10/2780`
  - remaining blocker: `shoryuken-hp`, `10` rows.
- defensive Q-gap improved versus V55 but not enough to flip top-1:
  - `0-6` human-defense mean competitor-minus-defense gap: `0.0760`
  - `7-12` human-defense mean competitor-minus-defense gap: `0.0726`
- projectile bucket comparison remained essentially V55-like:
  - `0-6`: jump `110/110`
  - `7-12`: jump `467/481`, special `14/481`
  - `13-24`: jump `853/863`, special `8/863`
  - `25-48`: jump `445/445`

Conclusion:
- V58 is not promotable either.
- All-competitor defensive margin fixes the V57 special leakage and preserves
  reliable safe jump, but it still does not make urgent/borderline rows choose
  `guard`/`back`.
- Current evidence says the issue is not only competitor switching; the TD
  reward/replay mix still gives `guard`/`back` too little absolute Q support
  relative to jump.

### Next Direction

V59 should not be another blind margin-weight increase.

Recommended next steps:
- collect more focused `time_to_self <= 12` clean guard/back human-demo rows
  with fewer unrelated CPU actions between projectile situations.
- add or test a policy-time projectile timing prior/mask for urgent rows:
  - when incoming projectile `time_to_self <= 6`, demote jump-start unless the
    state is explicitly known safe.
  - keep jump-start available for `time_to_self >= 13`.
- alternatively add a stronger BC-style classification objective on filtered
  clean defensive rows, but gate it tightly by timing bucket so it does not
  overwrite V52/V55 safe-jump behavior.
- continue to use V52/V55 as the safe-jump baseline; do not live-probe V57 or
  V58 as promotable candidates.

## Auto-Retrain Replay Plan Fix

Date: 2026-05-01

Status:
- design plan only.
- needed before relying on human-demo-heavy live incremental retrain.

### Problem

`tools/rl_auto_retrain.py` currently resolves a single row-source ratio string
and passes it to `tools/train_dqn_learner.py`.

When no explicit ratio is configured, it falls back to:
- `cpu-demo=0.50,human-demo=0.30,remote=0.20`

This is fragile for targeted human demo retrain:
- a human-demo incremental chunk may not contain `remote`.
- a model/base recipe may not contain `cpu-demo`.
- `train_dqn_learner.py --replay-source-ratios` intentionally errors if a
  requested source has no rows.

Result:
- incremental retrain can fail even though the input log is valid.
- targeted projectile human demo can also be diluted by older human-demo rows
  because current ratios operate only on row `execution_source`, not on log
  role.

### Better Model

Separate two concepts:

1. Log-level replay role:
- old base logs.
- live incremental chunk.
- targeted human-demo log.
- filtered projectile-demo boost log.

2. Row-level execution source:
- `cpu-demo`
- `human-demo`
- `remote`
- etc.

The auto-retrain path should be able to say:
- keep enough base replay to avoid forgetting general behavior.
- include the new live/human-demo chunk.
- boost a filtered projectile human-demo log.
- only then apply source balancing among the sources that actually exist.

### Implementation Plan

Step 1: fix missing-source crashes.
- add an `auto-available` replay source ratio mode in `rl_auto_retrain.py`.
- default auto-retrain ratio should become `auto-available`, not the fixed
  three-source ratio.
- before building the train command, scan `base_logs + chunk_log` for available
  execution sources.
- start from preferred ratios:
  - `cpu-demo=0.50`
  - `human-demo=0.30`
  - `remote=0.20`
- drop sources that are absent.
- renormalize the remaining preferred ratios.
- if none of the preferred sources are present, leave source ratios empty and
  let the trainer use raw rows.

Examples:
- only `human-demo`: use `human-demo=1.0`.
- `remote + human-demo`: use `remote=0.40,human-demo=0.60` if based on the
  preferred `0.20/0.30` weights.
- all three: keep `cpu-demo=0.50,human-demo=0.30,remote=0.20`.

Step 2: add log-level boost inputs.
- add repeatable `--extra-base-log PATH` to `rl_auto_retrain.py`.
- add optional `--extra-base-log-repeat N` or `--boost-log PATH=N`.
- append the repeated paths after normal base logs and before the chunk.
- write these boost logs into model metadata under replay recipe/auto retrain.

Short-term usage:
- full old base log once.
- filtered projectile human-demo log 2-4 times.
- live/human-demo chunk once.

Step 3: preserve metadata.
- store resolved source ratios, raw requested mode, base logs, extra/boost logs,
  chunk log, and live source log in `metadata.auto_retrain`.
- also write replay recipe fields so future dry-runs can reproduce the same
  replay plan.

Step 4: add dry-run diagnostics.
- dry-run should print:
  - detected sources by log.
  - resolved auto-available ratio.
  - final train command.
  - base logs, boost logs, chunk log.

### Acceptance Criteria

- auto retrain with a human-demo-only source chunk does not fail because
  `remote` or `cpu-demo` are absent.
- auto retrain with remote-only chunks still works.
- auto retrain with mixed remote/human-demo chunks resolves ratios only for
  available sources.
- targeted filtered projectile demo can be boosted without replacing the
  general base replay.
- model metadata records the resolved replay plan.

### Interim Workaround

Until this is implemented, pass an explicit ratio matching available sources:
- human demo only:
  - `--replay-source-ratios human-demo=1`
- remote + human demo:
  - `--replay-source-ratios remote=0.5,human-demo=0.5`

Do not use the current fixed default for targeted human-demo incremental
retrain.
