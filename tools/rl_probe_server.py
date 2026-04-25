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
PROTOCOL_VERSION = 2
TYPE_HELLO = 1
TYPE_ACK = 2
TYPE_PING = 3
TYPE_PONG = 4
TYPE_OBS = 5
PACKET = struct.Struct("<IHHQIIQ")
ACTION_PACKET = struct.Struct("<IHHQQIIIHHI")
OBS_HEADER = struct.Struct("<IHHQQIIIIHHI")
TRANSITION_BATCH_HEADER = struct.Struct("<IHHQQIII")
TRANSITION_BATCH_ACK = struct.Struct("<IHHQQII")

RL_MOVE_NEUTRAL = 0x0000
RL_MOVE_DOWN = 0x0002
RL_MOVE_BACK = 0x0003
RL_MOVE_FORWARD = 0x0004
RL_MOVE_DOWN_BACK = 0x0007
RL_MOVE_DOWN_FORWARD = 0x0008

BTN_LP = 0x0010
BTN_HP = 0x0040
BTN_LK = 0x0100
POLICY_CHOICES = ("forward", "back", "hp", "forward-hp", "ryu-fireball", "throw", "tatsu", "shoryuken", "tabular")

TABULAR_ACTION_WIRES = {
    "neutral": RL_MOVE_NEUTRAL,
    "forward": RL_MOVE_FORWARD,
    "back": RL_MOVE_BACK,
    "hp": BTN_HP,
    "forward-hp": RL_MOVE_FORWARD | BTN_HP,
}
TABULAR_ACTION_NAMES_BY_WIRE = {wire: name for name, wire in TABULAR_ACTION_WIRES.items()}
TABULAR_DEFAULT_ACTIONS = ("forward", "back", "hp", "forward-hp")


