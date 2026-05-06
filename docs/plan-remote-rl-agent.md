# Remote RL Agent Plan For MiSTer vs CPU

## Goal

Run the real SF3 game simulation on MiSTer, stream compact per-frame battle observations to a remote PC over the network, receive control actions back, and use that loop to improve a remote RL agent against the built-in CPU.

The intended topology is:

- MiSTer side: environment actor and source of truth
- Remote PC side: low-latency inference service plus slower learner
- CPU opponent: still local, still driven by the game's existing `cpu_algorithm()`

## Executive Summary

Your core direction is good:

- reuse the netplay ideas around frame numbering, input history, and delayed scheduling
- do not reuse the Gekko peer model itself
- split inference from learning
- schedule actions for `t + k`, not same-frame

The main refinements are:

1. Do not build the RL bridge inside the current netplay implementation.
   `PORT_MISTER` disables `ENABLE_NETPLAY`, and the current CMake excludes all `src/netplay/*.c` files from MiSTer builds except stubs. That means `netplay.c` and `game_state.c` are not present on the target build by default.

2. Do not use `GameState_Save()` in the hot path.
   It is a large memcpy-based snapshot routine. Keep it for debug and offline logging only. Build a compact observation struct directly from live globals for per-frame inference.

3. Inject remote actions at the raw input buffer layer.
   The cleanest place is after `keyConvert()` writes `p1sw_buff/p2sw_buff` and before the game latches them into `p1sw_0/p2sw_0`.

4. Treat delayed action as both a transport problem and an RL problem.
   With `obs[t] -> action[t+k]`, the learner must align actions to their execution frame, not to the observation frame alone. For v1, make `decision_interval_frames` and `action_hold_frames` explicit to simplify credit assignment.

5. Treat directional input as execution-time relative state, not only observation-time intent.
   Delayed execution means a `forward` decision made at `obs[t]` can turn into the wrong absolute `LEFT/RIGHT` by `target_frame = t + k` if the sides swap. V1 should therefore prefer a relative-direction wire mode and let MiSTer remap only the direction bits at execution time using current facing.

6. Make the baseline match flow decision explicit up front.
   V1 should start from `MODE_VERSUS` plus an RL session flag, not `MODE_NETWORK` and not a training flow. Training-based flow can be evaluated later as a reset optimization, but it should not be the first baseline.

7. Avoid overloading `MODE_NETWORK` for RL.
   Too many gameplay and UI branches special-case `MODE_NETWORK`. Use a dedicated RL session flag first, and only add a new game mode enum after a spike proves it is worth the code churn.

## Review Of The Initial Design

### Keep

- Borrow netplay concepts: frame id, pending input history, delayed scheduling, state/debug snapshots.
- Make MiSTer the only real simulator.
- Make the remote PC inference-only on the critical path.
- Use a compact observation packet and a separate training/logging path.
- Use `target_frame = t + k`.

### Change

- Do not make the remote PC a Gekko/netplay peer.
- Do not depend on `src/netplay/netplay.c` or `src/netplay/game_state.c` in MiSTer builds.
- Do not send the full `GameState` every frame.
- Do not block the game loop on network I/O.
- Do not make the model's native action space raw `LEFT/RIGHT + buttons` if you can avoid it.

### Add

- A dedicated compile-time/runtime RL bridge feature separate from netplay.
- A non-blocking action queue on MiSTer keyed by `target_frame`.
- A decision ledger for RL transition alignment.
- A control cadence setting separate from observation cadence.
- Episode/reset/versioning rules from day one.

## Baseline Match Flow Decision

The plan should stop treating this as an open-ended recommendation.

Recommended v1 baseline:

- use `MODE_VERSUS`
- add an `rl_session_active` runtime flag
- drive one side through remote-agent input injection
- keep the other side on the existing local CPU path

Why `MODE_VERSUS` first:

- it keeps round flow, timer, winner flow, and post-round transitions closer to real versus play
- it avoids the special-case `MODE_NETWORK` branches
- it avoids training-specific pause, menu, dummy, and record/replay behavior in the first implementation
- it better matches the actual target task: teaching the agent to play real matches against the CPU

Why not training flow first:

- training has useful reset affordances, but it also brings a large amount of unrelated state and menu behavior
- it is better treated as a later optimization for faster curriculum loops once the control path is proven

What Milestone 0A decides:

- not "which family of flow should we use in general"
- only whether the recommended `MODE_VERSUS + rl_session_active` baseline has any blocking regressions that force an exception

## Relevant Repo Findings

### 1. Existing Input Pipeline Is A Good Fit

Raw controller input currently flows through:

- `keyConvert()` writes `p1sw_buff` / `p2sw_buff`
  - `src/sf33rd/Source/Game/io/ioconv.c:123-124`
- the frame step latches buffers into `p1sw_0` / `p2sw_0`
  - `src/main.c:432-461`
- `appCopyKeyData()` mirrors into `PLsw`
  - `src/main.c:323-329`
- `Convert_User_Setting()` converts raw `SWKey` inputs into logical gameplay inputs
  - `src/sf33rd/Source/Game/system/sys_sub.c:98-150`
- `Player_move()` picks either user input or CPU input based on `wk->wu.operator`
  - `src/sf33rd/Source/Game/engine/plmain.c:41-66`
- `move_P1_move_P2()` / `move_P2_move_P1()` call `Player_move(... Convert_User_Setting(...))`
  - `src/sf33rd/Source/Game/engine/plcnt.c:974-1003`

Implication:

- After the RL bridge maps a validated wire action into raw `SWKey`, the least invasive hook is to override `p1sw_buff` or `p2sw_buff` before the latch.
- This preserves the current `Convert_User_Setting()` and `processed_lvbt()` path.

### 2. Human vs CPU Routing Already Exists

`Player_move()` already does the critical split:

- `wk->wu.operator != 0` -> use player-side input
- `wk->wu.operator == 0` -> use `cpu_algorithm(wk)`

References:

- `src/sf33rd/Source/Game/engine/plmain.c:48-63`
- `src/sf33rd/Source/Game/engine/plcnt.c:1333`

Implication:

- An AI-vs-CPU mode does not need a new control architecture.
- It mainly needs reliable setup, reset, and input override plumbing.

### 3. Netplay Has Good Concepts To Reuse

The current netplay path already has:

- input history ring buffer
  - `src/netplay/netplay.c:70,224-237`
- frame-indexed input recall
  - `src/netplay/netplay.c:232-237`
- a per-frame advance function that latches current and previous inputs
  - `src/netplay/netplay.c:434-447`
- state save/load and rollback support
  - `src/netplay/netplay.c:367-415`
- a full rollback state shape made of `GameState + EffectState`
  - `src/netplay/netplay.c:42-55`

Implication:

- Reuse the scheduling model, not the transport/session model.
- A new RL bridge should have its own queue and packet protocol, but the same mental model of frame-keyed inputs.

### 4. `GameState_Save()` Is Useful But Not Hot-Path Friendly

`GameState_Save()` / `GameState_Load()` explicitly memcpy a very large amount of game state, including `PLsw`.

References:

- `src/netplay/game_state.c:22-40`
- `src/netplay/game_state.c:459-461`
- `src/netplay/game_state.c:648-664`
- `src/netplay/game_state.c:1085-1087`

Implication:

- It is good for debug snapshots, replay logs, and offline dataset capture.
- It should not be the main per-frame observation builder on MiSTer.

### 5. `GameState_Save()` Is Not Currently Available In MiSTer Builds

This is the most important repo-specific constraint.

Current build behavior:

- `PORT_MISTER` defaults `ENABLE_NETPLAY` to `OFF`
  - `CMakeLists.txt:12-28`
- when `ENABLE_NETPLAY` is off, CMake excludes all `src/netplay/*.c`
  - `CMakeLists.txt:63-70`
- that means `src/netplay/game_state.c` is also excluded in MiSTer builds

Implication:

- You cannot assume `GameState_Save()` is linkable on MiSTer today.
- If you want shared snapshot support, move `game_state.c/h` into a non-netplay module or carve it out from the CMake exclusion.

### 6. There Is Already A Good Local Fake-Agent Pattern

The test runner directly writes scripted inputs into `p1sw_buff` / `p2sw_buff`.

References:

- `src/test/test_runner.c:1076-1085`
- `src/test/test_runner.c:1354-1365`

Implication:

- Milestone 0 should reuse this pattern before any network work.
- It lets you verify AI-vs-CPU control, action hold, and reset behavior locally first.

### 7. End-Of-Frame Observation Hook Is Clear

`Game2_1()` ends with:

- `hit_check_main_process()`
  - `src/sf33rd/Source/Game/game.c:532-584`

Implication:

- This is a strong candidate for end-of-frame observation capture.
- At that point the frame's hit/guard outcomes are already updated.

## Recommended Architecture

## A. MiSTer Actor

Responsibilities:

- run the only authoritative game simulation
- run the built-in CPU locally
- own episode id, frame id, and action queue state
- send compact observations
- receive scheduled actions
- compute rewards and done flags
- log transitions without stalling gameplay

Recommended modules:

- `src/rl/rl_bridge.h`
- `src/rl/rl_bridge.c`
- `src/rl/rl_protocol.h`
- `src/rl/rl_action_queue.h`
- `src/rl/rl_action_queue.c`
- `src/rl/rl_observation.h`
- `src/rl/rl_observation.c`
- `src/rl/rl_reward.h`
- `src/rl/rl_reward.c`
- `src/rl/rl_session.h`
- `src/rl/rl_session.c`

Good news:

- `CMakeLists.txt` already uses `file(GLOB_RECURSE GAME_SRC src/*.c)`, so `src/rl/*.c` will be picked up automatically.

## B. Remote PC Inference Service

Responsibilities:

- receive `ObsPacket`
- normalize features
- run forward pass
- emit `ActionPacket`
- report latency and model version

Rules:

- no training work on the critical path
- no blocking on disk or replay buffer writes before sending action
- keep p50/p95/p99 inference timing visible

## C. Remote PC Learner

Responsibilities:

- receive transition logs
- maintain replay buffer
- update weights asynchronously
- publish new actor weights by version

Rules:

- actor weights are frozen during inference
- model updates must be atomic
- learner stalls must never stall the inference process

## D. Two Network Paths

### Critical path

- transport: UDP
- traffic: compact observation packets and action packets
- policy: best-effort, sequence-aware, non-blocking

### Non-critical path

- transport: TCP, QUIC, or batched UDP
- traffic: transitions, episode summaries, debug snapshots, model control messages
- policy: reliable or retriable, but never on the action critical path

## Key Design Decisions

### 1. Separate RL Bridge From Netplay

Recommended:

- add a new feature such as `ENABLE_REMOTE_AGENT_BRIDGE`
- keep it independent from `ENABLE_NETPLAY`
- implement it with Linux/POSIX sockets on MiSTer

Why:

- current netplay dependencies are tied to desktop builds and `SDL3_net`
- current MiSTer build excludes netplay sources entirely
- the RL bridge does not need rollback peer transport

### 2. Do Not Overload `MODE_NETWORK`

`MODE_NETWORK` has many gameplay/UI side effects:

- random seeding
  - `src/sf33rd/Source/Game/game.c:351-357`
- winner flow
  - `src/sf33rd/Source/Game/game.c:765-779`
- menu skip logic
  - `src/sf33rd/Source/Game/menu/menu.c:3791-3800`

Recommendation:

- do not set RL matches to `MODE_NETWORK`
- do not use a training flow as the initial baseline
- for v1, use `MODE_VERSUS + rl_session_active`
- only revisit training flow after the first end-to-end remote loop is stable

Practical guidance:

- treat `MODE_VERSUS` as the default baseline, not just one option
- use a short confirmation spike to validate `MODE_VERSUS` round/reset behavior with one CPU side and one remote-agent side
- evaluate training flow later only as a fast-reset path for curriculum or bulk data collection
- only add a new `ModeType` if the `MODE_VERSUS + rl_session_active` spike proves too messy to maintain

### 2A. Keep Future Upstream Netplay Merge Risk Low

Assumption:

- upstream may later implement or heavily rewrite P2P rollback netplay
- that work will likely touch `src/netplay/*`, `ENABLE_NETPLAY`, `MODE_NETWORK`, input history, rollback/session setup, and network packet code

Design rule:

- treat the remote RL agent as a local input provider plus observation exporter
- do not treat the remote PC as a netplay peer
- do not implement the RL agent inside `src/netplay/*`
- do not depend on Gekko, rollback sessions, `SDL3_net`, or future upstream netplay packet formats
- do not use `MODE_NETWORK` as the RL match mode

Recommended isolation boundary:

- keep RL implementation in `src/rl/*`
- keep protocol types in `src/rl/rl_protocol.h`
- keep frame-keyed action scheduling in `src/rl/rl_action_queue.*`
- keep observation building in `src/rl/rl_observation.*`
- keep reward and transition bookkeeping in `src/rl/rl_reward.*` and `src/rl/rl_session.*`
- expose only a small hook API to the rest of the game:
  - `RL_ApplyScheduledActionToBuffers(frame_id)`
  - `RL_OnFrameEnd(frame_id)`
  - `RL_OnEpisodeReset(reason)`
  - `RL_IsSessionActive()`

Allowed integration points:

- `src/main.c`
  - call the input-buffer hook after `keyConvert()` and before `p1sw_0/p2sw_0` latch
  - call a non-blocking per-frame RL tick if needed
- `src/sf33rd/Source/Game/game.c`
  - call the frame-end observation/reward hook after `hit_check_main_process()`
- match/setup code
  - enable `MODE_VERSUS + rl_session_active`
  - configure one side as player-input controlled and the other as CPU controlled

Merge strategy:

- keep all substantial RL code in new files so upstream netplay changes do not cause large file-level conflicts
- keep edits to shared game files as one-line or small-block hook calls where possible
- if a shared helper is needed by both future upstream netplay and RL, put it in a neutral module such as `src/input/*`, `src/session/*`, or `src/debug/*`, not under `src/netplay/*`
- only reuse netplay concepts, not netplay implementation ownership
- if upstream later provides useful generic frame-clock or input-history primitives, adapt through a small RL wrapper instead of making `src/rl/*` depend directly on upstream P2P session state

Expected benefit:

- future upstream P2P netplay merges should mostly affect `src/netplay/*` and `MODE_NETWORK` paths
- RL merge conflicts should be limited to a few stable hook sites in `main.c`, `game.c`, and setup/config code
- RL protocol and learner compatibility remain under local control even if upstream netplay protocol changes

### 3. Inject Actions At The Raw Input Buffer Layer

Best v1 hook:

- after `keyConvert()`
- before `p1sw_0 = p1sw_buff` / `p2sw_0 = p2sw_buff`

Reference:

- `src/main.c:432-461`

Recommended hook shape:

- `RL_ApplyScheduledActionToBuffers(frame_id)`

Behavior:

- if remote AI controls player 0, override `p1sw_buff`
- if remote AI controls player 1, override `p2sw_buff`
- leave the non-agent side untouched so CPU/human paths still work

Why this layer:

- execution-time direction remapping can happen here just before writing final raw `SWKey`
- `Convert_User_Setting()` still runs normally
- existing legality cleanup still applies

### 4. Build Compact Observations From Live State, Not Snapshots

Do not hot-path through `GameState_Save()`.

Build `RLObservationV1` directly from live state such as:

- self and opponent position
  - `plw[i].wu.position_x`
  - `plw[i].wu.position_y`
  - `include/structs.h:232-237`
- facing
  - `plw[i].wu.rl_flag`
  - `include/structs.h:201`
- health
  - `plw[i].wu.vital_new`
  - `include/structs.h:249-252`
- current attack and guard flags
  - `plw[i].current_attack`
  - `plw[i].guard_flag`
  - `include/structs.h:540-556`
- movement gating
  - `plw[i].do_not_move`
  - `plw[i].high_jump_flag`
  - `include/structs.h:607-613`
- routine state
  - `plw[i].wu.routine_no[0..2]`
  - `include/structs.h:221-223`
- super gauge
  - `plw[i].sa->store`
  - `plw[i].sa->store_max`
  - `include/structs.h:557,471-472`
- stun
  - `sdat[i].cstn`
  - `src/sf33rd/Source/Game/engine/stun.h:6-14`
- stage bounds
  - `scrl`, `scrr`
  - `src/sf33rd/Source/Game/engine/workuser.h:524-525`
- round and win state
  - `Round_num`
  - `VS_Win_Record[2]`
  - `src/sf33rd/Source/Game/engine/workuser.h:109,518-519`

Recommended observation groups:

- self
- opponent
- match and round
- relative stage geometry
- last executed action
- next scheduled action
- frames until next scheduled action

That last point is important:

- because the agent acts with delay, the observation should include enough queued-action context to know what will execute before the next new decision
- v1 should keep this minimal instead of expanding the full queue into the observation schema
- full pending-queue dumps can remain a debug-only feature

### 4A. Freeze `RLObservationV1` As A Fixed Schema Before Implementation

Before writing code, the project should freeze one canonical logical schema for `RLObservationV1`.

Rules:

- the table below defines field semantics, ordering, and preprocessing expectations
- transport packing can change later, but changing field meaning or field order requires a protocol version bump
- v1 should prefer gameplay-state sources over UI mirror state when both exist

Canonical v1 choices:

- HP uses `plw[i].wu.vital_new / round_start_hp[i]`
  - capture `round_start_hp[i]` from `plw[i].wu.vital_new` after round bootstrap completes and before the first controllable frame begins
  - if the player state is not fully initialized at that point, delay capture until the first `rl_session_active && playable` frame
  - do not assume `Max_vitality` is always the right per-player denominator after mode, difficulty, or handicap modifiers
  - do not use `vitality` as the primary source
  - do not use `original_vitality` as the live HP max
- super should expose both stock count and in-progress gauge
  - stock count uses `plw[i].sa->store / plw[i].sa->store_max`
  - in-progress gauge uses `plw[i].sa->gauge.s.h / plw[i].sa->gauge_len`
  - `store` is the number of full super stocks currently available, not the partial fill progress
  - `spg_dat` is a useful debug cross-check, but not the canonical gameplay source
- stun uses `sdat[i].cstn / plw[i].py->genkai`
  - `sdat[i].slen` is UI gauge length and should not be used as the normalization base
- facing uses derived relative features from `plw[i].wu.rl_flag`, not raw left/right button semantics
  - map `rl_flag == 0` to `-1` / facing world-left
  - map `rl_flag == 1` to `+1` / facing world-right
  - keep a compact `self_facing_sign`
  - expose `opp_in_front` rather than raw world-left/world-right labels
- stage geometry uses per-fighter corner distances derived from `position_x`, `scrl`, and `scrr`
  - do not send raw `scrl` / `scrr` as primary observation features
- action context uses relative action encoding
  - do not label raw absolute `LEFT` / `RIGHT` `SWKey` masks as relative observations
  - expose move intent and attack bits separately so delayed direction remapping stays explicit

Recommended fixed logical schema:

| Field | Type | Normalize / Encoding | Canonical source | Relative |
| --- | --- | --- | --- | --- |
| `self_hp_ratio` | `f32` | `plw[self].wu.vital_new / round_start_hp[self]` clamped to `[0, 1]` | `plw[self].wu.vital_new`, episode-start `round_start_hp[self]` | No |
| `opp_hp_ratio` | `f32` | `plw[opp].wu.vital_new / round_start_hp[opp]` clamped to `[0, 1]` | `plw[opp].wu.vital_new`, episode-start `round_start_hp[opp]` | No |
| `self_super_stock` | `u8` | raw full-stock count | `plw[self].sa->store` | No |
| `self_super_stock_max` | `u8` | raw max stock count | `plw[self].sa->store_max` | No |
| `opp_super_stock` | `u8` | raw full-stock count | `plw[opp].sa->store` | No |
| `opp_super_stock_max` | `u8` | raw max stock count | `plw[opp].sa->store_max` | No |
| `self_super_gauge_ratio` | `f32` | `plw[self].sa->gauge.s.h / plw[self].sa->gauge_len` clamped to `[0, 1]` | `plw[self].sa->gauge.s.h`, `plw[self].sa->gauge_len` | No |
| `opp_super_gauge_ratio` | `f32` | `plw[opp].sa->gauge.s.h / plw[opp].sa->gauge_len` clamped to `[0, 1]` | `plw[opp].sa->gauge.s.h`, `plw[opp].sa->gauge_len` | No |
| `self_stun_ratio` | `f32` | `sdat[self].cstn / plw[self].py->genkai` clamped to `[0, 1]` | `sdat[self].cstn`, `plw[self].py->genkai` | No |
| `opp_stun_ratio` | `f32` | `sdat[opp].cstn / plw[opp].py->genkai` clamped to `[0, 1]` | `sdat[opp].cstn`, `plw[opp].py->genkai` | No |
| `opp_dx_ratio` | `f32` | `(plw[opp].wu.position_x - plw[self].wu.position_x) / max(1, scrr - scrl)` | `plw[*].wu.position_x`, `scrl`, `scrr` | Yes |
| `opp_dy_ratio` | `f32` | `(plw[opp].wu.position_y - plw[self].wu.position_y) / max(1, scrr - scrl)` | `plw[*].wu.position_y`, `scrl`, `scrr` | Yes |
| `self_left_corner_ratio` | `f32` | `(plw[self].wu.position_x - scrl) / max(1, scrr - scrl)` | `plw[self].wu.position_x`, `scrl`, `scrr` | No |
| `self_right_corner_ratio` | `f32` | `(scrr - plw[self].wu.position_x) / max(1, scrr - scrl)` | `plw[self].wu.position_x`, `scrl`, `scrr` | No |
| `opp_left_corner_ratio` | `f32` | `(plw[opp].wu.position_x - scrl) / max(1, scrr - scrl)` | `plw[opp].wu.position_x`, `scrl`, `scrr` | No |
| `opp_right_corner_ratio` | `f32` | `(scrr - plw[opp].wu.position_x) / max(1, scrr - scrl)` | `plw[opp].wu.position_x`, `scrl`, `scrr` | No |
| `self_facing_sign` | `s8` | `-1` when `plw[self].wu.rl_flag == 0`, `+1` when `rl_flag == 1` | `plw[self].wu.rl_flag` | Yes |
| `opp_in_front` | `u8` | `1` if opponent is in the controlled player's forward direction, else `0` | `plw[self].wu.rl_flag`, `plw[*].wu.position_x` | Yes |
| `self_guard_flag` | `u8` | raw combat/contact categorical value as-is; not a pure blocking boolean | `plw[self].guard_flag` | No |
| `opp_guard_flag` | `u8` | raw combat/contact categorical value as-is; not a pure blocking boolean | `plw[opp].guard_flag` | No |
| `self_current_attack` | `u16` | raw attack button-category code; currently `0x010/0x020/0x040/0x100/0x200/0x400` for `LP/MP/HP/LK/MK/HK` | `plw[self].current_attack` | No |
| `opp_current_attack` | `u16` | raw attack button-category code; currently `0x010/0x020/0x040/0x100/0x200/0x400` for `LP/MP/HP/LK/MK/HK` | `plw[opp].current_attack` | No |
| `self_do_not_move` | `u8` | raw movement-gate flag; currently observed as low-signal in normal versus runtime | `plw[self].do_not_move` | No |
| `opp_do_not_move` | `u8` | raw movement-gate flag; currently observed as low-signal in normal versus runtime | `plw[opp].do_not_move` | No |
| `self_hit_stop` | `u8` | `1` if `plw[self].wu.hit_stop != 0`, else `0`; often behaves as shared contact stop | `plw[self].wu.hit_stop` | No |
| `opp_hit_stop` | `u8` | `1` if `plw[opp].wu.hit_stop != 0`, else `0`; often behaves as shared contact stop | `plw[opp].wu.hit_stop` | No |
| `self_high_jump_flag` | `u8` | raw high-jump-only flag; not a generic airborne flag | `plw[self].high_jump_flag` | No |
| `opp_high_jump_flag` | `u8` | raw high-jump-only flag; not a generic airborne flag | `plw[opp].high_jump_flag` | No |
| `self_routine_0` | `u16` | raw categorical id | `plw[self].wu.routine_no[0]` | No |
| `self_routine_1` | `u16` | raw categorical id | `plw[self].wu.routine_no[1]` | No |
| `self_routine_2` | `u16` | raw categorical id | `plw[self].wu.routine_no[2]` | No |
| `opp_routine_0` | `u16` | raw categorical id | `plw[opp].wu.routine_no[0]` | No |
| `opp_routine_1` | `u16` | raw categorical id | `plw[opp].wu.routine_no[1]` | No |
| `opp_routine_2` | `u16` | raw categorical id | `plw[opp].wu.routine_no[2]` | No |
| `self_routine_attack_state` | `u8` | derived validation flag: `self_routine_1 == 4` | `plw[self].wu.routine_no[1]` | No |
| `opp_routine_attack_state` | `u8` | derived strike-warning flag: `opp_routine_1 == 4`; validated as useful for first strike-defense tabular state split, but not a throw detector | `plw[opp].wu.routine_no[1]` | Yes |
| `self_contact_reaction_state` | `u8` | derived validation flag: `self_routine_1 == 1`; includes hit and guard reaction | `plw[self].wu.routine_no[1]` | No |
| `opp_contact_reaction_state` | `u8` | derived validation flag: `opp_routine_1 == 1`; includes hit and guard reaction | `plw[opp].wu.routine_no[1]` | No |
| `round_num` | `u8` | raw categorical round index | `Round_num` | No |
| `self_match_round_wins` | `u8` | raw round wins inside the current match | `PL_Wins[self]` | No |
| `opp_match_round_wins` | `u8` | raw round wins inside the current match | `PL_Wins[opp]` | No |
| `self_round_wins` | `u8` | raw VS cumulative match-win count; field name is retained for v1 compatibility even though source is not per-round | `VS_Win_Record[self]` | No |
| `opp_round_wins` | `u8` | raw VS cumulative match-win count; field name is retained for v1 compatibility even though source is not per-round | `VS_Win_Record[opp]` | No |
| `last_executed_move_intent` | `u8` | relative-direction wire enum from the last action that actually executed | RL session state | Yes |
| `last_executed_attack_bits` | `u16` | attack/button bits from the last action that actually executed | RL session state | No |
| `next_scheduled_move_intent` | `u8` | relative-direction wire enum for the next queued action | pending action queue | Yes |
| `next_scheduled_attack_bits` | `u16` | attack/button bits for the next queued action | pending action queue | No |
| `frames_until_next_action` | `u8` | unsigned frame countdown; `255` means no queued next action | pending action queue, current frame id | Yes |

Notes:

- `self` / `opp` are always from the controlled agent's perspective, not player-1/player-2 fixed slots
- if `frames_until_next_action == 255`, set `next_scheduled_move_intent = RL_MOVE_NEUTRAL` and `next_scheduled_attack_bits = 0`
- `opp_dy_ratio` intentionally uses the same stage-width denominator as `opp_dx_ratio` in v1 as a pragmatic scale; a later version can switch to a fixed vertical scale or jump-range-based scale with a protocol version bump
- `self_match_round_wins` / `opp_match_round_wins` come from `PL_Wins[*]` and represent the current match's round score
- `self_round_wins` / `opp_round_wins` are legacy field names from the original plan; the current runtime source is `VS_Win_Record[*]`, which counts cumulative versus match wins rather than intra-match rounds
- if a source field is later found to be unavailable or unstable in one build target, the replacement must preserve the same logical meaning and require a version bump if that meaning changes
- if the wire payload later switches to quantized integers instead of `f32`, the logical schema above still remains the canonical contract

#### MVP Training Observation Set

This is the smallest observation subset considered useful for the first remote inference / training loop. The full schema above remains available for debug and future policies, but v1 training should start here to keep the learner input stable and understandable.

Core MVP fields:

- resources:
  - `self_hp_ratio`
  - `opp_hp_ratio`
  - `self_super_stock`
  - `self_super_stock_max`
  - `opp_super_stock`
  - `opp_super_stock_max`
  - `self_super_gauge_ratio`
  - `opp_super_gauge_ratio`
  - `self_stun_ratio`
  - `opp_stun_ratio`
- spacing and stage geometry:
  - `opp_dx_ratio`
  - `opp_dy_ratio`
  - `self_left_corner_ratio`
  - `self_right_corner_ratio`
  - `opp_left_corner_ratio`
  - `opp_right_corner_ratio`
  - `self_facing_sign`
  - `opp_in_front`
- combat state:
  - `self_current_attack`
  - `opp_current_attack`
  - `self_guard_flag`
  - `opp_guard_flag`
  - `self_hit_stop`
  - `opp_hit_stop`
  - `self_routine_0..2`
  - `opp_routine_0..2`
- round / match context:
  - `round_num`
  - `self_match_round_wins`
  - `opp_match_round_wins`
  - `self_round_wins`
  - `opp_round_wins`
- delayed-action context:
  - `last_executed_move_intent`
  - `last_executed_attack_bits`
  - `next_scheduled_move_intent`
  - `next_scheduled_attack_bits`
  - `frames_until_next_action`

Non-MVP fields to keep for debug / later promotion:

- `self_do_not_move`, `opp_do_not_move`
  - currently low-signal in the normal versus path
- `self_high_jump_flag`, `opp_high_jump_flag`
  - high-jump-specific and not a generic airborne flag

Recommended first training stance:

- train with the MVP fields above, encoded from the controlled agent's perspective
- keep `do_not_move` and `high_jump_flag` available in debug logs, but do not rely on them for the first reward/policy iteration
- if jump-state ambiguity becomes a training blocker, add an explicit `self_airborne` / `opp_airborne` feature in the next schema revision rather than overloading `high_jump_flag`

#### Human-Fighter Observer Gap Review

This review captures the gap between the current MVP observer and what a human player naturally reasons about during a match. Revisit it after Milestone 2 networking is working and before Milestone 4 transition logging / reward design is finalized.

Already covered well enough for MVP:

