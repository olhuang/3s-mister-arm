#!/usr/bin/env python3
"""Minimal UDP server for Milestone 2/3 RL hello/ack, ping/pong, and remote-action probing."""

from __future__ import annotations

import argparse
import collections
import json
import os
import random
import socket
import struct
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass, field


MAGIC = 0x33524C41
PACKET_VERSION = 1
PROTOCOL_VERSION = 3
TYPE_HELLO = 1
TYPE_ACK = 2
TYPE_PING = 3
TYPE_PONG = 4
TYPE_OBS = 5
PACKET = struct.Struct("<IHHQIIQ")
ACTION_PACKET = struct.Struct("<IHHQQIIIHHHHI")
OBS_HEADER = struct.Struct("<IHHQQIIIIHHI")
OBS_SPACING_PAYLOAD = struct.Struct("<HHhhhhhhBBBBB3x")
OBS_SPACING_PAYLOAD_VERSION = 2
TRANSITION_BATCH_HEADER = struct.Struct("<IHHQQIII")
TRANSITION_BATCH_ACK = struct.Struct("<IHHQQII")
ACTION_SET_VERSION = 4

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
RL_POLICY_ACTION_RYU_SHINKUU_HADOUKEN = 1220
RL_POLICY_ACTION_RYU_DENJIN_HADOUKEN = 1221
RL_POLICY_ACTION_RYU_SHIN_SHORYUKEN = 1222
RL_POLICY_ACTION_RYU_SHORYUKEN = 1228
RL_POLICY_ACTION_RYU_FIREBALL = 1229
RL_POLICY_ACTION_RYU_TATSU = 1230
RL_POLICY_ACTION_RYU_JOUDAN = 1231
RL_POLICY_ACTION_RYU_AIR_TATSU = 1246

