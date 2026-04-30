# Remote RL Agent Engineering Log

This log tracks implementation progress, engineering decisions, test results, and open issues for the remote RL agent work.

## 2026-04-30: Train And Compare V18 Source-Mixed DQN

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / replay source mixing preparation

Files changed:
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- train the first v18 candidate with an explicit row-level source mix.
- test whether adding a small amount of v9 live-policy replay improves the v9 ground-specials policy surface without reinforcing sparse-action overestimation.

Implementation notes:
- trained `model/dqn-mixdemo-schema-v3-ground-specials-v18`.
- v18 uses the v9 ground-specials recipe, standard DQN target mode, and the new source-mix control:
  - `--replay-source-ratios cpu-demo=0.6,human-demo=0.3,remote=0.1`
- row-level source mix was exactly:
  - `cpu-demo=11682` / `60.0%`
  - `human-demo=5841` / `30.0%`
  - `remote=1947` / `10.0%`
- `repeated-last-action=16` and `neutral-fallback=4` were dropped because they were not listed in the ratio.
- built DQN experiences were:
  - `human-demo=4405` / `45.3%`
  - `cpu-demo=4227` / `43.5%`
  - `remote=1083` / `11.1%`
- experience mix differs from row mix because DQN replay is decision/macro based and engine-outcome oversampling changes source density.

Result:
- v18 trained and published successfully:
  - rows: `19470`
  - experiences: `9715`
  - last loss: `0.004914`
  - avg loss: `0.006962`
- saved v18 metadata greedy distribution over its 5000-row eval slice:
  - `stand-lp=48.6%`
  - `crouch-hp=31.0%`
  - `stand-hk=10.4%`
  - `fireball-hp=8.7%`
  - `guard-crouch=0.3%`
- same-observation CPU/human slice compare against v9:
  - v9: `stand-lp=36.3%`, `fireball-hp=27.5%`, `crouch-hp=24.0%`, `stand-hk=9.3%`, `guard-crouch=1.7%`
  - v18: `stand-lp=49.8%`, `crouch-hp=31.6%`, `fireball-hp=11.0%`, `stand-hk=5.7%`, `guard-crouch=0.4%`
  - changed decisions: `1249/5000`
- same-observation v9-live-log compare:
  - v9: `fireball-hp=39.2%`, `crouch-hp=35.8%`, `stand-hk=16.6%`, `stand-lp=5.8%`, `guard-crouch=2.3%`
  - v18: `crouch-hp=49.2%`, `fireball-hp=19.3%`, `stand-lp=18.2%`, `stand-hk=11.5%`, `guard-crouch=0.5%`
  - changed decisions: `589/1967`
- conclusion:
  - v18 does not create a guard collapse or LP/MP fireball collapse.
  - v18 also does not improve the sparse-action overestimation problem.
  - adding 10% v9 live replay mostly shifts probability away from `fireball-hp` into `stand-lp` and `crouch-hp`.
  - v18 should not replace v9 for live use based on offline evidence.

Validation:
- Python compile passed:
  - `python3 -m py_compile tools/train_dqn_learner.py tools/compare_dqn_models.py`
- full v18 training passed:
  - `python3 tools/train_dqn_learner.py logs/rl-transitions-cpu-demo-schema-v3-4-3-3.ndjson logs/rl-transitions-human-demo-schema-v3-4-3-3.ndjson logs/rl-transitions-live-dqn-ground-specials-v9-4-3-3.ndjson --model-dir model/dqn-mixdemo-schema-v3-ground-specials-v18 --model-version 18 --steps 3000 --batch-size 64 --gamma 0.9 --learning-rate 0.001 --target-sync-steps 200 --dqn-target-mode standard --replay-source-ratios cpu-demo=0.6,human-demo=0.3,remote=0.1 --actions forward,back,guard-stand,guard-crouch,stand-lp,stand-mp,stand-hp,stand-lk,stand-mk,stand-hk,forward-hp,crouch-lp,crouch-mp,crouch-hp,crouch-lk,crouch-mk,crouch-hk,fireball-lp,fireball-mp,fireball-hp,throw,shoryuken-lp,shoryuken-mp,shoryuken-hp,tatsu-lk,tatsu-mk,tatsu-hk --fallback-policy stand-mk --training-action-source auto --reward-risk-profile all-attacks --reward-risk-window-decisions 15 --reward-attack-no-damage-cost 0.3 --reward-attack-punished-cost 1.0 --reward-shoryuken-no-damage-extra-cost 0.0 --reward-shoryuken-punished-extra-cost 0.5 --reward-jump-attack-no-damage-extra-cost 0.0 --reward-jump-attack-punished-extra-cost 0.0 --reward-guard-success-bonus 0.0 --reward-guard-success-window-decisions 6 --reward-guard-threat-max-dx 120 --reward-passive-guard-cost 0.3 --reward-far-guard-cost 0.5 --reward-spacing-target-min-dx 50 --reward-spacing-target-max-dx 120 --reward-spacing-improve-bonus 0.5 --reward-spacing-worsen-cost 0.2 --reward-spacing-maintain-bonus 0.1 --reward-spacing-threat-back-bonus 0.3 --engine-outcome-training-mode prefer-engine-action --engine-outcome-window-decisions 15 --engine-outcome-action-windows fireball-lp=45,fireball-mp=45,fireball-hp=45,tatsu-lk=25,tatsu-mk=25,tatsu-hk=25 --engine-outcome-hit-bonus 1.0 --engine-outcome-no-damage-cost 0.2 --engine-outcome-punished-cost 1.0 --engine-outcome-oversample 1 --engine-outcome-action-oversamples fireball-lp=10,fireball-mp=20,fireball-hp=8,shoryuken-lp=4,shoryuken-mp=6,shoryuken-hp=8,tatsu-lk=6,tatsu-mk=6,tatsu-hk=6 --batch-sampling balanced --balanced-batch-ratios movement=0.3,normal=0.3,special=0.4 --epsilon 0.05 --seed 7 --log-interval 500 --eval-limit 5000 --diagnostic-top-n 12`
- metadata inspection passed:
  - `jq '.metadata | {rows_read, rows_read_before_source_mix, experiences, replay_source_mix_stats, source_rows:.source_replay_diagnostics.row_counts, source_experiences:.source_replay_diagnostics.experience_counts, model_versions:.source_replay_diagnostics.experience_model_version_counts, batch_sampling, greedy_counts, greedy_top_action, greedy_top_action_rate, dqn_target_mode, last_loss, avg_loss}' model/dqn-mixdemo-schema-v3-ground-specials-v18/current.json`
- CPU/human same-observation compare passed:
  - `python3 tools/compare_dqn_models.py logs/rl-transitions-cpu-demo-schema-v3-4-3-3.ndjson logs/rl-transitions-human-demo-schema-v3-4-3-3.ndjson --model v9=model/dqn-mixdemo-schema-v3-ground-specials-v9 --model v18=model/dqn-mixdemo-schema-v3-ground-specials-v18 --limit 5000 --top-n 8 --focus-actions crouch-hp,stand-lp,stand-hk,stand-mk,fireball-lp,fireball-mp,fireball-hp,guard-stand,guard-crouch --focus-rank-limit 3 --training-action-source auto`
- v9-live-log same-observation compare passed:
  - `python3 tools/compare_dqn_models.py logs/rl-transitions-live-dqn-ground-specials-v9-4-3-3.ndjson --model v9=model/dqn-mixdemo-schema-v3-ground-specials-v9 --model v18=model/dqn-mixdemo-schema-v3-ground-specials-v18 --limit 5000 --top-n 8 --focus-actions crouch-hp,stand-lp,stand-hk,stand-mk,fireball-lp,fireball-mp,fireball-hp,guard-stand,guard-crouch --focus-rank-limit 3 --training-action-source auto`

Follow-up:
- do not promote v18 to live testing as-is.
- avoid using v9 live replay as a default positive training source until the trainer can apply stronger action-support priors, source-specific weights, or policy-improvement filtering.
- next useful path is inference-time reranking / action-support prior, because source-mix retraining still shifts collapse among `stand-lp`, `crouch-hp`, and `fireball-hp` instead of adding a healthier tactical spread.

## 2026-04-30: Add Opt-In DQN Replay Source Mix Controls

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / replay source mixing preparation

Files changed:
- `tools/train_dqn_learner.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- allow a v18-style DQN run to train from mixed live-policy and demo logs with an explicit, reproducible source policy.
- keep default trainer behavior raw so existing v9/v17 recipes and comparisons remain unchanged.

Implementation notes:
- added source-mix flags that run after log read / initial-episode drop and before DQN experience building:
  - `--replay-source-include`
  - `--replay-source-exclude`
  - `--replay-source-max-rows`
  - `--replay-source-ratios`
- source names accept labels such as `remote`, `human-demo`, `cpu-demo`, `repeated-last-action`, and `neutral-fallback`, plus numeric execution-source ids.
- `--replay-source-ratios` performs deterministic row-level undersampling with `--seed` and does not oversample scarce sources.
- when ratios are set, sources not listed in the ratio are dropped; this gives a concise v18 candidate shape such as `remote=0.7,human-demo=0.3` while excluding repeated-action and fallback rows.
- actor metadata now records:
  - `rows_read_before_source_mix`
  - `replay_source_mix_config`
  - `replay_source_mix_stats`
- stdout prints `source_mix=...` in the publish summary and a `replay_source_mix=...` diagnostics line with pre/post/target source counts.

Result:
- raw mode preserved previous behavior in the smoke test:
  - `source_mix=raw:1200->1200`
  - `replay_source_mix=mode:raw rows:1200->1200 dropped:0`
- ratio mode worked on the mixed live-v9 + human-demo smoke:
  - source mix rows changed from `3000` to `2781`
  - post-mix rows were `remote=1947` and `human-demo=834`
  - `repeated-last-action=16` and `neutral-fallback=4` were dropped because they were not listed in the target ratio
  - row-level mix landed at `70.0% remote / 30.0% human-demo`
- experience-level mix was `remote=1041` and `human-demo=349`; this differs from row-level mix because DQN experience construction is decision/macro based.

Validation:
- Python compile passed:
  - `python3 -m py_compile tools/train_dqn_learner.py`
- raw source-mix smoke passed:
  - `python3 tools/train_dqn_learner.py logs/rl-transitions-cpu-demo-schema-v3-4-3-3.ndjson logs/rl-transitions-human-demo-schema-v3-4-3-3.ndjson --model-dir /tmp/rl-dqn-source-mix-raw-smoke --model-version 1 --limit 1200 --steps 2 --batch-size 16 --hidden-sizes 8 --actions forward,back,guard-stand,guard-crouch,stand-mk,crouch-hp,fireball-lp,fireball-mp,fireball-hp --fallback-policy stand-mk --training-action-source auto --reward-risk-profile none --engine-outcome-training-mode prefer-engine-action --engine-outcome-window-decisions 15 --engine-outcome-action-windows fireball-lp=45,fireball-mp=45,fireball-hp=45 --log-interval 1 --eval-limit 200 --diagnostic-top-n 8`
  - reported unchanged raw source mix.
- ratio source-mix smoke passed:
  - `python3 tools/train_dqn_learner.py logs/rl-transitions-live-dqn-ground-specials-v9-4-3-3.ndjson logs/rl-transitions-human-demo-schema-v3-4-3-3.ndjson --model-dir /tmp/rl-dqn-source-mix-ratio-smoke --model-version 2 --limit 3000 --steps 2 --batch-size 16 --hidden-sizes 8 --actions forward,back,guard-stand,guard-crouch,stand-lp,stand-hk,crouch-hp,fireball-hp --fallback-policy stand-mk --training-action-source auto --reward-risk-profile none --engine-outcome-training-mode prefer-engine-action --engine-outcome-window-decisions 15 --replay-source-ratios remote=0.7,human-demo=0.3 --log-interval 1 --eval-limit 200 --diagnostic-top-n 8`
  - reported `replay_source_mix=mode:configured rows:3000->2781 dropped:219 ... post:remote:1947/70.0%,human-demo:834/30.0%`.
- metadata spot-check passed:
  - `jq '.metadata | {rows_read, rows_read_before_source_mix, replay_source_mix_config, replay_source_mix_stats}' /tmp/rl-dqn-source-mix-ratio-smoke/current.json`

Follow-up:
- choose the actual v18 source mix recipe before full training; first candidate is likely v9-style DQN recipe plus `--replay-source-ratios remote=0.7,human-demo=0.3` against the v9 live log and fresh human-demo / CPU-demo logs.
- compare any v18 candidate against v9/v17 on the same observation slice before live testing, with special attention to whether remote replay amplifies the existing `crouch-hp` / `stand-lp` / `fireball-hp` policy surface.

## 2026-04-30: Add Source-Aware DQN Replay Diagnostics

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / replay source mixing preparation

Files changed:
- `tools/train_dqn_learner.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- make source composition visible before training a v18-style model from mixed demo plus live policy logs.
- keep this as a diagnostics-only step so existing v9/v17 training comparisons are not confounded by a hidden replay sampling change.

Implementation notes:
- added `source_replay_diagnostics` to DQN actor metadata.
- diagnostics split both raw replay rows and built DQN experiences by:
  - `execution_source`: `none`, `remote`, `repeated-last-action`, `neutral-fallback`, `human-demo`, `cpu-demo`
  - `model_version_executed`
  - per-source action count / reward / mean reward
- `Experience` now carries `source_name` and `model_version` metadata for diagnostics, but training inputs, targets, batch sampling, and greedy inference behavior are unchanged.
- macro delayed rewards and conservative action penalties update the per-source reward sums, so source reward diagnostics match the final replay rewards used by the trainer.

Result:
- CPU-demo smoke correctly reported `cpu-demo` as 100% of rows and experiences, with `model_version_executed = 0`.
- mixed live-v9 + human-demo smoke reported:
  - rows: `remote=1947`, `human-demo=1033`, `repeated-last-action=16`, `neutral-fallback=4`
  - row model versions: `9=1967`, `0=1033`
  - experiences: `remote=1041`, `human-demo=422`, `repeated-last-action=11`
  - experience model versions: `9=1052`, `0=422`
- this confirms the trainer can now audit live-policy rows separately from demo rows before choosing v18 source-mix ratios.

Validation:
- Python compile passed:
  - `python3 -m py_compile tools/train_dqn_learner.py`
- CPU-demo source diagnostics smoke passed:
  - `python3 tools/train_dqn_learner.py logs/rl-transitions-cpu-demo-schema-v3-4-3-3.ndjson logs/rl-transitions-human-demo-schema-v3-4-3-3.ndjson --model-dir /tmp/rl-dqn-source-diag-smoke --model-version 1 --limit 1200 --steps 2 --batch-size 16 --hidden-sizes 8 --actions forward,back,guard-stand,guard-crouch,stand-mk,crouch-hp,fireball-lp,fireball-mp,fireball-hp --fallback-policy stand-mk --training-action-source auto --reward-risk-profile none --engine-outcome-training-mode prefer-engine-action --engine-outcome-window-decisions 15 --engine-outcome-action-windows fireball-lp=45,fireball-mp=45,fireball-hp=45 --log-interval 1 --eval-limit 200 --diagnostic-top-n 8`
  - reported `replay_sources=rows:cpu-demo:1200/100.0% experiences:cpu-demo:236/100.0% row_model_versions:0:1200/100.0% experience_model_versions:0:236/100.0%`.
- live-v9 plus human-demo source diagnostics smoke passed:
  - `python3 tools/train_dqn_learner.py logs/rl-transitions-live-dqn-ground-specials-v9-4-3-3.ndjson logs/rl-transitions-human-demo-schema-v3-4-3-3.ndjson --model-dir /tmp/rl-dqn-source-diag-live-smoke --model-version 2 --limit 3000 --steps 2 --batch-size 16 --hidden-sizes 8 --actions forward,back,guard-stand,guard-crouch,stand-lp,stand-hk,crouch-hp,fireball-hp --fallback-policy stand-mk --training-action-source auto --reward-risk-profile none --engine-outcome-training-mode prefer-engine-action --engine-outcome-window-decisions 15 --log-interval 1 --eval-limit 200 --diagnostic-top-n 8`
  - reported live source rows at model version `9` and demo rows at model version `0`.
- metadata spot-check passed:
  - `jq '.metadata.source_replay_diagnostics | {row_counts, row_model_version_counts, experience_counts, experience_model_version_counts}' /tmp/rl-dqn-source-diag-live-smoke/current.json`

Follow-up:
- define the actual replay source mixing policy before v18 training, including source caps or ratios for `human-demo`, `cpu-demo`, `remote`, `repeated-last-action`, and `neutral-fallback`.
- do not treat `model_version_executed = 0` demo rows as a model quality signal; version `0` means no remote actor produced that action.

## 2026-04-30: Add Double DQN Target Mode And Train V17

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / DQN sparse-action overestimation control

Files changed:
- `tools/train_dqn_learner.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- test whether Double DQN target construction reduces the ground-specials sparse-action overestimation seen in v9/v11/v16.
- keep the experiment clean by using the v9 training recipe and changing only the DQN bootstrapping target mode.

Implementation notes:
- added `--dqn-target-mode standard|double` to `tools/train_dqn_learner.py`.
- `standard` remains the default and preserves the previous target:
  - `target = reward + gamma * max_a Q_target(next_state, a)`
- `double` selects the next action with the online network and evaluates it with the target network:
  - `best_next_action = argmax_a Q_online(next_state, a)`
  - `target = reward + gamma * Q_target(next_state, best_next_action)`
- published model metadata now records:
  - `dqn_target_mode`
  - `target_sync_steps`
- trained `model/dqn-mixdemo-schema-v3-ground-specials-v17` with the v9 recipe plus `--dqn-target-mode double`:
  - fresh schema-v3 CPU-demo + human-demo logs
  - `3000` steps, batch size `64`, `gamma=0.9`, learning rate `0.001`, target sync `200`
  - 27-action ground-specials action set
  - `all-attacks` risk profile
  - spacing and guard shaping matching v9
  - engine-outcome replay matching v9
  - no conservative action penalty
- v17 metadata confirms `dqn_target_mode=double` and `target_sync_steps=200`.

Result:
- v17 trained successfully, but the policy surface is effectively unchanged from v9.
- saved `5000`-row eval distribution:
  - v17: `stand-lp=26.72%`, `crouch-hp=26.16%`, `fireball-hp=25.10%`, `stand-hk=19.44%`, `guard-crouch=2.00%`
  - this matches the v9 metadata distribution to practical precision.
- same-observation compare over `5000` rows:
  - v9: `stand-lp=36.3%`, `fireball-hp=27.5%`, `crouch-hp=24.0%`, `stand-hk=9.3%`, `guard-crouch=1.7%`
  - v17: `stand-lp=36.3%`, `fireball-hp=27.4%`, `crouch-hp=24.0%`, `stand-hk=9.3%`, `guard-crouch=1.7%`
  - `COMPARE v9 -> v17 changed=1/5000`
- conclusion:
  - Double DQN support is useful to keep as an opt-in trainer mode.
  - v17 should not replace v9 for live testing on offline evidence alone.
  - the current sparse-action issue is not solved by Double DQN under the v9 recipe.
  - next control should be inference-time reranking / action-support priors, or another explicit target-value control, not more conservative reward penalty tuning.

Validation:
- Python compile passed:
  - `python3 -m py_compile tools/train_dqn_learner.py`
- standard-target smoke passed:
  - `python3 tools/train_dqn_learner.py logs/rl-transitions-cpu-demo-schema-v3-4-3-3.ndjson --model-dir /tmp/rl-dqn-target-standard-smoke --model-version 1 --limit 800 --steps 2 --batch-size 8 --hidden-sizes 8 --actions forward,back,guard-stand,guard-crouch,stand-mk,fireball-lp,fireball-mp,fireball-hp,shoryuken-hp --fallback-policy stand-mk --training-action-source auto --reward-risk-profile none --engine-outcome-training-mode prefer-engine-action --engine-outcome-window-decisions 15 --engine-outcome-action-windows fireball-lp=45,fireball-mp=45,fireball-hp=45 --dqn-target-mode standard --log-interval 1 --eval-limit 100 --diagnostic-top-n 8`
  - reported `target_mode=standard` and published version `1`.
- double-target smoke passed:
  - `python3 tools/train_dqn_learner.py logs/rl-transitions-cpu-demo-schema-v3-4-3-3.ndjson --model-dir /tmp/rl-dqn-target-double-smoke --model-version 2 --limit 800 --steps 2 --batch-size 8 --hidden-sizes 8 --actions forward,back,guard-stand,guard-crouch,stand-mk,fireball-lp,fireball-mp,fireball-hp,shoryuken-hp --fallback-policy stand-mk --training-action-source auto --reward-risk-profile none --engine-outcome-training-mode prefer-engine-action --engine-outcome-window-decisions 15 --engine-outcome-action-windows fireball-lp=45,fireball-mp=45,fireball-hp=45 --dqn-target-mode double --log-interval 1 --eval-limit 100 --diagnostic-top-n 8`
  - reported `target_mode=double` and published version `2`.
- full v17 training passed:
  - `python3 tools/train_dqn_learner.py logs/rl-transitions-cpu-demo-schema-v3-4-3-3.ndjson logs/rl-transitions-human-demo-schema-v3-4-3-3.ndjson --model-dir model/dqn-mixdemo-schema-v3-ground-specials-v17 --model-version 17 --steps 3000 --batch-size 64 --gamma 0.9 --learning-rate 0.001 --target-sync-steps 200 --dqn-target-mode double --actions forward,back,guard-stand,guard-crouch,stand-lp,stand-mp,stand-hp,stand-lk,stand-mk,stand-hk,forward-hp,crouch-lp,crouch-mp,crouch-hp,crouch-lk,crouch-mk,crouch-hk,fireball-lp,fireball-mp,fireball-hp,throw,shoryuken-lp,shoryuken-mp,shoryuken-hp,tatsu-lk,tatsu-mk,tatsu-hk --fallback-policy stand-mk --training-action-source auto --reward-risk-profile all-attacks --reward-risk-window-decisions 15 --reward-attack-no-damage-cost 0.3 --reward-attack-punished-cost 1.0 --reward-shoryuken-no-damage-extra-cost 0.0 --reward-shoryuken-punished-extra-cost 0.5 --reward-jump-attack-no-damage-extra-cost 0.0 --reward-jump-attack-punished-extra-cost 0.0 --reward-guard-success-bonus 0.0 --reward-guard-success-window-decisions 6 --reward-guard-threat-max-dx 120 --reward-passive-guard-cost 0.3 --reward-far-guard-cost 0.5 --reward-spacing-target-min-dx 50 --reward-spacing-target-max-dx 120 --reward-spacing-improve-bonus 0.5 --reward-spacing-worsen-cost 0.2 --reward-spacing-maintain-bonus 0.1 --reward-spacing-threat-back-bonus 0.3 --engine-outcome-training-mode prefer-engine-action --engine-outcome-window-decisions 15 --engine-outcome-action-windows fireball-lp=45,fireball-mp=45,fireball-hp=45,tatsu-lk=25,tatsu-mk=25,tatsu-hk=25 --engine-outcome-hit-bonus 1.0 --engine-outcome-no-damage-cost 0.2 --engine-outcome-punished-cost 1.0 --engine-outcome-oversample 1 --engine-outcome-action-oversamples fireball-lp=10,fireball-mp=20,fireball-hp=8,shoryuken-lp=4,shoryuken-mp=6,shoryuken-hp=8,tatsu-lk=6,tatsu-mk=6,tatsu-hk=6 --batch-sampling balanced --balanced-batch-ratios movement=0.3,normal=0.3,special=0.4 --epsilon 0.05 --seed 7 --log-interval 500 --eval-limit 5000 --diagnostic-top-n 12`
  - reported `DQN published version=17`, `experiences=58719`, `target_mode=double`, and `loss=0.011467 avg_loss=0.011811`.
- same-observation compare passed:
  - `python3 tools/compare_dqn_models.py logs/rl-transitions-cpu-demo-schema-v3-4-3-3.ndjson logs/rl-transitions-human-demo-schema-v3-4-3-3.ndjson --model v9=model/dqn-mixdemo-schema-v3-ground-specials-v9 --model v11=model/dqn-mixdemo-schema-v3-ground-specials-v11 --model v16b=model/dqn-mixdemo-schema-v3-ground-specials-v16b --model v17=model/dqn-mixdemo-schema-v3-ground-specials-v17 --limit 5000 --top-n 8 --focus-actions crouch-hp,stand-mk,fireball-lp,fireball-mp,fireball-hp,guard-stand,guard-crouch --focus-rank-limit 3 --training-action-source auto`
  - reported `COMPARE v9 -> v17 changed=1/5000`.

Follow-up:
- treat v9 as the stronger live candidate than v17 unless a separate live run contradicts the offline comparison.
- implement an opt-in DQN inference reranker or action-support prior that can penalize low-support or context-inappropriate top actions without retraining.
- compare any reranked policy against v9/v17 on the same observation slice before live testing.

## 2026-04-30: Review V16 Conservative Penalty A/B Results

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / DQN sparse-action overestimation control

Files changed:
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- record the completed v16a/v16b conservative-penalty A/B review.
- decide whether the conservative penalty is enough to make the ground-specials DQN recipe a default.

Implementation notes:
- reviewed `model/dqn-mixdemo-schema-v3-ground-specials-v16a/current.json` and `model/dqn-mixdemo-schema-v3-ground-specials-v16b/current.json`.
- both models used the same fresh schema-v3 mixed CPU-demo + human-demo logs, `3000` steps, balanced batch sampling, `all-attacks` risk shaping, engine-outcome oversampling, and the same 27-action ground-specials action set.
- v16a conservative config:
  - `action_penalty=0.3`, `min_action_count=300`, `negative_mean_extra=0.2`
  - scaled conservative cost: `14.943`
- v16b conservative config:
  - `action_penalty=1.0`, `min_action_count=1000`, `negative_mean_extra=1.0`
  - scaled conservative cost: `96.3`
- metadata-level greedy comparison over the saved `5000` eval rows:
  - v9 no-penalty baseline: top `stand-lp=26.72%`, `crouch-hp=26.16%`, `fireball-hp=25.10%`, `stand-hk=19.44%`, `guard-crouch=2.00%`
  - v11 no-penalty baseline: top `stand-lp=26.48%`, `crouch-hp=26.26%`, `fireball-hp=25.14%`, `stand-hk=19.54%`, `guard-crouch=2.00%`
  - v16a: top `crouch-hp=26.62%`, `stand-lp=25.72%`, `fireball-hp=25.42%`, `stand-hk=19.62%`, `guard-crouch=2.02%`
  - v16b: top `crouch-hp=27.92%`, `fireball-hp=26.52%`, `stand-lp=22.58%`, `stand-hk=20.24%`, `guard-crouch=2.02%`
- same-slice `compare_dqn_models.py --limit 5000` comparison:
  - v9: `stand-lp=36.3%`, `fireball-hp=27.5%`, `crouch-hp=24.0%`, `stand-hk=9.3%`, `guard-crouch=1.7%`
  - v11: `stand-lp=36.0%`, `fireball-hp=27.6%`, `crouch-hp=24.1%`, `stand-hk=9.3%`, `guard-crouch=1.7%`
  - v16a: `stand-lp=35.4%`, `fireball-hp=28.1%`, `crouch-hp=24.2%`, `stand-hk=9.4%`, `guard-crouch=1.7%`
  - v16b: `stand-lp=31.4%`, `fireball-hp=30.5%`, `crouch-hp=25.1%`, `stand-hk=9.5%`, `guard-crouch=1.7%`
  - v9 -> v16a changed only `47/5000` rows; v9 -> v16b changed `263/5000` rows.
- conclusion:
  - conservative penalty does not create a new guard collapse; `guard-crouch` stays near `1.7%` on the same-slice compare and near `2%` in saved metadata.
  - it also does not create an LP/MP fireball collapse; `fireball-lp` remains `0%` top1 and `fireball-mp` remains negligible.
  - the stronger v16b setting mostly shifts probability away from `stand-lp` into `fireball-hp` and `crouch-hp`.
  - `stand-mk` is not the active collapse in this run; it is `0%` top1 across the compared ground-specials models.
  - v16a/v16b should not become the default recipe yet; sparse-action overestimation remains, with `crouch-hp`, `stand-lp`, `stand-hk`, and `fireball-hp` still dominating the policy surface.
- marked the conservative-penalty A/B checklist item complete, but kept the Double DQN / inference-reranking review open.

Validation:
- metadata summary passed:
  - `jq` summaries over v9, v11, v12, v16a, and v16b actor metadata.
- same-observation compare passed:
  - `python3 tools/compare_dqn_models.py logs/rl-transitions-cpu-demo-schema-v3-4-3-3.ndjson logs/rl-transitions-human-demo-schema-v3-4-3-3.ndjson --model v9=model/dqn-mixdemo-schema-v3-ground-specials-v9 --model v11=model/dqn-mixdemo-schema-v3-ground-specials-v11 --model v16a=model/dqn-mixdemo-schema-v3-ground-specials-v16a --model v16b=model/dqn-mixdemo-schema-v3-ground-specials-v16b --limit 5000 --top-n 8 --focus-actions crouch-hp,stand-mk,fireball-lp,fireball-mp,fireball-hp,guard-stand,guard-crouch --focus-rank-limit 3 --training-action-source auto`
  - reported `COMPARE v9 -> v16a changed=47/5000` and `COMPARE v9 -> v16b changed=263/5000`.

Follow-up:
- keep conservative penalty opt-in rather than default for now.
- review Double DQN, clipped target values, or inference-time reranking / priors as the next sparse-action-overestimation control.
- avoid further tuning that only shifts collapse among `stand-lp`, `stand-hk`, `crouch-hp`, and `fireball-hp` without adding a clearer action-support prior or target-value correction.

## 2026-04-30: Validate Fresh Transition Schema V3 Demo Logs

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / transition action-label cleanup

Files changed:
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- record that fresh schema-v3 CPU-demo and human-demo transition logs are valid enough to use as the next retraining baseline.
- close the post-schema-v3 validation checklist item before long-run DQN retraining.

Implementation notes:
- telemetry build, deployment, CPU-demo collection, human-demo collection, and first-pass validation were completed before this documentation sync.
- validated `logs/rl-transitions-cpu-demo-schema-v3-4-3-3.ndjson`:
  - rows: `122276`
  - schema versions: `{3: 122276}`
  - demo policy rows: `policy_nonzero_rows=0`
  - analyzer source breakdown: `none:83991,input:36708,engine:1577`
  - engine labels include Ryu Hadouken, Shoryuken, Tatsumaki, throw, Shinkuu Hadouken, crouch normals, Joudan, and jump attacks.
  - input labels include guard, walk/back, jump, normals, and throw intent.
- validated `logs/rl-transitions-human-demo-schema-v3-4-3-3.ndjson`:
  - rows: `18849`
  - schema versions: `{3: 18849}`
  - demo policy rows: `policy_nonzero_rows=0`
  - analyzer source breakdown: `input:9682,none:8697,engine:470`
  - engine labels include Ryu Hadouken, Shoryuken, Tatsumaki, throw, Shinkuu Hadouken, normals, and jump attacks.
  - input labels include walk/back, stand/crouch normals, guard, jump, throw, and back-jump attack intent.
- marked the Milestone 6 schema-v3 fresh-log validation checklist item complete.

Validation:
- CPU-demo analyzer passed:
  - `python3 tools/analyze_rl_transitions.py logs/rl-transitions-cpu-demo-schema-v3-4-3-3.ndjson --training-action-source auto --limit 12`
  - reported `action_label_source training_action_source=auto counts=none:83991,input:36708,engine:1577`.
  - reported `ENGINE_OUTCOME_SUMMARY ... events=1577`.
- human-demo analyzer passed:
  - `python3 tools/analyze_rl_transitions.py logs/rl-transitions-human-demo-schema-v3-4-3-3.ndjson --training-action-source auto --limit 12`
  - reported `action_label_source training_action_source=auto counts=input:9682,none:8697,engine:470`.
  - reported `ENGINE_OUTCOME_SUMMARY ... events=470`.
- direct schema / policy-family check passed:
  - `python3 -c '<schema and action-label summary over CPU-demo and human-demo logs>'`
  - reported schema v3 only and `policy_nonzero_rows=0` for both demo logs.
- fresh CPU-demo DQN smoke passed:
  - `python3 tools/train_dqn_learner.py logs/rl-transitions-cpu-demo-schema-v3-4-3-3.ndjson --model-dir /tmp/rl-dqn-fresh-schema-v3-smoke --model-version 16 --limit 1200 --steps 2 --batch-size 16 --hidden-sizes 8 --actions forward,back,guard-stand,guard-crouch,stand-mk,crouch-hp,fireball-lp,fireball-mp,fireball-hp,shoryuken-hp --fallback-policy stand-mk --training-action-source auto --reward-risk-profile none --engine-outcome-training-mode prefer-engine-action --engine-outcome-window-decisions 15 --engine-outcome-action-windows fireball-lp=45,fireball-mp=45,fireball-hp=45 --log-interval 1 --eval-limit 200 --diagnostic-top-n 10`
  - reported `DQN published version=16`, `experiences=237`, `engine_outcome=prefer-engine-action:16/24`, `included=221 excluded=21`, and `engine_input_fallback=8`.
  - smoke emitted a greedy collapse warning for `fireball-lp 80.5%`; this is a policy-quality signal for later A/B work, not a schema validation blocker.

Follow-up:
- use only fresh schema-v3 logs for the next long-run DQN retraining pass.
- run the planned v16-style ground-specials conservative-penalty A/B comparison.
- define replay-buffer mixing metadata for human-demo, CPU-demo, and remote-agent episodes before treating mixed replay import as settled.

## 2026-04-29: Add Conservative Action Penalty Plan And Trainer Flags

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / DQN sparse-action overestimation control

Files changed:
- `tools/train_dqn_learner.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- make sparse-action overestimation an explicit A/B path after v11-v15 showed that pure command tuning shifts collapse between `crouch-hp`, `stand-mk`, `throw`, and fireball variants instead of solving it.
- add a small opt-in trainer-side regularization step without changing transition schema, C-side logging, OBS payloads, or live DQN inference.

Implementation notes:
- recorded the support-aware conservative DQN penalty rollout plan in `docs/plan-remote-rl-agent.md`.
- added `--conservative-action-penalty` and `--conservative-min-action-count`:
  - after replay building, actions with fewer than the configured post-build training examples receive a raw reward cost on each replay experience.
- added `--conservative-negative-mean-extra`:
  - actions with non-positive observed mean reward receive an additional raw reward cost.
  - if no observed rows exist for an action, the post-build training mean is used.
- added `--conservative-exempt-actions` so engine-labeled specials or other trusted curriculum actions can be excluded from the checks.
- conservative penalties run after engine-outcome delayed credit, HP-delta consumption, macro-continuation credit, and all other reward shaping, then update the replay experiences and action reward diagnostics.
- stdout and model metadata now record `conservative_penalty` diagnostics with adjusted experience count, raw/scaled cost, low-count actions, non-positive-mean actions, and per-action cost totals.

Validation:
- Python compile passed:
  - `python3 -m py_compile tools/train_dqn_learner.py`
- diff whitespace check passed:
  - `git diff --check -- tools/train_dqn_learner.py docs/plan-remote-rl-agent.md`
- conservative penalty smoke passed:
  - `python3 tools/train_dqn_learner.py logs/rl-transitions-cpu-demo-schema-v3-4-3-3.ndjson --model-dir /tmp/rl-dqn-conservative-smoke --model-version 1 --limit 1200 --steps 2 --batch-size 16 --hidden-sizes 8 --actions forward,back,guard-stand,guard-crouch,stand-mk,crouch-hp,fireball-lp,fireball-mp,fireball-hp,shoryuken-hp --fallback-policy stand-mk --training-action-source auto --reward-risk-profile all-attacks --reward-risk-window-decisions 15 --reward-risk-action-windows fireball-lp=45,fireball-mp=45,fireball-hp=45 --reward-attack-no-damage-cost 0.3 --reward-attack-punished-cost 1.0 --engine-outcome-training-mode prefer-engine-action --engine-outcome-window-decisions 15 --engine-outcome-action-windows fireball-lp=45,fireball-mp=45,fireball-hp=45 --engine-outcome-hit-bonus 1.0 --engine-outcome-no-damage-cost 0.2 --engine-outcome-punished-cost 1.0 --conservative-action-penalty 0.2 --conservative-min-action-count 10 --conservative-negative-mean-extra 0.1 --conservative-exempt-actions fireball-lp,fireball-mp,fireball-hp,shoryuken-hp --log-interval 1 --eval-limit 200 --diagnostic-top-n 10`
  - diagnostics reported `conservative_penalty=events:99 raw_cost:10.7 scaled_cost:0.107`, with low-count penalties applied to `stand-mk,crouch-hp`.

Follow-up:
- train a v16-style ground-specials model from the v9/v11 command family with conservative penalties enabled.
- compare whether `crouch-hp`, `stand-lp`, `stand-hk`, and `stand-mk` top1/top3 rates drop without creating a new `guard` / `fireball` collapse.

## 2026-04-29: Record Anti-Air Shoryuken Feature Plan

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / DQN anti-air behavior

Files changed:
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- capture the plan for teaching DQN to use Shoryuken as an anti-air against opponent jump-ins.
- avoid a misleading shortcut where raw routine ids are added only to training logs, or a large global engine hit bonus accidentally buffs every special / normal hit instead of specifically teaching anti-air.

Decision notes:
- current DQN feature vectors still use compact numeric spacing/threat fields and do not include `obs_opp_routine_1` / `obs_opp_routine_2`.
- future anti-air learner visibility should prefer derived, schema-versioned features such as `obs_opp_airborne`, `obs_opp_jump_toward`, `obs_opp_above_self`, and `obs_anti_air_threat`.
- train and live inference must receive the same OBS payload fields before any model is trained with those features; transition-log-only fields would create train/live mismatch.
- reward shaping should use a targeted anti-air Shoryuken bonus rather than a large global `--engine-outcome-hit-bonus`, so fireball / tatsu / throw / normal hits are not all boosted at the same time.

Follow-up:
- validate opponent jump-in routine states with fresh schema-v3 logs and analyzer summaries.
- bump the compact OBS payload schema when the derived anti-air fields are promoted.
- collect a focused human-demo anti-air Shoryuken log before expecting offline DQN to learn reliable jump-in punishment.
- add compare diagnostics for Shoryuken rank/top-k specifically when `obs_anti_air_threat=1`.

## 2026-04-29: Add Balanced Batch Sampling For Offline DQN

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / DQN action distribution experiments