- spacing and stage geometry:
  - `opp_dx_ratio`
  - `opp_dy_ratio`
  - corner distances
  - `self_facing_sign`
  - `opp_in_front`
- resource state:
  - HP
  - SA stock
  - SA gauge fill
  - stun
- coarse combat state:
  - attack button-category code through `current_attack`
  - raw combat/contact state through `guard_flag`
  - contact stop through `hit_stop`
  - routine triplets for normal / damage / catch / caught / attack state
- own control pipeline context:
  - last executed action
  - next scheduled action
  - frames until next action

Likely missing or too implicit for strong training:

- opponent movement intent:
  - walking forward / backward
  - crouching
  - neutral jump / forward jump / back jump
  - dash forward / dash back
  - airborne state
- opponent action phase:
  - startup
  - active
  - recovery
  - blockstun
  - hitstun
  - knockdown / wakeup
- own action outcome:
  - requested movement actually changed position
  - requested jump actually entered airborne state
  - requested attack actually entered attack state
  - own attack hit
  - own attack was blocked
  - own attack likely whiffed
  - opponent hit self
  - self blocked opponent attack
  - self was thrown / threw opponent
- event deltas for credit assignment:
  - `delta_self_hp`
  - `delta_opp_hp`
  - `delta_self_stun`
  - `delta_opp_stun`
  - `entered_hit_stop`
  - `entered_damage_state`
  - `entered_contact_state`

Recommended derived-feature candidates:

- `round_active`
- `self_can_act`, `opp_can_act`
- `self_airborne`, `opp_airborne`
- `self_crouching`, `opp_crouching`
- `self_movement_state`, `opp_movement_state`
- `self_action_phase`, `opp_action_phase`
- `self_contact_result`, `opp_contact_result`
- `last_action_result`
- `last_action_delta_x`, `last_action_delta_y`
- `self_knockdown`, `opp_knockdown`
- `self_blockstun`, `opp_blockstun`
- `self_hitstun`, `opp_hitstun`
- `self_throw_state`, `opp_throw_state`
- `timer_remaining`

Deferred but likely important later:

- projectile / object positions
- parry / blocking result
- combo or hit-sequence counters
- full move id once the code path for concrete normal / special / SA identity is decoded

Milestone placement:

- Milestone 2 should not block on these additions; it only needs the current MVP observer to exercise the transport and delay budget.
- Milestone 4 should revisit action-outcome and delta fields because they directly affect transition logging, reward shaping, and credit assignment.
- Milestone 6 should revisit movement/action-phase derived fields for stronger policies and curriculum learning.

### 4B. `RLObservationV1` 中文欄位導讀

這一節不是新的 schema。它是上面 canonical table 的中文解讀，重點放在:

- 欄位代表什麼
- RL 可以用它學到什麼
- 哪些欄位能回答「對手有沒有出招 / 在不在跳 / 有沒有被打中或被擋」

#### 資源與勝負狀態

- `self_hp_ratio`, `opp_hp_ratio`
  - 表示自己與對手血量。
  - RL 可用來學:
    - 何時要保守
    - 何時要換血
    - 瀕死時是否要壓進或撤退
- `self_super_stock`, `opp_super_stock`
  - 表示自己與對手已經集滿、可直接使用的 SA 次數。
  - RL 可用來學:
    - 自己能不能立刻開 SA
    - 對手是否已經進入有 SA 威脅的狀態
- `self_super_gauge_ratio`, `opp_super_gauge_ratio`
  - 表示自己與對手目前這一格 SA 還在集的進度。
  - RL 可用來學:
    - 距離下一格 SA 還差多少
    - 壓制或拉開距離時是否值得賭對手快滿氣
- `self_stun_ratio`, `opp_stun_ratio`
  - 表示自己與對手暈值。
  - RL 可用來學:
    - 對手快暈時是否繼續壓
    - 自己快暈時是否降低互動頻率

#### 空間與位置

- `opp_dx_ratio`, `opp_dy_ratio`
  - 表示對手相對於自己的水平與垂直距離。
  - RL 可用來學:
    - 近距 / 中距 / 遠距決策
    - 對空與空對地判斷
    - 前跳是否能打到
- `self_left_corner_ratio`, `self_right_corner_ratio`
- `opp_left_corner_ratio`, `opp_right_corner_ratio`
  - 表示雙方距離版邊多近。
  - RL 可用來學:
    - corner pressure
    - 逃 corner
    - 把對手往角落逼

#### 朝向與相對前後

- `self_facing_sign`
  - 表示自己目前面向 world-left 或 world-right。
  - RL 不需要直接學世界左右，主要用它配合其他欄位維持方向一致性。
- `opp_in_front`
  - 表示對手是否在自己的前方。
  - 這個比 raw left/right 更接近實戰語意，因為 RL 真正需要的是「前 / 後」。

#### 戰鬥狀態與出招線索

- `self_current_attack`, `opp_current_attack`
  - 這是判斷「自己 / 對手有沒有出招」的核心欄位。
  - 目前這個 source 更接近 raw 攻擊按鍵類別碼，不是完整招式 id。
  - 現行 code path 會看到:
    - `0x010` = `LP`
    - `0x020` = `MP`
    - `0x040` = `HP`
    - `0x100` = `LK`
    - `0x200` = `MK`
    - `0x400` = `HK`
  - RL 可用來學:
    - 對手是否正在出招
    - 對手目前是哪一類攻擊按鍵
    - 自己目前正在做什麼攻擊輸入類別
- `self_guard_flag`, `opp_guard_flag`
  - 名字雖然叫 `guard_flag`，但目前實機與 code audit 都顯示它比較像廣義 combat/contact state。
  - 很多 hit / guard / throw 相關流程都會把它設成 `3`，所以不能把它當成純「正在防禦」布林值。
  - 可用來推測:
    - 自己的攻擊是否進入了防禦或接觸處理
    - 對手是否進入了防禦、受擊、摔投等互動狀態
- `self_hit_stop`, `opp_hit_stop`
  - 表示 `hit_stop != 0`。
  - 在目前實機行為裡，它常常更像「雙方共享的 contact stop」，不是彼此完全獨立的局部事件。
  - 配合 guard / HP 變化時，能幫助 RL 區分:
    - 打中
    - 被擋
    - 純空揮
- `self_do_not_move`, `opp_do_not_move`
  - 原始欄位名是 movement gate，但在目前 versus bring-up 觀測裡幾乎一直是 `0`。
  - 先保留在 schema 裡，但暫時不要高估它的訓練價值。
- `self_high_jump_flag`, `opp_high_jump_flag`
  - 表示是否進入特定 high-jump / hijump-cancel 路徑。
  - 它不是一般 jump / airborne 判定，所以普通跳躍時常常不會亮。
- `self_routine_0..2`, `opp_routine_0..2`
  - 表示角色內部 state machine / routine 狀態。
  - 這些欄位很原始，但對 RL 很有價值，因為它們常常比高階文字標籤更穩定地反映:
    - 站立 / 蹲下 / 跳躍
    - 攻擊進行中
    - 受擊 / 硬直 / 倒地

#### 回答常見問題

- RL 怎麼知道對手有沒有出招?
  - 主要看 `opp_current_attack`
  - 再配 `opp_routine_*`
- RL 怎麼知道對手站著還是在跳?
  - 主要看 `opp_dy_ratio`
  - 再配 `opp_routine_*`
  - `opp_high_jump_flag` 只能當 high-jump 特例補充，不足以覆蓋一般跳躍
  - 如果後續驗證覺得這樣不夠直觀，可以再加明確 `opp_airborne`
- RL 怎麼知道對手是出拳還是出腳?
  - v1 不直接給 punch / kick 布林值
  - 主要靠 `opp_current_attack`
  - remote side 可以:
    - 直接把 button-category code 當 categorical feature
    - 或建立 code -> semantic tag 對照
- RL 怎麼知道對手出了什麼絕招?
  - v1 目前還不能只靠 `opp_current_attack` 直接回答這件事
  - 真正要區分具體招式，仍要再配 `opp_routine_*`、hit/throw 子狀態，或後續額外欄位
- RL 怎麼知道自己的招有沒有打中 / 被擋 / 空揮?
  - v1 不打算只靠單一 observation 欄位回答這件事
  - 一般會綜合:
    - `opp_hp_ratio` 變化
    - `opp_guard_flag`
    - `self_hit_stop` / `opp_hit_stop`
    - 後續 transition / reward / decision ledger
  - 也就是說:
    - 打中: 通常伴隨對手掉血，且可能有 hit stop
    - 被擋: 通常 guard flag 變化明顯，且可能有 hit stop，但傷害模式不同
    - 空揮: 有出招，但沒有造成血量或 guard 的對應變化

#### 回合資訊

- `round_num`, `self_match_round_wins`, `opp_match_round_wins`, `self_round_wins`, `opp_round_wins`
  - `round_num` 是目前回合。
  - `self_match_round_wins` / `opp_match_round_wins` 是目前這場 match 內的 round 比數。
  - `self_round_wins` / `opp_round_wins` 這兩個欄位名雖然沿用原計畫，但目前 runtime source 其實是 VS mode 累積 match 勝負數。
  - 這對多回合策略很重要，例如:
    - 領先時保守
    - 落後時提高風險

### 4C. `RL Debug` Overlay 實機驗證語意

以下內容以 2026-04-22 的 MiSTer 實測與 code audit 為準，優先描述 overlay 上每個縮寫實際代表的意思。

- line 1: `%s HP%d/%d OP%d/%d R%d RW%d-%d M%d-%d`
  - `HP/OP`: raw HP / round-start HP
  - `R`: current round number
  - `RW`: current match's round score from RL perspective
  - `M`: VS mode 累積 match 勝負數，不是回合內小局比分
- line 2: `SA%d/%d SG%d/%d ST%d/%d`
  - `SA`: full-stock count
  - `SG`: in-progress super gauge fill
  - `ST`: raw stun / max stun
- line 3: `DX%c%d DY%d F%d`
  - `DX/DY`: relative spacing
  - `F`: facing sign derived from `rl_flag`
- line 4: `CL%d CR%d OL%d OR%d`
  - self / opponent corner distances
- line 5: `CF%d/%d AK%03X/%03X`
  - `CF`: raw combat/contact state from `guard_flag`; many hit / guard / catch paths set this to `3`
  - `AK`: attack button-category code from `current_attack`
- line 6: `NM%d/%d HS%d/%d HJ%d/%d`
  - `NM`: raw `do_not_move` gate; currently low-signal in normal versus play
  - `HS`: `hit_stop != 0`; often shows as shared contact stop on both players
  - `HJ`: high-jump-only flag, not general jump state
- line 7: `SR%d,%d,%d OR%d,%d,%d`
  - `SR/OR`: self / opponent `routine_no[0..2]`
  - `routine_no[0]` separates pre-fight from active-fight stages; live battle commonly reaches `4`
  - `routine_no[1]` is the clearest high-level state bucket:
    - `0` normal
    - `1` damage/contact reaction; live tests confirm this includes both hit reaction and guard/block reaction after close-range contact
    - `2` catch
    - `3` caught
    - `4` attack
  - `routine_no[2]` is a substate index whose meaning depends on `routine_no[1]`
- line 8: `X%d/%03X N%d/%03X T%d O%lu/%luus`
  - action context plus observation build cost

#### 動作排程上下文

- `last_executed_move_intent`
- `last_executed_attack_bits`
- `next_scheduled_move_intent`
- `next_scheduled_attack_bits`
- `frames_until_next_action`
  - 這些欄位是為 delayed control 設計的。
  - 因為 remote policy 不是 same-frame 立即生效，所以 RL 需要知道:
    - 上一個真正執行的是什麼
    - 下一個排隊中的動作是什麼
    - 還要幾幀才輪到下一個動作

#### Combo / 指令輸出的理解方式

未來 RL 不會把 `L.D.R.LP` 這種整串指令當成一個字串一次送給 MiSTer。

v1 的基本模型是:

- 每個 decision step 輸出一個 action
- action 由:
  - 一個 relative movement intent
  - 一組 attack bits
  組成
- action 可以因為 `action_hold_frames` 持續多幀

所以像 `L.D.R.LP` 這種輸入，比較像是時間序列:

1. 一步輸出左
2. 下一步輸出下
3. 下一步輸出右
4. 下一步輸出 LP

也就是說:

- 不一定每幀都換一鍵
- 但本質上是多個時間步的 action sequence
- combo 是 policy 在多個 step 上學出來的時序模式，不是單包字串命令

### 5. Separate Wire Action Format From Policy Action Format

Recommended v1 wire action mode:

- use a relative-direction wire action, not an absolute `LEFT` / `RIGHT` `SWKey` mask
- encode movement as a controlled-agent-relative intent
- encode attack buttons as final button bits
- map relative movement to raw `SWKey` only on MiSTer at the action's execution frame

Suggested v1 move enum:

- `RL_MOVE_NEUTRAL`
- `RL_MOVE_UP`
- `RL_MOVE_DOWN`
- `RL_MOVE_BACK`
- `RL_MOVE_FORWARD`
- `RL_MOVE_UP_BACK`
- `RL_MOVE_UP_FORWARD`
- `RL_MOVE_DOWN_BACK`
- `RL_MOVE_DOWN_FORWARD`

Why this matters:

- the remote policy chooses from `obs[t]`, but the action executes at `target_frame = t + k`
- if side switch happens between `t` and `t + k`, an absolute `LEFT` / `RIGHT` packet can invert the intended meaning
- execution-time relative-direction remapping avoids treating side-switch drift as a learning problem

Compatibility option:

- an absolute `SWKey` wire mode can exist later for diagnostics or simple scripted agents
- that mode must explicitly accept side-switch direction drift and should not be the default training mode

Recommended policy-side semantic action:

- movement intent:
  - neutral
  - forward
  - back
  - up
  - down
  - down-forward
  - down-back
- attack intent:
  - none
  - LP / MP / HP / LK / MK / HK
- optional extras later:
  - throw macro
  - parry macro
  - super confirm macro

Responsibility boundary:

- remote policy produces semantic actions
- remote action adapter converts semantic actions and macros into the final executable wire action
- MiSTer accepts final wire actions on the protocol boundary, plus remote-owned attribution fields for transition credit
- MiSTer does not own high-level macro expansion
- MiSTer may remap the relative-direction subfield into raw `SWKey` directions at execution time
- MiSTer may still apply minimal legality cleanup at the input-buffer edge

Canonical v1 rule:

- the packet received by MiSTer should already contain the final wire action intended for execution
- semantic-to-wire translation belongs on the remote side, not in the MiSTer runtime
- high-level policy action ID / sub-action ID / macro step fields are metadata for logging and learner attribution; MiSTer must not reinterpret them into inputs
- the only intended MiSTer-side interpretation layer is relative-direction to raw `SWKey` remapping at the exact execution frame
- direction remapping is not macro expansion and must not infer high-level policy intent

### 5A. Action Adapter Responsibility Table

The table below is the canonical v1 responsibility split.

| Concern | Remote PC side | MiSTer side | V1 decision |
| --- | --- | --- | --- |
| semantic policy output | choose semantic action from observation | none | remote owns |
| macro expansion | expand optional macros such as throw/parry/super-confirm into executable intent before packetization | none | remote owns |
| relative-direction encoding | encode movement intent into the relative-direction wire subfield | none | remote owns |
| execution-time directional remap | none | map relative movement to absolute raw `SWKey` direction bits using current `plw[self].wu.rl_flag` | MiSTer owns this narrow step |
| final wire action assembly | build final wire payload and attach `episode_id`, `decision_id`, `target_frame` | none | remote owns |
| packet serialization | serialize action packet fields and version metadata | deserialize and validate | split |
| protocol validation | none beyond local self-checks | validate `version`, action encoding mode, `episode_id`, `decision_id`, `target_frame`, and duplicate rules | MiSTer owns |
| high-level legality shaping | should avoid generating impossible combinations in the action adapter | must not reinterpret policy intent; only reject invalid packets | remote owns policy legality |
| minimal input legality cleanup | none | optional last-mile cleanup at the raw input-buffer edge if the engine already expects it | MiSTer owns only this tiny layer |
| target-frame scheduling | echo the `target_frame` from the triggering `ObsPacket` | choose `target_frame`, queue by `target_frame`, and execute on the correct frame | MiSTer owns schedule; remote echoes |
| fallback generation on misses | none on the critical path | generate hold/neutral/down-back fallback if no valid action arrives in time | MiSTer owns |

Hard boundary:

- MiSTer does not own semantic-to-wire translation
- MiSTer does not own macro expansion
- MiSTer does own v1's explicitly negotiated execution-time relative-direction remap
- if an absolute `SWKey` mode is used later, the design must explicitly accept side-switch drift risk

Benefits:

- fewer invalid combinations
- more stable learning across side switches
- easier action masking and curriculum

### 6. Treat Delay As First-Class

Do not design for strict same-frame remote control.

Recommended timing model:

- at end of frame `t`, MiSTer emits `obs[t]`
- remote returns an action for `target_frame = t + k`
- MiSTer inserts that action into a pending action queue
- at frame start, MiSTer applies the action scheduled for that frame

Recommended initial values:

- same LAN: `k = 2` or `3`
- non-LAN: `k >= 4`

Additional refinement:

- v1 critical-path observation cadence should equal decision cadence
- v1 sends `ObsPacket` only on decision frames
- control cadence should still be configurable through `decision_interval_frames`
- v1 should strongly consider `decision_interval_frames >= k`
- v1 should strongly consider `action_hold_frames >= decision_interval_frames`

Why:

- this reduces bandwidth
- this reduces action jitter
- this keeps `decision_id`, `target_frame`, ledger entries, and replay logging one-to-one
- this makes transition alignment much easier than full 60 Hz delayed control
- if per-frame auxiliary observations are needed later, send them through a separate non-critical telemetry path rather than overloading `ObsPacket`

## Temporal Contract

These definitions should be treated as protocol-level rules, not implementation suggestions.

- `obs[t]` is the state after frame `t` has fully completed simulation, specifically after `hit_check_main_process()` returns.
- `action[target_frame]` is applied before frame `target_frame` begins simulation, at the raw input-buffer layer before `p1sw_0/p2sw_0` are latched from `p1sw_buff/p2sw_buff`.
- in v1, `ObsPacket` is emitted only on decision frames, so critical-path observation cadence equals decision cadence.
- in v1 relative-direction wire mode, MiSTer maps the relative movement subfield into raw `SWKey` direction bits using current `plw[self].wu.rl_flag` at execution time.
- reward belongs to the decision whose action actually executed, and is accumulated over that executed decision's active interval until the next executed decision takes over or the episode ends.
- `frame_id`, `obs_frame`, and `target_frame` are session-wide monotonic counters and do not reset when `episode_id` increments.

For v1, assume:

- observation capture point: frame-end
- action application point: next-frame start for the chosen `target_frame`
- learner alignment anchor: executed action, not merely requested action
- frame counter scope: session-wide monotonic, with `episode_id` providing round boundaries

## Fallback Policy

Fallback behavior must be explicit because it becomes part of the training distribution.

Recommended v1 default:

- if no valid action arrives for a due `target_frame`, reuse the last executed action
- `action_hold_frames` is the only canonical hold-duration config unit
- compare fallback hold duration in frames, not in decision windows
- v1 default can set `action_hold_frames = 2 * decision_interval_frames`
- after the `action_hold_frames` budget expires, switch to `neutral`

Optional experimental fallback modes:

- `down_back_static`
  - after the hold window expires, always send down-back relative to facing
- `down_back_when_movable`
  - after the hold window expires, use down-back only when `plw[self].do_not_move == 0`
  - otherwise use neutral

V1 requirement:

- do not hide vague state-dependent heuristics such as "if defense seems meaningful"
- any non-neutral defensive fallback must be a named and separately measurable mode

Additional rules:

- late packets for already-executed frames are dropped
- fallback usage must be recorded in the decision ledger
- telemetry should count:
  - missed actions
  - fallback-to-last-action events
  - fallback-to-down-back events
  - fallback-to-neutral events

### 7. Use A Non-Blocking Main-Thread Poll First

For v1 on MiSTer:

- use non-blocking UDP sockets
- poll `recvfrom()` once per frame
- send the current observation packet once per decision frame on the critical path
- avoid a dedicated thread on the gameplay critical path until profiling proves it is necessary

Why:

- simpler failure model
- easier debugging
- less synchronization complexity

If later needed:

- add a background thread only for non-critical transition logging

### 8. Keep A Debug Snapshot Path, But Off The Critical Path

Use full snapshots only for:

- every `N` frames
- round-end or episode-end capture
- desync/debug reproduction
- offline dataset generation

Because `game_state.c` is currently excluded in MiSTer builds, you have two options:

1. move `GameState_Save()` / `GameState_Load()` to a new shared serialization module
2. keep RL debug snapshots as a desktop-only or test-only feature until that refactor is done

## Proposed Packet Model

## Wire Format Rules

The transport protocol needs explicit low-level rules before implementation starts.

- all wire fields are serialized as little-endian
- packets are not sent as raw C structs from memory
- serialization must be explicit field-by-field so padding and alignment are never part of the protocol
- action encoding mode must be explicit in `RLSessionHello` / `RLSessionAck` and may be reinforced by packet flags
- recommended v1 action encoding mode is relative-direction wire mode
- incompatible `version` values are dropped immediately and counted as protocol errors
- version mismatches should also emit an explicit warning or metric on both sides

## Session handshake packets

Before any critical-path observations or actions are accepted, MiSTer and the remote service should complete a minimal setup handshake.

V1 rule:

- MiSTer is authoritative for session configuration
- remote may accept the exact config or reject it
- no `ObsPacket` should be sent until `RLSessionAck.status == accepted`
- no `ActionPacket` should be accepted until the current `session_nonce` has been acknowledged
- reconnects and config changes send a new `RLSessionHello` with a new `session_nonce`

```c
typedef struct RLSessionHello {
    uint32_t magic;
    uint16_t version;
    uint16_t flags;
    uint32_t session_nonce;
    uint16_t obs_schema_version;
    uint16_t action_encoding_mode;
    uint16_t controlled_player;
    uint16_t fallback_mode;
    uint16_t decision_delay_frames;
    uint16_t decision_interval_frames;
    uint16_t action_hold_frames;
    uint16_t target_frame_policy;
    uint32_t feature_flags;
    uint32_t model_version_expected;
    uint32_t config_hash;
} RLSessionHello;
```

```c
typedef struct RLSessionAck {
    uint32_t magic;
    uint16_t version;
    uint16_t flags;
    uint32_t session_nonce;
    uint16_t status;
    uint16_t accepted_action_encoding_mode;
    uint32_t accepted_feature_flags;
    uint32_t accepted_config_hash;
    uint32_t model_version_current;
    uint32_t error_code;
} RLSessionAck;
```

Handshake fields lock these v1 assumptions:

- protocol version
- observation schema version
- action encoding mode
- controlled player index
- `decision_delay_frames`
- `decision_interval_frames`
- `action_hold_frames`
- target-frame policy
- fallback mode
- optional feature bits such as debug timing stats
- expected and current model version
- `config_hash`, computed over the session configuration fields that must match exactly

Recommended v1 status values:

- `accepted`
- `unsupported_protocol_version`
- `unsupported_obs_schema`
- `unsupported_action_encoding`
- `unsupported_timing_config`
- `unsupported_feature_flags`

Recommended v1 target-frame policy:

- MiSTer computes `target_frame = obs_frame + decision_delay_frames`
- remote must echo the exact `target_frame` from the triggering `ObsPacket`
- remote must not choose a new `target_frame`
- if `ActionPacket.target_frame` does not match the ledger entry for `(run_id, episode_id, decision_id)`, MiSTer treats it as a protocol error
- if `RLSessionAck.accepted_config_hash` does not match `RLSessionHello.config_hash`, MiSTer treats the session setup as rejected

Current protocol identity rules:

- `run_id` is a persisted `u64` RL dataset/run identity allocated by MiSTer when the RL runtime initializes.
- `episode_id` is unique only within one `run_id` and increments for each round-scoped rollout.
- `round_num` is the game-facing `Round_num` and is logged for analysis; it is not used as a unique episode key.
- learner/replay dedupe must use `(run_id, episode_id, decision_id)`.
- observation, action, transition-batch, and transition-batch-ack packets all carry `run_id`.

## Observation packet

```c
typedef struct RLObsHeader {
    uint32_t magic;
    uint16_t version;
    uint16_t flags;
    uint64_t run_id;
    uint32_t episode_id;
    uint32_t decision_id;
    uint32_t obs_frame;
    uint32_t target_frame;
    uint16_t obs_len;
    uint16_t action_hold_frames;
    uint32_t model_version_expected;
} RLObsHeader;
```

Payload:

- compact observation payload
- optional immediate reward summary for the previous executed decision
- optional timing stats

## Action packet

```c
typedef struct RLActionPacket {
    uint32_t magic;
    uint16_t version;
    uint16_t policy_action_id;
    uint64_t run_id;
    uint32_t episode_id;
    uint32_t decision_id;
    uint32_t target_frame;
    uint16_t action_wire;
    uint16_t policy_sub_action_id;
    uint16_t policy_action_step;
    uint16_t reserved;
    uint32_t model_version;
} RLActionPacket;
```

In v1, `action_wire` means:

- relative movement subfield
- final attack/button bits
- the already-expanded executable frame of the high-level policy action
- no implicit absolute `LEFT` / `RIGHT` `SWKey` unless an explicit absolute-action compatibility mode is negotiated

In the action-packet schema, `policy_action_id`, `policy_sub_action_id`, and
`policy_action_step` are attribution fields produced by the remote adapter. They
do not ask MiSTer to expand a macro; they let transition logs distinguish
semantic actions such as `guard`, `fireball`, `throw`, and `jump-forward-mk`
after MiSTer executes the final wire input.

Suggested v1 layout:

- bits `0..3`: `RL_MOVE_*` enum value
- bits `4..15`: attack/button bits, using an `rl_protocol.h` mapping that mirrors the existing non-direction `SWKey` buttons
- final raw direction bits are generated by MiSTer at execution time and are not carried as absolute `LEFT` / `RIGHT` bits in relative-direction mode

Recommended invariants:

- `episode_id` mismatch -> drop packet
- `target_frame < current_frame` -> drop packet
- remote must echo the `target_frame` from the triggering `ObsPacket`; it must not self-select a new target frame
- `ActionPacket.target_frame` mismatch with the ledger entry for `(episode_id, decision_id)` -> protocol error
- action encoding mode unsupported by MiSTer -> drop packet and count a protocol error
- `(episode_id, decision_id)` must be unique within a live session
- a given `(episode_id, decision_id)` must map to exactly one `target_frame`
- if the same `(episode_id, decision_id)` arrives again with a different `target_frame`, treat it as a protocol error
- if no valid action arrives by `target_frame`, use fallback

Recommended v1 duplicate rule:

- keep the first valid action received for a given `(episode_id, decision_id, target_frame)`
- treat later arrivals with the same tuple as duplicates and count them in telemetry
- treat later arrivals with the same `(episode_id, decision_id)` but a different `target_frame` as protocol errors, not normal duplicates

## Pending Action Queue

Recommended MiSTer-side queue:

- fixed-size ring buffer, power-of-two sized
- keyed by `target_frame`
- each slot stores:
  - valid bit
  - `episode_id`
  - `decision_id`
  - `target_frame`
  - `action_wire`
  - `model_version`

Recommended initial size:

- 256 entries

That is intentionally larger than the small `k` values so resets, jitter, and delayed packets are easy to reason about.

## Reward, Done, And Transition Alignment

This is the most important ML-side refinement.

With delayed actions:

- `obs[t]` does not directly lead to action execution at `t`
- it leads to execution at `t + k`
- therefore reward attribution cannot be assembled with a naive `(obs[t], action[t], reward[t+1])` tuple

Recommended MiSTer-side bookkeeping:

- maintain a decision ledger keyed by `(episode_id, decision_id)`
- when `obs[t]` is sent, record:
  - `episode_id`
  - `decision_id`
  - `obs_frame = t`
  - `target_frame = t + k`
  - observation summary or reference
- when the matching action arrives, attach it to the ledger entry
- when `target_frame` is reached, mark that decision as active
- accumulate reward for the active decision until the next decision becomes active or the episode ends

Minimum ledger fields:

- `episode_id`
- `decision_id`
- `obs_frame`
- `target_frame`
- `requested_action_wire`
- `executed_action_wire`
- `execution_frame_actual`
- `execution_source`
  - remote
  - repeated-last-action
  - defensive-down-back
  - neutral-fallback
- `reward_accum`
- `done`

Why `executed_action_wire` matters:

- a requested action may arrive late
- a requested action may be replaced by fallback
- a previous action may be held forward instead

The learner should train on what actually executed, not only on what the remote service intended to send. In v1, transition logs should also decode `executed_action_wire` into `executed_move_intent` and `executed_attack_bits` for easier replay-buffer inspection.

For v1, keep reward simple:

- `delta_opp_hp - delta_self_hp`
- round win bonus
- round loss penalty

Optional later:

- anti-air success
- stun creation
- knockdown conversion
- corner control

## Episode And Reset Rules

You need explicit reset semantics from the beginning.

Recommended v1 granularity:

- one round = one `episode_id`
- one best-of-N contest = one match context
- match context is preserved across rounds through observation fields such as `round_num`, `self_round_wins`, and `opp_round_wins`
- `episode_id` should increment when a new controllable round is initialized, not during the KO freeze itself

Why:

- round transitions fully reset the most important control state: positions, HP, super, stun, timers, and pending actions
- clearing queue/ledger/RNN state at each round boundary is much simpler and safer for v1 than carrying one episode across multiple rounds
- the agent still sees match-level context through cumulative match-win features in the next round's initial observation

Recommended reset events:

- round end
- match end
- return to menu
- character/stage reseed
- manual remote reset

On reset:

- increment `episode_id`
- keep the session-wide `frame_id` monotonic
- clear pending action queue
- clear decision ledger
- clear last-action fallback state
- tell remote inference to clear recurrent state if any

