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
- Keep `back` and `guard` as separate universal policy actions before training
  a defensive DQN action head.
