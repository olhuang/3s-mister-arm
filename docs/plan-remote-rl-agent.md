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
  - `Win_Record[2]`
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
- super uses `plw[i].sa->store / plw[i].sa->store_max`
  - `spg_dat` is a useful debug cross-check, but not the canonical gameplay source
- stun uses `sdat[i].cstn / plw[i].py->genkai`
  - `sdat[i].slen` is UI gauge length and should not be used as the normalization base
- facing uses derived relative features from `plw[i].wu.rl_flag`, not raw left/right button semantics
  - map `rl_flag == 0` to `+1` / facing world-right
  - map `rl_flag == 1` to `-1` / facing world-left
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
| `self_super_ratio` | `f32` | `plw[self].sa->store / plw[self].sa->store_max` clamped to `[0, 1]` | `plw[self].sa->store`, `plw[self].sa->store_max` | No |
| `opp_super_ratio` | `f32` | `plw[opp].sa->store / plw[opp].sa->store_max` clamped to `[0, 1]` | `plw[opp].sa->store`, `plw[opp].sa->store_max` | No |
| `self_stun_ratio` | `f32` | `sdat[self].cstn / plw[self].py->genkai` clamped to `[0, 1]` | `sdat[self].cstn`, `plw[self].py->genkai` | No |
| `opp_stun_ratio` | `f32` | `sdat[opp].cstn / plw[opp].py->genkai` clamped to `[0, 1]` | `sdat[opp].cstn`, `plw[opp].py->genkai` | No |
| `opp_dx_ratio` | `f32` | `(plw[opp].wu.position_x - plw[self].wu.position_x) / max(1, scrr - scrl)` | `plw[*].wu.position_x`, `scrl`, `scrr` | Yes |
| `opp_dy_ratio` | `f32` | `(plw[opp].wu.position_y - plw[self].wu.position_y) / max(1, scrr - scrl)` | `plw[*].wu.position_y`, `scrl`, `scrr` | Yes |
| `self_left_corner_ratio` | `f32` | `(plw[self].wu.position_x - scrl) / max(1, scrr - scrl)` | `plw[self].wu.position_x`, `scrl`, `scrr` | No |
| `self_right_corner_ratio` | `f32` | `(scrr - plw[self].wu.position_x) / max(1, scrr - scrl)` | `plw[self].wu.position_x`, `scrl`, `scrr` | No |
| `opp_left_corner_ratio` | `f32` | `(plw[opp].wu.position_x - scrl) / max(1, scrr - scrl)` | `plw[opp].wu.position_x`, `scrl`, `scrr` | No |
| `opp_right_corner_ratio` | `f32` | `(scrr - plw[opp].wu.position_x) / max(1, scrr - scrl)` | `plw[opp].wu.position_x`, `scrl`, `scrr` | No |
| `self_facing_sign` | `s8` | `+1` when `plw[self].wu.rl_flag == 0`, `-1` when `rl_flag == 1` | `plw[self].wu.rl_flag` | Yes |
| `opp_in_front` | `u8` | `1` if opponent is in the controlled player's forward direction, else `0` | `plw[self].wu.rl_flag`, `plw[*].wu.position_x` | Yes |
| `self_guard_flag` | `u8` | raw boolean / categorical as-is | `plw[self].guard_flag` | No |
| `opp_guard_flag` | `u8` | raw boolean / categorical as-is | `plw[opp].guard_flag` | No |
| `self_current_attack` | `u16` | raw categorical id, embedded or one-hot on remote side | `plw[self].current_attack` | No |
| `opp_current_attack` | `u16` | raw categorical id, embedded or one-hot on remote side | `plw[opp].current_attack` | No |
| `self_do_not_move` | `u8` | raw boolean | `plw[self].do_not_move` | No |
| `opp_do_not_move` | `u8` | raw boolean | `plw[opp].do_not_move` | No |
| `self_hit_stop` | `u8` | `1` if `plw[self].wu.hit_stop != 0`, else `0` | `plw[self].wu.hit_stop` | No |
| `opp_hit_stop` | `u8` | `1` if `plw[opp].wu.hit_stop != 0`, else `0` | `plw[opp].wu.hit_stop` | No |
| `self_high_jump_flag` | `u8` | raw boolean | `plw[self].high_jump_flag` | No |
| `opp_high_jump_flag` | `u8` | raw boolean | `plw[opp].high_jump_flag` | No |
| `self_routine_0` | `u16` | raw categorical id | `plw[self].wu.routine_no[0]` | No |
| `self_routine_1` | `u16` | raw categorical id | `plw[self].wu.routine_no[1]` | No |
| `self_routine_2` | `u16` | raw categorical id | `plw[self].wu.routine_no[2]` | No |
| `opp_routine_0` | `u16` | raw categorical id | `plw[opp].wu.routine_no[0]` | No |
| `opp_routine_1` | `u16` | raw categorical id | `plw[opp].wu.routine_no[1]` | No |
| `opp_routine_2` | `u16` | raw categorical id | `plw[opp].wu.routine_no[2]` | No |
| `round_num` | `u8` | raw categorical round index | `Round_num` | No |
| `self_round_wins` | `u8` | raw count | `Win_Record[self]` | No |
| `opp_round_wins` | `u8` | raw count | `Win_Record[opp]` | No |
| `last_executed_move_intent` | `u8` | relative-direction wire enum from the last action that actually executed | RL session state | Yes |
| `last_executed_attack_bits` | `u16` | attack/button bits from the last action that actually executed | RL session state | No |
| `next_scheduled_move_intent` | `u8` | relative-direction wire enum for the next queued action | pending action queue | Yes |
| `next_scheduled_attack_bits` | `u16` | attack/button bits for the next queued action | pending action queue | No |
| `frames_until_next_action` | `u8` | unsigned frame countdown; `255` means no queued next action | pending action queue, current frame id | Yes |