RL_POLICY_SUB_NONE = 0
RL_POLICY_SUB_LP = 1
RL_POLICY_SUB_MP = 2
RL_POLICY_SUB_HP = 3
RL_POLICY_SUB_LK = 4
RL_POLICY_SUB_MK = 5
RL_POLICY_SUB_HK = 6
RL_POLICY_SUB_FORWARD = 13
RL_POLICY_SUB_BACK = 14
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
RL_POLICY_JUMP_DIRECTIONS = (
    ("forward", RL_MOVE_UP_FORWARD, RL_POLICY_ACTION_JUMP_ATTACK_FORWARD),
    ("neutral", RL_MOVE_UP, RL_POLICY_ACTION_JUMP_ATTACK_NEUTRAL),
    ("back", RL_MOVE_UP_BACK, RL_POLICY_ACTION_JUMP_ATTACK_BACK),
)
STAND_NORMAL_ACTION_NAMES = tuple(f"stand-{button}" for button, _, _ in RL_POLICY_BUTTONS)
CROUCH_NORMAL_ACTION_NAMES = tuple(f"crouch-{button}" for button, _, _ in RL_POLICY_BUTTONS)
FIREBALL_ACTION_NAMES = ("fireball", "fireball-mp", "fireball-hp")
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
JUMP_NORMAL_ACTION_NAMES = tuple(
    f"jump-{direction}-{button}"
    for direction, _, _ in RL_POLICY_JUMP_DIRECTIONS
    for button, _, _ in RL_POLICY_BUTTONS
)
JUMP_NORMAL_ACTION_WIRES = {
    f"jump-{direction}-{button}": move | button_wire
    for direction, move, _ in RL_POLICY_JUMP_DIRECTIONS
    for button, button_wire, _ in RL_POLICY_BUTTONS
}
JUMP_NORMAL_ACTION_SEQUENCES = {
    action: (
        move,
        move,
        wire,
        wire,
        RL_MOVE_NEUTRAL,
        RL_MOVE_NEUTRAL,
    )
    for action, wire in JUMP_NORMAL_ACTION_WIRES.items()
    for direction, move, _action_id in RL_POLICY_JUMP_DIRECTIONS
    if action.startswith(f"jump-{direction}-")
}
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
    "ryu-fireball",
    "throw",
    "tatsu",
    *TATSU_ACTION_NAMES,
    "shoryuken",
    *SHORYUKEN_ACTION_NAMES,
    *JUMP_NORMAL_ACTION_NAMES,
)
MODEL_POLICY_CHOICES = (
    "tabular",
    "dqn",
)
POLICY_CHOICES = SCRIPTED_POLICY_CHOICES + MODEL_POLICY_CHOICES
GUARD_MACRO_DECISION_STEPS = 6

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
    *JUMP_NORMAL_ACTION_NAMES,
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
TABULAR_ACTION_WIRES.update({f"stand-{name}": wire for name, wire, _ in RL_POLICY_BUTTONS})
TABULAR_ACTION_WIRES.update({f"crouch-{name}": RL_MOVE_DOWN | wire for name, wire, _ in RL_POLICY_BUTTONS})
TABULAR_ACTION_NAMES_BY_WIRE = {
    wire: name for name, wire in TABULAR_ACTION_WIRES.items() if name != "neutral"
}
TABULAR_ACTION_NAMES_BY_WIRE[RL_MOVE_FORWARD | BTN_LP] = "fireball"
TABULAR_ACTION_NAMES_BY_WIRE.update({wire: action for action, wire in JUMP_NORMAL_ACTION_WIRES.items()})
TABULAR_ACTION_NAMES_BY_WIRE.update({RL_MOVE_DOWN_FORWARD | wire: action for action, wire, _ in SHORYUKEN_ACTIONS})
TABULAR_ACTION_NAMES_BY_WIRE.update({RL_MOVE_BACK | wire: action for action, wire, _ in TATSU_ACTIONS})
TABULAR_DEFAULT_ACTIONS = TABULAR_ACTION_NAMES

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
    {
        f"jump-{direction}-{name}": (action_id, sub_action)
        for direction, _, action_id in RL_POLICY_JUMP_DIRECTIONS
        for name, _, sub_action in RL_POLICY_BUTTONS
    }
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
    (RL_POLICY_ACTION_RYU_FIREBALL, RL_POLICY_SUB_LP): "fireball",
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
}
TABULAR_ACTION_NAMES_BY_POLICY_META.update(
    {(RL_POLICY_ACTION_STAND_NORMAL, sub_action): f"stand-{name}" for name, _, sub_action in RL_POLICY_BUTTONS}
)
TABULAR_ACTION_NAMES_BY_POLICY_META.update(
    {(RL_POLICY_ACTION_CROUCH_NORMAL, sub_action): f"crouch-{name}" for name, _, sub_action in RL_POLICY_BUTTONS}
)
TABULAR_ACTION_NAMES_BY_POLICY_META.update(
    {
        (action_id, sub_action): f"jump-{direction}-{name}"
        for direction, _, action_id in RL_POLICY_JUMP_DIRECTIONS
        for name, _, sub_action in RL_POLICY_BUTTONS
    }
)

DQN_FEATURE_NAMES = (
    "obs_abs_dx",
    "obs_abs_dy",
    "obs_self_front_edge_dist",
    "obs_self_back_edge_dist",
    "obs_opp_front_edge_dist",
    "obs_opp_back_edge_dist",
    "obs_opp_in_front",
    "obs_opp_routine_attack_state",
)
DQN_FEATURE_SCALES = {
    "obs_abs_dx": 384.0,
    "obs_abs_dy": 192.0,
    "obs_self_front_edge_dist": 384.0,
    "obs_self_back_edge_dist": 384.0,
    "obs_opp_front_edge_dist": 384.0,
    "obs_opp_back_edge_dist": 384.0,
    "obs_opp_in_front": 1.0,
    "obs_opp_routine_attack_state": 1.0,
}