Files changed:
- `tools/train_dqn_learner.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- prevent high-frequency movement / guard rows from dominating every offline DQN gradient batch.
- give low-frequency but learner-important action families such as fireball / shoryuken / tatsu a stable per-batch presence without further changing raw replay logs.

Implementation notes:
- added `--batch-sampling uniform|balanced`; `uniform` preserves historical random replay sampling.
- added `--balanced-batch-ratios movement=0.4,normal=0.3,special=0.3` for action-family batch targets.
- action-family grouping is:
  - movement: `forward`, `back`, `guard-stand`, `guard-crouch`
  - normal: normals and `throw`
  - special: `fireball-*`, `shoryuken-*`, `tatsu-*`
- stdout and model metadata now include `batch_sampling` diagnostics with ratios, target counts, and replay pool counts.

Validation:
- Python compile passed:
  - `python3 -m py_compile tools/train_dqn_learner.py`
- uniform smoke preserved baseline sampler behavior:
  - `python3 tools/train_dqn_learner.py logs/rl-transitions-cpu-demo-schema-v3-4-3-3.ndjson --model-dir /tmp/rl-dqn-balanced-uniform-smoke --model-version 12 --limit 800 --steps 2 --batch-size 4 --hidden-sizes 8 --actions forward,back,guard-stand,guard-crouch,stand-mk,fireball-lp,fireball-mp,fireball-hp,shoryuken-lp,tatsu-hk --fallback-policy stand-mk --training-action-source auto --reward-risk-profile none --engine-outcome-training-mode prefer-engine-action --engine-outcome-window-decisions 15 --engine-outcome-action-windows fireball-lp=45,fireball-mp=45,fireball-hp=45 --engine-outcome-no-damage-cost 0.5 --engine-outcome-punished-cost 2.0 --log-interval 1 --eval-limit 100 --diagnostic-top-n 10`
  - reported `batch_sampling=mode:uniform` and zero target counts.
- balanced smoke confirmed family target counts:
  - same smoke shape with `--batch-size 64 --engine-outcome-oversample 1 --engine-outcome-action-oversamples fireball-lp=5,fireball-mp=5,fireball-hp=5,shoryuken-lp=4,tatsu-hk=4 --batch-sampling balanced --balanced-batch-ratios movement=0.4,normal=0.3,special=0.3`
  - reported `batch_sampling=mode:balanced`, `target:movement:26,normal:19,special:19`, and pools `movement:136,normal:1,special:72`.

Follow-up:
- train `model/dqn-mixdemo-schema-v3-ground-specials-v6` with ground + specials actions, specials oversampling, and balanced batch sampling; compare fireball top2/top3 against v5.

## 2026-04-29: Add Engine Outcome Oversampling For Offline DQN

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / DQN action distribution experiments

Files changed:
- `tools/train_dqn_learner.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- make low-frequency engine-labeled moves, especially Ryu fireballs and specials, easier to A/B test without recollecting logs.
- keep raw transition logs and normal input replay rows unchanged while allowing included engine-outcome experiences to be duplicated in the DQN replay set.

Implementation notes:
- added `--engine-outcome-oversample N`, where `1` preserves the previous one-experience-per-event behavior.
- added `--engine-outcome-action-oversamples action=N,...` for per-action replay copy counts.
- engine outcome diagnostics now record `training_experiences`, `oversample_extra_experiences`, and `training_scaled_reward_sum`; action count/reward diagnostics reflect the replay distribution after oversampling.

Validation:
- Python compile passed:
  - `python3 -m py_compile tools/train_dqn_learner.py`
- baseline oversampling smoke passed:
  - `python3 tools/train_dqn_learner.py logs/rl-transitions-cpu-demo-schema-v3-4-3-3.ndjson --model-dir /tmp/rl-dqn-engine-oversample-baseline-smoke --model-version 11 --limit 800 --steps 2 --batch-size 4 --hidden-sizes 8 --actions forward,back,guard-stand,guard-crouch,stand-mk,fireball-lp,fireball-mp,fireball-hp,shoryuken-lp,tatsu-hk --fallback-policy stand-mk --training-action-source auto --reward-risk-profile none --engine-outcome-training-mode prefer-engine-action --engine-outcome-window-decisions 15 --engine-outcome-action-windows fireball-lp=45,fireball-mp=45,fireball-hp=45 --engine-outcome-no-damage-cost 0.5 --engine-outcome-punished-cost 2.0 --log-interval 1 --eval-limit 100 --diagnostic-top-n 10`
  - reported `engine_oversample=15/+0`, preserving the default one-copy behavior.
- specials oversampling smoke passed:
  - same smoke command plus `--engine-outcome-oversample 2 --engine-outcome-action-oversamples fireball-lp=5,fireball-mp=5,fireball-hp=5,shoryuken-lp=4,tatsu-hk=4`
  - reported `engine_oversample=72/+57`; `fireball-hp` count rose from `6` to `30`, `fireball-mp` from `3` to `15`, and `fireball-lp` from `3` to `15`.
- mixed full-action smoke passed:
  - first `5000` rows from CPU-demo + human-demo with full action set and specials oversampling reported `engine_outcome=prefer-engine-action:64/73`, `engine_oversample=424/+360`, `excluded=0`, and `engine_input_fallback=9`.

Follow-up:
- run a mixed CPU-demo + human-demo all-action v4 train with specials oversampling and compare focus ranks for `fireball-lp`, `fireball-mp`, and `fireball-hp` against v3.

## 2026-04-29: Fix Engine Outcome Subset Fallback

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / schema-v3 trainer cleanup

Files changed:
- `tools/train_dqn_learner.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- fix `--engine-outcome-training-mode prefer-engine-action` when an engine-labeled move exists but the action is not present in the configured DQN action subset.
- preserve input-labeled demo rows instead of allowing `--training-action-source auto` to select the same unsupported `engine_*` action a second time.

Implementation notes:
- when engine outcome experience creation fails for a demo row with `engine_*`, the trainer now forces that row's normal replay path through `select_training_action(row, "input")`.
- `BuildDiagnostics` now records `engine_outcome_input_fallback_rows`.
- the published summary line now prints `engine_input_fallback=<n>`.

Validation:
- Python compile passed:
  - `python3 -m py_compile tools/train_dqn_learner.py`
- subset fallback smoke passed:
  - `python3 tools/train_dqn_learner.py logs/rl-transitions-cpu-demo-schema-v3-4-3-3.ndjson --model-dir /tmp/rl-dqn-engine-fallback-smoke --model-version 10 --limit 800 --steps 2 --batch-size 4 --hidden-sizes 8 --actions forward,back,guard-stand,guard-crouch,stand-mk --fallback-policy stand-mk --training-action-source auto --reward-risk-profile none --engine-outcome-training-mode prefer-engine-action --engine-outcome-window-decisions 15 --log-interval 1 --eval-limit 100 --diagnostic-top-n 8`
  - reported `engine_input_fallback=17` and `action_source_counts=input:164,none:636`, confirming excluded engine events no longer return as normal engine-source exclusions.
- full-action smoke on the current CPU-demo schema-v3 log passed:
  - `python3 tools/train_dqn_learner.py logs/rl-transitions-cpu-demo-schema-v3-4-3-3.ndjson --model-dir /tmp/rl-dqn-engine-fallback-full-smoke --model-version 10 --steps 2 --batch-size 64 --hidden-sizes 8 --epsilon 0.05 --seed 7 --gamma 0.95 --actions forward,back,guard-stand,guard-crouch,stand-lp,stand-mp,stand-hp,stand-lk,stand-mk,stand-hk,forward-hp,crouch-lp,crouch-mp,crouch-hp,crouch-lk,crouch-mk,crouch-hk,fireball-lp,fireball-mp,fireball-hp,throw,jump-forward-lp,jump-forward-mp,jump-forward-hp,jump-forward-lk,jump-forward-mk,jump-forward-hk,jump-neutral-lp,jump-neutral-mp,jump-neutral-hp,jump-neutral-lk,jump-neutral-mk,jump-neutral-hk,jump-back-lp,jump-back-mp,jump-back-hp,jump-back-lk,jump-back-mk,jump-back-hk,shoryuken-lp,shoryuken-mp,shoryuken-hp,tatsu-lk,tatsu-mk,tatsu-hk --fallback-policy stand-mk --training-action-source auto --reward-risk-profile none --engine-outcome-training-mode prefer-engine-action --engine-outcome-window-decisions 15 --engine-outcome-action-windows fireball-lp=45,fireball-mp=45,fireball-hp=45,tatsu-lk=25,tatsu-mk=25,tatsu-hk=25 --engine-outcome-no-damage-cost 0.5 --engine-outcome-punished-cost 2.0 --log-interval 1 --eval-limit 100 --diagnostic-top-n 10`
  - reported `engine_outcome=prefer-engine-action:251/291`, `excluded=0`, and `engine_input_fallback=40`.

Follow-up:
- retrain the CPU-demo schema-v3 DQN model with model version +1 so the live model benefits from the fallback fix.

## 2026-04-29: Rename DQN Demo Attribution To Engine Outcome

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / schema-v3 trainer cleanup

Files changed:
- `tools/rl_probe_server.py`
- `tools/train_dqn_learner.py`
- `tools/analyze_rl_transitions.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- align DQN trainer/analyzer terminology with schema v3's `policy_*`, `input_*`, and `engine_*` label families.
- replace the confusing `demo-attribution` trainer concept with `engine-outcome`, because delayed outcome credit is based on observed `engine_*` move starts.
- remove the data-loss trap where an engine-labeled row whose action was not in the configured DQN `--actions` subset skipped the normal input fallback path.

Implementation notes:
- `tools/train_dqn_learner.py` now exposes:
  - `--engine-outcome-training-mode off|prefer-engine-action`
  - `--engine-outcome-window-decisions`
  - `--engine-outcome-action-windows`
  - `--engine-outcome-stop-at-next-event`
  - `--engine-outcome-hit-bonus`
  - `--engine-outcome-no-damage-cost`
  - `--engine-outcome-punished-cost`
- deprecated hidden aliases for the old `--demo-attribution-*` flags still map to the new engine-outcome config for short-term command compatibility and print a warning.
- schema-v2-era modes `augment` and `replace-demo` now fail fast; v3 training should use `prefer-engine-action`.
- `prefer-engine-action` now uses the engine outcome experience only when the engine-labeled action is present in the configured action subset; otherwise it records an excluded engine-outcome event and lets the row continue through the normal `--training-action-source auto` path.
- stdout and model metadata now use `engine_outcome=...` / `engine_outcome_stats` instead of `demo_attr=...` / `demo_attribution_stats`.
- `tools/analyze_rl_transitions.py` now uses `--engine-outcome-window-decisions` and `--engine-outcome-stop-at-next-event`; hidden old aliases remain for short-term compatibility.
- `tools/rl_probe_server.py` now provides `engine_outcome_present()` and `engine_outcome_action_name()` helpers over schema-v3 `engine_*` fields.

Validation:
- Python compile passed:
  - `python3 -m py_compile tools/train_dqn_learner.py tools/analyze_rl_transitions.py tools/rl_probe_server.py`
- help output shows the new engine-outcome trainer/analyzer flags.
- schema-v3 CPU-demo DQN smoke with engine outcome enabled passed:
  - `python3 tools/train_dqn_learner.py logs/rl-transitions-cpu-demo-schema-v3-4-3-3.ndjson --model-dir /tmp/rl-dqn-engine-outcome-smoke --model-version 9 --limit 800 --steps 2 --batch-size 4 --hidden-sizes 8 --actions forward,back,guard-stand,guard-crouch,stand-mk,fireball-lp,fireball-mp,fireball-hp,shoryuken-lp,tatsu-hk --fallback-policy stand-mk --training-action-source auto --reward-risk-profile none --engine-outcome-training-mode prefer-engine-action --engine-outcome-window-decisions 15 --engine-outcome-action-windows fireball-lp=45,fireball-mp=45,fireball-hp=45 --engine-outcome-no-damage-cost 0.5 --engine-outcome-punished-cost 2.0 --log-interval 1 --eval-limit 100 --diagnostic-top-n 8`
  - reported `engine_outcome=prefer-engine-action:15/17`.
- subset fallback smoke passed:
  - `python3 tools/train_dqn_learner.py logs/rl-transitions-cpu-demo-schema-v3-4-3-3.ndjson --model-dir /tmp/rl-dqn-engine-outcome-subset-smoke --model-version 9 --limit 800 --steps 2 --batch-size 4 --hidden-sizes 8 --actions forward,back,guard-stand,guard-crouch,stand-mk --fallback-policy stand-mk --training-action-source auto --reward-risk-profile none --engine-outcome-training-mode prefer-engine-action --engine-outcome-window-decisions 15 --log-interval 1 --eval-limit 100 --diagnostic-top-n 8`
  - reported `engine_outcome=prefer-engine-action:0/17` and still built `experiences=137`, proving excluded engine labels no longer discard input fallback rows.
- analyzer smoke passed:
  - `python3 tools/analyze_rl_transitions.py logs/rl-transitions-cpu-demo-schema-v3-4-3-3.ndjson --tail-rows 800 --engine-outcome-window-decisions 15 --limit 5`
  - reported `ENGINE_OUTCOME_SUMMARY ... events=12`.
- `git diff --check` passed.
- canonical MiSTer telemetry build passed:
  - `tools/mister/build-game.sh --flavor telemetry`

Follow-up:
- use only `--engine-outcome-*` flags in new train commands.
- after the next long CPU-demo run, compare `engine_outcome_stats.excluded_events` against the action subset to catch missing action names before live testing.

## 2026-04-29: Remove Hot-Path Local Transition File Writes

Milestone:
- Milestone 4: Decision ledger and transition logging / Milestone 6 demo-data collection performance follow-up

Files changed:
- `src/rl/rl_session.c`
- `docs/config.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- remove synchronous MiSTer local transition-log writes from the decision-finalization hot path.
- rely on the existing per-episode transition batch upload to the probe server for demo and remote-RL data collection.
- reduce human-demo FPS spikes caused by repeated SD/FAT `open -> write -> close` operations.

Implementation notes:
- removed `RLSession_AppendTransitionLogLine()`.
- `RLSession_FinalizeLedgerEntry()` now formats each NDJSON row once and appends it only to the in-memory episode batch.
- episode-close still calls `RLNet_QueueTransitionBatch()` so the probe server receives the same rows over the existing TCP transition port.
- local MiSTer fallback file persistence is intentionally gone; if the probe server is not running or `rl-network = off`, transition rows are not persisted locally.

Validation:
- `rg -n 'AppendTransitionLogLine|SDL_IOFromFile\(log_path|rl-transitions\.ndjson' src/rl/rl_session.c docs/config.md docs/plan-remote-rl-agent.md` confirmed no runtime local append path remains in `src/rl/rl_session.c`.
- `git diff --check` passed.
- canonical telemetry build passed:
  - `tools/mister/build-game.sh --flavor telemetry`

Follow-up:
- deploy the telemetry package and collect a human-demo log through probe-server `--transition-log`; check FPS stability and transition batch counters `TBQ/TBS/TBA/TBF`.
- if long episodes still show spikes, profile `RLSession_FormatTransitionLogLine()` and transition batch `SDL_realloc` growth next.

## 2026-04-29: Strict Transition Schema V3 Cleanup

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / transition action-label cleanup

Files changed:
- `src/rl/rl_session.c`
- `tools/rl_probe_server.py`
- `tools/train_dqn_learner.py`
- `tools/analyze_rl_transitions.py`
- `tools/compare_dqn_models.py`
- `docs/rl-policy-action-taxonomy.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- remove legacy transition action-label fields now that old transition logs have been cleared.
- make schema v3 rows carry only the explicit `policy_*`, `input_*`, and `engine_*` action-label families.
- make Python replay/training/analyzer tools fail fast on schema 1/2 instead of guessing legacy semantics.

Implementation notes:
- C-side transition export now stamps `transition_schema_version=3`.
- C-side NDJSON no longer emits:
  - `requested_policy_action_id`
  - `requested_policy_sub_action_id`
  - `requested_policy_action_step`
  - `executed_policy_action_id`
  - `executed_policy_sub_action_id`
  - `executed_policy_action_step`
  - `demo_attributed_policy_action_id`
  - `demo_attributed_policy_sub_action_id`
  - `demo_attributed_routine2`
  - `demo_attributed_kind_of_waza`
  - `demo_attributed_current_attack`
  - `demo_attribution_source`
  - `demo_attribution_lag_frames`
- demo engine attribution now writes only `engine_*`; demo input labels continue to use `input_*`; remote RL policy rows continue to use `policy_*`.
- `tools/rl_probe_server.py` now defines `TRANSITION_SCHEMA_VERSION = 3`, requires schema v3 in replay normalization and action selection, and no longer has legacy action/wire fallback paths.
- `tools/train_dqn_learner.py` action-start gating now uses `input_action_step` for demo rows and `policy_executed_action_step` for remote rows.
- analyzer / compare diagnostics now report strict v3 label sources only (`policy`, `input`, `engine`, `none`).

Validation:
- `python3 -m py_compile tools/rl_probe_server.py tools/train_dqn_learner.py tools/analyze_rl_transitions.py tools/compare_dqn_models.py` passed.
- `git diff --check` passed.
- synthetic v3 analyzer smoke passed:
  - `python3 tools/analyze_rl_transitions.py /tmp/rl-transitions-schema-v3-smoke.ndjson --training-action-source auto --limit 12`
  - reported `action_label_source training_action_source=auto counts=none:3,engine:1`.
- synthetic v3 DQN smoke passed:
  - `python3 tools/train_dqn_learner.py /tmp/rl-transitions-schema-v3-smoke.ndjson --model-dir /tmp/rl-dqn-schema-v3-smoke --model-version 3 --steps 2 --batch-size 2 --hidden-sizes 8 --actions forward,guard-stand,fireball-lp --fallback-policy stand-mk --training-action-source auto --reward-risk-profile none --demo-attribution-training-mode prefer-demo-action --demo-attribution-window-decisions 15 --log-interval 1 --eval-limit 4 --diagnostic-top-n 5`
  - reported `demo_attr=prefer-demo-action:1/1`.
- synthetic v3 compare smoke passed:
  - `python3 tools/compare_dqn_models.py /tmp/rl-transitions-schema-v3-smoke.ndjson --model SMOKE=/tmp/rl-dqn-schema-v3-smoke --tail-rows 4 --top-n 5 --focus-actions fireball-lp`
  - reported `LOG_ACTION_SOURCE ... counts=none:3,engine:1`.
- strict schema rejection passed:
  - `python3 tools/analyze_rl_transitions.py /tmp/rl-transitions-schema-v2-reject.ndjson`
  - failed with `transition_schema_version=2 expected=3`.
- canonical MiSTer telemetry build passed:
  - `tools/mister/build-game.sh --flavor telemetry`

Follow-up:
- deploy the new telemetry package and collect fresh schema-v3 `cpu-demo` and `human-demo` logs.
- verify demo logs have `policy_* == 0`, engine-attributed specials in `engine_*`, and walk/back/guard intent in `input_*`.
- use only fresh v3 logs for the next long-run DQN retraining pass.

## 2026-04-29: Transition Schema V2 Analyzer Source Breakdown Step 4

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / transition action-label cleanup

Files changed:
- `tools/rl_probe_server.py`
- `tools/train_dqn_learner.py`
- `tools/analyze_rl_transitions.py`
- `tools/compare_dqn_models.py`
- `docs/rl-policy-action-taxonomy.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- make training, analysis, and comparison use the same canonical action-label source selector.
- expose label-source counts so schema-v2 logs can be checked before long-run retraining.

Implementation notes:
- moved the DQN action selector into `tools/rl_probe_server.py` as shared helpers:
  - `select_training_action(row, source_mode)`
  - `demo_attribution_present(row)`
  - `demo_attributed_action_name(row)`
  - `action_name_from_policy_meta(action_id, sub_action_id)`
- `tools/train_dqn_learner.py` now calls the shared selector instead of carrying a private copy.
- `tools/analyze_rl_transitions.py` now accepts `--training-action-source` and prints `action_label_source` counts plus top actions per source.
- `tools/compare_dqn_models.py` now accepts `--training-action-source` and prints a `LOG_ACTION_SOURCE` summary before model greedy-action output.
- schema-v1 logs continue to report `legacy`; schema-v2 logs should report `policy`, `input`, `engine`, `engine-legacy`, or `none` depending on selected mode and row contents.

Validation:
- `python3 -m py_compile tools/rl_probe_server.py tools/train_dqn_learner.py tools/analyze_rl_transitions.py tools/compare_dqn_models.py` passed.
- selector smoke passed:
  - schema-v2 demo row with engine/input/policy labels selected `fireball-hp` under `auto`, `guard-crouch` under `input`, and `stand-mp` under `policy`.
  - schema-v1 row selected legacy `guard-crouch` under `auto`.
- analyzer smoke on `logs/rl-transitions-cpu-demo-r12-v1-4-3-3.ndjson` printed `action_label_source training_action_source=auto counts=legacy:200`.
- compare smoke on the same log printed `LOG_ACTION_SOURCE training_action_source=auto rows=200 counts=legacy:200`.
- one-step DQN smoke still printed `action_source_counts=legacy:200`.
- `git diff --check` passed.

Follow-up:
- deploy / run a fresh schema-v2 mixed remote + CPU-demo log and confirm:
  - remote rows use `policy`.
  - CPU-demo specials use `engine`.
  - CPU-demo walk / guard rows use `input`.
  - rows without a usable label use `none` rather than a misleading legacy label.

## 2026-04-29: Transition Schema V2 DQN Action Source Step 3

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / transition action-label cleanup

Files changed:
- `tools/train_dqn_learner.py`
- `docs/rl-policy-action-taxonomy.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- let offline DQN replay choose the action-label source explicitly after schema-v2 rows split policy, input, and engine identities.
- keep default behavior compatible with old schema-v1 logs while enabling schema-v2 logs to use cleaner demo and remote labels.

Implementation notes:
- added `--training-action-source auto|policy|input|engine|prefer-engine`.
- default `auto` behavior:
  - schema-v2 demo row: use `engine_*` when present, otherwise `input_*`.
  - schema-v2 non-demo row: use `policy_executed_*`.
  - schema-v1 row: keep legacy `executed_policy_*` / wire fallback behavior.
- explicit `engine` can train from v2 `engine_*` and falls back to legacy `demo_attributed_*` for older logs.
- explicit `prefer-engine` uses engine first, then input, then policy, with schema-v1 legacy fallback.
- demo-attribution delayed-credit logic now treats v2 `engine_*` attribution as present and uses it before legacy `demo_attributed_*`.
- DQN metadata and stdout now include `training_action_source` and `action_source_counts`.

Validation:
- `python3 -m py_compile tools/train_dqn_learner.py` passed.
- targeted selector smoke passed:
  - schema-v2 demo row with engine/input/policy labels selected `fireball-hp` under `auto`, `guard-crouch` under `input`, and `stand-mp` under `policy`.
  - schema-v1 row selected legacy `guard-crouch` under `auto`.
- schema-v2 `build_experiences()` smoke passed and produced `action_source_counts={'engine': 1, 'policy': 1}` for a two-row mixed demo/remote sample.
- one-step DQN smoke on `logs/rl-transitions-cpu-demo-r12-v1-4-3-3.ndjson` passed with `--training-action-source auto`; because this is a schema-v1 log, diagnostics correctly printed `action_source_counts=legacy:200`.
- `git diff --check` passed.

Follow-up:
- update analyzer / compare tools to report label-source breakdown.
- collect a fresh schema-v2 mixed remote + CPU-demo log after deploying the new C-side build, then validate source counts before long-run retraining.

## 2026-04-29: Transition Schema V2 Python Replay Ingestion Step 2

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / transition action-label cleanup

Files changed:
- `tools/rl_probe_server.py`
- `docs/rl-policy-action-taxonomy.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- make Python replay normalization preserve the schema-v2 action identity fields emitted by new C-side transition logs.
- keep old logs compatible without synthesizing misleading v2 policy fields from legacy demo labels.

Implementation notes:
- `learner_replay_row()` now preserves:
  - `transition_schema_version`
  - `policy_requested_*`
  - `policy_executed_*`
  - `input_*`
  - `engine_*`
- missing `transition_schema_version` defaults to `1`; missing v2 action groups default to zero.
- the function deliberately does not copy legacy `requested_*` / `executed_*` into `policy_*`, because old `human-demo` / `cpu-demo` rows used those legacy fields as input-derived labels.
- DQN/training action source selection is unchanged in this step.

Validation:
- `python3 -m py_compile tools/rl_probe_server.py` passed.
- smoke check confirmed v2 fields survive `learner_replay_row()` and a legacy row gets `transition_schema_version=1` with zeroed v2 fields.
- `git diff --check` passed.

Follow-up:
- add `--training-action-source auto|policy|input|engine|prefer-engine` and update DQN/compare/analyzer code paths to report action-label source breakdown.

## 2026-04-29: Transition Schema V2 C-Side Export Step 1

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / transition action-label cleanup

Files changed:
- `src/rl/rl_session.c`
- `docs/rl-policy-action-taxonomy.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- start transition schema v2 by writing separate action identity field groups in new C-side transition rows.
- keep the legacy fields untouched so existing logs, parsers, DQN training commands, and comparison tools remain compatible until the Python rollout steps are implemented.

Implementation notes:
- transition rows now include `transition_schema_version:2`.
- remote action packets populate `policy_requested_*` when accepted and `policy_executed_*` when the queued remote or repeated-last policy action is executed.
- human-demo / CPU-demo rows populate `input_action_id`, `input_sub_action_id`, `input_action_step`, and `input_label_source` from the existing demo input mapper.
- Ryu demo engine attribution now mirrors the existing `demo_attributed_*` label into `engine_*` fields:
  - `engine_action_id`
  - `engine_sub_action_id`
  - `engine_routine_1`
  - `engine_routine_2`
  - `engine_kind_of_waza`
  - `engine_current_attack`
  - `engine_label_source`
  - `engine_lag_frames`
- no Python ingestion or DQN action-source selection behavior changed in this step.

Validation:
- `git diff --check` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed and rebuilt `src/rl/rl_session.c`.

Follow-up:
- update `tools/rl_probe_server.py` replay ingestion to preserve the v2 fields while keeping legacy fallback.
- add `--training-action-source auto|policy|input|engine|prefer-engine` only after ingestion can retain both schemas.

## 2026-04-29: Document Transition Schema V2 Rollout Plan

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / transition action-label cleanup

Files changed:
- `docs/rl-policy-action-taxonomy.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- record a staged rollout plan for separating policy-selected actions, input-derived demo labels, and engine-attributed move labels.
- avoid adding more overloaded fields to `requested_policy_action_id` / `executed_policy_action_id` before the schema semantics are clear.
- explicitly defer guard-specific diagnostic fields such as `guard_intent`, `guard_engine_candidate`, and `guard_contact_confirmed` until after the core action-identity split is implemented.

Implementation notes:
- added `Transition Schema V2 Rollout Plan` to the action taxonomy document.
- planned v2 field groups are:
  - `policy_*`: remote RL/DQN requested/executed action identity.
  - `input_*`: best-effort controller / CPU-demo input label.
  - `engine_*`: SF3 engine-recognized action-start label from R1/R2/KW/AK attribution.
- documented that `engine_*` means "engine-recognized move start near this decision row", not "current per-frame engine state"; future per-row state should use a separate `obs_self_engine_state_*` family.
- added Milestone 6 checklist items for the staged implementation:
  - C-side NDJSON export.
  - Python replay ingestion.
  - DQN `--training-action-source`.
  - analyzer / compare source breakdown.
  - short mixed remote + CPU-demo validation before long-run retraining.

Validation:
- documentation-only update; reviewed the diff for placement and wording.

Follow-up:
- implement step 1 by adding schema-v2 fields to the C decision ledger / transition export while preserving legacy fields.
- then update Python ingestion before changing DQN training defaults.

## 2026-04-29: Tighten Demo Guard Labels And Guard Bonus

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / CPU-demo guard-label cleanup

Files changed:
- `src/rl/rl_session.c`
- `tools/train_dqn_learner.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- stop CPU-demo / human-demo `DOWN_BACK` input from always becoming `guard-crouch`.
- reduce the false guard samples that made DQN overvalue crouch guard / passive defense.
- make guard success reward require actual contact evidence by default, not just `opp_attack=1` plus no self damage.

Implementation notes:
- `RLSession_DeriveDemoPolicyMeta()` now uses stricter demo guard labels:
  - `BACK` remains `guard-stand` when there is opponent attack threat in range, and can also use engine stand-guard candidate states.
  - `DOWN_BACK` becomes `guard-crouch` only when there is opponent attack threat in range or engine crouch-guard candidate states.
  - no-threat `DOWN_BACK` stays neutral/untrained instead of being labeled as guard.
- engine guard candidate helpers currently use:
  - stand: `R1=0 && R2 in {27,28,31,32,33}`
  - crouch: `R1=0 && R2 in {29,31,32,33}`
- `tools/train_dqn_learner.py` adds `--reward-guard-success-require-contact` / `--no-reward-guard-success-require-contact`.
  - default is enabled.
  - when enabled, guard success bonus requires `obs_self_contact_reaction_state` inside the guard window and no self HP damage.
  - passive / far guard costs remain based on clean no-damage guard windows.
- diagnostics now print `require_contact:1` in `guard_shape=...`.

Validation:
- `python3 -m py_compile tools/train_dqn_learner.py` passed.
- source-level smoke confirmed no-threat `DOWN_BACK` is no longer labeled `guard-crouch`; it remains neutral unless threat or engine guard candidate evidence is present.
- small DQN smoke passed on `logs/rl-transitions-cpu-demo-r12-v1-4-3-3.ndjson` with guard shaping enabled and printed `require_contact:1`.

Follow-up:
- rebuild/deploy the telemetry MiSTer binary before collecting the next CPU-demo log; Python-only reruns cannot change C-side demo labels in old logs.
- collect a fresh CPU-demo R1/R2 log and confirm `guard-crouch` no longer contains a large idle/no-threat bucket.
- retrain all-actions DQN on the fresh log and compare guard rates plus `--focus-actions fireball-lp,fireball-mp,fireball-hp`.

## 2026-04-29: Add Focus-Action DQN Compare Diagnostics

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / offline DQN policy diagnosis

Files changed:
- `tools/compare_dqn_models.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- make the DQN comparison tool inspect any caller-specified action group instead of hard-coding Hadouken / fireball analysis.
- answer whether an action is absent because it is truly low-value or because it is near top-1 but consistently blocked by another action.

Implementation notes:
- added `--focus-actions`, a comma-separated list of canonical tabular/DQN action names.
- added `--focus-rank-limit`, defaulting to `3`, for top-N blocker diagnostics.
- focus output reports:
  - rank distribution: `top1`, `top2`, `top3`, `top4plus`.
  - best focus action counts.
  - actions that block the focus group when the focus action is inside the selected top-N but not top-1.
  - mean and p90 Q gap between the selected top action and the best focus action.
  - the same breakdown inside `atk0/atk1 x close/mid/far` threat-distance buckets.

Validation:
- `python3 -m py_compile tools/compare_dqn_models.py` passed.
- focus smoke against `logs/rl-transitions-cpu-demo-v1-4-3-3.ndjson` and `model/dqn-cpudemo-allactions-demo-outcome-v2` passed with `--focus-actions fireball-lp,fireball-mp,fireball-hp`.

Follow-up:
- use this output to compare Hadouken, Shoryuken, Tatsumaki, and selected normal groups before adding replay upsampling or extra action-specific rewards.

## 2026-04-29: Consume Demo-Claimed HP Deltas During DQN Replay Build

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / CPU-demo delayed-credit cleanup

Files changed:
- `tools/train_dqn_learner.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- prevent one HP delta from rewarding both the engine-attributed move that caused it and a later unrelated input-based row.
- make long-window projectile credit cleaner: if a Hadouken chip is claimed by `fireball-lp`, the later `guard` / `neutral` row where the chip lands no longer receives that same `delta_opp_hp` reward.

Implementation notes:
- `build_experiences()` now copies each row into per-episode working rows so training-only HP-delta mutation does not alter the raw loaded row list.
- when `add_demo_attribution_experience()` finds an HP outcome inside its effective window, it:
  - computes the demo-attributed reward from that available HP delta.
  - records claimed diagnostics.
  - zeroes the claimed `delta_opp_hp` / `delta_self_hp` on the working rows before subsequent input-based replay processing.
- later input-based rewards, risk windows, guard shaping, spacing shaping, and position shaping see only unclaimed HP deltas in that episode pass.
- `demo_attr` diagnostics now print `claimed:<events>/<opp_hp>/<self_hp>`.

Validation:
- `python3 -m py_compile tools/train_dqn_learner.py` passed.
- targeted smoke on `logs/rl-transitions-cpu-demo-v1-4-3-3.ndjson`, `run=3`, `episode=15`, `decision=79`:
  - before demo attribution, `decision=96` had `delta_opp_hp=1`.
  - `fireball-lp` claimed that outcome and received `+1` raw / `+0.01` scaled reward.
  - after claim, the working row for `decision=96` had `delta_opp_hp=0`, so its input-based training reward became `0`.
- 5000-row DQN smoke passed:
  - `demo_attr=prefer-demo-action:59/86`
  - `early:57`
  - `claimed:57/233/140`
  - `action_stats` still included `fireball-lp`, `fireball-mp`, `fireball-hp`, `tatsu-mk`, `guard-crouch`, and `stand-mk`.

Follow-up:
- rerun the all-actions CPU-demo A/B models and compare whether `guard` drops when projectile/chip credit is no longer duplicated.
- decide whether fireball chip needs an action-specific contact bonus after inspecting the new non-duplicated reward stats.

## 2026-04-29: Stop Demo Attribution Windows At First HP Outcome

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / CPU-demo delayed-credit cleanup

Files changed:
- `tools/train_dqn_learner.py`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- treat `--demo-attribution-window-decisions` and `--demo-attribution-action-windows` as maximum tracking windows.
- for long-window moves such as Hadouken, stop the effective outcome window at the first self/opponent HP delta, because that means the move was either rewarded by hit/chip or punished by counter-hit.
- if no HP delta occurs before the configured maximum window, keep the existing no-damage interpretation for whiff / evade / parry-like outcomes.

Implementation notes:
- `add_demo_attribution_experience()` now scans from the attributed event row to the configured maximum window and cuts `window_end` to the first row with `delta_opp_hp > 0` or `delta_self_hp > 0`.
- the demo attribution diagnostics now print `early:<count>` and metadata includes `early_outcome_events`.
- `--demo-attribution-stop-at-next-event` still applies after the first-HP-delta shortening; it can only make the effective window shorter.

Validation:
- `python3 -m py_compile tools/train_dqn_learner.py` passed.
- targeted smoke on `logs/rl-transitions-cpu-demo-v1-4-3-3.ndjson`, `run=3`, `episode=15`, `decision=79`:
  - event is `fireball-lp` (`1229/lp`)
  - configured action window was `45`
  - effective outcome window stopped at `decision=96`, the first row with `delta_opp_hp=1`
  - `early_outcome_events=1`
  - raw reward remained `+1`, scaled reward `+0.01`
  - next state for the demo-attributed experience matches decision `96`, not the end of the full 45-decision maximum window.

Follow-up:
- decide whether to also consume/claim the HP delta so the later input-based row does not simultaneously reward unrelated `guard` / `neutral` actions.
- evaluate whether fireball chip needs an action-specific contact bonus after duplicate-credit cleanup.

## 2026-04-29: Rename LP Hadouken Learner Action To Fireball-LP

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / special-move action naming cleanup

Files changed:
- `tools/rl_probe_server.py`
- `tools/train_dqn_learner.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- remove the ambiguous legacy learner action name `fireball` from the default tabular/DQN action set.
- make all Hadouken learner actions strength-explicit: `fireball-lp`, `fireball-mp`, and `fireball-hp`.
- keep old commands, logs, and model manifests readable by treating `fireball` / `ryu-fireball` as aliases for `fireball-lp`.

Implementation notes:
- `TABULAR_ACTION_NAMES` now contains `fireball-lp`, `fireball-mp`, and `fireball-hp`; bare `fireball` is no longer a trainable/default action name.
- `--policy fireball` and `--policy ryu-fireball` remain scripted LP Hadouken aliases for fixed-policy probes.
- `canonical_tabular_action_name()` maps `fireball` and `ryu-fireball` to `fireball-lp`.
- model/action coercion now canonicalizes legacy action names in `actions`, q-tables, q-counts, DQN `--actions`, and per-action window flags.
- transition/demo attribution maps Ryu Hadouken LP metadata `(1229, lp)` to `fireball-lp`; old partial labels fall back to `fireball-lp`.

Validation:
- `python3 -m py_compile tools/rl_probe_server.py tools/train_dqn_learner.py tools/compare_dqn_models.py tools/analyze_rl_transitions.py` passed.
- action registry smoke confirmed:
  - `tabular_count 45`
  - `fireball-lp` is in `TABULAR_ACTION_NAMES`
  - bare `fireball` is not in `TABULAR_ACTION_NAMES`
  - `fireball` and `ryu-fireball` canonicalize to `fireball-lp`
  - `forward+LP` and `(Ryu Hadouken, lp)` both map to `fireball-lp`
  - `parse_action_names("fireball,fireball-lp,ryu-fireball,fireball-mp")` dedupes to `("fireball-lp", "fireball-mp")`
- DQN smoke passed with `fireball-lp`, `fireball-mp`, and `fireball-hp` in `--actions` and per-action demo windows:
  - `actions=11`
  - `demo_attr=prefer-demo-action:67/86`
  - `action_stats` included `fireball-hp`, `fireball-lp`, and `fireball-mp`.

Follow-up:
- update active CPU-demo training commands to use `fireball-lp` and `fireball-lp=...` windows.
- keep accepting bare `fireball` only as compatibility input, not as a new model action name.

## 2026-04-29: Split Ryu Shoryuken And Tatsumaki Strength Variants

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / special-move action refinement

Files changed:
- `tools/rl_probe_server.py`
- `tools/train_dqn_learner.py`
- `tools/compare_dqn_models.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- add LP/MP/HP Shoryuken and LK/MK/HK Tatsumaki Senpukyaku as first-class learner/probe actions.
- keep CPU-demo engine-attributed Shoryuken/Tatsumaki strengths semantically clean instead of collapsing regular variants into `shoryuken-mp` / `tatsu-mk`.

Implementation notes:
- `TABULAR_ACTION_NAMES` now includes:
  - `shoryuken-lp`, `shoryuken-mp`, `shoryuken-hp`
  - `tatsu-lk`, `tatsu-mk`, `tatsu-hk`
- scripted probe policies now expose the same strength-specific names.
- legacy aliases remain:
  - `shoryuken` -> `shoryuken-hp`
  - `tatsu` -> `tatsu-lk`
- strength-specific scripted macros emit:
  - Shoryuken: `forward, down, down-forward, down-forward+P, neutral, neutral`
  - Tatsumaki: `down, down-back, back, back+K, neutral, neutral`
- DQN Shoryuken extra risk costs now apply to all `shoryuken-*` variants instead of only `shoryuken-mp`.
- `tools/compare_dqn_models.py` now aggregates `shoryuken_rate`, `base_shoryuken_to_other`, and `other_to_shoryuken` across all Shoryuken variants.

Validation:
- `python3 -m py_compile tools/rl_probe_server.py tools/train_dqn_learner.py tools/compare_dqn_models.py` passed.
- action registry smoke confirmed:
  - `tabular_count 45`
  - no missing tabular or scripted entries for `shoryuken-lp`, `shoryuken-mp`, `shoryuken-hp`, `tatsu-lk`, `tatsu-mk`, `tatsu-hk`
  - policy metadata round-trips for all six new/expanded special variants
  - `shoryuken` canonicalizes to `shoryuken-hp`; `tatsu` canonicalizes to `tatsu-lk`
- DQN smoke passed with all six variants in `--actions`, `--reward-risk-action-windows`, and `--demo-attribution-action-windows`:
  - `actions=15`
  - `demo_attr=prefer-demo-action:79/86`
  - `action_stats` included `shoryuken-lp`, `tatsu-lk`, `tatsu-mk`, and Hadouken variants in the sampled rows
- compare smoke passed and reported aggregate `shoryuken_rate=100.0%` for a synthetic collapsed smoke model selecting `shoryuken-lp`, confirming compare aggregation includes non-MP Shoryuken variants.

