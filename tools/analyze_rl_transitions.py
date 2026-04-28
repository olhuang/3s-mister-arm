#!/usr/bin/env python3
"""Summarize RL transition rewards by action and spacing bucket."""

from __future__ import annotations

import argparse
import collections
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from rl_probe_server import (
    TABULAR_ACTION_NAMES_BY_POLICY_META,
    bucket_range,
    tabular_training_reward,
    transition_action_name,
)


DX_BUCKETS = ("close", "mid", "far")
DEFAULT_ACTIONS = (
    "forward",
    "back",
    "guard-stand",
    "guard-crouch",
    "stand-lp",
    "stand-mp",
    "stand-hp",
    "stand-lk",
    "stand-mk",
    "stand-hk",
    "forward-hp",
    "crouch-lk",
    "crouch-mk",
    "crouch-hk",
    "fireball",
    "throw",
    "jump-forward-mk",
    "jump-forward-hk",
    "jump-neutral-hk",
    "jump-back-hk",
    "shoryuken-mp",
    "tatsu-mk",
)


@dataclass
class Stats:
    rows: int = 0
    reward_sum: float = 0.0
    opp_hp_sum: int = 0
    self_hp_sum: int = 0
    positive: int = 0
    negative: int = 0
    zero: int = 0
    delayed: int = 0
    large_delta_rows: int = 0
    large_delta_reward_sum: float = 0.0

    def add(self, reward: float, opp_hp: int, self_hp: int, delayed: bool, large_delta_threshold: int) -> None:
        self.rows += 1
        self.reward_sum += reward
        self.opp_hp_sum += opp_hp
        self.self_hp_sum += self_hp
        if reward > 0.0:
            self.positive += 1
        elif reward < 0.0:
            self.negative += 1
        else:
            self.zero += 1
        if delayed:
            self.delayed += 1
        if max(abs(opp_hp), abs(self_hp)) >= large_delta_threshold:
            self.large_delta_rows += 1
            self.large_delta_reward_sum += reward

    @property
    def mean_reward(self) -> float:
        return self.reward_sum / self.rows if self.rows else 0.0


@dataclass(frozen=True)
class ExplicitAction:
    action: str
    dx_bucket: str
    row_index: int


@dataclass
class DemoAttributionStats:
    events: int = 0
    hit_events: int = 0
    punished_events: int = 0
    trade_events: int = 0
    whiff_events: int = 0
    opp_hp_sum: int = 0
    self_hp_sum: int = 0
    lag_sum: int = 0
    lag_max: int = 0
    window_rows_sum: int = 0

    def add(self, opp_hp: int, self_hp: int, lag_frames: int, window_rows: int) -> None:
        self.events += 1
        self.opp_hp_sum += opp_hp
        self.self_hp_sum += self_hp
        self.lag_sum += lag_frames
        self.lag_max = max(self.lag_max, lag_frames)
        self.window_rows_sum += window_rows
        if opp_hp > 0:
            self.hit_events += 1
        if self_hp > 0:
            self.punished_events += 1
        if opp_hp > 0 and self_hp > 0:
            self.trade_events += 1
        if opp_hp <= 0 and self_hp <= 0:
            self.whiff_events += 1

    @property
    def hit_rate(self) -> float:
        return self.hit_events / self.events if self.events else 0.0

    @property
    def punished_rate(self) -> float:
        return self.punished_events / self.events if self.events else 0.0

    @property
    def whiff_rate(self) -> float:
        return self.whiff_events / self.events if self.events else 0.0

    @property
    def mean_lag(self) -> float:
        return self.lag_sum / self.events if self.events else 0.0

    @property
    def mean_window_rows(self) -> float:
        return self.window_rows_sum / self.events if self.events else 0.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Analyze transition NDJSON reward attribution by tabular action and dx bucket. "
            "The credited view assigns nonzero neutral/recovery HP-delta rows to the latest explicit action "
            "in the same episode."
        )
    )
    parser.add_argument("transition_log", help="Path to rl-transitions*.ndjson")
    parser.add_argument(
        "--actions",
        default=",".join(DEFAULT_ACTIONS),
        help="Comma-separated action names to include; default: %(default)s",
    )
    parser.add_argument(
        "--tail-rows",
        type=int,
        default=0,
        help="Analyze only the last N raw rows after reading the file; default analyzes the full file",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=40,
        help="Maximum rows to print per detailed table",
    )
    parser.add_argument(
        "--large-delta-threshold",
        type=int,
        default=64,
        help="Flag rows where either HP delta magnitude is at least this value",
    )
    parser.add_argument(
        "--demo-attribution-window-decisions",
        type=int,
        default=10,
        help=(
            "For demo_attributed move starts, sum HP deltas over this many following decision rows "
            "within the same episode; default: %(default)s"
        ),
    )
    parser.add_argument(
        "--demo-attribution-stop-at-next-event",
        action="store_true",
        help=(
            "Stop each demo-attribution window before the next attributed move event. "
            "Off by default because projectiles can hit after a later input."
        ),
    )
    return parser.parse_args()


