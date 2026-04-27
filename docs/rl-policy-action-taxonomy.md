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

This registry does not claim official move names yet. The source handlers are
the source of truth for now because many handlers are generic names such as
`Att_HADOUKEN` even when the player-facing move name differs by character.
Target combos and detailed normal attack chains still need a separate attack
table pass before they are treated as individual policy actions.

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

## Universal Actions

| policy_action_id | policy_action_name | sub_action_group | macro_template |
|---:|---|---|---|
| 0 | neutral | none | `neutral` |
| 1 | walk | forward, back | `forward`, `back` |
| 2 | dash | forward, back | `forward, forward`, `back, back` |
| 3 | jump | neutral, forward, back | `up`, `up-forward`, `up-back` |
| 4 | guard | stand, crouch | `back_hold`, `down-back_hold` |
| 5 | parry | high, low, air | `tap_forward`, `tap_down`, `tap_forward_air` |
| 6 | normal | lp, mp, hp, lk, mk, hk | `<button>` |
| 7 | command_normal | direction + button | `<direction>+<button>` |
| 8 | throw | forward, back | `forward+LP+LK`, `back+LP+LK` |
| 9 | tech_throw | neutral | `LP+LK` |
| 10 | quick_stand | neutral | `down_on_knockdown` |
| 11 | taunt | neutral | `HP+HK` |
| 12 | jump_attack | lp, mp, hp, lk, mk, hk | `up-forward+<button>` |

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

### Gill

| policy_action_id | slot | routines | handlers | macro_template | sub_action_group |
|---:|---:|---|---|---|---|
| 1020 | 20 | 21 | `Att_RESURRECTION` | `button_or_charge+p` | `p` |
| 1021 | 21 | 21 | `Att_RESURRECTION` | `button_or_charge+p` | `p` |
| 1022 | 22 | 21 | `Att_RESURRECTION` | `button_or_charge+p` | `p` |
| 1024 | 24 | 20 | `Att_HADOUKEN` | `qcf_qcf+p` | `p` |
| 1025 | 25 | 22 | `Att_JYOUKA` | `qcf_qcf+k` | `k` |
| 1028 | 28 | 18 | `Att_SLIDE_and_JUMP` | `dp+p` | `p` |
| 1029 | 29 | 17 | `Att_MOONSALT_KNEE_DROP` | `hcb_raw+k` | `k` |
| 1030 | 30 | 16 | `Att_HADOUKEN` | `qcf+p` | `p` |
| 1031 | 31 | 19 | `Att_SENPUUKYAKU` | `qcb+p` | `p` |

### Alex

| policy_action_id | slot | routines | handlers | macro_template | sub_action_group |
|---:|---:|---|---|---|---|
| 1120 | 20 | 19 | `Att_HADOUKEN2` | `button_or_charge+p` | `p` |
| 1121 | 21 | 20 | `Att_CHOUCHUURENGEKI` | `qcf_qcf+p` | `p` |
| 1122 | 22 | 21 | `Att_SENPUUKYAKU2` | `qcf_qcf+p` | `p` |
| 1128 | 28 | 17 | `Att_SHOURYUUKEN` | `dp+k` | `k` |
| 1129 | 29 | 18 | `Att_HADOUKEN` | `hcb_raw+p` | `p` |
| 1130 | 30 | 16 | `Att_CHOUCHUURENGEKI` | `qcf+p` | `p` |
| 1131 | 31 | 22, 25 | `Att_SENPUUKYAKU`, `Att_HOMING_JUMP` | `charge_d_u+k` | `k` |
| 1132 | 32 | 26 | `Att_SLIDE_and_JUMP` | `charge_b_f+k` | `k` |
| 1133 | 33 | 24 | `Att_PL01_DDT` | `hcb_raw+k` | `k` |

### Ryu

