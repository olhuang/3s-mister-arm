#!/usr/bin/env python3
"""Minimal UDP server for Milestone 2/3 RL hello/ack, ping/pong, and remote-action probing."""

from __future__ import annotations

import argparse
import collections
import json
import math
import os
import random
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field

import rl_evidence


MAGIC = 0x33524C41
PACKET_VERSION = 1
PROTOCOL_VERSION = 4
TYPE_HELLO = 1
TYPE_ACK = 2
TYPE_PING = 3
TYPE_PONG = 4
TYPE_OBS = 5
PACKET = struct.Struct("<IHHQIIQ")
ACTION_PACKET = struct.Struct("<IHHQQIIIHHHHI")
OBS_HEADER = struct.Struct("<IHHQQIIIIHHI")
OBS_SPACING_PAYLOAD = struct.Struct("<HHhhhhhhhhHHHHBBBBBBBBBBBBBBBBhhhh")
OBS_SPACING_PAYLOAD_VERSION = 6
TRANSITION_BATCH_HEADER = struct.Struct("<IHHQQIII")
TRANSITION_BATCH_ACK = struct.Struct("<IHHQQII")
ACTION_SET_VERSION = 5
_warned_stripped_feature_sets: set[tuple[str, tuple[str, ...]]] = set()

RL_MOVE_NEUTRAL = 0x0000
RL_MOVE_UP = 0x0001
RL_MOVE_UP_FORWARD = 0x0006
RL_MOVE_DOWN = 0x0002
RL_MOVE_BACK = 0x0003
RL_MOVE_FORWARD = 0x0004
RL_MOVE_UP_BACK = 0x0005
RL_MOVE_DOWN_BACK = 0x0007
RL_MOVE_DOWN_FORWARD = 0x0008

BTN_LP = 0x0010
BTN_MP = 0x0020
BTN_HP = 0x0040
BTN_LK = 0x0100
BTN_MK = 0x0200
BTN_HK = 0x0400

RL_POLICY_ACTION_NEUTRAL = 0
RL_POLICY_ACTION_WALK = 1
RL_POLICY_ACTION_JUMP = 3
RL_POLICY_ACTION_GUARD = 4
RL_POLICY_ACTION_STAND_NORMAL = 6
RL_POLICY_ACTION_NORMAL = RL_POLICY_ACTION_STAND_NORMAL
RL_POLICY_ACTION_COMMAND_NORMAL = 7
RL_POLICY_ACTION_THROW = 8
RL_POLICY_ACTION_JUMP_ATTACK_FORWARD = 12
RL_POLICY_ACTION_JUMP_ATTACK_NEUTRAL = 13
RL_POLICY_ACTION_JUMP_ATTACK_BACK = 14
RL_POLICY_ACTION_CROUCH_NORMAL = 15
RL_POLICY_ACTION_AIR_NORMAL = 16
RL_POLICY_ACTION_RYU_SHINKUU_HADOUKEN = 1220
RL_POLICY_ACTION_RYU_DENJIN_HADOUKEN = 1221
RL_POLICY_ACTION_RYU_SHIN_SHORYUKEN = 1222
RL_POLICY_ACTION_RYU_SHORYUKEN = 1228
RL_POLICY_ACTION_RYU_FIREBALL = 1229
RL_POLICY_ACTION_RYU_TATSU = 1230
RL_POLICY_ACTION_RYU_JOUDAN = 1231
RL_POLICY_ACTION_RYU_AIR_TATSU = 1246
RL_POLICY_ACTION_KEN_SHORYUREPPA = 2120
RL_POLICY_ACTION_KEN_SHINRYUKEN = 2121
RL_POLICY_ACTION_KEN_SHIPPU_JINRAIKYAKU = 2122
RL_POLICY_ACTION_KEN_SHORYUKEN = 2128
RL_POLICY_ACTION_KEN_FIREBALL = 2129
RL_POLICY_ACTION_KEN_TATSU = 2130
RL_POLICY_ACTION_KEN_AIR_TATSU = 2146

RL_POLICY_SUB_NONE = 0
RL_POLICY_SUB_LP = 1
RL_POLICY_SUB_MP = 2
RL_POLICY_SUB_HP = 3
RL_POLICY_SUB_LK = 4
RL_POLICY_SUB_MK = 5
RL_POLICY_SUB_HK = 6
RL_POLICY_SUB_FORWARD = 13
RL_POLICY_SUB_BACK = 14
RL_POLICY_SUB_NEUTRAL_DIRECTION = 15
RL_POLICY_SUB_UP_FORWARD = 16
RL_POLICY_SUB_UP_BACK = 17
RL_POLICY_SUB_STAND = 20
RL_POLICY_SUB_CROUCH = 21

RL_POLICY_BUTTONS = (
    ("lp", BTN_LP, RL_POLICY_SUB_LP),
    ("mp", BTN_MP, RL_POLICY_SUB_MP),
    ("hp", BTN_HP, RL_POLICY_SUB_HP),
    ("lk", BTN_LK, RL_POLICY_SUB_LK),
    ("mk", BTN_MK, RL_POLICY_SUB_MK),
    ("hk", BTN_HK, RL_POLICY_SUB_HK),
)
RL_POLICY_JUMP_STARTS = (
    ("forward", RL_MOVE_UP_FORWARD, RL_POLICY_SUB_UP_FORWARD),
    ("neutral", RL_MOVE_UP, RL_POLICY_SUB_NEUTRAL_DIRECTION),
    ("back", RL_MOVE_UP_BACK, RL_POLICY_SUB_UP_BACK),
)
STAND_NORMAL_ACTION_NAMES = tuple(f"stand-{button}" for button, _, _ in RL_POLICY_BUTTONS)
CROUCH_NORMAL_ACTION_NAMES = tuple(f"crouch-{button}" for button, _, _ in RL_POLICY_BUTTONS)
FIREBALL_ACTIONS = (
    ("fireball-lp", BTN_LP, RL_POLICY_SUB_LP),
    ("fireball-mp", BTN_MP, RL_POLICY_SUB_MP),
    ("fireball-hp", BTN_HP, RL_POLICY_SUB_HP),
)
FIREBALL_ACTION_NAMES = tuple(action for action, _, _ in FIREBALL_ACTIONS)
SHORYUKEN_ACTIONS = (
    ("shoryuken-lp", BTN_LP, RL_POLICY_SUB_LP),
    ("shoryuken-mp", BTN_MP, RL_POLICY_SUB_MP),
    ("shoryuken-hp", BTN_HP, RL_POLICY_SUB_HP),
)
SHORYUKEN_ACTION_NAMES = tuple(action for action, _, _ in SHORYUKEN_ACTIONS)
TATSU_ACTIONS = (
    ("tatsu-lk", BTN_LK, RL_POLICY_SUB_LK),
    ("tatsu-mk", BTN_MK, RL_POLICY_SUB_MK),
    ("tatsu-hk", BTN_HK, RL_POLICY_SUB_HK),
)
TATSU_ACTION_NAMES = tuple(action for action, _, _ in TATSU_ACTIONS)
JUMP_START_ACTION_NAMES = tuple(f"jump-{direction}-start" for direction, _, _ in RL_POLICY_JUMP_STARTS)
JUMP_START_ACTION_WIRES = {
    f"jump-{direction}-start": move
    for direction, move, _ in RL_POLICY_JUMP_STARTS
}
AIR_NORMAL_ACTION_NAMES = tuple(f"air-{button}" for button, _, _ in RL_POLICY_BUTTONS)
AIR_NORMAL_ACTION_WIRES = {f"air-{button}": wire for button, wire, _ in RL_POLICY_BUTTONS}
SCRIPTED_POLICY_CHOICES = (
    "forward",
    "back",
    "guard",
    "guard-stand",
    "guard-crouch",
    "hp",
    *STAND_NORMAL_ACTION_NAMES,
    "forward-hp",
    *CROUCH_NORMAL_ACTION_NAMES,
    *FIREBALL_ACTION_NAMES,
    "fireball",
    "ryu-fireball",
    "throw",
    "tatsu",
    *TATSU_ACTION_NAMES,
    "shoryuken",
    *SHORYUKEN_ACTION_NAMES,
    *JUMP_START_ACTION_NAMES,
    *AIR_NORMAL_ACTION_NAMES,
)
MODEL_POLICY_CHOICES = (
    "tabular",
    "dqn",
    "bc",
    "actor-critic",
    "tactical",
)
POLICY_CHOICES = SCRIPTED_POLICY_CHOICES + MODEL_POLICY_CHOICES
GUARD_MACRO_DECISION_STEPS = 6
DEMO_EXECUTION_SOURCES = frozenset({4, 5})
TRANSITION_SCHEMA_VERSION = 10
SUPPORTED_TRANSITION_SCHEMA_VERSIONS = frozenset({5, 6, 7, 8, 9, 10})
TRAINING_MODE_TYPES = frozenset({3, 4})
TRAINING_ACTION_SOURCES = ("auto", "policy", "input", "engine", "prefer-engine")

TABULAR_ACTION_NAMES = (
    "forward",
    "back",
    "guard-stand",
    "guard-crouch",
    *STAND_NORMAL_ACTION_NAMES,
    "forward-hp",
    *CROUCH_NORMAL_ACTION_NAMES,
    *FIREBALL_ACTION_NAMES,
    "throw",
    *JUMP_START_ACTION_NAMES,
    *AIR_NORMAL_ACTION_NAMES,
    *SHORYUKEN_ACTION_NAMES,
    *TATSU_ACTION_NAMES,
)
TABULAR_ACTION_WIRES = {
    "neutral": RL_MOVE_NEUTRAL,
    "forward": RL_MOVE_FORWARD,
    "back": RL_MOVE_BACK,
    "forward-hp": RL_MOVE_FORWARD | BTN_HP,
    "throw": RL_MOVE_FORWARD | BTN_LP | BTN_LK,
}
DQN_MOVEMENT_GUARD_ACTIONS = frozenset({"forward", "back", "guard-stand", "guard-crouch"})
DQN_JUMP_START_ACTIONS = frozenset(JUMP_START_ACTION_NAMES)
DQN_AIR_ATTACK_ACTIONS = frozenset(AIR_NORMAL_ACTION_NAMES)
DQN_VALID_ACTION_MASK_MODES = ("off", "self-routine-v1", "action-start-v1")
DQN_VALID_ACTION_MASK_CLI_MODES = ("auto", *DQN_VALID_ACTION_MASK_MODES)
TABULAR_ACTION_WIRES.update({f"stand-{name}": wire for name, wire, _ in RL_POLICY_BUTTONS})
TABULAR_ACTION_WIRES.update({f"crouch-{name}": RL_MOVE_DOWN | wire for name, wire, _ in RL_POLICY_BUTTONS})
TABULAR_ACTION_WIRES.update(JUMP_START_ACTION_WIRES)
TABULAR_ACTION_NAMES_BY_WIRE = {
    wire: name for name, wire in TABULAR_ACTION_WIRES.items() if name != "neutral"
}
TABULAR_ACTION_NAMES_BY_WIRE[RL_MOVE_FORWARD | BTN_LP] = "fireball-lp"
TABULAR_ACTION_NAMES_BY_WIRE.update({RL_MOVE_DOWN_FORWARD | wire: action for action, wire, _ in SHORYUKEN_ACTIONS})
TABULAR_ACTION_NAMES_BY_WIRE.update({RL_MOVE_BACK | wire: action for action, wire, _ in TATSU_ACTIONS})
TABULAR_DEFAULT_ACTIONS = TABULAR_ACTION_NAMES

TABULAR_ACTION_ALIASES = {
    "guard": "guard-stand",
    "hp": "stand-hp",
    "fireball": "fireball-lp",
    "ryu-fireball": "fireball-lp",
    "shoryuken": "shoryuken-hp",
    "tatsu": "tatsu-lk",
    "jump-forward": "jump-forward-start",
    "jump-neutral": "jump-neutral-start",
    "jump-back": "jump-back-start",
}

POLICY_ACTION_META_BY_NAME = {
    "neutral": (RL_POLICY_ACTION_NEUTRAL, RL_POLICY_SUB_NONE),
    "forward": (RL_POLICY_ACTION_WALK, RL_POLICY_SUB_FORWARD),
    "back": (RL_POLICY_ACTION_WALK, RL_POLICY_SUB_BACK),
    "guard": (RL_POLICY_ACTION_GUARD, RL_POLICY_SUB_STAND),
    "guard-stand": (RL_POLICY_ACTION_GUARD, RL_POLICY_SUB_STAND),
    "guard-crouch": (RL_POLICY_ACTION_GUARD, RL_POLICY_SUB_CROUCH),
    "hp": (RL_POLICY_ACTION_STAND_NORMAL, RL_POLICY_SUB_HP),
    "forward-hp": (RL_POLICY_ACTION_COMMAND_NORMAL, RL_POLICY_SUB_HP),
    "throw": (RL_POLICY_ACTION_THROW, RL_POLICY_SUB_FORWARD),
    "fireball-lp": (RL_POLICY_ACTION_RYU_FIREBALL, RL_POLICY_SUB_LP),
    "fireball": (RL_POLICY_ACTION_RYU_FIREBALL, RL_POLICY_SUB_LP),
    "fireball-mp": (RL_POLICY_ACTION_RYU_FIREBALL, RL_POLICY_SUB_MP),
    "fireball-hp": (RL_POLICY_ACTION_RYU_FIREBALL, RL_POLICY_SUB_HP),
    "ryu-fireball": (RL_POLICY_ACTION_RYU_FIREBALL, RL_POLICY_SUB_LP),
    "tatsu": (RL_POLICY_ACTION_RYU_TATSU, RL_POLICY_SUB_LK),
    "shoryuken": (RL_POLICY_ACTION_RYU_SHORYUKEN, RL_POLICY_SUB_HP),
}
POLICY_ACTION_META_BY_NAME.update(
    {action: (RL_POLICY_ACTION_RYU_SHORYUKEN, sub_action) for action, _, sub_action in SHORYUKEN_ACTIONS}
)
POLICY_ACTION_META_BY_NAME.update(
    {action: (RL_POLICY_ACTION_RYU_TATSU, sub_action) for action, _, sub_action in TATSU_ACTIONS}
)
POLICY_ACTION_META_BY_NAME.update(
    {f"stand-{name}": (RL_POLICY_ACTION_STAND_NORMAL, sub_action) for name, _, sub_action in RL_POLICY_BUTTONS}
)
POLICY_ACTION_META_BY_NAME.update(
    {f"crouch-{name}": (RL_POLICY_ACTION_CROUCH_NORMAL, sub_action) for name, _, sub_action in RL_POLICY_BUTTONS}
)
POLICY_ACTION_META_BY_NAME.update(
    {f"jump-{direction}-start": (RL_POLICY_ACTION_JUMP, sub_action) for direction, _, sub_action in RL_POLICY_JUMP_STARTS}
)
POLICY_ACTION_META_BY_NAME.update(
    {f"air-{name}": (RL_POLICY_ACTION_AIR_NORMAL, sub_action) for name, _, sub_action in RL_POLICY_BUTTONS}
)

TABULAR_ACTION_NAMES_BY_POLICY_META = {
    (RL_POLICY_ACTION_WALK, RL_POLICY_SUB_FORWARD): "forward",
    (RL_POLICY_ACTION_WALK, RL_POLICY_SUB_BACK): "back",
    (RL_POLICY_ACTION_GUARD, RL_POLICY_SUB_STAND): "guard-stand",
    (RL_POLICY_ACTION_GUARD, RL_POLICY_SUB_CROUCH): "guard-crouch",
    (RL_POLICY_ACTION_COMMAND_NORMAL, RL_POLICY_SUB_HP): "forward-hp",
    (RL_POLICY_ACTION_THROW, RL_POLICY_SUB_FORWARD): "throw",
    (RL_POLICY_ACTION_THROW, RL_POLICY_SUB_NONE): "throw",
    (RL_POLICY_ACTION_RYU_SHINKUU_HADOUKEN, RL_POLICY_SUB_NONE): "shinkuu-hadouken",
    (RL_POLICY_ACTION_RYU_DENJIN_HADOUKEN, RL_POLICY_SUB_NONE): "denjin-hadouken",
    (RL_POLICY_ACTION_RYU_SHIN_SHORYUKEN, RL_POLICY_SUB_NONE): "shin-shoryuken",
    (RL_POLICY_ACTION_RYU_FIREBALL, RL_POLICY_SUB_LP): "fireball-lp",
    (RL_POLICY_ACTION_RYU_FIREBALL, RL_POLICY_SUB_MP): "fireball-mp",
    (RL_POLICY_ACTION_RYU_FIREBALL, RL_POLICY_SUB_HP): "fireball-hp",
    (RL_POLICY_ACTION_RYU_SHORYUKEN, RL_POLICY_SUB_LP): "shoryuken-lp",
    (RL_POLICY_ACTION_RYU_SHORYUKEN, RL_POLICY_SUB_MP): "shoryuken-mp",
    (RL_POLICY_ACTION_RYU_SHORYUKEN, RL_POLICY_SUB_HP): "shoryuken-hp",
    (RL_POLICY_ACTION_RYU_TATSU, RL_POLICY_SUB_LK): "tatsu-lk",
    (RL_POLICY_ACTION_RYU_TATSU, RL_POLICY_SUB_MK): "tatsu-mk",
    (RL_POLICY_ACTION_RYU_TATSU, RL_POLICY_SUB_HK): "tatsu-hk",
    (RL_POLICY_ACTION_RYU_JOUDAN, RL_POLICY_SUB_LK): "joudan-lk",
    (RL_POLICY_ACTION_RYU_JOUDAN, RL_POLICY_SUB_MK): "joudan-mk",
    (RL_POLICY_ACTION_RYU_JOUDAN, RL_POLICY_SUB_HK): "joudan-hk",
    (RL_POLICY_ACTION_RYU_AIR_TATSU, RL_POLICY_SUB_LK): "air-tatsu-lk",
    (RL_POLICY_ACTION_RYU_AIR_TATSU, RL_POLICY_SUB_MK): "air-tatsu-mk",
    (RL_POLICY_ACTION_RYU_AIR_TATSU, RL_POLICY_SUB_HK): "air-tatsu-hk",
    (RL_POLICY_ACTION_KEN_SHORYUREPPA, RL_POLICY_SUB_NONE): "shoryureppa",
    (RL_POLICY_ACTION_KEN_SHINRYUKEN, RL_POLICY_SUB_NONE): "shinryuken",
    (RL_POLICY_ACTION_KEN_SHIPPU_JINRAIKYAKU, RL_POLICY_SUB_NONE): "shippu-jinraikyaku",
    (RL_POLICY_ACTION_KEN_FIREBALL, RL_POLICY_SUB_LP): "fireball-lp",
    (RL_POLICY_ACTION_KEN_FIREBALL, RL_POLICY_SUB_MP): "fireball-mp",
    (RL_POLICY_ACTION_KEN_FIREBALL, RL_POLICY_SUB_HP): "fireball-hp",
    (RL_POLICY_ACTION_KEN_SHORYUKEN, RL_POLICY_SUB_LP): "shoryuken-lp",
    (RL_POLICY_ACTION_KEN_SHORYUKEN, RL_POLICY_SUB_MP): "shoryuken-mp",
    (RL_POLICY_ACTION_KEN_SHORYUKEN, RL_POLICY_SUB_HP): "shoryuken-hp",
    (RL_POLICY_ACTION_KEN_TATSU, RL_POLICY_SUB_LK): "tatsu-lk",
    (RL_POLICY_ACTION_KEN_TATSU, RL_POLICY_SUB_MK): "tatsu-mk",
    (RL_POLICY_ACTION_KEN_TATSU, RL_POLICY_SUB_HK): "tatsu-hk",
    (RL_POLICY_ACTION_KEN_AIR_TATSU, RL_POLICY_SUB_LK): "air-tatsu-lk",
    (RL_POLICY_ACTION_KEN_AIR_TATSU, RL_POLICY_SUB_MK): "air-tatsu-mk",
    (RL_POLICY_ACTION_KEN_AIR_TATSU, RL_POLICY_SUB_HK): "air-tatsu-hk",
}
TABULAR_ACTION_NAMES_BY_POLICY_META.update(
    {(RL_POLICY_ACTION_STAND_NORMAL, sub_action): f"stand-{name}" for name, _, sub_action in RL_POLICY_BUTTONS}
)
TABULAR_ACTION_NAMES_BY_POLICY_META.update(
    {(RL_POLICY_ACTION_CROUCH_NORMAL, sub_action): f"crouch-{name}" for name, _, sub_action in RL_POLICY_BUTTONS}
)
TABULAR_ACTION_NAMES_BY_POLICY_META.update(
    {(RL_POLICY_ACTION_JUMP, sub_action): f"jump-{direction}-start" for direction, _, sub_action in RL_POLICY_JUMP_STARTS}
)
TABULAR_ACTION_NAMES_BY_POLICY_META.update(
    {(RL_POLICY_ACTION_AIR_NORMAL, sub_action): f"air-{name}" for name, _, sub_action in RL_POLICY_BUTTONS}
)

DQN_BASE_FEATURE_NAMES = (
    "obs_abs_dx",
    "obs_abs_dy",
    "obs_self_stage_back_edge_dist",
    "obs_opp_stage_back_edge_dist",
    "obs_self_corner_state",
    "obs_opp_corner_state",
    "obs_corner_pressure_state",
    "obs_range_threat_bucket",
    "obs_opp_in_front",
    "obs_opp_routine_attack_state",
    "obs_self_airborne",
    "obs_self_jump_phase",
    "obs_self_ground_action_start_allowed",
    "obs_self_jump_start_allowed",
    "obs_self_air_attack_allowed",
    "obs_projectile_active",
    "obs_projectile_owner",
    "obs_projectile_rel_x",
    "obs_projectile_rel_y",
    "obs_projectile_vel_x",
    "obs_projectile_time_to_self",
)
DQN_OPP_ROUTINE_1_VALUES = (0, 1, 2, 3, 4)
DQN_OPP_ROUTINE_2_VALUES = (0, 1, 3, 4, 5, 6, 7, 8, 12, 13, 16, 17, 18, 19, 21, 24, 28, 32, 36, 37)
DQN_OPP_ROUTINE_FEATURE_NAMES = tuple(
    f"obs_opp_routine_1_is_{value}" for value in DQN_OPP_ROUTINE_1_VALUES
) + tuple(f"obs_opp_routine_2_is_{value}" for value in DQN_OPP_ROUTINE_2_VALUES)
DQN_SELF_ROUTINE_1_VALUES = (0, 1, 2, 3, 4)
DQN_SELF_ROUTINE_2_VALUES = (0, 1, 3, 4, 5, 6, 7, 8, 12, 13, 16, 17, 18, 19, 21, 22, 23, 24, 28, 32, 36, 37)
DQN_SELF_ROUTINE_FEATURE_NAMES = tuple(
    f"obs_self_routine_1_is_{value}" for value in DQN_SELF_ROUTINE_1_VALUES
) + tuple(f"obs_self_routine_2_is_{value}" for value in DQN_SELF_ROUTINE_2_VALUES)
DQN_FEATURE_NAMES = (
    DQN_BASE_FEATURE_NAMES
    + ("obs_self_routine_attack_state",)
    + DQN_OPP_ROUTINE_FEATURE_NAMES
    + DQN_SELF_ROUTINE_FEATURE_NAMES
)
DQN_FEATURE_SCALES = {
    "obs_abs_dx": 384.0,
    "obs_abs_dy": 192.0,
    "obs_self_stage_back_edge_dist": 864.0,
    "obs_opp_stage_back_edge_dist": 864.0,
    "obs_self_corner_state": 2.0,
    "obs_opp_corner_state": 2.0,
    "obs_corner_pressure_state": 2.0,
    "obs_range_threat_bucket": 2.0,
    "obs_self_front_edge_dist": 384.0,
    "obs_self_back_edge_dist": 384.0,
    "obs_opp_front_edge_dist": 384.0,
    "obs_opp_back_edge_dist": 384.0,
    "obs_opp_in_front": 1.0,
    "obs_opp_routine_attack_state": 1.0,
    "obs_self_airborne": 1.0,
    "obs_self_jump_phase": 3.0,
    "obs_self_ground_action_start_allowed": 1.0,
    "obs_self_jump_start_allowed": 1.0,
    "obs_self_air_attack_allowed": 1.0,
    "obs_projectile_active": 1.0,
    "obs_projectile_owner": 2.0,
    "obs_projectile_rel_x": 384.0,
    "obs_projectile_rel_y": 256.0,
    "obs_projectile_vel_x": 16.0,
    "obs_projectile_time_to_self": 120.0,
    "obs_self_routine_attack_state": 1.0,
}
DQN_FEATURE_SCALES.update({name: 1.0 for name in DQN_OPP_ROUTINE_FEATURE_NAMES})
DQN_FEATURE_SCALES.update({name: 1.0 for name in DQN_SELF_ROUTINE_FEATURE_NAMES})


@dataclass(frozen=True)
class ActorModel:
    version: int
    policy: str
    source: str
    metadata: dict[str, object] = field(default_factory=dict)
    q_table: dict[str, dict[str, float]] = field(default_factory=dict)
    q_counts: dict[str, dict[str, int]] = field(default_factory=dict)
    dqn_model: dict[str, object] = field(default_factory=dict)
    actor_critic_model: dict[str, object] = field(default_factory=dict)
    tactical_intent_model: dict[str, object] = field(default_factory=dict)
    actions: tuple[str, ...] = TABULAR_DEFAULT_ACTIONS
    epsilon: float = 0.0
    fallback_policy: str = "hp"
    updated_rows: int = 0
    min_action_count: int = 1


@dataclass(frozen=True)
class ActorModelStatus:
    active: ActorModel
    last_published_version: int
    last_loaded_version: int
    publish_count: int
    load_count: int


@dataclass(frozen=True)
class PolicyActionFrame:
    action_wire: int
    policy_action_id: int
    policy_sub_action_id: int
    policy_action_step: int = 0


@dataclass(frozen=True)
class ActionSelection:
    name: str | None
    step: int
    source: str


@dataclass(frozen=True)
class DQNSupportPriorConfig:
    min_action_count: int = 0
    count_penalty: float = 0.0
    negative_mean_penalty: float = 0.0
    exempt_actions: frozenset[str] = field(default_factory=frozenset)

    @property
    def enabled(self) -> bool:
        return (
            (self.min_action_count > 0 and self.count_penalty > 0.0)
            or self.negative_mean_penalty > 0.0
        )

    def label(self) -> str:
        if not self.enabled:
            return "off"
        exempt = ",".join(sorted(self.exempt_actions)) if self.exempt_actions else "none"
        return (
            f"min:{self.min_action_count}"
            f"/count_penalty:{self.count_penalty:.3f}"
            f"/negative_mean:{self.negative_mean_penalty:.3f}"
            f"/exempt:{exempt}"
        )


@dataclass(frozen=True)
class DQNValidActionMaskConfig:
    mode: str = "off"

    @property
    def enabled(self) -> bool:
        return self.mode != "off"

    def label(self) -> str:
        return self.mode


@dataclass(frozen=True)
class BCInferenceConfig:
    temperature: float = 0.8
    top_k: int = 3
    deterministic_danger: bool = False
    danger_max_time_to_self: int = 12
    danger_max_abs_dx: int = 144
    danger_max_abs_y: int = 96

    def label(self) -> str:
        danger = "on" if self.deterministic_danger else "off"
        return (
            f"temperature:{self.temperature:.3f}"
            f"/top_k:{self.top_k}"
            f"/danger:{danger}"
            f"/danger_t<={self.danger_max_time_to_self}"
            f"/danger_dx<={self.danger_max_abs_dx}"
            f"/danger_abs_y<={self.danger_max_abs_y}"
        )


@dataclass(frozen=True)
class ActorCriticInferenceConfig:
    temperature: float = 0.8
    top_k: int = 8
    top_p: float = 0.0

    def label(self) -> str:
        top_p = "off" if self.top_p <= 0.0 or self.top_p >= 1.0 else f"{self.top_p:.3f}"
        return f"temperature:{self.temperature:.3f}/top_k:{self.top_k}/top_p:{top_p}"


@dataclass(frozen=True)
class ActorCriticSpacingPriorConfig:
    enabled: bool = False
    close_max_abs_dx: int = 64
    poke_max_abs_dx: int = 120
    very_far_min_abs_dx: int = 220
    forward_bonus: float = 0.70
    back_penalty: float = 0.80
    far_guard_penalty: float = 0.25
    close_attack_far_penalty: float = 0.75
    shoryuken_far_penalty: float = 1.20
    fireball_bonus: float = 0.35
    fireball_min_abs_dx: int = 96
    fireball_max_abs_dx: int = 280
    threat_suppress_max_time_to_self: int = 12
    threat_suppress_max_abs_dx: int = 144
    threat_suppress_max_abs_y: int = 96
    threat_attack_max_abs_dx: int = 160
    threat_guard_bonus: float = 0.90
    threat_back_bonus: float = 0.45
    threat_forward_penalty: float = 1.10
    threat_attack_penalty: float = 0.75

    def label(self) -> str:
        if not self.enabled:
            return "off"
        return (
            f"close<={self.close_max_abs_dx}"
            f"/poke<={self.poke_max_abs_dx}"
            f"/very_far>={self.very_far_min_abs_dx}"
            f"/forward+{self.forward_bonus:.3f}"
            f"/back-{self.back_penalty:.3f}"
            f"/guard-{self.far_guard_penalty:.3f}"
            f"/close_attack-{self.close_attack_far_penalty:.3f}"
            f"/dp-{self.shoryuken_far_penalty:.3f}"
            f"/fireball+{self.fireball_bonus:.3f}@{self.fireball_min_abs_dx}-{self.fireball_max_abs_dx}"
            f"/threat_guard+{self.threat_guard_bonus:.3f}"
            f"/threat_forward-{self.threat_forward_penalty:.3f}"
        )