def iter_lines(path: Path, tail_rows: int) -> Iterable[str]:
    if tail_rows > 0:
        lines: collections.deque[str] = collections.deque(maxlen=tail_rows)
        with path.open("r", encoding="utf-8") as stream:
            for line in stream:
                lines.append(line)
        yield from lines
        return
    with path.open("r", encoding="utf-8") as stream:
        yield from stream


def dx_bucket(row: dict[str, object]) -> str:
    return bucket_range(int(row.get("obs_abs_dx", 0) or 0), (48, 144), DX_BUCKETS)


def int_field(row: dict[str, object], name: str) -> int:
    return int(row.get(name, 0) or 0)


def episode_key(row: dict[str, object]) -> tuple[int, int]:
    return (int_field(row, "run_id"), int_field(row, "episode_id"))


def add_stat(
    table: dict[tuple[str, ...], Stats],
    key: tuple[str, ...],
    reward: float,
    opp_hp: int,
    self_hp: int,
    delayed: bool,
    large_delta_threshold: int,
) -> None:
    table.setdefault(key, Stats()).add(reward, opp_hp, self_hp, delayed, large_delta_threshold)


def format_stats(key: tuple[str, ...], stats: Stats) -> str:
    key_text = " ".join(key)
    return (
        f"{key_text:<36} rows={stats.rows:7d} reward={stats.reward_sum:9.1f} "
        f"mean={stats.mean_reward:7.3f} opp_hp={stats.opp_hp_sum:7d} self_hp={stats.self_hp_sum:7d} "
        f"+/-/0={stats.positive}/{stats.negative}/{stats.zero} delayed={stats.delayed:6d} "
        f"large={stats.large_delta_rows}:{stats.large_delta_reward_sum:.1f}"
    )


def policy_meta_name(action_id: int, sub_action_id: int) -> str:
    if action_id == 0 and sub_action_id == 0:
        return "neutral"
    action_name = TABULAR_ACTION_NAMES_BY_POLICY_META.get((action_id, sub_action_id))
    if action_name is not None:
        return action_name
    return f"policy:{action_id}/{sub_action_id}"


def demo_attribution_present(row: dict[str, object]) -> bool:
    return (
        int_field(row, "demo_attribution_source") != 0
        or int_field(row, "demo_attributed_policy_action_id") != 0
        or int_field(row, "demo_attributed_policy_sub_action_id") != 0
    )


def demo_attributed_action_name(row: dict[str, object]) -> str:
    return policy_meta_name(
        int_field(row, "demo_attributed_policy_action_id"),
        int_field(row, "demo_attributed_policy_sub_action_id"),
    )


def format_demo_stats(key: tuple[str, ...], stats: DemoAttributionStats) -> str:
    key_text = " ".join(key)
    return (
        f"{key_text:<42} events={stats.events:5d} "
        f"hit={stats.hit_events:5d}/{stats.hit_rate:5.1%} "
        f"punished={stats.punished_events:5d}/{stats.punished_rate:5.1%} "
        f"trade={stats.trade_events:4d} whiff={stats.whiff_events:5d}/{stats.whiff_rate:5.1%} "
        f"opp_hp={stats.opp_hp_sum:6d} self_hp={stats.self_hp_sum:6d} "
        f"lag_avg/max={stats.mean_lag:4.1f}/{stats.lag_max} "
        f"win_rows_avg={stats.mean_window_rows:4.1f}"
    )


def print_demo_table(title: str, table: dict[tuple[str, ...], DemoAttributionStats], limit: int) -> None:
    print(f"\n{title}")
    if not table:
        print("  none")
        return
    ordered = sorted(
        table.items(),
        key=lambda item: (item[1].events, item[1].opp_hp_sum + item[1].self_hp_sum),
        reverse=True,
    )
    for index, (key, stats) in enumerate(ordered):
        if index >= limit:
            print(f"  ... {len(ordered) - limit} more")
            break
        print(format_demo_stats(key, stats))


