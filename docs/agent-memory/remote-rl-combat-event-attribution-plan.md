# Remote RL Complete Combat Event Attribution Plan

This document is the full plan for making remote RL logs replayable and
attribution-safe for both the agent side and the opponent side.

The goal is not to add a few more snapshot fields. The goal is to turn the
current decision log into a combat event log that can answer:

- what action started
- who started it
- whether the game accepted it
- whether it hit, blocked, whiffed, chipped, threw, teched, or punished
- which later damage/contact/guard result belongs to that earlier action
- how confident the attribution is
- why attribution failed when it cannot be proven

## Current Gap

The current transition row is a decision-centric record:

- policy action requested/executed
- input-derived action label
- self-side engine action label for recognized move starts
- compact observation snapshot
- HP/stun/position deltas
- reward and terminal state

That is enough for coarse learning and post-hoc guesses, but it is not enough
for full fight review.

The missing layer is event identity. A later HP delta needs to point back to
the attack, projectile, throw, or punish event that caused it. A guard row
needs to say whether the defender actually blocked, ate chip, got thrown, got
hit high/low/air, or was in an unblockable/unmovable state.

## Design Principles

1. Events are the truth model; snapshots are evidence.
   - Observation fields describe what the state looked like at a frame.
   - Combat events describe what happened across frames.

2. Self and opponent use the same schema.
   - The only difference is actor/target side.
   - Any field that exists for self attacks must have an opponent equivalent.

3. Never force attribution.
   - Unknown with a failure reason is better than a wrong label.
   - Every resolved event carries source and confidence.

4. Preserve learner safety.
   - Rich event labels start as analysis/debug truth.
   - Reward shaping and DQN ingestion only use them after validation gates pass.

5. Keep the hot path fixed-size.
   - Use small ring buffers and numeric enums in `src/rl/*`.
   - Avoid dynamic allocation, string formatting, or large JSON work per frame.

6. Version all schema changes.
   - Transition summary fields become schema v4.
   - Full combat event export starts as `combat_event_schema_version = 1`.

## Target Log Shape

The final logging model has two layers.

### 1. Transition Summary Rows

These remain one row per decision and are optimized for training/analyzer use.
They summarize the best event attribution that happened during or after the
decision window.

Examples:

- `self_attack_event_id`
- `self_attack_result`
- `self_attack_damage_hp`
- `self_attack_was_punished`
- `self_defense_event_id`
- `incoming_attack_event_id`
- `self_defense_result`
- `self_defense_damage_hp`
- `opp_attack_event_id`
- `opp_attack_result`
- `opp_defense_result`

### 2. Combat Event Journal

This is a logical event stream for full replay and debugging. It must not be a
second independent C-side network/file stream. The C side should attach combat
events to the same transition batch/envelope as the decision rows that advanced
past those events. The remote PC may split the received batch into separate
transition and event NDJSON files after receipt, but transport from MiSTer must
stay atomic and ordered.

Final disk persistence contract:

- MiSTer/C side emits one synchronized transition batch/envelope; it must not
  write or send a second independent combat-event stream.
- Remote PC persistence defaults to two NDJSON files derived from that same
  received envelope:
  - transition summary rows in the configured transition log
  - combat event journal rows in a sibling combat-event log
- The two files are separate for analyzer ergonomics only. They are not
  independent sources of truth.
- Both files must preserve enough envelope identity to reconcile them, including
  `run_id`, `episode_id`, and event/summary ids; if a batch/envelope id is added
  to the transport, both persisted files must include it.
- If the receiver cannot persist the event file for an envelope, it must mark
  the affected transition batch as incomplete or failed rather than silently
  writing transition summaries that reference missing event rows.

Each event row is one fact, such as:

- attack start
- projectile spawn
- contact
- hit
- block
- chip
- throw start
- throw result
- whiff finalization
- punish
- attribution failure

The event journal is the source for complete battle review. Transition rows are
compact derived summaries.

Events that finalize between decision rows must be retained in a fixed-size
pending-export ring until the next transition batch/envelope can carry them.
The ring id is separate from `event_id`; export slots may wrap, but event ids
may not. If pending export overflows, MiSTer must increment
`dropped_combat_event_count` / `dropped_combat_event_first_id` metadata in the
same envelope so analyzers know that reference integrity is incomplete instead
of silently trusting a partial journal.

## Core Event Identity

Every combat event uses these fields.

| Field | Purpose | Required because |
| --- | --- | --- |
| `combat_event_schema_version` | Version the event schema | Older analyzers must fail fast instead of guessing |
| `run_id` | Match/log run id | Prevents event id collisions across logs |
| `episode_id` | Episode id | Prevents cross-round attribution |
| `round_num` | Round number | Human-readable grouping and validation |
| `event_id` | Unique monotonically increasing event id within run | Links starts, contacts, outcomes, and summaries |
| `parent_event_id` | Optional already-created parent event | Links projectile hit to projectile spawn, punish to finalized attack/recovery |
| `actor` | `self` or `opp` | Distinguishes agent action from opponent threat |
| `target` | `self`, `opp`, or `none` | Distinguishes who was affected |
| `event_type` | Event family | Lets analyzers count starts, hits, blocks, throws, whiffs |
| `event_frame` | Exact frame of the fact | Decisions span multiple frames |
| `decision_id` | Nearest/owning decision | Connects event to model choice and replay row |
| `source` | Engine/obs/projectile/heuristic source | Makes trust boundaries explicit |
| `confidence` | High/medium/low/unknown | Lets training ignore weak labels |
| `failure_reason` | Why attribution failed | Makes gaps visible instead of silent |

`event_id` is not a ring-buffer index. It must be generated from a single
`uint64` monotonically increasing counter shared by self, opponent, projectile,
throw, defense, and attribution-failure events for the whole run. Ring buffers
store structs that contain this id. A slot can be reused only after its old
event is finalized/exported, but the id itself must never be reused within the
run. `0` is reserved for "no event". If the counter ever approaches wrap-around,
the session must start a new run or emit a fatal schema health error; silently
wrapping is forbidden.

`parent_event_id` can only point to an event that has already been created. For
retroactive relationships, finalize/create the parent first and then create the
child. Do not emit a child whose parent will be filled in later by out-of-band
mutation; that is too fragile for NDJSON logs and batch export.

## Event Lifecycle State Machine

Event ordering must be explicit so the event journal never needs circular
references or later row mutation.

Attack lifecycle:

1. `attack_start`
2. optional `attack_active` / `contact`
3. one final `attack_result`
4. optional child `punish`

Projectile lifecycle:

1. owner `attack_start`
2. `projectile_spawn` with `parent_event_id = owner_attack_event_id`
3. zero or more `contact` events for multi-hit projectiles
4. one final `projectile_result`

Throw lifecycle:

1. `throw_start`
2. one final `throw_result`
3. matching `defense_result` for the target when applicable

Defense lifecycle:

1. incoming `attack_start`, `projectile_spawn`, or `throw_start`
2. optional `contact`
3. one `defense_result` linked to the incoming event

Punish lifecycle:

1. unsafe attack has already reached `attack_result=whiff`, `interrupted`, or
   `no_damage_recovery`
2. opponent creates/owns the damaging `attack_start` or `projectile_result`
3. create `punish` as a child of the punished attack event, with the punisher
   event id in `punisher_attack_event_id`

Round lifecycle:

1. `round_start`
2. combat events
3. `round_end`
4. forced finalization of all pending events for that episode

## Event Types

Use numeric enums in C and names in Python/docs.

| Event type | Meaning | Main use |
| --- | --- | --- |
| `attack_start` | A character started a game-accepted attack | Root id for hit/block/whiff/punish |
| `attack_active` | Optional active-window evidence | Helps validate whiff/contact windows |
| `contact` | Attack interacted with target | Multi-hit and hit/block evidence |
| `attack_result` | Final result for a non-projectile attack | Hit/block/chip/whiff/punished stats |
| `defense_result` | Defender outcome from incoming threat | Guard quality and failure analysis |
| `projectile_spawn` | Projectile became active | Separates owner recovery from projectile hit |
| `projectile_result` | Projectile hit/blocked/expired | Fireball zoning attribution |
| `throw_start` | Throw attempt began | Separates throws from strikes |
| `throw_result` | Throw success/tech/whiff | Explains guard failures at close range |
| `stun_state` | Hitstun/blockstun/knockdown start or end | Explains whether defense was possible |
| `position_event` | Side switch, corner trap, corner escape | Explains sudden spacing/threat changes |
| `punish` | Actor was punished after unsafe action | Risk learning for DP/fireball/tatsu |
| `round_start` | Episode/round begins | Flush boundary and replay anchor |
| `round_end` | Episode/round ends | Forced finalization and winner/reason |
| `attribution_failure` | A delta/contact had no safe source | Schema health and reverse-engineering target |

## Common Action Identity Fields

Attack, projectile, throw, punish, and defense events carry action identity when
available.

| Field | Purpose | Required because |
| --- | --- | --- |
| `action_id` | Canonical high-level policy action | Allows action success/failure stats |
| `sub_action_id` | Strength/direction/variant | Finds LP/MP/HP or LK/MK/HK-specific bugs |
| `action_step` | Macro step if policy-owned | Explains macro continuation outcomes |
| `input_action_id` | Input-derived label | Keeps human/CPU-demo evidence available |
| `engine_action_id` | Engine-derived label | Best source for accepted attacks |
| `routine_1` | Engine routine major state | Raw evidence and mapping debug |
| `routine_2` | Engine routine substate | Distinguishes special/throw dispatch paths |
| `current_attack` | Engine attack code | Identifies concrete attack state |
| `kind_of_waza` | Engine move family/type | Separates normal/special/throw/projectile |
| `engine_lag_frames` | Delay from action to engine recognition | Validates attribution windows |

Action identity should exist for both sides:

- `self_engine_*`
- `opp_engine_*`
- event-local `action_id` / `engine_action_id`

The old generic `engine_*` transition fields can remain for compatibility only
until schema v4 rollout, but schema v4 should make side ownership explicit.

## Spatial Context Fields

Every start/result event should carry enough spacing to explain why it was good
or bad.

| Field | Purpose | Required because |
| --- | --- | --- |
| `actor_x`, `actor_y` | Actor position | Replays event location |
| `target_x`, `target_y` | Target position | Computes range at start/result |
| `abs_dx`, `abs_dy` | Distance at event | Core close/mid/far diagnosis |
| `range_bucket` | close/mid/far/far_projectile/etc. | Stable analyzer buckets |
| `actor_in_front` | Facing relation | Detects side-switch ambiguity |
| `actor_airborne`, `target_airborne` | Air state | Anti-air and jump-in semantics |
| `actor_corner_dist`, `target_corner_dist` | Corner pressure | Explains trapped/escape behavior |

## Attack Start Tracking

Maintain active and finalized attack-event rings per side.

Recommended size:

- 32-entry active ring per side for pending attack/result matching
- 48-entry finalized ring per side for recent punish matching
- a slot marked active/pending must not be overwritten; overflow emits an
  `attribution_failure` / schema-health counter instead of corrupting ids

Start evidence should be collected from:

- `Attack_Counter` edge
- `current_attack` edge or nonzero code change
- `routine_no[1]` attack-state edge
- `routine_no[2]` special/throw dispatch edge
- policy/input attack request for self-side context
- engine action attribution for character-specific mapping

An `attack_start` event is high confidence when engine evidence exists. It is
medium confidence when only policy/input plus matching attack-state evidence
exists. It is low confidence when only heuristic evidence exists.

## Attack Result Tracking

Each attack event has a finite lifetime.

Suggested first windows:

- normals: 30 frames
- throws: 12 frames
- Shoryuken: 45 frames
- Tatsu: 45 frames
- fireball attack-start to projectile spawn: 45 frames
- projectile lifetime: separate projectile tracker

Possible results:

- `hit`
- `blocked`
- `chip`
- `interrupted`
- `whiff`
- `projectile_spawned`
- `projectile_hit`
- `projectile_blocked`
- `thrown`
- `throw_tech`
- `punished`
- `trade`
- `unknown`

`whiff` should only finalize after the action window ends with no contact,
damage, projectile spawn, or throw result. Do not mark whiff immediately on the
first no-damage decision row.

`interrupted` means the attack was accepted or started but the actor was hit,
thrown, or otherwise stopped before reaching a confirmed active/contact result.
This is distinct from `whiff`: it tells the learner/analyzer that the move may
have been too slow or used at the wrong timing, not necessarily out of range.