| policy_action_id | slot | routines | handlers | macro_template | sub_action_group |
|---:|---:|---|---|---|---|
| 1220 | 20 | 19 | `Att_HADOUKEN` | `qcf_qcf+p` | `p` |
| 1221 | 21 | 21 | `Att_DENJINHADOUKEN` | `qcf_qcf+p` | `p` |
| 1222 | 22 | 20 | `Att_SHINSHOURYUUKEN` | `qcf_qcf+p` | `p` |
| 1228 | 28 | 17 | `Att_SHOURYUUKEN` | `dp+p` | `p` |
| 1229 | 29 | 16 | `Att_HADOUKEN` | `qcf+p` | `p` |
| 1230 | 30 | 18 | `Att_SENPUUKYAKU` | `qcb+k` | `k` |
| 1231 | 31 | 23 | `Att_SLIDE_and_JUMP` | `hcf+k` | `k` |
| 1246 | 46 | 22 | `Att_KUUCHUUNICHIRINSHOU` | `qcb+k` | `k` |

### Yun

| policy_action_id | slot | routines | handlers | macro_template | sub_action_group |
|---:|---:|---|---|---|---|
| 1320 | 20 | 19 | `Att_HADOUKEN` | `qcf_qcf+p` | `p` |
| 1321 | 21 | 20 | `Att_SLIDE_and_JUMP` | `qcf_qcf+p` | `p` |
| 1322 | 22 | 21 | `Att_SLIDE_and_JUMP` | `qcf_qcf+p` | `p` |
| 1328 | 28 | 22 | `Att_HADOUKEN` | `hcb_raw+k` | `k` |
| 1329 | 29 | 24 | `Att_SLIDE_and_JUMP` | `dp+p` | `p` |
| 1330 | 30 | 16 | `Att_HADOUKEN` | `qcb+p` | `p` |
| 1331 | 31 | 17 | `Att_SHOURYUUKEN` | `dp+k` | `k` |
| 1332 | 32 | 18 | `Att_SENPUUKYAKU` | `qcf+p` | `p` |

### Dudley

| policy_action_id | slot | routines | handlers | macro_template | sub_action_group |
|---:|---:|---|---|---|---|
| 1420 | 20 | 19 | `Att_SHOURYUUREPPA` | `qcf_qcf+p` | `p` |
| 1421 | 21 | 20 | `Att_HADOUKEN2` | `qcf_qcf+p` | `p` |
| 1422 | 22 | 21 | `Att_CHOUCHUURENGEKI` | `qcf_qcf+p` | `p` |
| 1428 | 28 | 16 | `Att_SENPUUKYAKU` | `dp+p` | `p` |
| 1429 | 29 | 25 | `Att_HADOUKEN` | `f-d-b-n-f+p` | `p` |
| 1430 | 30 | 18 | `Att_HADOUKEN` | `hcb_raw+p` | `p` |
| 1431 | 31 | 17 | `Att_SENPUUKYAKU` | `hcf_raw+p` | `p` |
| 1432 | 32 | 22 | `Att_CHOUCHUURENGEKI` | `hcf_raw+k` | `k` |
| 1433 | 33 | 22 | `Att_CHOUCHUURENGEKI` | `hcb_raw+k` | `k` |

### Necro

| policy_action_id | slot | routines | handlers | macro_template | sub_action_group |
|---:|---:|---|---|---|---|
| 1520 | 20 | 18 | `Att_HADOUKEN` | `qcf_qcf+p` | `p` |
| 1521 | 21 | 20 | `Att_HADOUKEN` | `qcf_qcf+p` | `p` |
| 1522 | 22 | 22 | `Att_HADOUKEN` | `qcf_qcf+p` | `p` |
| 1528 | 28 | 19 | `Att_HADOUKEN` | `hcf+k` | `k` |
| 1529 | 29 | 17 | `Att_HADOUKEN` | `dp+p` | `p` |
| 1530 | 30 | 16 | `Att_CHOUCHUURENGEKI` | `hcf+p` | `p` |
| 1531 | 31 | 21, 25 | `Att_SENPUUKYAKU`, `Att_JINNCHUUWATARI` | `qcb+p` | `p` |
| 1532 | 32 | 24, 26 | `Att_HADOUKEN`, `Att_SLIDE_and_JUMP` | `qcb+k` | `k` |

### Hugo

