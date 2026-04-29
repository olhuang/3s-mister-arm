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

import rl_probe_server as rl
from rl_probe_server import (
    TABULAR_ACTION_NAMES,
    TABULAR_ACTION_NAMES_BY_POLICY_META,
    bucket_range,
    tabular_training_reward,
)


DX_BUCKETS = ("close", "mid", "far")
DEFAULT_ACTIONS = TABULAR_ACTION_NAMES
RYU_CHARACTER_ID = 2
ROUTINE_UNKNOWN = -1

SELF_R1_FIELD_NAMES = (
    "obs_self_routine_1",
    "obs_self_routine1",
    "self_routine_1",
    "self_routine1",
    "obs_self_routine_no_1",
    "self_routine_no_1",
)
SELF_R2_FIELD_NAMES = (
    "obs_self_routine_2",
    "obs_self_routine2",
    "self_routine_2",
    "self_routine2",
    "obs_self_routine_no_2",
    "self_routine_no_2",
)
OPP_R1_FIELD_NAMES = (
    "obs_opp_routine_1",
    "obs_opp_routine1",
    "opp_routine_1",
    "opp_routine1",
    "obs_opp_routine_no_1",
    "opp_routine_no_1",
)
OPP_R2_FIELD_NAMES = (
    "obs_opp_routine_2",
    "obs_opp_routine2",
    "opp_routine_2",
    "opp_routine2",
    "obs_opp_routine_no_2",
    "opp_routine_no_2",
)

NORMAL_ROUTINE2_ACTIONS = {
    0: "appear",
    1: "stand",
    2: "turn-stand",
    3: "walk-forward",
    4: "walk-back",
    5: "dash-forward",
    6: "dash-back",
    7: "stand-up",
    8: "crouch-start",
    9: "crouch",
    10: "turn-crouch",
    11: "walk-forward-arcade",
    12: "walk-back-arcade",
    13: "walk-forward-alt",
    14: "walk-forward-alt",
    15: "walk-forward-alt",
    16: "jump-ready",
    17: "high-jump-ready",
    18: "jump-air",
    19: "jump-air",
    20: "jump-air",
    21: "jump-air",
    22: "jump-air",
    23: "jump-air",
    24: "jump-air",
    25: "jump-air",
    26: "jump-air",
    27: "guard-stand-provisional",
    28: "guard-stand-provisional",
    29: "guard-crouch-provisional",
    30: "guard-provisional",
    31: "guard-block-provisional",
    32: "guard-block-provisional",
    33: "guard-block-provisional",
}

RYU_ATTACK_ROUTINE2_ACTIONS = {
    2: "throw",
    14: "throw-catch-start",
    16: "hadouken",
    17: "shoryuken",
    18: "tatsumaki-senpukyaku",
    19: "shinkuu-hadouken",
    20: "shin-shoryuken",
    21: "denjin-hadouken",
    22: "air-tatsumaki-senpukyaku",
    23: "joudan-sokutou-geri",
}


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