Do not rely on frame id alone to separate episodes.

### Episode / Reset Policy Table

| Event | Episode policy | MiSTer reset actions | Remote reset actions | Notes |
| --- | --- | --- | --- | --- |
| round end -> next round bootstrap | increment `episode_id`; start a fresh episode for the next round | clear pending action queue, clear decision ledger, clear last-action fallback state, reset frame-local scheduling state | clear recurrent state / frame cache, drop stale in-flight actions for the old episode | recommended v1 baseline |
| match end -> next match bootstrap | increment `episode_id`; start a fresh episode for the next match-opening round | same as round reset, plus reset any match-local automation state used for auto-rematch or reseed | same as round reset | a future `match_id` can be added to logs if needed, but is not required for v1 |
| character or stage reseed | hard reset; always start a new episode | same as match bootstrap reset | same as match bootstrap reset | treat as a stronger boundary than plain round advance |
| return to menu / mode exit | hard reset; no episode continues across menu flow | same as match bootstrap reset and mark session inactive | same as match bootstrap reset and mark session inactive | protects against stale packets crossing UI boundaries |
| manual remote reset command | hard reset; start a new episode on the next playable frame | same as match bootstrap reset | same as match bootstrap reset | useful for training loops and debugging |

Round-vs-match conclusion:

- v1 episodes are round-scoped
- `frame_id` remains session-scoped and monotonic across round and match resets
- match progress is observation context, not episode continuity
- if match-scoped episodes are ever explored later, they should be a deliberate experiment with a new policy section and likely a `match_id`

## Proposed Configuration Surface

Add a new runtime config block independent from netplay.

Suggested fields in `configuration.h`:

- `enabled`
- `player`
- `remote_ip`
- `obs_port`
- `action_port`
- `obs_schema_version`
- `action_encoding_mode`
- `decision_delay_frames`
- `decision_interval_frames`
- `action_hold_frames`
- `fallback_mode`
- `feature_flags`
- `debug_snapshot_interval`
- `transition_log_path`

Suggested config keys in `src/port/config/config.h` / `config.c`:

- `rl-agent-enabled`
- `rl-agent-player`
- `rl-network`
- `rl-agent-remote-ip`
- `rl-agent-obs-port`
- `rl-agent-action-port`
- `rl-agent-action-encoding-mode`
- `rl-agent-delay-frames`
- `rl-agent-decision-interval`
- `rl-agent-action-hold`
- `rl-agent-fallback-mode`
- `rl-agent-debug-snapshot-interval`

Suggested CLI flags in `src/args.c`:

- `--rl-agent`
- `--rl-network`
- `--rl-player`
- `--rl-remote-ip`
- `--rl-obs-port`
- `--rl-action-port`
- `--rl-action-encoding-mode`
- `--rl-delay`
- `--rl-decision-interval`
- `--rl-action-hold`

## Recommended File Touches

New files:

- `src/rl/rl_bridge.h`
- `src/rl/rl_bridge.c`
- `src/rl/rl_protocol.h`
- `src/rl/rl_action_queue.h`
- `src/rl/rl_action_queue.c`
- `src/rl/rl_observation.h`
- `src/rl/rl_observation.c`
- `src/rl/rl_reward.h`
- `src/rl/rl_reward.c`
- `src/rl/rl_session.h`
- `src/rl/rl_session.c`

Keep out of RL implementation:

- `src/netplay/*`
- upstream P2P session objects
- Gekko-specific packet or rollback APIs
- `MODE_NETWORK` control flow

Existing files likely to change:

- `src/main.c`
  - input override hook after `keyConvert()`
  - per-frame RL bridge tick
- `src/sf33rd/Source/Game/game.c`
  - end-of-frame observation/reward hook after `hit_check_main_process()`
- `src/configuration.h`
  - new RL configuration block
- `src/args.c`
  - new CLI options
- `src/port/config/config.h`
  - new config keys
- `src/port/config/config.c`
  - defaults
- `vendor/Main_MiSTer/thirdsarm_wrapper.cpp`
  - MiSTer OSD launch toggle
  - persisted RL launch-mode config
  - wrapper-side launch arg injection
- `vendor/Menu_MiSTer/menu.sv`
  - `CONF_STR` entry for `RL Agent (Restart)`
  - status bit allocation for wrapper polling

Potential shared refactor:

- move `src/netplay/game_state.c` / `game_state.h` into a shared serialization module if you want snapshot support on MiSTer

## Milestone Tracking Checklist

Tracking convention:

- [ ] unchecked means not started or not yet verified
- [ ] check a task only after it is implemented and locally verified
- [ ] check `Milestone complete` only after all `Done when` items are checked
- [ ] add commit hashes, build names, or test notes next to completed items as implementation progresses
- [ ] record implementation details, failed attempts, and validation notes in `docs/remote-rl-agent-engineering-log.md`

Milestone index:

- [x] Milestone 0A: Baseline match-flow confirmation spike
- [x] Milestone 0B: Facing and remap validation micro-spike
- [x] Milestone 0C: Local fake agent spike
- [x] Milestone 1: Compact observation builder
- [x] Milestone 2: Session handshake, network probe, and delay budget
- [x] Milestone 3: Remote inference only
- [x] Milestone 4: Decision ledger and transition logging
- [ ] Milestone 5: Async learner and model hot-swap
- [ ] Milestone 6: Higher-control-rate policy and curriculum

### Milestone 0A: Baseline match-flow confirmation spike

Status:

- [x] Milestone complete

Goal:

- [x] Confirm that `MODE_VERSUS + rl_session_active` is a workable base flow

Tasks:

- [x] Force one side to player-controlled input and the other to CPU through `Operator_Status` / `wk->wu.operator`
- [x] Run a short end-to-end spike in `MODE_VERSUS`
- [x] Verify round start behavior
- [x] Verify round end behavior
- [x] Verify winner flow behavior
- [x] Verify reset behavior
- [x] Verify no blocking regressions require falling back to a training-based baseline

Done when:

- [x] The match runs with one remote-agent slot and one CPU slot
- [x] Round and winner flow behave predictably enough to automate
- [x] Training flow is not needed as the initial baseline

### Milestone 0B: Facing and remap validation micro-spike

Status:

- [x] Milestone complete

Goal:

- [x] Verify the `rl_flag` facing contract before building the rest of the relative-direction stack

Tasks:

- [x] Add a temporary RL validation path that can keep the non-agent side on human input for deterministic facing/remap testing
- [x] Expose concise RL debug overlay state such as `P1C`, `P1H`, `P2C`, and `P2H` so the current routing is visible during spot checks
- [x] Add a fixed RL movement validation selector for `forward`, `back`, `jump-forward`, and `down-back`
- [x] Verify `plw[i].wu.rl_flag == 0` means facing world-left and maps to `self_facing_sign = -1`
- [x] Verify `plw[i].wu.rl_flag == 1` means facing world-right and maps to `self_facing_sign = +1`
- [x] Verify `opp_in_front` matches on-screen relative positioning across side switches
- [x] Verify `RL_MOVE_FORWARD` remaps to the correct raw `SWKey` direction bits immediately before input latch
- [x] Verify `RL_MOVE_BACK` remaps to the correct raw `SWKey` direction bits immediately before input latch
- [x] Verify a delayed relative action still moves in the intended direction if characters switch sides between `obs_frame` and `target_frame`
- [x] Verify `down_back_static` fallback uses the same remap logic
- [x] Verify `down_back_when_movable` fallback uses the same remap logic

Done when:

- [x] Facing signs match observed character facing on both sides
- [x] Forward/back remapping is correct before and after side switches
- [x] Delayed execution does not invert intended forward/back movement
- [x] Fallback directional actions use the same verified remap path

### Milestone 0C: Local fake agent spike

Status:

- [x] Milestone complete

Goal:

- [x] Prove AI-vs-CPU control and reset behavior without networking

Tasks:

- [x] Add a local scripted override path that writes scheduled actions into the chosen player's raw input buffer
- [x] Confirm `wk->wu.operator` split behaves correctly
- [x] Confirm the non-agent side still runs `cpu_algorithm()`
- [x] Confirm action hold behavior locally
- [x] Confirm local reset behavior clears stale scheduled actions

Done when:

- [x] The agent-controlled side can move and attack
- [x] The CPU side still fights normally
- [x] No menu or round-flow regressions are observed

### Milestone 1: Compact observation builder

Status:

- [x] Milestone complete

Goal:

- [x] Build and print/log `RLObservationV1` locally

Tasks:

- [x] Add end-of-frame observation hook after `hit_check_main_process()`
- [x] Capture `round_start_hp[i]` at the defined playable-round boundary
- [x] Build all fixed `RLObservationV1` fields from the schema table
- [x] Serialize compact observations to a local file or debug print
- [x] Validate positions against on-screen movement
- [x] Validate HP, super, stun, attack state, guard state, and round state against gameplay
- [x] Validate `last_executed_*`, `next_scheduled_*`, and `frames_until_next_action`
- [x] Measure observation build cost on MiSTer or the closest available target

Done when:

- [x] Observation fields match visible gameplay and expected internal state
- [x] Observation action-context fields use relative move intent plus attack bits, not raw absolute direction masks
- [x] Observation build cost is acceptable on MiSTer

Current read:

- [x] Observation bring-up is good enough to continue development
- [x] `RL Debug` overlay is now trustworthy for raw HP and logical input display
- [x] The runtime `RLObservationV1` implementation now matches the canonical schema in section `4A`
- [x] Corner-distance and action-context fields are now in the implementation path
- [x] `RL Debug` overlay now exposes enough state to validate position / guard / attack / round / action-context on MiSTer
- [x] `RL Debug` labels and docs now reflect validated raw-state semantics for `guard_flag`, `current_attack`, `do_not_move`, `hit_stop`, `high_jump_flag`, and `routine_no`
- [x] Observation build-cost measurement is now available in `RL Debug`
- [x] Human-fighter observer gaps are documented for Milestone 4 / Milestone 6 review without blocking Milestone 2

MiSTer validation matrix:

1. Enable from OSD:
   - `RL Settings -> RL Agent (Restart) = Player 1` or `Player 2`
   - `RL Settings -> RL Opponent (Restart) = CPU`
   - `FPS Counter = RL Debug`
   - `Restart`
2. Routing check:
   - overlay label shows `P1C` or `P2C`
   - turning `FPS Counter = Off` hides the overlay
3. Overlay line layout:
   - line 1: `P1C HP160/160 OP160/160 R2 RW1-0 M3-2`
   - line 2: `SA0/2 SG24/72 ST0/64`
   - line 3: `DXR42 DY0 F1`
   - line 4: `CL20 CR364 OL280 OR104`
   - line 5: `CF0/3 AK010/000`
   - line 6: `NM0/0 HS0/0 HJ0/0`
   - line 7: `SR4,0,1 OR4,4,18`
   - line 8: `X4/010 N0/000 T12 O8/67us`
   - input row: `U D L R LP MP HP LK MK HK`, white when idle and red when active
4. Summary / resource check:
   - line 1: `HP` / `OP` raw values track visible health bars
   - line 1: `R` tracks the current round, `RW` tracks current-match round wins, and `M` tracks cumulative VS match wins
   - line 2: `SA` / `SG` / `ST` track stock count, gauge fill, and stun gain/reset
5. Space / facing / corner check:
   - line 3: `DX` changes with horizontal spacing
   - line 3: `DY` changes when one side jumps
   - line 3: `F` flips after side switch
   - line 4: `CL/CR/OL/OR` shrink toward the corresponding corner and expand away from it
6. Combat-state check:
   - line 5: `CFself/opp` enters the expected combat/contact states during block, hit, and throw interactions
   - line 5: `AKself/opp` changes when either side enters an attack and matches the expected button-category code
   - line 6: `NM`, `HS`, and `HJ` are interpreted as raw movement-gate / contact-stop / high-jump flags, not generic movement or airborne booleans
   - line 7: routine triplets move as characters transition between pre-fight / neutral / attack / damage / catch states
7. Action-context check:
   - line 8: `Xmove/atk` matches the action executing this frame
   - line 8: `Nmove/atk` matches the next scripted fake-agent action
   - line 8: `T` counts down toward the next action swap
   - input row button tokens stay white when released and turn red only for active RL-side buttons
8. Cost check:
   - line 8: `Oavg/maxus` is the observation build cost in microseconds
   - pass criteria for Milestone 1: cost remains low, stable, and comfortably below frame-budget concern during live play

Recommended runtime matrix:

- `P1C` with `rl-network = on`: primary remote-policy bring-up against CPU; watch `OBS/Q/EX`, action-context countdown, and transition export counters
- `P2C` with `rl-network = on`: repeat the same checks from the opposite side to catch self/opp perspective mistakes
- `P1C` / `P2C` with `rl-network = off`: older local fake-agent fallback path for basic non-network sanity checks
- `P1H` / `P2H` with `rl-network = on`: same remote-policy path as `P1C` / `P2C`, but against human input on the other side
- `P1H` / `P2H` with `rl-network = off`: use `RL Movement = Forward / Back / Jump Forward / Down Back` to sanity-check that relative move-intent labels still agree with remapped directions

Suggested test sequence:

1. Start with `P1C` or `P2C` plus `rl-network = on`:
   - validate remote handshake, queue/execution counters, and basic action delivery without human-input variables
2. Move to `P1H` or `P2H` plus `rl-network = on`:
   - validate the real remote-policy path while a human controls the other side
3. Finish with `P1H` or `P2H` plus `rl-network = off`:
   - run the deterministic movement remap checks (`Forward`, `Back`, `Jump Forward`, `Down Back`)

### Milestone 2: Session handshake, network probe, and delay budget

Status:

- [x] Milestone complete

Goal:

- [x] Agree on session config and measure the real transport envelope before choosing final control timing

Tasks:

- [x] Add `RLSessionHello`
- [x] Add `RLSessionAck`
- [x] Add `config_hash` generation and validation
- [x] Reject mismatched protocol versions
- [x] Reject mismatched observation schema versions
- [x] Reject unsupported action encoding modes
- [x] Reject unsupported timing configs
- [x] Reject unsupported feature flags
- [x] Add a minimal ping/pong packet path between MiSTer and the remote PC
- [x] Measure RTT
- [x] Measure jitter
- [x] Add local p50 latency calculation helper
- [x] Add local p95 latency calculation helper
- [x] Add local p99 latency calculation helper
- [x] Measure p50 latency on target network
- [x] Measure p95 latency on target network
- [x] Measure p99 latency on target network
- [x] Choose `k` from measured data
- [x] Choose `decision_interval_frames` from measured data
- [x] Choose `action_hold_frames` from measured data

Current implementation notes:

- `src/rl/rl_protocol.*` defines the Milestone 2 protocol data layer:
  - `RLSessionHello`
  - `RLSessionAck`
  - `RLSessionConfig`
  - deterministic FNV-1a `config_hash`
  - ack/config validation helpers
  - sorted-sample p50/p95/p99 probe-stat helper
- `src/rl/rl_net.*` currently provides a no-op disabled network state:
  - no socket is opened unless RL agent mode is active, RL network mode is enabled, and `rl-agent-remote-ip` / `--rl-remote-ip` is set
  - the first live path sends `HELLO`, waits for `ACK`, then sends periodic `PING` packets and accepts `PONG`
  - gameplay input behavior is unchanged; the probe only updates network state and RTT statistics
  - current default timing is `decision_interval_frames = 4`, `action_hold_frames = 4`, `candidate_k_delay_frames = 4`
- `tools/rl_probe_server.py` is the first remote-side validation server for this path.
- `RL Debug` overlay appends a compact network line:
  - `NETOFF`: no remote probe configured
  - `NETHELLO`: UDP socket is open and MiSTer is sending hello packets
  - `NETOK`: hello/ack succeeded and ping/pong samples are accumulating
  - `NETERR`: probe was configured but socket setup failed
  - `S`: sample count
  - `P`: p50/p95/p99 RTT in microseconds
  - `MAX`: max RTT in microseconds
  - `E`: socket/send/recv error count
- `RL Debug` also appends an action gate line:
  - `ACT`: all action packets received on the action socket
  - `OK`: action packets accepted by the Milestone 2 session gate
  - `UA`: rejected before hello/ack acceptance
  - `SN`: rejected because `session_nonce` was stale or mismatched
  - `BV`: rejected because version/header was invalid
  - `BM`: rejected because packet size was malformed
- MiSTer now opens a local non-blocking action UDP socket on `rl-agent-action-port` and applies session gating before any later Milestone 3 queue/execution logic.
- accepted action packets are counted but not yet executed; queueing and target-frame execution remain Milestone 3 work.
- target-network measurement has now been run on the actual MiSTer + remote PC network:
  - `S128`
  - `p50 = 16819us`
  - `p95 = 17568us`
  - `p99 = 20752us`
  - `max = 30718us`
- chosen first measured baseline:
  - `candidate_k_delay_frames = 4`
  - `decision_interval_frames = 4`
  - `action_hold_frames = 4`

Local / MiSTer validation steps:

1. On the remote PC, run:
   - `python3 tools/rl_probe_server.py --host 0.0.0.0 --port 37330 --verbose`
2. Launch MiSTer with RL enabled and remote probe settings:
   - set `games/3s-arm/config`:
     - `rl-agent-remote-ip = <remote_pc_ip>`
     - `rl-agent-obs-port = 37330`
     - `rl-agent-action-port = 37331`
   - set OSD `RL Settings -> RL Network (Restart) = On`
   - restart through the wrapper
3. In OSD, set `FPS Counter = RL Debug`.
4. Expected overlay progression:
   - without remote IP: `NETOFF`
   - with remote IP before ack: `NETHELLO`
   - after ack/pong: `NETOK S... Pp50/p95/p99 MAX...us E0`
5. Record p50/p95/p99/max RTT from the overlay after at least 128 samples.
6. Current measured baseline result:
   - `NETOK S128 P16819/17568/20752 MAX30718`
   - use `k = 4`, `decision_interval_frames = 4`, `action_hold_frames = 4` as the first conservative runtime baseline
7. Session-gate validation:
   - run `python3 tools/rl_probe_server.py --host 0.0.0.0 --port 37330 --action-port 37331 --action-mode pre-ack --verbose`
   - before handshake acceptance stabilizes, `ACT` should increase and `UA` should increase
   - run `python3 tools/rl_probe_server.py --host 0.0.0.0 --port 37330 --action-port 37331 --action-mode stale --verbose`
   - after `NETOK`, `ACT` should increase and `SN` should increase
   - run `python3 tools/rl_probe_server.py --host 0.0.0.0 --port 37330 --action-port 37331 --action-mode valid --verbose`
   - after `NETOK`, `ACT` should increase and `OK` should increase

Done when:

- [x] Remote inference does not accept actions until hello/ack config is accepted
- [x] MiSTer rejects actions from unacknowledged or stale `session_nonce`
- [x] Transport timing is measured on the actual target network
- [x] Delay knobs are chosen from data, not guesses

### Milestone 3: Remote inference only

Status:

- [x] Milestone complete

Goal:

- [x] Connect MiSTer to a remote rule-based or heuristic server

Tasks:

- [x] Add non-blocking UDP socket setup
- [x] Add minimal `ObsPacket` header send path on decision frames
- [x] Add `ActionPacket` receive path
- [x] Add pending action queue keyed by `target_frame`
- [x] Validate `(episode_id, decision_id, target_frame)` duplicate rules
- [x] Reject `ActionPacket.target_frame` mismatches against the minimal in-flight expectation table
- [x] Add default fallback mode using `action_hold_frames`
- [x] Add telemetry counters for packet miss, late packet, duplicate packet, target mismatch, and fallback usage
- [x] Start with fixed measured `k`
- [x] Implement a minimal remote heuristic server path in `tools/rl_probe_server.py`

Done when:

- [x] Stable packet flow is observed
- [x] Actions execute on their intended target frames
- [x] Side-switch delayed actions keep correct relative direction
- [x] No gameplay stalls occur when packets drop

Implementation notes:

- MiSTer now sends a minimal `RLObsPacketHeader` on decision frames and records in-flight expectations as `(episode_id, decision_id, target_frame)` tuples.
- `RLActionPacket` that passes the Milestone 2 gate is now checked against that in-flight expectation table before queueing.
- `RL Debug` keeps the Milestone 2 gate counters and adds Milestone 3 counters:
  - `OBS`: observation headers successfully sent
  - `Qx/y`: current queue depth / total queued accepted actions
  - `EX`: executed queued actions
  - `LT`: late action drops
  - `DU`: duplicate action drops or queue-capacity collisions
  - `TM`: target-mismatch rejects against the minimal expectation table
  - `FB`: fallback executions when a due target frame had no valid queued action
- `tools/rl_probe_server.py` now also accepts Milestone 3 observation headers and sends a fixed action that echoes the incoming `episode_id`, `decision_id`, and `target_frame`.
- duplicate handling now follows the v1 rule more closely:
  - first accepted `(episode_id, decision_id, target_frame)` is kept
  - later arrivals with the same tuple increment `DU`
  - later arrivals with the same `(episode_id, decision_id)` but a different `target_frame` increment `TM`
- `tools/rl_probe_server.py --obs-reply-mode duplicate|wrong-target` can now force those two protocol cases on hardware.
- Hardware validation on 2026-04-22:
  - fixed `forward` policy reached steady-state packet flow with `OBS891 Q1/890 EX886 LT1 DU0 TM0 FB1`
  - fixed `hp` policy originally lit the overlay without producing a punch because the MVP path held attack buttons for the full action-hold window
  - remote execution now pulses attack bits for one frame while still holding movement for `action_hold_frames`; hardware retest confirmed `hp` now throws punches correctly

### Milestone 4: Decision ledger and transition logging

Status:

- [x] Milestone complete

Goal:

- [x] Make the environment actually trainable

Tasks:

- [x] Add decision ledger keyed by `(episode_id, decision_id)`
- [x] Review the action-outcome and event-delta candidates from the Human-Fighter Observer Gap Review
- [x] Record `obs_frame`
- [x] Record `target_frame`
- [x] Record `requested_action_wire`
- [x] Record `executed_action_wire`
- [x] Record `execution_frame_actual`
- [x] Record `execution_source`
- [x] Accumulate reward over the executed decision interval
- [x] Align done flags with round-scoped episode boundaries
- [x] Export transitions to the remote learner path
- [x] Decode `executed_action_wire` into `executed_move_intent` and `executed_attack_bits` in logs

Done when:

- [x] Each transition includes episode id
- [x] Each transition includes decision id
- [x] Each transition includes observation frame
- [x] Each transition includes target frame
- [x] Each transition includes requested action wire
- [x] Each transition includes executed action wire
- [x] Each transition includes execution frame actual
- [x] Each transition includes reward span
- [x] Each transition includes done flag
- [x] Each transition includes execution source and decoded executed move/attack fields

Implementation notes:

- Milestone 3 is now closed after hardware validation of:
  - stable packet flow
  - duplicate and wrong-target rejection
  - delayed forward/back side-switch behavior
- `src/rl/rl_session.c` now keeps a fixed-size decision ledger keyed by `(episode_id, decision_id)`.
- Each ledger entry currently records:
  - `episode_id`
  - `decision_id`
  - `agent_character_id`
  - `agent_character_name`
  - `opponent_character_id`
  - `opponent_character_name`
  - `obs_frame`
  - `target_frame`
  - `requested_action_wire`
  - decoded `requested_move_intent`
  - decoded `requested_attack_bits`
  - `executed_action_wire`
  - `was_executed`
  - `execution_frame_actual`
  - `execution_source`
  - `executed_move_intent`
  - `executed_attack_bits`
  - `reward_accum`
  - `done`
  - `terminal_reason`
- Transitions are accumulated as per-episode NDJSON batches and uploaded to the probe server transition port.
- MiSTer no longer writes local per-row `logs/rl-transitions.ndjson` files; this avoids synchronous SD/FAT writes in the frame hot path.
- Current reward baseline:
  - per-frame `delta_opp_hp - delta_self_hp`
  - `+100` round win bonus
  - `-100` round loss penalty
- Milestone 4 closeout hardware validation:
  - last sampled ledger window: `rows=274`
  - `overlay_attack_events=23`
  - `overlay_attack_contacts=3`
  - `overlay_attack_whiffs=20`
  - `last_ah=23`
  - `last_acc=3`
  - `last_awc=20`
  - event totals matched the RL Outcome overlay `AC/AW/AH/ACC/AWC` counters
- [x] Transition schema has an explicit decision on whether to include first-pass action outcome / delta fields
- [x] Transition schema has a first-pass action outcome / delta field set
- [x] Learner-side replay buffer can distinguish remote action, repeated-last-action, down-back fallback, and neutral fallback
- [x] Transition schema is documented as an evolving debug/training schema, not a frozen learner contract
- Character identity closeout:
  - every transition records the agent and opponent SF3 character IDs / names from runtime `My_char[self/opp]`
  - learner import should treat `*_character_id` as canonical and `*_character_name` as debug-friendly metadata

Current first-pass action outcome / delta fields:

- runtime `RLObservationV1` now exposes:
  - `delta_self_hp`, `delta_opp_hp`
  - `delta_self_x`, `delta_self_y`
  - `delta_opp_x`, `delta_opp_y`
  - `delta_self_stun`, `delta_opp_stun`
  - `self_airborne`, `opp_airborne`
  - `self_entered_hit_stop`, `opp_entered_hit_stop`
  - `self_entered_contact_state`, `opp_entered_contact_state`
  - `self_entered_damage_state`, `opp_entered_damage_state`
- transition NDJSON now exports decision-span aggregates for:
  - `agent_character_id`, `opponent_character_id`
  - `agent_character_name`, `opponent_character_name`
  - `delta_self_hp`, `delta_opp_hp`
  - `delta_self_stun`, `delta_opp_stun`
  - `delta_self_x`, `delta_self_y`
  - `delta_opp_x`, `delta_opp_y`
  - `delta_self_forward`, `delta_opp_forward`
  - `self_airborne_seen`, `opp_airborne_seen`
  - `self_entered_hit_stop`, `opp_entered_hit_stop`
  - `self_entered_contact_state`, `opp_entered_contact_state`
  - `self_entered_damage_state`, `opp_entered_damage_state`
  - `requested_movement_succeeded`
  - `requested_attack_entered_state`
  - `requested_attack_made_contact`
  - `requested_attack_likely_whiffed`
  - `requested_attack_input_started`
  - `requested_attack_became_active`
  - `observed_attack_state_started`
  - `observed_attack_code_changed`
  - `observed_attack_counter_started`
  - `overlay_attack_event_finalized`
  - `overlay_attack_contact`
  - `overlay_attack_whiff`
  - `overlay_attack_active_count`
  - `overlay_attack_contact_count`
  - `overlay_attack_whiff_count`
  - `self_attack_started`, `opp_attack_started`
  - `self_attack_code_changed`, `opp_attack_code_changed`
  - `self_attack_counter_started`, `opp_attack_counter_started`
  - `self_attack_routine_started`, `opp_attack_routine_started`
  - `self_airborne_started`, `opp_airborne_started`
- the decision-span delta/event aggregation is now driven from `RLObservation_OnFrameEnd()` so it tracks post-logic frame results instead of pre-logic input staging
- `delta_self_x/y` and `delta_opp_x/y` are world-coordinate deltas.
- `delta_self_forward` and `delta_opp_forward` are facing-relative deltas:
  - positive means moving forward relative to that character's facing
  - negative means moving backward
- `delta_self_stun` and `delta_opp_stun` are signed:
  - positive means stun increased
  - negative means stun recovered
- `entered_contact_state` is currently a conservative derived signal based on `guard_flag != 0 || hit_stop`; it is not a precise hit/block result.
- `was_executed=false` terminal entries should stay in debug logs, but the first learner replay buffer should filter them unless it explicitly wants canceled decisions.
- `agent_character_id` / `opponent_character_id` identify the actual SF3 characters for matchup-aware training; names are included for readability.
- `logs/rl-transitions.ndjson` is still an evolving debug/training schema. Do not treat it as a frozen learner contract until the replay-buffer import path is implemented.
- `requested_attack_input_started` means this decision actually executed an attack-button pulse.
- `requested_attack_became_active` means the defender-side `Attack_Counter` edge fired for this requested attack. Today this is the closest runtime proxy for "the game actually accepted a new attack" and is the better field for counting real punch/kick starts.
- `observed_attack_state_started` is the stricter runtime `current_attack: 0 -> nonzero` edge. It can undercount repeated punches if the engine keeps `current_attack` nonzero across many decision windows.
- `observed_attack_code_changed` means runtime `current_attack` changed into a nonzero code during the decision window. Treat both observed attack fields as debug / reverse-engineering signals unless a later milestone proves they help the learner.
- `observed_attack_counter_started` mirrors the defender-side `Attack_Counter` edge and should stay close to `requested_attack_became_active` for attack-request windows.
- `requested_attack_entered_state`, `requested_attack_made_contact`, and `requested_attack_likely_whiffed` are older decision-window heuristics. Keep them for bring-up comparison, but do not use them as the primary attack counter.
- `overlay_attack_event_finalized`, `overlay_attack_contact`, and `overlay_attack_whiff` mirror the verified RL overlay event logic. Count only rows with `overlay_attack_event_finalized == 1` when validating real attack/contact/whiff totals from the ledger.
- `overlay_attack_active_count`, `overlay_attack_contact_count`, and `overlay_attack_whiff_count` are the current round's cumulative attack-event counters at export time.
- `self_airborne_seen` / `opp_airborne_seen` are span-level state-seen flags. Use `self_airborne_started` / `opp_airborne_started` when counting jump/airborne entry edges.
- `RL Debug` is now split by `rl-debug-view` / OSD `RL Debug View`:
  - `All`: broad bring-up view for fight/input/net state, excluding the dedicated combat-event outcome page
  - `Net`: network / action-gate / queue counters
  - `Input`: action context plus colored input row
  - `Fight`: match, resources, spacing, and raw combat state
  - `Outcome`: combat-event counters/results only (`AH`/`CE`/`CER`/`CEU`/`CP`/`CPR`/lifetime lines)
  - `Off`: keeps `show-fps = rl-debug` selected but hides the RL text