Follow-up:
- retrain the CPU-demo special-action DQN with `shoryuken-lp`, `shoryuken-mp`, `shoryuken-hp`, `tatsu-lk`, `tatsu-mk`, and `tatsu-hk` in `--actions`.
- include per-action windows for all Tatsu variants when using delayed-credit training, e.g. `tatsu-lk=25,tatsu-mk=25,tatsu-hk=25`.

## 2026-04-29: Add Prefer-Demo-Action DQN Replay Mode

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / CPU-demo move-outcome training

Files changed:
- `tools/train_dqn_learner.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- train CPU-demo / human-demo attacks from engine-attributed `demo_attributed_*` move labels instead of input-based `executed_*` labels when an attributed move is present.
- preserve unattributed demo rows, such as walk / guard / spacing examples, as normal input-based experiences.
- support per-action risk windows so projectile and long-animation actions are not forced to use the same no-damage / punished lookahead as quick normals.

Implementation notes:
- `--demo-attribution-training-mode` now accepts `prefer-demo-action`.
- `prefer-demo-action` behavior:
  - demo row with `demo_attributed_*`: close the previous input-based experience, add one engine-attributed demo experience, and skip the row's input-based action experience.
  - demo row without `demo_attributed_*`: keep the normal input-based replay path.
  - non-demo row: keep the normal input-based replay path.
- this differs from:
  - `augment`, which adds engine-attributed experiences but also keeps the same row's input-based experience.
  - `replace-demo`, which skips input-based replay for all demo rows, including unattributed walk / guard rows.
- `--reward-risk-action-windows action=N,...` now overrides `--reward-risk-window-decisions` per action for input-based risk shaping; this pairs with the existing `--demo-attribution-action-windows` for engine-attributed delayed credit.

Validation:
- `python3 -m py_compile tools/train_dqn_learner.py` passed.
- prefer-demo-action smoke passed:
  ```sh
  python3 tools/train_dqn_learner.py logs/rl-transitions-cpu-demo-v1-4-3-3.ndjson --model-dir /tmp/rl-dqn-prefer-demo-smoke --model-version 1 --limit 5000 --steps 5 --batch-size 8 --hidden-sizes 16 --actions forward,back,guard-stand,guard-crouch,throw,stand-mk,fireball,fireball-mp,fireball-hp,shoryuken-mp,tatsu-mk --demo-attribution-training-mode prefer-demo-action --demo-attribution-window-decisions 15 --demo-attribution-action-windows fireball=45,fireball-mp=45,fireball-hp=45,tatsu-mk=25 --demo-attribution-no-damage-cost 0.5 --demo-attribution-punished-cost 2.0 --log-interval 5 --eval-limit 200 --diagnostic-top-n 8
  ```
- smoke output confirmed mixed behavior:
  - `demo_attr=prefer-demo-action:79/86`
  - `experiences=1999`
  - `included=1920`, showing unattributed input-based demo rows were preserved
  - `action_stats` included attributed specials such as `fireball-hp`, `fireball`, and `tatsu-mk`

Follow-up:
- train the CPU-demo special-action model with `--demo-attribution-training-mode prefer-demo-action` and compare it against `augment` and `replace-demo`.
- if Hadouken still remains low, next diagnostics should test a no-throw action subset and fireball-focused data rather than further increasing global shaping.

## 2026-04-28: Split Ryu Fireball Strength Variants

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / special-move action refinement

Files changed:
- `tools/rl_probe_server.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- stop collapsing CPU-demo Hadouken MP/HP engine-attributed move labels into the LP `fireball` learner action.
- allow DQN/tabular actors to explicitly choose `fireball`, `fireball-mp`, or `fireball-hp`.

Implementation notes:
- `TABULAR_ACTION_NAMES` now includes `fireball-mp` and `fireball-hp` alongside the legacy LP `fireball` action.
- `SCRIPTED_POLICY_CHOICES` now exposes `--policy fireball-mp` and `--policy fireball-hp` for fixed-policy probes.
- `POLICY_ACTION_META_BY_NAME` maps:
  - `fireball` -> Ryu Hadouken / `lp`
  - `fireball-mp` -> Ryu Hadouken / `mp`
  - `fireball-hp` -> Ryu Hadouken / `hp`
- scripted macros now emit strength-specific QCF endings:
  - `fireball`: `down-back, down, down-forward, forward+LP, neutral, neutral`
  - `fireball-mp`: `down-back, down, down-forward, forward+MP, neutral, neutral`
  - `fireball-hp`: `down-back, down, down-forward, forward+HP, neutral, neutral`
- `demo_attributed_*` replay now keeps `fireball-mp` / `fireball-hp` as distinct action names because those names are live learner actions.

Validation:
- `python3 -m py_compile tools/rl_probe_server.py tools/train_dqn_learner.py tools/analyze_rl_transitions.py tools/compare_dqn_models.py` passed.
- action registry smoke printed:
  - `fireball ... meta=(1229, 1) seq=['0x7', '0x2', '0x8', '0x14', '0x0', '0x0']`
  - `fireball-mp ... meta=(1229, 2) seq=['0x7', '0x2', '0x8', '0x24', '0x0', '0x0']`
  - `fireball-hp ... meta=(1229, 3) seq=['0x7', '0x2', '0x8', '0x44', '0x0', '0x0']`
  - `tabular_actions 41`
  - `missing_exec []`
- CPU-demo attribution check on `logs/rl-transitions-cpu-demo-v1-4-3-3.ndjson` now reports:
  - `fireball 640`
  - `fireball-mp 391`
  - `fireball-hp 1320`
  - `shoryuken-mp 326`
  - `tatsu-mk 488`
- full training published `model/dqn-cpudemo-allnormals-fireballvariants-corner-v1` with:
  - `experiences=92487`
  - `actions=40`
  - `demo_attr=augment:3594/3779`
  - action stats: `fireball-hp:1275/17.23/0.014`, `fireball:611/4.22/0.007`, `fireball-mp:381/4.92/0.013`
  - greedy top actions: `throw 30.7%`, `guard-stand 22.2%`, `stand-mk 20.1%`, `forward 14.5%`, `guard-crouch 12.4%`, `fireball 0.0%`
- comparing the previous collapsed-specials model against the variants model on the same 5000-row CPU-demo tail changed `297/5000` greedy choices.

Findings:
- the previous lack of Hadouken in greedy policy was not only caused by MP/HP being collapsed into LP; after splitting variants, `fireball-mp` and `fireball-hp` still did not become top-1 greedy actions.
- in the current feature/reward setup, far no-threat observations still rank guard/forward/throw above Hadouken variants, so the next bottleneck is state/reward/data quality rather than action-label availability.

Follow-up:
- collect or synthesize targeted Hadouken data where far-range fireball leads to positive outcomes and unsafe close/mid fireball is punished.
- consider fireball-specific reward shaping or richer projectile/opponent-airborne observations before trying to force more Hadouken through scalar rewards alone.
- keep `fireball-mp` / `fireball-hp` in future DQN action sets so CPU-demo labels remain semantically clean.

## 2026-04-28: Add DQN Corner Position Reward Shaping

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / anti-turtle DQN reward shaping

Files changed:
- `tools/train_dqn_learner.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- reduce the live all-normals DQN tendency to over-defend, retreat to its own corner, and keep guarding at long range.
- add offline reward-shaping knobs that can penalize clean corner guard/back starts and reward forward movement that increases own back-edge distance.

Implementation notes:
- `tools/train_dqn_learner.py` now supports corner position shaping:
  - `--reward-corner-back-edge-threshold`
  - `--reward-corner-guard-cost`
  - `--reward-corner-back-cost`
  - `--reward-corner-escape-bonus`
  - `--reward-corner-escape-min-delta`
- shaping applies only to `executed_policy_action_step == 0` rows near the player's own back edge.
- guard/back costs and forward escape bonus apply only when the short lookahead window has no self HP damage, preserving natural HP-delta punishment for actually getting hit.
- training stdout and model metadata now include `position_bonus`, `position_cost`, `position_net`, and a `position_shape=...` diagnostics line.

Validation:
- `python3 -m py_compile tools/train_dqn_learner.py` passed.
- smoke training against `logs/rl-transitions-cpu-demo-v1-4-3-3.ndjson` printed:
  - `position_bonus=2130.0`
  - `position_cost=28172.5`
  - `position_shape=corner_back_edge<=80 corner_guard:11343/17014.5 corner_back:5579/11158.0 escape:1065/2130.0 net:-26042.5`
- full CPU-demo all-normal retrains were compared on the same 5000-row CPU-demo tail:
  - baseline `model/dqn-cpudemo-allnormals-v1`: `guard-crouch 33.3%`, `guard-stand 25.7%`, `forward 12.9%`, attack rate `27.9%`
  - `model/dqn-cpudemo-allnormals-corner-v3`: `guard-crouch 25.0%`, `guard-stand 23.2%`, `forward 19.5%`, attack rate `32.4%`
  - `model/dqn-cpudemo-allnormals-corner-v4`: `guard-crouch 20.6%`, `guard-stand 19.8%`, `forward 19.1%`, attack rate `40.4%`
- targeted corner-bucket analysis showed the important limitation:
  - non-corner `atk0_far` improved from `guard-crouch 70.1% / forward 8.2%` to `guard-crouch 36.9% / forward 30.7%` in v4.
  - true `corner_atk0_far` stayed heavily defensive (`guard-crouch 98.0%` baseline to `96.0%` in v4), so this is not sufficient evidence that corner escape is learned.

Findings:
- position shaping is useful for reducing generic far-range passivity.
- the current CPU-demo dataset does not contain enough successful corner-escape alternatives for reward shaping alone to flip the policy at `corner + far + no opponent attack`.
- pushing corner costs higher mainly changes non-corner far behavior and overall attack/throw rate before it reliably fixes the exact corner turtle state.

Follow-up:
- collect targeted corner-escape demo data where the controlled side is near its own back edge, walks forward out of the corner, and then resumes offense/guard.
- consider adding a corner-specific observation feature or finer distance/corner buckets if the MLP still fails to separate trapped-corner states from general far states.
- do not treat `model/dqn-cpudemo-allnormals-corner-v4` as the final anti-turtle answer; it is a useful MiSTer smoke candidate only if we want to test whether more active non-corner behavior feels better.

## 2026-04-28: Expand Basic Normal Action Support And Train CPU-Demo DQN

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / all-normals CPU-demo DQN bootstrap

Files changed:
- `tools/rl_probe_server.py`
- `tools/train_dqn_learner.py`
- `tools/analyze_rl_transitions.py`
- `tools/compare_dqn_models.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- support all standing, crouching, forward-jump, neutral-jump, and back-jump LP/MP/HP/LK/MK/HK basic normals in the probe-side action registry.
- train a first CPU-demo DQN model that can choose defense, movement, throw, and all basic normals without enabling fireball / Shoryuken / Tatsumaki shortcuts.

Implementation notes:
- `tools/rl_probe_server.py` now generates normal action names from shared button and jump-direction tables.
- direct fixed-wire support covers all standing and crouching normals; jump normals use the existing six-step macro shape: jump direction, jump direction, jump direction + button, jump direction + button, neutral, neutral.
- policy metadata now maps all new crouch and jump normals to stance/direction-specific policy action IDs and button sub-actions.
- `tools/train_dqn_learner.py` now derives generic attack-risk and jump-risk sets from `rl.TABULAR_ACTION_NAMES`, so newly registered normals automatically participate in `--reward-risk-profile all-attacks`.
- `tools/analyze_rl_transitions.py` and `tools/compare_dqn_models.py` now consume the expanded registry instead of carrying stale hard-coded action lists.

Validation:
- `python3 -m py_compile tools/rl_probe_server.py tools/train_dqn_learner.py tools/analyze_rl_transitions.py tools/compare_dqn_models.py` passed.
- action registry smoke printed `actions 39` and `missing_exec []`, confirming every registered action has either a fixed wire or scripted macro path.
- one-step DQN smoke passed with the 35-action all-basic-normal subset against `logs/rl-transitions-cpu-demo-v1-4-3-3.ndjson`, publishing `/tmp/dqn-allnormals-smoke`.
- full training command published `model/dqn-cpudemo-allnormals-v1` with:
  - `experiences=89426`
  - `actions=35`
  - `guard_net=9737.6`
  - `spacing_net=5623.4`
  - `demo_attr=augment:533/3779`
  - greedy top actions: `guard-stand 33.8%`, `stand-mk 20.6%`, `guard-crouch 19.7%`, `throw 13.0%`, `forward 12.5%`, `back 0.3%`
- comparison on the CPU-demo tail showed `model/dqn-cpudemo-allnormals-v1` reduced attack rate from `37.7%` in `model/dqn-cpudemo-basic-defense-throw-v2` to `27.9%`, while adding `throw 16.3%` to the greedy tail distribution and keeping jump greed very low.

Findings:
- normal coverage from the existing CPU-demo log is good for standing normals and crouching normals, but sparse for jump normals.
- normal actions with zero trainable samples in this log: `jump-forward-lp`, all neutral-jump normals, and all back-jump normals.
- tiny jump coverage exists for `jump-forward-mp` (`3`), `jump-forward-hp` (`5`), `jump-forward-lk` (`1`), `jump-forward-mk` (`51`), and `jump-forward-hk` (`1`).
- greedy evaluation selected jump normals only `12/5000` rows (`jump-neutral-mp`), so the all-normal model did not collapse into jump spam.
- throw entered the greedy tail distribution (`814/5000`, `16.3%`), mostly at close/mid range, which is stronger than the prior basic-defense-throw v2 model where throw did not appear in greedy top actions.

Follow-up:
- live-test `model/dqn-cpudemo-allnormals-v1` before changing reward shaping again.
- collect more CPU-demo or human-demo coverage if neutral/back jump normals should become real learner options; the existing CPU-demo log is not sufficient for those moves.
- review whether `back` remains under-selected because far/passive guard shaping still makes guard safer than retreat.

## 2026-04-28: Document Ryu R1/R2 Mapping Source Trace

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / R1/R2 ordinary-state validation

Files changed:
- `docs/rl-policy-action-taxonomy.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- preserve the SF3 source-code path used to interpret raw `routine_no[1]` / `routine_no[2]` values, with Ryu as the first worked example.
- make future all-character move mapping repeatable: trace `R1/R2` through engine dispatch tables, then validate with overlay/log values before promoting runtime decoders.

Implementation notes:
- documented `plmain.c::plmain_lv_02` as the `R1` high-level state dispatcher.
- documented `plpnm.c::Player_normal` / `plpnm_lv_00[R2]` as the shared ordinary-state path for walk, crouch, jump, guard, and related normal states.
- documented `plpat.c::Player_attack`, `plpat_lv_00[R2]`, and `plxx_extra_attack_table[player_number]` as the attack path split for common versus character-specific routines.
- documented `pls03.c::hissatsu_setup_union` and `set_attack_routine_number` as the paths that set `R1=4` and assign attack `R2`.
- documented Ryu's `plpat02.c::pl02_extra_attack` / `pl02_exatt_table[R2 - 16]` source trace for Hadouken, Shoryuken, Tatsumaki Senpukyaku, super-art paths, Air Tatsumaki, and Joudan Sokutou Geri.
- recorded provisional `R1=0` ordinary-state labels and marked guard/jump/block labels as validation aids until fresh raw-R1/R2 logs confirm them.

Validation:
- doc references were checked against the SF3 source files listed above.
- `git diff --check -- docs/rl-policy-action-taxonomy.md docs/remote-rl-agent-engineering-log.md` passed.

Follow-up:
- use a fresh raw-R1/R2 transition log to confirm `normal.walk-*`, `normal.guard-*`, `normal.crouch`, and `normal.jump-*` before training from those ordinary-state labels.
- repeat the same source trace for Ken/Akuma next because they share some Ryu-like handlers but have character-specific routine meanings.

## 2026-04-28: Add Raw Routine Transition Diagnostics

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / R1/R2 ordinary-state validation

Files changed:
- `src/rl/rl_session.c`
- `tools/rl_probe_server.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- write raw self/opponent `routine_no[1]` and `routine_no[2]` snapshots into transition rows so `tools/analyze_rl_transitions.py` can classify ordinary engine states such as walk, crouch, jump, guard, attack, damage/contact, catch, and caught.
- keep these as diagnostic replay fields only; they are not promoted into UDP OBS payloads, tabular state keys, or DQN feature vectors.

Implementation notes:
- transition JSON now includes:
  - `obs_self_routine_1`
  - `obs_self_routine_2`
  - `obs_opp_routine_1`
  - `obs_opp_routine_2`
- the values are captured from the same observation used for the existing spacing/state row snapshot.
- `tools/rl_probe_server.py` preserves the four fields in `learner_replay_row()` so local replay/import paths do not strip them.

Validation:
- `python3 -m py_compile tools/rl_probe_server.py tools/analyze_rl_transitions.py` passed.
- `python3 tools/analyze_rl_transitions.py logs/rl-transitions-cpu-demo-v1-4-3-3.ndjson --tail-rows 200 --limit 8` passed against an older log; as expected it fell back to derived coarse states because that log predates the raw fields.
- `git diff --check -- src/rl/rl_session.c tools/rl_probe_server.py docs/plan-remote-rl-agent.md docs/remote-rl-agent-engineering-log.md` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed and rebuilt `src/rl/rl_session.c`.

Follow-up:
- collect a fresh short human-demo or CPU-demo log and confirm `ENGINE_STATE_ACTION_BY_ROUTINE` shows raw `normal.walk-*`, `normal.guard-*`, `normal.crouch`, and `normal.jump-*` labels before using these labels as learner targets.

## 2026-04-28: Add Engine State Action Analyzer Mapping

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / R1/R2 ordinary-state validation

Files changed:
- `tools/analyze_rl_transitions.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- add an analyzer-only `engine_state_action` view keyed by `(routine_no[1], routine_no[2])` so ordinary engine states such as walk, crouch, jump, guard, damage/contact, catch/caught, and attack routines can be counted before promoting more raw routine fields into the transition schema.
- keep the mapping diagnostic/provisional: raw `R1/R2` fields are required for precise ordinary-state labels, while older logs with only derived routine flags fall back to coarse `attack.r2-unknown` / `damage-contact.r2-unknown`.

Implementation notes:
- `tools/analyze_rl_transitions.py` now recognizes common future raw field spellings such as `self_routine_1`, `self_routine_2`, `obs_self_routine1`, and opponent equivalents.
- `R1=0` maps selected normal-state `R2` values to provisional labels such as `normal.walk-forward`, `normal.walk-back`, `normal.crouch`, `normal.jump-air`, and `normal.guard-*`.
- `R1=4` maps Ryu attack `R2` values to known engine move labels (`hadouken`, `shoryuken`, `tatsumaki-senpukyaku`, throw/catch, and provisional super/special paths); non-Ryu or unvalidated entries stay as routine IDs.
- new output sections:
  - `ENGINE_STATE_ACTION_SUMMARY`
  - `ENGINE_STATE_ACTION_BY_SIDE`
  - `ENGINE_STATE_ACTION_BY_SIDE_DX`
  - `ENGINE_STATE_ACTION_BY_ROUTINE`

Validation:
- `python3 -m py_compile tools/analyze_rl_transitions.py` passed.
- `python3 tools/analyze_rl_transitions.py --help` passed.
- `python3 tools/analyze_rl_transitions.py logs/rl-transitions-cpu-demo-v1-4-3-3.ndjson --tail-rows 200 --limit 8` passed; as expected for the current schema, it reported derived coarse states rather than raw ordinary walk/guard labels.

Follow-up:
- add raw `self_routine_1/self_routine_2` and `opp_routine_1/opp_routine_2` to a diagnostic transition-log schema only after confirming logging overhead and compatibility.
- validate `R1=0` guard/walk/jump/crouch labels with short human-demo and CPU-demo clips before using them as learner targets.

## 2026-04-28: Add Demo-Attributed DQN Reward Shaping

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / CPU-demo move-outcome training

Files changed:
- `tools/train_dqn_learner.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- let offline DQN training optionally consume engine-attributed demo move starts instead of relying only on input-based `requested_*` / `executed_*` labels.
- use the same delayed-credit outcome idea as `tools/analyze_rl_transitions.py` so CPU-demo rows can train from actual Ryu move identity (`fireball`, `shoryuken`, `tatsu`, `throw`, normals) when the exact input pulse is not visible at the decision boundary.

Implementation notes:
- `tools/train_dqn_learner.py` now has `--demo-attribution-training-mode off|augment|replace-demo`.
  - `off` is the default and preserves the old input-based DQN training path.
  - `augment` keeps normal input-based experiences and adds extra experiences from `demo_attributed_*` event rows.
  - `replace-demo` skips normal input-based experiences for `execution_source = 4/5` rows and uses only `demo_attributed_*` events for demo-sourced experience creation.
- delayed-credit shaping uses `--demo-attribution-window-decisions N` to sum future `delta_opp_hp` / `delta_self_hp` within the same episode.
- `--demo-attribution-action-windows action=N,...` is reserved for per-action window tuning; omitted actions use the global window.
- `--demo-attribution-stop-at-next-event` can make windows non-overlapping when needed, but overlapping remains available for projectile-style delayed hits.
- optional raw reward adjustments:
  - `--demo-attribution-hit-bonus`
  - `--demo-attribution-no-damage-cost`
  - `--demo-attribution-punished-cost`
- DQN metadata and stdout now record `demo_attribution_*` config and stats, including event counts, hit/no-damage/punished/trade counts, HP sums, bonus/cost totals, and scaled reward sum.

Validation:
- `python3 -m py_compile tools/train_dqn_learner.py` passed.
- `python3 tools/train_dqn_learner.py --help` shows the new demo-attribution flags.
- smoke training passed:
  ```sh
  python3 tools/train_dqn_learner.py logs/rl-transitions-cpu-demo-v1-4-3-3.ndjson --model-dir /tmp/rl-dqn-demoattr-smoke --model-version 1 --steps 10 --batch-size 8 --hidden-sizes 16 --actions fireball,shoryuken-mp,tatsu-mk,throw,jump-forward-mk,stand-mk,crouch-hk --demo-attribution-training-mode replace-demo --demo-attribution-window-decisions 10 --demo-attribution-no-damage-cost 0.5 --demo-attribution-punished-cost 2.0 --log-interval 5
  ```
- smoke result: `events=621`, `included=580`, `excluded=41`, `hit=303`, `no_damage=277`, `punished=60`, `trade=20`, `hp=1902/675`.

Follow-up:
- compare `replace-demo` versus `augment` on CPU-demo + human-demo mixes.
- tune per-action windows after fireball / throw / jump outcomes show consistent delayed-credit timing.
- decide whether demo-attributed outcomes should also drive imitation-style sampling weights instead of only Q-reward shaping.

## 2026-04-28: Add Demo-Attributed Delayed-Credit Analyzer

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / CPU-demo move-outcome analysis before DQN reward integration

Files changed:
- `tools/analyze_rl_transitions.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- classify engine-attributed demo move starts as hit, whiff/no-damage, punished, or trade using later HP deltas.
- keep credit assignment in Python analysis/reward-shaping code instead of adding derived outcome guesses to the C-side transition schema.

Implementation notes:
- `tools/analyze_rl_transitions.py` now retains parsed rows and groups them by `(run_id, episode_id)`.
- added `--demo-attribution-window-decisions N` to sum `delta_opp_hp` / `delta_self_hp` from each `demo_attributed_*` event row through the next `N` decision rows in the same episode.
- added `--demo-attribution-stop-at-next-event` for non-overlapping windows; default remains overlapping because projectiles can hit after a later input.
- new output sections:
  - `DEMO_ATTRIBUTION_SUMMARY`
  - `DEMO_ATTRIBUTED_BY_ACTION_WINDOW`
  - `DEMO_ATTRIBUTED_BY_ACTION_DX_WINDOW`
  - `DEMO_ATTRIBUTED_BY_R2_KW_WINDOW`
  - `DEMO_ATTRIBUTION_INPUT_TO_ENGINE_MISMATCH`

Validation:
- `python3 -m py_compile tools/analyze_rl_transitions.py` passed.
- `python3 tools/analyze_rl_transitions.py logs/rl-transitions-cpu-demo-v1-4-3-3.ndjson --demo-attribution-window-decisions 10 --limit 20` passed.
- `git diff --check -- tools/analyze_rl_transitions.py docs/plan-remote-rl-agent.md docs/remote-rl-agent-engineering-log.md` passed.

Smoke result:
- the short CPU-demo Ryu log produced `19` attributed events.
- with a 10-decision window, `fireball-hp` showed `6` events, `5` hit events, `1` punished/trade event, and `1` whiff/no-damage event.
- input-to-engine mismatch output confirmed the analyzer can show cases such as `neutral -> fireball-hp` and `forward -> fireball-hp`, which are exactly why engine attribution is needed for CPU-demo logs.

Follow-up:
- once the analyzer output looks stable on a longer CPU-demo log, wire the same delayed-credit outcome calculation into `tools/train_dqn_learner.py` reward shaping.

## 2026-04-28: Document Engine Move Attribution Expansion Method

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / move-label validation before extending demo attribution beyond Ryu

Files changed:
- `docs/rl-policy-action-taxonomy.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- preserve the discovered method for converting SF3 runtime attack identity into stable policy action / sub-action labels.
- make future non-Ryu expansion repeatable instead of relying on memory from the Ryu investigation.

Implementation notes:
- added `Engine Move Attribution Method` to the taxonomy document.
- documented the separation between input-based `requested_*` / `executed_*` fields and engine-observed `demo_attributed_*` fields.
- recorded the field roles:
  - `R2` / `routine_no[2]` is the primary active move / routine key.
  - `KW` / `kind_of_waza` encodes strength and normal/special punch/kick class.
  - `AK` / `current_attack` is useful for normal button identity.
  - `RS` / attack routine start is a timing hint, not a move id.
- documented the future-character workflow: source command slot -> `cmd_data.c` R2 -> `plpatXX.c` dispatch handler -> overlay validation -> runtime decoder promotion.

Validation:
- `git diff --check -- docs/rl-policy-action-taxonomy.md docs/plan-remote-rl-agent.md docs/remote-rl-agent-engineering-log.md` passed.

Follow-up:
- use the method to create per-character overlay identity draft tables before adding non-Ryu demo attribution code.

## 2026-04-28: Add Ryu Engine-Attributed Demo Action Fields

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / CPU-demo and human-demo bootstrapping data quality

Files changed:
- `src/rl/rl_session.c`
- `tools/rl_probe_server.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- preserve the existing input-based `requested_*` / `executed_*` action fields while adding a separate engine-observed move label for demo rows.
- make CPU-demo logs useful even when the CPU input pulse is not visible on the exact decision frame, by attributing the move from Ryu `routine_no[2]`, `kind_of_waza`, and `current_attack`.

Implementation notes:
- transition rows now include:
  - `demo_attributed_policy_action_id`
  - `demo_attributed_policy_sub_action_id`
  - `demo_attributed_routine2`
  - `demo_attributed_kind_of_waza`
  - `demo_attributed_current_attack`
  - `demo_attribution_source`
  - `demo_attribution_lag_frames`
- attribution only runs for demo execution sources (`human-demo` / `cpu-demo`) and currently only when the controlled character is Ryu (`agent_character_id = 2`).
- `demo_attribution_source = 1` means Ryu engine routine-start attribution (`R2 + KW`, including specials, throws, and provisional super-art routine IDs).
- `demo_attribution_source = 2` means Ryu normal-attack attribution from `current_attack` / normal `kind_of_waza`; normal stance/jump class is best-effort and uses the sampled input class when available.
- `learner_replay_row()` preserves the new fields so offline analyzers or later demo-specific training tools can consume them.

Validation:
- `git diff --check -- src/rl/rl_session.c tools/rl_probe_server.py` passed.
- `python3 -m py_compile tools/rl_probe_server.py` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed and produced `build/mister-telemetry-package`.

Follow-up:
- collect a short `cpu-demo` Ryu log and compare input-based action counts with `demo_attributed_*` counts.
- verify normal stance/jump attribution against overlay video before using normal `demo_attributed_*` labels as supervised targets.
- add non-Ryu character mappings only after their `routine_no[2]` / `kind_of_waza` tables are validated.

## 2026-04-28: Add Fight Overlay Attack Identity Probe Fields

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / move-label validation before transition schema expansion

Files changed:
- `src/rl/rl_observation.h`
- `src/rl/rl_observation.c`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- expose self-side SF3 attack identity candidate fields on the Fight debug overlay before adding them to transition logs.
- support visual validation that `routine_no[2]`, `current_attack`, and `kind_of_waza` correlate with real moves during CPU-demo / human-demo tests.

Implementation notes:
- `RLObservationV1` now captures `self_kind_of_waza` and `opp_kind_of_waza` from `plw[*].wu.kind_of_waza`.
- the Fight overlay adds `SATT R2<routine2> AK<current_attack> KW<kind_of_waza> RS<attack_routine_started>`.
- no UDP observation payload, transition row, learner state, or replay schema was changed.

Validation:
- `git diff --check` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed and produced `build/mister-telemetry-package`.

Follow-up:
- validate the overlay values against visible normals, specials, throws, and projectiles.
- only after validation, decide which of these fields should be promoted into transition logs and/or learner observations.

Runtime finding:
- `AK` / `current_attack` is useful for normal attack button identity only:
  - jump / stand / crouch normals show `010/020/040` for `LP/MP/HP` and `100/200/400` for `LK/MK/HK`.
  - specials do not currently use `AK` as a stable move identity field.
- `RS` / `self_attack_routine_started` can become nonzero during attacks, but it is not stable enough to identify which attack was performed.
- `KW` / `kind_of_waza` appears to encode attack class and strength:
  - `00/02/04` => `LP/MP/HP`
  - `01/03/05` => `LK/MK/HK`
  - `08/0A/0C` => punch-strength specials such as Hadouken and Shoryuken (`LP/MP/HP`)
  - `09/0B/0D` => kick-strength specials such as Tatsumaki Senpukyaku (`LK/MK/HK`)
- implication: `KW` is strong for normal/special strength and punch-vs-kick class, but it cannot distinguish Hadouken from Shoryuken by itself. Move identity likely needs `routine_no[2]` (`R2`) plus character id, with `KW` providing strength/category.
- `R2` / `routine_no[2]` appears to identify the active attack or motion routine, not only named special moves:
  - `16` => Hadouken
  - `17` => Shoryuken
  - `18` => Tatsumaki Senpukyaku
  - `14` => grab / catch startup path
  - `2` => throw
- updated implication: move labeling should treat `R2` as the primary move/routine id and `KW` as the strength/category modifier. The candidate transition identity tuple is now `character_id + R2 + KW`, with `AK` used mainly to label normals when helpful.
- added a provisional Ryu `R2/KW/AK` overlay identity table to `docs/rl-policy-action-taxonomy.md`:
  - confirmed normals use `AK` for button identity and `KW=00/02/04` for punches, `KW=01/03/05` for kicks.
  - confirmed Ryu specials use `R2=16/17/18` for Hadouken/Shoryuken/Tatsumaki and `KW=08/0A/0C` or `09/0B/0D` for strength/category.
  - recorded `R2=2` for completed throw and `R2=14` for grab/catch path.
  - left normal stance/jump `R2`, super-art `KW`, Joudan Sokutou Geri, and Air Tatsumaki as validation TODOs.

## 2026-04-28: Add CPU-Demo Transition Recording Mode

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / demo bootstrapping data collection

Files changed:
- `src/args.c`
- `src/port/sdl/sdl_app.c`
- `src/rl/rl_session.h`
- `src/rl/rl_session.c`
- `src/sf33rd/Source/Game/engine/plmain.c`
- `vendor/Menu_MiSTer/menu.sv`
- `vendor/Main_MiSTer/thirdsarm_wrapper.cpp`
- `docs/config.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- allow the selected RL side to be driven by the built-in game CPU while exporting learner-ingestible transition rows.
- provide an automatic high-volume demo source for movement, guard, and punish samples without requiring manual human input.
- keep the existing `remote` and `human-demo` control-source behavior unchanged.

Implementation notes:
- extended `rl-control-source` / `--rl-control-source` from `remote|human-demo` to `remote|human-demo|cpu-demo`.
- `cpu-demo` routes the selected `rl-player` side as CPU-controlled in the VS operator setup.
- CPU-demo transition recording happens from `Player_move()` after the CPU/player pipeline has resolved `wk->cp->sw_lvbt`, so the logged action reflects the input actually used by the game for that player.
- CPU-demo rows set `execution_source = 5`; requested/executed policy metadata is identical because the action was local to the game.
- the demo policy mapper is shared with human-demo and labels walk, guard, stand/crouch normals, jump attacks, throws, and forward+HP command-normal from the resolved input.
- OSD `RL Control (Restart)` now uses status bits `[54:53]` and exposes `Remote, Human Demo, CPU Demo`.
- overlay labels show `P1CD` / `P2CD` for CPU-demo mode.

Validation:
- `git diff --check` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed and produced `build/mister-telemetry-package`.
- `tools/mister-wrapper/build-hps.sh` passed and produced `build/mister-wrapper-hps/MiSTer_3S-ARM`.
- wrapper-core Quartus rebuild was not run in this pass; the `vendor/Menu_MiSTer/menu.sv` OSD row needs wrapper core/package/deploy before the three-value `RL Control` menu appears on hardware.

Follow-up:
- build/package wrapper core before expecting the three-value OSD row on hardware.
- collect a short `cpu-demo` log and confirm rows contain `execution_source = 5` and useful guard/back/forward samples before using it for DQN pretraining.
- define replay-buffer mixing rules for remote, human-demo, and CPU-demo rows.

## 2026-04-28: Add Human-Demo Transition Recording Mode

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / human-demo bootstrapping data collection

Files changed:
- `src/configuration.h`
- `src/args.c`
- `src/main.c`
- `src/port/config/config.h`
- `src/port/config/config.c`
- `src/port/sdl/sdl_app.c`
- `src/rl/rl_session.h`
- `src/rl/rl_session.c`
- `tools/rl_probe_server.py`
- `docs/config.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- allow a human to control the RL-selected side against CPU while exporting learner-ingestible transition rows.
- collect cleaner examples of guard/back/forward/spacing behavior than the current tabular/DQN policies produce.
- keep the existing remote policy path unchanged for normal `remote` control-source runs.

Implementation notes:
- added `rl-control-source = remote|human-demo` and `--rl-control-source`.
- `remote` is the default and preserves current remote/tabular/DQN behavior.
- `human-demo` skips all RL input overrides and records the selected `rl-player` side's actual `p1sw_buff` / `p2sw_buff` input at the usual decision cadence.
- human-demo rows set `execution_source = 4`, with requested and executed policy metadata equal because the player action is already local.
- the first human input mapper converts raw inputs into the current high-level action taxonomy:
  - `forward` / `back` for plain walk inputs
  - `guard-stand` for back-only input when latest opponent routine attack state is active within short/mid range
  - `guard-crouch` for down-back without attack
  - stand/crouch normals, jump attacks, throws, and forward+HP command-normal from button/direction combinations
- with `rl-network = on`, the UDP hello/transition-batch path can still upload completed episodes, but human-demo does not send OBS/action inference packets.
- overlay labels show `P1D` / `P2D` for human-demo mode.
- `learner_replay_row()` now preserves `requested_action_wire` and `execution_source` so later tools can filter human-demo versus remote-agent rows.

Validation:
- `git diff --check` passed.
- `python3 -m py_compile tools/rl_probe_server.py` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed and created `build/mister-telemetry-package`.

Follow-up:
- define replay-buffer mixing rules for human-demo episodes versus remote-agent episodes.
- validate the first back-vs-guard heuristic against a short human-vs-CPU collection log and adjust labels if it over-tags retreat as guard.

## 2026-04-28: Add MiSTer OSD Control For RL Control Source

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / human-demo bootstrapping data collection

Files changed:
- `vendor/Menu_MiSTer/menu.sv`
- `vendor/Main_MiSTer/thirdsarm_wrapper.cpp`
- `docs/config.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- make `rl-control-source = remote|human-demo` switchable from the MiSTer OSD instead of requiring manual config edits.

Implementation notes:
- added `RL Settings -> RL Control (Restart), Remote, Human Demo` on status bit `[53]`.
- wrapper defaults generated configs to `rl-control-source = remote`.
- wrapper reads/writes `rl-control-source`, seeds the OSD status bit at launch/restart, and logs the selected mode.
- wrapper strips incoming `--rl-control-source` and injects the persisted OSD/config value into the child runtime when RL agent mode is enabled.
- the setting remains launch-time and requires the existing `Restart` action.

Validation:
- `git diff --check` passed.
- `tools/mister-wrapper/build-hps.sh` first failed under sandboxed network with `Could not resolve host: github.com`.
- reran `tools/mister-wrapper/build-hps.sh` with approved network access; HPS wrapper build passed and produced `build/mister-wrapper-hps/MiSTer_3S-ARM`.
- wrapper-core Quartus build was not run in this pass; `vendor/Menu_MiSTer/menu.sv` changes still require a wrapper core rebuild/package before the new OSD row appears on hardware.

Follow-up:
- rebuild/package wrapper HPS and wrapper core before expecting the new OSD row on hardware.
- hardware-test that `RL Control (Restart)` writes `rl-control-source = remote|human-demo` and that runtime overlay switches between `P1C/P2C` and `P1D/P2D` after Restart.

## 2026-04-28: Add DQN Spacing Reward Shaping

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / Phase 1 basic-action DQN reward shaping

Files changed:
- `tools/train_dqn_learner.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- give `forward` and `back` immediate offline DQN reward signal when they improve spacing toward a configured target band.
- keep the change local to offline DQN reward shaping so live tabular/DQN action execution, C-side transition schema, and current probe-server macros do not change.
- defer walk macros and finer distance buckets until the spacing-shaping A/B result shows whether movement credit alone helps.

Implementation notes:
- added spacing-shaping CLI knobs:
  - `--reward-spacing-target-min-dx`
  - `--reward-spacing-target-max-dx`
  - `--reward-spacing-improve-bonus`
  - `--reward-spacing-worsen-cost`
  - `--reward-spacing-maintain-bonus`
  - `--reward-spacing-threat-back-bonus`
- spacing shaping applies only to `forward` / `back` action starts (`executed_policy_action_step == 0`).
- the trainer compares the action-start `obs_abs_dx` against the next decision boundary row and measures distance to the configured target band.
- clean movement that moves closer to the target band can receive an improve bonus; clean movement that moves farther away can receive a worsen cost; clean movement that stays inside the band can receive a maintain bonus.
- `back` can receive an extra close-range threat bonus when the opponent is already in the validated attack routine and the next decision boundary increases `obs_abs_dx`.
- all spacing adjustments require a no-self-damage movement window; if movement gets punished, natural HP-delta loss remains the primary signal.
- trainer metadata records spacing config and `reward_spacing_stats`; stdout prints `spacing_bonus`, `spacing_cost`, `spacing_net`, and `DQN diagnostics spacing_shape=...`.

Validation:
- `python3 -m py_compile tools/train_dqn_learner.py` passed.
- `python3 tools/train_dqn_learner.py --help | rg "reward-spacing"` showed all six new spacing-shaping CLI flags.
- spacing-shaping smoke passed:
  - `python3 tools/train_dqn_learner.py logs/rl-transitions-basic-v1-cpu-lv4-4-3-3.ndjson --model-dir /tmp/rl-dqn-spacing-smoke --model-version 1 --limit 7000 --drop-initial-episodes-per-run 3 --steps 5 --batch-size 16 --hidden-sizes 16 --log-interval 0 --eval-limit 500 --actions forward,back,guard-stand,guard-crouch,stand-mk,crouch-mk,jump-forward-mk --reward-risk-profile all-attacks --reward-risk-window-decisions 15 --reward-attack-no-damage-cost 1.0 --reward-attack-punished-cost 2.0 --reward-jump-attack-no-damage-extra-cost 2.0 --reward-jump-attack-punished-extra-cost 2.0 --reward-guard-success-bonus 2.0 --reward-guard-success-window-decisions 15 --reward-guard-threat-max-dx 144 --reward-passive-guard-cost 0.5 --reward-far-guard-cost 0.5 --reward-spacing-target-min-dx 50 --reward-spacing-target-max-dx 120 --reward-spacing-improve-bonus 0.5 --reward-spacing-worsen-cost 0.3 --reward-spacing-maintain-bonus 0.2 --reward-spacing-threat-back-bonus 0.3`
  - published `rows=5061 raw_rows=7000 drop_ep=3/1939`, `experiences=599`, `spacing_bonus=21.6`, `spacing_cost=5.7`, `spacing_net=15.9`.
  - printed `DQN diagnostics spacing_shape=target:50-120 improve:27/13.5 maintain:36/7.2 worsen:19/5.7 threat_back:3/0.9 net:15.9`, confirming the spacing reward fired and was accounted separately from guard/risk shaping.
  - the five-step smoke still collapsed to `crouch-mk`; this is only a wiring smoke, not an offline quality comparison.

Follow-up:
- compare basic-only DQN with and without spacing shaping on `logs/rl-transitions-basic-v1-cpu-lv4-4-3-3.ndjson`.
- review walk-forward/back macro actions only after the P0 spacing-shaping comparison shows whether movement credit shifts greedy policy away from passive guard/attack-only choices.
- review 5-level distance buckets after checking whether current DQN features and sample count are enough for the Phase 1 basic-only action set.
- review live data collection settings, especially repeat-delay neutral pollution, before collecting a new long-run basic-only dataset.

## 2026-04-28: Refine DQN Guard Cost And Episode Drop

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / Phase 1 basic-action DQN reward shaping

Files changed:
- `tools/train_dqn_learner.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- avoid double-punishing wrong guard decisions that already took natural HP-delta damage.
- make passive/far guard costs represent empty guard only, not failed guard.
- allow DQN training to drop the first few episodes from each run when early live collection is polluted by fallback repeat-delay neutral behavior.