Notes:

- `self` / `opp` are always from the controlled agent's perspective, not player-1/player-2 fixed slots
- if `frames_until_next_action == 255`, set `next_scheduled_move_intent = RL_MOVE_NEUTRAL` and `next_scheduled_attack_bits = 0`
- `opp_dy_ratio` intentionally uses the same stage-width denominator as `opp_dx_ratio` in v1 as a pragmatic scale; a later version can switch to a fixed vertical scale or jump-range-based scale with a protocol version bump
- if a source field is later found to be unavailable or unstable in one build target, the replacement must preserve the same logical meaning and require a version bump if that meaning changes
- if the wire payload later switches to quantized integers instead of `f32`, the logical schema above still remains the canonical contract

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
- MiSTer accepts only wire actions on the protocol boundary
- MiSTer does not own high-level macro expansion
- MiSTer may remap the relative-direction subfield into raw `SWKey` directions at execution time
- MiSTer may still apply minimal legality cleanup at the input-buffer edge

Canonical v1 rule:

- the packet received by MiSTer should already contain the final wire action intended for execution
- semantic-to-wire translation belongs on the remote side, not in the MiSTer runtime
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
- if `ActionPacket.target_frame` does not match the ledger entry for `(episode_id, decision_id)`, MiSTer treats it as a protocol error
- if `RLSessionAck.accepted_config_hash` does not match `RLSessionHello.config_hash`, MiSTer treats the session setup as rejected

## Observation packet

```c
typedef struct RLObsHeader {
    uint32_t magic;
    uint16_t version;
    uint16_t flags;
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
    uint16_t flags;
    uint32_t episode_id;
    uint32_t decision_id;
    uint32_t target_frame;
    uint16_t action_wire;
    uint16_t reserved;
    uint32_t model_version;
} RLActionPacket;
```

In v1, `action_wire` means:

- relative movement subfield
- final attack/button bits
- no high-level macro payload
- no implicit absolute `LEFT` / `RIGHT` `SWKey` unless an explicit absolute-action compatibility mode is negotiated

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
- the agent still sees match-level context through round-win features in the next round's initial observation

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
- [ ] Milestone 0B: Facing and remap validation micro-spike
- [ ] Milestone 0C: Local fake agent spike
- [ ] Milestone 1: Compact observation builder
- [ ] Milestone 2: Session handshake, network probe, and delay budget
- [ ] Milestone 3: Remote inference only
- [ ] Milestone 4: Decision ledger and transition logging
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