## Contact and Damage Resolution

Contact resolver consumes frame-level facts:

- `delta_self_hp`
- `delta_opp_hp`
- `delta_self_stun`
- `delta_opp_stun`
- `self_entered_hit_stop`
- `opp_entered_hit_stop`
- `self_entered_contact_state`
- `opp_entered_contact_state`
- contact reaction state
- routine attack/contact states
- projectile proximity and owner

Resolution order:

1. Exact projectile hit/block candidate.
2. Exact throw candidate.
3. Simultaneous/trade pair candidate when both sides enter hitstop or both HP
   deltas occur in the same frame window.
4. Recent high-confidence attack event from the opposing side.
5. Recent medium-confidence attack event from the opposing side.
6. Heuristic routine/current_attack candidate.
7. Attribution failure event.

The resolver must mark which HP/stun delta was consumed by which event so the
same damage is not double-credited to projectile, attack, and delayed reward
windows.

The resolver is edge-triggered, not a full per-frame search. It only scans
candidate lists when a relevant edge occurs:

- `delta_self_hp != 0`
- `delta_opp_hp != 0`
- `delta_self_stun != 0`
- `delta_opp_stun != 0`
- `self_entered_hit_stop`
- `opp_entered_hit_stop`
- `self_entered_contact_state`
- `opp_entered_contact_state`
- projectile spawn/disappear/owner-proximity edge
- throw routine edge

The implementation should maintain compact active-index lists so the common
path checks the current active event per side plus projectile candidates, not
all ring slots. The first performance budget is: attribution work should remain
below 500 microseconds on the MiSTer frame-end path in smoke logs, with p95 and
max recorded before the labels are promoted.

## Defense Result Tracking

Defense is not "did the model press guard"; defense is "what happened when an
incoming event threatened the defender".

Each defense result links to an incoming event when possible.

| Field | Purpose | Required because |
| --- | --- | --- |
| `defense_event_id` | Unique defense result | Lets rows and event journal reference it |
| `defender` | self or opp | Symmetric analysis |
| `incoming_attack_event_id` | Source threat | Answers what made defense fail |
| `intended_guard_action_id` | Policy/input guard/back/attack intent | Separates requested defense from actual contact state |
| `defense_action_id` | Guard/back/forward/attack/etc. | Evaluates policy choice |
| `defense_result` | blocked/hit/chip/thrown/etc. | Core defense label |
| `defense_damage_hp` | HP loss | Severity |
| `defense_damage_stun` | Stun loss/gain | Pressure tracking |
| `actual_guard_state_at_contact` | stand/crouch/none/air at contact frame | Explains whether guard was active in time |
| `guard_state` | stand/crouch/none/air | Backward-compatible summary of actual guard state |
| `target_state` | neutral/blockstun/hitstun/invincible/recovering/knockdown/wakeup/unknown | Explains whether defense or throw was possible |
| `block_possible` | yes/no/unknown | Separates bad policy from impossible state |
| `throw_range` | yes/no/unknown | Explains close guard failures |
| `reaction_window_frames` | threat-to-contact time | Separates late reaction from wrong action |
| `frames_since_contact_reaction` | Time since latest hit/block/knockdown reaction | Separates neutral defense from wakeup/pressure defense |
| `wakeup_type` | none/face_up/face_down/quick_rise/tech_roll/unknown | Distinguishes oki decisions from neutral defense |
| `failure_reason` | late_guard/wrong_height/thrown/etc. | Training diagnostics |

Defense result values:

- `blocked`
- `hit_high`
- `hit_low`
- `hit_air`
- `chip`
- `thrown`
- `throw_tech`
- `escaped`
- `counterhit`
- `punished`
- `unknown`

For the current v351/v10 problem class, this is the key layer for proving
whether crouch guard failed because of:

- throw range
- wrong guard height
- late guard
- chip projectile
- multi-hit guard drop
- walking forward into contact
- recovery state where blocking was impossible

## Projectile Tracking

Projectile tracking must be independent from the owner routine snapshot.

Maintain a projectile ring buffer with:

- `projectile_event_id`
- `owner`
- `spawn_frame`
- `spawn_attack_event_id`
- `x`, `y`
- `vel_x`, `vel_y`
- `time_to_self`, `time_to_opp`
- `last_seen_frame`
- `result`
- `hit_target`
- `hit_count`
- `remaining_hits`
- `damage_hp`
- `chip_damage`
- `confidence`

Spawn attribution should link the projectile to the most recent fireball-like
attack event from the owner. If no such attack exists, create a projectile
event with `source=projectile_tracker`, `confidence=medium`, and
`failure_reason=no_recent_fireball_start`.

Projectile result values:

- `active`
- `hit`
- `blocked`
- `chip`
- `expired`
- `owner_changed_unknown`
- `unknown`

Multi-hit projectiles must remain alive until their engine evidence expires or
`remaining_hits` reaches zero when that can be inferred. Do not finalize a
projectile as expired after the first block/hit if later hits can still occur.

## Throw Tracking

Throw tracking is separate because blocking does not beat throws.

Throw start evidence:

- engine action/routine maps to throw
- close range
- current attack/kind_of_waza indicates throw family
- immediate target HP loss with throw routine evidence

Throw result values:

- `success`
- `tech`
- `whiff`
- `escaped`
- `unknown`

Throw fields:

- `throw_event_id`
- `actor`
- `target`
- `range_at_start`
- `defender_action_id`
- `target_valid_state`
- `target_invulnerable`
- `target_in_blockstun`
- `throw_tech_possible`
- `damage_hp`
- `damage_stun`
- `confidence`

This prevents "crouch guard failed" from hiding the true result "got thrown".

## Punish Tracking

Punish attribution answers whether an action was unsafe.

Create a punish event when:

- an attack event finalized as whiff/no-damage/recovery
- the same actor takes HP damage within a punish window
- the incoming attack is from the opponent and starts after or during recovery

Fields:

- `punish_event_id`
- `punished_attack_event_id`
- `punisher_attack_event_id`
- `punished_action_id`
- `punish_window_frames`
- `damage_hp`
- `range_bucket`
- `confidence`

This is critical for Shoryuken, Tatsu, close fireball, and random normals.

## Stun, Position, And Round Events

These events are not primary attack results, but they explain why later
decisions were or were not actionable.

`stun_state` event values:

- `hitstun_start`
- `hitstun_end`
- `blockstun_start`
- `blockstun_end`
- `knockdown_start`
- `wakeup_start`
- `wakeup_end`

Fields:

- `state_actor`
- `state_value`
- `source_event_id`
- `start_frame`
- `end_frame`
- `duration_frames`
- `actionable`

`position_event` values:

- `side_switch`
- `corner_trapped`
- `corner_escaped`
- `corner_push`

Fields:

- `actor`
- `target`
- `old_abs_dx`
- `new_abs_dx`
- `old_corner_dist`
- `new_corner_dist`
- `source_event_id`

`round_start` / `round_end` fields:

- `round_num`
- `episode_id`
- `event_frame`
- `winner`
- `reason`
- `final_self_hp`
- `final_opp_hp`
- `final_self_stun`
- `final_opp_stun`

Round events are replay anchors and boundary guards. They also make analyzers
validate that no pending combat event leaked into the next episode.

## Transition Schema v4 Summary Fields

Add transition summary fields after the event engine exists. These fields are
not the full event journal, only compact per-decision summaries.

Self attack summary:

- `self_attack_event_id`
- `self_attack_action_id`
- `self_attack_sub_action_id`
- `self_attack_result`
- `self_attack_damage_hp`
- `self_attack_damage_stun`
- `self_attack_chip_damage`
- `self_attack_contact_count`
- `self_attack_was_punished`
- `self_attack_projectile_event_id`
- `self_attack_source`
- `self_attack_confidence`
- `self_attack_failure_reason`

Self defense summary:

- `self_defense_event_id`
- `incoming_attack_event_id`
- `incoming_projectile_event_id`
- `incoming_throw_event_id`
- `incoming_action_id`
- `incoming_sub_action_id`
- `self_defense_action_id`
- `self_defense_result`
- `self_defense_damage_hp`
- `self_defense_damage_stun`
- `self_defense_range_bucket`
- `self_defense_guard_state`
- `self_defense_block_possible`
- `self_defense_failure_reason`
- `self_defense_source`
- `self_defense_confidence`

Opponent attack summary:

- `opp_attack_event_id`
- `opp_attack_action_id`
- `opp_attack_sub_action_id`
- `opp_attack_result`
- `opp_attack_damage_hp`
- `opp_attack_damage_stun`
- `opp_attack_chip_damage`
- `opp_attack_contact_count`
- `opp_attack_was_punished`
- `opp_attack_projectile_event_id`
- `opp_attack_source`
- `opp_attack_confidence`
- `opp_attack_failure_reason`

Opponent defense summary:

- `opp_defense_event_id`
- `opp_incoming_attack_event_id`
- `opp_incoming_projectile_event_id`
- `opp_incoming_throw_event_id`
- `opp_incoming_action_id`
- `opp_incoming_sub_action_id`
- `opp_defense_action_id`
- `opp_defense_result`
- `opp_defense_damage_hp`
- `opp_defense_damage_stun`
- `opp_defense_range_bucket`
- `opp_defense_guard_state`
- `opp_defense_block_possible`
- `opp_defense_failure_reason`
- `opp_defense_source`
- `opp_defense_confidence`

Resource delta summary:

- `delta_self_super_meter`
- `delta_opp_super_meter`
- `self_attack_meter_spent`
- `opp_attack_meter_spent`

Meter fields are required before EX/super outcomes can be used for reward
shaping. A whiffed EX/super is not only a whiff; it also spends resources.
These fields can remain `unknown` until the exact meter source is validated.

Side-explicit engine fields:

- `self_engine_action_id`
- `self_engine_sub_action_id`
- `self_engine_routine_1`
- `self_engine_routine_2`
- `self_engine_current_attack`
- `self_engine_kind_of_waza`
- `self_engine_label_source`
- `self_engine_lag_frames`
- `opp_engine_action_id`
- `opp_engine_sub_action_id`
- `opp_engine_routine_1`
- `opp_engine_routine_2`
- `opp_engine_current_attack`
- `opp_engine_kind_of_waza`
- `opp_engine_label_source`
- `opp_engine_lag_frames`

Raw edge/export fields that should return if they are removed from current
schema:

- `self_entered_hit_stop`
- `opp_entered_hit_stop`
- `self_entered_contact_state`
- `opp_entered_contact_state`
- `requested_attack_input_started`
- `requested_attack_became_active`
- `requested_attack_entered_state`
- `requested_attack_made_contact`
- `requested_attack_likely_whiffed`
- `overlay_attack_event_finalized`
- `overlay_attack_contact`
- `overlay_attack_whiff`
- `overlay_attack_active_count`
- `overlay_attack_contact_count`
- `overlay_attack_whiff_count`

These raw fields remain evidence, not final truth.

## C-Side Module Plan

Keep implementation under `src/rl/*`.

Recommended files:

- `src/rl/rl_combat_event.h`
- `src/rl/rl_combat_event.c`
- `src/rl/rl_combat_attribution.h`
- `src/rl/rl_combat_attribution.c`

Phase 0+1 should start with `src/rl/rl_combat_event.h` only unless executable
logic is genuinely needed. In Phase 0+1 the header should contain only the
evidence bitmask version and bit-position constants needed to keep C/Python
mapping stable. Defer event type/result/source/confidence/failure enums,
`rl_combat_event.c`, event structs, event id counters, pending-export rings, and
resolver helpers until later phases that actually consume them. This keeps the
evidence-only phase from adding dead code or tempting resolver assignments.

Responsibilities:

- define event structs/enums
- own fixed-size side/projectile event rings
- ingest `RLObservationV1` frame-end snapshots
- detect side-symmetric attack starts
- detect projectile spawns/results
- resolve contact/damage/defense outcomes
- finalize whiffs and punish events
- expose compact summaries to `rl_session.c`
- expose journal rows to the transition sender/export path

`rl_session.c` should remain the decision ledger and export coordinator. It
should not grow into a large combat attribution engine.

Phase 0+1 rollback gate:

- add a runtime/config gate for C evidence export. The Phase 0+1
  implementation uses `rl-agent-export-evidence`, documented in
  `docs/config.md`, with MiSTer OSD exposure as `RL Evidence Log (Restart)`
- default the first rollout to disabled until Python parser hardening and
  compatibility smokes pass
- when disabled, emit the current base transition row without Phase 0+1 evidence
  fields