- deferred for a later schema revision because the current runtime source is not yet trustworthy enough:
  - `self_crouching`, `opp_crouching`
  - richer movement phase labels
  - explicit `hit / blocked / whiff / throw` outcome enums

### First Learner-Safe Replay Subset

Until the replay-buffer import path is implemented and validated, the first learner should not ingest the full transition ledger as if every field were equally trustworthy.

Recommended v1 learner whitelist:

- replay row keys:
  - `run_id`
  - `episode_id`
  - `decision_id`
  - `round_num`
  - `obs_frame`
  - `target_frame`
- action actually trained against:
  - `executed_action_wire`
  - `executed_move_intent`
  - `executed_attack_bits`
  - `execution_source`
- reward / termination:
  - `reward_accum`
  - `done`
  - `terminal_reason`
- compact outcome and delta fields:
  - `delta_self_hp`, `delta_opp_hp`
  - `delta_self_stun`, `delta_opp_stun`
  - `delta_self_x`, `delta_self_y`
  - `delta_opp_x`, `delta_opp_y`
  - `delta_self_forward`, `delta_opp_forward`
  - `overlay_attack_event_finalized`
  - `overlay_attack_contact`
  - `overlay_attack_whiff`
- replay metadata:
  - `agent_character_id`
  - `opponent_character_id`
  - `model_version_executed`

Recommended v1 replay-buffer filters:

- filter out `was_executed == false` rows unless the experiment explicitly wants canceled decisions
- dedupe imported rows by `(run_id, episode_id, decision_id)`
- treat `execution_source` as replay metadata and sample-control information first, not as a gameplay observation feature
- treat `agent_character_name` / `opponent_character_name` as debug-only labels

Fields that should remain debug / analysis-only in the first learner import:

- requested-action fields:
  - `requested_action_wire`
  - `requested_move_intent`
  - `requested_attack_bits`
- older decision-window heuristics:
  - `requested_movement_succeeded`
  - `requested_attack_entered_state`
  - `requested_attack_made_contact`
  - `requested_attack_likely_whiffed`
  - `requested_attack_input_started`
  - `requested_attack_became_active`
- reverse-engineering / runtime attack-state signals:
  - `observed_attack_state_started`
  - `observed_attack_code_changed`
  - `observed_attack_counter_started`
  - `self_attack_started`, `opp_attack_started`
  - `self_attack_code_changed`, `opp_attack_code_changed`
  - `self_attack_counter_started`, `opp_attack_counter_started`
  - `self_attack_routine_started`, `opp_attack_routine_started`
- cumulative counters:
  - `overlay_attack_active_count`
  - `overlay_attack_contact_count`
  - `overlay_attack_whiff_count`

Rationale:

- the learner should train primarily on what actually executed, not only on what the remote service intended to send
- HP / stun / position deltas are accumulated from post-logic frame observations and are the most trustworthy compact outcome signals available today
- `overlay_attack_*` fields are useful auxiliary labels, but should not yet be treated as universally correct attack-result truth across every move family

### V1 Reward Interpretation

Current v1 reward remains intentionally simple:

- per-frame reward contribution:
  - `delta_opp_hp - delta_self_hp`
- episode-close bonus:
  - `+100` for winning the round
  - `-100` for losing the round

What this means for defense and avoidance:

- the first learner does not get a dedicated "good block", "good backdash", or "good evade" scalar in every transition
- instead, defense is learned indirectly through delayed credit:
  - defensive movement that avoids later damage should improve future return because `delta_self_hp` stays lower
  - successful avoidance that creates a later punish opportunity should also be credited through later positive reward
- this is a sparse signal for defense, so sequence credit assignment and later curriculum / human-demo support are expected to matter

Do not overread the attack-outcome helpers in v1:

- `overlay_attack_event_finalized` / `overlay_attack_contact` / `overlay_attack_whiff` are acceptable as auxiliary replay labels and analysis counters
- do not yet use them as the sole reward or universal "success/failure" truth for normals, specials, projectiles, throws, and multistage moves
- if later reward shaping wants explicit punish / whiff / defensive-success bonuses, promote those only after move-family validation and schema-versioned notes

Useful jq validation recipes:

```bash
# Count nonzero movement outcomes in the last 1000 transitions.
tail -n 1000 logs/rl-transitions.ndjson | jq -s '{
  rows: length,
  self_forward_nonzero: map(select(.delta_self_forward != 0)) | length,
  movement_succeeded: map(select(.requested_movement_succeeded == 1)) | length,
  attack_entered: map(select(.requested_attack_entered_state == 1)) | length,
  attack_contact: map(select(.requested_attack_made_contact == 1)) | length,
  attack_whiff: map(select(.requested_attack_likely_whiffed == 1)) | length,
  attack_input_started: map(select(.requested_attack_input_started == 1)) | length,
  attack_became_active: map(select(.requested_attack_became_active == 1)) | length,
  observed_attack_state_started: map(select(.observed_attack_state_started == 1)) | length,
  observed_attack_code_changed: map(select(.observed_attack_code_changed == 1)) | length,
  observed_attack_counter_started: map(select(.observed_attack_counter_started == 1)) | length,
  overlay_attack_events: map(select(.overlay_attack_event_finalized == 1)) | length,
  overlay_attack_contacts: map(select(.overlay_attack_event_finalized == 1 and .overlay_attack_contact == 1)) | length,
  overlay_attack_whiffs: map(select(.overlay_attack_event_finalized == 1 and .overlay_attack_whiff == 1)) | length,
  self_airborne_started: map(select(.self_airborne_started == 1)) | length,
  opp_stun_increased: map(select(.delta_opp_stun > 0)) | length,
  opp_stun_recovered: map(select(.delta_opp_stun < 0)) | length,
  unexecuted: map(select(.was_executed == false)) | length
}'

# Inspect recent movement outcomes.
tail -n 40 logs/rl-transitions.ndjson | jq '{
  decision_id,
  requested_move_intent,
  executed_move_intent,
  delta_self_x,
  delta_self_forward,
  requested_movement_succeeded,
  execution_source,
  was_executed
}'

# Inspect recent attack outcomes.
tail -n 80 logs/rl-transitions.ndjson | jq 'select(.requested_attack_bits != 0) | {
  decision_id,
  requested_attack_bits,
  executed_attack_bits,
  requested_attack_input_started,
  requested_attack_became_active,
  requested_attack_entered_state,
  observed_attack_state_started,
  observed_attack_code_changed,
  observed_attack_counter_started,
  requested_attack_made_contact,
  requested_attack_likely_whiffed,
  delta_opp_hp,
  delta_opp_stun
}'

# Group recent transition rows by matchup.
tail -n 2000 logs/rl-transitions.ndjson | jq -s '
  group_by(.agent_character_name + "_vs_" + .opponent_character_name)
  | map({
      matchup: .[0].agent_character_name + "_vs_" + .[0].opponent_character_name,
      rows: length,
      overlay_attack_events: map(select(.overlay_attack_event_finalized == 1)) | length,
      overlay_attack_contacts: map(select(.overlay_attack_event_finalized == 1 and .overlay_attack_contact == 1)) | length,
      overlay_attack_whiffs: map(select(.overlay_attack_event_finalized == 1 and .overlay_attack_whiff == 1)) | length
    })'
```

### Milestone 5: Async learner and model hot-swap

Status:

- [ ] Milestone complete

Goal:

- [ ] Train online without stalling gameplay

Tasks:

- [x] Split inference and learner services
- [x] Keep training work off the critical action path
- [x] Publish versioned actor weights
- [x] Atomically hot-swap actor weights
- [x] Include `model_version_current` in session ack or telemetry
- [x] Include model version in action/transition logs
- [x] Track inference latency while training is active

Done when:

- [ ] Action latency stays stable during training
- [x] Model version changes are visible in logs and packets
- [x] Inference continues to respond while learner updates weights

Implementation notes:

- Protocol v2 adds persisted `run_id` identity to observation, action, transition-batch, and transition-batch-ack packets.
- MiSTer persists the last allocated `run_id` in `logs/rl-run-state.txt` and allocates a new run id when the RL runtime initializes.
- `episode_id` is now a per-run round rollout sequence instead of `Round_num`; transition rows include `round_num` separately for analysis.
- Ledger HP reward accumulation now uses cumulative round damage deltas from raw HP snapshots, and transition rows include `start_self_hp`, `start_opp_hp`, `final_self_hp`, and `final_opp_hp` for validation.
- Round episode changes now follow `Round_num` instead of `PL_Wins` / `VS_Win_Record` mutations, which avoids empty skipped episode ids during round-end bookkeeping.
- The learner replay importer dedupes by `(run_id, episode_id, decision_id)`.
- First Milestone 5 slice adds model-version plumbing without introducing training work on the critical action path.
- Live learner/inference validation now shows publish-to-execute catch-up on real traffic:
  - one sampled window still lagged with `model_exec=346` while `model_active=model_pub=model_load=351`
  - a later sampled window reached `model_exec=352 model_active=352 model_pub=352 model_load=352` immediately after `MODEL published version=352`
  - treat this as current evidence that actor hot-swap is reaching executed transitions, not just manifest publication
- A later sample strengthened that conclusion further:
  - `rows=4603 done=16 sources=neutral-fallback:1,remote:4602`
  - `model_exec=375 model_active=376 model_pub=376 model_load=376`
  - this suggests the execute path is typically trailing the active actor by only one version, which is acceptable for the current async publish flow
- The current live run also showed `sources=neutral-fallback:1,remote:3083`, which suggests fallback execution is rare enough that Milestone 5 logs are mostly reflecting remote-policy decisions.
- The old `inf=512:0/0/16000us` summary was traced to a probe-server telemetry bug:
  - service-time samples were truncated to integer microseconds before aggregation
  - short OBS-to-action work often collapsed to `0`
  - the remaining visible outlier was often a scheduler-scale spike near `16000us`
- The probe server now measures with `perf_counter_ns()` and aggregates raw nanosecond samples before printing fractional microseconds.
- Do not mark `Action latency stays stable during training` complete until fresh live logs are collected with the fixed `inf=` telemetry.
- Transition export has now been slimmed to reduce runtime cost:
  - serialized transition rows no longer include duplicated character-name strings
  - several debug-only span-state / attack-heuristic / running-count fields are no longer written into NDJSON or sent in episode batches
  - finalized rows are now formatted once and reused for both local append and remote batch accumulation
- The slimmer transition row now keeps a small learner-safe spacing snapshot from the decision observation:
  - `obs_abs_dx`
  - `obs_abs_dy`
  - `obs_self_front_edge_dist`
  - `obs_self_back_edge_dist`
  - `obs_opp_front_edge_dist`
  - `obs_opp_back_edge_dist`
  - `obs_opp_in_front`
- The transition row also carries routine-state probes:
  - decision-observation flags: `obs_self_routine_attack_state`, `obs_opp_routine_attack_state`, `obs_self_contact_reaction_state`, `obs_opp_contact_reaction_state`
  - `obs_opp_routine_attack_state` is promoted into the tabular learner state as `opp_attack=0/1` for the first strike-defense experiment
  - `obs_self_contact_reaction_state` remains outcome/debug only because live timing showed it often appears after damage/contact, not before it
- These spacing fields intentionally use raw absolute enemy distance plus facing-relative raw front/back edge distances first. Keep signed `dx/dy` and left/right corner ratios as debug/future-schema candidates unless later validation shows the learner needs the extra world-coordinate detail.
- Treat the current slimmer transition row plus the compact spacing snapshot as the default learner/debug contract unless a later Milestone 6 or validation task explicitly needs one of the removed debug-only fields restored.
- Deferred transition refinement: consider adding learner-safe SA state back into transition/replay rows after the RL loop is running reliably. The live observation already carries `self_super_stock`, `self_super_gauge_ratio`, `opp_super_stock`, and `opp_super_gauge_ratio`, but replay-only learner paths may need those fields, or compact `can_super` / `opp_can_super` derivatives, to learn when supers are available.
- `RLObsPacketHeader.model_version_expected` now carries MiSTer's current executed model version to the remote service.
- `RLActionPacket.model_version` is accepted from the remote service and stored with queued/executed actions.
- Transition NDJSON now exports:
  - `model_version_expected`
  - `model_version_requested`
  - `model_version_executed`
- RL net overlay shows `MV` for the currently executed model version.
- Current Windows-to-WSL live learner/inference launch command:
  ```sh
  python \\wsl.localhost\Ubuntu\home\olhua\src\3s-mister-arm\tools\rl_probe_server.py --host 0.0.0.0 --port 37330 --action-port 37331 --policy hp --policy-repeat-delay-ms 3000 --model-version 0 --model-dir \\wsl.localhost\Ubuntu\home\olhua\src\3s-mister-arm\model\rl-model-live --transition-log \\wsl.localhost\Ubuntu\home\olhua\src\3s-mister-arm\logs\rl-transitions-live.ndjson --learner-auto-publish --learner-publish-interval-sec 10 --learner-warmup-rows 100 --learner-batch-size 32
  ```
- `tools/rl_probe_server.py --model-version N` stamps fixed/scripted policy action packets for bring-up.
- `tools/rl_probe_server.py --model-dir DIR` stores versioned actor manifests as `actor-vN.json` and atomically hot-swaps `current.json`.
- `tools/rl_probe_server.py --learner-auto-publish` publishes a new actor manifest from the learner/log-reader thread after replay warmup and at `--learner-publish-interval-sec`.
- inference reads the current actor manifest before replying to observation packets, so action packets use the hot-swapped actor policy and model version without blocking on learner work.
- `tools/rl_probe_server.py --transition-log PATH` now imports a learner-safe replay subset in the background log-reader thread:
  - filters out `was_executed=false` rows
  - keeps executed action, reward / done, compact delta fields, overlay attack auxiliaries, and metadata such as character IDs and executed model version
  - tracks replay capacity, warmup readiness, reward-sign counts, and execution-source mix for learner bring-up
- MiSTer now also has a first non-critical episode-batch transport:
  - finalized transition rows are accumulated in memory for the active episode
  - episode-close queues the episode's NDJSON rows for background TCP upload to the remote learner on `obs_port + 2`
  - transport runs off the action critical path and expects an ACK per uploaded episode batch
- `tools/rl_probe_server.py` now also supports a non-critical transition pull path:
  - `--transition-pull-remote-path PATH` uses read-only SCP polling to mirror a MiSTer-side transition log into the local `--transition-log`
  - `--transition-pull-local-source PATH` provides the same mirror/update flow for local smoke tests
  - `--learner-only` skips UDP bind so the pull/import path can be validated or run standalone without the live action server
- `tools/rl_probe_server.py` also accepts the episode-batch transport on TCP:
  - `--transition-port PORT` listens for uploaded episode batches and appends them into `--transition-log`
  - when `--transition-log` is set and `--transition-port` is omitted, it defaults to `--action-port + 1`
- `tools/rl_probe_server.py --policy ryu-fireball` loops a relative Ryu fireball script:
  - `DOWN`
  - `DOWN_FORWARD`
  - `FORWARD`
  - `FORWARD + LP`
  - neutral recovery frames
- `tools/rl_probe_server.py --policy throw` loops:
  - `FORWARD + LP + LK`
  - neutral recovery frames
- `tools/rl_probe_server.py --policy tatsu` loops a relative Ryu/Ken hurricane-kick script:
  - `DOWN`
  - `DOWN_BACK`
  - `BACK`
  - `BACK + LK`
  - neutral recovery frames
- `tools/rl_probe_server.py --policy shoryuken` loops a relative dragon-punch script:
  - `FORWARD`
  - `DOWN`
  - `DOWN_FORWARD`
  - `DOWN_FORWARD + HP`
  - neutral recovery frames
- `tools/rl_probe_server.py --policy-repeat-delay-ms N` holds neutral after each scripted policy loop before repeating.
- `tools/rl_probe_server.py --transition-log PATH` starts a background learner/log-reader thread while keeping UDP inference on the main path.
- the optional learner thread tails transition NDJSON and periodically reports:
  - rows / done rows / latest episode
  - attack events/contact/whiff counts
  - latest executed model version
  - latest timing config as `timing=k/decision_interval/action_hold`
  - current timing bucket size / done count / reward-sign mix as `timing_rows=... timing_done=... timing_rew=...`
  - current policy bucket size / done count / reward-sign mix as `policy_rows=... policy_done=... policy_rew=...`
  - aggregate fallback percentage as `fallback_pct=...`
  - current timing bucket fallback percentage as `timing_fallback_pct=...`
  - current policy bucket fallback percentage as `policy_fallback_pct=...`
  - inference response latency samples as `count:p50/p95/maxus`
- `tools/rl_probe_server.py --learner-tail-from-start` reads an existing transition log from the beginning; otherwise it tails only new rows.

### Milestone 6: Higher-control-rate policy and curriculum

Status:

- [ ] Milestone complete

Goal:

- [ ] Improve fighting strength after the transport/control path is proven

Tasks:

- [ ] Tune `k`
- [ ] Tune `decision_interval_frames`
- [ ] Tune `action_hold_frames`
- [x] Bring up a minimal tabular learner loop that updates actor policy from transition replay rows
- [x] Add a minimum-sample confidence gate before tabular q-scores can drive greedy inference
- [x] Avoid publishing duplicate tabular actor versions when no new learner updates arrived
- [x] Add same-frame compact spacing payloads to UDP OBS packets for tabular inference
- [x] Add `fireball` / `throw` to the first tabular action set and log ready action distributions by distance bucket
- [x] Add tabular macro-action lock so multi-step actions such as `fireball` are not interrupted by the next q-table decision
- [x] Add an anti-DP fireball macro variant to reduce accidental shoryuken credit pollution
- [x] Enable engine_* fields for remote execution (remove RLSession_IsDemoExecutionSource gate) so model actions get engine outcome attribution
- [x] Fix fireball macro walking-DP misclassification: add neutral frames to clear SF3 input buffer before fireball motion
- [x] Add a guard/back-hold macro so tabular `back` can produce a defense window instead of a single short hold
- [x] Add cross distance/threat ready-action stats for strike-defense policy diagnosis
- [x] Add `jump-forward-mk` to the tabular action set as a first active approach attack
- [x] Add a first offline DQN/MLP Q learner tool and `policy=dqn` probe inference path for q-table comparison
- [x] Add offline DQN A/B/C reward-risk profiles and same-observation model comparison tooling
- [x] Add DQN action subset training and collapse diagnostics for offline policy debugging
- [x] Add offline DQN guard success / passive guard reward shaping knobs for Phase 1 defense curriculum smoke tests
- [x] Make offline DQN replay decision-level by training only on macro step-0 action starts and delayed-crediting macro continuation rewards
- [x] Add live tabular action-subset support for Phase 1 basic-action data collection
- [x] Add jump-attack-specific DQN risk costs for high-commitment jump-in whiffs
- [x] Add DQN replay filtering for initial repeat-delay-polluted episodes and clean-window guard costs
- [x] Add offline DQN spacing reward shaping for Phase 1 movement credit
- [x] Add offline DQN corner position reward shaping for anti-turtle experiments
- [x] Add opt-in offline DQN projectile response reward shaping for safe jump-over, close back/guard success, and late jump-hit penalties
- [x] Add opt-in projectile-response replay oversampling for safe jump, late jump-hit, and close back/guard rows
- [x] Add projectile expert Q-gap diagnostics and a valid-action-masked margin loss for safe human anti-fireball jump rows
- [x] Record the V52 projectile expert margin recipe, parameters, offline findings, live-probe findings, and V53 direction in [docs/agent-memory/remote-rl-v52-projectile-margin.md](agent-memory/remote-rl-v52-projectile-margin.md)
- [x] Add projectile timing-bucket diagnostics for V53: action distribution, jump safe/damaged counts, after-current damage, Q gaps, and blockers by `obs_projectile_time_to_self` bucket
- [x] Train a V53 projectile timing-split candidate that keeps V52 jump-group margin and limits safe-jump margin to reliable timing buckets; result: not enough behavior change, late-jump defensive negative margin remains a V54 item
- [x] Document the V54/V55 late defensive margin, targeted human-demo, and live incremental retrain readiness plan in [docs/agent-memory/remote-rl-v52-projectile-margin.md](agent-memory/remote-rl-v52-projectile-margin.md)
- [x] Add explicit late-jump-hit defensive margin for V54 so urgent/borderline projectile rows can prefer `guard-stand`/`guard-crouch`/`back` over jump when jump was hit
- [x] Add an auto-retrain preset for V54/V55 so the same late defensive margin recipe can be used for live incremental retrain
- [x] Train and compare V54 late defensive margin candidates against V52/V53 before live probe or live incremental retrain; result: trainer/preset ready, current old-demo-only V54 candidates are not promotable
- [x] Document the training-mode demo transition logging plan in [docs/agent-memory/remote-rl-training-mode-demo-log.md](agent-memory/remote-rl-training-mode-demo-log.md)
- [x] Add training-mode local demo transition logging for controlled human-vs-dummy data collection without enabling remote DQN action override
- [x] Add trainer/analyzer support for opt-in training-mode damage-only HP delta rewards while preserving raw transition deltas for analysis
- [x] Collect targeted human-demo projectile defense rows for V55/live incremental retrain, especially `time_to_self <= 12` guard/back success examples
- [x] Train V55 with the targeted training-mode human-demo log; result: safe-jump Q-gap stayed strong, but urgent/borderline projectile rows still ranked jump too broadly
- [x] Add clean human-demo projectile defensive expert margin support for V57/V58, including all-competitor mode and `projectile-response-v6` preset wiring
- [x] Train and analyze V57/V58 defensive expert candidates; result: V57 moved defensive Q closer but leaked into specials, V58 preserved safe-jump but still did not make `guard`/`back` top-1 on urgent rows
- [x] Add projectile-aware batch sampling plus a clean defensive-row selector so urgent projectile guard/back examples appear reliably in every training batch; V59/V60 result: Q gaps improve but top-1 still stays jump
- [x] Add an opt-in V61 policy-time projectile timing prior for `time_to_self <= 12`: soft-penalize jump-start Q scores for close incoming opponent projectiles, skip airborne/jump-phase rows, and keep the default server behavior unchanged unless the CLI flag is enabled
- [x] Analyze the first V61 live probe; result: the prior helped close rows, but `7-12` penalty was too weak and the largest jump failures came from too-early `31-48` jump timing
- [x] Add V61b timing-window prior controls so jump can be penalized both when too-late/close and when too-early/far, while leaving the live-safe `19-30` window unpenalized
- [x] V61b live probe: use V60 weights plus timing-window prior controls, then re-check `7-12`, `19-30`, `31-48`, non-projectile behavior, and HP outcome before retraining; result: `31-48` jump disappeared but `19-22` was still slightly early
- [x] V61c live probe: move the safe jump window down to roughly `23-30`; result: `19-22` jump almost disappeared, `23-30` jump stayed mostly clean, and combined V61b/V61c data is enough for a V62 filtered retrain experiment
- [ ] V62 direction: retrain with filtered V61b/V61c on-policy rows, preserving clean `23-30` jump and teaching defensive behavior for `<=22` and `31-48`; use filtered BC/classification only if margin/replay still cannot internalize the prior
- [x] Document the from-scratch full-retrain data collection curriculum in [docs/agent-memory/remote-rl-retrain-data-collection-plan.md](agent-memory/remote-rl-retrain-data-collection-plan.md)
- [ ] Full-retrain collection Phase 0: collect schema/label sanity logs and verify execution source, action labels, HP deltas, projectile fields, action-start masks, and detector dry-run hit rates
- [x] Full-retrain collection Phase 1: collect movement and spacing curriculum logs and train/check the first movement baseline before attacks
- [x] Full-retrain collection Phase 2: collect basic normal attack curriculum logs with hit, whiff, blocked, and punished examples
- [ ] Full-retrain collection Phase 3: collect specials curriculum logs for fireball, shoryuken, and tatsu good/bad contexts
- [ ] Full-retrain collection Phase 4: collect basic defense logs for guard, back-evade, and post-block punish
- [ ] Full-retrain collection Phase 5: collect projectile defense timing logs with human-visible close/mid/far fireball cues, then split post-hoc into `time_to_self` buckets and opponent-recovery labels
- [ ] Full-retrain collection Phase 6: collect anti-air and jump-defense logs, and verify M5 did not generalize projectile guard behavior to opponent jump-ins
- [ ] Full-retrain collection Phase 7: collect corner, pressure, and oki/wakeup logs before treating pressure behavior as solved
- [ ] Full-retrain collection Phase 8: collect high-quality CPU-demo, serious human-demo, structured mixed, and on-policy integration logs after curriculum phases exist
- [ ] Full-retrain training: run cumulative warm-start models M1-M8 and regression-check each stage before live promotion; M1 and M2 are complete, with M2 v4c passing raw M1/P2 gates without support-prior
- [ ] Fix `rl_auto_retrain.py` replay planning for human-demo incremental retrain: add auto-available source ratios, log-level boost inputs, and replay-plan metadata
- [ ] Review walk-forward/back macro actions after spacing-shaping A/B results
- [ ] Review finer distance buckets after spacing-shaping sample-volume checks
- [ ] Collect targeted corner-escape demo data before treating corner anti-turtle shaping as solved
- [ ] Review live basic-only collection with lower/no repeat-delay pollution after the next DQN comparison
- [x] Add an offline transition analyzer for action/distance HP-delta attribution
- [x] Add analyzer-only `(routine_no[1], routine_no[2])` engine-state action mapping for ordinary-state validation
- [x] Add raw `routine_no[1]/[2]` transition diagnostics for self/opponent engine-state analyzer input
- [x] Document the Ryu `R1/R2` engine dispatch trace for future all-character move mapping
- [x] Expand observation features only with schema versioning for the first routine attack/contact-reaction validation probes
- [x] Promote validated opponent routine attack state into the first tabular strike-defense state split
- [x] Draft an all-character policy action ID / sub-action / macro taxonomy from SF3 command source tables
- [x] Add readable SF3 move-name aliases to the policy action taxonomy
- [x] Split `back` and `guard` into separate high-level actions after the DQN pipeline smoke passes
- [x] Add high-level policy action / sub-action / macro-step attribution to transition rows
- [x] Add `guard-stand`, `guard-crouch`, `crouch-mk`, `shoryuken-mp`, and `tatsu-mk` to the probe-side action set
- [x] Split Ryu Hadouken into LP / MP / HP learner actions instead of collapsing CPU-demo variants into LP fireball
- [x] Rename the legacy LP Hadouken learner action from `fireball` to strength-explicit `fireball-lp`, while keeping `fireball` / `ryu-fireball` as scripted/backward aliases
- [x] Split Ryu Shoryuken and Tatsumaki Senpukyaku into LP/MP/HP and LK/MK/HK learner actions
- [x] Split jump attacks into forward / neutral / back policy action IDs and add HK jump-kick probes
- [x] Split stand/crouch normal policy action IDs and add standing LP/MP/LK/MK/HK plus crouching LK/MK/HK probes
- [x] Expand probe/DQN action support to all standing, crouching, forward-jump, neutral-jump, and back-jump LP/MP/HP/LK/MK/HK basic normals
- [ ] Expand reward features only after baseline reward is stable
- [ ] Review whether `overlay_attack_event_finalized` / `overlay_attack_contact` / `overlay_attack_whiff` have consistent learner semantics across normals, specials, projectiles, throws, and multistage moves before promoting them beyond debug / auxiliary labels
- [x] Record the anti-air Shoryuken feature plan before changing the DQN observation schema or reward knobs
- [ ] Promote anti-air DQN observation features only after train/live payload parity and jump-in validation are defined
- [ ] Collect a targeted human-demo anti-air Shoryuken log before expecting offline DQN to learn jump-in punishment reliably
- [x] Record the support-aware conservative DQN penalty plan for sparse-action overestimation
- [x] Add an opt-in conservative action penalty to offline DQN replay rewards without changing transition schema or live inference
- [x] A/B test conservative DQN penalty against v9/v11-style ground-specials models before making it part of the default training recipe
- [x] Review whether sparse-action overestimation still requires Double DQN / inference reranking after conservative-penalty A/B results
- [x] Add offline Double DQN target mode and train v17 from the v9 ground-specials recipe
- [x] Add inference-time reranking / action-support priors after v17 Double DQN showed no material policy change
- [x] Run move-family validation passes with scripted policies such as `hp`, `throw`, `ryu-fireball`, `tatsu`, and `shoryuken`, then document which attack-outcome fields are trustworthy enough for learner use versus debug-only analysis
- [x] Add a human-demo recording path so human-vs-CPU play can export learner-ingestible episodes for bootstrapping / behavior-cloning experiments
- [x] Add a CPU-demo recording path so built-in CPU-vs-CPU play can export learner-ingestible bootstrap episodes
- [x] Add `prefer-engine-action` / engine-outcome DQN replay mode so engine-labeled demo attacks replace input labels without discarding unattributed guard / walk demo rows
- [x] Stop engine-attributed demo delayed-credit windows at the first self/opponent HP delta, while still using per-action window settings as maximum tracking lengths
- [x] Consume HP deltas claimed by engine-attributed demo experiences so delayed projectile credit does not also reward unrelated later input-based rows
- [x] Add focus-action DQN comparison diagnostics so any specified action group can be inspected by rank, blocker action, and threat/distance bucket
- [x] Tighten demo guard labels and DQN guard bonus semantics so crouch/back intent is not automatically treated as successful guard without threat or contact evidence
- [x] Implement strict transition schema v3 rollout from `docs/rl-policy-action-taxonomy.md#transition-schema-v3-rollout-plan`
- [x] Remove legacy transition action fields from C-side NDJSON export and bump `transition_schema_version` to `3`
- [x] Update Python replay ingestion to require schema v3 and remove schema 1/2 fallback
- [x] Keep DQN `--training-action-source auto|policy|input|engine|prefer-engine`
- [x] Update analyzer / compare source breakdown for strict v3 canonical action labels (`policy`, `input`, `engine`, `none`)
- [x] Validate schema v3 with fresh CPU-demo and human-demo logs before long-run retraining
- [x] Add DQN replay diagnostics for `execution_source` and `model_version_executed` before changing source-mix ratios
- [x] Add opt-in DQN replay source-mix include / exclude / cap / ratio controls for v18 experiments
- [ ] Define how replay-buffer import mixes human-demo episodes with remote-agent episodes, including metadata such as data source, control mode, and player side
- [x] Train a v18 candidate from a declared source-mix recipe and compare against v9 before live use
- [x] Review v18 source-mix results before using live-policy replay as a default training input
- [x] Collect a clean live replay with v9 plus a conservative action-support prior before the next live-replay retrain
- [x] Add entropy regularization (`--dqn-entropy-reg-weight`) to DQN trainer to prevent action collapse
- [x] Add adaptive unsupported-action Q ceiling (`--dqn-unsupported-action-adaptive-ceiling`) computed from movement action mean Q
- [x] Assess engine-state label coverage for BC pre-training: 70.6% actionable coverage on P3 data, exceeding 30-50% threshold
- [x] Implement BC (Behavioral Cloning) training mode in `train_dqn_learner.py` with `--training-mode bc`, engine state + input label derivation, and cross-entropy training
- [x] Train BC baseline model on full retrain data (M3bc v320): 66,756 labeled rows, CE loss 3.74→1.41
- [x] DQN fine-tune from BC baseline (M3bc+dqn v330): first-ever special moves at top-1 greedy (shoryuken-lp 52.8%), confirming BC+DQN approach works
- [x] Fix BC/DQN entropy regularization so `--dqn-entropy-reg-weight` backpropagates the entropy objective instead of only changing reported loss
- [x] Harden BC segment KW propagation before next training: short anchor window, stop on competing special anchors/segments, and skip missing-KW special rows instead of defaulting to LP/MK
- [x] Train BC-natural-v1 from only P8 natural human/cpu demo logs and record whether pure natural play has enough label/action coverage
- [x] Train BC-coverage-v1 from M1/P2/P3/P8 coverage logs and compare against BC-natural-v1 before DQN fine-tune
- [x] Balance shoryuken over-concentration (52.8%→35.2%) and fireball suppression (0%→15.1%) via fireball guard/cancel no-damage fix + shoryuken whiff penalty + stronger expert margin; v335 promoted
- [x] Collect fireball-good scenario data (far range, opponent grounded) to improve fireball hit rate in training distribution; used schema v6 natural-serious-human-v4 log
- [x] Run M3bc+dqn-v2 with improved fireball/shoryuken data balance and report M3 quality gate results; result: v331 reduced shoryuken eval concentration versus v330 but failed fireball-good and M1 movement gates, so do not promote
- [x] Document v332 corrective plan after v331 review: add self routine context, preserve warm-start through feature expansion, exempt zoning fireball from movement regression, and add context-gated special expert margin
- [x] Implement v332 trainer foundations: self routine DQN features, init-model feature expansion, fireball movement-regression exemption, and `--special-expert-margin-context-gate`
- [x] Train M3bc+dqn-v3 / v332-v335 with context features, context-gated special margin, fireball guard/cancel fix, schema v6 natural log, shoryuken whiff penalty, and stronger expert margin; v335: first fireball top1 (15.1% trainer, 4.7% FB-good), good/bad separation 3.6x
- [x] Add v336 opt-in live-side Shoryuken context prior / compare support so `shoryuken-*` gets a small Q penalty outside coarse anti-air contexts while preserving the promoted v335 weights
- [x] Add v337 opt-in live-side ground-normal context prior / compare support so stand/crouch normals get a small Q penalty outside close or threat/contact poke contexts
- [x] Add v338 fireball-zoning prior / compare support after v337 live probe; offline result: Shoryuken prior `0.06` + fireball bonus `0.03` without ground-normal prior raises fireball modestly while avoiding the broad v337 normal penalty
- [x] Live-probe v338a with Shoryuken prior `0.06`, fireball zoning prior `0.03`, and no ground-normal prior; result: anti-air OK, aggression and fireball improved, but enemy-attack defense is still weak
- [x] Add v339 threat-response prior / compare support after v338a; offline result: v339e guard/back/unsafe `0.18/0.10/0.18` improves grounded attack-threat defense rows while preserving fireball and avoiding airborne-opponent Shoryuken penalties
- [x] Live-probe v339e with Shoryuken prior `0.06`, fireball zoning prior `0.03`, threat-defense guard/back/unsafe `0.18/0.10/0.18`, and no ground-normal prior; result: anti-air slightly weaker, fireball slightly higher, normals defense still weak, so do not promote
- [x] Replace threat-defense live-side patching with a trainer/data fix for grounded normals defense; keep anti-air rows separate and re-check without threat-defense prior
- [x] Grounded normals defense Phase 1: inventory existing logs for close/mid opponent-normal attack rows, guard/back responses, forward/normal punish failures, and anti-air jump-in rows that must be protected
- [x] Grounded normals defense Phase 2: add or reuse an extractor/analyzer view that emits grounded opponent-normal threat rows with distance bucket, self action-start state, chosen action, HP/contact outcome, and anti-air exclusion labels
- [x] Grounded normals defense Phase 3: add trainer support for a grounded-normal-defense objective, preferring guard/back margin or BC-style labels only in grounded opponent-normal threat rows, plus negative pressure against forward/random normals into active normals. Added `--grounded-normal-defense-bc-loss` (CE loss toward human-demo guard/back at weight 0.08), `--reward-guard-success-bonus` (bonus 0.5 with window 30, max_dx 240), `--reward-throw-far-cost` (cost 0.5 when abs_dx > 64). Fixed conservative penalty exempt list to include movement/defense/jump actions. Added shoryuken engine outcome action windows and `--movement-regression-exclude-special-expert-eligible`.
- [x] Grounded normals defense Phase 4: trained v341-v350 candidates from v335 weights. v350 (guard success bonus + throw far penalty + BC defense loss) selected as best candidate: shoryuken 42.6%→17.0%, fireball maintained 10.4%, guard success bonus 742.0/1484 events. No action collapse. Live-side priors tuned: shoryuken prior 0.15, threat defense guard/back/unsafe 0.20/0.15/0.20, ground-normal penalty 0.08, fireball bonus 0.03.
- [x] Grounded normals defense Phase 5: live-probed v348/v350 with threat-defense prior + ground-normal prior + shoryuken prior. Results: anti-air preserved, normals reduced, defense slightly improved, multi-hit defense (tatsu) still weak due to block-stun gap.
- [x] Fix v350 multi-hit defense prior gap: add opt-in threat-defense contact sustain so guard/back pressure can continue while `obs_self_contact_reaction_state=1` and opponent is still in attack state; synthetic smoke passed and v350 same-observation compare shows large guard/back lift in `atk1_close/mid` without increasing Shoryuken
- [x] Fix v350 medium/far random Shoryuken guardrail: add opt-in far-distance extra Shoryuken penalty so non-anti-air `abs_dx >= 180` rows can receive additional DP suppression while preserving the existing close anti-air exemption window
- [x] Live-probe stronger v350 far Shoryuken guardrail: `abs_dx >= 180` with extra penalty `0.20`; result still used Shoryuken too often beyond 180, so soft Q penalty is insufficient
- [x] Fix far Shoryuken guardrail early-return gap: make far extra penalty / hard block apply before self action-start checks so recovery or non-action-start rows cannot bypass the far non-anti-air DP guardrail
- [x] Live-probe v350 hard far Shoryuken block: opt-in block for non-anti-air Shoryuken; result still allowed too much far Shoryuken, leading to the narrow anti-air exemption diagnostic
- [x] Live-probe narrow anti-air exemption variant: `--dqn-shoryuken-prior-max-abs-dx 39 --dqn-shoryuken-prior-far-min-abs-dx 40 --dqn-shoryuken-prior-far-block`; result still used far Shoryuken, exposing an active macro continuation bypass
- [x] Fix epsilon bypass for far Shoryuken hard block: v350 has `epsilon=0.05`, and random exploration previously sampled from valid actions before prior rerank; hard-blocked actions are now filtered out of epsilon eligible actions too
- [x] Fix active macro continuation bypass for far Shoryuken hard block: DQN policy now cancels a currently playing `shoryuken-*` macro when the current observation row hard-blocks that action, so macro step 1+ cannot continue through the guardrail after distance/context changes
- [x] Train the next live-replay candidate only from declared clean source ratios and compare it against raw v9 plus reranked v9 before live use
- [x] Add opt-in movable action-start filtering for selected DQN replay sources so recovery-state policy selections do not become valid action samples
- [x] Train v20 from the clean support-prior live replay with remote-only movable action-start filtering and compare it against v9/v18/v19 before live use
- [x] Review lower remote-replay ratios or source-specific filtering before promoting a live-replay-trained DQN
- [x] Treat v20's remaining far-range `fireball-mp` shift as a separate issue from recovery-state action pollution before promoting a live-replay-trained DQN
- [x] Train v21a/v21b fireball oversample A/B candidates and compare them against v9/v19/v20
- [x] Run a short live smoke with v21a before treating it as the next live baseline
- [x] Train v22 from v21a live replay with the v21a fireball-oversample recipe and remote movable filtering
- [x] Add OBS payload v3 raw routine ids and DQN opponent routine one-hot features for the v23 feature-slice experiment
- [x] Train v23 from the v21a live replay with the v21a fireball-oversample recipe and remote movable filtering
- [x] Train v24 from CPU/human demo plus v21a-live and v23-live replay with a declared `55/30/15` source mix
- [x] Document the rolling incremental retrain plan
- [x] Add DQN trainer `--init-model` warm-start and replay recipe metadata
- [x] Add live-log cursor / chunk snapshot support for incremental retrain
- [x] Add auto retrain runner for timed/row-count triggered warm-start training and publish
- [x] Add a v35a auto-retrain preset so close-pressure / anti-air tuning can be reused without long extra-arg commands
- [x] Record V37b / V38 full-action support-prior training parameters and findings before continuing full action-set experiments
- [x] Add DQN zero-sample / low-support action regularization so full-action output heads with no replay support cannot become top greedy actions
- [x] Add a shared DQN valid-action mask for train-time target selection and probe-time inference, starting with self-routine-aware jump-action gating
- [x] Let `rl_probe_server.py` auto-enable DQN valid-action masks from actor metadata so masked-trained actors do not require a manual probe flag
- [x] Add DQN verbose action-mask diagnostics and reduce high-frequency verbose PING logging
- [x] After shared valid-action mask validation, split jump-in policy actions into ground jump-start actions and true airborne attack actions with observation-schema support
- [ ] After the jump-start / air-attack taxonomy and schema split, add opt-in train-time invalid-action Q penalty so raw DQN weights learn on the cleaned-up action space
- [ ] Review v24 live behavior before promoting it over v23; same-observation compare kept `stand-hk` suppressed but did not reduce the `tatsu-lk` replacement shift
- [ ] Review v23's `tatsu-lk` / `crouch-mk` policy shift before any live promotion; `stand-hk` was suppressed, but the replacement action is not yet validated
- [ ] Add stronger source/action-specific live negative replay handling before expecting v21a-live punish data to move `stand-hk` / mid-fireball behavior
- [ ] Add character curriculum
- [ ] Add stage curriculum
- [ ] Add automated reset loops
- [x] Add a conservative RL auto-rematch path through the existing VS result rematch flow
- [x] Fix long-run transition sender thread resource leak that could OOM-kill `3s-arm`
- [x] Fix transition sender running-state race / missed-wakeup after ruling out perf-capture config as the latest restart cause
- [x] Document the complete self/opponent combat event attribution plan in [docs/agent-memory/remote-rl-combat-event-attribution-plan.md](agent-memory/remote-rl-combat-event-attribution-plan.md)
- [x] Combat event attribution Phase 0+1: harden Python parsers/replay mappers first, audit evidence fields, define evidence bitmask constants, add a runtime evidence-export gate, export versioned `evidence_flags_*` bitmasks plus `ep_` counters, size/guard transition JSON export without large stack buffers, and restore/export filled evidence without changing reward or inference
  - [x] Added `src/rl/rl_combat_event.h` with Phase 0+1 bitmask version/bit constants only; no event structs, rings, ids, resolver helpers, or result/confidence/failure enums
  - [x] Replaced the transition formatter's stack `line[2048]` path with a reusable RL-session heap buffer allocated/freed through the RL net lifecycle
  - [x] Fixed the positive truncation hazard by requiring complete formatter success before appending transition rows; evidence-extension failure falls back to a complete base row
  - [x] Added config/CLI/OSD-backed `rl-agent-export-evidence` / `RL Evidence Log (Restart)` gate; default is off
  - [x] Added six-field compact evidence export when the gate is on:
    `evidence_bitmask_version`, `evidence_flags_lo`, `evidence_flags_hi`, and
    the three `ep_overlay_attack_*_count` fields
  - [x] Added Python evidence decoder, analyzer `--expand-evidence --output-expanded`, reserved-bit warning, negative flag rejection, and DQN feature-name evidence denylist guards
  - [x] Preserved reward, inference, action scheduling, and transition replay feature builders as evidence-agnostic by default
  - [x] Ran on-device/live transition smoke with gate off/on: gate-off rows had no evidence fields, gate-on rows had the full six-field evidence shape, both logs parsed as complete JSON, and episode counters reset/decreased-free across episode boundaries
  - [x] Recorded live row-size budget: gate-off max 1752 bytes, gate-on max 1937 bytes inside the 4096-byte formatter buffer
  - [x] Deferred explicit formatter micro-timing until the full combat-event log is implemented or live/intermediate tests show a visible performance problem; current Phase 0+1 live smoke had no observed gameplay/performance issue
- [ ] Combat event attribution Phase 2: implement fixed-size self/opponent attack event rings with monotonic run-wide event ids, episode-boundary flush, and no active-slot overwrite
  - [x] Phase 2A: added `src/rl/rl_combat_event.c` plus attack-event ring API/state for self and opponent, run-wide monotonic nonzero event ids, no active-slot overwrite, explicit finalize, and episode-boundary unknown flush
  - [x] Phase 2A: wired combat-event run/episode lifecycle into `rl_session.c` start/reset/finalize paths without changing transition JSON, reward, inference, or trainer feature inputs
  - [x] Phase 2B: create attack events from self/opponent attack-start edges and attach raw routine/current-attack/policy context; same-side new starts roll active prior events to unknown instead of filling the ring
  - [x] Phase 2C: added conservative basic finalization windows: clean non-projectile attacks can finalize as whiff after the attack state ends, actor damage can finalize as interrupted, and contact/projectile/throw-protected events timeout as unknown instead of being mislabeled
  - [x] Phase 2D: expose OSD/debug visibility for event counts/results without promoting event labels into rewards or changing transition NDJSON; disk/analyzer event visibility remains Phase 7 event-journal work
  - [x] Phase 2 live-smoke refinement: whiff lifecycle now treats routine attack state as the active-window signal, not sticky `current_attack`; accepted attack-start events are whiff-eligible so very short LP whiffs do not require a separately latched routine-active frame
  - [x] Phase 2 timeout/LP refinement: clean non-projectile pending timeouts finalize as `W` instead of `U`, and normal LP events get a 20-frame fast whiff fallback for sticky active-window / unrelated projectile-noise cases
  - [x] Phase 2 rollover refinement: same-side new starts finalize previous clean active events as `W`, leaving `R` only for contact/projectile-like/throw-protected ambiguous rollovers
  - [x] Phase 2 overlay stats refinement: `CE` / `CEU` counters are round-local and reset at episode begin; `CEL` / `CELU` lifetime counters remain available in `All` view, while event ids stay run-wide monotonic
  - [x] Phase 2 side-split overlay refinement: round-local `CE` / `CER` / `CEU` lines now show self/opponent splits for S/F/A/W/I/U/F/R/D so simultaneous-whiff misses reveal which side diverged
  - [x] Phase 2 timeout-cause overlay refinement: `All` view now shows `CEUC` / `CEUL` self/opponent cause splits for timeout unknowns: contact, projectile, throw, projectile-like, and not-whiff-eligible
  - [x] Phase 2 overlay readability refinement: `U D L R LP MP HP LK MK HK` input tokens now render only in the `Input` debug view, not in `All` or `Outcome`
  - [x] Phase 2 contact-cause overlay refinement: `All` view now splits contact/damage timeout unknowns into `CEUD` hit-stop/contact-state/damage-state and `CEUH` HP/stun deltas
  - [x] Phase 2 EC-only whiff refinement: broad `entered_contact_state` / `guard_flag` evidence remains visible in `CEUD EC`, but no longer blocks basic clean-whiff classification by itself
  - [x] Phase 2 live overlay smoke: live All/Outcome overlay checks now show clean simultaneous strike whiffs reaching `CER W`; projectile guard/clash cases remain conservative `CEU R` until Phase 4/6 projectile/contact resolution
- [ ] Combat event attribution Phase 3: replace ambiguous generic `engine_*` ownership with side-explicit `self_engine_*` and `opp_engine_*` attribution at attack-event creation time, keeping unknown/confidence fields for unsupported mappings
  - [x] Phase 3 side-explicit export foundation: transition schema v7 adds `self_engine_*` and `opp_engine_*` root fields while keeping generic `engine_*` as a self-side compatibility alias
  - [x] Phase 3 event-start attribution foundation: self/opponent attack-event starts carry side-local Ryu engine action/sub-action/routine/current-attack/KW/source/lag fields when supported; unsupported characters remain unknown
  - [x] Phase 3 local validation: `rl_combat_event.c` warning compile, Python analyzer/probe compile, `git diff --check`, and telemetry ARM build passed
  - [x] Phase 3 live validation: `logs/phase3-side-engine-live.ndjson` schema v7 showed self/opponent engine labels through four visual side swaps; generic `engine_*` matched self only with zero opponent pollution
- [x] Combat event attribution Phase 4: implement projectile event tracking so fireball spawn/hit/block/expire results are attributed to projectile ids instead of owner routine snapshots
  - [x] Phase 4A projectile lifecycle foundation: added a fixed-size projectile event ring with shared monotonic event ids, owner-side spawn tracking, parent fireball attack linking, conservative hit/block/expired/unknown finalization, OSD `CP`/`CPR` counters, and schema v8 transition counter snapshots
  - [x] Phase 4A overlay cleanup: moved combat-event attack/projectile counters exclusively into the `Outcome` view and removed older non-event delta/input heuristic lines from that view
  - [x] Phase 4A live-validation fix: transient VS pause now suspends RL action/observation handling without flushing/resetting combat-event counters, and projectile result classification no longer treats broad `guard_flag` / `entered_contact_state` evidence as enough to force `CPR B` or block clean expiry
  - [x] Phase 4A parent-attack cleanup: when a projectile spawn links to a projectile-like parent attack, the parent attack is finalized as projectile-claimed instead of later polluting `CEU R` rollover-unknown counters; the projectile event remains the source of truth for `CPR H/B/X/U`
  - [x] Phase 4 live validation: fireball-lp/mp/hp at close/mid/far increment `CP S/F/A`; blocked fireballs reach `CPR B`, damaging fireballs reach `CPR H`, fly-out reaches `CPR X`, projectile clashes reach `CPR X +1/+1`, parry remains conservative `CPR U`, pause no longer resets counters, and fireball parent attacks no longer add `CEU R`
  - [x] Phase 4B projectile edge-case documentation: recorded `CP` / `CPR` contract, accepted parry/clash behavior, pause/reset semantics, parent-attack ownership, and Phase 6 limitations in the combat-event attribution plan
- [ ] Combat event attribution Phase 5: implement throw event tracking so close guard failures can distinguish thrown/tech/whiff/unknown from strike or chip damage
  - [x] Phase 5A throw evidence audit: documented current `tsukami_f` / `tsukamare_f`, routine-state, R2/KW, HP/stun, and close-range signals; confirmed current transition evidence is self-success oriented and must be made self/opponent symmetric before a throw ring is learner-safe
  - [x] Phase 5B throw observation symmetry: transition schema v9 adds self/opponent symmetric throw-active and throw-caught edge/seen fields (`self_throw_started`, `opp_throw_started`, `self_throw_caught_started`, `opp_throw_caught_started`, `self_throw_seen`, `opp_throw_seen`, `self_throw_caught_seen`, `opp_throw_caught_seen`) before creating result counters
  - [x] Phase 5C throw event ring foundation: added fixed-size self/opponent throw events with conservative success/whiff/unknown results plus Outcome `CT` / `CTR` side-split counters, no reward or trainer adoption
  - [x] Phase 5C/5D live-refinement prep: throw starts now include throw-active and Ryu throw-start routine edges, so out-of-range throws can become `CTR W` without treating held LP+LK policy/input rows as repeated starts; raw throw-active starts are suppressed after recent non-whiff throw results, while fresh engine start edges may supersede a clean active throw as `CTR W` for rapid whiff retries; success waits a short confirm window so simultaneous/contested throw or throw-escape routine evidence is kept out of `CTR T` and conservatively finalized as `CTR U`; normal and back throw success still use caught-state evidence
  - [x] Phase 5D throw Outcome overlay/live validation: live retests accepted close throw success as `CTR T`, clean throw whiff as `CTR W`, and mutual throw/tech-like cases as conservative `CTR U` with no remaining `CTR T` false-positive; mutual throw side split may be one-sided or both-sided depending on observed start/escape timing and is deferred to Phase 6 matching
- [ ] Combat event attribution Phase 6a: implement edge-triggered contact-to-attack/projectile/throw matching with consumed HP/stun deltas, trade handling, confidence, and attribution failure events
  - [x] Phase 6a-0 contact-match instrumentation: added debug-only `CEM A/P/T/U self/opponent` Outcome counters that classify each meaningful HP/stun/contact edge into one source family with priority projectile -> throw -> attack -> unknown. This does not mutate deltas, change transition schema, change rewards, or promote labels into learner features; full event-id consumption and confidence/failure emission remain in Phase 6a.
  - [x] Phase 6a-0 projectile live refinements: projectile parent attacks are excluded from `CEM A`, projectile parry uses widened parry-success edges, and projectile expiry (`CPR X` / disappeared) with opposing-projectile evidence is treated as a projectile clash edge so fireball-vs-fireball collision can produce `CEM P` without requiring a character HP/stun/contact edge.
  - [x] Phase 6a-0 projectile edge-case live validation: fireball clash reached `CPR X +1/+1` and `CEM P +1/+1`; opponent fireball parry stayed conservative as `CPR U +0/+1`; single fireball fly-out stayed `CPR X +1/+0` and did not increment `CEM P`.
  - [x] Phase 6a-1A attribution ring skeleton: each CEM record now writes a debug-only attribution event with source family, source event id when available, target side, edge type, conservative confidence, and failure reason; Outcome adds `CEA R/F/O` counters for ring records, failures, and overwrites without changing transition schema, rewards, replay, or trainer behavior.
  - [x] Phase 6a-1A live smoke: whiffs and jumped/evaded fireballs left `CEM` / `CEA` unchanged, and broad live testing did not reveal obvious `CEA` / `CEM` mismatches.
  - [x] Phase 6a-1B attribution edge coverage: Outcome now shows `CEAE HP/ST/DM/BL` and `CEAX PA/TH/CL/HS/CT` counters, and the Outcome view is narrowed to combat-event lifecycle/attribution lines only for live testing.
  - [x] Phase 6a-1B blocked projectile note: live blocked fireball reached `CEM P +1` / `CEA R +1` with `CEAE HP +1` and `BL +0`; this is accepted as chip HP attribution, with blocked-chip semantics deferred to Phase 6b defense result context.
- [ ] Combat event attribution Phase 6b: implement defense result emission with intended action, actual guard state at contact, target_state, wakeup context, block_possible, confidence, and failure reasons
  - [x] Phase 6b-0 defense result debug counters: attribution events now derive target-side `CDR H/B/C/P` and `CDRX T/E/U` counters for clean hit, block, blocked chip, parry, thrown, evaded/negated, and unknown without changing transition schema, rewards, replay, trainer features, or event-journal export.
  - [x] Phase 6b-1 defense context snapshots: attribution events now retain target-side defense intent/context fields (`target_policy_*`, actual guard state, target state, and raw guard/block/parry/throw/contact evidence) and Outcome shows `CDC G/BR/PA/TC` context counters, still with no transition schema, reward, replay, trainer, or event-journal export changes.
- [ ] Combat event attribution Phase 6c: implement punish detection after finalized unsafe/whiff/interrupted attack events with high-confidence gating
  - [x] Phase 6c-0 punish candidate debug counters: finalized whiff/interrupted attack events now open a short punishable window; later high-confidence opposite-side hit/throw attribution records consume that window and increment `CPN R/W/I` plus `CPNX A/P/T` source-family counters, with no transition schema, reward, replay, trainer, or event-journal export changes.
  - [x] Phase 6c-1 punish candidate path/reason split: Outcome now separates finalized-window vs active-attack fallback punish candidates with `CPNC F/A` and `CPNR FW/FI/AW/AI`, documenting live limitations before formal punish event export.
  - [x] Phase 6c-2 frozen debug overlay contract: documented the live-validated Outcome overlay contract for `CE`/`CER`, `CP`/`CPR`, `CT`/`CTR`, `CEM`/`CEA`/`CEAE`/`CEAX`, `CDR`/`CDRX`/`CDC`, and `CPN`/`CPNX`/`CPNC`/`CPNR`, including conservative limitations before Phase 7 event-journal export.
- [ ] Combat event attribution Phase 7: roll out transition schema v4 compact summaries plus `combat_event_schema_version=1` event journal export inside the same transition batch/envelope
  - [x] Phase 7A event journal export skeleton: added the `rl-agent-export-combat-events` config/CLI/OSD gate, emits `combat_event_schema_version=1` attack/projectile/throw/attribution/punish journal rows in the same TCP transition batch envelope, and splits them into a separate `--combat-event-log` file in the Python probe without changing reward, replay, trainer features, or transition row shape.
  - [x] Phase 7A-1 event journal dedupe: live testing showed repeated terminal/finalize calls could append the same episode event ring hundreds of times; session export now records the last exported run/episode journal and emits each episode journal once.
  - [x] Phase 7A-2 ordered complete journal snapshots: finalized/recorded combat events are copied into a per-episode journal buffer before small live rings can overwrite them, and `RLCombatEvent_EmitJournal()` emits rows sorted by run-wide `event_id` instead of ring slot order.
- [ ] Combat event attribution Phase 8: upgrade analyzers to report attack success/failure, defense failures by incoming action/range/result, projectile lifecycle, throws, punishes, and unknown attribution reasons from event fields
  - [x] Phase 8A combat event journal analyzer: added `tools/analyze_rl_combat_events.py` to summarize schema/kind/episode health, chronological `event_id` integrity, duplicate keys, attack effective buckets, projectile lifecycle, defense results, punish paths, source-reference integrity, and optional transition-log joins/projectile counter checks.
  - [x] Phase 8A-1 delegated projectile outcome resolution: analyzer now joins `attack.finalize_reason=projectile_claimed` rows to `projectile.parent_attack_event_id` and reports final effective buckets such as `projectile_hit`, `projectile_blocked`, `projectile_expired`, and `projectile_unknown` without changing raw C journal rows.
  - [x] Phase 8A-2 delegated projectile side split: `Delegated Projectile Outcome` now reports `self` / `opponent` owner-side breakdowns for linked projectile results, finalize reasons, and expired clash-vs-clean counts.
  - [x] Phase 8A-3 throw/attribution/punish side splits: analyzer now reports throw rows by `owner_side`, attribution rows by both `source_side` and `target_side`, and punish rows by both `punisher_side` and `punished_side`.
  - [x] Phase 8A-4 probe/trainer safety hardening: probe server combat-event split now uses raw byte schema-key detection instead of per-line JSON parsing, and feature-name sanitization now strips combat event root fields before model metadata can influence DQN features.
  - [x] Phase 8A-5 defense unknown sub-buckets: analyzer now breaks `defense_result=unknown` attribution rows into source lifecycle and target-evidence buckets, with source/target side splits and examples before any Phase 9 reward adoption.
  - [x] Phase 8A-6 defense unknown reconciliation: analyzer now reconciles each `defense_result=unknown` attribution row against same `(run_id, episode_id, source_event_id, target_side)` resolved attribution rows, reports resolved/ambiguous/unresolved final-result candidates, and confirms unknown/resolved event rows can join matching transition rows by decision id.
  - [x] Phase 8A-7 derived attribution statistics: analyzer now reports a separate derived/effective defense-result view that keeps raw non-unknown labels unchanged, promotes only safely reconciled unknown rows, and leaves unresolved or ambiguous rows visible as analyzer-derived rather than C-side truth.
  - [x] Phase 8A-8 move offense/defense statistics: analyzer now reports per-side offense and defense-vs-move stats by exact move and overlapping tags (`punch`, `kick`, button strength, `projectile`, `special`, `super`, `throw`, `air`, `ground`, `stand`, `crouch`), including uses, hit/block/whiff counts and rates, plus parry/clash/interrupted/unknown counts.
- [ ] Combat event attribution Phase 9: add opt-in trainer use of high-confidence event labels only after move-family validation passes
- [ ] Evaluate higher control rate after latency p95/p99 is stable
- [ ] Review derived movement/action-phase candidates from the Human-Fighter Observer Gap Review before changing the observation schema

Done when:

- [ ] Control timing improvements are backed by telemetry
- [ ] Any promoted derived observation features have schema-versioned docs and validation notes
- [ ] Any promoted attack-outcome labels have move-family validation notes showing how normals, specials, projectiles, throws, and multistage moves were checked
- [ ] Combat event attribution has side-symmetric self/opponent attack, defense, projectile, throw, punish, source, confidence, and failure-reason coverage before labels are promoted into learner rewards
- [ ] Any human-demo ingest path has documented replay-buffer metadata, source-mix diagnostics, and a clear statement of whether it is used for bootstrapping, behavior cloning, evaluation, or mixed training
- [ ] Curriculum changes are reflected in logs and reproducible configs
- [ ] Policy strength improves without destabilizing the transport/control path

