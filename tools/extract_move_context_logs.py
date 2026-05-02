#!/usr/bin/env python3
"""Extract labeled move-context logs from a mixed transition log."""

from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path
from typing import NamedTuple

import rl_probe_server as rl


DX_BUCKETS = ("close", "mid", "far")


class SelectorRule(NamedTuple):
    buckets: frozenset[str] | None
    hit: bool | None
    punished: bool | None


def int_field(row: dict[str, object], name: str) -> int:
    return int(row.get(name, 0) or 0)


def dx_bucket(row: dict[str, object]) -> str:
    return rl.bucket_range(int_field(row, "obs_abs_dx"), (48, 144), DX_BUCKETS)


def episode_key(row: dict[str, object]) -> tuple[int, int]:
    return (int_field(row, "run_id"), int_field(row, "episode_id"))


def read_rows(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with path.open("r", encoding="utf-8") as stream:
        for line in stream:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def engine_action_name(row: dict[str, object]) -> str | None:
    return rl.engine_outcome_action_name(row)


def parse_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def parse_rule(text: str) -> SelectorRule:
    buckets: frozenset[str] | None = None
    hit: bool | None = None
    punished: bool | None = None
    for token in text.split():
        if "=" not in token:
            raise ValueError(f"rule token must be key=value: {token!r}")
        key, raw_value = token.split("=", 1)
        key = key.strip().lower()
        raw_value = raw_value.strip().lower()
        if key == "buckets":
            values = frozenset(parse_csv(raw_value))
            invalid = values - set(DX_BUCKETS)
            if invalid:
                raise ValueError(f"invalid buckets in rule {text!r}: {sorted(invalid)}")
            buckets = values
            continue
        if key in {"hit", "punished"}:
            if raw_value not in {"0", "1"}:
                raise ValueError(f"rule {key} must be 0 or 1 in {text!r}")
            bool_value = raw_value == "1"
            if key == "hit":
                hit = bool_value
            else:
                punished = bool_value
            continue
        raise ValueError(f"unknown rule key {key!r} in {text!r}")
    return SelectorRule(buckets=buckets, hit=hit, punished=punished)


def named_rules(selector: str) -> list[str]:
    if selector == "hit-good":
        return ["buckets=mid,far hit=1 punished=0"]
    if selector == "zoning-good":
        return ["buckets=far punished=0"]
    if selector == "good-combined":
        return ["buckets=mid,far hit=1 punished=0", "buckets=far punished=0"]
    if selector == "bad":
        return ["buckets=close", "punished=1"]
    raise ValueError(f"unknown selector preset: {selector}")


def build_rules(rule_texts: list[str]) -> list[SelectorRule]:
    return [parse_rule(text) for text in rule_texts]


def action_matches(
    row: dict[str, object],
    actions: frozenset[str],
    prefixes: tuple[str, ...],
) -> str | None:
    action = engine_action_name(row)
    if not action:
        return None
    if action in actions:
        return action
    if prefixes and any(action.startswith(prefix) for prefix in prefixes):
        return action
    return None


def outcome_for_event(
    episode_rows: list[tuple[int, dict[str, object]]],
    position: int,
    window_decisions: int,
) -> tuple[int, int, bool, bool]:
    window = episode_rows[position : position + window_decisions + 1]
    opp_hp = sum(int_field(row, "delta_opp_hp") for _, row in window)
    self_hp = sum(int_field(row, "delta_self_hp") for _, row in window)
    return opp_hp, self_hp, opp_hp > 0, self_hp > 0


def selector_matches(
    rules: list[SelectorRule],
    bucket: str,
    hit: bool,
    punished: bool,
) -> bool:
    for rule in rules:
        if rule.buckets is not None and bucket not in rule.buckets:
            continue
        if rule.hit is not None and hit != rule.hit:
            continue
        if rule.punished is not None and punished != rule.punished:
            continue
        return True
    return False


def collect_indices(
    rows: list[dict[str, object]],
    actions: frozenset[str],
    prefixes: tuple[str, ...],
    rules: list[SelectorRule],
    selector_label: str,
    window_decisions: int,
    context_before: int,
    context_after: int,
) -> tuple[set[int], list[dict[str, object]]]:
    by_episode: dict[tuple[int, int], list[tuple[int, dict[str, object]]]] = collections.defaultdict(list)
    for index, row in enumerate(rows):
        by_episode[episode_key(row)].append((index, row))

    selected_indices: set[int] = set()
    events: list[dict[str, object]] = []
    for episode_rows in by_episode.values():
        for position, (index, row) in enumerate(episode_rows):
            action = action_matches(row, actions, prefixes)
            if action is None:
                continue
            bucket = dx_bucket(row)
            opp_hp, self_hp, hit, punished = outcome_for_event(
                episode_rows,
                position,
                window_decisions,
            )
            if not selector_matches(rules, bucket, hit, punished):
                continue
            events.append(
                {
                    "index": index,
                    "action": action,
                    "bucket": bucket,
                    "episode": episode_key(row),
                    "opp_hp": opp_hp,
                    "self_hp": self_hp,
                    "hit": hit,
                    "punished": punished,
                    "selector": selector_label,
                }
            )
            start = max(0, position - context_before)
            stop = min(len(episode_rows), position + context_after + 1)
            for context_position in range(start, stop):
                selected_indices.add(episode_rows[context_position][0])
    return selected_indices, events


def summarize(
    rows: list[dict[str, object]],
    indices: set[int],
    events: list[dict[str, object]],
    selector: str,
) -> None:
    engine_counts: collections.Counter[str] = collections.Counter()
    dx_counts: collections.Counter[str] = collections.Counter()
    source_counts: collections.Counter[int] = collections.Counter()
    for index in sorted(indices):
        row = rows[index]
        action = engine_action_name(row)
        if action:
            engine_counts[action] += 1
        dx_counts[dx_bucket(row)] += 1
        source_counts[int_field(row, "execution_source")] += 1

    event_actions = collections.Counter(str(event["action"]) for event in events)
    event_buckets = collections.Counter(str(event["bucket"]) for event in events)
    print(
        f"selector={selector} events={len(events)} rows={len(indices)} "
        f"event_actions={dict(event_actions)} event_buckets={dict(event_buckets)}"
    )
    print(f"  row_dx={dict(dx_counts)} sources={dict(source_counts)}")
    print(f"  engine_rows={dict(engine_counts.most_common(12))}")


def write_rows(path: Path, rows: list[dict[str, object]], indices: set[int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        for index in sorted(indices):
            stream.write(json.dumps(rows[index], separators=(",", ":")))
            stream.write("\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_log", type=Path)
    parser.add_argument(
        "--actions",
        default="fireball-lp,fireball-mp,fireball-hp",
        help="Comma-separated exact engine action names to match",
    )
    parser.add_argument(
        "--action-prefixes",
        default="",
        help="Comma-separated engine action prefixes to match, e.g. fireball,shoryuken",
    )
    parser.add_argument(
        "--good-output",
        type=Path,
        default=Path("logs/rl-transitions-retrain-p3-fireball-good-extracted-v1.ndjson"),
    )
    parser.add_argument(
        "--bad-output",
        type=Path,
        default=Path("logs/rl-transitions-retrain-p3-fireball-bad-extracted-v1.ndjson"),
    )
    parser.add_argument(
        "--good-selector",
        choices=("hit-good", "zoning-good", "good-combined"),
        default="good-combined",
        help="Preset for --good-rules when no explicit good rules are provided",
    )
    parser.add_argument(
        "--good-rule",
        action="append",
        default=[],
        help="OR-combined good rule, e.g. 'buckets=mid,far hit=1 punished=0'",
    )
    parser.add_argument(
        "--bad-rule",
        action="append",
        default=[],
        help="OR-combined bad rule, e.g. 'buckets=close' or 'punished=1'",
    )
    parser.add_argument("--window-decisions", type=int, default=15)
    parser.add_argument("--context-before", type=int, default=6)
    parser.add_argument("--context-after", type=int, default=15)
    parser.add_argument(
        "--drop-overlap",
        action="store_true",
        help="Remove rows that appear in both extracted context windows before writing",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write extracted logs; default is dry-run only",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    actions = frozenset(parse_csv(args.actions))
    prefixes = tuple(parse_csv(args.action_prefixes))
    if not actions and not prefixes:
        raise SystemExit("at least one --actions or --action-prefixes value is required")
    good_rule_texts = args.good_rule or named_rules(args.good_selector)
    bad_rule_texts = args.bad_rule or named_rules("bad")
    good_rules = build_rules(good_rule_texts)
    bad_rules = build_rules(bad_rule_texts)

    rows = read_rows(args.source_log)
    good_indices, good_events = collect_indices(
        rows,
        actions,
        prefixes,
        good_rules,
        "good",
        max(0, args.window_decisions),
        max(0, args.context_before),
        max(0, args.context_after),
    )
    bad_indices, bad_events = collect_indices(
        rows,
        actions,
        prefixes,
        bad_rules,
        "bad",
        max(0, args.window_decisions),
        max(0, args.context_before),
        max(0, args.context_after),
    )

    print(
        f"source={args.source_log} rows={len(rows)} write={int(args.write)} "
        f"actions={sorted(actions)} prefixes={list(prefixes)}"
    )
    print(f"good_rules={good_rule_texts}")
    print(f"bad_rules={bad_rule_texts}")
    summarize(rows, good_indices, good_events, "good")
    summarize(rows, bad_indices, bad_events, "bad")

    overlap = good_indices & bad_indices
    if overlap:
        print(f"warning: good/bad context row overlap={len(overlap)}")
        if args.drop_overlap:
            good_indices -= overlap
            bad_indices -= overlap
            print(
                f"drop_overlap=1 good_rows={len(good_indices)} "
                f"bad_rows={len(bad_indices)}"
            )

    if args.write:
        write_rows(args.good_output, rows, good_indices)
        write_rows(args.bad_output, rows, bad_indices)
        print(f"wrote_good={args.good_output} rows={len(good_indices)}")
        print(f"wrote_bad={args.bad_output} rows={len(bad_indices)}")


if __name__ == "__main__":
    main()