def print_table(title: str, table: dict[tuple[str, ...], Stats], limit: int) -> None:
    print(f"\n{title}")
    if not table:
        print("  none")
        return
    ordered = sorted(
        table.items(),
        key=lambda item: (abs(item[1].reward_sum), item[1].rows),
        reverse=True,
    )
    for index, (key, stats) in enumerate(ordered):
        if index >= limit:
            print(f"  ... {len(ordered) - limit} more")
            break
        print(format_stats(key, stats))


def analyze_demo_attribution(rows: list[dict[str, object]], args: argparse.Namespace) -> None:
    window_decisions = max(0, int(args.demo_attribution_window_decisions))
    stop_at_next = bool(args.demo_attribution_stop_at_next_event)
    by_episode: dict[tuple[int, int], list[dict[str, object]]] = collections.defaultdict(list)
    source_counts: collections.Counter[int] = collections.Counter()
    lag_counts: collections.Counter[int] = collections.Counter()
    mismatch_counts: collections.Counter[tuple[str, str]] = collections.Counter()
    event_rows = 0

    by_action: dict[tuple[str, ...], DemoAttributionStats] = {}
    by_action_dx: dict[tuple[str, ...], DemoAttributionStats] = {}
    by_r2_kw: dict[tuple[str, ...], DemoAttributionStats] = {}

    for row in rows:
        by_episode[episode_key(row)].append(row)

    for episode_rows in by_episode.values():
        for index, row in enumerate(episode_rows):
            if not demo_attribution_present(row):
                continue

            event_rows += 1
            action = demo_attributed_action_name(row)
            bucket = dx_bucket(row)
            r2 = int_field(row, "demo_attributed_routine2")
            kw = int_field(row, "demo_attributed_kind_of_waza")
            source = int_field(row, "demo_attribution_source")
            lag = int_field(row, "demo_attribution_lag_frames")
            source_counts[source] += 1
            lag_counts[lag] += 1

            end = min(len(episode_rows), index + window_decisions + 1)
            if stop_at_next:
                for next_index in range(index + 1, end):
                    if demo_attribution_present(episode_rows[next_index]):
                        end = next_index
                        break
            window = episode_rows[index:end]
            opp_hp = sum(int_field(window_row, "delta_opp_hp") for window_row in window)
            self_hp = sum(int_field(window_row, "delta_self_hp") for window_row in window)
            window_rows = len(window)

            for table, key in (
                (by_action, (action,)),
                (by_action_dx, (action, f"dx={bucket}")),
                (by_r2_kw, (f"R2={r2}", f"KW=0x{kw:02X}", action)),
            ):
                table.setdefault(key, DemoAttributionStats()).add(opp_hp, self_hp, lag, window_rows)

            input_action = transition_action_name(row)
            if input_action is None:
                input_action = policy_meta_name(
                    int_field(row, "executed_policy_action_id"),
                    int_field(row, "executed_policy_sub_action_id"),
                )
            if input_action != action:
                mismatch_counts[(input_action, action)] += 1

    print(
        f"\nDEMO_ATTRIBUTION_SUMMARY window_decisions={window_decisions} "
        f"stop_at_next_event={str(stop_at_next).lower()} events={event_rows}"
    )
    if event_rows == 0:
        print("  none")
        return
    print("  source_counts=" + ",".join(f"{source}:{count}" for source, count in sorted(source_counts.items())))
    print("  lag_frames=" + ",".join(f"{lag}:{count}" for lag, count in sorted(lag_counts.items())))
    print_demo_table("DEMO_ATTRIBUTED_BY_ACTION_WINDOW", by_action, args.limit)
    print_demo_table("DEMO_ATTRIBUTED_BY_ACTION_DX_WINDOW", by_action_dx, args.limit)
    print_demo_table("DEMO_ATTRIBUTED_BY_R2_KW_WINDOW", by_r2_kw, args.limit)

    print("\nDEMO_ATTRIBUTION_INPUT_TO_ENGINE_MISMATCH")
    if not mismatch_counts:
        print("  none")
    else:
        for index, ((input_action, engine_action), count) in enumerate(mismatch_counts.most_common(args.limit)):
            if index >= args.limit:
                print(f"  ... {len(mismatch_counts) - args.limit} more")
                break
            print(f"{input_action:<24} -> {engine_action:<24} rows={count:5d}")