Implementation notes:
- `reward_guard_adjustment()` now computes the guard lookahead window once and applies passive/far guard costs only when that window has no self HP damage.
- successful guard bonus still requires opponent attack state, close/mid threat range, and the same no-self-damage window.
- added `--drop-initial-episodes-per-run`; it drops the first `N` unique `(run_id, episode_id)` episodes encountered for each run before building DQN experiences, stats, metadata, and greedy diagnostics.
- trainer metadata records `rows_read_before_episode_drop`, `drop_initial_episodes_per_run`, `dropped_initial_episode_rows`, and `dropped_initial_episodes`.
- trainer stdout now prints filtered rows, raw rows, and dropped episode/row counts as `rows=<filtered> raw_rows=<raw> drop_ep=<episodes>/<rows>`.

Validation:
- `python3 -m py_compile tools/train_dqn_learner.py` passed.
- guard/drop smoke passed:
  - `python3 tools/train_dqn_learner.py logs/rl-transitions-basic-v1-cpu-lv4-4-3-3.ndjson --model-dir /tmp/rl-dqn-guard-drop-smoke.<tmp> --model-version 1 --limit 7000 --drop-initial-episodes-per-run 3 --steps 5 --batch-size 16 --hidden-sizes 16 --log-interval 0 --eval-limit 500 --actions forward,back,guard-stand,guard-crouch,stand-mk,crouch-mk,jump-forward-mk --reward-risk-profile all-attacks --reward-risk-window-decisions 15 --reward-attack-no-damage-cost 1.0 --reward-attack-punished-cost 2.0 --reward-jump-attack-no-damage-extra-cost 2.0 --reward-jump-attack-punished-extra-cost 2.0 --reward-guard-success-bonus 2.0 --reward-guard-success-window-decisions 15 --reward-guard-threat-max-dx 144 --reward-passive-guard-cost 0.5 --reward-far-guard-cost 0.5`
  - published `rows=5061 raw_rows=7000 drop_ep=3/1939`, confirming the first three episodes in the run were dropped before experience building.
  - guard/risk diagnostics still fired: `risk_shape=... jump:196.0/56.0` and `guard_shape=success:16/32.0 passive:43/21.5 far:36/18.0 net:-7.5`.

Follow-up:
- use `--drop-initial-episodes-per-run 3` in the next A/B/C comparison on `rl-transitions-basic-v1-cpu-lv4-4-3-3.ndjson`.
- if later collection removes or lowers `--policy-repeat-delay-ms`, rerun the same comparison with and without episode dropping to confirm whether the filter is still needed.

## 2026-04-28: Add DQN Jump-Attack Risk Extras

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / Phase 1 basic-action DQN reward shaping

Files changed:
- `tools/train_dqn_learner.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- make jump-in whiffs, especially `jump-forward-mk`, more expensive than ground poke whiffs during offline DQN training.
- model the practical SF3 risk that a mistimed jump has high commitment, cannot guard in the air, and can be anti-aired or punished on landing.
- keep useful jump-ins available by adding extra cost only when the jump attack produces no opponent HP damage in the lookahead window.

Implementation notes:
- added `JUMP_ATTACK_RISK_ACTIONS` for `jump-forward-mk`, `jump-forward-hk`, `jump-neutral-hk`, and `jump-back-hk`.
- added two positive-cost CLI knobs:
  - `--reward-jump-attack-no-damage-extra-cost`
  - `--reward-jump-attack-punished-extra-cost`
- jump extras apply only under `--reward-risk-profile all-attacks` and stack on top of the generic all-attacks no-damage / punished costs.
- trainer metadata now records jump extra cost config and per-run totals through `reward_risk_stats`.
- stdout prints `DQN diagnostics risk_shape=... jump:<no_damage_extra>/<punished_extra>` for quick smoke checks.

Validation:
- `python3 -m py_compile tools/train_dqn_learner.py` passed.
- jump-risk smoke passed:
  - `python3 tools/train_dqn_learner.py logs/rl-transitions-basic-v1-cpu-lv4-4-3-3.ndjson --model-dir /tmp/rl-dqn-jump-risk-smoke.<tmp> --model-version 1 --limit 5000 --steps 5 --batch-size 16 --hidden-sizes 16 --log-interval 0 --eval-limit 500 --actions forward,back,guard-stand,guard-crouch,stand-mk,crouch-mk,jump-forward-mk --reward-risk-profile all-attacks --reward-risk-window-decisions 15 --reward-attack-no-damage-cost 1.0 --reward-attack-punished-cost 2.0 --reward-jump-attack-no-damage-extra-cost 2.0 --reward-jump-attack-punished-extra-cost 2.0 --reward-guard-success-bonus 2.0 --reward-guard-success-window-decisions 15 --reward-guard-threat-max-dx 144 --reward-passive-guard-cost 0.2 --reward-far-guard-cost 0.5`
  - published `risk_cost=508.0`, with `DQN diagnostics risk_shape=... attack:240.0/140.0 ... jump:94.0/34.0`, confirming jump extras fired separately from generic attack costs.

Follow-up:
- compare Phase 1 basic-only DQN variants:
  - A: pure HP-delta baseline.
  - B: guard bonus + generic all-attacks risk.
  - C: guard bonus + generic all-attacks risk + jump-attack extra cost.
- if C avoids jump spam without collapsing to passive guard or crouch MK, use the same cost profile for the next longer basic-only run.

## 2026-04-28: Add Live Tabular Action Subsets

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / Phase 1 basic-action data collection

Files changed:
- `tools/rl_probe_server.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- collect a clean long-run transition log with only basic actions such as forward/back movement, stand/crouch guard, standing MK, crouching MK, and jump-forward MK.
- avoid hard-coding one temporary curriculum action set into the probe server.
- prevent a fresh model directory from bootstrapping a default full-action tabular actor before the learner publishes the intended subset.

Implementation notes:
- added `--tabular-actions`, a comma-separated live tabular action subset.
- the tabular learner now trains only on the configured subset and publishes the same subset in tabular actor manifests.
- `ActorModelStore` now accepts initial actions/fallback policy, so bootstrap `current.json` uses the configured tabular subset when `--policy tabular` starts from an empty model directory.
- startup validation rejects tabular actor runs when `--tabular-fallback-policy` resolves to an action outside `--tabular-actions`; this avoids silently mixing HP/full-action fallback into a basic-only curriculum log.
- learner publish metadata records `tabular_actions` for easier post-run audit.

Validation:
- `python3 -m py_compile tools/rl_probe_server.py` passed.
- `python3 tools/rl_probe_server.py --help` shows `--tabular-actions`.
- invalid action validation passed:
  - `python3 tools/rl_probe_server.py --policy tabular --tabular-actions forward,bad --learner-only`
  - exited with `Unknown action(s) for --tabular-actions: bad`.
- subset/fallback validation passed:
  - `python3 tools/rl_probe_server.py --policy tabular --tabular-actions forward,back --tabular-fallback-policy hp --learner-only`
  - exited with `--tabular-fallback-policy hp resolves to stand-hp, which is not in --tabular-actions`.
- non-tabular scripted fallback validation passed:
  - `python3 tools/rl_probe_server.py --policy tabular --tabular-actions forward,back,tatsu-mk --tabular-fallback-policy tatsu --learner-only`
  - exited with `--tabular-fallback-policy tatsu is not a tabular action alias`.
- bootstrap manifest smoke passed:
  - instantiated `ActorModelStore` with `policy=tabular`, actions `forward,back,guard-stand,guard-crouch,stand-mk,crouch-mk,jump-forward-mk`, and fallback `stand-mk`.
  - generated `current.json` contained only that action subset and `fallback_policy=stand-mk`.

Follow-up:
- run a fresh basic-only hard-CPU long-run log with:
  - `--tabular-actions forward,back,guard-stand,guard-crouch,stand-mk,crouch-mk,jump-forward-mk`
  - `--tabular-fallback-policy stand-mk`
- train Phase 1 DQN from that basic-only log before reintroducing fireball, shoryuken, tatsu, or HK jump attacks.

## 2026-04-28: Make Offline DQN Replay Decision-Level

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / Phase 1 defense curriculum

Files changed:
- `tools/train_dqn_learner.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- stop treating macro continuation rows (`executed_policy_action_step > 0`) as independent DQN decisions.
- credit HP-delta reward from guard/fireball/shoryuken/tatsu/jump macro continuation rows back to the originating step-0 decision.
- make guard reward shaping visible to the model instead of diluting it across forced guard continuation frames.

Implementation notes:
- `build_experiences()` now creates DQN experiences only for recognized included action rows with `executed_policy_action_step == 0`.
- included macro continuation rows no longer create experiences; nonzero reward on those rows is added to the most recent included step-0 experience.
- step-0 experience `next_state` is updated when the next step-0 action boundary is reached, and the final included experience in each episode is closed with the episode's last row as terminal next state.
- excluded explicit actions still reset delayed-credit attribution so their later reward is not credited to a previous included action.
- `BuildDiagnostics` now records macro continuation rows, continuation reward rows/sum, continuation delayed credits, and uncredited continuation rewards.
- trainer stdout now prints `cont=<rows>` and `cont_rew=<scaled_reward>` beside included/excluded counts.

Validation:
- `python3 -m py_compile tools/train_dqn_learner.py` passed.
- decision-level replay smoke:
  - `python3 tools/train_dqn_learner.py logs/rl-transitions-actionset-v4-hardcpu-v1-4-3-3.ndjson --model-dir /tmp/rl-dqn-decision-replay-smoke --model-version 1 --limit 5000 --steps 5 --batch-size 16 --hidden-sizes 16 --log-interval 0 --eval-limit 500 --actions forward,back,guard-stand,guard-crouch,stand-hp,crouch-mk --reward-risk-profile all-attacks --reward-risk-window-decisions 15 --reward-attack-no-damage-cost 0.5 --reward-attack-punished-cost 2.0 --reward-guard-success-bonus 2.0 --reward-guard-success-window-decisions 15 --reward-guard-threat-max-dx 144 --reward-passive-guard-cost 0.2 --reward-far-guard-cost 0.5`
  - published `experiences=184`, `included=184`, `cont=195`, `cont_rew=-0.380`, compared with the previous row-level smoke that produced `experiences=379`; this confirms guard macro continuation rows are no longer independent DQN decisions.
  - guard-shaping diagnostics still fired: `guard_shape=success:10/20.0 passive:16/3.2 far:10/5.0 net:11.8`.

Follow-up:
- rerun full Phase 1 guard-shaping training because the previous `model/dqn-phase1-basic-c15-guard-shaping` was produced by the older row-level replay builder.
- compare the rebuilt model against `model/dqn-phase1-basic-c15`; this is the first comparison where guard shaping should have a fair signal-to-noise ratio.
- if the rebuilt model still keeps `atk1_close` on `stand-hp`, increase guard success bonus or collect scripted guard success data before broadening the action set.

## 2026-04-28: Add Offline DQN Guard Reward Shaping

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / Phase 1 defense curriculum

Files changed:
- `tools/train_dqn_learner.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- give offline DQN training a positive signal for successful `guard-stand` / `guard-crouch` decisions under opponent strike threat.
- add small costs for passive or far guard so Phase 1 models do not learn to hold guard as a universal idle/default action.
- keep the experiment local to the offline trainer; no C-side transition schema or MiSTer runtime behavior changed.

Implementation notes:
- added guard shaping config:
  - `--reward-guard-success-bonus`
  - `--reward-guard-success-window-decisions`
  - `--reward-guard-threat-max-dx`
  - `--reward-passive-guard-cost`
  - `--reward-far-guard-cost`
- guard success bonus applies only to `guard-stand` / `guard-crouch` action starts when:
  - `executed_policy_action_step == 0`
  - `obs_opp_routine_attack_state != 0`
  - `obs_abs_dx <= reward_guard_threat_max_dx`
  - the guard-success lookahead window has no `delta_self_hp`
- passive/far guard costs also apply only on guard action starts, avoiding repeated macro-step reward/cost for the six-step guard macros.
- trainer metadata now records guard shaping config and `reward_guard_stats`.
- trainer stdout now prints `guard_bonus`, `guard_cost`, `guard_net`, and a `DQN diagnostics guard_shape=...` summary.

Validation:
- `python3 -m py_compile tools/train_dqn_learner.py` passed.
- guard-shaping smoke:
  - `python3 tools/train_dqn_learner.py logs/rl-transitions-actionset-v4-hardcpu-v1-4-3-3.ndjson --model-dir /tmp/rl-dqn-guard-shaping-smoke --model-version 1 --limit 5000 --steps 5 --batch-size 16 --hidden-sizes 16 --log-interval 0 --eval-limit 500 --actions forward,back,guard-stand,guard-crouch,stand-hp,crouch-mk --reward-risk-profile all-attacks --reward-risk-window-decisions 15 --reward-attack-no-damage-cost 0.5 --reward-attack-punished-cost 2.0 --reward-guard-success-bonus 2.0 --reward-guard-success-window-decisions 15 --reward-guard-threat-max-dx 144 --reward-passive-guard-cost 0.2 --reward-far-guard-cost 0.5`
  - published `actions=6`, `risk_cost=406.0`, `guard_bonus=20.0`, `guard_cost=8.2`, `guard_net=11.8`, and printed `guard_shape=success:10/20.0 passive:16/3.2 far:10/5.0 net:11.8`.

Follow-up:
- run the full Phase 1 guard-shaping command on mixed old-v4 + hardcpu-v1 logs.
- compare against `model/dqn-phase1-basic-c15` and check whether `atk1_close` / `atk1_mid` shift from `stand-hp` to guard while `atk0_far` stops selecting guard as the dominant default.
- if guard shaping works offline, collect a fresh Phase 1 live log before considering a broader action set.

## 2026-04-27: Add DQN Action Subsets And Collapse Diagnostics

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / first ML baseline

Files changed:
- `tools/train_dqn_learner.py`
- `tools/compare_dqn_models.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- allow DQN/MLP Q models to train on a smaller action subset from existing transition logs before collecting more MiSTer data.
- diagnose the observed greedy-policy collapse toward one normal attack before live DQN testing.
- avoid reward leakage when an explicit action is excluded from the subset.

Implementation notes:
- `tools/train_dqn_learner.py` adds `--actions`, a comma-separated DQN action subset that is published into the actor manifest.
- excluded explicit actions are counted and clear the delayed-credit pointer, so later neutral/recovery HP deltas are not credited to the previous included action.
- trainer metadata now records:
  - `actions_subset` and `actions_subset_size`
  - `build_diagnostics`
  - observed all-action counts/rewards
  - greedy top-1/top-2/top-3 counts
  - greedy mean Q per action
  - greedy top action and top-action rate
- trainer stdout now includes included/excluded counts, excluded reward sum, per-action `count/reward/mean`, top-2/top-3 summaries, and a collapse warning controlled by `--collapse-warning-threshold`.
- `tools/compare_dqn_models.py` now prints model action-count, top greedy action/rate, collapse status, and selected-Q mean for the printed top actions.

Validation:
- `python3 -m py_compile tools/train_dqn_learner.py tools/compare_dqn_models.py` passed.
- help smoke confirmed new trainer flags:
  - `--actions`
  - `--diagnostic-top-n`
  - `--collapse-warning-threshold`
- subset baseline smoke:
  - `python3 tools/train_dqn_learner.py logs/rl-transitions-actionset-v4-4-3-3.ndjson --model-dir /tmp/rl-dqn-subset-a-smoke --model-version 1 --limit 5000 --steps 5 --batch-size 16 --log-interval 0 --actions forward,back,guard-stand,guard-crouch,stand-hp,crouch-mk,fireball,shoryuken-mp,tatsu-mk,jump-forward-hk --reward-risk-profile none --diagnostic-top-n 6`
  - published `actions=10`, `included=863`, `excluded=381`, and warned `stand-hp 99.2%`.
- subset all-attacks smoke:
  - `python3 tools/train_dqn_learner.py logs/rl-transitions-actionset-v4-4-3-3.ndjson --model-dir /tmp/rl-dqn-subset-c-smoke --model-version 1 --limit 5000 --steps 5 --batch-size 16 --log-interval 0 --actions forward,back,guard-stand,guard-crouch,stand-hp,crouch-mk,fireball,shoryuken-mp,tatsu-mk,jump-forward-hk --reward-risk-profile all-attacks --diagnostic-top-n 6`
  - published `actions=10`, `risk_cost=357.5`, `included=863`, `excluded=381`, and warned `stand-hp 99.2%`.
- compare smoke:
  - `python3 tools/compare_dqn_models.py logs/rl-transitions-actionset-v4-4-3-3.ndjson --tail-rows 1000 --model A=/tmp/rl-dqn-subset-a-smoke --model C=/tmp/rl-dqn-subset-c-smoke --top-n 6`
  - printed action-count, selected-Q mean, and `collapse=WARN` for both subset smoke models.

Follow-up:
- run full A/B/C subset models with enough steps to decide whether the collapse is data, reward, or action-space driven.
- if subset models still collapse, collect targeted curriculum logs instead of taking DQN live.

## 2026-04-27: Add Offline DQN Reward-Risk A/B/C Profiles

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / first ML baseline

Files changed:
- `tools/rl_probe_server.py`
- `tools/train_dqn_learner.py`
- `tools/compare_dqn_models.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- train baseline and reward-risk DQN/MLP Q models from the same transition log so Shoryuken no-damage costs can be compared without changing the live environment.
- avoid ambiguous command names by using positive `cost` parameters rather than negative `penalty` arguments.
- detect whether reducing empty Shoryuken merely shifts the model toward other empty attacks.

Implementation notes:
- `learner_replay_row()` now preserves requested/executed policy action IDs, sub-action IDs, and macro steps so offline DQN replay can use high-level action attribution instead of falling back to wire-only decoding.
- `tools/train_dqn_learner.py` adds:
  - `--reward-risk-profile none`
  - `--reward-risk-profile shoryuken-only`
  - `--reward-risk-profile all-attacks`
  - `--reward-risk-window-decisions`
  - `--reward-attack-no-damage-cost`
  - `--reward-attack-punished-cost`
  - `--reward-shoryuken-no-damage-extra-cost`
  - `--reward-shoryuken-punished-extra-cost`
- risk costs are positive raw reward units, subtracted before `--reward-scale`.
- `shoryuken-only` applies only Shoryuken no-damage / punished extra costs; `all-attacks` applies generic attack no-damage / punished costs to attack actions and adds the Shoryuken extras on top.
- terminal wins inside the lookahead window suppress risk costs so a harmless post-KO or already-winning action is not punished.
- `tools/compare_dqn_models.py` compares repeated `--model LABEL=path` DQN manifests against the same transition observations and reports greedy distributions overall plus `atk0/atk1 x close/mid/far`.

Validation:
- `python3 -m py_compile tools/rl_probe_server.py tools/train_dqn_learner.py tools/compare_dqn_models.py` passed.
- baseline smoke:
  - `python3 tools/train_dqn_learner.py logs/rl-transitions-actionset-v3-4-3-3.ndjson --model-dir /tmp/rl-dqn-ab-baseline-smoke --model-version 1 --limit 2000 --steps 5 --batch-size 16 --log-interval 0 --reward-risk-profile none`
  - published `risk=none risk_cost=0.0`.
- Shoryuken-only smoke:
  - `python3 tools/train_dqn_learner.py logs/rl-transitions-actionset-v3-4-3-3.ndjson --model-dir /tmp/rl-dqn-ab-shoryu-smoke --model-version 1 --limit 2000 --steps 5 --batch-size 16 --log-interval 0 --reward-risk-profile shoryuken-only`
  - published `risk=shoryuken-only risk_cost=2.0`.
- all-attacks smoke:
  - `python3 tools/train_dqn_learner.py logs/rl-transitions-actionset-v3-4-3-3.ndjson --model-dir /tmp/rl-dqn-ab-allattacks-smoke --model-version 1 --limit 2000 --steps 5 --batch-size 16 --log-interval 0 --reward-risk-profile all-attacks`
  - published `risk=all-attacks risk_cost=70.0`.
- larger 10k one-step smoke produced nonzero and profile-separated risk costs:
  - Shoryuken-only `risk_cost=31.0`
  - all-attacks `risk_cost=806.0`
- compare smoke:
  - `python3 tools/compare_dqn_models.py logs/rl-transitions-actionset-v3-4-3-3.ndjson --tail-rows 1000 --model A=/tmp/rl-dqn-ab-baseline-smoke --model B=/tmp/rl-dqn-ab-shoryu-smoke --model C=/tmp/rl-dqn-ab-allattacks-smoke --top-n 5`
  - printed overall and threat/distance greedy action distributions plus pairwise action-change counts.

Follow-up:
- run full A/B/C DQN training on the frozen actionset-v4 log with enough steps to make the comparison meaningful.
- compare Shoryuken selection rate and total attack selection rate before choosing any reward-risk profile for live testing.
- do not treat offline greedy distribution as live winrate; validate the selected DQN live for at least 50-100 rounds.

## 2026-04-27: Split Normal IDs By Stance And Add Normal Probes

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / action namespace refinement

Files changed:
- `tools/rl_probe_server.py`
- `tools/analyze_rl_transitions.py`
- `docs/rl-policy-action-taxonomy.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- add the requested standing LP/MP/LK/MK/HK and crouching LK/MK/HK probe actions.
- avoid ambiguity between standing MK and crouching MK by making normal actions stance-specific in policy metadata.

Implementation notes:
- split universal normal metadata into:
  - `6`: `stand_normal`
  - `15`: `crouch_normal`
- added learner/scripted fixed actions `stand-lp`, `stand-mp`, `stand-hp`, `stand-lk`, `stand-mk`, `stand-hk`, `crouch-lk`, `crouch-mk`, and `crouch-hk`.
- the legacy scripted `hp` policy remains supported as an alias for `stand-hp`, so existing probe commands using `--tabular-fallback-policy hp` continue to work.
- bumped `ACTION_SET_VERSION` from `3` to `4` so old tabular/DQN manifests are ignored instead of mixing generic normal metadata with stance-specific normals.
- `tools/analyze_rl_transitions.py` default action list now includes the stance-specific normals.

Validation:
- `python3 -m py_compile tools/rl_probe_server.py tools/analyze_rl_transitions.py tools/train_dqn_learner.py` passed.
- synthetic metadata smoke confirmed standing normals stamp `stand_normal/<button>` and crouching normals stamp `crouch_normal/<button>`.
- synthetic wire smoke confirmed standing normals use bare button wires and crouching normals use `down+button` wires.
- synthetic transition decode smoke confirmed policy metadata maps back to `stand-lp`, `stand-mp`, `stand-hp`, `stand-lk`, `stand-mk`, `stand-hk`, `crouch-lk`, `crouch-mk`, and `crouch-hk`.
- `python3 tools/rl_probe_server.py --help` shows the new stance-specific normal scripted policies and fallback-policy choices.
- analyzer tail smoke passed on `logs/rl-transitions-defense-v1-4-3-3.ndjson --tail-rows 1000`; old `hp` rows now decode as `stand-hp` through the stance-specific metadata map.
- one-step offline DQN smoke passed against `logs/rl-transitions-defense-v1-4-3-3.ndjson --limit 2000`; the published manifest carried `action_set_version=4` and all nine stance-specific normal actions.

Follow-up:
- start a fresh model/log for live testing because this is an action-set version bump.
- watch whether the larger normal action set makes tabular exploration too sparse; if it does, use DQN/offline pretraining or a smaller curriculum subset before adding more moves.

## 2026-04-27: Split Jump Attack IDs By Direction

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / action namespace refinement

Files changed:
- `tools/rl_probe_server.py`
- `tools/analyze_rl_transitions.py`
- `docs/rl-policy-action-taxonomy.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- make jump attacks distinguishable by jump direction in transition logs and learner action attribution.
- add the first HK jump-kick probes for forward, neutral, and back jumps.

Implementation notes:
- split the old universal `jump_attack=12` taxonomy into direction-specific IDs:
  - `12`: `jump_attack_forward`
  - `13`: `jump_attack_neutral`
  - `14`: `jump_attack_back`
- `jump-forward-mk` now stamps `jump_attack_forward/mk` instead of generic `jump_attack/mk`.
- added `jump-forward-hk`, `jump-neutral-hk`, and `jump-back-hk`, all using `sub_action_id=6/hk` with their direction-specific action ID.
- bumped `ACTION_SET_VERSION` from `2` to `3` so old tabular/DQN manifests are ignored instead of mixing generic and direction-specific jump action semantics.
- `tools/analyze_rl_transitions.py` default action list now includes the three HK jump-kick probes.

Validation:
- `python3 -m py_compile tools/rl_probe_server.py tools/analyze_rl_transitions.py tools/train_dqn_learner.py` passed.
- synthetic macro smoke confirmed `jump-forward-hk`, `jump-neutral-hk`, and `jump-back-hk` emit up-forward/up/up-back HK sequences and stamp action IDs `12`, `13`, and `14`.
- synthetic transition decode smoke confirmed direction-specific jump metadata maps back to `jump-forward-mk`, `jump-forward-hk`, `jump-neutral-hk`, and `jump-back-hk`.
- `python3 tools/rl_probe_server.py --help` shows the new jump HK scripted policies and fallback-policy choices.
- analyzer tail smoke passed on `logs/rl-transitions-defense-v1-4-3-3.ndjson --tail-rows 1000`; the default action list now includes the three HK jump-kick probes.
- one-step offline DQN smoke passed against `logs/rl-transitions-defense-v1-4-3-3.ndjson --limit 2000`; the published manifest carried `action_set_version=3` and all three HK jump-kick actions.

Follow-up:
- start a fresh model/log for live testing because this is an action-set version bump.
- after live validation, consider whether other air normals should follow the same direction-specific naming before adding them to curriculum.

## 2026-04-27: Split Back/Guard And Add Ryu MK/MP Actions

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / action-set refinement

Files changed:
- `tools/rl_probe_server.py`
- `tools/analyze_rl_transitions.py`
- `tools/train_dqn_learner.py`
- `docs/plan-remote-rl-agent.md`
- `docs/rl-policy-action-taxonomy.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- make retreat spacing and blocking trainable as different learner choices.
- add the next Ryu curriculum actions requested for live probe testing: crouching MK, MP Shoryuken, and MK Tatsumaki Senpukyaku.

Implementation notes:
- `back` is now a plain `walk/back` fixed action again and no longer expands into the stand-guard macro.
- added separate `guard-stand` and `guard-crouch` actions; they stamp `guard/stand` and `guard/crouch` metadata and expand to six decision replies of `back` or `down-back`.
- added `crouch-mk` as fixed `down+MK`, stamped as `normal/mk`; this is the first live MK normal, so learner import maps `normal/mk` to `crouch-mk`.
- added `shoryuken-mp` as `forward -> down -> down-forward -> down-forward+MP -> neutral -> neutral`, stamped as Ryu `Shoryuken` / `mp`.
- added `tatsu-mk` as `down -> down-back -> back -> back+MK -> neutral -> neutral`, stamped as Ryu `Tatsumaki Senpukyaku` / `mk`.
- `tools/analyze_rl_transitions.py` default action list now matches the expanded probe action set.
- tabular and DQN actor manifests now carry `action_set_version=2`; probe-side hot-load ignores older tabular/DQN manifests so stale q-tables do not reinterpret old `back` guard credit as plain retreat.

Validation:
- `python3 -m py_compile tools/rl_probe_server.py tools/analyze_rl_transitions.py tools/train_dqn_learner.py` passed.
- synthetic probe smoke confirmed tabular `back` returns wire `0x0003` with policy metadata `walk/back`, not `guard/stand`.
- synthetic macro smoke confirmed `guard-stand`, `guard-crouch`, `shoryuken-mp`, and `tatsu-mk` emit the expected wires and policy metadata.
- synthetic transition decode smoke confirmed policy metadata maps back to `guard-stand`, `guard-crouch`, `crouch-mk`, `shoryuken-mp`, and `tatsu-mk`.
- analyzer tail smoke passed on `logs/rl-transitions-defense-v1-4-3-3.ndjson --tail-rows 1000`; the default action list now includes the split guard and new Ryu actions.
- one-step offline DQN smoke passed against `logs/rl-transitions-defense-v1-4-3-3.ndjson --limit 2000`; the published manifest carried `action_set_version=2` and the expanded action list.

Follow-up:
- use a fresh transition log for live evaluation of this action-set version; old transition logs can still be analyzed, but old q-table/DQN model quality is not comparable.
- watch live `ready_threat_dx` for whether `guard-stand` / `guard-crouch` appear under `atk1_close` or `atk1_mid` while `back` remains usable for spacing.

## 2026-04-27: Add Readable Move Names To Policy Taxonomy

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / action namespace documentation

Files changed:
- `docs/rl-policy-action-taxonomy.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- make the all-character policy action taxonomy readable by humans instead of relying on generic source handlers such as `Att_HADOUKEN`.
- keep policy IDs, source command slots, routine numbers, handlers, and macro templates unchanged.

Implementation notes:
- added a `move_name` column to every character command registry table.
- mapped command rows to SF3 move-list names such as `Hadouken`, `Shoryuken`, `Genei-jin`, `Aegis Reflector`, and `Light of Virtue`.
- rows that combine EX, air, or source-only branches keep slash-separated aliases, for example Oro EX command rows and Twelve source kick variant rows.
- the taxonomy still treats source handlers and command slots as the executable source of truth; move names are display aliases for analysis and curriculum planning.

Validation:
- `python3 -m py_compile tools/rl_probe_server.py tools/analyze_rl_transitions.py tools/train_dqn_learner.py` passed.
- markdown table smoke checked that every character registry row has the new `move_name` column.
- `git diff --check -- docs/rl-policy-action-taxonomy.md docs/plan-remote-rl-agent.md docs/remote-rl-agent-engineering-log.md` passed.

Follow-up:
- validate ambiguous aliases before live curriculum use, especially Oro EX variants, Twelve `qcf+k`, and Akuma Hyakkishu / Ashura Senku branches.

## 2026-04-27: Migrate Live Actions To Policy Action Attribution

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / action namespace implementation

Files changed:
- `src/rl/rl_protocol.h`
- `src/rl/rl_session.c`
- `tools/rl_probe_server.py`
- `tools/analyze_rl_transitions.py`
- `tools/train_dqn_learner.py`
- `docs/rl-policy-action-taxonomy.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- move the current live probe/C action path from wire-only attribution toward the policy action ID / sub-action ID taxonomy.
- keep existing tabular and DQN behavior compatible while making transition logs ready for the later `back` vs `guard` split.

Implementation notes:
- bumped the RL protocol to `3` and action schema to `2`; `RLActionPacket` now carries `policy_action_id`, `policy_sub_action_id`, and `policy_action_step` alongside the final executable `action_wire`.
- C-side queued actions and decision ledger entries now preserve requested and executed policy action attribution and export it in transition NDJSON rows.
- probe-side action selection now returns a `PolicyActionFrame` instead of only a wire value; fixed actions and macro steps stamp taxonomy IDs for `walk`, `guard`, `normal`, `command_normal`, `throw`, Ryu `fireball` / `tatsu` / `shoryuken`, and `jump-forward-mk`.
- current model-selected `back` still expands into the guard macro and is stamped as `guard/stand`; learner import maps that metadata back to the old `back` bucket until `back` and `guard` are separate actions.
- transition analyzers and the offline DQN trainer now prefer `executed_policy_action_id` / `executed_policy_sub_action_id` and fall back to `executed_action_wire` for older logs.

Validation:
- `python3 -m py_compile tools/rl_probe_server.py tools/analyze_rl_transitions.py tools/train_dqn_learner.py` passed.
- Python packet smoke passed: action packet size is `48` bytes and `ryu-fireball` stamps `1229/lp` with the expected macro step.
- Python macro-step smoke passed for `ryu-fireball` and `jump-forward-mk`, producing steps `0..5` without wrapping the last step to `-1`.
- old-log analyzer smoke passed on `logs/rl-transitions-defense-v1-4-3-3.ndjson` tail `2000` rows using fallback wire decoding.
- `git diff --check` passed for the touched source/docs.
- `tools/mister/build-game.sh --flavor telemetry` passed and produced `build/mister-telemetry-package`.

Follow-up:
- deploy probe server and MiSTer runtime together; protocol `3` action packets are not compatible with the previous runtime.
- split `back` and `guard` into separate high-level actions after confirming the schema migration is stable in live logs.

## 2026-04-27: Draft All-Character Policy Action Taxonomy

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / action namespace design

Files changed:
- `docs/rl-policy-action-taxonomy.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- define a stable policy action ID / sub-action ID scheme before adding more SF3 moves to tabular or DQN.
- avoid mixing high-level model choices, concrete strength variants, and probe-side macro expansion in a single flat action string.
- create a source-backed inventory of command-recognized character actions for later curriculum subsets.

Implementation notes:
- universal actions use IDs below `1000` for movement, defense, normals, command normals, throws, tech, quick stand, and taunt.
- character command actions use `1000 + character_id * 100 + source_command_slot`, so IDs stay traceable to `cmd_data.c`.
- the registry records source command slot, source routine numbers, `plpatXX.c` handler names, macro template, and sub-action group.
- source handler names remain the first source of truth; official move aliases are intentionally deferred because handlers such as `Att_HADOUKEN` are reused across characters and move families.
- macros marked `button_or_charge`, `*_raw`, or numeric button groups require manual validation before live learner enablement.

Validation:
- source inspection matched the registry against `src/sf33rd/Source/Game/engine/cmd_data.c`, `cmd_main.c`, `pls03.c`, `plpat.c`, and `plpatXX.c`.
- `git diff --check -- docs/rl-policy-action-taxonomy.md docs/plan-remote-rl-agent.md docs/remote-rl-agent-engineering-log.md` passed.

Follow-up:
- add transition fields for requested/executed policy action ID, sub-action ID, and policy action step.
- split `back` and `guard` before training defensive DQN action heads.
- add official move aliases and validate uncertain macro templates only as each character enters the curriculum.

## 2026-04-27: Add Offline DQN Learner And Probe Inference

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / first ML baseline

Files changed:
- `tools/rl_probe_server.py`
- `tools/train_dqn_learner.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- prepare the first q-table-vs-ML comparison while a fresh tabular transition run is still collecting.
- train a simple DQN/MLP Q actor offline from transition NDJSON before allowing it to control live MiSTer.
- keep the first ML path independent from MiSTer/C changes and from external Python packages.

Implementation notes:
- added `policy=dqn` as a probe-side model policy, separate from scripted policies and `tabular`.
- DQN actors use the same high-level action set as tabular: `forward`, `back`, `hp`, `forward-hp`, `fireball`, `throw`, and `jump-forward-mk`.
- DQN features are normalized numeric OBS values: absolute spacing, front/back edge distances, `opp_in_front`, and validated opponent routine attack state.
- `tools/train_dqn_learner.py` reads transition logs, builds `(state, action, reward, next_state, done)` experiences, applies delayed HP-delta reward to the most recent explicit action like the tabular learner, trains a small stdlib-only MLP with target-network DQN updates, and publishes a `policy=dqn` actor manifest.
- `tools/rl_probe_server.py` can hot-load `policy=dqn` manifests from `--model-dir`, run MLP inference from same-frame OBS payloads, and reuse the existing action adapter / macro lock.
- `--learner-auto-publish` remains tabular/scripted-only; DQN publication is owned by the offline trainer for this first version.

Validation:
- `python3 -m py_compile tools/rl_probe_server.py tools/train_dqn_learner.py tools/analyze_rl_transitions.py` passed.
- `python3 tools/train_dqn_learner.py --help` passed.
- synthetic offline training smoke passed: `tools/train_dqn_learner.py` trained from a temporary NDJSON replay and published `policy=dqn` `current.json`.
- synthetic probe inference smoke passed: `ActorModelStore` loaded the generated DQN actor, `dqn_actor_action_name()` returned a valid high-level action, and `policy_action_wire()` returned a valid wire action.
- real-log smoke was attempted, but the checked local candidate transition logs were empty or missing in this worktree; rerun it after the in-progress live tabular run finishes.
- `git diff --check -- tools/rl_probe_server.py tools/train_dqn_learner.py docs/plan-remote-rl-agent.md docs/remote-rl-agent-engineering-log.md` passed.

Follow-up:
- next implementation action after DQN pipeline smoke: split `back` and `guard` into separate high-level actions, then carry high-level action / macro attribution into transition rows so DQN can learn `opp_attack=1 + close/mid -> guard` without mixing that credit with retreat/back-spacing behavior.
- after the current `jump-forward-mk` tabular live run finishes, train DQN offline on that full transition log and inspect loss, greedy action distribution, and reward/action coverage before running `--policy dqn` live.
- if DQN inference works but action quality is poor, compare against the tabular baseline using the same action set and avoid adding reward shaping until action attribution and replay coverage are understood.

## 2026-04-27: Add Tabular Jump-Forward MK Macro

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / action-set refinement

Files changed:
- `tools/rl_probe_server.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- give the current tabular learner one active approach attack that can earn immediate HP-delta reward when it connects.
- avoid adding pure `advance` yet, because the current contextual-bandit learner cannot reliably assign later attack reward back to spacing-only movement.
- keep the change scoped to the probe-side action adapter; no guard logic, reward rules, C-side protocol fields, or transition schema were changed.