- [ ] Milestone complete

Goal:

- [ ] Verify the `rl_flag` facing contract before building the rest of the relative-direction stack

Tasks:

- [ ] Add a temporary RL validation path that can keep the non-agent side on human input for deterministic facing/remap testing
- [ ] Expose concise RL debug overlay state such as `P1C`, `P1H`, `P2C`, and `P2H` so the current routing is visible during spot checks
- [ ] Add a fixed RL movement validation selector for `forward`, `back`, `jump-forward`, and `down-back`
- [ ] Verify `plw[i].wu.rl_flag == 0` means facing world-right and maps to `self_facing_sign = +1`
- [ ] Verify `plw[i].wu.rl_flag == 1` means facing world-left and maps to `self_facing_sign = -1`
- [ ] Verify `opp_in_front` matches on-screen relative positioning across side switches
- [ ] Verify `RL_MOVE_FORWARD` remaps to the correct raw `SWKey` direction bits immediately before input latch
- [ ] Verify `RL_MOVE_BACK` remaps to the correct raw `SWKey` direction bits immediately before input latch
- [ ] Verify a delayed relative action still moves in the intended direction if characters switch sides between `obs_frame` and `target_frame`
- [ ] Verify `down_back_static` fallback uses the same remap logic
- [ ] Verify `down_back_when_movable` fallback uses the same remap logic

Done when:

- [ ] Facing signs match observed character facing on both sides
- [ ] Forward/back remapping is correct before and after side switches
- [ ] Delayed execution does not invert intended forward/back movement
- [ ] Fallback directional actions use the same verified remap path

### Milestone 0C: Local fake agent spike

Status:

- [ ] Milestone complete

Goal:

- [ ] Prove AI-vs-CPU control and reset behavior without networking

Tasks:

- [ ] Add a local scripted override path that writes scheduled actions into the chosen player's raw input buffer
- [ ] Confirm `wk->wu.operator` split behaves correctly
- [ ] Confirm the non-agent side still runs `cpu_algorithm()`
- [ ] Confirm action hold behavior locally
- [ ] Confirm local reset behavior clears stale scheduled actions

Done when:

- [ ] The agent-controlled side can move and attack
- [ ] The CPU side still fights normally
- [ ] No menu or round-flow regressions are observed

### Milestone 1: Compact observation builder

Status:

- [ ] Milestone complete

Goal:

- [ ] Build and print/log `RLObservationV1` locally

Tasks:

- [ ] Add end-of-frame observation hook after `hit_check_main_process()`
- [ ] Capture `round_start_hp[i]` at the defined playable-round boundary
- [ ] Build all fixed `RLObservationV1` fields from the schema table
- [ ] Serialize compact observations to a local file or debug print
- [ ] Validate positions against on-screen movement
- [ ] Validate HP, super, stun, attack state, guard state, and round state against gameplay
- [ ] Validate `last_executed_*`, `next_scheduled_*`, and `frames_until_next_action`
- [ ] Measure observation build cost on MiSTer or the closest available target

Done when:

- [ ] Observation fields match visible gameplay and expected internal state
- [ ] Observation action-context fields use relative move intent plus attack bits, not raw absolute direction masks
- [ ] Observation build cost is acceptable on MiSTer

### Milestone 2: Session handshake, network probe, and delay budget

Status:

- [ ] Milestone complete

Goal:

- [ ] Agree on session config and measure the real transport envelope before choosing final control timing

Tasks:

- [ ] Add `RLSessionHello`
- [ ] Add `RLSessionAck`
- [ ] Add `config_hash` generation and validation
- [ ] Reject mismatched protocol versions
- [ ] Reject mismatched observation schema versions
- [ ] Reject unsupported action encoding modes
- [ ] Reject unsupported timing configs
- [ ] Reject unsupported feature flags
- [ ] Add a minimal ping/pong packet path between MiSTer and the remote PC
- [ ] Measure RTT
- [ ] Measure jitter
- [ ] Measure p50 latency
- [ ] Measure p95 latency
- [ ] Measure p99 latency
- [ ] Choose `k` from measured data
- [ ] Choose `decision_interval_frames` from measured data
- [ ] Choose `action_hold_frames` from measured data

