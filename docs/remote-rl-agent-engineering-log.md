# Remote RL Agent Engineering Log

This log tracks implementation progress, engineering decisions, test results, and open issues for the remote RL agent work.

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

Last updated: 2026-04-21

- [x] Milestone 0A: Baseline match-flow confirmation spike
- [ ] Milestone 0B: Facing and remap validation micro-spike
- [ ] Milestone 0C: Local fake agent spike
- [ ] Milestone 1: Compact observation builder
- [ ] Milestone 2: Session handshake, network probe, and delay budget
- [ ] Milestone 3: Remote inference only
- [ ] Milestone 4: Decision ledger and transition logging
- [ ] Milestone 5: Async learner and model hot-swap
- [ ] Milestone 6: Higher-control-rate policy and curriculum

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

- TBD

Validation notes:

- TBD

Open questions:

- exact debug visualization or logging path for `rl_flag`
- exact forced side-switch scenario for delayed action validation

### Milestone 0C: Local Fake Agent Spike

Objective:

- verify local scripted input override before networking

Implementation notes:

- TBD

Validation notes:

- TBD

Open questions:

- whether to start with compile-time debug toggle, config flag, or CLI flag

### Milestone 1: Compact Observation Builder

Objective:

- build and validate `RLObservationV1`

Implementation notes:

- TBD

Validation notes:

- TBD

Open questions:

- exact first playable frame for `round_start_hp[i]` capture
- final local debug output format

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

## Test And Build Records

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

- [ ] Confirm exact `MODE_VERSUS + rl_session_active` setup hook
- [ ] Confirm `rl_flag` mapping with runtime observation
- [ ] Confirm first playable frame for `round_start_hp[i]`
- [ ] Choose `config_hash` algorithm
- [ ] Choose remote heuristic server location
- [ ] Choose transition log format

## Closed Issues

- None yet.