Implementation notes:
- added Python-side constants for `RL_MOVE_UP_FORWARD` and `BTN_MK`.
- added `jump-forward-mk` to `POLICY_CHOICES` so it can be run as a fixed scripted probe policy.
- added `jump-forward-mk` to `TABULAR_ACTION_NAMES` so the tabular actor can explore and select it.
- added a macro sequence: `up-forward -> up-forward -> up-forward+MK -> up-forward+MK -> neutral -> neutral`.
- mapped the `up-forward+MK` wire phase back to the high-level `jump-forward-mk` tabular action bucket for learner credit.

Validation:
- `python3 -m py_compile tools/rl_probe_server.py tools/analyze_rl_transitions.py` passed.
- synthetic macro/action smoke passed: `scripted_sequence("jump-forward-mk")` produced `0x0006, 0x0006, 0x0206, 0x0206, 0x0000, 0x0000`.
- learner credit smoke passed: `tabular_action_name(0x0206)` maps to `jump-forward-mk`, and a synthetic tabular actor selected `jump-forward-mk` when it was the only eligible positive q-score.
- `git diff --check -- tools/rl_probe_server.py docs/plan-remote-rl-agent.md docs/remote-rl-agent-engineering-log.md` passed.

Follow-up:
- run a fresh live tabular pass and watch whether `ready_dx` / `ready_threat_dx` start selecting `jump-forward-mk` at close or mid spacing.
- if the MK timing is too early or too late visually, tune the macro sequence before changing reward or transition schema.

## 2026-04-27: Add Threat/Distance Ready-Action Stats

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / strike-defense policy diagnosis

Files changed:
- `tools/rl_probe_server.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- make live learner output show whether `fireball` and `back` are being selected in reasonable threat/distance regions.
- distinguish healthy far-range `opp_attack=1` fireball choices from risky close/mid-range fireball choices.
- diagnose over-defensive policy maps without changing learner updates, rewards, or action execution.

Implementation notes:
- `summarize_ready_actions()` now also returns `ready_threat_dx_actions`, keyed by `atk0_close`, `atk0_mid`, `atk0_far`, `atk1_close`, `atk1_mid`, and `atk1_far`.
- learner stats now print `ready_threat_dx=atk0_close{...} atk0_mid{...} atk0_far{...} atk1_close{...} atk1_mid{...} atk1_far{...}`.
- this is a Q-table readiness summary only: it counts ready greedy actions by state bucket and does not count actual executed actions.

Validation:
- `python3 -m py_compile tools/rl_probe_server.py tools/analyze_rl_transitions.py` passed.
- synthetic summary smoke passed: `ready_threat_dx` formatter produced the expected ordered buckets and separated `atk1_close{back:1}` from `atk1_mid{fireball:1}` / `atk1_far{fireball:1}`.
- replay smoke passed on the first `5000` rows of `logs/rl-transitions-tabular-4-3-3.ndjson`, producing `ready_threat_dx=...` from a real learner snapshot.
- `git diff --check -- tools/rl_probe_server.py docs/plan-remote-rl-agent.md docs/remote-rl-agent-engineering-log.md` passed.

Follow-up:
- in live runs, expect `atk1_close` / `atk1_mid` to trend toward `back` if strike defense is learning, while `atk1_far` and `atk0_far` may reasonably keep `fireball`.

## 2026-04-26: Add Tabular Back Guard Macro

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / strike-defense learning

Files changed:
- `tools/rl_probe_server.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- make defensive `back` decisions last long enough to cover a realistic strike-defense window.
- avoid globally increasing `action_hold_frames`, which would also slow movement, throws, fireballs, and attack timing.
- keep transition credit on the existing `back` action bucket instead of adding a separate tabular `guard` action that the C-side transition log cannot currently distinguish from plain `back` wire input.

Implementation notes:
- added a scripted `guard` policy sequence for fixed-policy validation: six consecutive `RL_MOVE_BACK` decision replies.
- tabular inference now maps a greedy/exploratory `back` action into that guard macro via the existing macro lock.
- with the current `decision_interval=3` and `action_hold=3`, one tabular `back` selection now produces about an 18-frame stand-guard window.
- `TABULAR_ACTION_NAMES` intentionally remains `forward`, `back`, `hp`, `forward-hp`, `fireball`, and `throw`; learner updates still see wire-level `back` and therefore train the `back` bucket.

Validation:
- `python3 -m py_compile tools/rl_probe_server.py tools/analyze_rl_transitions.py` passed.
- guard scripted-policy smoke passed: `scripted_sequence("guard")` produced six consecutive `0x0003` (`RL_MOVE_BACK`) decision replies.
- tabular macro-lock smoke passed: after a tabular `back` selection, a synthetic actor that switched to preferring `hp` still emitted six `back` wires before allowing `hp`.
- `git diff --check -- tools/rl_probe_server.py docs/plan-remote-rl-agent.md docs/remote-rl-agent-engineering-log.md` passed.

Follow-up:
- run a fresh tabular model/log and watch `ready_opp_attack=1{back:...}` plus visible guard behavior.
- if low attacks become a blocker, add a separate down-back guard macro after validating that action/credit semantics stay clear.

## 2026-04-26: Promote Opponent Strike Warning Into Tabular State

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / strike-defense learning

Files changed:
- `tools/rl_probe_server.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- let the tabular learner distinguish normal spacing states from states where the opponent is already in a validated strike-attack routine.
- keep throw defense as a spacing / close-range risk problem instead of inventing a fake "about to throw" observation.
- keep contact-reaction fields out of learner state because live samples showed they behave as outcome/debug labels rather than pre-contact warnings.

Live findings before promotion:
- schema cleanup was confirmed on `logs/rl-transitions-back-4-3-3.ndjson` (`3562` rows) and `logs/rl-transitions-hp-4-3-3.ndjson` (`831` rows): both carried `obs_opp_routine_attack_state` and `obs_self_contact_reaction_state`, and neither carried old `span_*` / `*_seen` fields.
- fixed `back` reduced observed self damage sharply versus the `hp` control run:
  - `back`: `self_damage=155`, `self_damage_rows=8`, `self_dmg_per_100=4.35`
  - `hp` control: `self_damage=320`, `self_damage_rows=25`, about `38.5` self damage per 100 rows overall
- damage rows were usually preceded by opponent routine attack state:
  - `back`: `5/8` damage rows had recent `obs_opp_routine_attack_state=1`
  - `hp` control: `23/25` damage rows had recent `obs_opp_routine_attack_state=1`
- timing samples showed `obs_opp_routine_attack_state=1` commonly appears one to four decisions before strike damage, making it suitable as a learner-visible strike warning.
- timing samples also showed `obs_self_contact_reaction_state=1` often appears after damage/contact, making it unsuitable as a first policy state feature.
- throw samples showed `obs_opp_routine_attack_state=0` with `obs_self_contact_reaction_state=1`, confirming that the routine attack flag is not a throw detector; close-range throw risk should be learned from spacing/action history later.

Implementation notes:
- `tabular_state_key()` now includes `opp_attack=0/1` from `obs_opp_routine_attack_state`.
- `obs_self_contact_reaction_state` remains imported for analysis but is not included in the tabular state key.
- learner stats now print `ready_opp_attack=0{...} 1{...}` so live runs can show whether ready greedy choices under strike-warning states start preferring defensive actions such as `back`.
- reward remains unchanged as learner-local HP delta: `delta_opp_hp - delta_self_hp`.

Validation:
- `python3 -m py_compile tools/rl_probe_server.py tools/analyze_rl_transitions.py` passed.
- state-key smoke passed: otherwise identical rows now produce distinct keys with `opp_attack=0` and `opp_attack=1`.
- ready-summary smoke passed: `summarize_ready_actions()` and `format_opp_attack_action_counts()` produced `ready_opp_attack=0{back:1} 1{back:1}` for synthetic ready states.
- replay smoke passed on existing local logs:
  - `logs/rl-transitions-back-4-3-3.ndjson`: imported `697` rows, produced `18` tabular states, all with `opp_attack=...`
  - `logs/rl-transitions-hp-4-3-3.ndjson`: imported `831` rows, produced `11` tabular states, all with `opp_attack=...`
- `git diff --check -- tools/rl_probe_server.py docs/plan-remote-rl-agent.md docs/remote-rl-agent-engineering-log.md` passed.

Follow-up:
- run a fresh tabular model/log after this change and check whether `ready_opp_attack=1{back:...}` appears as enough strike-warning states become ready.
- do not promote close-range throw defense until a separate action/feature plan is chosen; throw pressure should initially be treated as spacing risk, not as a visible startup flag.

## 2026-04-26: Remove Routine Span Probes From Transition Export

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / observation quality

Files changed:
- `src/rl/rl_session.c`
- `tools/rl_probe_server.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- keep transition NDJSON from mixing decision-time observations with post-observation span labels.
- prevent `*_seen` style fields from being mistaken for learner-safe OBS features.

Implementation notes:
- new transition rows no longer export:
  - `span_self_routine_attack_seen`
  - `span_opp_routine_attack_seen`
  - `span_self_contact_reaction_seen`
  - `span_opp_contact_reaction_seen`
- `obs_self_routine_attack_state`, `obs_opp_routine_attack_state`, `obs_self_contact_reaction_state`, and `obs_opp_contact_reaction_state` remain because they are decision-observation snapshots.
- run-level defensive-success analysis should be reconstructed offline from consecutive `obs_*` rows plus HP/stun deltas instead of storing future-window labels in each row.

## 2026-04-26: Rename Routine Span Probes

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / observation quality

Files changed:
- `src/rl/rl_session.c`
- `tools/rl_probe_server.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- avoid confusing decision-span labels with decision-observation fields.
- make it clear that `*_seen` fields contain events that happened during the action span after the observation was sampled.

Implementation notes:
- transition NDJSON briefly wrote routine/contact span aggregate fields with a `span_` prefix.
- `obs_*` fields remain reserved for decision-time snapshots that the remote policy can actually observe at inference time.
- this intermediate experiment was superseded the same day by removing span probes from new transition exports.

## 2026-04-26: Add Routine Attack / Contact Reaction Validation Probes

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / observation quality

Files changed:
- `src/rl/rl_observation.h`
- `src/rl/rl_observation.c`
- `src/rl/rl_protocol.h`
- `src/rl/rl_session.c`
- `tools/rl_probe_server.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- validate whether `routine_no[1] == 4` is a trustworthy opponent/self attack-state flag.
- validate whether `routine_no[1] == 1` can identify contact / defensive reaction windows when paired with subsequent HP delta.
- keep these fields validation-only before using them in the learner state key or reward shaping.

Implementation notes:
- `RLObservationV1` now derives:
  - `self_routine_attack_state`
  - `opp_routine_attack_state`
  - `self_contact_reaction_state`
  - `opp_contact_reaction_state`
- UDP OBS payload schema advanced to version `2` and now carries those four derived flags alongside the compact spacing fields.
- Transition NDJSON now exports decision-observation flags:
  - `obs_self_routine_attack_state`
  - `obs_opp_routine_attack_state`
  - `obs_self_contact_reaction_state`
  - `obs_opp_contact_reaction_state`
- An intermediate build also exported decision-span flags, but those were removed from new transition rows because they mixed post-observation labels into the learner-visible log.
- `tools/rl_probe_server.py` parses the schema-v2 OBS payload and imports the new decision-observation transition fields, but `tabular_state_key()` still ignores them so live policy behavior does not change yet.

Validation plan:
- run the usual Windows probe command with the updated script and redeployed runtime.
- confirm `obs_opp_routine_attack_state` lines up with overlay `OR*,4,*` on opponent attacks.
- infer defensive-success windows offline from consecutive `obs_*` rows plus HP/stun deltas, instead of relying on per-row span labels.
- do not promote these flags to learner features until live logs show stable semantics across normals, projectiles, throws, and multistage moves.

## 2026-04-26: Add Transition Reward Attribution Analyzer

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / reward diagnosis

Files changed:
- `tools/analyze_rl_transitions.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- make long-run tabular policy interpretation repeatable by summarizing HP-delta reward by action and distance bucket
- distinguish direct action-row reward from delayed neutral/recovery reward credited back to the latest explicit action

Implementation notes:
- added `tools/analyze_rl_transitions.py`.
- the analyzer reuses `rl_probe_server.py`'s tabular action mapping, `tabular_training_reward()`, and `obs_abs_dx` bucket thresholds.
- output includes:
  - `DIRECT_BY_ACTION`
  - `DIRECT_BY_ACTION_DX`
  - `CREDITED_BY_ACTION`
  - `CREDITED_BY_ACTION_DECISION_DX`
  - `DELAYED_CREDIT_DECISION_DX_TO_REWARD_DX`
- delayed credit is episode-scoped: nonzero reward on a neutral/unknown row is attributed to the most recent explicit tabular action in the same `(run_id, episode_id)`.

Validation:
- `python3 -m py_compile tools/analyze_rl_transitions.py` passed.
- `python3 tools/analyze_rl_transitions.py logs/rl-transitions-tabular-4-3-3.ndjson --tail-rows 100000 --limit 30` passed.
- `python3 tools/analyze_rl_transitions.py logs/rl-transitions-tabular-4-3-3.ndjson --limit 30` passed on `383918` rows.
- `git diff --check -- tools/analyze_rl_transitions.py docs/plan-remote-rl-agent.md docs/remote-rl-agent-engineering-log.md` passed.

Long-run readout from `logs/rl-transitions-tabular-4-3-3.ndjson`:
- full log analyzed: `rows=383918`, `done=448`, `explicit_rows=122774`, `reward_rows=13115`, `delayed_credit_rows=9236`.
- direct action rows:
  - `hp`: `reward=+2900`, `mean=+0.072`
  - `fireball`: `reward=+439`, `mean=+0.015`
  - `throw`: `reward=-109`, `mean=-0.007`
- direct distance split:
  - `fireball dx=far`: `reward=+1625`, `mean=+0.074`
  - `fireball dx=mid`: `reward=-832`, `mean=-0.125`
  - `fireball dx=close`: `reward=-354`, `mean=-0.609`
  - `throw dx=far`: `reward=+514`, `mean=+0.041`
  - `throw dx=mid`: `reward=-444`, `mean=-0.119`
  - `throw dx=close`: `reward=-179`, `mean=-0.577`
- credited view:
  - `fireball`: `reward=+2391`, `mean=+0.071`
  - `hp`: `reward=-2303`, `mean=-0.054`
  - `throw`: `reward=-3435`, `mean=-0.200`
- key interpretation:
  - far fireball is currently the cleanest positive signal.
  - mid/close fireball is strongly punished, so the policy should keep learning spacing sensitivity rather than treating fireball as universally good.
  - throw is not yet a reliable positive action in the credited view, even if some far throw rows look mildly positive; that far-throw signal is likely spacing/credit leakage rather than real throw strength.

Follow-up:
- use this analyzer after each long run before changing the action set.
- if throw remains selected despite negative credited reward, inspect whether the learner's q-table has stale lucky throw buckets or whether move-level labels are needed before throw can be learner-safe.
- add move-level transition labeling before using projectile/throw/DP labels as hard reward features.

## 2026-04-26: Fix Transition Sender Running-State Race

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / long-run stability

Files changed:
- `src/rl/rl_net.c`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- fix the remaining transition sender lifecycle race after ruling out perf-capture config as the latest long-run restart cause

Investigation notes:
- MiSTer remote config at `/media/fat/games/3s-arm/config` had no `perf-*` keys.
- recent MiSTer-side logs contained no `PERF capture` entries.
- `lock-status` reported the remote lock as free before the read-only config check.
- `busy-status` using the old default host failed, so the follow-up check used explicit `192.168.0.133`.
- review found `transition_sender_thread_running` was still read/written from both the game thread and sender thread without the queue mutex.
- there was a missed-wakeup window: the sender could observe an empty queue and be about to exit while a new batch was enqueued; the game thread could still see `running=true` and skip starting a replacement sender.

Implementation notes:
- `transition_sender_thread_running` is now cleared by `RLNet_PopQueuedTransitionBatch()` while holding `transition_queue_mutex` when the queue is observed empty.
- `RLNet_MaybeStartTransitionSenderThread()` now checks `transition_sender_thread_running`, reaps completed thread handles, and starts replacement sender threads under the same queue mutex.
- completed sender threads are still joined outside the mutex to avoid deadlock.
- `RLNet_Shutdown()` now snapshots and waits the sender thread without clearing the handle while it is still running, then clears handle/state under the mutex after wait.
- `reset_transition_queue()` now locks the queue mutex when it already exists before freeing queued payloads.

Validation:
- read-only remote config check confirmed no active perf-capture config keys and no recent `PERF capture` logs.
- `git diff --check -- src/rl/rl_net.c` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed and produced `build/mister-telemetry-package`.

Follow-up:
- deploy this telemetry package before the next long RL run.
- during the next long run, watch transition counters and MiSTer `dmesg`; if the process still restarts without OOM or perf-capture logs, collect uptime plus the last 100 lines of dmesg immediately after restart.

## 2026-04-26: Add Anti-DP Fireball Macro Variant

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / tabular macro-action execution

Files changed:
- `tools/rl_probe_server.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- reduce accidental shoryuken parsing from the learned fireball macro so damage credit is less likely to be assigned to `fireball` when the game actually performed a DP

Investigation notes:
- transition logs contained no direct shoryuken final inputs:
  - `down-forward + LP` (`0x0018`) count was `0`
  - `down-forward + HP` (`0x0048`) count was `0`
- visible accidental shoryukens were most likely caused by command-buffer context, where a previous `forward`-like action plus QCF+LP looked like a DP motion to the game parser.
- since current learner credit is input-level (`executed_action_wire`) rather than move-code-level, such accidental DPs would be credited as `fireball` if they ended on `forward + LP`.

Implementation notes:
- `fireball` and `ryu-fireball` scripted sequences now emit:
  - `down-back -> down -> down-forward -> forward+LP -> neutral -> neutral`
- the leading `down-back` is intended to clear a prior `forward` from the effective command sequence before the QCF+LP finish.

Validation:
- `python3 -m py_compile tools/rl_probe_server.py` passed.
- synthetic sequence smoke passed: both `fireball` and `ryu-fireball` now expand to `0x7,0x2,0x8,0x14,0x0,0x0`.
- synthetic macro smoke passed: tabular fireball emits the same anti-DP sequence while macro-locked.

Follow-up:
- rerun live tabular and confirm fireballs still appear while accidental shoryuken frequency drops.
- long-term fix remains move-level transition labeling so learner credit can distinguish actual fireball from actual shoryuken.

## 2026-04-26: Lock Tabular Fireball Macro Sequence

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / tabular macro-action execution

Files changed:
- `tools/rl_probe_server.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- make tabular `fireball` execute as one uninterrupted QCF+LP macro instead of letting every OBS reply re-run q-table selection and break the motion

Investigation notes:
- transition logs showed `fireball` was attempted (`forward + LP`, `0x0014`) only `16` times while `throw` appeared `220` times.
- all recorded fireball attempts had `delta_opp_hp = 0` and `delta_self_hp = 0`.
- the user confirmed no projectile was visible on screen.
- root cause: tabular selection could choose `fireball` for one decision, then the next decision could choose `hp`, `throw`, or another action before the full `down -> down-forward -> forward -> forward+LP` sequence finished.

Implementation notes:
- `policy_action_wire()` now receives a `macro_states` table keyed by session/run/episode.
- when tabular chooses a multi-step scripted action, the probe server starts an active macro and emits the first sequence step.
- later OBS replies for the same episode emit the next macro step before consulting the q-table again.
- the macro state is cleared after the full sequence, including neutral recovery frames, is emitted.
- fixed single-step actions such as `throw` still execute immediately without macro lock.

Validation:
- `python3 -m py_compile tools/rl_probe_server.py` passed.
- synthetic macro-lock smoke passed: after a tabular `fireball` selection, later calls whose q-table preferred `hp` still emitted `0x2,0x8,0x4,0x14,0x0,0x0`, then returned to `hp`.

Follow-up:
- rerun live tabular and confirm a visible projectile appears when fireball is selected.
- after live confirmation, check transition log for `0x0014` rows followed by nonzero `delta_opp_hp` when fireballs connect.

## 2026-04-26: Fix Long-Run RL Transition Sender Thread Leak

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / long-run stability

Files changed:
- `src/rl/rl_net.c`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- stop long RL runs from eventually exhausting MiSTer memory and getting `3s-arm` killed by the kernel OOM killer

Investigation notes:
- MiSTer `dmesg` showed:
  - `Out of memory: Killed process ... (3s-arm)`
  - `total-vm:459000kB`
  - `anon-rss:445584kB`
- the device itself had about `492MB` RAM, so this matched the observed "MiSTer side restarts" symptom: `3s-arm` was killed and the wrapper/front-end recovered.
- the highest-risk RL path was transition batch sending:
  - every episode can queue a transition batch
  - `RLNet_MaybeStartTransitionSenderThread()` created a short-lived sender thread
  - when the thread finished, it only set `transition_sender_thread_running = false`
  - the next batch could overwrite `transition_sender_thread` with a new handle without joining the completed thread

Implementation notes:
- `RLNet_MaybeStartTransitionSenderThread()` now:
  - returns while an existing sender is still running
  - joins and clears a completed sender thread before creating another one
  - sets `transition_sender_thread_running` before thread creation and clears it on create failure
- runtime reset now frees any queued transition batch payloads before clearing the queue, covering the rare reset/create-failure path.

Validation:
- `git diff --check -- src/rl/rl_net.c docs/plan-remote-rl-agent.md docs/remote-rl-agent-engineering-log.md` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed and produced `build/mister-telemetry-package`.

Follow-up:
- deploy and run a long RL session while sampling `/proc/<3s-arm pid>/status`; `VmRSS` should stop climbing episode-by-episode.
- watch MiSTer overlay transition counters `TBQ/TBS/TBA/TBF` to confirm transition batches still send after the thread lifecycle change.

## 2026-04-26: Add Fireball / Throw To Tabular Action Set

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / tabular action diversity and observability

Files changed:
- `tools/rl_probe_server.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- expand the first tabular learner action set beyond movement and HP so distance-specific behavior has clearer options to discover
- expose ready greedy action distribution by distance bucket instead of relying only on the single global `top_ready` action

Implementation notes:
- the default tabular action set is now `forward`, `back`, `hp`, `forward-hp`, `fireball`, and `throw`.
- tabular `throw` maps to the same single-frame wire used by the scripted throw probe: `forward + LP + LK`.
- tabular `fireball` runs the existing QCF+LP scripted sequence under the shorter learner action name `fireball`.
- transition rows map the final `forward + LP` execution wire back to `fireball`, allowing delayed HP-delta rewards to be credited to the high-level tabular action.
- learner snapshots now count the best ready greedy action per state and print:
  - `ready_actions=<action>:<state_count>,...`
  - `ready_dx=close{...} mid{...} far{...}`
- this summary uses the same `min_n` and positive-score gate as greedy tabular inference.

Validation:
- `python3 -m py_compile tools/rl_probe_server.py` passed.
- synthetic Python smoke passed:
  - `forward+LP` mapped to `fireball`
  - `forward+LP+LK` mapped to `throw`
  - ready summary produced `close{throw:1} mid{fireball:1} far{forward:1}` for a hand-built q-table
- synthetic policy smoke passed: a tabular q-table whose best ready action was `fireball` emitted the expected QCF+LP sequence (`0x2`, `0x8`, `0x4`, `0x14`).
- `git diff --check -- tools/rl_probe_server.py docs/plan-remote-rl-agent.md docs/remote-rl-agent-engineering-log.md` passed.

Follow-up:
- run live tabular and watch whether `ready_actions` / `ready_dx` diversify beyond `hp`.
- expect early learning to be slower because the action space grew from four actions to six.

## 2026-04-26: Same-Frame OBS Spacing Payload For Tabular Inference

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / tabular state freshness

Files changed:
- `src/rl/rl_protocol.h`
- `src/rl/rl_net.h`
- `src/rl/rl_net.c`
- `src/rl/rl_session.c`
- `tools/rl_probe_server.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- remove the tabular actor's dependence on the latest transition-replay bucket when choosing a live action
- make each UDP OBS request carry the current compact spacing snapshot so the PC chooses from the state seen on that OBS frame

Implementation notes:
- `RLObsSpacingPayloadV1` was added as a packed, schema-versioned payload behind the existing `RLObsPacketHeader.obs_len` field.
- MiSTer OBS packets now send `header + RLObsSpacingPayloadV1` and set `obs_len = sizeof(payload)`.
- the spacing payload uses the same fields already exported in transition rows: `obs_abs_dx`, `obs_abs_dy`, both players' front/back edge distances, and `obs_opp_in_front`.
- `RLSession_CaptureObservationSpacing()` and OBS payload creation share the same fill helper so ledger rows and live OBS state stay aligned.
- `tools/rl_probe_server.py` now parses the spacing payload, derives the same tabular bucket key, and passes that same-frame key to tabular inference.
- header-only or invalid OBS payloads still fall back to `latest_tabular_state`, preserving compatibility with older MiSTer builds.
- learner stats now include `obs=<payload>/<header-only>` and `tab_state=obs:<n>/latest:<n>` to make live state-source checks visible.

Validation:
- `python3 -m py_compile tools/rl_probe_server.py` passed.
- synthetic Python smoke packed an OBS spacing payload, parsed it, derived a tabular key, and selected the expected `forward-hp` action through the min-count gate.
- `git diff --check -- src/rl/rl_protocol.h src/rl/rl_net.h src/rl/rl_net.c src/rl/rl_session.c tools/rl_probe_server.py docs/plan-remote-rl-agent.md docs/remote-rl-agent-engineering-log.md` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed and produced `build/mister-telemetry-package`.

Follow-up:
- live-run tabular and confirm learner stats show `obs` payload counts rising and `tab_state=obs` dominating `latest`.

## 2026-04-25: Auto-Select VS Rematch For RL Sessions

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / automated reset loop

Files changed:
- `src/sf33rd/Source/Game/menu/menu.c`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- let RL sessions continue into another match without manual VS result input
- use the safest available path first by reusing the existing VS result rematch branch instead of hard-resetting match state

Implementation notes:
- a checkpoint commit was created before this change:
  - `9882679c checkpoint: before rl auto rematch`
- in `VS_Result()` case 4, when `RLSession_IsActive()` and `Mode_Type == MODE_VERSUS`, the menu now auto-confirms both result cursors and advances to existing case 6.
- case 6 still performs the real rematch transition through `Setup_VS_Mode(...)`, `G_No[1] = 12`, and `G_No[2] = 1`.
- the existing RL rematch guard in case 6 still forces `MODE_VERSUS`, `Play_Mode = 1`, and reapplies `RLSession_ApplyVersusOperatorSetup()`.
- live testing showed this reached character select but did not auto-confirm the same characters into the next match.
- the RL rematch path now marks both players with `Sel_PL_Complete = -0x8000`, reusing the existing character-select fast path that keeps `My_char[]` and enqueues player loading.
- when that fast path runs while RL is active in VS mode, `PL_Sel_1st()` immediately marks SA selection complete for the retained character, including the no-SA / `My_char == 0` paths.
- live testing still required each side to press LK twice, so the sentinel handling was moved earlier into `Sel_PL_Control()`:
  - `RLSession_AutoConfirmRematchSelect()` consumes `Sel_PL_Complete = -0x8000`
  - it enqueues player loading for the retained `My_char[]`
  - it marks character and SA selection complete before normal select input handling can wait for manual attack confirms
- live testing then reached the handicap/stage and CPU-character-select path. Root cause: RL-vs-CPU select still looked like one human operator plus one CPU operator, so normal VS/CPU selection logic did not take the "both sides selected" exit path.
- the auto-rematch select helper now temporarily marks both players as operators during the select exit path, sets an `rl_auto_rematch_select_ready` guard, and skips the handicap branch only for this guarded RL rematch path. `Game2_0()` still reapplies `RLSession_ApplyVersusOperatorSetup()` before battle, restoring the configured agent-vs-CPU operator split.
- this is the conservative auto-rematch path; direct skip from win scene to next match remains deferred until this proves stable.

Validation:
- previous `git diff --check -- src/sf33rd/Source/Game/menu/menu.c docs/plan-remote-rl-agent.md docs/remote-rl-agent-engineering-log.md` passed before the character-select follow-up.
- previous `tools/mister/build-game.sh --flavor telemetry` passed and produced `build/mister-telemetry-package` before the character-select follow-up.
- `git diff --check -- src/sf33rd/Source/Game/menu/menu.c src/sf33rd/Source/Game/screen/sel_pl.c docs/plan-remote-rl-agent.md docs/remote-rl-agent-engineering-log.md` passed after the character-select follow-up.
- `tools/mister/build-game.sh --flavor telemetry` passed after the character-select follow-up and produced `build/mister-telemetry-package`.
- `git diff --check -- src/sf33rd/Source/Game/screen/sel_pl.c docs/plan-remote-rl-agent.md docs/remote-rl-agent-engineering-log.md` passed after moving sentinel handling into `Sel_PL_Control()`.
- `tools/mister/build-game.sh --flavor telemetry` passed after moving sentinel handling into `Sel_PL_Control()` and produced `build/mister-telemetry-package`.
- `git diff --check -- src/sf33rd/Source/Game/screen/sel_pl.c docs/plan-remote-rl-agent.md docs/remote-rl-agent-engineering-log.md` passed after adding the guarded both-operators select exit.
- `tools/mister/build-game.sh --flavor telemetry` passed after adding the guarded both-operators select exit and produced `build/mister-telemetry-package`.

Follow-up:
- deploy the telemetry package and verify a full RL match can end and enter the next match without manual VS result input.
- confirm transition batches keep arriving after the automatically rematched match ends.

## 2026-04-25: Split Tabular Raw Top From Ready Top

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / tabular live-log accuracy

Files changed:
- `tools/rl_probe_server.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- make learner logs distinguish the highest raw q-score from the highest action that is actually eligible for greedy tabular inference
- avoid misleading logs such as `min_n=8 top=hp:1.10/4`, where the displayed top action was below the min-count gate and could not be used by the actor's greedy path

Implementation notes:
- `TabularPolicyLearner.snapshot(...)` now accepts `min_action_count`.
- snapshots still report the raw top q-score.
- snapshots also report `ready_*` fields for the highest positive q-score whose state/action count is at least `min_action_count`.
- learner stats now print:
  - `top_raw=<action>:<score>/<count>`
  - `top_ready=<action>:<score>/<count>`
- actor selection behavior is unchanged.

Validation:
- `python3 -m py_compile tools/rl_probe_server.py` passed.
- `git diff --check -- tools/rl_probe_server.py docs/plan-remote-rl-agent.md docs/remote-rl-agent-engineering-log.md` passed.
- synthetic snapshot smoke passed:
  - raw top was `hp 10.0/1`
  - ready top was `forward 1.0/8`
- learner-only smoke against the current tabular transition log printed both fields:
  - `top_raw=hp:2.24/14`
  - `top_ready=hp:2.24/14`
  - duplicate publish gate still held `model_pub=1` on repeated unchanged stats ticks

Follow-up:
- rerun live tabular and judge min-count readiness from `top_ready`, not `top_raw`.

## 2026-04-25: Skip Duplicate Tabular Actor Publishes

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / tabular live-log hygiene

Files changed:
- `tools/rl_probe_server.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- stop learner auto-publish from creating new actor versions when no new transition rows have produced tabular updates
- reduce live-log noise where model versions kept increasing while `rows`, `tab_updates`, and q-table contents were unchanged

Implementation notes:
- `LearnerLogTailer` now records the last published tabular update count.
- when auto-publish is due for `policy=tabular`, it publishes only if current `tab_updates` is greater than the last published value.
- skipped duplicate publishes still advance the next publish deadline so the learner does not spin on an expired timer.
- non-tabular learner publish behavior is unchanged.

Validation:
- `python3 -m py_compile tools/rl_probe_server.py` passed.
- `git diff --check -- tools/rl_probe_server.py docs/plan-remote-rl-agent.md docs/remote-rl-agent-engineering-log.md` passed.
- learner-only smoke with `--learner-stats-interval-sec 1` and `--learner-publish-interval-sec 1` passed:
  - first ready stats tick published `MODEL published version=1`
  - subsequent stats ticks had unchanged `rows=37870` and `tab_updates=26073`
  - `model_pub` stayed at `1` and no duplicate learner model versions were published

Follow-up:
- rerun live tabular and confirm `MODEL published version=...` only appears after a new transition batch/import increases `tab_updates`.

## 2026-04-25: Add Tabular Minimum-Sample Gate

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / tabular policy stability

Files changed:
- `tools/rl_probe_server.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- prevent sparse lucky-hit tabular q-scores from immediately becoming greedy actions during live play
- make early tabular learning more stable before adding same-frame OBS payloads or a neural learner

Implementation notes:
- `TabularPolicyLearner` now tracks per-state/action update counts alongside q-scores.
- learner-published tabular actor manifests now include:
  - `q_counts`
  - `min_action_count`
- `tabular_actor_action_wire()` only uses a positive q-score for greedy inference when that state/action count is at least `min_action_count`.
- `--tabular-min-action-count` defaults to `8`.
- epsilon exploration can still sample the configured tabular action set; the min-count gate applies to greedy q-table selection.
- learner stats now print `min_n=<count>` and `top=<action>:<score>/<count>` so live logs show whether the top-scoring action is well-supported or sparse.

Validation:
- `python3 -m py_compile tools/rl_probe_server.py` passed.
- synthetic actor smoke passed:
  - with `hp=10.0/count=1`, `forward=1.0/count=8`, and `min_action_count=8`, tabular inference selected `forward` (`wire=4`)
  - after raising `hp` to `count=8`, tabular inference selected `hp` (`wire=64`)
- learner-only smoke against the current tabular transition log published a tabular actor with `min_action_count=8`, `metadata.tabular_min_action_count=8`, and `q_counts` in `current.json`.

Follow-up:
- rerun live tabular with `--tabular-min-action-count 8`.
- watch for `top=.../<count>` and confirm low-count actions no longer dominate live behavior.
- if policy remains unstable after this gate, the next code step is same-frame OBS payload support so inference no longer depends on the latest learner-imported transition bucket.

Live follow-up:
- Windows Python running from a `\\wsl.localhost\Ubuntu\...` model directory hit a transient `PermissionError` during atomic `current.json` replacement:
  - `PermissionError: [WinError 5] Access is denied: '.current.<tmp>' -> 'current.json'`
- `tools/rl_probe_server.py` now wraps actor-manifest `os.replace(...)` calls in a short retry loop so a temporary Windows/UNC file lock does not kill the learner thread.

## 2026-04-25: Split Tabular Reward From Episode Reward

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / minimum learner reward hygiene

Files changed:
- `tools/rl_probe_server.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- keep terminal win/loss reward available for future sequential RL while preventing the current contextual-bandit tabular learner from assigning the whole `+100/-100` episode result to the last executed action

Implementation notes:
- transition `reward_accum` remains unchanged and still represents the full reward stream, including terminal win/loss bonus.
- tabular q-score updates now use learner-local `tabular_reward = delta_opp_hp - delta_self_hp`.
- neutral/recovery rows are still not learned as greedy actions.
- if a neutral/recovery row carries nonzero HP-delta reward, delayed credit now applies that HP-delta reward to the most recent explicit action bucket.
- learner stats now include `tab_reward=hp-delta:<sum>` to distinguish the tabular training signal from aggregate transition `rew=...`.
- learner-published actor metadata includes:
  - `tabular_reward_source = hp-delta`
  - `tabular_training_reward_total`

Validation:
- `python3 -m py_compile tools/rl_probe_server.py` passed.
- `git diff --check -- tools/rl_probe_server.py docs/plan-remote-rl-agent.md docs/remote-rl-agent-engineering-log.md` passed.
- synthetic learner-only smoke passed:
  - a terminal `forward` row with `reward_accum=105` but `delta_opp_hp=5` updated toward `5`, not `105`
  - a nonterminal `hp` row with `delta_opp_hp=15` became top action with `hp:0.75`
  - learner stats reported `tab_reward=hp-delta:20.0`
  - actor metadata included `tabular_reward_source=hp-delta` and `tabular_training_reward_total=20.0`

Follow-up:
- rerun live tabular smoke after deploy; expect HP-delta action scores to favor actions that directly cause damage or avoid damage, while `reward_accum` remains available for the future DQN/sequence learner.

## 2026-04-25: Preserve RL Transition Flush Across VS Rematch

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / live tabular smoke stability

Files changed:
- `src/rl/rl_session.c`
- `src/sf33rd/Source/Game/menu/menu.c`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- fix the live observation where second-match action control continued but transition batches stopped arriving after a later round ended
- keep RL active VS rematch flow from falling back into an arcade-style next-opponent route

Implementation notes:
- `RLSession_ApplyRemoteActionToBuffers()` now calls a reset guard before clearing remote runtime state.
- The guard finalizes the current episode ledger before reset when the remote runtime is initialized and gameplay has left the override-eligible battle state.
- This prevents `RLSession_ResetRemoteRuntime(false)` from clearing `transition_batch_payload` without first queueing it through `RLNet_QueueTransitionBatch(...)`.
- VS result rematch now forces `Mode_Type = MODE_VERSUS` and `Play_Mode = 1` while RL is active before entering the character-select transition.
- The VS rematch path also reapplies `RLSession_ApplyVersusOperatorSetup()` after forcing mode state, so the configured RL agent/operator split is restored for the next match.

Validation:
- `git diff --check -- src/rl/rl_session.c src/sf33rd/Source/Game/menu/menu.c` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed.

Follow-up:
- deploy the telemetry package to MiSTer before the next live test.
- rerun `--policy tabular` and confirm that a second match can end a round and still append transition rows.
- watch for duplicate `episode_end` rows; the transition importer dedupes by `(run_id, episode_id, decision_id)`, but duplicate terminal rows would still indicate C-side finalize sequencing needs one more guard.

## 2026-04-25: Minimal Tabular Learner Actor Loop

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / minimum training loop

Files changed:
- `tools/rl_probe_server.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- make the remote RL path train something real before adding more transition fields or neural-network dependencies
- prove that replay rows can update an actor manifest and that the action path can use the updated actor

Implementation notes:
- added `--policy tabular`.
- added a small contextual-bandit learner inside `tools/rl_probe_server.py`.
- transition rows are bucketed using the compact spacing snapshot:
  - `obs_abs_dx`
  - `obs_abs_dy`
  - `obs_self_front_edge_dist`
  - `obs_self_back_edge_dist`
  - `obs_opp_front_edge_dist`
  - `obs_opp_back_edge_dist`
  - `obs_opp_in_front`
- supported learned actions are:
  - `forward`
  - `back`
  - `hp`
  - `forward-hp`
- neutral rows are intentionally not learned as greedy actions in this first version, because delayed damage / recovery rewards can make "do nothing" look falsely positive before reward attribution is refined.
- when a neutral/recovery row carries nonzero reward, the learner conservatively credits that reward to the most recent explicit action bucket. This is a small learner-side credit-delay patch, not a replacement for later reward/transition refinement.
- each imported replay row updates one score with:
  - `score += alpha * (reward_accum - score)`
- learner-published `tabular` actor manifests now include:
  - `actions`
  - `epsilon`
  - `fallback_policy`
  - `updated_rows`
  - `q`
- OBS inference chooses from the active tabular q-table only when the latest known state has a positive-scoring action. Otherwise it falls back to a scripted policy, defaulting to `hp`.
- Current limitation:
  - MiSTer still sends a header-only OBS packet with `obs_len=0`.
  - Therefore Python-side tabular inference uses the latest spacing bucket imported by the learner from transition replay, not an exact same-frame OBS-derived state.
  - This is acceptable for the first closed-loop smoke, but a later schema-versioned OBS payload is needed before treating tabular policy quality as meaningful gameplay evidence.
