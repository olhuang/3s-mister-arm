# RL Policy Action Taxonomy

This document defines a stable first-pass policy action namespace for SF3 remote RL
agents. It is a registry, not a live action-set change. The live learner should
still enable only small curriculum subsets until each macro is validated on
MiSTer.

## Scope

This registry covers:

- universal controls, normals, defense, movement, throws, taunt, and recovery
- command-recognized character actions from `cmd_data.c`
- source dispatch metadata from `plpatXX.c`
- macro templates that the probe server can later expand into relative wire
  inputs

Character rows now include a `move_name` display alias for readable analysis.
The source handlers remain the executable source of truth because many handlers
are generic names such as `Att_HADOUKEN` even when the player-facing move name
differs by character. Target combos and detailed normal attack chains still need
a separate attack table pass before they are treated as individual policy
actions.

## ID Scheme

Universal policy actions use IDs below `1000`.

Character command actions use:

```text
policy_action_id = 1000 + character_id * 100 + source_command_slot
```

The source character IDs used by this repo are:

| character_id | character |
|---:|---|
| 0 | Gill |
| 1 | Alex |
| 2 | Ryu |
| 3 | Yun |
| 4 | Dudley |
| 5 | Necro |
| 6 | Hugo |
| 7 | Ibuki |
| 8 | Elena |
| 9 | Oro |
| 10 | Yang |
| 11 | Ken |
| 12 | Sean |
| 13 | Urien |
| 14 | Akuma |
| 15 | Chun-Li |
| 16 | Makoto |
| 17 | Q |
| 18 | Twelve |
| 19 | Remy |

## Engine Move Attribution Method

The policy namespace and the SF3 engine state are intentionally separate. In
transition schema v3 there are three non-overlapping action-label families:

- `policy_*` describes the remote RL/DQN/tabular policy request and execution.
  Demo rows should leave this family empty because no remote policy selected
  the move.
- `input_*` describes the best-effort label derived from local human-demo or
  CPU-demo controller input. Use this for walk, back, guard intent, and simple
  input-derived normals when no engine move start is observed.
- `engine_*` describes what the game actually entered after command
  recognition, using runtime attack identity fields. Use this for CPU-demo /
  human-demo move labels and accidental-command diagnosis.

Current runtime identity fields:

| shorthand | source meaning | current use |
|---|---|---|
| `R2` | `routine_no[2]` | primary active move / routine id |
| `KW` | `kind_of_waza` | strength and punch/kick class |
| `AK` | `current_attack` | normal button identity; not reliable for specials |
| `RS` | attack routine start event | attribution timing hint; not a move id |

### Transition Schema V3 Rollout Plan

Status: strict rollout implemented as of 2026-04-29. All legacy logs have been
cleared, so schema v3 intentionally removed compatibility fields instead of
adding another migration layer.

The goal of transition schema v3 is to make action labels unambiguous:

- policy intent/execution: what the remote actor requested and what the bridge
  executed.
- input label: what the local controller / CPU-demo input looked like.
- engine attribution: what the SF3 engine actually recognized as a move start.

Schema v3 rows must carry `transition_schema_version: 3`. Python training and
analysis tools should reject schema 1/2 or missing-version rows instead of
guessing a legacy meaning.

Field groups:

| group | fields | meaning |
|---|---|---|
| policy | `policy_requested_action_id`, `policy_requested_sub_action_id`, `policy_requested_action_step`, `policy_executed_action_id`, `policy_executed_sub_action_id`, `policy_executed_action_step` | Remote RL/DQN action identity only. In `human-demo` / `cpu-demo` rows these should normally be zero because no remote policy selected the action. |
| input | `input_action_id`, `input_sub_action_id`, `input_action_step`, `input_label_source` | Best-effort label derived from raw controller input. This is useful for walk, guard intent, and simple button inputs in human-demo / CPU-demo data. |
| engine | `engine_action_id`, `engine_sub_action_id`, `engine_routine_1`, `engine_routine_2`, `engine_kind_of_waza`, `engine_current_attack`, `engine_label_source`, `engine_lag_frames` | Engine-recognized action start label. This is the preferred demo label for specials, throws, and validated normals when an engine event is observed. |

Removed schema-v2 compatibility fields:

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

Label source values in step 1:

| field | value | meaning |
|---|---:|---|
| `input_label_source` | 0 | no input label |
| `input_label_source` | 1 | existing human-demo / CPU-demo input mapper |
| `engine_label_source` | 0 | no engine attribution |
| `engine_label_source` | 1 | Ryu engine routine start attribution |
| `engine_label_source` | 2 | Ryu engine normal attack start attribution |

Important semantic split:

- `engine_*` means "the game entered a recognizable move start near this
  decision row."
- It does not mean "the character is currently in this state on every frame."
- If a future analyzer needs per-row engine state, add a separate
  `obs_self_engine_state_*` family instead of reusing `engine_*`.

Rollout steps:

1. C-side NDJSON export:
   - bump `RL_TRANSITION_SCHEMA_VERSION` to `3`.
   - remove legacy `requested_*`, `executed_*`, and `demo_attributed_*` JSON
     fields.
   - remote RL rows fill `policy_*`.
   - demo rows fill `input_*` from the existing demo input mapper.
   - demo engine attribution fills `engine_*` from the existing Ryu
     `R2/KW/AK` attribution path.

2. Python replay ingestion:
   - require `transition_schema_version == 3`.
   - preserve only v3 action-label groups.
   - fail fast on schema 1/2 or missing-version rows.

3. Training / analyzer / compare source selection:
   - default `auto` behavior:
     - demo row with `engine_*`: train/analyze engine action.
     - demo row without `engine_*` but with `input_*`: train/analyze input
       action.
     - remote row with `policy_executed_*`: train/analyze policy action.
   - explicit source modes stay available for diagnostics:
     `auto|policy|input|engine|prefer-engine`.
   - source breakdown should report only `policy`, `input`, `engine`, and
     `none`.

4. Validation:
   - collect fresh CPU-demo and human-demo v3 logs.
   - confirm demo logs have `policy_* == 0`.
   - confirm CPU-demo fireball / shoryuken / tatsu rows train from `engine_*`.
   - confirm walk / guard samples train from `input_*` when no engine
     attribution exists.
   - run a short DQN smoke test on one v3 CPU-demo log.

### Transition Schema V4 / Action Set V5 Jump Split

Status: implemented as of 2026-05-01 for the next split-taxonomy logs and
models. V40 and older action-set-v4 models remain schema-v3 actors and should
not be warm-started into this action set.

The schema-v4 change keeps the v3 `policy_*`, `input_*`, and `engine_*`
families, but fixes the jump namespace:

- `RL_POLICY_ACTION_JUMP` (`3`) now represents only starting a jump from a
  ground action-start state. The direction comes from sub-actions
  `up_forward`, `neutral_direction`, or `up_back`, and maps to
  `jump-forward-start`, `jump-neutral-start`, or `jump-back-start`.