| policy_action_id | slot | routines | handlers | macro_template | sub_action_group |
|---:|---:|---|---|---|---|
| 1620 | 20 | 22 | `Att_HADOUKEN2` | `button_or_charge+p` | `p` |
| 1621 | 21 | 23 | `Att_SHOURYUUKEN` | `qcf_qcf+k` | `k` |
| 1622 | 22 | 21 | `Att_SLIDE_and_JUMP` | `qcf_qcf+p` | `p` |
| 1628 | 28 | 17 | `Att_HADOUKEN2` | `button_or_charge+p` | `p` |
| 1629 | 29 | 24 | `Att_PL06_HASHIRI_NAGE` | `button_or_charge+k` | `k` |
| 1630 | 30 | 20 | `Att_SHOURYUUKEN` | `dp+k` | `k` |
| 1631 | 31 | 16 | `Att_HADOUKEN2` | `qcb+p` | `p` |
| 1632 | 32 | 18, 25 | `Att_CHOUCHUURENGEKI`, `Att_PL06_HASHIRI_NAGE` | `qcf+k` | `k` |
| 1633 | 33 | 19 | `Att_HADOUKEN2` | `hcb_raw+k` | `k` |

### Ibuki

| policy_action_id | slot | routines | handlers | macro_template | sub_action_group |
|---:|---:|---|---|---|---|
| 1720 | 20 | 19 | `Att_SLIDE_and_JUMP` | `qcf_qcf+p` | `p` |
| 1721 | 21 | 21 | `Att_PL07_SA2` | `qcf_qcf+p` | `p` |
| 1728 | 28 | 16 | `Att_SHOURYUUKEN` | `dp+k` | `k` |
| 1729 | 29 | 18 | `Att_CHOUCHUURENGEKI` | `hcb_raw+p` | `p` |
| 1730 | 30 | 22, 26 | `Att_PL07_AT2`, `Att_HOMING_JUMP` | `back_down_db_raw+k` | `k` |
| 1731 | 31 | 25 | `Att_SLIDE_and_JUMP` | `dp+p` | `p` |
| 1732 | 32 | 20 | `Att_CHOUCHUURENGEKI` | `qcb+k` | `k` |
| 1733 | 33 | 17 | `Att_PL07_AT1` | `qcf+p` | `p` |
| 1734 | 34 | 25 | `Att_SLIDE_and_JUMP` | `qcf+k` | `k` |
| 1738 | 38 | 24 | `Att_PL07_SA3` | `qcf_qcf+p` | `p` |
| 1746 | 46 | 23 | `Att_PL07_AT3` | `qcf+p` | `p` |

### Elena

| policy_action_id | slot | routines | handlers | macro_template | sub_action_group |
|---:|---:|---|---|---|---|
| 1820 | 20 | 19 | `Att_SHOURYUUREPPA` | `qcf_qcf+k` | `k` |
| 1821 | 21 | 20 | `Att_SHOURYUUREPPA` | `qcf_qcf+k` | `k` |
| 1822 | 22 | 21 | `Att_PL08_HEALING` | `qcf_qcf+p` | `p` |
| 1828 | 28 | 16 | `Att_SHOURYUUKEN` | `dp+k` | `k` |
| 1829 | 29 | 17 | `Att_SENPUUKYAKU` | `hcf_raw+k` | `k` |
| 1830 | 30 | 18 | `Att_SENPUUKYAKU` | `hcb_raw+p` | `p` |
| 1831 | 31 | 24 | `Att_HADOUKEN` | `back_down_db_raw+k` | `k` |
| 1832 | 32 | 23 | `Att_SLIDE_and_JUMP` | `qcb+k` | `k` |

### Oro

| policy_action_id | slot | routines | handlers | macro_template | sub_action_group |
|---:|---:|---|---|---|---|
| 1920 | 20 | 20, 27 | `Att_HADOUKEN`, `Att_PL09_EX_TENGUIWA` | `qcf_qcf+p` | `p` |
| 1921 | 21 | 21 | `Att_HADOUKEN` | `qcf_qcf+p` | `p` |
| 1922 | 22 | 22, 28 | `Att_HADOUKEN`, `Att_PL09_EX_KISHINRIKI` | `qcf_qcf+p` | `p` |
| 1924 | 24 | 26 | `Att_SP_YAGYOUDAMA` | `qcf_qcf+3/3/3/19` | `3/3/3/19` |
| 1928 | 28 | 17 | `Att_SHOURYUUKEN` | `charge_d_u+p` | `p` |
| 1929 | 29 | 19 | `Att_HADOUKEN` | `hcb_raw+p` | `p` |
| 1930 | 30 | 16 | `Att_HADOUKEN` | `charge_b_f+p` | `p` |
| 1931 | 31 | 24, 25 | `Att_JINNCHUUWATARI`, `Att_JINNCHUUWATARI_EX` | `qcf+k` | `k` |
| 1946 | 46 | 18 | `Att_KUUCHUUNICHIRINSHOU` | `button_or_charge+p` | `p` |
| 1947 | 47 | 23 | `Att_KUUCHUUJINNCHUUWATARI` | `qcf+k` | `k` |