- when enabled, emit the fixed Phase 0+1 evidence fields on every successfully
  evidence-extended row
- if the evidence extension fails at runtime, disable or skip evidence export
  for that row/run, increment visible telemetry, and fall back to a base row
  rather than emitting partial JSON
- do not let this gate affect reward, inference, action scheduling, or episode
  lifecycle

Full rollout export gates:

- keep export controls config-backed after the full combat event system ships.
  Config is the source of truth; OSD controls may toggle the same cached runtime
  flags, but must not create separate OSD-only state
- suggested final keys:
  - `rl-agent-export-evidence`
  - `rl-agent-export-combat-events`
  - `rl-agent-export-event-summaries`
- `rl-agent-export-combat-events` controls whether the remote PC persists the
  sibling combat-event NDJSON file for journal rows
- `rl-agent-export-event-summaries` controls whether transition rows include
  compact schema-v4 event summary fields
- event summary fields that contain `*_event_id` references require
  `rl-agent-export-combat-events = on`, because those ids must resolve to the
  sibling event journal. If combat-event export is off, either disable
  event-id summaries or emit only clearly documented aggregate summaries with no
  event references
- after move-family validation and event-journal validation pass, the final
  defaults may be on for full debug/replay builds, but users must be able to
  turn combat event output off for low-overhead training/logging runs
- if toggled from OSD mid-run, analyzers must treat the log as mixed-output:
  some envelopes may have event journals/summaries and later envelopes may not.
  The receiver must report coverage counts instead of assuming uniform export
  across the whole file

## Python Tooling Plan

Update the Python side in two passes: parser tolerance before C exports any new
evidence fields, then full schema/event analysis after the C-side event schema
is stable.

Tools:

- `tools/rl_probe_server.py`
- `tools/analyze_rl_transitions.py`
- `tools/train_dqn_learner.py`
- `tools/compare_dqn_models.py`
- optional new `tools/analyze_rl_combat_events.py`

Required Python behavior:

- before C exports any new evidence fields, parse transition rows tolerantly:
  unknown keys must not crash analyzers, and known evidence fields must be
  available to strict validation modes
- harden the NDJSON-to-replay-buffer mapping functions specifically; raw
  `json.loads()` already tolerates extra keys, but strict dataclass/NamedTuple,
  CSV, numpy, and replay feature builders must ignore fields outside their
  declared input schema
- feature builders must use explicit allowlists for the row fields they need.
  They must not iterate over `row.keys()` to create default features, blindly
  pass the whole transition row into learners, or let newly added root keys
  become features without an explicit schema/reward decision
- parse transition schema v4
- parse combat event schema v1
- decode Phase 0+1 rows through the per-row `evidence_bitmask_version` and a
  fixed versioned mapping table. Unknown versions must never be guessed:
  default parsers warn and return `evidence = None` while continuing to parse
  the transition row; strict audit/debug modes fail clearly.
- provide a developer-only evidence expansion mode in `tools/rl_probe_server.py`
  and `tools/analyze_rl_transitions.py`, such as `--expand-evidence` or
  `--debug-bitmask`, so bitmask fields can be printed as human-readable
  dictionaries during smoke/debug work. `tools/compare_dqn_models.py` should at
  least expose reserved-bit diagnostics or share the same decoder in a debug
  path so comparison smokes can detect parser drift
- `tools/analyze_rl_transitions.py` must also support an optional expanded
  human-readable output file, for example
  `--expand-evidence --output-expanded PATH`. This file should preserve the
  original row identity and add decoded evidence names/dictionaries for audit.
  The compact source transition log remains unchanged and remains the default
  learner/debug contract.
- keep `evidence_flags_lo`, `evidence_flags_hi`, and `ep_overlay_*` fields out
  of DQN/replay feature lists; add an explicit guard/comment near
  `DQN_FEATURE_NAMES` and a smoke assertion that these fields are not default
  learner features
- model metadata `feature_names` must also be guarded. If a loaded model or
  training manifest includes `evidence_` or `ep_overlay_` feature names before
  the later learner-adoption gate, Python should warn and strip/fail according
  to the tool's strictness instead of silently honoring those metadata fields
- validate event id references
- summarize attack success/failure by side/action/range
- summarize defense failures by incoming action/result/range
- summarize projectile lifecycle
- summarize throw success/tech/whiff
- report unknown attribution rates and failure reasons
- keep trainer ingestion gated behind explicit flags until validation passes

Trainer and inference code must ignore Phase 0+1 evidence fields by default.
New evidence is parser-visible for audit/analyzer checks only.

## Episode Boundary Contract

No combat event can cross an episode boundary.

When `RLSession_OnEpisodeEnd()` or equivalent round-close logic runs:

- emit `round_end` with winner, terminal reason, final HP/stun/meter, and frame
- finalize every pending attack event as `unknown`, `interrupted`, or
  `round_ended` according to available evidence
- finalize every pending projectile as `expired_round_end` unless its hit/block
  was already consumed before the episode ended
- finalize pending throw events as `unknown_round_end`
- emit attribution failures for any unconsumed HP/stun delta
- flush active rings for self, opponent, projectile, and throw trackers
- reset per-episode active-index lists
- keep the global `event_id` counter increasing across the run

The next episode must start from empty active rings. Any event row whose
`episode_id` differs from the transition or combat batch it is attached to is a
schema error.

## Schema Compatibility Contract

Transition schema v4 and combat event schema v1 should be rolled out together,
but they serve different purposes.

- Transition v3 logs remain readable by v3 analyzers and should fail clearly in
  v4-only trainer modes.
- Transition v4 rows may contain compact event summary ids and result enums.
- The full event journal is carried in the same exported batch/envelope as the
  transition rows that crossed those events.
- The remote PC should persist transition rows and event rows as two separate
  NDJSON files after receiving an atomic batch, but MiSTer must not produce
  separate unsynchronized streams. The two files must be reconciled from the
  same envelope identity and treated as incomplete if either side of the batch
  is missing.
- Config-backed export gates control which layers are persisted or embedded.
  If `rl-agent-export-combat-events` is off, transition summaries must not
  contain event-id references unless those ids are resolvable from another
  explicitly documented journal source. Prefer disabling event-id summaries or
  emitting aggregate-only summaries in that mode.
- Python analyzers must validate that every transition summary id references an
  event from the same run and episode.
- Python tools should warn, not silently guess, when v4 summary fields are
  absent from older v3 logs.
- Phase 0+1 evidence fields may be added before transition v4 only when Python
  parsers have first been updated to ignore unknown keys and to expose the known
  evidence fields to explicit audit checks. They remain debug/evidence-only and
  must not change reward, inference, or default training behavior.
- Schema v4 should keep `engine_action_id` and related generic `engine_*`
  fields as deprecated aliases for self-side attribution while adding
  `self_engine_*` fields. Python readers should prefer `self_engine_*` and
  fall back to generic `engine_*` for v3/v4 compatibility. Remove the generic
  alias only in a later schema after analyzers and trainers have migrated.
- Event journal export may use a separate internal `event_batch_payload`, but
  the flush conditions and network envelope must be synchronized with the
  transition batch. The remote receiver should validate event rows before
  resolving transition summary references.

## Runtime Evidence Audit

Before implementing event resolution, Phase 0+1 must audit every evidence field
used by the plan.

For each field, record one of:

- `declared_and_filled`
- `declared_not_filled`
- `missing`
- `filled_but_not_exported`
- `exported_but_untrusted`

The audit must include:

- `requested_attack_*`
- `overlay_attack_*`
- hitstop/contact/damage-state edges
- `delta_self_hp` / `delta_opp_hp`
- stun deltas
- projectile fields
- routine ids
- engine action fields
- any proposed meter/wakeup/target-state fields

If a field is `declared_not_filled`, exporting it is not enough; the phase must
either implement the accumulator or mark the field unavailable.

Phase 0+1 starts from this verified seed list of currently useful evidence
fields that are declared and accumulated in `RLDecisionLedgerEntry`, but are not
yet exported in transition NDJSON. The implementation phase must re-check the
table against the exact source revision before changing C export.

| Field | Current status | Semantics | Accuracy / limitation | Phase 0+1 export use |
| --- | --- | --- | --- | --- |
| `requested_attack_input_started` | filled, not exported | per-decision flag | request/input evidence, not proof that the game accepted an attack | evidence-only |
| `requested_attack_became_active` | filled, not exported | per-decision flag | accepted/active heuristic for the requested action window, not a final hit/block result | evidence-only |
| `requested_attack_entered_state` | filled, not exported | per-decision flag | routine/attack-state evidence during the requested action window | evidence-only |
| `requested_attack_made_contact` | filled, not exported | per-decision flag | heuristic: true if contact/hitstop/damage evidence occurred during the decision window, not necessarily from the requested attack | evidence-only |
| `requested_attack_likely_whiffed` | filled, not exported | heuristic per-decision flag | medium-trust heuristic only; do not treat as final whiff attribution | evidence-only, medium trust |
| `requested_jump_started` | filled, not exported | per-decision flag | movement edge for the controlled side, not an airborne attack label | evidence-only |
| `requested_movement_succeeded` | filled, not exported | heuristic per-decision flag | movement-span heuristic, not proof of intentional spacing success | evidence-only |
| `observed_attack_state_started` | filled, not exported | per-decision attack edge summary | observed game-state edge; owner/action attribution is not resolved | evidence-only |
| `observed_attack_code_changed` | filled, not exported | per-decision attack edge summary | `current_attack` edge evidence only; action mapping remains character/move-family dependent | evidence-only |
| `observed_attack_counter_started` | filled, not exported | per-decision attack edge summary | attack-counter edge evidence only | evidence-only |
| `overlay_attack_event_finalized` | filled, not exported | overlay event edge | overlay lifecycle signal, not a full combat event journal row. Must be latched from finalized overlay event sequence evidence, not read from transient latest-overlay state at transition formatting time. | evidence-only |
| `overlay_attack_contact` | filled, not exported | overlay event result flag | overlay result signal with known multi-hit/clash tolerance. Must be consumed from the finalized overlay event sequence/result that this transition owns, not from a later frame's `last_overlay_*` value. | evidence-only |
| `overlay_attack_whiff` | filled, not exported | overlay event result flag | overlay result signal, not a final move-family whiff label. Must be consumed from the finalized overlay event sequence/result that this transition owns, not from a later frame's `last_overlay_*` value. | evidence-only |
| `overlay_attack_active_count` | filled, not exported | episode-cumulative counter | overlay-pipeline count only, based on the existing attack overlay / `Attack_Counter` detection path; not all engine attack starts. Snapshot value is captured when the transition is finalized, so values should reset at episode start and remain monotonic inside an episode, but rows in the same episode may differ. | evidence-only counter |
| `overlay_attack_contact_count` | filled, not exported | episode-cumulative counter | overlay-pipeline contact finalization count only; not a contact resolver result and not all contact in the engine. Snapshot value is captured when the transition is finalized, so values should reset at episode start and remain monotonic inside an episode, but rows in the same episode may differ. | evidence-only counter |
| `overlay_attack_whiff_count` | filled, not exported | episode-cumulative counter | overlay-pipeline whiff finalization count only; not a final move-family whiff label. Snapshot value is captured when the transition is finalized, so values should reset at episode start and remain monotonic inside an episode, but rows in the same episode may differ. | evidence-only counter |
| `self_attack_started` | filled, not exported | per-decision self attack edge | side-specific edge evidence only; no result/confidence/failure reason yet | evidence-only |
| `opp_attack_started` | filled, not exported | per-decision opponent attack edge | side-specific edge evidence only; no result/confidence/failure reason yet | evidence-only |
| `self_airborne_started` | filled, not exported | per-decision movement edge | movement state edge, not jump-attack attribution | evidence-only |
| `opp_airborne_started` | filled, not exported | per-decision movement edge | movement state edge, not jump-attack attribution | evidence-only |
| `self_entered_hit_stop` | filled, not exported | per-decision combat edge | contact evidence; source attack is unresolved in Phase 0+1 | evidence-only |
| `opp_entered_hit_stop` | filled, not exported | per-decision combat edge | contact evidence; source attack is unresolved in Phase 0+1 | evidence-only |
| `self_entered_contact_state` | filled, not exported | per-decision contact/block/hit edge | broad contact/reaction evidence, not a block-vs-hit split | evidence-only |
| `opp_entered_contact_state` | filled, not exported | per-decision contact/block/hit edge | broad contact/reaction evidence, not a block-vs-hit split | evidence-only |
| `self_entered_damage_state` | filled, not exported | per-decision damage/hit edge | damage-state edge, not consumed/attributed damage | evidence-only |
| `opp_entered_damage_state` | filled, not exported | per-decision damage/hit edge | damage-state edge, not consumed/attributed damage | evidence-only |
| `self_throw_started` | exported in schema v9 root; evidence bit 23 when evidence gate is on | per-decision throw edge | throw-like edge evidence; no throw success/tech/whiff result yet | evidence-only |
| `opp_throw_caught_started` | exported in schema v9 root; evidence bit 24 when evidence gate is on | per-decision throw-caught edge | throw-caught edge evidence; source/result unresolved | evidence-only |

