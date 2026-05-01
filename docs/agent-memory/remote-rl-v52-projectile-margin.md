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