### Yang

| policy_action_id | slot | routines | handlers | macro_template | sub_action_group |
|---:|---:|---|---|---|---|
| 2020 | 20 | 19 | `Att_HADOUKEN` | `qcf_qcf+p` | `p` |
| 2021 | 21 | 20 | `Att_SLIDE_and_JUMP` | `qcf_qcf+p` | `p` |
| 2022 | 22 | 21 | `Att_TENSHINSENKYUUTAI` | `qcf_qcf+k` | `k` |
| 2028 | 28 | 22 | `Att_HADOUKEN` | `hcb_raw+k` | `k` |
| 2029 | 29 | 23 | `Att_PL10_MACH_SLIDE2` | `dp+k` | `k` |
| 2030 | 30 | 18 | `Att_SLIDE_and_JUMP` | `qcf+p` | `p` |
| 2031 | 31 | 17 | `Att_TENSHINSENKYUUTAI` | `qcf+k` | `k` |
| 2032 | 32 | 16 | `Att_HADOUKEN` | `qcb+p` | `p` |

### Ken

| policy_action_id | slot | routines | handlers | macro_template | sub_action_group |
|---:|---:|---|---|---|---|
| 2120 | 20 | 19 | `Att_SHOURYUUREPPA` | `qcf_qcf+p` | `p` |
| 2121 | 21 | 20 | `Att_SHOURYUUREPPA` | `qcf_qcf+k` | `k` |
| 2122 | 22 | 21 | `Att_SLIDE_and_JUMP` | `qcf_qcf+k` | `k` |
| 2128 | 28 | 17 | `Att_SHOURYUUKEN` | `dp+p` | `p` |
| 2129 | 29 | 16 | `Att_HADOUKEN` | `qcf+p` | `p` |
| 2130 | 30 | 18 | `Att_SENPUUKYAKU` | `qcb+k` | `k` |
| 2146 | 46 | 22 | `Att_KUUCHUUNICHIRINSHOU` | `qcb+k` | `k` |

### Sean

| policy_action_id | slot | routines | handlers | macro_template | sub_action_group |
|---:|---:|---|---|---|---|
| 2220 | 20 | 16 | `Att_HADOUKEN` | `qcf_qcf+p` | `p` |
| 2221 | 21 | 17 | `Att_SHOURYUUREPPA` | `qcf_qcf+p` | `p` |
| 2222 | 22 | 18 | `Att_SLIDE_and_JUMP` | `qcf_qcf+p` | `p` |
| 2228 | 28 | 22 | `Att_CHOUCHUURENGEKI` | `hcf_raw+p` | `p` |
| 2229 | 29 | 24 | `Att_SENPUUKYAKU` | `dp+p` | `p` |
| 2230 | 30 | 19, 25 | `Att_ABISEGERI`, `Att_HOMING_JUMP` | `qcf+k` | `k` |
| 2231 | 31 | 20 | `Att_CHOUCHUURENGEKI` | `qcb+p` | `p` |
| 2232 | 32 | 21 | `Att_SHOURYUUKEN` | `qcb+k` | `k` |

### Urien