Phase 0+1 must also audit proposed but not-yet-proven evidence:

- self/opponent invulnerability or actionable target-state source
- super meter deltas and meter-spend evidence
- `time_to_opp` or equivalent projectile-to-target timing evidence
- wakeup/knockdown state source and whether it is safe to export as evidence

If these proposed fields cannot be sourced reliably, mark them unavailable
instead of creating zero-filled placeholders.

Treat the audit as two passes. Pass 1 exports only the filled seed evidence
fields in bitmask v1 plus the episode counters. Pass 2 records proposed fields
as available, unavailable, or future-work in the engineering log; proposed
fields do not block Phase 0+1 completion and must not be emitted as always-zero
placeholders.

Overlay evidence contamination guard:

- `ep_overlay_attack_*_count` fields are cumulative snapshots and may advance as
  later frames finalize more overlay events. That is not contamination as long
  as analyzers treat them only as episode-cumulative counters.
- Per-decision overlay flags are different: `overlay_attack_event_finalized`,
  `overlay_attack_contact`, and `overlay_attack_whiff` must describe the overlay
  event(s) assigned to the transition row, not whichever overlay event happened
  to be latest when the row is formatted.
- Do not derive per-decision overlay flags by reading transient
  `remote_debug.last_overlay_attack_*` values at transition formatting time.
  Latch the result when an overlay event finalizes, give it a sequence/id, and
  let the ledger entry consume only unlogged finalized overlay evidence.
- After a ledger row consumes an overlay event sequence, mark that sequence as
  logged/consumed so later rows cannot duplicate it.
- If multiple overlay events finalize inside one decision window and Phase 0+1
  cannot represent all of them, keep the existing boolean summary as
  evidence-only, record the limitation in the audit/engineering log, and let
  Phase 2+ event journals carry the one-row-per-event truth model.

Phase 0+1 must also inspect `RLSession_FormatTransitionLogLine()`. It currently
uses a single `SDL_snprintf()` into `line[2048]`; restoring the seed evidence
fields is expected to fit only narrowly, and schema v4 will not. The phase must
not solve this by adding a large hot-path stack buffer or a shared static/BSS
scratch buffer. Phase 0+1 should use one heap-owned reusable formatter buffer:
a file-scope `char*` pointer plus capacity, not a file-scope array. Allocate it
with `SDL_malloc()` from explicit RL session functions such as
`RLSession_AllocFormatBuffer()` and free it from the matching
`RLSession_FreeFormatBuffer()`. Wire those functions into the existing RL net
lifecycle: allocate from `RLNet_Init()` after disabled cleanup/config setup, and
free from `RLNet_Shutdown()` / `RLNet_InitDisabled()` before reinitialization.
The implementation notes must name the exact allocate and free functions. Pass
the buffer to the formatter as `char* buf, size_t buf_size`. Do not allocate,
realloc, or free the formatter buffer per frame. The starting capacity target
is 4096 bytes, but Phase 0+1 must record the measured current max row length,
the worst-case evidence addition, and the chosen capacity before later phases
add event summaries. The 2026-05-05 live gate-off/gate-on smoke recorded max row
lengths of 1752 bytes and 1937 bytes respectively, so explicit formatter
micro-timing is not a Phase 0+1 blocker unless live testing shows a visible
performance regression.

Do not use `SDL_GetTicks()` for sub-millisecond formatter timing. Prefer
`SDL_GetPerformanceCounter()` / `SDL_GetPerformanceFrequency()` when available;
if the MiSTer SDL profile lacks a high-resolution counter, document the fallback
timer and its resolution in the engineering log before accepting timing results.

Any formatter or append-style formatter must treat `SDL_snprintf()` truncation
correctly. Its return value is the would-have-written length, not the actual
appended length when truncated. The existing `written > 0` style check is not
sufficient because truncated JSON may still return a positive value. Structure
Phase 0+1 formatting as a safe base-row formatter plus a gated evidence
extension:

- base-row formatting failure means the whole row must be dropped
- evidence-extension failure means clear the buffer, retry the base row once
  without evidence, increment evidence fallback/format telemetry, and do not
  append evidence fields for that row
- no partial JSON may ever be appended to local NDJSON, transition batches, or
  network payloads

Use this pattern for every append:

```c
if (buf == NULL || buf_size == 0 || offset >= buf_size) {
    return RL_TRANSITION_FORMAT_OVERFLOW;
}
SDL_assert(offset < buf_size);
size_t remaining = buf_size - offset;
int written = SDL_snprintf(buf + offset, remaining, ...);
if (written < 0 || (size_t)written >= remaining) {
    buf[0] = '\0';
    return RL_TRANSITION_FORMAT_TRUNCATED;
}
SDL_assert(offset + (size_t)written <= buf_size);
offset += (size_t)written;
if (offset > buf_size) {
    buf[0] = '\0';
    return RL_TRANSITION_FORMAT_OVERFLOW;
}
```

If evidence formatting returns an overflow/truncation/error status, the caller
must not append the partial buffer. It should retry the base row without
evidence and increment visible debug/telemetry counters so a too-small evidence
buffer is caught quickly. If base-row formatting also fails, drop the entire
transition row; broken JSON is worse than a missing row.

The table above names logical evidence fields, not necessarily individual JSON
keys. When the runtime evidence-export gate is enabled, Phase 0+1 export is
fixed as root-level compact numeric fields:

- `evidence_bitmask_version = 1`
- `evidence_flags_lo`
- `evidence_flags_hi`
- `ep_overlay_attack_active_count`
- `ep_overlay_attack_contact_count`
- `ep_overlay_attack_whiff_count`

These six fields are emitted together on every evidence-enabled transition row.
Do not emit a partial subset of the six fields. `evidence_bitmask_version` is
per-row, not session metadata, so a single NDJSON row can be decoded without
external state. Both `evidence_flags_lo` and `evidence_flags_hi` are always
present; `0` means no bits are set, not field absent. Rows emitted while the
runtime export gate is disabled, or rows that fall back after an evidence
formatter failure, keep the base v3-compatible shape and omit all six evidence
fields.

C-to-JSON counter mapping:

- `remote_debug.episode_attack_active_count` /
  `RLDecisionLedgerEntry.overlay_attack_active_count` exports as
  `ep_overlay_attack_active_count`
- `remote_debug.episode_attack_contact_count` /
  `RLDecisionLedgerEntry.overlay_attack_contact_count` exports as
  `ep_overlay_attack_contact_count`
- `remote_debug.episode_attack_whiff_count` /
  `RLDecisionLedgerEntry.overlay_attack_whiff_count` exports as
  `ep_overlay_attack_whiff_count`

Keep the JSON `overlay` name because these counts come from the existing
overlay attack event pipeline, not from the future all-combat event resolver.

Do not emit 28 flat boolean root keys and do not emit a nested `evidence`
object in Phase 0+1. Episode-cumulative counters use the `ep_` prefix so Python
analyzers cannot confuse them with per-decision flags.

`evidence_flags_lo` and `evidence_flags_hi` are unsigned 32-bit values in C
(`uint32_t` / local `u32`) and must be printed as non-negative JSON decimals.
Use `PRIu32` where available; `%u` is acceptable only with an explicit cast to
the exact unsigned type used by the platform formatter. Never print these
fields with `%d` or a signed type. Python decoders must first validate that the
parsed value is an integer in the inclusive range `0..0xffffffff`; a negative
value such as `-1` is a malformed signed C export and must not be rescued by
masking. Only after that validation should Python mask with `0xffffffff` before
bit tests.

Phase 0+1 bitmask v1 mapping:

| Bit | Logical evidence field |
| --- | --- |
| 0 | `requested_attack_input_started` |
| 1 | `requested_attack_became_active` |
| 2 | `requested_attack_entered_state` |
| 3 | `requested_attack_made_contact` |
| 4 | `requested_attack_likely_whiffed` |
| 5 | `requested_jump_started` |
| 6 | `requested_movement_succeeded` |
| 7 | `observed_attack_state_started` |
| 8 | `observed_attack_code_changed` |
| 9 | `observed_attack_counter_started` |
| 10 | `overlay_attack_event_finalized` |
| 11 | `overlay_attack_contact` |
| 12 | `overlay_attack_whiff` |
| 13 | `self_attack_started` |
| 14 | `opp_attack_started` |
| 15 | `self_airborne_started` |
| 16 | `opp_airborne_started` |
| 17 | `self_entered_hit_stop` |
| 18 | `opp_entered_hit_stop` |
| 19 | `self_entered_contact_state` |
| 20 | `opp_entered_contact_state` |
| 21 | `self_entered_damage_state` |
| 22 | `opp_entered_damage_state` |
| 23 | `self_throw_started` |
| 24 | `opp_throw_caught_started` |
| 25-63 | reserved, must be zero in bitmask v1 |

The 25 per-decision boolean/edge flags use bits 0-24. The three
episode-cumulative counters use the separate `ep_` numeric fields and are not
bitmask bits.

Adding, removing, or reordering bits requires a new `evidence_bitmask_version`.
Python decoders must not decode unknown versions. Reserved bits set in a known
version are a warning, not a hard parse failure: expand known bits, set
`reserved_bits_set = true` in debug expansion, increment a per-log
`reserved_bits_set_count`, track the maximum reserved mask observed, and report
the count prominently. Probe/analyzer tooling should emit a visible warning to
`stderr` at episode end or stats-print time, for example:
`WARNING: reserved evidence bits set N times in this episode, max_lo=0x..., max_hi=0x...`.

Parser hardening is a prerequisite for export. Python tools must pass a
smoke that ignores unknown transition keys and can optionally assert the known
Phase 0+1 evidence fields before C starts emitting those fields. For feature
builder compatibility, prefer injecting synthetic evidence fields directly into
row dictionaries and passing those dictionaries to replay/feature builder
functions instead of rewriting NDJSON and re-reading it; this avoids false
failures from key ordering or JSON float reserialization. If bitmasks are used,
the smoke must also prove Python expands every bit back into the logical
evidence names in the audit table.

## Confidence Matrix

This matrix applies to Phase 2+ combat events only. Phase 0+1 evidence bitmask
fields are raw edges/counters and do not carry source, confidence, or failure
reason values.

Confidence must be mechanically defined per event type. These are initial
rules; they should become C enum helpers and analyzer checks.

| Event | High confidence | Medium confidence | Low confidence |
| --- | --- | --- | --- |
| `attack_start` | side engine action id is nonzero and routine/attack edge agrees | policy/input attack plus matching attack routine edge | routine attack state only |
| `projectile_spawn` | projectile owner/position edge plus recent fireball attack event | projectile owner/position edge without recent fireball event | projectile active snapshot only |
| `throw_start` | engine throw action/routine plus close range | throw-like routine/current_attack plus close range | HP delta at close range with no better source |
| `contact` | hitstop/contact edge plus matching active event | HP/stun delta plus active event | contact state snapshot only |
| `defense_result` | incoming high-confidence event plus actual guard/hit/throw evidence | incoming medium-confidence event plus HP/contact evidence | heuristic routine/contact split |
| `projectile_result` | projectile id plus HP/chip/contact consumed | projectile proximity plus HP/chip/contact | projectile disappeared near target |
| `punish` | finalized unsafe event plus later high-confidence incoming damage inside punish window | finalized unsafe event plus medium-confidence incoming damage | HP loss after whiff with weak timing only |

`unknown` is required when evidence conflicts or when no rule reaches low
confidence. Trainer use must default to high-confidence only.

## Deferred Enum Foundation Contract

Numeric enum namespaces must be defined before any event summary or event
journal fields become public, but only when the phase that consumes them starts:

- Phase 0+1: define only evidence bitmask version/bit constants.
- Phase 2+: define `RLCombatEventType` when event rows/rings exist.
- Phase 3+ or first attribution phase: define `RLCombatEventSource` and
  `RLCombatConfidence` when source/confidence values are exported.
