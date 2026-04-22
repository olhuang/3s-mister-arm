#!/usr/bin/env python3
"""Minimal UDP server for Milestone 2/3 RL hello/ack, ping/pong, and remote-action probing."""

from __future__ import annotations

import argparse
import socket
import struct
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


def make_action_packet(nonce: int, episode_id: int, decision_id: int, target_frame: int, action_wire: int) -> bytes:
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
        0,
    )


def maybe_send_action(
    sock: socket.socket,
    addr: tuple[str, int],
    action_port: int | None,
    action_mode: str,
    nonce: int,
    sequence: int,
    verbose: bool,
) -> None:
    if action_port is None or action_mode == "off":
        return

    send_nonce = nonce
    if action_mode == "stale":
        send_nonce = (nonce - 1) & 0xFFFFFFFFFFFFFFFF

    payload = make_action_packet(send_nonce, 1, sequence, sequence + 4, 0x0040)
    target = (addr[0], action_port)
    sock.sendto(payload, target)
    if verbose:
        print(f"{target} ACTION mode={action_mode} nonce={send_nonce} decision={sequence}")


def fixed_action_wire(policy: str) -> int:
    return {
        "forward": 0x0004,
        "back": 0x0003,
        "hp": 0x0040,
        "forward-hp": 0x0044,
    }.get(policy, 0x0004)


def serve(
    host: str,
    port: int,
    verbose: bool,
    action_port: int | None,
    action_mode: str,
    policy: str,
) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((host, port))
    print(f"RL probe server listening on {host}:{port}")
    hello_count: dict[int, int] = {}

    while True:
        data, addr = sock.recvfrom(2048)
        if len(data) == OBS_HEADER.size:
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
                payload = make_action_packet(
                    nonce,
                    episode_id,
                    decision_id,
                    target_frame,
                    fixed_action_wire(policy),
                )
                target = (addr[0], action_port)
                sock.sendto(payload, target)
                if verbose:
                    print(
                        f"{target} OBS-ACTION policy={policy} ep={episode_id} dec={decision_id} "
                        f"obs={obs_frame} target={target_frame} hold={action_hold_frames}"
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
                maybe_send_action(sock, addr, action_port, "valid", nonce, sequence, verbose)
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
                maybe_send_action(sock, addr, action_port, action_mode, nonce, sequence, verbose)

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
        choices=["forward", "back", "hp", "forward-hp"],
        default="forward",
        help="Fixed action used when MiSTer sends Milestone 3 observation headers",
    )
    parser.add_argument("--verbose", action="store_true", help="Log every valid packet")
    args = parser.parse_args()
    serve(args.host, args.port, args.verbose, args.action_port, args.action_mode, args.policy)


if __name__ == "__main__":
    main()