Done when:

- [ ] Remote inference does not accept actions until hello/ack config is accepted
- [ ] MiSTer rejects actions from unacknowledged or stale `session_nonce`
- [ ] Transport timing is measured on the actual target network
- [ ] Delay knobs are chosen from data, not guesses

### Milestone 3: Remote inference only

Status:

- [ ] Milestone complete

Goal:

- [ ] Connect MiSTer to a remote rule-based or heuristic server

Tasks:

- [ ] Add non-blocking UDP socket setup
- [ ] Add `ObsPacket` send path on decision frames
- [ ] Add `ActionPacket` receive path
- [ ] Add pending action queue keyed by `target_frame`
- [ ] Validate `(episode_id, decision_id, target_frame)` duplicate rules
- [ ] Reject `ActionPacket.target_frame` mismatches against the ledger
- [ ] Add default fallback mode using `action_hold_frames`
- [ ] Add telemetry counters for packet miss, late packet, duplicate packet, and fallback usage
- [ ] Start with fixed measured `k`
- [ ] Implement a remote rule-based or heuristic server

Done when:

- [ ] Stable packet flow is observed
- [ ] Actions execute on their intended target frames
- [ ] Side-switch delayed actions keep correct relative direction
- [ ] No gameplay stalls occur when packets drop

### Milestone 4: Decision ledger and transition logging

Status:

- [ ] Milestone complete

Goal:

- [ ] Make the environment actually trainable

Tasks:

- [ ] Add decision ledger keyed by `(episode_id, decision_id)`
- [ ] Record `obs_frame`
- [ ] Record `target_frame`
- [ ] Record `requested_action_wire`
- [ ] Record `executed_action_wire`
- [ ] Record `execution_frame_actual`
- [ ] Record `execution_source`
- [ ] Accumulate reward over the executed decision interval
- [ ] Align done flags with round-scoped episode boundaries
- [ ] Export transitions to the remote learner path
- [ ] Decode `executed_action_wire` into `executed_move_intent` and `executed_attack_bits` in logs

Done when:

- [ ] Each transition includes episode id
- [ ] Each transition includes decision id
- [ ] Each transition includes observation frame
- [ ] Each transition includes target frame
- [ ] Each transition includes requested action wire
- [ ] Each transition includes executed action wire
- [ ] Each transition includes execution frame actual
- [ ] Each transition includes reward span
- [ ] Each transition includes done flag
- [ ] Learner-side replay buffer can distinguish remote action, repeated-last-action, down-back fallback, and neutral fallback

### Milestone 5: Async learner and model hot-swap

Status:

- [ ] Milestone complete

Goal:

- [ ] Train online without stalling gameplay

Tasks:

- [ ] Split inference and learner services
- [ ] Keep training work off the critical action path
- [ ] Publish versioned actor weights
- [ ] Atomically hot-swap actor weights
- [ ] Include `model_version_current` in session ack or telemetry
- [ ] Include model version in action/transition logs
- [ ] Track inference latency while training is active

Done when:

- [ ] Action latency stays stable during training
- [ ] Model version changes are visible in logs and packets
- [ ] Inference continues to respond while learner updates weights

### Milestone 6: Higher-control-rate policy and curriculum

Status:

- [ ] Milestone complete

Goal:

- [ ] Improve fighting strength after the transport/control path is proven

Tasks:

- [ ] Tune `k`
- [ ] Tune `decision_interval_frames`
- [ ] Tune `action_hold_frames`
- [ ] Expand observation features only with schema versioning
- [ ] Expand reward features only after baseline reward is stable
- [ ] Add character curriculum
- [ ] Add stage curriculum
- [ ] Add automated reset loops
- [ ] Evaluate higher control rate after latency p95/p99 is stable

Done when:

- [ ] Control timing improvements are backed by telemetry
- [ ] Curriculum changes are reflected in logs and reproducible configs
- [ ] Policy strength improves without destabilizing the transport/control path

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