- learner stats now include:
  - `tab_states`
  - `tab_updates`
  - `tab_ignored`
  - `tab_delayed`
  - `eps`
  - `top`

Validation:
- `python3 -m py_compile tools/rl_probe_server.py` passed.
- `git diff --check -- tools/rl_probe_server.py` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed.
- synthetic smoke passed:
  - one HP replay row with positive reward created one spacing bucket
  - publishing that q-table as a `tabular` actor selected `executed_action_wire=64` for the same latest bucket
- learner-only smoke against `logs/rl-transitions-hp-4-3-3.ndjson` imported `585` rows, created `13` tabular states, applied `87` updates, ignored `518` neutral rows, credited `20` delayed reward rows back to the previous explicit action, published tabular actors, and reported `top=hp:10.38`.

Follow-up:
- run first live `tabular` pass at timing `4/3/3`.
- confirm learner logs show nonzero `tab_states` and `tab_updates`.
- confirm actor manifests in `model/rl-model-tabular` contain `q`.
- confirm transition rows show `model_version_executed` advancing after learner publishes.
- do not judge gameplay quality until OBS carries same-frame learner state or the transition/import delay is explicitly modeled.

## 2026-04-25: Add Compact Spacing State To Transition Replay Rows

Milestone:
- Milestone 5: Async learner and model hot-swap / Milestone 6 transition data quality

Files changed:
- `src/rl/rl_session.c`
- `tools/rl_probe_server.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- keep the RL loop moving while restoring the minimum spacing state replay-only learners need to learn distance, approach, retreat, and corner pressure
- avoid restoring the full debug-heavy observation schema into transition rows

Implementation notes:
- transition NDJSON now includes a decision-observation spacing snapshot:
  - `obs_abs_dx`
  - `obs_abs_dy`
  - `obs_self_front_edge_dist`
  - `obs_self_back_edge_dist`
  - `obs_opp_front_edge_dist`
  - `obs_opp_back_edge_dist`
  - `obs_opp_in_front`
- `obs_abs_dx` / `obs_abs_dy` are raw absolute enemy distances from the controlled agent's perspective.
- front/back edge distances are derived from each fighter's facing sign:
  - facing world-left: front is left edge, back is right edge
  - facing world-right: front is right edge, back is left edge
- `tools/rl_probe_server.py` learner replay import now preserves the same seven fields.
- Signed `dx/dy` and left/right corner ratios remain useful debug/future-schema candidates, but are intentionally not part of the first learner-safe replay spacing subset.

Validation:
- `git diff --check -- src/rl/rl_session.c tools/rl_probe_server.py docs/plan-remote-rl-agent.md docs/remote-rl-agent-engineering-log.md` passed.
- `python3 -m py_compile tools/rl_probe_server.py` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed.
- local synthetic `learner_replay_row()` smoke passed for the new spacing fields: `obs_abs_dx`, `obs_abs_dy`, front/back edge distances, and `obs_opp_in_front`.
- live `hp` policy validation produced `logs/rl-transitions-hp-4-3-3.ndjson` with:
  - `rows=585`
  - `done=2`
  - `terminal_reason` counts: `decision_replaced=583`, `episode_end=2`
  - `obs_frame` out-of-order count: `0`
  - spacing fields present on all `585` rows
  - `obs_abs_dx` range: `1..322`
  - `obs_abs_dy` range: `0..125`
  - `obs_opp_in_front`: `579` rows true, `6` rows false
  - actions: `executed_action_wire=64` on `67` rows, neutral on `518` rows
  - both episodes ended with `final_self_hp=160`, `final_opp_hp=0`, `total_reward=260`

## 2026-04-25: Slim Transition Log From 55 to 22 Fields

Milestone:
- Milestone 5: Async learner and model hot-swap / transition data quality

Files changed:
- `src/rl/rl_session.c`
- `tools/rl_probe_server.py`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- reduce transition log (rl-transitions.ndjson) to only the fields needed for RL training and debugging
- remove 33 debug-only, redundant, and stale fields to shrink per-row JSON size and simplify the learner pipeline

Kept fields (22):
- Identity: `run_id`, `episode_id`, `decision_id`, `round_num`, `obs_frame`
- Characters: `agent_character_id`, `opponent_character_id`
- Action: `executed_action_wire`
- Combat deltas: `delta_self_hp`, `delta_opp_hp`, `delta_self_stun`, `delta_opp_stun`
- Movement deltas: `delta_self_y`, `delta_opp_y`, `delta_self_forward`, `delta_opp_forward`
- Debug HP: `final_self_hp`, `final_opp_hp`
- Model: `model_version_executed`
- RL core: `reward_accum`, `done`, `terminal_reason`

Removed fields (33):
- Config constants repeated every row: `decision_delay_frames`, `decision_interval_frames`, `action_hold_frames`
- Redundant HP snapshots: `start_self_hp`, `start_opp_hp` (recoverable from prior final_hp)
- Redundant action decomposition: `executed_move_intent`, `executed_attack_bits`, `requested_action_wire`, `requested_move_intent`, `requested_attack_bits`
- Now-constant flags: `was_executed` (always true), `execution_source` (always remote)
- Debug timing: `target_frame`, `execution_frame_actual`
- Redundant position: `delta_self_x`, `delta_opp_x` (forward already accounts for facing)
- Debug model versions: `model_version_expected`, `model_version_requested`
- Overlay attack counters: `overlay_attack_event_finalized`, `overlay_attack_contact`, `overlay_attack_whiff`
- Requested attack tracking: `requested_attack_entered_state`, `requested_attack_made_contact`, `requested_attack_likely_whiffed`, `requested_attack_input_started`, `requested_attack_became_active`
- Observed attack tracking: `observed_attack_state_started`, `observed_attack_code_changed`, `observed_attack_counter_started`
- Throw tracking: `self_throw_started`, `opp_throw_caught_started`, `self_throw_seen`, `opp_throw_caught_seen`

Python side changes:
- `learner_replay_row()` whitelist updated to match 22-field schema
- Removed `was_executed` guard (no longer needed, all exported rows are executed)
- `LearnerLogTailer._consume_row()` simplified: removed timing bucket, execution source, overlay attack, and throw counter tracking
- `LearnerLogTailer._print_stats()` simplified: removed timing/source/fallback reporting
- Removed stale init member variables
- Removed `RLSession_ExecutionSourceLabel()` (unused after removing execution_source from log)

Validation:
- `python3 -m py_compile tools/rl_probe_server.py` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed.


## 2026-04-25: Remove Pending Attack Outcome Mechanism — Fix Reward Routing And Log Ordering

Milestone:
- Milestone 5: Async learner and model hot-swap / transition correctness follow-up

Files changed:
- `src/rl/rl_session.c`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- fix severe reward routing bug where 98.5% of transition rows had `reward_accum = 0` because the `pending_attack_outcome` mechanism routed all HP damage reward to old decisions instead of the currently active one
- fix out-of-order `obs_frame` in transition logs caused by delayed finalization of attack outcome entries

Root cause analysis:
- the earlier `pending_attack_outcome` mechanism (added 2026-04-25 "Attack Outcome Attribution Window Fix") held old decisions alive for 240 frames to capture delayed HP damage
- this caused `combat_entry` to point at a stale ledger entry instead of the currently active one, so per-frame `opp_hp_delta - self_hp_delta` reward accumulated on old decisions
- when the 240-frame window expired, the old entry was finalized with `terminal_reason = attack_outcome_window_closed` and written to the log after much newer entries, breaking obs_frame ordering
- evidence from `logs/rl-transitions-throw-4-3-3.ndjson`:
  - 1404 of 1426 rows (98.5%) had `reward_accum = 0`
  - 21 `attack_outcome_window_closed` rows carried all the HP damage reward
  - 25 out-of-order obs_frame entries, each delayed by exactly 237 frames (~4 seconds)
  - 3 `episode_end` done=true rows per episode instead of one

Implementation notes:
- removed the `pending_attack_outcome` and `attack_outcome_deadline_frame` fields from `RLDecisionLedgerEntry`
- removed `RLSession_FindPendingAttackOutcomeEntry()` and `RLSession_FinalizeExpiredAttackOutcomeEntries()` functions
- removed terminal_reason `4` (`attack_outcome_window_closed`) — only `decision_replaced`, `episode_end`, and `not_terminal` remain
- removed `RL_ATTACK_OUTCOME_WINDOW_FRAMES` constant
- simplified `RLSession_SetActiveLedgerEntry()` — old entries are always finalized with `decision_replaced` instead of being held alive
- simplified `RLSession_FinalizeEpisodeLedger()` — win/loss +100/-100 bonus goes directly to `active_ledger_entry`
- simplified `RLSession_OnObservationFrameEnd()`:
  - removed `pending_attack_entry`, `combat_entry`, and `has_combat_signal` variables
  - all HP delta / stun / combat signals now accumulate on the currently active decision entry
  - `RLSession_IsRoundEndHpSync()` guard simplified (no longer conditioned on pending_attack_entry)
- overlay attack counters (ACC/AWC/AH) remain unchanged — they use their own independent `overlay_attack_event_pending` / `overlay_attack_event_seq` mechanism which is not affected

Design rationale:
- for RL training, the reward signal must be associated with the decision that was **active when damage occurred**, not the decision that initiated the attack
- the RL learner will learn temporal credit assignment through its own value function / Q-network; the transition export should not try to do temporal credit assignment itself
- this makes every `decision_replaced` row self-contained: it includes all HP/stun deltas and reward that occurred during that decision's active window

Expected behavior after fix:
- every `decision_replaced` row that spans a damage frame will have nonzero `delta_opp_hp` or `delta_self_hp`
- `reward_accum` will be nonzero on the decision that was active when damage actually occurred
- transition log will always be in `obs_frame` order (no delayed finalization)
- each episode will have exactly one `done=true` row with `terminal_reason = episode_end`

Validation:
- `git diff --check -- src/rl/rl_session.c` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed.
- Hardware validation needed: rerun throw policy match and confirm rewarded rows are spread across active decisions instead of concentrated on stale attack outcomes.


## 2026-04-25: Attack Outcome Attribution Window Fix

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / transition correctness follow-up

Files changed:
- `src/rl/rl_session.c`
- `tools/rl_probe_server.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- fix severe transition shrinkage where attacks visibly hit but HP reward and attack outcome labels were exported on later neutral rows or compressed into terminal rows

Implementation notes:
- attack decisions now keep a 240-frame pending outcome window after their input frame instead of being finalized immediately when the next decision becomes active
- pending attack ledgers are protected from reuse until exported, so later hit/contact/throw observations can still be attributed back to the attack that caused them
- combat deltas now prefer the most recent pending attack ledger within the outcome window; movement span data still accrues to the active decision row
- terminal observations now compute and apply the final HP/stun/contact deltas before episode finalization instead of returning early
- round win/loss bonus now also prefers the pending attack owner, so final-hit damage and KO reward land on the same attack decision when possible
- round-end HP sync suppression is no longer allowed to drop large terminal damage if a pending attack owner exists
- transition rows again export the requested attack outcome fields:
  - `requested_attack_entered_state`
  - `requested_attack_made_contact`
  - `requested_attack_likely_whiffed`
  - `requested_attack_input_started`
  - `requested_attack_became_active`
  - `observed_attack_state_started`
  - `observed_attack_code_changed`
  - `observed_attack_counter_started`
- learner stats now print `reqatk=<active>/<contact>/<whiff>` alongside the existing overlay `atk=` summary

Validation:
- `git diff --check -- src/rl/rl_session.c tools/rl_probe_server.py` passed.
- `python3 -m py_compile tools/rl_probe_server.py` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed.

Follow-up:
- rerun short `hp`, `throw`, and one special policy pass to confirm positive damage rows now align with attack-request rows instead of mostly neutral/terminal rows
- tune `RL_ATTACK_OUTCOME_WINDOW_FRAMES` if 240 frames is too wide for overlapping multi-attack policies or still too short for slow projectile/special outcomes

## 2026-04-25: Throw Transition HP Span Fix

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum

Files changed:
- `src/rl/rl_session.c`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- fix move-family review evidence where `logs/rl-transitions-throw-4-3-3.ndjson` won two rounds by throw but exported too few positive damage rows and misleading round-start HP spans

Implementation notes:
- reviewed `logs/rl-transitions-throw-4-3-3.ndjson`:
  - `rows=256`
  - `done=2`
  - `total_delta_opp_hp=320`
  - `estimated_16hp_successes=20`
  - `row_positive_damage=5`
- root cause:
  - transition rows exported `start_self_hp` / `start_opp_hp` from round-start HP, not decision-start HP
  - terminal non-battle observations could be accumulated as combat damage before episode finalization, compressing remaining round damage into the last decision row
- `RLSession_SendRemoteObservationIfDue()` and the active-ledger fallback now initialize `start_*_hp` from the current observation HP
- `RLSession_OnObservationFrameEnd()` now finalizes terminal observations before damage/reward accumulation, preserving the round-win bonus without treating post-round state cleanup as a huge hit

Validation:
- old-log review command:
  ```sh
  jq -s '{rows:length,done:map(select(.done==true))|length,row_positive_damage:map(select(.delta_opp_hp>0))|length,total_delta_opp_hp:(map(.delta_opp_hp)|add),estimated_16hp_successes:((map(.delta_opp_hp)|add)/16),positive_reward_rows:map(select(.reward_accum>0))|length,total_reward:(map(.reward_accum)|add),rounds:([.[].episode_id]|unique)}' logs/rl-transitions-throw-4-3-3.ndjson
  ```
- old-log review result:
  ```text
  rows=256 done=2 row_positive_damage=5 total_delta_opp_hp=320 estimated_16hp_successes=20 positive_reward_rows=5 total_reward=520 rounds=1,2
  ```
- `git diff --check -- src/rl/rl_session.c` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed.

Follow-up after rerun:
- a new `logs/rl-transitions-throw-4-3-3.ndjson` still showed the same shape:
  - `rows=256`
  - `done=2`
  - `row_positive_damage=4`
  - `total_delta_opp_hp=314`
  - `estimated_16hp_successes=19.625`
  - `positive_reward_rows=4`
- the first fix worked for decision-local `start_opp_hp`, but did not remove the round-end HP sync:
  - the last row in episode 2 exported `start_opp_hp=144`, `final_opp_hp=3`, `delta_opp_hp=141`, `reward_accum=241`
- the log also showed only six rows where the throw macro was actually requested / executed, so "won two rounds by throw" cannot be validated by counting requested throw action rows alone
- added direct throw/caught observation and transition fields:
  - `self_throw_started`
  - `opp_throw_caught_started`
  - `self_throw_seen`
  - `opp_throw_caught_seen`
- learner stats now print `throw=<self_started>/<opp_caught_started>` for live validation
- added a conservative round-end HP sync guard to keep large `<=3 HP` conclusion-state jumps out of per-decision HP reward while preserving the explicit round-win bonus

Follow-up validation:
- `python3 -m py_compile tools/rl_probe_server.py` passed.
- `git diff --check -- src/rl/rl_session.c src/rl/rl_observation.c src/rl/rl_observation.h tools/rl_probe_server.py` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed.

## 2026-04-24: First Scripted Move-Family Pass Set Completed

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum

Files changed:
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- record the first full fixed-policy move-family pass set and establish the next phase after baseline timing stabilization

Implementation notes:
- the first fixed `4/3/3` move-family pass set was completed for:
  - `hp`
  - `throw`
  - `ryu-fireball`
  - `tatsu`
  - `shoryuken`
- all five runs kept the control path healthy:
  - `sources=remote:...`
  - `fallback_pct=0.00`
  - `policy_fallback_pct=0.00`
  - stable sub-millisecond `inf` telemetry
- current first-pass interpretation:
  - `ryu-fireball`: pass
  - `shoryuken`: pass
  - `throw`: provisional pass
  - `tatsu`: provisional pass
  - `hp`: control-path pass, but not a clean apples-to-apples comparison run because it used the live learner/model-dir path instead of the fixed-policy-only path
- this is enough to move to the next sub-phase:
  - fixed movement-prefix attack validation
  - examples: walk-forward-then-attack, crouch-then-attack, short retreat-then-attack
- this is not yet enough to promote all attack-outcome fields to learner-safe labels across every move family

Validation:
- representative learner logs:
  ```text
  LEARNER rows=256 done=2 run=5 ep=5 atk=6/6/0 replay=256/256 skipped=0 rew=+6/-0/0250 timing=4/3/3 timing_rows=256 timing_done=2 timing_rew=+6/-0/0250 policy=ryu-fireball policy_rows=256 policy_done=2 policy_rew=+6/-0/0250 sources=remote:256 fallback_pct=0.00 timing_fallback_pct=0.00 policy_fallback_pct=0.00 ready=yes warmup=100 batch=32 batch_mean=0.000 model_exec=0 model_active=0 model_pub=0 model_load=0 model_counts=0/0 inf=512:106.9/205.9/368.8us
  LEARNER rows=256 done=2 run=9 ep=2 atk=6/6/0 replay=256/256 skipped=0 rew=+7/-0/0249 timing=4/3/3 timing_rows=256 timing_done=2 timing_rew=+7/-0/0249 policy=shoryuken policy_rows=256 policy_done=2 policy_rew=+7/-0/0249 sources=remote:256 fallback_pct=0.00 timing_fallback_pct=0.00 policy_fallback_pct=0.00 ready=yes warmup=100 batch=32 batch_mean=0.000 model_exec=0 model_active=0 model_pub=0 model_load=0 model_counts=0/0 inf=512:111.9/207.3/289.2us
  LEARNER rows=256 done=2 run=8 ep=2 atk=4/3/1 replay=256/256 skipped=0 rew=+4/-0/0252 timing=4/3/3 timing_rows=256 timing_done=2 timing_rew=+4/-0/0252 policy=tatsu policy_rows=256 policy_done=2 policy_rew=+4/-0/0252 sources=remote:256 fallback_pct=0.00 timing_fallback_pct=0.00 policy_fallback_pct=0.00 ready=yes warmup=100 batch=32 batch_mean=8.125 model_exec=0 model_active=0 model_pub=0 model_load=0 model_counts=0/0 inf=512:118.8/204.6/278.3us
  ```

## 2026-04-24: Policy-Bucket Learner Summary For Move-Family Validation

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum

Files changed:
- `tools/rl_probe_server.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- prepare move-family validation by letting one learner log report per-policy replay aggregates, not just overall or per-timing aggregates

Implementation notes:
- `ActorModelStore` now keeps a lightweight version-to-policy lookup using published actor manifests
- learner log tailing now maintains a small aggregate bucket per executed policy
- each `LEARNER` line now reports for the latest executed policy:
  - `policy=...`
  - `policy_rows=...`
  - `policy_done=...`
  - `policy_rew=+/-/0`
  - `policy_fallback_pct=...`
- this is aimed at upcoming scripted move-family passes with policies such as:
  - `hp`
  - `throw`
  - `ryu-fireball`
  - `tatsu`
  - `shoryuken`
- the current implementation assumes actor manifests remain available in `--model-dir` for executed model versions that appear in transition rows

Validation:
- `python3 -m py_compile tools/rl_probe_server.py` pending.
- `git diff --check -- tools/rl_probe_server.py docs/plan-remote-rl-agent.md docs/remote-rl-agent-engineering-log.md` pending.

## 2026-04-24: First Clean 4/3/3 Timing Candidate

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum

Files changed:
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- record the first short live timing sweep where `4/3/3` produced clean remote-only execution with zero fallback in the learner log

Implementation notes:
- live learner logs for `timing=4/3/3` showed:
  - `sources=remote:128`, then `sources=remote:256`
  - `fallback_pct=0.00`
  - `timing_fallback_pct=0.00`
  - `inf=512:95.7/189.2/939.6us` by the second sampled window
- the same run also showed stable publish-to-execute lag:
  - `model_exec=596 model_active=599 model_pub=599`
  - later `model_exec=599 model_active=600 model_pub=600`
- this is strong early evidence that `4/3/3` is a viable Milestone 6 timing candidate from a transport/control-path perspective
- this does not yet prove stronger gameplay outcomes than `4/4/4`; the sample is still small:
  - `rows=256`
  - `done=2`
  - `rew=+2/-6/0248`

Validation:
- Live log evidence:
  ```text
  LEARNER rows=128 done=1 run=5 ep=2 atk=7/1/6 replay=128/128 skipped=0 rew=+0/-1/0127 timing=4/3/3 timing_rows=128 timing_done=1 timing_rew=+0/-1/0127 sources=remote:128 fallback_pct=0.00 timing_fallback_pct=0.00 ready=yes warmup=100 batch=32 batch_mean=0.000 model_exec=596 model_active=599 model_pub=599 model_load=599 model_counts=3/1 inf=512:109.5/201.2/300.1us
  TRANSITIONS batch run=5 ep=3 rows=128 bytes=123703 from=192.168.0.133:40378
  LEARNER rows=256 done=2 run=5 ep=3 atk=10/4/6 replay=256/256 skipped=0 rew=+2/-6/0248 timing=4/3/3 timing_rows=256 timing_done=2 timing_rew=+2/-6/0248 sources=remote:256 fallback_pct=0.00 timing_fallback_pct=0.00 ready=yes warmup=100 batch=32 batch_mean=0.000 model_exec=599 model_active=600 model_pub=600 model_load=600 model_counts=4/1 inf=512:95.7/189.2/939.6us
  ```

## 2026-04-24: Per-Timing Learner Summary For Sweep Comparison

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum

Files changed:
- `tools/rl_probe_server.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- make timing sweeps easier to compare when one learner log contains rows from multiple timing configurations

Implementation notes:
- learner log tailing now keeps a small aggregate bucket per timing tuple:
  - `(decision_delay_frames, decision_interval_frames, action_hold_frames)`
- each `LEARNER` line now reports for the latest timing tuple:
  - `timing_rows`
  - `timing_done`
  - `timing_rew=+/-/0`
  - `timing_fallback_pct`
- this is meant to support Milestone 6 timing sweeps without forcing a separate transition log file for every short experiment
- the overall `rows`, `rew`, `sources`, and `fallback_pct` fields still describe the full imported replay set

Validation:
- `python3 -m py_compile tools/rl_probe_server.py` pending.
- `git diff --check -- tools/rl_probe_server.py docs/plan-remote-rl-agent.md docs/remote-rl-agent-engineering-log.md` pending.

## 2026-04-24: Milestone 6 Timing-Tuning Telemetry Bring-Up

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum

Files changed:
- `src/rl/rl_session.c`
- `tools/rl_probe_server.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- make timing sweeps for `k / decision_interval_frames / action_hold_frames` traceable in transition data and learner logs before changing policy cadence itself

Implementation notes:
- transition NDJSON / episode-batch export now includes:
  - `decision_delay_frames`
  - `decision_interval_frames`
  - `action_hold_frames`
- `tools/rl_probe_server.py` now carries those timing fields into the learner-safe replay row metadata
- learner stats now print:
  - `timing=<k>/<decision_interval>/<action_hold>`
  - `fallback_pct=<percent>`
- this should make it much easier to compare runs after config changes without relying on separate handwritten notes
- this change does not yet alter runtime timing behavior; it only improves observability for the next Milestone 6 tuning passes

Validation:
- `python3 -m py_compile tools/rl_probe_server.py` passed.
- `git diff --check -- src/rl/rl_session.c tools/rl_probe_server.py docs/plan-remote-rl-agent.md docs/remote-rl-agent-engineering-log.md` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed.

## 2026-04-24: Transition Export Slimming For Runtime Smoothness

Milestone:
- Milestone 5: Async learner and model hot-swap / Milestone 6 prep

Files changed:
- `src/rl/rl_session.c`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- reduce live gameplay stutter by shrinking per-decision transition export work before attempting bigger control-timing changes

Implementation notes:
- `RLSession_FormatTransitionLogLine(...)` now exports a smaller learner-safe / validation-safe subset instead of the previous debug-heavy row
- removed from the serialized NDJSON / transition-batch payload:
  - character-name strings duplicated by character IDs
  - span-state booleans such as airborne / hit-stop / contact / damage-state flags
  - older requested/observed attack heuristics that the learner path does not currently ingest
  - overlay attack active/contact/whiff running counts
  - several attack-start / attack-code / airborne-start booleans that were mainly useful for early bring-up forensics
- kept in the serialized output:
  - run / episode / decision ids
  - frame ids
  - start/final HP
  - character IDs
  - model-version expected/requested/executed
  - requested / executed action wires and decoded executed action fields
  - compact HP / stun / position / facing-relative deltas
  - overlay attack finalized/contact/whiff flags
  - execution source, reward, done, and terminal reason
- `RLSession_FinalizeLedgerEntry(...)` no longer formats the same transition row twice; it now reuses the already-formatted line for both local append and episode-batch accumulation
- this change reduces both CPU formatting cost and TCP batch payload size, but it does not yet explain or fix the higher `neutral-fallback` rate from the latest run

Validation:
- `git diff --check -- src/rl/rl_session.c docs/plan-remote-rl-agent.md docs/remote-rl-agent-engineering-log.md tools/rl_probe_server.py` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed.

## 2026-04-24: Inference Latency Telemetry Precision Fix

Milestone:
- Milestone 5: Async learner and model hot-swap

Files changed:
- `tools/rl_probe_server.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- fix the probe server latency telemetry bug where `inf=` frequently collapsed to `0/0/16000us`, which made Milestone 5 latency evidence unreliable

Implementation notes:
- the probe server now measures OBS-to-action service time with `time.perf_counter_ns()` instead of `time.monotonic_ns()`
- `InferenceStats` now stores raw nanosecond samples instead of truncating to integer microseconds before aggregation
- learner stats still print microseconds, but now with one decimal place:
  - `inf=<count>:<p50_us>/<p95_us>/<max_us>us`
- this should preserve sub-millisecond variation and make it much easier to distinguish real Python-side service cost from occasional scheduler spikes

Validation:
- `python3 -m py_compile tools/rl_probe_server.py` pending.
- `git diff --check -- tools/rl_probe_server.py docs/plan-remote-rl-agent.md docs/remote-rl-agent-engineering-log.md` pending.

## 2026-04-24: Live Hot-Swap Execute-Path Confirmation

Milestone:
- Milestone 5: Async learner and model hot-swap

Files changed:
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- record the first live run where learner-published actor versions were observed catching up in executed transitions, not just in publish telemetry

Implementation notes:
- during live learner/inference testing, the probe server showed:
  - a temporary lag where `model_exec=346` while `model_active=model_pub=model_load=351`
  - a later catch-up where `MODEL published version=352` was followed by transition rows with `model_exec=352 model_active=352 model_pub=352 model_load=352`
- this is the strongest current evidence that the Milestone 5 hot-swap path is functioning end-to-end:
  - learner publishes new actor versions
  - the in-memory active actor updates
  - subsequent executed transitions report the new model version
- the same live run also showed:
  - `rows=3084`
  - `done=11`
  - `sources=neutral-fallback:1,remote:3083`
- these counts suggest transition upload and replay import are continuing normally and that fallback execution is now rare in the measured run
- `model_counts=39/1` indicates the active actor is usually updated directly by local learner publishes rather than by repeated background reloads from disk; this is acceptable for the current single-process learner/inference setup
- latency proof is still incomplete:
  - `inf=512:0/0/16000us` does not yet provide enough confidence to mark `Action latency stays stable during training` complete

Validation:
- Live log evidence observed with the current Windows-to-WSL learner command:
  ```text
  LEARNER rows=2742 done=10 run=3 ep=10 ... model_exec=346 model_active=351 model_pub=351 model_load=351 model_counts=38/1 inf=512:0/0/16000us
  MODEL published version=352 policy=hp source=learner
  TRANSITIONS batch run=3 ep=11 rows=342 bytes=645060 from=192.168.0.133:44936
  LEARNER rows=3084 done=11 run=3 ep=11 ... model_exec=352 model_active=352 model_pub=352 model_load=352 model_counts=39/1 inf=512:0/0/16000us
  ```
- Additional live evidence from the same run continued to show stable catch-up:
  ```text
  LEARNER rows=4603 done=16 run=3 ep=16 atk=271/217/54 replay=4603/4603 skipped=0 rew=+120/-119/04364 sources=neutral-fallback:1,remote:4602 ready=yes warmup=100 batch=32 batch_mean=1.000 model_exec=375 model_active=376 model_pub=376 model_load=376 model_counts=63/1 inf=512:0/0/16000us
  MODEL published version=377 policy=hp source=learner
  ```
- This later sample suggests the execute path is now usually within one published version of the active actor, which is consistent with a healthy publish-to-execute lag instead of a stuck hot-swap path.

## 2026-04-24: Learner And Actor Version Observability Tightening

Milestone:
- Milestone 5: Async learner and model hot-swap

Files changed:
- `tools/rl_probe_server.py`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- make Milestone 5 hot-swap validation easier by separating learner replay progress from actor publish/load/execute version telemetry in the probe-server stats line

Implementation notes:
- `ActorModelStore` now exposes a status snapshot with:
  - active actor version
  - last published version
  - last loaded version
  - publish count
  - load count
- learner stats now print:
  - `run`
  - `model_exec`
  - `model_active`
  - `model_pub`
  - `model_load`
  - `model_counts`
- this should make it obvious whether:
  - new transition batches are still arriving
  - learner publishes are advancing
  - the in-memory actor has switched
  - executed transitions are still coming from an older actor version

Validation:
- `python3 -m py_compile tools/rl_probe_server.py` passed.
- `git diff --check -- tools/rl_probe_server.py docs/remote-rl-agent-engineering-log.md` passed.
- Current live test command:
  ```sh
  python \\wsl.localhost\Ubuntu\home\olhua\src\3s-mister-arm\tools\rl_probe_server.py --host 0.0.0.0 --port 37330 --action-port 37331 --policy hp --policy-repeat-delay-ms 3000 --model-version 0 --model-dir \\wsl.localhost\Ubuntu\home\olhua\src\3s-mister-arm\model\rl-model-live --transition-log \\wsl.localhost\Ubuntu\home\olhua\src\3s-mister-arm\logs\rl-transitions-live.ndjson --learner-auto-publish --learner-publish-interval-sec 10 --learner-warmup-rows 100 --learner-batch-size 32
  ```

## 2026-04-24: HP-Zero Active-Round Control And Background Model Watch

Milestone:
- Milestone 5: Async learner and model hot-swap / Milestone 4 ledger correctness follow-up

Files changed:
- `src/rl/rl_session.c`
- `tools/rl_probe_server.py`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- keep remote input alive when visible HP reaches zero but the game has not yet ended the round, and remove model-manifest filesystem checks from the inference hot path

Implementation notes:
- RL input/observation gating now follows the game battle-active flags (`Allow_a_battle_f != 0 && Demo_Time_Stop == 0`) instead of requiring both players' raw HP to stay above zero
- HP reaching zero remains an observation/reward signal, but no longer directly stops remote input or finalizes the episode
- episode finalization now waits for the game to leave battle-active state, so it should align with the actual round conclusion instead of the first zero-HP frame
- `ActorModelStore.current()` now returns only the in-memory actor
- external `current.json` refresh checks moved to a background watcher thread, while learner publishes still update the in-memory actor immediately

Validation:
- `python3 -m py_compile tools/rl_probe_server.py` passed.
- `git diff --check -- src/rl/rl_session.c tools/rl_probe_server.py docs/remote-rl-agent-engineering-log.md` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed.
- Fresh hardware validation needed: confirm auto punch continues while `Allow_a_battle_f` is still active even if visible HP is zero, and confirm inference `p95/max` improves because OBS replies no longer touch the model directory.

## 2026-04-24: Fixed-Policy Repeat Delay And Model Refresh Throttle

Milestone:
- Milestone 5: Async learner and model hot-swap

Files changed:
- `tools/rl_probe_server.py`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- fix `--policy-repeat-delay-ms` being ignored by fixed policies such as `hp`, and reduce inference latency spikes caused by checking `current.json` on every observation packet

Implementation notes:
- fixed policies now share the same per `(nonce, run_id, episode_id, policy)` cooldown state as scripted policies
- `--policy hp --policy-repeat-delay-ms 3000` now emits one HP action, then neutral actions until the 3000 ms cooldown expires
- `ActorModelStore.current()` now throttles external `current.json` refresh checks to every 250 ms by default instead of every observation
- the refresh interval can be overridden with `RL_MODEL_REFRESH_INTERVAL_SEC`
- learner-side publishes still update the in-memory active actor immediately

Validation:
- `python3 -m py_compile tools/rl_probe_server.py` passed.
- `git diff --check -- tools/rl_probe_server.py docs/remote-rl-agent-engineering-log.md` passed.
- local policy smoke confirmed fixed `hp` emits `[64, 0, 64]` across a 200 ms cooldown.

## 2026-04-24: Learner Actor Manifest Publish And Hot-Swap Skeleton

Milestone:
- Milestone 5: Async learner and model hot-swap

Files changed:
- `tools/rl_probe_server.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- add a first versioned actor publication and atomic hot-swap path so the remote inference service can move from fixed `--model-version` stamping to learner-published actor versions

Implementation notes:
- added `ActorModelStore` to `tools/rl_probe_server.py`
- `--model-dir DIR` enables actor manifest storage:
  - `actor-vN.json` records immutable published actor metadata
  - `current.json` is updated through `os.replace()` for atomic hot-swap
- inference reads the current actor before each observation reply and stamps action packets with that actor's `version` and `policy`
- `--learner-auto-publish` lets the learner/log-reader publish a new actor manifest after replay warmup and every `--learner-publish-interval-sec`
- `--learner-publish-policy POLICY` can force the policy used by learner-published manifests; otherwise publishing keeps the active policy

Validation:
- `python3 -m py_compile tools/rl_probe_server.py` passed.
- `git diff --check -- tools/rl_probe_server.py docs/plan-remote-rl-agent.md docs/remote-rl-agent-engineering-log.md` passed.
- learner-only smoke with `--model-dir`, `--learner-auto-publish`, and existing `logs/rl-transitions.ndjson` ran under `timeout 3`; expected timeout exit `124` after publishing `actor-v0.json` through `actor-v5.json` and atomically updating `current.json`.
- Live MiSTer validation still needed: run the probe server with `--model-dir` and confirm RL overlay/logs show `model_version_executed` increasing after learner publication while observation replies continue.

## 2026-04-24: RL Round-Playable Episode Boundary Fix

Milestone:
- Milestone 5: Async learner and model hot-swap / Milestone 4 ledger correctness follow-up

Files changed:
- `src/rl/rl_session.c`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- fix fresh hardware logs where each episode began after the round HP was already terminal, causing the whole HP/reward delta to land on the final executed decision and adding one extra `was_executed=false` terminal row per round

Implementation notes:
- remote input override and observation send are now gated on a playable round:
  - `Allow_a_battle_f != 0`
  - `Demo_Time_Stop == 0`
  - both agent and opponent HP are above zero
- stale action packets received during non-playable round phases are rejected before they can initialize a new runtime episode
- terminal HP observations now finalize the active episode immediately at frame end, before the next frame can clear the ledger during KO / round-end flow
- unexecuted in-flight ledger entries are discarded at episode finalization instead of being exported as zero-reward terminal transitions

Validation:
- `git diff --check -- src/rl/rl_session.c docs/remote-rl-agent-engineering-log.md` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed.
- Fresh hardware validation still needed: run a 3-round match and confirm each episode starts at live HP, HP deltas appear before the terminal row when damage occurs mid-round, and no extra `was_executed=false` terminal row is emitted.

## 2026-04-24: Protocol v2 Run ID And Unique Round Episodes

Milestone:
- Milestone 5: Async learner and model hot-swap

Files changed:
- `src/rl/rl_protocol.h`
- `src/rl/rl_net.h`
- `src/rl/rl_net.c`
- `src/rl/rl_session.h`
- `src/rl/rl_session.c`
- `tools/rl_probe_server.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- make every round-scoped RL episode uniquely identifiable in `rl-transitions.ndjson`, remote action packets, and transition-batch uploads instead of reusing `Round_num` as `episode_id`

Implementation notes:
- bumped the RL observation/action/batch protocol to v2 while keeping the UDP hello/ping probe packet version at v1
- added `run_id` to:
  - `RLObsPacketHeader`
  - `RLActionPacket`
  - `RLTransitionBatchHeader`
  - `RLTransitionBatchAck`
- MiSTer now persists the last allocated run id in `logs/rl-run-state.txt`
- `episode_id` is now a per-run monotonic round rollout sequence
- transition NDJSON now exports:
  - `run_id`
  - unique per-run `episode_id`
  - game-facing `round_num`
- expected-decision, queued-action, seen-action, and decision-ledger lookups now key by `run_id` as well as `episode_id` / `decision_id`
- learner replay import now keeps `run_id` / `round_num` and dedupes by `(run_id, episode_id, decision_id)`
- transition-batch ACKs validate both `run_id` and `episode_id`

Validation:
- `python3 -m py_compile tools/rl_probe_server.py` passed.
- `git diff --check -- src/rl/rl_protocol.h src/rl/rl_net.h src/rl/rl_net.c src/rl/rl_session.h src/rl/rl_session.c tools/rl_probe_server.py` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed.

## 2026-04-24: Ledger HP Delta Recovery And Round Boundary Cleanup

Milestone:
- Milestone 5: Async learner and model hot-swap / Milestone 4 ledger correctness follow-up

Files changed:
- `src/rl/rl_observation.h`
- `src/rl/rl_observation.c`
- `src/rl/rl_session.c`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- fix transition rows where round win/loss rewards were present but every per-decision HP delta stayed zero, making training depend almost entirely on sparse terminal rewards

Implementation notes:
- `RLObservationV1` now carries raw `self_hp`, `opp_hp`, `self_hp_start`, and `opp_hp_start`
- ledger reward accumulation now derives HP deltas from cumulative round damage:
  - `self_damage_total = self_hp_start - self_hp`
  - `opp_damage_total = opp_hp_start - opp_hp`
  - each observation contributes the difference from the previous observed damage total
- transition rows now include diagnostic HP fields:
  - `start_self_hp`
  - `start_opp_hp`
  - `final_self_hp`
  - `final_opp_hp`
- round episode changes now key only off `Round_num` to avoid `PL_Wins` / `VS_Win_Record` updates creating empty skipped episode ids during round-end flow

Validation:
- `python3 -m py_compile tools/rl_probe_server.py` passed.
- `git diff --check -- src/rl/rl_observation.h src/rl/rl_observation.c src/rl/rl_session.c` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed.
- Needs hardware replay validation with a fresh `rl-transitions.ndjson` to confirm `hp_rows > 0` when visible HP damage occurs.

## 2026-04-23: Milestone 5 Episode Batch Transport

Milestone:
- Milestone 5: Async learner and model hot-swap

Files changed:
- `src/rl/rl_protocol.h`
- `src/rl/rl_net.h`
- `src/rl/rl_net.c`
- `src/rl/rl_session.c`
- `tools/rl_probe_server.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- replace manual transition-log copying with a first formal non-critical transport that uploads completed episode batches from MiSTer to the remote learner while keeping local NDJSON logging intact

Implementation notes:
- added `RLTransitionBatchHeader` / `RLTransitionBatchAck` protocol structs
- MiSTer now:
  - keeps local `rl-transitions.ndjson` append behavior unchanged
  - accumulates finalized NDJSON rows for the current episode in memory
  - queues the completed episode for background TCP upload on `obs_port + 2`
  - expects a per-episode ACK from the remote learner service
- transport work is kept off the action critical path by a background sender thread and a small pending queue in `src/rl/rl_net.c`
- `tools/rl_probe_server.py` now also hosts a TCP transition-batch listener:
  - appends received payloads into `--transition-log`
  - ACKs the batch after a successful append
  - defaults `--transition-port` to `--action-port + 1` when transition logging is enabled
- the earlier pull-mirror path remains available for smoke / fallback use, but the intended path is now direct episode-batch upload

Validation:
- `python3 -m py_compile tools/rl_probe_server.py` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed.
- local socket-level runtime smoke for the TCP listener could not be completed in this sandbox because local Python socket creation is denied with `PermissionError: [Errno 1] Operation not permitted`.

## 2026-04-23: Milestone 5 Transition Pull Mirror

Milestone:
- Milestone 5: Async learner and model hot-swap

Files changed:
- `tools/rl_probe_server.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- remove the manual-copy requirement for learner bring-up by letting the remote-side probe server mirror a MiSTer transition log into a local learner file on a non-critical background thread