@dataclass(frozen=True)
class TacticalPolicyConfig:
    close_max_abs_dx: int = 64
    poke_max_abs_dx: int = 120
    fireball_max_abs_dx: int = 260
    too_far_min_abs_dx: int = 220
    corner_edge_max_dist: int = 48
    incoming_projectile_max_time_to_self: int = 18
    incoming_projectile_max_dx: int = 220
    incoming_projectile_max_abs_y: int = 96
    jump_in_max_abs_dx: int = 128
    threat_attack_max_abs_dx: int = 144
    valid_action_mask_mode: str = "action-start-v1"

    def label(self) -> str:
        return (
            f"close<={self.close_max_abs_dx}"
            f"/poke<={self.poke_max_abs_dx}"
            f"/fireball<={self.fireball_max_abs_dx}"
            f"/too_far>={self.too_far_min_abs_dx}"
            f"/proj_t<={self.incoming_projectile_max_time_to_self}"
            f"/proj_dx<={self.incoming_projectile_max_dx}"
            f"/threat_dx<={self.threat_attack_max_abs_dx}"
            f"/mask:{self.valid_action_mask_mode}"
        )


@dataclass(frozen=True)
class TacticalPolicyDecision:
    spacing_bucket: str
    corner_context: str
    self_phase: str
    opponent_phase: str
    threat_type: str
    opportunity_type: str
    recommended_intent: str
    intent_reason: str
    label_confidence: str
    action_name: str
    intent_source: str = "heuristic"


@dataclass(frozen=True)
class DQNProjectileTimingPriorConfig:
    enabled: bool = False
    min_time_to_self: int = 0
    urgent_max_time_to_self: int = 6
    borderline_max_time_to_self: int = 12
    urgent_jump_penalty: float = 0.05
    borderline_jump_penalty: float = 0.03
    early_min_time_to_self: int = 31
    early_max_time_to_self: int = 48
    early_jump_penalty: float = 0.0
    threat_max_dx: int = 240
    threat_max_abs_y: int = 96

    def label(self) -> str:
        if not self.enabled:
            return "off"
        penalties = [
            f"{self.min_time_to_self}-{self.urgent_max_time_to_self}={self.urgent_jump_penalty:.3f}",
            (
                f"{self.urgent_max_time_to_self + 1}-{self.borderline_max_time_to_self}"
                f"={self.borderline_jump_penalty:.3f}"
            ),
        ]
        if self.early_jump_penalty > 0.0:
            penalties.append(
                f"{self.early_min_time_to_self}-{self.early_max_time_to_self}"
                f"={self.early_jump_penalty:.3f}"
            )
        return (
            f"jump_penalty:{','.join(penalties)}"
            f"/dx<={self.threat_max_dx}/abs_y<={self.threat_max_abs_y}"
        )


@dataclass(frozen=True)
class DQNShoryukenContextPriorConfig:
    enabled: bool = False
    penalty: float = 0.04
    min_abs_dx: int = 24
    max_abs_dx: int = 150
    opp_air_routine_min: int = 18
    opp_air_routine_max: int = 26
    far_min_abs_dx: int = 0
    far_extra_penalty: float = 0.0
    far_block: bool = False

    def label(self) -> str:
        if not self.enabled:
            return "off"
        label = (
            f"penalty:{self.penalty:.3f}"
            f"/dx:{self.min_abs_dx}-{self.max_abs_dx}"
            f"/opp_r2:{self.opp_air_routine_min}-{self.opp_air_routine_max}"
        )
        if self.far_extra_penalty > 0.0:
            label += f"/far_dx>={self.far_min_abs_dx}+{self.far_extra_penalty:.3f}"
        if self.far_block:
            label += f"/far_block_dx>={self.far_min_abs_dx}"
        return label


@dataclass(frozen=True)
class DQNGroundNormalContextPriorConfig:
    enabled: bool = False
    penalty: float = 0.04
    close_max_abs_dx: int = 48
    poke_max_abs_dx: int = 120

    def label(self) -> str:
        if not self.enabled:
            return "off"
        return (
            f"penalty:{self.penalty:.3f}"
            f"/close_dx<={self.close_max_abs_dx}"
            f"/poke_dx<={self.poke_max_abs_dx}"
        )


@dataclass(frozen=True)
class DQNFireballZoningPriorConfig:
    enabled: bool = False
    bonus: float = 0.03
    min_abs_dx: int = 120
    max_abs_dx: int = 260

    def label(self) -> str:
        if not self.enabled:
            return "off"
        return f"bonus:{self.bonus:.3f}/dx:{self.min_abs_dx}-{self.max_abs_dx}"


@dataclass(frozen=True)
class DQNThreatDefensePriorConfig:
    enabled: bool = False
    guard_bonus: float = 0.03
    back_bonus: float = 0.02
    unsafe_penalty: float = 0.0
    max_abs_dx: int = 144
    contact_sustain: bool = False

    def label(self) -> str:
        if not self.enabled:
            return "off"
        return (
            f"guard:{self.guard_bonus:.3f}"
            f"/back:{self.back_bonus:.3f}"
            f"/unsafe:{self.unsafe_penalty:.3f}"
            f"/dx<={self.max_abs_dx}"
            f"/contact:{int(self.contact_sustain)}"
        )


@dataclass
class TimingBucketStats:
    rows: int = 0
    done: int = 0
    reward_positive: int = 0
    reward_negative: int = 0
    reward_zero: int = 0
    fallback_rows: int = 0


@dataclass
class PolicyBucketStats:
    rows: int = 0
    done: int = 0
    reward_positive: int = 0
    reward_negative: int = 0
    reward_zero: int = 0
    fallback_rows: int = 0


