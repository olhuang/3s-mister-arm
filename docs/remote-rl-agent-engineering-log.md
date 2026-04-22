# Remote RL Agent Engineering Log

This log tracks implementation progress, engineering decisions, test results, and open issues for the remote RL agent work.

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
- keep Milestone 2 open until stale/unacknowledged action rejection rules are fully wired into the later action path
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

Last updated: 2026-04-22

- [x] Milestone 0A: Baseline match-flow confirmation spike
- [x] Milestone 0B: Facing and remap validation micro-spike
- [x] Milestone 0C: Local fake agent spike
- [x] Milestone 1: Compact observation builder
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