| policy_action_id | slot | routines | handlers | macro_template | sub_action_group |
|---:|---:|---|---|---|---|
| 2320 | 20 | 20 | `Att_CHOUCHUURENGEKI` | `qcf_qcf+p` | `p` |
| 2321 | 21 | 21 | `Att_CHOUCHUURENGEKI` | `qcf_qcf+p` | `p` |
| 2322 | 22 | 22 | `Att_HADOUKEN` | `qcf_qcf+p` | `p` |
| 2328 | 28 | 23 | `Att_CHOUCHUURENGEKI` | `charge_b_f+k` | `k` |
| 2329 | 29 | 24, 17 | `Att_SLIDE_and_JUMP`, `Att_MOONSALT_KNEE_DROP2` | `charge_d_u+k` | `k` |
| 2330 | 30 | 16 | `Att_HADOUKEN` | `qcf+p` | `p` |
| 2331 | 31 | 19 | `Att_SENPUUKYAKU` | `charge_d_u+p` | `p` |

### Akuma

| policy_action_id | slot | routines | handlers | macro_template | sub_action_group |
|---:|---:|---|---|---|---|
| 2420 | 20 | 16 | `Att_HADOUKEN` | `qcf_qcf+p` | `p` |
| 2421 | 21 | 20 | `Att_SHOURYUUREPPA` | `qcf_qcf+p` | `p` |
| 2422 | 22 | 17 | `Att_SHOURYUUKEN` | `qcf_qcf+k` | `k` |
| 2424 | 24 | 24 | `Att_CHOUCHUURENGEKI` | `raging_demon_like+18/18/18/18` | `18/18/18/18` |
| 2425 | 25 | 26 | `Att_HADOUKEN` | `down_down_down+19/19/19/19` | `19/19/19/19` |
| 2428 | 28 | 23 | `Att_PL14_AT1` | `dp+19/19/23/23` | `19/19/23/23` |
| 2429 | 29 | 23 | `Att_PL14_AT1` | `back_down_db_raw+19/19/23/23` | `19/19/23/23` |
| 2430 | 30 | 17 | `Att_SHOURYUUKEN` | `dp+p` | `p` |
| 2431 | 31 | 16 | `Att_HADOUKEN` | `qcf+p` | `p` |
| 2432 | 32 | 18 | `Att_SENPUUKYAKU` | `qcb+k` | `k` |
| 2433 | 33 | 16 | `Att_HADOUKEN` | `reverse_qcb_raw+p` | `p` |
| 2434 | 34 | 21 | `Att_SLIDE_and_JUMP` | `f+k` | `k` |
| 2435 | 35 | 27 | `Att_PL14_AT3` | `dp+k` | `k` |
| 2438 | 38 | 25 | `Att_PL14_AT2` | `qcf_qcf+p` | `p` |
| 2439 | 39 | 19 | `Att_KUUCHUUJINNCHUUWATARI` | `qcf_qcf+k` | `k` |
| 2446 | 46 | 25 | `Att_PL14_AT2` | `qcf+p` | `p` |
| 2447 | 47 | 22 | `Att_KUUCHUUNICHIRINSHOU` | `qcb+k` | `k` |

### Chun-Li

| policy_action_id | slot | routines | handlers | macro_template | sub_action_group |
|---:|---:|---|---|---|---|
| 2520 | 20 | 18 | `Att_HADOUKEN` | `qcf_qcf+p` | `p` |
| 2521 | 21 | 20 | `Att_SLIDE_and_JUMP` | `qcf_qcf+k` | `k` |
| 2522 | 22 | 22 | `Att_SLIDE_and_JUMP` | `qcf_qcf+k` | `k` |
| 2528 | 28 | 16 | `Att_SENPUUKYAKU` | `charge_d_u+k` | `k` |
| 2529 | 29 | 17 | `Att_HADOUKEN2` | `n+k` | `k` |
| 2530 | 30 | 19 | `Att_HADOUKEN` | `hcf+p` | `p` |
| 2531 | 31 | 21 | `Att_SLIDE_and_JUMP` | `reverse_qcb_raw+k` | `k` |

### Makoto

| policy_action_id | slot | routines | handlers | macro_template | sub_action_group |
|---:|---:|---|---|---|---|
| 2620 | 20 | 17 | `Att_PL17_AT1` | `qcf_qcf+k` | `k` |
| 2621 | 21 | 19 | `Att_PL17_AT2` | `qcf_qcf+p` | `p` |
| 2622 | 22 | 18 | `Att_HADOUKEN2` | `qcf_qcf+p` | `p` |
| 2628 | 28 | 18 | `Att_HADOUKEN2` | `dp+p` | `p` |
| 2629 | 29 | 18 | `Att_HADOUKEN2` | `qcb+p` | `p` |
| 2630 | 30 | 16 | `Att_CHOUCHUURENGEKI` | `qcf+p` | `p` |
| 2631 | 31 | 16 | `Att_CHOUCHUURENGEKI` | `reverse_qcb_raw+k` | `k` |
| 2646 | 46 | 20 | `Att_KUUCHUUJINNCHUUWATARI` | `qcb+k` | `k` |