- Phase 6+: define `RLCombatFailureReason` when unresolved attribution failures
  are emitted.
- Later resolver phases: define `RLCombatAttackResult`,
  `RLCombatDefenseResult`, `RLCombatProjectileResult`, and
  `RLCombatThrowResult` when those result families are exported.

Use explicit C enum values with stable storage ranges. `0` means unknown/none
for every enum, and `255` is reserved for future incompatibility/fatal sentinel
values when the field is stored as `u8`. Python owns enum-to-string display for
NDJSON analysis; C hot-path export should use numeric values unless a debug
tool explicitly asks for names.

When those later enums are introduced, do not reuse generic names such as
`SOURCE_ENGINE` across unrelated enum families. Prefix constants with the enum
family, for example `RL_COMBAT_SOURCE_ENGINE`, `RL_COMBAT_CONFIDENCE_HIGH`, and
`RL_COMBAT_FAILURE_NO_ACTIVE_ATTACK`.

Phase 0+1 bitmask-constant work is a namespace/compatibility foundation only.
Do not add C logic that assigns event types, attack results, defense results,
projectile results, throw results, punish labels, confidence, source, or failure
reasons from gameplay state. The Phase 0+1 evidence bitmask may only copy
existing ledger booleans/counters and audited observation fields into versioned
export fields.

## Implementation Phases

This is a full plan, not the minimal path.

### Phase 0+1: Foundation, Evidence Audit, And Evidence Export

Files:

- `docs/agent-memory/remote-rl-combat-event-attribution-plan.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`
- `src/rl/rl_session.c`
- `src/rl/rl_session.h`
- `src/rl/rl_combat_event.h` for evidence bitmask constants only
- `tools/rl_probe_server.py`
- `tools/analyze_rl_transitions.py`
- other Python parsers only if they currently reject unknown fields

Work:

- harden Python transition parsers before C emits new evidence fields
- document event model and rollout
- list schema v4 summary fields
- list combat event journal fields
- decide evidence bitmask version/bit constants and compatibility strategy in
  `rl_combat_event.h`; do not define event/result/failure enums yet
- audit every proposed evidence field as declared/filled/exported/trusted in a
  table with semantics and training-safety notes
- add a runtime/config evidence-export gate, document the final config key, and
  keep reward/inference behavior unchanged when the gate is toggled
- use the fixed Phase 0+1 bitmask v1 export shape:
  `evidence_bitmask_version`, `evidence_flags_lo`, `evidence_flags_hi`, and
  `ep_overlay_attack_*_count`
- replace or resize the current 2048-byte transition JSON line path with a
  session-owned reusable formatter buffer; add a safe `SDL_snprintf()`
  pre-guard and truncation guard before adding fields
- fix the pre-existing transition formatter append guard before adding new
  evidence fields; a truncated positive `SDL_snprintf()` return must not be
  treated as a valid line length
- export existing internal evidence fields that are currently missing from live
  NDJSON
- implement missing accumulators only when the field is already part of the
  current evidence contract; otherwise mark it unavailable
- measure transition-line formatting cost before and after evidence export
- keep them marked debug/evidence-only
- do not change reward or inference
- create zero event structs, zero event rings, and zero event JSON arrays in
  Phase 0+1; the phase only reads existing decision/observation fields into the
  evidence bitmask and episode-counter exports

Validation:

- documentation review
- `git diff --check`
- Python round-trip parse smoke before C export: unknown transition keys do not
  crash, known evidence fields are exposed to analyzer/audit checks, and trainer
  code still ignores evidence by default
- runtime gate smoke confirms evidence fields are absent when the gate is off,
  present as the full six-field set when the gate is on, and toggling the gate
  does not change reward, inference, action scheduling, or episode lifecycle
- v3 compatibility smoke loads a real log without Phase 0+1 fields and confirms
  missing `evidence_bitmask_version` produces graceful no-evidence behavior
- bitmask mapping smoke proves C bit positions and Python decoder names match
  for `evidence_bitmask_version = 1`; default parsing warns and leaves
  evidence unexpanded for unknown versions, strict audit mode fails, and
  reserved bits produce a visible count
- hi-bit future-proof smoke injects a synthetic row with
  `evidence_flags_hi = 0x80000000` and verifies Python reports reserved bit 63
  without crashing
- mixed-version smoke injects rows with `evidence_bitmask_version = 1` and an
  unknown version in the same log; analyzers report the mixed versions, expand
  v1 rows, and keep unknown-version rows usable with `evidence = None`
- hardcoded bit constant smoke asserts representative C/Python constants, for
  example the bit index for `self_entered_hit_stop`, so inserting a new enum in
  the middle cannot silently shift later bits
- developer debug smoke proves `--expand-evidence` or `--debug-bitmask` prints a
  human-readable dictionary for silent-zero investigation
- expanded-log smoke proves `tools/analyze_rl_transitions.py --expand-evidence`
  can write an optional human-readable NDJSON/debug file without modifying the
  compact source log and with row identity preserved
- compatibility smoke loads a real v3 log, injects synthetic Phase 0+1 evidence
  fields, and verifies replay/trainer feature builders produce unchanged
  default features/actions; inject evidence into in-memory row dictionaries for
  feature-builder checks instead of relying on NDJSON rewrite/readback
- compatibility smoke must cover `tools/train_dqn_learner.py`,
  `tools/compare_dqn_models.py`, `tools/analyze_rl_transitions.py`, and the
  replay/import path used by `tools/rl_probe_server.py`
- learner feature guard smoke asserts `evidence_flags_lo`,
  `evidence_flags_hi`, `evidence_bitmask_version`, and `ep_overlay_*` fields are
  absent from default DQN/replay feature names and absent/blocked in model
  metadata `feature_names`
- deterministic trainer zero-leak smoke runs the same seeded feature/training
  path on baseline rows and rows with synthetic Phase 0+1 evidence fields, then
  verifies default features/actions and, where the training path is deterministic
  enough, model/loss outputs remain bit-for-bit identical
- local transition row schema smoke
- every exported evidence field has at least one scripted or natural-log
  invariant, not only "field appears"
- pre-existing truncation guard smoke first proves the old `written > 0` style
  guard would accept a truncated positive return, then proves the fixed guard
  rejects it before evidence fields are added
- broken JSON/fallback smoke forces an undersized evidence formatter buffer and
  proves no partial JSON line is appended to the local log, transition batch, or
  network payload; evidence extension fails back to a complete base row, and
  Python receivers do not see `JSONDecodeError` from half-written rows
- buffer guard proves every normally formatted transition line fits in the
  configured reusable/bounded buffer
- C-side memory/stack guard proves the formatter does not add large stack
  allocations and does not leak heap/session-owned buffers across long episodes
- compare overlay counters against OSD counters
- episode-counter lifecycle smoke proves `ep_overlay_attack_*_count` values
  reset at episode boundaries and are monotonic snapshots within an episode.
  Same-episode rows are allowed to have different values because entries may
  finalize at different times; decreases inside one episode or nonzero carry
  into a new episode are failures
- overlay contamination smoke proves per-decision `overlay_attack_contact` /
  `overlay_attack_whiff` are latched from the overlay event sequence assigned to
  the row, not from a later finalized event's transient `last_overlay_*` state;
  repeated consumption of the same overlay sequence by multiple rows is a
  failure
- deferred performance check: measure `RLSession_FormatTransitionLogLine()` cost
  on the closest available target before the full combat-event journal ships, or
  earlier if live/intermediate testing shows visible performance symptoms. Leave
  room under the 500us attribution budget; if formatting alone exceeds 200us
  p95, stop and consider a builder/batched format change
- run a worst-case formatter smoke during dense contact/effect frames where both
  sides attack and multiple evidence flags/counters are set
- run an all-flags formatter stress row with `evidence_flags_lo = 0x01ffffff`,
  `evidence_flags_hi = 0`, and `ep_overlay_*` counters set to large test values
  such as `999` to prove capacity and truncation behavior

Minimum Phase 0+1 evidence invariants:

- `requested_attack_became_active` is nonzero in scripted `stand-hp` or
  `shoryuken-*` logs where an accepted attack starts
- `self_entered_hit_stop` or `opp_entered_hit_stop` is nonzero in a scripted
  hit/contact smoke
- `requested_attack_likely_whiffed` is nonzero in a scripted far normal/special
  whiff smoke and is treated as medium-trust evidence only
- `overlay_attack_contact_count + overlay_attack_whiff_count` is within the
  documented tolerance of `overlay_attack_active_count`; tolerance must account
  for multi-hit and clash/projectile-nullification cases where contact is not
  one-to-one with an active attack event
- throw edge fields are nonzero in scripted close throw/throw-caught smoke or
  explicitly marked unavailable for the next phase
- parser/analyzer output distinguishes per-decision flags from
  episode-cumulative counters
- `ep_overlay_attack_*_count` maps from the documented C fields to the documented
  JSON keys and counts only the overlay attack event pipeline
- per-decision overlay flags are sequence-latched/consumed evidence; a later
  overlay event cannot overwrite an earlier row's contact/whiff result before
  export

Done when:

- plan is linked from the main remote RL plan
- Milestone 6 checklist has explicit event-attribution tasks
- the evidence audit table exists in the engineering log and names every field
  exported in Phase 0+1
- `rl_combat_event.h` defines Phase 0+1 evidence bitmask constants without
  executable dead code, event/result enums, event ids, or resolver helpers
- Python parsers tolerate unknown keys and expose known evidence fields in audit
  mode before C export lands
- runtime evidence-export gate, transition line buffer sizing, session
  ownership, pre-guard/truncation checks, fallback-to-base-row behavior, and
  bitmask mapping/versioning are documented and verified
- analyzers can count accepted attacks/contact/whiffs from evidence fields while
  keeping them out of trainer reward/inference paths

Suggested Phase 0+1 commit order:

1. Fix the existing transition formatter truncation guard and add telemetry for
   truncated/failed transition formatting. Do not add evidence fields yet.
   Implemented locally on 2026-05-05.
2. Add the reusable formatter buffer lifecycle:
   `RLSession_AllocFormatBuffer()` / `RLSession_FreeFormatBuffer()` in
   `rl_session.*`, called from `RLNet_Init()` / `RLNet_Shutdown()` or their
   equivalent re-init paths. Replace the stack `line[2048]` path only after the
   lifecycle is proven. Implemented locally on 2026-05-05.
3. Add `rl_combat_event.h` with evidence bitmask version/bit constants only.
   Do not add `rl_combat_event.c`, event structs, event ids, event type/result
   enums, source/confidence/failure enums, or resolver helpers. Implemented
   locally on 2026-05-05.
4. Harden Python parsers and feature builders:
   `--expand-evidence` / `--debug-bitmask`, reserved-bit warnings, negative flag
   rejection, mixed-version reporting, hi-bit smoke, optional expanded evidence
   output, and feature-name denylist guards. Analyzer expansion and feature-name
   denylist guards implemented locally on 2026-05-05; `--debug-bitmask` remains
   analyzer-covered by `--expand-evidence` unless compare-specific output is
   needed later.
5. Add the runtime/config evidence-export gate and C evidence export. Build
   `evidence_flags_lo/hi` from audited ledger fields and export the three
   documented `ep_overlay_*` counters from the documented C fields. Implemented
   locally on 2026-05-05; live gate off/on smoke remains pending.
6. Run the full validation matrix, update the audit table/engineering log with
   measured row sizes, formatter timing, counter lifecycle findings, and any
   unavailable proposed evidence fields.

Fallback plan:

- If heap allocation through the RL net/session lifecycle is blocked, do not
  silently switch to a stack buffer or static/BSS array. Stop and document the
  lifecycle blocker before choosing a temporary exception.
- If evidence formatting fails in live smoke, leave the runtime gate off and
  keep base transition rows flowing while the evidence formatter is repaired.

### Phase 2: Attack Event Rings

Files:

- `src/rl/rl_combat_event.*`
- `src/rl/rl_session.c`

Implementation status:

- 2026-05-05 Phase 2A implemented the fixed-size self/opponent attack-event
  ring foundation in `src/rl/rl_combat_event.*`.
- Event ids are run-wide, monotonic, and nonzero; ring slots can reuse empty or
  finalized events, but active attack-event slots are never overwritten.
- `rl_session.c` now calls combat-event begin/flush/reset hooks from the
  remote runtime's run/episode lifecycle. Episode-boundary flush finalizes any
  still-active attack events as explicit unknowns.