Complete combat event attribution plan:

- The current v3 transition row remains decision-centric and is not enough to
  prove attack/defense success/failure attribution for both sides.
- The full direction is documented in [docs/agent-memory/remote-rl-combat-event-attribution-plan.md](agent-memory/remote-rl-combat-event-attribution-plan.md).
- The target model has two layers:
  - transition schema v4 compact summaries for learner/analyzer use
  - `combat_event_schema_version=1` event journal rows for full battle replay,
    carried in the same transition batch/envelope instead of a second C-side
    stream
- Final remote PC disk persistence should split that one received envelope into
  two NDJSON files by default: the configured transition log for summary rows
  and a sibling combat-event log for event journal rows. The two files are
  analyzer conveniences, not independent streams, and must remain
  reconcilable by run/episode/event or future batch identity.
- Full rollout keeps config-backed export gates, optionally exposed by OSD as
  controls for the same runtime flags:
  `rl-agent-export-evidence`, `rl-agent-export-combat-events`, and
  `rl-agent-export-event-summaries`. Event-id summaries require combat-event
  export to be on; if combat-event output is off, summaries must be disabled or
  limited to aggregate fields with no event references.
- Event ids are monotonic run-wide ids, not ring-buffer indices; active ring
  slots must never be overwritten before finalization.
- Event ids use `uint64` with `0` reserved for "no event"; pending-export rings
  must report dropped-event metadata instead of silently losing finalized events.
- Phase 0+1 is parser-first: Python tools must tolerate unknown transition keys
  and expose known evidence fields for audit before C emits new fields.
- Phase 0+1 must explicitly budget the current transition JSON line buffer and
  add truncation checks before restoring evidence export; do not replace
  `line[2048]` with a large hot-path stack buffer or shared static scratch
  buffer. Base transition formatting failures drop the row; evidence-extension
  failures must clear the partial buffer, fall back to a complete base row, and
  never append partial JSON to local logs, transition batches, or the network
  sender.
- Phase 0+1 evidence export needs a runtime/config rollback gate, for example
  `rl-agent-export-evidence`. With the gate off, existing base transition rows
  continue without evidence fields; with it on, evidence-enabled rows emit the
  full six-field Phase 0+1 shape unless the evidence formatter falls back.
- Phase 0+1 live smoke accepted row-size budget as sufficient: compact
  evidence rows stayed below 2KB in the 4096-byte formatter buffer. Explicit
  sub-millisecond formatter timing is non-blocking for Phase 0+1 and is
  deferred until the full event journal/export path exists, or until live tests
  show a visible performance regression.
- Phase 0+1 boolean/edge evidence uses `evidence_bitmask_version = 1`,
  `evidence_flags_lo`, and `evidence_flags_hi` on every row; both flag fields
  are always present unsigned 32-bit JSON decimals. Python must reject negative
  or out-of-range flag values before applying `0xffffffff` masks so signed C
  formatting bugs cannot become silent all-bits-set evidence.
- Python analyzers must not guess unknown bitmask versions; default parse keeps
  transition rows usable with `evidence = None`, while strict audit/debug modes
  fail clearly and debug expansion maps bits to named fields. Reserved hi/lo
  bits require visible warning counters, including synthetic hi-bit and
  mixed-version smokes.
- Phase 0+1 Python feature builders and model metadata loaders must use explicit
  feature allowlists; unknown root keys and `evidence_` / `ep_overlay_` fields
  must not enter default replay/DQN features through `row.keys()` iteration or
  model `feature_names` metadata.
- `tools/analyze_rl_transitions.py` must provide an optional expanded
  human-readable evidence output, e.g. `--expand-evidence --output-expanded
  PATH`, so compact bitmask logs can be audited without changing the original
  learner-safe transition log.
- Phase 0+1 per-decision overlay evidence must be latched and consumed by
  overlay event sequence/id. It must not read transient latest-overlay
  `last_overlay_*` state at transition formatting time, because later frames
  could otherwise overwrite the row's contact/whiff evidence.
- Phase 0+1 must create zero event structs, zero event rings, and zero event
  JSON arrays; resolver data structures start in later phases. Phase 0+1
  `rl_combat_event.h` is limited to evidence bitmask constants, not event
  type/result/source/confidence/failure enums.
- The event model is side-symmetric and covers:
  - attack starts/results
  - defense results
  - projectile spawn/results
  - throw start/results
  - stun/position/round boundary events
  - contact/multi-hit evidence
  - punish relationships
  - attribution failures
- Every resolved event must carry source, confidence, and failure reason when
  unresolved. Unknown labels are valid output; wrong forced labels are not.
- Pending events must be finalized or explicitly failed at episode boundary;
  no event can leak across rounds.
- Event labels must stay analysis/debug-only until the move-family validation
  matrix passes for normals, specials, projectiles, throws, and multistage moves.

Full-action DQN sparse-action plan:

- Problem statement:
  - V37b / V38 full-action models showed that raw DQN can rank actions with
    zero replay support as the top action.
  - CPU-demo V38 is the clearest failure: `jump-neutral-mk`,
    `jump-back-hk`, and `jump-neutral-mp` had `0` training experiences but raw
    greedy inference selected them for most evaluation rows.
  - Current conservative action penalties only modify existing experiences, so
    an action with `count == 0` receives no gradient and can remain an
    uncalibrated high-Q output head.

- Step 1: zero-sample / low-support action regularization.
  - Added opt-in trainer flags for unsupported-action Q regularization:
    - `--dqn-unsupported-action-regularization`
    - `--dqn-unsupported-action-min-count <N>`
    - `--dqn-unsupported-action-q-ceiling <value>`
    - `--dqn-unsupported-action-loss-weight <value>`
  - For each training state, add an auxiliary loss for actions with replay
    support below the configured minimum, including `count == 0`, so their
    predicted Q is pushed below the ceiling.
  - Keep this separate from reward shaping; it should constrain output heads,
    not depend on an action having an experience row.
  - Metadata records the regularization config and diagnostics:
    `eligible_action_count`, per-action regularized events/loss, and the
    zero-sample actions that were affected.
  - Local validation:
    - `python3 -m py_compile tools/train_dqn_learner.py`
    - `python3 tools/train_dqn_learner.py --help`
    - small DQN smoke on `logs/rl-transitions-human-demo-schema-v3-4-3-3.ndjson`
      with `--limit 300`, `--steps 3`, `--batch-size 8`,
      `--dqn-unsupported-action-regularization`,
      `--dqn-unsupported-action-min-count 999`,
      `--dqn-unsupported-action-q-ceiling -100`, and
      `--dqn-unsupported-action-loss-weight 0.0001` emitted
      `eligible_action_count=45`, `regularized_events=1080`, and zero-sample
      actions in `regularized_zero_sample_actions`.
  - Validation:
    - retrain CPU-demo full-action from the V38 recipe with regularization.
    - first V39 validation with `min_count=300`, `q_ceiling=0.0`, and
      `loss_weight=0.1` did not materially improve raw greedy collapse:
      `jump-neutral-mk` moved only from `80.7%` to `80.6%`.
    - require `jump-neutral-mk`, `jump-back-hk`, and `jump-neutral-mp` to lose
      raw greedy dominance without collapsing into a new single fireball/guard
      action.
    - compare raw greedy and strong support-prior greedy distributions.

- Step 2: shared valid-action mask.
  - Added a shared helper used by both trainer and probe inference:
    `dqn_valid_actions_for_row(row, actions, mode)`.
  - Initial conservative mask uses already-exported row fields:
    `obs_self_routine_1`, `obs_self_routine_2`,
    `obs_self_routine_attack_state`, and
    `obs_self_contact_reaction_state`.
  - First mask rule set:
    - when self is in ordinary grounded/movable states, exclude `jump-*`
      attack actions from DQN ranking.
    - when self is in jump-air ordinary states (`R1=0`, `R2=18..26`), allow
      jump attacks and optionally suppress new grounded specials/normals.
    - when self is in attack, damage/contact, caught/catch, or other
      non-movable states, avoid treating a newly selected action as a valid
      action-start and keep target/inference max from using impossible actions.
  - Applied the mask in three places:
    - train-time DQN bootstrapping: the target max action should only consider
      valid next-state actions.
    - probe-time DQN ranking: invalid actions should not be candidates before
      support-prior reranking.
    - same-observation compare diagnostics.
  - Kept the first implementation opt-in, with metadata recording mask mode,
    masked action counts, and fallback behavior when a mask removes every
    action.
  - Validation:
    - `python3 -m py_compile tools/rl_probe_server.py tools/train_dqn_learner.py tools/compare_dqn_models.py`
    - help output showed the new flag on all three tools; after probe metadata
      auto-selection, `rl_probe_server.py` shows
      `--dqn-valid-action-mask {auto,off,self-routine-v1}`, while trainer and
      compare diagnostics keep `{off,self-routine-v1}`.
    - helper smoke confirmed ground rows allow ground actions and mask
      `jump-*`, jump-air rows allow `jump-*`, and attack/non-movable rows keep
      only movement/guard hold candidates.
    - rerun same-observation comparison on V37b/V38-style logs with and without
      the mask.
      - V38 on the first `5000` CPU-demo rows with `self-routine-v1` mask:
        `jump-neutral-mk` fell from raw `80.7%` to `4.9%`; top action became
        `guard-crouch 43.0%`.
      - V40 masked training on the CPU-demo V38 recipe published
        `model/dqn-cpudemo-schema-v3-full-actions-v40-mask`, version `40`.
        Training diagnostics reported `target_empty=0`, `greedy_empty=0`, and
        masked greedy top action `guard-crouch 23.3%`.
      - same-observation masked compare for V38 -> V40 changed `378/5000`
        actions and kept collapse status `ok`; V40 top action on those rows was
        `guard-crouch 42.5%`.
    - run a live probe only after offline diagnostics show jump-action collapse
      is fixed without introducing guard/fireball collapse.
  - Probe metadata auto-selection:
    - `rl_probe_server.py` now defaults `--dqn-valid-action-mask` to `auto`.
    - `auto` reads `metadata.dqn_valid_action_mask_config` from the active DQN
      actor manifest and applies the recorded mode when it is enabled.
    - `--dqn-valid-action-mask off` remains the explicit escape hatch for
      diagnostics that need raw unmasked inference.
    - local V40 startup smoke printed
      `DQN valid-action mask self-routine-v1 source=metadata model_version=40`,
      so the normal V40 probe command no longer needs to pass
      `--dqn-valid-action-mask self-routine-v1`.
  - Probe verbose diagnostics:
    - DQN `OBS-ACTION` verbose lines now include:
      - `dqn_action`
      - `dqn_mask`
      - `dqn_mask_source`
      - `dqn_valid=<valid>/<total>`
      - `dqn_phase`
      - `self_r1`, `self_r2`, `self_atk`, and `self_contact`.
    - Use these fields when a live V40 run appears to choose too many
      `jump-*` actions:
      - `dqn_phase=jump-air` means the mask believes the self player is in an
        ordinary airborne jump state where current taxonomy allows only
        `jump-*` actions.
      - `dqn_phase=ordinary-movable` with a `jump-*` action would indicate the
        mask was not applied or the selected action came from another path.
    - `--verbose` PING summaries are now sampled by
      `--verbose-ping-interval` with default `120`; set it to `0` to suppress
      PING summaries entirely, or `1` to restore per-PING logs.

- Step 3: post-mask jump-in action taxonomy and schema root fix.
  - Do this only after the shared valid-action mask proves that
    self-routine-aware ground/jump gating fixes the current full-action
    collapse without damaging normal ground policy behavior.
  - Do this before adding the state-conditioned invalid-action Q penalty so the
    raw-weight regularizer learns on clean action semantics instead of the
    current mixed `jump-*` heads.
  - Problem to solve:
    - current `jump-forward-*`, `jump-neutral-*`, and `jump-back-*` policy
      actions mix two different decisions:
      - starting a jump from grounded neutral/movable state
      - pressing an attack button after the character is already airborne
    - this makes it hard for the DQN to learn reasonable jump-in timing because
      a ground-state action head can look like a full air-attack decision.
  - Candidate action split:
    - ground jump-start actions:
      - `jump-forward-start`
      - `jump-neutral-start`
      - `jump-back-start`
    - airborne attack actions:
      - `air-lp`
      - `air-mp`
      - `air-hp`
      - `air-lk`
      - `air-mk`
      - `air-hk`
  - Expected mask semantics after the split:
    - grounded ordinary/movable state allows jump-start actions, but not
      `air-*` attacks.
    - ordinary jump-air state (`R1=0`, `R2=18..26`) allows `air-*` attacks,
      but not new grounded normals/specials or jump-start actions.
    - non-movable attack/contact/damage/caught states avoid new action-start
      choices and fall back to the configured hold/fallback behavior.
  - Observation-schema support:
    - add schema-versioned fields that make train/live parity explicit,
      instead of relying only on raw routine ids:
      - `obs_self_airborne`
      - `obs_self_jump_phase` or compact equivalent
      - `obs_self_ground_action_start_allowed`
      - `obs_self_jump_start_allowed`
      - `obs_self_air_attack_allowed`
      - optional opponent counterparts for anti-air / jump-in curriculum.
    - do not add `obs_self_action_start_allowed` as a separate schema field in
      the first version, because it would duplicate the family-specific
      allowed flags. Instead expose a shared helper such as:
      `self_action_start_allowed(row) =
      obs_self_ground_action_start_allowed || obs_self_jump_start_allowed ||
      obs_self_air_attack_allowed || future_action_family_allowed`.
    - first-version field semantics:
      - `obs_self_ground_action_start_allowed`: self is grounded, movable, not
        currently starting/active/recovering from an attack, and not in
        hitstun/blockstun/contact/damage/caught state; this gates ground
        normals, specials, throw, movement/guard starts, and other ground
        action-start families.
      - `obs_self_jump_start_allowed`: self can start a jump. For the first
        implementation this may equal `obs_self_ground_action_start_allowed`,
        but keep it separate so future exceptions can allow ground action while
        blocking jump, or vice versa.
      - `obs_self_air_attack_allowed`: self is airborne in an ordinary jump-air
        phase and can start an airborne button press; this gates `air-*`.
      - `obs_self_airborne` / `obs_self_jump_phase`: descriptive state fields
        used for diagnostics, training features, and eligibility debugging.
    - expected helper/mask semantics:
      - if `self_action_start_allowed(row)` is false, do not allow new
        attack/jump action starts; fall back to hold / movement / guard
        behavior.
      - if `obs_self_ground_action_start_allowed` is true, allow ground action
        families but not `air-*`.
      - if `obs_self_jump_start_allowed` is true, allow
        `jump-forward-start`, `jump-neutral-start`, and `jump-back-start`.
      - if `obs_self_air_attack_allowed` is true, allow `air-lp`, `air-mp`,
        `air-hp`, `air-lk`, `air-mk`, and `air-hk`, but not ground actions or
        `jump-*-start`.
    - update C-side OBS payload, transition rows, Python OBS parsing,
      `DQN_FEATURE_NAMES`, model metadata, analyzer diagnostics, and probe
      inference together so train-time and live-time action eligibility use
      the same features.
  - Implementation review / code-change map:
    - version and compatibility gates:
      - bump Python `ACTION_SET_VERSION` because old V40 action heads encode
        direction-specific jump attacks, while the new set separates
        `jump-*-start` from `air-*`.
      - bump C `RL_ACTION_SCHEMA_VERSION` so the handshake rejects old probe
        servers that still interpret the old jump-attack action ids.
      - bump C `RL_OBSERVATION_SCHEMA_VERSION` and Python
        `OBS_SPACING_PAYLOAD_VERSION`; the current 32-byte live OBS payload has
        only three reserved bytes, which is not enough for
        `obs_self_airborne`, jump phase, and three allow flags.
      - bump C/Python `TRANSITION_SCHEMA_VERSION` when transition NDJSON starts
        carrying the new observation fields and canonical action labels.
      - keep V40 as an action-set-v4/model-schema-v3 actor that requires the
        current hard mask; train the first split-taxonomy model from fresh
        schema-v4 logs instead of warm-starting V40.
    - C-side RL runtime:
      - `src/rl/rl_observation.h` / `src/rl/rl_observation.c`: surface the
        existing `self_airborne` field into live/log payloads, then add and
        derive `self_jump_phase`, `self_ground_action_start_allowed`,
        `self_jump_start_allowed`, and `self_air_attack_allowed` from the
        latest player routine, airborne, attack, contact/reaction, hit-stop,
        and movement-lock fields.
      - `src/rl/rl_protocol.h`: extend `RLObsSpacingPayloadV1` or introduce the
        next payload shape for the schema-v4 fields; keep the header framing
        unchanged unless validation shows a protocol-level bump is needed.
      - `src/rl/rl_session.c`: copy the new OBS fields into both
        `RLSession_FillObsSpacingPayload()` and
        `RLSession_CaptureObservationSpacing()`, then emit them from
        `RLSession_FormatTransitionLogLine()`.
      - `src/rl/rl_session.c`: add a new policy action id for air normals
        (button sub-action only), map movement-only `RL_POLICY_ACTION_JUMP`
        direction sub-actions to `jump-forward-start`,
        `jump-neutral-start`, and `jump-back-start`, and stop using
        `RL_POLICY_ACTION_JUMP_ATTACK_FORWARD/NEUTRAL/BACK` for new schema-v4
        rows.
      - `src/rl/rl_session.c`: update `RLSession_DeriveDemoPolicyMeta()` so
        demo input labels `air-*` only when the observation says air attack is
        allowed; grounded jump input should label a jump-start or stay
        unattributed until engine outcome attribution sees the real air normal.
      - `src/rl/rl_session.c`: update
        `RLSession_RyuNormalPolicyMetaFromIdentity()` and
        `RLSession_IsNormalPolicyAction()` so airborne normal engine
        attribution becomes the new air-normal action id instead of the old
        `jump_attack_forward` fallback.
      - `src/rl/rl_net.c` should not need action-specific logic, but its
        handshake and packet-version rejection path must be validated after the
        action/OBS schema bumps.
    - Python shared action/probe surface:
      - `tools/rl_probe_server.py`: replace `JUMP_NORMAL_ACTION_NAMES`,
        `JUMP_NORMAL_ACTION_WIRES`, and
        `JUMP_NORMAL_ACTION_SEQUENCES` with separate jump-start and air-normal
        action families.
      - `tools/rl_probe_server.py`: update `SCRIPTED_POLICY_CHOICES`,
        `TABULAR_ACTION_NAMES`, `TABULAR_ACTION_WIRES`,
        `POLICY_ACTION_META_BY_NAME`,
        `TABULAR_ACTION_NAMES_BY_POLICY_META`,
        `TABULAR_ACTION_NAMES_BY_WIRE`, aliases, `policy_action_frame_name()`,
        and macro/fixed-action helpers so `jump-*-start` sends only direction
        and `air-*` sends only the button while stamping the air-normal policy
        metadata.
      - `tools/rl_probe_server.py`: parse the expanded OBS payload, normalize
        the new transition fields in `learner_replay_row()`, and include the
        schema-v4 fields in verbose DQN diagnostics.
      - `tools/rl_probe_server.py`: add schema-backed action eligibility
        helpers and a new split-taxonomy DQN mask mode, keeping
        `self-routine-v1` only for action-set-v4/V40 compatibility.
      - `tools/rl_probe_server.py`: add the new action-start / airborne fields
        to `DQN_FEATURE_NAMES` and `DQN_FEATURE_SCALES` so offline training and
        live inference consume identical features.
    - Python training and diagnostics:
      - `tools/train_dqn_learner.py`: update attack-risk sets so
        `jump-*-start` is treated as movement/jump-start, while `air-*` is
        treated as an attack for generic and jump/air whiff costs.
      - `tools/train_dqn_learner.py`: switch movable-state filtering and
        train-time valid-action target masking from raw routine guesses to the
        schema-backed action-start allow flags.
      - `tools/train_dqn_learner.py`: review balanced batch groups after the
        split; either keep `air-*` in the normal bucket and jump-start in
        movement, or add an explicit air/jump group with ratio metadata.
      - `tools/compare_dqn_models.py`: update action-rate summaries,
        focus-action parsing, and shared mask selection for the new action set.
      - `tools/analyze_rl_transitions.py`: update default action lists,
        policy-meta names, engine-outcome summaries, and routine/action tables
        so schema-v4 logs show jump-start and air-normal labels clearly.
      - `tools/rl_auto_retrain.py`: ensure incremental retrain preserves the
        new action list from current models and review reward preset names /
        extra args that still say "jump attack" when they now apply to
        `air-*`.
  - Validation before training the first split model:
    - Python: `python3 -m py_compile tools/rl_probe_server.py
      tools/train_dqn_learner.py tools/compare_dqn_models.py
      tools/analyze_rl_transitions.py tools/rl_auto_retrain.py`.
    - Python smoke: synthetic policy-meta decode for `jump-forward-start`,
      `jump-neutral-start`, `jump-back-start`, and all six `air-*` actions.
    - Python mask smoke: grounded rows allow ground + jump-start and reject
      `air-*`; jump-air rows allow only `air-*`; non-movable rows reject both
      new action-start families.
    - C/local smoke: build with the telemetry flavor, then validate handshake
      schema rejection/acceptance, OBS payload size/version, and one local
      schema-v4 transition row containing the new fields.
    - Data smoke: collect a short CPU-demo schema-v4 log and verify analyzer
      counts show jump-start labels separately from air-normal labels before
      training the first V41/Vnext DQN.
  - Implemented on 2026-05-01:
    - protocol/action/OBS compatibility gates now move to
      `RL_PROTOCOL_VERSION=4`, `RL_OBSERVATION_SCHEMA_VERSION=4`,
      `RL_ACTION_SCHEMA_VERSION=3`, transition schema `4`, Python
      `OBS_SPACING_PAYLOAD_VERSION=4`, and Python `ACTION_SET_VERSION=5`.
    - `RLObsSpacingPayloadV1` expanded from 32 to 36 bytes and now carries
      `obs_self_airborne`, `obs_self_jump_phase`,
      `obs_self_ground_action_start_allowed`,
      `obs_self_jump_start_allowed`, and
      `obs_self_air_attack_allowed`.
    - current action set replaces the old direction-specific jump attacks with
      `jump-forward-start`, `jump-neutral-start`, `jump-back-start`, and
      `air-lp`, `air-mp`, `air-hp`, `air-lk`, `air-mk`, `air-hk`.
    - new policy metadata uses `RL_POLICY_ACTION_JUMP` plus directional
      sub-actions for jump starts, and `RL_POLICY_ACTION_AIR_NORMAL=16` plus
      button sub-actions for air normals.
    - `tools/rl_probe_server.py` added `action-start-v1` as the schema-backed
      DQN valid-action mask. Ground rows allow ground actions and
      `jump-*-start`; jump-air rows allow `air-*`; locked states fall back to
      movement/guard hold candidates.
    - DQN feature metadata now includes the new schema fields, so V41/Vnext
      split-taxonomy models should be trained from fresh schema-v4 logs rather
      than warm-started from V40 action-set-v4 weights.
  - Local validation completed:
    - `python3 -m py_compile tools/rl_probe_server.py
      tools/train_dqn_learner.py tools/compare_dqn_models.py
      tools/analyze_rl_transitions.py tools/rl_auto_retrain.py`
    - `python3 tools/rl_probe_server.py --help`
    - `python3 tools/train_dqn_learner.py --help`
    - `python3 tools/compare_dqn_models.py --help`
    - `python3 tools/analyze_rl_transitions.py --help`
    - synthetic OBS/action/mask smoke confirmed 36-byte OBS parsing,
      `jump-forward-start` / `air-mk` policy-meta decode, replay-row
      normalization, DQN feature vector inclusion, and `action-start-v1`
      ground/air gating.
    - `git diff --check`
    - `tools/mister/build-game.sh --flavor telemetry`
  - Remaining data validation before first split-taxonomy training:
    - schema-v4 smoke log
      `logs/rl-transitions-cpu-demo-schema-v4-smoke-4-3-3.ndjson` confirmed:
      all rows use transition schema `4`; all new observation fields are
      present; jump phase mapping is coherent (`phase=1` for ordinary jump
      ready, `phase=2` for ordinary jump-air, `phase=3` for other airborne
      states); old `jump-neutral-mk` / `jump-back-hk` style labels no longer
      appear; and air-normal labels can appear as separate `air-*` actions.
    - blocker found in that first smoke: `obs_self_ground_action_start_allowed`
      and `obs_self_jump_start_allowed` were true on only `8 / 2579` rows, and
      `obs_self_air_attack_allowed` was true on only `19 / 2579` rows. The
      split schema was working, but the first C derivation was too strict for
      training V41 because it also gated on raw `self_do_not_move`,
      `self_current_attack == 0`, and `self_throw_active`.
    - follow-up fix: derive the first-version action-start flags from the same
      routine-first state family used by the validated shared mask:
      `valid && R1=0 && !routine_attack && !contact_reaction && !hit_stop`,
      then apply family-specific checks for grounded, jump-ready/jump-air, and
      airborne jump-air. Keep raw movement/attack/throw fields for diagnostics
      and future refinements instead of making them hard blockers in the first
      schema-v4 gate.
    - before V41/Vnext training, re-record a short CPU-demo schema-v4 log and
      confirm the fixed C fields have useful density: ground/jump-start allow
      rows should be much closer to the routine-based estimate, ordinary
      jump-air rows should expose `obs_self_air_attack_allowed=1`, and analyzer
      output should continue to separate `jump-*-start` from `air-*`.
    - follow-up human-demo smoke log
      `logs/rl-transitions-cpu-demo-schema-v4-smoke-4-3-3.ndjson` confirmed
      the routine-first allow fix restored useful density:
      `obs_self_ground_action_start_allowed=1` on `796 / 1135` rows,
      `obs_self_jump_start_allowed=1` on `796 / 1135` rows, and
      `obs_self_air_attack_allowed=1` on `64 / 1135` rows. The recording also
      covered forward/back movement, neutral/forward/back jump phases,
      `air-lk` / `air-hk`, fireball, shoryuken, tatsu, and throws.
    - second blocker found: jump-start labels were still `0` because the first
      logged frame carrying up input had already advanced to ordinary
      jump-ready (`phase=1`, `R1=0`, `R2=16/17`), where the first
      `obs_self_jump_start_allowed` derivation was false. Broaden
      `obs_self_jump_start_allowed` to mean "jump-start action family is
      allowed", including ordinary jump-ready continuation, while keeping
      `obs_self_ground_action_start_allowed` false in jump-ready and keeping
      `obs_self_air_attack_allowed` reserved for ordinary jump-air.
    - before V41/Vnext training, re-record one more short schema-v4 human/CPU
      smoke and confirm `jump-forward-start`, `jump-neutral-start`, and
      `jump-back-start` appear alongside `air-*`, and that no old mixed
      `jump-neutral-mk` / `jump-back-hk` labels return.
    - post-fix human/CPU smoke log
      `logs/rl-transitions-cpu-human-demo-schema-v4-smoke-4-3-3.ndjson`
      passed the split-label validation:
      - `1271 / 1271` rows use transition schema `4`, with all schema-v4 OBS
        fields present.
      - allow density is now useful and state-specific:
        `obs_self_ground_action_start_allowed=1` on `917` rows,
        jump-ready-only `obs_self_jump_start_allowed=1` on `13` rows, and
        `obs_self_air_attack_allowed=1` on `67` rows.
      - split labels appear as intended:
        `jump-forward-start=6`, `jump-neutral-start=7`,
        `jump-back-start=4`, `air-hp=2`, and `air-hk=2`.
      - old mixed jump-attack labels such as `jump-neutral-mk` and
        `jump-back-hk` did not return.
      - fireball and tatsu engine labels were observed from ground-action
        rows, then their attack routines correctly closed all ground/jump/air
        action-start flags. Shoryuken was not present in this particular
        post-fix smoke and should be covered by the next broader training/demo
        capture rather than blocking the split-label validation.
    - follow-up inspection of `stand-hk` / `crouch-hk` rows found one more
      demo-label cleanup before V41 training:
      - `stand-hk` had some clean start rows with
        `(ground=1, jump=1, air=0)`, but most held-button rows were already in
        `R1=4` attack state with all allow flags off.
      - `crouch-hk` rows in the smoke were all `R1=4/R2=0` attack-state rows
        with all allow flags off, meaning the held input was being repeatedly
        labeled as a new `crouch-hk` action.
    - fix: gate demo input labels for throw, command normals, crouch normals,
      and stand normals on `obs_self_ground_action_start_allowed=1`. Keep
      `air-*` labels gated by `obs_self_air_attack_allowed` and
      `jump-*-start` labels gated by `obs_self_jump_start_allowed`. If held
      ground attack input is observed during attack/recovery/lockout, leave the
      row as neutral/none instead of labeling another ground action start.
    - follow-up deployed smoke
      `logs/rl-transitions-cpu-human-demo-schema-v4-smoke-4-3-3.ndjson`
      showed the ground gate working, but exposed an air-normal attribution
      gap: the log had `9` `R1=4/R2=3` common air-normal routine segments, but
      only `4` `air-*` labels (`air-hk=3`, `air-hp=1`). Several starts had
      `obs_self_air_attack_allowed=1` on the previous ledger row, then the
      attack button appeared after the routine had already switched to
      `R1=4/R2=3`; input gating correctly suppressed repeated lockout labels,
      but engine attribution only caught starts with a fresh
      `self_attack_started` edge.
    - fix: let Ryu demo engine normal attribution also trigger from
      `self_attack_routine_started` when the new routine is a known common
      normal attack routine (`R2=0/3/4`). Specials and throws still use the
      explicit routine mapper first, so this only backfills normal attack
      starts such as air normals.
    - next targeted smoke before V41 should confirm:
      - clean `stand-hk` and `crouch-hk` start rows appear with
        `(ground=1, jump=1, air=0)`.
      - attack routine/recovery rows no longer carry repeated input labels for
        `stand-hk`, `crouch-hk`, throw, or command normals.
      - the number of `air-*` labels tracks the number of real air-normal
        `R1=4/R2=3` routine-start segments, without repeated labels through
        the rest of the air attack routine.
      - `jump-*-start`, `air-*`, and special engine labels remain separated.

