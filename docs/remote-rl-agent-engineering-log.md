# Remote RL Agent Engineering Log

This log tracks implementation progress, engineering decisions, test results, and open issues for the remote RL agent work.

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
