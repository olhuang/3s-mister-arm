# Remote RL Training Mode Demo Log Plan

Date: 2026-05-01

## Goal

Use training mode as a general controlled-scenario transition data source.
The first supported workflow is:

- human controls the agent side
- the built-in training dummy / CPU controls the opponent side
- the RL bridge records transition rows
- no remote DQN action override is applied in training mode

Projectile defense is the first target use case, but this must stay generic
enough for later character-specific move, anti-air, punish, guard, throw, and
dummy record/replay data collection.

## Design

### Runtime gating

Keep remote gameplay input override VS-only. Add a separate demo-recording gate
that allows local demo rows in training mode when gameplay is live:

- RL session enabled
- `mpp_w.inGame`
- `Game_pause == 0`
- `Allow_a_battle_f != 0`
- `Demo_Time_Stop == 0`
- `Mode_Type == MODE_VERSUS` or `Is_Training_Mode(Mode_Type)`

This keeps training mode in "recording" mode, not "autopilot" mode.

### Episode boundaries

Training mode has no normal round/match lifecycle. For the first version,
episode segmentation should come from the existing runtime lifecycle:

- start an episode when training gameplay becomes recordable
- finalize the episode when gameplay leaves the recordable state
- reset the RL runtime on pause, menu, training reset, character change, or mode
  exit

The existing `run_id` and `episode_id` remain the primary grouping keys.
Training rows also carry mode metadata so analyzers and trainers do not have to
infer training data from `round_num`.

### Transition metadata

Add transition metadata:

- `mode_type`: numeric `Mode_Type`
- `play_mode`: numeric `Play_Mode`

Transition schema v6 is schema v5 plus these mode fields. Python tooling should
accept both schema v5 and v6 so older V52/V53/V54 logs remain trainable.

### Reward and HP delta handling

Do not make C-side transition logging projectile-specific. C-side rows should
record observed deltas and action/context fields.

Training mode can auto-recover HP. That may create negative HP deltas in the
log. For analysis this raw signal is useful, so do not destroy it at capture
time. Trainer/analyzer tooling should provide an opt-in mode that treats
training-mode HP deltas as damage-only:

```text
sanitized_self_delta = max(0, delta_self_hp)
sanitized_opp_delta  = max(0, delta_opp_hp)
sanitized_reward     = sanitized_opp_delta - sanitized_self_delta
```

The default remains raw HP delta until real training logs confirm the pattern.

## Validation

Local validation:

- compile the changed C files
- run Python syntax checks for RL tools
- run analyzer/trainer smoke tests against existing schema-v5 logs to verify
  backward compatibility

Hardware validation:

- run training mode with `rl-control-source = human-demo`
- use a probe server with action output disabled and transition logging enabled
- confirm rows upload with `execution_source=4`, `mode_type=3` or `4`, and
  `transition_schema_version=6`
- inspect HP delta sign counts before enabling damage-only training

## First Collection Use

For projectile defense data:

- P1 or configured agent side: human controlled
- dummy side: CPU or training dummy fireball setup
- probe server: transition log enabled, action mode off
- trainer: include only the filtered rows needed for the current curriculum
  and enable training-mode damage-only HP deltas only after log analysis