- Step 3B: add projectile-threat observation fields before training the first
  anti-fireball / jump-over model.
  - Motivation:
    - the action taxonomy already has the right escape action:
      `jump-forward-start`, `jump-neutral-start`, or `jump-back-start`.
    - however, the model cannot reliably learn "jump over the fireball" unless
      the observation tells it that an active projectile is on screen after the
      thrower has recovered.
    - opponent routine `R1=4/R2=16` only describes the startup/recovery of the
      fireball move; it is not enough once the projectile is traveling.
  - Candidate schema fields:
    - `obs_projectile_active`: `1` when a relevant active projectile exists,
      otherwise `0`.
    - `obs_projectile_owner`: relative owner enum, initially `0=none`,
      `1=self`, `2=opponent`.
    - `obs_projectile_rel_x`: signed projectile X relative to self, normalized
      by self facing so positive means "in front of self".
    - `obs_projectile_rel_y`: signed projectile Y relative to self.
    - `obs_projectile_vel_x`: signed projectile X velocity normalized by self
      facing; for an incoming opponent projectile in front of self this should
      usually be negative.
    - `obs_projectile_time_to_self`: optional derived estimate in frames; use a
      sentinel/clamped max value when there is no active projectile or the
      projectile is not moving toward self.
  - First-version selection rule:
    - prefer the nearest active opponent-owned projectile that is in front of
      self and moving toward self.
    - if no incoming opponent projectile exists, fall back to the nearest active
      projectile and expose `owner` so the model can distinguish self zoning
      from incoming threat.
    - keep the field count small: one selected projectile is enough for the
      first Ryu fireball/jump-over curriculum; multi-projectile summaries can
      be added later if needed.
  - Implementation method recorded 2026-05-01:
    - derive projectile observations in C from live engine state, not in the
      Python probe. The authoritative path is each player's
      `plw[player].wu.shell_ix[0..7]` list, whose valid entries index `frw[]`
      `WORK_Other` effect records.
    - scan both players' shell lists so the selected projectile can be
      self-owned or opponent-owned relative to the RL agent. Use
      `WORK_Other.master_id` to assign `obs_projectile_owner`.
    - first active-candidate filter matches the CPU shell-avoidance path:
      require an active shell/effect (`wu.be_flag`, `wu.id == 13`,
      `wu.routine_no[0] == 1`, not dying routine `wu.routine_no[1] == 2`),
      skip non-projectile/auxiliary shell types, and only accept shells owned
      by self or opponent.
    - normalize `obs_projectile_rel_x` and `obs_projectile_vel_x` by
      `obs_self_facing_sign` so positive `rel_x` means the projectile is in
      front of self, and negative `vel_x` means it is moving toward self.
    - use sentinel `32767` for no useful distance/time estimate. For
      `obs_projectile_time_to_self`, only compute a finite frame estimate when
      the selected projectile is in front of self and moving toward self.
    - schema-v5 packs these six fields into the live OBS spacing payload and
      transition NDJSON, then exposes them as normalized DQN features and
      verbose probe diagnostics.
  - Expected implementation areas:
    - C observation builder: locate the authoritative active projectile state
      used by Ryu hadouken and derive the compact projectile fields from live
      game globals, not from opponent move routine alone.
    - C/Python protocol: bump the OBS spacing payload/schema version as needed
      and serialize/decode the new projectile fields.
    - Python probe/training/analyzer: add feature normalization, model
      metadata, verbose diagnostics, and analyzer summaries for projectile
      active/owner/distance/velocity/time-to-self buckets.
  - Implementation status 2026-05-01:
    - implemented as schema v5 in `src/rl/rl_observation.*`,
      `src/rl/rl_protocol.h`, `src/rl/rl_session.c`, and
      `tools/rl_probe_server.py`.
    - live OBS spacing payload is now 44 bytes and transition NDJSON carries
      the same six projectile fields for replay/training.
    - Python DQN feature normalization and verbose diagnostics now expose the
      selected projectile threat as `proj=active/owner`, `proj_rx`, `proj_ry`,
      `proj_vx`, and `proj_t`.
    - local validation passed with `python3 -m py_compile
      tools/rl_probe_server.py` and `tools/mister/build-game.sh --flavor
      telemetry`.
    - on-device schema-v5 smoke
      `logs/rl-transitions-projectile-schema-v5-smoke-4-3-3.ndjson` confirmed:
      - all `2403` rows use transition schema `5`.
      - projectile observation stayed active across traveling fireball frames:
        `230 / 2403` rows had `obs_projectile_active=1`.
      - owner/sign semantics worked for both self and opponent projectiles:
        self-owned rows had positive `rel_x` / positive `vel_x`; opponent
        incoming rows had positive `rel_x`, negative `vel_x`, and finite
        `time_to_self`.
      - Shinkuu Hadouken also appeared as a self-owned projectile segment after
        the engine-labeled super start row.
      - jump-start rows near incoming opponent projectiles include both
        damaged too-late jumps and safe jump-over examples, which is enough
        signal for the next targeted demo/training pass.
    - `tools/analyze_rl_transitions.py` now has first-class projectile summary
      output for schema-v5 logs: owner counts, projectile segments,
      incoming-projectile time buckets, fireball engine-label counts, and
      jump-start near-projectile damaged/safe row diagnostics.
    - added `PROJECTILE_GUARD_SUMMARY` diagnostics to the analyzer so
      incoming-projectile `back` / guard rows are counted separately from
      jump-start rows. This is a data-quality tool, not a training-behavior
      change: it verifies whether the replay set contains close/late fireball
      responses where blocking is safer than jumping.
    - latest schema-v5 projectile smoke
      `logs/rl-transitions-projectile-schema-v5-smoke-4-3-3.ndjson` reported
      `guard_rows=72`, `no_damage_rows=69`, `chip_rows=3`,
      `full_hit_rows=0`; all guard-response rows were currently labeled
      `back`, which matches the present demo labeler behavior for held-back
      blocking.
  - Validation before training:
    - record a targeted human-demo smoke with Ryu fireballs, neutral/forward
      jump-over responses, blocked/failed jumps, and no-projectile baseline
      movement.
    - confirm projectile fields stay active while the fireball is traveling,
      not only during opponent `R1=4/R2=16`.
    - confirm `obs_projectile_rel_x`, `obs_projectile_vel_x`, and optional
      `obs_projectile_time_to_self` have the expected signs on both left/right
      sides.
    - confirm jump-over demo rows label the action as `jump-*-start` while the
      projectile threat fields are visible in the decision row or recent
      preceding rows.
  - V41 baseline training result 2026-05-01:
    - trained `model/dqn-projectile-schema-v5-full-actions-v41-baseline`
      version `41` from
      `logs/rl-transitions-projectile-schema-v5-smoke-4-3-3.ndjson`.
    - recipe intentionally used the existing V38/V40 full-action DQN settings
      plus schema-backed `--dqn-valid-action-mask action-start-v1`; it did not
      add projectile-specific reward shaping or oversampling.
    - training built `1937` experiences from `7783` human-demo rows and
      published successfully, but it is not promotable:
      - masked greedy top action on the training eval slice was
        `shoryuken-hp 1367 / 1937 = 70.6%`.
      - same-log comparison with `action-start-v1` still chose
        `shoryuken-hp 4228 / 7783 = 54.3%`.
      - on incoming opponent projectile rows where
        `obs_self_jump_start_allowed=1`, V41 chose
        `shoryuken-hp 309 / 343 = 90.1%`, with `jump_top=0` and only
        `25 / 343` rows having any `jump-*-start` inside the top five.
      - a strong support-prior diagnostic reduced some sparse-action ranking
        but collapsed the same-log distribution to `back 6191 / 7783 =
        79.5%`; it did not make jump-over behavior emerge.
    - conclusion: schema-v5 features are present, but the old generic
      full-action reward recipe does not teach anti-fireball response. The
      next training change should be an opt-in projectile curriculum/reward
      profile that explicitly rewards safe jump-over timing, rewards close
      guard/back no-damage responses, penalizes late jump-into-fireball
      outcomes, and controls sparse action heads during projectile rows.
  - Trainer update 2026-05-01:
    - `tools/train_dqn_learner.py` now has opt-in
      `--reward-projectile-response-profile incoming-v1` shaping.
    - The profile only scores action-start rows with an incoming opponent
      projectile (`owner=opponent`, `rel_x > 0`, `vel_x < 0`, bounded
      `time_to_self`, `rel_x`, and `rel_y`).
    - It can add raw reward for clean `jump-*-start` rows that become airborne
      and clear/pass the projectile, add raw reward for close clean `back`
      spacing, add raw reward for close clean `guard-*` with contact, and
      subtract raw reward when a jump-start projectile response takes self HP
      damage.
    - `tools/rl_auto_retrain.py --reward-preset projectile-response-v1` opts
      into this shaping on top of the `ground-specials-v35a` recipe; existing
      reward presets remain unchanged.
  - V42/V43/V44 projectile-response training result 2026-05-01:
    - V42 used the first `projectile-response-v1` settings and published
      `model/dqn-projectile-schema-v5-full-actions-v42-response`, but the
      threat filter was too narrow: `threat_rows=4`, all projectile-response
      event counts were zero, and greedy behavior was unchanged.
    - Diagnostics showed the replay has `106` same-row incoming projectile
      action starts (`back=72`, `jump-forward-start=17`,
      `jump-back-start=7`, `jump-neutral-start=4`, `forward=6`), but many real
      projectile rows use `obs_projectile_rel_y=66` and `time_to_self=25-48`.
    - The preset was widened to `--reward-projectile-threat-max-abs-y 96` and
      `--reward-projectile-threat-max-time-to-self 48`.
    - V43 published
      `model/dqn-projectile-schema-v5-full-actions-v43-response`; shaping was
      now active: `threat_rows=89`, `safe_jump=18/21.6`,
      `late_jump_hit=10/15.0`, `projectile_net=6.6`.
    - V43 still did not fix the policy: same-log incoming projectile +
      jump-start-allowed rows stayed at `shoryuken-hp 313 / 343`, with
      `jump_top=0`.
    - V44 added train-time unsupported-action regularization and published
      `model/dqn-projectile-schema-v5-full-actions-v44-response-unsupported-reg`.
      This reduced global `shoryuken-hp` only modestly (`54.3%` V41 to
      `51.7%` V44) and incoming projectile rows only from `309 / 343` to
      `306 / 343`; `jump_top` remained `0`.
    - conclusion: projectile-response reward shaping is wired and measurable,
      but sparse event counts plus full-action Q overestimation still dominate.
      Do not promote V42/V43/V44. The next training change should add
      projectile-response row oversampling / batching or an explicit
      projectile-response action-target curriculum before another full recipe
      retrain.

- Step 4: train-time invalid-action Q penalty on the split action space.
  - Do this after Step 3, not before it.
  - Goal:
    - make the DQN weights themselves learn that illegal actions for the
      current state should not have competitive raw Q values.
    - this is a soft model-quality improvement, not a hard legality guarantee.
      Live/probe inference should still keep the hard valid-action mask until
      there is a deliberate replacement.
  - Candidate training rule:
    - for each replay state, compute valid and invalid actions with the
      schema-backed action eligibility helper used by target selection and
      probe inference.
    - add an opt-in auxiliary loss that pushes invalid-action Q values below
      the best valid-action Q by a configured margin, for example:
      `max(0, q_invalid - max(q_valid) + margin)^2`.
    - avoid applying the penalty when the valid set is empty; record those rows
      as diagnostics instead of manufacturing a target.
  - Why this differs from the V39 unsupported-action regularizer:
    - V39 only penalized globally unsupported or low-support action heads.
    - this penalty is state-conditioned: a `jump-*-start` head can be valid
      while grounded, an `air-*` head can be valid while airborne, and both
      should be invalid in non-movable states.
  - Implementation notes for later:
    - keep it opt-in, with flags for enablement, margin, loss weight, and
      optional cap/normalization strategy.
    - record metadata and stdout diagnostics for penalized rows/actions,
      empty-valid rows, total auxiliary loss, and raw-vs-masked greedy action
      distributions.
    - evaluate it first on the CPU-demo V38/V40 successor recipe before mixing
      live replay.
  - Validation target:
    - raw `valid_mask=off` same-observation compare should no longer be
      dominated by impossible grounded `air-*` attacks or airborne
      `jump-*-start` actions.
    - masked inference should remain stable and should not collapse into a new
      single guard/fireball action.
    - even if raw behavior improves, live probing should continue to use the
      actor metadata auto-mask or an explicit valid-action mask; reserve
      `--dqn-valid-action-mask off` for raw diagnostic runs.

Implementation notes:

- `tools/rl_probe_server.py --policy tabular` now supports a minimal contextual-bandit learner loop:
  - transition rows are bucketed from the compact spacing snapshot (`obs_abs_dx`, `obs_abs_dy`, front/back edge distances, `obs_opp_in_front`) plus `obs_opp_routine_attack_state` as `opp_attack=0/1` for strike-defense learning
  - the learner maintains per-state action scores for explicit actions including movement, stand/crouch/jump normals, `fireball-lp` / `fireball-mp` / `fireball-hp`, `throw`, `shoryuken-lp` / `shoryuken-mp` / `shoryuken-hp`, and `tatsu-lk` / `tatsu-mk` / `tatsu-hk`
  - `--tabular-actions` can restrict live tabular learning and learner-published tabular actors to a curriculum subset; use a fresh model dir/log for each subset, and choose a `--tabular-fallback-policy` that resolves to an action inside that subset
  - neutral rows are not learned as greedy actions in the first version, because delayed damage/recovery rewards can otherwise make "do nothing" look falsely good
  - tabular score updates use a learner-local reward of `delta_opp_hp - delta_self_hp`; transition `reward_accum` still keeps full episode reward including terminal win/loss bonuses for future sequential RL learners
  - when a neutral/recovery row carries nonzero HP-delta reward, the learner conservatively credits that reward to the most recent explicit action bucket
  - each imported replay row applies an exponential update toward that tabular HP-delta reward for the executed action
  - learner-published `tabular` actor manifests include `actions`, `epsilon`, `fallback_policy`, `updated_rows`, `q`, `q_counts`, and `min_action_count`
  - tabular/DQN actor manifests carry `action_set_version=4`; probe hot-load ignores older model manifests so stale q-tables do not reinterpret old `back` guard credit as plain retreat, old generic jump-attack IDs as direction-specific jumps, or old generic normal IDs as stance-specific normals
  - inference uses the active actor q-table only when a positive-scoring action has at least `min_action_count` updates for the latest learned bucket; otherwise it falls back to a scripted policy such as `hp`
  - `--tabular-min-action-count` defaults to `8` to keep sparse lucky hits from immediately becoming greedy actions
  - learner stats print `top_raw=<action>:<score>/<count>` for the highest q-score and `top_ready=<action>:<score>/<count>` for the highest action that satisfies the same minimum-count gate used by greedy inference
  - learner stats also print `ready_actions=...`, `ready_dx=close{...} mid{...} far{...}`, `ready_opp_attack=0{...} 1{...}`, and `ready_threat_dx=atk0_close{...} ... atk1_far{...}` so live runs can show whether ready greedy choices are diversifying by spacing, opponent strike-warning state, and their cross-product
  - tabular `back` is now plain retreat / spacing movement again: one relative `back` wire decision stamped as policy action `walk/back`
  - `guard-stand` and `guard-crouch` are separate learner actions and scripted probe policies:
    - `guard-stand`: six consecutive relative `back` decision replies, roughly an 18-frame stand-guard window with the current `decision_interval=3` / `action_hold=3` timing
    - `guard-crouch`: six consecutive relative `down-back` decision replies, roughly an 18-frame crouch-guard window with the same timing
  - the legacy scripted `guard` policy remains an alias for stand guard, but new learner action attribution should use `guard-stand` or `guard-crouch`
  - transition schema v3 requires `transition_schema_version = 3` and uses only non-overlapping action-label families:
    - `policy_*`: remote RL/DQN/tabular policy request and execution
    - `input_*`: human-demo / CPU-demo input-derived labels such as walk, back, guard intent, and simple normals
    - `engine_*`: engine-observed move-start labels from validated `R1/R2/KW/AK` attribution
  - schema v3 intentionally removed the old `requested_policy_*`, `executed_policy_*`, and `demo_attributed_*` compatibility fields; Python replay/training/analyzer tools now reject schema 1/2 logs instead of guessing legacy semantics
  - tabular inference now locks multi-step scripted actions such as `fireball-lp` until the full input sequence has been emitted, preventing later q-table decisions from interrupting QCF+LP before the projectile can come out
  - jump attacks now use direction-specific policy action IDs:
    - `jump-forward-lp`, `jump-forward-mp`, `jump-forward-hp`, `jump-forward-lk`, `jump-forward-mk`, and `jump-forward-hk`: `jump_attack_forward` / button strength
    - `jump-neutral-lp`, `jump-neutral-mp`, `jump-neutral-hp`, `jump-neutral-lk`, `jump-neutral-mk`, and `jump-neutral-hk`: `jump_attack_neutral` / button strength
    - `jump-back-lp`, `jump-back-mp`, `jump-back-hp`, `jump-back-lk`, `jump-back-mk`, and `jump-back-hk`: `jump_attack_back` / button strength
  - `jump-forward-mk` remains available as both a scripted probe policy and a tabular macro action: `up-forward -> up-forward -> up-forward+MK -> up-forward+MK -> neutral -> neutral`; transition credit maps the `up-forward+MK` wire phase back to the high-level `jump-forward-mk` bucket
  - the HK jump-kick probes use the same six-step shape with `HK` and their corresponding jump direction
  - stand and crouch normals now use stance-specific policy action IDs:
    - `stand-lp`, `stand-mp`, `stand-hp`, `stand-lk`, `stand-mk`, `stand-hk`: `stand_normal` / button strength
    - `crouch-lp`, `crouch-mp`, `crouch-hp`, `crouch-lk`, `crouch-mk`, `crouch-hk`: `crouch_normal` / button strength
  - the legacy scripted `hp` policy remains as an alias for `stand-hp`, but learner action attribution should use `stand-hp`
  - Ryu Shoryuken learner actions use strength-specific macros and taxonomy sub-actions:
    - `shoryuken-lp`: `forward -> down -> down-forward -> down-forward+LP -> neutral -> neutral`
    - `shoryuken-mp`: `forward -> down -> down-forward -> down-forward+MP -> neutral -> neutral`
    - `shoryuken-hp` / `shoryuken`: `forward -> down -> down-forward -> down-forward+HP -> neutral -> neutral`
  - Ryu Tatsumaki Senpukyaku learner actions use strength-specific macros and taxonomy sub-actions:
    - `tatsu-lk` / `tatsu`: `down -> down-back -> back -> back+LK -> neutral -> neutral`
    - `tatsu-mk`: `down -> down-back -> back -> back+MK -> neutral -> neutral`
    - `tatsu-hk`: `down -> down-back -> back -> back+HK -> neutral -> neutral`
  - Ryu Hadouken learner actions use strength-specific macros and taxonomy sub-actions:
    - `fireball-lp`: `down-back -> down -> down-forward -> forward+LP -> neutral -> neutral`
    - `fireball-mp`: `down-back -> down -> down-forward -> forward+MP -> neutral -> neutral`
    - `fireball-hp`: `down-back -> down -> down-forward -> forward+HP -> neutral -> neutral`
    - CPU-demo `engine_*` rows now keep `fireball-lp`, `fireball-mp`, and `fireball-hp` as distinct DQN actions when those names are present in the training action set
    - the LP sequence remains the anti-DP default for the legacy `fireball` / `ryu-fireball` aliases; model manifests and CLI action subsets canonicalize those names to `fireball-lp`
  - `rl-control-source = human-demo` records human-controlled agent-side input as transition rows without overwriting `p1sw_buff` / `p2sw_buff`:
    - the selected `rl-player` side stays human-controlled while the opponent routing still follows `rl-opponent-mode`
    - transition rows are tagged with `execution_source = 4`
    - requested/executed action metadata is identical because the human action is already executed locally
    - with `rl-network = on`, the UDP handshake and transition-batch upload path remain available, but OBS/action request packets are not emitted
    - the first mapper labels down-back as `guard-crouch`, labels back as `guard-stand` only when the latest compact observation sees opponent routine attack state at short/mid distance, and otherwise keeps back as `walk/back`
    - the wrapper OSD exposes this as `RL Settings -> RL Control (Restart), Remote / Human Demo / CPU Demo`, persisted as `rl-control-source`
  - `rl-control-source = cpu-demo` records built-in CPU-controlled agent-side input as transition rows:
    - the selected `rl-player` side is routed as CPU-controlled while the opponent routing still follows `rl-opponent-mode`
    - transition rows are tagged with `execution_source = 5`
    - requested/executed action metadata is identical because the game CPU action is already executed locally
    - with `rl-network = on`, the UDP handshake and transition-batch upload path remain available, but OBS/action request packets are not emitted
    - the same demo mapper labels walk/guard/stand-normal/crouch-normal/jump-attack/throw metadata from the CPU-resolved input
    - Ryu demo rows also include engine-attributed move metadata when the game starts an attack routine:
      - `engine_action_id`
      - `engine_sub_action_id`
      - `engine_routine_1`
      - `engine_routine_2`
      - `engine_kind_of_waza`
      - `engine_current_attack`
      - `engine_label_source`
      - `engine_lag_frames`
      - `input_*` remains the input-derived label; `engine_*` is the engine-observed actual move, useful for CPU-demo/human-demo labels and accidental-command checks
      - first-pass attribution is Ryu-specific: specials/throws use `character_id + routine_no[2] + kind_of_waza`, while normal attacks use `current_attack` / normal `kind_of_waza` with a best-effort action class from the sampled input state
      - the reusable expansion method is documented in `docs/rl-policy-action-taxonomy.md#engine-move-attribution-method`: add another character by matching source command slot -> engine `R2` dispatch -> observed `R2/KW/AK/RS` overlay values before promoting the decoder to runtime
      - `tools/analyze_rl_transitions.py` can now delayed-credit `engine_*` move starts over a configurable future decision window:
        - `--engine-outcome-window-decisions N` sums later `delta_opp_hp` / `delta_self_hp` inside the same episode to classify each engine-labeled move as hit, whiff/no-damage, punished, or trade
        - `--engine-outcome-stop-at-next-event` optionally prevents overlapping windows, but the default keeps overlap allowed because projectiles can hit after the next input
        - this is analysis / reward-shaping logic, not C-side transition truth
  - the Fight debug overlay now exposes self-side attack identity probe fields before adding them to transition rows:
    - `SATT R2<routine_no[2]> AK<current_attack> KW<kind_of_waza> RS<attack_routine_started>`
    - these fields are overlay-only until validated against visible normals, specials, throws, and projectiles
  - MiSTer remote config was checked on `192.168.0.133`; no `perf-*` config keys or recent `PERF capture` logs were present, so the latest long-run restart was not explained by an enabled perf capture
  - `src/rl/rl_net.c` now protects the transition sender running-state with the transition queue mutex, clears it while observing an empty queue, reaps completed thread handles before replacement, and avoids clearing the shutdown handle until after the sender is joined
  - learner auto-publish skips duplicate tabular actor publication when `tab_updates` has not increased since the previous publish
  - `tools/analyze_rl_transitions.py <transition-log>` summarizes direct and delayed-credited HP-delta reward by action and `obs_abs_dx` bucket; use it before changing action sets or reward rules
  - transition rows include raw diagnostic routine ids for analyzer and learner-visible engine-state mapping:
    - `obs_self_routine_1`, `obs_self_routine_2`
    - `obs_opp_routine_1`, `obs_opp_routine_2`
    - as of the v23 feature-slice experiment, UDP OBS payload v3 also carries these raw ids.
    - tabular state keys still do not consume raw routine ids.
    - DQN v23 consumes opponent routine ids only through categorical one-hot features, not as continuous numeric features.
  - first full-log analyzer pass on `logs/rl-transitions-tabular-4-3-3.ndjson` (`383918` rows, `448` done rows) showed far fireball as the cleanest positive signal (`direct fireball dx=far reward=+1625`, credited fireball `reward=+2391`) while throw was negative in credited view (`reward=-3435`), so throw should not be treated as learner-safe strength until move-level labels or cleaner credit confirm it
  - UDP OBS packets now carry a schema-versioned compact spacing/state payload (`payload_version=3`) with the same bucket inputs used by transition replay: `obs_abs_dx`, `obs_abs_dy`, front/back edge distances, `obs_opp_in_front`, raw self/opponent routine ids, plus routine flags for `routine_no[1] == 4` attack state and `routine_no[1] == 1` contact/defensive reaction state.
  - only opponent attack state is promoted to the tabular learner state key; DQN v23 additionally uses opponent routine one-hot features.
  - Python-side tabular inference prefers the same-frame OBS spacing bucket and falls back to the latest replay-imported bucket only when an old header-only OBS packet or invalid payload is seen
  - learner stats print `obs=<payload>/<header-only>` and `tab_state=obs:<n>/latest:<n>` so live runs can confirm whether tabular inference is using same-frame OBS state