@dataclass(frozen=True)
class EngineStateAction:
    side: str
    source: str
    routine1: int
    routine2: int
    action: str


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
            "For engine-attributed demo move starts, sum HP deltas over this many following decision rows "
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
    parser.add_argument(
        "--training-action-source",
        choices=rl.TRAINING_ACTION_SOURCES,
        default="auto",
        help=(
            "Canonical action label source for DIRECT/CREDITED tables. auto uses engine/input labels "
            "for schema-v3 demo rows and policy labels for schema-v3 remote rows."
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


def optional_int_field(row: dict[str, object], names: tuple[str, ...]) -> int | None:
    for name in names:
        if name not in row:
            continue
        try:
            return int(row.get(name, 0) or 0)
        except (TypeError, ValueError):
            return 0
    return None


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


def engine_state_action_name(routine1: int, routine2: int | None, character_id: int | None) -> str:
    if routine1 == 0:
        if routine2 is None:
            return "normal.r2-unknown"
        action = NORMAL_ROUTINE2_ACTIONS.get(routine2)
        if action is not None:
            return f"normal.{action}"
        return f"normal.r2-{routine2}"

    if routine1 == 1:
        if routine2 is None:
            return "damage-contact.r2-unknown"
        return f"damage-contact.r2-{routine2}"

    if routine1 == 2:
        if routine2 is None:
            return "catch.r2-unknown"
        return f"catch.r2-{routine2}"

    if routine1 == 3:
        if routine2 is None:
            return "caught.r2-unknown"
        return f"caught.r2-{routine2}"

    if routine1 == 4:
        if routine2 is None:
            return "attack.r2-unknown"
        if character_id == RYU_CHARACTER_ID:
            action = RYU_ATTACK_ROUTINE2_ACTIONS.get(routine2)
            if action is not None:
                return f"attack.ryu-{action}"
        if routine2 < 16:
            return f"attack.common-r2-{routine2}"
        return f"attack.char-extra-r2-{routine2}"

    return f"routine1-{routine1}.r2-{routine2 if routine2 is not None else 'unknown'}"


def engine_state_action_from_row(row: dict[str, object], side: str) -> EngineStateAction | None:
    if side == "self":
        r1_fields = SELF_R1_FIELD_NAMES
        r2_fields = SELF_R2_FIELD_NAMES
        attack_flag = "obs_self_routine_attack_state"
        contact_flag = "obs_self_contact_reaction_state"
        character_id = int_field(row, "agent_character_id")
    elif side == "opp":
        r1_fields = OPP_R1_FIELD_NAMES
        r2_fields = OPP_R2_FIELD_NAMES
        attack_flag = "obs_opp_routine_attack_state"
        contact_flag = "obs_opp_contact_reaction_state"
        character_id = int_field(row, "opponent_character_id")
    else:
        raise ValueError(f"unknown engine state side: {side}")

    routine1 = optional_int_field(row, r1_fields)
    routine2 = optional_int_field(row, r2_fields)
    source = "raw"
    if routine1 is None:
        if int_field(row, attack_flag):
            routine1 = 4
            source = "derived"
        elif int_field(row, contact_flag):
            routine1 = 1
            source = "derived"
        else:
            return None

    action = engine_state_action_name(routine1, routine2, character_id)
    return EngineStateAction(
        side=side,
        source=source,
        routine1=routine1,
        routine2=routine2 if routine2 is not None else ROUTINE_UNKNOWN,
        action=action,
    )


def demo_attribution_present(row: dict[str, object]) -> bool:
    return rl.demo_attribution_present(row)


def engine_attributed_action_name(row: dict[str, object]) -> str:
    return rl.engine_attributed_action_name(row) or "neutral"


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


def print_count_table(title: str, table: dict[tuple[str, ...], Stats], limit: int) -> None:
    print(f"\n{title}")
    if not table:
        print("  none")
        return
    ordered = sorted(
        table.items(),
        key=lambda item: (item[1].rows, abs(item[1].reward_sum)),
        reverse=True,
    )
    for index, (key, stats) in enumerate(ordered):
        if index >= limit:
            print(f"  ... {len(ordered) - limit} more")
            break
        print(format_stats(key, stats))


def format_counter(counter: collections.Counter[str], limit: int = 12) -> str:
    if not counter:
        return "none"
    return ",".join(f"{key}:{value}" for key, value in counter.most_common(limit))


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
            action = engine_attributed_action_name(row)
            bucket = dx_bucket(row)
            r2 = int_field(row, "engine_routine_2")
            kw = int_field(row, "engine_kind_of_waza")
            source = int_field(row, "engine_label_source")
            lag = int_field(row, "engine_lag_frames")
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

            input_action = rl.select_training_action(row, "input").name
            if input_action != action:
                mismatch_counts[(input_action or "none", action)] += 1

    print(
        f"\nDEMO_ATTRIBUTION_SUMMARY window_decisions={window_decisions} "
        f"stop_at_next_event={str(stop_at_next).lower()} events={event_rows}"
    )
    if event_rows == 0:
        print("  none")
        return
    print("  source_counts=" + ",".join(f"{source}:{count}" for source, count in sorted(source_counts.items())))
    print("  lag_frames=" + ",".join(f"{lag}:{count}" for lag, count in sorted(lag_counts.items())))
    print_demo_table("ENGINE_ATTRIBUTED_BY_ACTION_WINDOW", by_action, args.limit)
    print_demo_table("ENGINE_ATTRIBUTED_BY_ACTION_DX_WINDOW", by_action_dx, args.limit)
    print_demo_table("ENGINE_ATTRIBUTED_BY_R2_KW_WINDOW", by_r2_kw, args.limit)

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
    engine_state_by_side: dict[tuple[str, ...], Stats] = {}
    engine_state_by_side_dx: dict[tuple[str, ...], Stats] = {}
    engine_state_by_routine: dict[tuple[str, ...], Stats] = {}
    engine_state_source_counts: collections.Counter[tuple[str, str]] = collections.Counter()
    action_source_counts: collections.Counter[str] = collections.Counter()
    action_source_action_counts: dict[str, collections.Counter[str]] = collections.defaultdict(collections.Counter)
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
        try:
            replay_row = rl.learner_replay_row(row)
        except ValueError as exc:
            raise SystemExit(f"{path}:{row_index}: {exc}") from exc
        if replay_row is None:
            skipped_json += 1
            continue
        row = replay_row

        rows.append(row)
        parsed_rows += 1
        key = episode_key(row)
        if first_key is None:
            first_key = key
        last_key = key

        action_selection = rl.select_training_action(row, args.training_action_source)
        action = action_selection.name
        action_source_counts[action_selection.source] += 1
        if action is not None:
            action_source_action_counts[action_selection.source][action] += 1
        reward = tabular_training_reward(row)
        opp_hp = int_field(row, "delta_opp_hp")
        self_hp = int_field(row, "delta_self_hp")
        bucket = dx_bucket(row)
        done = bool(row.get("done", False))
        if done:
            done_rows += 1
        if reward != 0.0:
            reward_rows += 1

        for side in ("self", "opp"):
            engine_state = engine_state_action_from_row(row, side)
            if engine_state is None:
                continue
            engine_state_source_counts[(side, engine_state.source)] += 1
            routine2_text = "unknown" if engine_state.routine2 == ROUTINE_UNKNOWN else str(engine_state.routine2)
            add_stat(
                engine_state_by_side,
                (side, engine_state.action, f"src={engine_state.source}"),
                reward,
                opp_hp,
                self_hp,
                False,
                args.large_delta_threshold,
            )
            add_stat(
                engine_state_by_side_dx,
                (side, engine_state.action, f"dx={bucket}", f"src={engine_state.source}"),
                reward,
                opp_hp,
                self_hp,
                False,
                args.large_delta_threshold,
            )
            add_stat(
                engine_state_by_routine,
                (side, f"R1={engine_state.routine1}", f"R2={routine2_text}", engine_state.action),
                reward,
                opp_hp,
                self_hp,
                False,
                args.large_delta_threshold,
            )

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
    print(
        f"action_label_source training_action_source={args.training_action_source} "
        f"counts={format_counter(action_source_counts, len(action_source_counts) or 1)}"
    )
    if action_source_action_counts:
        for source in sorted(action_source_action_counts):
            print(f"  {source:<13} {format_counter(action_source_action_counts[source], args.limit)}")

    print_table("DIRECT_BY_ACTION", direct_by_action, args.limit)
    print_table("DIRECT_BY_ACTION_DX", direct_by_action_dx, args.limit)
    print_table("CREDITED_BY_ACTION", credited_by_action, args.limit)
    print_table("CREDITED_BY_ACTION_DECISION_DX", credited_by_action_dx, args.limit)
    print_table("DELAYED_CREDIT_DECISION_DX_TO_REWARD_DX", delayed_shift, args.limit)
    print(
        "\nENGINE_STATE_ACTION_SUMMARY "
        + " ".join(
            f"{side}_{source}={count}"
            for (side, source), count in sorted(engine_state_source_counts.items())
        )
    )
    if not engine_state_source_counts:
        print("  none")
    else:
        print_count_table("ENGINE_STATE_ACTION_BY_SIDE", engine_state_by_side, args.limit)
        print_count_table("ENGINE_STATE_ACTION_BY_SIDE_DX", engine_state_by_side_dx, args.limit)
        print_count_table("ENGINE_STATE_ACTION_BY_ROUTINE", engine_state_by_routine, args.limit)
    analyze_demo_attribution(rows, args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