- 2026-05-05 Phase 2B creates self/opponent attack events from observation
  attack-start edges: current-attack 0->nonzero, attack-counter delta, or
  attack-routine entry. Each event attaches run/episode/decision/frame,
  side, character, routine 1/2, current attack, kind-of-waza, and self-side
  policy/input context when available.
- If a new attack-start edge appears for a side while that side still has an
  active attack event, the previous active event is finalized as
  `UNKNOWN + SUPERSEDED_BY_NEW_START`. This is a ring-hygiene rollover only,
  not hit/block/whiff attribution.
- 2026-05-05 Phase 2C adds conservative basic finalization windows. A clean
  non-projectile event may become `WHIFF + BASIC_WHIFF_WINDOW` only after the
  actor leaves attack state, the minimum whiff age is reached, and the event has
  not seen target contact/damage, projectile, throw, or projectile-like policy
  evidence. Actor damage/stun can become `INTERRUPTED + BASIC_INTERRUPTED`
  when no target contact/damage was already observed. Protected or long-lived
  events become `UNKNOWN + BASIC_UNKNOWN_TIMEOUT`.
- 2026-05-05 live-smoke refinement: `current_attack` is retained as attack
  identity/context evidence, but it is not used as the attack active-window
  lifecycle gate because it can remain sticky after visible recovery. Basic
  whiff finalization treats an accepted attack-start event as whiff-eligible,
  then uses routine attack state only to tell whether the active window is still
  open. This keeps very short light attacks from being missed when their routine
  active state is too brief to latch during live sampling.
- 2026-05-05 timeout/LP refinement: clean non-projectile events that reach the
  basic pending timeout without contact/projectile/throw evidence are finalized
  as `WHIFF`, not `UNKNOWN`. Normal LP events also use a 20-frame fast whiff
  fallback so sticky active-window evidence or unrelated same-side projectile
  noise does not turn a visible light-punch whiff into timeout unknown.
- 2026-05-05 rollover refinement: if a same-side new attack start supersedes a
  still-active clean event, the old event is finalized as `WHIFF` instead of
  `UNKNOWN + SUPERSEDED_BY_NEW_START`. `R` / rollover unknown remains reserved
  for contact/projectile-like/throw-protected ambiguous events.
- 2026-05-05 side-split overlay refinement: round-local OSD stats now display
  self/opponent splits as `CE Sself/opp Fself/opp Aself/opp`, `CER Wself/opp
  Iself/opp Uself/opp`, and in All view `CEU Fself/opp Rself/opp Dself/opp`.
  This is debug visibility only; event totals and trainer behavior are
  unchanged.
- 2026-05-05 timeout-cause overlay refinement: All view additionally shows
  `CEUC Cself/opp Pself/opp Tself/opp` for timeout unknowns caused by
  contact/damage, projectile, or throw evidence, plus `CEUL Lself/opp
  Nself/opp` for projectile-like and not-whiff-eligible timeout unknowns.
  These are diagnostic counters only.
- 2026-05-05 contact-cause overlay refinement: when timeout unknowns are caused
  by the contact/damage bucket, All view also shows `CEUD EHself/opp
  ECself/opp EDself/opp` and `CEUH HPself/opp STself/opp` so live smoke can
  identify whether hit-stop, contact-state, damage-state, HP delta, or stun
  delta blocked clean whiff classification.
- 2026-05-05 EC-only whiff refinement: live smoke showed simultaneous visible
  whiffs as `CEUC C +0/+1` and `CEUD EC +0/+1` with no hit-stop, damage-state,
  HP, stun, projectile, throw, or not-whiff cause. Because
  `entered_contact_state` is derived from broad `guard_flag || hit_stop`, and
  hit-stop is already tracked separately, EC-only evidence is no longer treated
  as strong target contact/damage for Phase 2 basic whiff classification. Keep
  latching and displaying `CEUD EC` for diagnostics, but do not let it alone
  force a clean strike whiff to timeout unknown.
- Phase 2C still does not export event rows, transition summaries, rewards, or
  trainer-visible labels. These results are lifecycle/debug labels until the
  Phase 6 contact resolver and move-family validation prove them safe.
- 2026-05-05 Phase 2D exposes attack-event lifecycle stats through the existing
  RL debug state and OSD overlay. The outcome overlay includes started,
  finalized, active self/opponent, whiff, interrupted, and timeout-unknown
  counts; the all-view overlay also shows flush unknowns, rollover unknowns,
  and dropped starts.
- 2026-05-05 round-stat refinement: the main `CE` / `CEU` overlay counters are
  round-local and reset at episode begin, while event ids remain run-wide and
  monotonic. `All` view additionally shows `CEL` / `CELU` lifetime counters for
  long-run health checks.
- Phase 2D intentionally does not add temporary transition-log fields or a
  partial event log. Disk/analyzer event visibility starts with the Phase 7
  schema v4 summary plus combat-event journal export, carried in the shared
  transition batch/envelope.

Work:

- add fixed-size attack event rings for self and opponent
- use globally monotonic `event_id` values, never ring indices
- detect starts from attack counter/current_attack/routine edges
- attach raw engine state, spacing, target state, and preliminary confidence
- finalize non-projectile whiffs/interrupted/unknown after per-family windows
- enforce episode-boundary flush behavior

Validation:

- scripted `stand-hp`, `crouch-mk`, `shoryuken-*`, `tatsu-*`
- event counts match visible attempts within expected tolerance
- no event id reuse inside a run
- active pending slots are never overwritten

Done when:

- each accepted non-projectile attack has an event id and final result or
  explicit unknown

### Phase 3: Side-Explicit Engine Attribution

Files:

- `src/rl/rl_session.c`
- `src/rl/rl_combat_attribution.*`

Work:

- split current generic `engine_*` export into side-explicit self fields
- add opponent engine attribution at attack-event creation time
- use observation-side opponent routine/current_attack/kind_of_waza evidence
  instead of assuming existing self-side ledger attribution can be reused
- keep character id and confidence in the attribution result
- keep unknown instead of mapping unsupported characters incorrectly

Implementation status:

- 2026-05-05 Phase 3 foundation added transition schema v7 side-explicit
  engine fields: `self_engine_*` and `opp_engine_*`. The old generic
  `engine_*` fields remain as deprecated self-side aliases for v5/v6/v7
  Python compatibility.
- Attack-event starts now carry side-local engine action/sub-action,
  routine 1/2, current attack, kind-of-waza, source, and lag fields when the
  actor is a supported Ryu mapping. Unsupported characters remain unknown
  instead of being forced into a Ryu label.
- Opponent attribution uses opponent observation evidence
  (`opp_routine`, `opp_current_attack`, `opp_kind_of_waza`, and opponent
  attack-start edges). It does not reuse the self-side ledger attribution.
- Python replay/analyzer helpers prefer `self_engine_*` when present and fall
  back to generic `engine_*` for older logs.

Validation:

- Ryu-vs-Ryu scripted policies
- CPU-demo rows show both self and opponent engine starts when each side acts
- no side-swapped labels after side switch

Done when:

- self and opponent attacks can both be named by engine fields when supported

### Phase 4: Projectile Event Tracker

Files:

- `src/rl/rl_combat_event.*`
- `src/rl/rl_observation.*` if more projectile evidence is needed

Work:

- track projectile spawn, owner, position, velocity, time-to-impact
- link spawn to recent fireball attack event
- resolve projectile hit/block/chip/expired
- avoid using owner current routine as the hit source after spawn

Implementation status:

- 2026-05-05 Phase 4A foundation added an owner-side projectile event ring in
  `rl_combat_event.*`. Projectile events use the same monotonic event id
  allocator as attack events and keep `parent_attack_event_id` when a recent
  projectile-like fireball attack event is available.
- Projectile updates are intentionally conservative: each active owner-side
  projectile records spawn/last relative position, velocity, time-to-self, and
  target contact/damage/guard evidence. Disappearance after a short missing
  window finalizes as hit, blocked, expired, or unknown only when evidence is
  strong enough.
- The current observation schema still exposes only one selected projectile per
  frame. If another projectile hides the owner-side projectile, the tracker does
  not immediately expire the hidden event; it waits for no projectile to be
  visible or for timeout. This avoids false expirations during clashes but may
  leave conservative unknowns.
- Transition schema v8 adds projectile counter snapshots for live validation,
  and the overlay adds `CP` / `CPR` side-split projectile counters. Event journal
  rows remain Phase 7.
- 2026-05-05 Phase 4 live validation passed on MiSTer. The accepted Phase 4B
  contract is:
  - `CP S/F/A` tracks projectile event started/finalized/active counters, not
    owner routine snapshots.
  - `CPR H` means the projectile saw clear damage / HP / stun evidence.
  - `CPR B` means the projectile saw an explicit block reaction. Broad
    `guard_flag` / `entered_contact_state` evidence is not enough by itself.
  - `CPR X` means the projectile cleanly disappeared/expired, including the
    accepted Phase 4 clash behavior where both sides' projectile events expire
    as `X +1/+1`.
  - `CPR U` is accepted for parry and other evidence-insufficient projectile
    outcomes until Phase 6 contact matching adds stronger attribution.
  - Projectile-like parent attacks are finalized as projectile-claimed when a
    projectile spawn links to them. `CPR` is therefore the source of truth for
    fireball success/failure; `CEU R` must not be used as fireball failure.
  - Transient VS pause suspends RL action/observation handling but does not
    flush or reset combat-event counters.

Phase 4B edge-case notes:

- Fireball spawn: expect `CP S +1/+0` and `CP F +1/+0` for a complete visible
  projectile lifecycle.
- Fireball hit: expect `CPR H +1/+0`; the linked parent attack must not add
  `CEU R +1/+0`.
- Fireball block: expect `CPR B +1/+0`; the linked parent attack must not add
  `CEU R +1/+0`.
- Fireball fly-out: expect `CPR X +1/+0`.
- Fireball clash/cancel: Phase 4 accepts `CPR X +1/+1`. Exact
  projectile-nullification identity is deferred to Phase 6.
- Fireball parry: Phase 4 accepts `CPR U +1/+0`. A dedicated parry result is a
  Phase 6+ schema/semantic decision, not a Phase 4 requirement.
- Current observation still exposes only one selected projectile per frame, so
  simultaneous-projectile handling remains conservative. Do not promote `CPR`
  edge cases to hard reward labels until Phase 6 consumed-delta/contact matching
  validates them across characters and projectile families.

Validation:

- scripted `fireball-lp/mp/hp` at close/mid/far
- projectile spawn count matches visible projectiles
- projectile hit/block/chip results consume the matching HP/stun/contact delta
- live Outcome overlay confirms pause preservation, hit/block/fly-out/clash/parry
  behavior, and no projectile-parent `CEU R` pollution

Done when:

- fireball success/failure can be analyzed without delayed-window guesses
- this phase can be developed in parallel with Phase 5 because projectile and
  throw trackers do not depend on each other

### Phase 5: Throw Event Tracker

Files:

- `src/rl/rl_combat_event.*`
- `src/rl/rl_combat_attribution.*`

Work:

- add throw start/result events
- classify success/tech/whiff/unknown
- link close-range guard failures to throw when evidence supports it

Phase 5A throw evidence audit:

| Signal | Current source | Current meaning | Reliability / limitation | Phase 5 use |
|--------|----------------|-----------------|--------------------------|-------------|
| `obs.self_throw_active` | `plw[self].tsukami_f != 0` | selected RL-side actor is in a throw/catch attempt | useful owner-active evidence | self throw start/active candidate |
| `obs.self_throw_started` | rising edge of `self_throw_active` | selected RL-side throw/catch attempt began | good edge for self starts when previous frame state is valid | self `throw_start` candidate |
| `obs.opp_throw_caught` | `plw[opp].tsukamare_f != 0` | opponent is caught by selected RL-side throw/catch | strong success evidence for self throw | self `throw_success` candidate |
| `obs.opp_throw_caught_started` | rising edge of `opp_throw_caught` | opponent newly entered caught state | strong success edge for self throw | self result edge |
| `obs.opp_throw_active` | `plw[opp].tsukami_f != 0` | opponent-side throw/catch attempt | added in Phase 5B; symmetric owner-active evidence | opponent throw start/active candidate |
| `obs.self_throw_caught` | `plw[self].tsukamare_f != 0` | selected RL-side actor is caught by opponent throw | added in Phase 5B; symmetric caught evidence | opponent `throw_success` candidate |
| `obs.*_throw_escape_active` | routine `R1=0`, `R2=47/48/49/50` | throw escape / nagenuke-style recovery routine | internal Phase 5D evidence; not exported in transition schema v9 | contested throw guard; prevents false `CTR T` |
| routine `R1=2` | `obs_*_routine[1]` | catch/grab state bucket | useful support evidence, not enough by itself | confidence/support |
| routine `R1=3` | `obs_*_routine[1]` | caught state bucket | useful support evidence, not enough by itself | success/support |
| Ryu `R2=14` | engine routine substate | previously observed grab/catch startup path | Ryu-specific; must not be universalized without per-character validation | Ryu throw start support |
| Ryu `R2=2` | engine routine substate | previously observed completed throw path | Ryu-specific; must not be universalized without per-character validation | Ryu throw result support |
| HP/stun deltas | transition deltas | damage happened in the decision span | not throw-specific; can be strike/projectile/throw/round-end sync | result support only after throw evidence |
| close range | `obs_abs_dx` / front-edge distances | throw plausibility gate | spacing support only; not an event signal | confidence/failure reason support |