- `RL_POLICY_ACTION_AIR_NORMAL` (`16`) represents airborne button normals. The
  button comes from `lp/mp/hp/lk/mk/hk` sub-actions and maps to `air-lp` through
  `air-hk`.
- legacy `jump_attack_forward` / `jump_attack_neutral` / `jump_attack_back`
  ids (`12..14`) are kept reserved for old schema-v3/action-set-v4 logs but are
  not emitted for new schema-v4 rows.

Schema-v4 rows add these observation fields:

| field | meaning |
|---|---|
| `obs_self_airborne` | whether the self player is airborne in the sampled observation |
| `obs_self_jump_phase` | compact jump phase: none, jump-ready, ordinary jump-air, or other airborne |
| `obs_self_ground_action_start_allowed` | ground action families can start now |
| `obs_self_jump_start_allowed` | jump-start actions can start now |
| `obs_self_air_attack_allowed` | `air-*` button normals can start now |

Probe/trainer/analyzer code should use the schema-backed helper semantics:

- ground action-start rows can train/rank ground actions plus
  `jump-*-start`, not `air-*`.
- ordinary jump-air rows can train/rank `air-*`, not ground actions or
  `jump-*-start`.
- locked/recovery/contact/damage rows should not create new attack/jump-start
  targets; live inference may still keep movement/guard hold candidates as a
  conservative fallback.

### Routine Number Dispatch Source Map

Do not interpret `R2` without `R1`. The stable engine-state key is at least
`routine_no[1] + routine_no[2]`; attack extras also need `character_id`.

Primary dispatch path:

| source file / symbol | role |
|---|---|
| `src/sf33rd/Source/Game/engine/plmain.c::plmain_lv_02` | `routine_no[1]` high-level player state dispatch |
| `src/sf33rd/Source/Game/engine/plpnm.c::Player_normal` | `R1=0`; dispatches `plpnm_lv_00[routine_no[2]]` for ordinary movement / guard / jump / crouch states |
| `src/sf33rd/Source/Game/engine/plpat.c::Player_attack` | `R1=4`; if `R2 > 15`, dispatches the character extra table; otherwise dispatches common `plpat_lv_00[R2]` |
| `src/sf33rd/Source/Game/engine/pls03.c::hissatsu_setup_union` | command/special setup path; writes `routine_no[1]=4`, `routine_no[2]=rno` |
| `src/sf33rd/Source/Game/engine/pls03.c::set_attack_routine_number` | normal/attack setup path; writes `routine_no[1]=4`, `routine_no[2]=wk->as->r_no` |

Known `R1` categories from `plmain_lv_02`:

| R1 | engine dispatcher | current analyzer meaning |
|---:|---|---|
| 0 | `Player_normal` | ordinary states: stand, walk, dash, crouch, jump, guard, landing / misc normal motions |
| 1 | `Player_damage` | damage / contact reaction; includes hit and block/guard reaction states |
| 2 | `Player_catch` | active catch / grab-side state |
| 3 | `Player_caught` | caught / grabbed-side state |
| 4 | `Player_attack` | normal/common attacks plus character-specific specials, throws, supers, and extra actions |

For `R1=4`, `R2` is split by `Player_attack`:

| R2 range | source dispatch | mapping rule |
|---|---|---|
| `0..15` | `plpat.c::plpat_lv_00[R2]` | common attack routines; combine with `KW` / `AK` and visible validation |
| `>=16` | `plpat.c::plxx_extra_attack_table[player_number]` | character-specific extra table; combine `character_id + R2 + KW` |

For `R1=0`, ordinary state mapping currently comes from `pls01.c` setters plus
`plpnm.c::plpnm_lv_00`. These labels are analyzer aids and must be validated
with fresh logs before they become learner targets:

| R1 | R2 | provisional analyzer label | source evidence |
|---:|---:|---|---|
| 0 | 1 | `normal.stand` | `check_walking_lv_dir` falls back to `R2=1` when standing |
| 0 | 2 | `normal.turn-stand` | `check_turn_to_back` sets `R2=2` when not crouching |
| 0 | 3 | `normal.walk-forward` | `check_F_R_walk`, `lever_dir=1` |
| 0 | 4 | `normal.walk-back` | `check_F_R_walk`, `lever_dir=2` |
| 0 | 5 | `normal.dash-forward` | `check_F_R_dash`, forward dash branch |
| 0 | 6 | `normal.dash-back` | `check_F_R_dash`, back dash branch |
| 0 | 7 | `normal.stand-up` | `check_stand_up` |
| 0 | 8 | `normal.crouch-start` | `check_bend_myself` |
| 0 | 9 | `normal.crouch` | `check_walking_lv_dir` falls back to `R2=9` when crouched |
| 0 | 10 | `normal.turn-crouch` | `check_turn_to_back` sets `R2=10` while crouching |
| 0 | 11 | `normal.walk-forward-arcade` | `check_arcade_walk_start`, forward branch |
| 0 | 12 | `normal.walk-back-arcade` | `check_arcade_walk_start`, back branch |
| 0 | 16 | `normal.jump-ready` | `check_jump_ready` regular jump branch |
| 0 | 17 | `normal.high-jump-ready` | `check_jump_ready` / `check_hijump_only` high-jump branch |
| 0 | 18..26 | `normal.jump-air` | `plpnm_lv_00` routes these entries through `Normal_18000` jump-air handling |
| 0 | 27 | `normal.guard-stand-provisional` | `check_defense_lever`; non-crouch guard branch when `check_attbox_dir` is false |
| 0 | 28 | `normal.guard-stand-provisional` | `check_defense_lever`; non-crouch guard branch when `check_attbox_dir` is true |
| 0 | 29 | `normal.guard-crouch-provisional` | `check_defense_lever`; down input branch |
| 0 | 31..33 | `normal.guard-block-provisional` | `plpnm_lv_00` routes these entries through `Normal_31000`; validate exact block types |

### Ryu R1/R2 Decoder Source Trace

Ryu's character id is `2`. Under `R1=4`, `Player_attack` calls
`plxx_extra_attack_table[player_number]` when `R2 > 15`; for Ryu this reaches
`src/sf33rd/Source/Game/engine/plpat02.c::pl02_extra_attack`, which dispatches
`pl02_exatt_table[R2 - 16]`.

Ryu source-backed attack mapping:

| R1 | R2 | source handler | policy action | KW/sub-action logic | status |
|---:|---:|---|---|---|---|
| 4 | 16 | `Att_HADOUKEN` | 1229 Hadouken | `08/0A/0C` => `lp/mp/hp` | overlay-confirmed for regular Hadouken |
| 4 | 17 | `Att_SHOURYUUKEN` | 1228 Shoryuken | `08/0A/0C` => `lp/mp/hp` | overlay-confirmed for regular Shoryuken |
| 4 | 18 | `Att_SENPUUKYAKU` | 1230 Tatsumaki Senpukyaku | `09/0B/0D` => `lk/mk/hk` | overlay-confirmed for regular Tatsumaki |
| 4 | 19 | `Att_HADOUKEN` | 1220 Shinkuu Hadouken | super-art `KW` still TBD | source-backed, overlay not fully validated |
| 4 | 20 | `Att_SHINSHOURYUUKEN` | 1222 Shin Shoryuken | super-art `KW` still TBD | source-backed, overlay not fully validated |
| 4 | 21 | `Att_DENJINHADOUKEN` | 1221 Denjin Hadouken | super-art `KW` still TBD | source-backed, overlay not fully validated |
| 4 | 22 | `Att_KUUCHUUNICHIRINSHOU` | 1246 Air Tatsumaki Senpukyaku | likely `09/0B/0D`, verify | source-backed, overlay not fully validated |
| 4 | 23 | `Att_SLIDE_and_JUMP` | 1231 Joudan Sokutou Geri | likely kick-special `KW`, verify | source-backed, overlay not fully validated |
| 4 | 2 | common `plpat_lv_00[2]` / `Attack_02000` | air-MP continuation / Ryu MP branch | Ryu `asstbl_lv_0010[_arcade][Ryu][MP][2]` => `.r_no=2`, `.char_ix=5`, `.data_ix=21` | live-observed as Ryu air-MP follow-up damage; do not classify as throw |
| 4 | 14 | common `plpat_lv_00[14]` / catch path | universal throw | direction from input row only | source table throw startup path |
| 4 | 15 | common `plpat_lv_00[15]` / catch path | universal throw | direction from input row only | source table alternate throw startup path |

Ryu `R1=4/R2=2` correction:

- Source trace: `check_nm_attack()` selects `asstbl_lv_0010[_arcade]` for
  standing normals; for Ryu `MP`, selector `waza_select(..., sf=0)` can choose
  `koa=2` when `decode_wst_data()` sees `0x4004`, i.e. a new normalized
  forward input. That table entry is `.r_no=2`, so `set_attack_routine_number()`
  writes `routine_no[1]=4`, `routine_no[2]=2`.
- Live Ryu-vs-Ryu MP-only validation later showed this state can also appear
  as the grounded follow-up / continuation window after `air-mp`, where the
  same visible air-MP causes two separate HP/stun deltas. Combat attribution
  should attach that damage to `air-mp` / MP continuation semantics, not emit a
  throw or a standalone throw result.
- Throw startup for Ryu is `R1=4/R2=14` or `R1=4/R2=15`; successful throw
  ownership is better validated from `Player_catch` (`R1=2`) and
  `Player_caught` (`R1=3`) / catch flags, not from `R2=2`.

Ken check:

- Ken command/special routines still use the command rows below.
- A source-table pass over Ken's normal AS tables
  (`asstbl_lv_0010/1010/2010/3010/4010[_arcade]`) found no Ken normal entry
  with `.r_no=2`. Do not apply the Ryu `R2=2` continuation rule to Ken without
  a separate Ken live validation.

Runtime decoder implementation:

- `src/rl/rl_session.c::RLSession_RyuSpecialPolicyMetaFromRoutine2`
  implements the first Ryu-specific `R2 + KW -> policy action/sub-action`
  mapping.
- `src/rl/rl_session.c::RLSession_SubActionFromRyuKindOfWaza` maps `KW` to
  button strength.
- `src/rl/rl_session.c::RLSession_RyuNormalPolicyMetaFromIdentity` uses
  `current_attack` / normal `KW` for normals, with stance/jump class inferred
  from sampled input or airborne/crouch context.
- `tools/analyze_rl_transitions.py::engine_state_action_name` implements the
  analyzer-only ordinary-state and Ryu attack labels from raw `obs_*_routine_1`
  / `obs_*_routine_2`.

Future-character expansion rule:

- For another character, do not copy Ryu's `R2` labels blindly. Use the same
  dispatch chain: `R1=4` -> `Player_attack` -> `plxx_extra_attack_table` ->
  that character's `plXX_exatt_table[R2 - 16]` -> taxonomy command row.
- Reuse common `R1=0` ordinary-state labels across characters only after a
  short overlay/log validation pass, because animation timing differs even
  when the normal-state dispatcher is shared.

Attribution flow for command moves:

1. Use `character_id` to select the character-specific decoder.
2. Use `R2` as the primary engine routine key.
3. Use `KW` to select the sub action / strength:
   - normal punches: `00/02/04` => `lp/mp/hp`
   - normal kicks: `01/03/05` => `lk/mk/hk`
   - punch-special strengths: `08/0A/0C` => `lp/mp/hp`
   - kick-special strengths: `09/0B/0D` => `lk/mk/hk`
4. Map `character_id + R2` to the stable taxonomy action. For source-backed
   command moves, this should agree with:
   - `policy_action_id = 1000 + character_id * 100 + source_command_slot`
   - the matching command row in `src/sf33rd/Source/Game/command/cmd_data.c`
   - the matching dispatch entry in `src/sf33rd/Source/Game/engine/plpatXX.c`
5. For throws, `R2` may identify the grab / throw routine but not throw
   direction. Keep `sub_action_id = none` unless the input-based row has a
   clear forward/back throw direction.
6. For normals, `AK` / normal `KW` can identify the button, but stance and jump
   class need more context. Use the sampled input or airborne/crouch state only
   as a best-effort label until normal stance/jump tables are validated.

How to add another character:

1. Add or verify that character's command rows in this taxonomy.
2. Find the source command slot and R2/routine value in `cmd_data.c`.
3. Find the character dispatch table in `plpatXX.c` and confirm which handler
   is entered for that R2.
4. Record observed overlay values while performing each move strength:
   `R2`, `KW`, `AK`, and whether `RS` lines up with the visible attack start.
5. Add a character-specific overlay identity draft table like the Ryu one below.
6. Only then promote the mapping into the runtime demo-attribution decoder.

## Universal Actions

| policy_action_id | policy_action_name | sub_action_group | macro_template |
|---:|---|---|---|
| 0 | neutral | none | `neutral` |
| 1 | walk | forward, back | `forward`, `back` |
| 2 | dash | forward, back | `forward, forward`, `back, back` |
| 3 | jump | neutral, forward, back | `up`, `up-forward`, `up-back` |
| 4 | guard | stand, crouch | `back_hold`, `down-back_hold` |
| 5 | parry | high, low, air | `tap_forward`, `tap_down`, `tap_forward_air` |
| 6 | stand_normal | lp, mp, hp, lk, mk, hk | `<button>` |
| 7 | command_normal | direction + button | `<direction>+<button>` |
| 8 | throw | forward, back | `forward+LP+LK`, `back+LP+LK` |
| 9 | tech_throw | neutral | `LP+LK` |
| 10 | quick_stand | neutral | `down_on_knockdown` |
| 11 | taunt | neutral | `HP+HK` |
| 12 | jump_attack_forward | lp, mp, hp, lk, mk, hk | legacy schema-v3/action-set-v4 only |
| 13 | jump_attack_neutral | lp, mp, hp, lk, mk, hk | legacy schema-v3/action-set-v4 only |
| 14 | jump_attack_back | lp, mp, hp, lk, mk, hk | legacy schema-v3/action-set-v4 only |
| 15 | crouch_normal | lp, mp, hp, lk, mk, hk | `down+<button>` |
| 16 | air_normal | lp, mp, hp, lk, mk, hk | `<button>` while `obs_self_air_attack_allowed` |