@dataclass(frozen=True)
class ActorModel:
    version: int
    policy: str
    source: str
    q_table: dict[str, dict[str, float]] = field(default_factory=dict)
    q_counts: dict[str, dict[str, int]] = field(default_factory=dict)
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
        if name in TABULAR_ACTION_WIRES and name not in actions:
            actions.append(name)
    return tuple(actions) or TABULAR_DEFAULT_ACTIONS


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
            if action not in TABULAR_ACTION_WIRES:
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
            if action not in TABULAR_ACTION_WIRES:
                continue
            try:
                clean_counts[action] = max(0, int(count))
            except (TypeError, ValueError):
                continue
        if clean_counts:
            q_counts[str(state_key)] = clean_counts
    return q_counts


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
    def __init__(self, model_dir: str | None, initial_policy: str, initial_version: int) -> None:
        self._model_dir = model_dir
        self._current_path = os.path.join(model_dir, "current.json") if model_dir else None
        self._lock = threading.Lock()
        self._active = ActorModel(max(0, initial_version), initial_policy, "cli")
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
                self.publish(self._active.policy, source="bootstrap", version=self._active.version)
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
        source = str(data.get("source", "file") or "file")
        q_table = _coerce_q_table(data.get("q"))
        q_counts = _coerce_q_counts(data.get("q_counts"))
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
        self._lock = threading.Lock()

    def record(self, elapsed_ns: int) -> None:
        with self._lock:
            self._samples_ns.append(elapsed_ns)
            if len(self._samples_ns) > self._capacity:
                del self._samples_ns[: len(self._samples_ns) - self._capacity]

    def snapshot(self) -> dict[str, float | int]:
        with self._lock:
            samples_ns = sorted(self._samples_ns)
        if not samples_ns:
            return {"count": 0, "p50_us": 0.0, "p95_us": 0.0, "max_us": 0.0}
        p50_ns = samples_ns[len(samples_ns) // 2]
        p95_ns = samples_ns[min(len(samples_ns) - 1, int(len(samples_ns) * 0.95))]
        max_ns = samples_ns[-1]
        return {
            "count": len(samples_ns),
            "p50_us": p50_ns / 1000.0,
            "p95_us": p95_ns / 1000.0,
            "max_us": max_ns / 1000.0,
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
    return "|".join(
        (
            f"front={opp_in_front}",
            f"dx={bucket_range(abs_dx, (48, 144), ('close', 'mid', 'far'))}",
            f"dy={bucket_range(abs_dy, (16, 64), ('flat', 'offset', 'high'))}",
            f"self_front={bucket_range(self_front, (48, 160), ('corner', 'mid', 'open'))}",
            f"self_back={bucket_range(self_back, (48, 160), ('corner', 'mid', 'open'))}",
            f"opp_front={bucket_range(opp_front, (48, 160), ('corner', 'mid', 'open'))}",
            f"opp_back={bucket_range(opp_back, (48, 160), ('corner', 'mid', 'open'))}",
        )
    )


def tabular_action_name(action_wire: int) -> str | None:
    return TABULAR_ACTION_NAMES_BY_WIRE.get(action_wire & 0xFFFF)


def tabular_training_reward(row: dict[str, object]) -> float:
    return float(int(row.get("delta_opp_hp", 0) or 0) - int(row.get("delta_self_hp", 0) or 0))


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
        action_name = tabular_action_name(int(row.get("executed_action_wire", 0) or 0))
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
        "executed_action_wire": int(row.get("executed_action_wire", 0) or 0),
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
        "final_self_hp": int(row.get("final_self_hp", 0) or 0),
        "final_opp_hp": int(row.get("final_opp_hp", 0) or 0),
        "model_version_executed": int(row.get("model_version_executed", 0) or 0),
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
        self._tabular_learner = TabularPolicyLearner(tabular_alpha, tabular_epsilon, tabular_fallback_policy)
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
            f"model_exec={self._latest_model_version_executed} "
            f"model_active={model_status.active.version} "
            f"model_pub={model_status.last_published_version} "
            f"model_load={model_status.last_loaded_version} "
            f"model_counts={model_status.publish_count}/{model_status.load_count} "
            f"inf={inf['count']}:{inf['p50_us']:.1f}/{inf['p95_us']:.1f}/{inf['max_us']:.1f}us",
            flush=True,
        )
        if self._learner_auto_publish and learner_ready:
            now_ns = time.monotonic_ns()
            if now_ns >= self._next_publish_ns:
                active = self._model_store.current()
                policy = self._learner_publish_policy or active.policy
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
    action_wire: int,
    model_version: int,
) -> bytes:
    return ACTION_PACKET.pack(
        MAGIC,
        PROTOCOL_VERSION,
        0,
        nonce,
        run_id,
        episode_id,
        decision_id,
        target_frame,
        action_wire,
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

    payload = make_action_packet(send_nonce, 0, 1, sequence, sequence + 4, 0x0040, model_version)
    target = (addr[0], action_port)
    sock.sendto(payload, target)
    if verbose:
        print(f"{target} ACTION mode={action_mode} nonce={send_nonce} decision={sequence} model={model_version}")


def fixed_action_wire(policy: str) -> int | None:
    return {
        "forward": RL_MOVE_FORWARD,
        "back": RL_MOVE_BACK,
        "hp": BTN_HP,
        "forward-hp": RL_MOVE_FORWARD | BTN_HP,
    }.get(policy)


def scripted_sequence(policy: str) -> tuple[int, ...] | None:
    scripts = {
        "ryu-fireball": (
            RL_MOVE_DOWN,
            RL_MOVE_DOWN_FORWARD,
            RL_MOVE_FORWARD,
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
    }
    return scripts.get(policy)


def scripted_action_wire(
    policy: str,
    policy_states: dict[tuple[int, int, int, str], dict[str, int]],
    nonce: int,
    run_id: int,
    episode_id: int,
    repeat_delay_ms: int,
) -> int:
    key = (nonce, run_id, episode_id, policy)
    state = policy_states.setdefault(key, {"index": 0, "delay_until_ns": 0})
    now_ns = time.monotonic_ns()
    if state["delay_until_ns"] > now_ns:
        return RL_MOVE_NEUTRAL
    if state["delay_until_ns"] != 0:
        state["delay_until_ns"] = 0
        state["index"] = 0

    fixed = fixed_action_wire(policy)
    if fixed is not None:
        if repeat_delay_ms > 0:
            state["delay_until_ns"] = now_ns + (repeat_delay_ms * 1_000_000)
        return fixed

    sequence = scripted_sequence(policy)
    if sequence is None:
        return RL_MOVE_FORWARD

    index = state["index"]
    action_wire = sequence[index]
    index += 1
    if index >= len(sequence):
        index = 0
        if repeat_delay_ms > 0:
            state["delay_until_ns"] = now_ns + (repeat_delay_ms * 1_000_000)
    state["index"] = index
    return action_wire


def tabular_actor_action_wire(actor: ActorModel, state_key: str | None) -> int | None:
    if actor.policy != "tabular" or not state_key:
        return None
    if random.random() < actor.epsilon:
        return TABULAR_ACTION_WIRES[random.choice(actor.actions)]
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
    best_action = max(eligible_actions, key=lambda action: (float(scores.get(action, 0.0)), action))
    return TABULAR_ACTION_WIRES.get(best_action)


def policy_action_wire(
    actor: ActorModel,
    model_store: ActorModelStore,
    policy_states: dict[tuple[int, int, int, str], dict[str, int]],
    nonce: int,
    run_id: int,
    episode_id: int,
    repeat_delay_ms: int,
) -> int:
    tabular_wire = tabular_actor_action_wire(actor, model_store.latest_tabular_state())
    if tabular_wire is not None:
        return tabular_wire
    fallback_policy = actor.fallback_policy if actor.policy == "tabular" else actor.policy
    return scripted_action_wire(fallback_policy, policy_states, nonce, run_id, episode_id, repeat_delay_ms)


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
    tabular_min_action_count: int,
) -> None:
    inference_stats = InferenceStats()
    model_store = ActorModelStore(model_dir, policy, model_version)
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

    while True:
        data, addr = sock.recvfrom(2048)
        if len(data) == OBS_HEADER.size:
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
            ) = OBS_HEADER.unpack(data)
            if magic != MAGIC or version != PROTOCOL_VERSION or packet_type != TYPE_OBS:
                if verbose:
                    print(f"{addr} bad_obs_header magic=0x{magic:08x} version={version} type={packet_type}")
                continue
            if action_port is not None:
                target_wire = policy_action_wire(
                    active_model,
                    model_store,
                    policy_states,
                    nonce,
                    run_id,
                    episode_id,
                    policy_repeat_delay_ms,
                )
                payload = make_action_packet(
                    nonce,
                    run_id,
                    episode_id,
                    decision_id,
                    target_frame,
                    target_wire,
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
                        target_wire,
                        active_model.version,
                    )
                    sock.sendto(wrong_payload, target)
                if verbose:
                    print(
                        f"{target} OBS-ACTION policy={active_model.policy} reply={obs_reply_mode} "
                        f"run={run_id} ep={episode_id} dec={decision_id} obs={obs_frame} "
                        f"target={target_frame} hold={action_hold_frames}"
                        f" model_expected={model_version_expected} model={active_model.version}"
                        f" wire=0x{target_wire:04x}"
                    )
            inference_stats.record(time.perf_counter_ns() - inference_start_ns)
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
        choices=POLICY_CHOICES,
        default=None,
        help="Policy stamped into learner-published actor manifests; defaults to the currently active policy",
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
        "--tabular-fallback-policy",
        choices=POLICY_CHOICES[:-1],
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
        args.tabular_min_action_count,
    )


if __name__ == "__main__":
    main()