### Q

| policy_action_id | slot | routines | handlers | macro_template | sub_action_group |
|---:|---:|---|---|---|---|
| 2720 | 20 | 20 | `Att_SLIDE_and_JUMP` | `qcf_qcf+p` | `p` |
| 2721 | 21 | 21 | `Att_HADOUKEN2` | `qcf_qcf+p` | `p` |
| 2722 | 22 | 22 | `Att_HADOUKEN` | `qcf_qcf+p` | `p` |
| 2728 | 28 | 16 | `Att_SLIDE_and_JUMP` | `charge_b_f+p` | `p` |
| 2729 | 29 | 17 | `Att_SLIDE_and_JUMP` | `charge_b_f+k` | `k` |
| 2730 | 30 | 18 | `Att_HADOUKEN2` | `qcb+p` | `p` |
| 2731 | 31 | 19 | `Att_HADOUKEN2` | `reverse_qcb_raw+k` | `k` |
| 2732 | 32 | 23 | `Att_PL18_NINGENBAKUDAN` | `qcf+p` | `p` |
| 2733 | 33 | 24 | `Att_HADOUKEN` | `qcf+k` | `k` |

### Twelve

| policy_action_id | slot | routines | handlers | macro_template | sub_action_group |
|---:|---:|---|---|---|---|
| 2820 | 20 | 20 | `Att_HADOUKEN` | `qcf_qcf+p` | `p` |
| 2821 | 21 | 22 | `Att_METAMORPHOSE` | `qcf_qcf+p` | `p` |
| 2828 | 28 | 16 | `Att_HADOUKEN` | `qcb+p` | `p` |
| 2829 | 29 | 19 | `Att_HADOUKEN` | `qcf+p` | `p` |
| 2830 | 30 | 19 | `Att_HADOUKEN` | `qcf+k` | `k` |
| 2838 | 38 | 27 | `Att_SA__D_R_A` | `qcf_qcf+k` | `k` |
| 2846 | 46 | 17 | `Att_AIRDASH` | `triple_f+0/0/0/0` | `0/0/0/0` |
| 2847 | 47 | 18 | `Att_KUUCHUUHISSATU` | `qcb+k` | `k` |
| 2848 | 48 | 23 | `Att_AIR_A_X_E` | `qcb+p` | `p` |
| 2849 | 49 | 17 | `Att_AIRDASH` | `triple_b+0/0/0/0` | `0/0/0/0` |

### Remy

| policy_action_id | slot | routines | handlers | macro_template | sub_action_group |
|---:|---:|---|---|---|---|
| 2920 | 20 | 16 | `Att_HADOUKEN` | `qcf_qcf+p` | `p` |
| 2921 | 21 | 20 | `Att_HADOUKEN` | `qcf_qcf+k` | `k` |
| 2922 | 22 | 17 | `Att_PL20_AT1` | `qcf_qcf+k` | `k` |
| 2928 | 28 | 17 | `Att_PL20_AT1` | `charge_d_u+k` | `k` |
| 2929 | 29 | 16 | `Att_HADOUKEN` | `charge_b_f+p` | `p` |
| 2930 | 30 | 16 | `Att_HADOUKEN` | `charge_b_f+k` | `k` |
| 2931 | 31 | 18 | `Att_PL20_AT2` | `qcb+k` | `k` |

## Open Validation Items

- Decode `button_or_charge` rows into concrete macros before live enablement.
- Give source-specific handlers official move aliases where useful for analysis.
- Split grouped `p`/`k` rows into concrete strength rows only when a curriculum
  needs them.
- Add official action-name aliases for transition analysis output; the wire
  protocol now carries requested/executed policy action ID, sub-action ID, and
  action step fields.
- Keep `back` and `guard` as separate universal policy actions before training
  a defensive DQN action head.