def _coerce_action_names(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return TABULAR_DEFAULT_ACTIONS
    actions: list[str] = []
    for item in value:
        name = canonical_tabular_action_name(str(item))
        if name is not None and name not in actions:
            actions.append(name)
    return tuple(actions) or TABULAR_DEFAULT_ACTIONS


def parse_action_names(value: str, *, option_name: str = "--actions") -> tuple[str, ...]:
    if not value.strip():
        return TABULAR_DEFAULT_ACTIONS
    actions: list[str] = []
    invalid: list[str] = []
    for raw_item in value.split(","):
        raw_action = raw_item.strip()
        if not raw_action:
            continue
        action = canonical_tabular_action_name(raw_action)
        if action is None:
            invalid.append(raw_action)
            continue
        if action not in TABULAR_ACTION_NAMES:
            invalid.append(raw_action)
            continue
        if action not in actions:
            actions.append(action)
    if invalid:
        raise SystemExit(f"Unknown action(s) for {option_name}: {','.join(invalid)}")
    if not actions:
        raise SystemExit(f"{option_name} did not include any actions")
    return tuple(actions)


def parse_action_name_set(value: str, *, option_name: str) -> frozenset[str]:
    if not value.strip():
        return frozenset()
    return frozenset(parse_action_names(value, option_name=option_name))


def canonical_tabular_action_name(policy: str) -> str | None:
    if policy in TABULAR_ACTION_NAMES:
        return policy
    return TABULAR_ACTION_ALIASES.get(policy)


def _coerce_q_table(value: object) -> dict[str, dict[str, float]]:
    if not isinstance(value, dict):
        return {}
    q_table: dict[str, dict[str, float]] = {}
    for state_key, scores in value.items():
        if not isinstance(scores, dict):
            continue
        clean_scores: dict[str, float] = {}
        for action_name, score in scores.items():
            action = canonical_tabular_action_name(str(action_name))
            if action is None or action not in TABULAR_ACTION_NAMES:
                continue
            try:
                clean_scores[action] = float(score)
            except (TypeError, ValueError):
                continue
        if clean_scores:
            q_table[str(state_key)] = clean_scores
    return q_table


def _coerce_q_counts(value: object) -> dict[str, dict[str, int]]:
    if not isinstance(value, dict):
        return {}
    q_counts: dict[str, dict[str, int]] = {}
    for state_key, counts in value.items():
        if not isinstance(counts, dict):
            continue
        clean_counts: dict[str, int] = {}
        for action_name, count in counts.items():
            action = canonical_tabular_action_name(str(action_name))
            if action is None or action not in TABULAR_ACTION_NAMES:
                continue
            try:
                clean_counts[action] = clean_counts.get(action, 0) + max(0, int(count))
            except (TypeError, ValueError):
                continue
        if clean_counts:
            q_counts[str(state_key)] = clean_counts
    return q_counts


def _coerce_action_count_map(value: object) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    counts: dict[str, int] = {}
    for action_name, raw_count in value.items():
        action = canonical_tabular_action_name(str(action_name))
        if action is None or action not in TABULAR_ACTION_NAMES:
            continue
        try:
            counts[action] = max(0, int(raw_count))
        except (TypeError, ValueError):
            continue
    return counts


def _coerce_action_reward_map(value: object) -> dict[str, float]:
    if not isinstance(value, dict):
        return {}
    rewards: dict[str, float] = {}
    for action_name, raw_reward in value.items():
        action = canonical_tabular_action_name(str(action_name))
        if action is None or action not in TABULAR_ACTION_NAMES:
            continue
        try:
            rewards[action] = float(raw_reward)
        except (TypeError, ValueError):
            continue
    return rewards


def sanitized_dqn_feature_names(value: object, context: str) -> tuple[str, ...]:
    feature_names, stripped = rl_evidence.sanitize_feature_names(value)
    if stripped:
        key = (context, stripped)
        if key not in _warned_stripped_feature_sets:
            _warned_stripped_feature_sets.add(key)
            print(
                f"WARNING: {context}: stripped combat evidence/event feature names: {','.join(stripped)}",
                file=sys.stderr,
            )
    return feature_names


def _coerce_dqn_model(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}

    raw_feature_names = value.get("feature_names")
    if isinstance(raw_feature_names, list):
        feature_names = tuple(
            name for name in sanitized_dqn_feature_names(raw_feature_names, "dqn model") if name in DQN_FEATURE_SCALES
        )
    else:
        feature_names = DQN_FEATURE_NAMES
    if not feature_names:
        feature_names = DQN_FEATURE_NAMES

    raw_feature_scales = value.get("feature_scales")
    feature_scales = dict(DQN_FEATURE_SCALES)
    if isinstance(raw_feature_scales, dict):
        for name, scale in raw_feature_scales.items():
            key = str(name)
            if key not in DQN_FEATURE_SCALES:
                continue
            try:
                feature_scales[key] = max(1e-6, float(scale))
            except (TypeError, ValueError):
                continue

    clean_layers: list[dict[str, object]] = []
    input_dim = len(feature_names)
    raw_layers = value.get("layers")
    if not isinstance(raw_layers, list):
        return {}
    for index, raw_layer in enumerate(raw_layers):
        if not isinstance(raw_layer, dict):
            return {}
        raw_weights = raw_layer.get("weights")
        raw_bias = raw_layer.get("bias")
        if not isinstance(raw_weights, list) or not isinstance(raw_bias, list):
            return {}
        weights: list[list[float]] = []
        for row in raw_weights:
            if not isinstance(row, list) or len(row) != input_dim:
                return {}
            try:
                weights.append([float(item) for item in row])
            except (TypeError, ValueError):
                return {}
        try:
            bias = [float(item) for item in raw_bias]
        except (TypeError, ValueError):
            return {}
        if len(weights) != len(bias) or not weights:
            return {}
        activation = str(raw_layer.get("activation", "linear") or "linear")
        if activation not in {"relu", "linear"}:
            return {}
        if index + 1 == len(raw_layers):
            activation = "linear"
        clean_layers.append({"weights": weights, "bias": bias, "activation": activation})
        input_dim = len(bias)

    if not clean_layers or len(clean_layers[-1]["bias"]) < 1:
        return {}
    return {
        "feature_names": list(feature_names),
        "feature_scales": feature_scales,
        "layers": clean_layers,
    }


def _coerce_actor_critic_layers(raw_layers: object, input_dim: int) -> list[dict[str, object]]:
    if not isinstance(raw_layers, list):
        return []
    clean_layers: list[dict[str, object]] = []
    current_dim = max(0, int(input_dim))
    for index, raw_layer in enumerate(raw_layers):
        if not isinstance(raw_layer, dict):
            return []
        raw_weights = raw_layer.get("weights")
        raw_bias = raw_layer.get("bias")
        if not isinstance(raw_weights, list) or not isinstance(raw_bias, list):
            return []
        weights: list[list[float]] = []
        for row in raw_weights:
            if not isinstance(row, list) or len(row) != current_dim:
                return []
            try:
                weights.append([float(item) for item in row])
            except (TypeError, ValueError):
                return []
        try:
            bias = [float(item) for item in raw_bias]
        except (TypeError, ValueError):
            return []
        if len(weights) != len(bias) or not weights:
            return []
        activation = str(raw_layer.get("activation", "linear") or "linear")
        if activation not in {"relu", "linear"}:
            return []
        if index + 1 == len(raw_layers):
            activation = "linear"
        clean_layers.append({"weights": weights, "bias": bias, "activation": activation})
        current_dim = len(bias)
    return clean_layers


def _coerce_actor_critic_model(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    try:
        schema_version = int(value.get("schema_version", 0) or 0)
    except (TypeError, ValueError):
        return {}
    if schema_version != 1:
        return {}
    architecture = str(value.get("architecture", "independent-mlp-v1") or "independent-mlp-v1")
    if architecture != "independent-mlp-v1":
        return {}

    raw_feature_names = value.get("feature_names")
    if isinstance(raw_feature_names, list):
        feature_names = tuple(
            name
            for name in sanitized_dqn_feature_names(raw_feature_names, "actor-critic model")
            if name in DQN_FEATURE_SCALES
        )
    else:
        feature_names = DQN_FEATURE_NAMES
    if not feature_names:
        feature_names = DQN_FEATURE_NAMES

    raw_feature_scales = value.get("feature_scales")
    feature_scales = dict(DQN_FEATURE_SCALES)
    if isinstance(raw_feature_scales, dict):
        for name, scale in raw_feature_scales.items():
            key = str(name)
            if key not in DQN_FEATURE_SCALES:
                continue
            try:
                feature_scales[key] = max(1e-6, float(scale))
            except (TypeError, ValueError):
                continue

    actor_layers = _coerce_actor_critic_layers(value.get("actor_layers"), len(feature_names))
    value_layers = _coerce_actor_critic_layers(value.get("value_layers"), len(feature_names))
    if not actor_layers or not value_layers:
        return {}
    if len(actor_layers[-1]["bias"]) < 1 or len(value_layers[-1]["bias"]) < 1:
        return {}
    return {
        "schema_version": schema_version,
        "algorithm_version": str(value.get("algorithm_version", "") or ""),
        "architecture": architecture,
        "feature_names": list(feature_names),
        "feature_scales": feature_scales,
        "actor_layers": actor_layers,
        "value_layers": value_layers,
    }


def _coerce_tactical_intent_model(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    try:
        schema_version = int(value.get("schema_version", 0) or 0)
    except (TypeError, ValueError):
        return {}
    if schema_version != 1:
        return {}
    raw_intents = value.get("intent_names")
    if not isinstance(raw_intents, list):
        return {}
    intent_names: list[str] = []
    for item in raw_intents:
        name = str(item)
        if name and name not in intent_names:
            intent_names.append(name)
    if not intent_names:
        return {}

    raw_feature_names = value.get("feature_names")
    if isinstance(raw_feature_names, list):
        feature_names = tuple(
            name
            for name in sanitized_dqn_feature_names(raw_feature_names, "tactical intent model")
            if name in DQN_FEATURE_SCALES
        )
    else:
        feature_names = DQN_FEATURE_NAMES
    if not feature_names:
        feature_names = DQN_FEATURE_NAMES

    raw_feature_scales = value.get("feature_scales")
    feature_scales = dict(DQN_FEATURE_SCALES)
    if isinstance(raw_feature_scales, dict):
        for name, scale in raw_feature_scales.items():
            key = str(name)
            if key not in DQN_FEATURE_SCALES:
                continue
            try:
                feature_scales[key] = max(1e-6, float(scale))
            except (TypeError, ValueError):
                continue

    layers = _coerce_actor_critic_layers(value.get("layers"), len(feature_names))
    if not layers:
        return {}
    output_size = len(layers[-1].get("bias", []))
    if output_size != len(intent_names):
        return {}
    return {
        "schema_version": schema_version,
        "algorithm_version": str(value.get("algorithm_version", "") or ""),
        "intent_names": intent_names,
        "feature_names": list(feature_names),
        "feature_scales": feature_scales,
        "layers": layers,
    }


def replace_with_retries(src: str, dst: str, attempts: int = 8, delay_sec: float = 0.025) -> None:
    for attempt in range(max(1, attempts)):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if attempt + 1 >= attempts:
                raise
            time.sleep(delay_sec * (attempt + 1))


class ActorModelStore:
    def __init__(
        self,
        model_dir: str | None,
        initial_policy: str,
        initial_version: int,
        initial_actions: tuple[str, ...] = TABULAR_DEFAULT_ACTIONS,
        initial_fallback_policy: str = "hp",
    ) -> None:
        self._model_dir = model_dir
        self._current_path = os.path.join(model_dir, "current.json") if model_dir else None
        self._lock = threading.Lock()
        self._active = ActorModel(
            max(0, initial_version),
            initial_policy,
            "cli",
            actions=initial_actions,
            fallback_policy=initial_fallback_policy,
        )
        self._known_policies: dict[int, str] = {self._active.version: self._active.policy}
        self._latest_tabular_state: str | None = None
        self._last_published_version = self._active.version
        self._last_loaded_version = self._active.version
        self._publish_count = 0
        self._load_count = 0
        self._current_mtime_ns = 0
        self._refresh_interval_ns = int(float(os.environ.get("RL_MODEL_REFRESH_INTERVAL_SEC", "0.25")) * 1_000_000_000)
        if self._model_dir:
            os.makedirs(self._model_dir, exist_ok=True)
            self._load_current(force=True)
            if self._current_path and not os.path.exists(self._current_path):
                self.publish(
                    self._active.policy,
                    source="bootstrap",
                    version=self._active.version,
                    actions=self._active.actions,
                    fallback_policy=self._active.fallback_policy,
                )
            threading.Thread(target=self._watch_current, daemon=True).start()

    def _load_current(self, force: bool = False) -> None:
        if not self._current_path:
            return
        try:
            stat = os.stat(self._current_path)
        except OSError:
            return
        if not force and stat.st_mtime_ns == self._current_mtime_ns:
            return
        try:
            with open(self._current_path, "r", encoding="utf-8") as stream:
                data = json.load(stream)
        except (OSError, json.JSONDecodeError):
            return
        version = int(data.get("version", self._active.version) or 0)
        policy = str(data.get("policy", self._active.policy) or self._active.policy)
        try:
            action_set_version = int(data.get("action_set_version", 0) or 0)
        except (TypeError, ValueError):
            action_set_version = 0
        if policy in MODEL_POLICY_CHOICES and action_set_version != ACTION_SET_VERSION:
            print(
                f"MODEL ignored version={version} policy={policy} "
                f"action_set={action_set_version} expected={ACTION_SET_VERSION}",
                flush=True,
            )
            self._current_mtime_ns = stat.st_mtime_ns
            return
        source = str(data.get("source", "file") or "file")
        raw_metadata = data.get("metadata")
        metadata = raw_metadata if isinstance(raw_metadata, dict) else {}
        q_table = _coerce_q_table(data.get("q"))
        q_counts = _coerce_q_counts(data.get("q_counts"))
        dqn_model = _coerce_dqn_model(data.get("dqn"))
        actor_critic_model = _coerce_actor_critic_model(data.get("actor_critic"))
        tactical_intent_model = _coerce_tactical_intent_model(data.get("tactical_intent"))
        actions = _coerce_action_names(data.get("actions"))
        try:
            epsilon = float(data.get("epsilon", 0.0) or 0.0)
        except (TypeError, ValueError):
            epsilon = 0.0
        fallback_policy = str(data.get("fallback_policy", "hp") or "hp")
        try:
            updated_rows = int(data.get("updated_rows", 0) or 0)
        except (TypeError, ValueError):
            updated_rows = 0
        try:
            min_action_count = max(1, int(data.get("min_action_count", 1) or 1))
        except (TypeError, ValueError):
            min_action_count = 1
        with self._lock:
            if version >= self._active.version:
                self._active = ActorModel(
                    version,
                    policy,
                    source,
                    metadata=metadata,
                    q_table=q_table,
                    q_counts=q_counts,
                    dqn_model=dqn_model,
                    actor_critic_model=actor_critic_model,
                    tactical_intent_model=tactical_intent_model,
                    actions=actions,
                    epsilon=epsilon,
                    fallback_policy=fallback_policy,
                    updated_rows=updated_rows,
                    min_action_count=min_action_count,
                )
                self._known_policies[version] = policy
                self._current_mtime_ns = stat.st_mtime_ns
                self._last_loaded_version = version
                self._load_count += 1

    def current(self) -> ActorModel:
        with self._lock:
            return self._active

    def status(self) -> ActorModelStatus:
        with self._lock:
            return ActorModelStatus(
                active=self._active,
                last_published_version=self._last_published_version,
                last_loaded_version=self._last_loaded_version,
                publish_count=self._publish_count,
                load_count=self._load_count,
            )

    def policy_for_version(self, version: int) -> str:
        if version <= 0:
            with self._lock:
                return self._known_policies.get(version, self._active.policy)
        with self._lock:
            known = self._known_policies.get(version)
            if known is not None:
                return known
        if not self._model_dir:
            with self._lock:
                return self._active.policy
        data = None
        for filename in (f"actor-v{version}.json", f"actor-critic-v{version}.json", f"tactical-intent-v{version}.json"):
            version_path = os.path.join(self._model_dir, filename)
            try:
                with open(version_path, "r", encoding="utf-8") as stream:
                    data = json.load(stream)
                break
            except (OSError, json.JSONDecodeError):
                continue
        if not isinstance(data, dict):
            with self._lock:
                return self._active.policy
        policy = str(data.get("policy", "") or "")
        if not policy:
            with self._lock:
                return self._active.policy
        with self._lock:
            self._known_policies[version] = policy
        return policy

    def set_latest_tabular_state(self, state_key: str) -> None:
        with self._lock:
            self._latest_tabular_state = state_key

    def latest_tabular_state(self) -> str | None:
        with self._lock:
            return self._latest_tabular_state

    def _watch_current(self) -> None:
        interval_sec = max(0.05, self._refresh_interval_ns / 1_000_000_000)
        while True:
            time.sleep(interval_sec)
            self._load_current()

    def publish(
        self,
        policy: str,
        source: str,
        version: int | None = None,
        metadata: dict[str, object] | None = None,
        q_table: dict[str, dict[str, float]] | None = None,
        q_counts: dict[str, dict[str, int]] | None = None,
        dqn_model: dict[str, object] | None = None,
        actor_critic_model: dict[str, object] | None = None,
        tactical_intent_model: dict[str, object] | None = None,
        actions: tuple[str, ...] = TABULAR_DEFAULT_ACTIONS,
        epsilon: float = 0.0,
        fallback_policy: str = "hp",
        updated_rows: int = 0,
        min_action_count: int = 1,
    ) -> ActorModel:
        if not self._model_dir or not self._current_path:
            with self._lock:
                next_version = self._active.version if version is None else max(0, version)
                self._active = ActorModel(
                    next_version,
                    policy,
                    source,
                    metadata=metadata or {},
                    q_table=q_table or {},
                    q_counts=q_counts or {},
                    dqn_model=dqn_model or {},
                    actor_critic_model=actor_critic_model or {},
                    tactical_intent_model=tactical_intent_model or {},
                    actions=actions,
                    epsilon=epsilon,
                    fallback_policy=fallback_policy,
                    updated_rows=updated_rows,
                    min_action_count=max(1, min_action_count),
                )
                self._known_policies[self._active.version] = self._active.policy
                self._last_published_version = self._active.version
                self._publish_count += 1
                return self._active

        with self._lock:
            next_version = self._active.version + 1 if version is None else max(0, version)
            if next_version < self._active.version:
                next_version = self._active.version
            model = ActorModel(
                next_version,
                policy,
                source,
                metadata=metadata or {},
                q_table=q_table or {},
                q_counts=q_counts or {},
                dqn_model=dqn_model or {},
                actor_critic_model=actor_critic_model or {},
                tactical_intent_model=tactical_intent_model or {},
                actions=actions,
                epsilon=epsilon,
                fallback_policy=fallback_policy,
                updated_rows=updated_rows,
                min_action_count=max(1, min_action_count),
            )
            payload = {
                "version": model.version,
                "policy": model.policy,
                "source": model.source,
                "action_set_version": ACTION_SET_VERSION,
                "created_at_unix": time.time(),
                "metadata": metadata or {},
            }
            if model.policy == "tabular":
                payload.update(
                    {
                        "actions": list(model.actions),
                        "epsilon": model.epsilon,
                        "fallback_policy": model.fallback_policy,
                        "q": model.q_table,
                        "q_counts": model.q_counts,
                        "updated_rows": model.updated_rows,
                        "min_action_count": model.min_action_count,
                    }
                )
            elif model.policy in ("dqn", "bc"):
                payload.update(
                    {
                        "actions": list(model.actions),
                        "epsilon": model.epsilon,
                        "fallback_policy": model.fallback_policy,
                        "dqn": model.dqn_model,
                        "updated_rows": model.updated_rows,
                    }
                )
            elif model.policy == "actor-critic":
                payload.update(
                    {
                        "actions": list(model.actions),
                        "epsilon": model.epsilon,
                        "fallback_policy": model.fallback_policy,
                        "actor_critic": model.actor_critic_model,
                        "updated_rows": model.updated_rows,
                    }
                )
            elif model.policy == "tactical":
                payload.update(
                    {
                        "actions": list(model.actions),
                        "epsilon": model.epsilon,
                        "fallback_policy": model.fallback_policy,
                        "tactical_intent": model.tactical_intent_model,
                        "updated_rows": model.updated_rows,
                    }
                )
            version_path = os.path.join(self._model_dir, f"actor-v{model.version}.json")
            fd, temp_path = tempfile.mkstemp(prefix=f".actor-v{model.version}.", suffix=".tmp", dir=self._model_dir)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as stream:
                    json.dump(payload, stream, sort_keys=True)
                    stream.write("\n")
                replace_with_retries(temp_path, version_path)
                fd, temp_path = tempfile.mkstemp(prefix=".current.", suffix=".tmp", dir=self._model_dir)
                with os.fdopen(fd, "w", encoding="utf-8") as stream:
                    json.dump(payload, stream, sort_keys=True)
                    stream.write("\n")
                replace_with_retries(temp_path, self._current_path)
                self._current_mtime_ns = os.stat(self._current_path).st_mtime_ns
            finally:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
            self._active = model
            self._known_policies[model.version] = model.policy
            self._last_published_version = model.version
            self._last_loaded_version = model.version
            self._publish_count += 1
            print(f"MODEL published version={model.version} policy={model.policy} source={model.source}", flush=True)
            return model


class InferenceStats:
    def __init__(self, capacity: int = 512) -> None:
        self._capacity = capacity
        self._samples_ns: list[int] = []
        self._obs_payload = 0
        self._obs_header_only = 0
        self._tabular_obs_state = 0
        self._tabular_latest_state = 0
        self._lock = threading.Lock()

    def record(self, elapsed_ns: int, *, obs_payload: bool = False, tabular_state_source: str = "") -> None:
        with self._lock:
            self._samples_ns.append(elapsed_ns)
            if len(self._samples_ns) > self._capacity:
                del self._samples_ns[: len(self._samples_ns) - self._capacity]
            if obs_payload:
                self._obs_payload += 1
            else:
                self._obs_header_only += 1
            if tabular_state_source == "obs":
                self._tabular_obs_state += 1
            elif tabular_state_source == "latest":
                self._tabular_latest_state += 1

    def snapshot(self) -> dict[str, float | int]:
        with self._lock:
            samples_ns = sorted(self._samples_ns)
            obs_payload = self._obs_payload
            obs_header_only = self._obs_header_only
            tabular_obs_state = self._tabular_obs_state
            tabular_latest_state = self._tabular_latest_state
        if not samples_ns:
            return {
                "count": 0,
                "p50_us": 0.0,
                "p95_us": 0.0,
                "max_us": 0.0,
                "obs_payload": obs_payload,
                "obs_header_only": obs_header_only,
                "tabular_obs_state": tabular_obs_state,
                "tabular_latest_state": tabular_latest_state,
            }
        p50_ns = samples_ns[len(samples_ns) // 2]
        p95_ns = samples_ns[min(len(samples_ns) - 1, int(len(samples_ns) * 0.95))]
        max_ns = samples_ns[-1]
        return {
            "count": len(samples_ns),
            "p50_us": p50_ns / 1000.0,
            "p95_us": p95_ns / 1000.0,
            "max_us": max_ns / 1000.0,
            "obs_payload": obs_payload,
            "obs_header_only": obs_header_only,
            "tabular_obs_state": tabular_obs_state,
            "tabular_latest_state": tabular_latest_state,
        }


class ReplayBuffer:
    def __init__(self, capacity: int) -> None:
        self._rows: collections.deque[dict[str, object]] = collections.deque(maxlen=max(1, capacity))

    def add(self, row: dict[str, object]) -> None:
        self._rows.append(row)

    def __len__(self) -> int:
        return len(self._rows)

    def can_sample(self, batch_size: int) -> bool:
        return len(self._rows) >= max(1, batch_size)

    def sample(self, batch_size: int) -> list[dict[str, object]]:
        return random.sample(list(self._rows), min(len(self._rows), max(1, batch_size)))


def bucket_range(value: int, thresholds: tuple[int, int], labels: tuple[str, str, str]) -> str:
    if value <= thresholds[0]:
        return labels[0]
    if value <= thresholds[1]:
        return labels[1]
    return labels[2]


def tabular_state_key(row: dict[str, object]) -> str:
    abs_dx = int(row.get("obs_abs_dx", 0) or 0)
    abs_dy = int(row.get("obs_abs_dy", 0) or 0)
    self_front = int(row.get("obs_self_front_edge_dist", 0) or 0)
    self_back = int(row.get("obs_self_back_edge_dist", 0) or 0)
    opp_front = int(row.get("obs_opp_front_edge_dist", 0) or 0)
    opp_back = int(row.get("obs_opp_back_edge_dist", 0) or 0)
    opp_in_front = 1 if int(row.get("obs_opp_in_front", 0) or 0) else 0
    opp_attack = 1 if int(row.get("obs_opp_routine_attack_state", 0) or 0) else 0
    return "|".join(
        (
            f"front={opp_in_front}",
            f"opp_attack={opp_attack}",
            f"dx={bucket_range(abs_dx, (48, 144), ('close', 'mid', 'far'))}",
            f"dy={bucket_range(abs_dy, (16, 64), ('flat', 'offset', 'high'))}",
            f"self_front={bucket_range(self_front, (48, 160), ('corner', 'mid', 'open'))}",
            f"self_back={bucket_range(self_back, (48, 160), ('corner', 'mid', 'open'))}",
            f"opp_front={bucket_range(opp_front, (48, 160), ('corner', 'mid', 'open'))}",
            f"opp_back={bucket_range(opp_back, (48, 160), ('corner', 'mid', 'open'))}",
        )
    )


def tabular_state_part(state_key: str, name: str) -> str:
    prefix = f"{name}="
    for part in state_key.split("|"):
        if part.startswith(prefix):
            return part[len(prefix) :]
    return "unknown"


def summarize_ready_actions(
    q_table: dict[str, dict[str, float]],
    q_counts: dict[str, dict[str, int]],
    actions: tuple[str, ...],
    min_action_count: int,
) -> tuple[
    dict[str, int],
    dict[str, dict[str, int]],
    dict[str, dict[str, int]],
    dict[str, dict[str, int]],
]:
    min_count = max(1, min_action_count)
    ready_actions = {action: 0 for action in actions}
    ready_dx_actions = {bucket: {action: 0 for action in actions} for bucket in ("close", "mid", "far", "unknown")}
    ready_opp_attack_actions = {
        bucket: {action: 0 for action in actions} for bucket in ("0", "1", "unknown")
    }
    ready_threat_dx_actions = {
        f"atk{opp_attack}_{dx}": {action: 0 for action in actions}
        for opp_attack in ("0", "1")
        for dx in ("close", "mid", "far")
    }
    ready_threat_dx_actions["unknown"] = {action: 0 for action in actions}
    for state, scores in q_table.items():
        best_action = ""
        best_score = 0.0
        counts = q_counts.get(state, {})
        for action in actions:
            score = float(scores.get(action, 0.0))
            count = int(counts.get(action, 0))
            if count < min_count or score <= 0.0:
                continue
            if not best_action or score > best_score:
                best_action = action
                best_score = score
        if not best_action:
            continue
        dx = tabular_state_part(state, "dx")
        if dx not in ready_dx_actions:
            dx = "unknown"
        opp_attack = tabular_state_part(state, "opp_attack")
        if opp_attack not in ready_opp_attack_actions:
            opp_attack = "unknown"
        threat_dx = f"atk{opp_attack}_{dx}"
        if threat_dx not in ready_threat_dx_actions:
            threat_dx = "unknown"
        ready_actions[best_action] += 1
        ready_dx_actions[dx][best_action] += 1
        ready_opp_attack_actions[opp_attack][best_action] += 1
        ready_threat_dx_actions[threat_dx][best_action] += 1
    return ready_actions, ready_dx_actions, ready_opp_attack_actions, ready_threat_dx_actions


def format_action_counts(counts: dict[str, int]) -> str:
    parts = [f"{action}:{count}" for action, count in counts.items() if count > 0]
    return ",".join(parts) if parts else "none"


def format_dx_action_counts(dx_counts: dict[str, dict[str, int]]) -> str:
    return " ".join(
        f"{bucket}{{{format_action_counts(dx_counts.get(bucket, {}))}}}" for bucket in ("close", "mid", "far")
    )


def format_opp_attack_action_counts(opp_attack_counts: dict[str, dict[str, int]]) -> str:
    parts = [
        f"{bucket}{{{format_action_counts(opp_attack_counts.get(bucket, {}))}}}" for bucket in ("0", "1")
    ]
    unknown = format_action_counts(opp_attack_counts.get("unknown", {}))
    if unknown != "none":
        parts.append(f"unknown{{{unknown}}}")
    return " ".join(parts)


def format_threat_dx_action_counts(threat_dx_counts: dict[str, dict[str, int]]) -> str:
    keys = [f"atk{opp_attack}_{dx}" for opp_attack in ("0", "1") for dx in ("close", "mid", "far")]
    parts = [f"{key}{{{format_action_counts(threat_dx_counts.get(key, {}))}}}" for key in keys]
    unknown = format_action_counts(threat_dx_counts.get("unknown", {}))
    if unknown != "none":
        parts.append(f"unknown{{{unknown}}}")
    return " ".join(parts)


def parse_obs_spacing_payload(payload: bytes) -> dict[str, object] | None:
    if len(payload) != OBS_SPACING_PAYLOAD.size:
        return None
    (
        payload_version,
        _reserved0,
        obs_abs_dx,
        obs_abs_dy,
        obs_self_front_edge_dist,
        obs_self_back_edge_dist,
        obs_opp_front_edge_dist,
        obs_opp_back_edge_dist,
        obs_self_stage_back_edge_dist,
        obs_opp_stage_back_edge_dist,
        obs_self_routine_1,
        obs_self_routine_2,
        obs_opp_routine_1,
        obs_opp_routine_2,
        obs_opp_in_front,
        obs_self_corner_state,
        obs_opp_corner_state,
        obs_corner_pressure_state,
        obs_range_threat_bucket,
        obs_self_routine_attack_state,
        obs_opp_routine_attack_state,
        obs_self_contact_reaction_state,
        obs_opp_contact_reaction_state,
        obs_self_airborne,
        obs_self_jump_phase,
        obs_self_ground_action_start_allowed,
        obs_self_jump_start_allowed,
        obs_self_air_attack_allowed,
        obs_projectile_active,
        obs_projectile_owner,
        obs_projectile_rel_x,
        obs_projectile_rel_y,
        obs_projectile_vel_x,
        obs_projectile_time_to_self,
    ) = OBS_SPACING_PAYLOAD.unpack(payload)
    if payload_version != OBS_SPACING_PAYLOAD_VERSION:
        return None
    return {
        "obs_abs_dx": obs_abs_dx,
        "obs_abs_dy": obs_abs_dy,
        "obs_self_front_edge_dist": obs_self_front_edge_dist,
        "obs_self_back_edge_dist": obs_self_back_edge_dist,
        "obs_opp_front_edge_dist": obs_opp_front_edge_dist,
        "obs_opp_back_edge_dist": obs_opp_back_edge_dist,
        "obs_self_stage_back_edge_dist": obs_self_stage_back_edge_dist,
        "obs_opp_stage_back_edge_dist": obs_opp_stage_back_edge_dist,
        "obs_self_corner_state": obs_self_corner_state,
        "obs_opp_corner_state": obs_opp_corner_state,
        "obs_corner_pressure_state": obs_corner_pressure_state,
        "obs_range_threat_bucket": obs_range_threat_bucket,
        "obs_self_routine_1": obs_self_routine_1,
        "obs_self_routine_2": obs_self_routine_2,
        "obs_opp_routine_1": obs_opp_routine_1,
        "obs_opp_routine_2": obs_opp_routine_2,
        "obs_opp_in_front": obs_opp_in_front,
        "obs_self_routine_attack_state": obs_self_routine_attack_state,
        "obs_opp_routine_attack_state": obs_opp_routine_attack_state,
        "obs_self_contact_reaction_state": obs_self_contact_reaction_state,
        "obs_opp_contact_reaction_state": obs_opp_contact_reaction_state,
        "obs_self_airborne": obs_self_airborne,
        "obs_self_jump_phase": obs_self_jump_phase,
        "obs_self_ground_action_start_allowed": obs_self_ground_action_start_allowed,
        "obs_self_jump_start_allowed": obs_self_jump_start_allowed,
        "obs_self_air_attack_allowed": obs_self_air_attack_allowed,
        "obs_projectile_active": obs_projectile_active,
        "obs_projectile_owner": obs_projectile_owner,
        "obs_projectile_rel_x": obs_projectile_rel_x,
        "obs_projectile_rel_y": obs_projectile_rel_y,
        "obs_projectile_vel_x": obs_projectile_vel_x,
        "obs_projectile_time_to_self": obs_projectile_time_to_self,
    }


def tabular_action_name(action_wire: int) -> str | None:
    return TABULAR_ACTION_NAMES_BY_WIRE.get(action_wire & 0xFFFF)


def row_int_field(row: dict[str, object], name: str) -> int:
    try:
        return int(row.get(name, 0) or 0)
    except (TypeError, ValueError):
        return 0


def self_engine_row_int_field(row: dict[str, object], generic_name: str) -> int:
    side_name = f"self_{generic_name}"
    if side_name in row:
        return row_int_field(row, side_name)
    return row_int_field(row, generic_name)


def dqn_projectile_timing_prior_jump_penalty(
    row: dict[str, object],
    config: DQNProjectileTimingPriorConfig,
) -> float:
    if not config.enabled:
        return 0.0
    if row_int_field(row, "obs_self_airborne") != 0 or row_int_field(row, "obs_self_jump_phase") >= 2:
        return 0.0
    if row_int_field(row, "obs_projectile_active") == 0:
        return 0.0
    if row_int_field(row, "obs_projectile_owner") != 2:
        return 0.0

    rel_x = row_int_field(row, "obs_projectile_rel_x")
    rel_y = row_int_field(row, "obs_projectile_rel_y")
    vel_x = row_int_field(row, "obs_projectile_vel_x")
    time_to_self = row_int_field(row, "obs_projectile_time_to_self")
    if (
        rel_x <= 0
        or rel_x > config.threat_max_dx
        or abs(rel_y) > config.threat_max_abs_y
        or vel_x >= 0
    ):
        return 0.0

    if config.min_time_to_self <= time_to_self <= config.urgent_max_time_to_self:
        return max(0.0, config.urgent_jump_penalty)
    if time_to_self <= config.borderline_max_time_to_self:
        return max(0.0, config.borderline_jump_penalty)
    if (
        config.early_jump_penalty > 0.0
        and config.early_min_time_to_self <= time_to_self <= config.early_max_time_to_self
    ):
        return max(0.0, config.early_jump_penalty)
    return 0.0


def dqn_projectile_timing_prior_penalty(
    action: str,
    row: dict[str, object],
    config: DQNProjectileTimingPriorConfig,
) -> float:
    if action not in DQN_JUMP_START_ACTIONS:
        return 0.0
    return dqn_projectile_timing_prior_jump_penalty(row, config)


def dqn_shoryuken_context_prior_penalty(
    action: str,
    row: dict[str, object],
    config: DQNShoryukenContextPriorConfig,
) -> float:
    if not config.enabled or action not in SHORYUKEN_ACTION_NAMES:
        return 0.0
    abs_dx = row_int_field(row, "obs_abs_dx")
    opp_routine_1 = row_int_field(row, "obs_opp_routine_1")
    opp_routine_2 = row_int_field(row, "obs_opp_routine_2")
    anti_air_context = (
        config.min_abs_dx <= abs_dx <= config.max_abs_dx
        and opp_routine_1 == 0
        and config.opp_air_routine_min <= opp_routine_2 <= config.opp_air_routine_max
    )
    if anti_air_context:
        return 0.0
    penalty = max(0.0, config.penalty)
    far_context = abs_dx >= max(0, config.far_min_abs_dx)
    if config.far_block and far_context:
        return 1_000_000.0
    if config.far_extra_penalty > 0.0 and far_context:
        penalty += max(0.0, config.far_extra_penalty)
    if row_int_field(row, "obs_self_airborne") != 0 or row_int_field(row, "obs_self_jump_phase") != 0:
        return penalty
    if not dqn_ground_action_start_allowed(row):
        return penalty
    return penalty


def dqn_ground_normal_context_prior_penalty(
    action: str,
    row: dict[str, object],
    config: DQNGroundNormalContextPriorConfig,
) -> float:
    if not config.enabled or action not in STAND_NORMAL_ACTION_NAMES + CROUCH_NORMAL_ACTION_NAMES:
        return 0.0
    penalty = max(0.0, config.penalty)
    if row_int_field(row, "obs_self_airborne") != 0 or row_int_field(row, "obs_self_jump_phase") != 0:
        return penalty
    if not dqn_ground_action_start_allowed(row):
        return penalty

    abs_dx = row_int_field(row, "obs_abs_dx")
    if abs_dx <= config.close_max_abs_dx:
        return 0.0
    if abs_dx > config.poke_max_abs_dx:
        return penalty

    opponent_threat_or_contact = (
        row_int_field(row, "obs_opp_routine_attack_state") != 0
        or row_int_field(row, "obs_opp_contact_reaction_state") != 0
    )
    return 0.0 if opponent_threat_or_contact else penalty


def dqn_fireball_zoning_prior_bonus(
    action: str,
    row: dict[str, object],
    config: DQNFireballZoningPriorConfig,
) -> float:
    if not config.enabled or action not in FIREBALL_ACTION_NAMES:
        return 0.0
    if row_int_field(row, "obs_self_airborne") != 0 or row_int_field(row, "obs_self_jump_phase") != 0:
        return 0.0
    if not dqn_ground_action_start_allowed(row):
        return 0.0

    abs_dx = row_int_field(row, "obs_abs_dx")
    if abs_dx < config.min_abs_dx or abs_dx > config.max_abs_dx:
        return 0.0
    if row_int_field(row, "obs_opp_contact_reaction_state") != 0:
        return 0.0
    if row_int_field(row, "obs_opp_airborne") != 0 or row_int_field(row, "obs_opp_jump_phase") != 0:
        return 0.0
    return max(0.0, config.bonus)


def dqn_threat_defense_prior_bonus(
    action: str,
    row: dict[str, object],
    config: DQNThreatDefensePriorConfig,
) -> float:
    if not config.enabled or action not in ("guard-stand", "guard-crouch", "back"):
        return 0.0
    if row_int_field(row, "obs_self_airborne") != 0 or row_int_field(row, "obs_self_jump_phase") != 0:
        return 0.0
    if row_int_field(row, "obs_opp_routine_attack_state") == 0:
        return 0.0
    if row_int_field(row, "obs_opp_airborne") != 0 or row_int_field(row, "obs_opp_jump_phase") != 0:
        return 0.0
    can_start_ground_action = dqn_ground_action_start_allowed(row)
    contact_sustain = config.contact_sustain and row_int_field(row, "obs_self_contact_reaction_state") != 0
    if not can_start_ground_action and not contact_sustain:
        return 0.0
    if row_int_field(row, "obs_abs_dx") > config.max_abs_dx:
        return 0.0
    if action == "back":
        return max(0.0, config.back_bonus)
    return max(0.0, config.guard_bonus)


def dqn_threat_defense_prior_penalty(
    action: str,
    row: dict[str, object],
    config: DQNThreatDefensePriorConfig,
) -> float:
    if not config.enabled or config.unsafe_penalty <= 0.0:
        return 0.0
    unsafe_actions = (
        STAND_NORMAL_ACTION_NAMES
        + CROUCH_NORMAL_ACTION_NAMES
        + SHORYUKEN_ACTION_NAMES
        + TATSU_ACTION_NAMES
        + FIREBALL_ACTION_NAMES
    )
    if action != "forward" and action not in unsafe_actions:
        return 0.0
    if row_int_field(row, "obs_self_airborne") != 0 or row_int_field(row, "obs_self_jump_phase") != 0:
        return 0.0
    if row_int_field(row, "obs_opp_routine_attack_state") == 0:
        return 0.0
    if row_int_field(row, "obs_opp_airborne") != 0 or row_int_field(row, "obs_opp_jump_phase") != 0:
        return 0.0
    can_start_ground_action = dqn_ground_action_start_allowed(row)
    contact_sustain = config.contact_sustain and row_int_field(row, "obs_self_contact_reaction_state") != 0
    if not can_start_ground_action and not contact_sustain:
        return 0.0
    if row_int_field(row, "obs_abs_dx") > config.max_abs_dx:
        return 0.0
    return max(0.0, config.unsafe_penalty)


def actor_critic_spacing_prior_suppressed_by_threat(
    row: dict[str, object],
    config: ActorCriticSpacingPriorConfig,
) -> bool:
    if row_int_field(row, "obs_self_contact_reaction_state") != 0:
        return True
    if (
        row_int_field(row, "obs_opp_routine_attack_state") != 0
        and row_int_field(row, "obs_abs_dx") <= config.threat_attack_max_abs_dx
    ):
        return True
    if row_int_field(row, "obs_projectile_active") == 0:
        return False
    if row_int_field(row, "obs_projectile_owner") != 2:
        return False
    rel_x = row_int_field(row, "obs_projectile_rel_x")
    rel_y = row_int_field(row, "obs_projectile_rel_y")
    vel_x = row_int_field(row, "obs_projectile_vel_x")
    time_to_self = row_int_field(row, "obs_projectile_time_to_self")
    return (
        1 <= time_to_self <= config.threat_suppress_max_time_to_self
        and 0 < rel_x <= config.threat_suppress_max_abs_dx
        and abs(rel_y) <= config.threat_suppress_max_abs_y
        and vel_x < 0
    )


def actor_critic_threat_defense_adjustment(
    action: str,
    row: dict[str, object],
    config: ActorCriticSpacingPriorConfig,
) -> float:
    if not actor_critic_spacing_prior_suppressed_by_threat(row, config):
        return 0.0
    if action == "guard-crouch" or action == "guard-stand":
        return max(0.0, config.threat_guard_bonus)
    if action == "back":
        return max(0.0, config.threat_back_bonus)
    if action == "forward":
        return -max(0.0, config.threat_forward_penalty)
    if (
        action in STAND_NORMAL_ACTION_NAMES
        or action in CROUCH_NORMAL_ACTION_NAMES
        or action in SHORYUKEN_ACTION_NAMES
        or action in TATSU_ACTION_NAMES
        or action == "forward-hp"
        or action == "throw"
    ):
        return -max(0.0, config.threat_attack_penalty)
    return 0.0


def actor_critic_close_attack_action(action: str) -> bool:
    return (
        action in STAND_NORMAL_ACTION_NAMES
        or action in CROUCH_NORMAL_ACTION_NAMES
        or action == "forward-hp"
        or action == "throw"
    )


def actor_critic_spacing_prior_adjustment(
    action: str,
    row: dict[str, object],
    config: ActorCriticSpacingPriorConfig,
) -> float:
    if not config.enabled:
        return 0.0
    if row_int_field(row, "obs_self_airborne") != 0 or row_int_field(row, "obs_self_jump_phase") != 0:
        return 0.0
    if actor_critic_spacing_prior_suppressed_by_threat(row, config):
        return actor_critic_threat_defense_adjustment(action, row, config)

    abs_dx = row_int_field(row, "obs_abs_dx")
    adjustment = 0.0
    if abs_dx > config.poke_max_abs_dx:
        if action == "forward":
            adjustment += max(0.0, config.forward_bonus)
        elif action == "back":
            adjustment -= max(0.0, config.back_penalty)
        elif action in ("guard-stand", "guard-crouch"):
            adjustment -= max(0.0, config.far_guard_penalty)
    if abs_dx > config.close_max_abs_dx and actor_critic_close_attack_action(action):
        adjustment -= max(0.0, config.close_attack_far_penalty)
    if abs_dx > config.poke_max_abs_dx and action in SHORYUKEN_ACTION_NAMES:
        adjustment -= max(0.0, config.shoryuken_far_penalty)
    if abs_dx >= config.very_far_min_abs_dx and action in SHORYUKEN_ACTION_NAMES + STAND_NORMAL_ACTION_NAMES:
        adjustment -= max(0.0, config.close_attack_far_penalty)
    if (
        config.fireball_min_abs_dx <= abs_dx <= config.fireball_max_abs_dx
        and action in FIREBALL_ACTION_NAMES
    ):
        adjustment += max(0.0, config.fireball_bonus)
    return adjustment


def normalize_dqn_valid_action_mask_mode(mode: object) -> str:
    normalized = str(mode).strip().lower().replace("_", "-")
    return normalized or "off"


def parse_dqn_valid_action_mask_config(mode: str) -> DQNValidActionMaskConfig:
    normalized = normalize_dqn_valid_action_mask_mode(mode)
    if normalized not in DQN_VALID_ACTION_MASK_MODES:
        raise ValueError(
            f"unknown DQN valid-action mask mode {mode!r}; "
            f"expected one of {','.join(DQN_VALID_ACTION_MASK_MODES)}"
        )
    return DQNValidActionMaskConfig(mode=normalized)


def parse_dqn_valid_action_mask_cli_config(mode: str) -> tuple[bool, DQNValidActionMaskConfig]:
    normalized = normalize_dqn_valid_action_mask_mode(mode)
    if normalized == "auto":
        return True, DQNValidActionMaskConfig()
    return False, parse_dqn_valid_action_mask_config(normalized)


def metadata_flag_enabled(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() not in {"", "0", "false", "no", "off", "disabled"}


def dqn_valid_action_mask_config_from_metadata(
    metadata: dict[str, object],
) -> tuple[DQNValidActionMaskConfig, str]:
    raw_config = metadata.get("dqn_valid_action_mask_config")
    source = "metadata"
    if isinstance(raw_config, dict):
        if not metadata_flag_enabled(raw_config.get("enabled")):
            return DQNValidActionMaskConfig(), "metadata:disabled"
        raw_mode = raw_config.get("mode", "off")
    else:
        awac_config = metadata.get("awac_config")
        raw_mode = awac_config.get("valid_action_mask") if isinstance(awac_config, dict) else None
        source = "metadata:awac_config"
    if raw_mode is None:
        return DQNValidActionMaskConfig(), "metadata:none"
    try:
        config = parse_dqn_valid_action_mask_config(str(raw_mode))
    except ValueError:
        return DQNValidActionMaskConfig(), f"metadata:invalid:{normalize_dqn_valid_action_mask_mode(raw_mode)}"
    if not config.enabled:
        return config, "metadata:off"
    return config, source


def resolve_dqn_valid_action_mask_config(
    actor: ActorModel,
    cli_config: DQNValidActionMaskConfig,
    auto_from_metadata: bool,
) -> tuple[DQNValidActionMaskConfig, str]:
    if not auto_from_metadata:
        return cli_config, "cli"
    if actor.policy not in ("dqn", "bc", "actor-critic"):
        return DQNValidActionMaskConfig(), f"auto:not-{actor.policy}"
    return dqn_valid_action_mask_config_from_metadata(actor.metadata)


def dqn_self_is_ordinary_jump_air(row: dict[str, object]) -> bool:
    return (
        row_int_field(row, "obs_self_routine_1") == 0
        and 18 <= row_int_field(row, "obs_self_routine_2") <= 26
        and row_int_field(row, "obs_self_routine_attack_state") == 0
        and row_int_field(row, "obs_self_contact_reaction_state") == 0
    )


def row_bool_field(row: dict[str, object], name: str) -> bool:
    return row_int_field(row, name) != 0


def dqn_self_is_ordinary_movable(row: dict[str, object]) -> bool:
    return (
        row_int_field(row, "obs_self_routine_1") == 0
        and row_int_field(row, "obs_self_routine_attack_state") == 0
        and row_int_field(row, "obs_self_contact_reaction_state") == 0
    )


def dqn_ground_action_start_allowed(row: dict[str, object]) -> bool:
    if "obs_self_ground_action_start_allowed" in row:
        return row_bool_field(row, "obs_self_ground_action_start_allowed")
    return dqn_self_is_ordinary_movable(row) and not dqn_self_is_ordinary_jump_air(row)


def dqn_jump_start_allowed(row: dict[str, object]) -> bool:
    if "obs_self_jump_start_allowed" in row:
        return row_bool_field(row, "obs_self_jump_start_allowed")
    return dqn_ground_action_start_allowed(row)


def dqn_air_attack_allowed(row: dict[str, object]) -> bool:
    if "obs_self_air_attack_allowed" in row:
        return row_bool_field(row, "obs_self_air_attack_allowed")
    return dqn_self_is_ordinary_jump_air(row)


def dqn_action_start_allowed(row: dict[str, object]) -> bool:
    return (
        dqn_ground_action_start_allowed(row)
        or dqn_jump_start_allowed(row)
        or dqn_air_attack_allowed(row)
    )


def dqn_self_mask_phase(row: dict[str, object]) -> str:
    if dqn_air_attack_allowed(row):
        return "air-attack"
    if dqn_ground_action_start_allowed(row) or dqn_jump_start_allowed(row):
        return "ground-action-start"
    if dqn_self_is_ordinary_jump_air(row):
        return "jump-air"
    if dqn_self_is_ordinary_movable(row):
        return "ordinary-movable"
    return "non-movable"


def dqn_valid_action_for_row(action: str, row: dict[str, object], config: DQNValidActionMaskConfig) -> bool:
    if not config.enabled:
        return True
    if action not in TABULAR_ACTION_NAMES:
        return False
    if config.mode == "action-start-v1":
        if action in DQN_MOVEMENT_GUARD_ACTIONS:
            return True
        if action in DQN_AIR_ATTACK_ACTIONS:
            return dqn_air_attack_allowed(row)
        if action in DQN_JUMP_START_ACTIONS:
            return dqn_jump_start_allowed(row)
        return dqn_ground_action_start_allowed(row)

    if config.mode != "self-routine-v1":
        return True

    if dqn_self_is_ordinary_jump_air(row):
        return action in DQN_AIR_ATTACK_ACTIONS or action in DQN_MOVEMENT_GUARD_ACTIONS
    if dqn_self_is_ordinary_movable(row):
        return action not in DQN_AIR_ATTACK_ACTIONS
    return action in DQN_MOVEMENT_GUARD_ACTIONS


def dqn_valid_actions_for_row(
    row: dict[str, object],
    actions: tuple[str, ...] | list[str],
    config: DQNValidActionMaskConfig = DQNValidActionMaskConfig(),
) -> tuple[str, ...]:
    return tuple(action for action in actions if dqn_valid_action_for_row(str(action), row, config))


def dqn_valid_action_indices_for_row(
    row: dict[str, object],
    actions: tuple[str, ...] | list[str],
    config: DQNValidActionMaskConfig = DQNValidActionMaskConfig(),
    value_count: int | None = None,
) -> tuple[int, ...]:
    count = len(actions) if value_count is None else min(len(actions), max(0, int(value_count)))
    return tuple(
        index
        for index in range(count)
        if dqn_valid_action_for_row(str(actions[index]), row, config)
    )


def tactical_spacing_bucket(row: dict[str, object], config: TacticalPolicyConfig) -> str:
    abs_dx = abs(row_int_field(row, "obs_abs_dx"))
    if abs_dx <= config.close_max_abs_dx // 2:
        return "throw_range"
    if abs_dx <= config.close_max_abs_dx:
        return "close"
    if abs_dx <= config.poke_max_abs_dx:
        return "poke"
    if abs_dx <= config.fireball_max_abs_dx:
        return "fireball"
    return "too_far"


def tactical_corner_context(row: dict[str, object], config: TacticalPolicyConfig) -> str:
    self_corner_state = row_int_field(row, "obs_self_corner_state")
    opponent_corner_state = row_int_field(row, "obs_opp_corner_state")
    if "obs_self_corner_state" in row and "obs_opp_corner_state" in row:
        self_cornered = self_corner_state != 0
        opponent_cornered = opponent_corner_state != 0
    else:
        self_cornered = min(
            row_int_field(row, "obs_self_front_edge_dist"),
            row_int_field(row, "obs_self_back_edge_dist"),
        ) <= config.corner_edge_max_dist
        opponent_cornered = min(
            row_int_field(row, "obs_opp_front_edge_dist"),
            row_int_field(row, "obs_opp_back_edge_dist"),
        ) <= config.corner_edge_max_dist
    if self_cornered and opponent_cornered:
        return "both_cornered"
    if self_cornered:
        return "self_cornered"
    if opponent_cornered:
        return "opponent_cornered"
    return "mid_screen"


def tactical_self_phase(row: dict[str, object]) -> str:
    if row_int_field(row, "obs_self_contact_reaction_state") != 0:
        return "contact_reaction"
    if row_int_field(row, "obs_self_airborne") != 0 or row_int_field(row, "obs_self_jump_phase") != 0:
        return "airborne"
    if row_int_field(row, "obs_self_routine_attack_state") != 0 or row_int_field(row, "obs_self_routine_1") == 4:
        return "attacking"
    if row_int_field(row, "obs_self_ground_action_start_allowed") != 0:
        return "actionable"
    return "unknown"


def tactical_opponent_phase(row: dict[str, object]) -> str:
    if row_int_field(row, "obs_opp_contact_reaction_state") != 0:
        return "contact_reaction"
    if (
        row_int_field(row, "obs_projectile_active") != 0
        and row_int_field(row, "obs_projectile_owner") == 2
        and row_int_field(row, "obs_opp_routine_attack_state") == 0
    ):
        return "projectile_active"
    if row_int_field(row, "obs_opp_airborne") != 0 or row_int_field(row, "obs_opp_jump_phase") != 0:
        return "jumping"
    if row_int_field(row, "obs_opp_routine_attack_state") != 0 or row_int_field(row, "obs_opp_routine_1") == 4:
        return "attacking"
    return "neutral"


def tactical_incoming_projectile_threat(row: dict[str, object], config: TacticalPolicyConfig) -> bool:
    if row_int_field(row, "obs_projectile_active") == 0 or row_int_field(row, "obs_projectile_owner") != 2:
        return False
    rel_x = row_int_field(row, "obs_projectile_rel_x")
    rel_y = row_int_field(row, "obs_projectile_rel_y")
    vel_x = row_int_field(row, "obs_projectile_vel_x")
    time_to_self = row_int_field(row, "obs_projectile_time_to_self")
    return (
        1 <= time_to_self <= config.incoming_projectile_max_time_to_self
        and 0 < rel_x <= config.incoming_projectile_max_dx
        and abs(rel_y) <= config.incoming_projectile_max_abs_y
        and vel_x < 0
    )


def tactical_threat_type(
    row: dict[str, object],
    spacing: str,
    self_phase_value: str,
    opponent_phase_value: str,
    config: TacticalPolicyConfig,
) -> str:
    abs_dx = abs(row_int_field(row, "obs_abs_dx"))
    if self_phase_value == "contact_reaction" and row_int_field(row, "obs_opp_routine_attack_state") != 0:
        return "multi_hit_pressure"
    if tactical_incoming_projectile_threat(row, config):
        return "incoming_projectile"
    if opponent_phase_value == "jumping" and abs_dx <= config.jump_in_max_abs_dx:
        return "jump_in"
    if spacing == "throw_range" and row_int_field(row, "obs_opp_routine_attack_state") != 0:
        return "throw_range"
    if row_int_field(row, "obs_opp_routine_attack_state") != 0 and abs_dx <= config.threat_attack_max_abs_dx:
        return "close_attack"
    if tactical_corner_context(row, config) == "self_cornered" and abs_dx <= config.poke_max_abs_dx:
        return "corner_pressure"
    return "none"


def tactical_opportunity_type(
    row: dict[str, object],
    spacing: str,
    self_phase_value: str,
    opponent_phase_value: str,
    threat: str,
) -> tuple[str, str]:
    if self_phase_value != "actionable":
        return "none", "self_not_actionable"
    if threat != "none":
        if threat == "jump_in":
            return "anti_air", "jump_in_threat"
        return "none", f"threat_{threat}"
    if opponent_phase_value == "jumping" and spacing in {"close", "poke", "fireball"}:
        return "anti_air", "opponent_jumping"
    if opponent_phase_value == "contact_reaction" and spacing in {"throw_range", "close", "poke"}:
        return "pressure", "opponent_contact_reaction"
    if spacing == "throw_range":
        return "throw_mixup", "throw_range_no_threat"
    if spacing == "poke":
        return "poke", "poke_range_no_threat"
    if spacing == "fireball":
        return "fireball_zoning", "fireball_range_no_threat"
    if spacing == "too_far":
        return "none", "too_far_no_threat"
    return "none", "neutral_no_clear_opportunity"


def tactical_recommended_intent(
    row: dict[str, object],
    spacing: str,
    corner: str,
    self_phase_value: str,
    threat: str,
    opportunity: str,
    opportunity_reason: str,
) -> tuple[str, str, str]:
    if self_phase_value == "attacking":
        return "wait", "self_attacking", "medium"
    if self_phase_value not in {"actionable", "airborne"}:
        return "hold_guard", "self_not_actionable", "medium"
    if threat == "incoming_projectile":
        return "hold_guard", "incoming_projectile", "high"
    if threat == "jump_in":
        return ("anti_air" if self_phase_value == "actionable" else "hold_guard"), "jump_in_threat", "high"
    if threat in {"close_attack", "multi_hit_pressure"}:
        return "hold_guard", threat, "high"
    if threat == "throw_range":
        return "escape", "throw_range_threat", "medium"
    if threat == "corner_pressure":
        return "escape", "corner_pressure", "medium"

    if self_phase_value == "airborne":
        return "air_poke", "airborne_no_clear_threat", "low"
    if opportunity == "anti_air":
        return "anti_air", opportunity_reason, "high"
    if opportunity == "pressure":
        return "pressure", opportunity_reason, "medium"
    if opportunity == "throw_mixup":
        return "throw", opportunity_reason, "medium"
    if opportunity == "poke":
        return "poke", opportunity_reason, "medium"
    if opportunity == "fireball_zoning":
        return "fireball_zoning", opportunity_reason, "medium"

    if spacing == "too_far":
        return "approach", "too_far_no_threat", "medium"
    if spacing == "fireball":
        return "adjust_spacing", "fireball_range_no_clear_opportunity", "low"
    if corner == "self_cornered":
        return "escape", "self_cornered_no_clear_opportunity", "low"
    return "wait", "neutral_no_clear_opportunity", "low"


def tactical_rotate_candidates(row: dict[str, object], candidates: tuple[str, ...], salt: int = 0) -> tuple[str, ...]:
    if len(candidates) <= 1:
        return candidates
    decision_id = row_int_field(row, "decision_id")
    episode_id = row_int_field(row, "episode_id")
    index = (decision_id + episode_id * 3 + salt) % len(candidates)
    return candidates[index:] + candidates[:index]


def tactical_first_valid_action(
    row: dict[str, object],
    candidates: tuple[str, ...],
    config: TacticalPolicyConfig,
) -> str | None:
    mask_config = DQNValidActionMaskConfig(config.valid_action_mask_mode)
    for candidate in candidates:
        action = canonical_tabular_action_name(candidate)
        if action is not None and dqn_valid_action_for_row(action, row, mask_config):
            return action
    return None


def tactical_decode_action(
    row: dict[str, object],
    intent: str,
    config: TacticalPolicyConfig,
) -> str:
    self_phase_value = tactical_self_phase(row)
    if self_phase_value == "attacking":
        return "neutral"
    if self_phase_value == "airborne":
        candidates = ("air-mk", "air-hk", "air-mp", "back")
    elif intent == "hold_guard":
        candidates = ("guard-crouch", "guard-stand", "back")
    elif intent == "low_guard":
        candidates = ("guard-crouch", "back", "guard-stand")
    elif intent == "anti_air":
        candidates = tactical_rotate_candidates(row, ("shoryuken-mp", "crouch-hp", "stand-hp", "back"), 1)
    elif intent == "punish":
        candidates = tactical_rotate_candidates(row, ("crouch-mk", "stand-hp", "throw", "shoryuken-mp"), 2)
    elif intent == "pressure":
        candidates = tactical_rotate_candidates(row, ("crouch-mk", "stand-mp", "throw", "stand-lp"), 3)
    elif intent == "throw":
        candidates = tactical_rotate_candidates(row, ("throw", "crouch-lk", "guard-crouch"), 4)
    elif intent == "poke":
        candidates = tactical_rotate_candidates(row, ("crouch-mk", "stand-mp", "fireball-mp", "crouch-hk"), 5)
    elif intent == "fireball_zoning":
        abs_dx = abs(row_int_field(row, "obs_abs_dx"))
        if abs_dx >= config.too_far_min_abs_dx:
            candidates = tactical_rotate_candidates(row, ("forward", "fireball-mp", "fireball-hp"), 6)
        else:
            candidates = tactical_rotate_candidates(row, ("fireball-mp", "forward", "fireball-hp", "back"), 7)
    elif intent == "approach":
        candidates = tactical_rotate_candidates(row, ("forward", "forward", "fireball-mp", "jump-forward-start"), 8)
    elif intent == "escape":
        candidates = tactical_rotate_candidates(row, ("back", "guard-crouch", "jump-back-start"), 9)
    elif intent == "air_poke":
        candidates = ("air-mk", "air-hk", "air-mp", "back")
    elif intent == "adjust_spacing":
        candidates = tactical_rotate_candidates(row, ("forward", "back", "fireball-mp"), 10)
    else:
        candidates = ("guard-crouch", "forward", "back")
    action = tactical_first_valid_action(row, candidates, config)
    if action is not None:
        return action
    fallback = tactical_first_valid_action(row, ("guard-crouch", "guard-stand", "back", "forward"), config)
    return fallback or "forward"


def tactical_policy_decision(row: dict[str, object], config: TacticalPolicyConfig) -> TacticalPolicyDecision:
    return tactical_policy_decision_with_intent(row, config, None, None, "heuristic")


def tactical_policy_decision_with_intent(
    row: dict[str, object],
    config: TacticalPolicyConfig,
    intent_override: str | None,
    intent_confidence_override: float | None,
    intent_source: str,
) -> TacticalPolicyDecision:
    spacing = tactical_spacing_bucket(row, config)
    corner = tactical_corner_context(row, config)
    self_phase_value = tactical_self_phase(row)
    opponent_phase_value = tactical_opponent_phase(row)
    threat = tactical_threat_type(row, spacing, self_phase_value, opponent_phase_value, config)
    opportunity, opportunity_reason = tactical_opportunity_type(
        row,
        spacing,
        self_phase_value,
        opponent_phase_value,
        threat,
    )
    intent, reason, confidence = tactical_recommended_intent(
        row,
        spacing,
        corner,
        self_phase_value,
        threat,
        opportunity,
        opportunity_reason,
    )
    if intent_override:
        intent = intent_override
        reason = f"{intent_source}:{reason}"
        if intent_confidence_override is None:
            confidence = "medium"
        elif intent_confidence_override >= 0.70:
            confidence = "high"
        elif intent_confidence_override >= 0.40:
            confidence = "medium"
        else:
            confidence = "low"
    action_name = tactical_decode_action(row, intent, config)
    return TacticalPolicyDecision(
        spacing_bucket=spacing,
        corner_context=corner,
        self_phase=self_phase_value,
        opponent_phase=opponent_phase_value,
        threat_type=threat,
        opportunity_type=opportunity,
        recommended_intent=intent,
        intent_reason=reason,
        label_confidence=confidence,
        action_name=action_name,
        intent_source=intent_source,
    )


def tactical_intent_feature_vector(model: dict[str, object], row: dict[str, object]) -> list[float]:
    feature_names = model.get("feature_names", list(DQN_FEATURE_NAMES))
    if not isinstance(feature_names, list):
        feature_names = list(DQN_FEATURE_NAMES)
    else:
        feature_names = list(sanitized_dqn_feature_names(feature_names, "tactical intent inference metadata"))
        if not feature_names:
            feature_names = list(DQN_FEATURE_NAMES)
    feature_scales = model.get("feature_scales", dict(DQN_FEATURE_SCALES))
    if not isinstance(feature_scales, dict):
        feature_scales = dict(DQN_FEATURE_SCALES)
    return dqn_feature_vector(row, feature_names, feature_scales)  # type: ignore[arg-type]


def tactical_intent_prediction(
    model: dict[str, object],
    row: dict[str, object],
) -> tuple[str, float] | None:
    intent_names = model.get("intent_names")
    if not isinstance(intent_names, list) or not intent_names:
        return None
    features = tactical_intent_feature_vector(model, row)
    logits = mlp_predict_values(model.get("layers"), features)
    if not logits:
        return None
    count = min(len(intent_names), len(logits))
    if count <= 0:
        return None
    max_logit = max(float(logits[index]) for index in range(count))
    exp_values = [math.exp(max(-80.0, min(80.0, float(logits[index]) - max_logit))) for index in range(count)]
    total = sum(exp_values)
    if total <= 0.0:
        return None
    probs = [value / total for value in exp_values]
    best_index = max(range(count), key=lambda index: (probs[index], str(intent_names[index])))
    return str(intent_names[best_index]), probs[best_index]


def tactical_macro_should_cancel(action: str, row: dict[str, object], config: TacticalPolicyConfig) -> bool:
    if action not in FIREBALL_ACTION_NAMES + TATSU_ACTION_NAMES + SHORYUKEN_ACTION_NAMES:
        return False
    spacing = tactical_spacing_bucket(row, config)
    self_phase_value = tactical_self_phase(row)
    opponent_phase_value = tactical_opponent_phase(row)
    threat = tactical_threat_type(row, spacing, self_phase_value, opponent_phase_value, config)
    return threat in {"incoming_projectile", "close_attack", "multi_hit_pressure", "throw_range"}


def tactical_actor_action_name(
    actor: ActorModel,
    obs_row: dict[str, object] | None,
    config: TacticalPolicyConfig,
) -> str | None:
    if actor.policy != "tactical" or not obs_row:
        return None
    prediction = tactical_intent_prediction(actor.tactical_intent_model, obs_row) if actor.tactical_intent_model else None
    if prediction is None:
        return tactical_policy_decision(obs_row, config).action_name
    intent, confidence = prediction
    return tactical_policy_decision_with_intent(obs_row, config, intent, confidence, "learned").action_name


def is_current_transition_schema_row(row: dict[str, object]) -> bool:
    return row_int_field(row, "transition_schema_version") in SUPPORTED_TRANSITION_SCHEMA_VERSIONS


def require_current_transition_schema(row: dict[str, object], context: str = "transition row") -> None:
    version = row_int_field(row, "transition_schema_version")
    if version not in SUPPORTED_TRANSITION_SCHEMA_VERSIONS:
        supported = ",".join(str(item) for item in sorted(SUPPORTED_TRANSITION_SCHEMA_VERSIONS))
        raise ValueError(f"{context}: transition_schema_version={version} expected one of {supported}")


def is_demo_transition_row(row: dict[str, object]) -> bool:
    return row_int_field(row, "execution_source") in DEMO_EXECUTION_SOURCES


def is_training_mode_transition_row(row: dict[str, object]) -> bool:
    return row_int_field(row, "mode_type") in TRAINING_MODE_TYPES


def action_name_from_policy_meta(action_id: int, sub_action_id: int) -> str | None:
    action_name = TABULAR_ACTION_NAMES_BY_POLICY_META.get((action_id, sub_action_id))
    if action_name is not None and action_name in TABULAR_ACTION_NAMES:
        return action_name
    if action_id in (RL_POLICY_ACTION_RYU_FIREBALL, RL_POLICY_ACTION_KEN_FIREBALL):
        return "fireball-lp"
    if action_id in (RL_POLICY_ACTION_RYU_SHORYUKEN, RL_POLICY_ACTION_KEN_SHORYUKEN):
        return "shoryuken-mp"
    if action_id in (RL_POLICY_ACTION_RYU_TATSU, RL_POLICY_ACTION_KEN_TATSU):
        return "tatsu-mk"
    if action_id == RL_POLICY_ACTION_THROW:
        return "throw"
    return action_name


def engine_outcome_present(row: dict[str, object]) -> bool:
    return (
        self_engine_row_int_field(row, "engine_label_source") != 0
        or self_engine_row_int_field(row, "engine_action_id") != 0
        or self_engine_row_int_field(row, "engine_sub_action_id") != 0
    )


def engine_outcome_action_name(row: dict[str, object]) -> str | None:
    return action_name_from_policy_meta(
        self_engine_row_int_field(row, "engine_action_id"),
        self_engine_row_int_field(row, "engine_sub_action_id"),
    )


def demo_attribution_present(row: dict[str, object]) -> bool:
    return engine_outcome_present(row)


def engine_attributed_action_name(row: dict[str, object]) -> str | None:
    return engine_outcome_action_name(row)


def action_selection_from_fields(
    row: dict[str, object],
    action_field: str,
    sub_action_field: str,
    step_field: str,
    source: str,
) -> ActionSelection:
    action_name = action_name_from_policy_meta(row_int_field(row, action_field), row_int_field(row, sub_action_field))
    return ActionSelection(action_name, row_int_field(row, step_field), source)


def engine_action_selection(row: dict[str, object]) -> ActionSelection:
    action_name = action_name_from_policy_meta(
        self_engine_row_int_field(row, "engine_action_id"),
        self_engine_row_int_field(row, "engine_sub_action_id"),
    )
    return ActionSelection(action_name, 0, "engine" if action_name is not None else "none")


def select_training_action(row: dict[str, object], source_mode: str = "auto") -> ActionSelection:
    if source_mode not in TRAINING_ACTION_SOURCES:
        raise ValueError(f"unknown training action source: {source_mode}")

    require_current_transition_schema(row)
    policy = action_selection_from_fields(
        row,
        "policy_executed_action_id",
        "policy_executed_sub_action_id",
        "policy_executed_action_step",
        "policy",
    )
    input_selection = action_selection_from_fields(
        row,
        "input_action_id",
        "input_sub_action_id",
        "input_action_step",
        "input",
    )
    engine = engine_action_selection(row)

    if source_mode == "policy":
        return policy if policy.name is not None else ActionSelection(None, 0, "none")
    if source_mode == "input":
        return input_selection if input_selection.name is not None else ActionSelection(None, 0, "none")
    if source_mode == "engine":
        return engine
    if source_mode == "prefer-engine":
        if engine.name is not None:
            return engine
        if input_selection.name is not None:
            return input_selection
        if policy.name is not None:
            return policy
        return ActionSelection(None, 0, "none")

    if is_demo_transition_row(row):
        if engine.name is not None:
            return engine
        if input_selection.name is not None:
            return input_selection
        return ActionSelection(None, 0, "none")
    if policy.name is not None:
        return policy
    return ActionSelection(None, 0, "none")


def tabular_training_reward(row: dict[str, object], training_mode_hp_delta_mode: str = "raw") -> float:
    opp_delta = int(row.get("delta_opp_hp", 0) or 0)
    self_delta = int(row.get("delta_self_hp", 0) or 0)
    if training_mode_hp_delta_mode == "damage-only" and is_training_mode_transition_row(row):
        opp_delta = max(0, opp_delta)
        self_delta = max(0, self_delta)
    return float(opp_delta - self_delta)


def dqn_feature_value(row: dict[str, object], name: str) -> float:
    if name.startswith("obs_self_routine_1_is_"):
        try:
            value = int(name.rsplit("_", 1)[1])
        except ValueError:
            return 0.0
        return 1.0 if row_int_field(row, "obs_self_routine_1") == value else 0.0
    if name.startswith("obs_self_routine_2_is_"):
        try:
            value = int(name.rsplit("_", 1)[1])
        except ValueError:
            return 0.0
        return 1.0 if row_int_field(row, "obs_self_routine_2") == value else 0.0
    if name.startswith("obs_opp_routine_1_is_"):
        try:
            value = int(name.rsplit("_", 1)[1])
        except ValueError:
            return 0.0
        return 1.0 if row_int_field(row, "obs_opp_routine_1") == value else 0.0
    if name.startswith("obs_opp_routine_2_is_"):
        try:
            value = int(name.rsplit("_", 1)[1])
        except ValueError:
            return 0.0
        return 1.0 if row_int_field(row, "obs_opp_routine_2") == value else 0.0
    try:
        return float(row.get(name, 0.0) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def dqn_feature_vector(
    row: dict[str, object],
    feature_names: tuple[str, ...] | list[str] = DQN_FEATURE_NAMES,
    feature_scales: dict[str, float] | None = None,
) -> list[float]:
    scales = feature_scales or DQN_FEATURE_SCALES
    features: list[float] = []
    for name in feature_names:
        value = dqn_feature_value(row, str(name))
        scale = max(1e-6, float(scales.get(str(name), 1.0) or 1.0))
        normalized = value / scale
        features.append(max(-4.0, min(4.0, normalized)))
    return features


def mlp_predict_values(layers: object, activations: list[float]) -> list[float]:
    if not isinstance(layers, list):
        return []
    for layer in layers:
        if not isinstance(layer, dict):
            return []
        weights = layer.get("weights")
        bias = layer.get("bias")
        if not isinstance(weights, list) or not isinstance(bias, list):
            return []
        next_values: list[float] = []
        for raw_row, raw_bias in zip(weights, bias):
            if not isinstance(raw_row, list):
                return []
            try:
                value = float(raw_bias) + sum(float(weight) * input_value for weight, input_value in zip(raw_row, activations))
            except (TypeError, ValueError):
                return []
            next_values.append(value)
        if str(layer.get("activation", "linear") or "linear") == "relu":
            next_values = [max(0.0, value) for value in next_values]
        activations = next_values
    return activations


def dqn_predict_values(dqn_model: dict[str, object], row: dict[str, object]) -> list[float]:
    feature_names = dqn_model.get("feature_names", list(DQN_FEATURE_NAMES))
    if not isinstance(feature_names, list):
        feature_names = list(DQN_FEATURE_NAMES)
    else:
        feature_names = list(sanitized_dqn_feature_names(feature_names, "dqn inference metadata"))
        if not feature_names:
            feature_names = list(DQN_FEATURE_NAMES)
    feature_scales = dqn_model.get("feature_scales", dict(DQN_FEATURE_SCALES))
    if not isinstance(feature_scales, dict):
        feature_scales = dict(DQN_FEATURE_SCALES)
    activations = dqn_feature_vector(row, feature_names, feature_scales)  # type: ignore[arg-type]
    return mlp_predict_values(dqn_model.get("layers"), activations)


def actor_critic_feature_vector(actor_critic_model: dict[str, object], row: dict[str, object]) -> list[float]:
    feature_names = actor_critic_model.get("feature_names", list(DQN_FEATURE_NAMES))
    if not isinstance(feature_names, list):
        feature_names = list(DQN_FEATURE_NAMES)
    else:
        feature_names = list(sanitized_dqn_feature_names(feature_names, "actor-critic inference metadata"))
        if not feature_names:
            feature_names = list(DQN_FEATURE_NAMES)
    feature_scales = actor_critic_model.get("feature_scales", dict(DQN_FEATURE_SCALES))
    if not isinstance(feature_scales, dict):
        feature_scales = dict(DQN_FEATURE_SCALES)
    return dqn_feature_vector(row, feature_names, feature_scales)  # type: ignore[arg-type]


def actor_critic_predict_logits_value(
    actor_critic_model: dict[str, object],
    row: dict[str, object],
) -> tuple[list[float], float | None]:
    features = actor_critic_feature_vector(actor_critic_model, row)
    logits = mlp_predict_values(actor_critic_model.get("actor_layers"), features)
    value_values = mlp_predict_values(actor_critic_model.get("value_layers"), features)
    value = float(value_values[0]) if value_values else None
    return logits, value


def dqn_support_prior_penalty(
    action: str,
    action_counts: dict[str, int],
    action_rewards: dict[str, float],
    config: DQNSupportPriorConfig,
) -> float:
    if not config.enabled or action in config.exempt_actions or not action_counts:
        return 0.0
    count = int(action_counts.get(action, 0))
    reward = float(action_rewards.get(action, 0.0))
    penalty = 0.0
    if config.min_action_count > 0 and config.count_penalty > 0.0 and count < config.min_action_count:
        missing_ratio = (config.min_action_count - count) / max(1, config.min_action_count)
        penalty += config.count_penalty * max(0.0, min(1.0, missing_ratio))
    if config.negative_mean_penalty > 0.0 and count > 0:
        mean_reward = reward / count
        if mean_reward <= 0.0:
            penalty += config.negative_mean_penalty
    return penalty


def dqn_ranked_action_scores(
    actions: tuple[str, ...],
    dqn_model: dict[str, object],
    metadata: dict[str, object],
    row: dict[str, object],
    support_prior_config: DQNSupportPriorConfig = DQNSupportPriorConfig(),
    valid_action_mask_config: DQNValidActionMaskConfig = DQNValidActionMaskConfig(),
    projectile_timing_prior_config: DQNProjectileTimingPriorConfig = DQNProjectileTimingPriorConfig(),
    shoryuken_context_prior_config: DQNShoryukenContextPriorConfig = DQNShoryukenContextPriorConfig(),
    ground_normal_context_prior_config: DQNGroundNormalContextPriorConfig = DQNGroundNormalContextPriorConfig(),
    fireball_zoning_prior_config: DQNFireballZoningPriorConfig = DQNFireballZoningPriorConfig(),
    threat_defense_prior_config: DQNThreatDefensePriorConfig = DQNThreatDefensePriorConfig(),
) -> list[tuple[str, float]]:
    values = dqn_predict_values(dqn_model, row)
    if not values:
        return []
    action_counts = _coerce_action_count_map(metadata.get("action_counts")) if support_prior_config.enabled else {}
    action_rewards = _coerce_action_reward_map(metadata.get("action_rewards")) if support_prior_config.enabled else {}
    scored_actions: list[tuple[str, float]] = []
    for index, action in enumerate(actions):
        if index >= len(values) or action not in TABULAR_ACTION_NAMES:
            continue
        if not dqn_valid_action_for_row(action, row, valid_action_mask_config):
            continue
        score = float(values[index])
        score -= dqn_support_prior_penalty(action, action_counts, action_rewards, support_prior_config)
        score -= dqn_projectile_timing_prior_penalty(action, row, projectile_timing_prior_config)
        score -= dqn_shoryuken_context_prior_penalty(action, row, shoryuken_context_prior_config)
        score -= dqn_ground_normal_context_prior_penalty(action, row, ground_normal_context_prior_config)
        score -= dqn_threat_defense_prior_penalty(action, row, threat_defense_prior_config)
        score += dqn_fireball_zoning_prior_bonus(action, row, fireball_zoning_prior_config)
        score += dqn_threat_defense_prior_bonus(action, row, threat_defense_prior_config)
        scored_actions.append((action, score))
    return sorted(scored_actions, key=lambda item: (item[1], item[0]), reverse=True)


def dqn_action_hard_blocked_by_priors(
    action: str,
    row: dict[str, object],
    shoryuken_context_prior_config: DQNShoryukenContextPriorConfig = DQNShoryukenContextPriorConfig(),
) -> bool:
    return dqn_shoryuken_context_prior_penalty(action, row, shoryuken_context_prior_config) >= 1_000_000.0


class TabularPolicyLearner:
    def __init__(
        self,
        alpha: float,
        epsilon: float,
        fallback_policy: str,
        actions: tuple[str, ...] = TABULAR_DEFAULT_ACTIONS,
    ) -> None:
        self._alpha = min(1.0, max(0.0, alpha))
        self._epsilon = min(1.0, max(0.0, epsilon))
        self._fallback_policy = fallback_policy
        self._actions = actions
        self._q_table: dict[str, dict[str, float]] = {}
        self._q_counts: dict[str, dict[str, int]] = {}
        self._updates = 0
        self._ignored_actions = 0
        self._delayed_reward_updates = 0
        self._training_reward_total = 0.0
        self._last_explicit_action: tuple[str, str] | None = None
        self._lock = threading.Lock()

    @property
    def fallback_policy(self) -> str:
        return self._fallback_policy

    def update(self, row: dict[str, object]) -> str | None:
        try:
            action_selection = select_training_action(row, "auto")
        except ValueError:
            return None
        action_name = action_selection.name
        reward = tabular_training_reward(row)
        if action_name is None or action_name not in self._actions:
            with self._lock:
                self._ignored_actions += 1
                if reward != 0.0 and self._last_explicit_action is not None:
                    state_key, delayed_action = self._last_explicit_action
                    scores = self._q_table.setdefault(state_key, {name: 0.0 for name in self._actions})
                    counts = self._q_counts.setdefault(state_key, {name: 0 for name in self._actions})
                    old_score = float(scores.get(delayed_action, 0.0))
                    scores[delayed_action] = old_score + self._alpha * (reward - old_score)
                    counts[delayed_action] = int(counts.get(delayed_action, 0)) + 1
                    self._updates += 1
                    self._delayed_reward_updates += 1
                    self._training_reward_total += reward
                    return state_key
            return None
        state_key = tabular_state_key(row)
        with self._lock:
            scores = self._q_table.setdefault(state_key, {name: 0.0 for name in self._actions})
            counts = self._q_counts.setdefault(state_key, {name: 0 for name in self._actions})
            old_score = float(scores.get(action_name, 0.0))
            scores[action_name] = old_score + self._alpha * (reward - old_score)
            counts[action_name] = int(counts.get(action_name, 0)) + 1
            self._updates += 1
            self._training_reward_total += reward
            self._last_explicit_action = (state_key, action_name)
        return state_key

    def snapshot(self, min_action_count: int = 1) -> dict[str, object]:
        with self._lock:
            q_table = {state: dict(scores) for state, scores in self._q_table.items()}
            q_counts = {state: dict(counts) for state, counts in self._q_counts.items()}
            top_state = ""
            top_action = ""
            top_score = 0.0
            top_count = 0
            ready_state = ""
            ready_action = ""
            ready_score = 0.0
            ready_count = 0
            min_count = max(1, min_action_count)
            ready_actions, ready_dx_actions, ready_opp_attack_actions, ready_threat_dx_actions = summarize_ready_actions(
                q_table, q_counts, self._actions, min_count
            )
            for state, scores in q_table.items():
                if not scores:
                    continue
                action, score = max(scores.items(), key=lambda item: (item[1], item[0]))
                if not top_state or score > top_score:
                    top_state = state
                    top_action = action
                    top_score = score
                    top_count = int(q_counts.get(state, {}).get(action, 0))
                for ready_candidate, ready_candidate_score in scores.items():
                    count = int(q_counts.get(state, {}).get(ready_candidate, 0))
                    if count < min_count or float(ready_candidate_score) <= 0.0:
                        continue
                    if not ready_state or float(ready_candidate_score) > ready_score:
                        ready_state = state
                        ready_action = ready_candidate
                        ready_score = float(ready_candidate_score)
                        ready_count = count
            return {
                "q_table": q_table,
                "q_counts": q_counts,
                "actions": self._actions,
                "epsilon": self._epsilon,
                "fallback_policy": self._fallback_policy,
                "states": len(q_table),
                "updates": self._updates,
                "ignored_actions": self._ignored_actions,
                "delayed_reward_updates": self._delayed_reward_updates,
                "training_reward_total": self._training_reward_total,
                "top_state": top_state,
                "top_action": top_action,
                "top_score": top_score,
                "top_count": top_count,
                "ready_state": ready_state,
                "ready_action": ready_action,
                "ready_score": ready_score,
                "ready_count": ready_count,
                "ready_actions": ready_actions,
                "ready_dx_actions": ready_dx_actions,
                "ready_opp_attack_actions": ready_opp_attack_actions,
                "ready_threat_dx_actions": ready_threat_dx_actions,
            }


def learner_replay_row(row: dict[str, object]) -> dict[str, object] | None:
    require_current_transition_schema(row, "learner replay row")
    return {
        "run_id": int(row.get("run_id", 0) or 0),
        "episode_id": int(row.get("episode_id", 0) or 0),
        "decision_id": int(row.get("decision_id", 0) or 0),
        "round_num": int(row.get("round_num", 0) or 0),
        "mode_type": int(row.get("mode_type", 0) or 0),
        "play_mode": int(row.get("play_mode", 0) or 0),
        "obs_frame": int(row.get("obs_frame", 0) or 0),
        "transition_schema_version": int(row.get("transition_schema_version", 0) or 0),
        "agent_character_id": int(row.get("agent_character_id", 0) or 0),
        "opponent_character_id": int(row.get("opponent_character_id", 0) or 0),
        "requested_action_wire": int(row.get("requested_action_wire", 0) or 0),
        "executed_action_wire": int(row.get("executed_action_wire", 0) or 0),
        "policy_requested_action_id": int(row.get("policy_requested_action_id", 0) or 0),
        "policy_requested_sub_action_id": int(row.get("policy_requested_sub_action_id", 0) or 0),
        "policy_requested_action_step": int(row.get("policy_requested_action_step", 0) or 0),
        "policy_executed_action_id": int(row.get("policy_executed_action_id", 0) or 0),
        "policy_executed_sub_action_id": int(row.get("policy_executed_sub_action_id", 0) or 0),
        "policy_executed_action_step": int(row.get("policy_executed_action_step", 0) or 0),
        "input_action_id": int(row.get("input_action_id", 0) or 0),
        "input_sub_action_id": int(row.get("input_sub_action_id", 0) or 0),
        "input_action_step": int(row.get("input_action_step", 0) or 0),
        "input_label_source": int(row.get("input_label_source", 0) or 0),
        "engine_action_id": int(row.get("engine_action_id", 0) or 0),
        "engine_sub_action_id": int(row.get("engine_sub_action_id", 0) or 0),
        "engine_routine_1": int(row.get("engine_routine_1", 0) or 0),
        "engine_routine_2": int(row.get("engine_routine_2", 0) or 0),
        "engine_kind_of_waza": int(row.get("engine_kind_of_waza", 0) or 0),
        "engine_current_attack": int(row.get("engine_current_attack", 0) or 0),
        "engine_label_source": int(row.get("engine_label_source", 0) or 0),
        "engine_lag_frames": int(row.get("engine_lag_frames", 0) or 0),
        "self_engine_action_id": int(row.get("self_engine_action_id", 0) or 0),
        "self_engine_sub_action_id": int(row.get("self_engine_sub_action_id", 0) or 0),
        "self_engine_routine_1": int(row.get("self_engine_routine_1", 0) or 0),
        "self_engine_routine_2": int(row.get("self_engine_routine_2", 0) or 0),
        "self_engine_kind_of_waza": int(row.get("self_engine_kind_of_waza", 0) or 0),
        "self_engine_current_attack": int(row.get("self_engine_current_attack", 0) or 0),
        "self_engine_label_source": int(row.get("self_engine_label_source", 0) or 0),
        "self_engine_lag_frames": int(row.get("self_engine_lag_frames", 0) or 0),
        "opp_engine_action_id": int(row.get("opp_engine_action_id", 0) or 0),
        "opp_engine_sub_action_id": int(row.get("opp_engine_sub_action_id", 0) or 0),
        "opp_engine_routine_1": int(row.get("opp_engine_routine_1", 0) or 0),
        "opp_engine_routine_2": int(row.get("opp_engine_routine_2", 0) or 0),
        "opp_engine_kind_of_waza": int(row.get("opp_engine_kind_of_waza", 0) or 0),
        "opp_engine_current_attack": int(row.get("opp_engine_current_attack", 0) or 0),
        "opp_engine_label_source": int(row.get("opp_engine_label_source", 0) or 0),
        "opp_engine_lag_frames": int(row.get("opp_engine_lag_frames", 0) or 0),
        "delta_self_hp": int(row.get("delta_self_hp", 0) or 0),
        "delta_opp_hp": int(row.get("delta_opp_hp", 0) or 0),
        "delta_self_stun": int(row.get("delta_self_stun", 0) or 0),
        "delta_opp_stun": int(row.get("delta_opp_stun", 0) or 0),
        "delta_self_y": int(row.get("delta_self_y", 0) or 0),
        "delta_opp_y": int(row.get("delta_opp_y", 0) or 0),
        "delta_self_forward": int(row.get("delta_self_forward", 0) or 0),
        "delta_opp_forward": int(row.get("delta_opp_forward", 0) or 0),
        "obs_abs_dx": int(row.get("obs_abs_dx", 0) or 0),
        "obs_abs_dy": int(row.get("obs_abs_dy", 0) or 0),
        "obs_self_front_edge_dist": int(row.get("obs_self_front_edge_dist", 0) or 0),
        "obs_self_back_edge_dist": int(row.get("obs_self_back_edge_dist", 0) or 0),
        "obs_opp_front_edge_dist": int(row.get("obs_opp_front_edge_dist", 0) or 0),
        "obs_opp_back_edge_dist": int(row.get("obs_opp_back_edge_dist", 0) or 0),
        "obs_opp_in_front": int(row.get("obs_opp_in_front", 0) or 0),
        "obs_self_routine_1": int(row.get("obs_self_routine_1", 0) or 0),
        "obs_self_routine_2": int(row.get("obs_self_routine_2", 0) or 0),
        "obs_opp_routine_1": int(row.get("obs_opp_routine_1", 0) or 0),
        "obs_opp_routine_2": int(row.get("obs_opp_routine_2", 0) or 0),
        "obs_self_routine_attack_state": int(row.get("obs_self_routine_attack_state", 0) or 0),
        "obs_opp_routine_attack_state": int(row.get("obs_opp_routine_attack_state", 0) or 0),
        "obs_self_contact_reaction_state": int(row.get("obs_self_contact_reaction_state", 0) or 0),
        "obs_opp_contact_reaction_state": int(row.get("obs_opp_contact_reaction_state", 0) or 0),
        "obs_self_airborne": int(row.get("obs_self_airborne", 0) or 0),
        "obs_self_jump_phase": int(row.get("obs_self_jump_phase", 0) or 0),
        "obs_self_ground_action_start_allowed": int(row.get("obs_self_ground_action_start_allowed", 0) or 0),
        "obs_self_jump_start_allowed": int(row.get("obs_self_jump_start_allowed", 0) or 0),
        "obs_self_air_attack_allowed": int(row.get("obs_self_air_attack_allowed", 0) or 0),
        "obs_projectile_active": int(row.get("obs_projectile_active", 0) or 0),
        "obs_projectile_owner": int(row.get("obs_projectile_owner", 0) or 0),
        "obs_projectile_rel_x": int(row.get("obs_projectile_rel_x", 0) or 0),
        "obs_projectile_rel_y": int(row.get("obs_projectile_rel_y", 0) or 0),
        "obs_projectile_vel_x": int(row.get("obs_projectile_vel_x", 0) or 0),
        "obs_projectile_time_to_self": int(row.get("obs_projectile_time_to_self", 0) or 0),
        "self_throw_started": int(row.get("self_throw_started", 0) or 0),
        "opp_throw_started": int(row.get("opp_throw_started", 0) or 0),
        "self_throw_caught_started": int(row.get("self_throw_caught_started", 0) or 0),
        "opp_throw_caught_started": int(row.get("opp_throw_caught_started", 0) or 0),
        "self_throw_seen": int(row.get("self_throw_seen", 0) or 0),
        "opp_throw_seen": int(row.get("opp_throw_seen", 0) or 0),
        "self_throw_caught_seen": int(row.get("self_throw_caught_seen", 0) or 0),
        "opp_throw_caught_seen": int(row.get("opp_throw_caught_seen", 0) or 0),
        "final_self_hp": int(row.get("final_self_hp", 0) or 0),
        "final_opp_hp": int(row.get("final_opp_hp", 0) or 0),
        "model_version_executed": int(row.get("model_version_executed", 0) or 0),
        "execution_source": int(row.get("execution_source", 0) or 0),
        "reward_accum": float(row.get("reward_accum", 0.0) or 0.0),
        "done": bool(row.get("done", False)),
        "terminal_reason": str(row.get("terminal_reason", "unknown") or "unknown"),
    }


def mister_ssh_args() -> list[str]:
    connect_timeout = int(os.environ.get("MISTER_SSH_CONNECT_TIMEOUT", "10") or "10")
    return [
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        f"ConnectTimeout={connect_timeout}",
        "-o",
        "ConnectionAttempts=1",
    ]


def mister_ssh_password_args() -> list[str]:
    return mister_ssh_args() + [
        "-o",
        "PubkeyAuthentication=no",
        "-o",
        "PreferredAuthentications=password",
        "-o",
        "NumberOfPasswordPrompts=1",
    ]


def mister_ssh_key_only_args() -> list[str]:
    return mister_ssh_args() + [
        "-o",
        "BatchMode=yes",
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "IdentityAgent=none",
        "-o",
        "PreferredAuthentications=publickey",
        "-o",
        "NumberOfPasswordPrompts=0",
    ]


class TransitionPuller(threading.Thread):
    def __init__(
        self,
        local_path: str,
        pull_interval_sec: float,
        remote_host: str | None,
        remote_user: str,
        remote_password: str | None,
        remote_path: str | None,
        local_source_path: str | None,
    ) -> None:
        super().__init__(daemon=True)
        self._local_path = local_path
        self._pull_interval_sec = max(0.2, pull_interval_sec)
        self._remote_host = remote_host
        self._remote_user = remote_user
        self._remote_password = remote_password
        self._remote_path = remote_path
        self._local_source_path = local_source_path
        self._last_error: str | None = None
        self._pull_count = 0

    def _source_label(self) -> str:
        if self._local_source_path:
            return self._local_source_path
        return f"{self._remote_user}@{self._remote_host}:{self._remote_path}"

    def _download_remote_to_temp(self, temp_path: str) -> None:
        if not self._remote_host or not self._remote_path:
            raise RuntimeError("remote transition pull requires host and remote path")

        target = f"{self._remote_user}@{self._remote_host}:{self._remote_path}"
        if self._remote_password:
            command = [
                "sshpass",
                "-p",
                self._remote_password,
                "scp",
                *mister_ssh_password_args(),
                target,
                temp_path,
            ]
        else:
            command = ["scp", *mister_ssh_key_only_args(), target, temp_path]

        subprocess.run(command, check=True, capture_output=True, text=True)

    def _copy_local_source_to_temp(self, temp_path: str) -> None:
        if not self._local_source_path:
            raise RuntimeError("local source path missing")
        with open(self._local_source_path, "rb") as src, open(temp_path, "wb") as dst:
            dst.write(src.read())

    def _fetch_to_temp(self, temp_path: str) -> None:
        if self._local_source_path:
            self._copy_local_source_to_temp(temp_path)
            return
        self._download_remote_to_temp(temp_path)

    def _sync_local_mirror(self, temp_path: str) -> bool:
        os.makedirs(os.path.dirname(self._local_path) or ".", exist_ok=True)
        with open(temp_path, "rb") as fetched:
            fetched_bytes = fetched.read()

        if not os.path.exists(self._local_path):
            with open(self._local_path, "wb") as dst:
                dst.write(fetched_bytes)
            return True

        with open(self._local_path, "rb") as current:
            current_bytes = current.read()

        if fetched_bytes == current_bytes:
            return False

        # Fast path: remote log only grew, so append the new suffix and keep the tailer position stable.
        if fetched_bytes.startswith(current_bytes):
            with open(self._local_path, "ab") as dst:
                dst.write(fetched_bytes[len(current_bytes) :])
            return True

        # Fallback: rewrite the local mirror. The learner tailer dedupes imported rows by key.
        with open(self._local_path, "wb") as dst:
            dst.write(fetched_bytes)
        return True

    def run(self) -> None:
        print(f"PULLER watching {self._source_label()} -> {self._local_path}", flush=True)
        while True:
            temp_path = ""
            try:
                with tempfile.NamedTemporaryFile(prefix="rl-transitions-pull-", suffix=".ndjson", delete=False) as temp:
                    temp_path = temp.name
                self._fetch_to_temp(temp_path)
                if self._sync_local_mirror(temp_path):
                    self._pull_count += 1
                    print(f"PULLER updated local mirror pulls={self._pull_count}", flush=True)
                self._last_error = None
            except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
                message = str(exc)
                if self._last_error != message:
                    print(f"PULLER error: {message}", flush=True)
                    self._last_error = message
            finally:
                if temp_path:
                    try:
                        os.unlink(temp_path)
                    except OSError:
                        pass
            time.sleep(self._pull_interval_sec)


class TransitionBatchServer(threading.Thread):
    def __init__(self, host: str, port: int, transition_log: str, combat_event_log: str | None = None) -> None:
        super().__init__(daemon=True)
        self._host = host
        self._port = port
        self._transition_log = transition_log
        self._combat_event_log = combat_event_log
        self._write_lock = threading.Lock()

    @staticmethod
    def _recv_exact(conn: socket.socket, size: int) -> bytes:
        payload = bytearray()
        while len(payload) < size:
            chunk = conn.recv(size - len(payload))
            if not chunk:
                break
            payload.extend(chunk)
        return bytes(payload)

    @staticmethod
    def _is_combat_event_line(line: bytes) -> bool:
        return b'"combat_event_schema_version"' in line

    @staticmethod
    def _write_lines(path: str, lines: list[bytes]) -> None:
        if not lines:
            return
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "ab") as stream:
            for line in lines:
                stream.write(line)

    def _append_payload(self, payload: bytes) -> tuple[int, int, int]:
        transition_lines: list[bytes] = []
        combat_event_lines: list[bytes] = []
        dropped_combat_events = 0

        for line in payload.splitlines(keepends=True):
            if not line.strip():
                continue
            if self._is_combat_event_line(line):
                if self._combat_event_log:
                    combat_event_lines.append(line)
                else:
                    dropped_combat_events += 1
            else:
                transition_lines.append(line)

        os.makedirs(os.path.dirname(self._transition_log) or ".", exist_ok=True)
        with self._write_lock:
            self._write_lines(self._transition_log, transition_lines)
            if self._combat_event_log:
                self._write_lines(self._combat_event_log, combat_event_lines)
        return len(transition_lines), len(combat_event_lines), dropped_combat_events

    def run(self) -> None:
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((self._host, self._port))
        server.listen()
        print(f"TRANSITIONS listening on {self._host}:{self._port} -> {self._transition_log}", flush=True)
        while True:
            conn, addr = server.accept()
            with conn:
                try:
                    header_data = self._recv_exact(conn, TRANSITION_BATCH_HEADER.size)
                    if len(header_data) != TRANSITION_BATCH_HEADER.size:
                        continue
                    (
                        magic,
                        version,
                        packet_type,
                        nonce,
                        run_id,
                        episode_id,
                        payload_len,
                        row_count,
                    ) = TRANSITION_BATCH_HEADER.unpack(header_data)
                    if magic != MAGIC or version != PROTOCOL_VERSION or packet_type != 6:
                        continue
                    payload = self._recv_exact(conn, payload_len)
                    if len(payload) != payload_len:
                        continue
                    transition_rows, combat_event_rows, dropped_combat_events = self._append_payload(payload)
                    ack = TRANSITION_BATCH_ACK.pack(MAGIC, PROTOCOL_VERSION, 7, nonce, run_id, episode_id, 0)
                    conn.sendall(ack)
                    print(
                        f"TRANSITIONS batch run={run_id} ep={episode_id} rows={transition_rows}/{row_count} "
                        f"combat_events={combat_event_rows} dropped_combat_events={dropped_combat_events} "
                        f"bytes={payload_len} from={addr[0]}:{addr[1]}",
                        flush=True,
                    )
                except OSError:
                    continue


class LearnerLogTailer(threading.Thread):
    def __init__(
        self,
        path: str,
        stats_interval_sec: float,
        tail_from_start: bool,
        inference_stats: InferenceStats,
        replay_capacity: int,
        learner_batch_size: int,
        learner_warmup_rows: int,
        model_store: ActorModelStore,
        learner_auto_publish: bool,
        learner_publish_interval_sec: float,
        learner_publish_policy: str | None,
        tabular_alpha: float,
        tabular_epsilon: float,
        tabular_fallback_policy: str,
        tabular_actions: tuple[str, ...],
        tabular_min_action_count: int,
    ) -> None:
        super().__init__(daemon=True)
        self._path = path
        self._stats_interval_sec = max(0.1, stats_interval_sec)
        self._tail_from_start = tail_from_start
        self._inference_stats = inference_stats
        self._replay = ReplayBuffer(replay_capacity)
        self._learner_batch_size = max(1, learner_batch_size)
        self._learner_warmup_rows = max(1, learner_warmup_rows)
        self._model_store = model_store
        self._learner_auto_publish = learner_auto_publish
        self._learner_publish_interval_ns = int(max(0.1, learner_publish_interval_sec) * 1_000_000_000)
        self._learner_publish_policy = learner_publish_policy
        self._tabular_learner = TabularPolicyLearner(
            tabular_alpha,
            tabular_epsilon,
            tabular_fallback_policy,
            actions=tabular_actions,
        )
        self._tabular_min_action_count = max(1, tabular_min_action_count)
        self._next_publish_ns = time.monotonic_ns() + self._learner_publish_interval_ns
        self._last_published_tabular_updates = -1
        self._rows = 0
        self._imported_rows = 0
        self._skipped_unexecuted = 0
        self._reward_positive = 0
        self._reward_negative = 0
        self._reward_zero = 0
        self._done = 0
        self._latest_run_id = 0
        self._latest_episode = 0
        self._latest_model_version_executed = 0
        self._latest_model_policy_executed = "unknown"
        self._policy_buckets: dict[str, PolicyBucketStats] = {}
        self._seen_keys: set[tuple[int, int, int]] = set()

    def _consume_row(self, row: dict[str, object]) -> None:
        self._rows += 1
        self._latest_run_id = int(row.get("run_id", self._latest_run_id) or 0)
        self._latest_episode = int(row.get("episode_id", self._latest_episode) or 0)
        self._latest_model_version_executed = int(
            row.get("model_version_executed", self._latest_model_version_executed) or 0
        )
        self._latest_model_policy_executed = self._model_store.policy_for_version(self._latest_model_version_executed)
        if row.get("done") is True:
            self._done += 1

        replay_key = (
            int(row.get("run_id", 0) or 0),
            int(row.get("episode_id", 0) or 0),
            int(row.get("decision_id", 0) or 0),
        )
        if replay_key in self._seen_keys:
            return

        try:
            replay_row = learner_replay_row(row)
        except ValueError:
            self._skipped_unexecuted += 1
            return
        if replay_row is None:
            self._skipped_unexecuted += 1
            return

        self._seen_keys.add(replay_key)
        self._replay.add(replay_row)
        state_key = self._tabular_learner.update(replay_row)
        if state_key is not None:
            self._model_store.set_latest_tabular_state(state_key)
        self._imported_rows += 1
        policy_name = self._model_store.policy_for_version(int(replay_row["model_version_executed"]))
        policy_bucket = self._policy_buckets.setdefault(policy_name, PolicyBucketStats())
        policy_bucket.rows += 1
        if bool(replay_row["done"]):
            policy_bucket.done += 1
        reward = float(replay_row["reward_accum"])
        if reward > 0:
            self._reward_positive += 1
            policy_bucket.reward_positive += 1
        elif reward < 0:
            self._reward_negative += 1
            policy_bucket.reward_negative += 1
        else:
            self._reward_zero += 1
            policy_bucket.reward_zero += 1

    def _print_stats(self) -> None:
        inf = self._inference_stats.snapshot()
        learner_ready = len(self._replay) >= self._learner_warmup_rows and self._replay.can_sample(self._learner_batch_size)
        batch_mean_reward = 0.0
        model_status = self._model_store.status()
        if learner_ready:
            batch = self._replay.sample(self._learner_batch_size)
            if batch:
                batch_mean_reward = sum(float(item["reward_accum"]) for item in batch) / len(batch)
        policy_bucket = self._policy_buckets.get(self._latest_model_policy_executed, PolicyBucketStats())
        tabular = self._tabular_learner.snapshot(self._tabular_min_action_count)
        top_raw = "none"
        if tabular["top_state"]:
            top_raw = f"{tabular['top_action']}:{float(tabular['top_score']):.2f}/{int(tabular['top_count'])}"
        top_ready = "none"
        if tabular["ready_state"]:
            top_ready = f"{tabular['ready_action']}:{float(tabular['ready_score']):.2f}/{int(tabular['ready_count'])}"
        ready_actions = format_action_counts(tabular["ready_actions"] if isinstance(tabular["ready_actions"], dict) else {})
        ready_dx = format_dx_action_counts(tabular["ready_dx_actions"] if isinstance(tabular["ready_dx_actions"], dict) else {})
        ready_opp_attack = format_opp_attack_action_counts(
            tabular["ready_opp_attack_actions"] if isinstance(tabular["ready_opp_attack_actions"], dict) else {}
        )
        ready_threat_dx = format_threat_dx_action_counts(
            tabular["ready_threat_dx_actions"] if isinstance(tabular["ready_threat_dx_actions"], dict) else {}
        )
        print(
            "LEARNER "
            f"rows={self._rows} done={self._done} run={self._latest_run_id} ep={self._latest_episode} "
            f"replay={len(self._replay)}/{self._imported_rows} skipped={self._skipped_unexecuted} "
            f"rew=+{self._reward_positive}/-{self._reward_negative}/0{self._reward_zero} "
            f"policy={self._latest_model_policy_executed} "
            f"policy_rows={policy_bucket.rows} policy_done={policy_bucket.done} "
            f"policy_rew=+{policy_bucket.reward_positive}/-{policy_bucket.reward_negative}/0{policy_bucket.reward_zero} "
            f"ready={'yes' if learner_ready else 'no'} warmup={self._learner_warmup_rows} "
            f"batch={self._learner_batch_size} batch_mean={batch_mean_reward:.3f} "
            f"tab_states={tabular['states']} tab_updates={tabular['updates']} "
            f"tab_ignored={tabular['ignored_actions']} tab_delayed={tabular['delayed_reward_updates']} "
            f"tab_reward=hp-delta:{float(tabular['training_reward_total']):.1f} "
            f"eps={float(tabular['epsilon']):.2f} min_n={self._tabular_min_action_count} "
            f"top_raw={top_raw} top_ready={top_ready} "
            f"ready_actions={ready_actions} ready_dx={ready_dx} "
            f"ready_opp_attack={ready_opp_attack} ready_threat_dx={ready_threat_dx} "
            f"model_exec={self._latest_model_version_executed} "
            f"model_active={model_status.active.version} "
            f"model_pub={model_status.last_published_version} "
            f"model_load={model_status.last_loaded_version} "
            f"model_counts={model_status.publish_count}/{model_status.load_count} "
            f"obs={inf['obs_payload']}/{inf['obs_header_only']} "
            f"tab_state=obs:{inf['tabular_obs_state']}/latest:{inf['tabular_latest_state']} "
            f"inf={inf['count']}:{inf['p50_us']:.1f}/{inf['p95_us']:.1f}/{inf['max_us']:.1f}us",
            flush=True,
        )
        if self._learner_auto_publish and learner_ready:
            now_ns = time.monotonic_ns()
            if now_ns >= self._next_publish_ns:
                active = self._model_store.current()
                policy = self._learner_publish_policy or active.policy
                if policy == "dqn":
                    self._next_publish_ns = now_ns + self._learner_publish_interval_ns
                    return
                tabular_snapshot = self._tabular_learner.snapshot(self._tabular_min_action_count)
                tabular_updates = int(tabular_snapshot["updates"])
                if policy == "tabular" and tabular_updates <= self._last_published_tabular_updates:
                    self._next_publish_ns = now_ns + self._learner_publish_interval_ns
                    return
                q_table = tabular_snapshot["q_table"] if policy == "tabular" else None
                q_counts = tabular_snapshot["q_counts"] if policy == "tabular" else None
                self._model_store.publish(
                    policy,
                    source="learner",
                    metadata={
                        "rows_seen": self._rows,
                        "replay_rows": len(self._replay),
                        "imported_rows": self._imported_rows,
                        "batch_mean_reward": batch_mean_reward,
                        "reward_positive": self._reward_positive,
                        "reward_negative": self._reward_negative,
                        "reward_zero": self._reward_zero,
                        "tabular_states": tabular_snapshot["states"],
                        "tabular_updates": tabular_updates,
                        "tabular_ignored_actions": tabular_snapshot["ignored_actions"],
                        "tabular_delayed_reward_updates": tabular_snapshot["delayed_reward_updates"],
                        "tabular_reward_source": "hp-delta",
                        "tabular_training_reward_total": tabular_snapshot["training_reward_total"],
                        "tabular_min_action_count": self._tabular_min_action_count,
                        "tabular_actions": list(tabular_snapshot["actions"])
                        if isinstance(tabular_snapshot["actions"], tuple)
                        else list(TABULAR_DEFAULT_ACTIONS),
                    },
                    q_table=q_table if isinstance(q_table, dict) else None,
                    q_counts=q_counts if isinstance(q_counts, dict) else None,
                    actions=tabular_snapshot["actions"] if isinstance(tabular_snapshot["actions"], tuple) else TABULAR_DEFAULT_ACTIONS,
                    epsilon=float(tabular_snapshot["epsilon"]),
                    fallback_policy=str(tabular_snapshot["fallback_policy"]),
                    updated_rows=tabular_updates,
                    min_action_count=self._tabular_min_action_count,
                )
                if policy == "tabular":
                    self._last_published_tabular_updates = tabular_updates
                self._next_publish_ns = now_ns + self._learner_publish_interval_ns

    def run(self) -> None:
        next_stats_ns = time.monotonic_ns() + int(self._stats_interval_sec * 1_000_000_000)
        stream = None
        position = 0
        while True:
            if stream is None:
                try:
                    stream = open(self._path, "r", encoding="utf-8")
                    if not self._tail_from_start:
                        stream.seek(0, os.SEEK_END)
                    position = stream.tell()
                    print(f"LEARNER tailing {self._path}", flush=True)
                except OSError:
                    time.sleep(0.5)
                    continue

            line = stream.readline()
            if line:
                position = stream.tell()
                try:
                    self._consume_row(json.loads(line))
                except json.JSONDecodeError:
                    pass
                continue

            try:
                if os.path.getsize(self._path) < position:
                    stream.close()
                    stream = None
                    position = 0
                    continue
            except OSError:
                stream.close()
                stream = None
                position = 0
                continue

            now_ns = time.monotonic_ns()
            if now_ns >= next_stats_ns:
                self._print_stats()
                next_stats_ns = now_ns + int(self._stats_interval_sec * 1_000_000_000)
            time.sleep(0.01)


def packet_name(packet_type: int) -> str:
    return {
        TYPE_HELLO: "HELLO",
        TYPE_ACK: "ACK",
        TYPE_PING: "PING",
        TYPE_PONG: "PONG",
        TYPE_OBS: "OBS",
    }.get(packet_type, f"UNKNOWN({packet_type})")


def make_packet(packet_type: int, nonce: int, sequence: int, config_hash: int, send_time_us: int) -> bytes:
    return PACKET.pack(MAGIC, PACKET_VERSION, packet_type, nonce, sequence, config_hash, send_time_us)


def make_action_packet(
    nonce: int,
    run_id: int,
    episode_id: int,
    decision_id: int,
    target_frame: int,
    action: PolicyActionFrame,
    model_version: int,
) -> bytes:
    return ACTION_PACKET.pack(
        MAGIC,
        PROTOCOL_VERSION,
        action.policy_action_id & 0xFFFF,
        nonce,
        run_id,
        episode_id,
        decision_id,
        target_frame,
        action.action_wire & 0xFFFF,
        action.policy_sub_action_id & 0xFFFF,
        action.policy_action_step & 0xFFFF,
        0,
        model_version,
    )


def maybe_send_action(
    sock: socket.socket,
    addr: tuple[str, int],
    action_port: int | None,
    action_mode: str,
    nonce: int,
    sequence: int,
    model_version: int,
    verbose: bool,
) -> None:
    if action_port is None or action_mode == "off":
        return

    send_nonce = nonce
    if action_mode == "stale":
        send_nonce = (nonce - 1) & 0xFFFFFFFFFFFFFFFF

    payload = make_action_packet(
        send_nonce,
        0,
        1,
        sequence,
        sequence + 4,
        make_policy_action_frame("hp", BTN_HP),
        model_version,
    )
    target = (addr[0], action_port)
    sock.sendto(payload, target)
    if verbose:
        print(f"{target} ACTION mode={action_mode} nonce={send_nonce} decision={sequence} model={model_version}")


def fixed_action_wire(policy: str) -> int | None:
    if policy == "hp":
        return BTN_HP
    if policy in AIR_NORMAL_ACTION_WIRES:
        return AIR_NORMAL_ACTION_WIRES[policy]
    return TABULAR_ACTION_WIRES.get(policy)


def policy_action_meta(policy: str) -> tuple[int, int]:
    return POLICY_ACTION_META_BY_NAME.get(policy, POLICY_ACTION_META_BY_NAME["neutral"])


def make_policy_action_frame(policy: str, action_wire: int, step: int = 0) -> PolicyActionFrame:
    action_id, sub_action_id = policy_action_meta(policy)
    return PolicyActionFrame(
        action_wire=action_wire & 0xFFFF,
        policy_action_id=action_id,
        policy_sub_action_id=sub_action_id,
        policy_action_step=step,
    )


def policy_action_frame_name(frame: PolicyActionFrame) -> str:
    if frame.policy_action_id == RL_POLICY_ACTION_NEUTRAL:
        return "neutral"
    return TABULAR_ACTION_NAMES_BY_POLICY_META.get(
        (frame.policy_action_id, frame.policy_sub_action_id),
        f"{frame.policy_action_id}/{frame.policy_sub_action_id}",
    )


def scripted_sequence(policy: str) -> tuple[int, ...] | None:
    fireball_scripts = {
        action: (
            RL_MOVE_NEUTRAL,
            RL_MOVE_NEUTRAL,
            RL_MOVE_DOWN_BACK,
            RL_MOVE_DOWN,
            RL_MOVE_DOWN_FORWARD,
            RL_MOVE_FORWARD | button_wire,
            RL_MOVE_NEUTRAL,
            RL_MOVE_NEUTRAL,
        )
        for action, button_wire, _ in FIREBALL_ACTIONS
    }
    fireball_scripts["fireball"] = fireball_scripts["fireball-lp"]
    fireball_scripts["ryu-fireball"] = fireball_scripts["fireball-lp"]

    scripts = {
        "guard": (RL_MOVE_BACK,) * GUARD_MACRO_DECISION_STEPS,
        "guard-stand": (RL_MOVE_BACK,) * GUARD_MACRO_DECISION_STEPS,
        "guard-crouch": (RL_MOVE_DOWN_BACK,) * GUARD_MACRO_DECISION_STEPS,
        **fireball_scripts,
        "throw": (
            RL_MOVE_FORWARD | BTN_LP | BTN_LK,
            RL_MOVE_NEUTRAL,
            RL_MOVE_NEUTRAL,
            RL_MOVE_NEUTRAL,
        ),
        "tatsu": (
            RL_MOVE_DOWN,
            RL_MOVE_DOWN_BACK,
            RL_MOVE_BACK,
            RL_MOVE_BACK | BTN_LK,
            RL_MOVE_NEUTRAL,
            RL_MOVE_NEUTRAL,
        ),
        "shoryuken": (
            RL_MOVE_FORWARD,
            RL_MOVE_DOWN,
            RL_MOVE_DOWN_FORWARD,
            RL_MOVE_DOWN_FORWARD | BTN_HP,
            RL_MOVE_NEUTRAL,
            RL_MOVE_NEUTRAL,
        ),
        **{
            action: (
                RL_MOVE_DOWN,
                RL_MOVE_DOWN_BACK,
                RL_MOVE_BACK,
                RL_MOVE_BACK | wire,
                RL_MOVE_NEUTRAL,
                RL_MOVE_NEUTRAL,
            )
            for action, wire, _ in TATSU_ACTIONS
        },
        **{
            action: (
                RL_MOVE_FORWARD,
                RL_MOVE_DOWN,
                RL_MOVE_DOWN_FORWARD,
                RL_MOVE_DOWN_FORWARD | wire,
                RL_MOVE_NEUTRAL,
                RL_MOVE_NEUTRAL,
            )
            for action, wire, _ in SHORYUKEN_ACTIONS
        },
    }
    return scripts.get(policy)


def scripted_action_frame(
    policy: str,
    policy_states: dict[tuple[int, int, int, str], dict[str, int]],
    nonce: int,
    run_id: int,
    episode_id: int,
    repeat_delay_ms: int,
) -> PolicyActionFrame:
    key = (nonce, run_id, episode_id, policy)
    state = policy_states.setdefault(key, {"index": 0, "delay_until_ns": 0})
    now_ns = time.monotonic_ns()
    if state["delay_until_ns"] > now_ns:
        return make_policy_action_frame("neutral", RL_MOVE_NEUTRAL)
    if state["delay_until_ns"] != 0:
        state["delay_until_ns"] = 0
        state["index"] = 0

    fixed = fixed_action_wire(policy)
    if fixed is not None:
        if repeat_delay_ms > 0:
            state["delay_until_ns"] = now_ns + (repeat_delay_ms * 1_000_000)
        return make_policy_action_frame(policy, fixed)

    sequence = scripted_sequence(policy)
    if sequence is None:
        return make_policy_action_frame("forward", RL_MOVE_FORWARD)

    index = state["index"]
    step = index
    action_wire = sequence[index]
    index += 1
    if index >= len(sequence):
        index = 0
        if repeat_delay_ms > 0:
            state["delay_until_ns"] = now_ns + (repeat_delay_ms * 1_000_000)
    state["index"] = index
    return make_policy_action_frame(policy, action_wire, step=step)


def scripted_action_wire(
    policy: str,
    policy_states: dict[tuple[int, int, int, str], dict[str, int]],
    nonce: int,
    run_id: int,
    episode_id: int,
    repeat_delay_ms: int,
) -> int:
    return scripted_action_frame(policy, policy_states, nonce, run_id, episode_id, repeat_delay_ms).action_wire


def tabular_actor_action_name(actor: ActorModel, state_key: str | None) -> str | None:
    if actor.policy != "tabular" or not state_key:
        return None
    if random.random() < actor.epsilon:
        return random.choice(actor.actions)
    scores = actor.q_table.get(state_key)
    if not scores:
        return None
    counts = actor.q_counts.get(state_key, {})
    eligible_actions = [
        action
        for action in actor.actions
        if int(counts.get(action, 0)) >= actor.min_action_count and float(scores.get(action, 0.0)) > 0.0
    ]
    if not eligible_actions:
        return None
    return max(eligible_actions, key=lambda action: (float(scores.get(action, 0.0)), action))


def dqn_actor_action_name(
    actor: ActorModel,
    obs_row: dict[str, object] | None,
    support_prior_config: DQNSupportPriorConfig = DQNSupportPriorConfig(),
    valid_action_mask_config: DQNValidActionMaskConfig = DQNValidActionMaskConfig(),
    projectile_timing_prior_config: DQNProjectileTimingPriorConfig = DQNProjectileTimingPriorConfig(),
    shoryuken_context_prior_config: DQNShoryukenContextPriorConfig = DQNShoryukenContextPriorConfig(),
    ground_normal_context_prior_config: DQNGroundNormalContextPriorConfig = DQNGroundNormalContextPriorConfig(),
    fireball_zoning_prior_config: DQNFireballZoningPriorConfig = DQNFireballZoningPriorConfig(),
    threat_defense_prior_config: DQNThreatDefensePriorConfig = DQNThreatDefensePriorConfig(),
) -> str | None:
    if actor.policy != "dqn" or not obs_row or not actor.dqn_model:
        return None
    if random.random() < actor.epsilon:
        eligible_actions = [
            action
            for action in dqn_valid_actions_for_row(obs_row, actor.actions, valid_action_mask_config)
            if not dqn_action_hard_blocked_by_priors(
                action,
                obs_row,
                shoryuken_context_prior_config,
            )
        ]
        if not eligible_actions:
            return None
        return random.choice(eligible_actions)
    ranked_actions = dqn_ranked_action_scores(
        actor.actions,
        actor.dqn_model,
        actor.metadata,
        obs_row,
        support_prior_config,
        valid_action_mask_config,
        projectile_timing_prior_config,
        shoryuken_context_prior_config,
        ground_normal_context_prior_config,
        fireball_zoning_prior_config,
        threat_defense_prior_config,
    )
    if not ranked_actions:
        return None
    return ranked_actions[0][0]


def bc_projectile_danger_active(row: dict[str, object], config: BCInferenceConfig) -> bool:
    if row_int_field(row, "obs_self_airborne") != 0 or row_int_field(row, "obs_self_jump_phase") >= 2:
        return False
    if row_int_field(row, "obs_projectile_active") == 0:
        return False
    if row_int_field(row, "obs_projectile_owner") != 2:
        return False
    rel_x = row_int_field(row, "obs_projectile_rel_x")
    rel_y = row_int_field(row, "obs_projectile_rel_y")
    vel_x = row_int_field(row, "obs_projectile_vel_x")
    time_to_self = row_int_field(row, "obs_projectile_time_to_self")
    return (
        1 <= time_to_self <= config.danger_max_time_to_self
        and 0 < rel_x <= config.danger_max_abs_dx
        and abs(rel_y) <= config.danger_max_abs_y
        and vel_x < 0
    )


def bc_close_attack_danger_active(row: dict[str, object], config: BCInferenceConfig) -> bool:
    return (
        row_int_field(row, "obs_self_airborne") == 0
        and row_int_field(row, "obs_self_jump_phase") == 0
        and row_int_field(row, "obs_opp_routine_attack_state") != 0
        and row_int_field(row, "obs_opp_airborne") == 0
        and row_int_field(row, "obs_opp_jump_phase") == 0
        and row_int_field(row, "obs_abs_dx") <= config.danger_max_abs_dx
    )


def bc_deterministic_danger_action_name(
    ranked_actions: list[tuple[str, float]],
    row: dict[str, object],
    config: BCInferenceConfig,
) -> str | None:
    if not config.deterministic_danger:
        return None
    if not bc_projectile_danger_active(row, config) and not bc_close_attack_danger_active(row, config):
        return None
    ranked_by_score = {action: score for action, score in ranked_actions}
    candidates = ("guard-crouch", "guard-stand", "back")
    eligible = [action for action in candidates if action in ranked_by_score]
    if not eligible:
        return None
    return max(eligible, key=lambda action: (ranked_by_score[action], action))


def bc_sample_ranked_action_name(
    ranked_actions: list[tuple[str, float]],
    config: BCInferenceConfig,
) -> str | None:
    if not ranked_actions:
        return None
    top_k = max(0, int(config.top_k))
    candidates = ranked_actions if top_k == 0 else ranked_actions[:top_k]
    if len(candidates) <= 1 or config.temperature <= 0.0:
        return candidates[0][0]
    max_score = max(score for _, score in candidates)
    inv_temp = 1.0 / max(1e-6, float(config.temperature))
    weights = [math.exp(max(-80.0, min(80.0, (score - max_score) * inv_temp))) for _, score in candidates]
    if not weights or sum(weights) <= 0.0:
        return candidates[0][0]
    return random.choices([action for action, _ in candidates], weights=weights, k=1)[0]


def bc_actor_action_name(
    actor: ActorModel,
    obs_row: dict[str, object] | None,
    config: BCInferenceConfig,
    valid_action_mask_config: DQNValidActionMaskConfig = DQNValidActionMaskConfig(),
) -> str | None:
    if actor.policy != "bc" or not obs_row or not actor.dqn_model:
        return None
    if random.random() < actor.epsilon:
        eligible_actions = dqn_valid_actions_for_row(obs_row, actor.actions, valid_action_mask_config)
        if not eligible_actions:
            return None
        return random.choice(eligible_actions)
    ranked_actions = dqn_ranked_action_scores(
        actor.actions,
        actor.dqn_model,
        actor.metadata,
        obs_row,
        valid_action_mask_config=valid_action_mask_config,
    )
    danger_action = bc_deterministic_danger_action_name(ranked_actions, obs_row, config)
    if danger_action is not None:
        return danger_action
    return bc_sample_ranked_action_name(ranked_actions, config)


def actor_critic_ranked_action_scores(
    actions: tuple[str, ...],
    actor_critic_model: dict[str, object],
    row: dict[str, object],
    valid_action_mask_config: DQNValidActionMaskConfig = DQNValidActionMaskConfig(),
    spacing_prior_config: ActorCriticSpacingPriorConfig = ActorCriticSpacingPriorConfig(),
) -> list[tuple[str, float]]:
    logits, _value = actor_critic_predict_logits_value(actor_critic_model, row)
    if not logits:
        return []
    scored_actions: list[tuple[str, float]] = []
    for index, action in enumerate(actions):
        if index >= len(logits) or action not in TABULAR_ACTION_NAMES:
            continue
        if not dqn_valid_action_for_row(action, row, valid_action_mask_config):
            continue
        score = float(logits[index])
        score += actor_critic_spacing_prior_adjustment(action, row, spacing_prior_config)
        scored_actions.append((action, score))
    return sorted(scored_actions, key=lambda item: (item[1], item[0]), reverse=True)


def actor_critic_sample_ranked_action_name(
    ranked_actions: list[tuple[str, float]],
    config: ActorCriticInferenceConfig,
) -> str | None:
    if not ranked_actions:
        return None
    top_k = max(0, int(config.top_k))
    candidates = ranked_actions if top_k == 0 else ranked_actions[:top_k]
    if not candidates:
        return None
    if config.temperature <= 0.0 or len(candidates) == 1:
        return candidates[0][0]
    max_score = max(score for _, score in candidates)
    inv_temp = 1.0 / max(1e-6, float(config.temperature))
    weights = [math.exp(max(-80.0, min(80.0, (score - max_score) * inv_temp))) for _, score in candidates]
    if 0.0 < config.top_p < 1.0:
        total = sum(weights)
        if total > 0.0:
            filtered_candidates: list[tuple[str, float]] = []
            filtered_weights: list[float] = []
            cumulative = 0.0
            for candidate, weight in zip(candidates, weights):
                filtered_candidates.append(candidate)
                filtered_weights.append(weight)
                cumulative += weight / total
                if cumulative >= config.top_p:
                    break
            candidates = filtered_candidates
            weights = filtered_weights
    if not weights or sum(weights) <= 0.0:
        return candidates[0][0]
    return random.choices([action for action, _ in candidates], weights=weights, k=1)[0]


def actor_critic_actor_action_name(
    actor: ActorModel,
    obs_row: dict[str, object] | None,
    config: ActorCriticInferenceConfig,
    valid_action_mask_config: DQNValidActionMaskConfig = DQNValidActionMaskConfig(),
    spacing_prior_config: ActorCriticSpacingPriorConfig = ActorCriticSpacingPriorConfig(),
) -> str | None:
    if actor.policy != "actor-critic" or not obs_row or not actor.actor_critic_model:
        return None
    if random.random() < actor.epsilon:
        eligible_actions = dqn_valid_actions_for_row(obs_row, actor.actions, valid_action_mask_config)
        if not eligible_actions:
            return None
        return random.choice(eligible_actions)
    ranked_actions = actor_critic_ranked_action_scores(
        actor.actions,
        actor.actor_critic_model,
        obs_row,
        valid_action_mask_config,
        spacing_prior_config,
    )
    return actor_critic_sample_ranked_action_name(ranked_actions, config)


def active_macro_action_frame(
    macro_states: dict[tuple[int, int, int], dict[str, int | str]],
    nonce: int,
    run_id: int,
    episode_id: int,
) -> PolicyActionFrame | None:
    key = (nonce, run_id, episode_id)
    state = macro_states.get(key)
    if not state:
        return None
    action = str(state.get("action", ""))
    sequence = scripted_sequence(action)
    index = int(state.get("index", 0))
    if sequence is None or index < 0 or index >= len(sequence):
        macro_states.pop(key, None)
        return None
    step = index
    action_wire = sequence[index]
    index += 1
    if index >= len(sequence):
        macro_states.pop(key, None)
    else:
        state["index"] = index
    return make_policy_action_frame(action, action_wire, step=step)


def active_macro_action_name(
    macro_states: dict[tuple[int, int, int], dict[str, int | str]],
    nonce: int,
    run_id: int,
    episode_id: int,
) -> str | None:
    state = macro_states.get((nonce, run_id, episode_id))
    if not state:
        return None
    action = str(state.get("action", ""))
    return action if action else None


def active_macro_action_wire(
    macro_states: dict[tuple[int, int, int], dict[str, int | str]],
    nonce: int,
    run_id: int,
    episode_id: int,
) -> int | None:
    frame = active_macro_action_frame(macro_states, nonce, run_id, episode_id)
    return None if frame is None else frame.action_wire


def start_macro_action_frame(
    macro_states: dict[tuple[int, int, int], dict[str, int | str]],
    nonce: int,
    run_id: int,
    episode_id: int,
    action: str,
) -> PolicyActionFrame | None:
    sequence = scripted_sequence(action)
    if sequence is None:
        return None
    macro_states[(nonce, run_id, episode_id)] = {"action": action, "index": 1}
    return make_policy_action_frame(action, sequence[0], step=0)


def start_macro_action_wire(
    macro_states: dict[tuple[int, int, int], dict[str, int | str]],
    nonce: int,
    run_id: int,
    episode_id: int,
    action: str,
) -> int | None:
    frame = start_macro_action_frame(macro_states, nonce, run_id, episode_id, action)
    return None if frame is None else frame.action_wire


def policy_action_frame(
    actor: ActorModel,
    model_store: ActorModelStore,
    policy_states: dict[tuple[int, int, int, str], dict[str, int]],
    macro_states: dict[tuple[int, int, int], dict[str, int | str]],
    nonce: int,
    run_id: int,
    episode_id: int,
    repeat_delay_ms: int,
    tabular_state_key_override: str | None = None,
    obs_row_override: dict[str, object] | None = None,
    dqn_support_prior_config: DQNSupportPriorConfig = DQNSupportPriorConfig(),
    dqn_valid_action_mask_config: DQNValidActionMaskConfig = DQNValidActionMaskConfig(),
    dqn_projectile_timing_prior_config: DQNProjectileTimingPriorConfig = DQNProjectileTimingPriorConfig(),
    dqn_shoryuken_context_prior_config: DQNShoryukenContextPriorConfig = DQNShoryukenContextPriorConfig(),
    dqn_ground_normal_context_prior_config: DQNGroundNormalContextPriorConfig = DQNGroundNormalContextPriorConfig(),
    dqn_fireball_zoning_prior_config: DQNFireballZoningPriorConfig = DQNFireballZoningPriorConfig(),
    dqn_threat_defense_prior_config: DQNThreatDefensePriorConfig = DQNThreatDefensePriorConfig(),
    bc_inference_config: BCInferenceConfig = BCInferenceConfig(),
    actor_critic_inference_config: ActorCriticInferenceConfig = ActorCriticInferenceConfig(),
    actor_critic_spacing_prior_config: ActorCriticSpacingPriorConfig = ActorCriticSpacingPriorConfig(),
    tactical_policy_config: TacticalPolicyConfig = TacticalPolicyConfig(),
) -> PolicyActionFrame:
    if actor.policy in MODEL_POLICY_CHOICES:
        macro_action = active_macro_action_name(macro_states, nonce, run_id, episode_id)
        if (
            actor.policy == "dqn"
            and macro_action is not None
            and obs_row_override is not None
            and dqn_action_hard_blocked_by_priors(
                macro_action,
                obs_row_override,
                dqn_shoryuken_context_prior_config,
            )
        ):
            macro_states.pop((nonce, run_id, episode_id), None)
        if (
            actor.policy == "tactical"
            and macro_action is not None
            and obs_row_override is not None
            and tactical_macro_should_cancel(macro_action, obs_row_override, tactical_policy_config)
        ):
            macro_states.pop((nonce, run_id, episode_id), None)
        macro_frame = active_macro_action_frame(macro_states, nonce, run_id, episode_id)
        if macro_frame is not None:
            return macro_frame
    action_name = None
    if actor.policy == "tabular":
        tabular_state = tabular_state_key_override if tabular_state_key_override else model_store.latest_tabular_state()
        action_name = tabular_actor_action_name(actor, tabular_state)
    elif actor.policy == "dqn":
        action_name = dqn_actor_action_name(
            actor,
            obs_row_override,
            dqn_support_prior_config,
            dqn_valid_action_mask_config,
            dqn_projectile_timing_prior_config,
            dqn_shoryuken_context_prior_config,
            dqn_ground_normal_context_prior_config,
            dqn_fireball_zoning_prior_config,
            dqn_threat_defense_prior_config,
        )
    elif actor.policy == "bc":
        action_name = bc_actor_action_name(
            actor,
            obs_row_override,
            bc_inference_config,
            dqn_valid_action_mask_config,
        )
    elif actor.policy == "actor-critic":
        action_name = actor_critic_actor_action_name(
            actor,
            obs_row_override,
            actor_critic_inference_config,
            dqn_valid_action_mask_config,
            actor_critic_spacing_prior_config,
        )
    elif actor.policy == "tactical":
        action_name = tactical_actor_action_name(
            actor,
            obs_row_override,
            tactical_policy_config,
        )
    if action_name is not None:
        fixed = fixed_action_wire(action_name)
        if fixed is not None:
            return make_policy_action_frame(action_name, fixed)
        macro_frame = start_macro_action_frame(macro_states, nonce, run_id, episode_id, action_name)
        if macro_frame is not None:
            return macro_frame
    fallback_policy = actor.fallback_policy if actor.policy in MODEL_POLICY_CHOICES else actor.policy
    return scripted_action_frame(fallback_policy, policy_states, nonce, run_id, episode_id, repeat_delay_ms)


def policy_action_wire(
    actor: ActorModel,
    model_store: ActorModelStore,
    policy_states: dict[tuple[int, int, int, str], dict[str, int]],
    macro_states: dict[tuple[int, int, int], dict[str, int | str]],
    nonce: int,
    run_id: int,
    episode_id: int,
    repeat_delay_ms: int,
    tabular_state_key_override: str | None = None,
    obs_row_override: dict[str, object] | None = None,
    dqn_support_prior_config: DQNSupportPriorConfig = DQNSupportPriorConfig(),
    dqn_valid_action_mask_config: DQNValidActionMaskConfig = DQNValidActionMaskConfig(),
    dqn_projectile_timing_prior_config: DQNProjectileTimingPriorConfig = DQNProjectileTimingPriorConfig(),
    dqn_shoryuken_context_prior_config: DQNShoryukenContextPriorConfig = DQNShoryukenContextPriorConfig(),
    dqn_ground_normal_context_prior_config: DQNGroundNormalContextPriorConfig = DQNGroundNormalContextPriorConfig(),
    dqn_fireball_zoning_prior_config: DQNFireballZoningPriorConfig = DQNFireballZoningPriorConfig(),
    dqn_threat_defense_prior_config: DQNThreatDefensePriorConfig = DQNThreatDefensePriorConfig(),
    bc_inference_config: BCInferenceConfig = BCInferenceConfig(),
    actor_critic_inference_config: ActorCriticInferenceConfig = ActorCriticInferenceConfig(),
    actor_critic_spacing_prior_config: ActorCriticSpacingPriorConfig = ActorCriticSpacingPriorConfig(),
    tactical_policy_config: TacticalPolicyConfig = TacticalPolicyConfig(),
) -> int:
    return policy_action_frame(
        actor,
        model_store,
        policy_states,
        macro_states,
        nonce,
        run_id,
        episode_id,
        repeat_delay_ms,
        tabular_state_key_override,
        obs_row_override,
        dqn_support_prior_config,
        dqn_valid_action_mask_config,
        dqn_projectile_timing_prior_config,
        dqn_shoryuken_context_prior_config,
        dqn_ground_normal_context_prior_config,
        dqn_fireball_zoning_prior_config,
        dqn_threat_defense_prior_config,
        bc_inference_config,
        actor_critic_inference_config,
        actor_critic_spacing_prior_config,
        tactical_policy_config,
    ).action_wire


def format_dqn_verbose_diagnostics(
    actor: ActorModel,
    obs_row: dict[str, object] | None,
    target_action: PolicyActionFrame,
    valid_action_mask_config: DQNValidActionMaskConfig,
    valid_action_mask_source: str,
    actor_critic_inference_config: ActorCriticInferenceConfig,
    actor_critic_spacing_prior_config: ActorCriticSpacingPriorConfig,
    projectile_timing_prior_config: DQNProjectileTimingPriorConfig,
    shoryuken_context_prior_config: DQNShoryukenContextPriorConfig,
    ground_normal_context_prior_config: DQNGroundNormalContextPriorConfig,
    fireball_zoning_prior_config: DQNFireballZoningPriorConfig,
    threat_defense_prior_config: DQNThreatDefensePriorConfig,
    tactical_policy_config: TacticalPolicyConfig,
) -> str:
    if actor.policy == "tactical":
        action_name = policy_action_frame_name(target_action)
        if obs_row is None:
            return f" tactical_action={action_name} tactical_obs=n/a tactical_config={tactical_policy_config.label()}"
        prediction = tactical_intent_prediction(actor.tactical_intent_model, obs_row) if actor.tactical_intent_model else None
        if prediction is None:
            decision = tactical_policy_decision(obs_row, tactical_policy_config)
        else:
            decision = tactical_policy_decision_with_intent(
                obs_row,
                tactical_policy_config,
                prediction[0],
                prediction[1],
                "learned",
            )
        return (
            f" tactical_action={action_name}"
            f" tactical_config={tactical_policy_config.label()}"
            f" tactical_intent={decision.recommended_intent}"
            f" tactical_source={decision.intent_source}"
            f" tactical_reason={decision.intent_reason}"
            f" tactical_conf={decision.label_confidence}"
            f" tactical_spacing={decision.spacing_bucket}"
            f" tactical_corner={decision.corner_context}"
            f" tactical_self={decision.self_phase}"
            f" tactical_opp={decision.opponent_phase}"
            f" tactical_threat={decision.threat_type}"
            f" tactical_opportunity={decision.opportunity_type}"
            f" tactical_decoded={decision.action_name}"
            f" tactical_phase={dqn_self_mask_phase(obs_row)}"
            f" self_r1={row_int_field(obs_row, 'obs_self_routine_1')}"
            f" self_r2={row_int_field(obs_row, 'obs_self_routine_2')}"
            f" self_atk={row_int_field(obs_row, 'obs_self_routine_attack_state')}"
            f" self_contact={row_int_field(obs_row, 'obs_self_contact_reaction_state')}"
            f" opp_r1={row_int_field(obs_row, 'obs_opp_routine_1')}"
            f" opp_r2={row_int_field(obs_row, 'obs_opp_routine_2')}"
            f" opp_atk={row_int_field(obs_row, 'obs_opp_routine_attack_state')}"
            f" proj={row_int_field(obs_row, 'obs_projectile_active')}/{row_int_field(obs_row, 'obs_projectile_owner')}"
            f" proj_t={row_int_field(obs_row, 'obs_projectile_time_to_self')}"
        )
    if actor.policy not in ("dqn", "bc", "actor-critic"):
        return ""
    action_name = policy_action_frame_name(target_action)
    if actor.policy == "actor-critic":
        if obs_row is None:
            return (
                f" ac_action={action_name}"
                f" ac_mask={valid_action_mask_config.label()}"
            f" ac_mask_source={valid_action_mask_source}"
            f" ac_infer={actor_critic_inference_config.label()}"
            f" ac_spacing={actor_critic_spacing_prior_config.label()}"
            " ac_valid=n/a"
            " ac_value=n/a"
        )
        valid_actions = dqn_valid_actions_for_row(obs_row, actor.actions, valid_action_mask_config)
        ranked_actions = actor_critic_ranked_action_scores(
            actor.actions,
            actor.actor_critic_model,
            obs_row,
            valid_action_mask_config,
            actor_critic_spacing_prior_config,
        )
        _logits, value = actor_critic_predict_logits_value(actor.actor_critic_model, obs_row)
        top = ",".join(f"{name}:{score:.3f}" for name, score in ranked_actions[:5]) if ranked_actions else "none"
        value_label = "n/a" if value is None else f"{value:.3f}"
        spacing_adjustment = actor_critic_spacing_prior_adjustment(
            action_name or "",
            obs_row,
            actor_critic_spacing_prior_config,
        )
        return (
            f" ac_action={action_name}"
            f" ac_mask={valid_action_mask_config.label()}"
            f" ac_mask_source={valid_action_mask_source}"
            f" ac_infer={actor_critic_inference_config.label()}"
            f" ac_spacing={actor_critic_spacing_prior_config.label()}"
            f" ac_spacing_adj={spacing_adjustment:.3f}"
            f" ac_valid={len(valid_actions)}/{len(actor.actions)}"
            f" ac_phase={dqn_self_mask_phase(obs_row)}"
            f" ac_value={value_label}"
            f" ac_top={top}"
            f" self_r1={row_int_field(obs_row, 'obs_self_routine_1')}"
            f" self_r2={row_int_field(obs_row, 'obs_self_routine_2')}"
            f" self_atk={row_int_field(obs_row, 'obs_self_routine_attack_state')}"
            f" self_contact={row_int_field(obs_row, 'obs_self_contact_reaction_state')}"
            f" proj={row_int_field(obs_row, 'obs_projectile_active')}/{row_int_field(obs_row, 'obs_projectile_owner')}"
            f" proj_t={row_int_field(obs_row, 'obs_projectile_time_to_self')}"
        )
    if actor.policy == "bc":
        if obs_row is None:
            return (
                f" bc_action={action_name}"
                f" bc_mask={valid_action_mask_config.label()}"
                f" bc_mask_source={valid_action_mask_source}"
                " bc_valid=n/a"
            )
        valid_actions = dqn_valid_actions_for_row(obs_row, actor.actions, valid_action_mask_config)
        return (
            f" bc_action={action_name}"
            f" bc_mask={valid_action_mask_config.label()}"
            f" bc_mask_source={valid_action_mask_source}"
            f" bc_valid={len(valid_actions)}/{len(actor.actions)}"
            f" bc_phase={dqn_self_mask_phase(obs_row)}"
            f" self_r1={row_int_field(obs_row, 'obs_self_routine_1')}"
            f" self_r2={row_int_field(obs_row, 'obs_self_routine_2')}"
            f" self_atk={row_int_field(obs_row, 'obs_self_routine_attack_state')}"
            f" self_contact={row_int_field(obs_row, 'obs_self_contact_reaction_state')}"
            f" proj={row_int_field(obs_row, 'obs_projectile_active')}/{row_int_field(obs_row, 'obs_projectile_owner')}"
            f" proj_t={row_int_field(obs_row, 'obs_projectile_time_to_self')}"
        )
    if obs_row is None:
        return (
            f" dqn_action={action_name}"
            f" dqn_mask={valid_action_mask_config.label()}"
            f" dqn_mask_source={valid_action_mask_source}"
            f" dqn_proj_prior={projectile_timing_prior_config.label()}"
            f" dqn_dp_prior={shoryuken_context_prior_config.label()}"
            f" dqn_norm_prior={ground_normal_context_prior_config.label()}"
            f" dqn_fb_prior={fireball_zoning_prior_config.label()}"
            f" dqn_def_prior={threat_defense_prior_config.label()}"
            " dqn_valid=n/a"
            " self_r1=n/a self_r2=n/a self_atk=n/a self_contact=n/a"
            " self_air=n/a self_jump_phase=n/a ground_ok=n/a jump_ok=n/a air_ok=n/a"
            " proj=n/a"
        )
    valid_actions = dqn_valid_actions_for_row(obs_row, actor.actions, valid_action_mask_config)
    projectile_timing_prior_penalty = dqn_projectile_timing_prior_jump_penalty(
        obs_row,
        projectile_timing_prior_config,
    )
    shoryuken_context_prior_penalty = dqn_shoryuken_context_prior_penalty(
        "shoryuken-lp",
        obs_row,
        shoryuken_context_prior_config,
    )
    ground_normal_context_prior_penalty = dqn_ground_normal_context_prior_penalty(
        "stand-lp",
        obs_row,
        ground_normal_context_prior_config,
    )
    fireball_zoning_prior_bonus = dqn_fireball_zoning_prior_bonus(
        "fireball-hp",
        obs_row,
        fireball_zoning_prior_config,
    )
    threat_defense_prior_bonus = dqn_threat_defense_prior_bonus(
        "guard-stand",
        obs_row,
        threat_defense_prior_config,
    )
    threat_defense_prior_penalty = dqn_threat_defense_prior_penalty(
        "forward",
        obs_row,
        threat_defense_prior_config,
    )
    return (
        f" dqn_action={action_name}"
        f" dqn_mask={valid_action_mask_config.label()}"
        f" dqn_mask_source={valid_action_mask_source}"
        f" dqn_proj_prior={projectile_timing_prior_config.label()}"
        f" dqn_proj_prior_jump_penalty={projectile_timing_prior_penalty:.3f}"
        f" dqn_dp_prior={shoryuken_context_prior_config.label()}"
        f" dqn_dp_prior_penalty={shoryuken_context_prior_penalty:.3f}"
        f" dqn_norm_prior={ground_normal_context_prior_config.label()}"
        f" dqn_norm_prior_penalty={ground_normal_context_prior_penalty:.3f}"
        f" dqn_fb_prior={fireball_zoning_prior_config.label()}"
        f" dqn_fb_prior_bonus={fireball_zoning_prior_bonus:.3f}"
        f" dqn_def_prior={threat_defense_prior_config.label()}"
        f" dqn_def_prior_bonus={threat_defense_prior_bonus:.3f}"
        f" dqn_def_prior_penalty={threat_defense_prior_penalty:.3f}"
        f" dqn_valid={len(valid_actions)}/{len(actor.actions)}"
        f" dqn_phase={dqn_self_mask_phase(obs_row)}"
        f" self_r1={row_int_field(obs_row, 'obs_self_routine_1')}"
        f" self_r2={row_int_field(obs_row, 'obs_self_routine_2')}"
        f" self_atk={row_int_field(obs_row, 'obs_self_routine_attack_state')}"
        f" self_contact={row_int_field(obs_row, 'obs_self_contact_reaction_state')}"
        f" self_air={row_int_field(obs_row, 'obs_self_airborne')}"
        f" self_jump_phase={row_int_field(obs_row, 'obs_self_jump_phase')}"
        f" ground_ok={1 if dqn_ground_action_start_allowed(obs_row) else 0}"
        f" jump_ok={1 if dqn_jump_start_allowed(obs_row) else 0}"
        f" air_ok={1 if dqn_air_attack_allowed(obs_row) else 0}"
        f" proj={row_int_field(obs_row, 'obs_projectile_active')}/{row_int_field(obs_row, 'obs_projectile_owner')}"
        f" proj_rx={row_int_field(obs_row, 'obs_projectile_rel_x')}"
        f" proj_ry={row_int_field(obs_row, 'obs_projectile_rel_y')}"
        f" proj_vx={row_int_field(obs_row, 'obs_projectile_vel_x')}"
        f" proj_t={row_int_field(obs_row, 'obs_projectile_time_to_self')}"
    )


def verbose_packet_log_decision(
    packet_type: int,
    ping_count: int,
    ping_interval: int,
) -> tuple[bool, int, str]:
    if packet_type != TYPE_PING:
        return True, ping_count, ""
    ping_count += 1
    if ping_interval <= 0:
        return False, ping_count, ""
    if ping_count == 1 or ping_count % ping_interval == 0:
        return True, ping_count, f" ping_log_count={ping_count}"
    return False, ping_count, ""


def serve(
    host: str,
    port: int,
    verbose: bool,
    verbose_ping_interval: int,
    action_port: int | None,
    action_mode: str,
    policy: str,
    obs_reply_mode: str,
    model_version: int,
    policy_repeat_delay_ms: int,
    transition_log: str | None,
    combat_event_log: str | None,
    learner_stats_interval_sec: float,
    learner_tail_from_start: bool,
    replay_capacity: int,
    learner_batch_size: int,
    learner_warmup_rows: int,
    transition_pull_interval_sec: float,
    transition_pull_host: str | None,
    transition_pull_user: str,
    transition_pull_password: str | None,
    transition_pull_remote_path: str | None,
    transition_pull_local_source: str | None,
    transition_server_port: int,
    learner_only: bool,
    model_dir: str | None,
    learner_auto_publish: bool,
    learner_publish_interval_sec: float,
    learner_publish_policy: str | None,
    tabular_alpha: float,
    tabular_epsilon: float,
    tabular_fallback_policy: str,
    tabular_actions: tuple[str, ...],
    tabular_min_action_count: int,
    dqn_support_prior_config: DQNSupportPriorConfig,
    dqn_valid_action_mask_config: DQNValidActionMaskConfig,
    dqn_valid_action_mask_auto: bool,
    bc_valid_action_mask_config: DQNValidActionMaskConfig,
    bc_valid_action_mask_auto: bool,
    bc_inference_config: BCInferenceConfig,
    actor_critic_valid_action_mask_config: DQNValidActionMaskConfig,
    actor_critic_valid_action_mask_auto: bool,
    actor_critic_inference_config: ActorCriticInferenceConfig,
    actor_critic_spacing_prior_config: ActorCriticSpacingPriorConfig,
    tactical_policy_config: TacticalPolicyConfig,
    dqn_projectile_timing_prior_config: DQNProjectileTimingPriorConfig,
    dqn_shoryuken_context_prior_config: DQNShoryukenContextPriorConfig,
    dqn_ground_normal_context_prior_config: DQNGroundNormalContextPriorConfig,
    dqn_fireball_zoning_prior_config: DQNFireballZoningPriorConfig,
    dqn_threat_defense_prior_config: DQNThreatDefensePriorConfig,
) -> None:
    inference_stats = InferenceStats()
    initial_actions = tabular_actions if policy == "tabular" else TABULAR_DEFAULT_ACTIONS
    initial_fallback_policy = tabular_fallback_policy if policy == "tabular" else "hp"
    model_store = ActorModelStore(
        model_dir,
        policy,
        model_version,
        initial_actions=initial_actions,
        initial_fallback_policy=initial_fallback_policy,
    )
    if transition_log and (transition_pull_remote_path or transition_pull_local_source):
        TransitionPuller(
            transition_log,
            transition_pull_interval_sec,
            transition_pull_host,
            transition_pull_user,
            transition_pull_password,
            transition_pull_remote_path,
            transition_pull_local_source,
        ).start()
    if transition_log and transition_server_port > 0:
        TransitionBatchServer(host, transition_server_port, transition_log, combat_event_log).start()
    if transition_log:
        LearnerLogTailer(
            transition_log,
            learner_stats_interval_sec,
            learner_tail_from_start,
            inference_stats,
            replay_capacity,
            learner_batch_size,
            learner_warmup_rows,
            model_store,
            learner_auto_publish,
            learner_publish_interval_sec,
            learner_publish_policy,
            tabular_alpha,
            tabular_epsilon,
            tabular_fallback_policy,
            tabular_actions,
            tabular_min_action_count,
        ).start()
    if learner_only:
        print("RL probe learner-only mode active", flush=True)
        while True:
            time.sleep(1.0)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((host, port))
    print(f"RL probe server listening on {host}:{port}")
    if dqn_support_prior_config.enabled:
        print(f"DQN support prior active {dqn_support_prior_config.label()}", flush=True)
    if dqn_projectile_timing_prior_config.enabled:
        print(f"DQN projectile timing prior active {dqn_projectile_timing_prior_config.label()}", flush=True)
    if dqn_shoryuken_context_prior_config.enabled:
        print(f"DQN shoryuken context prior active {dqn_shoryuken_context_prior_config.label()}", flush=True)
    if dqn_ground_normal_context_prior_config.enabled:
        print(f"DQN ground-normal context prior active {dqn_ground_normal_context_prior_config.label()}", flush=True)
    if dqn_fireball_zoning_prior_config.enabled:
        print(f"DQN fireball zoning prior active {dqn_fireball_zoning_prior_config.label()}", flush=True)
    if dqn_threat_defense_prior_config.enabled:
        print(f"DQN threat-defense prior active {dqn_threat_defense_prior_config.label()}", flush=True)
    if policy == "bc" or model_store.current().policy == "bc":
        print(f"BC inference active {bc_inference_config.label()}", flush=True)
    if policy == "actor-critic" or model_store.current().policy == "actor-critic":
        print(f"Actor-critic inference active {actor_critic_inference_config.label()}", flush=True)
    if actor_critic_spacing_prior_config.enabled:
        print(f"Actor-critic spacing prior active {actor_critic_spacing_prior_config.label()}", flush=True)
    if policy == "tactical" or model_store.current().policy == "tactical":
        print(f"Tactical policy active {tactical_policy_config.label()}", flush=True)
    active_model = model_store.current()
    if active_model.policy == "bc":
        initial_cli_mask_config = bc_valid_action_mask_config
        initial_mask_auto = bc_valid_action_mask_auto
    elif active_model.policy == "actor-critic":
        initial_cli_mask_config = actor_critic_valid_action_mask_config
        initial_mask_auto = actor_critic_valid_action_mask_auto
    else:
        initial_cli_mask_config = dqn_valid_action_mask_config
        initial_mask_auto = dqn_valid_action_mask_auto
    initial_mask_config, initial_mask_source = resolve_dqn_valid_action_mask_config(
        active_model,
        initial_cli_mask_config,
        initial_mask_auto,
    )
    last_model_mask_status: tuple[str, int, str, str] | None = None
    if active_model.policy in ("dqn", "bc", "actor-critic"):
        last_model_mask_status = (
            active_model.policy,
            active_model.version,
            initial_mask_config.mode,
            initial_mask_source,
        )
        print(
            f"{active_model.policy.upper()} valid-action mask {initial_mask_config.label()} "
            f"source={initial_mask_source} model_version={active_model.version}",
            flush=True,
        )
    hello_count: dict[int, int] = {}
    ping_verbose_count = 0
    policy_states: dict[tuple[int, int, int, str], dict[str, int]] = {}
    macro_states: dict[tuple[int, int, int], dict[str, int | str]] = {}

    while True:
        data, addr = sock.recvfrom(2048)
        if len(data) >= OBS_HEADER.size:
            inference_start_ns = time.perf_counter_ns()
            active_model = model_store.current()
            if active_model.policy == "bc":
                mask_cli_config = bc_valid_action_mask_config
                mask_auto = bc_valid_action_mask_auto
            elif active_model.policy == "actor-critic":
                mask_cli_config = actor_critic_valid_action_mask_config
                mask_auto = actor_critic_valid_action_mask_auto
            else:
                mask_cli_config = dqn_valid_action_mask_config
                mask_auto = dqn_valid_action_mask_auto
            effective_dqn_valid_action_mask_config, dqn_valid_action_mask_source = resolve_dqn_valid_action_mask_config(
                active_model,
                mask_cli_config,
                mask_auto,
            )
            if active_model.policy in ("dqn", "bc", "actor-critic"):
                model_mask_status = (
                    active_model.policy,
                    active_model.version,
                    effective_dqn_valid_action_mask_config.mode,
                    dqn_valid_action_mask_source,
                )
                if model_mask_status != last_model_mask_status:
                    last_model_mask_status = model_mask_status
                    print(
                        f"{active_model.policy.upper()} valid-action mask {effective_dqn_valid_action_mask_config.label()} "
                        f"source={dqn_valid_action_mask_source} model_version={active_model.version}",
                        flush=True,
                    )
            (
                magic,
                version,
                packet_type,
                nonce,
                run_id,
                episode_id,
                decision_id,
                obs_frame,
                target_frame,
                obs_len,
                action_hold_frames,
                model_version_expected,
            ) = OBS_HEADER.unpack(data[: OBS_HEADER.size])
            if magic != MAGIC or version != PROTOCOL_VERSION or packet_type != TYPE_OBS:
                if verbose:
                    print(f"{addr} bad_obs_header magic=0x{magic:08x} version={version} type={packet_type}")
                continue
            expected_len = OBS_HEADER.size + obs_len
            if len(data) != expected_len:
                if verbose:
                    print(f"{addr} bad_obs_size size={len(data)} expected={expected_len} obs_len={obs_len}")
                continue
            obs_state_key: str | None = None
            obs_row: dict[str, object] | None = None
            obs_payload_valid = False
            if obs_len:
                obs_row = parse_obs_spacing_payload(data[OBS_HEADER.size:])
                if obs_row is not None:
                    obs_payload_valid = True
                    obs_row.update(
                        {
                            "run_id": run_id,
                            "episode_id": episode_id,
                            "decision_id": decision_id,
                            "obs_frame": obs_frame,
                            "target_frame": target_frame,
                        }
                    )
                    obs_state_key = tabular_state_key(obs_row)
                elif verbose:
                    print(f"{addr} bad_obs_payload obs_len={obs_len}")
            tabular_state_source = ""
            if active_model.policy == "tabular":
                if obs_state_key is not None:
                    tabular_state_source = "obs"
                elif model_store.latest_tabular_state() is not None:
                    tabular_state_source = "latest"
            if action_port is not None:
                target_action = policy_action_frame(
                    active_model,
                    model_store,
                    policy_states,
                    macro_states,
                    nonce,
                    run_id,
                    episode_id,
                    policy_repeat_delay_ms,
                    obs_state_key,
                    obs_row,
                    dqn_support_prior_config,
                    effective_dqn_valid_action_mask_config,
                    dqn_projectile_timing_prior_config,
                    dqn_shoryuken_context_prior_config,
                    dqn_ground_normal_context_prior_config,
                    dqn_fireball_zoning_prior_config,
                    dqn_threat_defense_prior_config,
                    bc_inference_config,
                    actor_critic_inference_config,
                    actor_critic_spacing_prior_config,
                    tactical_policy_config,
                )
                payload = make_action_packet(
                    nonce,
                    run_id,
                    episode_id,
                    decision_id,
                    target_frame,
                    target_action,
                    active_model.version,
                )
                target = (addr[0], action_port)
                sock.sendto(payload, target)
                if obs_reply_mode == "duplicate":
                    sock.sendto(payload, target)
                elif obs_reply_mode == "wrong-target":
                    wrong_payload = make_action_packet(
                        nonce,
                        run_id,
                        episode_id,
                        decision_id,
                        target_frame + 1,
                        target_action,
                        active_model.version,
                    )
                    sock.sendto(wrong_payload, target)
                if verbose:
                    dqn_verbose = format_dqn_verbose_diagnostics(
                        active_model,
                        obs_row,
                        target_action,
                        effective_dqn_valid_action_mask_config,
                        dqn_valid_action_mask_source,
                        actor_critic_inference_config,
                        actor_critic_spacing_prior_config,
                        dqn_projectile_timing_prior_config,
                        dqn_shoryuken_context_prior_config,
                        dqn_ground_normal_context_prior_config,
                        dqn_fireball_zoning_prior_config,
                        dqn_threat_defense_prior_config,
                        tactical_policy_config,
                    )
                    print(
                        f"{target} OBS-ACTION policy={active_model.policy} reply={obs_reply_mode} "
                        f"run={run_id} ep={episode_id} dec={decision_id} obs={obs_frame} "
                        f"target={target_frame} hold={action_hold_frames}"
                        f" model_expected={model_version_expected} model={active_model.version}"
                        f" obs_payload={'yes' if obs_payload_valid else 'no'} state={tabular_state_source or 'n/a'}"
                        f" wire=0x{target_action.action_wire:04x}"
                        f" action={target_action.policy_action_id}/{target_action.policy_sub_action_id}"
                        f" step={target_action.policy_action_step}"
                        f"{dqn_verbose}"
                    )
            inference_stats.record(
                time.perf_counter_ns() - inference_start_ns,
                obs_payload=obs_payload_valid,
                tabular_state_source=tabular_state_source,
            )
            continue
        if len(data) != PACKET.size:
            if verbose:
                print(f"{addr} bad_size {len(data)}")
            continue

        magic, version, packet_type, nonce, sequence, config_hash, send_time_us = PACKET.unpack(data)
        if magic != MAGIC or version != PACKET_VERSION:
            if verbose:
                print(f"{addr} bad_header magic=0x{magic:08x} version={version}")
            continue

        if packet_type == TYPE_HELLO:
            if action_mode == "pre-ack":
                maybe_send_action(sock, addr, action_port, "valid", nonce, sequence, model_store.current().version, verbose)
                count = hello_count.get(nonce, 0) + 1
                hello_count[nonce] = count
                if count < 4:
                    if verbose:
                        print(f"{addr} PRE-ACK hold nonce={nonce} hello_count={count}")
                else:
                    reply = make_packet(TYPE_ACK, nonce, sequence, config_hash, int(time.monotonic_ns() / 1000))
                    sock.sendto(reply, addr)
            else:
                reply = make_packet(TYPE_ACK, nonce, sequence, config_hash, int(time.monotonic_ns() / 1000))
                sock.sendto(reply, addr)
        elif packet_type == TYPE_PING:
            reply = make_packet(TYPE_PONG, nonce, sequence, config_hash, send_time_us)
            sock.sendto(reply, addr)
            if action_mode in {"valid", "stale"}:
                maybe_send_action(sock, addr, action_port, action_mode, nonce, sequence, model_store.current().version, verbose)

        should_log_packet, ping_verbose_count, packet_extra = verbose_packet_log_decision(
            packet_type,
            ping_verbose_count,
            verbose_ping_interval,
        )
        should_log_packet = verbose and should_log_packet
        if should_log_packet:
            print(
                f"{addr} {packet_name(packet_type)} nonce={nonce} seq={sequence} "
                f"hash=0x{config_hash:08x}{packet_extra}"
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="0.0.0.0", help="UDP bind host")
    parser.add_argument("--port", type=int, default=37330, help="UDP bind port")
    parser.add_argument("--action-port", type=int, default=None, help="MiSTer-side UDP action receive port")
    parser.add_argument(
        "--action-mode",
        choices=["off", "valid", "stale", "pre-ack"],
        default="off",
        help="Optionally send test action packets for gate validation",
    )
    parser.add_argument(
        "--policy",
        choices=POLICY_CHOICES,
        default="forward",
        help="Fixed or scripted action used when MiSTer sends observation headers",
    )
    parser.add_argument(
        "--obs-reply-mode",
        choices=["normal", "duplicate", "wrong-target"],
        default="normal",
        help="How to reply to Milestone 3 observation headers",
    )
    parser.add_argument("--model-version", type=int, default=0, help="Model version stamped into action packets")
    parser.add_argument(
        "--policy-repeat-delay-ms",
        type=int,
        default=0,
        help="Neutral stand delay after each scripted policy loop before repeating",
    )
    parser.add_argument(
        "--transition-log",
        default=None,
        help="Optional local rl-transitions.ndjson path for background learner/log-reader stats",
    )
    parser.add_argument(
        "--combat-event-log",
        default=None,
        help=(
            "Optional local combat-events.ndjson path. When transition batch uploads contain "
            "combat_event_schema_version rows, they are split here instead of entering --transition-log."
        ),
    )
    parser.add_argument(
        "--learner-stats-interval-sec",
        type=float,
        default=5.0,
        help="Stats print interval for the optional background learner/log reader",
    )
    parser.add_argument(
        "--learner-tail-from-start",
        action="store_true",
        help="Read --transition-log from the beginning instead of tailing new rows",
    )
    parser.add_argument(
        "--replay-capacity",
        type=int,
        default=100000,
        help="Maximum number of learner-safe transition rows kept in the local replay buffer",
    )
    parser.add_argument(
        "--learner-batch-size",
        type=int,
        default=128,
        help="Batch size used for replay readiness stats and sampling smoke checks",
    )
    parser.add_argument(
        "--learner-warmup-rows",
        type=int,
        default=5000,
        help="Minimum replay rows before the learner is considered ready to train",
    )
    parser.add_argument(
        "--transition-pull-interval-sec",
        type=float,
        default=5.0,
        help="Background poll interval for pulling transition logs into --transition-log",
    )
    parser.add_argument(
        "--transition-pull-host",
        default=os.environ.get("MISTER_HOST", "192.168.1.171"),
        help="MiSTer host used by the optional transition puller",
    )
    parser.add_argument(
        "--transition-pull-user",
        default=os.environ.get("MISTER_USER", "root"),
        help="MiSTer SSH user used by the optional transition puller",
    )
    parser.add_argument(
        "--transition-pull-password",
        default=os.environ.get("MISTER_PASSWORD"),
        help="MiSTer SSH password used by the optional transition puller",
    )
    parser.add_argument(
        "--transition-pull-remote-path",
        default=None,
        help="Optional remote transition log path to pull into --transition-log using SCP",
    )
    parser.add_argument(
        "--transition-pull-local-source",
        default=None,
        help="Optional local source file used to smoke-test the background puller without remote access",
    )
    parser.add_argument(
        "--transition-port",
        type=int,
        default=None,
        help="TCP port for non-critical episode transition batch uploads; defaults to --action-port + 1 when transition logging is enabled",
    )
    parser.add_argument(
        "--learner-only",
        action="store_true",
        help="Skip UDP bind and run only the transition pull / replay-import background paths",
    )
    parser.add_argument(
        "--model-dir",
        default=None,
        help="Optional directory for versioned actor manifests and atomic current.json hot-swap",
    )
    parser.add_argument(
        "--learner-auto-publish",
        action="store_true",
        help="Publish a new actor manifest whenever replay warmup is ready and the publish interval elapses",
    )
    parser.add_argument(
        "--learner-publish-interval-sec",
        type=float,
        default=30.0,
        help="Minimum interval between learner actor publications when --learner-auto-publish is set",
    )
    parser.add_argument(
        "--learner-publish-policy",
        choices=SCRIPTED_POLICY_CHOICES + ("tabular",),
        default=None,
        help="Policy stamped into learner-published actor manifests; defaults to the currently active policy; DQN is published by the offline trainer",
    )
    parser.add_argument(
        "--tabular-alpha",
        type=float,
        default=0.05,
        help="Contextual-bandit learning rate used by the tabular learner",
    )
    parser.add_argument(
        "--tabular-epsilon",
        type=float,
        default=0.10,
        help="Exploration probability stamped into learner-published tabular actors",
    )
    parser.add_argument(
        "--tabular-actions",
        default=",".join(TABULAR_DEFAULT_ACTIONS),
        help="Comma-separated action subset used by live tabular learning and tabular actor manifests",
    )
    parser.add_argument(
        "--tabular-fallback-policy",
        choices=SCRIPTED_POLICY_CHOICES,
        default="hp",
        help="Scripted policy used when a tabular actor has no score for the current bucket",
    )
    parser.add_argument(
        "--tabular-min-action-count",
        type=int,
        default=8,
        help="Minimum state/action update count before a tabular q-score can drive greedy inference",
    )
    parser.add_argument(
        "--dqn-support-prior-min-count",
        type=int,
        default=0,
        help="Minimum replay action count before DQN support-prior count penalty is skipped; 0 disables count penalty",
    )
    parser.add_argument(
        "--dqn-support-prior-count-penalty",
        type=float,
        default=0.0,
        help="Q-score penalty applied proportionally to missing replay support below --dqn-support-prior-min-count",
    )
    parser.add_argument(
        "--dqn-support-prior-negative-mean-penalty",
        type=float,
        default=0.0,
        help="Q-score penalty applied when an action's replay mean reward is non-positive",
    )
    parser.add_argument(
        "--dqn-support-prior-exempt-actions",
        default="",
        help="Comma-separated DQN actions exempt from support-prior penalties",
    )
    parser.add_argument(
        "--dqn-valid-action-mask",
        choices=DQN_VALID_ACTION_MASK_CLI_MODES,
        default="auto",
        help=(
            "DQN action eligibility mask. auto reads metadata.dqn_valid_action_mask_config from the active "
            "actor; off disables masking; self-routine-v1 uses current self routine/contact fields; "
            "action-start-v1 uses schema-backed ground/jump/air action-start flags"
        ),
    )
    parser.add_argument(
        "--bc-valid-action-mask",
        choices=DQN_VALID_ACTION_MASK_CLI_MODES,
        default="action-start-v1",
        help=(
            "BC action eligibility mask. Defaults to action-start-v1 so sampled BC actions respect "
            "ground/jump/air start eligibility; auto reads metadata.dqn_valid_action_mask_config."
        ),
    )
    parser.add_argument(
        "--bc-temperature",
        type=float,
        default=0.8,
        help="Softmax temperature for BC top-k action sampling; 0 makes BC deterministic argmax",
    )
    parser.add_argument(
        "--bc-top-k",
        type=int,
        default=3,
        help="Number of highest-logit valid BC actions to sample from; 0 samples from every valid action",
    )
    parser.add_argument(
        "--bc-deterministic-danger",
        action="store_true",
        help="Force BC to choose the best guard/back action in close attack or urgent projectile danger rows",
    )
    parser.add_argument(
        "--bc-danger-max-time-to-self",
        type=int,
        default=12,
        help="Maximum obs_projectile_time_to_self treated as urgent for --bc-deterministic-danger",
    )
    parser.add_argument(
        "--bc-danger-max-abs-dx",
        type=int,
        default=144,
        help="Maximum obs_abs_dx or incoming projectile rel_x treated as danger for BC deterministic guard/back",
    )
    parser.add_argument(
        "--bc-danger-max-abs-y",
        type=int,
        default=96,
        help="Maximum absolute projectile rel_y treated as urgent for --bc-deterministic-danger",
    )
    parser.add_argument(
        "--actor-critic-valid-action-mask",
        choices=DQN_VALID_ACTION_MASK_CLI_MODES,
        default="action-start-v1",
        help=(
            "Actor-critic action eligibility mask. Defaults to action-start-v1 so sampled actions respect "
            "ground/jump/air start eligibility; auto reads metadata.awac_config.valid_action_mask when present."
        ),
    )
    parser.add_argument(
        "--actor-critic-temperature",
        type=float,
        default=0.8,
        help="Softmax temperature for actor-critic top-k action sampling; 0 makes actor-critic deterministic argmax",
    )
    parser.add_argument(
        "--actor-critic-top-k",
        type=int,
        default=8,
        help="Number of highest-logit valid actor-critic actions to sample from; 0 samples from every valid action",
    )
    parser.add_argument(
        "--actor-critic-top-p",
        type=float,
        default=0.0,
        help="Optional nucleus threshold after top-k filtering for actor-critic sampling; 0 disables top-p",
    )
    parser.add_argument(
        "--actor-critic-spacing-prior",
        action="store_true",
        help="Apply an opt-in spacing prior to actor-critic logits so far rows prefer approach/fireball over close-range attacks",
    )
    parser.add_argument(
        "--actor-critic-spacing-close-max-abs-dx",
        type=int,
        default=64,
        help="Maximum obs_abs_dx treated as close enough for unpenalized close-range actor-critic attacks",
    )
    parser.add_argument(
        "--actor-critic-spacing-poke-max-abs-dx",
        type=int,
        default=120,
        help="Maximum obs_abs_dx treated as poke range before actor-critic far-spacing penalties/forward bonus apply",
    )
    parser.add_argument(
        "--actor-critic-spacing-very-far-min-abs-dx",
        type=int,
        default=220,
        help="Minimum obs_abs_dx treated as very far for extra actor-critic close-action suppression",
    )
    parser.add_argument(
        "--actor-critic-spacing-forward-bonus",
        type=float,
        default=0.70,
        help="Actor-critic logit bonus for forward beyond the poke range",
    )
    parser.add_argument(
        "--actor-critic-spacing-back-penalty",
        type=float,
        default=0.80,
        help="Actor-critic logit penalty for back beyond the poke range",
    )
    parser.add_argument(
        "--actor-critic-spacing-far-guard-penalty",
        type=float,
        default=0.25,
        help="Actor-critic logit penalty for guard-stand/guard-crouch beyond the poke range",
    )
    parser.add_argument(
        "--actor-critic-spacing-close-attack-far-penalty",
        type=float,
        default=0.75,
        help="Actor-critic logit penalty for close-range attacks beyond close range",
    )
    parser.add_argument(
        "--actor-critic-spacing-shoryuken-far-penalty",
        type=float,
        default=1.20,
        help="Actor-critic logit penalty for Shoryuken beyond poke range",
    )
    parser.add_argument(
        "--actor-critic-spacing-fireball-bonus",
        type=float,
        default=0.35,
        help="Actor-critic logit bonus for fireballs inside the configured zoning range",
    )
    parser.add_argument(
        "--actor-critic-spacing-fireball-min-abs-dx",
        type=int,
        default=96,
        help="Minimum obs_abs_dx where actor-critic fireball spacing bonus applies",
    )
    parser.add_argument(
        "--actor-critic-spacing-fireball-max-abs-dx",
        type=int,
        default=280,
        help="Maximum obs_abs_dx where actor-critic fireball spacing bonus applies",
    )
    parser.add_argument(
        "--actor-critic-spacing-threat-attack-max-abs-dx",
        type=int,
        default=160,
        help="Maximum obs_abs_dx where opponent attack state suppresses approach spacing and activates defense bias",
    )
    parser.add_argument(
        "--actor-critic-spacing-threat-guard-bonus",
        type=float,
        default=0.90,
        help="Actor-critic logit bonus for guard-stand/guard-crouch while spacing prior sees a threat",
    )
    parser.add_argument(
        "--actor-critic-spacing-threat-back-bonus",
        type=float,
        default=0.45,
        help="Actor-critic logit bonus for back while spacing prior sees a threat",
    )
    parser.add_argument(
        "--actor-critic-spacing-threat-forward-penalty",
        type=float,
        default=1.10,
        help="Actor-critic logit penalty for forward while spacing prior sees a threat",
    )
    parser.add_argument(
        "--actor-critic-spacing-threat-attack-penalty",
        type=float,
        default=0.75,
        help="Actor-critic logit penalty for close attacks/specials while spacing prior sees a threat",
    )
    parser.add_argument(
        "--tactical-valid-action-mask",
        choices=DQN_VALID_ACTION_MASK_MODES,
        default="action-start-v1",
        help="Action eligibility mask used by --policy tactical",
    )
    parser.add_argument(
        "--tactical-close-max-abs-dx",
        type=int,
        default=64,
        help="Maximum obs_abs_dx treated as close range by --policy tactical",
    )
    parser.add_argument(
        "--tactical-poke-max-abs-dx",
        type=int,
        default=120,
        help="Maximum obs_abs_dx treated as poke range by --policy tactical",
    )
    parser.add_argument(
        "--tactical-fireball-max-abs-dx",
        type=int,
        default=260,
        help="Maximum obs_abs_dx treated as fireball zoning range by --policy tactical",
    )
    parser.add_argument(
        "--tactical-too-far-min-abs-dx",
        type=int,
        default=220,
        help="Minimum obs_abs_dx where --policy tactical strongly prefers approach before fireball",
    )
    parser.add_argument(
        "--tactical-corner-edge-max-dist",
        type=int,
        default=48,
        help="Maximum edge distance treated as cornered by --policy tactical",
    )
    parser.add_argument(
        "--tactical-incoming-projectile-max-time-to-self",
        type=int,
        default=18,
        help="Maximum obs_projectile_time_to_self treated as incoming projectile threat by --policy tactical",
    )
    parser.add_argument(
        "--tactical-incoming-projectile-max-dx",
        type=int,
        default=220,
        help="Maximum positive obs_projectile_rel_x treated as incoming projectile threat by --policy tactical",
    )
    parser.add_argument(
        "--tactical-jump-in-max-abs-dx",
        type=int,
        default=128,
        help="Maximum obs_abs_dx where opponent airborne state is treated as jump-in threat by --policy tactical",
    )
    parser.add_argument(
        "--tactical-threat-attack-max-abs-dx",
        type=int,
        default=144,
        help="Maximum obs_abs_dx where opponent attack state is treated as close attack threat by --policy tactical",
    )
    parser.add_argument(
        "--dqn-projectile-timing-prior",
        action="store_true",
        help="Apply a soft jump-start Q penalty for close incoming opponent projectiles before DQN argmax",
    )
    parser.add_argument(
        "--dqn-projectile-prior-urgent-jump-penalty",
        type=float,
        default=0.05,
        help="Jump-start Q penalty when obs_projectile_time_to_self is in the urgent projectile bucket",
    )
    parser.add_argument(
        "--dqn-projectile-prior-borderline-jump-penalty",
        type=float,
        default=0.03,
        help="Jump-start Q penalty when obs_projectile_time_to_self is in the borderline projectile bucket",
    )
    parser.add_argument(
        "--dqn-projectile-prior-min-time-to-self",
        type=int,
        default=0,
        help="Minimum obs_projectile_time_to_self eligible for the projectile timing prior",
    )
    parser.add_argument(
        "--dqn-projectile-prior-urgent-max-time-to-self",
        type=int,
        default=6,
        help="Maximum obs_projectile_time_to_self for the urgent projectile prior bucket",
    )
    parser.add_argument(
        "--dqn-projectile-prior-borderline-max-time-to-self",
        type=int,
        default=12,
        help="Maximum obs_projectile_time_to_self for the borderline projectile prior bucket",
    )
    parser.add_argument(
        "--dqn-projectile-prior-early-jump-penalty",
        type=float,
        default=0.0,
        help="Optional jump-start Q penalty for too-early far projectile timing",
    )
    parser.add_argument(
        "--dqn-projectile-prior-early-min-time-to-self",
        type=int,
        default=31,
        help="Minimum obs_projectile_time_to_self for the optional too-early projectile prior bucket",
    )
    parser.add_argument(
        "--dqn-projectile-prior-early-max-time-to-self",
        type=int,
        default=48,
        help="Maximum obs_projectile_time_to_self for the optional too-early projectile prior bucket",
    )
    parser.add_argument(
        "--dqn-projectile-prior-threat-max-dx",
        type=int,
        default=240,
        help="Maximum positive obs_projectile_rel_x eligible for the projectile timing prior",
    )
    parser.add_argument(
        "--dqn-projectile-prior-threat-max-abs-y",
        type=int,
        default=96,
        help="Maximum absolute obs_projectile_rel_y eligible for the projectile timing prior",
    )
    parser.add_argument(
        "--dqn-shoryuken-context-prior",
        action="store_true",
        help="Apply a soft Shoryuken Q penalty outside coarse anti-air contexts before DQN argmax",
    )
    parser.add_argument(
        "--dqn-shoryuken-prior-penalty",
        type=float,
        default=0.04,
        help="Shoryuken Q penalty outside the anti-air context when --dqn-shoryuken-context-prior is enabled",
    )
    parser.add_argument(
        "--dqn-shoryuken-prior-min-abs-dx",
        type=int,
        default=24,
        help="Minimum obs_abs_dx considered a plausible anti-air Shoryuken context",
    )
    parser.add_argument(
        "--dqn-shoryuken-prior-max-abs-dx",
        type=int,
        default=150,
        help="Maximum obs_abs_dx considered a plausible anti-air Shoryuken context",
    )
    parser.add_argument(
        "--dqn-shoryuken-prior-opp-air-routine-min",
        type=int,
        default=18,
        help="Minimum obs_opp_routine_2 treated as opponent jump/air routine for the Shoryuken prior",
    )
    parser.add_argument(
        "--dqn-shoryuken-prior-opp-air-routine-max",
        type=int,
        default=26,
        help="Maximum obs_opp_routine_2 treated as opponent jump/air routine for the Shoryuken prior",
    )
    parser.add_argument(
        "--dqn-shoryuken-prior-far-min-abs-dx",
        type=int,
        default=0,
        help="Minimum obs_abs_dx for optional extra Shoryuken penalty outside anti-air context; 0 keeps it available from any non-anti-air distance when extra penalty is set",
    )
    parser.add_argument(
        "--dqn-shoryuken-prior-far-extra-penalty",
        type=float,
        default=0.0,
        help="Additional Shoryuken Q penalty for non-anti-air rows at or beyond --dqn-shoryuken-prior-far-min-abs-dx",
    )
    parser.add_argument(
        "--dqn-shoryuken-prior-far-block",
        action="store_true",
        help="Hard-block Shoryuken in non-anti-air rows at or beyond --dqn-shoryuken-prior-far-min-abs-dx",
    )
    parser.add_argument(
        "--dqn-ground-normal-context-prior",
        action="store_true",
        help="Apply a soft grounded normal Q penalty outside close or threat/contact poke contexts before DQN argmax",
    )
    parser.add_argument(
        "--dqn-ground-normal-prior-penalty",
        type=float,
        default=0.04,
        help="Grounded normal Q penalty outside close or threat/contact poke contexts",
    )
    parser.add_argument(
        "--dqn-ground-normal-prior-close-max-abs-dx",
        type=int,
        default=48,
        help="Maximum obs_abs_dx where stand/crouch normals are not penalized by the ground-normal prior",
    )
    parser.add_argument(
        "--dqn-ground-normal-prior-poke-max-abs-dx",
        type=int,
        default=120,
        help="Maximum obs_abs_dx for threat/contact poke contexts before normals are penalized as too far",
    )
    parser.add_argument(
        "--dqn-fireball-zoning-prior",
        action="store_true",
        help="Apply a soft fireball Q bonus in far grounded zoning contexts before DQN argmax",
    )
    parser.add_argument(
        "--dqn-fireball-zoning-prior-bonus",
        type=float,
        default=0.03,
        help="Fireball Q bonus in eligible far grounded zoning contexts",
    )
    parser.add_argument(
        "--dqn-fireball-zoning-prior-min-abs-dx",
        type=int,
        default=120,
        help="Minimum obs_abs_dx considered an eligible fireball zoning context",
    )
    parser.add_argument(
        "--dqn-fireball-zoning-prior-max-abs-dx",
        type=int,
        default=260,
        help="Maximum obs_abs_dx considered an eligible fireball zoning context",
    )
    parser.add_argument(
        "--dqn-threat-defense-prior",
        action="store_true",
        help="Apply a soft guard/back Q bonus when the opponent is attacking at close/mid range",
    )
    parser.add_argument(
        "--dqn-threat-defense-prior-guard-bonus",
        type=float,
        default=0.03,
        help="Guard Q bonus in eligible opponent-attack close/mid contexts",
    )
    parser.add_argument(
        "--dqn-threat-defense-prior-back-bonus",
        type=float,
        default=0.02,
        help="Back Q bonus in eligible opponent-attack close/mid contexts",
    )
    parser.add_argument(
        "--dqn-threat-defense-prior-unsafe-penalty",
        type=float,
        default=0.0,
        help="Forward and grounded-normal Q penalty in eligible opponent-attack close/mid contexts",
    )
    parser.add_argument(
        "--dqn-threat-defense-prior-max-abs-dx",
        type=int,
        default=144,
        help="Maximum obs_abs_dx considered an eligible opponent-attack defense context",
    )
    parser.add_argument(
        "--dqn-threat-defense-prior-contact-sustain",
        action="store_true",
        help=(
            "Keep threat-defense guard/back pressure active while self is in contact reaction and "
            "the opponent is still attacking; useful for multi-hit block-stun gaps"
        ),
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Log valid packets; PING summaries are sampled by --verbose-ping-interval",
    )
    parser.add_argument(
        "--verbose-ping-interval",
        type=int,
        default=120,
        help="When --verbose is set, print one PING summary every N PING packets; 0 suppresses PING summaries",
    )
    args = parser.parse_args()
    transition_log = args.transition_log
    if transition_log is None and (args.transition_pull_remote_path or args.transition_pull_local_source):
        transition_log = "/tmp/rl-transitions-pulled.ndjson"
    if args.combat_event_log and transition_log is None:
        raise SystemExit("--combat-event-log requires --transition-log so both files come from the same batch envelope")
    transition_server_port = args.transition_port
    if transition_server_port is None and transition_log is not None and args.action_port is not None:
        transition_server_port = args.action_port + 1
    tabular_actions = parse_action_names(args.tabular_actions, option_name="--tabular-actions")
    fallback_action = canonical_tabular_action_name(args.tabular_fallback_policy)
    tabular_actor_requested = args.policy == "tabular" or args.learner_publish_policy == "tabular"
    if tabular_actor_requested:
        if fallback_action is None:
            raise SystemExit(
                f"--tabular-fallback-policy {args.tabular_fallback_policy} is not a tabular action alias"
            )
        if fallback_action not in tabular_actions:
            raise SystemExit(
                f"--tabular-fallback-policy {args.tabular_fallback_policy} resolves to {fallback_action}, "
                f"which is not in --tabular-actions"
            )
    dqn_support_prior_config = DQNSupportPriorConfig(
        min_action_count=max(0, int(args.dqn_support_prior_min_count)),
        count_penalty=max(0.0, float(args.dqn_support_prior_count_penalty)),
        negative_mean_penalty=max(0.0, float(args.dqn_support_prior_negative_mean_penalty)),
        exempt_actions=parse_action_name_set(
            str(args.dqn_support_prior_exempt_actions),
            option_name="--dqn-support-prior-exempt-actions",
        ),
    )
    dqn_valid_action_mask_auto, dqn_valid_action_mask_config = parse_dqn_valid_action_mask_cli_config(
        str(args.dqn_valid_action_mask)
    )
    bc_valid_action_mask_auto, bc_valid_action_mask_config = parse_dqn_valid_action_mask_cli_config(
        str(args.bc_valid_action_mask)
    )
    actor_critic_valid_action_mask_auto, actor_critic_valid_action_mask_config = parse_dqn_valid_action_mask_cli_config(
        str(args.actor_critic_valid_action_mask)
    )
    bc_inference_config = BCInferenceConfig(
        temperature=max(0.0, float(args.bc_temperature)),
        top_k=max(0, int(args.bc_top_k)),
        deterministic_danger=bool(args.bc_deterministic_danger),
        danger_max_time_to_self=max(0, int(args.bc_danger_max_time_to_self)),
        danger_max_abs_dx=max(0, int(args.bc_danger_max_abs_dx)),
        danger_max_abs_y=max(0, int(args.bc_danger_max_abs_y)),
    )
    actor_critic_inference_config = ActorCriticInferenceConfig(
        temperature=max(0.0, float(args.actor_critic_temperature)),
        top_k=max(0, int(args.actor_critic_top_k)),
        top_p=max(0.0, min(1.0, float(args.actor_critic_top_p))),
    )
    actor_critic_spacing_close_max_dx = max(0, int(args.actor_critic_spacing_close_max_abs_dx))
    actor_critic_spacing_poke_max_dx = max(
        actor_critic_spacing_close_max_dx,
        int(args.actor_critic_spacing_poke_max_abs_dx),
    )
    actor_critic_spacing_very_far_min_dx = max(
        actor_critic_spacing_poke_max_dx,
        int(args.actor_critic_spacing_very_far_min_abs_dx),
    )
    actor_critic_spacing_fireball_min_dx = max(0, int(args.actor_critic_spacing_fireball_min_abs_dx))
    actor_critic_spacing_fireball_max_dx = max(
        actor_critic_spacing_fireball_min_dx,
        int(args.actor_critic_spacing_fireball_max_abs_dx),
    )
    actor_critic_spacing_prior_config = ActorCriticSpacingPriorConfig(
        enabled=bool(args.actor_critic_spacing_prior),
        close_max_abs_dx=actor_critic_spacing_close_max_dx,
        poke_max_abs_dx=actor_critic_spacing_poke_max_dx,
        very_far_min_abs_dx=actor_critic_spacing_very_far_min_dx,
        forward_bonus=max(0.0, float(args.actor_critic_spacing_forward_bonus)),
        back_penalty=max(0.0, float(args.actor_critic_spacing_back_penalty)),
        far_guard_penalty=max(0.0, float(args.actor_critic_spacing_far_guard_penalty)),
        close_attack_far_penalty=max(0.0, float(args.actor_critic_spacing_close_attack_far_penalty)),
        shoryuken_far_penalty=max(0.0, float(args.actor_critic_spacing_shoryuken_far_penalty)),
        fireball_bonus=max(0.0, float(args.actor_critic_spacing_fireball_bonus)),
        fireball_min_abs_dx=actor_critic_spacing_fireball_min_dx,
        fireball_max_abs_dx=actor_critic_spacing_fireball_max_dx,
        threat_attack_max_abs_dx=max(0, int(args.actor_critic_spacing_threat_attack_max_abs_dx)),
        threat_guard_bonus=max(0.0, float(args.actor_critic_spacing_threat_guard_bonus)),
        threat_back_bonus=max(0.0, float(args.actor_critic_spacing_threat_back_bonus)),
        threat_forward_penalty=max(0.0, float(args.actor_critic_spacing_threat_forward_penalty)),
        threat_attack_penalty=max(0.0, float(args.actor_critic_spacing_threat_attack_penalty)),
    )
    tactical_close_max_dx = max(0, int(args.tactical_close_max_abs_dx))
    tactical_poke_max_dx = max(tactical_close_max_dx, int(args.tactical_poke_max_abs_dx))
    tactical_fireball_max_dx = max(tactical_poke_max_dx, int(args.tactical_fireball_max_abs_dx))
    tactical_policy_config = TacticalPolicyConfig(
        close_max_abs_dx=tactical_close_max_dx,
        poke_max_abs_dx=tactical_poke_max_dx,
        fireball_max_abs_dx=tactical_fireball_max_dx,
        too_far_min_abs_dx=max(tactical_poke_max_dx, int(args.tactical_too_far_min_abs_dx)),
        corner_edge_max_dist=max(0, int(args.tactical_corner_edge_max_dist)),
        incoming_projectile_max_time_to_self=max(0, int(args.tactical_incoming_projectile_max_time_to_self)),
        incoming_projectile_max_dx=max(0, int(args.tactical_incoming_projectile_max_dx)),
        incoming_projectile_max_abs_y=96,
        jump_in_max_abs_dx=max(0, int(args.tactical_jump_in_max_abs_dx)),
        threat_attack_max_abs_dx=max(0, int(args.tactical_threat_attack_max_abs_dx)),
        valid_action_mask_mode=str(args.tactical_valid_action_mask),
    )
    projectile_prior_min_time = max(0, int(args.dqn_projectile_prior_min_time_to_self))
    projectile_prior_urgent_max_time = max(
        projectile_prior_min_time,
        int(args.dqn_projectile_prior_urgent_max_time_to_self),
    )
    projectile_prior_borderline_max_time = max(
        projectile_prior_urgent_max_time,
        int(args.dqn_projectile_prior_borderline_max_time_to_self),
    )
    projectile_prior_early_min_time = max(
        projectile_prior_borderline_max_time + 1,
        int(args.dqn_projectile_prior_early_min_time_to_self),
    )
    projectile_prior_early_max_time = max(
        projectile_prior_early_min_time,
        int(args.dqn_projectile_prior_early_max_time_to_self),
    )
    dqn_projectile_timing_prior_config = DQNProjectileTimingPriorConfig(
        enabled=bool(args.dqn_projectile_timing_prior),
        min_time_to_self=projectile_prior_min_time,
        urgent_max_time_to_self=projectile_prior_urgent_max_time,
        borderline_max_time_to_self=projectile_prior_borderline_max_time,
        urgent_jump_penalty=max(0.0, float(args.dqn_projectile_prior_urgent_jump_penalty)),
        borderline_jump_penalty=max(0.0, float(args.dqn_projectile_prior_borderline_jump_penalty)),
        early_min_time_to_self=projectile_prior_early_min_time,
        early_max_time_to_self=projectile_prior_early_max_time,
        early_jump_penalty=max(0.0, float(args.dqn_projectile_prior_early_jump_penalty)),
        threat_max_dx=max(0, int(args.dqn_projectile_prior_threat_max_dx)),
        threat_max_abs_y=max(0, int(args.dqn_projectile_prior_threat_max_abs_y)),
    )
    shoryuken_prior_min_dx = max(0, int(args.dqn_shoryuken_prior_min_abs_dx))
    shoryuken_prior_max_dx = max(shoryuken_prior_min_dx, int(args.dqn_shoryuken_prior_max_abs_dx))
    shoryuken_prior_air_min = max(0, int(args.dqn_shoryuken_prior_opp_air_routine_min))
    shoryuken_prior_air_max = max(shoryuken_prior_air_min, int(args.dqn_shoryuken_prior_opp_air_routine_max))
    shoryuken_prior_far_min_dx = max(0, int(args.dqn_shoryuken_prior_far_min_abs_dx))
    dqn_shoryuken_context_prior_config = DQNShoryukenContextPriorConfig(
        enabled=bool(args.dqn_shoryuken_context_prior),
        penalty=max(0.0, float(args.dqn_shoryuken_prior_penalty)),
        min_abs_dx=shoryuken_prior_min_dx,
        max_abs_dx=shoryuken_prior_max_dx,
        opp_air_routine_min=shoryuken_prior_air_min,
        opp_air_routine_max=shoryuken_prior_air_max,
        far_min_abs_dx=shoryuken_prior_far_min_dx,
        far_extra_penalty=max(0.0, float(args.dqn_shoryuken_prior_far_extra_penalty)),
        far_block=bool(args.dqn_shoryuken_prior_far_block),
    )
    ground_normal_prior_close_max_dx = max(0, int(args.dqn_ground_normal_prior_close_max_abs_dx))
    ground_normal_prior_poke_max_dx = max(
        ground_normal_prior_close_max_dx,
        int(args.dqn_ground_normal_prior_poke_max_abs_dx),
    )
    dqn_ground_normal_context_prior_config = DQNGroundNormalContextPriorConfig(
        enabled=bool(args.dqn_ground_normal_context_prior),
        penalty=max(0.0, float(args.dqn_ground_normal_prior_penalty)),
        close_max_abs_dx=ground_normal_prior_close_max_dx,
        poke_max_abs_dx=ground_normal_prior_poke_max_dx,
    )
    fireball_zoning_prior_min_dx = max(0, int(args.dqn_fireball_zoning_prior_min_abs_dx))
    fireball_zoning_prior_max_dx = max(
        fireball_zoning_prior_min_dx,
        int(args.dqn_fireball_zoning_prior_max_abs_dx),
    )
    dqn_fireball_zoning_prior_config = DQNFireballZoningPriorConfig(
        enabled=bool(args.dqn_fireball_zoning_prior),
        bonus=max(0.0, float(args.dqn_fireball_zoning_prior_bonus)),
        min_abs_dx=fireball_zoning_prior_min_dx,
        max_abs_dx=fireball_zoning_prior_max_dx,
    )
    dqn_threat_defense_prior_config = DQNThreatDefensePriorConfig(
        enabled=bool(args.dqn_threat_defense_prior),
        guard_bonus=max(0.0, float(args.dqn_threat_defense_prior_guard_bonus)),
        back_bonus=max(0.0, float(args.dqn_threat_defense_prior_back_bonus)),
        unsafe_penalty=max(0.0, float(args.dqn_threat_defense_prior_unsafe_penalty)),
        max_abs_dx=max(0, int(args.dqn_threat_defense_prior_max_abs_dx)),
        contact_sustain=bool(args.dqn_threat_defense_prior_contact_sustain),
    )
    serve(
        args.host,
        args.port,
        args.verbose,
        max(0, int(args.verbose_ping_interval)),
        args.action_port,
        args.action_mode,
        args.policy,
        args.obs_reply_mode,
        args.model_version,
        args.policy_repeat_delay_ms,
        transition_log,
        args.combat_event_log,
        args.learner_stats_interval_sec,
        args.learner_tail_from_start,
        args.replay_capacity,
        args.learner_batch_size,
        args.learner_warmup_rows,
        args.transition_pull_interval_sec,
        args.transition_pull_host,
        args.transition_pull_user,
        args.transition_pull_password,
        args.transition_pull_remote_path,
        args.transition_pull_local_source,
        transition_server_port or 0,
        args.learner_only,
        args.model_dir,
        args.learner_auto_publish,
        args.learner_publish_interval_sec,
        args.learner_publish_policy,
        args.tabular_alpha,
        args.tabular_epsilon,
        args.tabular_fallback_policy,
        tabular_actions,
        args.tabular_min_action_count,
        dqn_support_prior_config,
        dqn_valid_action_mask_config,
        dqn_valid_action_mask_auto,
        bc_valid_action_mask_config,
        bc_valid_action_mask_auto,
        bc_inference_config,
        actor_critic_valid_action_mask_config,
        actor_critic_valid_action_mask_auto,
        actor_critic_inference_config,
        actor_critic_spacing_prior_config,
        tactical_policy_config,
        dqn_projectile_timing_prior_config,
        dqn_shoryuken_context_prior_config,
        dqn_ground_normal_context_prior_config,
        dqn_fireball_zoning_prior_config,
        dqn_threat_defense_prior_config,
    )


if __name__ == "__main__":
    main()