def main() -> int:
    args = parse_args()
    path = Path(args.transition_log)
    actions = tuple(action.strip() for action in args.actions.split(",") if action.strip())
    action_set = set(actions)

    if not path.exists():
        print(f"error: transition log not found: {path}", file=sys.stderr)
        return 2

    parsed_rows = 0
    skipped_json = 0
    explicit_rows = 0
    reward_rows = 0
    delayed_credit_rows = 0
    uncredited_reward_rows = 0
    done_rows = 0
    first_key: tuple[int, int] | None = None
    last_key: tuple[int, int] | None = None
    last_explicit_by_episode: dict[tuple[int, int], ExplicitAction] = {}

    direct_by_action: dict[tuple[str, ...], Stats] = {}
    direct_by_action_dx: dict[tuple[str, ...], Stats] = {}
    credited_by_action: dict[tuple[str, ...], Stats] = {}
    credited_by_action_dx: dict[tuple[str, ...], Stats] = {}
    delayed_shift: dict[tuple[str, ...], Stats] = {}
    rows: list[dict[str, object]] = []

    for row_index, line in enumerate(iter_lines(path, max(0, args.tail_rows)), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            skipped_json += 1
            continue
        if not isinstance(row, dict):
            skipped_json += 1
            continue

        rows.append(row)
        parsed_rows += 1
        key = episode_key(row)
        if first_key is None:
            first_key = key
        last_key = key

        action = transition_action_name(row)
        reward = tabular_training_reward(row)
        opp_hp = int_field(row, "delta_opp_hp")
        self_hp = int_field(row, "delta_self_hp")
        bucket = dx_bucket(row)
        done = bool(row.get("done", False))
        if done:
            done_rows += 1
        if reward != 0.0:
            reward_rows += 1

        if action in action_set:
            explicit_rows += 1
            last_explicit_by_episode[key] = ExplicitAction(action, bucket, row_index)
            add_stat(direct_by_action, (action,), reward, opp_hp, self_hp, False, args.large_delta_threshold)
            add_stat(direct_by_action_dx, (action, f"dx={bucket}"), reward, opp_hp, self_hp, False, args.large_delta_threshold)
            add_stat(credited_by_action, (action,), reward, opp_hp, self_hp, False, args.large_delta_threshold)
            add_stat(
                credited_by_action_dx,
                (action, f"decision_dx={bucket}"),
                reward,
                opp_hp,
                self_hp,
                False,
                args.large_delta_threshold,
            )
        elif reward != 0.0:
            previous = last_explicit_by_episode.get(key)
            if previous is None:
                uncredited_reward_rows += 1
            elif previous.action in action_set:
                delayed_credit_rows += 1
                add_stat(
                    credited_by_action,
                    (previous.action,),
                    reward,
                    opp_hp,
                    self_hp,
                    True,
                    args.large_delta_threshold,
                )
                add_stat(
                    credited_by_action_dx,
                    (previous.action, f"decision_dx={previous.dx_bucket}"),
                    reward,
                    opp_hp,
                    self_hp,
                    True,
                    args.large_delta_threshold,
                )
                add_stat(
                    delayed_shift,
                    (previous.action, f"decision_dx={previous.dx_bucket}", f"reward_dx={bucket}"),
                    reward,
                    opp_hp,
                    self_hp,
                    True,
                    args.large_delta_threshold,
                )

        if done:
            last_explicit_by_episode.pop(key, None)

    print(f"file={path}")
    print(
        f"rows={parsed_rows} skipped_json={skipped_json} done={done_rows} "
        f"episodes={first_key}->{last_key} tail_rows={max(0, args.tail_rows)}"
    )
    print(
        f"explicit_rows={explicit_rows} reward_rows={reward_rows} delayed_credit_rows={delayed_credit_rows} "
        f"uncredited_reward_rows={uncredited_reward_rows} actions={','.join(actions)}"
    )

    print_table("DIRECT_BY_ACTION", direct_by_action, args.limit)
    print_table("DIRECT_BY_ACTION_DX", direct_by_action_dx, args.limit)
    print_table("CREDITED_BY_ACTION", credited_by_action, args.limit)
    print_table("CREDITED_BY_ACTION_DECISION_DX", credited_by_action_dx, args.limit)
    print_table("DELAYED_CREDIT_DECISION_DX_TO_REWARD_DX", delayed_shift, args.limit)
    analyze_demo_attribution(rows, args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