Phase 5A conclusion:

- Existing transition/evidence fields are enough to validate self throw success
  in logs, but they are not self/opponent symmetric.
- Do not implement the throw event ring by guessing opponent throws from HP
  deltas, `guard_flag`, or contact reaction alone.
- Phase 5B must first add symmetric observation evidence:
  - `self_throw_active`
  - `opp_throw_active`
  - `self_throw_caught`
  - `opp_throw_caught`
  - rising-edge fields for all four states
- The first throw ring should treat HP/stun deltas as supporting evidence only
  after throw-active/caught evidence exists.
- `tech` remains unresolved in Phase 5 unless a distinct engine signal is found.
  Until then, tech-like or interrupted/cancelled interactions should finalize
  as `unknown`, not as success or whiff.

Phase 5B implementation contract:

- `RLObservationV1` now exposes both sides of the raw throw/caught states:
  - `self_throw_active`, `opp_throw_active`
  - `self_throw_caught`, `opp_throw_caught`
  - rising edges for all four states
- Transition schema v9 exports the per-decision OR-accumulated edge/seen fields:
  - `self_throw_started`
  - `opp_throw_started`
  - `self_throw_caught_started`
  - `opp_throw_caught_started`
  - `self_throw_seen`
  - `opp_throw_seen`
  - `self_throw_caught_seen`
  - `opp_throw_caught_seen`
- These fields are root-level numeric transition fields, not DQN features and
  not throw result labels. They exist so Phase 5C can build a side-symmetric
  throw event ring without guessing opponent throws from HP/stun deltas alone.
- Phase 5B does not change reward, trainer feature selection, combat event
  result counters, or the future combat event journal shape.

Phase 5B/C planned result semantics:

- `throw_success`: owner throw-active/start evidence plus target caught edge or
  target caught state, optionally supported by close range and HP/stun delta.
- `throw_whiff`: owner throw-active event ends after a short window with no
  target caught evidence, no clear throw damage, and no stronger contact source.
- `throw_unknown`: timeout, interruption, possible tech, round end, conflicting
  strike/projectile/contact evidence, or missing symmetric evidence.
- Do not add throw labels to reward/trainer features until Phase 6 matching can
  consume HP/stun/contact deltas across attack/projectile/throw candidates.

Phase 5C implementation contract:

- `rl_combat_event` owns independent fixed-size throw rings for self and
  opponent (`RL_COMBAT_THROW_EVENT_RING_CAP = 16` each). Throw event ids share
  the same run-wide monotonic allocator as attack/projectile events.
- Throw starts originally came from symmetric throw-active rising edges:
  `self_throw_started` for self owner and `opp_throw_started` for opponent
  owner.
- Phase 5C/5D live refinement widens throw starts to include conservative
  throw-attempt intent:
  - Ryu engine throw-start routine edge (`R1=4`, `R2=14`) when a fresh
    routine/attack edge is observed;
  - raw throw-active rising edges (`tsukami_f`) only when no active throw event
    and no recent non-whiff throw result for that side already covers the same
    interaction.
  This is required so out-of-range throw attempts create a `CT S` event and can
  later finalize as `CTR W` instead of producing no counter at all.
- Policy/input `throw` rows are metadata only and must not be standalone start
  triggers. Live testing showed held LP+LK plus direction changes can produce
  repeated policy/input rows without a new engine throw attempt, inflating
  `CT S/F`, `CTR W`, and `CTR U`.
- Same-side raw throw-active starts are suppressed while an active throw event
  exists and for a short window after non-whiff results, preventing a successful
  throw from being counted once from engine start and again from `tsukami_f`.
- Fresh Ryu throw-start routine edges are still allowed to supersede an active
  clean throw as `CTR W`, which keeps rapid repeated whiff attempts from being
  swallowed by the previous active event. The supersede-to-whiff path only
  applies when the active event has no caught/contact/damage/interruption,
  opposing-throw, or throw-escape evidence.
- `CTR T` success is emitted only when the target-side caught state/edge is
  observed (`opp_throw_caught*` for self owner, `self_throw_caught*` for
  opponent owner) and there is no simultaneous/escape evidence that makes the
  interaction contested. Success waits a short confirm window
  (`RL_COMBAT_THROW_SUCCESS_CONFIRM_FRAMES`, currently 8 frames) unless clear
  damage/stun evidence already confirms the throw; this gives delayed
  tech/escape evidence a chance to win before `CTR T` is emitted.
- `CTR W` whiff is emitted only when owner throw-active ends after the minimum
  whiff window with no target caught evidence, no target contact/damage
  evidence, no HP/stun delta, no actor interruption, and no opposing
  throw/escape evidence.
- `CTR U` unknown covers episode flush, timeout with conflicting evidence,
  possible tech, interruption, or ambiguous contact/damage without caught
  evidence.
- "Throw tech" for current Phase 5D validation means both sides attempt throw
  and neither gets a real throw success. Because the engine-level tech/escape
  signal is still conservative, simultaneous/opposing throw evidence plus
  `R2=47/48/49/50` throw-escape routines must finalize as `CTR U`, not `CTR T`.
  Normal forward throw and back throw success remain `CTR T` when caught-state
  evidence appears without contested evidence.
- Phase 5D live validation accepted mutual throw/tech-like cases when they
  finalize as `CTR U` without any `CTR T` false-positive. The side split is
  allowed to be self-only, opponent-only, or both-sided (`+1/0`, `0/+1`, or
  `+1/+1`) because the current tracker is conservative and depends on which
  side's throw-start/escape evidence is observed in the confirm window. Full
  bilateral attribution is deferred to Phase 6 contact/result matching.
- Outcome overlay now shows:
  - `CT S/F/A` for throw started/finalized/active side splits
  - `CTR T/W/U` for throw success/whiff/unknown side splits
- Phase 5C still does not change transition schema, reward, trainer features,
  or the future combat event journal export.

Minimal overlay/debug plan:

- Phase 5C added combat-event `CT S/F/A` side-split counters for throw
  started/finalized/active.
- Phase 5C added `CTR T/W/U` side-split counters for throw success, whiff, and
  unknown.
- These stay in the `Outcome` debug view with existing combat-event counters.
- Do not re-add raw input text or broad non-event debug lines to `Outcome`.
- If raw bring-up evidence is needed before the ring is trusted, put it in a
  temporary Fight/Input diagnostic line or transition analyzer, not as learner
  truth.

Validation:

- scripted throw policy
- close guard/back/forward scenarios
- CPU close-pressure logs
- self throw success should increment self-side `CT S/F` and `CTR T`
- opponent throw success should increment opponent-side `CT S/F` and `CTR T`
- out-of-range throw should become `CTR W` only when no caught/contact evidence
  appears inside the whiff window
- tech-like or ambiguous interactions should remain `CTR U`
- pause menu should not reset throw counters, matching Phase 4 projectile
  counter behavior

Done when:

- "crouch guard failed" can distinguish thrown from strike/chip damage
- this phase can be developed in parallel with Phase 4

### Phase 6a: Contact To Attack Matching

Files:

- `src/rl/rl_combat_event.*`
- `src/rl/rl_session.c`

Work:

- consume HP/stun/contact deltas into event outcomes
- match contact/damage edges to attack, projectile, or throw candidates
- detect simultaneous/trade before one side is marked interrupted
- mark deltas as consumed exactly once
- record failure reasons and confidence

Validation:

- HP-delta conservation per episode
- no double-credit of the same damage
- projectile delayed hit after owner recovery or owner damage
- trade / simultaneous hit scenarios

Done when:

- each meaningful HP/stun/contact edge has either an attributed source event or
  an explicit attribution failure event

Phase 6a-0 implementation slice:

- Add debug-only contact-match instrumentation before full event-id
  consumption. This first slice records one source family per meaningful
  target edge and exposes it only through the Outcome overlay as
  `CEM Aself/opp Pself/opp Tself/opp Uself/opp`.
- A meaningful edge is any per-frame entered hit-stop, entered contact state,
  entered damage state, HP delta, or stun delta on the target side. The edge is
  counted once for the source side in that frame.
- Refinement from live validation: HP delta, stun delta, damage state, and
  throw-caught rising edges are strong target edges. Guard block reaction is a
  sustained state and must not by itself create repeated `CEM` rows; block
  contact is counted through the existing entered-contact edge. Plain
  hit-stop/contact-state evidence is only counted when the candidate source
  side already has attack/projectile/throw evidence. This prevents sustained
  block reaction, the attacker's own hit-stop, side swaps, and
  projectile-contact splash from creating repeated or reverse-side `CEM U`
  noise.
- Projectile-only soft contact is stricter than strike contact: if a projectile
  candidate has no HP/stun/damage edge yet, the soft contact only counts when a
  block-reaction routine is present. This prevents a failed jump over a
  projectile from counting both the early hit-stop/contact edge and the later
  damage edge.
- Successful parry is a projectile target edge even without HP/stun/damage or
  block reaction. Phase 6a-0 detects it from the engine parry success counter
  (`paring_ctr_vs[Play_Type][side]`) rising edge, the parry bonus flag rising
  edge, or the parry success routine (`R1=0`, `R2=31/32/33/34`) rising edge,
  and allows it to produce `CEM P` for projectile candidates.
- Source-family priority is projectile -> throw -> attack -> unknown. Projectile
  wins over the projectile parent attack so fireball hit/block/expire behavior
  remains owned by `CP` / `CPR`; throw wins over generic attack when caught or
  throw-active evidence is present; attack is the fallback for active strike
  evidence.
- CEM attack candidates must come from the combat attack ring, not raw
  `routine/current_attack` state. Raw attack state is too broad for projectile
  supers, projectile clashes, and parent fireball routines, where it can leak
  false `CEM A` after the projectile event is already the true source.
- CEM attack candidates must also exclude active attack events that are
  `projectile_like` or have already seen a projectile. Projectile parent
  attacks are lifecycle context for `CP` / `CPR`, not fallback strike sources.
- Throw contact matching is one-shot per throw event. The first caught/contact
  edge marks the throw event as already matched, so delayed HP/stun/damage
  evidence from the same throw does not create a second `CEM T`.
- This slice does not mutate HP/stun deltas, does not write event ids into the
  transition row, does not emit the future event journal, and does not affect
  reward/trainer features. It is an observability step for live validation.
- Full Phase 6a remains open until the matcher records event-id attribution,
  consumes HP/stun/contact deltas exactly once, handles trades with explicit
  confidence, and emits attribution-failure events for unresolved edges.

Phase 6a-0 live validation focus:

- normal hit/block/contact should increment `CEM A` for the side that caused
  the target edge
- projectile hit/block/clash/parry contact should increment `CEM P`, not the
  projectile parent attack
- throw success/contact should increment `CEM T`
- simultaneous trades may increment both sides in the same visual exchange
- `CEM U` should stay low; any repeatable high `U` case becomes the next Phase
  6a matcher gap

### Phase 6b: Defense Result Emission

Files:

- `src/rl/rl_combat_event.*`
- `src/rl/rl_session.c`

Work:

- emit defense_result events for both sides from matched incoming events
- detect guard/block/chip/hit/throw/escaped/unknown outcomes
- record intended defense action separately from actual guard state at contact
- record target state, block_possible, throw range, wakeup context, and failure
  reason

Validation:

- multi-hit Tatsu/block-stun cases
- stand/crouch guard high/low/throw cases
- guard-drop between multihit contacts
- wakeup/knockdown pressure cases

Done when:

- defense failures can distinguish hit, chip, throw, late guard,
  wrong-height guard, recovery/impossible state, and unknown