Implementation notes:
- added a `TransitionPuller` background thread to `tools/rl_probe_server.py`
- the puller supports:
  - `--transition-pull-remote-path PATH` for read-only SCP polling from MiSTer using `MISTER_HOST`, `MISTER_USER`, and `MISTER_PASSWORD` defaults
  - `--transition-pull-local-source PATH` for local smoke tests of the same mirror/update path
- the puller writes into the local `--transition-log` path:
  - appends only the new suffix when the fetched file is a strict extension of the current mirror
  - rewrites the mirror if the source diverges, while the learner importer dedupes replay rows by `(episode_id, decision_id)`
- added `--learner-only` so the transition pull / replay import path can run without binding the UDP action server

Validation:
- `python3 -m py_compile tools/rl_probe_server.py` passed.
- local mirror smoke passed with:
  - `python3 tools/rl_probe_server.py --learner-only --transition-pull-local-source <source> --transition-log <mirror> --learner-tail-from-start --learner-stats-interval-sec 0.2 --transition-pull-interval-sec 0.2 --learner-warmup-rows 2 --learner-batch-size 1`
  - first pull imported one replay row
  - appending a second row to the source produced:
    - `PULLER updated local mirror pulls=2`
    - `replay=2/2`
    - `done=1`
    - `ready=yes`

## 2026-04-23: Milestone 5 Replay Buffer Import Skeleton

Milestone:
- Milestone 5: Async learner and model hot-swap

Files changed:
- `tools/rl_probe_server.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- move the learner skeleton from "tail transition logs and print counters" to "import a learner-safe replay subset and report replay readiness" without adding real training yet

Implementation notes:
- added a fixed-capacity in-memory replay buffer to `tools/rl_probe_server.py`
- added `learner_replay_row(...)` to import only the current learner-safe subset:
  - executed action fields
  - reward / done / terminal fields
  - compact HP / stun / movement deltas
  - overlay attack auxiliary labels
  - character IDs and executed model version as metadata
- rows with `was_executed != true` are skipped during replay import
- learner stats now report:
  - replay size and imported row count
  - skipped unexecuted rows
  - positive / negative / zero reward counts
  - execution-source mix
  - warmup readiness and sampled batch mean reward
- added CLI knobs:
  - `--replay-capacity`
  - `--learner-batch-size`
  - `--learner-warmup-rows`

Validation:
- `python3 -m py_compile tools/rl_probe_server.py` passed.
- `python3 tools/rl_probe_server.py --transition-log logs/rl-transitions.ndjson --learner-tail-from-start --learner-stats-interval-sec 0.2 --learner-warmup-rows 10 --learner-batch-size 8 --port 0` printed stable learner stats with:
  - `rows=4423`
  - `replay=4420/4420`
  - `skipped=3`
  - `sources=remote:3173,repeated-last-action:1247`
  - `ready=yes`
  - `model=12`

## 2026-04-23: First Learner Replay Subset And Reward Notes

Milestone:
- Milestone 5 follow-up planning / Milestone 6 preparation

Files changed:
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- document which transition fields are learner-safe for a first replay-buffer import and clarify how the current HP-based reward is expected to teach defense only through delayed credit

Implementation notes:
- recorded a first learner whitelist centered on:
  - executed action fields
  - reward / done / terminal fields
  - HP / stun / movement deltas
  - character IDs and executed model version as metadata
- explicitly marked requested-action heuristics, observed attack-state fields, and cumulative overlay counters as debug / analysis-only for the first learner import
- clarified that:
  - `reward_accum` remains `delta_opp_hp - delta_self_hp` plus round win/loss bonus
  - defense and avoidance are expected to arrive through long-horizon credit rather than a dedicated v1 defensive label
  - `overlay_attack_*` fields remain auxiliary labels until move-family validation proves they are learner-safe across normals, specials, projectiles, throws, and multistage moves

Validation:
- reviewed the updated learner-field and reward notes against the existing Milestone 4 closeout notes and current `src/rl/rl_session.c` reward / ledger export logic

## 2026-04-23: Milestone 5 Model Version Plumbing

Milestone:
- Milestone 5: Async learner and model hot-swap

Files changed:
- `src/rl/rl_session.h`
- `src/rl/rl_session.c`
- `src/rl/rl_observation.c`
- `tools/rl_probe_server.py`
- `docs/config.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- make model versions visible in packets, overlay, and transition logs before adding learner hot-swap machinery

Implementation notes:
- MiSTer now sends `RLObsPacketHeader.model_version_expected` from the currently executed remote model version
- accepted remote action packets store `RLActionPacket.model_version` in the queue and ledger
- transition NDJSON now exports:
  - `model_version_expected`
  - `model_version_requested`
  - `model_version_executed`
- RL net overlay shows current model version as `MV`
- `tools/rl_probe_server.py --model-version N` stamps fixed-policy action packets for bring-up

Validation:
- `python3 -m py_compile tools/rl_probe_server.py` passed.
- `git diff --check` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed.

## 2026-04-23: Milestone 5 Async Learner Skeleton

Milestone:
- Milestone 5: Async learner and model hot-swap

Files changed:
- `tools/rl_probe_server.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- split the remote-side critical inference path from slower learner/log processing before adding real training or hot-swap

Implementation notes:
- `tools/rl_probe_server.py` now keeps UDP observation handling and action replies on the main thread
- optional `--transition-log PATH` starts a daemon learner/log-reader thread that tails local transition NDJSON
- the learner/log reader reports:
  - transition rows and done count
  - latest episode
  - attack event/contact/whiff counts
  - latest executed model version
  - inference response latency samples as `count:p50/p95/maxus`
- `--learner-tail-from-start` imports an existing file from the beginning; default behavior tails only new rows
- this is intentionally a skeleton: it proves non-critical learner work can run beside inference, but it does not train or hot-swap weights yet

Validation:
- `python3 -m py_compile tools/rl_probe_server.py` passed.
- local UDP bind / learner-tail smoke passed with `/tmp/rl-transitions-smoke.ndjson`, reporting `rows=2 done=1 ep=1 atk=2/1/1 model=12`
- `git diff --check` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed.

## 2026-04-23: Probe Scripted Move Policies

Milestone:
- Milestone 5: Async learner and model hot-swap

Files changed:
- `tools/rl_probe_server.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- add deterministic special/throw action scripts for validating command input, contact, whiff, and future outcome labeling

Implementation notes:
- added `--policy ryu-fireball`, which loops:
  - `DOWN`
  - `DOWN_FORWARD`
  - `FORWARD`
  - `FORWARD + LP`
  - neutral recovery frames
- added `--policy throw`, which loops:
  - `FORWARD + LP + LK`
  - neutral recovery frames
- added `--policy tatsu`, which loops:
  - `DOWN`
  - `DOWN_BACK`
  - `BACK`
  - `BACK + LK`
  - neutral recovery frames
- added `--policy shoryuken`, which loops:
  - `FORWARD`
  - `DOWN`
  - `DOWN_FORWARD`
  - `DOWN_FORWARD + HP`
  - neutral recovery frames
- added `--policy-repeat-delay-ms N`, which holds neutral after each scripted policy loop before repeating
- scripted policies use the existing relative-movement action wire, so MiSTer still maps forward/back/down-forward/down-back at execution time based on current facing

Validation:
- `python3 -m py_compile tools/rl_probe_server.py` passed.
- `git diff --check` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed.

## 2026-04-23: Character Identity in Transition Ledger

Milestone:
- Milestone 4 closeout / Milestone 5 preparation

Files changed:
- `src/rl/rl_session.c`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- make transition rows self-describing for matchup-aware learner import

Implementation notes:
- each transition NDJSON row now includes:
  - `agent_character_id`
  - `agent_character_name`
  - `opponent_character_id`
  - `opponent_character_name`
- character IDs are captured from runtime `My_char[self/opp]` when the decision ledger entry is created
- learner import should use the ID fields as canonical and names as debug metadata

Validation:
- `git diff --check` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed.

## 2026-04-23: Event-Aligned Attack Outcomes in Ledger

Milestone:
- Milestone 4: Decision ledger and transition logging

Files changed:
- `src/rl/rl_session.c`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- align transition ledger attack contact / whiff accounting with the verified RL outcome overlay counters

Implementation notes:
- transition NDJSON now exports event-level overlay outcome fields:
  - `overlay_attack_event_finalized`
  - `overlay_attack_contact`
  - `overlay_attack_whiff`
  - `overlay_attack_active_count`
  - `overlay_attack_contact_count`
  - `overlay_attack_whiff_count`
- only the first exported transition after an attack event finalizes gets `overlay_attack_event_finalized=1`, so jq counting should filter on that flag to avoid duplicate counts
- the older `requested_attack_made_contact` / `requested_attack_likely_whiffed` decision-window heuristics remain in the log for comparison, but the event-level overlay fields are the preferred bring-up counters now

Validation:
- `git diff --check` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed.
- Hardware ledger/overlay closeout passed with the sampled window:
  - `rows=274`
  - `overlay_attack_events=23`
  - `overlay_attack_contacts=3`
  - `overlay_attack_whiffs=20`
  - `last_ah=23`
  - `last_acc=3`
  - `last_awc=20`
  - ledger event totals matched the RL Outcome overlay counters

Status:
- Milestone 4 is closed.
- Remaining refinement items are intentionally deferred to later schema/learner work:
  - split `contact` into hit / blocked / throw when we need richer reward shaping
  - decide whether the older decision-window `requested_attack_*` heuristics should be removed after replay-buffer import lands
  - make model/version fields part of Milestone 5 logs and packets

## 2026-04-23: Outcome Overlay Attack Counters

Milestone:
- Milestone 4: Decision ledger and transition logging

Files changed:
- `src/rl/rl_observation.c`
- `src/rl/rl_session.h`
- `src/rl/rl_session.c`
- `docs/config.md`

Purpose:
- make on-screen RL debug easier to compare against visible gameplay by adding per-round accumulated attack-start / contact / whiff counters

Implementation notes:
- added round-episode counters to `RLRemoteDebugState`:
  - `episode_attack_active_count`
  - `episode_attack_contact_count`
  - `episode_attack_whiff_count`
- these counters now finalize per overlay attack event instead of per exported transition:
  - `ACC` increments when the finalized event saw contact
  - `AWC` increments when the finalized event ended as a likely whiff
  - `AH` increments once per finalized attack event
- counters reset on remote runtime reset and on round/episode rollover
- outcome overlay now adds:
  - `AH`: accumulated real attack starts this round
  - `ACC`: accumulated contacts this round
  - `AWC`: accumulated likely whiffs this round
  - `AC` / `AW`: last finalized overlay attack event outcome, aligned with the accumulated counters rather than the raw ledger heuristics

Validation:
- `git diff --check` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed.

## 2026-04-23: Milestone 4 Attack Activation Refinement

Milestone:
- Milestone 4: Decision ledger and transition logging

Files changed:
- `src/rl/rl_observation.h`
- `src/rl/rl_observation.c`
- `src/rl/rl_session.h`
- `src/rl/rl_session.c`
- `docs/config.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- separate raw attack-button pulses from the smaller set of decisions that actually become a new in-game attack, so whiff/contact counts line up better with observed gameplay

Implementation notes:
- added runtime edge fields for both attack-routine and attack-counter bring-up:
  - `self_attack_routine_started`
  - `opp_attack_routine_started`
  - `self_attack_counter_started`
  - `opp_attack_counter_started`
- transition logs now also export:
  - `requested_attack_became_active`
  - `observed_attack_counter_started`
- `requested_attack_became_active` is now driven by the defender-side `Attack_Counter` edge and is the preferred first-pass count for "real punches/kicks actually started"
- `requested_attack_likely_whiffed` now keys off `requested_attack_became_active && !requested_attack_made_contact` instead of the broader `current_attack != 0` state-seen flag
- RL outcome overlay now shows `AR` so runtime bring-up can distinguish:
  - `AI`: input pulse sent
  - `AR`: attack counter actually advanced
  - `OS`: older `current_attack`-derived debug signals plus attack-counter edge

Validation:
- `git diff --check` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed.

Follow-up:
- retest `--policy hp` and compare `requested_attack_became_active` against visible punch count

## 2026-04-23: Human-Opponent Remote Policy Routing

Milestone:
- Milestone 3: Remote inference only

Files changed:
- `src/rl/rl_session.c`
- `docs/config.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- let `P1H` / `P2H` use the same remote-policy inference path as CPU-opponent sessions so human-opponent testing and debug runs stay on the real network/action pipeline

Implementation notes:
- `RLSession_RemoteControlEnabled()` no longer disables the remote path just because `human_opponent` is enabled
- when `rl-opponent-mode = human`:
  - `rl-network = on` now uses remote action queue/execution
  - `rl-network = off` still uses the old scripted movement helper for Milestone 0B validation
- guarded the older scripted/local-fake helpers so they do not run when the remote path is active
- this keeps `P1H` / `P2H` labels accurate while making them more useful for controlled remote debugging

Validation:
- `git diff --check` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed.

Follow-up:
- hardware-test `P1H` / `P2H` with `rl-network = on` and confirm `OBS/Q/EX` advance normally while the opponent side remains human-controlled

## 2026-04-23: Milestone 4 Attack Outcome Semantics Refinement

Milestone:
- Milestone 4: Decision ledger and transition logging

Files changed:
- `src/rl/rl_observation.h`
- `src/rl/rl_observation.c`
- `src/rl/rl_session.h`
- `src/rl/rl_session.c`
- `docs/config.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- separate "RL actually sent an attack input pulse" from "the game runtime observed an attack-state edge" so transition logs can be used for learner/debug analysis without over- or under-counting attacks

Implementation notes:
- added `requested_attack_input_started` to transition logs; it is true when the executed decision contains nonzero attack bits
- added observed runtime fields:
  - `observed_attack_state_started`
  - `observed_attack_code_changed`
  - `self_attack_code_changed` / `opp_attack_code_changed`
- `observed_attack_state_started` remains the strict `current_attack: 0 -> nonzero` edge, which explains why it can be much lower than the number of HP decisions when `current_attack` stays nonzero
- `observed_attack_code_changed` captures nonzero runtime attack-code changes and is useful for diagnosing engine semantics, but it is not the source of truth for input attempts
- removed the temporary `requested_attack_started` alias so the schema now has one canonical input-attempt field
- RL outcome overlay now shows `AI`, `OS`, `AC`, and `AW` instead of the older compact `ASstarted/state/contact/whiff` grouping

Validation:
- `git diff --check` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed.

Follow-up:
- hardware-test `--policy hp` and count `requested_attack_input_started` versus `observed_attack_state_started` / `observed_attack_code_changed`

## 2026-04-22: Milestone 3 Remote Queue And Execution MVP

Milestone:
- Milestone 3: Remote inference only

Files changed:
- `src/rl/rl_protocol.h`
- `src/rl/rl_net.h`
- `src/rl/rl_net.c`
- `src/rl/rl_session.h`
- `src/rl/rl_session.c`
- `src/rl/rl_observation.c`
- `tools/rl_probe_server.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- move Milestone 3 from packet counting into the first real remote control loop
- queue accepted remote actions by `target_frame` and execute them through the existing raw-input override path

Implementation notes:
- added a packed `RLObsPacketHeader` for the first decision-frame observation send path
- MiSTer now sends an observation header every `decision_interval_frames` once hello/ack is accepted
- `src/rl/rl_session.c` now owns a small pending action queue plus a small in-flight expectation table keyed by `(episode_id, decision_id, target_frame)`
- accepted `RLActionPacket` now flows through:
  - Milestone 2 session gate in `src/rl/rl_net.c`
  - minimal expectation-table match in `src/rl/rl_session.c`
  - pending queue insertion by `target_frame`
  - execution on the intended frame through `p1sw_buff/p2sw_buff`
- added a first fallback policy:
  - if a due expected target frame has no valid queued action, reuse the last executed remote action for `action_hold_frames`
- extended `RL Debug` with Milestone 3 counters:
  - `OBS`, `Q`, `EX`, `LT`, `DU`, `TM`, `FB`
- extended `tools/rl_probe_server.py` so it can receive Milestone 3 observation headers and reply with a fixed action policy while still preserving the Milestone 2 gate-test modes

Validation:
- `python3 -c "import ast, pathlib; ast.parse(pathlib.Path('tools/rl_probe_server.py').read_text())"` passed.
- `git diff --check` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed.

Follow-up:
- run MiSTer-side validation for fixed remote actions and confirm `OBS/Q/EX` move together on hardware
- separate real duplicate-rule handling from queue-capacity fallback once the first hardware run is in
- keep the full decision ledger / transition logging work for Milestone 4

Update after hardware retest:
- MiSTer hardware produced stable packet flow with:
  - `OBS891 Q1/890 EX886 LT1 DU0 TM0 FB1`
- `--policy hp` exposed one MVP behavior bug:
  - the overlay showed HP pressed, but the character often did not punch because remote attack bits were held for the full `action_hold_frames` window instead of producing a one-frame press edge
- fixed in `src/rl/rl_session.c`:
  - movement bits still hold for `action_hold_frames`
  - attack bits now pulse for one frame only
- hardware retest confirmed `--policy hp` now produces visible punches as expected

Further Milestone 3 closeout work:
- duplicate-rule handling now persists a small seen-decision table in `src/rl/rl_session.c`
- first accepted `(episode_id, decision_id, target_frame)` is remembered even after execution/fallback
- later packets with the same tuple are now counted as `DU`
- later packets with the same `(episode_id, decision_id)` but a different `target_frame` are now counted as `TM`
- `tools/rl_probe_server.py` gained:
  - `--obs-reply-mode normal`
  - `--obs-reply-mode duplicate`
  - `--obs-reply-mode wrong-target`
  so MiSTer-side `DU/TM` counters can be validated deterministically on hardware

Milestone 3 closeout:
- hardware validation also confirmed delayed relative `forward/back` behavior remains correct across side switches
- Milestone 3 is now considered complete

## 2026-04-22: Milestone 4 Decision Ledger And Transition Export MVP

Milestone:
- Milestone 4: Decision ledger and transition logging

Files changed:
- `src/rl/rl_session.h`
- `src/rl/rl_session.c`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- make the remote control loop trainable by recording what was requested, what actually executed, and what reward span that executed decision accrued

Implementation notes:
- added a fixed-size decision ledger keyed by `(episode_id, decision_id)` in `src/rl/rl_session.c`
- ledger entries are created when MiSTer sends an observation header
- when an action packet arrives, the ledger entry records `requested_action_wire`
- when the decision becomes active, the ledger entry records:
  - `executed_action_wire`
  - `execution_frame_actual`
  - `execution_source`
  - decoded `executed_move_intent`
  - decoded `executed_attack_bits`
- exported transitions now also include:
  - decoded `requested_move_intent`
  - decoded `requested_attack_bits`
  - `was_executed`
  - `terminal_reason`
- reward now accumulates onto the currently active ledger entry using:
  - per-frame `delta_opp_hp - delta_self_hp`
  - plus `+100/-100` round result bonus at episode closeout
- round changes now finalize the previous episode's ledger entries with `done=true`
- transitions are exported as NDJSON to `logs/rl-transitions.ndjson` under `Paths_GetPrefPath()`

Validation:
- `git diff --check` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed.

Follow-up:
- run a short MiSTer session and inspect `rl-transitions.ndjson`
- revisit richer event-delta fields from the Human-Fighter Observer Gap Review
- add remote-side transition transport after the local ledger output is validated

## 2026-04-22: Milestone 4 First-Pass Action Outcome And Event Delta Fields

Milestone:
- Milestone 4: Decision ledger and transition logging

Files changed:
- `src/rl/rl_observation.h`
- `src/rl/rl_observation.c`
- `src/rl/rl_session.c`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- make the local observer and exported transitions more useful for training by adding first-pass action-outcome and event-delta signals that are already derivable from stable runtime state

Implementation notes:
- `RLObservationV1` now includes per-frame derived fields for:
  - HP delta
  - X/Y delta
  - stun delta
  - airborne
  - entered hit-stop
  - entered contact state
  - entered damage state
- the transition ledger now accumulates and exports decision-span aggregates for:
  - HP delta
  - stun delta
  - self / opponent X and Y movement
  - airborne-seen flags
  - entered hit-stop / contact / damage flags
- kept the derivation conservative:
  - airborne uses `position_y != 0`
  - contact state uses `guard_flag != 0 || hit_stop`
  - damage state uses HP loss or stun increase
- moved the aggregation source to `RLObservation_OnFrameEnd()` so the ledger records post-logic frame results rather than pre-logic input staging
- explicitly deferred crouching and richer action-phase labels until a more trustworthy runtime source is identified

Validation:
- `git diff --check` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed.

Follow-up:
- verify the new `DH/DS/AB/EH/EC/ED` RL debug overlay lines on MiSTer
- inspect `rl-transitions.ndjson` for the new delta / event fields during hit, block, jump, and whiff cases
- revisit explicit `hit / blocked / whiff / throw` outcome enums in a later Milestone 4 refinement

## 2026-04-23: Milestone 4 Relative Movement And Request Outcome Fields

Milestone:
- Milestone 4: Decision ledger and transition logging

Files changed:
- `src/rl/rl_observation.h`
- `src/rl/rl_observation.c`
- `src/rl/rl_session.h`
- `src/rl/rl_session.c`
- `src/port/config/config.h`
- `src/port/config/config.c`
- `src/port/sdl/sdl_app.c`
- `vendor/Menu_MiSTer/menu.sv`
- `vendor/Main_MiSTer/thirdsarm_wrapper.cpp`
- `docs/config.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- make transition records easier for the learner to consume by adding facing-relative movement and first-pass requested-action outcome fields

Implementation notes:
- added opponent facing to `RLObservationV1` so opponent movement can also be converted into facing-relative motion
- transition logs now include:
  - `delta_self_forward`
  - `delta_opp_forward`
  - `requested_movement_succeeded`
  - `requested_attack_entered_state`
  - `requested_attack_made_contact`
  - `requested_attack_likely_whiffed`
  - `requested_attack_input_started`
  - `observed_attack_state_started`
  - `observed_attack_code_changed`
  - `requested_jump_started`
  - `self_attack_started` / `opp_attack_started`
  - `self_attack_code_changed` / `opp_attack_code_changed`
  - `self_airborne_started` / `opp_airborne_started`
- RL debug overlay now includes a compact outcome line:
  - `RFself/opp`
  - `MS`
  - `AI`
  - `OSstate/code`
  - `AC`
  - `AW`
  - `J`
- documented that:
  - world X/Y deltas remain signed world-coordinate deltas
  - forward deltas are facing-relative
  - stun deltas are signed and can be negative when stun recovers
  - contact state is conservative and not a precise hit/block enum
  - unexecuted terminal entries should usually be filtered by the first replay buffer
- `rl-transitions.ndjson` is still an evolving debug/training schema
- attack and airborne edge fields were added so match-level analysis can count starts instead of counting all decision windows that merely saw an attack/airborne state
- added `rl-debug-view` and the MiSTer OSD `RL Debug View` selector:
  - `Off`
  - `All`
  - `Net`
  - `Input`
  - `Fight`
  - `Outcome`
- switching `RL Debug View` persists `rl-debug-view` and signals the runtime to reread overlay settings
- the colored key row now appears only in `All` and `Input` views

Validation:
- `git diff --check` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed.
- `/home/olhua/src/3s-mister-arm/tools/mister-wrapper/build-hps.sh` passed.

Follow-up:
- verify `forward` produces nonzero `delta_self_forward` and `requested_movement_succeeded=1`
- verify `hp` produces attack entered/contact/whiff outcomes in plausible cases
- defer precise `hit / blocked / whiff / throw` enums until the hitcheck and throw paths are decoded more confidently

## 2026-04-22: Milestone 2 Action Session Gate

Milestone:
- Milestone 2: Session handshake, network probe, and delay budget

Files changed:
- `src/rl/rl_protocol.h`
- `src/rl/rl_net.h`
- `src/rl/rl_net.c`
- `src/rl/rl_observation.c`
- `src/args.c`
- `tools/rl_probe_server.py`
- `docs/config.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- finish the remaining Milestone 2 session-protection work for future action packets
- reject unacknowledged or stale-session action traffic before Milestone 3 queue/execution begins

Implementation notes:
- added `RLActionPacket` to `src/rl/rl_protocol.h`
- MiSTer now binds a local non-blocking UDP action socket on `rl-agent-action-port`
- action packets are counted and gated by:
  - valid magic/version
  - hello/ack accepted
  - matching live `session_nonce`
- accepted action packets are counted as gate-passed only; they are intentionally not queued or executed yet
- added counters to `RL Debug`:
  - `ACT`, `OK`, `UA`, `SN`, `BV`, `BM`
- extended `tools/rl_probe_server.py` with:
  - `--action-port`
  - `--action-mode valid`
  - `--action-mode stale`
  - `--action-mode pre-ack`
  so MiSTer-side gate behavior can be validated from one tool

Validation:
- `git diff --check` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed.
- `python3 -c "import ast, pathlib; ast.parse(pathlib.Path('tools/rl_probe_server.py').read_text())"` passed.

Follow-up:
- Milestone 2 gate work is complete.
- Milestone 3 should start with queueing accepted action packets by `target_frame` instead of only counting them.

## 2026-04-22: Milestone 2 Target-Network Timing Baseline

Milestone:
- Milestone 2: Session handshake, network probe, and delay budget