## Sub Actions

| sub_action_id | name |
|---:|---|
| 0 | none |
| 1 | lp |
| 2 | mp |
| 3 | hp |
| 4 | lk |
| 5 | mk |
| 6 | hk |
| 7 | p |
| 8 | k |
| 9 | ex_p |
| 10 | ex_k |
| 11 | all_p |
| 12 | all_k |
| 13 | forward |
| 14 | back |
| 15 | neutral_direction |
| 16 | up_forward |
| 17 | up_back |
| 18 | down_forward |
| 19 | down_back |
| 20 | stand |
| 21 | crouch |
| 22 | air |
| 30 | sa1 |
| 31 | sa2 |
| 32 | sa3 |
| 40 | hold |
| 41 | release |
| 50 | source_variant |

For character rows, `sub_action_group=p` means the macro can expand into
`lp/mp/hp/ex_p` variants later. `sub_action_group=k` means `lk/mk/hk/ex_k`.
Rows with numeric groups such as `18/18/18/18` are source command button masks
that still need manual naming before live use.

## Macro Notation

All directions are relative to the current facing direction at execution time.

| macro_template | intended expansion |
|---|---|
| `qcf+p` | `down, down-forward, forward+p` |
| `qcb+k` | `down, down-back, back+k` |
| `dp+p` | `forward, down, down-forward+p` |
| `qcf_qcf+p` | `down, down-forward, forward, down, down-forward, forward+p` |
| `qcb_qcb+k` | `down, down-back, back, down, down-back, back+k` |
| `charge_b_f+p` | hold `back`, then `forward+p` |
| `charge_d_u+k` | hold `down`, then `up+k` |
| `hcf_raw+p` | source pattern `back, down, forward+p`; verify exact diagonals before live use |
| `hcb_raw+k` | source pattern `forward, down, back+k`; verify exact diagonals before live use |
| `button_or_charge+p` | source command was not confidently decoded; validate before enabling |
| `raging_demon_like+...` | nonstandard multi-button command; validate before enabling |

## Character Command Registry

Rows below come from `src/sf33rd/Source/Game/engine/cmd_data.c` command slots and
`src/sf33rd/Source/Game/engine/plpatXX.c` extra-attack dispatch tables. A single
command slot can map to multiple routines when the original engine branches by
state or strength.