### Phase 6c: Punish Detection

Files:

- `src/rl/rl_combat_event.*`
- `src/rl/rl_session.c`

Work:

- create punish events only after the punished attack has been finalized as
  unsafe/no-damage/interrupted/whiff/recovery
- link `punished_attack_event_id` and `punisher_attack_event_id`
- gate punish labels by timing window, damage, and confidence

Validation:

- Shoryuken whiff-then-punish cases
- close fireball punished vs safe zoning fireball
- interrupted attack is not mislabeled as range whiff

Done when:

- punish events explain unsafe-action damage without falsely punishing neutral
  damage or unavoidable combo damage

### Phase 7: Transition Schema v4 And Event Journal Export

Files:

- `src/rl/rl_session.c`
- `src/rl/rl_protocol.*` if packet/batch framing changes
- `tools/rl_probe_server.py`
- analyzers

Work:

- bump transition schema to v4
- export compact summary fields
- export combat event journal rows in the same transition batch/envelope,
  not as a separate C-side stream
- keep schema v3 reader behavior explicit in Python

Validation:

- schema smoke with remote probe
- Python parser rejects unsupported schema versions clearly
- every event row in the envelope belongs to the same run/episode or an
  explicitly declared boundary event
- event journal row count and transition summary references agree

Done when:

- a live log can be replayed from event rows without guessing major damage
  sources

### Phase 8: Analyzer And Report Upgrade

Files:

- `tools/analyze_rl_transitions.py`
- new `tools/analyze_rl_combat_events.py`

Work:

- add fight replay summaries:
  - timeline
  - per-side damage sources
  - attack success rate by action/range
  - defense failure by incoming action/range/result
  - projectile lifecycle
  - throw success/tech/whiff
  - punish table
  - unknown attribution table

Validation:

- run on scripted logs and natural live logs
- compare output against manual video/OSD review for sample rounds

Done when:

- the analyzer can answer the user's current questions directly from event
  fields, not heuristic reconstruction

### Phase 9: Learner Adoption Gates

Files:

- `tools/train_dqn_learner.py`
- model comparison tools

Work:

- add explicit flags for event-aware reward shaping
- keep defaults compatible and conservative
- use high-confidence event labels first
- add source/confidence diagnostics to model metadata

Candidate reward uses:

- event-based hit/block/whiff/punish rewards by action family, replacing
  broad delayed-window HP sums only for high-confidence attack events
- event-based guard success rewards, replacing window-based guard success only
  when a high-confidence incoming event confirms block/chip/avoidance and
  `block_possible=yes`
- event-based projectile rewards for hit/block/chip/expired, useful for
  fireball context gates after projectile delayed-hit validation
- event-based throw rewards for success/tech/whiff, gated by throw
  high-confidence labels
- event-based defense failure costs split by hit/chip/throw/late/wrong-height,
  applied only when `block_possible=yes`, `target_state=neutral` or another
  actionable state, and `reaction_window_frames` exceeds the chosen threshold
- event-based punish costs for Shoryuken/Tatsu/close-fireball only when both
  punished and punisher events are high confidence

Validation:

- offline A/B against v351-style config
- no action collapse
- no Shoryuken/fireball over-credit from projectile or macro ambiguity
- live smoke before promotion
- model metadata records event type/source/confidence/unknown distributions
- training flag defaults remain off; event labels require explicit opt-in

Done when:

- event-aware training improves defense/attack diagnostics and live behavior
  without increasing unknown-label dependence

## Phase 0+1 Validation Matrix

These checks validate evidence export before attack rings or resolvers exist.

| Scenario | Required evidence checks |
| --- | --- |
| Python parser smoke | unknown keys ignored; known evidence keys parsed; trainer path ignores evidence |
| bitmask version smoke | `evidence_bitmask_version=1` decodes; unknown versions warn and leave evidence unexpanded by default; strict audit mode fails |
| bitmask mapping smoke | each C evidence bit expands to the intended Python evidence name |
| debug expansion smoke | `--expand-evidence` or `--debug-bitmask` prints readable evidence dictionaries |
| replay mapping smoke | replay/trainer feature builders ignore evidence unless explicit audit/event flags are enabled |
| learner feature guard | evidence bitmask/version/counter fields are absent from default DQN/replay feature lists |
| transition line budget | formatted line fits configured reusable/bounded buffer; truncation guard tested |
| truncation guard smoke | capacity zero, offset beyond capacity, and simulated insufficient capacity return errors without advancing past capacity |
| C memory/stack guard | no large hot-path stack buffer, no shared static scratch buffer, no formatter/session buffer leak in long-episode smoke |
| deferred formatter timing | non-blocking after Phase 0+1 live smoke unless visible performance symptoms appear; before full event export, dense attack/contact/effect rows should remain inside the formatter budget |
| scripted `stand-hp` | requested attack input/active/state fields become nonzero |
| scripted anti-air or direct hit | hitstop/contact/damage-state edge fields become nonzero |
| scripted far whiff | whiff evidence becomes nonzero and is marked medium-trust |
| scripted close throw | throw edge fields become nonzero or are marked unavailable |
| overlay counter smoke | active/contact/whiff counters match OSD/debug counter tolerance, allowing multi-hit and clash exceptions |
| round-end smoke | no evidence or pending export metadata from the previous episode leaks into the next episode |
| hot-path smoke | deferred until full event export or visible performance symptoms; when run, `RLSession_FormatTransitionLogLine()` p95 stays below the formatter budget |

## Full Event Validation Matrix

| Scenario | Required event checks |
| --- | --- |
| `stand-hp` scripted | attack_start, hit/block/whiff result, no projectile |
| `crouch-mk` scripted | low/ground normal identity, range-specific whiff/hit |
| `fireball-lp/mp/hp` | attack_start -> projectile_spawn -> projectile_result |
| `shoryuken-lp/mp/hp` | startup identity, anti-air hit, ground whiff, punish |
| `tatsu-lk/mk/hk` | distance-bucket contact count, block continuation, guard-drop detection |
| multi-hit projectile / super | same projectile id can consume repeated hit/block deltas until expired |
| delayed projectile after owner recovery/damage | projectile hit credits projectile id, not owner current routine |
| `throw` scripted | throw_start/result, defender action, close-range proof |
| throw tech / throw whiff | tech has no HP damage but has throw result; whiff has no damage/displacement result |
| `guard-stand` | block high/mid strikes, fail against throw/low when applicable |
| `guard-crouch` | block lows, fail against throw/high/air when applicable |
| trade / simultaneous hit | both HP deltas are consumed and both attack events become hit/trade, not one interrupted |
| round-end edge cases | pending events finalize before ring flush; no event crosses episode boundary |
| side switch / corner transition | event actor/target ownership remains correct after side switch |
| wakeup / oki pressure | target_state/wakeup_type explain whether defense was actionable |
| CPU natural offense | opponent attack attribution coverage and unknown reasons |
| Ryu mirror natural match | event counts compared against OSD/manual sample review |
| Live DQN v351 replay | self defense failures by incoming action/range/result |

## Acceptance Criteria

Do not promote event labels into training until these are true on fresh logs.

Core schema:

- every event id is unique inside a run
- event ids are generated by a monotonic run-wide counter, not ring indices
- every summary event id references a real event row
- every event row has source, confidence, and failure reason if unresolved
- pending events are finalized or explicitly failed at episode boundary
- pending-export overflow is visible through dropped-event metadata instead of
  silent event loss
- analyzers fail fast on unknown schema versions

Damage attribution:

- per-episode event-attributed self damage plus unknown-damage events equals
  summed `-delta_self_hp`, excluding documented round-sync corrections
- same for opponent damage
- no single HP delta is consumed by multiple unrelated event results

Move-family coverage:

- normals, specials, projectiles, throws, and multistage moves each have
  validation notes
- projectile hits are not credited to owner routine snapshots after spawn
- throw damage is not reported as failed crouch guard without throw evidence

Training safety:

- high-confidence labels are separable from medium/low/unknown labels
- per-event-type high-confidence rate is above 80% in validation logs before
  that event type is used for reward shaping
- per-event-type unknown rate is below 10% or explicitly excluded from trainer
  reward usage
- reward shaping can be disabled
- model metadata records event-label usage and confidence distribution

## Risks And Mitigations

Risk: engine mapping is Ryu-specific.

- Mitigation: emit unknown for unsupported characters; use character id in every
  attribution result; expand character mapping only with validation.

Risk: contact state cannot cleanly separate block and hit.

- Mitigation: keep raw evidence fields; use HP/stun deltas, guard/contact
  state, hitstop, and routine evidence together; mark low confidence when split
  is not provable.

Risk: multi-hit moves double-credit damage.

- Mitigation: contact events carry `hit_index`; damage resolver consumes each
  HP delta once.

Risk: projectiles outlive owner action.

- Mitigation: projectile tracker owns projectile results after spawn.

Risk: event id collision due to ring-buffer reuse.

- Mitigation: event ids come from a monotonic run-wide counter; ring slots only
  store event structs and never define identity.

Risk: log rows become too large.

- Mitigation: transition rows carry compact summaries; full event detail goes
  into a logical event journal carried in the same batch envelope and persisted
  remotely after receipt if needed. Phase 0+1 must size and guard the current
  transition line buffer before adding evidence fields, then revisit the budget
  before schema v4 summary fields land.

Risk: enlarging `line[2048]` creates hot-path stack overflow or silent memory
corruption.

- Mitigation: do not add large stack buffers and do not use a shared static
  scratch buffer. Use session-owned reusable storage, free owned memory at
  session shutdown, and validate long-run memory stability.

Risk: evidence booleans bloat JSON and `SDL_snprintf()` cost.

- Mitigation: Phase 0+1 uses `evidence_bitmask_version = 1`,
  `evidence_flags_lo`, and `evidence_flags_hi` for boolean/edge evidence,
  expands them in Python analyzers/debug tools, and keeps `ep_` episode
  counters separate.

Risk: bitmask logs become unreadable and hide silent-zero evidence bugs.

- Mitigation: Python tooling must provide developer-only bitmask expansion and
  mapping tests so each bit can be inspected as a named evidence field.

Risk: `SDL_snprintf()` truncation handling advances past buffer capacity.

- Mitigation: follow the documented append guard exactly: fail before the call
  when `capacity == 0` or `offset >= capacity`, fail after the call when
  `written < 0` or `written >= remaining_capacity`, and never update `offset`
  after a failed/truncated write.

Risk: finalized events wait for a later decision row and overflow before export.

- Mitigation: use a fixed-size pending-export ring separate from active event
  rings, expose dropped-event metadata in the same envelope, and flush/fail all
  pending export state at episode boundary.

Risk: hot-path overhead.

- Mitigation: fixed-size rings, numeric enums, active-index lists,
  edge-triggered resolution, frame-end accumulation, batch export only, and a
  first p95 budget target below 500 microseconds.

Risk: HP/stun delta evidence is sparse or incorrectly accumulated.

- Mitigation: Phase 0+1 audits delta fields with fresh logs before resolver
  implementation; if transition deltas are wrong, fix frame-end delta capture
  before using resolver labels.

Risk: schema v4 breaks existing v3 tooling.

- Mitigation: document v3/v4 compatibility, fail fast in trainer modes that
  need v4, and let analyzers warn/gracefully degrade when event summaries are
  absent.

Risk: learner overfits imperfect labels.

- Mitigation: confidence gates, explicit training flags, metadata diagnostics,
  and promotion only after validation matrix passes.

## First Implementation Target After This Plan

The next implementation task should be Phase 0+1:

1. Harden Python parsers so unknown transition keys are safe before C exports
   new evidence.
2. Add `src/rl/rl_combat_event.h` with evidence bitmask version/bit constants
   only.
3. Audit every proposed evidence field as declared/filled/exported/trusted and
   record semantics in the engineering log.
4. Add the runtime/config evidence-export gate and implement the fixed Phase
   0+1 bitmask v1 export shape plus Python decoder.
5. Replace the transition JSON line path with reusable/bounded non-stack
   storage, add safe truncation checks, and measure formatting cost.
6. Restore/export existing evidence fields only when they are actually filled.
7. Add schema notes, parser smoke checks, bitmask mapping checks, and debug
   expansion.
8. Do not add event/result/source/confidence/failure enums, event structs,
   event rings, event ids, event JSON arrays, reward changes, or live inference
   changes.

That first target is intentionally non-behavioral. It lays the measurement
foundation before the combat event resolver starts making stronger claims.
