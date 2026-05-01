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

Before collecting the full reboot dataset:

1. run Phase 0 sanity logs for the current schema/build.
2. analyze action-start counts, projectile field correctness, and detector
   dry-run hit rates.
3. fix detector/selector mismatches before using the logs for training.
4. collect Phase 1 movement data.
5. train `M1` and verify spacing behavior before moving to attacks.