- Anti-air Shoryuken feature plan:
  - Goal: teach the DQN to choose `shoryuken-*` when the opponent is jumping in, without globally over-buffing every engine-labeled hit or destabilizing the current fireball / spacing / guard balance.
  - Do not rely only on raw `obs_opp_routine_1` / `obs_opp_routine_2` as continuous numeric DQN inputs:
    - those raw routine ids are useful analyzer diagnostics, but they are categorical engine state codes.
    - if they become learner-visible, train and live inference must both receive the same schema-versioned values; adding them only to transition logs would create train/live mismatch.
  - Prefer derived learner features for the first anti-air schema slice:
    - `obs_opp_airborne`: opponent is in a validated jump-air / airborne routine state.
    - `obs_opp_jump_toward`: opponent airborne movement is closing horizontal distance or is otherwise identified as a forward jump-in.
    - `obs_opp_above_self`: opponent has vertical separation consistent with a jump-in threat.
    - `obs_anti_air_threat`: compact boolean derived from airborne + closing/jump-in + Shoryuken-relevant distance/height.
    - raw routine ids are live-visible as of OBS payload v3, but higher-level derived flags are still preferred for anti-air-specific policy work.
  - Implementation sequence:
    - validate Ryu / opponent jump-in routine states with fresh schema-v3 logs and analyzer summaries.
    - bump the OBS spacing/state payload version and add the derived anti-air fields to both C-side OBS packets and Python `parse_obs_spacing_payload()`.
    - add the derived fields to `DQN_FEATURE_NAMES` / `DQN_FEATURE_SCALES`, so `tools/train_dqn_learner.py` model manifests and `tools/rl_probe_server.py --policy dqn` live inference use identical inputs.
    - add compare/analyzer diagnostics that bucket greedy choices by `obs_anti_air_threat=0/1`, especially Shoryuken top1/top2/top3 rate and blocker action.
  - Data requirement:
    - collect a dedicated human-demo anti-air log such as `logs/rl-transitions-human-demo-antiair-shoryuken-v1-4-3-3.ndjson`.
    - the demo should include repeated opponent jump-ins at close/mid spacing, correctly timed `shoryuken-mp` / `shoryuken-hp`, and a small number of late/whiff/punished examples so the model sees both success and failure.
  - Reward-shaping requirement:
    - avoid using a large global `--engine-outcome-hit-bonus` such as `3.0` as the main anti-air fix, because it also buffs fireballs, tatsu, throw, and normal engine hits.
    - add a targeted anti-air Shoryuken reward knob instead, for example a future `--reward-anti-air-shoryuken-hit-bonus`, applied only when:
      - the training action is `shoryuken-lp`, `shoryuken-mp`, or `shoryuken-hp`;
      - the decision or delayed-outcome window observed `obs_anti_air_threat=1` / opponent airborne jump-in evidence;
      - the delayed outcome includes opponent HP damage.
    - keep normal Shoryuken whiff/punished costs separate so the agent still learns not to DP after neutral jumps, back jumps, or out-of-range airborne states.
  - Success criteria for the first A/B test:
    - on anti-air-threat observations, Shoryuken variants appear in top1/top2/top3 at a materially higher rate than the baseline model.
    - on non-airborne or far/back-jump observations, Shoryuken remains rare and does not replace fireball / spacing / guard decisions.
    - live probe logs show actual Shoryuken attempts against jump-ins, not only elevated offline Q ranks.
  - `tools/train_dqn_learner.py` now supports the first offline DQN/MLP Q learner path:
  - reads transition NDJSON logs and converts rows into `(state, action, reward, next_state, done)` experiences using the same learner-safe HP-delta reward as tabular (`delta_opp_hp - delta_self_hp`)
  - can optionally train from engine-labeled move starts instead of input-only demo labels:
    - `--engine-outcome-training-mode off|prefer-engine-action`
    - `off` is the default and keeps the existing DQN replay behavior unchanged
    - `prefer-engine-action` uses `engine_*` event rows in place of input-based experiences only when a demo row has an engine-labeled move and that action is present in the configured `--actions` subset
    - if an engine-labeled action is not present in `--actions`, trainer diagnostics count it as an excluded engine-outcome event and force the normal replay path to use the row's `input_*` label, preserving subset training data instead of selecting the same unsupported `engine_*` label again
    - unattributed demo rows still keep their normal input-based experiences, preserving walk / guard examples
    - `--engine-outcome-window-decisions N` sums later `delta_opp_hp` / `delta_self_hp` in the same episode to give each engine-labeled move a delayed outcome reward
    - `--engine-outcome-action-windows action=N,...` reserves per-action delayed-credit tuning while preserving a global default window
    - `--engine-outcome-stop-at-next-event` can prevent overlapping windows when projectile-delayed credit is not desired
    - `--engine-outcome-hit-bonus`, `--engine-outcome-no-damage-cost`, and `--engine-outcome-punished-cost` are raw reward adjustments applied before `--reward-scale`
    - `--engine-outcome-oversample N` and `--engine-outcome-action-oversamples action=N,...` can duplicate included engine-outcome experiences in replay so low-frequency engine-labeled specials can be A/B tested without changing raw logs or normal input replay rows
    - stdout and model metadata record `engine_outcome=...` / `engine_outcome_stats` so CPU-demo training can be audited for included/excluded events, hit/no-damage/punished/trade counts, HP sums, reward adjustment totals, and oversampled replay experience counts
    - stdout and model metadata also record `source_replay_diagnostics`, splitting replay rows and built experiences by `execution_source`, `model_version_executed`, and per-source action reward/counts; this is diagnostics-only and does not change replay sampling
    - `--replay-source-include`, `--replay-source-exclude`, `--replay-source-max-rows`, and `--replay-source-ratios` provide opt-in source-mix control before DQN experience building; default empty flags keep raw replay behavior unchanged
    - `--replay-source-ratios remote=0.7,human-demo=0.3` applies deterministic row-level undersampling with `--seed`; sources not listed in the ratio are dropped, which is useful for excluding `repeated-last-action` / `neutral-fallback` rows from v18 candidate training
    - model metadata records `replay_source_mix_config` and `replay_source_mix_stats`, including pre/post source counts, dropped counts, and target row counts
    - deprecated hidden aliases for the old `--demo-attribution-*` flag names still map to the new engine-outcome config for short-term command compatibility; removed schema-v2 modes `augment` and `replace-demo` now fail fast
  - can train with balanced replay batches:
    - `--batch-sampling uniform|balanced`
    - `uniform` preserves the historical random replay sampling
    - `balanced` samples each training batch by action family using `--balanced-batch-ratios movement=0.4,normal=0.3,special=0.3`
    - movement includes `forward`, `back`, `guard-stand`, and `guard-crouch`; normal includes normals and `throw`; special includes `fireball-*`, `shoryuken-*`, and `tatsu-*`
    - stdout and model metadata record `batch_sampling` diagnostics with pool counts and per-batch target counts so DQN A/B tests can confirm whether specials are actually represented in every batch
  - can apply an opt-in support-aware conservative action penalty after replay building:
    - purpose: reduce sparse-action Q overestimation where a low-support action such as `crouch-hp` / `stand-mk` / `fireball-lp` becomes a greedy all-purpose answer despite weak observed reward evidence
    - the penalty is trainer-only reward shaping; it does not change transition schema, C-side logging, OBS payloads, or live inference code
    - `--conservative-action-penalty` subtracts a positive raw reward cost from each replay experience whose final post-build action count is below `--conservative-min-action-count`
    - `--conservative-negative-mean-extra` subtracts an additional positive raw reward cost when the action's observed mean reward is non-positive; when no observed rows exist for an action, the post-build training mean is used
    - `--conservative-exempt-actions` excludes known curriculum-safe actions from both checks, useful for protecting engine-labeled specials during early A/B tests
    - the adjustment runs after engine-outcome delayed credit / HP-delta consumption / macro continuation credit, so it does not interfere with attribution semantics
    - stdout and model metadata record `conservative_penalty` diagnostics: adjusted experience count, raw/scaled cost, low-count actions, non-positive-mean actions, and per-action cost totals
    - first A/B target: rerun a v9/v11-style ground-specials command with conservative penalties enabled and check whether `crouch-hp`, `stand-lp`, `stand-hk`, and `stand-mk` fall without creating a new `guard` / `fireball` collapse
  - supports offline A/B/C reward-risk profiles without changing transition logs:
    - `--reward-risk-profile none`: baseline `hp-delta` reward
    - `--reward-risk-profile shoryuken-only`: applies only Shoryuken no-damage / punished extra costs
    - `--reward-risk-profile all-attacks`: applies generic attack no-damage / punished costs, plus Shoryuken extra costs
  - reward-risk costs use positive `cost` parameters (`--reward-attack-no-damage-cost`, `--reward-attack-punished-cost`, `--reward-shoryuken-no-damage-extra-cost`, `--reward-shoryuken-punished-extra-cost`) and are subtracted before `--reward-scale`, avoiding confusing negative penalty arguments
  - reward-risk lookahead supports per-action overrides with `--reward-risk-action-windows action=N,...`, so projectile or long-animation actions can use a longer no-damage / punished evaluation window than quick normals
  - jump attacks can receive additional high-commitment risk cost on top of generic attack cost through `--reward-jump-attack-no-damage-extra-cost` and `--reward-jump-attack-punished-extra-cost`; Phase 1 uses this to make `jump-forward-mk` whiffs costlier than ground `stand-mk` / `crouch-mk` whiffs without banning useful jump-ins outright
  - guard reward shaping is available for offline Phase 1 DQN experiments without changing transition schema:
    - `--reward-guard-success-bonus` adds raw reward to `guard-stand` / `guard-crouch` starts when `obs_opp_routine_attack_state=1`, `obs_abs_dx <= --reward-guard-threat-max-dx`, and the guard-success lookahead window has no self HP damage
    - `--reward-passive-guard-cost` subtracts raw reward from clean guard starts when the opponent is not attacking
    - `--reward-far-guard-cost` subtracts raw reward from clean guard starts outside the configured threat distance
    - passive/far guard costs apply only when the same guard lookahead window has no self HP damage, so a wrong guard that gets hit is punished by the natural HP-delta loss rather than double-counted as empty guard
    - guard shaping applies only on `executed_policy_action_step == 0` so multi-step guard macros do not receive repeated bonus/cost on every macro frame
    - diagnostics print `guard_shape=success:<events>/<bonus> passive:<events>/<cost> far:<events>/<cost> net:<raw_adjustment>` and metadata records the guard-shaping config/stat payload
  - spacing reward shaping is available for offline Phase 1 DQN experiments without changing live policy behavior:
    - `--reward-spacing-target-min-dx` / `--reward-spacing-target-max-dx` define the preferred `obs_abs_dx` band for basic MK-range movement experiments
    - `--reward-spacing-improve-bonus` rewards `forward` / `back` starts that move the next decision boundary closer to that target band
    - `--reward-spacing-worsen-cost` charges clean movement starts that move farther away from the target band
    - `--reward-spacing-maintain-bonus` can reward clean movement starts that keep both current and next decision boundary inside the target band
    - `--reward-spacing-threat-back-bonus` can add a small extra bonus when `back` increases too-close spacing while `obs_opp_routine_attack_state=1`
    - spacing shaping applies only on `executed_policy_action_step == 0` and only when the movement window has no self HP damage, so getting hit remains governed by natural HP-delta loss
    - diagnostics print `spacing_shape=target:<min>-<max> improve:<events>/<bonus> maintain:<events>/<bonus> worsen:<events>/<cost> threat_back:<events>/<bonus> net:<raw_adjustment>` and metadata records the spacing-shaping config/stat payload
  - corner position reward shaping is available for offline anti-turtle DQN experiments without changing transition schema:
    - `--reward-corner-back-edge-threshold` defines the own-back-edge distance treated as trapped near the corner
    - `--reward-corner-guard-cost` subtracts raw reward from clean `guard-stand` / `guard-crouch` starts near the corner
    - `--reward-corner-back-cost` subtracts raw reward from clean `back` starts near the corner
    - `--reward-corner-escape-bonus` rewards `forward` starts near the corner when the next decision boundary increases `obs_self_back_edge_dist` by at least `--reward-corner-escape-min-delta`
    - position shaping applies only on `executed_policy_action_step == 0` and only when the short position window has no self HP damage
    - diagnostics print `position_shape=corner_back_edge<=<threshold> corner_guard:<events>/<cost> corner_back:<events>/<cost> escape:<events>/<bonus> net:<raw_adjustment>` and metadata records the position-shaping config/stat payload
    - first CPU-demo all-normal experiments showed this improves general far-range passivity but does not fully solve `corner + far + opp_attack=0` turtling, because the current CPU-demo dataset has insufficient successful corner-escape alternatives for the DQN to imitate
  - projectile response reward shaping is available for offline anti-fireball DQN experiments without changing transition schema:
    - `--reward-projectile-response-profile incoming-v1` enables the profile; default `off` preserves existing recipes
    - incoming threats require opponent-owned active projectiles in front of self, moving toward self, within configurable `time_to_self`, `rel_x`, and `rel_y` bounds
    - `tools/rl_auto_retrain.py --reward-preset projectile-response-v1` currently uses `time_to_self=2..48` and `abs(rel_y)<=96`; the initial `2..24` / `<=48` filter was too narrow for the schema-v5 projectile smoke log
    - `--reward-projectile-safe-jump-bonus` rewards clean `jump-*-start` rows that become airborne and clear/pass the projectile inside the response window
    - `--reward-projectile-late-jump-hit-cost` subtracts raw reward when a jump-start response to an incoming projectile takes self HP damage
    - `--reward-projectile-close-back-success-bonus` rewards clean close-range `back` rows that increase spacing or clear/pass the projectile
    - `--reward-projectile-close-guard-success-bonus` rewards clean close-range `guard-stand` / `guard-crouch` rows, requiring guard contact by default
    - diagnostics print `projectile_shape=... safe_jump:<events>/<bonus> late_jump_hit:<events>/<cost> close_back:<events>/<bonus> close_guard:<events>/<bonus> net:<raw_adjustment>` and metadata records the projectile-response config/stat payload
    - `--projectile-response-safe-jump-oversample`, `--projectile-response-late-jump-hit-oversample`,
      `--projectile-response-close-back-oversample`, and
      `--projectile-response-close-guard-oversample` can opt into replay-copy
      oversampling for rows that satisfy the same projectile-response outcome
      classifier used by reward shaping; default `1` preserves baseline replay
      sampling.
    - `tools/rl_auto_retrain.py --reward-preset projectile-response-v2` builds
      on `projectile-response-v1` with safe-jump oversampling, late-jump-hit
      oversampling, lower Shoryuken engine-outcome oversampling, and a larger
      safe-jump bonus for focused anti-fireball candidates.
  - `--actions` trains and publishes a DQN action subset; excluded explicit actions are counted and reset delayed-credit attribution so their later neutral/recovery reward is not accidentally credited to the previous included action
  - DQN replay now treats high-level macro action starts as the training decision boundary:
    - only rows with `executed_policy_action_step == 0` create DQN experiences
    - recognized included macro continuation rows (`step > 0`) do not create new experiences
    - nonzero HP-delta on continuation rows is delayed-credited back to the most recent included step-0 experience
    - step-0 experience `next_state` is updated to the next step-0 action boundary, or the episode terminal row at episode end
    - stdout now prints `cont=<rows>` and `cont_rew=<scaled_reward>` so smoke runs can confirm continuation rows are no longer training decisions
  - `--drop-initial-episodes-per-run N` drops the first `N` `(run_id, episode_id)` episodes from each run before building experiences; use this for basic-only logs where early fallback/repeat-delay behavior creates heavy neutral pollution before the learner publishes useful actors
  - training diagnostics now print included/excluded action row counts, excluded reward sum, per-action count/reward/mean summaries, greedy top-1/top-2/top-3 summaries, and a collapse warning when one greedy action exceeds the configured threshold
  - uses normalized numeric spacing/threat features: `obs_abs_dx`, `obs_abs_dy`, both fighters' front/back edge distances, `obs_opp_in_front`, and `obs_opp_routine_attack_state`
  - trains a small stdlib-only MLP with target-network DQN updates, so it does not require `numpy` / `torch` for first smoke tests
  - publishes `policy=dqn` actor manifests with `actions`, `epsilon`, `fallback_policy`, and serialized MLP weights under `dqn`
  - `tools/rl_probe_server.py --policy dqn --model-dir <dir>` can hot-load those manifests and run DQN inference from same-frame OBS payloads, then reuse the existing macro/fixed action adapter for `fireball-lp`, `fireball-mp`, `fireball-hp`, `guard-stand`, `guard-crouch`, all standing/crouching LP/MP/HP/LK/MK/HK normals, all forward/neutral/back jump LP/MP/HP/LK/MK/HK normals, `shoryuken-lp`, `shoryuken-mp`, `shoryuken-hp`, `tatsu-lk`, `tatsu-mk`, and `tatsu-hk`
    - probe-side DQN inference can apply an opt-in action-support prior / reranker with `--dqn-support-prior-min-count`, `--dqn-support-prior-count-penalty`, `--dqn-support-prior-negative-mean-penalty`, and `--dqn-support-prior-exempt-actions`
    - the reranker reads actor metadata `action_counts` / `action_rewards`, subtracts the configured support penalty from each action's Q score at inference time, and leaves model weights, transition schema, replay logs, and default behavior unchanged when the flags are empty
    - the first conservative v9 live-recording candidate is `--dqn-support-prior-min-count 300 --dqn-support-prior-count-penalty 0.005 --dqn-support-prior-negative-mean-penalty 0.002`; stronger settings pushed the same v9 policy surface toward `fireball-hp` too aggressively
  - `tools/compare_dqn_models.py` compares A/B/C DQN manifests on the same transition observations and prints overall, distance/threat-bucketed, attack-rate, Shoryuken-rate, selected-Q, and collapse-warning greedy action distributions
    - compare runs can apply the same support prior to selected model labels through `--dqn-support-prior-models`, which lets raw v9 and reranked v9 be evaluated on the exact same observation rows before live use
- `docs/rl-policy-action-taxonomy.md` now records the first source-backed action registry:
  - universal actions use IDs below `1000`
  - character command actions use `1000 + character_id * 100 + source_command_slot`
  - sub-actions separate strength / stance / air / hold variants from the policy action ID
  - command rows carry source command slot, readable SF3 move-name alias, source routine handler, macro template, and validation status
  - ambiguous EX, air, or source-only variants keep slash-separated readable names until live validation proves they should be split
- Live tabular testing exposed a VS rematch / second-match transition issue:
  - second-match action control could continue, but episode transition batches stopped arriving after a later round ended
  - observed second-match flow could resemble arcade next-opponent selection
  - C-side fix now flushes the current episode ledger before remote runtime reset when gameplay leaves the override-eligible battle state
  - C-side VS result rematch now forces `MODE_VERSUS` / `Play_Mode = 1` while RL is active before entering the character-select transition
- RL active VS result now auto-selects rematch through the existing VS result case-6 path:
  - this is the conservative "方案 A" path: it avoids manual result-screen input but still uses `Setup_VS_Mode()` and the normal rematch transition instead of hard-resetting battle state
  - auto-rematch marks the next character-select pass to retain the previous `My_char[]` values, enqueue player loading, auto-complete character/SA selection, and skip the handicap / CPU-select branch before manual confirms are required
  - faster direct match restart remains a later option after this path is validated
- Long-run RL stability:
  - MiSTer `dmesg` showed Linux OOM-killed `3s-arm` at roughly `445MB` RSS during a long RL run
  - root cause candidate: each transition batch could create a short-lived sender thread, but completed thread handles were not joined before the pointer was overwritten by a later batch
  - `src/rl/rl_net.c` now reaps completed transition sender threads before starting another one and frees any queued transition payloads during runtime reset
- Example first live tabular command:
  ```sh
  python \\wsl.localhost\Ubuntu\home\olhua\src\3s-mister-arm\tools\rl_probe_server.py --host 0.0.0.0 --port 37330 --action-port 37331 --policy tabular --policy-repeat-delay-ms 3000 --model-version 0 --model-dir \\wsl.localhost\Ubuntu\home\olhua\src\3s-mister-arm\model\rl-model-tabular --transition-log \\wsl.localhost\Ubuntu\home\olhua\src\3s-mister-arm\logs\rl-transitions-tabular-4-3-3.ndjson --learner-auto-publish --learner-publish-policy tabular --learner-publish-interval-sec 10 --learner-warmup-rows 100 --learner-batch-size 32 --tabular-alpha 0.05 --tabular-epsilon 0.10 --tabular-fallback-policy hp --tabular-min-action-count 8
  ```
- transition NDJSON now carries `decision_delay_frames`, `decision_interval_frames`, and `action_hold_frames` so timing sweeps can be analyzed after the fact
- learner stats now print both `timing=` and `fallback_pct=` to make early Milestone 6 comparison runs easier to interpret
- learner stats now also keep a per-timing aggregate bucket so short timing sweeps can be compared inside one accumulated log stream
- learner stats now also keep a per-policy aggregate bucket so scripted move-family validation can compare `hp`, `throw`, `ryu-fireball`, `tatsu`, and `shoryuken` inside one log stream
- first short live timing sweep result:
  - `4/3/3` produced `sources=remote:256`
  - `fallback_pct=0.00`
  - `timing_fallback_pct=0.00`
  - `inf=512:95.7/189.2/939.6us`
  - treat `4/3/3` as the current first candidate baseline for Milestone 6 follow-up comparisons
- first fixed-policy move-family pass set is now complete:
  - `ryu-fireball`: pass
  - `shoryuken`: pass
  - `throw`: provisional pass; the old `logs/rl-transitions-throw-4-3-3.ndjson` contains the expected aggregate `320` opponent HP damage (`20` estimated 16-HP throws) across two rounds, but the old ledger compressed it into only `5` positive damage rows because decision rows used round-start HP and terminal cleanup could be counted as combat damage
  - `tatsu`: provisional pass
  - `hp`: control-path pass, but not the cleanest apples-to-apples fixed-policy comparison because it used the live learner/model-dir path
- throw follow-up fix:
  - `src/rl/rl_session.c` now exports decision-start `start_*_hp` values from the current observation HP
  - terminal non-battle observations now accumulate the final HP/stun/contact delta before episode finalization, so the last hit is not reduced to only the round-win bonus
  - the rerun still showed a round-end HP sync row (`144 -> 3`, `delta_opp_hp=141`) while only six rows actually requested/executed the throw macro, so throw validation needs direct throw/caught labels instead of HP-only counting
  - transition rows now include `self_throw_started`, `opp_throw_caught_started`, `self_throw_seen`, and `opp_throw_caught_seen`
  - learner logs now print `throw=<self_started>/<opp_caught_started>`
  - attack decisions now keep a 240-frame pending outcome window so late HP/contact/throw results can be credited back to the attack row instead of later neutral rows, including slower specials and projectile-style outcomes
  - round win/loss bonus now also prefers the pending attack row, so final-hit damage and KO reward stay together when possible
  - large `<=3 HP` round-conclusion sync jumps are only suppressed when no pending attack owner exists; otherwise they are retained for attack attribution
  - requested attack outcome fields are back in transition rows, and learner logs now print `reqatk=<active>/<contact>/<whiff>`
  - rerun a short `throw` pass before promoting throw outcome labels beyond debug / auxiliary status
- current next sub-phase:
  - fixed movement-prefix attack validation
  - examples: walk-forward-then-attack, crouch-then-attack, short retreat-then-attack
- do not promote all attack-outcome labels to learner-safe status yet; use the move-family pass set as evidence that the control path is stable enough to continue into prefix-based validation

### Milestone 6 V62 Projectile Timing Update

V62 adds a filtered projectile timing group margin objective to the DQN trainer.
This is the first trainer-side attempt to internalize the V61c policy-time
projectile timing rule:

- defense target ranges: `time_to_self 0-22` and `31-48`.
- safe-jump target range: `time_to_self 23-30`.
- defense target group: `back`, `guard-stand`, `guard-crouch`.
- jump target group: `jump-forward-start`, `jump-neutral-start`,
  `jump-back-start`.

Implementation status:

- [x] Add timing-range selectors for projectile batch and expert-margin rows.
- [x] Add `projectile_timing_group_margin` train-time objective.
- [x] Train and analyze V62 candidates using V61b/V61c live probe logs.
- [ ] Live-probe the best V62 candidate with a reduced policy-time prior.

Current candidate decision:

- best trained V62 candidate:
  `model/dqn-projectile-schema-v5-full-actions-v62-group-margin-candidate`
- rejected overshoot:
  `model/dqn-projectile-schema-v5-full-actions-v62-group-margin-strong-candidate`
- conclusion:
  V62 standalone improves close and early-projectile buckets but is not yet
  fully promotable without a small policy-time prior.

Key analysis:

- grounded live incoming projectile rows improved versus V60:
  - `0-6` jump rate: `41.4% -> 20.7%`.
  - `7-12` jump rate: `71.4% -> 35.2%`.
  - `31-36` jump rate: `90.6% -> 69.4%`.
  - `37-48` jump rate: `91.3% -> 67.4%`.
- safe-jump preservation for the best candidate stayed acceptable:
  human-demo safe-jump top-1 `495/504`.
- the strong candidate overfit defense and broke safe-jump:
  human-demo safe-jump top-1 `93/504`.

Next probe recommendation:

- use V62 group-margin candidate.
- keep `--dqn-projectile-timing-prior` enabled, but reduce jump penalties to
  around `0.02-0.03` for `0-22` and `31-48`.
- leave `23-30` unpenalized so safe jump remains available.

### Milestone 6 Full-Retrain Collection Plan

If the DQN line is restarted from scratch, use
[docs/agent-memory/remote-rl-retrain-data-collection-plan.md](agent-memory/remote-rl-retrain-data-collection-plan.md)
as the source of truth for data collection.

The plan changes the default collection strategy from "record a few free-form
gameplay logs and rely on reward shaping" to "collect a staged curriculum with
effective-experience quotas":

- Phase 0: schema and label sanity.
- Phase 1: movement and spacing.
- Phase 2: basic normals.
- Phase 3: specials.
- Phase 4: basic defense.
- Phase 5: projectile defense timing.
- Phase 6: anti-air and jump defense.
- Phase 7: corner and pressure.
- Phase 8: natural match integration and on-policy correction.

Important collection constraints:

- Operator-facing per-phase commands, log filenames, action restrictions,
  config notes, and pass gates are documented in
  [docs/agent-memory/remote-rl-retrain-data-collection-plan.md](agent-memory/remote-rl-retrain-data-collection-plan.md#operator-collection-runbook).
- Phase 5 is collected with human-visible projectile cues, not by trying to aim
  exact `time_to_self` buckets during play.
- Phase 5 post-analysis must split logs by `time_to_self` and opponent
  fireball-recovery/actionability; jump-forward punish should remain available
  beyond `23-30` when the opponent is still punishable.
- Phase 6 is the required anti-air patch after Phase 5, because projectile
  defense can otherwise generalize into a bad guard/back answer against jump-ins.
- Phase 7 includes oki/wakeup data, not only corner spacing.
- Phase 0 and every later phase need detector dry-run checks before training.

Minimum useful reboot target:

- about `60K` effective experiences.
- preferred target: `80K-120K` effective experiences.
- use effective action-start and outcome counts as collection gates, not raw row
  counts alone.

Future task tracking:

- [ ] Phase 0 sanity logs collected, analyzer-verified, and detector dry-run
  checked.
- [x] Phase 1 movement/spacing data collected and M1 movement baseline trained.
- [x] Phase 2 normals and far-whiff negative data collected; M2 v4c attack
  baseline trained and raw-validated without support-prior.
- [x] Phase 3 specials data collected; first seven M3 training attempts (v1-v6,
  M3a) all rejected because DQN could not produce special top-1 behavior without
  destroying M1/M2 movement replay. Root cause: context blindness — DQN MLP
  cannot distinguish "good special range" from "movement states" with current
  observation features, and engine labels cover only 2.7% of rows. BC
  pre-training approach validated: engine state (obs_self routine) + input labels
  provide 70.6% actionable label coverage. BC pre-training on full retrain data
  (M3bc v320, 66,756 labeled rows) followed by DQN conservative fine-tuning
  (M3bc+dqn v330, LR 1e-4) produced the **first-ever special-move top-1 greedy**:
  shoryuken-lp 52.8%, back 44.5%, forward 2.7%. BC prior successfully prevents
  action collapse; DQN amplifies positive-reward shoryuken and suppresses
  negative-reward fireball. Shoryuken concentration (52.8%) and fireball
  suppression (0%) need further balancing with better fireball data and/or
  entropy regularization. See engineering log 2026-05-03 entries for full details.
- [ ] Phase 4 defense data collected and M4 defense baseline trained.
- [ ] Phase 5 projectile timing data collected by visual cue, post-hoc bucketed
  by timing/recovery, and M5 projectile baseline trained.
- [ ] Phase 6 anti-air data collected, M5 jump-in guard regression checked, and
  M6 anti-air baseline trained.
- [ ] Phase 7 corner/pressure/oki data collected and M7 corner baseline trained.
- [ ] Phase 8 natural/on-policy integration logs collected and M8 integration
  baseline trained.
- [ ] final M8 regression report recorded before any live promotion.

### Milestone 6 Move-Family Validation Table

Use this table to keep early attack-validation passes stable and comparable.

Common setup:

- timing baseline: `4/3/3`
- learner command: keep the same `tools/rl_probe_server.py` command except for `--policy ...`
- reset / clear the transition log before each short policy pass when possible
- use a fixed opponent behavior for the pass:
  - preferred first pass: opponent steadily approaches the RL side
  - avoid mixing free-form CPU behavior and scripted approach behavior in the same comparison set
- keep run length short and repeatable:
  - target at least `rows >= 256`
  - target at least `done >= 2` when practical

| Policy | Opponent setup | RL prefix before attack | Primary question | Expected healthy log signals | Pass if | Notes to record |
| --- | --- | --- | --- | --- | --- | --- |
| `hp` | steady approach | none | do simple grounded attacks enter the attack path and produce plausible contact/whiff labels? | `policy=hp`, `policy_fallback_pct=0.00`, nonzero `atk`, nonzero `overlay_attack_event_finalized` | punches visibly occur and the attack-event counters/logs move in plausible proportion | note whether whiffs dominate because of spacing |
| `throw` | steady approach into close range | optional short walk-forward | do throw attempts produce distinct close-range behavior and avoid being mislabeled as generic strike contact? | `policy=throw`, low/no fallback, visible throw attempts, stable `policy_rows` growth | throw attempts are visibly present and logs do not look identical to plain `hp` behavior | record whether proximity is sufficient without extra walk-up prefix |
| `ryu-fireball` | steady approach | none | do projectile-style attacks keep plausible whiff/contact behavior at range? | `policy=ryu-fireball`, low/no fallback, repeated attack events, lower close-contact expectation than `hp` | fireballs visibly occur and attack-event counters grow without requiring close-range contact | note whether contact labels undercount projectile hits |
| `tatsu` | steady approach | none | do advancing specials preserve attack-event labeling while movement changes? | `policy=tatsu`, low/no fallback, repeated attack events, visible forward-moving special | tatsu visibly occurs and logs stay plausible despite movement during the move | note whether movement causes more whiff than expected |
| `shoryuken` | steady approach | none | do vertical / rising specials still produce plausible attack-event labels? | `policy=shoryuken`, low/no fallback, repeated attack events, visible rising special | shoryuken visibly occurs and attack-event counters remain plausible | note whether contact is undercounted because of fast state changes |

Per-pass record fields:

- date / build / run id
- policy
- opponent setup
- timing tuple
- rows / done
- `policy_rows`
- `policy_rew`
- `policy_fallback_pct`
- `atk`
- visible outcome summary:
  - attack visibly occurs?
  - contact observed?
  - whiff observed?
- pass / fail
- follow-up notes

## Biggest Risks

### 1. Build-layer mismatch

Risk:

- trying to "reuse netplay directly" on MiSTer will fail because those sources are not built there today

Mitigation:

- build RL bridge independently from netplay

### 2. Hot-path observation cost

Risk:

- large snapshot memcpys every frame waste MiSTer CPU time

Mitigation:

- direct compact observation builder
- debug snapshots only off the critical path

### 3. Delayed-action credit assignment

Risk:

- online RL learns the wrong mapping if action execution and reward attribution are misaligned

Mitigation:

- decision ledger
- explicit `decision_interval_frames`
- explicit `action_hold_frames`
- include pending queued actions in observation

### 4. Network and inference jitter

Risk:

- mean latency may look fine while p95/p99 breaks control

Mitigation:

- same-LAN first
- fixed `k`
- fallback action hold
- latency histograms from day one

### 5. Match-flow side effects

Risk:

- reusing `MODE_NETWORK` or a training mode blindly may trigger unexpected winner/menu/reset behavior

Mitigation:

- short mode spike before large implementation
- start with an RL session flag, not a new mode enum

### 6. Upstream P2P netplay churn

Risk:

- future upstream P2P netplay may rewrite `src/netplay/*`, `ENABLE_NETPLAY`, `MODE_NETWORK`, rollback/session setup, and netplay packet formats

Mitigation:

- keep remote RL agent code in `src/rl/*`
- treat the remote agent as a local input provider and observation exporter, not a netplay peer
- keep shared-file edits limited to small hook calls
- avoid direct dependencies from `src/rl/*` to upstream P2P netplay session state

## Recommended First Implementation Order

- [ ] Baseline `MODE_VERSUS + rl_session_active` confirmation spike
- [ ] Facing/remap validation micro-spike
- [ ] Local scripted input override for one player
- [ ] AI-vs-CPU setup helper and reliable reset path
- [ ] Compact observation builder
- [ ] Session hello/ack plus network probe and delay budgeting
- [ ] UDP receive/send and target-frame queue
- [ ] Remote rule-based server
- [ ] Decision ledger and transition log
- [ ] Real learner and model hot-swap

## One-Sentence Conclusion

The right architecture is to keep MiSTer as the only authoritative simulator, add a new RL bridge independent from netplay, inject scheduled wire actions at the input-buffer layer with MiSTer remapping relative movement into raw directional `SWKey` bits at execution time, send compact live-state observations instead of full snapshots, and treat delayed execution as a first-class scheduling and RL transition-alignment problem from the start.