Files changed:
- `src/rl/rl_protocol.c`
- `src/port/config/config.c`
- `src/main.c`
- `docs/config.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- record the first real MiSTer <-> remote PC RTT measurement
- stop treating `k / decision_interval / action_hold` as placeholders

Implementation notes:
- measured on the actual MiSTer + Windows probe path using the `RL Debug` overlay:
  - `NETOK S128 P16819/17568/20752 MAX30718`
  - `p50 = 16819us`
  - `p95 = 17568us`
  - `p99 = 20752us`
  - `max = 30718us`
- one frame at 60fps is about `16667us`, so this path sits around one frame at p50 and can burst toward two frames at the max sample.
- selected the first conservative baseline as:
  - `candidate_k_delay_frames = 4`
  - `decision_interval_frames = 4`
  - `action_hold_frames = 4`
- updated runtime defaults so config-generated and protocol-default timing now match the chosen baseline.

Validation:
- MiSTer runtime probe reached `NETOK` and accumulated 128 samples on the actual target network.
- `git diff --check` pending local re-run after this doc/default sync.

Follow-up:
- Milestone 2 timing baseline is now fixed and ready for Milestone 3
- use `4/4/4` as the Milestone 3 starting point unless new measurements on the target network meaningfully change

## 2026-04-22: Milestone 2 OSD Network Toggle

Milestone:
- Milestone 2: Session handshake, network probe, and delay budget

Files changed:
- `vendor/Menu_MiSTer/menu.sv`
- `vendor/Main_MiSTer/thirdsarm_wrapper.cpp`
- `src/configuration.h`
- `src/args.c`
- `src/main.c`
- `src/port/config/config.h`
- `src/port/config/config.c`
- `src/rl/rl_net.c`
- `docs/config.md`
- `docs/plan-remote-rl-agent.md`

Purpose:
- put the RL network probe enable/disable control in MiSTer OSD
- keep remote IP, obs/action ports, and timing knobs in `games/3s-arm/config` for easy manual editing

Implementation notes:
- added OSD `RL Settings -> RL Network (Restart), Off/On`
- wrapper persists that menu item as `rl-network = off|on`
- wrapper strips forwarded RL network CLI/config knobs and injects only `--rl-network` from the persisted setting, keeping the config file authoritative for IP/ports/timing
- runtime now requires all three conditions before opening a UDP socket:
  - `--rl-agent` / RL agent mode active
  - `rl-network = on` / `--rl-network`
  - `rl-agent-remote-ip` / `--rl-remote-ip` is set
- `rl-agent-remote-ip`, `rl-agent-obs-port`, `rl-agent-action-port`, `rl-agent-delay-frames`, `rl-agent-decision-interval`, and `rl-agent-action-hold` are read from config after `Config_Init()`

Validation:
- `git diff --check` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed.
- `/home/olhua/src/3s-mister-arm/tools/mister-wrapper/build-hps.sh` passed and produced `build/mister-wrapper-hps/MiSTer_3S-ARM`.
- FPGA wrapper core / `.rbf` rebuild is still required before `RL Network (Restart)` appears on MiSTer OSD hardware.

Follow-up:
- rebuild wrapper/core so the new `CONF_STR` entry appears on MiSTer OSD
- on hardware, verify `RL Network (Restart)` writes `rl-network = on/off` and that `RL Debug` stays `NETOFF` until network is on plus a remote IP is configured

## 2026-04-22: Milestone 2 UDP Probe Path

Milestone:
- Milestone 2: Session handshake, network probe, and delay budget

Files changed:
- `src/rl/rl_net.h`
- `src/rl/rl_net.c`
- `src/rl/rl_observation.c`
- `src/configuration.h`
- `src/args.c`
- `src/main.c`
- `src/port/config/config.h`
- `src/port/config/config.c`
- `tools/rl_probe_server.py`
- `docs/config.md`
- `docs/plan-remote-rl-agent.md`

Purpose:
- add the first live remote RL transport probe without changing gameplay input behavior
- make target-network RTT/jitter visible in `RL Debug`

Implementation notes:
- RL UDP probe is default-off.
- It opens a socket only when RL agent mode is enabled and `rl-agent-remote-ip` / `--rl-remote-ip` is set.
- MiSTer sends `HELLO`, accepts matching `ACK`, then sends periodic `PING` packets and records matching `PONG` RTT samples.
- `RL Debug` now shows `NETOFF`, `NETHELLO`, `NETOK`, or `NETERR`, plus sample count, p50/p95/p99/max RTT, and error count.
- `tools/rl_probe_server.py` is the matching minimal remote-side UDP ACK/PONG responder.
- `rl-agent-obs-port`, `rl-agent-action-port`, `rl-agent-delay-frames`, `rl-agent-decision-interval`, and `rl-agent-action-hold` are now config/CLI backed. The action port is reserved for the later action packet path.

Validation:
- `tools/mister/build-game.sh --flavor telemetry` passed.
- `git diff --check` passed.
- `python3 -c "import ast, pathlib; ast.parse(pathlib.Path('tools/rl_probe_server.py').read_text())"` passed.
- Local UDP smoke test passed with `tools/rl_probe_server.py` bound to `127.0.0.1:37330` and a small Python client confirming:
  - `HELLO` receives `ACK`
  - `PING` receives `PONG`
  - `PONG` preserves the original ping timestamp for RTT measurement

Follow-up:
- run the probe on the actual MiSTer + remote PC network
- record p50/p95/p99/max RTT after at least 128 samples
- choose `candidate_k_delay_frames`, `decision_interval_frames`, and `action_hold_frames` from the recorded target-network data
- then connect the action queue / stale nonce rejection path

Primary plan:

- `docs/plan-remote-rl-agent.md`

Current branch policy:

- keep upstream baseline branches clean
- implement RL work on the local work branch only
- keep RL implementation independent from `src/netplay/*`

Project rules:

- `AGENTS.md`
- `docs/agent-memory/remote-rl-agent-rules.md`

## How To Use This Log

- Add one work-session entry whenever code, config, protocol, or deployment behavior changes.
- Link each entry to the relevant milestone from `docs/plan-remote-rl-agent.md`.
- Record exact commands, build artifacts, MiSTer deploy paths, and observed behavior.
- Record failed attempts too; they are useful for avoiding repeated debugging.
- Keep milestone checkboxes in the plan as the high-level tracker.
- Keep this file as the detailed implementation journal.

## Current Status

Last updated: 2026-04-24

- [x] Milestone 0A: Baseline match-flow confirmation spike
- [x] Milestone 0B: Facing and remap validation micro-spike
- [x] Milestone 0C: Local fake agent spike
- [x] Milestone 1: Compact observation builder
- [x] Milestone 2: Session handshake, network probe, and delay budget
- [x] Milestone 3: Remote inference only
- [x] Milestone 4: Decision ledger and transition logging
- [ ] Milestone 5: Async learner and model hot-swap
- [ ] Milestone 6: Higher-control-rate policy and curriculum

Current read:

- Milestone 5 is active.
- Implemented Milestone 5 slices include protocol v2 run identity, unique round episode ids, model-version packet/log plumbing, learner-safe replay import, transition pull mirroring, and non-critical episode-batch upload.
- Remaining Milestone 5 work is real versioned actor publication, atomic actor hot-swap, and latency validation while learner updates are active.

## Decision Log

### 2026-04-21: Keep RL Agent Independent From Netplay

Status:

- accepted

Decision:

- implement the remote RL agent as a local input provider plus observation exporter
- keep implementation under `src/rl/*`
- do not implement RL transport or scheduling inside `src/netplay/*`
- do not treat the remote PC as a Gekko or P2P netplay peer
- use `MODE_VERSUS + rl_session_active` as the v1 baseline match flow

Reason:

- upstream may later implement or rewrite P2P netplay
- isolating RL code keeps future upstream merges smaller and safer
- the RL architecture is authoritative MiSTer simulation plus remote inference, not peer-to-peer rollback

Follow-up:

- keep shared-file edits limited to small hook calls
- use neutral modules only if a helper must be shared with future upstream netplay

### 2026-04-21: Use Relative-Direction Wire Mode

Status:

- accepted

Decision:

- remote sends `action_wire` with a relative movement subfield and final attack/button bits
- MiSTer remaps relative movement into raw directional `SWKey` bits at execution time
- MiSTer does not own macro expansion or semantic policy interpretation

Reason:

- action decisions are delayed from `obs_frame` to `target_frame`
- characters may switch sides during that delay
- absolute `LEFT` / `RIGHT` actions can invert the intended forward/back meaning

Follow-up:

- Milestone 0B must verify `rl_flag`, forward/back remap, delayed side-switch behavior, and fallback remap behavior

### 2026-04-21: Round-Scoped Episodes

Status:

- accepted

Decision:

- v1 uses one round as one `episode_id`
- match progress remains observation context through `round_num`, `self_round_wins`, and `opp_round_wins`
- `frame_id` remains session-wide monotonic across episode resets

Reason:

- round boundaries reset key fighting state and simplify queue, ledger, and recurrent-state reset behavior

Follow-up:

- transition logs must preserve enough match context to analyze multi-round behavior later

## Work Sessions

### 2026-04-21: Planning And Tracking Setup

Milestones:

- Milestone 0A through Milestone 6 planning

Changes:

- created remote RL agent implementation plan
- converted milestones into a tracking checklist
- added this engineering log

Notes:

- implementation has not started yet
- first implementation step should be Milestone 0A

Commands:

```sh
# No build or test commands run for this documentation-only setup.
```

Results:

- plan exists at `docs/plan-remote-rl-agent.md`
- engineering log exists at `docs/remote-rl-agent-engineering-log.md`

### 2026-04-21: Added Remote RL Agent Project Rules

Milestones:

- Project workflow setup

Changes:

- added `docs/agent-memory/remote-rl-agent-rules.md`
- updated `AGENTS.md` to require loading the remote RL agent rules for RL-related sessions
- linked the engineering log to the project rules

Notes:

- new sessions should read the plan, checklist, engineering log, and project rules before implementation
- future code changes should state purpose, expected effect, risks, planned files, and validation before editing
- after code changes, update the plan checklist and engineering log, then commit code and related docs together unless explicitly told not to commit

Commands:

```sh
# No build or test commands run for this documentation-only workflow update.
```

Results:

- project rules exist at `docs/agent-memory/remote-rl-agent-rules.md`
- root agent instructions now point to the remote RL agent rules

### 2026-04-21: Milestone 0A Operator Setup Hook

Milestones:

- Milestone 0A: Baseline match-flow confirmation spike

Files changed:

- `src/configuration.h`
- `src/args.c`
- `src/main.c`
- `src/rl/rl_session.h`
- `src/rl/rl_session.c`
- `src/sf33rd/Source/Game/menu/menu.c`
- `src/sf33rd/Source/Game/game.c`

Purpose:

- add a default-off RL session flag for the baseline `MODE_VERSUS + rl_session_active` spike
- allow `--rl-agent --rl-player 1|2` to force one side to player-input control and the other side to CPU control

Implementation notes:

- added `RemoteRLAgentConfiguration`
- added CLI flags `--rl-agent` and `--rl-player`
- added `RLSession_ApplyVersusOperatorSetup()`
- hook is called after `Setup_VS_Mode()` sets both players to human
- hook is also called in `Game2_0()` after existing `Partner_Type` logic can set a side to CPU
- implementation stays under `src/rl/*` and does not touch `src/netplay/*`

Validation:

```sh
tools/mister/build-game.sh --flavor telemetry
```

Result:

- passed
- package created at `build/mister-telemetry-package`

Failures or surprises:

- first build failed because `rl_session.c` included `workuser.h` but not `plcnt.h`, so `plw` was undeclared
- fixed by including `sf33rd/Source/Game/engine/plcnt.h`

Follow-up:

- run the game with `--rl-agent --rl-player 1` or `--rl-agent --rl-player 2`
- verify round start behavior
- verify round end behavior
- verify winner flow behavior
- verify reset behavior
- only mark Milestone 0A checklist items complete after runtime validation

### 2026-04-21: MiSTer OSD RL Agent Launch Toggle

Milestones:

- Milestone 0A: Baseline match-flow confirmation spike

Files changed:

- `vendor/Menu_MiSTer/menu.sv`
- `vendor/Main_MiSTer/thirdsarm_wrapper.cpp`
- `docs/config.md`

Purpose:

- remove the need to launch from the MiSTer console with manual `--rl-agent --rl-player` arguments
- add an OSD menu toggle that persists RL agent launch mode and injects the correct startup args on relaunch

Implementation notes:

- added `RL Agent (Restart)` to `CONF_STR` with `Off / Player 1 / Player 2`
- assigned the menu to wrapper status bits `[48:47]`, which required widening the wrapper-side `status` bus
- added wrapper config read/write helpers for `rl-agent-player = off|1|2`
- wrapper now strips any forwarded `--rl-agent` / `--rl-player` args and re-injects launch args from the persisted OSD setting so wrapper config stays authoritative on MiSTer
- RL agent mode is seeded back into the OSD from persisted config on startup and restart
- changing the OSD option persists immediately, but takes effect only after wrapper `Restart`

Validation:

```sh
/home/olhua/src/3s-mister-arm/tools/mister-wrapper/build-hps.sh
/home/olhua/src/3s-mister-arm/tools/mister/build-game.sh --flavor telemetry
```

Result:

- passed
- HPS wrapper built at `build/mister-wrapper-hps/MiSTer_3S-ARM`
- telemetry package still built at `build/mister-telemetry-package`
- FPGA core / `.rbf` rebuild still pending because the `CONF_STR` change must be rolled into the menu/core image before OSD deployment testing

Follow-up:

- rebuild the menu/core image because `CONF_STR` changed
- deploy to MiSTer and verify:
  - `RL Agent (Restart)` appears in the OSD
  - selecting `Player 1` relaunches with `--rl-agent --rl-player 1`
  - selecting `Player 2` relaunches with `--rl-agent --rl-player 2`
  - selecting `Off` removes RL launch args on restart

### 2026-04-21: Lock VS Player-Type Menu Rows While RL Agent Is Active

Milestones:

- Milestone 0A: Baseline match-flow confirmation spike

Files changed:

- `src/sf33rd/Source/Game/menu/menu.c`

Purpose:

- keep the in-game VS option menu aligned with the actual RL baseline behavior
- avoid letting users interact with P1/P2 player-type rows that are later overridden by `RLSession_ApplyVersusOperatorSetup()`

Implementation notes:

- added a small local helper that treats game-option rows `8` and `9` as RL-managed when `RLSession_IsActive()`
- when RL is active, cursor movement skips those rows
- when RL is active, left/right modification is ignored on those rows
- this is a minimal v1 UX fix; it prevents contradictory editing without introducing new menu text assets

Validation:

```sh
/home/olhua/src/3s-mister-arm/tools/mister/build-game.sh --flavor telemetry
```

Result:

- passed
- telemetry package created at `build/mister-telemetry-package`

Follow-up:

- confirm on-device that the VS option cursor jumps over the two player-type rows while RL agent mode is enabled
- if stronger UX is needed later, add a visible `managed by RL agent` label or dimmed-state treatment

### 2026-04-21: Add RL Debug FPS Overlay Mode

Milestones:

- Milestone 0A: Baseline match-flow confirmation spike

Files changed:

- `vendor/Menu_MiSTer/menu.sv`
- `vendor/Main_MiSTer/thirdsarm_wrapper.cpp`
- `src/port/sdl/sdl_app.c`
- `src/port/sdl/fbdev_presenter.c`
- `docs/config.md`

Purpose:

- extend the MiSTer OSD `FPS Counter` menu with a fourth mode, `RL Debug`
- display RL baseline session state directly in the overlay during bring-up

Implementation notes:

- expanded the `FPS Counter` `CONF_STR` entry from `Off/FPS/Debug` to `Off/FPS/Debug/RL Debug`
- extended wrapper-side `show-fps` parsing and persistence to accept `rl-debug`
- extended game-side FPS overlay parsing with `FPS_OVERLAY_RL_DEBUG`
- when `rl-debug` is active, overlay text is now the compact slot marker `P0`, `P1`, or `P2`
- this mode intentionally reuses the existing `show-fps`/`SIGUSR1` path instead of adding a second OSD debug toggle

Validation:

```sh
/home/olhua/src/3s-mister-arm/tools/mister/build-game.sh --flavor telemetry
/home/olhua/src/3s-mister-arm/tools/mister-wrapper/build-hps.sh
```

Result:

- passed
- game package built successfully at `build/mister-telemetry-package`
- HPS wrapper built successfully at `build/mister-wrapper-hps/MiSTer_3S-ARM`
- FPGA core / `.rbf` rebuild is still required before the new `RL Debug` OSD menu item appears on MiSTer hardware

Follow-up:

- verify on MiSTer that `FPS Counter` cycles through all 4 modes
- verify `RL Debug` shows `P0`, `P1`, or `P2` correctly after wrapper restart

### 2026-04-21: Baseline VS Validation And RL Overlay Simplification

Milestones:

- Milestone 0A: Baseline match-flow confirmation spike

Files changed:

- `src/port/sdl/sdl_app.c`
- `docs/config.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:

- record successful MiSTer validation that the RL baseline VS flow works for both agent-side selections
- simplify the RL debug overlay text from `RL Agent: Off/P1/P2` to compact `P0/P1/P2`

Implementation notes:

- MiSTer validation confirmed that baseline RL VS launch works when the RL agent controls either player 1 or player 2
- `P0` now means RL agent disabled, while `P1` and `P2` indicate the active controlled slot
- the overlay remains specific to the dedicated `rl-debug` FPS counter mode

Validation:

```sh
# Hardware validation reported by MiSTer run testing.
```

Result:

- passed
- baseline VS mode works with RL agent configured for player 1
- baseline VS mode works with RL agent configured for player 2
- RL debug overlay text simplified to `P0`, `P1`, and `P2`

Follow-up:

- use Milestone 0A as the baseline foundation for the next scripted local fake-agent work

### 2026-04-21: Milestone 0A Runtime Validation Matrix Passed

Milestones:

- Milestone 0A: Baseline match-flow confirmation spike

Files changed:

- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:

- record that baseline runtime validation has completed successfully on MiSTer hardware
- close Milestone 0A with an explicit test matrix instead of a generic "seems okay" note

Implementation notes:

- validation was performed using the current baseline mode where the selected RL side remains on player-input routing and the opposite side remains on CPU routing
- this is still a baseline flow test, not a scripted or remote-agent control test

Validation:

```text
RL player 1: player wins a round
RL player 1: CPU wins a round
RL player 2: player wins a round
RL player 2: CPU wins a round
```

Result:

- passed
- `MODE_VERSUS + rl_session_active` works for RL player 1 and RL player 2
- round end, winner flow, and next-round reset behaved correctly in all four tested scenarios
- no blocking reason was found to fall back to a training-based baseline

Follow-up:

- move to Milestone 0B for `rl_flag` and delayed direction remap validation

### 2026-04-21: Add RL Settings And Scripted Movement For Milestone 0B

Milestones:

- Milestone 0B: Facing and remap validation micro-spike

Files changed:

- `src/configuration.h`
- `src/main.c`
- `src/args.c`
- `src/rl/rl_session.h`
- `src/rl/rl_session.c`
- `src/port/sdl/sdl_app.c`
- `vendor/Menu_MiSTer/menu.sv`
- `vendor/Main_MiSTer/thirdsarm_wrapper.cpp`
- `docs/config.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:

- support a human-controlled non-agent side during Milestone 0B so facing/remap checks are easier to reproduce than against live CPU behavior
- extend the RL debug overlay with concise opponent-routing and scripted-movement information
- group RL-related OSD settings under one `RL Settings` submenu

Implementation notes:

- added `--rl-opponent-human` on the game side and `rl-opponent-mode = cpu|human` on the MiSTer wrapper side
- moved `RL Agent (Restart)` and `RL Opponent (Restart)` into a new MiSTer OSD `RL Settings` submenu
- added `RL Movement` with `Forward`, `Back`, `Jump Forward`, and `Down Back`
- `RLSession_ApplyVersusOperatorSetup()` now routes the non-agent side to CPU or human input according to the RL opponent mode
- `RLSession_ApplyScriptedMovementToBuffers()` writes the selected fixed relative movement into the RL side's raw input buffer after `keyConvert()` and before input latch
- scripted movement is intentionally active only when RL is enabled and the non-agent side is routed to human input
- `rl-debug` overlay now shows concise routing codes:
  - `P0`: RL agent disabled
  - `P1C` / `P2C`: RL player 1 / 2 with CPU opponent
  - `P1H` / `P2H`: RL player 1 / 2 with human opponent
  - `:F`, `:B`, `:JF`, or `:DB`: active scripted movement in human-opponent validation mode

Validation:

```sh
/home/olhua/src/3s-mister-arm/tools/mister/build-game.sh --flavor telemetry
/home/olhua/src/3s-mister-arm/tools/mister-wrapper/build-hps.sh
```

Result:

- passed
- game package built successfully at `build/mister-telemetry-package`
- HPS wrapper built successfully at `build/mister-wrapper-hps/MiSTer_3S-ARM`
- FPGA core / `.rbf` rebuild is still required before the new `RL Settings` submenu appears on MiSTer hardware

Follow-up:

- verify on MiSTer that `RL Settings` contains `RL Agent`, `RL Opponent`, and `RL Movement`
- verify on MiSTer that `RL Opponent (Restart)` correctly switches the non-agent side between CPU and human input
- verify each scripted movement remaps correctly for both facings
- use the new human-opponent mode to run the Milestone 0B facing/remap spot checks

### 2026-04-21: Fix Scripted Movement Gate And Facing Remap

Milestones:

- Milestone 0B: Facing and remap validation micro-spike

Files changed:

- `src/rl/rl_session.c`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:

- prevent scripted RL movement from driving the cursor while still inside VS menu flow
- fix the observed forward/back inversion in the relative movement remap

Implementation notes:

- scripted movement now requires `mpp_w.inGame`, `Play_Mode == 1`, and `Game_pause == 0` in addition to RL active + human-opponent + `MODE_VERSUS`
- MiSTer testing showed the original `rl_flag` mapping assumption was inverted
- remap contract is now:
  - `rl_flag == 0`: facing world-left, so forward maps to `SWK_LEFT`
  - `rl_flag == 1`: facing world-right, so forward maps to `SWK_RIGHT`
- plan schema and Milestone 0B checklist were updated to match the observed contract

Validation:

```sh
/home/olhua/src/3s-mister-arm/tools/mister/build-game.sh --flavor telemetry
```

Result:

- passed
- game package built successfully at `build/mister-telemetry-package`

Follow-up:

- verify on MiSTer that scripted movement no longer acts in VS menu
- verify `Forward`, `Back`, `Jump Forward`, and `Down Back` now move in the intended relative direction for both `P1H` and `P2H`

### 2026-04-21: Stabilize Scripted Jump-Forward Across Cross-Over

Milestones:

- Milestone 0B: Facing and remap validation micro-spike

Files changed:

- `src/rl/rl_session.c`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:

- avoid one stale-facing jump after the RL side crosses over the human opponent

Implementation notes:

- MiSTer validation showed `Forward`, `Back`, `Jump Forward`, and `Down Back` were basically correct after the previous fix
- one remaining issue was observed: after a jump-forward crossed over the opponent, the next jump-forward could jump backward once, then recover on the following jump
- this suggests `rl_flag` can lag the cross-over by one input decision at the scripted-input hook point
- the 0B scripted movement helper now maps forward/back from current relative X position:
  - agent left of opponent -> forward is `SWK_RIGHT`
  - agent right of opponent -> forward is `SWK_LEFT`
  - exact same X position falls back to the current `rl_flag` mapping
- this change is intentionally scoped to the validation helper; the final remote action path can still decide whether to use facing, position, or explicit wire-mode semantics

Validation:

```sh
/home/olhua/src/3s-mister-arm/tools/mister/build-game.sh --flavor telemetry
```

Result:

- passed
- game package built successfully at `build/mister-telemetry-package`

Follow-up:

- verify on MiSTer that repeated `Jump Forward` remains toward the opponent immediately after crossing over

### 2026-04-21: Milestone 0B P1H/P2H Runtime Validation Passed

Milestones:

- Milestone 0B: Facing and remap validation micro-spike

Files changed:

- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:

- record successful MiSTer validation for the human-opponent relative movement checks
- close Milestone 0B before starting local fake-agent work

Implementation notes:

- runtime validation was reported for both `P1H` and `P2H`
- the tested RL movement selector values were:
  - `Forward`
  - `Back`
  - `Jump Forward`
  - `Down Back`
- validation covered the practical remap contract needed by the next local fake-agent step, including cross-over behavior after the position-based remap stabilization

Validation:

```text
P1H: RL Forward passed
P1H: RL Back passed
P1H: RL Jump Forward passed
P1H: RL Down Back passed
P2H: RL Forward passed
P2H: RL Back passed
P2H: RL Jump Forward passed
P2H: RL Down Back passed
```

Result:

- passed
- Milestone 0B checklist closed in the plan

Follow-up:

- start Milestone 0C by adding a CPU-opponent local fake-agent path that writes held scripted actions into the selected RL player's raw input buffer

### 2026-04-21: Start Milestone 0C Local Fake-Agent Sequence

Milestones:

- Milestone 0C: Local fake agent spike

Files changed:

- `src/main.c`
- `src/rl/rl_session.h`
- `src/rl/rl_session.c`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:

- start proving AI-vs-CPU control without networking
- add a local held-action sequence that drives the selected RL player while the non-agent side remains CPU-controlled

Implementation notes:

- renamed the main input hook call site to `RLSession_ApplyInputOverrideToBuffers()`
- retained the existing human-opponent 0B movement validation path
- added a CPU-opponent local fake-agent sequence with held forward, neutral attack, down-back, jump-forward attack, and back actions
- the sequence writes to `p1sw_buff` or `p2sw_buff` after `keyConvert()` and before the input latch
- local fake-agent state resets whenever the override is inactive, when human-opponent validation is active, or when gameplay is outside active unpaused VS play
- the implementation remains in `src/rl/*` plus the existing small `src/main.c` hook and does not touch `src/netplay/*`

Validation:

```sh
tools/mister/build-game.sh --flavor telemetry
```

Result:

- passed
- package created at `build/mister-telemetry-package`

Follow-up:

- verify on MiSTer with `P1C` and `P2C` that the agent-controlled side moves and attacks
- verify the non-agent side still runs CPU behavior
- verify held actions and sequence reset behavior across round transitions/menu exits

### 2026-04-21: Milestone 0C Runtime Validation Passed

Milestones:

- Milestone 0C: Local fake agent spike

Files changed:

- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:

- record successful MiSTer validation for the local CPU-opponent fake-agent path
- close Milestone 0C before moving to observation work

Implementation notes:

- runtime validation was reported for the local fake-agent path
- validation covered the selected RL side writing held scripted movement/attack input into the raw input buffer
- validation covered the non-agent side continuing to use CPU behavior
- no menu or round-flow regression was reported

Validation:

```text
P1C/P2C local fake-agent runtime validation passed.
Agent-controlled side moves and attacks.
CPU-controlled side fights normally.
Held scripted actions and reset behavior are acceptable for closing Milestone 0C.
```

Result:

- passed
- Milestone 0C checklist closed in the plan

Follow-up:

- move to Milestone 1: compact observation builder
- first implementation step should add a local `RLObservationV1` builder and an end-of-frame hook after `hit_check_main_process()`

### 2026-04-21: Add RL Observation Debug Overlay

Milestones:

- Milestone 1: Compact observation builder

Files changed:

- `src/rl/rl_observation.h`
- `src/rl/rl_observation.c`
- `src/sf33rd/Source/Game/game.c`
- `src/port/sdl/sdl_app.c`
- `src/port/sdl/fbdev_presenter.c`
- `docs/config.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:

- start local observation validation without networking or file logging
- put compact observation debug output into the existing `RL Debug` overlay
- show the RL-controlled side's effective raw input buttons on screen

Implementation notes:

- added `RLObservation_OnFrameEnd()` after `hit_check_main_process()`
- added a compact `RLObservationV1` state cache built from live player, stun, super, round, and input globals
- captured `round_start_hp[i]` on the first active observed round frame and recaptured on round changes or HP reset increases
- formatted `RL Debug` as three short lines:
  - route plus HP percentages
  - super, stun, X distance, facing sign, and round number
  - active input labels
- added multi-line overlay support for both SDL renderer debug text and MiSTer fbdev rasterized text
- kept output overlay-only for this slice; no disk logging or network path was added

Validation:

```sh
tools/mister/build-game.sh --flavor telemetry
```

Result:

- passed
- package created at `build/mister-telemetry-package`

Follow-up:

- verify on MiSTer that the overlay remains readable and does not cover important gameplay information
- validate HP, super, stun, position, facing, round, and input labels against visible gameplay
- fill out the rest of `RLObservationV1`, especially action-context fields, before closing Milestone 1

### 2026-04-21: Fix RL Debug Overlay Multiline And Low-HP Percent

Milestones:

- Milestone 1: Compact observation builder

Files changed:

- `src/port/sdl/fbdev_presenter.c`
- `src/rl/rl_observation.c`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:

- fix the reported issue where MiSTer `RL Debug` only showed the first line of overlay text
- avoid displaying `HP0` while the fighter still has visible remaining life

Implementation notes:

- updated `FBDevPresenter_ApplyFPSOverlayToBuffer()` to use the same multi-line text layout rules as the main fbdev overlay path
- this closes the remaining single-line layout path that could still clip RL debug text to the first line
- updated observation percent formatting so any positive HP value displays at least `1%`

Validation:

```sh
tools/mister/build-game.sh --flavor telemetry
```

Result:

- passed
- package created at `build/mister-telemetry-package`

Follow-up:

- verify on MiSTer that `RL Debug` now shows all expected lines
- verify that near-empty health now shows `HP1` instead of `HP0`

### 2026-04-21: Switch RL Debug Overlay To Raw HP And Colored Input Tokens

Milestones:

- Milestone 1: Compact observation builder

Files changed:

- `src/rl/rl_observation.h`
- `src/rl/rl_observation.c`
- `src/port/sdl/sdl_app.c`
- `src/port/sdl/fbdev_presenter.h`
- `src/port/sdl/fbdev_presenter.c`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:

- make the RL debug overlay more useful for direct gameplay inspection
- avoid misleading `HP0` display while the fighter is still alive
- show a fixed input legend where active buttons are highlighted in red

Implementation notes:

- line 1 now shows raw HP values instead of percentages, using `current/max`
- line 2 keeps compact state values using raw super and stun gauges
- line 3 is now a fixed token row:
  - `U D L R LP MP HP LK MK HK`
- inactive tokens stay white
- active tokens are drawn red
- SDL renderer and MiSTer fbdev presenter now both render the token row through dedicated per-token draw logic instead of the generic single-color text path
- fbdev presenter now receives the current RL input `SWKey` through a dedicated setter so token highlighting matches the active input on hardware

Validation:

```sh
tools/mister/build-game.sh --flavor telemetry
```

Result:

- passed
- package created at `build/mister-telemetry-package`

Follow-up:

- verify on MiSTer that line 1 shows raw HP values matching the visible life bar
- verify on MiSTer that the fixed input legend is always visible and active buttons turn red at the right frames

### 2026-04-21: Fix RL Debug Button Labels To Use Logical Attack Mapping

Milestones:

- Milestone 1: Compact observation builder

Files changed:

- `src/rl/rl_observation.h`
- `src/rl/rl_observation.c`
- `src/port/sdl/sdl_app.c`
- `src/port/sdl/fbdev_presenter.c`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:

- fix the reported issue where `LK`, `MK`, and `HK` appeared shifted in the RL debug input legend
- make the attack labels reflect gameplay button meaning instead of raw physical `SWKey` slot ordering

Implementation notes:

- directions still use raw `SWKey` bits for `U`, `D`, `L`, and `R`
- attack tokens now use a logical display mask built from the same `Convert_User_Setting()` mapping path used by gameplay
- this means `LP/MP/HP/LK/MK/HK` follow the current `Pad_Infor[].Shot[]` configuration instead of assuming raw `SWKey` slot order
- SDL and fbdev token highlighting now both read the same logical attack mask

Validation:

```sh
tools/mister/build-game.sh --flavor telemetry
```

Result:

- passed
- package created at `build/mister-telemetry-package`

Follow-up:

- verify on MiSTer that `LK`, `MK`, and `HK` now light the expected tokens

### 2026-04-22: Milestone 1 Status Review

Milestones:

- Milestone 1: Compact observation builder

Files changed:

- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:

- reconcile the current implementation against the Milestone 1 checklist
- record whether Milestone 1 can be closed or still has meaningful gaps

Implementation notes:

- current state is strong enough for observation bring-up and iterative debug:
  - end-of-frame hook exists
  - `RL Debug` overlay is readable on MiSTer
  - raw HP and logical button display now match runtime behavior well enough for spot checks
- Milestone 1 is still not ready to close because the implementation does not yet cover the full canonical schema from the plan
- remaining gaps include:
  - no implemented `last_executed_*`
  - no implemented `next_scheduled_*`
  - no implemented `frames_until_next_action`
  - no implemented corner-distance fields in the runtime observation path
  - no systematic MiSTer validation pass for position / guard / attack / round-state coverage
  - no observation build-cost measurement yet

Validation:

```text
Overlay bring-up looks healthy, but milestone-close criteria are still only partially satisfied.
```

Result:

- Milestone 1 remains open
- the right next step is still to finish Milestone 1 rather than start Milestone 2

Follow-up:

- finish the remaining canonical `RLObservationV1` fields in code
- validate the missing observation groups on MiSTer
- measure observation build cost on MiSTer or the closest equivalent target

## Milestone Notes

### Milestone 0A: Baseline Match-Flow Confirmation Spike

Objective:

- verify `MODE_VERSUS + rl_session_active` can run one agent-controlled side against one CPU side

Implementation notes:

- `--rl-agent` and `--rl-player` config/CLI path added
- `RLSession_ApplyVersusOperatorSetup()` applies operator flags for the baseline spike
- hook sites are `Setup_VS_Mode()` and `Game2_0()`

Validation notes:

- telemetry build passed on 2026-04-21
- runtime validation passed on MiSTer hardware for:
  - RL player 1 with player win
  - RL player 1 with CPU win
  - RL player 2 with player win
  - RL player 2 with CPU win

Open questions:

- exact automation mechanism for unattended round cycling once local scripted control is added

### Milestone 0B: Facing And Remap Validation Micro-Spike

Objective:

- verify `rl_flag` semantics and relative-direction remap behavior

Implementation notes:

- human-opponent validation mode added for deterministic spot checks
- RL debug overlay reports `P1H` / `P2H` during human-opponent validation and appends the selected movement label
- fixed movement selector covers forward, back, jump-forward, and down-back
- remap now uses relative X position first, with `rl_flag` as the same-X fallback, to avoid stale-facing behavior immediately after cross-over

Validation notes:

- MiSTer runtime validation passed for `P1H` and `P2H` with forward, back, jump-forward, and down-back

Open questions:

- final remote action path still needs to choose whether to use facing, position, or an explicit negotiated remap rule for delayed side-switch execution

### Milestone 0C: Local Fake Agent Spike

Objective:

- verify local scripted input override before networking

Implementation notes:

- started with a local CPU-opponent fake-agent sequence in `src/rl/rl_session.c`
- the sequence writes held movement and attack actions into the selected RL player's raw input buffer after `keyConvert()` and before input latch
- the local fake-agent sequence is active only for RL-enabled `MODE_VERSUS` gameplay when the opponent is CPU-controlled

Validation notes:

- telemetry build passed after initial implementation
- on-device local fake-agent runtime validation passed

Open questions:

- exact first playable frame for `round_start_hp[i]` capture now moves to Milestone 1

### Milestone 1: Compact Observation Builder

Objective:

- build and validate `RLObservationV1`

Implementation notes:

- started with a local `RLObservationV1` builder in `src/rl/rl_observation.c`
- added an end-of-frame hook after `hit_check_main_process()`
- `RL Debug` overlay now uses a compact multi-line observation view instead of only the routing label
- overlay includes RL routing, HP, super, stun, opponent X distance, facing sign, round number, and the RL-side raw input buttons
- input labels are `U`, `D`, `L`, `R`, `LP`, `MP`, `HP`, `LK`, `MK`, and `HK`
- fbdev and SDL renderer overlays now support short multi-line debug text
- raw HP display and logical attack-button display are now working well enough for runtime spot checks
- the runtime struct is still only a partial subset of the full canonical schema from the plan

Validation notes:

- telemetry build passed after initial implementation
- on-device overlay readability and button-label correctness are now good
- full observation-group validation and build-cost measurement are still pending

Open questions:

- validate whether the current first active-frame `round_start_hp[i]` capture matches round bootstrap on hardware
- validate positions, HP, super, stun, attack state, guard state, and round state against visible gameplay

### 2026-04-22: Close Milestone 1 Observation Builder

Milestones:

- Milestone 1: Compact observation builder

Purpose:

- finish the runtime observation schema so it matches the canonical `RLObservationV1` table
- expose action-context and corner-distance directly on MiSTer
- make the `RL Debug` overlay sufficient for validation and cost measurement without extra tooling

Changes:

- updated `src/rl/rl_observation.h` so `RLObservationV1` now uses the canonical schema fields:
  - normalized HP / super / stun ratios
  - normalized `opp_dx_ratio` / `opp_dy_ratio`
  - normalized self / opponent corner ratios
  - all fixed state / round / action-context fields from plan section `4A`
- updated `src/rl/rl_observation.c`:
  - compute ratios from `round_start_hp`, `sa->store_max`, `py->genkai`, and `scrl/scrr`
  - keep raw debug values for overlay readability
  - measure observation build cost per frame and expose running `avg/max` microseconds
  - expand `RL Debug` into a compact multiline validation view covering:
    - HP / super / stun / round / wins
    - `DX`, `DY`, facing, and corner distances
    - guard flags and attack ids
    - do-not-move / hit-stop / high-jump flags
    - self / opponent routine triplets
    - action-context and observation cost
- updated `src/rl/rl_session.h` / `src/rl/rl_session.c`:
  - added explicit `RL_MOVE_*` intent enum matching the plan
  - added `RLActionContext`
  - fake-agent and human-opponent validation paths now publish:
    - `last_executed_move_intent`
    - `last_executed_attack_bits`
    - `next_scheduled_move_intent`
    - `next_scheduled_attack_bits`
    - `frames_until_next_action`
- updated docs:
  - `docs/plan-remote-rl-agent.md`
  - `docs/config.md`

Validation:

- local build passed:
  - `tools/mister/build-game.sh --flavor telemetry`
- lint-style patch check passed:
  - `git diff --check`
- MiSTer validation path is now documented as a concrete matrix using existing OSD controls:
  - `RL Settings -> RL Agent`
  - `RL Settings -> RL Opponent`
  - `RL Settings -> RL Movement`
  - `FPS Counter = RL Debug`

Result:

- Milestone 1 is now ready to close
- the next stage can focus on Milestone 2 handshake / delay-budget work instead of more local observation bring-up
- decide whether to finish the remaining schema fields in the current runtime struct or refactor it to mirror the plan table more literally

### 2026-04-22: Align RL Debug Super And Win Semantics With MiSTer Validation

Milestones:

- Milestone 1: Compact observation builder follow-up

Purpose:

- correct two observation/overlay assumptions that MiSTer runtime validation disproved
- show both super-stock count and current gauge fill
- move round-win tracking to the versus-specific counter path

Changes:

- updated `src/rl/rl_observation.h` / `src/rl/rl_observation.c`
  - canonical observation now carries:
    - `self_super_stock`, `self_super_stock_max`
    - `opp_super_stock`, `opp_super_stock_max`
    - `self_super_gauge_ratio`, `opp_super_gauge_ratio`
  - `RL Debug` now shows:
    - `SAa/b` for full-stock count
    - `SGx/y` for current gauge fill progress
  - round-win display now reads from `VS_Win_Record[*]`
- increased RL overlay text buffers in:
  - `src/port/sdl/sdl_app.c`
  - `src/port/sdl/fbdev_presenter.c`
- updated docs:
  - `docs/plan-remote-rl-agent.md`
  - `docs/config.md`

Validation input from MiSTer:

- `SA` was observed as `0/2`, `1/2`, `2/2`, confirming the old display was stock count instead of gauge progress
- round wins stayed `0-0`, indicating `Win_Record[*]` was not the right versus overlay source

Result:

- RL overlay semantics now better match actual versus runtime behavior

### 2026-04-22: Audit RL Debug Raw-State Semantics And Rename Overlay Labels

Milestones:

- Milestone 1: Compact observation builder follow-up

Purpose:

- reconcile the remaining RL Debug raw-state labels with MiSTer runtime observations and code audit results
- make the overlay names less misleading before moving on to networking work

Changes:

- updated `src/rl/rl_observation.c`
  - renamed the multiline overlay labels to better match current runtime semantics:
    - `M` for cumulative versus match wins
    - `CF` for raw combat/contact state from `guard_flag`
    - `AK` for `current_attack` button-category codes
    - `NM` for raw `do_not_move`
    - `HS` for contact-oriented `hit_stop`
    - `HJ` for the high-jump-only flag
    - `SR` / `OR` for self / opponent routine triplets
- updated docs:
  - `docs/plan-remote-rl-agent.md`
    - corrected canonical-field notes for `guard_flag`, `current_attack`, `do_not_move`, `hit_stop`, `high_jump_flag`, and `VS_Win_Record`
    - added a dedicated `RL Debug` validated-semantics section based on MiSTer observations plus code audit
    - updated the Milestone 1 MiSTer validation matrix to use the new labels and meanings
  - `docs/config.md`
    - updated `show-fps = rl-debug` notes to explain the renamed overlay abbreviations

Code-audit conclusions captured in docs:

- `guard_flag` is not a pure block boolean; many hit / guard / catch paths set it to `3`
- `current_attack` comes from `shot_data_refresh()` and currently behaves as an attack button-category code (`LP/MP/HP/LK/MK/HK`)
- `do_not_move` appears to be low-signal in the current versus path and is commonly `0`
- `hit_stop` often behaves like a shared contact stop on both players
- `high_jump_flag` is specific to high-jump / hijump-cancel logic, not generic airborne state
- `routine_no[0..2]` remains the most informative raw state bundle; `routine_no[1]` cleanly separates normal / damage / catch / caught / attack

Validation:

```sh
tools/mister/build-game.sh --flavor telemetry
git diff --check
```

Result:

- RL Debug labels and docs now line up with the current raw-state interpretation used during MiSTer bring-up

### 2026-04-22: Add Current-Match Round Score And MVP Observation Set

Milestones:

- Milestone 1: Compact observation builder follow-up

Purpose:

- expose both current-match round score and cumulative VS match wins in `RL Debug`
- document the minimum observation subset intended for the first usable RL training loop

Changes:

- updated `src/rl/rl_observation.h` / `src/rl/rl_observation.c`
  - added `self_match_round_wins` and `opp_match_round_wins` from `PL_Wins[*]`
  - changed the first overlay line to show `R`, `RW`, and `M` separately:
    - `R`: current round
    - `RW`: current match's round score from the RL perspective
    - `M`: cumulative versus match wins from `VS_Win_Record[*]`
- updated docs:
  - `docs/plan-remote-rl-agent.md`
    - added `PL_Wins[*]` fields to the canonical schema
    - added an MVP training observation subset
    - updated `RL Debug` line-1 semantics and validation matrix
  - `docs/config.md`
    - updated `show-fps = rl-debug` notes for `RW`

Validation plan:

```sh
tools/mister/build-game.sh --flavor telemetry
git diff --check
```

MiSTer follow-up:

- verify `RW` increments after each round win inside a match
- verify `RW` resets when a new match starts
- verify `M` still tracks cumulative VS match wins

### 2026-04-22: Document Human-Fighter Observer Gap Review

Milestones:

- Milestone 1: Compact observation builder follow-up
- Milestone 4 / Milestone 6 planning input

Purpose:

- capture the gap between the current MVP observer and the information a human player naturally uses during a match
- keep Milestone 2 unblocked while preserving the review items for transition logging, reward design, and later observation expansion

Changes:

- updated `docs/plan-remote-rl-agent.md`
  - added `Human-Fighter Observer Gap Review` under the observation schema section
  - marked the Milestone 1 current read to say these gaps are documented and do not block Milestone 2
  - added Milestone 4 tasks to review action-outcome and event-delta candidates
  - added Milestone 6 tasks to review derived movement/action-phase candidates before schema expansion

Summary:

- current MVP is sufficient for spacing, resources, coarse combat state, and delayed action context
- likely missing or implicit fields include opponent movement intent, action phase, own action outcome, and event deltas
- priority follow-up areas are:
  - action outcomes and deltas for Milestone 4 transition/reward design
  - derived movement/action-phase features for Milestone 6 policy strength

Validation:

```sh
# Documentation-only update.
```

### 2026-04-22: Refresh Milestone 1 RL Debug Validation Matrix

Milestones:

- Milestone 1: Compact observation builder follow-up

Purpose:

- keep the Milestone 1 MiSTer validation matrix aligned with the latest `RL Debug` overlay layout

Changes:

- updated `docs/plan-remote-rl-agent.md`
  - added the current line-by-line overlay example to the Milestone 1 validation matrix
  - corrected line references for `DX/DY/F`, `CL/CR/OL/OR`, action-context, input-row tokens, and observation cost
  - documented the first-line `R`, `RW`, and `M` meanings in the matrix itself

Validation:

```sh
git diff --check
```

### 2026-04-22: Start Milestone 2 Protocol Skeleton

Milestones:

- Milestone 2: Session handshake, network probe, and delay budget

Purpose:

- start the remote RL session handshake/probe milestone with a safe data-layer-only implementation
- define the hello/ack/config/hash/probe-stat helpers before adding live socket I/O

Changes:

- added `src/rl/rl_protocol.h`
  - protocol/schema/action version constants
  - `RLSessionConfig`
  - `RLSessionHello`
  - `RLSessionAck`
  - ack status enum
  - `RLProbeStats`
- added `src/rl/rl_protocol.c`
  - default config
  - deterministic FNV-1a config hash
  - timing/config validation helpers
  - ack validation helper
  - sorted-sample p50/p95/p99 probe-stat helper
- added `src/rl/rl_net.h` / `src/rl/rl_net.c`
  - no-op disabled network state
  - no socket open/send/receive path yet
  - default config state only, so existing fake-agent and overlay behavior stay unchanged
- updated `docs/plan-remote-rl-agent.md`
  - checked off protocol data-layer tasks
  - split percentile helper work from target-network latency measurement work
  - documented current no-op disabled path and placeholder timing values

Validation plan:

```sh
tools/mister/build-game.sh --flavor telemetry
git diff --check
```

Follow-up:

- add the actual UDP ping/pong packet path
- expose remote host/port configuration
- collect target-network RTT / jitter / p50 / p95 / p99 before choosing final `k`, `decision_interval_frames`, and `action_hold_frames`

### Milestone 2: Session Handshake, Network Probe, And Delay Budget

Objective:

- agree on session config and measure real network timing

Implementation notes:

- TBD

Validation notes:

- TBD

Open questions:

- final `config_hash` algorithm
- exact feature flag bit assignments

### Milestone 3: Remote Inference Only

Objective:

- connect MiSTer to a remote heuristic server

Implementation notes:

- TBD

Validation notes:

- TBD

Open questions:

- first remote server language and runtime
- whether to keep remote heuristic server in this repo or a separate repo

### Milestone 4: Decision Ledger And Transition Logging

Objective:

- make the environment trainable with executed-action-aligned transitions

Implementation notes:

- TBD

Validation notes:

- TBD

Open questions:

- transition log format
- transport for non-critical learner data

### Milestone 5: Async Learner And Model Hot-Swap

Objective:

- train online without blocking inference

Implementation notes:

- TBD

Validation notes:

- TBD

Open questions:

- model runtime
- weight hot-swap protocol

### Milestone 6: Higher-Control-Rate Policy And Curriculum

Objective:

- improve agent strength after the transport/control path is stable

Implementation notes:

- TBD

Validation notes:

- TBD

Open questions:

- curriculum schedule
- expanded observation schema versioning strategy
- whether `overlay_attack_event_finalized` / `overlay_attack_contact` / `overlay_attack_whiff` keep consistent learner semantics across normals, specials, projectiles, throws, and multistage moves, or should remain debug / auxiliary-only labels until move-family validation is complete
- how human-vs-CPU demo episodes should be recorded and tagged so they can bootstrap learner training without being confused with remote-agent-generated experience

## Test And Build Records

### Move-Family Validation SOP

Use this SOP for the first stable scripted attack-policy validation passes.

1. Choose one policy for the pass:
   - `hp`
   - `throw`
   - `ryu-fireball`
   - `tatsu`
   - `shoryuken`

2. Pick a dedicated transition log path for that pass:
   ```text
   logs/rl-transitions-<policy>-4-3-3.ndjson
   ```

3. Start the probe server with:
   - the selected `--policy`
   - the dedicated `--transition-log`
   - the usual live learner arguments

   Example:
   ```sh
   python \\wsl.localhost\Ubuntu\home\olhua\src\3s-mister-arm\tools\rl_probe_server.py --host 0.0.0.0 --port 37330 --action-port 37331 --policy hp --policy-repeat-delay-ms 3000 --model-version 0 --model-dir \\wsl.localhost\Ubuntu\home\olhua\src\3s-mister-arm\model\rl-model-live --transition-log \\wsl.localhost\Ubuntu\home\olhua\src\3s-mister-arm\logs\rl-transitions-hp-4-3-3.ndjson --learner-auto-publish --learner-publish-interval-sec 10 --learner-warmup-rows 100 --learner-batch-size 32
   ```

4. On the MiSTer/game side, set the timing baseline to `4/3/3`:
   ```ini
   rl-agent-delay-frames = 4
   rl-agent-decision-interval = 3
   rl-agent-action-hold = 3
   ```

5. Restart the MiSTer/game runtime after changing timing config.
   Do not assume editing config live will change the active run.

6. Use one fixed opponent behavior for the whole pass:
   - preferred first pass: opponent steadily approaches the RL side
   - avoid mixing free-form CPU behavior and scripted approach behavior in the same comparison set

7. Run the pass until at least:
   - `rows >= 256`
   - `done >= 2`

8. Capture one or more representative `LEARNER` lines including:
   - `timing=...`
   - `policy=...`
   - `policy_rows=...`
   - `policy_rew=...`
   - `policy_fallback_pct=...`
   - `atk=...`
   - `inf=...`

9. Do a visible gameplay sanity check:
   - attack visibly occurs: yes / no
   - contact observed: yes / no
   - whiff observed: yes / no

10. Record the run in the move-family validation template below:
    - date
    - policy
    - opponent setup
    - timing
    - command
    - log summary
    - visible outcome check
    - pass / fail
    - follow-up notes

11. Repeat the same procedure for the next policy, changing only:
    - `--policy`
    - `--transition-log`

### Move-Family Validation Record Template

Date:

- YYYY-MM-DD

Milestone:

- Milestone 6: Higher-control-rate policy and curriculum

Policy:

- `hp` / `throw` / `ryu-fireball` / `tatsu` / `shoryuken`

Opponent setup:

- steady approach / other fixed setup

Timing:

- `k/decision_interval/action_hold`

Command:

```sh
# learner/probe command here
# note any MiSTer-side timing/config overrides here
```

Log summary:

- `rows=`
- `done=`
- `policy_rows=`
- `policy_rew=`
- `policy_fallback_pct=`
- `atk=`
- `inf=`

Visible outcome check:

- attack visibly occurs: yes / no
- contact observed: yes / no
- whiff observed: yes / no

Result:

- pass / fail

Notes:

- spacing / timing observations
- whether labels looked plausible
- follow-up action

### Template

Date:

- YYYY-MM-DD

Milestone:

- TBD

Command:

```sh
# command here
```

Result:

- TBD

Notes:

- TBD

## MiSTer Deploy Records

### Template

Date:

- YYYY-MM-DD

Build artifact:

- TBD

Deploy command:

```sh
# command here
```

MiSTer target:

- TBD

Result:

- TBD

Notes:

- TBD

## Open Issues

- [ ] Validate whether overlay attack-outcome fields are learner-safe across normals, specials, projectiles, throws, and multistage moves
- [ ] Revisit transition/replay SA state after the RL loop runs reliably: live observations already include super stock and gauge ratios, but replay-only learner rows may need compact `self_super_stock`, `self_super_gauge_ratio`, `opp_super_stock`, and `opp_super_gauge_ratio` fields or derived `can_super` flags so policies can learn when supers are available.
- [ ] Define a human-demo recording / ingest path for learner bootstrapping, including replay metadata and mixing policy with remote-agent episodes

## Closed Issues

- [x] Confirm exact `MODE_VERSUS + rl_session_active` setup hook
- [x] Confirm `rl_flag` mapping with runtime observation
- [x] Confirm first playable frame for `round_start_hp[i]`
- [x] Choose `config_hash` algorithm
- [x] Choose remote heuristic server location
- [x] Choose transition log format