Move-name aliases were cross-checked against public 3rd Strike move lists from
[Street Fighter Wiki](https://streetfighter.fandom.com/wiki/List_of_moves_in_Street_Fighter_III%3A_3rd_Strike)
and [StrategyWiki](https://strategywiki.org/wiki/Street_Fighter_III%3A_3rd_Strike/Moves).
Rows with combined EX, air, or source-only variants keep slash-separated names
until live validation proves a cleaner split.

### Gill

| policy_action_id | slot | move_name | routines | handlers | macro_template | sub_action_group |
|---:|---:|---|---|---|---|---|
| 1020 | 20 | Resurrection | 21 | `Att_RESURRECTION` | `button_or_charge+p` | `p` |
| 1021 | 21 | Resurrection | 21 | `Att_RESURRECTION` | `button_or_charge+p` | `p` |
| 1022 | 22 | Resurrection | 21 | `Att_RESURRECTION` | `button_or_charge+p` | `p` |
| 1024 | 24 | Meteor Shower | 20 | `Att_HADOUKEN` | `qcf_qcf+p` | `p` |
| 1025 | 25 | Seraphic Wing | 22 | `Att_JYOUKA` | `qcf_qcf+k` | `k` |
| 1028 | 28 | Cyber Lariat | 18 | `Att_SLIDE_and_JUMP` | `dp+p` | `p` |
| 1029 | 29 | Moonsault Knee Drop | 17 | `Att_MOONSALT_KNEE_DROP` | `hcb_raw+k` | `k` |
| 1030 | 30 | Pyrokinesis / Cryokinesis | 16 | `Att_HADOUKEN` | `qcf+p` | `p` |
| 1031 | 31 | Psycho Head Butt | 19 | `Att_SENPUUKYAKU` | `qcb+p` | `p` |

### Alex

| policy_action_id | slot | move_name | routines | handlers | macro_template | sub_action_group |
|---:|---:|---|---|---|---|---|
| 1120 | 20 | Hyper Bomb | 19 | `Att_HADOUKEN2` | `button_or_charge+p` | `p` |
| 1121 | 21 | Boomerang Raid | 20 | `Att_CHOUCHUURENGEKI` | `qcf_qcf+p` | `p` |
| 1122 | 22 | Stun Gun Headbutt | 21 | `Att_SENPUUKYAKU2` | `qcf_qcf+p` | `p` |
| 1128 | 28 | Air Knee Smash | 17 | `Att_SHOURYUUKEN` | `dp+k` | `k` |
| 1129 | 29 | Power Bomb | 18 | `Att_HADOUKEN` | `hcb_raw+p` | `p` |
| 1130 | 30 | Flash Chop | 16 | `Att_CHOUCHUURENGEKI` | `qcf+p` | `p` |
| 1131 | 31 | Air Stampede | 22, 25 | `Att_SENPUUKYAKU`, `Att_HOMING_JUMP` | `charge_d_u+k` | `k` |
| 1132 | 32 | Slash Elbow | 26 | `Att_SLIDE_and_JUMP` | `charge_b_f+k` | `k` |
| 1133 | 33 | Spiral DDT | 24 | `Att_PL01_DDT` | `hcb_raw+k` | `k` |

### Ryu

| policy_action_id | slot | move_name | routines | handlers | macro_template | sub_action_group |
|---:|---:|---|---|---|---|---|
| 1220 | 20 | Shinkuu Hadouken | 19 | `Att_HADOUKEN` | `qcf_qcf+p` | `p` |
| 1221 | 21 | Denjin Hadouken | 21 | `Att_DENJINHADOUKEN` | `qcf_qcf+p` | `p` |
| 1222 | 22 | Shin Shoryuken | 20 | `Att_SHINSHOURYUUKEN` | `qcf_qcf+p` | `p` |
| 1228 | 28 | Shoryuken | 17 | `Att_SHOURYUUKEN` | `dp+p` | `p` |
| 1229 | 29 | Hadouken | 16 | `Att_HADOUKEN` | `qcf+p` | `p` |
| 1230 | 30 | Tatsumaki Senpukyaku | 18 | `Att_SENPUUKYAKU` | `qcb+k` | `k` |
| 1231 | 31 | Joudan Sokutou Geri | 23 | `Att_SLIDE_and_JUMP` | `hcf+k` | `k` |
| 1246 | 46 | Air Tatsumaki Senpukyaku | 22 | `Att_KUUCHUUNICHIRINSHOU` | `qcb+k` | `k` |

#### Ryu Overlay Identity Draft

This table is a provisional overlay-derived decoder for Ryu move labeling. It
should be treated as a validation aid until the fields are promoted into
transition logs. `R2` is `routine_no[2]`, `KW` is `kind_of_waza`, and `AK` is
`current_attack`.

Observed field behavior:

- `R2` is the primary active move / routine code.
- `KW` encodes strength and normal/special punch/kick class.
- `AK` is reliable for normal button identity, but not for specials.
- `RS` (`attack_routine_started`) is an event hint only and is not stable enough
  to identify the move.

| move family | policy_action_id | sub_action | R2 | KW | AK | status / notes |
|---|---:|---|---:|---|---|---|
| normal punch | `stand_normal` / `crouch_normal` / `air_normal` | `lp` | TBD | `00` | `010` | AK/KW observed; R2 still needs stance/jump validation |
| normal punch | `stand_normal` / `crouch_normal` / `air_normal` | `mp` | TBD | `02` | `020` | AK/KW observed; R2 still needs stance/jump validation |
| normal punch | `stand_normal` / `crouch_normal` / `air_normal` | `hp` | TBD | `04` | `040` | AK/KW observed; R2 still needs stance/jump validation |
| normal kick | `stand_normal` / `crouch_normal` / `air_normal` | `lk` | TBD | `01` | `100` | AK/KW observed; R2 still needs stance/jump validation |
| normal kick | `stand_normal` / `crouch_normal` / `air_normal` | `mk` | TBD | `03` | `200` | AK/KW observed; R2 still needs stance/jump validation |
| normal kick | `stand_normal` / `crouch_normal` / `air_normal` | `hk` | TBD | `05` | `400` | AK/KW observed; R2 still needs stance/jump validation |
| air-MP continuation / MP branch | `air_normal` | `mp` | 2 | observed as missing/unstable in transition export | observed as missing/unstable in transition export | source table says Ryu standing forward+MP branch; live MP-only logs show it as the second damage window of visible air-MP |
| Hadouken | 1229 | `lp` / `mp` / `hp` | 16 | `08` / `0A` / `0C` | not stable | overlay observed |
| Shoryuken | 1228 | `lp` / `mp` / `hp` | 17 | `08` / `0A` / `0C` | not stable | overlay observed |
| Tatsumaki Senpukyaku | 1230 | `lk` / `mk` / `hk` | 18 | `09` / `0B` / `0D` | not stable | overlay observed |
| grab / catch startup path | 8 | `forward` / `back` | 14 / 15 | TBD | not stable | source-backed throw startup path; validate success with `R1=2` / `R1=3` catch states |

Source-known Ryu command routines that still need overlay confirmation:

| move family | policy_action_id | source slot | source R2 | expected KW / AK | validation note |
|---|---:|---:|---:|---|---|
| Shinkuu Hadouken | 1220 | 20 | 19 | TBD | super-art KW not validated |
| Denjin Hadouken | 1221 | 21 | 21 | TBD | super-art KW not validated |
| Shin Shoryuken | 1222 | 22 | 20 | TBD | super-art KW not validated |
| Joudan Sokutou Geri | 1231 | 31 | 23 | likely kick-special KW, verify | command kick not validated |
| Air Tatsumaki Senpukyaku | 1246 | 46 | 22 | likely `09` / `0B` / `0D`, verify | air-special KW not validated |

### Yun

| policy_action_id | slot | move_name | routines | handlers | macro_template | sub_action_group |
|---:|---:|---|---|---|---|---|
| 1320 | 20 | You-hou | 19 | `Att_HADOUKEN` | `qcf_qcf+p` | `p` |
| 1321 | 21 | Sourai Rengeki | 20 | `Att_SLIDE_and_JUMP` | `qcf_qcf+p` | `p` |
| 1322 | 22 | Genei-jin | 21 | `Att_SLIDE_and_JUMP` | `qcf_qcf+p` | `p` |
| 1328 | 28 | Zenpou Tenshin | 22 | `Att_HADOUKEN` | `hcb_raw+k` | `k` |
| 1329 | 29 | Tetsuzanko | 24 | `Att_SLIDE_and_JUMP` | `dp+p` | `p` |
| 1330 | 30 | Kobokushi | 16 | `Att_HADOUKEN` | `qcb+p` | `p` |
| 1331 | 31 | Nishoukyaku | 17 | `Att_SHOURYUUKEN` | `dp+k` | `k` |
| 1332 | 32 | Zesshou Hohou | 18 | `Att_SENPUUKYAKU` | `qcf+p` | `p` |

### Dudley

| policy_action_id | slot | move_name | routines | handlers | macro_template | sub_action_group |
|---:|---:|---|---|---|---|---|
| 1420 | 20 | Rocket Upper | 19 | `Att_SHOURYUUREPPA` | `qcf_qcf+p` | `p` |
| 1421 | 21 | Rolling Thunder | 20 | `Att_HADOUKEN2` | `qcf_qcf+p` | `p` |
| 1422 | 22 | Corkscrew Blow | 21 | `Att_CHOUCHUURENGEKI` | `qcf_qcf+p` | `p` |
| 1428 | 28 | Jet Upper | 16 | `Att_SENPUUKYAKU` | `dp+p` | `p` |
| 1429 | 29 | Punch & Cross | 25 | `Att_HADOUKEN` | `f-d-b-n-f+p` | `p` |
| 1430 | 30 | Cross Counter | 18 | `Att_HADOUKEN` | `hcb_raw+p` | `p` |
| 1431 | 31 | Machine Gun Blow | 17 | `Att_SENPUUKYAKU` | `hcf_raw+p` | `p` |
| 1432 | 32 | Ducking / Ducking Straight / Ducking Upper | 22 | `Att_CHOUCHUURENGEKI` | `hcf_raw+k` | `k` |
| 1433 | 33 | Short Swing Blow | 22 | `Att_CHOUCHUURENGEKI` | `hcb_raw+k` | `k` |

### Necro

| policy_action_id | slot | move_name | routines | handlers | macro_template | sub_action_group |
|---:|---:|---|---|---|---|---|
| 1520 | 20 | Magnetic Storm | 18 | `Att_HADOUKEN` | `qcf_qcf+p` | `p` |
| 1521 | 21 | Slam Dance | 20 | `Att_HADOUKEN` | `qcf_qcf+p` | `p` |
| 1522 | 22 | Electric Snake | 22 | `Att_HADOUKEN` | `qcf_qcf+p` | `p` |
| 1528 | 28 | Snake Fang | 19 | `Att_HADOUKEN` | `hcf+k` | `k` |
| 1529 | 29 | Denji Blast | 17 | `Att_HADOUKEN` | `dp+p` | `p` |
| 1530 | 30 | Tornado Hook | 16 | `Att_CHOUCHUURENGEKI` | `hcf+p` | `p` |
| 1531 | 31 | Flying Viper | 21, 25 | `Att_SENPUUKYAKU`, `Att_JINNCHUUWATARI` | `qcb+p` | `p` |
| 1532 | 32 | Rising Cobra | 24, 26 | `Att_HADOUKEN`, `Att_SLIDE_and_JUMP` | `qcb+k` | `k` |

### Hugo

| policy_action_id | slot | move_name | routines | handlers | macro_template | sub_action_group |
|---:|---:|---|---|---|---|---|
| 1620 | 20 | Gigas Breaker | 22 | `Att_HADOUKEN2` | `button_or_charge+p` | `p` |
| 1621 | 21 | Megaton Press | 23 | `Att_SHOURYUUKEN` | `qcf_qcf+k` | `k` |
| 1622 | 22 | Hammer Frenzy | 21 | `Att_SLIDE_and_JUMP` | `qcf_qcf+p` | `p` |
| 1628 | 28 | Moonsault Press | 17 | `Att_HADOUKEN2` | `button_or_charge+p` | `p` |
| 1629 | 29 | Meat Squasher | 24 | `Att_PL06_HASHIRI_NAGE` | `button_or_charge+k` | `k` |
| 1630 | 30 | Shootdown Backbreaker | 20 | `Att_SHOURYUUKEN` | `dp+k` | `k` |
| 1631 | 31 | Giant Palm Bomber | 16 | `Att_HADOUKEN2` | `qcb+p` | `p` |
| 1632 | 32 | Monster Lariat | 18, 25 | `Att_CHOUCHUURENGEKI`, `Att_PL06_HASHIRI_NAGE` | `qcf+k` | `k` |
| 1633 | 33 | Ultra Throw | 19 | `Att_HADOUKEN2` | `hcb_raw+k` | `k` |

### Ibuki

| policy_action_id | slot | move_name | routines | handlers | macro_template | sub_action_group |
|---:|---:|---|---|---|---|---|
| 1720 | 20 | Kasumi Suzaku | 19 | `Att_SLIDE_and_JUMP` | `qcf_qcf+p` | `p` |
| 1721 | 21 | Yoroi Dooshi | 21 | `Att_PL07_SA2` | `qcf_qcf+p` | `p` |
| 1728 | 28 | Kazekiri | 16 | `Att_SHOURYUUKEN` | `dp+k` | `k` |
| 1729 | 29 | Raida | 18 | `Att_CHOUCHUURENGEKI` | `hcb_raw+p` | `p` |
| 1730 | 30 | Hien | 22, 26 | `Att_PL07_AT2`, `Att_HOMING_JUMP` | `back_down_db_raw+k` | `k` |
| 1731 | 31 | Tsuji Goe | 25 | `Att_SLIDE_and_JUMP` | `dp+p` | `p` |
| 1732 | 32 | Tsumuji | 20 | `Att_CHOUCHUURENGEKI` | `qcb+k` | `k` |
| 1733 | 33 | Kubi Ori | 17 | `Att_PL07_AT1` | `qcf+p` | `p` |
| 1734 | 34 | Kasumi Gake | 25 | `Att_SLIDE_and_JUMP` | `qcf+k` | `k` |
| 1738 | 38 | Yami Shigure | 24 | `Att_PL07_SA3` | `qcf_qcf+p` | `p` |
| 1746 | 46 | Kunai | 23 | `Att_PL07_AT3` | `qcf+p` | `p` |

### Elena

| policy_action_id | slot | move_name | routines | handlers | macro_template | sub_action_group |
|---:|---:|---|---|---|---|---|
| 1820 | 20 | Spinning Beat | 19 | `Att_SHOURYUUREPPA` | `qcf_qcf+k` | `k` |
| 1821 | 21 | Brave Dance | 20 | `Att_SHOURYUUREPPA` | `qcf_qcf+k` | `k` |
| 1822 | 22 | Healing | 21 | `Att_PL08_HEALING` | `qcf_qcf+p` | `p` |
| 1828 | 28 | Scratch Wheel | 16 | `Att_SHOURYUUKEN` | `dp+k` | `k` |
| 1829 | 29 | Rhino Horn | 17 | `Att_SENPUUKYAKU` | `hcf_raw+k` | `k` |
| 1830 | 30 | Mallet Smash | 18 | `Att_SENPUUKYAKU` | `hcb_raw+p` | `p` |
| 1831 | 31 | Lynx Tail | 24 | `Att_HADOUKEN` | `back_down_db_raw+k` | `k` |
| 1832 | 32 | Spin Scythe | 23 | `Att_SLIDE_and_JUMP` | `qcb+k` | `k` |

### Oro

| policy_action_id | slot | move_name | routines | handlers | macro_template | sub_action_group |
|---:|---:|---|---|---|---|---|
| 1920 | 20 | Tengu Stone / EX Tengu Stone | 20, 27 | `Att_HADOUKEN`, `Att_PL09_EX_TENGUIWA` | `qcf_qcf+p` | `p` |
| 1921 | 21 | Kishin Riki | 21 | `Att_HADOUKEN` | `qcf_qcf+p` | `p` |
| 1922 | 22 | Kishin Kuuchuu Jigoku Guruma / EX Kishin Riki | 22, 28 | `Att_HADOUKEN`, `Att_PL09_EX_KISHINRIKI` | `qcf_qcf+p` | `p` |
| 1924 | 24 | Yagyou Dama / EX Yagyou Dama | 26 | `Att_SP_YAGYOUDAMA` | `qcf_qcf+3/3/3/19` | `3/3/3/19` |
| 1928 | 28 | Oni Yanma | 17 | `Att_SHOURYUUKEN` | `charge_d_u+p` | `p` |
| 1929 | 29 | Niou Riki | 19 | `Att_HADOUKEN` | `hcb_raw+p` | `p` |
| 1930 | 30 | Nichirin Shou | 16 | `Att_HADOUKEN` | `charge_b_f+p` | `p` |
| 1931 | 31 | Jinchuu Watari | 24, 25 | `Att_JINNCHUUWATARI`, `Att_JINNCHUUWATARI_EX` | `qcf+k` | `k` |
| 1946 | 46 | Kuuchuu Nichirin Shou | 18 | `Att_KUUCHUUNICHIRINSHOU` | `button_or_charge+p` | `p` |
| 1947 | 47 | Hitobashira Nobori | 23 | `Att_KUUCHUUJINNCHUUWATARI` | `qcf+k` | `k` |

### Yang

| policy_action_id | slot | move_name | routines | handlers | macro_template | sub_action_group |
|---:|---:|---|---|---|---|---|
| 2020 | 20 | Raishin Mahha Ken | 19 | `Att_HADOUKEN` | `qcf_qcf+p` | `p` |
| 2021 | 21 | Sei'ei Enbu | 20 | `Att_SLIDE_and_JUMP` | `qcf_qcf+p` | `p` |
| 2022 | 22 | Tenshin Senkyuutai | 21 | `Att_TENSHINSENKYUUTAI` | `qcf_qcf+k` | `k` |
| 2028 | 28 | Zenpou Tenshin | 22 | `Att_HADOUKEN` | `hcb_raw+k` | `k` |
| 2029 | 29 | Kaihou | 23 | `Att_PL10_MACH_SLIDE2` | `dp+k` | `k` |
| 2030 | 30 | Tourou Zan | 18 | `Att_SLIDE_and_JUMP` | `qcf+p` | `p` |
| 2031 | 31 | Senkyuutai | 17 | `Att_TENSHINSENKYUUTAI` | `qcf+k` | `k` |
| 2032 | 32 | Byakko Soushouda | 16 | `Att_HADOUKEN` | `qcb+p` | `p` |

### Ken

Ken note:

- Unlike Ryu, Ken's normal AS tables currently show no `.r_no=2` entry in the
  standing, crouching, or air-normal tables. Keep `R1=4/R2=2` unmapped for Ken
  until a Ken-specific live overlay/log pass proves a concrete meaning.

| policy_action_id | slot | move_name | routines | handlers | macro_template | sub_action_group |
|---:|---:|---|---|---|---|---|
| 2120 | 20 | Shoryureppa | 19 | `Att_SHOURYUUREPPA` | `qcf_qcf+p` | `p` |
| 2121 | 21 | Shinryuken | 20 | `Att_SHOURYUUREPPA` | `qcf_qcf+k` | `k` |
| 2122 | 22 | Shippu Jinraikyaku | 21 | `Att_SLIDE_and_JUMP` | `qcf_qcf+k` | `k` |
| 2128 | 28 | Shoryuken | 17 | `Att_SHOURYUUKEN` | `dp+p` | `p` |
| 2129 | 29 | Hadouken | 16 | `Att_HADOUKEN` | `qcf+p` | `p` |
| 2130 | 30 | Tatsumaki Senpukyaku | 18 | `Att_SENPUUKYAKU` | `qcb+k` | `k` |
| 2146 | 46 | Air Tatsumaki Senpukyaku | 22 | `Att_KUUCHUUNICHIRINSHOU` | `qcb+k` | `k` |

### Sean

| policy_action_id | slot | move_name | routines | handlers | macro_template | sub_action_group |
|---:|---:|---|---|---|---|---|
| 2220 | 20 | Hadou Burst | 16 | `Att_HADOUKEN` | `qcf_qcf+p` | `p` |
| 2221 | 21 | Shoryuu Cannon | 17 | `Att_SHOURYUUREPPA` | `qcf_qcf+p` | `p` |
| 2222 | 22 | Hyper Tornado | 18 | `Att_SLIDE_and_JUMP` | `qcf_qcf+p` | `p` |
| 2228 | 28 | Sean Tackle | 22 | `Att_CHOUCHUURENGEKI` | `hcf_raw+p` | `p` |
| 2229 | 29 | Dragon Smash | 24 | `Att_SENPUUKYAKU` | `dp+p` | `p` |
| 2230 | 30 | Ryuubi Kyaku | 19, 25 | `Att_ABISEGERI`, `Att_HOMING_JUMP` | `qcf+k` | `k` |
| 2231 | 31 | Zenten | 20 | `Att_CHOUCHUURENGEKI` | `qcb+p` | `p` |
| 2232 | 32 | Tornado | 21 | `Att_SHOURYUUKEN` | `qcb+k` | `k` |

### Urien

| policy_action_id | slot | move_name | routines | handlers | macro_template | sub_action_group |
|---:|---:|---|---|---|---|---|
| 2320 | 20 | Tyrant Slaughter | 20 | `Att_CHOUCHUURENGEKI` | `qcf_qcf+p` | `p` |
| 2321 | 21 | Temporal Thunder | 21 | `Att_CHOUCHUURENGEKI` | `qcf_qcf+p` | `p` |
| 2322 | 22 | Aegis Reflector | 22 | `Att_HADOUKEN` | `qcf_qcf+p` | `p` |
| 2328 | 28 | Chariot Tackle | 23 | `Att_CHOUCHUURENGEKI` | `charge_b_f+k` | `k` |
| 2329 | 29 | Violence Knee Drop | 24, 17 | `Att_SLIDE_and_JUMP`, `Att_MOONSALT_KNEE_DROP2` | `charge_d_u+k` | `k` |
| 2330 | 30 | Metallic Sphere | 16 | `Att_HADOUKEN` | `qcf+p` | `p` |
| 2331 | 31 | Dangerous Headbutt | 19 | `Att_SENPUUKYAKU` | `charge_d_u+p` | `p` |

### Akuma

| policy_action_id | slot | move_name | routines | handlers | macro_template | sub_action_group |
|---:|---:|---|---|---|---|---|
| 2420 | 20 | Messatsu Gou Hadou | 16 | `Att_HADOUKEN` | `qcf_qcf+p` | `p` |
| 2421 | 21 | Messatsu Gou Shoryu | 20 | `Att_SHOURYUUREPPA` | `qcf_qcf+p` | `p` |
| 2422 | 22 | Messatsu-Gourasen | 17 | `Att_SHOURYUUKEN` | `qcf_qcf+k` | `k` |
| 2424 | 24 | Shungokusatsu | 24 | `Att_CHOUCHUURENGEKI` | `raging_demon_like+18/18/18/18` | `18/18/18/18` |
| 2425 | 25 | Kongou Kokuretsuzan | 26 | `Att_HADOUKEN` | `down_down_down+19/19/19/19` | `19/19/19/19` |
| 2428 | 28 | Ashura Senku (forward) | 23 | `Att_PL14_AT1` | `dp+19/19/23/23` | `19/19/23/23` |
| 2429 | 29 | Ashura Senku (back) | 23 | `Att_PL14_AT1` | `back_down_db_raw+19/19/23/23` | `19/19/23/23` |
| 2430 | 30 | Go Shoryuken | 17 | `Att_SHOURYUUKEN` | `dp+p` | `p` |
| 2431 | 31 | Go Hadouken | 16 | `Att_HADOUKEN` | `qcf+p` | `p` |
| 2432 | 32 | Tatsumaki Zankuukyaku | 18 | `Att_SENPUUKYAKU` | `qcb+k` | `k` |
| 2433 | 33 | Shakunetsu-Hadouken | 16 | `Att_HADOUKEN` | `reverse_qcb_raw+p` | `p` |
| 2434 | 34 | Hyakkishu | 21 | `Att_SLIDE_and_JUMP` | `f+k` | `k` |
| 2435 | 35 | Hyakkishu | 27 | `Att_PL14_AT3` | `dp+k` | `k` |
| 2438 | 38 | Tenma Gou Zankuu | 25 | `Att_PL14_AT2` | `qcf_qcf+p` | `p` |
| 2439 | 39 | Messatsu-GouSenpuu | 19 | `Att_KUUCHUUJINNCHUUWATARI` | `qcf_qcf+k` | `k` |
| 2446 | 46 | Zankuu Hadouken | 25 | `Att_PL14_AT2` | `qcf+p` | `p` |
| 2447 | 47 | Air Tatsumaki Zankuukyaku | 22 | `Att_KUUCHUUNICHIRINSHOU` | `qcb+k` | `k` |

### Chun-Li

| policy_action_id | slot | move_name | routines | handlers | macro_template | sub_action_group |
|---:|---:|---|---|---|---|---|
| 2520 | 20 | Kikou Shou | 18 | `Att_HADOUKEN` | `qcf_qcf+p` | `p` |
| 2521 | 21 | Houyoku Sen | 20 | `Att_SLIDE_and_JUMP` | `qcf_qcf+k` | `k` |
| 2522 | 22 | Tensei Ranka | 22 | `Att_SLIDE_and_JUMP` | `qcf_qcf+k` | `k` |
| 2528 | 28 | Spinning Bird Kick | 16 | `Att_SENPUUKYAKU` | `charge_d_u+k` | `k` |
| 2529 | 29 | Hyakuretsu Kyaku | 17 | `Att_HADOUKEN2` | `n+k` | `k` |
| 2530 | 30 | Kikoken | 19 | `Att_HADOUKEN` | `hcf+p` | `p` |
| 2531 | 31 | Hazanshu | 21 | `Att_SLIDE_and_JUMP` | `reverse_qcb_raw+k` | `k` |

### Makoto

| policy_action_id | slot | move_name | routines | handlers | macro_template | sub_action_group |
|---:|---:|---|---|---|---|---|
| 2620 | 20 | Abare Tosanami | 17 | `Att_PL17_AT1` | `qcf_qcf+k` | `k` |
| 2621 | 21 | Seichusen Godanzuki | 19 | `Att_PL17_AT2` | `qcf_qcf+p` | `p` |
| 2622 | 22 | Tanden Renki | 18 | `Att_HADOUKEN2` | `qcf_qcf+p` | `p` |
| 2628 | 28 | Fukiage | 18 | `Att_HADOUKEN2` | `dp+p` | `p` |
| 2629 | 29 | Oroshi | 18 | `Att_HADOUKEN2` | `qcb+p` | `p` |
| 2630 | 30 | Hayate | 16 | `Att_CHOUCHUURENGEKI` | `qcf+p` | `p` |
| 2631 | 31 | Karakusa | 16 | `Att_CHOUCHUURENGEKI` | `reverse_qcb_raw+k` | `k` |
| 2646 | 46 | Tsurugi | 20 | `Att_KUUCHUUJINNCHUUWATARI` | `qcb+k` | `k` |

### Q

| policy_action_id | slot | move_name | routines | handlers | macro_template | sub_action_group |
|---:|---:|---|---|---|---|---|
| 2720 | 20 | Critical Combo Attack | 20 | `Att_SLIDE_and_JUMP` | `qcf_qcf+p` | `p` |
| 2721 | 21 | Deadly Double Combination | 21 | `Att_HADOUKEN2` | `qcf_qcf+p` | `p` |
| 2722 | 22 | Total Destruction | 22 | `Att_HADOUKEN` | `qcf_qcf+p` | `p` |
| 2728 | 28 | Dashing Straight | 16 | `Att_SLIDE_and_JUMP` | `charge_b_f+p` | `p` |
| 2729 | 29 | Dashing Leg Attack | 17 | `Att_SLIDE_and_JUMP` | `charge_b_f+k` | `k` |
| 2730 | 30 | Dashing Head Attack | 18 | `Att_HADOUKEN2` | `qcb+p` | `p` |
| 2731 | 31 | High Speed Barrage | 19 | `Att_HADOUKEN2` | `reverse_qcb_raw+k` | `k` |
| 2732 | 32 | Capture & Deadly Blow | 23 | `Att_PL18_NINGENBAKUDAN` | `qcf+p` | `p` |
| 2733 | 33 | Total Destruction: Danger | 24 | `Att_HADOUKEN` | `qcf+k` | `k` |

### Twelve

| policy_action_id | slot | move_name | routines | handlers | macro_template | sub_action_group |
|---:|---:|---|---|---|---|---|
| 2820 | 20 | X.N.D.L. | 20 | `Att_HADOUKEN` | `qcf_qcf+p` | `p` |
| 2821 | 21 | X.C.O.P.Y. | 22 | `Att_METAMORPHOSE` | `qcf_qcf+p` | `p` |
| 2828 | 28 | A.X.E. | 16 | `Att_HADOUKEN` | `qcb+p` | `p` |
| 2829 | 29 | N.D.L. | 19 | `Att_HADOUKEN` | `qcf+p` | `p` |
| 2830 | 30 | N.D.L. / source kick variant | 19 | `Att_HADOUKEN` | `qcf+k` | `k` |
| 2838 | 38 | X.F.L.A.T. | 27 | `Att_SA__D_R_A` | `qcf_qcf+k` | `k` |
| 2846 | 46 | Kokuu forward air dash | 17 | `Att_AIRDASH` | `triple_f+0/0/0/0` | `0/0/0/0` |
| 2847 | 47 | D.R.A. | 18 | `Att_KUUCHUUHISSATU` | `qcb+k` | `k` |
| 2848 | 48 | Air A.X.E. | 23 | `Att_AIR_A_X_E` | `qcb+p` | `p` |
| 2849 | 49 | Kokuu backward air dash | 17 | `Att_AIRDASH` | `triple_b+0/0/0/0` | `0/0/0/0` |

### Remy

| policy_action_id | slot | move_name | routines | handlers | macro_template | sub_action_group |
|---:|---:|---|---|---|---|---|
| 2920 | 20 | Light of Justice | 16 | `Att_HADOUKEN` | `qcf_qcf+p` | `p` |
| 2921 | 21 | Supreme Rising Rage Flash | 20 | `Att_HADOUKEN` | `qcf_qcf+k` | `k` |
| 2922 | 22 | Blue Nocturne | 17 | `Att_PL20_AT1` | `qcf_qcf+k` | `k` |
| 2928 | 28 | Rising Rage Flash | 17 | `Att_PL20_AT1` | `charge_d_u+k` | `k` |
| 2929 | 29 | Light of Virtue | 16 | `Att_HADOUKEN` | `charge_b_f+p` | `p` |
| 2930 | 30 | Light of Virtue (low) | 16 | `Att_HADOUKEN` | `charge_b_f+k` | `k` |
| 2931 | 31 | Cold Blue Kick | 18 | `Att_PL20_AT2` | `qcb+k` | `k` |

## Open Validation Items

- Decode `button_or_charge` rows into concrete macros before live enablement.
- Split grouped `p`/`k` rows into concrete strength rows only when a curriculum
  needs them.
- Validate ambiguous readable aliases for source-only variants such as Oro EX
  command rows, Twelve `qcf+k`, and Akuma Hyakkishu / Ashura Senku branches
  before promoting them into a live curriculum.
- Keep live learner action sets using separate `back`, `guard/stand`, and
  `guard/crouch` actions so retreat spacing is not credited as blocking.
- Collect a short schema-v4 CPU-demo log and confirm `jump-*-start` and
  `air-*` labels are separated before training the first action-set-v5 DQN.