@dataclass(frozen=True)
class ActorModel:
    version: int
    policy: str
    source: str
    q_table: dict[str, dict[str, float]] = field(default_factory=dict)
    q_counts: dict[str, dict[str, int]] = field(default_factory=dict)
    dqn_model: dict[str, object] = field(default_factory=dict)
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
        name = str(item)
        if name in TABULAR_ACTION_NAMES and name not in actions:
            actions.append(name)
    return tuple(actions) or TABULAR_DEFAULT_ACTIONS


def parse_action_names(value: str, *, option_name: str = "--actions") -> tuple[str, ...]:
    if not value.strip():
        return TABULAR_DEFAULT_ACTIONS
    actions: list[str] = []
    invalid: list[str] = []
    for raw_item in value.split(","):
        action = raw_item.strip()
        if not action:
            continue
        if action not in TABULAR_ACTION_NAMES:
            invalid.append(action)
            continue
        if action not in actions:
            actions.append(action)
    if invalid:
        raise SystemExit(f"Unknown action(s) for {option_name}: {','.join(invalid)}")
    if not actions:
        raise SystemExit(f"{option_name} did not include any actions")
    return tuple(actions)


def canonical_tabular_action_name(policy: str) -> str | None:
    if policy in TABULAR_ACTION_NAMES:
        return policy
    return {
        "guard": "guard-stand",
        "hp": "stand-hp",
        "ryu-fireball": "fireball",
        "shoryuken": "shoryuken-hp",
        "tatsu": "tatsu-lk",
    }.get(policy)


def _coerce_q_table(value: object) -> dict[str, dict[str, float]]:
    if not isinstance(value, dict):
        return {}
    q_table: dict[str, dict[str, float]] = {}
    for state_key, scores in value.items():
        if not isinstance(scores, dict):
            continue
        clean_scores: dict[str, float] = {}
        for action_name, score in scores.items():
            action = str(action_name)
            if action not in TABULAR_ACTION_NAMES:
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
            action = str(action_name)
            if action not in TABULAR_ACTION_NAMES:
                continue
            try:
                clean_counts[action] = max(0, int(count))
            except (TypeError, ValueError):
                continue
        if clean_counts:
            q_counts[str(state_key)] = clean_counts
    return q_counts


