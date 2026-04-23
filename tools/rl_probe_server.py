#!/usr/bin/env python3
"""Minimal UDP server for Milestone 2/3 RL hello/ack, ping/pong, and remote-action probing."""

from __future__ import annotations

import argparse
import json
import os
import socket
import struct
import threading
import time


MAGIC = 0x33524C41
PACKET_VERSION = 1
TYPE_HELLO = 1
TYPE_ACK = 2
TYPE_PING = 3
TYPE_PONG = 4
TYPE_OBS = 5
PACKET = struct.Struct("<IHHQIIQ")
ACTION_PACKET = struct.Struct("<IHHQIIIHHI")
OBS_HEADER = struct.Struct("<IHHQIIIIHHI")

RL_MOVE_NEUTRAL = 0x0000
RL_MOVE_DOWN = 0x0002
RL_MOVE_BACK = 0x0003
RL_MOVE_FORWARD = 0x0004
RL_MOVE_DOWN_BACK = 0x0007
RL_MOVE_DOWN_FORWARD = 0x0008

BTN_LP = 0x0010
BTN_HP = 0x0040
BTN_LK = 0x0100


class InferenceStats:
    def __init__(self, capacity: int = 512) -> None:
        self._capacity = capacity
        self._samples_us: list[int] = []
        self._lock = threading.Lock()

    def record(self, elapsed_us: int) -> None:
        with self._lock:
            self._samples_us.append(elapsed_us)
            if len(self._samples_us) > self._capacity:
                del self._samples_us[: len(self._samples_us) - self._capacity]

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            samples = sorted(self._samples_us)
        if not samples:
            return {"count": 0, "p50_us": 0, "p95_us": 0, "max_us": 0}
        return {
            "count": len(samples),
            "p50_us": samples[len(samples) // 2],
            "p95_us": samples[min(len(samples) - 1, int(len(samples) * 0.95))],
            "max_us": samples[-1],
        }


class LearnerLogTailer(threading.Thread):
    def __init__(
        self,
        path: str,
        stats_interval_sec: float,
        tail_from_start: bool,
        inference_stats: InferenceStats,
    ) -> None:
        super().__init__(daemon=True)
        self._path = path
        self._stats_interval_sec = max(0.1, stats_interval_sec)
        self._tail_from_start = tail_from_start
        self._inference_stats = inference_stats
        self._rows = 0
        self._done = 0
        self._attack_events = 0
        self._attack_contacts = 0
        self._attack_whiffs = 0
        self._latest_episode = 0
        self._latest_model_version = 0

    def _consume_row(self, row: dict[str, object]) -> None:
        self._rows += 1
        self._latest_episode = int(row.get("episode_id", self._latest_episode) or 0)
        self._latest_model_version = int(row.get("model_version_executed", self._latest_model_version) or 0)
        if row.get("done") is True:
            self._done += 1
        if row.get("overlay_attack_event_finalized") == 1:
            self._attack_events += 1
            if row.get("overlay_attack_contact") == 1:
                self._attack_contacts += 1
            if row.get("overlay_attack_whiff") == 1:
                self._attack_whiffs += 1

    def _print_stats(self) -> None:
        inf = self._inference_stats.snapshot()
        print(
            "LEARNER "
            f"rows={self._rows} done={self._done} ep={self._latest_episode} "
            f"atk={self._attack_events}/{self._attack_contacts}/{self._attack_whiffs} "
            f"model={self._latest_model_version} "
            f"inf={inf['count']}:{inf['p50_us']}/{inf['p95_us']}/{inf['max_us']}us",
            flush=True,
        )

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
    episode_id: int,
    decision_id: int,
    target_frame: int,
    action_wire: int,
    model_version: int,
) -> bytes:
    return ACTION_PACKET.pack(
        MAGIC,
        PACKET_VERSION,
        0,
        nonce,
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

    payload = make_action_packet(send_nonce, 1, sequence, sequence + 4, 0x0040, model_version)
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
    policy_states: dict[tuple[int, int, str], dict[str, int]],
    nonce: int,
    episode_id: int,
    repeat_delay_ms: int,
) -> int:
    fixed = fixed_action_wire(policy)
    if fixed is not None:
        return fixed

    sequence = scripted_sequence(policy)
    if sequence is None:
        return RL_MOVE_FORWARD

    key = (nonce, episode_id, policy)
    state = policy_states.setdefault(key, {"index": 0, "delay_until_ns": 0})
    now_ns = time.monotonic_ns()
    if state["delay_until_ns"] > now_ns:
        return RL_MOVE_NEUTRAL
    if state["delay_until_ns"] != 0:
        state["delay_until_ns"] = 0
        state["index"] = 0

    index = state["index"]
    action_wire = sequence[index]
    index += 1
    if index >= len(sequence):
        index = 0
        if repeat_delay_ms > 0:
            state["delay_until_ns"] = now_ns + (repeat_delay_ms * 1_000_000)
    state["index"] = index
    return action_wire


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
) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((host, port))
    print(f"RL probe server listening on {host}:{port}")
    hello_count: dict[int, int] = {}
    policy_states: dict[tuple[int, int, str], dict[str, int]] = {}
    inference_stats = InferenceStats()
    if transition_log:
        LearnerLogTailer(
            transition_log,
            learner_stats_interval_sec,
            learner_tail_from_start,
            inference_stats,
        ).start()

    while True:
        data, addr = sock.recvfrom(2048)
        if len(data) == OBS_HEADER.size:
            inference_start_ns = time.monotonic_ns()
            (
                magic,
                version,
                packet_type,
                nonce,
                episode_id,
                decision_id,
                obs_frame,
                target_frame,
                obs_len,
                action_hold_frames,
                model_version_expected,
            ) = OBS_HEADER.unpack(data)
            if magic != MAGIC or version != PACKET_VERSION or packet_type != TYPE_OBS:
                if verbose:
                    print(f"{addr} bad_obs_header magic=0x{magic:08x} version={version} type={packet_type}")
                continue
            if action_port is not None:
                target_wire = scripted_action_wire(policy, policy_states, nonce, episode_id, policy_repeat_delay_ms)
                payload = make_action_packet(
                    nonce,
                    episode_id,
                    decision_id,
                    target_frame,
                    target_wire,
                    model_version,
                )
                target = (addr[0], action_port)
                sock.sendto(payload, target)
                if obs_reply_mode == "duplicate":
                    sock.sendto(payload, target)
                elif obs_reply_mode == "wrong-target":
                    wrong_payload = make_action_packet(
                        nonce,
                        episode_id,
                        decision_id,
                        target_frame + 1,
                        target_wire,
                        model_version,
                    )
                    sock.sendto(wrong_payload, target)
                if verbose:
                    print(
                        f"{target} OBS-ACTION policy={policy} reply={obs_reply_mode} "
                        f"ep={episode_id} dec={decision_id} obs={obs_frame} "
                        f"target={target_frame} hold={action_hold_frames}"
                        f" model_expected={model_version_expected} model={model_version}"
                        f" wire=0x{target_wire:04x}"
                    )
            inference_stats.record((time.monotonic_ns() - inference_start_ns) // 1000)
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
                maybe_send_action(sock, addr, action_port, "valid", nonce, sequence, model_version, verbose)
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
                maybe_send_action(sock, addr, action_port, action_mode, nonce, sequence, model_version, verbose)

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
        choices=["forward", "back", "hp", "forward-hp", "ryu-fireball", "throw", "tatsu", "shoryuken"],
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
    parser.add_argument("--verbose", action="store_true", help="Log every valid packet")
    args = parser.parse_args()
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
        args.transition_log,
        args.learner_stats_interval_sec,
        args.learner_tail_from_start,
    )


if __name__ == "__main__":
    main()