def _coerce_dqn_model(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}

    raw_feature_names = value.get("feature_names")
    if isinstance(raw_feature_names, list):
        feature_names = tuple(str(name) for name in raw_feature_names if str(name) in DQN_FEATURE_SCALES)
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
        q_table = _coerce_q_table(data.get("q"))
        q_counts = _coerce_q_counts(data.get("q_counts"))
        dqn_model = _coerce_dqn_model(data.get("dqn"))
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
                    q_table=q_table,
                    q_counts=q_counts,
                    dqn_model=dqn_model,
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
        version_path = os.path.join(self._model_dir, f"actor-v{version}.json")
        try:
            with open(version_path, "r", encoding="utf-8") as stream:
                data = json.load(stream)
        except (OSError, json.JSONDecodeError):
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
                    q_table=q_table or {},
                    q_counts=q_counts or {},
                    dqn_model=dqn_model or {},
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
                q_table=q_table or {},
                q_counts=q_counts or {},
                dqn_model=dqn_model or {},
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
            elif model.policy == "dqn":
                payload.update(
                    {
                        "actions": list(model.actions),
                        "epsilon": model.epsilon,
                        "fallback_policy": model.fallback_policy,
                        "dqn": model.dqn_model,
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
        obs_opp_in_front,
        obs_self_routine_attack_state,
        obs_opp_routine_attack_state,
        obs_self_contact_reaction_state,
        obs_opp_contact_reaction_state,
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
        "obs_opp_in_front": obs_opp_in_front,
        "obs_self_routine_attack_state": obs_self_routine_attack_state,
        "obs_opp_routine_attack_state": obs_opp_routine_attack_state,
        "obs_self_contact_reaction_state": obs_self_contact_reaction_state,
        "obs_opp_contact_reaction_state": obs_opp_contact_reaction_state,
    }


def tabular_action_name(action_wire: int) -> str | None:
    return TABULAR_ACTION_NAMES_BY_WIRE.get(action_wire & 0xFFFF)


def transition_action_name(row: dict[str, object]) -> str | None:
    try:
        action_id = int(row.get("executed_policy_action_id", 0) or 0)
        sub_action_id = int(row.get("executed_policy_sub_action_id", 0) or 0)
    except (TypeError, ValueError):
        action_id = 0
        sub_action_id = 0
    action_name = TABULAR_ACTION_NAMES_BY_POLICY_META.get((action_id, sub_action_id))
    if action_name is not None:
        return action_name
    try:
        action_wire = int(row.get("executed_action_wire", 0) or 0)
    except (TypeError, ValueError):
        action_wire = 0
    return tabular_action_name(action_wire)


def tabular_training_reward(row: dict[str, object]) -> float:
    return float(int(row.get("delta_opp_hp", 0) or 0) - int(row.get("delta_self_hp", 0) or 0))


def dqn_feature_vector(
    row: dict[str, object],
    feature_names: tuple[str, ...] | list[str] = DQN_FEATURE_NAMES,
    feature_scales: dict[str, float] | None = None,
) -> list[float]:
    scales = feature_scales or DQN_FEATURE_SCALES
    features: list[float] = []
    for name in feature_names:
        try:
            value = float(row.get(str(name), 0.0) or 0.0)
        except (TypeError, ValueError):
            value = 0.0
        scale = max(1e-6, float(scales.get(str(name), 1.0) or 1.0))
        normalized = value / scale
        features.append(max(-4.0, min(4.0, normalized)))
    return features


def dqn_predict_values(dqn_model: dict[str, object], row: dict[str, object]) -> list[float]:
    feature_names = dqn_model.get("feature_names", list(DQN_FEATURE_NAMES))
    if not isinstance(feature_names, list):
        feature_names = list(DQN_FEATURE_NAMES)
    feature_scales = dqn_model.get("feature_scales", dict(DQN_FEATURE_SCALES))
    if not isinstance(feature_scales, dict):
        feature_scales = dict(DQN_FEATURE_SCALES)
    activations = dqn_feature_vector(row, feature_names, feature_scales)  # type: ignore[arg-type]
    layers = dqn_model.get("layers")
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
        action_name = transition_action_name(row)
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
    return {
        "run_id": int(row.get("run_id", 0) or 0),
        "episode_id": int(row.get("episode_id", 0) or 0),
        "decision_id": int(row.get("decision_id", 0) or 0),
        "round_num": int(row.get("round_num", 0) or 0),
        "obs_frame": int(row.get("obs_frame", 0) or 0),
        "agent_character_id": int(row.get("agent_character_id", 0) or 0),
        "opponent_character_id": int(row.get("opponent_character_id", 0) or 0),
        "requested_action_wire": int(row.get("requested_action_wire", 0) or 0),
        "requested_policy_action_id": int(row.get("requested_policy_action_id", 0) or 0),
        "requested_policy_sub_action_id": int(row.get("requested_policy_sub_action_id", 0) or 0),
        "requested_policy_action_step": int(row.get("requested_policy_action_step", 0) or 0),
        "executed_action_wire": int(row.get("executed_action_wire", 0) or 0),
        "executed_policy_action_id": int(row.get("executed_policy_action_id", 0) or 0),
        "executed_policy_sub_action_id": int(row.get("executed_policy_sub_action_id", 0) or 0),
        "executed_policy_action_step": int(row.get("executed_policy_action_step", 0) or 0),
        "demo_attributed_policy_action_id": int(row.get("demo_attributed_policy_action_id", 0) or 0),
        "demo_attributed_policy_sub_action_id": int(row.get("demo_attributed_policy_sub_action_id", 0) or 0),
        "demo_attributed_routine2": int(row.get("demo_attributed_routine2", 0) or 0),
        "demo_attributed_kind_of_waza": int(row.get("demo_attributed_kind_of_waza", 0) or 0),
        "demo_attributed_current_attack": int(row.get("demo_attributed_current_attack", 0) or 0),
        "demo_attribution_source": int(row.get("demo_attribution_source", 0) or 0),
        "demo_attribution_lag_frames": int(row.get("demo_attribution_lag_frames", 0) or 0),
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
    def __init__(self, host: str, port: int, transition_log: str) -> None:
        super().__init__(daemon=True)
        self._host = host
        self._port = port
        self._transition_log = transition_log
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

    def _append_payload(self, payload: bytes) -> None:
        os.makedirs(os.path.dirname(self._transition_log) or ".", exist_ok=True)
        with self._write_lock, open(self._transition_log, "ab") as stream:
            stream.write(payload)

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
                    self._append_payload(payload)
                    ack = TRANSITION_BATCH_ACK.pack(MAGIC, PROTOCOL_VERSION, 7, nonce, run_id, episode_id, 0)
                    conn.sendall(ack)
                    print(
                        f"TRANSITIONS batch run={run_id} ep={episode_id} rows={row_count} bytes={payload_len} from={addr[0]}:{addr[1]}",
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

        replay_row = learner_replay_row(row)
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


def scripted_sequence(policy: str) -> tuple[int, ...] | None:
    jump_sequence = JUMP_NORMAL_ACTION_SEQUENCES.get(policy)
    if jump_sequence is not None:
        return jump_sequence

    scripts = {
        "guard": (RL_MOVE_BACK,) * GUARD_MACRO_DECISION_STEPS,
        "guard-stand": (RL_MOVE_BACK,) * GUARD_MACRO_DECISION_STEPS,
        "guard-crouch": (RL_MOVE_DOWN_BACK,) * GUARD_MACRO_DECISION_STEPS,
        "fireball": (
            RL_MOVE_DOWN_BACK,
            RL_MOVE_DOWN,
            RL_MOVE_DOWN_FORWARD,
            RL_MOVE_FORWARD | BTN_LP,
            RL_MOVE_NEUTRAL,
            RL_MOVE_NEUTRAL,
        ),
        "fireball-mp": (
            RL_MOVE_DOWN_BACK,
            RL_MOVE_DOWN,
            RL_MOVE_DOWN_FORWARD,
            RL_MOVE_FORWARD | BTN_MP,
            RL_MOVE_NEUTRAL,
            RL_MOVE_NEUTRAL,
        ),
        "fireball-hp": (
            RL_MOVE_DOWN_BACK,
            RL_MOVE_DOWN,
            RL_MOVE_DOWN_FORWARD,
            RL_MOVE_FORWARD | BTN_HP,
            RL_MOVE_NEUTRAL,
            RL_MOVE_NEUTRAL,
        ),
        "ryu-fireball": (
            RL_MOVE_DOWN_BACK,
            RL_MOVE_DOWN,
            RL_MOVE_DOWN_FORWARD,
            RL_MOVE_FORWARD | BTN_LP,
            RL_MOVE_NEUTRAL,
            RL_MOVE_NEUTRAL,
        ),
        "throw": (
            RL_MOVE_FORWARD | BTN_LP | BTN_LK,
            RL_MOVE_NEUTRAL,
            RL_MOVE_NEUTRAL,
            RL_MOVE_NEUTRAL,
        ),
        "jump-forward-mk": (
            RL_MOVE_UP_FORWARD,
            RL_MOVE_UP_FORWARD,
            RL_MOVE_UP_FORWARD | BTN_MK,
            RL_MOVE_UP_FORWARD | BTN_MK,
            RL_MOVE_NEUTRAL,
            RL_MOVE_NEUTRAL,
        ),
        "jump-forward-hk": (
            RL_MOVE_UP_FORWARD,
            RL_MOVE_UP_FORWARD,
            RL_MOVE_UP_FORWARD | BTN_HK,
            RL_MOVE_UP_FORWARD | BTN_HK,
            RL_MOVE_NEUTRAL,
            RL_MOVE_NEUTRAL,
        ),
        "jump-neutral-hk": (
            RL_MOVE_UP,
            RL_MOVE_UP,
            RL_MOVE_UP | BTN_HK,
            RL_MOVE_UP | BTN_HK,
            RL_MOVE_NEUTRAL,
            RL_MOVE_NEUTRAL,
        ),
        "jump-back-hk": (
            RL_MOVE_UP_BACK,
            RL_MOVE_UP_BACK,
            RL_MOVE_UP_BACK | BTN_HK,
            RL_MOVE_UP_BACK | BTN_HK,
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


def dqn_actor_action_name(actor: ActorModel, obs_row: dict[str, object] | None) -> str | None:
    if actor.policy != "dqn" or not obs_row or not actor.dqn_model:
        return None
    if random.random() < actor.epsilon:
        return random.choice(actor.actions)
    values = dqn_predict_values(actor.dqn_model, obs_row)
    if not values:
        return None
    scored_actions = [
        (action, float(values[index]))
        for index, action in enumerate(actor.actions)
        if index < len(values) and action in TABULAR_ACTION_NAMES
    ]
    if not scored_actions:
        return None
    return max(scored_actions, key=lambda item: (item[1], item[0]))[0]


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
) -> PolicyActionFrame:
    if actor.policy in MODEL_POLICY_CHOICES:
        macro_frame = active_macro_action_frame(macro_states, nonce, run_id, episode_id)
        if macro_frame is not None:
            return macro_frame
    action_name = None
    if actor.policy == "tabular":
        tabular_state = tabular_state_key_override if tabular_state_key_override else model_store.latest_tabular_state()
        action_name = tabular_actor_action_name(actor, tabular_state)
    elif actor.policy == "dqn":
        action_name = dqn_actor_action_name(actor, obs_row_override)
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
    ).action_wire


def serve(
    host: str,
    port: int,
    verbose: bool,
    action_port: int | None,
    action_mode: str,
    policy: str,
    obs_reply_mode: str,
    model_version: int,
    policy_repeat_delay_ms: int,
    transition_log: str | None,
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
        TransitionBatchServer(host, transition_server_port, transition_log).start()
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
    hello_count: dict[int, int] = {}
    policy_states: dict[tuple[int, int, int, str], dict[str, int]] = {}
    macro_states: dict[tuple[int, int, int], dict[str, int | str]] = {}

    while True:
        data, addr = sock.recvfrom(2048)
        if len(data) >= OBS_HEADER.size:
            inference_start_ns = time.perf_counter_ns()
            active_model = model_store.current()
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
                    print(
                        f"{target} OBS-ACTION policy={active_model.policy} reply={obs_reply_mode} "
                        f"run={run_id} ep={episode_id} dec={decision_id} obs={obs_frame} "
                        f"target={target_frame} hold={action_hold_frames}"
                        f" model_expected={model_version_expected} model={active_model.version}"
                        f" obs_payload={'yes' if obs_payload_valid else 'no'} state={tabular_state_source or 'n/a'}"
                        f" wire=0x{target_action.action_wire:04x}"
                        f" action={target_action.policy_action_id}/{target_action.policy_sub_action_id}"
                        f" step={target_action.policy_action_step}"
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

        if verbose:
            print(
                f"{addr} {packet_name(packet_type)} nonce={nonce} seq={sequence} "
                f"hash=0x{config_hash:08x}"
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
    parser.add_argument("--verbose", action="store_true", help="Log every valid packet")
    args = parser.parse_args()
    transition_log = args.transition_log
    if transition_log is None and (args.transition_pull_remote_path or args.transition_pull_local_source):
        transition_log = "/tmp/rl-transitions-pulled.ndjson"
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
    serve(
        args.host,
        args.port,
        args.verbose,
        args.action_port,
        args.action_mode,
        args.policy,
        args.obs_reply_mode,
        args.model_version,
        args.policy_repeat_delay_ms,
        transition_log,
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
    )


if __name__ == "__main__":
    main()
