# Remote RL Agent Engineering Log

This log tracks implementation progress, engineering decisions, test results, and open issues for the remote RL agent work.

## 2026-05-07: Combat Event Phase 2 Duplicate Attack-Start Debounce

Milestone:
- Combat event attribution Phase 2 live refinement

Files changed:
- `src/rl/rl_session.c`
- `docs/plan-remote-rl-agent.md`
- `docs/agent-memory/remote-rl-combat-event-attribution-plan.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- Stop one physical attack, especially LP, from appearing as multiple
  attack-event starts/finalizations/whiffs in the Outcome overlay.

Implementation notes:
- Live testing showed one LP could make `CE/CER S/F/W` increase by `+2` or
  `+3`. The likely source is several start edges (`routine_started`,
  `current_attack_started`, `attack_counter_started`) arriving across adjacent
  frames for the same physical move.
- Added a small session-side debounce cache per side. If a new start arrives
  within six frames for the same run/episode/side and matches the previous
  current-attack, engine action/sub-action, or policy action/sub-action
  signature, the duplicate start is suppressed before it can finalize/restart
  the active attack event.
- Different action signatures can still supersede the active event. Very fast
  same-move chains inside the debounce window remain one logical event, which
  matches the accepted treatment for rapid LP chains when the engine does not
  expose distinct starts.

Validation:
- `git diff --check` passed.
- `python3 -m py_compile tools/analyze_rl_combat_events.py` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed and rebuilt
  `src/rl/rl_session.c`.
- Follow-up live MiSTer smoke should confirm one isolated LP increments
  `CE S/F` and `CER W` by one logical event instead of `+2` / `+3`, while a
  different immediate cancel still starts a new event.

## 2026-05-07: Combat Event Phase 6b-4 Weak Attack-Only Suppression

Milestone:
- Combat event attribution Phase 6b-4

Files changed:
- `src/rl/rl_combat_event.c`
- `docs/plan-remote-rl-agent.md`
- `docs/agent-memory/remote-rl-combat-event-attribution-plan.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- Fix the remaining `CDRX U` increase after hit-then-immediate-jump.

Implementation notes:
- The Phase 6b-3 airborne gate was not enough: live retest still showed
  `CDRX U`, which suggests the residual weak edge can fire during jump startup
  before the target is flagged airborne.
- Removed the target-state dependency from weak attack suppression. Any
  attack-sourced attribution with only `contact_state` / `hit_stop` and no
  strong HP/stun/damage/block/parry/throw/projectile-clash evidence is now
  suppressed before `CEM`, `CEA`, or `CDRX` counters increment.
- This treats weak-only attack contact as debug evidence, not a defense result.
  Strong hit/block/chip/parry/throw/clash paths still bypass the suppression.

Validation:
- `git diff --check` passed.
- `python3 -m py_compile tools/analyze_rl_combat_events.py` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed and rebuilt
  `src/rl/rl_combat_event.c`.
- Follow-up live MiSTer smoke should retest: normal hit still increments
  `CDR H` / derived hit, normal block still increments `CDR B` or `CDR C`,
  simultaneous whiffs still increment `CER W`, and hit-then-immediate-jump no
  longer adds `CDRX U`.

## 2026-05-07: Combat Event Phase 6b-3 Post-Hit Jump Weak-Edge Suppression

Milestone:
- Combat event attribution Phase 6b-3

Files changed:
- `src/rl/rl_combat_event.c`
- `docs/plan-remote-rl-agent.md`
- `docs/agent-memory/remote-rl-combat-event-attribution-plan.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- Stop clean hits followed by immediate jumps from adding extra raw
  `CDRX U` defense unknowns.

Implementation notes:
- Live testing showed that after being hit by a normal such as LP, immediately
  jumping could increment `CDRX U`. The real hit is already recorded by strong
  HP/stun/damage evidence; the later jump case is residual weak
  `contact_state` / `hit_stop` evidence with the target airborne.
- Broadened the Phase 6b-2 suppression gate from "target is attacking" to
  "target is attacking or airborne" for attack-sourced weak-only attribution.
- Strong outcome evidence still bypasses the gate, so real anti-air,
  air-to-air, block, parry, throw, and projectile-clash events remain recordable.

Validation:
- `git diff --check` passed.
- `python3 -m py_compile tools/analyze_rl_combat_events.py` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed and rebuilt
  `src/rl/rl_combat_event.c`.
- Follow-up live MiSTer smoke should confirm LP hit still reaches `CDR H` /
  derived hit attribution while an immediate jump afterward does not add an
  extra `CDRX U`.

## 2026-05-07: Combat Event Phase 6b-2 Dual-Whiff Weak-Edge Suppression

Milestone:
- Combat event attribution Phase 6b-2

Files changed:
- `src/rl/rl_combat_event.c`
- `docs/plan-remote-rl-agent.md`
- `docs/agent-memory/remote-rl-combat-event-attribution-plan.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- Stop simultaneous whiffs from polluting defense result unknown counters.

Implementation notes:
- Live testing showed continuous LP whiffs made `CER W` increase correctly,
  but also made `CDRX U` increase. That means attack lifecycle whiff handling
  was good, while defense attribution was recording weak `contact_state` /
  `hit_stop` edges as unknown outcomes.
- Added a narrow suppression gate before contact-match attribution counters are
  incremented. It only suppresses attack-sourced rows where the target is also
  attacking, the edge is weak contact/hit-stop only, and no HP/stun/damage,
  block reaction, parry, throw-caught, or projectile-clash evidence exists.
- Strong outcome paths remain unchanged, so true hit/block/chip/parry/throw
  and projectile-clash records should still reach `CDR` / `CDRX`.

Validation:
- `git diff --check` passed.
- `python3 -m py_compile tools/analyze_rl_combat_events.py` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed and rebuilt
  `src/rl/rl_combat_event.c`.
- Follow-up live MiSTer smoke should confirm repeated simultaneous LP whiffs
  still increment `CER W` while `CDRX U` no longer races upward.

## 2026-05-06: Combat Event Phase 8A-8 Move Offense/Defense Stats

Milestone:
- Combat event attribution Phase 8A-8

Files changed:
- `tools/analyze_rl_combat_events.py`
- `docs/plan-remote-rl-agent.md`
- `docs/agent-memory/remote-rl-combat-event-attribution-plan.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- Give the analyzer a per-side offense/defense table for move usage,
  hit/block/whiff counts, and rates by exact move and broad move tags.

Implementation notes:
- Added source-move records from non-delegated attack rows, projectile rows,
  and throw rows. `projectile_claimed` parent attack rows are represented by
  their projectile rows to avoid counting the same fireball twice.
- Exact move names are derived from existing `engine_action_id` /
  `engine_sub_action_id` metadata when available. The tag view intentionally
  overlaps categories such as `punch`, `kick`, `hp`, `mk`, `projectile`,
  `special`, `super`, `throw`, `air`, `ground`, `stand`, and `crouch`.
- Attack source outcomes use the Phase 8A-7 effective attribution view.
  Projectile and throw source outcomes use their finalized event results.
- Reports include `offense_by_side` and `defense_by_side`. Defense rows are
  the same source moves viewed from the opposite side, useful for answering
  "what did this side get hit by, block, avoid, or see whiff?"
- Hit/block/whiff rates use source-move `uses` as denominator. Since tags are
  overlapping, tag totals are not exclusive and should not be summed.

Validation:
- `python3 -m py_compile tools/analyze_rl_combat_events.py` passed.
- `python3 tools/analyze_rl_combat_events.py logs/phase7a-event-journal-live-events.ndjson --transition-log logs/phase7a-event-journal-live-transitions.ndjson --json-output /tmp/rl-combat-event-move-stats-summary.json --examples 6` passed.
- `python3 -m json.tool /tmp/rl-combat-event-move-stats-summary.json` passed.
- Latest live log produced `208` move-stat source rows: `self=142`,
  `opponent=66`.
- Example self offense exact moves: `fireball-hp uses=33 hit=5 blocked=8
  whiff=2`, `crouch-mk uses=18 hit=8 blocked=4 whiff=5`, and
  `fireball-mp uses=18 hit=3 blocked=6 whiff=2`.

## 2026-05-06: Combat Event Phase 8A-7 Derived Attribution Statistics

Milestone:
- Combat event attribution Phase 8A-7

Files changed:
- `tools/analyze_rl_combat_events.py`
- `docs/plan-remote-rl-agent.md`
- `docs/agent-memory/remote-rl-combat-event-attribution-plan.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- Add a second attribution summary that uses analyzer-derived reconciliation
  results while preserving the raw C journal labels for auditability.

Implementation notes:
- Added `effective_defense_result` records inside the analyzer. Raw
  non-unknown attribution rows keep their original `defense_result`.
- Unknown rows are promoted only when same-source/target reconciliation is
  `resolved_same_source_target`; ambiguous rows become `ambiguous`, and
  unresolved rows remain `unknown`.
- The text and JSON reports now include `derived`, `derived_by_source_side`,
  and `derived_by_target_side` sections with effective result counts, source
  counts, and raw comparison counts.
- This is still analysis-only. C event rows, transition schema, reward,
  replay, and trainer feature paths are unchanged.

Validation:
- `python3 -m py_compile tools/analyze_rl_combat_events.py` passed.
- `python3 tools/analyze_rl_combat_events.py logs/phase7a-event-journal-live-events.ndjson --transition-log logs/phase7a-event-journal-live-transitions.ndjson --json-output /tmp/rl-combat-event-derived-summary.json --examples 1` passed.
- `python3 -m json.tool /tmp/rl-combat-event-derived-summary.json` passed.
- Latest live log raw attribution results remain
  `unknown=94`, `hit=50`, `blocked_chip=16`, `blocked=11`, `evaded=5`,
  `parry=2`, and `thrown=1`.
- Latest live log derived/effective results are
  `hit=79`, `unknown=56`, `blocked_chip=16`, `blocked=16`, `parry=6`,
  `evaded=5`, and `thrown=1`. The analyzer promoted `38` unknown rows
  (`hit=29`, `blocked=5`, `parry=4`) and left `56` unresolved.

## 2026-05-06: Combat Event Phase 8A-6 Defense Unknown Reconciliation

Milestone:
- Combat event attribution Phase 8A-6

Files changed:
- `tools/analyze_rl_combat_events.py`
- `docs/plan-remote-rl-agent.md`
- `docs/agent-memory/remote-rl-combat-event-attribution-plan.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- Use the matching event journal plus transition log to account for each
  `defense_result=unknown` attribution row and identify cases where a later or
  sibling attribution row from the same source/target already records the final
  outcome.

Implementation notes:
- Added analyzer-side same-source/target reconciliation keyed by
  `(run_id, episode_id, source_event_id, target_side)`.
- Reconciliation is report-only: it emits `resolved_same_source_target`,
  `ambiguous_same_source_target`, or `unresolved_no_same_source_target_result`
  plus final-result candidates and examples. Raw C event rows, transition
  schema, rewards, replay, and trainer features are unchanged.
- When `--transition-log` is supplied, each unknown row and each resolved
  candidate are joined back to transition rows by decision id. The report now
  prints `transition_join_counts` so event-only inference is visible.

Validation:
- `python3 -m py_compile tools/analyze_rl_combat_events.py` passed.
- `python3 tools/analyze_rl_combat_events.py logs/phase7a-event-journal-live-events.ndjson --transition-log logs/phase7a-event-journal-live-transitions.ndjson --json-output /tmp/rl-combat-event-summary.json --examples 2` passed.
- `python3 -m json.tool /tmp/rl-combat-event-summary.json` passed.
- Latest live log result: `94` defense-unknown rows, `38` resolved by same
  source/target, `56` unresolved, and `0` ambiguous. Resolved final results are
  `hit=29`, `blocked=5`, and `parry=4`.
- Transition reconciliation was complete for this log: `56`
  `unknown_joined_no_resolved_event` and `38`
  `unknown_and_resolved_events_joined`; no unknown attribution row was missing
  its own transition anchor.

## 2026-05-06: Combat Event Phase 8A-5 Defense Unknown Sub-Buckets

Milestone:
- Combat event attribution Phase 8A-5

Files changed:
- `tools/analyze_rl_combat_events.py`
- `docs/plan-remote-rl-agent.md`
- `docs/agent-memory/remote-rl-combat-event-attribution-plan.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- Make `defense_result=unknown` attribution rows explain why they stayed
  unknown before any Phase 9 reward/trainer adoption.

Implementation notes:
- Added analyzer-side attribution unknown bucketing with source-event joins.
- The report now prints `defense_unknown` totals, bucket counts, edge type
  counts, target state counts, source-family counts, source/target side splits,
  and examples with source event lifecycle information.
- Buckets are conservative and derived only in the analyzer. C journal rows,
  transition schema, rewards, replay, and trainer features are unchanged.

Validation:
- `python3 -m py_compile tools/analyze_rl_combat_events.py` passed.
- `python3 tools/analyze_rl_combat_events.py logs/phase7a-event-journal-live-events.ndjson --transition-log logs/phase7a-event-journal-live-transitions.ndjson --examples 3` passed.
- `python3 tools/analyze_rl_combat_events.py logs/phase7a-event-journal-live-events.ndjson --transition-log logs/phase7a-event-journal-live-transitions.ndjson --json-output /tmp/rl-combat-event-summary.json --examples 1` passed.
- `python3 -m json.tool /tmp/rl-combat-event-summary.json >/tmp/rl-combat-event-summary.pretty.json` passed.
- The latest live log's `94` unknown defense attributions split into
  `unknown_source_rollover=41`, `unknown_source_timeout=30`,
  `unknown_source_whiff_later=20`, and `unknown_source_episode_flush=3`.
- `git diff --check` passed.

## 2026-05-06: Combat Event Phase 8A-4 Probe/Trainer Safety Hardening

Milestone:
- Combat event attribution Phase 8A-4

Files changed:
- `tools/rl_probe_server.py`
- `tools/rl_evidence.py`
- `docs/plan-remote-rl-agent.md`
- `docs/agent-memory/remote-rl-combat-event-attribution-plan.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- Address peer-review P0 findings before Phase 9: avoid probe-side per-line
  JSON parsing for combat event splitting, and prevent combat event journal
  fields from leaking into DQN feature metadata.

Implementation notes:
- `TransitionBatchServer._is_combat_event_line()` now checks for the raw
  `"combat_event_schema_version"` byte key instead of `json.loads()` on every
  uploaded transition/event line. This keeps malformed combat event rows on the
  combat-event log path and avoids unnecessary parse work for ordinary
  transition rows.
- Added `COMBAT_EVENT_ROOT_KEYS` to `tools/rl_evidence.py` and extended
  `is_forbidden_feature_name()` so event identity, side, result, source,
  confidence, target-context, projectile, throw, and punish journal fields are
  stripped from model `feature_names` metadata.
- Existing DQN feature names were checked against the expanded denylist and are
  unaffected.

Validation:
- `python3 -m py_compile tools/rl_probe_server.py tools/rl_evidence.py tools/train_dqn_learner.py` passed.
- Probe split smoke passed: ordinary transition rows are not classified as
  combat events, valid combat event rows are classified as events, and
  `_append_payload()` routes malformed rows containing
  `"combat_event_schema_version"` to the event log rather than the transition
  log.
- Feature sanitizer smoke passed: current `DQN_FEATURE_NAMES` are preserved,
  while `event_id`, `defense_result`, `source_side`, `target_side`,
  `parent_attack_event_id`, `evidence_flags_lo`, and
  `ep_overlay_attack_active_count` are stripped.
- `git diff --check` passed.

## 2026-05-06: Combat Event Phase 8A-3 Throw/Attribution/Punish Side Splits

Milestone:
- Combat event attribution Phase 8A-3

Files changed:
- `tools/analyze_rl_combat_events.py`
- `docs/plan-remote-rl-agent.md`
- `docs/agent-memory/remote-rl-combat-event-attribution-plan.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- Make the remaining aggregate event sections side-readable for live review.

Implementation notes:
- Added generic side-row summarization to the analyzer.
- Throw summaries now include `by_owner_side`.
- Attribution summaries now include both `by_source_side` and `by_target_side`,
  because attribution rows describe the attacker/source and the defender/target.
- Punish summaries now include both `by_punisher_side` and `by_punished_side`.
- Aggregate totals remain unchanged, and this is still a report-only change:
  C journal rows, transition schema, rewards, replay, and trainer features are
  untouched.

Validation:
- `python3 -m py_compile tools/analyze_rl_combat_events.py` passed.
- `python3 tools/analyze_rl_combat_events.py logs/phase7a-event-journal-live-events.ndjson --transition-log logs/phase7a-event-journal-live-transitions.ndjson --examples 1` passed and printed side splits for Throw, Attribution, and Punish.
- `python3 tools/analyze_rl_combat_events.py logs/phase7a-event-journal-live-events.ndjson --transition-log logs/phase7a-event-journal-live-transitions.ndjson --json-output /tmp/rl-combat-event-summary.json --examples 1` passed.
- `python3 -m json.tool /tmp/rl-combat-event-summary.json >/tmp/rl-combat-event-summary.pretty.json` passed.
- `git diff --check` passed.

## 2026-05-06: Combat Event Phase 8A-2 Delegated Projectile Side Split

Milestone:
- Combat event attribution Phase 8A-2

Files changed:
- `tools/analyze_rl_combat_events.py`
- `docs/plan-remote-rl-agent.md`
- `docs/agent-memory/remote-rl-combat-event-attribution-plan.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- Split delegated projectile outcome summaries by `self` / `opponent` owner
  side, while retaining the aggregate totals.

Implementation notes:
- Added `by_owner` to the analyzer's `attack.delegated_projectile` summary.
- The text report now prints per-owner linked projectile count, result counts,
  finalize reason counts, and expired `saw_opposing_projectile` vs clean fly-out
  counts.
- This remains a report-only change. C journal rows, transition schema, rewards,
  replay, and trainer features are unchanged.

Validation:
- `python3 -m py_compile tools/analyze_rl_combat_events.py` passed.
- `python3 tools/analyze_rl_combat_events.py logs/phase7a-event-journal-live-events.ndjson --transition-log logs/phase7a-event-journal-live-transitions.ndjson --examples 2` passed and reported delegated projectile owner splits: `self` linked `34` with `blocked=17`, `hit=9`, `expired=7`, `unknown=1`; `opponent` linked `10` with `hit=5`, `expired=3`, `blocked=2`.
- `python3 tools/analyze_rl_combat_events.py logs/phase7a-event-journal-live-events.ndjson --transition-log logs/phase7a-event-journal-live-transitions.ndjson --json-output /tmp/rl-combat-event-summary.json --examples 1` passed.
- `python3 -m json.tool /tmp/rl-combat-event-summary.json >/tmp/rl-combat-event-summary.pretty.json` passed.
- `git diff --check` passed.

## 2026-05-06: Combat Event Phase 8A-1 Delegated Projectile Resolution

Milestone:
- Combat event attribution Phase 8A-1

Files changed:
- `tools/analyze_rl_combat_events.py`
- `docs/plan-remote-rl-agent.md`
- `docs/agent-memory/remote-rl-combat-event-attribution-plan.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- Make analyzer output answer whether `projectile_claimed` attack rows
  ultimately hit, were blocked, expired, or stayed unknown.

Implementation notes:
- C-side journal rows remain unchanged: parent attacks still record
  `result=unknown` and `finalize_reason=projectile_claimed`.
- The analyzer now builds a `(run_id, episode_id, parent_attack_event_id)` join
  from projectile rows and resolves attack `effective_bucket` values to
  `projectile_hit`, `projectile_blocked`, `projectile_expired`, or
  `projectile_unknown` when exactly one projectile child is found.
- The report keeps `raw_lifecycle_bucket` so the original
  `delegated_to_projectile` ownership transfer remains visible and cannot be
  confused with direct attack hit/block results.
- Added a `Delegated Projectile Outcome` section with linked/missing/multi-link
  counts, projectile result/finalize/owner counts, expired clash-vs-clean
  breakdown, and examples for projectile unknown or missing links.

Validation:
- `python3 -m py_compile tools/analyze_rl_combat_events.py` passed.
- `python3 tools/analyze_rl_combat_events.py logs/phase7a-event-journal-live-events.ndjson --transition-log logs/phase7a-event-journal-live-transitions.ndjson --examples 3` passed and reported `44` delegated attacks, `44` linked projectiles, `0` missing links, `0` multi-links, and delegated projectile results `blocked=19`, `hit=14`, `expired=10`, `unknown=1`.
- `python3 tools/analyze_rl_combat_events.py logs/phase7a-event-journal-live-events.ndjson --transition-log logs/phase7a-event-journal-live-transitions.ndjson --json-output /tmp/rl-combat-event-summary.json --examples 1` passed.
- `python3 -m json.tool /tmp/rl-combat-event-summary.json >/tmp/rl-combat-event-summary.pretty.json` passed.
- `git diff --check` passed.

## 2026-05-06: Combat Event Phase 8A Journal Analyzer

Milestone:
- Combat event attribution Phase 8A

Files changed:
- `tools/analyze_rl_combat_events.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- Add a human-readable analyzer for Phase 7A combat event journal logs before
  changing C-side result classification rules.

Implementation notes:
- Added `tools/analyze_rl_combat_events.py`.
- The analyzer reports schema/kind/episode health, duplicate event keys,
  chronological `event_id` integrity, source-reference integrity, attack result
  buckets, projectile lifecycle, throw results, attribution defense results,
  punish path/reason/source-family splits, and optional transition-log join
  rates.
- Attack unknowns are now split into effective buckets:
  `delegated_to_projectile`, `round_boundary_unknown`, `rollover_unknown`,
  `timeout_unknown`, `timeout_projectile_like_unknown`, and
  `true_unknown_other`.
- The analyzer fails fast on unsupported `combat_event_schema_version` unless
  `--allow-unsupported-schema` is supplied.

Validation:
- `python3 -m py_compile tools/analyze_rl_combat_events.py` passed.
- `python3 tools/analyze_rl_combat_events.py logs/phase7a-event-journal-live-events.ndjson --transition-log logs/phase7a-event-journal-live-transitions.ndjson --examples 3` passed.
- Live analyzer output on the latest Phase 7A-2 log reported `455` event rows,
  `0` duplicate rows, monotonic `event_id` `1..455`, projectile counter checks
  matching both episodes, and `83` true attack-unknown rows after excluding
  `44` `delegated_to_projectile` rows and `4` `round_boundary_unknown` rows.
- `python3 tools/analyze_rl_combat_events.py logs/phase7a-event-journal-live-events.ndjson --transition-log logs/phase7a-event-journal-live-transitions.ndjson --json-output /tmp/rl-combat-event-summary.json --examples 1` passed.
- `python3 -m json.tool /tmp/rl-combat-event-summary.json >/tmp/rl-combat-event-summary.pretty.json` passed.
- `git diff --check` passed.

## 2026-05-06: Combat Event Phase 7A-2 Ordered Complete Journal Snapshots

Milestone:
- Combat event attribution Phase 7A-2

Files changed:
- `src/rl/rl_combat_event.h`
- `src/rl/rl_combat_event.c`
- `docs/agent-memory/remote-rl-combat-event-attribution-plan.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- Make combat event journal rows complete across a whole episode and emit them
  in chronological `event_id` order.

Live finding:
- The post-dedupe live log was cleanly split and duplicate-free, but still used
  the small live tracking rings as the episode-end export source.
- The event file had `303` unique rows, while transition counters showed more
  projectile events than the `16` projectile rows preserved per episode; the
  attribution journal also landed exactly on its `64`-entry ring cap.
- This showed that episode-end ring dumps lose older events once rings wrap.

Implementation notes:
- Added a per-episode journal snapshot buffer. Attack, projectile, and throw
  rows are copied when finalized; attribution and punish rows are copied when
  recorded.
- `RLCombatEvent_EmitJournal()` now emits from the journal snapshot buffer
  sorted by run-wide `event_id`, rather than by ring kind/slot order.
- The live rings remain the active gameplay/attribution working sets; the
  journal buffer is export-only and does not feed reward, inference, replay, or
  trainer features.

Validation:
- `cc -std=c11 -Wall -Wextra -Isrc -Iinclude -c src/rl/rl_combat_event.c -o /tmp/rl_combat_event_phase7a2.o` passed.
- `/tmp/rl_journal_smoke` passed: 40 finalized attack events exceeded the
  32-entry attack ring cap, and `RLCombatEvent_EmitJournal()` still emitted all
  40 rows once in ascending `event_id` order with zero format errors.
- `git diff --check` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed; existing upstream
  `mktemp` linker warning remains unrelated.

## 2026-05-06: Combat Event Phase 7A-1 Event Journal Dedupe

Milestone:
- Combat event attribution Phase 7A-1

Files changed:
- `src/rl/rl_session.c`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- Fix Phase 7A live event journal duplication while keeping the same two-file
  transition/event log split.

Live finding:
- `logs/phase7a-event-journal-live-events.ndjson` proved event export and
  Python split were working: `90138` valid schema-1 event rows were written.
- Those rows represented only `280` unique `(run_id, episode_id, event_kind,
  event_id)` keys, meaning repeated terminal/finalize calls were appending the
  same episode event ring hundreds of times.
- The matching transition log stayed clean: no combat event rows polluted
  `logs/phase7a-event-journal-live-transitions.ndjson`, and transition
  decisions had no duplicate keys.

Implementation notes:
- Added session-level tracking for the last exported combat-event journal
  `(run_id, episode_id)`.
- `RLSession_AppendCombatEventJournal()` now skips repeat emission for the same
  episode after a successful or partially emitted journal attempt.
- This leaves transition rows, reward, inference, replay, trainer features, and
  event schema unchanged.

Validation:
- `git diff --check` passed.
- Live-log duplicate audit confirmed the pre-fix issue:
  `90138` event rows, `280` unique event keys, `89858` duplicate rows, and
  max duplicate count `407`.
- `tools/mister/build-game.sh --flavor telemetry` passed; existing upstream
  `mktemp` linker warning remains unrelated.

## 2026-05-06: Combat Event Phase 7A Event Journal Export Skeleton

Milestone:
- Combat event attribution Phase 7A

Files changed:
- `src/rl/rl_combat_event.h`
- `src/rl/rl_combat_event.c`
- `src/rl/rl_session.h`
- `src/rl/rl_session.c`
- `src/configuration.h`
- `src/args.c`
- `src/main.c`
- `src/port/config/config.h`
- `tools/rl_probe_server.py`
- `vendor/Menu_MiSTer/menu.sv`
- `vendor/Main_MiSTer/thirdsarm_wrapper.cpp`
- `docs/config.md`
- `docs/agent-memory/remote-rl-combat-event-attribution-plan.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- Start Phase 7 by exporting formal combat event journal rows while keeping
  transition rows learner-safe and unchanged.

Implementation notes:
- Added `rl-agent-export-combat-events`, `--rl-export-combat-events`, and the
  MiSTer OSD `RL Event Log (Restart)` gate. Default remains off.
- Added `combat_event_schema_version=1` NDJSON rows for attack, projectile,
  throw, attribution/defense context, and punish events.
- Event rows are appended to the same TCP transition batch payload as
  transition rows, so disk logs can be joined from one envelope by
  `run_id`/`episode_id`/`decision_id`/`frame_id`/`event_id`.
- `tools/rl_probe_server.py` now splits batch payload lines: transition rows go
  to `--transition-log`, and combat event rows go to `--combat-event-log`.
  If no event log is supplied, event rows are dropped instead of polluting the
  transition log.
- This does not change reward, inference, action scheduling, replay, trainer
  features, or transition row shape.

Validation:
- `cc -std=c11 -Wall -Wextra -Isrc -Iinclude -c src/rl/rl_combat_event.c -o /tmp/rl_combat_event_phase7a.o` passed.
- `python3 -m py_compile tools/rl_probe_server.py` passed.
- Synthetic mixed-payload split smoke passed: one transition row stayed in
  `transitions.ndjson`, one `combat_event_schema_version=1` row went to
  `events.ndjson`.
- `git diff --check` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed.
- `tools/mister-wrapper/build-hps.sh` passed, producing
  `build/mister-wrapper-hps/MiSTer_3S-ARM`; existing upstream wrapper unused
  warnings remain unrelated.

## 2026-05-06: Combat Event Phase 6c-2 Frozen Debug Overlay Contract

Milestone:
- Combat event attribution Phase 6c-2

Files changed:
- `docs/agent-memory/remote-rl-combat-event-attribution-plan.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- Freeze the live-validated Outcome overlay semantics before Phase 7 starts
  exporting formal combat event journal rows.

Implementation notes:
- Documented the debug overlay contract for attack, projectile, throw,
  attribution, defense, and punish counters:
  `CE`/`CER`, `CP`/`CPR`, `CT`/`CTR`, `CEM`/`CEA`/`CEAE`/`CEAX`,
  `CDR`/`CDRX`/`CDC`, and `CPN`/`CPNX`/`CPNC`/`CPNR`.
- Recorded accepted live behavior from the MiSTer overlay tests, including
  simultaneous whiffs, projectile clash, projectile parry, blocked projectile
  chip context, throw contest handling, active-attack punish fallback, and
  fully recovered neutral hits not counting as punish.
- Kept this as a documentation-only contract. It does not change C logic,
  transition schema, rewards, replay, trainer features, or event-journal export.

Validation:
- `git diff --check` passed.

## 2026-05-06: Combat Event Phase 6c-1 Punish Candidate Path Split

Milestone:
- Combat event attribution Phase 6c-1

Files changed:
- `src/rl/rl_combat_event.h`
- `src/rl/rl_combat_event.c`
- `src/rl/rl_session.h`
- `src/rl/rl_session.c`
- `src/rl/rl_observation.c`
- `docs/plan-remote-rl-agent.md`
- `docs/agent-memory/remote-rl-combat-event-attribution-plan.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- Keep live-validated punish candidates observable while separating
  finalized-window punish candidates from active-attack fallback candidates.

Implementation notes:
- Added side-split counters for punish candidate path:
  finalized-window vs active-attack fallback.
- Added path+reason counters for finalized whiff/interrupted and active
  whiff/interrupted candidates.
- Outcome overlay adds `CPNC F/A` and `CPNR FW/FI/AW/AI`.
- Live refinement: shortened finalized-window matching from 45 frames to 12
  frames after delayed neutral hits still appeared as `CPN R/W`. Immediate DP
  whiff punish remains covered by active-attack fallback; longer recovery
  punish labels need action-specific unsafe windows in a later Phase 6c slice.
- Follow-up live refinement: disabled finalized-window whiff candidates after
  fully recovered DP/large-special neutral hits still counted as `CPN R/W`.
  Whiff punish is now expected through active fallback (`CPNC A`, usually
  `CPNR AW`/`AI`) until action-specific recovery windows are available.
- This remains debug-only. It does not change transition schema, reward,
  replay, trainer features, or event-journal export.

Validation:
- `git diff --check` passed.
- `cc -std=c11 -Wall -Wextra -Isrc -Iinclude -c src/rl/rl_combat_event.c -o /tmp/rl_combat_event_phase6c1_path_split.o` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed, rebuilding
  `rl_combat_event.c`, `rl_observation.c`, and `rl_session.c`.
- Finalized-window refinement validation passed:
  `git diff --check`,
  `cc -std=c11 -Wall -Wextra -Isrc -Iinclude -c src/rl/rl_combat_event.c -o /tmp/rl_combat_event_phase6c1_window.o`,
  and `tools/mister/build-game.sh --flavor telemetry`.
- Finalized-whiff disable validation passed:
  `git diff --check`,
  `cc -std=c11 -Wall -Wextra -Isrc -Iinclude -c src/rl/rl_combat_event.c -o /tmp/rl_combat_event_phase6c1_disable_fw.o`,
  and `tools/mister/build-game.sh --flavor telemetry`.

## 2026-05-06: Combat Event Phase 6c-0 Punish Candidate Counters

Milestone:
- Combat event attribution Phase 6c-0

Files changed:
- `src/rl/rl_combat_event.h`
- `src/rl/rl_combat_event.c`
- `src/rl/rl_session.h`
- `src/rl/rl_session.c`
- `src/rl/rl_observation.c`
- `docs/plan-remote-rl-agent.md`
- `docs/agent-memory/remote-rl-combat-event-attribution-plan.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- Start punish detection as conservative debug counters before formal punish
  event-journal rows or learner adoption.

Implementation notes:
- Finalized whiff/interrupted attack events now open a short side-local
  punishable window.
- A later opposite-side high-confidence attribution event with a real source id
  and defense result hit/thrown consumes that window and increments punish
  counters for the punisher side.
- Live refinement: a DP/large-special whiff punish can happen before the
  target attack event finalizes. If the defender still has a recent active
  non-projectile attack with no strong HP/stun/damage evidence against its own
  target, a later high-confidence opposite-side hit/throw can consume that
  active attack directly as a punish candidate.
- Outcome overlay adds `CPN R/W/I` and `CPNX A/P/T` for punish candidate total,
  punished-attack reason, and punisher source family.
- This does not handle all unsafe recovery cases yet, especially projectile
  recovery / close-fireball nuance. Those remain for later Phase 6c refinement.
- No transition schema, reward, replay, trainer, or event-journal export change.

Validation:
- `git diff --check` passed.
- `cc -std=c11 -Wall -Wextra -Isrc -Iinclude -c src/rl/rl_combat_event.c -o /tmp/rl_combat_event_phase6c0_punish.o` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed, rebuilding
  `rl_combat_event.c`, `rl_observation.c`, and `rl_session.c`.
- Active-attack punish refinement validation passed:
  `git diff --check`,
  `cc -std=c11 -Wall -Wextra -Isrc -Iinclude -c src/rl/rl_combat_event.c -o /tmp/rl_combat_event_phase6c0_active_punish.o`,
  and `tools/mister/build-game.sh --flavor telemetry`.

## 2026-05-06: Combat Event Phase 6b-1 Defense Context Snapshots

Milestone:
- Combat event attribution Phase 6b-1

Files changed:
- `src/rl/rl_combat_event.h`
- `src/rl/rl_combat_event.c`
- `src/rl/rl_session.h`
- `src/rl/rl_session.c`
- `src/rl/rl_observation.c`
- `docs/plan-remote-rl-agent.md`
- `docs/agent-memory/remote-rl-combat-event-attribution-plan.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- Preserve the defense context behind each internal attribution event so the
  future event journal can export `defense_result` with intent, actual guard
  state, target state, and raw evidence instead of relying only on overlay
  aggregate counters.

Implementation notes:
- Added `RLCombatDefenseGuardState` and `RLCombatDefenseTargetState`.
- `RLCombatAttributionEvent` now stores agent-side target policy intent when
  the defender is self, actual guard state, derived target state, routines, and
  raw target evidence bits for guard, block reaction, parry, throw-caught,
  airborne, attack-state, contact reaction, hit-stop, contact-state,
  damage-state, HP delta, and stun delta.
- Outcome overlay adds `CDC G/BR/PA/TC` side-split context counters to show raw
  guard, block-reaction, parry, and throw-caught evidence behind `CDR`.
- This remains debug/internal only: no transition schema bump, no reward,
  replay, trainer, or event-journal export change.

Validation:
- `git diff --check` passed.
- `cc -std=c11 -Wall -Wextra -Isrc -Iinclude -c src/rl/rl_combat_event.c -o /tmp/rl_combat_event_phase6b1_context.o` passed.
- A bare host compile of `src/rl/rl_session.c` is not valid because it requires
  generated `port/build_config.h`; the canonical MiSTer telemetry build below
  covered `rl_session.c`.
- `tools/mister/build-game.sh --flavor telemetry` passed, rebuilding
  `rl_combat_event.c`, `rl_observation.c`, and `rl_session.c`.

## 2026-05-06: Combat Event Phase 6b-0 Defense Result Counters

Milestone:
- Combat event attribution Phase 6b-0

Files changed:
- `src/rl/rl_combat_event.h`
- `src/rl/rl_combat_event.c`
- `src/rl/rl_session.h`
- `src/rl/rl_session.c`
- `src/rl/rl_observation.c`
- `docs/plan-remote-rl-agent.md`
- `docs/agent-memory/remote-rl-combat-event-attribution-plan.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- Start defense result emission as debug counters derived from the attribution
  ring, so live testing can distinguish clean hit, block, blocked chip, parry,
  throw, evaded/negated contact, and unknown before event-journal export.

Implementation notes:
- Added `RLCombatDefenseResult` and target-side split stats for hit, blocked,
  blocked chip, parry, thrown, evaded, and unknown.
- Attribution events now store a debug-only defense result.
- `CDR H/B/C/P` and `CDRX T/E/U` Outcome lines expose defense result counters.
- Blocked projectile chip is detected from HP/stun/damage attribution plus
  target guard/block context or a blocked projectile source result, so blocked
  fireball chip should become `CDR C` rather than `CDR H`.

Validation:
- `git diff --check` passed.
- `cc -std=c11 -Wall -Wextra -Isrc -Iinclude -c src/rl/rl_combat_event.c -o /tmp/rl_combat_event_phase6b0_cdr.o` passed.
- `python3 -m py_compile tools/rl_probe_server.py tools/analyze_rl_transitions.py` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed, rebuilding
  `rl_combat_event.c`, `rl_observation.c`, and `rl_session.c`.

Live retest note:
- Initial live validation showed ordinary attack hit and fireball hit both
  incrementing `CDR C` instead of `CDR H`. The root cause was that
  `target_guard` was included in the generic blocked-chip context; guard can be
  true on clean-hit contact frames. The correction keeps explicit block
  reaction/projectile-block evidence for chip and limits raw guard fallback to
  projectile HP-only chip cases with no stun/damage-state evidence.
- Correction validation passed: `git diff --check`,
  `cc -std=c11 -Wall -Wextra -Isrc -Iinclude -c src/rl/rl_combat_event.c -o /tmp/rl_combat_event_phase6b0_cdr_fix.o`,
  and `tools/mister/build-game.sh --flavor telemetry`.

## 2026-05-06: Combat Event Phase 6a-1B Edge Coverage Counters

Milestone:
- Combat event attribution Phase 6a-1B

Files changed:
- `src/rl/rl_combat_event.h`
- `src/rl/rl_combat_event.c`
- `src/rl/rl_session.h`
- `src/rl/rl_session.c`
- `src/rl/rl_observation.c`
- `docs/plan-remote-rl-agent.md`
- `docs/agent-memory/remote-rl-combat-event-attribution-plan.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- Make the attribution ring observable by edge type before Phase 6b defense
  result emission, while keeping transition schema, reward, replay, and trainer
  behavior unchanged.

Implementation notes:
- Added per-episode attribution edge counters for HP delta, stun delta,
  damage-state, block-reaction, parry, throw-caught, projectile clash, hit-stop,
  and contact-state attribution edges.
- Outcome overlay now shows `CEAE HP/ST/DM/BL` and `CEAX PA/TH/CL/HS/CT`.
- Cleaned Outcome overlay for this validation pass: it no longer shows the
  generic HP/round header, `AH/ACC/AWC`, timeout cause lines, or lifetime lines.
  Outcome now focuses on combat-event lifecycle and attribution counters.

Validation:
- `git diff --check` passed.
- `cc -std=c11 -Wall -Wextra -Isrc -Iinclude -c src/rl/rl_combat_event.c -o /tmp/rl_combat_event_phase6a1b_edges.o` passed.
- `python3 -m py_compile tools/rl_probe_server.py tools/analyze_rl_transitions.py` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed, rebuilding
  `rl_combat_event.c`, `rl_observation.c`, and `rl_session.c`.
- Live note: blocked fireball produced `CEM P +1`, `CEA R +1`, and `CEAE HP
  +1` with `CEAE BL +0`. This is accepted for Phase 6a-1B because blocked
  projectile chip can surface as HP delta as the primary attribution edge.
  Phase 6b must combine HP delta with guard/block context to emit blocked-chip
  defense results.

## 2026-05-06: Combat Event Phase 6a-1A Attribution Ring Skeleton

Milestone:
- Combat event attribution Phase 6a-1A

Files changed:
- `src/rl/rl_combat_event.h`
- `src/rl/rl_combat_event.c`
- `src/rl/rl_session.h`
- `src/rl/rl_session.c`
- `src/rl/rl_observation.c`
- `docs/plan-remote-rl-agent.md`
- `docs/agent-memory/remote-rl-combat-event-attribution-plan.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- Promote the live-validated `CEM` source-family classifier into a debug-only
  attribution ring so future event-journal export has a concrete internal
  record format before any schema, reward, replay, or trainer adoption.

Implementation notes:
- Added `RLCombatAttributionEvent` and a fixed-size 64-entry attribution ring.
- Every successful CEM classification writes one attribution event with source
  family, source event id when available, target side, edge type, confidence,
  and failure reason.
- Unknown CEM classifications now create attribution records with
  `no_source_candidate` instead of being only aggregate counters.
- Outcome overlay adds `CEA R/F/O` for attribution records, failure records,
  and ring overwrites. The attribution ring is not serialized into transition
  rows yet.

Validation:
- `git diff --check` passed.
- `cc -std=c11 -Wall -Wextra -Isrc -Iinclude -c src/rl/rl_combat_event.c -o /tmp/rl_combat_event_phase6a1_attribution.o` passed.
- `python3 -m py_compile tools/rl_probe_server.py tools/analyze_rl_transitions.py` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed, rebuilding
  `rl_combat_event.c`, `rl_observation.c`, and `rl_session.c`.
- Live smoke passed: whiffs and jumped/evaded fireballs left `CEM` / `CEA`
  unchanged; broader live testing showed no obvious `CEA` / `CEM` mismatch.

## 2026-05-06: Combat Event Phase 6a-0 Contact-Match Instrumentation

Milestone:
- Combat event attribution Phase 6a-0

Files changed:
- `src/rl/rl_combat_event.h`
- `src/rl/rl_combat_event.c`
- `src/rl/rl_session.h`
- `src/rl/rl_session.c`
- `src/rl/rl_observation.c`
- `docs/plan-remote-rl-agent.md`
- `docs/agent-memory/remote-rl-combat-event-attribution-plan.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- Start Phase 6a with a conservative observability layer before full event-id
  attribution: every meaningful target HP/stun/contact edge is classified into
  one source family so live testing can reveal whether attack, projectile,
  throw, or unknown matching is stable.

Implementation notes:
- Added `RLCombatContactMatchUpdate` and `RLCombatEvent_RecordContactMatch()`.
  The matcher records one debug-only source family per target edge with priority
  projectile -> throw -> attack -> unknown.
- Added per-episode `contact_match_*` stats and mirrored them through
  `RLRemoteDebugState`.
- Added Outcome overlay line `CEM Aself/opp Pself/opp Tself/opp Uself/opp`.
- The slice intentionally does not mutate HP/stun deltas, does not change the
  transition schema, does not emit event journal rows, and does not touch reward
  or trainer features. Full consumed-delta attribution, confidence, and
  attribution-failure events remain open in Phase 6a.

Validation:
- `git diff --check` passed.
- `python3 -m py_compile tools/rl_probe_server.py tools/analyze_rl_transitions.py` passed.
- `cc -std=c11 -Wall -Wextra -Isrc -Iinclude -c src/rl/rl_combat_event.c -o /tmp/rl_combat_event_phase6a.o` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed, rebuilding
  `rl_combat_event.c`, `rl_observation.c`, and `rl_session.c`.

Follow-up:
- Live validate `CEM`: normals should mostly increment `A`, fireballs should
  increment `P`, throws should increment `T`, and repeatable `U` cases become
  the next matcher gap.
- Promote from source-family counters to event-id consumption only after the
  live CEM distribution is stable across hit/block/projectile/throw/trade cases.

Refinement after first live CEM pass:
- User live report showed correct source-family counters accompanied by
  reverse-side `CEM U` noise: attacks and fireballs produced `A`/`P` on the
  source side but also `U` on the target's opposite source side; throw success
  produced `T` plus reverse `U`; side swaps could create `U`.
- Root cause: the first matcher treated plain entered hit-stop/contact-state as
  meaningful even when the source side had no attack/projectile/throw
  candidate. SF3 often puts both participants into hit-stop/contact-related
  states, so the attacker's own hit-stop looked like an unattributed incoming
  edge for the other source side.
- Fix: HP/stun/damage and throw-caught rising edges remain strong target edges
  and can become `U` if no source candidate exists. Guard block reaction is
  treated as a sustained state, not a strong edge; block contact is counted
  through entered-contact evidence. Plain hit-stop/contact-state evidence is
  counted only when that source side already has attack/projectile/throw
  evidence. Finalized same-frame projectile events also remain projectile
  candidates so clashes/parries do not fall back to the projectile parent
  attack.
- Second live report showed ordinary fireballs were clean (`CEM P+1`), but
  projectile supers and occasional projectile clashes still leaked `CEM A+1`
  from raw parent attack routine state; throw success also still often produced
  `CEM T+2`. Fix: CEM attack candidates now come only from the combat attack
  ring, not raw `routine/current_attack` state. Throw events now remember whether
  they already produced a contact match, so the caught edge and delayed
  HP/stun/damage from the same throw do not both increment `CEM T`.
- Third live report still showed `CEM A+1` for SA1 fireball and projectile
  clashes. Fix: the CEM attack fallback now excludes active attack events that
  are `projectile_like` or have already seen a projectile. Projectile parent
  attacks should remain lifecycle context for `CP` / `CPR`, not fallback strike
  sources.
- Fourth live report showed a failed jump over an opponent fireball could
  produce `CEM P +0/+2`. Fix: projectile-only soft contact no longer counts
  unless the target is in a block-reaction routine; projectile hits should wait
  for HP/stun/damage evidence, avoiding a separate early hit-stop/contact count.
- Fifth live report showed parrying an opponent fireball sometimes produced
  `CEM P +0/+0`. Fix: observation now records self/opponent parry-success
  rising edges from `paring_ctr_vs[Play_Type][side]`; projectile CEM treats that
  edge as a valid projectile target edge even without HP/stun/damage or block
  reaction.
- Follow-up live report still showed `CEM P +0/+0` for parried opponent
  fireballs, so parry evidence was widened. Observation now ORs together parry
  counter rising, parry bonus rising, and parry success routine rising
  (`R1=0`, `R2=31/32/33/34`) before feeding `target_parry_started` into CEM.
- Next live report showed fireball parry fixed, but fireball-vs-fireball
  collision produced `CEM P +0/+0` even when projectile results finalized as
  `CPR X`. Root cause: CEM only accepted character target edges, while a
  projectile clash can consume both projectile objects without HP/stun/contact
  on either player. Fix: CEM now treats same-frame mutual projectile expiration
  (`CPR X` / `DISAPPEARED`) as a projectile clash edge. Single-projectile
  expiration still remains `CPR X` only and does not produce CEM.
- Follow-up live report showed a clash with `CPR X +0/+1` and `CEM P +0/+0`,
  meaning only the opponent projectile side was tracked/finalized. The single
  selected projectile observation was too lossy for simultaneous fireballs. Fix:
  observation now keeps self/opponent projectile-active snapshots separately,
  projectile events remember whether an opposing projectile was active during
  their lifetime, and `CPR X` / `DISAPPEARED` with that opposing-projectile
  evidence becomes a CEM projectile clash edge even if only one side finalized.
- Live retest after side-specific projectile tracking passed the projectile
  edge cases: fireball clash produced `CPR X +1/+1` and `CEM P +1/+1`; parrying
  an opponent fireball remained conservative `CPR U +0/+1`; single fireball
  fly-out stayed `CPR X +1/+0` with `CEM P +0/+0`. This confirms clash CEM is
  now covered without reintroducing CEM noise for ordinary projectile expiry.

## 2026-05-05: Combat Event Phase 5C/5D Throw Live Refinement Prep

Update after live retest:
- User live report showed held LP+LK plus left/right direction changes
  repeatedly incremented `CT S/F`, `CTR W`, and `CTR U`. Root cause: the
  self-side policy/input `throw` action-step-0 metadata was used as a standalone
  throw-start source on every ledger row.
- Fix: policy/input `throw` now remains metadata only. Throw event starts come
  from raw throw-active edges or engine throw-routine edges/attribution, so held
  input rows do not create repeated events without a fresh engine attempt.
- Second live retest showed single successful throws and mutual throw attempts
  could still report `CT S/F +2`; when that happened one duplicate event often
  finalized as `CTR U`. Root cause: the same attempt could first start from an
  engine routine edge, then start again from a later `tsukami_f`/engine edge
  before the first event finalized.
- Fix: active throw events are updated before new throw starts are considered,
  and same-side active throw events now suppress duplicate starts. Throw success
  also waits a short confirm window unless damage/stun evidence is already
  present, so mutual throw/escape evidence can finalize as `CTR U` before
  `CTR T` is emitted.
- Third live retest still showed `CTR T +1/+2` on mutual throws and occasional
  duplicate success starts. Root cause: raw `tsukami_f` starts could still fire
  after a recently finalized engine-start throw result, and opponent contested
  evidence only used raw throw-active edges, missing simultaneous engine
  throw-start routines.
- Fix: throw start sources are now separated. Ryu `R2=14` engine throw-start
  edges may supersede an active clean throw into `CTR W` for rapid whiff retries;
  raw `tsukami_f` starts are suppressed while a throw is active and shortly
  after non-whiff throw results. Opposing engine throw-start edges now count as
  contested evidence, and `R2=2` completed-throw support is no longer used as a
  start source.
- Fourth live retest reduced mutual-throw cases to three paths: one still
  emitted self-side `CTR T`, one correctly emitted both-side `CTR U`, and one
  emitted self-side `CTR U`. Root cause is likely delayed escape/opposing
  evidence arriving after the old two-frame success confirm. The success
  confirm window is now widened to 8 frames so late nagenuke/escape evidence can
  win before `CTR T`.
- Final Phase 5D live retest accepted mutual throw/tech-like behavior:
  observed cases were `CT/CTR U 0/+1`, `+1/0`, and `+1/+1`, with no remaining
  `CTR T` false-positive. The side split may be one-sided or both-sided because
  the current tracker only credits the side whose start/escape evidence is
  observed inside the confirm window; Phase 6 matching will handle complete
  bilateral attribution.

Milestone:
- Milestone 6: Combat event attribution Phase 5C/5D

Files changed:
- `src/rl/rl_observation.h`
- `src/rl/rl_observation.c`
- `src/rl/rl_combat_event.h`
- `src/rl/rl_combat_event.c`
- `src/rl/rl_session.c`
- `docs/plan-remote-rl-agent.md`
- `docs/agent-memory/remote-rl-combat-event-attribution-plan.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- Fix two live throw-counter gaps before the Phase 5D live pass: out-of-range
  throw attempts should produce `CT S` and later `CTR W`, while simultaneous or
  tech-like throw interactions should not be counted as successful `CTR T`.

Implementation notes:
- Added internal observation evidence for throw escape / nagenuke-style
  routines (`R1=0`, `R2=47/48/49/50`) with rising edges. These fields are not
  exported in transition schema v9 and do not feed reward or learner features.
- Throw starts now accept Ryu engine throw-start routine edges (`R1=4`,
  `R2=14`) on fresh routine/attack edges and raw throw-active edges when no
  active/recent non-whiff result covers the same interaction. Policy/input
  `throw` rows and already-attributed engine action metadata are not standalone
  start triggers.
- Each ledger row starts at most one throw event per side, preventing repeated
  starts from the same decision span.
- Same-side active throw events suppress duplicate starts across decision rows.
  Throw start checks now run after active throw updates so a previous whiff can
  finalize before a new rapid throw is considered.
- A fresh engine throw-start edge may supersede a clean active throw into
  `CTR W`, even if the minimum whiff window has not elapsed. This is the rapid
  whiff retry path and is intentionally not available to raw `tsukami_f` starts.
- Throw finalization treats opposing throw evidence and throw-escape routines
  as contested. Contested caught evidence without real damage/stun evidence is
  finalized as `CTR U`, not `CTR T`; clean non-contested forward/back throw
  success still uses target caught evidence and remains `CTR T` after the
  widened success confirm window.

Validation:
- `git diff --check` passed.
- `python3 -m py_compile tools/rl_probe_server.py tools/analyze_rl_transitions.py` passed.
- `cc -std=c11 -Wall -Wextra -Isrc -Iinclude -c src/rl/rl_combat_event.c -o /tmp/rl_combat_event_throw_refine.o` passed.
- After the held-input fix, `rg -n 'PolicyActionIsInitialThrow|EntrySelfPolicyStartedThrow' src/rl/rl_session.c`
  returned no matches.
- Direct host compilation of `rl_observation.c` and `rl_session.c` is blocked
  without generated `port/build_config.h`; use the canonical telemetry build
  for those modules.
- `tools/mister/build-game.sh --flavor telemetry` passed, rebuilding
  `rl_combat_event.c`, `rl_observation.c`, `rl_session.c`, and later
  `rl_session.c` after the held-input fix. The telemetry ARM package was
  created successfully. The build still emits the existing third-party minizip
  `mktemp` linker warning.
- After the active-throw duplicate/start-order fix, `git diff --check`,
  `python3 -m py_compile tools/rl_probe_server.py tools/analyze_rl_transitions.py`,
  `cc -std=c11 -Wall -Wextra -Isrc -Iinclude -c src/rl/rl_combat_event.c -o /tmp/rl_combat_event_throw_refine3.o`,
  and `tools/mister/build-game.sh --flavor telemetry` passed. The telemetry
  build rebuilt `rl_combat_event.c` and `rl_session.c` and still emits the same
  third-party minizip `mktemp` linker warning.
- After the start-source split/recent-result guard, `git diff --check`,
  `python3 -m py_compile tools/rl_probe_server.py tools/analyze_rl_transitions.py`,
  `cc -std=c11 -Wall -Wextra -Isrc -Iinclude -c src/rl/rl_combat_event.c -o /tmp/rl_combat_event_throw_refine4.o`,
  and `tools/mister/build-game.sh --flavor telemetry` passed. The telemetry
  build rebuilt `rl_combat_event.c` and `rl_session.c`; the existing third-party
  minizip `mktemp` linker warning remains.
- After widening throw success confirm to 8 frames, `git diff --check`,
  `python3 -m py_compile tools/rl_probe_server.py tools/analyze_rl_transitions.py`,
  `cc -std=c11 -Wall -Wextra -Isrc -Iinclude -c src/rl/rl_combat_event.c -o /tmp/rl_combat_event_throw_confirm8.o`,
  and `tools/mister/build-game.sh --flavor telemetry` passed. The telemetry
  build rebuilt `rl_combat_event.c` and `rl_session.c`; the existing third-party
  minizip `mktemp` linker warning remains.

Follow-up:
- Phase 5D is live-accepted for close throw success, clean whiff, and
  mutual/tech-like conservative unknown. Phase 6 should improve side-complete
  attribution for mutual throws instead of treating the one-sided `CTR U` cases
  as Phase 5 bugs.

## 2026-05-05: Combat Event Phase 5C Throw Event Ring Foundation

Milestone:
- Milestone 6: Combat event attribution Phase 5C

Files changed:
- `src/rl/rl_combat_event.h`
- `src/rl/rl_combat_event.c`
- `src/rl/rl_session.h`
- `src/rl/rl_session.c`
- `src/rl/rl_observation.c`
- `docs/plan-remote-rl-agent.md`
- `docs/agent-memory/remote-rl-combat-event-attribution-plan.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- Add the first side-symmetric throw event ring and live Outcome counters, using
  the Phase 5B throw/caught evidence without promoting throw labels into reward
  or training features.

Implementation notes:
- Added self/opponent fixed-size throw rings in `rl_combat_event` with shared
  run-wide event ids, episode flush, no active-slot overwrite, and conservative
  success/whiff/unknown results.
- Throw starts come only from `self_throw_started` / `opp_throw_started`.
- Throw success (`CTR T`) requires target caught state/edge evidence.
- Throw whiff (`CTR W`) requires owner throw-active to end after the whiff
  window with no caught/contact/damage/HP/stun/interruption evidence.
- Throw unknown (`CTR U`) covers episode flush, timeout with conflicting
  evidence, possible tech-like cases, interruption, or ambiguous damage/contact
  without caught evidence.
- Outcome overlay now shows `CT S/F/A` and `CTR T/W/U` side-split counters.
- Transition schema remains v9; no reward, learner feature, or event-journal
  export adoption was added in this phase.

Validation:
- `git diff --check` passed.
- `python3 -m py_compile tools/rl_probe_server.py tools/analyze_rl_transitions.py` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed.

Follow-up:
- Phase 5D live validation should check self throw success, opponent throw
  success, clean throw whiff, ambiguous/tech-like cases, and pause-preserve
  behavior in the Outcome overlay.

## 2026-05-05: Combat Event Phase 5B Throw Observation Symmetry

Milestone:
- Milestone 6: Combat event attribution Phase 5B

Files changed:
- `src/rl/rl_observation.h`
- `src/rl/rl_observation.c`
- `src/rl/rl_session.c`
- `tools/rl_probe_server.py`
- `docs/plan-remote-rl-agent.md`
- `docs/agent-memory/remote-rl-combat-event-attribution-plan.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- Make raw throw/caught evidence self/opponent symmetric before adding a throw
  event ring. This avoids guessing opponent throws from HP/stun deltas or broad
  contact state alone.

Implementation notes:
- `RLObservationV1` now exposes both sides of `tsukami_f` and `tsukamare_f`:
  `self_throw_active`, `opp_throw_active`, `self_throw_caught`,
  `opp_throw_caught`, plus rising-edge fields for all four states.
- Transition schema bumped to v9 and exports the OR-accumulated throw evidence
  as root numeric fields:
  `self_throw_started`, `opp_throw_started`, `self_throw_caught_started`,
  `opp_throw_caught_started`, `self_throw_seen`, `opp_throw_seen`,
  `self_throw_caught_seen`, and `opp_throw_caught_seen`.
- The evidence bitmask v1 remains unchanged; the new symmetric fields are
  transition-root evidence for Phase 5C, not DQN features or throw result
  labels.
- Opponent-side combat attack updates now receive throw-active/caught evidence,
  matching the self-side protected-update path.
- The round-end HP sync guard now checks `self_throw_caught_started` for
  selected-side throw damage instead of the unrelated self throw-start edge.
- `tools/rl_probe_server.py` accepts schema v9 and preserves the new fields in
  `learner_replay_row()` so replay/import paths do not strip them.

Validation:
- `git diff --check` passed.
- `python3 -m py_compile tools/rl_probe_server.py tools/analyze_rl_transitions.py tools/train_dqn_learner.py tools/compare_dqn_models.py` passed.
- `PYTHONPATH=tools python3 -c '...'` schema-v9 throw replay smoke passed.
- `tools/mister/build-game.sh --flavor telemetry` passed.

Follow-up:
- Phase 5C can now add throw event start/result slots and `CT` / `CTR`
  counters using symmetric throw evidence, still with no reward/trainer
  adoption.

## 2026-05-05: Combat Event Phase 5A Throw Evidence Audit

Milestone:
- Milestone 6: Combat event attribution Phase 5A

Files changed:
- `docs/plan-remote-rl-agent.md`
- `docs/agent-memory/remote-rl-combat-event-attribution-plan.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- Start Phase 5 without prematurely adding a throw ring. Audit the throw
  evidence already present in observation/transition code and define the minimum
  symmetric evidence needed before throw result counters are safe.

Implementation notes:
- Documented the current throw-related raw signals:
  - self-side `tsukami_f` becomes `obs.self_throw_active`,
    `self_throw_started`, and `self_throw_seen`;
  - opponent-side `tsukamare_f` becomes `obs.opp_throw_caught`,
    `opp_throw_caught_started`, and `opp_throw_caught_seen`;
  - R1/R2 routine evidence can support throw attribution but must stay
    character-aware (`R1=2` catch, `R1=3` caught, Ryu `R2=14` grab startup,
    Ryu `R2=2` completed throw);
  - HP/stun deltas and close range are supporting evidence, not throw truth by
    themselves.
- Recorded the important asymmetry: current observation does not export
  `opp_throw_active`, `opp_throw_started`, `self_throw_caught`, or
  `self_throw_caught_started`, even though the previous-frame arrays track the
  raw game variables internally. Phase 5B must add this before a side-symmetric
  throw ring.
- Defined conservative planned semantics:
  - `throw_success`: owner throw-active/start plus target caught edge/state.
  - `throw_whiff`: owner throw-active ends with no caught/contact evidence
    inside the whiff window.
  - `throw_unknown`: timeout, possible tech, interruption, round end,
    conflicting contact evidence, or missing symmetric evidence.
- Defined the future Outcome overlay shape: `CT S/F/A` and `CTR T/W/U`, with
  side splits and no non-event/raw input text added back into `Outcome`.

Validation:
- `git diff --check` passed.

Follow-up:
- Implement Phase 5B symmetric throw observation fields before creating throw
  counters or result labels.
- Keep throw labels out of reward/trainer features until Phase 6 contact/delta
  matching can arbitrate attack/projectile/throw candidates.

## 2026-05-05: Combat Event Phase 4B Projectile Edge-Case Contract

Milestone:
- Milestone 6: Combat event attribution Phase 4B documentation closeout

Files changed:
- `docs/plan-remote-rl-agent.md`
- `docs/agent-memory/remote-rl-combat-event-attribution-plan.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- Record the projectile edge-case behavior that passed live MiSTer validation
  so later Phase 6/7 work has a stable contract for what Phase 4 owns and what
  remains intentionally conservative.

Implementation notes:
- Marked Phase 4 live validation complete in the main RL plan.
- Documented `CP` as projectile started/finalized/active counters and `CPR` as
  projectile result counters.
- Recorded the accepted result contract:
  - `CPR H`: clear damage / HP / stun evidence.
  - `CPR B`: explicit block reaction only.
  - `CPR X`: clean disappearance/expiry, including the accepted current clash
    behavior of `X +1/+1`.
  - `CPR U`: parry and evidence-insufficient projectile outcomes until Phase 6.
- Recorded that projectile-like parent attacks are projectile-claimed after
  spawn linkage, so `CPR` is the fireball outcome source of truth and `CEU R`
  should not be interpreted as projectile failure.
- Recorded that transient VS pause preserves combat counters.

Validation:
- User live report: pause preservation, fireball spawn, hit, block, fly-out,
  clash, parry, and parent `CEU R` cleanup all passed.
- `git diff --check` passed.

Follow-up:
- Phase 5 can proceed to throw tracking.
- Phase 6 should revisit parry and projectile clash as attribution/contact
  matching problems rather than Phase 4 lifecycle bugs.

## 2026-05-05: Combat Event Phase 4A Projectile Parent Cleanup

Milestone:
- Milestone 6: Combat event attribution Phase 4A live validation

Files changed:
- `src/rl/rl_combat_event.h`
- `src/rl/rl_combat_event.c`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- Address the remaining live overlay issue after projectile result
  classification was fixed: fireball hit/block now correctly reaches `CPR H`
  or `CPR B`, but the projectile-like parent attack still later increments
  `CEU R +1/+0` when the next same-side attack supersedes it.

Implementation notes:
- Added `RL_COMBAT_ATTACK_FINALIZE_PROJECTILE_CLAIMED` for projectile-like
  parent attacks whose result ownership has moved to a projectile event.
- When `RLCombatEvent_StartProjectile()` links a projectile to an active recent
  projectile-like attack, it now finalizes that parent attack immediately with
  the projectile-claimed reason.
- `RLCombatEvent_FindRecentProjectileAttack()` now only considers active
  projectile-like attacks, so a later projectile cannot attach to a stale
  finalized parent.
- The parent attack still contributes to `CE S/F`, but no longer increments
  `CEU R`; `CPR H/B/X/U` remains the source of truth for projectile outcome.

Validation:
- `git diff --check` passed.
- `cc -std=c11 -Wall -Wextra -Isrc -Iinclude -c src/rl/rl_combat_event.c -o /tmp/rl_combat_event_parent_cleanup.o`
  passed.
- `python3 -m py_compile tools/rl_probe_server.py tools/analyze_rl_transitions.py`
  passed.
- `tools/mister/build-game.sh --flavor telemetry` passed, rebuilding
  `rl_combat_event.c` and `rl_session.c` for ARM. The build still emits the
  existing third-party minizip `mktemp` linker warning.

## 2026-05-05: Combat Event Phase 4A Pause And Projectile Result Fix

Milestone:
- Milestone 6: Combat event attribution Phase 4A live validation

Files changed:
- `src/rl/rl_session.c`
- `src/rl/rl_combat_event.h`
- `src/rl/rl_combat_event.c`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- Fix the first live projectile/overlay validation issues reported from the
  `Outcome` page:
  - entering and leaving the pause menu reset `CE` / `CER` / `CP` / `CPR` /
    `CEU` counters;
  - broad projectile target evidence could invert hit/block results or turn a
    clean fireball disappearance into `CPR B`.

Implementation notes:
- Added a transient VS pause path that suspends RL action/output context without
  calling `RLSession_ResetRemoteRuntime(false)`, flushing the active combat
  episode, or resetting round-local combat counters.
- `RLSession_OnObservationFrameEnd()` now ignores pause frames for combat-event
  accumulation, so pause menu frames do not finalize or mutate attack/projectile
  event state.
- Projectile updates now latch an explicit target block-reaction signal from
  contact-reaction substates known to represent guard/block reactions
  (`routine[2]` 5 or 6). `routine[2]` 12 is deliberately not treated as block
  yet because existing fireball logs show it can also appear during post-hit
  reaction.
- Projectile result priority now prefers explicit block reaction for `CPR B`,
  clear damage/HP/stun evidence for `CPR H`, and clean disappearance for
  `CPR X`.
- Broad `guard_flag` / `entered_contact_state` evidence remains available for
  diagnostics, but by itself no longer forces blocked or unknown expiry.

Validation:
- `cc -std=c11 -Wall -Wextra -Isrc -Iinclude -c src/rl/rl_combat_event.c -o /tmp/rl_combat_event_phase4_fix.o`
  passed.
- `python3 -m py_compile tools/rl_probe_server.py tools/analyze_rl_transitions.py`
  passed.
- `git diff --check` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed, rebuilding
  `rl_combat_event.c` and `rl_session.c` for ARM. The build still emits the
  existing third-party minizip `mktemp` linker warning.

Follow-up:
- Rerun the live fireball matrix. Expected direction: pause no longer resets
  counters; fireball spawn still increments `CP S`; damaging fireballs prefer
  `CPR H`; blocked fireballs prefer `CPR B`; fly-out prefers `CPR X`.
- Parry and projectile-clash may still remain conservative `CPR U`/`CPR X`
  until Phase 6 contact matching adds consumed-delta and projectile-clash
  attribution.

## 2026-05-05: Combat Event Overlay Outcome Cleanup

Milestone:
- Milestone 6: Combat event attribution overlay refinement

Files changed:
- `src/rl/rl_observation.c`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- Make the RL debug `Outcome` page a combat-event-only page, so live validation
  no longer has to read CE/CP counters mixed with raw deltas, input heuristics,
  or the broad `All` bring-up view.

Implementation notes:
- Moved combat-event attack/projectile counters out of `All` and into
  `Outcome` only.
- Removed the older non-event `DH/DS/AB`, `EH/EC/ED`, and `RF/MS/AI/AR/OS`
  heuristic lines from `Outcome`.
- Promoted the detailed combat-event lines that were formerly `All`-only
  (`CEU`, `CEUC`, `CEUD`, `CEUH`, `CEUL`, `CEL`, `CELU`) into `Outcome`, so
  the page contains the full combat-event overlay set.

Validation:
- `git diff --check` passed.
- Standalone host compile of `rl_observation.c` is not representative because
  it depends on generated `port/build_config.h`; canonical MiSTer validation
  used the telemetry build instead.
- `tools/mister/build-game.sh --flavor telemetry` passed, rebuilding
  `rl_observation.c` for ARM. The build still emits the existing third-party
  minizip `mktemp` linker warning.

## 2026-05-05: Combat Event Phase 4A Projectile Lifecycle Foundation

Milestone:
- Milestone 6: Combat event attribution Phase 4A

Files changed:
- `src/rl/rl_combat_event.h`
- `src/rl/rl_combat_event.c`
- `src/rl/rl_session.h`
- `src/rl/rl_session.c`
- `src/rl/rl_observation.c`
- `tools/rl_probe_server.py`
- `docs/agent-memory/remote-rl-combat-event-attribution-plan.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- Start Phase 4 by giving projectiles their own lifecycle tracker instead of
  relying on delayed owner routine snapshots. This foundation is conservative:
  it records projectile spawn/active/finalize counters and links spawns to
  recent projectile-like attack events, but leaves exact contact consumption to
  the later matcher work.

Implementation notes:
- Added a fixed-size projectile event ring with shared monotonic event ids,
  owner side, optional `parent_attack_event_id`, spawn/last projectile position,
  velocity, time-to-self, and target contact/damage/guard evidence.
- Projectile finalization now classifies clear damage as hit, guarded contact
  as blocked, clean disappearance as expired, and ambiguous contact/clash as
  unknown.
- Because `RLObservationV1` currently exports only one selected projectile per
  frame, hidden owner-side projectiles are not immediately expired while any
  projectile is still visible. They finalize when no projectile is visible for
  a short missing window or when timeout is reached.
- Added OSD `CP` / `CPR` side-split counters and transition schema v8 projectile
  counter snapshots for live validation.

Validation:
- `cc -std=c11 -Wall -Wextra -Isrc -Iinclude -c src/rl/rl_combat_event.c -o /tmp/rl_combat_event_phase4.o`
  passed.
- `python3 -m py_compile tools/rl_probe_server.py tools/analyze_rl_transitions.py`
  passed.
- `git diff --check` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed, rebuilding
  `rl_combat_event.c`, `rl_observation.c`, and `rl_session.c` for ARM. The
  build still emits the existing third-party minizip `mktemp` linker warning.
- Live validation pending: fireball close/mid/far should increment `CP S/F/A`,
  blocked fireballs should prefer `CPR B`, damaging fireballs should prefer
  `CPR H`, and ambiguous fireball clashes may remain `CPR X` or `CPR U`.

## 2026-05-05: Combat Event Phase 3 Side-Explicit Engine Attribution

Milestone:
- Milestone 6: Combat event attribution Phase 3

Files changed:
- `src/rl/rl_combat_event.h`
- `src/rl/rl_combat_event.c`
- `src/rl/rl_session.c`
- `tools/rl_probe_server.py`
- `tools/analyze_rl_transitions.py`
- `docs/agent-memory/remote-rl-combat-event-attribution-plan.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- Start Phase 3 after Phase 2 live overlay smoke stabilized strike whiff
  classification. Make engine attribution side-explicit so self and opponent
  attacks can both be named without reusing ambiguous generic `engine_*`
  ownership.

Implementation notes:
- Bumped transition schema to `7` and added root-level `self_engine_*` and
  `opp_engine_*` fields. Generic `engine_*` remains a deprecated self-side
  alias for compatibility.
- Replaced the self-only engine mapper with a side-local mapper that uses the
  actor's own routine/current-attack/kind-of-waza/start-edge evidence.
- Attack-event starts now store side-local engine action/sub-action,
  routine 1/2, current attack, kind-of-waza, label source, and lag frames.
- Opponent Ryu specials/projectile-like starts can now mark opponent events as
  projectile-like without borrowing self policy labels. Unsupported characters
  stay unknown.
- Python helpers accept schema `7`, preserve side-explicit fields in learner
  replay rows, and prefer `self_engine_*` over generic `engine_*` for self-side
  engine-outcome compatibility.

Validation:
- `git diff --check` passed.
- `cc -std=c11 -Wall -Wextra -Isrc -Iinclude -c src/rl/rl_combat_event.c -o /tmp/rl_combat_event_wall.o`
  passed.
- `python3 -m py_compile tools/rl_probe_server.py tools/analyze_rl_transitions.py`
  passed.
- Standalone `rl_session.c` compile is not representative because it depends on
  generated `port/build_config.h`; canonical MiSTer validation used the
  telemetry build instead.
- `tools/mister/build-game.sh --flavor telemetry` passed, rebuilding the
  touched RL C files for ARM. The build still emits the existing third-party
  minizip `mktemp` linker warning.
- Live validation passed with `logs/phase3-side-engine-live.ndjson`: schema v7
  had 15 self engine labels, 22 opponent engine labels, 0 generic/self
  mismatches, and 0 opponent pollution in generic `engine_*` across four visual
  side swaps.

## 2026-05-05: Combat Event EC-Only Whiff Refinement

Milestone:
- Milestone 6: Combat event attribution Phase 2 live overlay smoke refinement

Files changed:
- `src/rl/rl_session.c`
- `docs/agent-memory/remote-rl-combat-event-attribution-plan.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- Fix live simultaneous-whiff cases where both sides started attacks, but the
  opponent side ended as timeout unknown: `CEUC C +0/+1`, `CEUD EC +0/+1`, and
  no `EH`, `ED`, `HP`, `ST`, projectile, throw, projectile-like, or not-whiff
  cause.

Implementation notes:
- `entered_contact_state` remains latched and visible as `CEUD EC`.
- `entered_contact_state` no longer contributes to `target_contact_or_damage`
  by itself. Strong target contact/damage for Phase 2 basic whiff now requires
  entered hit-stop, entered damage-state, HP delta, or stun delta.
- This keeps broad `guard_flag` / contact-state edges from turning visible
  clean whiffs into timeout unknowns.
- Transition JSON, rewards, inference, trainer features, and event-journal
  export are unchanged.

Validation:
- `git diff --check` passed.
- `cc -std=c11 -Wall -Wextra -Isrc -Iinclude -c src/rl/rl_combat_event.c -o /tmp/rl_combat_event_wall.o` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed and rebuilt
  `src/rl/rl_session.c`; only the pre-existing minizip `mktemp` linker warning
  appeared.

## 2026-05-05: Combat Event Contact Cause Overlay

Milestone:
- Milestone 6: Combat event attribution Phase 2 live overlay smoke refinement

Files changed:
- `src/rl/rl_combat_event.h`
- `src/rl/rl_combat_event.c`
- `src/rl/rl_session.h`
- `src/rl/rl_session.c`
- `src/rl/rl_observation.c`
- `docs/agent-memory/remote-rl-combat-event-attribution-plan.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- Split timeout-unknown contact/damage causes after live testing showed
  simultaneous whiffs as `CER W +1/+0, U +0/+1`, with `CEUC C +0/+1` and no
  projectile/throw/projectile-like/not-whiff cause movement.

Implementation notes:
- Attack events now latch the individual target contact contributors that feed
  `target_contact_or_damage`: entered hit-stop, entered contact-state, entered
  damage-state, HP delta, and stun delta.
- All view now adds `CEUD EHself/opp ECself/opp EDself/opp` and
  `CEUH HPself/opp STself/opp`.
- This is diagnostic-only. Event lifecycle behavior, transition JSON, reward,
  inference, trainer features, and event-journal export are unchanged.

Validation:
- `git diff --check` passed.
- `cc -std=c11 -Wall -Wextra -Isrc -Iinclude -c src/rl/rl_combat_event.c -o /tmp/rl_combat_event_wall.o` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed and rebuilt the RL
  combat/session/observation objects plus touched game/menu objects; only the
  pre-existing minizip `mktemp` linker warning appeared.

## 2026-05-05: Combat Event Overlay Input Legend Cleanup

Milestone:
- Milestone 6: Combat event attribution Phase 2 live overlay smoke refinement

Files changed:
- `src/port/sdl/sdl_app.c`
- `src/port/sdl/fbdev_presenter.h`
- `src/port/sdl/fbdev_presenter.c`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- Remove the `U D L R LP MP HP LK MK HK` input-token legend from `All` and
  `Outcome` RL debug overlay views so combat-event counters are easier to read
  during live smoke testing.

Implementation notes:
- The input legend now renders only when `rl-debug-view=input`.
- Desktop renderer sizing and MiSTer fbdev overlay rasterization both use the
  same visibility rule.
- Observation packets, transition logs, combat-event lifecycle, rewards,
  inference, and trainer features are unchanged.

Validation:
- `git diff --check` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed and rebuilt
  `src/port/sdl/fbdev_presenter.c` plus `src/port/sdl/sdl_app.c`; only the
  pre-existing minizip `mktemp` linker warning appeared.

## 2026-05-05: Combat Event Attribution Timeout Cause Overlay

Milestone:
- Milestone 6: Combat event attribution Phase 2 live overlay smoke refinement

Files changed:
- `src/rl/rl_combat_event.h`
- `src/rl/rl_combat_event.c`
- `src/rl/rl_session.h`
- `src/rl/rl_session.c`
- `src/rl/rl_observation.c`
- `docs/agent-memory/remote-rl-combat-event-attribution-plan.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- Diagnose live cases where simultaneous self/opponent whiffs show `S1/1` but
  one side goes to timeout unknown.

Implementation notes:
- Added round-local self/opponent timeout-unknown cause counters for:
  target contact/damage evidence, projectile evidence, throw evidence,
  projectile-like action evidence, and not-whiff-eligible events.
- All view now adds:
  `CEUC Cself/opp Pself/opp Tself/opp` and
  `CEUL Lself/opp Nself/opp`.
- Outcome/event lifecycle, transition JSON, reward, inference, trainer, and
  event-journal export behavior are unchanged.

Validation:
- `git diff --check` passed.
- `cc -std=c11 -Wall -Wextra -Isrc -Iinclude -c src/rl/rl_combat_event.c -o /tmp/rl_combat_event_wall.o` passed.
- `/tmp/rl_combat_event_u_cause_smoke` passed: timeout unknown causes were
  counted on the correct self/opponent side.
- `tools/mister/build-game.sh --flavor telemetry` passed and rebuilt the RL and
  touched game/menu objects; only the pre-existing minizip `mktemp` linker
  warning appeared.

Follow-up:
- In the next All-view smoke, inspect the side that goes `U`: `C`, `P`, `T`,
  `L`, or `N` indicates which protection latch blocked clean whiff.

## 2026-05-05: Combat Event Attribution Side-Split Overlay Stats

Milestone:
- Milestone 6: Combat event attribution Phase 2 live overlay smoke refinement

Files changed:
- `src/rl/rl_combat_event.h`
- `src/rl/rl_combat_event.c`
- `src/rl/rl_session.h`
- `src/rl/rl_session.c`
- `src/rl/rl_observation.c`
- `docs/agent-memory/remote-rl-combat-event-attribution-plan.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- Diagnose live cases where simultaneous self/opponent whiffs show `S+2` but
  only `W+1`.

Implementation notes:
- Added round-local self/opponent counters for attack starts, finalizations,
  whiffs, interrupts, timeout unknowns, flush unknowns, rollover unknowns, and
  dropped starts.
- Outcome overlay now shows `CE Sself/opp Fself/opp Aself/opp` and
  `CER Wself/opp Iself/opp Uself/opp`.
- All view now shows `CEU Fself/opp Rself/opp Dself/opp`.
- Lifetime `CEL` / `CELU` totals remain total-only.
- No event lifecycle, transition JSON, reward, inference, trainer, or
  event-journal export behavior changed.

Validation:
- `git diff --check` passed.
- `cc -std=c11 -Wall -Wextra -Isrc -Iinclude -c src/rl/rl_combat_event.c -o /tmp/rl_combat_event_wall.o` passed.
- `/tmp/rl_combat_event_side_split_smoke` passed: simultaneous self/opponent
  clean whiffs produced split starts and split whiffs of `1/1`, and a
  self-side protected timeout incremented only self-side `U`.
- `tools/mister/build-game.sh --flavor telemetry` passed and rebuilt the RL and
  touched game/menu objects; only the pre-existing minizip `mktemp` linker
  warning appeared.

Follow-up:
- In the next live smoke, read `CE Sx/y` and `CER Wx/y Ux/y Ix/y`: if starts
  are `1/1` but whiffs are `1/0`, the missing side should now be visible as
  active, interrupted, timeout unknown, or rollover unknown.

## 2026-05-05: Combat Event Attribution Clean Rollover Whiff Fix

Milestone:
- Milestone 6: Combat event attribution Phase 2 live overlay smoke refinement

Files changed:
- `src/rl/rl_combat_event.c`
- `docs/agent-memory/remote-rl-combat-event-attribution-plan.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- Reduce intermittent `CEU ... R` rollover-unknown increments during live
  overlay validation.

Implementation notes:
- `R` means a same-side new attack start arrived while the previous same-side
  event was still active.
- Clean superseded events now finalize as `WHIFF + BASIC_WHIFF_WINDOW` instead
  of `UNKNOWN + SUPERSEDED_BY_NEW_START`.
- Contact-protected, projectile-like, and throw-protected superseded events
  still remain rollover unknowns because Phase 2 does not yet resolve those
  outcomes.
- No transition JSON, reward, inference, trainer, or event-journal export
  behavior changed.

Validation:
- `git diff --check` passed.
- `cc -std=c11 -Wall -Wextra -Isrc -Iinclude -c src/rl/rl_combat_event.c -o /tmp/rl_combat_event_wall.o` passed.
- `/tmp/rl_combat_event_rollover_whiff_smoke` passed: clean rollover became
  whiff, fast clean rollover tolerated projectile noise, and contact /
  projectile-like rollovers remained `R`.
- `tools/mister/build-game.sh --flavor telemetry` passed and rebuilt
  `src/rl/rl_combat_event.c`; only the pre-existing minizip `mktemp` linker
  warning appeared.

Follow-up:
- Rerun the Outcome / All overlay smoke. Occasional `R` after this change
  should mostly correspond to protected ambiguous events, not ordinary clean
  whiffs being superseded by the next attack.

## 2026-05-05: Combat Event Attribution Timeout Unknown Cleanup

Milestone:
- Milestone 6: Combat event attribution Phase 2 live overlay smoke refinement

Files changed:
- `src/rl/rl_combat_event.h`
- `src/rl/rl_combat_event.c`
- `src/rl/rl_session.c`
- `docs/agent-memory/remote-rl-combat-event-attribution-plan.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- Reduce excessive round-local `CE ... U` counts and fix remaining quick LP
  whiff misses observed during live overlay validation.

Implementation notes:
- Clean non-projectile events that reach the basic pending timeout without
  target contact/damage, projectile, throw, or projectile-like evidence now
  finalize as `WHIFF` instead of timeout `UNKNOWN`.
- Normal LP starts now carry `fast_whiff_fallback`; if they remain clean for
  20 frames they finalize as `WHIFF` even when the active-window signal stays
  sticky.
- The fast LP fallback intentionally ignores unrelated same-side projectile
  noise, but still refuses to whiff if target contact/damage, throw evidence,
  or projectile-like action evidence is present.
- Contact/projectile-like/throw-protected events still remain `UNKNOWN` until
  later attribution phases add explicit hit/block/projectile/throw resolvers.
- No transition JSON, reward, inference, trainer, or event-journal export
  behavior changed.

Validation:
- `git diff --check` passed.
- `cc -std=c11 -Wall -Wextra -Isrc -Iinclude -c src/rl/rl_combat_event.c -o /tmp/rl_combat_event_wall.o` passed.
- `/tmp/rl_combat_event_unknown_whiff_smoke` passed: fast LP whiffed despite
  sticky active/projectile noise, clean non-fast timeouts became whiff, and
  contact/projectile-like protected timeouts remained unknown.
- `tools/mister/build-game.sh --flavor telemetry` passed and rebuilt
  `src/rl/rl_combat_event.c` plus `src/rl/rl_session.c`; only the pre-existing
  minizip `mktemp` linker warning appeared.

Follow-up:
- Rerun the Outcome overlay smoke. A high `U` count after this change should
  mostly indicate contact/projectile-like/throw-protected events, not clean
  whiffs leaking to timeout.

## 2026-05-05: Combat Event Attribution Fast Light Whiff Fix

Milestone:
- Milestone 6: Combat event attribution Phase 2 live overlay smoke refinement

Files changed:
- `src/rl/rl_combat_event.h`
- `src/rl/rl_combat_event.c`
- `docs/agent-memory/remote-rl-combat-event-attribution-plan.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- Fix live overlay behavior where quick LP whiffs could start an attack event
  but fail to increment `CE ... W`.

Implementation notes:
- The previous live-smoke fix required an event to separately observe routine
  attack state before it could finalize as `WHIFF`. That avoided sticky
  `current_attack`, but it was too strict for very short light attacks.
- Attack events now become `whiff_eligible` at accepted start time. Routine
  attack state is still the active-window signal, so sticky `current_attack`
  still cannot keep an event artificially active.
- Contact/projectile/throw/protected events still do not become basic whiffs.
- No transition JSON, reward, inference, trainer, or event-journal export
  behavior changed.

Validation:
- `git diff --check` passed.
- `cc -std=c11 -Wall -Wextra -Isrc -Iinclude -c src/rl/rl_combat_event.c -o /tmp/rl_combat_event_wall.o` passed.
- `/tmp/rl_combat_event_fast_whiff_smoke` passed: an accepted short attack
  start without a routine-active latch became `WHIFF`, routine-active attacks
  still whiffed after exit, and contact-protected events did not whiff.
- `tools/mister/build-game.sh --flavor telemetry` passed and rebuilt
  `src/rl/rl_combat_event.c` plus `src/rl/rl_session.c`; only the pre-existing
  minizip `mktemp` linker warning appeared.

Follow-up:
- During the next Outcome overlay smoke, specifically test repeated standing LP
  or crouching LP at whiff range and confirm round-local `W` tracks them.

## 2026-05-05: Combat Event Attribution Round-Local Overlay Stats

Milestone:
- Milestone 6: Combat event attribution Phase 2 live overlay smoke refinement

Files changed:
- `src/rl/rl_combat_event.h`
- `src/rl/rl_combat_event.c`
- `src/rl/rl_session.h`
- `src/rl/rl_session.c`
- `src/rl/rl_observation.c`
- `docs/agent-memory/remote-rl-combat-event-attribution-plan.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- Make combat-event OSD stats easier to validate by eye during live round
  testing.

Implementation notes:
- Existing `CE` / `CEU` counters are now round-local and reset at
  `RLCombatEvent_BeginEpisode()`.
- Event ids and `next_event_id` remain run-wide and monotonic across rounds.
- Added lifetime combat-event counters to `RLCombatEventStats` and
  `RLRemoteDebugState`.
- `All` overlay view now adds `CEL S/F/W/I/U` and `CELU F/R/D` lifetime lines
  for long-run health checks, while the regular Outcome view stays focused on
  current-round behavior.
- No transition JSON, reward, inference, trainer, or event-journal export
  behavior changed.

Validation:
- `git diff --check` passed.
- `cc -std=c11 -Wall -Wextra -Isrc -Iinclude -c src/rl/rl_combat_event.c -o /tmp/rl_combat_event_wall.o` passed.
- `/tmp/rl_combat_event_episode_stats_smoke` passed: round-local start/whiff
  counts reset on episode begin, lifetime counts persisted, and event ids kept
  increasing across episodes.
- `tools/mister/build-game.sh --flavor telemetry` passed and rebuilt the RL and
  touched game/menu objects; only the pre-existing minizip `mktemp` linker
  warning appeared.

Follow-up:
- During the next MiSTer live smoke, use Outcome view for per-round `CE` /
  `CEU` validation and All view only when checking lifetime drift or dropped
  starts.

## 2026-05-05: Combat Event Attribution Phase 2 Whiff Lifecycle Live Fix

Milestone:
- Milestone 6: Combat event attribution Phase 2 live overlay smoke refinement

Files changed:
- `src/rl/rl_combat_event.h`
- `src/rl/rl_combat_event.c`
- `src/rl/rl_session.c`
- `docs/agent-memory/remote-rl-combat-event-attribution-plan.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- Fix live overlay behavior where `CE ... W` rarely increased during visible
  whiffs.

Implementation notes:
- Live testing showed the basic whiff lifecycle was too strict because
  `actor_attack_state_active` treated nonzero `current_attack` as active. That
  value is useful attack identity/context evidence, but it can remain sticky
  after visible recovery.
- `RLSession_FillCombatAttackUpdate()` now uses routine attack state as the
  active-window signal for self and opponent attack events.
- `RLCombatAttackEvent` now latches `saw_actor_attack_state_active`; basic
  whiff finalization requires this latch before counting `WHIFF`, so edge-only
  starts that never enter attack routine do not become false whiffs.
- No transition JSON, reward, inference, trainer, or event-journal export
  behavior changed.

Validation:
- `git diff --check` passed.
- `cc -std=c11 -Wall -Wextra -Isrc -Iinclude -c src/rl/rl_combat_event.c -o /tmp/rl_combat_event_wall.o` passed.
- `/tmp/rl_combat_event_sticky_whiff_smoke` passed: a routine-active event
  whiffed after routine exit, while a start that never observed routine active
  did not increment whiff.
- `tools/mister/build-game.sh --flavor telemetry` passed and rebuilt
  `src/rl/rl_combat_event.c` plus `src/rl/rl_session.c`; only the pre-existing
  minizip `mktemp` linker warning appeared.

Follow-up:
- Deploy this telemetry build and rerun the Outcome overlay smoke. `W` should
  now move for clean visible non-projectile whiffs; projectile/throw/contact
  protected events should still avoid `W` until later attribution phases.

## 2026-05-05: Combat Event Attribution Phase 2D Debug Visibility

Milestone:
- Milestone 6: Combat event attribution Phase 2D

Files changed:
- `src/rl/rl_session.h`
- `src/rl/rl_session.c`
- `src/rl/rl_observation.c`
- `docs/agent-memory/remote-rl-combat-event-attribution-plan.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- Make Phase 2 attack event lifecycle visible during live MiSTer testing without
  changing transition NDJSON, reward, inference, or trainer features.

Implementation notes:
- Added combat-event counters to `RLRemoteDebugState`:
  started, finalized, whiff, interrupted, timeout unknown, episode-flush
  unknown, rollover unknown, dropped starts, and active self/opponent counts.
- `RLSession_GetRemoteDebugState()` now snapshots `RLCombatEvent_GetStats()` so
  overlay/debug readers see current event-ring stats.
- The outcome debug overlay adds:
  `CE S/F Aself/opp W/I/U`, where `U` is timeout unknown.
- The all-view overlay also adds `CEU F/R/D` for episode-flush unknown,
  rollover unknown, and dropped start counts.

Non-goals:
- No temporary transition-log fields and no partial event journal export. Disk
  analyzer visibility stays with Phase 7 so schema and two-file persistence
  remain coherent.
- No reward, inference, model metadata, or trainer feature change.

Validation:
- `git diff --check` passed.
- `cc -std=c11 -Wall -Wextra -Isrc -Iinclude -c src/rl/rl_combat_event.c -o /tmp/rl_combat_event_wall.o` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed and rebuilt
  `src/rl/rl_observation.c` plus `src/rl/rl_session.c`; only the pre-existing
  minizip `mktemp` linker warning appeared.

Follow-up:
- Deploy a telemetry build and use the RL outcome/all debug overlay to compare
  combat-event counts against visible attacks before moving to Phase 3 or
  Phase 7 export work.

## 2026-05-05: Combat Event Attribution Phase 2C Basic Attack Finalization

Milestone:
- Milestone 6: Combat event attribution Phase 2C

Files changed:
- `src/rl/rl_combat_event.h`
- `src/rl/rl_combat_event.c`
- `src/rl/rl_session.c`
- `docs/agent-memory/remote-rl-combat-event-attribution-plan.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- Give Phase 2 attack events a conservative lifecycle beyond rollover and
  episode flush, without implementing hit/block/projectile/throw attribution.

Implementation notes:
- Added basic finalize reasons:
  `BASIC_WHIFF_WINDOW`, `BASIC_INTERRUPTED`, and `BASIC_UNKNOWN_TIMEOUT`.
- Added event-side evidence latches:
  `saw_target_contact_or_damage`, `saw_projectile`, `saw_throw`, and
  `projectile_like`.
- `RLCombatEvent_UpdateActiveAttacks()` now applies the basic lifecycle:
  clean non-projectile attacks can become `WHIFF` after leaving attack state and
  reaching the minimum whiff age; actor damage/stun can become `INTERRUPTED` if
  target contact/damage was not already seen; protected/long-lived events become
  `UNKNOWN` at timeout.
- Projectile-like self policy actions and events that observed a same-side
  projectile do not become basic whiffs; they use the longer projectile timeout
  and remain `UNKNOWN` until Phase 4 projectile tracking exists.
- `rl_session.c` now builds per-side update facts from the active ledger row and
  current observation/delta facts, then updates both self and opponent active
  attack events every frame with an active ledger entry.

Non-goals:
- No event export, transition summary, reward, inference, or trainer feature
  change.
- No hit/block/contact attribution, projectile lifecycle, throw lifecycle,
  punish detection, or confidence/failure-reason model.

Validation:
- `git diff --check` passed.
- `cc -std=c11 -Wall -Wextra -Isrc -Iinclude -c src/rl/rl_combat_event.c -o /tmp/rl_combat_event_wall.o` passed.
- Standalone finalization smoke compiled and ran against
  `src/rl/rl_combat_event.c`; it verified basic whiff, basic interrupted,
  contact-protected unknown timeout, projectile-like extended timeout, and final
  active-count cleanup.
- `tools/mister/build-game.sh --flavor telemetry` passed and rebuilt
  `src/rl/rl_combat_event.c` plus `src/rl/rl_session.c`; only the pre-existing
  minizip `mktemp` linker warning appeared.

Follow-up:
- Phase 2D should expose debug/analyzer visibility for event counts/results so
  a live run can compare attack-start/finalization counts against visible
  attempts before event journal export.

## 2026-05-05: Combat Event Attribution Phase 2B Attack Start Events

Milestone:
- Milestone 6: Combat event attribution Phase 2B

Files changed:
- `src/rl/rl_combat_event.h`
- `src/rl/rl_combat_event.c`
- `src/rl/rl_session.c`
- `docs/agent-memory/remote-rl-combat-event-attribution-plan.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- Start creating attack events from existing self/opponent observation edges
  while keeping event labels out of transition JSON, reward, inference, and
  trainer features.

Implementation notes:
- Added `RLCombatEvent_FinalizeActiveSide()` for conservative ring hygiene.
  When a side starts a new attack while a previous same-side event is still
  active, the previous event is finalized as
  `UNKNOWN + SUPERSEDED_BY_NEW_START`.
- `RLSession_AccumulateAttackSignals()` now starts self/opponent attack events
  from the existing observation edge signals:
  `*_attack_started`, `*_attack_counter_started`, or
  `*_attack_routine_started`.
- Attack starts attach run id, episode id, decision id, frame id, side,
  character id, routine 1/2, current attack, and kind-of-waza.
- Self-side events additionally attach the best available policy/input context:
  executed policy action first, then demo/input label, then requested policy.
- Opponent events intentionally do not guess a policy action id yet; side-explicit
  engine attribution remains Phase 3.

Non-goals:
- No hit/block/contact attribution.
- No projectile, throw, punish, defense result, event journal export,
  transition summary, reward, or learner-feature change.

Validation:
- `git diff --check` passed.
- `cc -std=c11 -Wall -Wextra -Isrc -Iinclude -c src/rl/rl_combat_event.c -o /tmp/rl_combat_event_wall.o` passed.
- Standalone rollover smoke compiled and ran against `src/rl/rl_combat_event.c`;
  it verified same-side active rollover, side isolation, policy context storage,
  and episode flush.
- `tools/mister/build-game.sh --flavor telemetry` passed and rebuilt
  `src/rl/rl_combat_event.c` plus `src/rl/rl_session.c`; only the pre-existing
  minizip `mktemp` linker warning appeared.

Follow-up:
- Phase 2C should add basic non-projectile finalization windows for
  whiff/interrupted/unknown. Phase 2D should expose debug/analyzer visibility so
  live logs can compare event counts against visible attempts before event
  journal export.

## 2026-05-05: Combat Event Attribution Phase 2A Attack Ring Foundation

Milestone:
- Milestone 6: Combat event attribution Phase 2A

Files changed:
- `src/rl/rl_combat_event.h`
- `src/rl/rl_combat_event.c`
- `src/rl/rl_session.c`
- `docs/agent-memory/remote-rl-combat-event-attribution-plan.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- Start Phase 2 by adding the C-side attack-event ring foundation before attack
  start detection, result resolution, event export, or trainer adoption.

Implementation notes:
- Extended `rl_combat_event.h` beyond the Phase 0+1 bit constants with Phase 2
  attack-event types only: side, status, result, finalize reason, start record,
  attack event record, and stats.
- Added `src/rl/rl_combat_event.c` with fixed-size self/opponent attack rings.
- Event ids are run-wide monotonic `u64` values with `0` reserved for no event.
- Ring allocation reuses only empty/finalized slots; if every slot is active,
  the start request is dropped and counted instead of overwriting a pending
  event.
- Episode flush finalizes matching active events as `UNKNOWN` with
  `EPISODE_FLUSH` reason so active events cannot leak across rounds.
- Wired `rl_session.c` lifecycle hooks:
  `RLCombatEvent_ResetRun()` when a run id is created or counters reset,
  `RLCombatEvent_BeginEpisode()` when a new episode starts, and
  `RLCombatEvent_FlushEpisode()` from episode finalize/reset paths.

Non-goals:
- No attack-start detection yet.
- No projectile, throw, punish, contact matching, event journal export,
  transition schema change, reward change, or learner feature change.

Validation:
- `git diff --check` passed.
- `cc -std=c11 -Wall -Wextra -Isrc -Iinclude -c src/rl/rl_combat_event.c -o /tmp/rl_combat_event_wall.o` passed.
- Standalone smoke compiled and ran against `src/rl/rl_combat_event.c`; it
  verified event id allocation, active self count, explicit finalize, episode
  flush-to-unknown, and ring clearing on episode begin.
- `tools/mister/build-game.sh --flavor telemetry` passed and rebuilt
  `src/rl/rl_combat_event.c` plus `src/rl/rl_session.c`; only the pre-existing
  minizip `mktemp` linker warning appeared.

Follow-up:
- Phase 2B should create self/opponent attack events from observation
  attack-start edges and attach raw routine/current-attack/policy context while
  keeping event labels out of rewards and learner features.

## 2026-05-05: Combat Event Attribution Phase 0+1 Live Gate Smoke

Milestone:
- Milestone 6: Combat event attribution Phase 0+1 live validation

Inputs:
- `logs/dqn-retrain-m3-defense-v10_event_off.ndjson`
- `logs/dqn-retrain-m3-defense-v10_event_on.ndjson`

Purpose:
- Verify the C-side evidence gate and compact bitmask export under live MiSTer
  network logging before moving to later combat-event phases.

Results:
- Gate off: 995 rows, zero JSON errors, schema v6 rows only, no evidence keys
  present, and max row length 1752 bytes.
- Gate on: 1070 rows, zero JSON errors, schema v6 rows only, every row carried
  exactly the six Phase 0+1 evidence fields, and max row length 1937 bytes.
- `tools/analyze_rl_transitions.py --expand-evidence --output-expanded` expanded
  the gate-on log and handled the gate-off log as missing evidence without
  crashing.
- Python evidence decode found no reserved bits, no negative flag values, and no
  nonzero `evidence_flags_hi` values in the natural live run.
- DQN/replay feature safety remained intact: evidence and `ep_overlay_` fields
  did not enter default learner replay rows or `DQN_FEATURE_NAMES`.
- Episode counter lifecycle passed: `ep_overlay_attack_*_count` reset at the
  second episode boundary and remained monotonic inside episodes.

Known limitation confirmed:
- One row showed overlay counters jump by two while Phase 0+1 boolean evidence
  can only report one `overlay_attack_event_finalized` bit. This is expected for
  Phase 0+1; Phase 2+ event journals are needed for one-row-per-event truth.

Performance decision:
- No visible live performance issue was observed. Because the gate-on max row is
  still comfortably below the 4096-byte formatter buffer, explicit sub-ms
  formatter timing is deferred until the full combat-event log/export path is
  implemented, or until an intermediate live test shows visible performance
  symptoms.

## 2026-05-05: Combat Event Attribution Phase 0+1 Local Implementation

Milestone:
- Milestone 6: Combat event attribution Phase 0+1 local implementation

Files changed:
- `src/rl/rl_session.c`
- `src/rl/rl_session.h`
- `src/rl/rl_net.c`
- `src/rl/rl_combat_event.h`
- `src/configuration.h`
- `src/args.c`
- `src/main.c`
- `src/port/config/config.h`
- `src/port/config/config.c`
- `vendor/Menu_MiSTer/menu.sv`
- `vendor/Main_MiSTer/thirdsarm_wrapper.cpp`
- `tools/rl_evidence.py`
- `tools/analyze_rl_transitions.py`
- `tools/rl_probe_server.py`
- `tools/train_dqn_learner.py`
- `docs/config.md`
- `docs/agent-memory/remote-rl-combat-event-attribution-plan.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- Land the Phase 0+1 compact evidence-export foundation while keeping reward,
  inference, action scheduling, and default learner features unchanged.

Implementation notes:
- Added `src/rl/rl_combat_event.h` with only Phase 0+1 bitmask version and
  bit-position constants. No `.c` file, event ring, event id, resolver helper,
  source/confidence/failure enum, or result enum was added.
- Replaced the transition formatter's stack `line[2048]` path with a reusable
  4096-byte heap buffer owned by `rl_session.c` and allocated/freed via
  `RLSession_AllocFormatBuffer()` / `RLSession_FreeFormatBuffer()` from the RL
  net lifecycle.
- Refactored transition formatting into append-style guarded writes. Base-row
  formatting failure drops the row; evidence-extension failure clears the
  partial buffer, retries a complete base row, and increments evidence fallback
  telemetry.
- Added transition-format telemetry counters for formatter errors,
  truncations, and evidence fallback.
- Added `rl-agent-export-evidence` as a config/CLI/OSD-backed runtime gate.
  MiSTer OSD exposes it as `RL Evidence Log (Restart)`. Default is off.
- When the gate is on and evidence formatting succeeds, transition rows add
  exactly six numeric root fields: `evidence_bitmask_version`,
  `evidence_flags_lo`, `evidence_flags_hi`, and the three
  `ep_overlay_attack_*_count` fields.
- Updated overlay evidence consumption so per-decision overlay contact/whiff
  evidence is consumed from unlogged finalized overlay sequence state rather
  than read directly from transient `last_overlay_*` at transition formatting
  time.
- Added `tools/rl_evidence.py` and analyzer `--expand-evidence
  --output-expanded` support. The decoder rejects negative/out-of-range
  unsigned flag values before masking, expands v1 known bits, and reports
  reserved hi/lo bits.
- Added DQN model/feature metadata guards that warn and strip
  `evidence_*`/`ep_overlay_*` feature names if a future model accidentally
  includes them.

Validation:
- `git diff --check` passed.
- `python3 -m py_compile tools/rl_evidence.py tools/analyze_rl_transitions.py tools/rl_probe_server.py tools/train_dqn_learner.py tools/compare_dqn_models.py` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed and produced
  `build/mister-telemetry-package`.
- `tools/mister-wrapper/build-hps.sh` passed and produced
  `build/mister-wrapper-hps/MiSTer_3S-ARM`; it reported only pre-existing
  wrapper warnings for unused scale-mode helpers and `input.cpp`'s unused
  `poll_cnt`.
- Synthetic analyzer smoke passed:
  `python3 tools/analyze_rl_transitions.py /tmp/rl-evidence-smoke.ndjson --expand-evidence --output-expanded /tmp/rl-evidence-expanded.ndjson --limit 3`.
  It expanded v1 bits, left unknown version `99` as `evidence_expanded=null`,
  and emitted the expected reserved hi-bit warning for
  `evidence_flags_hi=0x80000000`.
- Negative flag smoke failed as intended with
  `evidence_flags_lo must be non-negative before masking`.
- Feature-name guard smoke stripped synthetic
  `evidence_flags_lo` / `ep_overlay_attack_active_count` feature names and
  kept only normal DQN feature names.

Open follow-ups:
- Full combat-event phases still need the Phase 2+ event journal, side-explicit
  attribution, projectile/throw/punish coverage, and event-aware analyzer work.
- Explicit formatter p95/p99 timing is deferred until the full combat-event
  export path is implemented, or until live/intermediate tests show a visible
  performance issue.

## 2026-05-05: Overlay Evidence Contamination Guard

Milestone:
- Milestone 6: harden Phase 0+1 overlay evidence semantics

Files changed:
- `docs/agent-memory/remote-rl-combat-event-attribution-plan.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- Prevent per-decision overlay contact/whiff evidence from being overwritten by
  later frames before transition export.

Key updates:
- Clarified that `ep_overlay_attack_*_count` values are cumulative snapshots;
  later frames increasing those counters is expected and not contamination as
  long as analyzers treat them as episode-cumulative counters.
- Per-decision `overlay_attack_event_finalized`, `overlay_attack_contact`, and
  `overlay_attack_whiff` must be latched from finalized overlay event sequence
  evidence, not read from transient `last_overlay_*` state at transition
  formatting time.
- A ledger row must consume only unlogged finalized overlay event evidence, and
  consumed sequence ids must be marked so later rows cannot duplicate them.
- If multiple overlay events finalize in one decision window and Phase 0+1 can
  only represent a boolean summary, the limitation must remain evidence-only
  and be recorded in the audit/engineering log; Phase 2+ event journals carry
  the one-row-per-event truth model.
- Added overlay contamination smoke to verify later overlay events cannot
  overwrite an earlier row's contact/whiff result before export.

Validation:
- Documentation-only change; no runtime behavior changed.
- `git diff --check` passed after this overlay evidence update.

## 2026-05-05: Combat Event Export Config And OSD Contract

Milestone:
- Milestone 6: finalize full-rollout combat event export controls

Files changed:
- `docs/agent-memory/remote-rl-combat-event-attribution-plan.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- Define how users can enable/disable evidence, combat event journal output,
  and transition event summaries after the complete combat attribution system
  ships.

Key updates:
- Export controls remain config-backed; OSD may expose toggles, but those
  toggles must update the same cached runtime/config flags rather than separate
  OSD-only state.
- Suggested final keys:
  - `rl-agent-export-evidence`
  - `rl-agent-export-combat-events`
  - `rl-agent-export-event-summaries`
- `rl-agent-export-combat-events` controls persistence of the sibling
  combat-event NDJSON file.
- `rl-agent-export-event-summaries` controls schema-v4 compact summaries in
  transition rows.
- Event-id summary fields require combat-event export to be on. If event
  journal output is off, summaries must either be disabled or limited to
  aggregate fields with no event references.
- Mid-run OSD/config toggles are allowed, but analyzers must report mixed-output
  coverage counts rather than assuming all envelopes have event journals or
  summaries.

Validation:
- Documentation-only change; no runtime behavior changed.
- `git diff --check` passed.

## 2026-05-05: Phase 0+1 Expanded Evidence Output Contract

Milestone:
- Milestone 6: finalize Phase 0+1 analyzer/debug ergonomics

Files changed:
- `docs/agent-memory/remote-rl-combat-event-attribution-plan.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- Make the human-readable bitmask expansion deliverable explicit while keeping
  the compact transition log unchanged for learner/replay safety.

Key updates:
- `tools/analyze_rl_transitions.py` must support an optional expanded output,
  for example `--expand-evidence --output-expanded PATH`.
- The expanded file should preserve row identity and add decoded evidence
  names/dictionaries for audit/debug.
- The compact source transition log remains unchanged and remains the default
  learner/debug contract.
- Added an expanded-log smoke to prove the optional output can be written
  without mutating the compact log.

Validation:
- Documentation-only change; no runtime behavior changed.
- `git diff --check` passed.

## 2026-05-05: Combat Event Attribution Disk Log Contract

Milestone:
- Milestone 6: finalize combat event attribution logging contract

Files changed:
- `docs/agent-memory/remote-rl-combat-event-attribution-plan.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- Make the final disk persistence shape explicit before implementation: one
  synchronized MiSTer/C-side envelope, persisted on the remote PC as two NDJSON
  files by default.

Key updates:
- MiSTer remains responsible for emitting one atomic transition batch/envelope;
  it must not create a second independent combat-event stream.
- Remote PC persistence defaults to two files derived from that same envelope:
  the configured transition log for summary rows and a sibling combat-event log
  for journal rows.
- The two files are analyzer ergonomics only, not independent sources of truth.
  They must remain reconcilable through `run_id`, `episode_id`, event/summary
  ids, and any future batch/envelope id.
- If event-file persistence fails for an envelope, the receiver must mark the
  transition batch incomplete/failed instead of silently writing summaries that
  reference missing event rows.

Validation:
- Documentation-only change; no runtime behavior changed.
- `git diff --check` passed.

## 2026-05-05: Combat Event Attribution Final Round Review Closeout

Milestone:
- Milestone 6: close final full-scope Phase 0+1 review

Files changed:
- `docs/agent-memory/remote-rl-combat-event-attribution-plan.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- Integrate the final full-scope review feedback before implementation,
  including rollback gating, formatter fallback semantics, exact buffer
  lifecycle hooks, C-to-JSON counter naming, enum scope reduction, mixed-version
  parser handling, and implementation order.

Key updates:
- Added a runtime/config evidence-export gate requirement, e.g.
  `rl-agent-export-evidence`, so Phase 0+1 evidence export can be disabled
  without changing reward, inference, action scheduling, or episode lifecycle.
- Refined formatter failure semantics:
  - base-row formatter failure drops the row and increments telemetry.
  - evidence-extension failure clears the partial buffer, retries the base row
    without evidence, and increments visible evidence fallback telemetry.
  - partial JSON must never be appended locally, batched, or sent over the
    network.
- Specified exact buffer lifecycle direction:
  `RLSession_AllocFormatBuffer()` / `RLSession_FreeFormatBuffer()` owned by
  `rl_session.*`, wired through `RLNet_Init()` / `RLNet_Shutdown()` or equivalent
  re-init paths.
- Added the C-to-JSON counter mapping:
  `remote_debug.episode_attack_*_count` /
  `RLDecisionLedgerEntry.overlay_attack_*_count` exports as
  `ep_overlay_attack_*_count`.
- Clarified `ep_overlay_attack_*_count` semantics: overlay attack pipeline only,
  not all engine attacks; snapshot captured at transition finalization, reset at
  episode boundary, monotonic within an episode, and same-episode rows may differ.
- Reduced Phase 0+1 `rl_combat_event.h` scope to evidence bitmask version/bit
  constants only. Event/result/source/confidence/failure enums are deferred to
  phases that export or consume them.
- Added mixed-version, config-gate, pre-existing truncation guard, evidence
  fallback, and C/Python counter mapping validation requirements.
- Added a recommended six-commit implementation order to keep Python hardening,
  formatter safety, bitmask constants, gated C export, and validation separable.

Review decisions:
- Accepted the rollback/config gate recommendation.
- Accepted exact alloc/free hook naming as implementation guidance.
- Accepted ep counter C-to-JSON mapping and overlay-only semantics.
- Accepted mixed-version and hi-bit parser smokes.
- Did not adopt static/BSS formatter fallback as an approved silent fallback;
  if heap lifecycle is blocked, implementation should stop and document the
  blocker before choosing a temporary exception.
- Refined the "drop row" rule: drop only if the base row cannot be formatted;
  evidence-only formatting failures should fall back to a complete base row to
  preserve transition continuity.

Validation:
- Documentation-only change; no runtime behavior changed.
- `git diff --check` passed.

## 2026-05-05: Combat Event Attribution Peer Review 1/2 Closeout

Milestone:
- Milestone 6: close Phase 0+1 pre-implementation review feedback

Files changed:
- `docs/agent-memory/remote-rl-combat-event-attribution-plan.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- Integrate the two final peer-review reports before Phase 0+1 implementation,
  focusing on C formatter failure semantics, formatter buffer ownership hooks,
  Python signed/hi-bit bitmask safety, feature-leak guards, and scope-creep
  prevention.

Key updates:
- Formatter truncation/overflow now has explicit row-drop semantics:
  clear/poison the buffer, do not append partial JSON to local NDJSON,
  transition batches, or network payloads, and increment visible telemetry.
- The pre-existing `written > 0` guard risk in
  `RLSession_FinalizeLedgerEntry()` is now called out as a Phase 0+1 bug fix
  prerequisite before adding evidence fields.
- Formatter buffer ownership is no longer left open-ended: use a heap-owned
  reusable `char*` pointer, allocate from an explicit RL session/net lifecycle
  hook, and free from the matching shutdown/re-init path. Large stack buffers
  and static/BSS arrays remain forbidden.
- Python flag parsing must reject negative or out-of-range
  `evidence_flags_lo/hi` values before applying `0xffffffff` masks, so a signed
  C formatting bug cannot silently decode as all bits set.
- Reserved-bit reporting now requires visible `stderr` warnings with per-episode
  counts and max reserved masks; validation includes a synthetic hi-bit
  `evidence_flags_hi = 0x80000000` smoke.
- Python feature builders must use explicit allowlists and must not derive
  features from `row.keys()` or model metadata that contains `evidence_` /
  `ep_overlay_` fields before the later learner-adoption gate.
- Evidence audit rows now include accuracy/limitation notes so heuristic fields
  such as `requested_attack_made_contact` cannot be mistaken for final
  attack-result truth.
- `ep_overlay_attack_*_count` validation now requires episode-boundary reset and
  monotonic in-episode snapshot behavior. This keeps the contract compatible
  with the current format-on-finalize transition path; any future final-episode
  snapshot semantics must be documented/versioned separately.
- Phase 0+1 scope guard now explicitly forbids `rl_combat_event.c`, event id
  counters, pending-export rings, event structs, and result/confidence/failure
  resolver assignment logic.

Validation:
- Documentation-only change; no runtime behavior changed.
- `git diff --check` passed.

## 2026-05-05: Combat Event Attribution Final Pre-Implementation Review Integration

Milestone:
- Milestone 6: finalize Phase 0+1 implementation contract

Files changed:
- `docs/agent-memory/remote-rl-combat-event-attribution-plan.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- Integrate the final pre-implementation feedback on row-local bitmask
  versioning, always-present flag fields, unsigned C formatting, session-owned
  formatter buffer lifetime, `SDL_snprintf()` underflow/truncation guards, and
  learner feature exclusion.

Key updates:
- `evidence_bitmask_version`, `evidence_flags_lo`, and `evidence_flags_hi` are
  now required on every transition row.
- `evidence_flags_lo` and `evidence_flags_hi` are specified as unsigned 32-bit
  JSON decimals; signed `%d` export is forbidden.
- Unknown bitmask versions now have explicit Python behavior: default parsers
  warn and keep the transition row usable with `evidence = None`; strict
  audit/debug modes fail clearly.
- Reserved bits are warnings with a per-log count, not hard parse failures.
- Replaced the previous static/BSS buffer option with a session-owned reusable
  formatter buffer allocated at RL session start and freed at shutdown.
- Added pre-call `capacity == 0` / `offset >= capacity` guard requirements for
  `SDL_snprintf()` append paths.
- Added learner feature guard requirements so Phase 0+1 evidence fields cannot
  silently enter `DQN_FEATURE_NAMES` or default replay features.

Validation:
- Documentation-only change; no runtime behavior changed.
- `git diff --check` passed.

## 2026-05-05: Combat Event Attribution Phase 0+1 Final Spec Lock

Milestone:
- Milestone 6: lock Phase 0+1 implementation contract before code

Files changed:
- `docs/agent-memory/remote-rl-combat-event-attribution-plan.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- Integrate the final pre-implementation review focused on bitmask versioning,
  `SDL_snprintf()` truncation semantics, debug readability, cross-language
  bit mapping, and Phase 0+1 scope creep prevention.

Key updates:
- Phase 0+1 export shape is now fixed:
  `evidence_bitmask_version = 1`, `evidence_flags_lo`,
  `evidence_flags_hi`, and `ep_overlay_attack_*_count`.
- Added the bitmask v1 field-to-bit mapping and reserved-bit rule.
- Python decoders must not guess unknown bitmask versions and must provide
  developer-only evidence expansion such as `--expand-evidence` or
  `--debug-bitmask`.
- Added explicit `SDL_snprintf()` truncation pseudo-code so append formatters do
  not advance offsets after a truncated write.
- Split the evidence audit into Pass 1 known-filled exports and Pass 2
  informational audit for proposed/unproven fields.
- Phase 0+1 now explicitly creates zero event structs, zero event rings, and
  zero event JSON arrays.

Validation:
- Documentation-only change; no runtime behavior changed.
- `git diff --check` passed.

## 2026-05-05: Combat Event Attribution C-Side Export Review Integration

Milestone:
- Milestone 6: harden Phase 0+1 C-side evidence export plan

Files changed:
- `docs/agent-memory/remote-rl-combat-event-attribution-plan.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- Integrate the latest review focused on embedded C stack safety,
  `SDL_snprintf()` growth, boolean evidence serialization cost, and the exact
  Python parser layer that must be tolerant of new fields.

Key updates:
- Phase 0+1 now forbids solving `line[2048]` by adding a large hot-path stack
  buffer; it requires reusable session/static/heap-owned storage or a bounded
  append builder plus truncation checks.
- Boolean/edge evidence is now expected to prefer schema-versioned bitmasks
  (`evidence_flags_*`) with Python analyzer expansion unless MiSTer timing
  proves flat/nested JSON fields are cheap enough.
- Python hardening now names the NDJSON-to-replay-buffer mapping path, not just
  `json.loads()`, as the place that must ignore unknown evidence keys.
- Phase 0+1 validation now includes memory/stack guard, leak checks, worst-case
  formatter timing, and overlay-counter tolerance for multi-hit/clash cases.

Review reconciliation:
- Already covered before this pass: phase order is 0+1 -> attack rings ->
  side-explicit engine attribution; contact/defense/punish are split into
  6a/6b/6c; episode-boundary contract, lifecycle ordering, stun/round/position
  event types, schema v3/v4 engine alias migration, and synchronized event
  journal export are already in the plan.
- Still deferred to implementation audit: whether Phase 0+1 uses bitmasks,
  flat root keys, or a nested `evidence` object for the final exported shape.

Validation:
- Documentation-only change; no runtime behavior changed.
- `git diff --check` passed.

## 2026-05-05: Combat Event Attribution Phase 0+1 Peer Review Hardening

Milestone:
- Milestone 6: harden Phase 0+1 before implementation

Files changed:
- `docs/agent-memory/remote-rl-combat-event-attribution-plan.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- Integrate two peer-review passes focused on Phase 0+1 ordering, schema
  compatibility, parser safety, export buffering, concrete evidence audit
  deliverables, and validation invariants.

Key updates:
- Changed combat `event_id` guidance from `uint32` to `uint64`, with `0`
  reserved for "no event".
- Added pending-export ring requirements and dropped-event metadata so events
  that finalize between decision rows cannot disappear silently before batch
  export.
- Made Phase 0+1 parser-first: Python tools must tolerate unknown keys and
  expose known evidence fields for audit before C emits restored evidence.
- Added a concrete seed audit table for currently filled but unexported
  evidence fields in `RLDecisionLedgerEntry`.
- Required `rl_combat_event.h` as the Phase 0+1 enum foundation, while deferring
  executable `rl_combat_event.c` logic until rings/export queues exist.
- Added transition-line buffer sizing/truncation guard requirements for the
  current `RLSession_FormatTransitionLogLine()` / `line[2048]` risk.
- Added Phase 0+1-specific validation matrix and evidence invariants, separate
  from the later full event resolver validation matrix.

Validation:
- Documentation-only change; no runtime behavior changed.
- `git diff --check` passed.

## 2026-05-05: Combat Event Attribution Review Feedback Integration

Milestone:
- Milestone 6: complete combat event attribution planning hardening

Files changed:
- `docs/agent-memory/remote-rl-combat-event-attribution-plan.md`
- `docs/plan-remote-rl-agent.md`

Purpose:
- Integrate external review feedback on event id lifetime, ring-buffer
  overwrite risk, interrupted attacks, episode boundaries, transition/event
  synchronization, hot-path cost, confidence definitions, and validation gaps.

Key updates:
- Event ids are now defined as monotonic run-wide `uint64` values, never ring
  indices.
- Event journal export is now defined as part of the same transition
  batch/envelope instead of a second independent C-side stream.
- Added explicit event lifecycle state machine and episode-boundary flush/finalize
  contract.
- Added `interrupted` attack result, stun/position/round event types, expanded
  defense target-state/wakeup/actual-guard fields, projectile multi-hit fields,
  and throw valid-state fields.
- Reordered implementation phases so attack rings precede side-explicit opponent
  engine attribution, and split resolver work into 6a/6b/6c.
- Added confidence matrix, runtime evidence audit requirement, hot-path
  edge-trigger rule, 500us first budget target, schema compatibility contract,
  and expanded validation matrix.

Validation:
- Documentation-only change; no runtime behavior changed.
- `git diff --check` passed.

## 2026-05-05: Complete Combat Event Attribution Plan

Milestone:
- Milestone 6: complete self/opponent combat event attribution planning

Files changed:
- `docs/agent-memory/remote-rl-combat-event-attribution-plan.md`
- `docs/plan-remote-rl-agent.md`

Purpose:
- Document the full plan for moving from decision-centric transition rows to
  side-symmetric combat event attribution for both agent and opponent.
- Cover attack, defense, projectile, throw, contact, punish, source,
  confidence, and explicit unknown/failure-reason handling.

Key decisions:
- Keep transition rows as compact learner/analyzer summaries, but add a
  separate combat event journal for full battle replay.
- Treat snapshots as evidence and events as the replay/attribution truth model.
- Require side-explicit ownership (`self_engine_*`, `opp_engine_*`) before using
  engine-derived labels to explain opponent offense or self defense failure.
- Track projectiles independently after spawn so later hits are not attributed
  to whatever owner routine is visible at contact time.
- Keep all new event labels analysis/debug-only until move-family validation
  passes for normals, specials, projectiles, throws, and multistage moves.

Follow-up tasks:
- Restore currently internal evidence fields to NDJSON as evidence-only fields.
- Add fixed-size event rings under `src/rl/*`.
- Add transition schema v4 compact summaries and
  `combat_event_schema_version=1` journal export.
- Upgrade analyzers before enabling trainer reward use of event labels.

Validation:
- Documentation-only change; no runtime behavior changed.
- `git diff --check` passed.

## 2026-05-04: Engine Fields For Remote Execution And Fireball Macro Fix

Milestone:
- Milestone 6: data quality and macro correctness fixes

Files changed:
- `src/rl/rl_session.c`
- `tools/rl_probe_server.py`

Purpose:
- Enable `engine_*` fields (engine_action_id, engine_kind_of_waza, engine_routine_1/2,
  engine_current_attack, engine_lag_frames) for remote execution (src=1), not just
  human-demo (src=4) and cpu-demo (src=5).
- Fix fireball macro producing Shoryuken due to SF3 input buffer interpreting
  forward(walk) → down → down-forward → forward+P as Shoryuken motion.

Implementation:
- Removed `!RLSession_IsDemoExecutionSource(entry->execution_source)` gate in
  `RLSession_MaybeAttributeDemoEngineAction()` (rl_session.c:973).
- Removed now-unused `RLSession_IsDemoExecutionSource()` function.
- Fireball macro: added 2 neutral frames at start to clear SF3 input buffer
  before fireball motion (NEUTRAL ×2 → DOWN_BACK → DOWN → DOWN_FORWARD → FORWARD+BUTTON).
- Reverted Shoryuken repeat-lockout commits (1215c272, 86ec280f, 5b6156ce, 0e6562a4)
  due to design concern: lockout triggered on all Shoryukens including anti-air,
  preventing back-to-back anti-air responses.

Validation:
- New log confirms engine fields populated for remote rows (28 engine events in 1144 rows).
- Fireball→Shoryuken misclassification reduced: 10/23 remaining mismatches traced to
  single neutral frame insufficient to clear ~10-frame SF3 input buffer.
  After adding second neutral frame: pending live test.

Discoveries during analysis:
- v350 log (737 rows, 12 sec): 126 fireball action rows (21 decisions), only 2 Shoryuken.
  Model was spamming fireballs at ~1.7/sec — visible as "Shoryuken-like" startup
  animation. Root cause: fireball macro's down-back→down→down-forward→forward+P
  sequence interpreted as Shoryuken when model was walking forward before macro.
- SF3 input priority: Shoryuken (6→2→3+P) takes priority over fireball (2→3→6+P)
  when both motions are present in input buffer (~10 frame window).
- Fix verified: 3 neutral frames clears buffer. Reduced to 2 neutral + DOWN_BACK
  for user-preferred sequence.

Action ID reference:
- policy_executed_action_id mapping: walk=1, jump=4, fireball=1229, shoryuken=1228,
  tatsu=1230, throw=8 (C side), stand-normal=6, crouch-normal=15
- engine_action_id uses same numbering as policy IDs
- Fireball macro wire sequence: 0→0→7→2→8→68→0→0 (8 steps, 4 frames each)

Policy requested vs executed analysis:
- 30.6% of rows have requested!=executed. All are requested=0 → executed=X.
  Requested=0 is normal for macro continuation steps and fallback actions.
  No cases of "model wanted A, executed B".

## 2026-05-04: Far Shoryuken Hard Block Macro Continuation Fix

Milestone:
- Milestone 6: live-side DQN Shoryuken guardrail for v350

Files changed:
- `tools/rl_probe_server.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

User observation:
- Live probe still used far Shoryuken too often even with:
  - `--dqn-shoryuken-prior-max-abs-dx 39`
  - `--dqn-shoryuken-prior-far-min-abs-dx 40`
  - `--dqn-shoryuken-prior-far-block`

Diagnosis:
- Q-score rerank hard block and epsilon eligible-action filtering both blocked
  new `shoryuken-*` selections on far rows.
- `policy_action_frame()` returned an already-active macro before running DQN
  action selection.
- Therefore a Shoryuken macro that started on an earlier decision could keep
  playing step 1+ after the current row had moved into hard-blocked range.

Implementation:
- Added `active_macro_action_name()`.
- Before consuming an active DQN macro frame, `policy_action_frame()` now checks
  whether the active macro action is hard-blocked by the current observation
  and Shoryuken prior config.
- If blocked, the macro state for `(nonce, run_id, episode_id)` is cleared and
  the current frame falls through to normal DQN selection / fallback.

Validation:
- `python3 -m py_compile tools/rl_probe_server.py tools/compare_dqn_models.py`
- direct helper smoke:
  - `shoryuken-lp` at `obs_abs_dx=80`, `max_abs_dx=39`, `far_min_abs_dx=40`,
    and `far_block=True` returns penalty `1000000.0`.
  - same row reports `dqn_action_hard_blocked_by_priors=True`.
  - an active `shoryuken-lp` macro at step 1 is cleared and the returned action
    is `back`, not another Shoryuken step.
  - epsilon eligible actions no longer include `shoryuken-lp`.

Next:
- Re-run the same v350 live command from the failed probe.
- Use `--verbose` briefly if Shoryuken still appears; expected diagnostic line
  for blocked rows should show `dqn_dp_prior_penalty=1000000.000`.
- If Shoryuken still appears with that penalty, the next suspect is visual
  attribution or stale server process rather than DQN selection.

## 2026-05-04: v350 Guard Success Bonus And Grounded Normals Defense Phase 4 Complete

Milestone:
- Milestone 6: grounded normals defense trainer improvements and live-side prior tuning

Key changes to `tools/train_dqn_learner.py`:
- Added `--reward-throw-far-cost 0.5` / `--reward-throw-far-max-abs-dx 64`: penalizes throw at abs_dx > 64
- Added `--grounded-normal-defense-bc-loss` / `--grounded-normal-defense-bc-weight 0.08`: CE loss toward human-demo guard/back in opponent normal threat rows
- Added `GroundedNormalDefenseBCConfig/Stats`, eligibility, and loss function
- Fixed `--conservative-exempt-actions` to include forward, back, guard-stand, guard-crouch, jump-* (root cause of v341-v345 action collapse)
- Added `--movement-regression-exclude-special-expert-eligible` flag
- Added shoryuken engine outcome action windows (lp=30, mp=35, hp=45)

Training iterations:
- v341 (margin loss): tatsu-mk collapse at 60.1% — margin approach abandoned
- v342 (BC loss, weight 0.1): tatsu-mk collapse — BC weight too low
- v343 (no defense loss, tatsu in conservative penalty): tatsu-mk collapse — root cause was conservative penalty killing movement/defense
- v344-v345 (from v335, BC 0.05-0.08): throw dominance 38.9-45.3% — conservative penalty fixed but throw escaped
- v346-v347 (from v335, fixed exempt list + movement-regression-exclude): healthy! No collapse. Shoryuken 42.6%→17.0%, but throw 39.6% still high
- v348 (from v335, +throw far penalty 0.5): throw_far:132/66.0 in training, live-probe throw still 39.6%
- v349 (BC weight 0.25): nearly identical to v348, only 33/5000 rows changed
- v350 (from v335, +guard success bonus 0.5, window 30, max_dx 240): guard_bonus 742.0, guard_net +741.4, guard-crouch reward from -4.93 to +0.16

Live-side prior tuning (v348 probe iterations):
- Shoryuken prior: 0.06→0.10→0.15 (0.15 effective for reducing ground Shoryuken spam)
- Added threat-defense prior: guard/back/unsafe 0.12/0.08/0.10→0.20/0.15/0.20
- Added ground-normal prior: penalty 0.05→0.08
- Threat-defense max_abs_dx: 144→192→240 (data-driven: p95 of normal hit distance = 189)
- Fireball zoning prior: 0.03 (unchanged)

Live test observations (v348 with priors):
1. Shoryuken at 0.15: ground Shoryuken spam reduced, anti-air preserved
2. Defense slightly improved but still weak against normals at close range
3. Tatsu multi-hit defense: only blocks first hit — block stun causes defense prior to disengage
4. Medium/heavy kick defense improved with max_abs_dx=240
5. Far-range throw almost eliminated

Opponent normal attack hit distance analysis (grounded normals only, excluding specials):
- n=2831, p50=85, p80=124, p90=156, p95=189, max=326
- R2=0 (mixed): p50=95, p90=157
- R2=3 (close): p50=65, p90=116
- R2=4 (long heavy): p50=297, p90=324 (n=33)
- R2=30 (long heavy): p50=175, p90=324 (n=47)

Tatsu defense analysis (230 segments in human-demo logs):
- Self hit: 107 (46.5%), blocked: 15 (6.5%), avoided: 123 (53.5%)
- Only 15 successful blocks — insufficient for BC-style imitation
- Guard success bonus approach: model-agnostic, rewards guarding through any attack

Open issues:
- Tatsu multi-hit defense: block-stun gap in threat-defense prior needs fix (opp R1=4 check when self in block stun)
- Throw still 39.6% in live-probe despite training penalty — needs live-side throw range prior
- Model cannot distinguish block stun vs hit stun from observation fields

Next:
- Add live-side throw range prior (penalty when abs_dx > 64)
- Fix tatsu multi-hit defense: continue defense push when opp R1=4 AND self in contact reaction
- Consider collecting more human demo with deliberate tatsu defense

## 2026-05-04: Threat-Defense Contact Sustain For Multi-Hit Defense

Milestone:
- Milestone 6: fix v350/v348 multi-hit defense gap after first blocked hit

Files changed:
- `tools/rl_probe_server.py`
- `tools/compare_dqn_models.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- address the live observation that tatsu / long multi-hit attacks are often
  guarded for the first hit only, then subsequent hits are not defended.
- keep the fix as an opt-in live-side prior change because observation v1 does
  not distinguish block stun from hit stun.

Diagnosis:
- threat-defense prior previously required `dqn_ground_action_start_allowed()`.
- when the first hit is blocked or contact occurs,
  `obs_self_contact_reaction_state=1` and
  `obs_self_ground_action_start_allowed=0`.
- that makes the prior disengage during block/contact reaction, even if the
  opponent is still in `obs_opp_routine_attack_state=1`.
- result: the model may stop choosing guard/back during the later hits of a
  multi-hit sequence.

Implementation:
- added `DQNThreatDefensePriorConfig.contact_sustain`.
- added CLI flag:
  - `--dqn-threat-defense-prior-contact-sustain`
- when enabled, threat-defense guard/back bonus and unsafe-action penalty can
  apply if:
  - self is in `obs_self_contact_reaction_state`.
  - opponent is still in attack state.
  - opponent is not airborne / jumping.
  - spacing is within `--dqn-threat-defense-prior-max-abs-dx`.
- the global DQN valid-action mask is unchanged. This only affects the
  threat-defense rerank prior.
- the flag is off by default because self contact reaction includes both hit
  and block reaction.

Validation:
- `python3 -m py_compile tools/rl_probe_server.py tools/compare_dqn_models.py`
- direct helper smoke:
  - ordinary grounded threat guard bonus: `0.2`.
  - contact reaction with sustain off: `0.0`.
  - contact reaction with sustain on: `0.2`.
  - contact reaction unsafe `tatsu-mk` penalty with sustain on: `0.2`.
  - airborne-opponent contact row remains excluded: `0.0`.
- existing row inventory confirms enough relevant rows for offline sanity:
  - `logs/rl-transitions-v335-live-probe.ndjson`: `10467`
    `self_contact + opp_attack` rows.
  - `logs/rl-transitions-retrain-p2-normals-human-v1.ndjson`: `6089`.
  - `logs/rl-transitions-retrain-p8-natural-human-v1.ndjson`: `1337`.
  - `logs/rl-transitions-retrain-p8-natural-cpudemo-v1.ndjson`: `2197`.
- same-observation compare on the first `5000` rows of
  `logs/rl-transitions-v335-live-probe.ndjson` using v350 and tuned live-side
  priors showed contact sustain strongly changes the intended buckets:
  - no sustain / no threat prior baseline in compare: defense `9.5%`,
    attack `16.3%`, Shoryuken `1.3%`, fireball `9.5%`.
  - contact sustain with threat-defense guard/back/unsafe `0.20/0.15/0.20`,
    max_dx `240`: defense `24.0%`, attack `11.1%`, Shoryuken `1.3%`,
    fireball `9.5%`.
  - `atk1_close`: `forward/stand-lp` dominated before; with sustain,
    `guard-crouch 40/66`, `back 14/66`, `forward 12/66`.
  - `atk1_mid`: with sustain, `guard-crouch 379/793`,
    `back 155/793`, `forward 259/793`.
  - changed `721/5000` rows with no Shoryuken increase.

Conclusion:
- the current multi-hit failure is consistent with a block/contact-reaction
  disengage, not only weak model preference.
- `--dqn-threat-defense-prior-contact-sustain` is a good next live probe flag
  for tatsu-style multi-hit defense.
- Main risk remains hit-stun ambiguity: if the first hit connects, the same
  contact flag can still push guard/back afterward. This is acceptable for a
  short probe but not a final learned solution.

Next:
- live-probe v350 with contact sustain enabled together with the latest tuned
  priors.
- Watch specifically:
  - whether tatsu second/third hits stay guarded.
  - whether post-hit behavior becomes too defensive after actually getting hit.
  - whether anti-air remains preserved.
- If contact sustain helps, the longer-term observation/schema fix is to split
  block stun from hit stun or expose a cleaner guard/contact outcome feature.

## 2026-05-04: Far Shoryuken Extra Penalty

Milestone:
- Milestone 6: reduce live medium/far-range random Shoryuken without reducing
  close anti-air availability

Files changed:
- `tools/rl_probe_server.py`
- `tools/compare_dqn_models.py`
- `docs/remote-rl-agent-engineering-log.md`

User observation:
- Shoryuken still fires randomly around mid distance, roughly `abs_dx ~= 200`.

Diagnosis:
- The current Shoryuken context prior only exempts coarse anti-air rows inside
  `--dqn-shoryuken-prior-min-abs-dx` and
  `--dqn-shoryuken-prior-max-abs-dx`, default `24-150`.
- A Shoryuken at `abs_dx ~= 200` is already outside the anti-air exemption, so
  it receives the base penalty, e.g. `0.15` in the current v350 live command.
- If it still wins top-1, the issue is not the anti-air exemption being too
  wide; the base penalty is not large enough for medium/far non-anti-air rows.

Implementation:
- Added optional far-distance extra penalty fields to
  `DQNShoryukenContextPriorConfig`:
  - `far_min_abs_dx`
  - `far_extra_penalty`
- Added probe CLI flags:
  - `--dqn-shoryuken-prior-far-min-abs-dx`
  - `--dqn-shoryuken-prior-far-extra-penalty`
- Added matching `tools/compare_dqn_models.py` flags.
- The extra penalty only applies outside the anti-air context. If a row matches
  the existing anti-air exemption, penalty remains `0.0`.

Validation:
- `python3 -m py_compile tools/rl_probe_server.py tools/compare_dqn_models.py`
- direct helper smoke with base Shoryuken penalty `0.15`, far threshold `180`,
  extra `0.10`:
  - anti-air row at `dx=100`, opponent air routine: `0.0`.
  - non-anti-air row at `dx=160`: `0.15`.
  - non-anti-air row at `dx=200`: `0.25`.
  - non-Shoryuken action unchanged: `0.0`.
- same-observation v350 slice had already-low Shoryuken top1, so it did not
  show a distribution shift; this is mainly a live-side guardrail for the
  reported `dx ~= 200` failure mode.

Next:
- Try the current v350 live command with:
  - `--dqn-shoryuken-prior-far-min-abs-dx 180`
  - `--dqn-shoryuken-prior-far-extra-penalty 0.10`
- If `dx ~= 200` Shoryuken still appears, increase only the extra far penalty
  before changing the close anti-air window.
- Watch that close anti-air remains available; this change should not affect
  anti-air rows inside `24-150`.

Live follow-up:
- User reports Shoryuken is still too frequent outside `abs_dx ~= 180` with
  far extra penalty `0.10`.
- Next probe should keep `--dqn-shoryuken-prior-far-min-abs-dx 180` and raise
  `--dqn-shoryuken-prior-far-extra-penalty` to `0.20`.
- Rationale: the failure is still beyond the far threshold, so increase the
  far-only penalty first instead of moving the threshold down toward the
  anti-air exemption boundary.

Second live follow-up:
- User reports far extra penalty `0.20` still does not suppress Shoryuken
  enough outside `abs_dx ~= 180`.
- Interpretation: a soft Q penalty is not enough for this model in those rows;
  either the Shoryuken Q gap is very large, or the live row is not matching the
  intended penalty path often enough.
- Added opt-in hard far block:
  - `--dqn-shoryuken-prior-far-block`
- Behavior:
  - still requires `--dqn-shoryuken-context-prior`.
  - only affects Shoryuken actions.
  - only applies outside the existing anti-air exemption.
  - at or beyond `--dqn-shoryuken-prior-far-min-abs-dx`, returns a very large
    Shoryuken penalty so another valid action should win.
- Smoke:
  - far non-anti-air Shoryuken at `dx=200`: `1000000.0` penalty.
  - anti-air Shoryuken at `dx=100`, opponent air routine: `0.0`.
  - non-Shoryuken action: `0.0`.

Next:
- Live-probe v350 with `--dqn-shoryuken-prior-far-block` and threshold `180`.
- If this finally stops far DP but makes the agent too passive at 180+, recover
  activity with fireball/back/guard priors rather than re-enabling far DP.

Third live follow-up / fix:
- User reports `--dqn-shoryuken-prior-far-block` still did not suppress far
  Shoryuken.
- Root cause found in the prior helper: far block was evaluated after early
  returns for self airborne / jump / `dqn_ground_action_start_allowed(row)`.
- In recovery or other non-action-start rows, the helper returned only the base
  Shoryuken penalty before reaching the far block branch.
- Fixed `dqn_shoryuken_context_prior_penalty()` so it computes anti-air context
  and far context first:
  - anti-air exemption remains first and returns `0.0`.
  - far hard block applies before self action-start checks.
  - far extra penalty also applies before self action-start checks.
- Smoke after fix:
  - far non-anti-air Shoryuken at `dx=200` with
    `obs_self_ground_action_start_allowed=0`: `1000000.0`.
  - anti-air Shoryuken at `dx=100`, opponent air routine: `0.0`.
  - soft far penalty at `dx=200` with action-start not allowed: `0.35`.
  - non-Shoryuken action: `0.0`.

Fourth live follow-up:
- User reports Shoryuken still appears in mid/far range even with
  `--dqn-shoryuken-prior-far-min-abs-dx 40 --dqn-shoryuken-prior-far-block`.
- Important interaction: the Shoryuken anti-air exemption is evaluated before
  far block. With defaults, anti-air exemption covers `abs_dx=24-150` when
  opponent routine fields look like a jump/air routine.
- Therefore `far_min_abs_dx=40` does not mean "block all Shoryuken at dx>=40"
  unless the anti-air exemption max is also moved below 40.
- Next live probe for a diagnostic hard block should add:
  - `--dqn-shoryuken-prior-max-abs-dx 39`
  - `--dqn-shoryuken-prior-far-min-abs-dx 40`
  - `--dqn-shoryuken-prior-far-block`
- Risk: this intentionally sacrifices most anti-air Shoryuken availability for
  the probe. Use it only to confirm whether the remaining visible DP was coming
  through the exemption path.

Fifth live follow-up / fix:
- User reports Shoryuken still appears occasionally after narrowing the
  anti-air exemption.
- Found a second bypass path: v350 manifest has `epsilon=0.05`.
- In `dqn_actor_action_name()`, epsilon exploration previously sampled directly
  from valid actions before Q rerank priors, so hard-blocked Shoryuken actions
  could still be selected by the 5% random branch.
- Added `dqn_action_hard_blocked_by_priors()` and filtered hard-blocked actions
  out of epsilon eligible actions.
- Smoke:
  - With `max_abs_dx=39`, `far_min_abs_dx=40`, and `far_block=True`, valid
    epsilon actions at `dx=80` originally included `shoryuken-lp/mp/hp`.
  - After filtering, epsilon eligible actions are
    `forward`, `back`, `guard-stand`, `fireball-hp`; all Shoryuken variants
    are blocked.
- Remaining possible source if a rare Shoryuken is still observed after this:
  - an already-started macro continuing for its remaining input frames.
  - old probe server process not restarted from the edited file.
  - visual confusion with opponent / CPU action rather than agent action.

## 2026-05-03: v338 Fireball Zoning Prior Probe Support

Milestone:
- Milestone 6: recover mid/far proactive zoning after v337 became passive

Files changed:
- `tools/rl_probe_server.py`
- `tools/compare_dqn_models.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- respond to the v337 live result where anti-air stayed acceptable, but
  mid/far range became too passive and fireball was used too rarely.
- add an opt-in positive prior for fireball only in far grounded zoning
  contexts, instead of stacking more broad action penalties.

Implementation:
- added `DQNFireballZoningPriorConfig`.
- added `--dqn-fireball-zoning-prior` to `tools/rl_probe_server.py`.
- the prior adds a small Q bonus to `fireball-lp`, `fireball-mp`, and
  `fireball-hp` only when:
  - self is grounded and ground action-start is allowed.
  - `obs_abs_dx` is inside the configured zoning window, default `120-260`.
  - opponent is not in contact reaction and is not airborne / jumping.
- added verbose probe diagnostics:
  - `dqn_fb_prior=...`
  - `dqn_fb_prior_bonus=...`
- added `tools/compare_dqn_models.py` support and a printed `fireball_rate`.

Validation:
- `python3 -m py_compile tools/rl_probe_server.py tools/compare_dqn_models.py`
- direct helper smoke:
  - far grounded `fireball-hp` bonus: `0.03`.
  - close fireball bonus: `0.0`.
  - self-airborne fireball bonus: `0.0`.
  - far `stand-lp` bonus: `0.0`.
- same-observation compare on `logs/rl-transitions-v335-live-probe.ndjson`,
  first `5000` rows:
  - raw v335: attack `18.7%`, Shoryuken `11.1%`, fireball `1.8%`,
    forward `74.0%`.
  - v336b style Shoryuken prior `0.06`: attack `14.8%`, Shoryuken `3.3%`,
    fireball `5.5%`, forward `76.0%`.
  - v338a Shoryuken prior `0.06` + fireball zoning bonus `0.03`, no
    ground-normal prior: attack `15.8%`, Shoryuken `3.2%`, fireball `6.6%`,
    forward `75.2%`.
- same-observation compare on P3 fireball-good/bad logs, first `5000` rows:
  - v336b: attack `7.2%`, Shoryuken `1.1%`, fireball `2.2%`, forward `85.7%`.
  - v338a: attack `8.0%`, Shoryuken `1.1%`, fireball `3.0%`, forward `85.0%`.

Conclusion:
- v338a is a safer live candidate than v337 because it avoids the broad
  ground-normal prior that caused the passive live behavior.
- The fireball zoning prior restores some far-range fireball selection, but the
  same-observation compare still shows high forward/passive selection, so this
  is an incremental probe candidate rather than a full fix.

Next:
- live-probe v338a with:
  - Shoryuken context prior `0.06`.
  - fireball zoning prior bonus `0.03`.
  - no ground-normal context prior.
- watch:
  - whether mid/far passive behavior improves versus v337.
  - whether far fireball usage becomes visible without becoming spammy.
  - whether anti-air remains acceptable.
- If still passive, prefer a trainer/data fix or a stronger context-specific
  fireball objective over re-enabling broad ground-normal penalties.

Live probe result:
- Tested v338a live with:
  - Shoryuken context prior `0.06`.
  - fireball zoning prior bonus `0.03`.
  - no ground-normal context prior.
- User observation:
  - anti-air did not get worse.
  - behavior became more aggressive than v337.
  - fireball usage increased.
  - the policy still does not defend well against enemy attacks.

Conclusion after live probe:
- v338a fixes the v337 passivity/fireball regression directionally.
- The remaining visible weakness shifted to threat response: when the opponent
  attacks, the policy is not choosing guard/back often enough.
- Keep v338a as the current live-side baseline candidate, but do not treat it
  as complete until enemy-attack defense improves.

Next:
- v339 should preserve:
  - Shoryuken prior `0.06`.
  - fireball zoning prior `0.03`.
  - no broad ground-normal prior.
- Add a threat-response adjustment that only applies when opponent attack /
  close threat evidence is present, such as:
  - a small guard/back positive prior in opponent-attack mid/close contexts.
  - or a trainer/data fix that boosts guard/back examples in attack-threat rows.
- Avoid a global passive guard prior; v337 already showed broad suppression can
  make the policy too passive.

## 2026-05-03: v339 Threat-Defense Prior Probe Support

Milestone:
- Milestone 6: improve defense against grounded enemy attacks after v338a

Files changed:
- `tools/rl_probe_server.py`
- `tools/compare_dqn_models.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- preserve v338a's improved aggression/fireball behavior while adding a
  narrow live-side response for enemy attack threat rows.
- avoid a global defensive prior that would recreate v337 passivity.

Implementation:
- added `DQNThreatDefensePriorConfig`.
- added `--dqn-threat-defense-prior` to `tools/rl_probe_server.py`.
- the prior only applies when:
  - self is grounded and ground action-start is allowed.
  - opponent attack-state evidence is present.
  - opponent is not airborne / jumping, preserving anti-air contexts.
  - `obs_abs_dx <= 144` by default.
- in eligible rows:
  - adds Q bonus to `guard-stand`, `guard-crouch`, and `back`.
  - optionally subtracts Q from unsafe immediate actions:
    `forward`, stand/crouch normals, fireballs, Shoryuken, and tatsu.
- added verbose probe diagnostics:
  - `dqn_def_prior=...`
  - `dqn_def_prior_bonus=...`
  - `dqn_def_prior_penalty=...`
- added `tools/compare_dqn_models.py` support and a printed `defense_rate`.

Validation:
- `python3 -m py_compile tools/rl_probe_server.py tools/compare_dqn_models.py`
- direct helper smoke:
  - grounded attack-threat `guard-stand` bonus: `0.08`.
  - grounded attack-threat `shoryuken-lp` unsafe penalty: `0.08`.
  - airborne-opponent `shoryuken-lp` unsafe penalty: `0.0`.
- same-observation compare on `logs/rl-transitions-v335-live-probe.ndjson`,
  first `5000` rows, using v338a as baseline:
  - v338a: attack `15.8%`, Shoryuken `3.2%`, fireball `6.6%`,
    defense `9.0%`.
  - v339a conservative guard/back bonus `0.03/0.02`: changed only `3/5000`
    rows, too weak for live testing.
  - v339b guard/back bonus `0.08/0.05`: changed only `7/5000` rows, still too
    weak.
  - v339c added unsafe penalty `0.08`: changed `37/5000` rows, but shifted some
    rows into Shoryuken.
  - v339e ground-threat-only unsafe penalty with guard/back/unsafe
    `0.18/0.10/0.18`: changed `178/5000` rows, attack `12.4%`, Shoryuken
    `3.1%`, fireball `6.6%`, defense `12.6%`.
  - v339e threat buckets:
    - `atk1_close`: back/guard-crouch top1 increased from `0/66` to `15/66`.
    - `atk1_mid`: back/guard-crouch top1 increased from `5/793` to `168/793`.

Conclusion:
- v339e is the best next live-probe candidate from this slice.
- It is intentionally narrow: no ground-normal prior, no airborne-opponent
  Shoryuken penalty, and fireball prior remains unchanged.
- The compare still shows high `forward` top1 overall, so if v339e remains weak
  live, the next step should be trainer/data work for grounded attack defense
  rather than increasing broad live-side penalties indefinitely.

Next:
- live-probe v339e with:
  - Shoryuken context prior `0.06`.
  - fireball zoning prior bonus `0.03`.
  - threat-defense guard bonus `0.18`.
  - threat-defense back bonus `0.10`.
  - threat-defense unsafe penalty `0.18`.
  - no ground-normal context prior.
- watch:
  - defense against grounded enemy attacks.
  - whether anti-air remains acceptable.
  - whether aggression/fireball from v338a stays healthy.

Live probe result:
- Tested v339e live with:
  - Shoryuken context prior `0.06`.
  - fireball zoning prior bonus `0.03`.
  - threat-defense guard/back/unsafe `0.18/0.10/0.18`.
  - no ground-normal context prior.
- User observation:
  - anti-air became slightly weaker.
  - fireball increased slightly.
  - defense against normals is still not good enough.

Conclusion after live probe:
- v339e is not a good promotion candidate.
- The threat-defense prior did not solve the actual normals-defense weakness
  and started to tax anti-air behavior, even though the gate excludes airborne
  opponent rows. That likely means the live anti-air / grounded-threat contexts
  overlap through coarse observation state, action timing, or recovery timing
  more than the same-observation slice suggests.
- Do not keep increasing threat-defense live-side penalties. The opt-in prior
  stack has served its diagnostic purpose: it shows the model needs a real
  grounded normals-defense training/data fix.

Next:
- Treat v338a as the better live-side baseline candidate than v339e for now:
  - Shoryuken prior `0.06`.
  - fireball zoning prior `0.03`.
  - no ground-normal prior.
  - no threat-defense prior.
- Start a trainer/data pass for grounded normals defense:
  - collect or extract close/mid opponent-normal attack rows.
  - label or margin `guard-stand`, `guard-crouch`, and `back` as preferred
    responses when the opponent is attacking and self is grounded/action-ready.
  - add negative replay/margin pressure against `forward` and random normals
    into active opponent normals.
  - keep anti-air rows separate so Shoryuken availability is not reduced by
    grounded-defense tuning.
- Re-check without threat-defense prior before another live probe.

## 2026-05-03: Grounded Normals Defense Trainer/Data Plan

Milestone:
- Milestone 6: replace live-side threat-defense patching with learned grounded
  normals defense

Purpose:
- turn the v339e live result into a staged trainer/data plan.
- stop escalating opt-in inference patches after they failed to fix normals
  defense and began weakening anti-air.
- keep v338a as the current live-side baseline while the model learns the
  missing behavior.

Baseline while this plan runs:
- Use v338a for live probes unless a new trained candidate passes offline gates:
  - Shoryuken context prior `0.06`.
  - fireball zoning prior `0.03`.
  - no ground-normal context prior.
  - no threat-defense prior.

Phase 1: Data inventory
- Goal:
  - quantify whether existing logs already contain enough grounded normals
    defense examples.
- Inputs to inspect first:
  - current v335/v338/v339 live probe logs.
  - P2 normals human logs.
  - P8 natural human / CPU demo logs.
  - any recent live replay rows with opponent attack-state evidence.
- Count separately:
  - close/mid opponent grounded-normal attack rows.
  - rows where self is grounded and action-start is allowed.
  - successful `guard-stand`, `guard-crouch`, and `back` responses.
  - failed `forward`, stand/crouch normal, fireball, tatsu, or Shoryuken
    responses into active opponent normals.
  - jump-in / anti-air rows that should remain available to Shoryuken.
- Done when:
  - a short table exists with row counts by distance bucket, opponent threat
    type, selected action family, and HP/contact outcome.

Phase 2: Extractor / analyzer slice
- Goal:
  - make grounded normals defense rows reproducible instead of hand-inspecting
    live logs.
- Preferred implementation:
  - extend an existing analyzer/extractor if one already has action-family and
    distance-bucket support.
  - otherwise add a small focused tool under `tools/`.
- Required row tags:
  - `grounded_normal_threat=1`.
  - `anti_air_excluded=1` for opponent airborne/jump rows.
  - `defense_success` for guard/back rows with no self HP loss in the short
    follow-up window.
  - `unsafe_into_normal` for forward/random attack rows that are punished or
    fail into active opponent normals.
- Done when:
  - the tool can produce a deterministic dry-run summary and optional filtered
    NDJSON for training.

Phase 3: Trainer objective
- Goal:
  - make the model learn grounded normals defense without a live-side
    threat-defense prior.
- Candidate objectives:
  - guard/back expert margin for grounded-normal threat rows.
  - negative margin or reward penalty for `forward` and random grounded attacks
    into active opponent normals.
  - optional BC-style labels only for clean human/demo guard/back defense rows.
- Guardrails:
  - exclude opponent airborne / jump-in rows from this objective.
  - do not penalize Shoryuken in anti-air contexts.
  - keep fireball-good/far-zoning gates separate from close/mid defense rows.
  - avoid changing transition schema unless the existing rows cannot express
    the needed labels.
- Done when:
  - a small smoke training run completes and metadata records the defense
    objective settings.

Phase 4: Offline gates
- Goal:
  - prove the candidate improves defense without relying on threat-defense
    inference patching.
- Compare candidate against v338a with:
  - no threat-defense prior.
  - Shoryuken prior `0.06` only if comparing live-equivalent flags.
  - fireball zoning prior `0.03` only if comparing live-equivalent flags.
- Required gates:
  - grounded-normal threat defense rows: guard/back rank and top1 rate improve.
  - anti-air rows: Shoryuken top-k availability does not materially regress.
  - fireball-good/bad rows: far fireball behavior does not regress.
  - movement rows: no return to v337-style passivity or one-action collapse.
- Done when:
  - compare output is recorded in this log with pass/fail for each gate.

Phase 5: Live probe
- Goal:
  - live-check only after the model, not the inference patch, moves in the
    right direction offline.
- Launch shape:
  - use the new trained actor/model directory.
  - keep v338a live flags at first:
    - Shoryuken prior `0.06`.
    - fireball zoning prior `0.03`.
    - no ground-normal prior.
    - no threat-defense prior.
- Watch:
  - defense against grounded normals.
  - anti-air availability.
  - fireball usage.
  - overall aggression/passivity.
- Done when:
  - live notes decide whether to promote, retrain with adjusted objective, or
    collect targeted defense demos.

Open decision after Phase 1:
- If existing logs have enough clean examples, start with extractor + trainer
  objective.
- If examples are sparse or ambiguous, collect targeted human-demo defense rows
  before training.

## 2026-05-03: v337 Ground-Normal Context Prior

Milestone:
- Milestone 6: reduce normal-action replacement after v336b Shoryuken prior

Files changed:
- `tools/rl_probe_server.py`
- `tools/compare_dqn_models.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- keep v336b's Shoryuken reduction while adding an opt-in live-side prior for
  random / inappropriate grounded normals.
- avoid continuing to increase the Shoryuken penalty when the live failure mode
  has shifted to action-family replacement.

Implementation:
- added `DQNGroundNormalContextPriorConfig`.
- added `--dqn-ground-normal-context-prior` to `tools/rl_probe_server.py`.
- the prior subtracts a small Q penalty from `stand-*` and `crouch-*` normals
  unless the row is a coarse plausible normal context:
  - self is grounded and ground action-start is allowed.
  - `obs_abs_dx <= 48` close range, or
  - `obs_abs_dx <= 120` and opponent attack/contact evidence is present.
- added verbose probe diagnostics:
  - `dqn_norm_prior=...`
  - `dqn_norm_prior_penalty=...`
- added matching `tools/compare_dqn_models.py` support for raw-vs-prior
  same-observation comparisons.

Validation:
- `python3 -m py_compile tools/rl_probe_server.py tools/compare_dqn_models.py`
- direct helper smoke:
  - close stand LP penalty: `0.0`.
  - mid neutral stand LP penalty: `0.04`.
  - mid threat/contact normals penalty: `0.0`.
  - far stand LP penalty: `0.04`.
  - non-normal actions unchanged: `0.0`.
- same-observation compare with v335 actor plus Shoryuken prior `0.06`:
  - `logs/rl-transitions-v335-live-probe.ndjson`, first `5000` rows:
    - ground-normal prior `0.03`: attack rate `14.6%`, Shoryuken `3.3%`,
      stand-lp `5.9%`.
    - ground-normal prior `0.05`: attack rate `14.0%`, Shoryuken `3.3%`,
      stand-lp `5.3%`.
  - `/tmp/rl-retrain-m1-mix-70-20-10.ndjson`, first `10000` rows:
    - ground-normal prior `0.03`: attack rate `20.1%`, Shoryuken `0.0%`,
      fireball-hp `17.8%`, fireball-mp `2.2%`.
  - P3 fireball-good/bad logs, first `5000` rows:
    - ground-normal prior `0.05`: attack rate `5.5%`, Shoryuken `1.1%`,
      stand-lp `2.2%`, fireball-hp unchanged at `1.5%`.

Conclusion:
- `0.05` is the better first live probe value than `0.03`.
- The prior is a useful live-side mitigation, but the v335 live-probe compare
  only lowers stand-lp modestly, so this is not a full long-term fix.
- If live behavior still shifts into normals, the next step should be a
  trainer / policy-architecture change rather than stacking more penalties.

Live probe result:
- Tested v337 live with:
  - Shoryuken context prior `0.06`.
  - ground-normal context prior `0.05`.
- User observation:
  - anti-air did not get worse.
  - mid/far range became too passive.
  - fireball was used too rarely.

Conclusion after live probe:
- The Shoryuken prior remains acceptable at `0.06` for now.
- The ground-normal prior fixed the replacement symptom too bluntly: suppressing
  mid/far normal actions appears to push the policy toward passivity instead of
  restoring better zoning decisions.
- Do not promote v337 as-is.

Next:
- Prefer a v338 policy-side/probe-side adjustment that restores useful
  mid/far aggression instead of adding more penalties.
- First candidates:
  - lower ground-normal prior penalty below `0.05`, or make it distance-bucketed
    so far/mid neutral is penalized less aggressively.
  - add or tune a fireball-positive context prior / reranker for far grounded
    zoning rows before applying a broad normal penalty.
  - compare same-observation action distributions for passive-rate,
    fireball-rate, Shoryuken-rate, and normal replacement before the next live
    probe.

## 2026-05-03: v336 Live-Side Shoryuken Context Prior

Milestone:
- Milestone 6: reduce live Shoryuken overuse after v335 promotion

Files changed:
- `tools/rl_probe_server.py`
- `tools/compare_dqn_models.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- keep v335 as the promoted best model while adding an opt-in inference-time
  safety prior for live probes.
- reduce grounded / neutral `shoryuken-*` over-selection without globally
  removing anti-air Shoryuken from plausible jump-in contexts.

Implementation:
- added `DQNShoryukenContextPriorConfig`.
- added `--dqn-shoryuken-context-prior` to `tools/rl_probe_server.py`.
- the prior subtracts a small Q penalty from `shoryuken-lp`,
  `shoryuken-mp`, and `shoryuken-hp` unless the row is a coarse anti-air
  context:
  - self is grounded and ground action-start is allowed.
  - `obs_abs_dx` is inside the configured close/mid window, default `24-150`.
  - opponent routine looks jump/air-like by current validated coarse gate:
    `obs_opp_routine_1 == 0` and `obs_opp_routine_2` in `18-26`.
- added verbose probe diagnostics:
  - `dqn_dp_prior=...`
  - `dqn_dp_prior_penalty=...`
- added matching `tools/compare_dqn_models.py` support so the same model can be
  compared raw vs prior on identical observation rows.

Validation:
- `python3 -m py_compile tools/rl_probe_server.py tools/compare_dqn_models.py`
- direct helper smoke:
  - grounded neutral Shoryuken penalty: `0.04`.
  - anti-air routine Shoryuken penalty: `0.0`.
  - far-air Shoryuken penalty: `0.04`.
  - non-Shoryuken actions unchanged: `0.0`.
- same-observation compare after locating the promoted actor at
  `model/dqn-retrain-m3-bc-plus-dqn-v3/actor-v335.json`:
  - `logs/rl-transitions-v335-live-probe.ndjson`, first `5000` rows:
    - raw v335 Shoryuken top1 `11.1%`.
    - v336 prior Shoryuken top1 `6.3%`.
    - `244/5000` choices changed, all `base_shoryuken_to_other`; `0`
      choices changed from non-Shoryuken to Shoryuken.
  - P3 fireball-good/bad logs, first `5000` rows:
    - raw v335 Shoryuken top1 `4.8%`.
    - v336 prior Shoryuken top1 `3.0%`.
    - `91/5000` choices changed, all `base_shoryuken_to_other`; `0`
      choices changed from non-Shoryuken to Shoryuken.
  - `/tmp/rl-retrain-m1-mix-70-20-10.ndjson`, first `10000` rows:
    - raw v335 Shoryuken top1 `25.8%`.
    - v336 prior Shoryuken top1 `2.4%`.
    - `2342/10000` choices changed, all `base_shoryuken_to_other`; `0`
      choices changed from non-Shoryuken to Shoryuken.

Next:
- first live probe recommendation:
  - start with `--dqn-shoryuken-context-prior`
  - default `--dqn-shoryuken-prior-penalty 0.04`
  - keep existing valid-action mask and any v335-required probe flags.
- first live probe user observation:
  - `--dqn-shoryuken-prior-penalty 0.04` reduced live random / inappropriate
    Shoryuken use by roughly half.
  - this matches the offline direction from v335 live-probe and M1 movement
    replay comparisons, but does not fully solve the live behavior yet.
- promotion gate:
  - M1 / movement-like rows should show materially lower Shoryuken top1 rate.
  - anti-air/jump-in rows should still keep Shoryuken in top-k.
  - fireball-good behavior should not regress materially.
- recommended next A/B:
  - keep `0.04` as the v336 baseline.
  - test `--dqn-shoryuken-prior-penalty 0.06` as v336b if anti-air still
    appears available and fireball behavior did not regress in the first live
    probe.
  - if anti-air disappears, back off to `0.02` or widen the anti-air context
    rather than increasing the penalty.
- v336b live user observation:
  - `--dqn-shoryuken-prior-penalty 0.06` did not make anti-air noticeably
    worse.
  - random / inappropriate Shoryuken was reduced further.
  - policy mass began showing up as random / inappropriate normals instead,
    so the next issue is attack-family replacement rather than Shoryuken alone.
- support-prior smoke:
  - Tested v335 + Shoryuken `0.06` prior + existing DQN support prior
    (`min_count=500`, `count_penalty=0.02`, `negative_mean=0.01`).
  - Existing support prior did not materially fix the live-probe `stand-lp`
    replacement pattern (`stand-lp` stayed around `5.8%` on the v335 live-probe
    compare).
  - It is useful as a diagnostic but should not be treated as the v337 fix.
- recommended v337 direction:
  - keep Shoryuken context prior at `0.06` for now.
  - add an opt-in ground-normal context prior / reranker that penalizes
    stand/crouch normals outside plausible poke/contact/close-threat contexts,
    rather than increasing the Shoryuken penalty again.

## 2026-05-03: M3bc+dqn-v3 / v332 Corrective Plan And Trainer Foundations

Milestone:
- Milestone 6: fix v331 fireball-good and shoryuken-overgeneralization gates

Files changed:
- `tools/rl_probe_server.py`
- `tools/train_dqn_learner.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Diagnosis accepted from v331 review:
- Fireball-good did not become fireball top-1 because DQN still lacks a strong
  positive fireball launch signal and because the previous recipe let movement
  regression penalize far-range fireball as a generic attack.
- Shoryuken remained overgeneralized because positive special margin / reward
  pressure was not context-gated enough and still leaked into movement rows.
- The DQN feature schema had opponent routine context but no self routine
  context, even though transition rows already carry:
  - `obs_self_routine_1`
  - `obs_self_routine_2`
  - `obs_self_routine_attack_state`

Plan:
- Add self-routine context to DQN features:
  - one-hot `obs_self_routine_1`
  - one-hot `obs_self_routine_2`
  - scalar `obs_self_routine_attack_state`
- Preserve warm-start from existing BC/DQN models by expanding the first layer
  when an init model's feature names are a subset of the current feature
  schema; new feature weights start at zero.
- Exempt far grounded zoning fireball from movement regression so a correct
  long-range fireball candidate is not pushed below movement actions.
- Add opt-in context-gated special expert margin:
  - fireball margin only in far grounded zoning context.
  - shoryuken margin only when opponent routine looks airborne/jump-like.
  - tatsu margin only in close/mid range.
- Keep fireball action labels anchored to launch decisions; do not move labels
  to projectile-active frames. Delayed reward/credit and context gating should
  connect later projectile outcomes back to launch decisions.

Implementation:
- `tools/rl_probe_server.py`
  - `DQN_FEATURE_NAMES` now includes self routine one-hot features and
    `obs_self_routine_attack_state`.
  - `dqn_feature_value` can materialize the new one-hot self routine features.
- `tools/train_dqn_learner.py`
  - added init-model input feature expansion for subset-compatible feature
    schemas.
  - movement regression now removes fireball actions from attack competitors
    in far grounded zoning contexts.
  - added `--special-expert-margin-context-gate`.
  - added `--special-expert-margin-fireball-min-abs-dx`.

Validation:
- `python3 -m py_compile tools/rl_probe_server.py tools/train_dqn_learner.py`
- feature schema smoke:
  - current DQN feature count is `72`.
  - self routine one-hot features and `obs_self_routine_attack_state` are
    present.
- warm-start / trainer smoke:
  `python3 tools/train_dqn_learner.py logs/rl-transitions-retrain-p3-specials-human-v1.ndjson --model-dir /tmp/rl-v332-feature-expand-smoke --model-version 1 --init-model model/dqn-retrain-bc-coverage-m3-v1 --init-model-action-mode exact --limit 800 --steps 2 --batch-size 8 --hidden-sizes 64,64 --training-action-source auto --reward-risk-profile none --special-expert-margin-loss --special-expert-margin-context-gate --special-expert-margin-batch-size 2 --movement-regression-loss-weight 0.01 --movement-regression-action-groups stand-normal,crouch-normal,air-normal,fireball,shoryuken,tatsu --batch-sampling balanced --balanced-batch-ratios movement=0.4,normal=0.2,special=0.4 --dqn-valid-action-mask action-start-v1 --log-interval 1 --eval-limit 100 --diagnostic-top-n 8`
  - completed and published smoke model.
  - init model `v322` loaded successfully despite feature schema expansion.

Next:
- Train a new BC/DQN pair under the v332 schema, or warm-start DQN from
  `BC-coverage v322` with feature expansion as an ablation.
- Use `--special-expert-margin-context-gate` and remove fireball from any
  broad anti-attack pressure unless the fireball row is explicitly bad.
- Re-check:
  - fireball-good vs fireball-bad separation.
  - M1 movement shoryuken contamination.
  - P2/P3 action distribution drift.

## 2026-05-03: M3bc+dqn-v2 Training Execution Plan

Milestone:
- Milestone 6: next BC pre-training + DQN fine-tune candidate

Purpose:
- train the next M3bc+dqn candidate from a cleaner BC prior after fixing
  entropy backprop and reviewing segment-based KW propagation.

Plan:
- harden BC special-strength labeling before training:
  - only allow engine-outcome anchors to match a nearby following special
    segment.
  - stop matching if another special anchor or a competing special segment
    appears first.
  - skip special attack rows with missing KW instead of defaulting them to
    `fireball-lp`, `shoryuken-lp`, or `tatsu-mk`.
- train `BC-natural-v1` from only:
  - `logs/rl-transitions-retrain-p8-natural-human-v1.ndjson`
  - `logs/rl-transitions-retrain-p8-natural-cpudemo-v1.ndjson`
- train `BC-coverage-v1` from:
  - `/tmp/rl-retrain-m1-mix-70-20-10.ndjson`
  - `logs/rl-transitions-retrain-p2-normals-human-v1.ndjson`
  - `logs/rl-transitions-retrain-p2-far-whiff-negative-human-v1.ndjson`
  - `logs/rl-transitions-retrain-p3-specials-human-v1.ndjson`
  - `logs/rl-transitions-retrain-p8-natural-human-v1.ndjson`
  - `logs/rl-transitions-retrain-p8-natural-cpudemo-v1.ndjson`
- choose the better BC prior before DQN fine-tune; prefer natural if action
  coverage is adequate, otherwise coverage.
- DQN fine-tune should include the selected BC init plus mixed replay and
  `p3-fireball-good/bad` logs so fireball value is corrected by reward rather
  than only by imitation.

Quality gates:
- BC label coverage should stay above roughly `50%`.
- BC greedy distribution should not collapse to one movement action.
- specials should appear in top-k diagnostics without dominating natural play.
- DQN fine-tune should reduce v330's `shoryuken-lp 52.8%` concentration while
  making fireball-good rows prefer fireball more than fireball-bad rows.

## 2026-05-03: Execute M3bc+dqn-v2 Training Plan

Milestone:
- Milestone 6: BC pre-training + DQN fine-tune candidate v2

Files changed:
- `tools/train_dqn_learner.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- execute the documented next-model plan after the entropy-backprop fix.
- compare a pure natural-play BC prior against a larger coverage-oriented BC
  prior, then fine-tune DQN from the better prior with fireball-good/bad logs.

Implementation:
- hardened `_derive_segment_kw_map`:
  - limits anchor-to-segment matching to a short local row window.
  - stops if another special engine anchor appears first.
  - stops if a competing special attack segment appears first.
- hardened `derive_bc_label`:
  - explicit KW mappings are now required for fireball, shoryuken, and tatsu
    strength labels.
  - missing-KW special attack rows are skipped as `attack-unknown` instead of
    silently becoming `fireball-lp`, `shoryuken-lp`, or `tatsu-mk`.

Validation:
- `python3 -m py_compile tools/train_dqn_learner.py`

BC-natural-v1:
- Command:
  `python3 tools/train_dqn_learner.py logs/rl-transitions-retrain-p8-natural-human-v1.ndjson logs/rl-transitions-retrain-p8-natural-cpudemo-v1.ndjson --model-dir model/dqn-retrain-bc-natural-m3-v1 --model-version 321 --training-mode bc --replay-source-include human-demo,cpu-demo --steps 5000 --batch-size 64 --hidden-sizes 64,64 --learning-rate 0.001 --dqn-entropy-reg-weight 0.001 --log-interval 500 --eval-limit 5000 --diagnostic-top-n 12`
- Result:
  - rows: `24,754`
  - labeled: `19,835` (`80.1%`)
  - skipped: `attack-unknown 4,919`
  - loss: `3.717 -> 1.765`, avg `1.811`
  - top labels: `forward 7,128`, `back 4,287`, `stand-lp 2,338`,
    `fireball-lp 1,623`, `fireball-hp 1,375`, `shoryuken-lp 862`,
    `fireball-mp 530`, `tatsu-mk 424`
- Assessment:
  - pure P8 natural data is enough to train a BC baseline.
  - coverage is smaller than the full coverage recipe and weaker for throws /
    some normals, so it is useful as an A/B baseline but not the best DQN init.

BC-coverage-v1:
- Command:
  `python3 tools/train_dqn_learner.py /tmp/rl-retrain-m1-mix-70-20-10.ndjson logs/rl-transitions-retrain-p2-normals-human-v1.ndjson logs/rl-transitions-retrain-p2-far-whiff-negative-human-v1.ndjson logs/rl-transitions-retrain-p3-specials-human-v1.ndjson logs/rl-transitions-retrain-p8-natural-human-v1.ndjson logs/rl-transitions-retrain-p8-natural-cpudemo-v1.ndjson --model-dir model/dqn-retrain-bc-coverage-m3-v1 --model-version 322 --training-mode bc --replay-source-include human-demo,cpu-demo --steps 5000 --batch-size 64 --hidden-sizes 64,64 --learning-rate 0.001 --dqn-entropy-reg-weight 0.001 --log-interval 500 --eval-limit 5000 --diagnostic-top-n 12`
- Result:
  - rows: `118,556`
  - labeled: `86,881` (`73.3%`)
  - skipped: `attack-unknown 31,675`
  - loss: `3.701 -> 1.461`, avg `1.715`
  - top labels: `forward 37,346`, `back 25,195`, `stand-lp 4,135`,
    `fireball-lp 3,657`, `shoryuken-lp 2,508`, `fireball-hp 2,061`,
    `guard-crouch 1,854`, `tatsu-mk 1,622`
- Assessment:
  - better DQN init than BC-natural-v1 due to more labels, lower loss, and
    broader action coverage.

M3bc+dqn-v2 / v331:
- Init:
  - `model/dqn-retrain-bc-coverage-m3-v1`, version `322`.
- Added fireball split logs:
  - `logs/rl-transitions-retrain-p3-fireball-good-human-v1.ndjson`
  - `logs/rl-transitions-retrain-p3-fireball-bad-human-v1.ndjson`
- Key settings:
  - LR `0.0001`, gamma `0.95`, Double DQN, valid mask `action-start-v1`.
  - entropy reg `0.001` with fixed backprop.
  - balanced batch `movement=0.4,normal=0.2,special=0.4`.
  - fireball oversample reduced to even `8/8/8`; shoryuken oversample reduced
    to `4/5/6`.
  - special expert margin enabled with batch size `8`.
- Trainer result:
  - rows: `126,942`
  - experiences: `52,925`
  - loss: `5.211 -> 0.363`, avg `0.361`
  - special expert margin eligible: `5,067`
  - trainer eval top1: `back 45.8%`, `shoryuken-lp 38.9%`, `forward 15.4%`
  - top3 includes `fireball-hp 11.2%`
- Same-observation checks:
  - fireball-good log:
    - top1: `forward 83.8%`, `back 9.5%`, `shoryuken-lp 6.1%`
    - fireball did not appear top1.
  - fireball-bad log:
    - top1: `forward 83.8%`, `back 8.7%`, `shoryuken-lp 5.1%`,
      `fireball-hp 0.1%`
    - good/bad fireball split is not meaningfully separated.
  - M1 movement mix:
    - top1: `back 43.8%`, `shoryuken-lp 30.1%`, `forward 26.2%`
    - close/mid movement rows still over-prefer shoryuken-lp.

Conclusion:
- `v331` is not promotable.
- The plan did reduce v330's global shoryuken concentration
  (`52.8% -> 38.9%` on the trainer eval slice), but it failed the two most
  important gates:
  - fireball-good rows still do not choose fireball.
  - M1 movement rows still have too much shoryuken.
- Next attempt should treat fireball-good as a separate stronger supervised or
  margin target, and should reduce shoryuken margin/oversample pressure further
  or make shoryuken expert margin context-gated.

## 2026-05-03: Fix BC/DQN Entropy Regularization Backprop

Milestone:
- Milestone 6: BC pre-training + DQN fine-tuning implementation review

Files changed:
- `tools/train_dqn_learner.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- review the M3bc+dqn v330 training implementation and fix a trainer issue
  that made entropy tuning ineffective.

Implementation:
- added a shared entropy-regularization gradient helper for output logits/Qs.
- BC training now adds the gradient of `-weight * entropy(softmax(outputs))`
  to the same output gradient as cross-entropy.
- DQN training now adds the same entropy gradient before backpropagating each
  sampled transition.

Review finding:
- previous `--dqn-entropy-reg-weight` accounting changed printed loss and
  metadata but did not call `add_backward_grads` for the entropy term.
- as a result, v330's recorded `entropy_reg_weight=0.0003` did not actually
  reduce shoryuken concentration; future M3bc+dqn-v2 entropy sweeps need this
  fix to be meaningful.

Validation:
- `python3 -m py_compile tools/train_dqn_learner.py`
- BC smoke:
  `python3 tools/train_dqn_learner.py logs/rl-transitions-retrain-p3-specials-human-v1.ndjson --training-mode bc --steps 2 --batch-size 8 --limit 50 --model-dir /tmp/rl-bc-entropy-smoke-20260503 --model-version 1 --dqn-entropy-reg-weight 0.001 --log-interval 1`
  - completed; printed non-zero entropy regularization and published v1.
- DQN smoke:
  `python3 tools/train_dqn_learner.py logs/rl-transitions-retrain-p3-specials-human-v1.ndjson --steps 2 --batch-size 8 --limit 200 --model-dir /tmp/rl-dqn-entropy-smoke-20260503 --model-version 1 --dqn-entropy-reg-weight 0.001 --log-interval 1 --eval-limit 50`
  - completed; printed non-zero entropy regularization and published v1.

Follow-up:
- rerun M3bc+dqn-v2 after positive fireball data balancing; do not compare
  entropy settings against v330 as if v330's entropy regularization was active.

## 2026-05-02: M3a Fireball Formal Split Training Attempts

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / full-retrain Phase
  3 M3a fireball

Files changed:
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Inputs:
- collected mixed formal fireball log:
  `logs/rl-transitions-retrain-p3-fireball-human-v1.ndjson`.
- extracted split logs with `tools/extract_move_context_logs.py`:
  - `logs/rl-transitions-retrain-p3-fireball-good-human-v1.ndjson`
  - `logs/rl-transitions-retrain-p3-fireball-bad-human-v1.ndjson`
- also extracted event-only diagnostics:
  - `/tmp/rl-p3-fireball-good-events.ndjson`
  - `/tmp/rl-p3-fireball-bad-events.ndjson`

Data quality:
- source log: `12364` rows, `14` episodes, skipped JSON `0`.
- engine-labeled fireballs:
  - `fireball-hp 198`
  - `fireball-lp 127`
  - `fireball-mp 121`
- split extraction:
  - good: `375` events, `7173` context rows after overlap removal.
  - bad: `69` events, `1213` context rows after overlap removal.
- good split is clean:
  - no positive self-HP damage.
  - fireball outcome windows have `0%` punished.
- bad split is useful:
  - self HP damage is present.
  - fireball punished rates are roughly `61-75%` by strength.

Training attempts:
- `model/dqn-retrain-m3a-fireball-human-v1`, version `312`:
  rejected. Fireball pressure was too global:
  - M1 replay attack rate `84.9%`.
  - M1 top action `fireball-lp 77.5%`.
  - fireball-good context replay still did not make fireball top-1.
- `model/dqn-retrain-m3a-fireball-human-v2`, version `313`:
  rejected. Conservative settings overcorrected:
  - train summary collapsed to `forward 100%`.
  - fireball-good event rows also became `forward 98.4%`.
- `model/dqn-retrain-m3a-fireball-human-v3`, version `314`:
  rejected. M1 was safe but fireball did not activate:
  - M1 replay attack rate `6.6%`.
  - fireball-good event rows had no fireball top-1.
- `model/dqn-retrain-m3a-fireball-human-v4`, version `315`:
  rejected. Event-only training kept M1 near the gate but still failed the
  fireball-good gate:
  - M1 replay attack rate `9.9%`.
  - fireball-good event rows still had no fireball top-1.
- `model/dqn-retrain-m3a-fireball-human-v5`, version `316`:
  rejected. Offensive event-only settings brought fireball back, but polluted
  old skills:
  - M1 replay attack rate `46.6%`.
  - P2 replay attack rate `24.6%`.
  - fireball-good event rows still favored normals/forward more than fireball.
- `model/dqn-retrain-m3a-fireball-human-v6`, version `317`:
  rejected. Lowering special expert min reward increased eligibility but did
  not solve the gate conflict:
  - M1 replay attack rate `11.6%`.
  - fireball-good event rows still had no fireball top-1.

Conclusion:
- the formal fireball log is good enough; the blocker is not collection
  quality.
- recipe-only tuning is stuck between two failure modes:
  - strong special pressure teaches fireball-like actions outside fireball
    contexts and regresses M1/P2.
  - conservative movement regression preserves M1/P2 but suppresses fireball
    even on clean fireball-good event rows.
- the next M3a step should change trainer/features instead of running another
  reward-only sweep.

Likely code directions:
- add a move-family expert-margin mode that can target only selected
  event-source files or selector-tagged rows, instead of treating all eligible
  special examples as one global pressure.
- add explicit fireball context features or gates, such as opponent jump/attack
  recovery, projectile lane state, and current self fireball recovery/state, so
  the model can distinguish "zone now" from generic far movement.
- add a negative expert/ranking loss for bad fireball rows that suppresses
  fireball without teaching unrelated normals as the universal alternative.

## 2026-05-02: Remove Old Fireball-Named Extractor Entry Point

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / full-retrain Phase
  3 specials tooling

Files changed:
- `tools/extract_move_context_logs.py`
- `tools/extract_m3a_fireball_logs.py`
- `docs/agent-memory/remote-rl-retrain-data-collection-plan.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- finish the tool rename by removing the old fireball-specific script path.
- keep one canonical extractor entrypoint so future docs and commands do not
  drift between two names.

Implementation:
- deleted `tools/extract_m3a_fireball_logs.py`.
- kept `tools/extract_move_context_logs.py` as the only supported extractor.
- removed compatibility-wrapper wording from the collection plan.

Validation:
- `python3 -m py_compile tools/extract_move_context_logs.py`
- `python3 tools/extract_move_context_logs.py logs/rl-transitions-retrain-p3-specials-human-v1.ndjson --drop-overlap`
  - good: `167` events, `3488` rows before overlap removal.
  - bad: `54` events, `1143` rows before overlap removal.
  - overlap: `115` rows.

## 2026-05-02: Generalize Extracted Specials Log Tool

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / full-retrain Phase
  3 specials tooling

Files changed:
- `tools/extract_move_context_logs.py`
- `docs/agent-memory/remote-rl-retrain-data-collection-plan.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- turn the provisional fireball-only extractor into a reusable mixed-log
  extraction tool for later M3a/M3b/M3c split probes.
- preserve the existing fireball defaults while moving to a neutral tool name.

Implementation:
- introduced `tools/extract_move_context_logs.py` as the generalized
  implementation.
- added configurable move-family matching through:
  - `--actions` for exact engine action names.
  - `--action-prefixes` for family/prefix matches.
- replaced the hard-coded selector logic with OR-combined rule sets:
  - `--good-rule`
  - `--bad-rule`
- preserved preset behavior by mapping the old fireball selectors onto rules:
  - good default:
    `buckets=mid,far hit=1 punished=0` or `buckets=far punished=0`
  - bad default:
    `buckets=close` or `punished=1`

Validation:
- `python3 -m py_compile tools/extract_move_context_logs.py`
- default fireball dry-run on
  `logs/rl-transitions-retrain-p3-specials-human-v1.ndjson`:
  - good: `167` events, `3488` rows before overlap removal.
  - bad: `54` events, `1143` rows before overlap removal.
  - overlap: `115` rows.
- generalized shoryuken dry-run on the same mixed P3 log with custom rules:
  - good: `88` events, `1909` rows.
  - bad: `85` events, `1843` rows.
  - overlap: `21` rows.

Follow-up:
- use the generalized extractor for provisional shoryuken/tatsu split analysis
  only after formal fireball-good/fireball-bad collection is complete.
- if later stages need richer selectors, extend the rule grammar instead of
  adding another move-family-specific script.

## 2026-05-02: Probe M3a1 From Extracted Fireball Logs

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / full-retrain Phase
  3 M3a fireball

Files changed:
- `tools/extract_move_context_logs.py`
- `tools/extract_m3a_fireball_logs.py`
- `docs/agent-memory/remote-rl-retrain-data-collection-plan.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- test whether the existing mixed P3 specials log can bootstrap M3a before
  formal fireball-good/fireball-bad collection is finished.
- add a repeatable dry-run/extraction helper for provisional fireball
  good/bad logs.

Implementation:
- added the original fireball-focused extractor, later renamed to
  `tools/extract_move_context_logs.py`.
- default selector:
  - good: mid/far fireball hit without self HP damage, plus far fireball with
    no self HP damage as provisional zoning-good.
  - bad: close fireball or any fireball with self HP damage in the outcome
    window.
- extracted logs with overlap rows removed:
  - `logs/rl-transitions-retrain-p3-fireball-good-extracted-v1.ndjson`
    (`3373` rows).
  - `logs/rl-transitions-retrain-p3-fireball-bad-extracted-v1.ndjson`
    (`1028` rows).

Validation:
- `python3 -m py_compile tools/extract_move_context_logs.py`
- dry-run extraction:
  - good-combined: `167` events, `3488` context rows before overlap removal.
  - bad: `54` events, `1143` context rows before overlap removal.
  - overlap: `115` rows.
- analyzer on extracted good:
  - `3373` rows, `166` engine fireball rows.
  - fireball events: `fireball-lp 101`, `fireball-mp 47`,
    `fireball-hp 18`.
  - no self HP damage in the extracted-good file.
- analyzer on extracted bad:
  - `1028` rows, `54` engine fireball rows.
  - fireball events: `fireball-lp 29`, `fireball-mp 16`,
    `fireball-hp 9`.
  - `54` positive self-HP rows, matching the intended punished/bad signal.

M3a1 training:
- trained `model/dqn-retrain-m3a1-fireball-extracted`, version `311`.
- action set: accepted M2 v4c actions plus `fireball-lp`, `fireball-mp`, and
  `fireball-hp`.
- replay logs:
  - `/tmp/rl-retrain-m1-mix-70-20-10.ndjson`
  - `logs/rl-transitions-retrain-p2-normals-human-v1.ndjson`
  - `logs/rl-transitions-retrain-p2-far-whiff-negative-human-v1.ndjson`
  - `logs/rl-transitions-retrain-p3-fireball-good-extracted-v1.ndjson`
  - `logs/rl-transitions-retrain-p3-fireball-bad-extracted-v1.ndjson`
- used normals-only movement regression for this probe so far fireball-good
  contexts were not directly suppressed by movement regression.

M3a1 comparison results:
- M1 movement mix:
  - attack rate `13.1%`.
  - no fireball top-1.
  - top actions: `forward 57.0%`, `back 29.7%`, `stand-hk 7.1%`.
- P2 normals log:
  - attack rate `14.8%`.
  - no fireball top-1.
- fireball-good extracted:
  - attack rate `3.7%`.
  - no fireball top-1.
  - top actions: `forward 56.7%`, `back 39.5%`, `stand-hk 2.5%`.
- fireball-bad extracted:
  - attack rate `9.0%`.
  - no fireball top-1.
  - top actions: `forward 66.5%`, `back 21.1%`, `stand-hk 6.2%`.

Conclusion:
- M3a1 is rejected.
- Extracted fireball logs are useful as a repeatable diagnostic and sanity
  source, but they are too small/biased to bootstrap M3a into fireball top-1
  behavior.
- Next step remains formal collection of:
  - `logs/rl-transitions-retrain-p3-fireball-good-human-v1.ndjson`
  - `logs/rl-transitions-retrain-p3-fireball-bad-human-v1.ndjson`
- The extracted-log tool should be reused after formal collection as a dry-run
  selector check, not as the main training source.

## 2026-05-02: Plan M3 v7 Specials Diagnostic And Split P3 Collection

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / full-retrain Phase
  3 specials

Files changed:
- `docs/agent-memory/remote-rl-retrain-data-collection-plan.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- turn the M3 review feedback into an executable next-step plan.
- test whether M3 v5/v6 stayed too conservative because specials were included
  in movement regression.
- define split P3 logs so future collection separates special families and
  good/bad contexts instead of relying on one mixed `p3-specials` log.

Planned M3 v7 diagnostic:
- keep the v6-style recipe shape and train from accepted M2 v4c plus P3.
- change only the movement-regression action groups to
  `stand-normal,crouch-normal,air-normal`.
- keep `--special-expert-margin-loss` enabled.
- treat v7 as diagnostic unless both gates pass:
  - M1 replay attack rate below `10%`.
  - P3 replay attack rate materially above v5/v6 with at least one special
    reaching top-1 on meaningful P3 contexts.

Split P3 collection plan:
- `logs/rl-transitions-retrain-p3-fireball-good-human-v1.ndjson`
- `logs/rl-transitions-retrain-p3-fireball-bad-human-v1.ndjson`
- `logs/rl-transitions-retrain-p3-shoryuken-antiair-human-v1.ndjson`
- `logs/rl-transitions-retrain-p3-shoryuken-whiff-human-v1.ndjson`
- `logs/rl-transitions-retrain-p3-tatsu-hit-human-v1.ndjson`
- `logs/rl-transitions-retrain-p3-tatsu-blocked-human-v1.ndjson`

Validation plan:
- run M3 v7 locally against the existing replay set.
- compare M3 v7 on the M1 movement mix and the P3 specials log.
- if v7 fails either gate, stop recipe-only tuning and collect split P3 logs.

Validation results:
- trained `model/dqn-retrain-m3-specials-baseline-v7`, version `307`.
- command changed the v6-style recipe by setting
  `--movement-regression-action-groups stand-normal,crouch-normal,air-normal`.
- trainer completed `4000` steps and published the model.
- training summary:
  - replay rows: `93802`.
  - experiences: `31999`.
  - top greedy action: `forward 53.5%`.
  - special margin sampled/violated: `106924/106924`.
  - movement regression sampled/violated: `140098/140098`.
- M1 comparison:
  - command:
    `python3 tools/compare_dqn_models.py /tmp/rl-retrain-m1-mix-70-20-10.ndjson --model M3v7=model/dqn-retrain-m3-specials-baseline-v7 --limit 10000 --top-n 12 --focus-actions forward,back,guard-stand,guard-crouch,jump-forward-start,stand-mp,stand-hp,stand-mk,stand-hk,forward-hp,crouch-mp,crouch-hp,crouch-mk,crouch-hk,fireball-lp,fireball-mp,fireball-hp,shoryuken-lp,shoryuken-mp,shoryuken-hp,tatsu-lk,tatsu-mk,tatsu-hk --focus-rank-limit 3 --training-action-source auto --dqn-valid-action-mask action-start-v1`
  - result: attack rate `13.9%`, top `forward 59.8%`, no shoryuken top-1.
  - gate: failed the tentative M1 attack-rate gate of `<10%`.
- P3 comparison:
  - command:
    `python3 tools/compare_dqn_models.py logs/rl-transitions-retrain-p3-specials-human-v1.ndjson --model M3v7=model/dqn-retrain-m3-specials-baseline-v7 --limit 12000 --top-n 12 --focus-actions forward,back,guard-stand,guard-crouch,jump-forward-start,stand-mp,stand-hp,stand-mk,stand-hk,forward-hp,crouch-mp,crouch-hp,crouch-mk,crouch-hk,fireball-lp,fireball-mp,fireball-hp,shoryuken-lp,shoryuken-mp,shoryuken-hp,tatsu-lk,tatsu-mk,tatsu-hk --focus-rank-limit 3 --training-action-source auto --dqn-valid-action-mask action-start-v1`
  - result: attack rate `11.4%`, top `forward 53.4%`, no special top-1.
  - gate: failed because specials still did not become top-1 in P3 contexts.

Conclusion:
- M3 v7 is rejected.
- Removing specials from movement regression was not enough to resolve the M3
  seesaw.
- Stop recipe-only tuning on the mixed P3 log. The next executable step is to
  collect targeted split P3 logs, starting with fireball-good and fireball-bad,
  then analyze each split before another M3 training sweep.

Follow-up review decision:
- adopt incremental action-space expansion for Phase 3 instead of one
  all-specials M3 run.
- `M3a`: initialize from accepted M2 v4c and add only
  `fireball-lp/fireball-mp/fireball-hp`.
- `M3b`: initialize from accepted M3a and add
  `shoryuken-lp/shoryuken-mp/shoryuken-hp`.
- `M3c`: initialize from accepted M3b and add
  `tatsu-lk/tatsu-mk/tatsu-hk`.
- keep M1/M2 and prior-stage split logs in each later stage's replay mix to
  reduce catastrophic forgetting.
- implementation note: `--movement-regression-action-groups` accepts group
  names (`fireball`, `shoryuken`, `tatsu`), not individual action names such as
  `fireball-lp`.
- next immediate step: collect and analyzer-verify
  `logs/rl-transitions-retrain-p3-fireball-good-human-v1.ndjson` and
  `logs/rl-transitions-retrain-p3-fireball-bad-human-v1.ndjson`, then train
  M3a before collecting shoryuken/tatsu-heavy follow-up logs.

## 2026-05-02: Add Full-Retrain Collection Operator Runbook

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / controlled full
  retrain data collection

Files changed:
- `docs/agent-memory/remote-rl-retrain-data-collection-plan.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- make the full-retrain collection process executable from the documentation
  without relying on chat history.
- record per-phase log filenames, PowerShell probe commands, MiSTer config
  notes, action restrictions, collection content, CPU difficulty guidance, and
  pass gates.

Implementation:
- added an operator-facing runbook to the full-retrain collection plan.
- documented separate logs for curriculum, CPU-demo natural, human-demo
  natural, and on-policy correction data.
- recorded that M1 should keep Phase 1 movement data separate from Phase 8
  natural logs and mix them at training time.
- added a plan index link to the new runbook.

Validation:
- documentation-only change.
- reviewed markdown snippets and command/log names locally.

## 2026-05-02: Refine Full-Retrain Collection Plan Risk Gates

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / controlled full
  retrain data collection

Files changed:
- `docs/agent-memory/remote-rl-retrain-data-collection-plan.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- make the reboot collection plan more executable by addressing the main risks
  in the first draft:
  - humans cannot collect exact `time_to_self` buckets live.
  - projectile jump punish depends on opponent fireball recovery, not timing
    alone.
  - projectile-defense training can over-generalize into bad guard/back
    behavior against opponent jump-ins.
  - natural match data quality matters more than raw row count.
  - oki/wakeup is a core pressure situation and should be explicit curriculum
    data.
  - detectors/selectors must be validated before training on each collected
    phase.

Implementation:
- changed Phase 5 collection from exact live timing buckets to three
  operator-visible projectile cues: close, mid, and just-released/far.
- kept post-collection `time_to_self` bucket analysis, but added
  opponent-recovery/actionability as the missing split for `20-48` jump-forward
  punish.
- added detector dry-run gates to Phase 0 and every subsequent phase.
- marked Phase 6 anti-air as a required patch after Phase 5 and added an M5
  jump-in guard regression check.
- added oki/wakeup targets to defense/corner-pressure collection.
- changed Phase 8 natural data guidance from raw volume to a split of
  high-quality CPU-demo, serious human-demo, and structured mixed rounds.

Validation:
- documentation-only change.
- checked markdown diff locally.

## 2026-05-02: Add Full-Retrain Collection Plan To Future Task Tracking

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / controlled full
  retrain data collection

Files changed:
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- make the full-retrain data collection plan actionable in the main Milestone 6
  task tracker instead of leaving it as a standalone reference document.

Implementation:
- added phase-level future tasks for Phase 0 through Phase 8 collection.
- added a final cumulative M1-M8 warm-start training/regression tracking item.
- mirrored the same phase checklist in the Full-Retrain Collection Plan section
  so future agents can track collection status without re-reading the whole
  agent-memory document first.

Validation:
- documentation-only change.
- checked markdown diff and task links locally.

## 2026-05-02: Document Full-Retrain Data Collection Curriculum

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / controlled full
  retrain data collection

Files changed:
- `docs/agent-memory/remote-rl-retrain-data-collection-plan.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- record a from-scratch data collection plan for training a complete base DQN
  model with movement, attacks, specials, defense, jumping, anti-air,
  projectile timing, corner behavior, and natural match integration.
- avoid repeating the V41-V62 failure mode where sparse free-form gameplay logs
  underrepresent key defensive/projectile choices and reward shaping has to
  compensate for missing data.

Implementation:
- added an agent-memory plan that uses effective experiences rather than raw
  rows as the collection quota.
- split the reboot collection into phases:
  - schema and label sanity.
  - movement and spacing.
  - basic normals.
  - specials.
  - basic defense.
  - projectile defense timing.
  - anti-air and jump defense.
  - corner and pressure.
  - natural match integration and on-policy correction.
- recorded the V61/V62 projectile timing lesson directly in the projectile
  phase:
  - `0-12`: prefer guard/back.
  - `13-22`: still risky, not a universal safe-jump window.
  - `23-30`: current best live safe-jump window.
  - `31-48`: too-early jump risk.

Validation:
- documentation-only change.
- checked the new plan is linked from the Milestone 6 plan.

Follow-up:
- if the reboot is started, collect Phase 0 sanity logs first, then Phase 1
  movement data before attack or projectile-heavy logs.

## 2026-05-01: Add Training Mode Demo Transition Logging

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / controlled demo data collection

Files changed:
- `src/rl/rl_session.c`
- `tools/rl_probe_server.py`
- `tools/train_dqn_learner.py`
- `tools/analyze_rl_transitions.py`
- `docs/agent-memory/remote-rl-training-mode-demo-log.md`
- `docs/plan-remote-rl-agent.md`

Purpose:
- make training mode usable as a generic controlled-scenario transition source.
- first workflow: human controls the configured agent side, built-in
  dummy/CPU controls the opponent side, and the RL bridge records local demo
  transitions.
- keep remote DQN action override VS-only so training dummy/menu/record-replay
  state is not mixed with remote autopilot control.

Implementation:
- added a separate local demo recording gate that accepts training mode when
  gameplay is live (`mpp_w.inGame`, no pause, battle active).
- kept `RLSession_CanOverrideGameplayInput()` VS-only for remote action
  injection.
- bumped C-side transition rows to schema v6 with `mode_type` and `play_mode`
  metadata.
- updated Python replay tooling to accept both schema v5 and v6 so existing
  V52/V53/V54 logs remain trainable.
- added analyzer and trainer `--training-mode-hp-delta-mode raw|damage-only`;
  `damage-only` ignores negative HP deltas only for training-mode rows while
  preserving raw logged deltas by default.

Validation:
- `python3 -m py_compile tools/rl_probe_server.py tools/train_dqn_learner.py tools/analyze_rl_transitions.py`
- `python3 tools/analyze_rl_transitions.py logs/rl-transitions-human-demo-projectile-schema-v5-smoke-4-3-3.ndjson --tail-rows 200 --limit 5 --training-mode-hp-delta-mode damage-only`
  - confirmed schema-v5 backward compatibility (`schemas=5:200`).
  - old rows report `mode_type_counts=0:200`.
- `python3 tools/train_dqn_learner.py logs/rl-transitions-human-demo-projectile-schema-v5-smoke-4-3-3.ndjson --model-dir /tmp/rl-training-mode-demo-smoke --model-version 60501 --limit 200 --steps 1 --batch-size 16 --hidden-sizes 8 --log-interval 0 --training-mode-hp-delta-mode damage-only`
  - built `102` experiences from `200` schema-v5 rows.
  - reported `training_mode_hp=mode:damage-only sanitized_rows:0` because the
    old log has no training-mode metadata.
- `tools/mister/build-game.sh --flavor telemetry`
  - rebuilt `src/rl/rl_session.c`.
  - package created at `build/mister-telemetry-package`.

Follow-up:
- hardware validation still needed: run training mode with
  `rl-control-source = human-demo`, dummy/CPU opponent, and probe action output
  disabled; confirm uploaded rows have `execution_source=4`,
  `transition_schema_version=6`, and `mode_type=3` or `4`.
- inspect the first real training-mode log's raw positive/negative HP delta
  distribution before using `--training-mode-hp-delta-mode damage-only` in a
  real V55 retrain.

## 2026-05-01: Plan Auto-Retrain Replay Fix For Human Demo Mix

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / full action-set DQN experiments

Files changed:
- `docs/agent-memory/remote-rl-v52-projectile-margin.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Problem:
- `tools/rl_auto_retrain.py` falls back to the fixed source ratio
  `cpu-demo=0.50,human-demo=0.30,remote=0.20`.
- `tools/train_dqn_learner.py --replay-source-ratios` errors when a requested
  source has no rows.
- human-demo incremental chunks or targeted projectile demo logs may therefore
  fail even when the log is valid.
- source ratios also operate only on row `execution_source`, so a targeted new
  human-demo log can be diluted by older human-demo rows.

Planned fix:
- add `auto-available` source-ratio resolution in `rl_auto_retrain.py`.
- make auto retrain default to `auto-available` instead of the fixed
  three-source ratio.
- scan `base_logs + chunk_log` for available execution sources before building
  the trainer command.
- drop absent preferred sources and renormalize the rest.
- add log-level boost inputs such as repeatable `--extra-base-log` or
  `--boost-log PATH=N` so filtered projectile demo logs can be upweighted
  without removing general replay.
- record requested/resolved ratios, boost logs, and final replay plan in model
  metadata.
- improve dry-run diagnostics to show detected sources and resolved replay
  plan.

Interim workaround:
- for human-demo-only incremental retrain, pass
  `--replay-source-ratios human-demo=1`.
- for remote + human-demo, pass a ratio containing only those present sources.

Status:
- documented as the next code fix before relying on human-demo-heavy live
  incremental retrain.

## 2026-05-01: Implement V54 Late Defensive Margin For Live Retrain Readiness

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / full action-set DQN experiments

Files changed:
- `tools/train_dqn_learner.py`
- `tools/rl_auto_retrain.py`
- `docs/agent-memory/remote-rl-v52-projectile-margin.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- prepare the trainer and auto-retrain path for the next projectile-defense
  loop: keep reliable safe-jump behavior, but add a way to teach urgent and
  borderline projectile rows to prefer `back`/`guard-stand`/`guard-crouch`
  over jump when jump gets hit.

Implementation:
- added late defensive margin config, CLI flags, metadata, and stdout
  diagnostics.
- added `projectile_late_defensive_margin_eligible` on late jump-hit
  projectile rows.
- added an auxiliary margin loss:
  `Q(best_defensive) >= Q(best_jump) + margin`.
- added extra late defensive margin minibatch sampling.
- added `projectile-response-v5` to `tools/rl_auto_retrain.py`.

Validation:
- `python3 -m py_compile tools/train_dqn_learner.py tools/rl_auto_retrain.py`
- preset check for `projectile-response-v5`.
- smoke train to `/tmp/rl-v54-late-def-smoke`.
- full random-init V54 train to
  `model/dqn-projectile-schema-v5-full-actions-v54-late-def-margin-candidate`.
- V53 warm-start fine-tunes to:
  - `model/dqn-projectile-schema-v5-full-actions-v54-late-def-finetune-candidate`
  - `model/dqn-projectile-schema-v5-full-actions-v54-late-def-conservative-candidate`

Findings:
- smoke confirmed the late defensive objective is wired correctly:
  - eligible experiences: `168`
  - sampled rows were mostly `7-12`, with some `0-6`
  - no empty valid/defensive/jump masks.
- random-init V54 was not acceptable:
  - reliable expert Q-gap top-1 dropped to `1650/1740` (`94.8%`).
  - `tatsu-mk` returned as a projectile blocker.
- V53 warm-start V54 was better but still not promotable:
  - full-strength fine-tune kept expert Q-gap at `1710/1740` (`98.3%`) but
    still let `tatsu-mk` appear and did not flip late-hit rows to guard/back.
  - conservative fine-tune preserved V53 projectile behavior
    (`1730/1740` expert top-1) but also did not change late-hit top actions.
- old demo data mostly contains "jump failed" evidence for urgent/borderline
  rows, not clean examples of the correct defensive replacement action.

Conclusion:
- V54 trainer support and `projectile-response-v5` are ready for targeted demo
  and live incremental retrain experiments.
- No old-demo-only V54 candidate should be promoted as the live actor.
- Before live incremental retrain, collect targeted human-demo projectile
  defense rows, especially `time_to_self <= 12` guard/back success examples.
- Use `projectile-response-v5` conservatively: late defensive margin weight
  `0.25`, batch size `8`, max timing `12`.

## 2026-05-01: Implement And Analyze V53 Projectile Timing Split

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / full action-set DQN experiments

Files changed:
- `tools/train_dqn_learner.py`
- `tools/rl_auto_retrain.py`
- `docs/agent-memory/remote-rl-v52-projectile-margin.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Implementation:
- added `--projectile-expert-margin-min-time-to-self` and
  `--projectile-expert-margin-max-time-to-self`.
- kept the V52 jump-group expert margin, but allowed V53 to apply it only to
  reliable/setup projectile timing buckets.
- added margin and Q-gap diagnostics by `obs_projectile_time_to_self` bucket.
- added `tools/rl_auto_retrain.py --reward-preset projectile-response-v4`,
  which is V52's `projectile-response-v3` recipe plus margin timing
  `13..48`.

Validation:
- `python3 -m py_compile tools/train_dqn_learner.py tools/rl_auto_retrain.py`
- smoke train to `/tmp/rl-v53-timing-smoke` with `--steps 8`.
- full train to
  `model/dqn-projectile-schema-v5-full-actions-v53-timing-split-candidate`
  with model version `53`, `--steps 3000`, and the V52 recipe plus
  `--projectile-expert-margin-min-time-to-self 13`
  `--projectile-expert-margin-max-time-to-self 48`.

Training result:
- V53 margin eligibility: `1740` experiences, down from V52's `1830`, all in
  timing buckets `13-24` and `25-48`.
- final projectile margin loss: `0.000091`.
- reliable/setup expert Q-gap:
  - rows: `1740`
  - top-1: `1730/1740` (`99.4%`)
  - positive gap: `10/1740`
  - remaining blocker: `shoryuken-hp` on `10` rows, all in `13-24`.

Offline comparison:
- On the human-demo incoming projectile + jump-start-allowed rows, V53's
  greedy actions were effectively identical to V52:
  - `0-6`: jump `52/55`, `shoryuken-hp` `3/55`
  - `7-12`: jump `315/323`, `shoryuken-hp` `2/323`, `tatsu-mk` `5/323`
  - `13-24`: jump `672/685`
  - `25-48`: jump `469/470`
- On `logs/rl-transitions-v52-live-probe.ndjson`, V53 also predicted the same
  actions as V52 for the 43 incoming projectile fresh decisions:
  - `7-12`: jump `9/10`; both damaged rows still predicted jump.
  - `13-24`: jump `13/13`; damaged rows still predicted jump.
  - `25-48`: jump `18/18`; damaged rows still predicted jump.

Conclusion:
- V53 is useful as diagnostic and reproducibility infrastructure, but it is not
  a behavior improvement over V52.
- Simply removing expert margin from urgent/borderline buckets does not make
  the network choose guard/back there; reward/oversample and neighboring
  reliable-bucket generalization still keep jump ranked high.
- Do not promote V53 over V52.
- V54 should add an explicit late-jump-hit defensive margin that pushes
  `guard-stand`/`guard-crouch`/`back` above jump on damaged urgent/borderline
  projectile rows.

## 2026-05-01: Record V52 Projectile Margin Reference And V53 Direction

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / full action-set DQN experiments

Files changed:
- `docs/agent-memory/remote-rl-v52-projectile-margin.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`
- `AGENTS.md`

Purpose:
- preserve the V52 projectile expert margin recipe as a named milestone so
  future work can reproduce the exact training run instead of reconstructing it
  from chat or scattered metadata.
- record the live V52 probe findings and turn them into a concrete V53 timing
  split plan.

Reference:
- [docs/agent-memory/remote-rl-v52-projectile-margin.md](agent-memory/remote-rl-v52-projectile-margin.md)

Key points recorded:
- full V52 trainer parameters and reproduction command.
- why jump-start equivalence is part of the margin objective.
- offline V48/V50/V51/V52 iteration findings.
- V52 live probe findings from `logs/rl-transitions-v52-live-probe.ndjson`.
- V53 direction:
  - keep V52 jump-group margin.
  - split incoming projectile rows by `obs_projectile_time_to_self`.
  - avoid forcing jump in urgent/borderline buckets.
  - keep safe-jump margin for reliable/setup buckets.
  - add late-jump-hit diagnostics and possibly a defensive negative margin.

Validation:
- documentation links checked locally with `rg`.
- no code changes in this documentation pass.

## 2026-05-01: Implement And Validate Projectile Expert Margin V52

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / full action-set DQN experiments

Files changed:
- `tools/train_dqn_learner.py`
- `tools/rl_auto_retrain.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`
- generated candidates under `model/dqn-projectile-schema-v5-full-actions-v48-*`,
  `v49-*`, `v50-*`, `v51-*`, and `v52-*` (untracked)

Implementation:
- added projectile expert margin eligibility on clean safe human-demo
  jump-start responses to incoming projectiles.
- added model metadata/stdout diagnostics for:
  - sampled margin events, violations, loss, invalid/empty masks.
  - expert Q-gap rows, unique rows, top-1/top-5 matches, mean gap, mean rank,
    and blocker action counts.
- added `--projectile-expert-margin-batch-size` so each DQN step can draw an
  extra margin-only minibatch from safe-jump expert rows. Normal replay
  sampling saw too few expert rows.
- added `--projectile-expert-margin-equivalent-jump-actions` and made it the
  default for projectile expert margin. Safe anti-fireball behavior needs the
  jump-start group to beat non-jump actions; forcing
  `jump-forward-start`/`jump-neutral-start`/`jump-back-start` to beat each
  other created unnecessary conflicts.
- updated `tools/rl_auto_retrain.py --reward-preset projectile-response-v3` to
  use the V52 recipe:
  - V47 projectile-response-v2 reward/oversampling base.
  - `--projectile-expert-margin-loss`
  - `--projectile-expert-margin 0.1`
  - `--projectile-expert-margin-weight 1.0`
  - `--projectile-expert-margin-batch-size 32`
  - `--projectile-expert-margin-equivalent-jump-actions`
  - `--projectile-expert-margin-valid-action-mask action-start-v1`

Validation:
- `python3 -m py_compile tools/train_dqn_learner.py tools/rl_auto_retrain.py`
- smoke training with `--limit 5000 --steps 8` and margin batch `32` completed.
- `tools/rl_auto_retrain.py --help` lists `projectile-response-v3`.
- external targeted comparison over
  `logs/rl-transitions-human-demo-projectile-schema-v5-smoke-4-3-3.ndjson`.

Iteration results:
- V48 (`weight=0.05`, normal replay batch only) was too weak:
  - safe expert rows still top-1 `0/1830`; mean group-unaware gap about `0.147`.
- V50 (`weight=5.0`, normal replay batch only) proved the direction was right
  but still under-sampled:
  - safe expert top-1 improved to `120/1830`; mean gap `0.044`.
- V51 (`weight=1.0`, margin batch `32`, exact action margin) made jump viable
  but exposed jump-direction conflicts:
  - safe-jump unique rows any-jump top-1 `151/181` (`83.4%`).
  - remaining blockers included `tatsu-mk` and `shoryuken-hp`.
- V52 (`weight=1.0`, margin batch `32`, jump-start equivalence) resolves the
  original failure mode:
  - model metadata safe-jump group Q-gap: top-1 `1820/1830` (`99.5%`),
    top-5 `1830/1830`, positive gap `10/1830`, mean gap `-0.097`.
  - targeted safe-jump unique rows: any-jump top-1 `180/181` (`99.4%`),
    `shoryuken-hp` top-1 `1/181` (`0.6%`), `tatsu-mk` top-1 `0/181`.
  - incoming projectile + jump-start-allowed rows: any-jump top-1
    `1508/1533` (`98.4%`), `shoryuken-hp` top-1 `11/1533` (`0.7%`),
    `tatsu-mk` top-1 `13/1533` (`0.8%`).

Decision:
- keep V52 / `projectile-response-v3` as the current offline candidate recipe
  for anti-fireball jump behavior.
- do not promote V48/V49/V50/V51.
- next validation should be a live probe/smoke on MiSTer before publishing as
  the default remote actor.
- milestone reference after live probe:
  [docs/agent-memory/remote-rl-v52-projectile-margin.md](agent-memory/remote-rl-v52-projectile-margin.md)

## 2026-05-01: V48 Projectile Expert Margin Plan

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / full action-set DQN experiments

Purpose:
- turn the V47 negative result into a targeted fix: first measure whether safe
  human anti-fireball jump labels lose the model's Q ranking, then train with
  an explicit valid-action-masked expert margin loss on those rows only.

Plan:
- add Q-gap diagnostics for projectile expert rows:
  - source must be `human-demo`.
  - action must be `jump-forward-start`, `jump-neutral-start`, or
    `jump-back-start`.
  - row must satisfy the incoming projectile response threat classifier.
  - by default the outcome must be a clean safe jump, not a late jump-hit.
  - report expert rank, top action, top-vs-expert Q gap, positive-gap counts,
    and blocker action counts.
- add opt-in margin training:
  - apply only to projectile expert rows above.
  - use the same schema-backed action-start valid-action mask for competitors.
  - use a max-violator hinge:
    `max(0, max_a(Q(s,a)+margin) - Q(s,expert))`.
  - keep the margin small and Q-scale-aware; start with `margin=0.1` and
    `weight=0.05`.
  - record loss/event diagnostics in stdout and model metadata.
- train V48 from the V47 projectile-response-v2 recipe plus the margin loss.

Expected effect:
- on safe-jump expert rows, the expert jump rank should move toward top-1 and
  `Q(top)-Q(expert)` should shrink or become negative.
- on incoming projectile + jump-start-allowed rows, `jump_top1` should become
  nonzero and `jump_top5` should improve beyond the V46/V47 `13.1%` baseline.

Risk / side effect:
- if margin is too strong or too broad, the model may over-prefer jump in
  unrelated states.
- mitigation: opt-in only, safe-jump-only by default, human-demo-only, and
  valid-action-masked competitors.

## 2026-05-01: Add Projectile Oversampling And Train V47 Candidate

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / full action-set DQN experiments

Files changed:
- `tools/train_dqn_learner.py`
- `tools/rl_auto_retrain.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`
- `model/dqn-projectile-schema-v5-full-actions-v47-oversample-candidate/`
  (generated, untracked)

Purpose:
- respond to V46 showing that standalone human projectile data is trainable but
  still leaves incoming projectile rows dominated by `shoryuken-hp`.
- add opt-in replay-copy oversampling for projectile-response outcomes so safe
  jump-start rows are sampled directly, not only rewarded sparsely.
- train a V47 candidate with safe-jump oversampling, late-jump-hit
  oversampling, reduced Shoryuken engine-outcome oversampling, and a larger
  safe-jump reward.

Implementation notes:
- added `ProjectileResponseOutcome` so reward shaping and oversampling share
  the same classifier for incoming projectile response rows.
- added trainer flags:
  - `--projectile-response-safe-jump-oversample`
  - `--projectile-response-late-jump-hit-oversample`
  - `--projectile-response-close-back-oversample`
  - `--projectile-response-close-guard-oversample`
- default multiplier `1` preserves existing replay behavior.
- when oversampling creates multiple copies of an action-start experience,
  delayed reward and next-state updates are applied to every copy.
- added `--reward-preset projectile-response-v2` to `tools/rl_auto_retrain.py`:
  - `safe_jump_bonus=2.0`
  - safe jump oversample `10`
  - late jump-hit oversample `4`
  - close back/guard oversample `3`
  - Shoryuken engine oversamples reduced from `8/10/12` to `4/5/6`

Validation:
- `python3 -m py_compile tools/train_dqn_learner.py tools/rl_auto_retrain.py`
- smoke training on the first `5000` rows completed:
  - experiences: `3255`
  - `projectile_oversample=96/+648`
  - `safe_jump=60/+540`
  - `late_jump_hit=36/+108`

Training recipe:
- source log:
  `logs/rl-transitions-human-demo-projectile-schema-v5-smoke-4-3-3.ndjson`
- model dir:
  `model/dqn-projectile-schema-v5-full-actions-v47-oversample-candidate`
- model version: `47`
- full V47/v2 recipe:
  - `--reward-projectile-safe-jump-bonus 2.0`
  - `--projectile-response-safe-jump-oversample 10`
  - `--projectile-response-late-jump-hit-oversample 4`
  - `--projectile-response-close-back-oversample 3`
  - `--projectile-response-close-guard-oversample 3`
  - `--engine-outcome-action-oversamples` with Shoryuken `4/5/6`
  - `--dqn-valid-action-mask action-start-v1`
  - `--dqn-unsupported-action-regularization`

Training result:
- training completed and published version `47`.
- rows: `59117`
- experiences: `30844`
- projectile shaping:
  - `threat_rows=898`
  - `safe_jump=183/366.0`
  - `late_jump_hit=67/100.5`
  - `close_back=0/0.0`
  - `close_guard=3/2.4`
  - `projectile_net=267.9`
- projectile oversampling:
  - `base=253`, `extra=1854`
  - `safe_jump=183/+1647`
  - `late_jump_hit=67/+201`
  - `close_guard=3/+6`
  - extra by action:
    `jump-forward-start=972`,
    `jump-neutral-start=630`,
    `jump-back-start=246`,
    `guard-stand=6`
- trainer eval slice greedy distribution:
  - `forward 2710 / 5000 = 54.2%`
  - `back 849 / 5000 = 17.0%`
  - `shoryuken-hp 791 / 5000 = 15.8%`

Targeted validation:
- incoming opponent projectile rows: `2953`
- incoming + jump-start-allowed rows: `1557`
- V46 incoming + jump-start-allowed:
  `shoryuken-hp 1339 / 1557 = 86.0%`,
  `jump_top1=0`, `jump_top5=204 / 1557 = 13.1%`
- V47 incoming + jump-start-allowed:
  `shoryuken-hp 1337 / 1557 = 85.9%`,
  `forward 201 / 1557 = 12.9%`,
  `jump_top1=0`, `jump_top5=204 / 1557 = 13.1%`
- V47 projectile-shape threat + jump-start-allowed:
  `shoryuken-hp 1313 / 1533 = 85.6%`,
  `jump_top1=0`, `jump_top5=204 / 1533 = 13.3%`

Interpretation:
- V47 proves the oversampling machinery works and is stable, but it is not
  promotable for the projectile-response goal.
- The negative result is useful: simple replay-copy oversampling plus larger
  safe-jump reward still does not make jump-start actions competitive on the
  incoming projectile observations.
- The failure mode is probably not just row scarcity. The next attempt should
  inspect Q ranks/Q gaps on the actual safe-jump training rows and consider
  either an explicit projectile-response action-target auxiliary loss or a
  projectile-focused batch/eval path that trains only on threat rows.

Follow-up:
- do not promote V47 as the live model.
- before V48, add diagnostics for same-row safe-jump training examples:
  action label, model top action, jump action rank, and Q gap.
- if diagnostics confirm jump rows still rank Shoryuken/forward above their
  own action label, implement an explicit behavior-cloning or margin loss on
  projectile-response rows rather than another reward-only retrain.

## 2026-05-01: Train V46 Standalone Human Projectile Candidate

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / full action-set DQN experiments

Files changed:
- `model/dqn-projectile-schema-v5-full-actions-v46-standalone-candidate/`
  (generated, untracked)

Purpose:
- train the first full v46 candidate from the larger standalone human-demo
  projectile schema-v5 log instead of the smaller V41-V44 projectile smoke log.
- verify whether the improved projectile-response support is enough by itself
  to move incoming projectile rows away from Shoryuken collapse and toward
  jump/back/guard responses.

Training recipe:
- source log:
  `logs/rl-transitions-human-demo-projectile-schema-v5-smoke-4-3-3.ndjson`
- model dir:
  `model/dqn-projectile-schema-v5-full-actions-v46-standalone-candidate`
- model version: `46`
- base recipe: V45 standalone/full-action settings:
  - `--reward-projectile-response-profile incoming-v1`
  - `--dqn-valid-action-mask action-start-v1`
  - `--dqn-unsupported-action-regularization`
  - balanced batches with `movement=0.25,normal=0.45,special=0.30`

Training result:
- training completed and published version `46`.
- rows: `59117`
- experiences: `30185`
- source mix: `human-demo=100%`
- projectile shaping:
  - `threat_rows=898`
  - `safe_jump=183/219.6`
  - `late_jump_hit=67/100.5`
  - `close_back=0/0.0`
  - `close_guard=3/2.4`
  - `projectile_net=121.5`
- trainer eval slice greedy distribution:
  - `forward 2340 / 5000 = 46.8%`
  - `shoryuken-hp 910 / 5000 = 18.2%`
  - `back 902 / 5000 = 18.0%`
  - `shoryuken-mp 305 / 5000 = 6.1%`

Validation:
- full same-log compare with `--dqn-valid-action-mask action-start-v1`:
  - V45: `back 26061 / 59117 = 44.1%`,
    `forward 17700 / 59117 = 29.9%`,
    `shoryuken-hp 7609 / 59117 = 12.9%`
  - V46: `forward 28639 / 59117 = 48.4%`,
    `back 15506 / 59117 = 26.2%`,
    `shoryuken-hp 5890 / 59117 = 10.0%`,
    `shoryuken-mp 4843 / 59117 = 8.2%`
  - changed rows: `16729 / 59117`
- targeted incoming-projectile rows:
  - incoming opponent projectile rows: `2953`
  - incoming + jump-start-allowed rows: `1557`
  - V45 incoming + jump-start-allowed:
    `shoryuken-hp 1341 / 1557 = 86.1%`,
    `jump_top1=0`, `jump_top5=204 / 1557 = 13.1%`
  - V46 incoming + jump-start-allowed:
    `shoryuken-hp 1339 / 1557 = 86.0%`,
    `forward 201 / 1557 = 12.9%`,
    `jump_top1=0`, `jump_top5=204 / 1557 = 13.1%`
  - V46 projectile-shape threat + jump-start-allowed:
    `shoryuken-hp 1315 / 1533 = 85.8%`,
    `jump_top1=0`, `jump_top5=204 / 1533 = 13.3%`

Interpretation:
- V46 is trainable and avoids global single-action collapse, but it is not
  promotable for the projectile-response goal.
- The larger standalone human-demo log fixes the data-volume problem from
  V41-V44, but the current reward/oversampling recipe still does not make
  `jump-*-start` competitive on incoming projectile rows.
- V46 mostly shifts global behavior from V45's `back` bias toward `forward`,
  while projectile-threat rows remain dominated by `shoryuken-hp`.

Follow-up:
- do not promote V46 as the live model.
- next attempt should add explicit projectile-response row oversampling or
  action-target curriculum so safe jump-start rows are sampled directly, not
  only rewarded sparsely.
- consider separating projectile-response evaluation/training batches from the
  general movement/attack balanced sampler before another full-action retrain.

## 2026-05-01: Train Projectile Response V42-V44 Candidates

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / full action-set DQN experiments

Files changed:
- `tools/rl_auto_retrain.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`
- `model/dqn-projectile-schema-v5-full-actions-v42-response/` (generated,
  untracked)
- `model/dqn-projectile-schema-v5-full-actions-v43-response/` (generated,
  untracked)
- `model/dqn-projectile-schema-v5-full-actions-v44-response-unsupported-reg/`
  (generated, untracked)

Purpose:
- run the first projectile-response shaped candidates against the same
  schema-v5 projectile smoke log used by V41.
- verify whether explicit safe-jump / late-jump / close back-guard shaping can
  move same-log incoming projectile rows away from `shoryuken-hp`.

Commands:
- V42/V43/V44 all used:
  `logs/rl-transitions-projectile-schema-v5-smoke-4-3-3.ndjson`
- V42:
  - model dir: `model/dqn-projectile-schema-v5-full-actions-v42-response`
  - projectile filter: `time_to_self=2..24`, `abs(rel_y)<=48`
- V43:
  - model dir: `model/dqn-projectile-schema-v5-full-actions-v43-response`
  - projectile filter: `time_to_self=2..48`, `abs(rel_y)<=96`
- V44:
  - model dir:
    `model/dqn-projectile-schema-v5-full-actions-v44-response-unsupported-reg`
  - same V43 projectile filter plus train-time
    `--dqn-unsupported-action-regularization`.

Results:
- V42 failed as a shaping smoke:
  - `projectile_shape threat_rows=4`
  - `safe_jump=0`, `late_jump_hit=0`, `close_back=0`, `close_guard=0`
  - global greedy still collapsed to `shoryuken-hp 70.4%` on trainer eval.
- Action-start diagnostics showed the filter was too narrow:
  - same-row incoming projectile starts: `106`
  - actions: `back=72`, `jump-forward-start=17`, `jump-back-start=7`,
    `jump-neutral-start=4`, `forward=6`
  - many real projectile rows use `obs_projectile_rel_y=66` and
    `time_to_self=25-48`.
- V43 fixed the shaping filter:
  - `projectile_shape threat_rows=89`
  - `safe_jump=18/21.6`
  - `late_jump_hit=10/15.0`
  - `close_back=0`, `close_guard=0`, because this smoke log's projectile-back
    rows are far opponent-spacing rows (`obs_abs_dx ~= 306..328`), not
    close-range back/guard samples.
- V43 same-log projectile behavior did not improve:
  - incoming projectile + jump-start-allowed rows:
    `shoryuken-hp 313 / 343`, `jump_top=0`, `jump_top5=25`
  - narrowed V43 filter rows:
    `shoryuken-hp 272 / 302`, `jump_top=0`, `jump_top5=25`
- V44 unsupported-action regularization helped only slightly:
  - global same-log `shoryuken-hp`: V41 `4228 / 7783 = 54.3%`, V44
    `4022 / 7783 = 51.7%`
  - incoming projectile + jump-start-allowed rows: V41 `309 / 343`, V44
    `306 / 343`
  - `jump_top` remained `0`.

Interpretation:
- The projectile-response reward code is now wired correctly and measurable.
- The current replay distribution is still too weak for a full-action DQN:
  only `45` jump-start rows exist, `33` are near incoming projectiles, and
  there are no close-range guard/back projectile samples in this log.
- Zero/low-support action overestimation remains a major issue; unsupported
  action regularization alone is not strong enough to make jump-over behavior
  emerge.

Follow-up:
- do not promote V42, V43, or V44.
- add projectile-response row oversampling / batch grouping, or build an
  explicit projectile-response action-target curriculum from the analyzer's
  near-projectile labels, before another full recipe retrain.
- collect or synthesize close-range guard/back projectile-response rows before
  expecting the close back/guard bonuses to affect training.

## 2026-05-01: Add Opt-In Projectile Response Reward Shaping

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / full action-set DQN experiments

Files changed:
- `tools/train_dqn_learner.py`
- `tools/rl_auto_retrain.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- stop blindly retraining the same generic full-action recipe after V41 showed
  schema-v5 projectile features alone do not teach anti-fireball behavior.
- add explicit trainer-side credit for safe jump-over, close successful
  back/guard responses, and late jump-into-projectile failures.

Implementation notes:
- added `--reward-projectile-response-profile incoming-v1`, defaulting to
  `off` so existing recipes keep identical reward behavior.
- incoming threats require an opponent-owned active projectile in front of the
  agent, moving toward the agent, with configurable `time_to_self`, `rel_x`,
  and `rel_y` bounds.
- `jump-*-start` gets an optional safe-jump bonus only when the response window
  stays clean, the agent becomes airborne, and the projectile clears/passes.
- `jump-*-start` gets an optional late-jump cost when the response window takes
  self HP damage.
- close `back` can receive a clean response bonus when spacing increases or
  the projectile clears/passes.
- close `guard-stand` / `guard-crouch` can receive a clean response bonus,
  requiring guard contact by default.
- added `--reward-preset projectile-response-v1` to `tools/rl_auto_retrain.py`;
  it extends `ground-specials-v35a` with the projectile-response knobs rather
  than changing older presets.

Validation:
- `python3 -m py_compile tools/train_dqn_learner.py tools/rl_auto_retrain.py tools/rl_probe_server.py`
- direct synthetic `build_experiences` smoke:
  - safe projectile response produced `jump-forward-start=+1.2`,
    `back=+0.6`, and `guard-stand=+0.8`.
  - late jump-hit smoke produced natural HP loss plus projectile cost:
    `jump-forward-start=-11.5`, with `late_jump_hit_cost_total=1.5`.

Follow-up:
- train the first projectile-response model with
  `--reward-preset projectile-response-v1` and compare same-log incoming
  projectile rows against V41.
- add projectile-row greedy diagnostics by `time_to_self` bucket if the first
  shaped model still collapses into a non-response action.

## 2026-05-01: Train V41 Projectile-Aware Baseline

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / full action-set DQN experiments

Files changed:
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`
- `model/dqn-projectile-schema-v5-full-actions-v41-baseline/` (generated,
  untracked)

Purpose:
- test the clean baseline before adding projectile-specific curriculum:
  schema-v5 projectile features plus the existing full-action DQN recipe.
- verify whether the model can learn anti-fireball `jump-*-start`, `back`, or
  guard decisions from the targeted projectile smoke log without new reward
  shaping.

Training recipe:
- source log:
  `logs/rl-transitions-projectile-schema-v5-smoke-4-3-3.ndjson`
- model dir:
  `model/dqn-projectile-schema-v5-full-actions-v41-baseline`
- model version: `41`
- base recipe: V38/V40 full-action DQN settings.
- key change from V40: `--dqn-valid-action-mask action-start-v1`, using the
  schema-backed ground/jump/air action-start fields.
- no projectile-specific reward shaping or projectile oversampling was added.

Training result:
- training completed and published version `41`.
- rows: `7783`
- experiences: `1937`
- source mix: `human-demo=100%`
- masked trainer greedy distribution on the eval slice:
  - `shoryuken-hp 1367 / 1937 = 70.6%`
  - `stand-mk 218 / 1937 = 11.3%`
  - `back 149 / 1937 = 7.7%`
- trainer emitted a collapse warning for `shoryuken-hp`.

Validation:
- same-log compare with `--dqn-valid-action-mask action-start-v1` reported:
  - `shoryuken-hp 4228 / 7783 = 54.3%`
  - `forward-hp 931 / 7783 = 12.0%`
  - `stand-mk 910 / 7783 = 11.7%`
  - `back 907 / 7783 = 11.7%`
- targeted projectile-row diagnostic:
  - incoming opponent projectile rows with `obs_self_jump_start_allowed=1`:
    `343`
  - top action on those rows:
    `shoryuken-hp 309 / 343 = 90.1%`
  - `jump_top=0 / 343`
  - any `jump-*-start` in top five: `25 / 343`
- strong support-prior diagnostic:
  - used `min_count=300`, `count_penalty=0.15`,
    `negative_mean_penalty=0.05`, exempting movement/guard actions.
  - overall top action became `back 6191 / 7783 = 79.5%`.
  - incoming projectile + jump-start-allowed rows still had
    `shoryuken-hp 260 / 343 = 75.8%` and `jump_top=0`.

Interpretation:
- V41 is not promotable.
- the schema-v5 projectile fields are available to the model, but the old
  generic full-action recipe does not create a usable anti-fireball policy.
- the immediate failure mode is sparse/full-action overestimation
  (`shoryuken-hp` has no replay support but dominates legal ground rows), plus
  no positive objective for safe jump-over timing.

Follow-up:
- implement an opt-in projectile response curriculum/reward profile before the
  next training run.
- candidate behavior:
  - safe `jump-*-start` over an incoming projectile gets a bonus.
  - late jump that leads to self damage gets an extra cost.
  - close `back` / guard rows with no damage or chip get a small bonus.
  - far/passive back rows remain controlled so the model does not collapse into
    always walking back.
  - projectile-focused diagnostics should report response counts by
    `time_to_self` bucket and top greedy action on incoming ground rows.

## 2026-05-01: Add Projectile Guard Summary to Transition Analyzer

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / full action-set DQN experiments

Files changed:
- `tools/analyze_rl_transitions.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- make fireball-response demo quality easier to judge before training the
  first projectile-aware DQN model.
- separate incoming-projectile guard/back rows from jump-start rows so we can
  verify the replay set contains both "jump over the fireball" and
  "block/hold back because it is too close" examples.

Implementation notes:
- added `PROJECTILE_GUARD_SUMMARY`, `PROJECTILE_GUARD_BY_ACTION`,
  `PROJECTILE_GUARD_BY_TIME_BUCKET`, and `PROJECTILE_GUARD_EVENTS` sections to
  `tools/analyze_rl_transitions.py`.
- guard diagnostics currently count incoming opponent projectile rows whose
  selected training action is `back`, `guard`, `guard-stand`, or
  `guard-crouch`.
- damage buckets use the row's `delta_self_hp`:
  - `none`: no self HP loss.
  - `chip`: 1-2 HP self loss.
  - `full-hit`: more than 2 HP self loss.
- this is analyzer-only; it does not change C observation packing, probe
  behavior, label derivation, or DQN training.

Validation:
- `python3 -m py_compile tools/analyze_rl_transitions.py` passed.
- `python3 tools/analyze_rl_transitions.py
  logs/rl-transitions-projectile-schema-v5-smoke-4-3-3.ndjson --limit 18`
  passed and reported:
  - `schemas=5:7783`
  - `active=805/7783`
  - `incoming_opp=464/805`
  - `owners=opponent:547,self:258`
  - `guard_rows=72`, `no_damage_rows=69`, `chip_rows=3`,
    `full_hit_rows=0`
  - `PROJECTILE_GUARD_BY_ACTION` currently shows those rows under `back`.

Interpretation:
- the current projectile smoke contains clean block/hold-back examples against
  incoming fireballs, plus a small number of chip rows.
- no full-hit guard rows appeared in this pass; full-hit cases are still
  visible through the existing jump-start damaged/safe projectile summary.

## 2026-05-01: Add Projectile Diagnostics to Transition Analyzer

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / full action-set DQN experiments

Files changed:
- `tools/analyze_rl_transitions.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- make schema-v5 projectile validation repeatable without ad hoc Python
  snippets.
- summarize whether logs contain the training signal needed for
  anti-fireball jump decisions: incoming opponent projectiles, jump-start rows
  near those projectiles, and damaged versus safe jump outcomes.

Implementation notes:
- added a `PROJECTILE_SUMMARY` block to `tools/analyze_rl_transitions.py`.
- the analyzer now reports:
  - transition schema counts.
  - projectile active rows and owner counts.
  - relative-X buckets, `time_to_self` buckets, and incoming-opponent
    projectile buckets.
  - per-owner relative position/velocity/time ranges.
  - contiguous projectile segments by owner.
  - fireball/super engine-label counts, so repeated projectile observation
    rows can be distinguished from repeated action labels.
  - row-level jump-start diagnostics around incoming opponent projectiles,
    including same-row projectile context and future self-damage within a
    configurable decision window.
- added CLI knobs:
  - `--projectile-window-before`
  - `--projectile-window-after`
  - `--projectile-damage-window-decisions`

Validation:
- `python3 -m py_compile tools/analyze_rl_transitions.py` passed.
- `python3 tools/analyze_rl_transitions.py
  logs/rl-transitions-projectile-schema-v5-smoke-4-3-3.ndjson --limit 12`
  passed and reported:
  - `schemas=5:2403`
  - `active=230/2403`
  - `incoming_opp=137/230`
  - `owners=opponent:150,self:80`
  - `fireball_engine_labels=fireball-lp:6,fireball-hp:3,fireball-mp:1,shinkuu-hadouken:1`
  - `jump_rows=19`, `near_incoming_rows=12`, `same_rows=7`,
    `damaged_rows=10`, `safe_rows=2`

Interpretation:
- the smoke log contains both too-late jump rows that were hit by opponent
  fireballs and safe jump-over rows where the projectile passed behind self.
- jump diagnostics are row-level, not de-duplicated physical jump events; this
  is intentional for now because replay training also consumes decision rows.

## 2026-05-01: Implement Schema-V5 Projectile-Threat Observation Fields

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / full action-set DQN experiments

Files changed:
- `src/rl/rl_observation.h`
- `src/rl/rl_observation.c`
- `src/rl/rl_protocol.h`
- `src/rl/rl_session.c`
- `tools/rl_probe_server.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- let the model observe an active traveling projectile after the opponent's
  fireball routine has finished, so `jump-*-start` can be learned as an
  anti-fireball response instead of only as a generic movement action.
- keep the first version compact: expose one selected projectile with owner,
  facing-normalized distance, facing-normalized velocity, and a time-to-self
  estimate.

Implementation notes:
- bumped live observation and transition data from schema v4 to schema v5.
- packed six projectile fields into `RLObsSpacingPayloadV1` and transition
  NDJSON:
  - `obs_projectile_active`
  - `obs_projectile_owner`
  - `obs_projectile_rel_x`
  - `obs_projectile_rel_y`
  - `obs_projectile_vel_x`
  - `obs_projectile_time_to_self`
- derive the fields in `RLObservation_OnFrameEnd()` by scanning both players'
  `plw[player].wu.shell_ix[0..7]` lists and resolving valid entries through
  `frw[]` `WORK_Other` records.
- first active-candidate filter follows the same source family as the CPU
  shell-avoidance path: active shell/effect id `13`, live routine, owned by
  self or opponent, and not one of the auxiliary shell types that should be
  ignored for projectile threat.
- selection priority:
  - opponent-owned, in front of self, moving toward self
  - opponent-owned and in front of self
  - any active self/opponent projectile
- `obs_projectile_rel_x` and `obs_projectile_vel_x` are normalized by
  `obs_self_facing_sign`; an incoming opponent projectile in front of self
  should usually show `rel_x > 0` and `vel_x < 0`.
- `32767` is the sentinel for no useful relative distance/time estimate.
- Python probe/training now decodes the 44-byte schema-v5 spacing payload,
  adds the projectile fields to DQN features/scales, preserves them in learner
  replay rows, and prints compact verbose diagnostics as
  `proj=active/owner proj_rx=... proj_ry=... proj_vx=... proj_t=...`.

Validation:
- `python3 -m py_compile tools/rl_probe_server.py` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed and rebuilt the
  MiSTer ARM executable/package. The only warning observed was the existing
  minizip `mktemp` linker warning, unrelated to RL projectile changes.

Remaining follow-up:
- deploy the schema-v5 build, record a targeted Ryu fireball/jump-over smoke,
  and confirm projectile fields stay active while the fireball travels.
- verify the `rel_x`, `vel_x`, and `time_to_self` signs on both left/right
  sides before using schema-v5 logs for V41/Vnext anti-fireball training.

## 2026-05-01: Plan Projectile-Threat Observation Fields

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / full action-set DQN experiments

Files changed:
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- schedule the observation-schema work needed for the model to learn
  anti-fireball jump decisions.
- make `jump-*-start` learnable as a response to an active traveling
  projectile, not only to the opponent's fireball startup routine.

Plan notes:
- added Step 3B before the train-time invalid-action Q penalty.
- candidate fields:
  - `obs_projectile_active`
  - `obs_projectile_owner`
  - `obs_projectile_rel_x`
  - `obs_projectile_rel_y`
  - `obs_projectile_vel_x`
  - optional `obs_projectile_time_to_self`
- first version should select one relevant projectile, preferring the nearest
  opponent-owned projectile that is in front of self and moving toward self.
- position/velocity signs should be self-facing-normalized so side swaps do not
  invert the learned anti-fireball policy.

Validation planned:
- targeted human-demo smoke with Ryu fireballs and neutral/forward jump-over
  responses.
- verify projectile fields stay active while the projectile travels, not only
  during opponent `R1=4/R2=16`.
- verify signs/time-to-self on both left/right sides before using the data for
  V41/Vnext training.

## 2026-05-01: Backfill Demo Air-Normal Engine Attribution

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / full action-set DQN experiments

Files changed:
- `src/rl/rl_session.c`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- fix the deployed schema-v4 demo-label smoke finding that air-normal labels
  were under-counted after the ground-label gate cleanup.
- preserve lockout/held-button suppression while still attributing real
  air-normal routine starts.

Smoke finding:
- `logs/rl-transitions-cpu-human-demo-schema-v4-smoke-4-3-3.ndjson` had
  `9` `R1=4/R2=3` common air-normal routine segments, but analyzer output only
  counted `4` `air-*` labels: `air-hk=3`, `air-hp=1`.
- the missing starts had `obs_self_air_attack_allowed=1` on the preceding
  ledger row, then the attack button appeared after the routine had already
  entered `R1=4/R2=3`. The input labeler correctly left these lockout rows as
  neutral, but engine attribution only caught normal attacks with a fresh
  `self_attack_started` edge.

Implementation notes:
- added `RLSession_IsCommonNormalAttackRoutine2()` for Ryu's common normal
  attack routines currently observed as `R2=0/3/4`.
- broadened `RLSession_MaybeAttributeDemoEngineAction()` so normal attack
  attribution can trigger on either `self_attack_started` or a
  `self_attack_routine_started` transition into one of those common normal
  routines.
- kept the special/throw routine mapper first, so `R2=16/17/18/22/23` still
  attributes as fireball/shoryuken/tatsu/air-tatsu/joudan instead of falling
  through to normal attribution.

Validation:
- existing-log inspection confirmed the pre-fix mismatch:
  `9` air-normal routine segments versus `4` `air-*` labels.
- follow-up validation still needs a rebuilt/deployed smoke capture to confirm
  the live logger now emits roughly one `air-*` label per real
  `R1=4/R2=3` air-normal segment.

Follow-up:
- re-record a short schema-v4 human/CPU smoke after deploying this build.
- confirm `air-*` labels track the real air-normal routine-start count without
  repeated labels through the rest of `R1=4/R2=3`.

## 2026-05-01: Gate Demo Ground-Attack Labels On Action-Start Allow

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / full action-set DQN experiments

Files changed:
- `src/rl/rl_session.c`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- clean schema-v4 demo labels before V41/Vnext training.
- prevent held attack buttons from repeatedly labeling locked attack/recovery
  rows as fresh ground-action starts.

Smoke finding:
- `logs/rl-transitions-cpu-human-demo-schema-v4-smoke-4-3-3.ndjson` showed
  split labels and allow flags working, but `stand-hk` / `crouch-hk` exposed a
  demo-label quality issue.
- `stand-hk` had `5` clean start rows with `(ground=1, jump=1, air=0)`, but
  `31` held-button rows were already in attack state with all allow flags off.
- `crouch-hk` had `16` labeled rows, all in `R1=4/R2=0` attack state with
  `(ground=0, jump=0, air=0)`.

Implementation notes:
- updated `RLSession_DeriveDemoPolicyMeta()` so throw, command-normal,
  crouch-normal, and stand-normal demo input labels require
  `obs_self_ground_action_start_allowed=1`.
- kept `air-*` labels gated by `obs_self_air_attack_allowed`.
- kept `jump-*-start` labels gated by `obs_self_jump_start_allowed`.
- when a held ground attack is observed during attack/recovery/lockout, the
  row remains neutral/none instead of becoming another action-start label.

Validation:
- existing-log estimate: this cleanup should remove repeated locked-state
  `stand-hk` / `crouch-hk` labels while preserving clean start labels.
- `python3 -m py_compile tools/rl_probe_server.py tools/train_dqn_learner.py tools/compare_dqn_models.py tools/analyze_rl_transitions.py tools/rl_auto_retrain.py`
- `git diff --check`
- `tools/mister/build-game.sh --flavor telemetry`

Follow-up:
- re-record a targeted schema-v4 smoke with neutral-to-`stand-hk`,
  neutral-to-`crouch-hk`, shoryuken, fireball, tatsu, jump starts, and air
  normals.
- confirm ground attack starts are labeled only on
  `(ground=1, jump=1, air=0)` rows and no longer repeat through `R1=4`
  attack/recovery rows.

## 2026-05-01: Validate Schema-V4 Split Labels With Human/CPU Smoke

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / full action-set DQN experiments

Files changed:
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- validate the schema-v4 jump-start / air-normal split after broadening
  `obs_self_jump_start_allowed` into ordinary jump-ready rows.
- decide whether the split-label data smoke is unblocked for V41/Vnext
  training preparation.

Smoke log:
- `logs/rl-transitions-cpu-human-demo-schema-v4-smoke-4-3-3.ndjson`

Findings:
- `1271 / 1271` rows use transition schema `4`, and all new schema-v4
  observation fields are present.
- all rows were human-demo execution source `4`; the CPU part of the filename
  refers to the opponent/demo setup, not the logged agent execution source.
- allow flags now have useful, state-specific density:
  - `(ground=1, jump=1, air=0)`: `917` rows.
  - `(ground=0, jump=1, air=0)`: `13` ordinary jump-ready rows.
  - `(ground=0, jump=0, air=1)`: `67` ordinary jump-air rows.
  - `(ground=0, jump=0, air=0)`: `274` locked/non-action-start rows.
- split action labels appeared:
  - `jump-forward-start`: `6`
  - `jump-neutral-start`: `7`
  - `jump-back-start`: `4`
  - `air-hp`: `2`
  - `air-hk`: `2`
- old mixed jump-attack labels did not return.
- special-move state checks:
  - `fireball-hp` engine label appeared from ground-action state
    `(ground=1, jump=1, air=0)`, then `R1=4/R2=16` had all allow flags off.
  - `tatsu-hk` engine label appeared from ground-action state
    `(ground=1, jump=1, air=0)`, then `R1=4/R2=18` had all allow flags off.
  - shoryuken did not appear in this particular post-fix smoke.

Validation:
- `python3 tools/analyze_rl_transitions.py logs/rl-transitions-cpu-human-demo-schema-v4-smoke-4-3-3.ndjson --training-action-source auto --limit 90`
- custom schema/action/allow summary script over the same log.
- `git diff --check`

Follow-up:
- the split-label smoke is unblocked for V41/Vnext preparation.
- include shoryuken coverage in the next broader demo/training capture, but it
  does not block the jump-start / air-normal split validation.

## 2026-05-01: Allow Jump-Start Labels in Jump-Ready Phase

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / full action-set DQN experiments

Files changed:
- `src/rl/rl_observation.c`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- fix the second schema-v4 data-smoke finding before V41/Vnext training.
- make demo rows label `jump-forward-start`, `jump-neutral-start`, and
  `jump-back-start` instead of losing jump starts as `neutral`.

Smoke finding:
- the refreshed human-demo smoke log
  `logs/rl-transitions-cpu-demo-schema-v4-smoke-4-3-3.ndjson` had `1135`
  schema-v4 rows, all from human-demo execution source `4`.
- the routine-first allow gate fix worked:
  - `obs_self_ground_action_start_allowed=1`: `796 / 1135` rows.
  - `obs_self_jump_start_allowed=1`: `796 / 1135` rows.
  - `obs_self_air_attack_allowed=1`: `64 / 1135` rows.
- the recording covered the needed smoke actions:
  - forward/back movement.
  - neutral/forward/back jump phases.
  - `air-lk` / `air-hk`.
  - fireball, shoryuken, tatsu, and throws.
- blocker: `jump-*-start` labels were still absent. The first decision row with
  up input had already advanced to ordinary jump-ready (`phase=1`, `R1=0`,
  `R2=16/17`), where the original `obs_self_jump_start_allowed` value was
  false.

Implementation notes:
- broadened `obs_self_jump_start_allowed` to include ordinary jump-ready rows:
  `ground_action_start_allowed || (ordinary_action_state && jump_ready)`.
- kept `obs_self_ground_action_start_allowed` false during jump-ready, so
  ground normals/specials are still not opened there.
- kept `obs_self_air_attack_allowed` restricted to airborne ordinary jump-air,
  so jump-ready does not become an air-normal state.
- this treats `jump-*-start` as the whole early jump-start family, including
  the first jump-ready continuation frames needed by the demo labeler.

Validation:
- existing-log estimate found `9` prospective jump-start events after a
  previous ground-allowed row: `3` up-back, `3` neutral jump, and `3`
  up-forward.
- `python3 -m py_compile tools/rl_probe_server.py tools/train_dqn_learner.py tools/compare_dqn_models.py tools/analyze_rl_transitions.py tools/rl_auto_retrain.py`
- `git diff --check`
- `tools/mister/build-game.sh --flavor telemetry`

Follow-up:
- re-record one more short schema-v4 human/CPU smoke and confirm
  `jump-forward-start`, `jump-neutral-start`, and `jump-back-start` appear
  alongside `air-*`.
- only train V41/Vnext after the split labels and allow flags both pass.

## 2026-05-01: Fix Schema-V4 Action-Start Allow Gate

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / full action-set DQN experiments

Files changed:
- `src/rl/rl_observation.c`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- fix the first schema-v4 data-smoke finding before training V41/Vnext.
- keep the jump-start / air-normal action split, but make the new allow fields
  dense enough to be useful for shared masks and offline DQN features.

Smoke finding:
- `logs/rl-transitions-cpu-demo-schema-v4-smoke-4-3-3.ndjson` passed the
  schema/action split checks:
  - all rows used transition schema `4`.
  - all new schema-v4 observation fields were present.
  - jump phase mapping was coherent: phase `1` for ordinary jump-ready,
    phase `2` for ordinary jump-air, and phase `3` for other airborne states.
  - old mixed jump-attack labels no longer appeared.
  - `air-*` labels can appear separately from `jump-*-start`.
- the allow flags were too sparse for training:
  - `obs_self_ground_action_start_allowed=1`: `8 / 2579` rows.
  - `obs_self_jump_start_allowed=1`: `8 / 2579` rows.
  - `obs_self_air_attack_allowed=1`: `19 / 2579` rows.
- a routine-first estimate on the same log found the intended signal should be
  much denser, roughly `718` ground/jump-start rows and `436` air-attack rows.

Implementation notes:
- changed `derive_action_start_flags()` to use the routine-first eligibility
  gate that matched the validated shared mask:
  `valid && R1=0 && !routine_attack && !contact_reaction && !hit_stop`.
- stopped making raw `self_do_not_move`, `self_current_attack == 0`, and
  `self_throw_active` hard blockers for the first schema-v4 allow fields. The
  smoke log showed those raw fields were too strict for ordinary actionable
  rows, so keep them as diagnostics / future refinements instead.
- ground/jump-start allow still requires grounded state and excludes ordinary
  jump-ready / jump-air routines.
- air-attack allow still requires airborne ordinary jump-air
  (`R1=0`, `R2=18..26`).

Validation:
- `python3 -m py_compile tools/rl_probe_server.py tools/train_dqn_learner.py tools/compare_dqn_models.py tools/analyze_rl_transitions.py tools/rl_auto_retrain.py`
- routine-first estimate on the existing smoke log recovered useful allow
  density for the next data smoke.
- `git diff --check`
- `tools/mister/build-game.sh --flavor telemetry`

Follow-up:
- rebuild/deploy and re-record a short schema-v4 CPU-demo smoke before V41.
- confirm the live C-emitted fields now show useful allow density and still
  separate `jump-*-start` labels from `air-*` labels.

## 2026-05-01: Implement Jump-Start / Air-Normal Action Split

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / full action-set DQN experiments

Files changed:
- `src/rl/rl_protocol.h`
- `src/rl/rl_observation.h`
- `src/rl/rl_observation.c`
- `src/rl/rl_session.c`
- `tools/rl_probe_server.py`
- `tools/train_dqn_learner.py`
- `tools/compare_dqn_models.py`
- `tools/analyze_rl_transitions.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`
- `docs/rl-policy-action-taxonomy.md`

Purpose:
- stop using one `jump-*` action head for both "start a jump from the ground"
  and "press an attack button while airborne."
- give the next DQN action space clean labels so the following invalid-action Q
  penalty can learn state-conditioned legality from the right semantics.

Implementation notes:
- bumped the compatibility gates to protocol `4`, OBS schema `4`, action schema
  `3`, transition schema `4`, OBS spacing payload version `4`, and Python
  action set version `5`.
- expanded the live OBS spacing payload from 32 to 36 bytes with:
  - `obs_self_airborne`
  - `obs_self_jump_phase`
  - `obs_self_ground_action_start_allowed`
  - `obs_self_jump_start_allowed`
  - `obs_self_air_attack_allowed`
- replaced the old full-action jump attacks with:
  - `jump-forward-start`
  - `jump-neutral-start`
  - `jump-back-start`
  - `air-lp`, `air-mp`, `air-hp`, `air-lk`, `air-mk`, `air-hk`
- added `RL_POLICY_ACTION_AIR_NORMAL=16`; schema-v4 jump starts use
  `RL_POLICY_ACTION_JUMP` plus directional sub-actions, and air normals use the
  new air-normal action id plus button sub-actions.
- added shared Python action-start helpers and a new `action-start-v1` DQN mask
  mode backed by the schema fields.
- updated DQN feature metadata so split-taxonomy models include the new
  airborne/action-start flags in offline training and live inference.
- kept the old jump-attack policy ids reserved but unused by current schema-v4
  action names.

Validation:
- `python3 -m py_compile tools/rl_probe_server.py tools/train_dqn_learner.py tools/compare_dqn_models.py tools/analyze_rl_transitions.py tools/rl_auto_retrain.py`
- `python3 tools/rl_probe_server.py --help`
- `python3 tools/train_dqn_learner.py --help`
- `python3 tools/compare_dqn_models.py --help`
- `python3 tools/analyze_rl_transitions.py --help`
- synthetic Python smoke confirmed:
  - 36-byte OBS payload parsing.
  - `jump-forward-start` and `air-mk` policy-meta decode.
  - schema-v4 replay-row normalization.
  - new DQN feature vector entries.
  - `action-start-v1` allows ground actions plus `jump-*-start` on ground rows,
    and allows `air-*` on air rows.
- `git diff --check`
- `tools/mister/build-game.sh --flavor telemetry`

Follow-up:
- collect a short CPU-demo schema-v4 log before training V41/Vnext.
- confirm `obs_self_air_attack_allowed=1` appears during ordinary jump-air rows
  (`R1=0`, `R2=18..26`) and analyzer output separates `jump-*-start` labels
  from `air-*` labels.

## 2026-05-01: Audit Jump Taxonomy Split Code Touch Points

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / full action-set DQN experiments

Files changed:
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- review the live/probe/training code paths that must change for the planned
  split between ground jump-start actions and true airborne attack actions.
- turn the review into an implementation map before editing action ids or
  schema versions.

Findings:
- the split is a schema/action-set change, not a trainer-only change.
- C-side runtime changes are required in:
  - `src/rl/rl_observation.h`
  - `src/rl/rl_observation.c`
  - `src/rl/rl_protocol.h`
  - `src/rl/rl_protocol.c`
  - `src/rl/rl_session.c`
  - validation of `src/rl/rl_net.c` handshake/action-packet rejection behavior.
- Python-side changes are required in:
  - `tools/rl_probe_server.py`
  - `tools/train_dqn_learner.py`
  - `tools/compare_dqn_models.py`
  - `tools/analyze_rl_transitions.py`
  - `tools/rl_auto_retrain.py`
- compatibility gates must move together:
  - Python `ACTION_SET_VERSION`
  - C `RL_ACTION_SCHEMA_VERSION`
  - C `RL_OBSERVATION_SCHEMA_VERSION`
  - Python `OBS_SPACING_PAYLOAD_VERSION`
  - C/Python `TRANSITION_SCHEMA_VERSION`
- the current live OBS spacing payload is 32 bytes and has only three reserved
  bytes left, so the schema-v4 fields should expand the payload instead of
  trying to squeeze five new fields into the reserved tail.
- `RLSession_RyuNormalPolicyMetaFromIdentity()` currently maps airborne normal
  attribution to `RL_POLICY_ACTION_JUMP_ATTACK_FORWARD`; this must become a new
  air-normal policy action id with button sub-actions.
- `RLSession_DeriveDemoPolicyMeta()` currently maps attack + up-direction input
  to direction-specific jump-attack action ids. After the split, demo input
  should label `air-*` only when the observation says an air attack can start;
  grounded jump input should label jump-start or let later engine attribution
  produce the air-normal label.
- `tools/train_dqn_learner.py` currently treats every action whose name starts
  with `jump-` as a jump-attack risk action. After the split,
  `jump-*-start` must not be treated as an air attack, while `air-*` should be
  included in attack/risk accounting.

Plan update:
- added a Step 3 implementation review / code-change map to
  `docs/plan-remote-rl-agent.md`.
- recorded that V40 remains action-set-v4/schema-v3 and should not be
  warm-started into the split action set.
- recorded validation requirements for synthetic action-meta decode, mask truth
  tables, telemetry build, handshake/schema compatibility, and a short
  schema-v4 CPU-demo data smoke before training the first split-taxonomy DQN.

Validation:
- docs-only audit; no runtime behavior changed in this entry.
- `git diff --check -- docs/plan-remote-rl-agent.md docs/remote-rl-agent-engineering-log.md`
  passed.

## 2026-05-01: Refine Jump Root-Fix Action-Start Schema

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / full action-set DQN experiments

Files changed:
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- refine the Step 3 action taxonomy / schema plan so the observation schema
  does not carry a redundant global `obs_self_action_start_allowed` field.
- keep the generic "can start any new high-level action" gate as a derived
  helper while recording family-specific action-start flags in the schema.

Plan notes:
- Step 3 schema fields should include:
  - `obs_self_airborne`
  - `obs_self_jump_phase`
  - `obs_self_ground_action_start_allowed`
  - `obs_self_jump_start_allowed`
  - `obs_self_air_attack_allowed`
- do not add `obs_self_action_start_allowed` as a first-version OBS field.
  Instead derive it in shared C/Python eligibility helpers as:
  `ground_action_start_allowed || jump_start_allowed || air_attack_allowed ||
  future_action_family_allowed`.
- first-version semantics:
  - `obs_self_ground_action_start_allowed`: self is grounded and can start a
    ground action family; this should be false during attack startup/active/
    recovery, hitstun, blockstun, contact/damage/caught, and similar lockout
    states.
  - `obs_self_jump_start_allowed`: self can start a jump. It may initially
    equal `obs_self_ground_action_start_allowed`, but stays separate to support
    future exceptions.
  - `obs_self_air_attack_allowed`: self is in an ordinary airborne jump phase
    and can start an air button action.
- valid-action logic after the split:
  - derived `self_action_start_allowed(row) == false` means no new attack/jump
    action start; use hold / movement / guard fallback.
  - ground allowed gates ground actions.
  - jump-start allowed gates `jump-forward-start`, `jump-neutral-start`, and
    `jump-back-start`.
  - air-attack allowed gates `air-lp`, `air-mp`, `air-hp`, `air-lk`, `air-mk`,
    and `air-hk`.

## 2026-05-01: Reorder Jump Root-Fix Before Raw DQN Penalty

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / full action-set DQN experiments

Files changed:
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- adjust the next full-action DQN plan so the root fix happens before the raw
  weight regularizer.
- avoid training an invalid-action Q penalty against the current mixed
  `jump-*` semantics, where one action head can mean both "start a jump from
  the ground" and "press an attack button while already airborne".

Plan change:
- do the post-mask jump action taxonomy and observation-schema split first:
  - `jump-forward-start`
  - `jump-neutral-start`
  - `jump-back-start`
  - `air-lp`, `air-mp`, `air-hp`, `air-lk`, `air-mk`, `air-hk`
- promote the schema support from a later follow-up into the same root-fix
  step:
  - `obs_self_airborne`
  - `obs_self_jump_phase`
  - `obs_self_ground_action_start_allowed`
  - `obs_self_jump_start_allowed`
  - `obs_self_air_attack_allowed`
  - optional opponent counterparts for anti-air / jump-in curriculum.
- move the train-time invalid-action Q penalty after that split, so it learns
  clean state-conditioned legality:
  - grounded ordinary state can choose `jump-*-start`, not `air-*`.
  - ordinary jump-air state can choose `air-*`, not `jump-*-start`.
  - non-movable state should not start either family.

Decision:
- treat this as the next root-fix sequence after confirming the current V40
  mask/probe behavior.
- keep the hard valid-action mask for live safety throughout the transition.

## 2026-05-01: DQN Verbose Mask Diagnostics And PING Log Throttling

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / full action-set DQN experiments

Files changed:
- `tools/rl_probe_server.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- make live V40 `jump-*` selections diagnosable from `--verbose` output.
- reduce high-frequency PING log spam so OBS/DQN action-selection lines remain
  readable during live probe sessions.

Implementation notes:
- DQN `OBS-ACTION` verbose output now appends:
  - `dqn_action`
  - `dqn_mask`
  - `dqn_mask_source`
  - `dqn_valid=<valid>/<total>`
  - `dqn_phase`
  - `self_r1`, `self_r2`, `self_atk`, and `self_contact`
- `dqn_phase` is derived from the same self-routine mask helper:
  - `jump-air`: ordinary airborne jump routine (`R1=0`, `R2=18..26`, no
    attack/contact reaction), where the current taxonomy allows `jump-*`.
  - `ordinary-movable`: ordinary movable state, where `jump-*` should be
    masked out.
  - `non-movable`: attack/contact/damage/caught/other state, where only
    movement/guard hold candidates are considered.
- added `--verbose-ping-interval`, default `120`, so `--verbose` logs the first
  PING and then every Nth PING. Use `0` to suppress PING summaries or `1` for
  old per-PING verbosity.

Validation:
- `python3 -m py_compile tools/rl_probe_server.py` passed.
- `python3 tools/rl_probe_server.py --help` shows `--verbose-ping-interval`.
- local V40 diagnostics smoke:
  - grounded ordinary row:
    `dqn_action=tatsu-hk ... dqn_valid=27/45 dqn_phase=ordinary-movable self_r1=0 self_r2=0`
  - jump-air row:
    `dqn_action=jump-neutral-mk ... dqn_valid=18/45 dqn_phase=jump-air self_r1=0 self_r2=20`
- PING throttle helper smoke with interval `3` logged counts `1` and `3`, and
  interval `0` suppressed PING summaries while still allowing non-PING packet
  logs.

Decision:
- If live V40 still appears to choose repeated `jump-*` actions, first inspect
  whether verbose says `dqn_phase=jump-air`. If yes, the current mask is
  treating the state as airborne and the next likely fix is action-taxonomy /
  observation-schema work, not metadata auto-selection.

## 2026-05-01: Probe Auto-Selects DQN Valid-Action Mask From Actor Metadata

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / full action-set DQN experiments

Files changed:
- `tools/rl_probe_server.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- make masked-trained DQN actors safer to serve by default.
- let V40-style actors automatically reuse the `dqn_valid_action_mask_config`
  recorded in their manifest metadata, so the probe command does not need a
  manual `--dqn-valid-action-mask self-routine-v1` flag.

Implementation notes:
- changed `rl_probe_server.py --dqn-valid-action-mask` default from `off` to
  `auto`.
- `auto` resolves the effective mask from
  `actor.metadata["dqn_valid_action_mask_config"]` when the active actor policy
  is `dqn`.
- `--dqn-valid-action-mask off` now explicitly disables mask inference for raw
  diagnostics.
- `--dqn-valid-action-mask self-routine-v1` still forces the mask from CLI,
  independent of actor metadata.
- probe startup and hot-swap paths log the resolved mode, source, and model
  version, for example `source=metadata model_version=40`.

Validation:
- `python3 -m py_compile tools/rl_probe_server.py` passed.
- `python3 tools/rl_probe_server.py --help` shows
  `--dqn-valid-action-mask {auto,off,self-routine-v1}`.
- metadata resolution smoke:
  - V40 auto resolved to `self-routine-v1 source=metadata`.
  - explicit CLI `off` resolved to `off source=cli`.
- action-selection smoke on a grounded ordinary row:
  - auto metadata mask selected `tatsu-hk`.
  - explicit CLI `off` selected raw `jump-neutral-mk`.
- short local UDP-bind startup smoke printed:
  `DQN valid-action mask self-routine-v1 source=metadata model_version=40`.

Decision:
- V40 probe commands can now omit `--dqn-valid-action-mask self-routine-v1`.
- keep `--dqn-valid-action-mask off` only for raw/unmasked diagnostic runs,
  because V40 still has raw unmasked jump-action collapse.

## 2026-05-01: Record DQN Invalid-Action Weight-Regularization Follow-Up

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / full action-set DQN experiments

Files changed:
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- record the follow-up needed to make the DQN raw weights learn that
  state-illegal actions, such as grounded air attacks, should not receive
  competitive Q values.
- clarify that this is complementary to the shared valid-action mask, not a
  replacement for live/probe legality gating.

Plan notes:
- add an opt-in train-time invalid-action Q penalty after the shared
  valid-action mask path is validated.
- compute valid and invalid actions per replay state using the same shared
  helper used by target selection and probe inference.
- penalize invalid action heads when their Q values exceed the best valid
  action by a configured margin, for example
  `max(0, q_invalid - max(q_valid) + margin)^2`.
- treat this as state-conditioned regularization:
  - a jump or future `air-*` action can be legal while airborne.
  - the same action should be penalized while grounded or otherwise
    non-movable.
- keep the hard valid-action mask for live safety, because neural-network
  weights alone cannot provide a strict legality guarantee under
  out-of-distribution states or Q-scale drift.

Validation target:
- CPU-demo same-observation compare with `valid_mask=off` should stop being
  dominated by impossible ground-state `jump-*` / future `air-*` actions.
- masked inference should remain stable and should not collapse into a new
  single guard/fireball action.
- diagnostics should report penalized rows/actions, empty-valid rows, total
  auxiliary loss, and raw-vs-masked greedy distributions.

## 2026-05-01: Shared DQN Valid-Action Mask And V40 CPU-Demo Masked Training

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / full action-set DQN experiments

Files changed:
- `tools/rl_probe_server.py`
- `tools/train_dqn_learner.py`
- `tools/compare_dqn_models.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`
- `model/dqn-cpudemo-schema-v3-full-actions-v40-mask/` (generated, untracked)

Purpose:
- implement the shared valid-action mask planned after V39 showed soft
  unsupported-action regularization was not enough.
- use the same self-routine-aware eligibility helper for train-time DQN target
  max, probe/live DQN ranking, epsilon exploration, and same-observation
  comparison diagnostics.

Implementation notes:
- added shared mask mode `self-routine-v1` in `tools/rl_probe_server.py`.
- added helpers:
  - `parse_dqn_valid_action_mask_config()`
  - `dqn_valid_action_for_row()`
  - `dqn_valid_actions_for_row()`
  - `dqn_valid_action_indices_for_row()`
- first mask semantics:
  - ordinary grounded/movable rows allow non-`jump-*` actions.
  - ordinary jump-air rows (`obs_self_routine_1 == 0`,
    `obs_self_routine_2 in 18..26`, no self attack/contact reaction) allow
    only `jump-*` actions.
  - attack/contact/non-movable rows allow only movement/guard hold candidates.
- added `--dqn-valid-action-mask {off,self-routine-v1}` to:
  - `tools/train_dqn_learner.py`
  - `tools/rl_probe_server.py`
  - `tools/compare_dqn_models.py`
- trainer metadata now records:
  - `dqn_valid_action_mask_config`
  - `dqn_valid_action_mask_stats`
  - target/greedy masked action totals and empty-mask counts.

Validation:
- `python3 -m py_compile tools/rl_probe_server.py tools/train_dqn_learner.py tools/compare_dqn_models.py` passed.
- help output for all three tools showed the new flag.
- helper smoke confirmed expected eligibility:
  - ground ordinary: `guard-stand`, `stand-mk`, `fireball-hp`
  - jump-air ordinary: `jump-neutral-mk`
  - attack/non-movable: `guard-stand`
- small DQN trainer smoke passed with
  `--dqn-valid-action-mask self-routine-v1`; stdout and metadata included
  target/greedy mask stats.

Same-observation V38/V39 mask check:
- command shape:
  ```sh
  python3 tools/compare_dqn_models.py logs/rl-transitions-cpu-demo-schema-v3-4-3-3.ndjson --model V38=model/dqn-cpudemo-schema-v3-full-actions-v38 --model V39=model/dqn-cpudemo-schema-v3-full-actions-v39 --limit 5000 --top-n 12 --dqn-valid-action-mask self-routine-v1
  ```
- V38 with mask:
  - top action became `guard-crouch 2148/5000 = 43.0%`
  - `jump-neutral-mk` fell to `244/5000 = 4.9%`
  - collapse status became `ok`
- V39 with mask was nearly identical:
  - top action `guard-crouch 2145/5000 = 42.9%`
  - `jump-neutral-mk 244/5000 = 4.9%`

V40 training:
- trained from the V38 CPU-demo full-action recipe, adding only:
  - `--model-dir model/dqn-cpudemo-schema-v3-full-actions-v40-mask`
  - `--model-version 40`
  - `--dqn-valid-action-mask self-routine-v1`
- training completed and published version `40`.
- trainer diagnostics:
  - experiences: `45124`
  - target mask states: `126209`
  - target empty masks: `0`
  - greedy rows: `5000`
  - greedy empty masks: `0`
  - masked greedy top: `guard-crouch 1165/5000 = 23.3%`
  - `jump-neutral-mk 385/5000 = 7.7%`
- same-observation masked compare:
  - V40 top action on the first `5000` CPU-demo rows:
    `guard-crouch 2126/5000 = 42.5%`
  - collapse status: `ok`
  - V38 -> V40 changed `378/5000` choices.

Decision:
- shared valid-action masking is effective offline and should be the next
  full-action DQN path.
- V40 still collapses if evaluated with `valid_mask=off`; any live/probe use of
  this model must use the actor metadata auto-mask or explicitly pass
  `--dqn-valid-action-mask self-routine-v1`.

Follow-up:
- run a live probe using the actor metadata auto-mask; pass
  `--dqn-valid-action-mask off` only for raw diagnostic comparisons.
- after live/offline validation, continue with the recorded jump-start vs
  air-attack action taxonomy split and schema-versioned airborne features.

## 2026-05-01: Record Post-Mask Jump-In Action Split Plan

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / full action-set DQN experiments

Files changed:
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- record the next action-taxonomy direction after shared valid-action mask
  validation.
- avoid mixing "start a jump from the ground" and "press an attack button while
  already airborne" inside the same `jump-*` DQN action heads.

Plan notes:
- first validate the shared valid-action mask using current routine-state
  fields.
- after that validation, split the current direction-specific jump attack
  actions into:
  - ground jump-start actions: `jump-forward-start`, `jump-neutral-start`,
    `jump-back-start`
  - airborne attack actions: `air-lp`, `air-mp`, `air-hp`, `air-lk`,
    `air-mk`, `air-hk`
- intended mask semantics after the split:
  - grounded ordinary/movable state can choose jump-start actions, but not
    `air-*` attacks.
  - ordinary jump-air state (`R1=0`, `R2=18..26`) can choose `air-*` attacks,
    but not new grounded normals/specials or new jump-start actions.
  - attack/contact/damage/caught and other non-movable states avoid new
    action-start choices and fall back to configured hold/fallback behavior.

Observation-schema follow-up:
- add schema-versioned support before relying on the split in train/live DQN:
  - `obs_self_airborne`
  - `obs_self_jump_phase` or a compact equivalent
  - `obs_self_ground_action_start_allowed`
  - `obs_self_jump_start_allowed`
  - `obs_self_air_attack_allowed`
  - optional opponent counterparts for anti-air and jump-in curriculum.
- keep the generic action-start gate as a derived helper instead of a separate
  first-version schema field.
- update C OBS payloads, transition rows, Python OBS parsing,
  `DQN_FEATURE_NAMES`, metadata, analyzer diagnostics, and probe inference
  together so train and live action eligibility use the same features.

Follow-up:
- keep this behind the shared valid-action mask validation; do not expand the
  action set or observation schema before the current mask experiment proves
  useful offline.

## 2026-05-01: Train V39 CPU-Demo Full-Action With Unsupported Regularization

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / full action-set DQN experiments

Files changed:
- `model/dqn-cpudemo-schema-v3-full-actions-v39/` (generated, untracked)
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- test whether the first opt-in unsupported-action regularization is enough to
  fix the V38 CPU-demo full-action jump-collapse failure.

Training recipe:
- V38 CPU-demo full-action recipe, plus:
  - `--model-dir model/dqn-cpudemo-schema-v3-full-actions-v39`
  - `--model-version 39`
  - `--dqn-unsupported-action-regularization`
  - `--dqn-unsupported-action-min-count 300`
  - `--dqn-unsupported-action-q-ceiling 0.0`
  - `--dqn-unsupported-action-loss-weight 0.1`

Validation result:
- training completed and published version `39`.
- replay rows / experiences matched V38:
  - rows: `122276`
  - experiences: `45124`
- regularization did run:
  - eligible actions: `34`
  - zero-sample actions: `13`
  - regularized events: `2303866`
  - total regularization loss: `23.706095642724385`
- raw greedy did not materially improve versus V38:
  - V38: `jump-neutral-mk 4037/5000 = 80.7%`
  - V39: `jump-neutral-mk 4031/5000 = 80.6%`
  - V38: `jump-back-hk 444/5000 = 8.9%`
  - V39: `jump-back-hk 444/5000 = 8.9%`
  - V38: `jump-neutral-mp 91/5000 = 1.8%`
  - V39: `jump-neutral-mp 92/5000 = 1.8%`
- q-mean moved only slightly:
  - `jump-neutral-mk`: `0.1867678145 -> 0.1858812352`
  - `jump-back-hk`: `0.1071111589 -> 0.1065539107`
  - `jump-neutral-mp`: `0.1154654855 -> 0.1149702650`

Decision:
- do not promote V39.
- the feature is wired and diagnostic metadata is useful, but the first
  realistic setting is far too weak to affect V38's zero-sample jump-head
  overestimation.

Follow-up:
- try a stronger auxiliary constraint only as an offline experiment, for
  example higher `--dqn-unsupported-action-loss-weight`, a lower
  `--dqn-unsupported-action-q-ceiling`, or both.
- prioritize the planned shared valid-action mask, because this V39 result
  suggests regularization alone may not be enough for full-action CPU-demo-only
  data.

## 2026-05-01: DQN Unsupported-Action Regularization

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / full action-set DQN experiments

Files changed:
- `tools/train_dqn_learner.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- add the first trainer-side fix for full-action DQN sparse-action
  overestimation.
- make zero-sample and low-support action heads receive an opt-in auxiliary
  Q-value loss even when they have no replay experiences of their own.

Implementation notes:
- added `--dqn-unsupported-action-regularization`, disabled by default.
- added `--dqn-unsupported-action-min-count`, default `1`, so enabling the
  feature without extra knobs targets only `count == 0` actions.
- added `--dqn-unsupported-action-q-ceiling` and
  `--dqn-unsupported-action-loss-weight`.
- the trainer computes eligible actions from post-build DQN `action_counts`;
  any action with `count < min_count` is regularized.
- for each training state, eligible action heads above the ceiling add a
  normalized auxiliary loss:
  `loss_weight * 0.5 * (q - q_ceiling)^2 / eligible_action_count`.
- the auxiliary gradient is added to the existing output gradient before the
  current stdlib backprop pass.
- model metadata now records:
  - `dqn_unsupported_action_regularization_config`
  - `dqn_unsupported_action_regularization_stats`
  - eligible actions, zero-sample actions, low-sample actions, regularized
    zero/low-sample actions, regularized event counts, and per-action loss.
- stdout diagnostics now include `unsupported_action_regularization=...`.

Validation:
- `python3 -m py_compile tools/train_dqn_learner.py` passed.
- `python3 tools/train_dqn_learner.py --help` passed and showed the new flags.
- smoke command passed:
  ```sh
  python3 tools/train_dqn_learner.py logs/rl-transitions-human-demo-schema-v3-4-3-3.ndjson --model-dir /tmp/rl-dqn-unsupported-reg-smoke --limit 300 --steps 3 --batch-size 8 --hidden-sizes 8 --dqn-unsupported-action-regularization --dqn-unsupported-action-min-count 999 --dqn-unsupported-action-q-ceiling -100 --dqn-unsupported-action-loss-weight 0.0001 --eval-limit 50 --log-interval 1 --diagnostic-top-n 12
  ```
- smoke output included `eligible_action_count=45`,
  `regularized_events=1080`, and `31` zero-sample actions in
  `regularized_zero_sample_actions` metadata.

Follow-up:
- retrain a V38-style CPU-demo full-action candidate with realistic
  regularization settings.
- compare raw greedy and support-prior greedy distributions against V38, and
  confirm that jump collapse does not shift into a single guard/fireball/DP
  action.
- implement the separate shared valid-action mask for train-time target max
  and probe-time DQN ranking.

## 2026-05-01: Full-Action DQN Sparse-Action Fix Plan

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / full action-set DQN experiments

Files changed:
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- record the next implementation plan after V37b/V38 showed that full-action
  DQN can assign dominant Q-values to zero-sample jump actions.

Plan summary:
- add opt-in zero-sample / low-support action regularization in the offline DQN
  trainer.
  - This must affect actions with `count == 0`, not only actions that already
    have replay experiences.
  - The intended mechanism is an auxiliary Q regularization loss that pushes
    unsupported action heads below a configured ceiling.
- add a shared valid-action mask for DQN train-time bootstrapping and
  probe-time inference.
  - Use existing row fields first: `obs_self_routine_1`,
    `obs_self_routine_2`, `obs_self_routine_attack_state`, and
    `obs_self_contact_reaction_state`.
  - Initial target: prevent ground-state inference / target max from selecting
    jump attacks, while allowing jump attacks in ordinary jump-air states
    (`R1=0`, `R2=18..26`).

Validation target:
- retrain a CPU-demo full-action candidate from the V38 recipe.
- require zero-sample actions such as `jump-neutral-mk`, `jump-back-hk`, and
  `jump-neutral-mp` to lose raw greedy dominance.
- verify the fix does not simply move collapse into guard, fireball, or another
  single high-support action.

## 2026-04-30: V37b / V38 Full-Action DQN Support-Prior Findings

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / full action-set DQN experiments

Files changed:
- `docs/remote-rl-agent-engineering-log.md`
- `docs/plan-remote-rl-agent.md`

Purpose:
- record the reproducible V37b and V38 full-action training recipes and the
  live/probe findings so later experiments do not repeat the same jump-collapse
  and CPU-demo-only failure modes.

Common training recipe:
- full 45-action set from `rl_probe_server.TABULAR_ACTION_NAMES`, including
  all stand/crouch normals, all jump-forward / jump-neutral / jump-back attacks,
  fireball, throw, Shoryuken, and tatsu variants.
- `--steps 2000`
- `--batch-size 64`
- `--learning-rate 0.0003`
- `--gamma 0.9`
- `--target-sync-steps 200`
- `--dqn-target-mode standard`
- `--hidden-sizes 64,64`
- `--fallback-policy stand-mk`
- `--training-action-source auto`
- `--batch-sampling balanced`
- `--balanced-batch-ratios movement=0.25,normal=0.45,special=0.30`
- `--epsilon 0.05`
- `--seed 7`
- `--eval-limit 5000`
- `--diagnostic-top-n 12`
- reward/risk shape:
  - `--reward-risk-profile all-attacks`
  - `--reward-risk-window-decisions 15`
  - `--reward-attack-no-damage-cost 0.3`
  - `--reward-attack-punished-cost 1.0`
  - `--reward-shoryuken-no-damage-extra-cost 0.0`
  - `--reward-shoryuken-punished-extra-cost 0.5`
  - `--reward-jump-attack-no-damage-extra-cost 1.0`
  - `--reward-jump-attack-punished-extra-cost 2.0`
  - `--reward-passive-guard-cost 0.4`
  - `--reward-far-guard-cost 0.6`
  - `--reward-guard-threat-max-dx 120`
  - `--reward-spacing-target-min-dx 50`
  - `--reward-spacing-target-max-dx 120`
  - `--reward-spacing-improve-bonus 0.5`
  - `--reward-spacing-worsen-cost 0.2`
  - `--reward-spacing-maintain-bonus 0.1`
  - `--reward-spacing-threat-back-bonus 0.3`
- engine-outcome shape:
  - `--engine-outcome-training-mode prefer-engine-action`
  - `--engine-outcome-window-decisions 15`
  - `--engine-outcome-action-windows fireball-lp=45,fireball-mp=45,fireball-hp=45,tatsu-lk=25,tatsu-mk=25,tatsu-hk=25,throw=8`
  - `--engine-outcome-hit-bonus 1.0`
  - `--engine-outcome-no-damage-cost 0.2`
  - `--engine-outcome-punished-cost 1.0`
  - `--engine-outcome-oversample 1`
  - `--engine-outcome-action-oversamples fireball-lp=4,fireball-mp=4,fireball-hp=4,shoryuken-lp=8,shoryuken-mp=10,shoryuken-hp=12,tatsu-lk=6,tatsu-mk=6,tatsu-hk=6,throw=8`
- conservative training penalty:
  - `--conservative-min-action-count 300`
  - `--conservative-action-penalty 2.0`
  - `--conservative-negative-mean-extra 1.0`

V37b training:
- source log: `logs/rl-transitions-live-dqn-v36-20260430-212325.ndjson`
- source filter: `--replay-source-ratios human-demo=1.0`
- model dir: `model/dqn-human-demo-v36log-full-actions-v37b`
- published version: `37`
- replay rows: `25609` human-demo rows, `16985` DQN experiences.
- conservative penalty: `7928` adjusted experiences, `11365.0` raw cost.
- raw greedy still showed jump overestimation:
  - `jump-neutral-mk: 60.1%`
  - `jump-back-hk: 20.7%`
  - `jump-neutral-mp: 6.5%`
- conclusion from raw model: training-time reward/support penalty alone did not
  fix full-action jump overestimation.

V37b live/probe support-prior recipe:
- model dir: `model/dqn-human-demo-v36log-full-actions-v37b`
- use at probe time:
  - `--dqn-support-prior-min-count 300`
  - `--dqn-support-prior-count-penalty 0.15`
  - `--dqn-support-prior-negative-mean-penalty 0.05`
- offline sweep on the same human-demo observations showed this strong prior
  moved the policy away from jump collapse:
  - weak prior (`0.005/0.002`): `jump-neutral-mk 55.0%`,
    `jump-back-hk 19.9%`, `jump-neutral-mp 7.0%`
  - strong prior (`0.15/0.05`): `jump-neutral-mk 2.0%`,
    `jump-back-hk` and `jump-neutral-mp` nearly disappeared
- live finding from manual play: this V37b + strong-prior combination felt
  substantially better and is the preferred full-action human-demo candidate.

V38 training:
- source log: `logs/rl-transitions-cpu-demo-schema-v3-4-3-3.ndjson`
- source filter: `--replay-source-ratios cpu-demo=1.0`
- model dir: `model/dqn-cpudemo-schema-v3-full-actions-v38`
- published version: `38`
- replay rows: `122276` CPU-demo rows, `45124` DQN experiences.
- conservative penalty: `32317` adjusted experiences, `35084.0` raw cost.
- raw greedy still collapsed:
  - `jump-neutral-mk: 80.7%`
  - `jump-back-hk: 8.9%`
  - `forward-hp: 3.3%`
  - `tatsu-hk: 2.8%`
  - `jump-neutral-mp: 1.8%`
- applying the same strong prior did reduce jump but caused a new collapse:
  - `fireball-hp: 66.1%`
  - `jump-neutral-mk: 12.6%`
  - `shoryuken-hp: 8.9%`
  - `tatsu-hk: 5.0%`

Decision:
- keep V37b + strong inference support-prior as the useful full-action result.
- do not promote V38 CPU-demo-only; the same recipe does not transfer to
  CPU-demo-only data and can shift into fireball/DP collapse under strong
  support-prior reranking.

Follow-up:
- prefer human-demo-heavy or human+CPU mix experiments over CPU-demo-only for
  the next full-action model.
- if full-action DQN remains useful, implement a cleaner training-time
  unsupported-action regularizer or self-routine features rather than relying
  only on reward penalties.

## 2026-04-30: V35a Auto Retrain Preset

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / rolling live-replay retrain

Files changed:
- `tools/rl_auto_retrain.py`
- `docs/rl-incremental-retrain-plan.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- make v35a follow-up auto retraining reproducible without a long
  `--trainer-extra-args` override string.
- keep the v35a close-pressure / anti-air recipe attached to a named runner
  preset.

Implementation notes:
- added `--reward-preset ground-specials-v35a`.
- the preset keeps the ground-specials reward/risk shape but changes the
  training recipe to match v35a:
  - `movement=0.25,normal=0.45,special=0.30`
  - passive/far guard cost `0.4/0.6`
  - fireball oversamples `4/4/4`
  - Shoryuken oversamples `8/10/12`
  - throw engine-outcome window `8` and oversample `8`
- `--trainer-extra-args` still appends after the preset and can override it
  for experiments.

Validation:
- `python3 tools/rl_auto_retrain.py --help` showed
  `--reward-preset {none,ground-specials-v24,ground-specials-v35a}`.
- dry-run validation confirmed the generated train command includes the v35a
  batch ratio, guard costs, reduced fireball oversamples, stronger Shoryuken
  oversamples, and throw engine-outcome support.

Follow-up:
- run the next v35a live auto-retrain with `--reward-preset ground-specials-v35a`
  and `--replay-source-ratios cpu-demo=0.40,human-demo=0.25,remote=0.35`.

## 2026-04-30: Auto Retrain Runner

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / rolling live-replay retrain

Files changed:
- `tools/rl_auto_retrain.py`
- `docs/rl-incremental-retrain-plan.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- add the first end-to-end rolling retrain runner.
- connect live-log chunk snapshotting to DQN warm-start training.
- publish a new `current.json` only after the trainer succeeds.
- advance the live-log cursor only after publish and metadata annotation succeed.

Implementation notes:
- added `tools/rl_auto_retrain.py`.
- the runner resolves base logs, live incremental log, source ratios, and recipe name from CLI args or `metadata.replay_recipe`.
- each cycle runs:
  - `rl_retrain_chunk.py snapshot`
  - `train_dqn_learner.py --init-model <model-dir>/current.json`
  - `metadata.auto_retrain` annotation on `current.json` and matching `actor-vN.json`
  - `rl_retrain_chunk.py commit`
- supports one-shot mode, polling mode via `--cycles 0 --interval-sec`, `--dry-run`, `--no-commit`, and pending-chunk reuse.
- first version records retrain metadata and diagnostics only; hard behavior gates remain intentionally off.
- reward presets:
  - `none` for tiny smoke tests.
  - `ground-specials-v24` for the current v24-style recipe.

Validation:
- `python3 -m py_compile tools/rl_auto_retrain.py` passed.
- `python3 tools/rl_auto_retrain.py --help` passed.
- dry-run smoke from a copied v24 model under `/tmp/rl-auto-retrain-smoke-model-a` passed:
  - resolved the expected train command.
  - used CPU demo, human demo, and the pending live chunk with `cpu-demo=0.50,human-demo=0.30,remote=0.20`.
- not-enough-rows smoke passed:
  - `--min-new-rows 100 --max-new-rows 25` returned `status=not-enough-rows`.
  - no trainer run was started.
- two-step auto retrain smoke passed:
  - source log: `logs/rl-transitions-live-dqn-v23-20260430-135148.ndjson`.
  - chunk rows: `25`.
  - warm-started from copied v24 model version `25`.
  - trainer published version `26`.
  - `metadata.auto_retrain` recorded base version, new version, source log, chunk log, row count, source ratios, reward preset, and duration.
  - cursor commit advanced `last_trained_row_count` to `25` and cleared `pending_chunk`.

Follow-up:
- use this runner with a real v24/v23 live probe log after the next controlled live collection.
- add optional promotion gates later if live behavior diagnostics show regressions.

## 2026-04-30: Live Log Cursor And Retrain Chunk Snapshot

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / rolling live-replay retrain

Files changed:
- `tools/rl_retrain_chunk.py`
- `docs/rl-incremental-retrain-plan.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- add the cursor/chunk stage needed before an auto retrain runner.
- make append-only live logs retrainable without repeatedly consuming the same live rows.
- avoid advancing the trained cursor until a retrain has successfully used and published the chunk.

Implementation notes:
- added `tools/rl_retrain_chunk.py`.
- subcommands:
  - `init`: initialize a source-log cursor at `start` or `eof`.
  - `status`: print the cursor JSON for a source log.
  - `snapshot`: read complete NDJSON rows after `last_trained_byte_offset`, write a chunk file, and store it as `pending_chunk`.
  - `commit`: after successful train/publish, advance `last_trained_*` from `pending_chunk` and clear it.
- `snapshot` refuses to overwrite an existing pending chunk unless `--replace-pending` is passed.
- `snapshot` stops before an incomplete trailing line, so active append-only logs can be read without consuming a partially written row.
- `snapshot` supports `--min-new-rows`, `--max-new-rows`, `--allow-truncate-reset`, `--chunk-prefix`, and `--label`.
- cursor state uses a `sources` map keyed by resolved source log path.

Validation:
- `python3 -m py_compile tools/rl_retrain_chunk.py` passed.
- `python3 tools/rl_retrain_chunk.py --help` passed.
- snapshot smoke on `logs/rl-transitions-live-dqn-v23-20260430-135148.ndjson` passed:
  - wrote a `25` row chunk under `/tmp/rl-retrain-chunk-smoke-20260430/chunks`.
  - pending cursor had `start_byte_offset=0`, `end_byte_offset=34769`, `row_count=25`, `last_decision_id=24`.
- not-enough-rows smoke passed:
  - `--min-new-rows 100 --max-new-rows 25` reported `status=not-enough-rows`.
- pending-protection smoke passed:
  - a second `snapshot` before `commit` returned `status=pending-exists`.
- commit smoke passed:
  - `commit` advanced `last_trained_byte_offset` to `34769` and `last_trained_row_count` to `25`.
  - the next `snapshot` started at byte `34769`.
- EOF init smoke passed:
  - `init --at eof` set the offset to the current source size.
  - a following `snapshot --min-new-rows 1` reported `status=not-enough-rows`.

Follow-up:
- implement the auto retrain runner that calls `snapshot`, trains with `--init-model`, publishes, then calls `commit`.

## 2026-04-30: Incremental Retrain Plan And DQN Warm-Start

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / rolling live-replay retrain

Files changed:
- `docs/rl-incremental-retrain-plan.md`
- `tools/train_dqn_learner.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- document the full rolling incremental retrain design before adding an auto retrain runner.
- implement the first concrete step: DQN warm-start training from an existing actor manifest.
- record replay recipe metadata so later auto retrain can discover stable base replay logs and source ratios from the current model.

Implementation notes:
- added `docs/rl-incremental-retrain-plan.md`.
- added `tools/train_dqn_learner.py --init-model`.
- `--init-model` accepts either an actor JSON path or a model directory containing `current.json`.
- warm-start validation requires:
  - `policy == dqn`
  - current `ACTION_SET_VERSION`
  - exact action list and order match
  - exact DQN feature-name schema match
  - layer count, input widths, output widths, bias lengths, and activation kinds match the requested network shape
- without `--init-model`, trainer behavior remains random `init_network(...)` full retrain.
- added metadata:
  - `incremental_training`
  - `init_model_path`
  - `init_model_version`
  - `init_model_source`
  - `init_model_feature_count`
  - `init_model_action_count`
  - `init_model_validation`
  - `hidden_sizes`
- added replay recipe metadata flags:
  - `--replay-recipe-name`
  - `--replay-recipe-base-logs`
  - `--replay-recipe-live-log`
- when a warm-start model already has `metadata.replay_recipe`, omitted replay-recipe flags inherit from the init model.

Validation:
- `python3 -m py_compile tools/train_dqn_learner.py` passed.
- full-retrain smoke without `--init-model` passed:
  - published `/tmp/rl-dqn-incremental-full-smoke/current.json`
  - output showed `init=random`
  - metadata recorded `incremental_training=false` and replay recipe fields
- warm-start smoke from v24 passed:
  - init model: `model/dqn-mixdemo-schema-v3-ground-specials-v24/current.json`
  - published `/tmp/rl-dqn-incremental-warm-smoke/current.json`
  - output showed `init=warm-start:25`
  - metadata recorded `incremental_training=true`, `init_model_version=25`, `init_model_feature_count=33`, `init_model_action_count=27`
- incompatible warm-start smoke from v9 failed as expected:
  - command rejected `model/dqn-mixdemo-schema-v3-ground-specials-v9/current.json`
  - reason: `feature schema mismatch got=8 expected=33`
- `git diff --check` passed.

Follow-up:
- implement live-log cursor and chunk snapshot support.
- implement `tools/rl_auto_retrain.py` after manual warm-start runs are satisfactory.

## 2026-04-30: Train V24 From V21a And V23 Live Replay

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / clean live-replay retrain cleanup

Files changed:
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- train a v24 candidate that keeps the v23 `r1/r2` observation feature path and adds the new v23 live replay to the earlier v21a live replay.
- test whether mixing the improved v23 live data can keep the live `stand-hk` / `crouch-hp` fixes while reducing v23's replacement shift toward `tatsu-lk` / `crouch-mk`.

Training:
- trained `model/dqn-mixdemo-schema-v3-ground-specials-v24`.
- v24 model manifest version is `25`.
- source logs:
  - `logs/rl-transitions-cpu-demo-schema-v3-4-3-3.ndjson`
  - `logs/rl-transitions-human-demo-schema-v3-4-3-3.ndjson`
  - `logs/rl-transitions-live-dqn-v21a-20260430-124456.ndjson`
  - `logs/rl-transitions-live-dqn-v23-20260430-135148.ndjson`
- source mix:
  - `cpu-demo=0.55`
  - `human-demo=0.30`
  - `remote=0.15`
- kept the v23/v21a fireball recipe:
  - `fireball-lp=8,fireball-mp=8,fireball-hp=8`
  - `--dqn-require-movable-state-sources remote`

Training diagnostics:
- rows after source mix: `62829`
- experiences: `25374`
- feature count: `33`
- remote rows after source mix:
  - v23 live model-version `24`: `5504` rows / `58.4%`
  - v21a live model-version `21`: `3920` rows / `41.6%`
- effective remote experiences:
  - total: `239`
  - v23 live model-version `24`: `159` / `66.5%`
  - v21a live model-version `21`: `80` / `33.5%`
- remote action-start rows checked: `4206`
- remote action-start rows included: `239`
- remote action-start rows filtered: `3967`
- remote experience action means:
  - `fireball-hp=66`, mean `-0.006`
  - `crouch-hp=59`, mean `-0.015`
  - `crouch-mk=34`, mean `+0.012`
  - `tatsu-lk=20`, mean `-0.030`
  - `stand-hk=17`, mean `-0.027`
- final loss:
  - `last_loss=0.005647`
  - `avg_loss=0.006919`

Same-observation compare summary:
- CPU/human slice:
  - v23: `fireball-hp=40.6%`, `tatsu-lk=18.4%`, `crouch-mk=6.1%`, `guard-crouch=4.4%`, `crouch-hp=2.5%`, `stand-hk=0.0%`
  - v24: `fireball-hp=38.1%`, `tatsu-lk=19.2%`, `crouch-mk=6.3%`, `guard-crouch=4.7%`, `crouch-hp=2.4%`, `stand-hk=0.1%`
- v21a-live slice:
  - v23: `fireball-hp=34.1%`, `tatsu-lk=23.6%`, `crouch-mk=11.4%`, `guard-crouch=5.7%`, `crouch-hp=4.0%`, `stand-hk=0.0%`
  - v24: `fireball-hp=32.7%`, `tatsu-lk=24.1%`, `crouch-mk=11.5%`, `guard-crouch=5.7%`, `crouch-hp=3.9%`, `stand-hk=0.0%`
- v23-live slice:
  - v23: `fireball-hp=36.1%`, `crouch-mk=13.5%`, `guard-crouch=10.9%`, `crouch-hp=10.2%`, `stand-lp=9.2%`, `tatsu-lk=7.5%`, `stand-hk=0.1%`
  - v24: `fireball-hp=33.4%`, `crouch-mk=14.5%`, `guard-crouch=11.2%`, `crouch-hp=10.0%`, `stand-lp=9.3%`, `tatsu-lk=8.2%`, `stand-hk=0.1%`

Focused pockets:
- v21a-live `opp_attack_close_mid`:
  - v23: `tatsu-lk=50.7%`, `crouch-hp=18.4%`, `fireball-hp=16.1%`, `stand-hk=0.0%`
  - v24: `tatsu-lk=51.8%`, `crouch-hp=17.9%`, `fireball-hp=15.4%`, `stand-hk=0.0%`
- v23-live `opp_attack_close_mid`:
  - v23: `fireball-hp=40.6%`, `crouch-hp=31.6%`, `tatsu-lk=21.4%`, `stand-hk=0.0%`
  - v24: `fireball-hp=39.1%`, `crouch-hp=30.8%`, `tatsu-lk=23.6%`, `stand-hk=0.0%`

Conclusion:
- v24 keeps the important v23 improvement: `stand-hk` remains suppressed in the live replay slices.
- v24 is not a clear improvement over v23 in same-observation compare.
- adding the v23 live replay and raising remote ratio to `15%` did not reduce the v23 replacement shift; `tatsu-lk` is slightly higher on the key v21a-live and v23-live pockets.
- v24 can be live-probed, but it should not be assumed better than v23 until live behavior confirms it.

Validation:
- full v24 training passed.
- metadata inspection passed.
- same-observation compare passed for CPU/human, v21a-live, and v23-live slices.

## 2026-04-30: OBS Payload V3 Opponent Routine Features And V23 Retrain

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / clean live-replay retrain cleanup

Files changed:
- `src/rl/rl_protocol.h`
- `src/rl/rl_session.c`
- `tools/rl_probe_server.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- let live DQN inference observe the same raw routine ids already present in transition rows.
- test whether opponent routine one-hot features let the model learn the repeated live failure pattern where close/mid `stand-hk` is punished when the opponent is already in an attack/crouch state.

Implementation notes:
- bumped `RL_OBSERVATION_SCHEMA_VERSION` and Python `OBS_SPACING_PAYLOAD_VERSION` from `2` to `3`.
- expanded `RLObsSpacingPayloadV1` / Python `OBS_SPACING_PAYLOAD` from `24` to `32` bytes by adding:
  - `obs_self_routine_1`
  - `obs_self_routine_2`
  - `obs_opp_routine_1`
  - `obs_opp_routine_2`
- added DQN categorical opponent routine features:
  - `obs_opp_routine_1_is_*` for `0,1,2,3,4`
  - `obs_opp_routine_2_is_*` for common observed values `0,1,3,4,5,6,7,8,12,13,16,17,18,19,21,24,28,32,36,37`
- DQN feature count is now `33` for newly trained models.
- old DQN manifests still load because the saved `feature_names` list is honored.

Training:
- trained `model/dqn-mixdemo-schema-v3-ground-specials-v23`.
- v23 model manifest version is `24` because v22 already used model version `23`.
- source live log:
  - `logs/rl-transitions-live-dqn-v21a-20260430-124456.ndjson`
- recipe kept from v22/v21a:
  - `--replay-source-ratios cpu-demo=0.6,human-demo=0.3,remote=0.1`
  - `--dqn-require-movable-state-sources remote`
  - `fireball-lp=8,fireball-mp=8,fireball-hp=8`

Training diagnostics:
- rows after source mix: `62830`
- experiences: `26329`
- feature count: `33`
- remote action-start rows checked: `3666`
- remote action-start rows included: `142`
- remote action-start rows filtered: `3524`
- source experiences:
  - `cpu-demo=13377`
  - `human-demo=12810`
  - `remote=142`
- remote experience action means:
  - `crouch-hp=59`, mean `-0.005`
  - `fireball-hp=39`, mean `-0.016`
  - `stand-hk=28`, mean `-0.027`
- final loss:
  - `last_loss=0.006210`
  - `avg_loss=0.006801`

Same-observation compare summary:
- CPU/human slice:
  - v21a: `stand-lp=33.7%`, `fireball-hp=32.9%`, `crouch-hp=22.8%`, `stand-hk=9.4%`, `fireball-mp=0.1%`
  - v22: `stand-lp=34.6%`, `fireball-hp=32.8%`, `crouch-hp=22.1%`, `stand-hk=9.3%`, `fireball-mp=0.1%`
  - v23: `fireball-hp=40.6%`, `tatsu-lk=18.4%`, `crouch-mk=6.1%`, `guard-crouch=4.4%`, `crouch-hp=2.5%`, `stand-hk=0.0%`, `fireball-mp=0.3%`
- old clean-live slice:
  - v21a: `fireball-hp=42.6%`, `crouch-hp=31.0%`, `stand-hk=17.0%`, `stand-lp=7.4%`, `fireball-mp=0.2%`
  - v22: `fireball-hp=42.8%`, `crouch-hp=30.6%`, `stand-hk=17.0%`, `stand-lp=7.7%`, `fireball-mp=0.2%`
  - v23: `fireball-hp=31.1%`, `tatsu-lk=21.8%`, `crouch-mk=11.2%`, `guard-crouch=7.6%`, `crouch-hp=3.7%`, `stand-hk=0.0%`, `fireball-mp=0.4%`
- v21a-live slice:
  - v21a: `crouch-hp=37.5%`, `fireball-hp=35.9%`, `stand-hk=16.5%`, `stand-lp=8.2%`, `fireball-mp=0.3%`
  - v22: `crouch-hp=36.6%`, `fireball-hp=36.3%`, `stand-hk=16.9%`, `stand-lp=8.3%`, `fireball-mp=0.3%`
  - v23: `fireball-hp=34.1%`, `tatsu-lk=23.6%`, `crouch-mk=11.4%`, `guard-crouch=5.7%`, `crouch-hp=4.0%`, `stand-hk=0.0%`, `fireball-mp=0.0%`

Focused live-failure analysis:
- in the first `5000` rows of the v21a-live log, actual `stand-hk` was most often punished in opponent attack close/mid states:
  - `(opp_r1=4, opp_r2=8, close)` had `77` actual `stand-hk` rows, net `-198`, mean `-2.571`.
  - `(opp_r1=4, opp_r2=8, mid)` had `123` actual `stand-hk` rows, net `-60`, mean `-0.488`.
- on `opp_attack_close_mid` rows:
  - v21a: `stand-hk=76.6%`
  - v22: `stand-hk=78.4%`
  - v23: `tatsu-lk=50.7%`, `crouch-hp=18.4%`, `fireball-hp=16.1%`, `stand-lp=9.2%`
- on `opp_r2=8` close/mid rows:
  - v21a: `stand-hk=58.9%`
  - v22: `stand-hk=63.3%`
  - v23: `tatsu-lk=98.2%`

Conclusion:
- v23 proves the feature path works: opponent routine one-hot features can strongly move the DQN surface, and `stand-hk` is suppressed on the same-observation replay slices.
- v23 should not be promoted as-is.
- the replacement behavior is a new sparse-action shift toward `tatsu-lk` / `crouch-mk`, not a clean defensive or low-risk punish response.
- the next candidate should constrain or penalize the replacement action in the same opponent routine/spacing pockets, or use a more targeted source/action-specific live-negative replay treatment instead of raw routine one-hot alone.

Validation:
- `python3 -m py_compile tools/rl_probe_server.py tools/train_dqn_learner.py tools/compare_dqn_models.py`
- OBS payload smoke passed:
  - payload size: `32`
  - feature count: `33`
- DQN mini-train smoke passed with the new feature vector.
- full v23 training passed.
- same-observation compares passed for CPU/human, old clean-live, and v21a-live slices.
- `git diff --check` passed.
- telemetry C build was attempted with `tools/mister/build-game.sh --flavor telemetry`, but this WSL environment has no available `docker`; a MiSTer build still needs to be run in a Docker-enabled environment before deploying OBS payload v3 live.

## 2026-04-30: Train And Compare V22 From V21a Live Replay

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / clean live-replay retrain cleanup

Files changed:
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- test whether adding the v21a live-smoke replay can reduce the observed live punish problems, especially `stand-hk` and mid-range `fireball-hp`.
- keep the v21a fireball oversample recipe while swapping the remote replay source from the earlier v9 support-prior log to the v21a live log.

Implementation notes:
- source live log:
  - `logs/rl-transitions-live-dqn-v21a-20260430-124456.ndjson`
  - rows: `8209`
  - episodes: `17`
  - model version in rows: `21`
- trained `model/dqn-mixdemo-schema-v3-ground-specials-v22`.
- v22 model manifest version is `23` because v21b already used model version `22`.
- v22 keeps:
  - `--replay-source-ratios cpu-demo=0.6,human-demo=0.3,remote=0.1`
  - `--dqn-require-movable-state-sources remote`
  - `fireball-lp=8,fireball-mp=8,fireball-hp=8`

Training diagnostics:
- row-level source mix:
  - `cpu-demo=37698` / `60.0%`
  - `human-demo=18849` / `30.0%`
  - `remote=6283` / `10.0%`
- remote action-start rows checked: `3666`
- remote action-start rows included: `142`
- remote action-start rows filtered: `3524`
- filtered reasons:
  - `self_routine_1:4=2116`
  - `self_routine_1:1=1236`
  - `self_routine_1:3=172`
- top filtered actions:
  - `crouch-hp=1404`
  - `stand-hk=1171`
  - `fireball-hp=418`
  - `stand-lp=369`
- built DQN experiences:
  - `cpu-demo=13377`
  - `human-demo=12810`
  - `remote=142`
- remote experience action means:
  - `crouch-hp=59`, mean `-0.005`
  - `fireball-hp=39`, mean `-0.016`
  - `stand-hk=28`, mean `-0.027`

Result:
- v22 trained and published successfully:
  - rows after source mix: `62830`
  - experiences: `26329`
  - last loss: `0.008240`
  - avg loss: `0.008747`
- train eval greedy:
  - `stand-lp=30.7%`
  - `fireball-hp=28.5%`
  - `crouch-hp=23.3%`
  - `stand-hk=16.7%`
  - `fireball-mp=0.0%`

Same-observation CPU/human slice compare:
- v9: `stand-lp=36.3%`, `fireball-hp=27.5%`, `crouch-hp=24.0%`, `stand-hk=9.3%`, `fireball-mp=0.1%`
- v21a: `stand-lp=33.7%`, `fireball-hp=32.9%`, `crouch-hp=22.8%`, `stand-hk=9.4%`, `fireball-mp=0.1%`
- v22: `stand-lp=34.6%`, `fireball-hp=32.8%`, `crouch-hp=22.1%`, `stand-hk=9.3%`, `fireball-mp=0.1%`
- changed decisions against v9:
  - v21a: `414/5000`
  - v22: `412/5000`

Same-observation old clean-live slice compare:
- v9: `fireball-hp=39.2%`, `crouch-hp=32.1%`, `stand-hk=16.7%`, `stand-lp=7.8%`, `fireball-mp=0.3%`
- v21a: `fireball-hp=42.6%`, `crouch-hp=31.0%`, `stand-hk=17.0%`, `stand-lp=7.4%`, `fireball-mp=0.2%`
- v22: `fireball-hp=42.8%`, `crouch-hp=30.6%`, `stand-hk=17.0%`, `stand-lp=7.7%`, `fireball-mp=0.2%`
- changed decisions against v9:
  - v21a: `347/5000`
  - v22: `354/5000`

Same-observation v21a-live slice compare:
- v9: `crouch-hp=39.6%`, `fireball-hp=31.9%`, `stand-hk=16.2%`, `stand-lp=8.7%`, `fireball-mp=0.4%`
- v21a: `crouch-hp=37.5%`, `fireball-hp=35.9%`, `stand-hk=16.5%`, `stand-lp=8.2%`, `fireball-mp=0.3%`
- v22: `crouch-hp=36.6%`, `fireball-hp=36.3%`, `stand-hk=16.9%`, `stand-lp=8.3%`, `fireball-mp=0.3%`
- changed decisions against v9:
  - v21a: `312/5000`
  - v22: `348/5000`

Conclusion:
- v22 is not a meaningful improvement over v21a.
- the v21a live replay contains the expected negative signal, but remote effective replay is only `142/26329` experiences, so the policy surface barely moves.
- the specific `stand-hk` problem is not fixed: on the v21a-live observation slice, `stand-hk` top-1 rises from v21a `16.5%` to v22 `16.9%`.
- the `fireball-mp` fix stays intact.
- do not promote v22 over v21a.
- the next change should be a trainer/inference change that gives live negative replay more targeted leverage, such as source/action-specific penalty or distance-aware reranking for `stand-hk` and close/mid `fireball-hp`.

Validation:
- full v22 training passed.
- metadata inspection passed:
  - `jq '.metadata | {rows_read, experiences, dqn_action_filter_config, replay_source_mix_stats, build: .build_diagnostics, source_experiences: .source_replay_diagnostics.experience_counts, source_actions_remote: .source_replay_diagnostics.experience_action_counts.remote, greedy_counts, greedy_top_action, greedy_top_action_rate, last_loss, avg_loss}' model/dqn-mixdemo-schema-v3-ground-specials-v22/current.json`
- same-observation compares passed:
  - `python3 tools/compare_dqn_models.py logs/rl-transitions-cpu-demo-schema-v3-4-3-3.ndjson logs/rl-transitions-human-demo-schema-v3-4-3-3.ndjson --model v9=model/dqn-mixdemo-schema-v3-ground-specials-v9 --model v21a=model/dqn-mixdemo-schema-v3-ground-specials-v21a --model v21b=model/dqn-mixdemo-schema-v3-ground-specials-v21b --model v22=model/dqn-mixdemo-schema-v3-ground-specials-v22 --limit 5000 --top-n 10 --focus-actions crouch-hp,stand-lp,stand-hk,stand-mk,fireball-lp,fireball-mp,fireball-hp,guard-stand,guard-crouch --focus-rank-limit 3 --training-action-source auto`
  - `python3 tools/compare_dqn_models.py logs/rl-transitions-live-dqn-v9-support-prior-20260430-113010.ndjson --model v9=model/dqn-mixdemo-schema-v3-ground-specials-v9 --model v21a=model/dqn-mixdemo-schema-v3-ground-specials-v21a --model v21b=model/dqn-mixdemo-schema-v3-ground-specials-v21b --model v22=model/dqn-mixdemo-schema-v3-ground-specials-v22 --limit 5000 --top-n 10 --focus-actions crouch-hp,stand-lp,stand-hk,stand-mk,fireball-lp,fireball-mp,fireball-hp,guard-stand,guard-crouch --focus-rank-limit 3 --training-action-source auto`
  - `python3 tools/compare_dqn_models.py logs/rl-transitions-live-dqn-v21a-20260430-124456.ndjson --model v9=model/dqn-mixdemo-schema-v3-ground-specials-v9 --model v21a=model/dqn-mixdemo-schema-v3-ground-specials-v21a --model v21b=model/dqn-mixdemo-schema-v3-ground-specials-v21b --model v22=model/dqn-mixdemo-schema-v3-ground-specials-v22 --limit 5000 --top-n 10 --focus-actions crouch-hp,stand-lp,stand-hk,stand-mk,fireball-lp,fireball-mp,fireball-hp,guard-stand,guard-crouch --focus-rank-limit 3 --training-action-source auto`

Follow-up:
- keep v21a as the better candidate between v21a and v22.
- implement stronger live-negative replay handling before another retrain that expects stand-hk / mid-fireball risk to move.

## 2026-04-30: Train And Compare V21a/V21b Fireball Oversample A/B

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / clean live-replay retrain cleanup

Files changed:
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- test whether v20's remaining far-range `fireball-mp` shift was caused by fireball engine-outcome oversampling rather than remote replay pollution.
- keep the v20 source mix and movable action-start filter fixed while changing only fireball oversample ratios.

Implementation notes:
- both candidates use the same live log and source mix as v20:
  - `logs/rl-transitions-live-dqn-v9-support-prior-20260430-113010.ndjson`
  - `--replay-source-ratios cpu-demo=0.6,human-demo=0.3,remote=0.1`
  - `--dqn-require-movable-state-sources remote`
- v20 fireball oversamples were `fireball-lp=10,fireball-mp=20,fireball-hp=8`.
- v21a uses balanced fireball oversamples:
  - `fireball-lp=8,fireball-mp=8,fireball-hp=8`
- v21b lowers MP further while keeping LP/HP equal:
  - `fireball-lp=8,fireball-mp=4,fireball-hp=8`
- v21a was published as `model/dqn-mixdemo-schema-v3-ground-specials-v21a` with model version `21`.
- v21b was published as `model/dqn-mixdemo-schema-v3-ground-specials-v21b` with model version `22`.

Training result:
- v21a:
  - experiences: `26317`
  - engine-outcome training experiences: `5119`
  - last loss: `0.008486`
  - avg loss: `0.008943`
  - train eval greedy: `stand-lp=29.5%`, `fireball-hp=28.5%`, `crouch-hp=24.4%`, `stand-hk=16.8%`, `fireball-mp=0.0%`
- v21b:
  - experiences: `25953`
  - engine-outcome training experiences: `4755`
  - last loss: `0.009981`
  - avg loss: `0.009018`
  - train eval greedy: `fireball-hp=31.7%`, `stand-lp=29.7%`, `crouch-hp=22.0%`, `stand-hk=15.6%`, `fireball-mp=0.0%`

Same-observation CPU/human slice compare:
- v9: `stand-lp=36.3%`, `fireball-hp=27.5%`, `crouch-hp=24.0%`, `stand-hk=9.3%`, `fireball-mp=0.1%`
- v19: `stand-lp=40.6%`, `fireball-hp=19.6%`, `fireball-mp=18.3%`, `crouch-hp=18.0%`, `stand-hk=2.5%`
- v20: `stand-lp=35.8%`, `fireball-mp=19.6%`, `crouch-hp=17.0%`, `fireball-hp=16.1%`, `stand-hk=10.4%`
- v21a: `stand-lp=33.7%`, `fireball-hp=32.9%`, `crouch-hp=22.8%`, `stand-hk=9.4%`, `fireball-mp=0.1%`
- v21b: `fireball-hp=40.6%`, `stand-lp=32.0%`, `crouch-hp=17.2%`, `stand-hk=8.7%`, `fireball-mp=0.0%`
- changed decisions against v9:
  - v19: `1451/5000`
  - v20: `1255/5000`
  - v21a: `414/5000`
  - v21b: `810/5000`

Same-observation clean-live slice compare:
- v9: `fireball-hp=39.2%`, `crouch-hp=32.1%`, `stand-hk=16.7%`, `stand-lp=7.8%`, `fireball-mp=0.3%`
- v19: `fireball-hp=30.2%`, `crouch-hp=25.5%`, `fireball-mp=18.6%`, `stand-lp=15.4%`, `stand-hk=8.7%`
- v20: `fireball-hp=26.9%`, `crouch-hp=24.8%`, `fireball-mp=20.8%`, `stand-hk=18.4%`, `stand-lp=7.5%`
- v21a: `fireball-hp=42.6%`, `crouch-hp=31.0%`, `stand-hk=17.0%`, `stand-lp=7.4%`, `fireball-mp=0.2%`
- v21b: `fireball-hp=47.8%`, `crouch-hp=26.1%`, `stand-hk=16.5%`, `stand-lp=7.7%`, `fireball-mp=0.0%`
- changed decisions against v9:
  - v19: `1539/5000`
  - v20: `1290/5000`
  - v21a: `347/5000`
  - v21b: `611/5000`

Conclusion:
- v20's `fireball-mp` shift was primarily caused by the `fireball-mp=20` engine-outcome oversample setting.
- v21a is the better candidate:
  - it removes the `fireball-mp` shift while staying closest to v9 on both CPU/human and clean-live slices.
  - it keeps `stand-lp`, `crouch-hp`, and `stand-hk` near the v9 surface.
- v21b also removes `fireball-mp`, but it pushes too much mass into `fireball-hp`, especially on clean-live rows.
- do not promote v21b over v21a based on this evidence.
- the next live smoke should use v21a, first without support-prior reranking, then optionally with the conservative support prior if live action distribution still looks too sparse-action heavy.

Validation:
- full v21a/v21b training passed.
- metadata inspection passed:
  - `jq '.metadata | {version, rows_read, experiences, engine_outcome_action_oversamples, engine_outcome_stats, source_experiences: .source_replay_diagnostics.experience_counts, source_actions: .source_replay_diagnostics.experience_action_counts, greedy_counts, greedy_top_action, greedy_top_action_rate, last_loss, avg_loss}' model/dqn-mixdemo-schema-v3-ground-specials-v21a/current.json model/dqn-mixdemo-schema-v3-ground-specials-v21b/current.json`
- same-observation compares passed:
  - `python3 tools/compare_dqn_models.py logs/rl-transitions-cpu-demo-schema-v3-4-3-3.ndjson logs/rl-transitions-human-demo-schema-v3-4-3-3.ndjson --model v9=model/dqn-mixdemo-schema-v3-ground-specials-v9 --model v19=model/dqn-mixdemo-schema-v3-ground-specials-v19 --model v20=model/dqn-mixdemo-schema-v3-ground-specials-v20 --model v21a=model/dqn-mixdemo-schema-v3-ground-specials-v21a --model v21b=model/dqn-mixdemo-schema-v3-ground-specials-v21b --limit 5000 --top-n 10 --focus-actions crouch-hp,stand-lp,stand-hk,stand-mk,fireball-lp,fireball-mp,fireball-hp,guard-stand,guard-crouch --focus-rank-limit 3 --training-action-source auto`
  - `python3 tools/compare_dqn_models.py logs/rl-transitions-live-dqn-v9-support-prior-20260430-113010.ndjson --model v9=model/dqn-mixdemo-schema-v3-ground-specials-v9 --model v19=model/dqn-mixdemo-schema-v3-ground-specials-v19 --model v20=model/dqn-mixdemo-schema-v3-ground-specials-v20 --model v21a=model/dqn-mixdemo-schema-v3-ground-specials-v21a --model v21b=model/dqn-mixdemo-schema-v3-ground-specials-v21b --limit 5000 --top-n 10 --focus-actions crouch-hp,stand-lp,stand-hk,stand-mk,fireball-lp,fireball-mp,fireball-hp,guard-stand,guard-crouch --focus-rank-limit 3 --training-action-source auto`

Follow-up:
- run a short live smoke with `model/dqn-mixdemo-schema-v3-ground-specials-v21a`.
- if v21a live smoke looks stable, collect a clean v21a live replay before any further retrain.

## 2026-04-30: Add Movable Action-Start Filtering And Train V20

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / clean live-replay retrain cleanup

Files changed:
- `tools/train_dqn_learner.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- prevent recovery / already-attacking policy selections from becoming valid DQN action samples.
- train v20 from the same clean support-prior live log used by v19, changing only remote-source action-start filtering.

Implementation notes:
- added `--dqn-require-movable-state-sources`, currently used as `--dqn-require-movable-state-sources remote`.
- filtered rows must be action starts from a configured source and fail the movable-state check:
  - `obs_self_routine_1 == 0`
  - `obs_self_routine_attack_state == 0`
  - `obs_self_contact_reaction_state == 0`
- a filtered action-start row still closes the previous valid experience's `next_state`.
- a filtered row's direct HP-delta reward can still be delayed-credit back to the previous valid experience, then the previous experience is closed so later recovery rows do not keep attributing reward to it.
- trainer metadata and diagnostics now report movable-filter counts by source, action, and reason.
- trained `model/dqn-mixdemo-schema-v3-ground-specials-v20`.
- v20 uses the same clean live log and row-level mix as v19:
  - `logs/rl-transitions-live-dqn-v9-support-prior-20260430-113010.ndjson`
  - `--replay-source-ratios cpu-demo=0.6,human-demo=0.3,remote=0.1`

Filter diagnostics:
- row-level source mix stayed unchanged:
  - `cpu-demo=37698` / `60.0%`
  - `human-demo=18849` / `30.0%`
  - `remote=6283` / `10.0%`
- remote action-start rows checked: `3231`
- remote action-start rows included: `130`
- remote action-start rows filtered: `3101`
- filtered reasons:
  - `self_routine_1:4=2182`
  - `self_routine_1:1=769`
  - `self_routine_1:3=140`
  - `self_routine_1:2=10`
- top filtered actions:
  - `crouch-hp=1084`
  - `stand-hk=908`
  - `fireball-hp=462`
  - `stand-lp=440`
  - `fireball-mp=15`
- built DQN experiences:
  - `human-demo=14212` / `51.0%`
  - `cpu-demo=13501` / `48.5%`
  - `remote=130` / `0.5%`

Result:
- v20 trained and published successfully:
  - rows after source mix: `62830`
  - experiences: `27843`
  - last loss: `0.009812`
  - avg loss: `0.008397`
- saved v20 metadata greedy distribution over its 5000-row eval slice:
  - `stand-lp=28.7%`
  - `crouch-hp=20.8%`
  - `stand-hk=19.0%`
  - `fireball-mp=18.0%`
  - `fireball-hp=12.9%`
  - `guard-crouch=0.3%`
- same-observation CPU/human slice compare:
  - v9: `stand-lp=36.3%`, `fireball-hp=27.5%`, `crouch-hp=24.0%`, `stand-hk=9.3%`, `fireball-mp=0.1%`
  - v18: `stand-lp=49.8%`, `crouch-hp=31.6%`, `fireball-hp=11.0%`, `stand-hk=5.7%`, `fireball-mp=0.1%`
  - v19: `stand-lp=40.6%`, `fireball-hp=19.6%`, `fireball-mp=18.3%`, `crouch-hp=18.0%`, `stand-hk=2.5%`
  - v20: `stand-lp=35.8%`, `fireball-mp=19.6%`, `crouch-hp=17.0%`, `fireball-hp=16.1%`, `stand-hk=10.4%`
  - changed decisions: v9 -> v20 `1255/5000`
- same-observation clean-live slice compare:
  - v9: `fireball-hp=39.2%`, `crouch-hp=32.1%`, `stand-hk=16.7%`, `stand-lp=7.8%`, `fireball-mp=0.3%`
  - v18: `crouch-hp=44.5%`, `stand-lp=20.5%`, `fireball-hp=19.5%`, `stand-hk=12.5%`, `fireball-mp=0.5%`
  - v19: `fireball-hp=30.2%`, `crouch-hp=25.5%`, `fireball-mp=18.6%`, `stand-lp=15.4%`, `stand-hk=8.7%`
  - v20: `fireball-hp=26.9%`, `crouch-hp=24.8%`, `fireball-mp=20.8%`, `stand-hk=18.4%`, `stand-lp=7.5%`
  - changed decisions: v9 -> v20 `1290/5000`
- conclusion:
  - movable action-start filtering confirms that most clean-live remote policy starts were not valid new action opportunities.
  - v20 improves the v19 `stand-lp` drift and slightly reduces `crouch-hp`.
  - v20 does not solve the `fireball-mp` shift; the remaining far-range `fireball-mp` preference appears to be a separate demo / reward / oversample surface, not the same recovery-state pollution.
  - v20 should not replace v9 for live use yet.

Validation:
- Python compile passed:
  - `python3 -m py_compile tools/train_dqn_learner.py`
- whitespace check passed:
  - `git diff --check -- tools/train_dqn_learner.py`
- movable-filter smoke passed:
  - `python3 tools/train_dqn_learner.py logs/rl-transitions-cpu-demo-schema-v3-4-3-3.ndjson logs/rl-transitions-human-demo-schema-v3-4-3-3.ndjson logs/rl-transitions-live-dqn-v9-support-prior-20260430-113010.ndjson --model-dir /tmp/rl-dqn-movable-filter-smoke --model-version 1 --steps 2 --batch-size 16 --hidden-sizes 8 --actions forward,back,guard-stand,guard-crouch,stand-lp,stand-hk,crouch-hp,fireball-hp,fireball-mp --fallback-policy stand-mk --training-action-source auto --reward-risk-profile none --engine-outcome-training-mode prefer-engine-action --engine-outcome-window-decisions 15 --dqn-require-movable-state-sources remote --replay-source-ratios cpu-demo=0.6,human-demo=0.3,remote=0.1 --log-interval 1 --eval-limit 200 --diagnostic-top-n 8`
- full v20 training passed:
  - `python3 tools/train_dqn_learner.py logs/rl-transitions-cpu-demo-schema-v3-4-3-3.ndjson logs/rl-transitions-human-demo-schema-v3-4-3-3.ndjson logs/rl-transitions-live-dqn-v9-support-prior-20260430-113010.ndjson --model-dir model/dqn-mixdemo-schema-v3-ground-specials-v20 --model-version 20 --steps 3000 --batch-size 64 --gamma 0.9 --learning-rate 0.001 --target-sync-steps 200 --dqn-target-mode standard --replay-source-ratios cpu-demo=0.6,human-demo=0.3,remote=0.1 --dqn-require-movable-state-sources remote --actions forward,back,guard-stand,guard-crouch,stand-lp,stand-mp,stand-hp,stand-lk,stand-mk,stand-hk,forward-hp,crouch-lp,crouch-mp,crouch-hp,crouch-lk,crouch-mk,crouch-hk,fireball-lp,fireball-mp,fireball-hp,throw,shoryuken-lp,shoryuken-mp,shoryuken-hp,tatsu-lk,tatsu-mk,tatsu-hk --fallback-policy stand-mk --training-action-source auto --reward-risk-profile all-attacks --reward-risk-window-decisions 15 --reward-attack-no-damage-cost 0.3 --reward-attack-punished-cost 1.0 --reward-shoryuken-no-damage-extra-cost 0.0 --reward-shoryuken-punished-extra-cost 0.5 --reward-jump-attack-no-damage-extra-cost 0.0 --reward-jump-attack-punished-extra-cost 0.0 --reward-guard-success-bonus 0.0 --reward-guard-success-window-decisions 6 --reward-guard-threat-max-dx 120 --reward-passive-guard-cost 0.3 --reward-far-guard-cost 0.5 --reward-spacing-target-min-dx 50 --reward-spacing-target-max-dx 120 --reward-spacing-improve-bonus 0.5 --reward-spacing-worsen-cost 0.2 --reward-spacing-maintain-bonus 0.1 --reward-spacing-threat-back-bonus 0.3 --engine-outcome-training-mode prefer-engine-action --engine-outcome-window-decisions 15 --engine-outcome-action-windows fireball-lp=45,fireball-mp=45,fireball-hp=45,tatsu-lk=25,tatsu-mk=25,tatsu-hk=25 --engine-outcome-hit-bonus 1.0 --engine-outcome-no-damage-cost 0.2 --engine-outcome-punished-cost 1.0 --engine-outcome-oversample 1 --engine-outcome-action-oversamples fireball-lp=10,fireball-mp=20,fireball-hp=8,shoryuken-lp=4,shoryuken-mp=6,shoryuken-hp=8,tatsu-lk=6,tatsu-mk=6,tatsu-hk=6 --batch-sampling balanced --balanced-batch-ratios movement=0.3,normal=0.3,special=0.4 --epsilon 0.05 --seed 7 --log-interval 500 --eval-limit 5000 --diagnostic-top-n 12`
- metadata inspection passed:
  - `jq '.metadata | {rows_read, experiences, dqn_action_filter_config, build_diagnostics: .build_diagnostics, source_rows: .source_replay_diagnostics.row_counts, source_experiences: .source_replay_diagnostics.experience_counts, source_actions_remote: .source_replay_diagnostics.experience_action_counts.remote, greedy_counts, greedy_top_action, greedy_top_action_rate, last_loss, avg_loss}' model/dqn-mixdemo-schema-v3-ground-specials-v20/current.json`
- same-observation compares passed:
  - `python3 tools/compare_dqn_models.py logs/rl-transitions-cpu-demo-schema-v3-4-3-3.ndjson logs/rl-transitions-human-demo-schema-v3-4-3-3.ndjson --model v9=model/dqn-mixdemo-schema-v3-ground-specials-v9 --model v18=model/dqn-mixdemo-schema-v3-ground-specials-v18 --model v19=model/dqn-mixdemo-schema-v3-ground-specials-v19 --model v20=model/dqn-mixdemo-schema-v3-ground-specials-v20 --limit 5000 --top-n 10 --focus-actions crouch-hp,stand-lp,stand-hk,stand-mk,fireball-lp,fireball-mp,fireball-hp,guard-stand,guard-crouch --focus-rank-limit 3 --training-action-source auto`
  - `python3 tools/compare_dqn_models.py logs/rl-transitions-live-dqn-v9-support-prior-20260430-113010.ndjson --model v9=model/dqn-mixdemo-schema-v3-ground-specials-v9 --model v18=model/dqn-mixdemo-schema-v3-ground-specials-v18 --model v19=model/dqn-mixdemo-schema-v3-ground-specials-v19 --model v20=model/dqn-mixdemo-schema-v3-ground-specials-v20 --limit 5000 --top-n 10 --focus-actions crouch-hp,stand-lp,stand-hk,stand-mk,fireball-lp,fireball-mp,fireball-hp,guard-stand,guard-crouch --focus-rank-limit 3 --training-action-source auto`

Follow-up:
- keep v9 plus conservative support-prior as the safer live baseline.
- investigate the far-range `fireball-mp` surface separately, likely by adjusting fireball strength oversamples / support priors or adding a policy-improvement gate before accepting live-replay-trained candidates.

## 2026-04-30: Train And Compare V19 Clean Live-Replay DQN

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / replay source mixing preparation

Files changed:
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- train the next live-replay candidate from the cleaner v9 support-prior live log.
- keep the source mix controlled against v18 by using the same row-level ratio and changing only the remote log source.

Implementation notes:
- source live log:
  - `logs/rl-transitions-live-dqn-v9-support-prior-20260430-113010.ndjson`
  - rows: `8081`
  - episodes: `(12, 1)` through `(12, 12)`
  - policy source rows: `8081`
- live log action distribution from analyzer:
  - `fireball-hp=3782`
  - `crouch-hp=1472`
  - `stand-hk=1180`
  - `stand-lp=596`
  - `guard-crouch=312`
  - `tatsu-lk=138`
  - `fireball-mp=106`
- trained `model/dqn-mixdemo-schema-v3-ground-specials-v19`.
- v19 uses the v9/v18 ground-specials recipe, standard DQN target mode, and:
  - `--replay-source-ratios cpu-demo=0.6,human-demo=0.3,remote=0.1`
- row-level source mix:
  - before mix: `cpu-demo=122276`, `human-demo=18849`, `remote=8078`, `repeated-last-action=3`
  - after mix: `cpu-demo=37698` / `60.0%`, `human-demo=18849` / `30.0%`, `remote=6283` / `10.0%`
- built DQN experiences:
  - `human-demo=14212` / `45.9%`
  - `cpu-demo=13501` / `43.6%`
  - `remote=3231` / `10.4%`

Result:
- v19 trained and published successfully:
  - rows after source mix: `62830`
  - experiences: `30944`
  - last loss: `0.006458`
  - avg loss: `0.007458`
- saved v19 metadata greedy distribution over its 5000-row eval slice:
  - `stand-lp=41.2%`
  - `crouch-hp=22.5%`
  - `fireball-mp=16.1%`
  - `fireball-hp=15.3%`
  - `stand-hk=4.2%`
  - `guard-crouch=0.4%`
- same-observation CPU/human slice compare:
  - v9: `stand-lp=36.3%`, `fireball-hp=27.5%`, `crouch-hp=24.0%`, `stand-hk=9.3%`, `guard-crouch=1.7%`
  - v9 with conservative support prior: `stand-lp=35.6%`, `fireball-hp=29.5%`, `crouch-hp=22.2%`, `stand-hk=9.3%`, `guard-crouch=2.1%`
  - v18: `stand-lp=49.8%`, `crouch-hp=31.6%`, `fireball-hp=11.0%`, `stand-hk=5.7%`, `guard-crouch=0.4%`
  - v19: `stand-lp=40.6%`, `fireball-hp=19.6%`, `fireball-mp=18.3%`, `crouch-hp=18.0%`, `stand-hk=2.5%`, `guard-crouch=0.6%`
  - changed decisions: v9 -> v19 `1451/5000`
- same-observation clean-live slice compare:
  - v9: `fireball-hp=39.2%`, `crouch-hp=32.1%`, `stand-hk=16.7%`, `stand-lp=7.8%`, `guard-crouch=2.6%`
  - v9 with conservative support prior: `fireball-hp=40.8%`, `crouch-hp=30.3%`, `stand-hk=16.8%`, `stand-lp=7.4%`, `guard-crouch=2.8%`
  - v18: `crouch-hp=44.5%`, `stand-lp=20.5%`, `fireball-hp=19.5%`, `stand-hk=12.5%`, `guard-crouch=0.2%`
  - v19: `fireball-hp=30.2%`, `crouch-hp=25.5%`, `fireball-mp=18.6%`, `stand-lp=15.4%`, `stand-hk=8.7%`, `guard-crouch=0.5%`
  - changed decisions: v9 -> v19 `1539/5000`
- conclusion:
  - v19 is better than v18 on the clean-live slice because it avoids v18's `crouch-hp=44.5%` shift.
  - v19 should not replace v9 yet: CPU/human rows still drift toward `stand-lp`, and far-range rows introduce a new `fireball-mp` preference.
  - the clean support-prior replay is useful training signal, but 10% remote replay is still high enough to move the policy surface materially.

Validation:
- analyzer passed:
  - `python3 tools/analyze_rl_transitions.py logs/rl-transitions-live-dqn-v9-support-prior-20260430-113010.ndjson --training-action-source auto`
- full v19 training passed:
  - `python3 tools/train_dqn_learner.py logs/rl-transitions-cpu-demo-schema-v3-4-3-3.ndjson logs/rl-transitions-human-demo-schema-v3-4-3-3.ndjson logs/rl-transitions-live-dqn-v9-support-prior-20260430-113010.ndjson --model-dir model/dqn-mixdemo-schema-v3-ground-specials-v19 --model-version 19 --steps 3000 --batch-size 64 --gamma 0.9 --learning-rate 0.001 --target-sync-steps 200 --dqn-target-mode standard --replay-source-ratios cpu-demo=0.6,human-demo=0.3,remote=0.1 --actions forward,back,guard-stand,guard-crouch,stand-lp,stand-mp,stand-hp,stand-lk,stand-mk,stand-hk,forward-hp,crouch-lp,crouch-mp,crouch-hp,crouch-lk,crouch-mk,crouch-hk,fireball-lp,fireball-mp,fireball-hp,throw,shoryuken-lp,shoryuken-mp,shoryuken-hp,tatsu-lk,tatsu-mk,tatsu-hk --fallback-policy stand-mk --training-action-source auto --reward-risk-profile all-attacks --reward-risk-window-decisions 15 --reward-attack-no-damage-cost 0.3 --reward-attack-punished-cost 1.0 --reward-shoryuken-no-damage-extra-cost 0.0 --reward-shoryuken-punished-extra-cost 0.5 --reward-jump-attack-no-damage-extra-cost 0.0 --reward-jump-attack-punished-extra-cost 0.0 --reward-guard-success-bonus 0.0 --reward-guard-success-window-decisions 6 --reward-guard-threat-max-dx 120 --reward-passive-guard-cost 0.3 --reward-far-guard-cost 0.5 --reward-spacing-target-min-dx 50 --reward-spacing-target-max-dx 120 --reward-spacing-improve-bonus 0.5 --reward-spacing-worsen-cost 0.2 --reward-spacing-maintain-bonus 0.1 --reward-spacing-threat-back-bonus 0.3 --engine-outcome-training-mode prefer-engine-action --engine-outcome-window-decisions 15 --engine-outcome-action-windows fireball-lp=45,fireball-mp=45,fireball-hp=45,tatsu-lk=25,tatsu-mk=25,tatsu-hk=25 --engine-outcome-hit-bonus 1.0 --engine-outcome-no-damage-cost 0.2 --engine-outcome-punished-cost 1.0 --engine-outcome-oversample 1 --engine-outcome-action-oversamples fireball-lp=10,fireball-mp=20,fireball-hp=8,shoryuken-lp=4,shoryuken-mp=6,shoryuken-hp=8,tatsu-lk=6,tatsu-mk=6,tatsu-hk=6 --batch-sampling balanced --balanced-batch-ratios movement=0.3,normal=0.3,special=0.4 --epsilon 0.05 --seed 7 --log-interval 500 --eval-limit 5000 --diagnostic-top-n 12`
- metadata inspection passed:
  - `jq '.metadata | {rows_read, rows_read_before_source_mix, experiences, replay_source_mix_stats, source_rows:.source_replay_diagnostics.row_counts, source_experiences:.source_replay_diagnostics.experience_counts, model_versions:.source_replay_diagnostics.experience_model_version_counts, greedy_counts, greedy_top_action, greedy_top_action_rate, dqn_target_mode, last_loss, avg_loss}' model/dqn-mixdemo-schema-v3-ground-specials-v19/current.json`
- same-observation compares passed:
  - `python3 tools/compare_dqn_models.py logs/rl-transitions-cpu-demo-schema-v3-4-3-3.ndjson logs/rl-transitions-human-demo-schema-v3-4-3-3.ndjson --model v9=model/dqn-mixdemo-schema-v3-ground-specials-v9 --model v9r=model/dqn-mixdemo-schema-v3-ground-specials-v9 --model v19=model/dqn-mixdemo-schema-v3-ground-specials-v19 --limit 5000 --top-n 10 --focus-actions crouch-hp,stand-lp,stand-hk,stand-mk,fireball-lp,fireball-mp,fireball-hp,guard-stand,guard-crouch --focus-rank-limit 3 --training-action-source auto --dqn-support-prior-models v9r --dqn-support-prior-min-count 300 --dqn-support-prior-count-penalty 0.005 --dqn-support-prior-negative-mean-penalty 0.002`
  - `python3 tools/compare_dqn_models.py logs/rl-transitions-live-dqn-v9-support-prior-20260430-113010.ndjson --model v9=model/dqn-mixdemo-schema-v3-ground-specials-v9 --model v9r=model/dqn-mixdemo-schema-v3-ground-specials-v9 --model v19=model/dqn-mixdemo-schema-v3-ground-specials-v19 --limit 5000 --top-n 10 --focus-actions crouch-hp,stand-lp,stand-hk,stand-mk,fireball-lp,fireball-mp,fireball-hp,guard-stand,guard-crouch --focus-rank-limit 3 --training-action-source auto --dqn-support-prior-models v9r --dqn-support-prior-min-count 300 --dqn-support-prior-count-penalty 0.005 --dqn-support-prior-negative-mean-penalty 0.002`
- Python compile passed:
  - `python3 -m py_compile tools/train_dqn_learner.py tools/compare_dqn_models.py`

Follow-up:
- do not promote v19 to live use as-is.
- next candidate should reduce the remote ratio below 10%, add source-specific filtering, or add a policy-improvement gate so remote rows teach negative outcomes without moving the whole policy toward `stand-lp` / `fireball-mp`.

## 2026-04-30: Add DQN Action-Support Prior Reranking

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / DQN sparse-action overestimation control

Files changed:
- `tools/rl_probe_server.py`
- `tools/compare_dqn_models.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- add an opt-in inference-time reranker that uses actor metadata action support without retraining model weights.
- test whether a conservative support prior can reduce the v9 `stand-lp` / `crouch-hp` / `fireball-hp` sparse-action surface without creating a new guard, back, or fireball collapse.

Implementation notes:
- DQN actor loading now preserves manifest `metadata`, including trainer-written `action_counts` and `action_rewards`.
- added `DQNSupportPriorConfig` and shared DQN ranking helpers in `tools/rl_probe_server.py`.
- probe-side DQN inference can now subtract support penalties from raw Q scores with:
  - `--dqn-support-prior-min-count`
  - `--dqn-support-prior-count-penalty`
  - `--dqn-support-prior-negative-mean-penalty`
  - `--dqn-support-prior-exempt-actions`
- default probe behavior remains unchanged because all support-prior flags default to off.
- `tools/compare_dqn_models.py` can apply the same reranker to selected model labels with `--dqn-support-prior-models`, so raw v9 and reranked v9 can be compared on the same observation rows.

Result:
- default no-prior comparison stayed identical:
  - raw v9 vs duplicate v9 on CPU/human rows: `changed=0/5000`
- stronger priors were too aggressive on the CPU/human slice:
  - `min=500,count=0.08,neg=0.04`: `fireball-hp=46.9%`, changed `2314/5000`
  - `min=1000,count=0.08,neg=0.04`: `fireball-hp=47.0%`, changed `2457/5000`
  - `min=500,count=0.12,neg=0.06`: `fireball-hp=50.0%`, changed `2879/5000`
- medium priors reduced `crouch-hp` but still pushed too much toward fireball on live-v9 observations:
  - `min=300,count=0.01,neg=0.005` on CPU/human: `stand-lp=34.2%`, `fireball-hp=31.8%`, `crouch-hp=20.3%`, changed `298/5000`
  - the same setting on live-v9 rows: `fireball-hp=48.4%`, `crouch-hp=26.3%`, changed `213/1967`
- the current conservative live-recording candidate is:
  - `--dqn-support-prior-min-count 300 --dqn-support-prior-count-penalty 0.005 --dqn-support-prior-negative-mean-penalty 0.002`
  - CPU/human rows: v9 `stand-lp=36.3%`, `fireball-hp=27.5%`, `crouch-hp=24.0%` -> reranked `stand-lp=35.6%`, `fireball-hp=29.5%`, `crouch-hp=22.2%`, changed `134/5000`
  - live-v9 rows: v9 `fireball-hp=39.2%`, `crouch-hp=35.8%`, `stand-hk=16.6%`, `guard-crouch=2.3%` -> reranked `fireball-hp=42.2%`, `crouch-hp=32.6%`, `stand-hk=16.7%`, `guard-crouch=2.7%`, changed `74/1967`
- an even milder count-only candidate is available if fireball increase must be minimized:
  - `--dqn-support-prior-min-count 300 --dqn-support-prior-count-penalty 0.005 --dqn-support-prior-negative-mean-penalty 0.0`
  - CPU/human rows: reranked `stand-lp=37.0%`, `fireball-hp=28.7%`, `crouch-hp=21.7%`, changed `120/5000`
  - live-v9 rows: reranked `fireball-hp=41.6%`, `crouch-hp=32.3%`, changed `73/1967`
- conclusion:
  - the support-prior infrastructure is useful and safe to keep because it is fully opt-in.
  - do not use the stronger settings for live collection; they shift the policy toward a fireball-heavy surface.
  - the next clean live replay should start with the low prior above, short-smoke the action distribution, and only then use the resulting remote rows for another retrain.

Validation:
- Python compile passed:
  - `python3 -m py_compile tools/rl_probe_server.py tools/compare_dqn_models.py`
- whitespace check passed:
  - `git diff --check -- tools/rl_probe_server.py tools/compare_dqn_models.py`
- raw/no-prior compare passed:
  - `python3 tools/compare_dqn_models.py logs/rl-transitions-cpu-demo-schema-v3-4-3-3.ndjson logs/rl-transitions-human-demo-schema-v3-4-3-3.ndjson --model v9=model/dqn-mixdemo-schema-v3-ground-specials-v9 --model v9copy=model/dqn-mixdemo-schema-v3-ground-specials-v9 --limit 5000 --top-n 5 --training-action-source auto`
- conservative rerank compares passed:
  - `python3 tools/compare_dqn_models.py logs/rl-transitions-cpu-demo-schema-v3-4-3-3.ndjson logs/rl-transitions-human-demo-schema-v3-4-3-3.ndjson --model v9=model/dqn-mixdemo-schema-v3-ground-specials-v9 --model v9r=model/dqn-mixdemo-schema-v3-ground-specials-v9 --limit 5000 --top-n 8 --training-action-source auto --dqn-support-prior-models v9r --dqn-support-prior-min-count 300 --dqn-support-prior-count-penalty 0.005 --dqn-support-prior-negative-mean-penalty 0.002`
  - `python3 tools/compare_dqn_models.py logs/rl-transitions-live-dqn-ground-specials-v9-4-3-3.ndjson --model v9=model/dqn-mixdemo-schema-v3-ground-specials-v9 --model v9r=model/dqn-mixdemo-schema-v3-ground-specials-v9 --limit 5000 --top-n 8 --training-action-source auto --dqn-support-prior-models v9r --dqn-support-prior-min-count 300 --dqn-support-prior-count-penalty 0.005 --dqn-support-prior-negative-mean-penalty 0.002`

Follow-up:
- collect a short clean live replay with v9 plus the conservative support-prior flags before doing another source-mix retrain.
- keep remote replay at a declared low ratio for the next candidate and compare it against both raw v9 and reranked v9 before live promotion.
- do not treat v18 as a live candidate; its source-mix result has been reviewed and should not replace v9.

## 2026-04-30: Train And Compare V18 Source-Mixed DQN

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / replay source mixing preparation

Files changed:
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- train the first v18 candidate with an explicit row-level source mix.
- test whether adding a small amount of v9 live-policy replay improves the v9 ground-specials policy surface without reinforcing sparse-action overestimation.

Implementation notes:
- trained `model/dqn-mixdemo-schema-v3-ground-specials-v18`.
- v18 uses the v9 ground-specials recipe, standard DQN target mode, and the new source-mix control:
  - `--replay-source-ratios cpu-demo=0.6,human-demo=0.3,remote=0.1`
- row-level source mix was exactly:
  - `cpu-demo=11682` / `60.0%`
  - `human-demo=5841` / `30.0%`
  - `remote=1947` / `10.0%`
- `repeated-last-action=16` and `neutral-fallback=4` were dropped because they were not listed in the ratio.
- built DQN experiences were:
  - `human-demo=4405` / `45.3%`
  - `cpu-demo=4227` / `43.5%`
  - `remote=1083` / `11.1%`
- experience mix differs from row mix because DQN replay is decision/macro based and engine-outcome oversampling changes source density.

Result:
- v18 trained and published successfully:
  - rows: `19470`
  - experiences: `9715`
  - last loss: `0.004914`
  - avg loss: `0.006962`
- saved v18 metadata greedy distribution over its 5000-row eval slice:
  - `stand-lp=48.6%`
  - `crouch-hp=31.0%`
  - `stand-hk=10.4%`
  - `fireball-hp=8.7%`
  - `guard-crouch=0.3%`
- same-observation CPU/human slice compare against v9:
  - v9: `stand-lp=36.3%`, `fireball-hp=27.5%`, `crouch-hp=24.0%`, `stand-hk=9.3%`, `guard-crouch=1.7%`
  - v18: `stand-lp=49.8%`, `crouch-hp=31.6%`, `fireball-hp=11.0%`, `stand-hk=5.7%`, `guard-crouch=0.4%`
  - changed decisions: `1249/5000`
- same-observation v9-live-log compare:
  - v9: `fireball-hp=39.2%`, `crouch-hp=35.8%`, `stand-hk=16.6%`, `stand-lp=5.8%`, `guard-crouch=2.3%`
  - v18: `crouch-hp=49.2%`, `fireball-hp=19.3%`, `stand-lp=18.2%`, `stand-hk=11.5%`, `guard-crouch=0.5%`
  - changed decisions: `589/1967`
- conclusion:
  - v18 does not create a guard collapse or LP/MP fireball collapse.
  - v18 also does not improve the sparse-action overestimation problem.
  - adding 10% v9 live replay mostly shifts probability away from `fireball-hp` into `stand-lp` and `crouch-hp`.
  - v18 should not replace v9 for live use based on offline evidence.

Validation:
- Python compile passed:
  - `python3 -m py_compile tools/train_dqn_learner.py tools/compare_dqn_models.py`
- full v18 training passed:
  - `python3 tools/train_dqn_learner.py logs/rl-transitions-cpu-demo-schema-v3-4-3-3.ndjson logs/rl-transitions-human-demo-schema-v3-4-3-3.ndjson logs/rl-transitions-live-dqn-ground-specials-v9-4-3-3.ndjson --model-dir model/dqn-mixdemo-schema-v3-ground-specials-v18 --model-version 18 --steps 3000 --batch-size 64 --gamma 0.9 --learning-rate 0.001 --target-sync-steps 200 --dqn-target-mode standard --replay-source-ratios cpu-demo=0.6,human-demo=0.3,remote=0.1 --actions forward,back,guard-stand,guard-crouch,stand-lp,stand-mp,stand-hp,stand-lk,stand-mk,stand-hk,forward-hp,crouch-lp,crouch-mp,crouch-hp,crouch-lk,crouch-mk,crouch-hk,fireball-lp,fireball-mp,fireball-hp,throw,shoryuken-lp,shoryuken-mp,shoryuken-hp,tatsu-lk,tatsu-mk,tatsu-hk --fallback-policy stand-mk --training-action-source auto --reward-risk-profile all-attacks --reward-risk-window-decisions 15 --reward-attack-no-damage-cost 0.3 --reward-attack-punished-cost 1.0 --reward-shoryuken-no-damage-extra-cost 0.0 --reward-shoryuken-punished-extra-cost 0.5 --reward-jump-attack-no-damage-extra-cost 0.0 --reward-jump-attack-punished-extra-cost 0.0 --reward-guard-success-bonus 0.0 --reward-guard-success-window-decisions 6 --reward-guard-threat-max-dx 120 --reward-passive-guard-cost 0.3 --reward-far-guard-cost 0.5 --reward-spacing-target-min-dx 50 --reward-spacing-target-max-dx 120 --reward-spacing-improve-bonus 0.5 --reward-spacing-worsen-cost 0.2 --reward-spacing-maintain-bonus 0.1 --reward-spacing-threat-back-bonus 0.3 --engine-outcome-training-mode prefer-engine-action --engine-outcome-window-decisions 15 --engine-outcome-action-windows fireball-lp=45,fireball-mp=45,fireball-hp=45,tatsu-lk=25,tatsu-mk=25,tatsu-hk=25 --engine-outcome-hit-bonus 1.0 --engine-outcome-no-damage-cost 0.2 --engine-outcome-punished-cost 1.0 --engine-outcome-oversample 1 --engine-outcome-action-oversamples fireball-lp=10,fireball-mp=20,fireball-hp=8,shoryuken-lp=4,shoryuken-mp=6,shoryuken-hp=8,tatsu-lk=6,tatsu-mk=6,tatsu-hk=6 --batch-sampling balanced --balanced-batch-ratios movement=0.3,normal=0.3,special=0.4 --epsilon 0.05 --seed 7 --log-interval 500 --eval-limit 5000 --diagnostic-top-n 12`
- metadata inspection passed:
  - `jq '.metadata | {rows_read, rows_read_before_source_mix, experiences, replay_source_mix_stats, source_rows:.source_replay_diagnostics.row_counts, source_experiences:.source_replay_diagnostics.experience_counts, model_versions:.source_replay_diagnostics.experience_model_version_counts, batch_sampling, greedy_counts, greedy_top_action, greedy_top_action_rate, dqn_target_mode, last_loss, avg_loss}' model/dqn-mixdemo-schema-v3-ground-specials-v18/current.json`
- CPU/human same-observation compare passed:
  - `python3 tools/compare_dqn_models.py logs/rl-transitions-cpu-demo-schema-v3-4-3-3.ndjson logs/rl-transitions-human-demo-schema-v3-4-3-3.ndjson --model v9=model/dqn-mixdemo-schema-v3-ground-specials-v9 --model v18=model/dqn-mixdemo-schema-v3-ground-specials-v18 --limit 5000 --top-n 8 --focus-actions crouch-hp,stand-lp,stand-hk,stand-mk,fireball-lp,fireball-mp,fireball-hp,guard-stand,guard-crouch --focus-rank-limit 3 --training-action-source auto`
- v9-live-log same-observation compare passed:
  - `python3 tools/compare_dqn_models.py logs/rl-transitions-live-dqn-ground-specials-v9-4-3-3.ndjson --model v9=model/dqn-mixdemo-schema-v3-ground-specials-v9 --model v18=model/dqn-mixdemo-schema-v3-ground-specials-v18 --limit 5000 --top-n 8 --focus-actions crouch-hp,stand-lp,stand-hk,stand-mk,fireball-lp,fireball-mp,fireball-hp,guard-stand,guard-crouch --focus-rank-limit 3 --training-action-source auto`

Follow-up:
- do not promote v18 to live testing as-is.
- avoid using v9 live replay as a default positive training source until the trainer can apply stronger action-support priors, source-specific weights, or policy-improvement filtering.
- next useful path is inference-time reranking / action-support prior, because source-mix retraining still shifts collapse among `stand-lp`, `crouch-hp`, and `fireball-hp` instead of adding a healthier tactical spread.

## 2026-04-30: Add Opt-In DQN Replay Source Mix Controls

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / replay source mixing preparation

Files changed:
- `tools/train_dqn_learner.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- allow a v18-style DQN run to train from mixed live-policy and demo logs with an explicit, reproducible source policy.
- keep default trainer behavior raw so existing v9/v17 recipes and comparisons remain unchanged.

Implementation notes:
- added source-mix flags that run after log read / initial-episode drop and before DQN experience building:
  - `--replay-source-include`
  - `--replay-source-exclude`
  - `--replay-source-max-rows`
  - `--replay-source-ratios`
- source names accept labels such as `remote`, `human-demo`, `cpu-demo`, `repeated-last-action`, and `neutral-fallback`, plus numeric execution-source ids.
- `--replay-source-ratios` performs deterministic row-level undersampling with `--seed` and does not oversample scarce sources.
- when ratios are set, sources not listed in the ratio are dropped; this gives a concise v18 candidate shape such as `remote=0.7,human-demo=0.3` while excluding repeated-action and fallback rows.
- actor metadata now records:
  - `rows_read_before_source_mix`
  - `replay_source_mix_config`
  - `replay_source_mix_stats`
- stdout prints `source_mix=...` in the publish summary and a `replay_source_mix=...` diagnostics line with pre/post/target source counts.

Result:
- raw mode preserved previous behavior in the smoke test:
  - `source_mix=raw:1200->1200`
  - `replay_source_mix=mode:raw rows:1200->1200 dropped:0`
- ratio mode worked on the mixed live-v9 + human-demo smoke:
  - source mix rows changed from `3000` to `2781`
  - post-mix rows were `remote=1947` and `human-demo=834`
  - `repeated-last-action=16` and `neutral-fallback=4` were dropped because they were not listed in the target ratio
  - row-level mix landed at `70.0% remote / 30.0% human-demo`
- experience-level mix was `remote=1041` and `human-demo=349`; this differs from row-level mix because DQN experience construction is decision/macro based.

Validation:
- Python compile passed:
  - `python3 -m py_compile tools/train_dqn_learner.py`
- raw source-mix smoke passed:
  - `python3 tools/train_dqn_learner.py logs/rl-transitions-cpu-demo-schema-v3-4-3-3.ndjson logs/rl-transitions-human-demo-schema-v3-4-3-3.ndjson --model-dir /tmp/rl-dqn-source-mix-raw-smoke --model-version 1 --limit 1200 --steps 2 --batch-size 16 --hidden-sizes 8 --actions forward,back,guard-stand,guard-crouch,stand-mk,crouch-hp,fireball-lp,fireball-mp,fireball-hp --fallback-policy stand-mk --training-action-source auto --reward-risk-profile none --engine-outcome-training-mode prefer-engine-action --engine-outcome-window-decisions 15 --engine-outcome-action-windows fireball-lp=45,fireball-mp=45,fireball-hp=45 --log-interval 1 --eval-limit 200 --diagnostic-top-n 8`
  - reported unchanged raw source mix.
- ratio source-mix smoke passed:
  - `python3 tools/train_dqn_learner.py logs/rl-transitions-live-dqn-ground-specials-v9-4-3-3.ndjson logs/rl-transitions-human-demo-schema-v3-4-3-3.ndjson --model-dir /tmp/rl-dqn-source-mix-ratio-smoke --model-version 2 --limit 3000 --steps 2 --batch-size 16 --hidden-sizes 8 --actions forward,back,guard-stand,guard-crouch,stand-lp,stand-hk,crouch-hp,fireball-hp --fallback-policy stand-mk --training-action-source auto --reward-risk-profile none --engine-outcome-training-mode prefer-engine-action --engine-outcome-window-decisions 15 --replay-source-ratios remote=0.7,human-demo=0.3 --log-interval 1 --eval-limit 200 --diagnostic-top-n 8`
  - reported `replay_source_mix=mode:configured rows:3000->2781 dropped:219 ... post:remote:1947/70.0%,human-demo:834/30.0%`.
- metadata spot-check passed:
  - `jq '.metadata | {rows_read, rows_read_before_source_mix, replay_source_mix_config, replay_source_mix_stats}' /tmp/rl-dqn-source-mix-ratio-smoke/current.json`

Follow-up:
- choose the actual v18 source mix recipe before full training; first candidate is likely v9-style DQN recipe plus `--replay-source-ratios remote=0.7,human-demo=0.3` against the v9 live log and fresh human-demo / CPU-demo logs.
- compare any v18 candidate against v9/v17 on the same observation slice before live testing, with special attention to whether remote replay amplifies the existing `crouch-hp` / `stand-lp` / `fireball-hp` policy surface.

## 2026-04-30: Add Source-Aware DQN Replay Diagnostics

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / replay source mixing preparation

Files changed:
- `tools/train_dqn_learner.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- make source composition visible before training a v18-style model from mixed demo plus live policy logs.
- keep this as a diagnostics-only step so existing v9/v17 training comparisons are not confounded by a hidden replay sampling change.

Implementation notes:
- added `source_replay_diagnostics` to DQN actor metadata.
- diagnostics split both raw replay rows and built DQN experiences by:
  - `execution_source`: `none`, `remote`, `repeated-last-action`, `neutral-fallback`, `human-demo`, `cpu-demo`
  - `model_version_executed`
  - per-source action count / reward / mean reward
- `Experience` now carries `source_name` and `model_version` metadata for diagnostics, but training inputs, targets, batch sampling, and greedy inference behavior are unchanged.
- macro delayed rewards and conservative action penalties update the per-source reward sums, so source reward diagnostics match the final replay rewards used by the trainer.

Result:
- CPU-demo smoke correctly reported `cpu-demo` as 100% of rows and experiences, with `model_version_executed = 0`.
- mixed live-v9 + human-demo smoke reported:
  - rows: `remote=1947`, `human-demo=1033`, `repeated-last-action=16`, `neutral-fallback=4`
  - row model versions: `9=1967`, `0=1033`
  - experiences: `remote=1041`, `human-demo=422`, `repeated-last-action=11`
  - experience model versions: `9=1052`, `0=422`
- this confirms the trainer can now audit live-policy rows separately from demo rows before choosing v18 source-mix ratios.

Validation:
- Python compile passed:
  - `python3 -m py_compile tools/train_dqn_learner.py`
- CPU-demo source diagnostics smoke passed:
  - `python3 tools/train_dqn_learner.py logs/rl-transitions-cpu-demo-schema-v3-4-3-3.ndjson logs/rl-transitions-human-demo-schema-v3-4-3-3.ndjson --model-dir /tmp/rl-dqn-source-diag-smoke --model-version 1 --limit 1200 --steps 2 --batch-size 16 --hidden-sizes 8 --actions forward,back,guard-stand,guard-crouch,stand-mk,crouch-hp,fireball-lp,fireball-mp,fireball-hp --fallback-policy stand-mk --training-action-source auto --reward-risk-profile none --engine-outcome-training-mode prefer-engine-action --engine-outcome-window-decisions 15 --engine-outcome-action-windows fireball-lp=45,fireball-mp=45,fireball-hp=45 --log-interval 1 --eval-limit 200 --diagnostic-top-n 8`
  - reported `replay_sources=rows:cpu-demo:1200/100.0% experiences:cpu-demo:236/100.0% row_model_versions:0:1200/100.0% experience_model_versions:0:236/100.0%`.
- live-v9 plus human-demo source diagnostics smoke passed:
  - `python3 tools/train_dqn_learner.py logs/rl-transitions-live-dqn-ground-specials-v9-4-3-3.ndjson logs/rl-transitions-human-demo-schema-v3-4-3-3.ndjson --model-dir /tmp/rl-dqn-source-diag-live-smoke --model-version 2 --limit 3000 --steps 2 --batch-size 16 --hidden-sizes 8 --actions forward,back,guard-stand,guard-crouch,stand-lp,stand-hk,crouch-hp,fireball-hp --fallback-policy stand-mk --training-action-source auto --reward-risk-profile none --engine-outcome-training-mode prefer-engine-action --engine-outcome-window-decisions 15 --log-interval 1 --eval-limit 200 --diagnostic-top-n 8`
  - reported live source rows at model version `9` and demo rows at model version `0`.
- metadata spot-check passed:
  - `jq '.metadata.source_replay_diagnostics | {row_counts, row_model_version_counts, experience_counts, experience_model_version_counts}' /tmp/rl-dqn-source-diag-live-smoke/current.json`

Follow-up:
- define the actual replay source mixing policy before v18 training, including source caps or ratios for `human-demo`, `cpu-demo`, `remote`, `repeated-last-action`, and `neutral-fallback`.
- do not treat `model_version_executed = 0` demo rows as a model quality signal; version `0` means no remote actor produced that action.

## 2026-04-30: Add Double DQN Target Mode And Train V17

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / DQN sparse-action overestimation control

Files changed:
- `tools/train_dqn_learner.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- test whether Double DQN target construction reduces the ground-specials sparse-action overestimation seen in v9/v11/v16.
- keep the experiment clean by using the v9 training recipe and changing only the DQN bootstrapping target mode.

Implementation notes:
- added `--dqn-target-mode standard|double` to `tools/train_dqn_learner.py`.
- `standard` remains the default and preserves the previous target:
  - `target = reward + gamma * max_a Q_target(next_state, a)`
- `double` selects the next action with the online network and evaluates it with the target network:
  - `best_next_action = argmax_a Q_online(next_state, a)`
  - `target = reward + gamma * Q_target(next_state, best_next_action)`
- published model metadata now records:
  - `dqn_target_mode`
  - `target_sync_steps`
- trained `model/dqn-mixdemo-schema-v3-ground-specials-v17` with the v9 recipe plus `--dqn-target-mode double`:
  - fresh schema-v3 CPU-demo + human-demo logs
  - `3000` steps, batch size `64`, `gamma=0.9`, learning rate `0.001`, target sync `200`
  - 27-action ground-specials action set
  - `all-attacks` risk profile
  - spacing and guard shaping matching v9
  - engine-outcome replay matching v9
  - no conservative action penalty
- v17 metadata confirms `dqn_target_mode=double` and `target_sync_steps=200`.

Result:
- v17 trained successfully, but the policy surface is effectively unchanged from v9.
- saved `5000`-row eval distribution:
  - v17: `stand-lp=26.72%`, `crouch-hp=26.16%`, `fireball-hp=25.10%`, `stand-hk=19.44%`, `guard-crouch=2.00%`
  - this matches the v9 metadata distribution to practical precision.
- same-observation compare over `5000` rows:
  - v9: `stand-lp=36.3%`, `fireball-hp=27.5%`, `crouch-hp=24.0%`, `stand-hk=9.3%`, `guard-crouch=1.7%`
  - v17: `stand-lp=36.3%`, `fireball-hp=27.4%`, `crouch-hp=24.0%`, `stand-hk=9.3%`, `guard-crouch=1.7%`
  - `COMPARE v9 -> v17 changed=1/5000`
- conclusion:
  - Double DQN support is useful to keep as an opt-in trainer mode.
  - v17 should not replace v9 for live testing on offline evidence alone.
  - the current sparse-action issue is not solved by Double DQN under the v9 recipe.
  - next control should be inference-time reranking / action-support priors, or another explicit target-value control, not more conservative reward penalty tuning.

Validation:
- Python compile passed:
  - `python3 -m py_compile tools/train_dqn_learner.py`
- standard-target smoke passed:
  - `python3 tools/train_dqn_learner.py logs/rl-transitions-cpu-demo-schema-v3-4-3-3.ndjson --model-dir /tmp/rl-dqn-target-standard-smoke --model-version 1 --limit 800 --steps 2 --batch-size 8 --hidden-sizes 8 --actions forward,back,guard-stand,guard-crouch,stand-mk,fireball-lp,fireball-mp,fireball-hp,shoryuken-hp --fallback-policy stand-mk --training-action-source auto --reward-risk-profile none --engine-outcome-training-mode prefer-engine-action --engine-outcome-window-decisions 15 --engine-outcome-action-windows fireball-lp=45,fireball-mp=45,fireball-hp=45 --dqn-target-mode standard --log-interval 1 --eval-limit 100 --diagnostic-top-n 8`
  - reported `target_mode=standard` and published version `1`.
- double-target smoke passed:
  - `python3 tools/train_dqn_learner.py logs/rl-transitions-cpu-demo-schema-v3-4-3-3.ndjson --model-dir /tmp/rl-dqn-target-double-smoke --model-version 2 --limit 800 --steps 2 --batch-size 8 --hidden-sizes 8 --actions forward,back,guard-stand,guard-crouch,stand-mk,fireball-lp,fireball-mp,fireball-hp,shoryuken-hp --fallback-policy stand-mk --training-action-source auto --reward-risk-profile none --engine-outcome-training-mode prefer-engine-action --engine-outcome-window-decisions 15 --engine-outcome-action-windows fireball-lp=45,fireball-mp=45,fireball-hp=45 --dqn-target-mode double --log-interval 1 --eval-limit 100 --diagnostic-top-n 8`
  - reported `target_mode=double` and published version `2`.
- full v17 training passed:
  - `python3 tools/train_dqn_learner.py logs/rl-transitions-cpu-demo-schema-v3-4-3-3.ndjson logs/rl-transitions-human-demo-schema-v3-4-3-3.ndjson --model-dir model/dqn-mixdemo-schema-v3-ground-specials-v17 --model-version 17 --steps 3000 --batch-size 64 --gamma 0.9 --learning-rate 0.001 --target-sync-steps 200 --dqn-target-mode double --actions forward,back,guard-stand,guard-crouch,stand-lp,stand-mp,stand-hp,stand-lk,stand-mk,stand-hk,forward-hp,crouch-lp,crouch-mp,crouch-hp,crouch-lk,crouch-mk,crouch-hk,fireball-lp,fireball-mp,fireball-hp,throw,shoryuken-lp,shoryuken-mp,shoryuken-hp,tatsu-lk,tatsu-mk,tatsu-hk --fallback-policy stand-mk --training-action-source auto --reward-risk-profile all-attacks --reward-risk-window-decisions 15 --reward-attack-no-damage-cost 0.3 --reward-attack-punished-cost 1.0 --reward-shoryuken-no-damage-extra-cost 0.0 --reward-shoryuken-punished-extra-cost 0.5 --reward-jump-attack-no-damage-extra-cost 0.0 --reward-jump-attack-punished-extra-cost 0.0 --reward-guard-success-bonus 0.0 --reward-guard-success-window-decisions 6 --reward-guard-threat-max-dx 120 --reward-passive-guard-cost 0.3 --reward-far-guard-cost 0.5 --reward-spacing-target-min-dx 50 --reward-spacing-target-max-dx 120 --reward-spacing-improve-bonus 0.5 --reward-spacing-worsen-cost 0.2 --reward-spacing-maintain-bonus 0.1 --reward-spacing-threat-back-bonus 0.3 --engine-outcome-training-mode prefer-engine-action --engine-outcome-window-decisions 15 --engine-outcome-action-windows fireball-lp=45,fireball-mp=45,fireball-hp=45,tatsu-lk=25,tatsu-mk=25,tatsu-hk=25 --engine-outcome-hit-bonus 1.0 --engine-outcome-no-damage-cost 0.2 --engine-outcome-punished-cost 1.0 --engine-outcome-oversample 1 --engine-outcome-action-oversamples fireball-lp=10,fireball-mp=20,fireball-hp=8,shoryuken-lp=4,shoryuken-mp=6,shoryuken-hp=8,tatsu-lk=6,tatsu-mk=6,tatsu-hk=6 --batch-sampling balanced --balanced-batch-ratios movement=0.3,normal=0.3,special=0.4 --epsilon 0.05 --seed 7 --log-interval 500 --eval-limit 5000 --diagnostic-top-n 12`
  - reported `DQN published version=17`, `experiences=58719`, `target_mode=double`, and `loss=0.011467 avg_loss=0.011811`.
- same-observation compare passed:
  - `python3 tools/compare_dqn_models.py logs/rl-transitions-cpu-demo-schema-v3-4-3-3.ndjson logs/rl-transitions-human-demo-schema-v3-4-3-3.ndjson --model v9=model/dqn-mixdemo-schema-v3-ground-specials-v9 --model v11=model/dqn-mixdemo-schema-v3-ground-specials-v11 --model v16b=model/dqn-mixdemo-schema-v3-ground-specials-v16b --model v17=model/dqn-mixdemo-schema-v3-ground-specials-v17 --limit 5000 --top-n 8 --focus-actions crouch-hp,stand-mk,fireball-lp,fireball-mp,fireball-hp,guard-stand,guard-crouch --focus-rank-limit 3 --training-action-source auto`
  - reported `COMPARE v9 -> v17 changed=1/5000`.

Follow-up:
- treat v9 as the stronger live candidate than v17 unless a separate live run contradicts the offline comparison.
- implement an opt-in DQN inference reranker or action-support prior that can penalize low-support or context-inappropriate top actions without retraining.
- compare any reranked policy against v9/v17 on the same observation slice before live testing.

## 2026-04-30: Review V16 Conservative Penalty A/B Results

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / DQN sparse-action overestimation control

Files changed:
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- record the completed v16a/v16b conservative-penalty A/B review.
- decide whether the conservative penalty is enough to make the ground-specials DQN recipe a default.

Implementation notes:
- reviewed `model/dqn-mixdemo-schema-v3-ground-specials-v16a/current.json` and `model/dqn-mixdemo-schema-v3-ground-specials-v16b/current.json`.
- both models used the same fresh schema-v3 mixed CPU-demo + human-demo logs, `3000` steps, balanced batch sampling, `all-attacks` risk shaping, engine-outcome oversampling, and the same 27-action ground-specials action set.
- v16a conservative config:
  - `action_penalty=0.3`, `min_action_count=300`, `negative_mean_extra=0.2`
  - scaled conservative cost: `14.943`
- v16b conservative config:
  - `action_penalty=1.0`, `min_action_count=1000`, `negative_mean_extra=1.0`
  - scaled conservative cost: `96.3`
- metadata-level greedy comparison over the saved `5000` eval rows:
  - v9 no-penalty baseline: top `stand-lp=26.72%`, `crouch-hp=26.16%`, `fireball-hp=25.10%`, `stand-hk=19.44%`, `guard-crouch=2.00%`
  - v11 no-penalty baseline: top `stand-lp=26.48%`, `crouch-hp=26.26%`, `fireball-hp=25.14%`, `stand-hk=19.54%`, `guard-crouch=2.00%`
  - v16a: top `crouch-hp=26.62%`, `stand-lp=25.72%`, `fireball-hp=25.42%`, `stand-hk=19.62%`, `guard-crouch=2.02%`
  - v16b: top `crouch-hp=27.92%`, `fireball-hp=26.52%`, `stand-lp=22.58%`, `stand-hk=20.24%`, `guard-crouch=2.02%`
- same-slice `compare_dqn_models.py --limit 5000` comparison:
  - v9: `stand-lp=36.3%`, `fireball-hp=27.5%`, `crouch-hp=24.0%`, `stand-hk=9.3%`, `guard-crouch=1.7%`
  - v11: `stand-lp=36.0%`, `fireball-hp=27.6%`, `crouch-hp=24.1%`, `stand-hk=9.3%`, `guard-crouch=1.7%`
  - v16a: `stand-lp=35.4%`, `fireball-hp=28.1%`, `crouch-hp=24.2%`, `stand-hk=9.4%`, `guard-crouch=1.7%`
  - v16b: `stand-lp=31.4%`, `fireball-hp=30.5%`, `crouch-hp=25.1%`, `stand-hk=9.5%`, `guard-crouch=1.7%`
  - v9 -> v16a changed only `47/5000` rows; v9 -> v16b changed `263/5000` rows.
- conclusion:
  - conservative penalty does not create a new guard collapse; `guard-crouch` stays near `1.7%` on the same-slice compare and near `2%` in saved metadata.
  - it also does not create an LP/MP fireball collapse; `fireball-lp` remains `0%` top1 and `fireball-mp` remains negligible.
  - the stronger v16b setting mostly shifts probability away from `stand-lp` into `fireball-hp` and `crouch-hp`.
  - `stand-mk` is not the active collapse in this run; it is `0%` top1 across the compared ground-specials models.
  - v16a/v16b should not become the default recipe yet; sparse-action overestimation remains, with `crouch-hp`, `stand-lp`, `stand-hk`, and `fireball-hp` still dominating the policy surface.
- marked the conservative-penalty A/B checklist item complete, but kept the Double DQN / inference-reranking review open.

Validation:
- metadata summary passed:
  - `jq` summaries over v9, v11, v12, v16a, and v16b actor metadata.
- same-observation compare passed:
  - `python3 tools/compare_dqn_models.py logs/rl-transitions-cpu-demo-schema-v3-4-3-3.ndjson logs/rl-transitions-human-demo-schema-v3-4-3-3.ndjson --model v9=model/dqn-mixdemo-schema-v3-ground-specials-v9 --model v11=model/dqn-mixdemo-schema-v3-ground-specials-v11 --model v16a=model/dqn-mixdemo-schema-v3-ground-specials-v16a --model v16b=model/dqn-mixdemo-schema-v3-ground-specials-v16b --limit 5000 --top-n 8 --focus-actions crouch-hp,stand-mk,fireball-lp,fireball-mp,fireball-hp,guard-stand,guard-crouch --focus-rank-limit 3 --training-action-source auto`
  - reported `COMPARE v9 -> v16a changed=47/5000` and `COMPARE v9 -> v16b changed=263/5000`.

Follow-up:
- keep conservative penalty opt-in rather than default for now.
- review Double DQN, clipped target values, or inference-time reranking / priors as the next sparse-action-overestimation control.
- avoid further tuning that only shifts collapse among `stand-lp`, `stand-hk`, `crouch-hp`, and `fireball-hp` without adding a clearer action-support prior or target-value correction.

## 2026-04-30: Validate Fresh Transition Schema V3 Demo Logs

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / transition action-label cleanup

Files changed:
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- record that fresh schema-v3 CPU-demo and human-demo transition logs are valid enough to use as the next retraining baseline.
- close the post-schema-v3 validation checklist item before long-run DQN retraining.

Implementation notes:
- telemetry build, deployment, CPU-demo collection, human-demo collection, and first-pass validation were completed before this documentation sync.
- validated `logs/rl-transitions-cpu-demo-schema-v3-4-3-3.ndjson`:
  - rows: `122276`
  - schema versions: `{3: 122276}`
  - demo policy rows: `policy_nonzero_rows=0`
  - analyzer source breakdown: `none:83991,input:36708,engine:1577`
  - engine labels include Ryu Hadouken, Shoryuken, Tatsumaki, throw, Shinkuu Hadouken, crouch normals, Joudan, and jump attacks.
  - input labels include guard, walk/back, jump, normals, and throw intent.
- validated `logs/rl-transitions-human-demo-schema-v3-4-3-3.ndjson`:
  - rows: `18849`
  - schema versions: `{3: 18849}`
  - demo policy rows: `policy_nonzero_rows=0`
  - analyzer source breakdown: `input:9682,none:8697,engine:470`
  - engine labels include Ryu Hadouken, Shoryuken, Tatsumaki, throw, Shinkuu Hadouken, normals, and jump attacks.
  - input labels include walk/back, stand/crouch normals, guard, jump, throw, and back-jump attack intent.
- marked the Milestone 6 schema-v3 fresh-log validation checklist item complete.

Validation:
- CPU-demo analyzer passed:
  - `python3 tools/analyze_rl_transitions.py logs/rl-transitions-cpu-demo-schema-v3-4-3-3.ndjson --training-action-source auto --limit 12`
  - reported `action_label_source training_action_source=auto counts=none:83991,input:36708,engine:1577`.
  - reported `ENGINE_OUTCOME_SUMMARY ... events=1577`.
- human-demo analyzer passed:
  - `python3 tools/analyze_rl_transitions.py logs/rl-transitions-human-demo-schema-v3-4-3-3.ndjson --training-action-source auto --limit 12`
  - reported `action_label_source training_action_source=auto counts=input:9682,none:8697,engine:470`.
  - reported `ENGINE_OUTCOME_SUMMARY ... events=470`.
- direct schema / policy-family check passed:
  - `python3 -c '<schema and action-label summary over CPU-demo and human-demo logs>'`
  - reported schema v3 only and `policy_nonzero_rows=0` for both demo logs.
- fresh CPU-demo DQN smoke passed:
  - `python3 tools/train_dqn_learner.py logs/rl-transitions-cpu-demo-schema-v3-4-3-3.ndjson --model-dir /tmp/rl-dqn-fresh-schema-v3-smoke --model-version 16 --limit 1200 --steps 2 --batch-size 16 --hidden-sizes 8 --actions forward,back,guard-stand,guard-crouch,stand-mk,crouch-hp,fireball-lp,fireball-mp,fireball-hp,shoryuken-hp --fallback-policy stand-mk --training-action-source auto --reward-risk-profile none --engine-outcome-training-mode prefer-engine-action --engine-outcome-window-decisions 15 --engine-outcome-action-windows fireball-lp=45,fireball-mp=45,fireball-hp=45 --log-interval 1 --eval-limit 200 --diagnostic-top-n 10`
  - reported `DQN published version=16`, `experiences=237`, `engine_outcome=prefer-engine-action:16/24`, `included=221 excluded=21`, and `engine_input_fallback=8`.
  - smoke emitted a greedy collapse warning for `fireball-lp 80.5%`; this is a policy-quality signal for later A/B work, not a schema validation blocker.

Follow-up:
- use only fresh schema-v3 logs for the next long-run DQN retraining pass.
- run the planned v16-style ground-specials conservative-penalty A/B comparison.
- define replay-buffer mixing metadata for human-demo, CPU-demo, and remote-agent episodes before treating mixed replay import as settled.

## 2026-04-29: Add Conservative Action Penalty Plan And Trainer Flags

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / DQN sparse-action overestimation control

Files changed:
- `tools/train_dqn_learner.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- make sparse-action overestimation an explicit A/B path after v11-v15 showed that pure command tuning shifts collapse between `crouch-hp`, `stand-mk`, `throw`, and fireball variants instead of solving it.
- add a small opt-in trainer-side regularization step without changing transition schema, C-side logging, OBS payloads, or live DQN inference.

Implementation notes:
- recorded the support-aware conservative DQN penalty rollout plan in `docs/plan-remote-rl-agent.md`.
- added `--conservative-action-penalty` and `--conservative-min-action-count`:
  - after replay building, actions with fewer than the configured post-build training examples receive a raw reward cost on each replay experience.
- added `--conservative-negative-mean-extra`:
  - actions with non-positive observed mean reward receive an additional raw reward cost.
  - if no observed rows exist for an action, the post-build training mean is used.
- added `--conservative-exempt-actions` so engine-labeled specials or other trusted curriculum actions can be excluded from the checks.
- conservative penalties run after engine-outcome delayed credit, HP-delta consumption, macro-continuation credit, and all other reward shaping, then update the replay experiences and action reward diagnostics.
- stdout and model metadata now record `conservative_penalty` diagnostics with adjusted experience count, raw/scaled cost, low-count actions, non-positive-mean actions, and per-action cost totals.

Validation:
- Python compile passed:
  - `python3 -m py_compile tools/train_dqn_learner.py`
- diff whitespace check passed:
  - `git diff --check -- tools/train_dqn_learner.py docs/plan-remote-rl-agent.md`
- conservative penalty smoke passed:
  - `python3 tools/train_dqn_learner.py logs/rl-transitions-cpu-demo-schema-v3-4-3-3.ndjson --model-dir /tmp/rl-dqn-conservative-smoke --model-version 1 --limit 1200 --steps 2 --batch-size 16 --hidden-sizes 8 --actions forward,back,guard-stand,guard-crouch,stand-mk,crouch-hp,fireball-lp,fireball-mp,fireball-hp,shoryuken-hp --fallback-policy stand-mk --training-action-source auto --reward-risk-profile all-attacks --reward-risk-window-decisions 15 --reward-risk-action-windows fireball-lp=45,fireball-mp=45,fireball-hp=45 --reward-attack-no-damage-cost 0.3 --reward-attack-punished-cost 1.0 --engine-outcome-training-mode prefer-engine-action --engine-outcome-window-decisions 15 --engine-outcome-action-windows fireball-lp=45,fireball-mp=45,fireball-hp=45 --engine-outcome-hit-bonus 1.0 --engine-outcome-no-damage-cost 0.2 --engine-outcome-punished-cost 1.0 --conservative-action-penalty 0.2 --conservative-min-action-count 10 --conservative-negative-mean-extra 0.1 --conservative-exempt-actions fireball-lp,fireball-mp,fireball-hp,shoryuken-hp --log-interval 1 --eval-limit 200 --diagnostic-top-n 10`
  - diagnostics reported `conservative_penalty=events:99 raw_cost:10.7 scaled_cost:0.107`, with low-count penalties applied to `stand-mk,crouch-hp`.

Follow-up:
- train a v16-style ground-specials model from the v9/v11 command family with conservative penalties enabled.
- compare whether `crouch-hp`, `stand-lp`, `stand-hk`, and `stand-mk` top1/top3 rates drop without creating a new `guard` / `fireball` collapse.

## 2026-04-29: Record Anti-Air Shoryuken Feature Plan

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / DQN anti-air behavior

Files changed:
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- capture the plan for teaching DQN to use Shoryuken as an anti-air against opponent jump-ins.
- avoid a misleading shortcut where raw routine ids are added only to training logs, or a large global engine hit bonus accidentally buffs every special / normal hit instead of specifically teaching anti-air.

Decision notes:
- current DQN feature vectors still use compact numeric spacing/threat fields and do not include `obs_opp_routine_1` / `obs_opp_routine_2`.
- future anti-air learner visibility should prefer derived, schema-versioned features such as `obs_opp_airborne`, `obs_opp_jump_toward`, `obs_opp_above_self`, and `obs_anti_air_threat`.
- train and live inference must receive the same OBS payload fields before any model is trained with those features; transition-log-only fields would create train/live mismatch.
- reward shaping should use a targeted anti-air Shoryuken bonus rather than a large global `--engine-outcome-hit-bonus`, so fireball / tatsu / throw / normal hits are not all boosted at the same time.

Follow-up:
- validate opponent jump-in routine states with fresh schema-v3 logs and analyzer summaries.
- bump the compact OBS payload schema when the derived anti-air fields are promoted.
- collect a focused human-demo anti-air Shoryuken log before expecting offline DQN to learn reliable jump-in punishment.
- add compare diagnostics for Shoryuken rank/top-k specifically when `obs_anti_air_threat=1`.

## 2026-04-29: Add Balanced Batch Sampling For Offline DQN

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / DQN action distribution experiments

Files changed:
- `tools/train_dqn_learner.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- prevent high-frequency movement / guard rows from dominating every offline DQN gradient batch.
- give low-frequency but learner-important action families such as fireball / shoryuken / tatsu a stable per-batch presence without further changing raw replay logs.

Implementation notes:
- added `--batch-sampling uniform|balanced`; `uniform` preserves historical random replay sampling.
- added `--balanced-batch-ratios movement=0.4,normal=0.3,special=0.3` for action-family batch targets.
- action-family grouping is:
  - movement: `forward`, `back`, `guard-stand`, `guard-crouch`
  - normal: normals and `throw`
  - special: `fireball-*`, `shoryuken-*`, `tatsu-*`
- stdout and model metadata now include `batch_sampling` diagnostics with ratios, target counts, and replay pool counts.

Validation:
- Python compile passed:
  - `python3 -m py_compile tools/train_dqn_learner.py`
- uniform smoke preserved baseline sampler behavior:
  - `python3 tools/train_dqn_learner.py logs/rl-transitions-cpu-demo-schema-v3-4-3-3.ndjson --model-dir /tmp/rl-dqn-balanced-uniform-smoke --model-version 12 --limit 800 --steps 2 --batch-size 4 --hidden-sizes 8 --actions forward,back,guard-stand,guard-crouch,stand-mk,fireball-lp,fireball-mp,fireball-hp,shoryuken-lp,tatsu-hk --fallback-policy stand-mk --training-action-source auto --reward-risk-profile none --engine-outcome-training-mode prefer-engine-action --engine-outcome-window-decisions 15 --engine-outcome-action-windows fireball-lp=45,fireball-mp=45,fireball-hp=45 --engine-outcome-no-damage-cost 0.5 --engine-outcome-punished-cost 2.0 --log-interval 1 --eval-limit 100 --diagnostic-top-n 10`
  - reported `batch_sampling=mode:uniform` and zero target counts.
- balanced smoke confirmed family target counts:
  - same smoke shape with `--batch-size 64 --engine-outcome-oversample 1 --engine-outcome-action-oversamples fireball-lp=5,fireball-mp=5,fireball-hp=5,shoryuken-lp=4,tatsu-hk=4 --batch-sampling balanced --balanced-batch-ratios movement=0.4,normal=0.3,special=0.3`
  - reported `batch_sampling=mode:balanced`, `target:movement:26,normal:19,special:19`, and pools `movement:136,normal:1,special:72`.

Follow-up:
- train `model/dqn-mixdemo-schema-v3-ground-specials-v6` with ground + specials actions, specials oversampling, and balanced batch sampling; compare fireball top2/top3 against v5.

## 2026-04-29: Add Engine Outcome Oversampling For Offline DQN

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / DQN action distribution experiments

Files changed:
- `tools/train_dqn_learner.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- make low-frequency engine-labeled moves, especially Ryu fireballs and specials, easier to A/B test without recollecting logs.
- keep raw transition logs and normal input replay rows unchanged while allowing included engine-outcome experiences to be duplicated in the DQN replay set.

Implementation notes:
- added `--engine-outcome-oversample N`, where `1` preserves the previous one-experience-per-event behavior.
- added `--engine-outcome-action-oversamples action=N,...` for per-action replay copy counts.
- engine outcome diagnostics now record `training_experiences`, `oversample_extra_experiences`, and `training_scaled_reward_sum`; action count/reward diagnostics reflect the replay distribution after oversampling.

Validation:
- Python compile passed:
  - `python3 -m py_compile tools/train_dqn_learner.py`
- baseline oversampling smoke passed:
  - `python3 tools/train_dqn_learner.py logs/rl-transitions-cpu-demo-schema-v3-4-3-3.ndjson --model-dir /tmp/rl-dqn-engine-oversample-baseline-smoke --model-version 11 --limit 800 --steps 2 --batch-size 4 --hidden-sizes 8 --actions forward,back,guard-stand,guard-crouch,stand-mk,fireball-lp,fireball-mp,fireball-hp,shoryuken-lp,tatsu-hk --fallback-policy stand-mk --training-action-source auto --reward-risk-profile none --engine-outcome-training-mode prefer-engine-action --engine-outcome-window-decisions 15 --engine-outcome-action-windows fireball-lp=45,fireball-mp=45,fireball-hp=45 --engine-outcome-no-damage-cost 0.5 --engine-outcome-punished-cost 2.0 --log-interval 1 --eval-limit 100 --diagnostic-top-n 10`
  - reported `engine_oversample=15/+0`, preserving the default one-copy behavior.
- specials oversampling smoke passed:
  - same smoke command plus `--engine-outcome-oversample 2 --engine-outcome-action-oversamples fireball-lp=5,fireball-mp=5,fireball-hp=5,shoryuken-lp=4,tatsu-hk=4`
  - reported `engine_oversample=72/+57`; `fireball-hp` count rose from `6` to `30`, `fireball-mp` from `3` to `15`, and `fireball-lp` from `3` to `15`.
- mixed full-action smoke passed:
  - first `5000` rows from CPU-demo + human-demo with full action set and specials oversampling reported `engine_outcome=prefer-engine-action:64/73`, `engine_oversample=424/+360`, `excluded=0`, and `engine_input_fallback=9`.

Follow-up:
- run a mixed CPU-demo + human-demo all-action v4 train with specials oversampling and compare focus ranks for `fireball-lp`, `fireball-mp`, and `fireball-hp` against v3.

## 2026-04-29: Fix Engine Outcome Subset Fallback

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / schema-v3 trainer cleanup

Files changed:
- `tools/train_dqn_learner.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- fix `--engine-outcome-training-mode prefer-engine-action` when an engine-labeled move exists but the action is not present in the configured DQN action subset.
- preserve input-labeled demo rows instead of allowing `--training-action-source auto` to select the same unsupported `engine_*` action a second time.

Implementation notes:
- when engine outcome experience creation fails for a demo row with `engine_*`, the trainer now forces that row's normal replay path through `select_training_action(row, "input")`.
- `BuildDiagnostics` now records `engine_outcome_input_fallback_rows`.
- the published summary line now prints `engine_input_fallback=<n>`.

Validation:
- Python compile passed:
  - `python3 -m py_compile tools/train_dqn_learner.py`
- subset fallback smoke passed:
  - `python3 tools/train_dqn_learner.py logs/rl-transitions-cpu-demo-schema-v3-4-3-3.ndjson --model-dir /tmp/rl-dqn-engine-fallback-smoke --model-version 10 --limit 800 --steps 2 --batch-size 4 --hidden-sizes 8 --actions forward,back,guard-stand,guard-crouch,stand-mk --fallback-policy stand-mk --training-action-source auto --reward-risk-profile none --engine-outcome-training-mode prefer-engine-action --engine-outcome-window-decisions 15 --log-interval 1 --eval-limit 100 --diagnostic-top-n 8`
  - reported `engine_input_fallback=17` and `action_source_counts=input:164,none:636`, confirming excluded engine events no longer return as normal engine-source exclusions.
- full-action smoke on the current CPU-demo schema-v3 log passed:
  - `python3 tools/train_dqn_learner.py logs/rl-transitions-cpu-demo-schema-v3-4-3-3.ndjson --model-dir /tmp/rl-dqn-engine-fallback-full-smoke --model-version 10 --steps 2 --batch-size 64 --hidden-sizes 8 --epsilon 0.05 --seed 7 --gamma 0.95 --actions forward,back,guard-stand,guard-crouch,stand-lp,stand-mp,stand-hp,stand-lk,stand-mk,stand-hk,forward-hp,crouch-lp,crouch-mp,crouch-hp,crouch-lk,crouch-mk,crouch-hk,fireball-lp,fireball-mp,fireball-hp,throw,jump-forward-lp,jump-forward-mp,jump-forward-hp,jump-forward-lk,jump-forward-mk,jump-forward-hk,jump-neutral-lp,jump-neutral-mp,jump-neutral-hp,jump-neutral-lk,jump-neutral-mk,jump-neutral-hk,jump-back-lp,jump-back-mp,jump-back-hp,jump-back-lk,jump-back-mk,jump-back-hk,shoryuken-lp,shoryuken-mp,shoryuken-hp,tatsu-lk,tatsu-mk,tatsu-hk --fallback-policy stand-mk --training-action-source auto --reward-risk-profile none --engine-outcome-training-mode prefer-engine-action --engine-outcome-window-decisions 15 --engine-outcome-action-windows fireball-lp=45,fireball-mp=45,fireball-hp=45,tatsu-lk=25,tatsu-mk=25,tatsu-hk=25 --engine-outcome-no-damage-cost 0.5 --engine-outcome-punished-cost 2.0 --log-interval 1 --eval-limit 100 --diagnostic-top-n 10`
  - reported `engine_outcome=prefer-engine-action:251/291`, `excluded=0`, and `engine_input_fallback=40`.

Follow-up:
- retrain the CPU-demo schema-v3 DQN model with model version +1 so the live model benefits from the fallback fix.

## 2026-04-29: Rename DQN Demo Attribution To Engine Outcome

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / schema-v3 trainer cleanup

Files changed:
- `tools/rl_probe_server.py`
- `tools/train_dqn_learner.py`
- `tools/analyze_rl_transitions.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- align DQN trainer/analyzer terminology with schema v3's `policy_*`, `input_*`, and `engine_*` label families.
- replace the confusing `demo-attribution` trainer concept with `engine-outcome`, because delayed outcome credit is based on observed `engine_*` move starts.
- remove the data-loss trap where an engine-labeled row whose action was not in the configured DQN `--actions` subset skipped the normal input fallback path.

Implementation notes:
- `tools/train_dqn_learner.py` now exposes:
  - `--engine-outcome-training-mode off|prefer-engine-action`
  - `--engine-outcome-window-decisions`
  - `--engine-outcome-action-windows`
  - `--engine-outcome-stop-at-next-event`
  - `--engine-outcome-hit-bonus`
  - `--engine-outcome-no-damage-cost`
  - `--engine-outcome-punished-cost`
- deprecated hidden aliases for the old `--demo-attribution-*` flags still map to the new engine-outcome config for short-term command compatibility and print a warning.
- schema-v2-era modes `augment` and `replace-demo` now fail fast; v3 training should use `prefer-engine-action`.
- `prefer-engine-action` now uses the engine outcome experience only when the engine-labeled action is present in the configured action subset; otherwise it records an excluded engine-outcome event and lets the row continue through the normal `--training-action-source auto` path.
- stdout and model metadata now use `engine_outcome=...` / `engine_outcome_stats` instead of `demo_attr=...` / `demo_attribution_stats`.
- `tools/analyze_rl_transitions.py` now uses `--engine-outcome-window-decisions` and `--engine-outcome-stop-at-next-event`; hidden old aliases remain for short-term compatibility.
- `tools/rl_probe_server.py` now provides `engine_outcome_present()` and `engine_outcome_action_name()` helpers over schema-v3 `engine_*` fields.

Validation:
- Python compile passed:
  - `python3 -m py_compile tools/train_dqn_learner.py tools/analyze_rl_transitions.py tools/rl_probe_server.py`
- help output shows the new engine-outcome trainer/analyzer flags.
- schema-v3 CPU-demo DQN smoke with engine outcome enabled passed:
  - `python3 tools/train_dqn_learner.py logs/rl-transitions-cpu-demo-schema-v3-4-3-3.ndjson --model-dir /tmp/rl-dqn-engine-outcome-smoke --model-version 9 --limit 800 --steps 2 --batch-size 4 --hidden-sizes 8 --actions forward,back,guard-stand,guard-crouch,stand-mk,fireball-lp,fireball-mp,fireball-hp,shoryuken-lp,tatsu-hk --fallback-policy stand-mk --training-action-source auto --reward-risk-profile none --engine-outcome-training-mode prefer-engine-action --engine-outcome-window-decisions 15 --engine-outcome-action-windows fireball-lp=45,fireball-mp=45,fireball-hp=45 --engine-outcome-no-damage-cost 0.5 --engine-outcome-punished-cost 2.0 --log-interval 1 --eval-limit 100 --diagnostic-top-n 8`
  - reported `engine_outcome=prefer-engine-action:15/17`.
- subset fallback smoke passed:
  - `python3 tools/train_dqn_learner.py logs/rl-transitions-cpu-demo-schema-v3-4-3-3.ndjson --model-dir /tmp/rl-dqn-engine-outcome-subset-smoke --model-version 9 --limit 800 --steps 2 --batch-size 4 --hidden-sizes 8 --actions forward,back,guard-stand,guard-crouch,stand-mk --fallback-policy stand-mk --training-action-source auto --reward-risk-profile none --engine-outcome-training-mode prefer-engine-action --engine-outcome-window-decisions 15 --log-interval 1 --eval-limit 100 --diagnostic-top-n 8`
  - reported `engine_outcome=prefer-engine-action:0/17` and still built `experiences=137`, proving excluded engine labels no longer discard input fallback rows.
- analyzer smoke passed:
  - `python3 tools/analyze_rl_transitions.py logs/rl-transitions-cpu-demo-schema-v3-4-3-3.ndjson --tail-rows 800 --engine-outcome-window-decisions 15 --limit 5`
  - reported `ENGINE_OUTCOME_SUMMARY ... events=12`.
- `git diff --check` passed.
- canonical MiSTer telemetry build passed:
  - `tools/mister/build-game.sh --flavor telemetry`

Follow-up:
- use only `--engine-outcome-*` flags in new train commands.
- after the next long CPU-demo run, compare `engine_outcome_stats.excluded_events` against the action subset to catch missing action names before live testing.

## 2026-04-29: Remove Hot-Path Local Transition File Writes

Milestone:
- Milestone 4: Decision ledger and transition logging / Milestone 6 demo-data collection performance follow-up

Files changed:
- `src/rl/rl_session.c`
- `docs/config.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- remove synchronous MiSTer local transition-log writes from the decision-finalization hot path.
- rely on the existing per-episode transition batch upload to the probe server for demo and remote-RL data collection.
- reduce human-demo FPS spikes caused by repeated SD/FAT `open -> write -> close` operations.

Implementation notes:
- removed `RLSession_AppendTransitionLogLine()`.
- `RLSession_FinalizeLedgerEntry()` now formats each NDJSON row once and appends it only to the in-memory episode batch.
- episode-close still calls `RLNet_QueueTransitionBatch()` so the probe server receives the same rows over the existing TCP transition port.
- local MiSTer fallback file persistence is intentionally gone; if the probe server is not running or `rl-network = off`, transition rows are not persisted locally.

Validation:
- `rg -n 'AppendTransitionLogLine|SDL_IOFromFile\(log_path|rl-transitions\.ndjson' src/rl/rl_session.c docs/config.md docs/plan-remote-rl-agent.md` confirmed no runtime local append path remains in `src/rl/rl_session.c`.
- `git diff --check` passed.
- canonical telemetry build passed:
  - `tools/mister/build-game.sh --flavor telemetry`

Follow-up:
- deploy the telemetry package and collect a human-demo log through probe-server `--transition-log`; check FPS stability and transition batch counters `TBQ/TBS/TBA/TBF`.
- if long episodes still show spikes, profile `RLSession_FormatTransitionLogLine()` and transition batch `SDL_realloc` growth next.

## 2026-04-29: Strict Transition Schema V3 Cleanup

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / transition action-label cleanup

Files changed:
- `src/rl/rl_session.c`
- `tools/rl_probe_server.py`
- `tools/train_dqn_learner.py`
- `tools/analyze_rl_transitions.py`
- `tools/compare_dqn_models.py`
- `docs/rl-policy-action-taxonomy.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- remove legacy transition action-label fields now that old transition logs have been cleared.
- make schema v3 rows carry only the explicit `policy_*`, `input_*`, and `engine_*` action-label families.
- make Python replay/training/analyzer tools fail fast on schema 1/2 instead of guessing legacy semantics.

Implementation notes:
- C-side transition export now stamps `transition_schema_version=3`.
- C-side NDJSON no longer emits:
  - `requested_policy_action_id`
  - `requested_policy_sub_action_id`
  - `requested_policy_action_step`
  - `executed_policy_action_id`
  - `executed_policy_sub_action_id`
  - `executed_policy_action_step`
  - `demo_attributed_policy_action_id`
  - `demo_attributed_policy_sub_action_id`
  - `demo_attributed_routine2`
  - `demo_attributed_kind_of_waza`
  - `demo_attributed_current_attack`
  - `demo_attribution_source`
  - `demo_attribution_lag_frames`
- demo engine attribution now writes only `engine_*`; demo input labels continue to use `input_*`; remote RL policy rows continue to use `policy_*`.
- `tools/rl_probe_server.py` now defines `TRANSITION_SCHEMA_VERSION = 3`, requires schema v3 in replay normalization and action selection, and no longer has legacy action/wire fallback paths.
- `tools/train_dqn_learner.py` action-start gating now uses `input_action_step` for demo rows and `policy_executed_action_step` for remote rows.
- analyzer / compare diagnostics now report strict v3 label sources only (`policy`, `input`, `engine`, `none`).

Validation:
- `python3 -m py_compile tools/rl_probe_server.py tools/train_dqn_learner.py tools/analyze_rl_transitions.py tools/compare_dqn_models.py` passed.
- `git diff --check` passed.
- synthetic v3 analyzer smoke passed:
  - `python3 tools/analyze_rl_transitions.py /tmp/rl-transitions-schema-v3-smoke.ndjson --training-action-source auto --limit 12`
  - reported `action_label_source training_action_source=auto counts=none:3,engine:1`.
- synthetic v3 DQN smoke passed:
  - `python3 tools/train_dqn_learner.py /tmp/rl-transitions-schema-v3-smoke.ndjson --model-dir /tmp/rl-dqn-schema-v3-smoke --model-version 3 --steps 2 --batch-size 2 --hidden-sizes 8 --actions forward,guard-stand,fireball-lp --fallback-policy stand-mk --training-action-source auto --reward-risk-profile none --demo-attribution-training-mode prefer-demo-action --demo-attribution-window-decisions 15 --log-interval 1 --eval-limit 4 --diagnostic-top-n 5`
  - reported `demo_attr=prefer-demo-action:1/1`.
- synthetic v3 compare smoke passed:
  - `python3 tools/compare_dqn_models.py /tmp/rl-transitions-schema-v3-smoke.ndjson --model SMOKE=/tmp/rl-dqn-schema-v3-smoke --tail-rows 4 --top-n 5 --focus-actions fireball-lp`
  - reported `LOG_ACTION_SOURCE ... counts=none:3,engine:1`.
- strict schema rejection passed:
  - `python3 tools/analyze_rl_transitions.py /tmp/rl-transitions-schema-v2-reject.ndjson`
  - failed with `transition_schema_version=2 expected=3`.
- canonical MiSTer telemetry build passed:
  - `tools/mister/build-game.sh --flavor telemetry`

Follow-up:
- deploy the new telemetry package and collect fresh schema-v3 `cpu-demo` and `human-demo` logs.
- verify demo logs have `policy_* == 0`, engine-attributed specials in `engine_*`, and walk/back/guard intent in `input_*`.
- use only fresh v3 logs for the next long-run DQN retraining pass.

## 2026-04-29: Transition Schema V2 Analyzer Source Breakdown Step 4

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / transition action-label cleanup

Files changed:
- `tools/rl_probe_server.py`
- `tools/train_dqn_learner.py`
- `tools/analyze_rl_transitions.py`
- `tools/compare_dqn_models.py`
- `docs/rl-policy-action-taxonomy.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- make training, analysis, and comparison use the same canonical action-label source selector.
- expose label-source counts so schema-v2 logs can be checked before long-run retraining.

Implementation notes:
- moved the DQN action selector into `tools/rl_probe_server.py` as shared helpers:
  - `select_training_action(row, source_mode)`
  - `demo_attribution_present(row)`
  - `demo_attributed_action_name(row)`
  - `action_name_from_policy_meta(action_id, sub_action_id)`
- `tools/train_dqn_learner.py` now calls the shared selector instead of carrying a private copy.
- `tools/analyze_rl_transitions.py` now accepts `--training-action-source` and prints `action_label_source` counts plus top actions per source.
- `tools/compare_dqn_models.py` now accepts `--training-action-source` and prints a `LOG_ACTION_SOURCE` summary before model greedy-action output.
- schema-v1 logs continue to report `legacy`; schema-v2 logs should report `policy`, `input`, `engine`, `engine-legacy`, or `none` depending on selected mode and row contents.

Validation:
- `python3 -m py_compile tools/rl_probe_server.py tools/train_dqn_learner.py tools/analyze_rl_transitions.py tools/compare_dqn_models.py` passed.
- selector smoke passed:
  - schema-v2 demo row with engine/input/policy labels selected `fireball-hp` under `auto`, `guard-crouch` under `input`, and `stand-mp` under `policy`.
  - schema-v1 row selected legacy `guard-crouch` under `auto`.
- analyzer smoke on `logs/rl-transitions-cpu-demo-r12-v1-4-3-3.ndjson` printed `action_label_source training_action_source=auto counts=legacy:200`.
- compare smoke on the same log printed `LOG_ACTION_SOURCE training_action_source=auto rows=200 counts=legacy:200`.
- one-step DQN smoke still printed `action_source_counts=legacy:200`.
- `git diff --check` passed.

Follow-up:
- deploy / run a fresh schema-v2 mixed remote + CPU-demo log and confirm:
  - remote rows use `policy`.
  - CPU-demo specials use `engine`.
  - CPU-demo walk / guard rows use `input`.
  - rows without a usable label use `none` rather than a misleading legacy label.

## 2026-04-29: Transition Schema V2 DQN Action Source Step 3

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / transition action-label cleanup

Files changed:
- `tools/train_dqn_learner.py`
- `docs/rl-policy-action-taxonomy.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- let offline DQN replay choose the action-label source explicitly after schema-v2 rows split policy, input, and engine identities.
- keep default behavior compatible with old schema-v1 logs while enabling schema-v2 logs to use cleaner demo and remote labels.

Implementation notes:
- added `--training-action-source auto|policy|input|engine|prefer-engine`.
- default `auto` behavior:
  - schema-v2 demo row: use `engine_*` when present, otherwise `input_*`.
  - schema-v2 non-demo row: use `policy_executed_*`.
  - schema-v1 row: keep legacy `executed_policy_*` / wire fallback behavior.
- explicit `engine` can train from v2 `engine_*` and falls back to legacy `demo_attributed_*` for older logs.
- explicit `prefer-engine` uses engine first, then input, then policy, with schema-v1 legacy fallback.
- demo-attribution delayed-credit logic now treats v2 `engine_*` attribution as present and uses it before legacy `demo_attributed_*`.
- DQN metadata and stdout now include `training_action_source` and `action_source_counts`.

Validation:
- `python3 -m py_compile tools/train_dqn_learner.py` passed.
- targeted selector smoke passed:
  - schema-v2 demo row with engine/input/policy labels selected `fireball-hp` under `auto`, `guard-crouch` under `input`, and `stand-mp` under `policy`.
  - schema-v1 row selected legacy `guard-crouch` under `auto`.
- schema-v2 `build_experiences()` smoke passed and produced `action_source_counts={'engine': 1, 'policy': 1}` for a two-row mixed demo/remote sample.
- one-step DQN smoke on `logs/rl-transitions-cpu-demo-r12-v1-4-3-3.ndjson` passed with `--training-action-source auto`; because this is a schema-v1 log, diagnostics correctly printed `action_source_counts=legacy:200`.
- `git diff --check` passed.

Follow-up:
- update analyzer / compare tools to report label-source breakdown.
- collect a fresh schema-v2 mixed remote + CPU-demo log after deploying the new C-side build, then validate source counts before long-run retraining.

## 2026-04-29: Transition Schema V2 Python Replay Ingestion Step 2

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / transition action-label cleanup

Files changed:
- `tools/rl_probe_server.py`
- `docs/rl-policy-action-taxonomy.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- make Python replay normalization preserve the schema-v2 action identity fields emitted by new C-side transition logs.
- keep old logs compatible without synthesizing misleading v2 policy fields from legacy demo labels.

Implementation notes:
- `learner_replay_row()` now preserves:
  - `transition_schema_version`
  - `policy_requested_*`
  - `policy_executed_*`
  - `input_*`
  - `engine_*`
- missing `transition_schema_version` defaults to `1`; missing v2 action groups default to zero.
- the function deliberately does not copy legacy `requested_*` / `executed_*` into `policy_*`, because old `human-demo` / `cpu-demo` rows used those legacy fields as input-derived labels.
- DQN/training action source selection is unchanged in this step.

Validation:
- `python3 -m py_compile tools/rl_probe_server.py` passed.
- smoke check confirmed v2 fields survive `learner_replay_row()` and a legacy row gets `transition_schema_version=1` with zeroed v2 fields.
- `git diff --check` passed.

Follow-up:
- add `--training-action-source auto|policy|input|engine|prefer-engine` and update DQN/compare/analyzer code paths to report action-label source breakdown.

## 2026-04-29: Transition Schema V2 C-Side Export Step 1

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / transition action-label cleanup

Files changed:
- `src/rl/rl_session.c`
- `docs/rl-policy-action-taxonomy.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- start transition schema v2 by writing separate action identity field groups in new C-side transition rows.
- keep the legacy fields untouched so existing logs, parsers, DQN training commands, and comparison tools remain compatible until the Python rollout steps are implemented.

Implementation notes:
- transition rows now include `transition_schema_version:2`.
- remote action packets populate `policy_requested_*` when accepted and `policy_executed_*` when the queued remote or repeated-last policy action is executed.
- human-demo / CPU-demo rows populate `input_action_id`, `input_sub_action_id`, `input_action_step`, and `input_label_source` from the existing demo input mapper.
- Ryu demo engine attribution now mirrors the existing `demo_attributed_*` label into `engine_*` fields:
  - `engine_action_id`
  - `engine_sub_action_id`
  - `engine_routine_1`
  - `engine_routine_2`
  - `engine_kind_of_waza`
  - `engine_current_attack`
  - `engine_label_source`
  - `engine_lag_frames`
- no Python ingestion or DQN action-source selection behavior changed in this step.

Validation:
- `git diff --check` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed and rebuilt `src/rl/rl_session.c`.

Follow-up:
- update `tools/rl_probe_server.py` replay ingestion to preserve the v2 fields while keeping legacy fallback.
- add `--training-action-source auto|policy|input|engine|prefer-engine` only after ingestion can retain both schemas.

## 2026-04-29: Document Transition Schema V2 Rollout Plan

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / transition action-label cleanup

Files changed:
- `docs/rl-policy-action-taxonomy.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- record a staged rollout plan for separating policy-selected actions, input-derived demo labels, and engine-attributed move labels.
- avoid adding more overloaded fields to `requested_policy_action_id` / `executed_policy_action_id` before the schema semantics are clear.
- explicitly defer guard-specific diagnostic fields such as `guard_intent`, `guard_engine_candidate`, and `guard_contact_confirmed` until after the core action-identity split is implemented.

Implementation notes:
- added `Transition Schema V2 Rollout Plan` to the action taxonomy document.
- planned v2 field groups are:
  - `policy_*`: remote RL/DQN requested/executed action identity.
  - `input_*`: best-effort controller / CPU-demo input label.
  - `engine_*`: SF3 engine-recognized action-start label from R1/R2/KW/AK attribution.
- documented that `engine_*` means "engine-recognized move start near this decision row", not "current per-frame engine state"; future per-row state should use a separate `obs_self_engine_state_*` family.
- added Milestone 6 checklist items for the staged implementation:
  - C-side NDJSON export.
  - Python replay ingestion.
  - DQN `--training-action-source`.
  - analyzer / compare source breakdown.
  - short mixed remote + CPU-demo validation before long-run retraining.

Validation:
- documentation-only update; reviewed the diff for placement and wording.

Follow-up:
- implement step 1 by adding schema-v2 fields to the C decision ledger / transition export while preserving legacy fields.
- then update Python ingestion before changing DQN training defaults.

## 2026-04-29: Tighten Demo Guard Labels And Guard Bonus

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / CPU-demo guard-label cleanup

Files changed:
- `src/rl/rl_session.c`
- `tools/train_dqn_learner.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- stop CPU-demo / human-demo `DOWN_BACK` input from always becoming `guard-crouch`.
- reduce the false guard samples that made DQN overvalue crouch guard / passive defense.
- make guard success reward require actual contact evidence by default, not just `opp_attack=1` plus no self damage.

Implementation notes:
- `RLSession_DeriveDemoPolicyMeta()` now uses stricter demo guard labels:
  - `BACK` remains `guard-stand` when there is opponent attack threat in range, and can also use engine stand-guard candidate states.
  - `DOWN_BACK` becomes `guard-crouch` only when there is opponent attack threat in range or engine crouch-guard candidate states.
  - no-threat `DOWN_BACK` stays neutral/untrained instead of being labeled as guard.
- engine guard candidate helpers currently use:
  - stand: `R1=0 && R2 in {27,28,31,32,33}`
  - crouch: `R1=0 && R2 in {29,31,32,33}`
- `tools/train_dqn_learner.py` adds `--reward-guard-success-require-contact` / `--no-reward-guard-success-require-contact`.
  - default is enabled.
  - when enabled, guard success bonus requires `obs_self_contact_reaction_state` inside the guard window and no self HP damage.
  - passive / far guard costs remain based on clean no-damage guard windows.
- diagnostics now print `require_contact:1` in `guard_shape=...`.

Validation:
- `python3 -m py_compile tools/train_dqn_learner.py` passed.
- source-level smoke confirmed no-threat `DOWN_BACK` is no longer labeled `guard-crouch`; it remains neutral unless threat or engine guard candidate evidence is present.
- small DQN smoke passed on `logs/rl-transitions-cpu-demo-r12-v1-4-3-3.ndjson` with guard shaping enabled and printed `require_contact:1`.

Follow-up:
- rebuild/deploy the telemetry MiSTer binary before collecting the next CPU-demo log; Python-only reruns cannot change C-side demo labels in old logs.
- collect a fresh CPU-demo R1/R2 log and confirm `guard-crouch` no longer contains a large idle/no-threat bucket.
- retrain all-actions DQN on the fresh log and compare guard rates plus `--focus-actions fireball-lp,fireball-mp,fireball-hp`.

## 2026-04-29: Add Focus-Action DQN Compare Diagnostics

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / offline DQN policy diagnosis

Files changed:
- `tools/compare_dqn_models.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- make the DQN comparison tool inspect any caller-specified action group instead of hard-coding Hadouken / fireball analysis.
- answer whether an action is absent because it is truly low-value or because it is near top-1 but consistently blocked by another action.

Implementation notes:
- added `--focus-actions`, a comma-separated list of canonical tabular/DQN action names.
- added `--focus-rank-limit`, defaulting to `3`, for top-N blocker diagnostics.
- focus output reports:
  - rank distribution: `top1`, `top2`, `top3`, `top4plus`.
  - best focus action counts.
  - actions that block the focus group when the focus action is inside the selected top-N but not top-1.
  - mean and p90 Q gap between the selected top action and the best focus action.
  - the same breakdown inside `atk0/atk1 x close/mid/far` threat-distance buckets.

Validation:
- `python3 -m py_compile tools/compare_dqn_models.py` passed.
- focus smoke against `logs/rl-transitions-cpu-demo-v1-4-3-3.ndjson` and `model/dqn-cpudemo-allactions-demo-outcome-v2` passed with `--focus-actions fireball-lp,fireball-mp,fireball-hp`.

Follow-up:
- use this output to compare Hadouken, Shoryuken, Tatsumaki, and selected normal groups before adding replay upsampling or extra action-specific rewards.

## 2026-04-29: Consume Demo-Claimed HP Deltas During DQN Replay Build

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / CPU-demo delayed-credit cleanup

Files changed:
- `tools/train_dqn_learner.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- prevent one HP delta from rewarding both the engine-attributed move that caused it and a later unrelated input-based row.
- make long-window projectile credit cleaner: if a Hadouken chip is claimed by `fireball-lp`, the later `guard` / `neutral` row where the chip lands no longer receives that same `delta_opp_hp` reward.

Implementation notes:
- `build_experiences()` now copies each row into per-episode working rows so training-only HP-delta mutation does not alter the raw loaded row list.
- when `add_demo_attribution_experience()` finds an HP outcome inside its effective window, it:
  - computes the demo-attributed reward from that available HP delta.
  - records claimed diagnostics.
  - zeroes the claimed `delta_opp_hp` / `delta_self_hp` on the working rows before subsequent input-based replay processing.
- later input-based rewards, risk windows, guard shaping, spacing shaping, and position shaping see only unclaimed HP deltas in that episode pass.
- `demo_attr` diagnostics now print `claimed:<events>/<opp_hp>/<self_hp>`.

Validation:
- `python3 -m py_compile tools/train_dqn_learner.py` passed.
- targeted smoke on `logs/rl-transitions-cpu-demo-v1-4-3-3.ndjson`, `run=3`, `episode=15`, `decision=79`:
  - before demo attribution, `decision=96` had `delta_opp_hp=1`.
  - `fireball-lp` claimed that outcome and received `+1` raw / `+0.01` scaled reward.
  - after claim, the working row for `decision=96` had `delta_opp_hp=0`, so its input-based training reward became `0`.
- 5000-row DQN smoke passed:
  - `demo_attr=prefer-demo-action:59/86`
  - `early:57`
  - `claimed:57/233/140`
  - `action_stats` still included `fireball-lp`, `fireball-mp`, `fireball-hp`, `tatsu-mk`, `guard-crouch`, and `stand-mk`.

Follow-up:
- rerun the all-actions CPU-demo A/B models and compare whether `guard` drops when projectile/chip credit is no longer duplicated.
- decide whether fireball chip needs an action-specific contact bonus after inspecting the new non-duplicated reward stats.

## 2026-04-29: Stop Demo Attribution Windows At First HP Outcome

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / CPU-demo delayed-credit cleanup

Files changed:
- `tools/train_dqn_learner.py`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- treat `--demo-attribution-window-decisions` and `--demo-attribution-action-windows` as maximum tracking windows.
- for long-window moves such as Hadouken, stop the effective outcome window at the first self/opponent HP delta, because that means the move was either rewarded by hit/chip or punished by counter-hit.
- if no HP delta occurs before the configured maximum window, keep the existing no-damage interpretation for whiff / evade / parry-like outcomes.

Implementation notes:
- `add_demo_attribution_experience()` now scans from the attributed event row to the configured maximum window and cuts `window_end` to the first row with `delta_opp_hp > 0` or `delta_self_hp > 0`.
- the demo attribution diagnostics now print `early:<count>` and metadata includes `early_outcome_events`.
- `--demo-attribution-stop-at-next-event` still applies after the first-HP-delta shortening; it can only make the effective window shorter.

Validation:
- `python3 -m py_compile tools/train_dqn_learner.py` passed.
- targeted smoke on `logs/rl-transitions-cpu-demo-v1-4-3-3.ndjson`, `run=3`, `episode=15`, `decision=79`:
  - event is `fireball-lp` (`1229/lp`)
  - configured action window was `45`
  - effective outcome window stopped at `decision=96`, the first row with `delta_opp_hp=1`
  - `early_outcome_events=1`
  - raw reward remained `+1`, scaled reward `+0.01`
  - next state for the demo-attributed experience matches decision `96`, not the end of the full 45-decision maximum window.

Follow-up:
- decide whether to also consume/claim the HP delta so the later input-based row does not simultaneously reward unrelated `guard` / `neutral` actions.
- evaluate whether fireball chip needs an action-specific contact bonus after duplicate-credit cleanup.

## 2026-04-29: Rename LP Hadouken Learner Action To Fireball-LP

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / special-move action naming cleanup

Files changed:
- `tools/rl_probe_server.py`
- `tools/train_dqn_learner.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- remove the ambiguous legacy learner action name `fireball` from the default tabular/DQN action set.
- make all Hadouken learner actions strength-explicit: `fireball-lp`, `fireball-mp`, and `fireball-hp`.
- keep old commands, logs, and model manifests readable by treating `fireball` / `ryu-fireball` as aliases for `fireball-lp`.

Implementation notes:
- `TABULAR_ACTION_NAMES` now contains `fireball-lp`, `fireball-mp`, and `fireball-hp`; bare `fireball` is no longer a trainable/default action name.
- `--policy fireball` and `--policy ryu-fireball` remain scripted LP Hadouken aliases for fixed-policy probes.
- `canonical_tabular_action_name()` maps `fireball` and `ryu-fireball` to `fireball-lp`.
- model/action coercion now canonicalizes legacy action names in `actions`, q-tables, q-counts, DQN `--actions`, and per-action window flags.
- transition/demo attribution maps Ryu Hadouken LP metadata `(1229, lp)` to `fireball-lp`; old partial labels fall back to `fireball-lp`.

Validation:
- `python3 -m py_compile tools/rl_probe_server.py tools/train_dqn_learner.py tools/compare_dqn_models.py tools/analyze_rl_transitions.py` passed.
- action registry smoke confirmed:
  - `tabular_count 45`
  - `fireball-lp` is in `TABULAR_ACTION_NAMES`
  - bare `fireball` is not in `TABULAR_ACTION_NAMES`
  - `fireball` and `ryu-fireball` canonicalize to `fireball-lp`
  - `forward+LP` and `(Ryu Hadouken, lp)` both map to `fireball-lp`
  - `parse_action_names("fireball,fireball-lp,ryu-fireball,fireball-mp")` dedupes to `("fireball-lp", "fireball-mp")`
- DQN smoke passed with `fireball-lp`, `fireball-mp`, and `fireball-hp` in `--actions` and per-action demo windows:
  - `actions=11`
  - `demo_attr=prefer-demo-action:67/86`
  - `action_stats` included `fireball-hp`, `fireball-lp`, and `fireball-mp`.

Follow-up:
- update active CPU-demo training commands to use `fireball-lp` and `fireball-lp=...` windows.
- keep accepting bare `fireball` only as compatibility input, not as a new model action name.

## 2026-04-29: Split Ryu Shoryuken And Tatsumaki Strength Variants

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / special-move action refinement

Files changed:
- `tools/rl_probe_server.py`
- `tools/train_dqn_learner.py`
- `tools/compare_dqn_models.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- add LP/MP/HP Shoryuken and LK/MK/HK Tatsumaki Senpukyaku as first-class learner/probe actions.
- keep CPU-demo engine-attributed Shoryuken/Tatsumaki strengths semantically clean instead of collapsing regular variants into `shoryuken-mp` / `tatsu-mk`.

Implementation notes:
- `TABULAR_ACTION_NAMES` now includes:
  - `shoryuken-lp`, `shoryuken-mp`, `shoryuken-hp`
  - `tatsu-lk`, `tatsu-mk`, `tatsu-hk`
- scripted probe policies now expose the same strength-specific names.
- legacy aliases remain:
  - `shoryuken` -> `shoryuken-hp`
  - `tatsu` -> `tatsu-lk`
- strength-specific scripted macros emit:
  - Shoryuken: `forward, down, down-forward, down-forward+P, neutral, neutral`
  - Tatsumaki: `down, down-back, back, back+K, neutral, neutral`
- DQN Shoryuken extra risk costs now apply to all `shoryuken-*` variants instead of only `shoryuken-mp`.
- `tools/compare_dqn_models.py` now aggregates `shoryuken_rate`, `base_shoryuken_to_other`, and `other_to_shoryuken` across all Shoryuken variants.

Validation:
- `python3 -m py_compile tools/rl_probe_server.py tools/train_dqn_learner.py tools/compare_dqn_models.py` passed.
- action registry smoke confirmed:
  - `tabular_count 45`
  - no missing tabular or scripted entries for `shoryuken-lp`, `shoryuken-mp`, `shoryuken-hp`, `tatsu-lk`, `tatsu-mk`, `tatsu-hk`
  - policy metadata round-trips for all six new/expanded special variants
  - `shoryuken` canonicalizes to `shoryuken-hp`; `tatsu` canonicalizes to `tatsu-lk`
- DQN smoke passed with all six variants in `--actions`, `--reward-risk-action-windows`, and `--demo-attribution-action-windows`:
  - `actions=15`
  - `demo_attr=prefer-demo-action:79/86`
  - `action_stats` included `shoryuken-lp`, `tatsu-lk`, `tatsu-mk`, and Hadouken variants in the sampled rows
- compare smoke passed and reported aggregate `shoryuken_rate=100.0%` for a synthetic collapsed smoke model selecting `shoryuken-lp`, confirming compare aggregation includes non-MP Shoryuken variants.

Follow-up:
- retrain the CPU-demo special-action DQN with `shoryuken-lp`, `shoryuken-mp`, `shoryuken-hp`, `tatsu-lk`, `tatsu-mk`, and `tatsu-hk` in `--actions`.
- include per-action windows for all Tatsu variants when using delayed-credit training, e.g. `tatsu-lk=25,tatsu-mk=25,tatsu-hk=25`.

## 2026-04-29: Add Prefer-Demo-Action DQN Replay Mode

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / CPU-demo move-outcome training

Files changed:
- `tools/train_dqn_learner.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- train CPU-demo / human-demo attacks from engine-attributed `demo_attributed_*` move labels instead of input-based `executed_*` labels when an attributed move is present.
- preserve unattributed demo rows, such as walk / guard / spacing examples, as normal input-based experiences.
- support per-action risk windows so projectile and long-animation actions are not forced to use the same no-damage / punished lookahead as quick normals.

Implementation notes:
- `--demo-attribution-training-mode` now accepts `prefer-demo-action`.
- `prefer-demo-action` behavior:
  - demo row with `demo_attributed_*`: close the previous input-based experience, add one engine-attributed demo experience, and skip the row's input-based action experience.
  - demo row without `demo_attributed_*`: keep the normal input-based replay path.
  - non-demo row: keep the normal input-based replay path.
- this differs from:
  - `augment`, which adds engine-attributed experiences but also keeps the same row's input-based experience.
  - `replace-demo`, which skips input-based replay for all demo rows, including unattributed walk / guard rows.
- `--reward-risk-action-windows action=N,...` now overrides `--reward-risk-window-decisions` per action for input-based risk shaping; this pairs with the existing `--demo-attribution-action-windows` for engine-attributed delayed credit.

Validation:
- `python3 -m py_compile tools/train_dqn_learner.py` passed.
- prefer-demo-action smoke passed:
  ```sh
  python3 tools/train_dqn_learner.py logs/rl-transitions-cpu-demo-v1-4-3-3.ndjson --model-dir /tmp/rl-dqn-prefer-demo-smoke --model-version 1 --limit 5000 --steps 5 --batch-size 8 --hidden-sizes 16 --actions forward,back,guard-stand,guard-crouch,throw,stand-mk,fireball,fireball-mp,fireball-hp,shoryuken-mp,tatsu-mk --demo-attribution-training-mode prefer-demo-action --demo-attribution-window-decisions 15 --demo-attribution-action-windows fireball=45,fireball-mp=45,fireball-hp=45,tatsu-mk=25 --demo-attribution-no-damage-cost 0.5 --demo-attribution-punished-cost 2.0 --log-interval 5 --eval-limit 200 --diagnostic-top-n 8
  ```
- smoke output confirmed mixed behavior:
  - `demo_attr=prefer-demo-action:79/86`
  - `experiences=1999`
  - `included=1920`, showing unattributed input-based demo rows were preserved
  - `action_stats` included attributed specials such as `fireball-hp`, `fireball`, and `tatsu-mk`

Follow-up:
- train the CPU-demo special-action model with `--demo-attribution-training-mode prefer-demo-action` and compare it against `augment` and `replace-demo`.
- if Hadouken still remains low, next diagnostics should test a no-throw action subset and fireball-focused data rather than further increasing global shaping.

## 2026-04-28: Split Ryu Fireball Strength Variants

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / special-move action refinement

Files changed:
- `tools/rl_probe_server.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- stop collapsing CPU-demo Hadouken MP/HP engine-attributed move labels into the LP `fireball` learner action.
- allow DQN/tabular actors to explicitly choose `fireball`, `fireball-mp`, or `fireball-hp`.

Implementation notes:
- `TABULAR_ACTION_NAMES` now includes `fireball-mp` and `fireball-hp` alongside the legacy LP `fireball` action.
- `SCRIPTED_POLICY_CHOICES` now exposes `--policy fireball-mp` and `--policy fireball-hp` for fixed-policy probes.
- `POLICY_ACTION_META_BY_NAME` maps:
  - `fireball` -> Ryu Hadouken / `lp`
  - `fireball-mp` -> Ryu Hadouken / `mp`
  - `fireball-hp` -> Ryu Hadouken / `hp`
- scripted macros now emit strength-specific QCF endings:
  - `fireball`: `down-back, down, down-forward, forward+LP, neutral, neutral`
  - `fireball-mp`: `down-back, down, down-forward, forward+MP, neutral, neutral`
  - `fireball-hp`: `down-back, down, down-forward, forward+HP, neutral, neutral`
- `demo_attributed_*` replay now keeps `fireball-mp` / `fireball-hp` as distinct action names because those names are live learner actions.

Validation:
- `python3 -m py_compile tools/rl_probe_server.py tools/train_dqn_learner.py tools/analyze_rl_transitions.py tools/compare_dqn_models.py` passed.
- action registry smoke printed:
  - `fireball ... meta=(1229, 1) seq=['0x7', '0x2', '0x8', '0x14', '0x0', '0x0']`
  - `fireball-mp ... meta=(1229, 2) seq=['0x7', '0x2', '0x8', '0x24', '0x0', '0x0']`
  - `fireball-hp ... meta=(1229, 3) seq=['0x7', '0x2', '0x8', '0x44', '0x0', '0x0']`
  - `tabular_actions 41`
  - `missing_exec []`
- CPU-demo attribution check on `logs/rl-transitions-cpu-demo-v1-4-3-3.ndjson` now reports:
  - `fireball 640`
  - `fireball-mp 391`
  - `fireball-hp 1320`
  - `shoryuken-mp 326`
  - `tatsu-mk 488`
- full training published `model/dqn-cpudemo-allnormals-fireballvariants-corner-v1` with:
  - `experiences=92487`
  - `actions=40`
  - `demo_attr=augment:3594/3779`
  - action stats: `fireball-hp:1275/17.23/0.014`, `fireball:611/4.22/0.007`, `fireball-mp:381/4.92/0.013`
  - greedy top actions: `throw 30.7%`, `guard-stand 22.2%`, `stand-mk 20.1%`, `forward 14.5%`, `guard-crouch 12.4%`, `fireball 0.0%`
- comparing the previous collapsed-specials model against the variants model on the same 5000-row CPU-demo tail changed `297/5000` greedy choices.

Findings:
- the previous lack of Hadouken in greedy policy was not only caused by MP/HP being collapsed into LP; after splitting variants, `fireball-mp` and `fireball-hp` still did not become top-1 greedy actions.
- in the current feature/reward setup, far no-threat observations still rank guard/forward/throw above Hadouken variants, so the next bottleneck is state/reward/data quality rather than action-label availability.

Follow-up:
- collect or synthesize targeted Hadouken data where far-range fireball leads to positive outcomes and unsafe close/mid fireball is punished.
- consider fireball-specific reward shaping or richer projectile/opponent-airborne observations before trying to force more Hadouken through scalar rewards alone.
- keep `fireball-mp` / `fireball-hp` in future DQN action sets so CPU-demo labels remain semantically clean.

## 2026-04-28: Add DQN Corner Position Reward Shaping

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / anti-turtle DQN reward shaping

Files changed:
- `tools/train_dqn_learner.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- reduce the live all-normals DQN tendency to over-defend, retreat to its own corner, and keep guarding at long range.
- add offline reward-shaping knobs that can penalize clean corner guard/back starts and reward forward movement that increases own back-edge distance.

Implementation notes:
- `tools/train_dqn_learner.py` now supports corner position shaping:
  - `--reward-corner-back-edge-threshold`
  - `--reward-corner-guard-cost`
  - `--reward-corner-back-cost`
  - `--reward-corner-escape-bonus`
  - `--reward-corner-escape-min-delta`
- shaping applies only to `executed_policy_action_step == 0` rows near the player's own back edge.
- guard/back costs and forward escape bonus apply only when the short lookahead window has no self HP damage, preserving natural HP-delta punishment for actually getting hit.
- training stdout and model metadata now include `position_bonus`, `position_cost`, `position_net`, and a `position_shape=...` diagnostics line.

Validation:
- `python3 -m py_compile tools/train_dqn_learner.py` passed.
- smoke training against `logs/rl-transitions-cpu-demo-v1-4-3-3.ndjson` printed:
  - `position_bonus=2130.0`
  - `position_cost=28172.5`
  - `position_shape=corner_back_edge<=80 corner_guard:11343/17014.5 corner_back:5579/11158.0 escape:1065/2130.0 net:-26042.5`
- full CPU-demo all-normal retrains were compared on the same 5000-row CPU-demo tail:
  - baseline `model/dqn-cpudemo-allnormals-v1`: `guard-crouch 33.3%`, `guard-stand 25.7%`, `forward 12.9%`, attack rate `27.9%`
  - `model/dqn-cpudemo-allnormals-corner-v3`: `guard-crouch 25.0%`, `guard-stand 23.2%`, `forward 19.5%`, attack rate `32.4%`
  - `model/dqn-cpudemo-allnormals-corner-v4`: `guard-crouch 20.6%`, `guard-stand 19.8%`, `forward 19.1%`, attack rate `40.4%`
- targeted corner-bucket analysis showed the important limitation:
  - non-corner `atk0_far` improved from `guard-crouch 70.1% / forward 8.2%` to `guard-crouch 36.9% / forward 30.7%` in v4.
  - true `corner_atk0_far` stayed heavily defensive (`guard-crouch 98.0%` baseline to `96.0%` in v4), so this is not sufficient evidence that corner escape is learned.

Findings:
- position shaping is useful for reducing generic far-range passivity.
- the current CPU-demo dataset does not contain enough successful corner-escape alternatives for reward shaping alone to flip the policy at `corner + far + no opponent attack`.
- pushing corner costs higher mainly changes non-corner far behavior and overall attack/throw rate before it reliably fixes the exact corner turtle state.

Follow-up:
- collect targeted corner-escape demo data where the controlled side is near its own back edge, walks forward out of the corner, and then resumes offense/guard.
- consider adding a corner-specific observation feature or finer distance/corner buckets if the MLP still fails to separate trapped-corner states from general far states.
- do not treat `model/dqn-cpudemo-allnormals-corner-v4` as the final anti-turtle answer; it is a useful MiSTer smoke candidate only if we want to test whether more active non-corner behavior feels better.

## 2026-04-28: Expand Basic Normal Action Support And Train CPU-Demo DQN

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / all-normals CPU-demo DQN bootstrap

Files changed:
- `tools/rl_probe_server.py`
- `tools/train_dqn_learner.py`
- `tools/analyze_rl_transitions.py`
- `tools/compare_dqn_models.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- support all standing, crouching, forward-jump, neutral-jump, and back-jump LP/MP/HP/LK/MK/HK basic normals in the probe-side action registry.
- train a first CPU-demo DQN model that can choose defense, movement, throw, and all basic normals without enabling fireball / Shoryuken / Tatsumaki shortcuts.

Implementation notes:
- `tools/rl_probe_server.py` now generates normal action names from shared button and jump-direction tables.
- direct fixed-wire support covers all standing and crouching normals; jump normals use the existing six-step macro shape: jump direction, jump direction, jump direction + button, jump direction + button, neutral, neutral.
- policy metadata now maps all new crouch and jump normals to stance/direction-specific policy action IDs and button sub-actions.
- `tools/train_dqn_learner.py` now derives generic attack-risk and jump-risk sets from `rl.TABULAR_ACTION_NAMES`, so newly registered normals automatically participate in `--reward-risk-profile all-attacks`.
- `tools/analyze_rl_transitions.py` and `tools/compare_dqn_models.py` now consume the expanded registry instead of carrying stale hard-coded action lists.

Validation:
- `python3 -m py_compile tools/rl_probe_server.py tools/train_dqn_learner.py tools/analyze_rl_transitions.py tools/compare_dqn_models.py` passed.
- action registry smoke printed `actions 39` and `missing_exec []`, confirming every registered action has either a fixed wire or scripted macro path.
- one-step DQN smoke passed with the 35-action all-basic-normal subset against `logs/rl-transitions-cpu-demo-v1-4-3-3.ndjson`, publishing `/tmp/dqn-allnormals-smoke`.
- full training command published `model/dqn-cpudemo-allnormals-v1` with:
  - `experiences=89426`
  - `actions=35`
  - `guard_net=9737.6`
  - `spacing_net=5623.4`
  - `demo_attr=augment:533/3779`
  - greedy top actions: `guard-stand 33.8%`, `stand-mk 20.6%`, `guard-crouch 19.7%`, `throw 13.0%`, `forward 12.5%`, `back 0.3%`
- comparison on the CPU-demo tail showed `model/dqn-cpudemo-allnormals-v1` reduced attack rate from `37.7%` in `model/dqn-cpudemo-basic-defense-throw-v2` to `27.9%`, while adding `throw 16.3%` to the greedy tail distribution and keeping jump greed very low.

Findings:
- normal coverage from the existing CPU-demo log is good for standing normals and crouching normals, but sparse for jump normals.
- normal actions with zero trainable samples in this log: `jump-forward-lp`, all neutral-jump normals, and all back-jump normals.
- tiny jump coverage exists for `jump-forward-mp` (`3`), `jump-forward-hp` (`5`), `jump-forward-lk` (`1`), `jump-forward-mk` (`51`), and `jump-forward-hk` (`1`).
- greedy evaluation selected jump normals only `12/5000` rows (`jump-neutral-mp`), so the all-normal model did not collapse into jump spam.
- throw entered the greedy tail distribution (`814/5000`, `16.3%`), mostly at close/mid range, which is stronger than the prior basic-defense-throw v2 model where throw did not appear in greedy top actions.

Follow-up:
- live-test `model/dqn-cpudemo-allnormals-v1` before changing reward shaping again.
- collect more CPU-demo or human-demo coverage if neutral/back jump normals should become real learner options; the existing CPU-demo log is not sufficient for those moves.
- review whether `back` remains under-selected because far/passive guard shaping still makes guard safer than retreat.

## 2026-04-28: Document Ryu R1/R2 Mapping Source Trace

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / R1/R2 ordinary-state validation

Files changed:
- `docs/rl-policy-action-taxonomy.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- preserve the SF3 source-code path used to interpret raw `routine_no[1]` / `routine_no[2]` values, with Ryu as the first worked example.
- make future all-character move mapping repeatable: trace `R1/R2` through engine dispatch tables, then validate with overlay/log values before promoting runtime decoders.

Implementation notes:
- documented `plmain.c::plmain_lv_02` as the `R1` high-level state dispatcher.
- documented `plpnm.c::Player_normal` / `plpnm_lv_00[R2]` as the shared ordinary-state path for walk, crouch, jump, guard, and related normal states.
- documented `plpat.c::Player_attack`, `plpat_lv_00[R2]`, and `plxx_extra_attack_table[player_number]` as the attack path split for common versus character-specific routines.
- documented `pls03.c::hissatsu_setup_union` and `set_attack_routine_number` as the paths that set `R1=4` and assign attack `R2`.
- documented Ryu's `plpat02.c::pl02_extra_attack` / `pl02_exatt_table[R2 - 16]` source trace for Hadouken, Shoryuken, Tatsumaki Senpukyaku, super-art paths, Air Tatsumaki, and Joudan Sokutou Geri.
- recorded provisional `R1=0` ordinary-state labels and marked guard/jump/block labels as validation aids until fresh raw-R1/R2 logs confirm them.

Validation:
- doc references were checked against the SF3 source files listed above.
- `git diff --check -- docs/rl-policy-action-taxonomy.md docs/remote-rl-agent-engineering-log.md` passed.

Follow-up:
- use a fresh raw-R1/R2 transition log to confirm `normal.walk-*`, `normal.guard-*`, `normal.crouch`, and `normal.jump-*` before training from those ordinary-state labels.
- repeat the same source trace for Ken/Akuma next because they share some Ryu-like handlers but have character-specific routine meanings.

## 2026-04-28: Add Raw Routine Transition Diagnostics

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / R1/R2 ordinary-state validation

Files changed:
- `src/rl/rl_session.c`
- `tools/rl_probe_server.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- write raw self/opponent `routine_no[1]` and `routine_no[2]` snapshots into transition rows so `tools/analyze_rl_transitions.py` can classify ordinary engine states such as walk, crouch, jump, guard, attack, damage/contact, catch, and caught.
- keep these as diagnostic replay fields only; they are not promoted into UDP OBS payloads, tabular state keys, or DQN feature vectors.

Implementation notes:
- transition JSON now includes:
  - `obs_self_routine_1`
  - `obs_self_routine_2`
  - `obs_opp_routine_1`
  - `obs_opp_routine_2`
- the values are captured from the same observation used for the existing spacing/state row snapshot.
- `tools/rl_probe_server.py` preserves the four fields in `learner_replay_row()` so local replay/import paths do not strip them.

Validation:
- `python3 -m py_compile tools/rl_probe_server.py tools/analyze_rl_transitions.py` passed.
- `python3 tools/analyze_rl_transitions.py logs/rl-transitions-cpu-demo-v1-4-3-3.ndjson --tail-rows 200 --limit 8` passed against an older log; as expected it fell back to derived coarse states because that log predates the raw fields.
- `git diff --check -- src/rl/rl_session.c tools/rl_probe_server.py docs/plan-remote-rl-agent.md docs/remote-rl-agent-engineering-log.md` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed and rebuilt `src/rl/rl_session.c`.

Follow-up:
- collect a fresh short human-demo or CPU-demo log and confirm `ENGINE_STATE_ACTION_BY_ROUTINE` shows raw `normal.walk-*`, `normal.guard-*`, `normal.crouch`, and `normal.jump-*` labels before using these labels as learner targets.

## 2026-04-28: Add Engine State Action Analyzer Mapping

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / R1/R2 ordinary-state validation

Files changed:
- `tools/analyze_rl_transitions.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- add an analyzer-only `engine_state_action` view keyed by `(routine_no[1], routine_no[2])` so ordinary engine states such as walk, crouch, jump, guard, damage/contact, catch/caught, and attack routines can be counted before promoting more raw routine fields into the transition schema.
- keep the mapping diagnostic/provisional: raw `R1/R2` fields are required for precise ordinary-state labels, while older logs with only derived routine flags fall back to coarse `attack.r2-unknown` / `damage-contact.r2-unknown`.

Implementation notes:
- `tools/analyze_rl_transitions.py` now recognizes common future raw field spellings such as `self_routine_1`, `self_routine_2`, `obs_self_routine1`, and opponent equivalents.
- `R1=0` maps selected normal-state `R2` values to provisional labels such as `normal.walk-forward`, `normal.walk-back`, `normal.crouch`, `normal.jump-air`, and `normal.guard-*`.
- `R1=4` maps Ryu attack `R2` values to known engine move labels (`hadouken`, `shoryuken`, `tatsumaki-senpukyaku`, throw/catch, and provisional super/special paths); non-Ryu or unvalidated entries stay as routine IDs.
- new output sections:
  - `ENGINE_STATE_ACTION_SUMMARY`
  - `ENGINE_STATE_ACTION_BY_SIDE`
  - `ENGINE_STATE_ACTION_BY_SIDE_DX`
  - `ENGINE_STATE_ACTION_BY_ROUTINE`

Validation:
- `python3 -m py_compile tools/analyze_rl_transitions.py` passed.
- `python3 tools/analyze_rl_transitions.py --help` passed.
- `python3 tools/analyze_rl_transitions.py logs/rl-transitions-cpu-demo-v1-4-3-3.ndjson --tail-rows 200 --limit 8` passed; as expected for the current schema, it reported derived coarse states rather than raw ordinary walk/guard labels.

Follow-up:
- add raw `self_routine_1/self_routine_2` and `opp_routine_1/opp_routine_2` to a diagnostic transition-log schema only after confirming logging overhead and compatibility.
- validate `R1=0` guard/walk/jump/crouch labels with short human-demo and CPU-demo clips before using them as learner targets.

## 2026-04-28: Add Demo-Attributed DQN Reward Shaping

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / CPU-demo move-outcome training

Files changed:
- `tools/train_dqn_learner.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- let offline DQN training optionally consume engine-attributed demo move starts instead of relying only on input-based `requested_*` / `executed_*` labels.
- use the same delayed-credit outcome idea as `tools/analyze_rl_transitions.py` so CPU-demo rows can train from actual Ryu move identity (`fireball`, `shoryuken`, `tatsu`, `throw`, normals) when the exact input pulse is not visible at the decision boundary.

Implementation notes:
- `tools/train_dqn_learner.py` now has `--demo-attribution-training-mode off|augment|replace-demo`.
  - `off` is the default and preserves the old input-based DQN training path.
  - `augment` keeps normal input-based experiences and adds extra experiences from `demo_attributed_*` event rows.
  - `replace-demo` skips normal input-based experiences for `execution_source = 4/5` rows and uses only `demo_attributed_*` events for demo-sourced experience creation.
- delayed-credit shaping uses `--demo-attribution-window-decisions N` to sum future `delta_opp_hp` / `delta_self_hp` within the same episode.
- `--demo-attribution-action-windows action=N,...` is reserved for per-action window tuning; omitted actions use the global window.
- `--demo-attribution-stop-at-next-event` can make windows non-overlapping when needed, but overlapping remains available for projectile-style delayed hits.
- optional raw reward adjustments:
  - `--demo-attribution-hit-bonus`
  - `--demo-attribution-no-damage-cost`
  - `--demo-attribution-punished-cost`
- DQN metadata and stdout now record `demo_attribution_*` config and stats, including event counts, hit/no-damage/punished/trade counts, HP sums, bonus/cost totals, and scaled reward sum.

Validation:
- `python3 -m py_compile tools/train_dqn_learner.py` passed.
- `python3 tools/train_dqn_learner.py --help` shows the new demo-attribution flags.
- smoke training passed:
  ```sh
  python3 tools/train_dqn_learner.py logs/rl-transitions-cpu-demo-v1-4-3-3.ndjson --model-dir /tmp/rl-dqn-demoattr-smoke --model-version 1 --steps 10 --batch-size 8 --hidden-sizes 16 --actions fireball,shoryuken-mp,tatsu-mk,throw,jump-forward-mk,stand-mk,crouch-hk --demo-attribution-training-mode replace-demo --demo-attribution-window-decisions 10 --demo-attribution-no-damage-cost 0.5 --demo-attribution-punished-cost 2.0 --log-interval 5
  ```
- smoke result: `events=621`, `included=580`, `excluded=41`, `hit=303`, `no_damage=277`, `punished=60`, `trade=20`, `hp=1902/675`.

Follow-up:
- compare `replace-demo` versus `augment` on CPU-demo + human-demo mixes.
- tune per-action windows after fireball / throw / jump outcomes show consistent delayed-credit timing.
- decide whether demo-attributed outcomes should also drive imitation-style sampling weights instead of only Q-reward shaping.

## 2026-04-28: Add Demo-Attributed Delayed-Credit Analyzer

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / CPU-demo move-outcome analysis before DQN reward integration

Files changed:
- `tools/analyze_rl_transitions.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- classify engine-attributed demo move starts as hit, whiff/no-damage, punished, or trade using later HP deltas.
- keep credit assignment in Python analysis/reward-shaping code instead of adding derived outcome guesses to the C-side transition schema.

Implementation notes:
- `tools/analyze_rl_transitions.py` now retains parsed rows and groups them by `(run_id, episode_id)`.
- added `--demo-attribution-window-decisions N` to sum `delta_opp_hp` / `delta_self_hp` from each `demo_attributed_*` event row through the next `N` decision rows in the same episode.
- added `--demo-attribution-stop-at-next-event` for non-overlapping windows; default remains overlapping because projectiles can hit after a later input.
- new output sections:
  - `DEMO_ATTRIBUTION_SUMMARY`
  - `DEMO_ATTRIBUTED_BY_ACTION_WINDOW`
  - `DEMO_ATTRIBUTED_BY_ACTION_DX_WINDOW`
  - `DEMO_ATTRIBUTED_BY_R2_KW_WINDOW`
  - `DEMO_ATTRIBUTION_INPUT_TO_ENGINE_MISMATCH`

Validation:
- `python3 -m py_compile tools/analyze_rl_transitions.py` passed.
- `python3 tools/analyze_rl_transitions.py logs/rl-transitions-cpu-demo-v1-4-3-3.ndjson --demo-attribution-window-decisions 10 --limit 20` passed.
- `git diff --check -- tools/analyze_rl_transitions.py docs/plan-remote-rl-agent.md docs/remote-rl-agent-engineering-log.md` passed.

Smoke result:
- the short CPU-demo Ryu log produced `19` attributed events.
- with a 10-decision window, `fireball-hp` showed `6` events, `5` hit events, `1` punished/trade event, and `1` whiff/no-damage event.
- input-to-engine mismatch output confirmed the analyzer can show cases such as `neutral -> fireball-hp` and `forward -> fireball-hp`, which are exactly why engine attribution is needed for CPU-demo logs.

Follow-up:
- once the analyzer output looks stable on a longer CPU-demo log, wire the same delayed-credit outcome calculation into `tools/train_dqn_learner.py` reward shaping.

## 2026-04-28: Document Engine Move Attribution Expansion Method

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / move-label validation before extending demo attribution beyond Ryu

Files changed:
- `docs/rl-policy-action-taxonomy.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- preserve the discovered method for converting SF3 runtime attack identity into stable policy action / sub-action labels.
- make future non-Ryu expansion repeatable instead of relying on memory from the Ryu investigation.

Implementation notes:
- added `Engine Move Attribution Method` to the taxonomy document.
- documented the separation between input-based `requested_*` / `executed_*` fields and engine-observed `demo_attributed_*` fields.
- recorded the field roles:
  - `R2` / `routine_no[2]` is the primary active move / routine key.
  - `KW` / `kind_of_waza` encodes strength and normal/special punch/kick class.
  - `AK` / `current_attack` is useful for normal button identity.
  - `RS` / attack routine start is a timing hint, not a move id.
- documented the future-character workflow: source command slot -> `cmd_data.c` R2 -> `plpatXX.c` dispatch handler -> overlay validation -> runtime decoder promotion.

Validation:
- `git diff --check -- docs/rl-policy-action-taxonomy.md docs/plan-remote-rl-agent.md docs/remote-rl-agent-engineering-log.md` passed.

Follow-up:
- use the method to create per-character overlay identity draft tables before adding non-Ryu demo attribution code.

## 2026-04-28: Add Ryu Engine-Attributed Demo Action Fields

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / CPU-demo and human-demo bootstrapping data quality

Files changed:
- `src/rl/rl_session.c`
- `tools/rl_probe_server.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- preserve the existing input-based `requested_*` / `executed_*` action fields while adding a separate engine-observed move label for demo rows.
- make CPU-demo logs useful even when the CPU input pulse is not visible on the exact decision frame, by attributing the move from Ryu `routine_no[2]`, `kind_of_waza`, and `current_attack`.

Implementation notes:
- transition rows now include:
  - `demo_attributed_policy_action_id`
  - `demo_attributed_policy_sub_action_id`
  - `demo_attributed_routine2`
  - `demo_attributed_kind_of_waza`
  - `demo_attributed_current_attack`
  - `demo_attribution_source`
  - `demo_attribution_lag_frames`
- attribution only runs for demo execution sources (`human-demo` / `cpu-demo`) and currently only when the controlled character is Ryu (`agent_character_id = 2`).
- `demo_attribution_source = 1` means Ryu engine routine-start attribution (`R2 + KW`, including specials, throws, and provisional super-art routine IDs).
- `demo_attribution_source = 2` means Ryu normal-attack attribution from `current_attack` / normal `kind_of_waza`; normal stance/jump class is best-effort and uses the sampled input class when available.
- `learner_replay_row()` preserves the new fields so offline analyzers or later demo-specific training tools can consume them.

Validation:
- `git diff --check -- src/rl/rl_session.c tools/rl_probe_server.py` passed.
- `python3 -m py_compile tools/rl_probe_server.py` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed and produced `build/mister-telemetry-package`.

Follow-up:
- collect a short `cpu-demo` Ryu log and compare input-based action counts with `demo_attributed_*` counts.
- verify normal stance/jump attribution against overlay video before using normal `demo_attributed_*` labels as supervised targets.
- add non-Ryu character mappings only after their `routine_no[2]` / `kind_of_waza` tables are validated.

## 2026-04-28: Add Fight Overlay Attack Identity Probe Fields

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / move-label validation before transition schema expansion

Files changed:
- `src/rl/rl_observation.h`
- `src/rl/rl_observation.c`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- expose self-side SF3 attack identity candidate fields on the Fight debug overlay before adding them to transition logs.
- support visual validation that `routine_no[2]`, `current_attack`, and `kind_of_waza` correlate with real moves during CPU-demo / human-demo tests.

Implementation notes:
- `RLObservationV1` now captures `self_kind_of_waza` and `opp_kind_of_waza` from `plw[*].wu.kind_of_waza`.
- the Fight overlay adds `SATT R2<routine2> AK<current_attack> KW<kind_of_waza> RS<attack_routine_started>`.
- no UDP observation payload, transition row, learner state, or replay schema was changed.

Validation:
- `git diff --check` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed and produced `build/mister-telemetry-package`.

Follow-up:
- validate the overlay values against visible normals, specials, throws, and projectiles.
- only after validation, decide which of these fields should be promoted into transition logs and/or learner observations.

Runtime finding:
- `AK` / `current_attack` is useful for normal attack button identity only:
  - jump / stand / crouch normals show `010/020/040` for `LP/MP/HP` and `100/200/400` for `LK/MK/HK`.
  - specials do not currently use `AK` as a stable move identity field.
- `RS` / `self_attack_routine_started` can become nonzero during attacks, but it is not stable enough to identify which attack was performed.
- `KW` / `kind_of_waza` appears to encode attack class and strength:
  - `00/02/04` => `LP/MP/HP`
  - `01/03/05` => `LK/MK/HK`
  - `08/0A/0C` => punch-strength specials such as Hadouken and Shoryuken (`LP/MP/HP`)
  - `09/0B/0D` => kick-strength specials such as Tatsumaki Senpukyaku (`LK/MK/HK`)
- implication: `KW` is strong for normal/special strength and punch-vs-kick class, but it cannot distinguish Hadouken from Shoryuken by itself. Move identity likely needs `routine_no[2]` (`R2`) plus character id, with `KW` providing strength/category.
- `R2` / `routine_no[2]` appears to identify the active attack or motion routine, not only named special moves:
  - `16` => Hadouken
  - `17` => Shoryuken
  - `18` => Tatsumaki Senpukyaku
  - `14` => grab / catch startup path
  - `2` => throw
- updated implication: move labeling should treat `R2` as the primary move/routine id and `KW` as the strength/category modifier. The candidate transition identity tuple is now `character_id + R2 + KW`, with `AK` used mainly to label normals when helpful.
- added a provisional Ryu `R2/KW/AK` overlay identity table to `docs/rl-policy-action-taxonomy.md`:
  - confirmed normals use `AK` for button identity and `KW=00/02/04` for punches, `KW=01/03/05` for kicks.
  - confirmed Ryu specials use `R2=16/17/18` for Hadouken/Shoryuken/Tatsumaki and `KW=08/0A/0C` or `09/0B/0D` for strength/category.
  - recorded `R2=2` for completed throw and `R2=14` for grab/catch path.
  - left normal stance/jump `R2`, super-art `KW`, Joudan Sokutou Geri, and Air Tatsumaki as validation TODOs.

## 2026-04-28: Add CPU-Demo Transition Recording Mode

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / demo bootstrapping data collection

Files changed:
- `src/args.c`
- `src/port/sdl/sdl_app.c`
- `src/rl/rl_session.h`
- `src/rl/rl_session.c`
- `src/sf33rd/Source/Game/engine/plmain.c`
- `vendor/Menu_MiSTer/menu.sv`
- `vendor/Main_MiSTer/thirdsarm_wrapper.cpp`
- `docs/config.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- allow the selected RL side to be driven by the built-in game CPU while exporting learner-ingestible transition rows.
- provide an automatic high-volume demo source for movement, guard, and punish samples without requiring manual human input.
- keep the existing `remote` and `human-demo` control-source behavior unchanged.

Implementation notes:
- extended `rl-control-source` / `--rl-control-source` from `remote|human-demo` to `remote|human-demo|cpu-demo`.
- `cpu-demo` routes the selected `rl-player` side as CPU-controlled in the VS operator setup.
- CPU-demo transition recording happens from `Player_move()` after the CPU/player pipeline has resolved `wk->cp->sw_lvbt`, so the logged action reflects the input actually used by the game for that player.
- CPU-demo rows set `execution_source = 5`; requested/executed policy metadata is identical because the action was local to the game.
- the demo policy mapper is shared with human-demo and labels walk, guard, stand/crouch normals, jump attacks, throws, and forward+HP command-normal from the resolved input.
- OSD `RL Control (Restart)` now uses status bits `[54:53]` and exposes `Remote, Human Demo, CPU Demo`.
- overlay labels show `P1CD` / `P2CD` for CPU-demo mode.

Validation:
- `git diff --check` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed and produced `build/mister-telemetry-package`.
- `tools/mister-wrapper/build-hps.sh` passed and produced `build/mister-wrapper-hps/MiSTer_3S-ARM`.
- wrapper-core Quartus rebuild was not run in this pass; the `vendor/Menu_MiSTer/menu.sv` OSD row needs wrapper core/package/deploy before the three-value `RL Control` menu appears on hardware.

Follow-up:
- build/package wrapper core before expecting the three-value OSD row on hardware.
- collect a short `cpu-demo` log and confirm rows contain `execution_source = 5` and useful guard/back/forward samples before using it for DQN pretraining.
- define replay-buffer mixing rules for remote, human-demo, and CPU-demo rows.

## 2026-04-28: Add Human-Demo Transition Recording Mode

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / human-demo bootstrapping data collection

Files changed:
- `src/configuration.h`
- `src/args.c`
- `src/main.c`
- `src/port/config/config.h`
- `src/port/config/config.c`
- `src/port/sdl/sdl_app.c`
- `src/rl/rl_session.h`
- `src/rl/rl_session.c`
- `tools/rl_probe_server.py`
- `docs/config.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- allow a human to control the RL-selected side against CPU while exporting learner-ingestible transition rows.
- collect cleaner examples of guard/back/forward/spacing behavior than the current tabular/DQN policies produce.
- keep the existing remote policy path unchanged for normal `remote` control-source runs.

Implementation notes:
- added `rl-control-source = remote|human-demo` and `--rl-control-source`.
- `remote` is the default and preserves current remote/tabular/DQN behavior.
- `human-demo` skips all RL input overrides and records the selected `rl-player` side's actual `p1sw_buff` / `p2sw_buff` input at the usual decision cadence.
- human-demo rows set `execution_source = 4`, with requested and executed policy metadata equal because the player action is already local.
- the first human input mapper converts raw inputs into the current high-level action taxonomy:
  - `forward` / `back` for plain walk inputs
  - `guard-stand` for back-only input when latest opponent routine attack state is active within short/mid range
  - `guard-crouch` for down-back without attack
  - stand/crouch normals, jump attacks, throws, and forward+HP command-normal from button/direction combinations
- with `rl-network = on`, the UDP hello/transition-batch path can still upload completed episodes, but human-demo does not send OBS/action inference packets.
- overlay labels show `P1D` / `P2D` for human-demo mode.
- `learner_replay_row()` now preserves `requested_action_wire` and `execution_source` so later tools can filter human-demo versus remote-agent rows.

Validation:
- `git diff --check` passed.
- `python3 -m py_compile tools/rl_probe_server.py` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed and created `build/mister-telemetry-package`.

Follow-up:
- define replay-buffer mixing rules for human-demo episodes versus remote-agent episodes.
- validate the first back-vs-guard heuristic against a short human-vs-CPU collection log and adjust labels if it over-tags retreat as guard.

## 2026-04-28: Add MiSTer OSD Control For RL Control Source

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / human-demo bootstrapping data collection

Files changed:
- `vendor/Menu_MiSTer/menu.sv`
- `vendor/Main_MiSTer/thirdsarm_wrapper.cpp`
- `docs/config.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- make `rl-control-source = remote|human-demo` switchable from the MiSTer OSD instead of requiring manual config edits.

Implementation notes:
- added `RL Settings -> RL Control (Restart), Remote, Human Demo` on status bit `[53]`.
- wrapper defaults generated configs to `rl-control-source = remote`.
- wrapper reads/writes `rl-control-source`, seeds the OSD status bit at launch/restart, and logs the selected mode.
- wrapper strips incoming `--rl-control-source` and injects the persisted OSD/config value into the child runtime when RL agent mode is enabled.
- the setting remains launch-time and requires the existing `Restart` action.

Validation:
- `git diff --check` passed.
- `tools/mister-wrapper/build-hps.sh` first failed under sandboxed network with `Could not resolve host: github.com`.
- reran `tools/mister-wrapper/build-hps.sh` with approved network access; HPS wrapper build passed and produced `build/mister-wrapper-hps/MiSTer_3S-ARM`.
- wrapper-core Quartus build was not run in this pass; `vendor/Menu_MiSTer/menu.sv` changes still require a wrapper core rebuild/package before the new OSD row appears on hardware.

Follow-up:
- rebuild/package wrapper HPS and wrapper core before expecting the new OSD row on hardware.
- hardware-test that `RL Control (Restart)` writes `rl-control-source = remote|human-demo` and that runtime overlay switches between `P1C/P2C` and `P1D/P2D` after Restart.

## 2026-04-28: Add DQN Spacing Reward Shaping

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / Phase 1 basic-action DQN reward shaping

Files changed:
- `tools/train_dqn_learner.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- give `forward` and `back` immediate offline DQN reward signal when they improve spacing toward a configured target band.
- keep the change local to offline DQN reward shaping so live tabular/DQN action execution, C-side transition schema, and current probe-server macros do not change.
- defer walk macros and finer distance buckets until the spacing-shaping A/B result shows whether movement credit alone helps.

Implementation notes:
- added spacing-shaping CLI knobs:
  - `--reward-spacing-target-min-dx`
  - `--reward-spacing-target-max-dx`
  - `--reward-spacing-improve-bonus`
  - `--reward-spacing-worsen-cost`
  - `--reward-spacing-maintain-bonus`
  - `--reward-spacing-threat-back-bonus`
- spacing shaping applies only to `forward` / `back` action starts (`executed_policy_action_step == 0`).
- the trainer compares the action-start `obs_abs_dx` against the next decision boundary row and measures distance to the configured target band.
- clean movement that moves closer to the target band can receive an improve bonus; clean movement that moves farther away can receive a worsen cost; clean movement that stays inside the band can receive a maintain bonus.
- `back` can receive an extra close-range threat bonus when the opponent is already in the validated attack routine and the next decision boundary increases `obs_abs_dx`.
- all spacing adjustments require a no-self-damage movement window; if movement gets punished, natural HP-delta loss remains the primary signal.
- trainer metadata records spacing config and `reward_spacing_stats`; stdout prints `spacing_bonus`, `spacing_cost`, `spacing_net`, and `DQN diagnostics spacing_shape=...`.

Validation:
- `python3 -m py_compile tools/train_dqn_learner.py` passed.
- `python3 tools/train_dqn_learner.py --help | rg "reward-spacing"` showed all six new spacing-shaping CLI flags.
- spacing-shaping smoke passed:
  - `python3 tools/train_dqn_learner.py logs/rl-transitions-basic-v1-cpu-lv4-4-3-3.ndjson --model-dir /tmp/rl-dqn-spacing-smoke --model-version 1 --limit 7000 --drop-initial-episodes-per-run 3 --steps 5 --batch-size 16 --hidden-sizes 16 --log-interval 0 --eval-limit 500 --actions forward,back,guard-stand,guard-crouch,stand-mk,crouch-mk,jump-forward-mk --reward-risk-profile all-attacks --reward-risk-window-decisions 15 --reward-attack-no-damage-cost 1.0 --reward-attack-punished-cost 2.0 --reward-jump-attack-no-damage-extra-cost 2.0 --reward-jump-attack-punished-extra-cost 2.0 --reward-guard-success-bonus 2.0 --reward-guard-success-window-decisions 15 --reward-guard-threat-max-dx 144 --reward-passive-guard-cost 0.5 --reward-far-guard-cost 0.5 --reward-spacing-target-min-dx 50 --reward-spacing-target-max-dx 120 --reward-spacing-improve-bonus 0.5 --reward-spacing-worsen-cost 0.3 --reward-spacing-maintain-bonus 0.2 --reward-spacing-threat-back-bonus 0.3`
  - published `rows=5061 raw_rows=7000 drop_ep=3/1939`, `experiences=599`, `spacing_bonus=21.6`, `spacing_cost=5.7`, `spacing_net=15.9`.
  - printed `DQN diagnostics spacing_shape=target:50-120 improve:27/13.5 maintain:36/7.2 worsen:19/5.7 threat_back:3/0.9 net:15.9`, confirming the spacing reward fired and was accounted separately from guard/risk shaping.
  - the five-step smoke still collapsed to `crouch-mk`; this is only a wiring smoke, not an offline quality comparison.

Follow-up:
- compare basic-only DQN with and without spacing shaping on `logs/rl-transitions-basic-v1-cpu-lv4-4-3-3.ndjson`.
- review walk-forward/back macro actions only after the P0 spacing-shaping comparison shows whether movement credit shifts greedy policy away from passive guard/attack-only choices.
- review 5-level distance buckets after checking whether current DQN features and sample count are enough for the Phase 1 basic-only action set.
- review live data collection settings, especially repeat-delay neutral pollution, before collecting a new long-run basic-only dataset.

## 2026-04-28: Refine DQN Guard Cost And Episode Drop

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / Phase 1 basic-action DQN reward shaping

Files changed:
- `tools/train_dqn_learner.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- avoid double-punishing wrong guard decisions that already took natural HP-delta damage.
- make passive/far guard costs represent empty guard only, not failed guard.
- allow DQN training to drop the first few episodes from each run when early live collection is polluted by fallback repeat-delay neutral behavior.

Implementation notes:
- `reward_guard_adjustment()` now computes the guard lookahead window once and applies passive/far guard costs only when that window has no self HP damage.
- successful guard bonus still requires opponent attack state, close/mid threat range, and the same no-self-damage window.
- added `--drop-initial-episodes-per-run`; it drops the first `N` unique `(run_id, episode_id)` episodes encountered for each run before building DQN experiences, stats, metadata, and greedy diagnostics.
- trainer metadata records `rows_read_before_episode_drop`, `drop_initial_episodes_per_run`, `dropped_initial_episode_rows`, and `dropped_initial_episodes`.
- trainer stdout now prints filtered rows, raw rows, and dropped episode/row counts as `rows=<filtered> raw_rows=<raw> drop_ep=<episodes>/<rows>`.

Validation:
- `python3 -m py_compile tools/train_dqn_learner.py` passed.
- guard/drop smoke passed:
  - `python3 tools/train_dqn_learner.py logs/rl-transitions-basic-v1-cpu-lv4-4-3-3.ndjson --model-dir /tmp/rl-dqn-guard-drop-smoke.<tmp> --model-version 1 --limit 7000 --drop-initial-episodes-per-run 3 --steps 5 --batch-size 16 --hidden-sizes 16 --log-interval 0 --eval-limit 500 --actions forward,back,guard-stand,guard-crouch,stand-mk,crouch-mk,jump-forward-mk --reward-risk-profile all-attacks --reward-risk-window-decisions 15 --reward-attack-no-damage-cost 1.0 --reward-attack-punished-cost 2.0 --reward-jump-attack-no-damage-extra-cost 2.0 --reward-jump-attack-punished-extra-cost 2.0 --reward-guard-success-bonus 2.0 --reward-guard-success-window-decisions 15 --reward-guard-threat-max-dx 144 --reward-passive-guard-cost 0.5 --reward-far-guard-cost 0.5`
  - published `rows=5061 raw_rows=7000 drop_ep=3/1939`, confirming the first three episodes in the run were dropped before experience building.
  - guard/risk diagnostics still fired: `risk_shape=... jump:196.0/56.0` and `guard_shape=success:16/32.0 passive:43/21.5 far:36/18.0 net:-7.5`.

Follow-up:
- use `--drop-initial-episodes-per-run 3` in the next A/B/C comparison on `rl-transitions-basic-v1-cpu-lv4-4-3-3.ndjson`.
- if later collection removes or lowers `--policy-repeat-delay-ms`, rerun the same comparison with and without episode dropping to confirm whether the filter is still needed.

## 2026-04-28: Add DQN Jump-Attack Risk Extras

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / Phase 1 basic-action DQN reward shaping

Files changed:
- `tools/train_dqn_learner.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- make jump-in whiffs, especially `jump-forward-mk`, more expensive than ground poke whiffs during offline DQN training.
- model the practical SF3 risk that a mistimed jump has high commitment, cannot guard in the air, and can be anti-aired or punished on landing.
- keep useful jump-ins available by adding extra cost only when the jump attack produces no opponent HP damage in the lookahead window.

Implementation notes:
- added `JUMP_ATTACK_RISK_ACTIONS` for `jump-forward-mk`, `jump-forward-hk`, `jump-neutral-hk`, and `jump-back-hk`.
- added two positive-cost CLI knobs:
  - `--reward-jump-attack-no-damage-extra-cost`
  - `--reward-jump-attack-punished-extra-cost`
- jump extras apply only under `--reward-risk-profile all-attacks` and stack on top of the generic all-attacks no-damage / punished costs.
- trainer metadata now records jump extra cost config and per-run totals through `reward_risk_stats`.
- stdout prints `DQN diagnostics risk_shape=... jump:<no_damage_extra>/<punished_extra>` for quick smoke checks.

Validation:
- `python3 -m py_compile tools/train_dqn_learner.py` passed.
- jump-risk smoke passed:
  - `python3 tools/train_dqn_learner.py logs/rl-transitions-basic-v1-cpu-lv4-4-3-3.ndjson --model-dir /tmp/rl-dqn-jump-risk-smoke.<tmp> --model-version 1 --limit 5000 --steps 5 --batch-size 16 --hidden-sizes 16 --log-interval 0 --eval-limit 500 --actions forward,back,guard-stand,guard-crouch,stand-mk,crouch-mk,jump-forward-mk --reward-risk-profile all-attacks --reward-risk-window-decisions 15 --reward-attack-no-damage-cost 1.0 --reward-attack-punished-cost 2.0 --reward-jump-attack-no-damage-extra-cost 2.0 --reward-jump-attack-punished-extra-cost 2.0 --reward-guard-success-bonus 2.0 --reward-guard-success-window-decisions 15 --reward-guard-threat-max-dx 144 --reward-passive-guard-cost 0.2 --reward-far-guard-cost 0.5`
  - published `risk_cost=508.0`, with `DQN diagnostics risk_shape=... attack:240.0/140.0 ... jump:94.0/34.0`, confirming jump extras fired separately from generic attack costs.

Follow-up:
- compare Phase 1 basic-only DQN variants:
  - A: pure HP-delta baseline.
  - B: guard bonus + generic all-attacks risk.
  - C: guard bonus + generic all-attacks risk + jump-attack extra cost.
- if C avoids jump spam without collapsing to passive guard or crouch MK, use the same cost profile for the next longer basic-only run.

## 2026-04-28: Add Live Tabular Action Subsets

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / Phase 1 basic-action data collection

Files changed:
- `tools/rl_probe_server.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- collect a clean long-run transition log with only basic actions such as forward/back movement, stand/crouch guard, standing MK, crouching MK, and jump-forward MK.
- avoid hard-coding one temporary curriculum action set into the probe server.
- prevent a fresh model directory from bootstrapping a default full-action tabular actor before the learner publishes the intended subset.

Implementation notes:
- added `--tabular-actions`, a comma-separated live tabular action subset.
- the tabular learner now trains only on the configured subset and publishes the same subset in tabular actor manifests.
- `ActorModelStore` now accepts initial actions/fallback policy, so bootstrap `current.json` uses the configured tabular subset when `--policy tabular` starts from an empty model directory.
- startup validation rejects tabular actor runs when `--tabular-fallback-policy` resolves to an action outside `--tabular-actions`; this avoids silently mixing HP/full-action fallback into a basic-only curriculum log.
- learner publish metadata records `tabular_actions` for easier post-run audit.

Validation:
- `python3 -m py_compile tools/rl_probe_server.py` passed.
- `python3 tools/rl_probe_server.py --help` shows `--tabular-actions`.
- invalid action validation passed:
  - `python3 tools/rl_probe_server.py --policy tabular --tabular-actions forward,bad --learner-only`
  - exited with `Unknown action(s) for --tabular-actions: bad`.
- subset/fallback validation passed:
  - `python3 tools/rl_probe_server.py --policy tabular --tabular-actions forward,back --tabular-fallback-policy hp --learner-only`
  - exited with `--tabular-fallback-policy hp resolves to stand-hp, which is not in --tabular-actions`.
- non-tabular scripted fallback validation passed:
  - `python3 tools/rl_probe_server.py --policy tabular --tabular-actions forward,back,tatsu-mk --tabular-fallback-policy tatsu --learner-only`
  - exited with `--tabular-fallback-policy tatsu is not a tabular action alias`.
- bootstrap manifest smoke passed:
  - instantiated `ActorModelStore` with `policy=tabular`, actions `forward,back,guard-stand,guard-crouch,stand-mk,crouch-mk,jump-forward-mk`, and fallback `stand-mk`.
  - generated `current.json` contained only that action subset and `fallback_policy=stand-mk`.

Follow-up:
- run a fresh basic-only hard-CPU long-run log with:
  - `--tabular-actions forward,back,guard-stand,guard-crouch,stand-mk,crouch-mk,jump-forward-mk`
  - `--tabular-fallback-policy stand-mk`
- train Phase 1 DQN from that basic-only log before reintroducing fireball, shoryuken, tatsu, or HK jump attacks.

## 2026-04-28: Make Offline DQN Replay Decision-Level

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / Phase 1 defense curriculum

Files changed:
- `tools/train_dqn_learner.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- stop treating macro continuation rows (`executed_policy_action_step > 0`) as independent DQN decisions.
- credit HP-delta reward from guard/fireball/shoryuken/tatsu/jump macro continuation rows back to the originating step-0 decision.
- make guard reward shaping visible to the model instead of diluting it across forced guard continuation frames.

Implementation notes:
- `build_experiences()` now creates DQN experiences only for recognized included action rows with `executed_policy_action_step == 0`.
- included macro continuation rows no longer create experiences; nonzero reward on those rows is added to the most recent included step-0 experience.
- step-0 experience `next_state` is updated when the next step-0 action boundary is reached, and the final included experience in each episode is closed with the episode's last row as terminal next state.
- excluded explicit actions still reset delayed-credit attribution so their later reward is not credited to a previous included action.
- `BuildDiagnostics` now records macro continuation rows, continuation reward rows/sum, continuation delayed credits, and uncredited continuation rewards.
- trainer stdout now prints `cont=<rows>` and `cont_rew=<scaled_reward>` beside included/excluded counts.

Validation:
- `python3 -m py_compile tools/train_dqn_learner.py` passed.
- decision-level replay smoke:
  - `python3 tools/train_dqn_learner.py logs/rl-transitions-actionset-v4-hardcpu-v1-4-3-3.ndjson --model-dir /tmp/rl-dqn-decision-replay-smoke --model-version 1 --limit 5000 --steps 5 --batch-size 16 --hidden-sizes 16 --log-interval 0 --eval-limit 500 --actions forward,back,guard-stand,guard-crouch,stand-hp,crouch-mk --reward-risk-profile all-attacks --reward-risk-window-decisions 15 --reward-attack-no-damage-cost 0.5 --reward-attack-punished-cost 2.0 --reward-guard-success-bonus 2.0 --reward-guard-success-window-decisions 15 --reward-guard-threat-max-dx 144 --reward-passive-guard-cost 0.2 --reward-far-guard-cost 0.5`
  - published `experiences=184`, `included=184`, `cont=195`, `cont_rew=-0.380`, compared with the previous row-level smoke that produced `experiences=379`; this confirms guard macro continuation rows are no longer independent DQN decisions.
  - guard-shaping diagnostics still fired: `guard_shape=success:10/20.0 passive:16/3.2 far:10/5.0 net:11.8`.

Follow-up:
- rerun full Phase 1 guard-shaping training because the previous `model/dqn-phase1-basic-c15-guard-shaping` was produced by the older row-level replay builder.
- compare the rebuilt model against `model/dqn-phase1-basic-c15`; this is the first comparison where guard shaping should have a fair signal-to-noise ratio.
- if the rebuilt model still keeps `atk1_close` on `stand-hp`, increase guard success bonus or collect scripted guard success data before broadening the action set.

## 2026-04-28: Add Offline DQN Guard Reward Shaping

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / Phase 1 defense curriculum

Files changed:
- `tools/train_dqn_learner.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- give offline DQN training a positive signal for successful `guard-stand` / `guard-crouch` decisions under opponent strike threat.
- add small costs for passive or far guard so Phase 1 models do not learn to hold guard as a universal idle/default action.
- keep the experiment local to the offline trainer; no C-side transition schema or MiSTer runtime behavior changed.

Implementation notes:
- added guard shaping config:
  - `--reward-guard-success-bonus`
  - `--reward-guard-success-window-decisions`
  - `--reward-guard-threat-max-dx`
  - `--reward-passive-guard-cost`
  - `--reward-far-guard-cost`
- guard success bonus applies only to `guard-stand` / `guard-crouch` action starts when:
  - `executed_policy_action_step == 0`
  - `obs_opp_routine_attack_state != 0`
  - `obs_abs_dx <= reward_guard_threat_max_dx`
  - the guard-success lookahead window has no `delta_self_hp`
- passive/far guard costs also apply only on guard action starts, avoiding repeated macro-step reward/cost for the six-step guard macros.
- trainer metadata now records guard shaping config and `reward_guard_stats`.
- trainer stdout now prints `guard_bonus`, `guard_cost`, `guard_net`, and a `DQN diagnostics guard_shape=...` summary.

Validation:
- `python3 -m py_compile tools/train_dqn_learner.py` passed.
- guard-shaping smoke:
  - `python3 tools/train_dqn_learner.py logs/rl-transitions-actionset-v4-hardcpu-v1-4-3-3.ndjson --model-dir /tmp/rl-dqn-guard-shaping-smoke --model-version 1 --limit 5000 --steps 5 --batch-size 16 --hidden-sizes 16 --log-interval 0 --eval-limit 500 --actions forward,back,guard-stand,guard-crouch,stand-hp,crouch-mk --reward-risk-profile all-attacks --reward-risk-window-decisions 15 --reward-attack-no-damage-cost 0.5 --reward-attack-punished-cost 2.0 --reward-guard-success-bonus 2.0 --reward-guard-success-window-decisions 15 --reward-guard-threat-max-dx 144 --reward-passive-guard-cost 0.2 --reward-far-guard-cost 0.5`
  - published `actions=6`, `risk_cost=406.0`, `guard_bonus=20.0`, `guard_cost=8.2`, `guard_net=11.8`, and printed `guard_shape=success:10/20.0 passive:16/3.2 far:10/5.0 net:11.8`.

Follow-up:
- run the full Phase 1 guard-shaping command on mixed old-v4 + hardcpu-v1 logs.
- compare against `model/dqn-phase1-basic-c15` and check whether `atk1_close` / `atk1_mid` shift from `stand-hp` to guard while `atk0_far` stops selecting guard as the dominant default.
- if guard shaping works offline, collect a fresh Phase 1 live log before considering a broader action set.

## 2026-04-27: Add DQN Action Subsets And Collapse Diagnostics

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / first ML baseline

Files changed:
- `tools/train_dqn_learner.py`
- `tools/compare_dqn_models.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- allow DQN/MLP Q models to train on a smaller action subset from existing transition logs before collecting more MiSTer data.
- diagnose the observed greedy-policy collapse toward one normal attack before live DQN testing.
- avoid reward leakage when an explicit action is excluded from the subset.

Implementation notes:
- `tools/train_dqn_learner.py` adds `--actions`, a comma-separated DQN action subset that is published into the actor manifest.
- excluded explicit actions are counted and clear the delayed-credit pointer, so later neutral/recovery HP deltas are not credited to the previous included action.
- trainer metadata now records:
  - `actions_subset` and `actions_subset_size`
  - `build_diagnostics`
  - observed all-action counts/rewards
  - greedy top-1/top-2/top-3 counts
  - greedy mean Q per action
  - greedy top action and top-action rate
- trainer stdout now includes included/excluded counts, excluded reward sum, per-action `count/reward/mean`, top-2/top-3 summaries, and a collapse warning controlled by `--collapse-warning-threshold`.
- `tools/compare_dqn_models.py` now prints model action-count, top greedy action/rate, collapse status, and selected-Q mean for the printed top actions.

Validation:
- `python3 -m py_compile tools/train_dqn_learner.py tools/compare_dqn_models.py` passed.
- help smoke confirmed new trainer flags:
  - `--actions`
  - `--diagnostic-top-n`
  - `--collapse-warning-threshold`
- subset baseline smoke:
  - `python3 tools/train_dqn_learner.py logs/rl-transitions-actionset-v4-4-3-3.ndjson --model-dir /tmp/rl-dqn-subset-a-smoke --model-version 1 --limit 5000 --steps 5 --batch-size 16 --log-interval 0 --actions forward,back,guard-stand,guard-crouch,stand-hp,crouch-mk,fireball,shoryuken-mp,tatsu-mk,jump-forward-hk --reward-risk-profile none --diagnostic-top-n 6`
  - published `actions=10`, `included=863`, `excluded=381`, and warned `stand-hp 99.2%`.
- subset all-attacks smoke:
  - `python3 tools/train_dqn_learner.py logs/rl-transitions-actionset-v4-4-3-3.ndjson --model-dir /tmp/rl-dqn-subset-c-smoke --model-version 1 --limit 5000 --steps 5 --batch-size 16 --log-interval 0 --actions forward,back,guard-stand,guard-crouch,stand-hp,crouch-mk,fireball,shoryuken-mp,tatsu-mk,jump-forward-hk --reward-risk-profile all-attacks --diagnostic-top-n 6`
  - published `actions=10`, `risk_cost=357.5`, `included=863`, `excluded=381`, and warned `stand-hp 99.2%`.
- compare smoke:
  - `python3 tools/compare_dqn_models.py logs/rl-transitions-actionset-v4-4-3-3.ndjson --tail-rows 1000 --model A=/tmp/rl-dqn-subset-a-smoke --model C=/tmp/rl-dqn-subset-c-smoke --top-n 6`
  - printed action-count, selected-Q mean, and `collapse=WARN` for both subset smoke models.

Follow-up:
- run full A/B/C subset models with enough steps to decide whether the collapse is data, reward, or action-space driven.
- if subset models still collapse, collect targeted curriculum logs instead of taking DQN live.

## 2026-04-27: Add Offline DQN Reward-Risk A/B/C Profiles

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / first ML baseline

Files changed:
- `tools/rl_probe_server.py`
- `tools/train_dqn_learner.py`
- `tools/compare_dqn_models.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- train baseline and reward-risk DQN/MLP Q models from the same transition log so Shoryuken no-damage costs can be compared without changing the live environment.
- avoid ambiguous command names by using positive `cost` parameters rather than negative `penalty` arguments.
- detect whether reducing empty Shoryuken merely shifts the model toward other empty attacks.

Implementation notes:
- `learner_replay_row()` now preserves requested/executed policy action IDs, sub-action IDs, and macro steps so offline DQN replay can use high-level action attribution instead of falling back to wire-only decoding.
- `tools/train_dqn_learner.py` adds:
  - `--reward-risk-profile none`
  - `--reward-risk-profile shoryuken-only`
  - `--reward-risk-profile all-attacks`
  - `--reward-risk-window-decisions`
  - `--reward-attack-no-damage-cost`
  - `--reward-attack-punished-cost`
  - `--reward-shoryuken-no-damage-extra-cost`
  - `--reward-shoryuken-punished-extra-cost`
- risk costs are positive raw reward units, subtracted before `--reward-scale`.
- `shoryuken-only` applies only Shoryuken no-damage / punished extra costs; `all-attacks` applies generic attack no-damage / punished costs to attack actions and adds the Shoryuken extras on top.
- terminal wins inside the lookahead window suppress risk costs so a harmless post-KO or already-winning action is not punished.
- `tools/compare_dqn_models.py` compares repeated `--model LABEL=path` DQN manifests against the same transition observations and reports greedy distributions overall plus `atk0/atk1 x close/mid/far`.

Validation:
- `python3 -m py_compile tools/rl_probe_server.py tools/train_dqn_learner.py tools/compare_dqn_models.py` passed.
- baseline smoke:
  - `python3 tools/train_dqn_learner.py logs/rl-transitions-actionset-v3-4-3-3.ndjson --model-dir /tmp/rl-dqn-ab-baseline-smoke --model-version 1 --limit 2000 --steps 5 --batch-size 16 --log-interval 0 --reward-risk-profile none`
  - published `risk=none risk_cost=0.0`.
- Shoryuken-only smoke:
  - `python3 tools/train_dqn_learner.py logs/rl-transitions-actionset-v3-4-3-3.ndjson --model-dir /tmp/rl-dqn-ab-shoryu-smoke --model-version 1 --limit 2000 --steps 5 --batch-size 16 --log-interval 0 --reward-risk-profile shoryuken-only`
  - published `risk=shoryuken-only risk_cost=2.0`.
- all-attacks smoke:
  - `python3 tools/train_dqn_learner.py logs/rl-transitions-actionset-v3-4-3-3.ndjson --model-dir /tmp/rl-dqn-ab-allattacks-smoke --model-version 1 --limit 2000 --steps 5 --batch-size 16 --log-interval 0 --reward-risk-profile all-attacks`
  - published `risk=all-attacks risk_cost=70.0`.
- larger 10k one-step smoke produced nonzero and profile-separated risk costs:
  - Shoryuken-only `risk_cost=31.0`
  - all-attacks `risk_cost=806.0`
- compare smoke:
  - `python3 tools/compare_dqn_models.py logs/rl-transitions-actionset-v3-4-3-3.ndjson --tail-rows 1000 --model A=/tmp/rl-dqn-ab-baseline-smoke --model B=/tmp/rl-dqn-ab-shoryu-smoke --model C=/tmp/rl-dqn-ab-allattacks-smoke --top-n 5`
  - printed overall and threat/distance greedy action distributions plus pairwise action-change counts.

Follow-up:
- run full A/B/C DQN training on the frozen actionset-v4 log with enough steps to make the comparison meaningful.
- compare Shoryuken selection rate and total attack selection rate before choosing any reward-risk profile for live testing.
- do not treat offline greedy distribution as live winrate; validate the selected DQN live for at least 50-100 rounds.

## 2026-04-27: Split Normal IDs By Stance And Add Normal Probes

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / action namespace refinement

Files changed:
- `tools/rl_probe_server.py`
- `tools/analyze_rl_transitions.py`
- `docs/rl-policy-action-taxonomy.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- add the requested standing LP/MP/LK/MK/HK and crouching LK/MK/HK probe actions.
- avoid ambiguity between standing MK and crouching MK by making normal actions stance-specific in policy metadata.

Implementation notes:
- split universal normal metadata into:
  - `6`: `stand_normal`
  - `15`: `crouch_normal`
- added learner/scripted fixed actions `stand-lp`, `stand-mp`, `stand-hp`, `stand-lk`, `stand-mk`, `stand-hk`, `crouch-lk`, `crouch-mk`, and `crouch-hk`.
- the legacy scripted `hp` policy remains supported as an alias for `stand-hp`, so existing probe commands using `--tabular-fallback-policy hp` continue to work.
- bumped `ACTION_SET_VERSION` from `3` to `4` so old tabular/DQN manifests are ignored instead of mixing generic normal metadata with stance-specific normals.
- `tools/analyze_rl_transitions.py` default action list now includes the stance-specific normals.

Validation:
- `python3 -m py_compile tools/rl_probe_server.py tools/analyze_rl_transitions.py tools/train_dqn_learner.py` passed.
- synthetic metadata smoke confirmed standing normals stamp `stand_normal/<button>` and crouching normals stamp `crouch_normal/<button>`.
- synthetic wire smoke confirmed standing normals use bare button wires and crouching normals use `down+button` wires.
- synthetic transition decode smoke confirmed policy metadata maps back to `stand-lp`, `stand-mp`, `stand-hp`, `stand-lk`, `stand-mk`, `stand-hk`, `crouch-lk`, `crouch-mk`, and `crouch-hk`.
- `python3 tools/rl_probe_server.py --help` shows the new stance-specific normal scripted policies and fallback-policy choices.
- analyzer tail smoke passed on `logs/rl-transitions-defense-v1-4-3-3.ndjson --tail-rows 1000`; old `hp` rows now decode as `stand-hp` through the stance-specific metadata map.
- one-step offline DQN smoke passed against `logs/rl-transitions-defense-v1-4-3-3.ndjson --limit 2000`; the published manifest carried `action_set_version=4` and all nine stance-specific normal actions.

Follow-up:
- start a fresh model/log for live testing because this is an action-set version bump.
- watch whether the larger normal action set makes tabular exploration too sparse; if it does, use DQN/offline pretraining or a smaller curriculum subset before adding more moves.

## 2026-04-27: Split Jump Attack IDs By Direction

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / action namespace refinement

Files changed:
- `tools/rl_probe_server.py`
- `tools/analyze_rl_transitions.py`
- `docs/rl-policy-action-taxonomy.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- make jump attacks distinguishable by jump direction in transition logs and learner action attribution.
- add the first HK jump-kick probes for forward, neutral, and back jumps.

Implementation notes:
- split the old universal `jump_attack=12` taxonomy into direction-specific IDs:
  - `12`: `jump_attack_forward`
  - `13`: `jump_attack_neutral`
  - `14`: `jump_attack_back`
- `jump-forward-mk` now stamps `jump_attack_forward/mk` instead of generic `jump_attack/mk`.
- added `jump-forward-hk`, `jump-neutral-hk`, and `jump-back-hk`, all using `sub_action_id=6/hk` with their direction-specific action ID.
- bumped `ACTION_SET_VERSION` from `2` to `3` so old tabular/DQN manifests are ignored instead of mixing generic and direction-specific jump action semantics.
- `tools/analyze_rl_transitions.py` default action list now includes the three HK jump-kick probes.

Validation:
- `python3 -m py_compile tools/rl_probe_server.py tools/analyze_rl_transitions.py tools/train_dqn_learner.py` passed.
- synthetic macro smoke confirmed `jump-forward-hk`, `jump-neutral-hk`, and `jump-back-hk` emit up-forward/up/up-back HK sequences and stamp action IDs `12`, `13`, and `14`.
- synthetic transition decode smoke confirmed direction-specific jump metadata maps back to `jump-forward-mk`, `jump-forward-hk`, `jump-neutral-hk`, and `jump-back-hk`.
- `python3 tools/rl_probe_server.py --help` shows the new jump HK scripted policies and fallback-policy choices.
- analyzer tail smoke passed on `logs/rl-transitions-defense-v1-4-3-3.ndjson --tail-rows 1000`; the default action list now includes the three HK jump-kick probes.
- one-step offline DQN smoke passed against `logs/rl-transitions-defense-v1-4-3-3.ndjson --limit 2000`; the published manifest carried `action_set_version=3` and all three HK jump-kick actions.

Follow-up:
- start a fresh model/log for live testing because this is an action-set version bump.
- after live validation, consider whether other air normals should follow the same direction-specific naming before adding them to curriculum.

## 2026-04-27: Split Back/Guard And Add Ryu MK/MP Actions

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / action-set refinement

Files changed:
- `tools/rl_probe_server.py`
- `tools/analyze_rl_transitions.py`
- `tools/train_dqn_learner.py`
- `docs/plan-remote-rl-agent.md`
- `docs/rl-policy-action-taxonomy.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- make retreat spacing and blocking trainable as different learner choices.
- add the next Ryu curriculum actions requested for live probe testing: crouching MK, MP Shoryuken, and MK Tatsumaki Senpukyaku.

Implementation notes:
- `back` is now a plain `walk/back` fixed action again and no longer expands into the stand-guard macro.
- added separate `guard-stand` and `guard-crouch` actions; they stamp `guard/stand` and `guard/crouch` metadata and expand to six decision replies of `back` or `down-back`.
- added `crouch-mk` as fixed `down+MK`, stamped as `normal/mk`; this is the first live MK normal, so learner import maps `normal/mk` to `crouch-mk`.
- added `shoryuken-mp` as `forward -> down -> down-forward -> down-forward+MP -> neutral -> neutral`, stamped as Ryu `Shoryuken` / `mp`.
- added `tatsu-mk` as `down -> down-back -> back -> back+MK -> neutral -> neutral`, stamped as Ryu `Tatsumaki Senpukyaku` / `mk`.
- `tools/analyze_rl_transitions.py` default action list now matches the expanded probe action set.
- tabular and DQN actor manifests now carry `action_set_version=2`; probe-side hot-load ignores older tabular/DQN manifests so stale q-tables do not reinterpret old `back` guard credit as plain retreat.

Validation:
- `python3 -m py_compile tools/rl_probe_server.py tools/analyze_rl_transitions.py tools/train_dqn_learner.py` passed.
- synthetic probe smoke confirmed tabular `back` returns wire `0x0003` with policy metadata `walk/back`, not `guard/stand`.
- synthetic macro smoke confirmed `guard-stand`, `guard-crouch`, `shoryuken-mp`, and `tatsu-mk` emit the expected wires and policy metadata.
- synthetic transition decode smoke confirmed policy metadata maps back to `guard-stand`, `guard-crouch`, `crouch-mk`, `shoryuken-mp`, and `tatsu-mk`.
- analyzer tail smoke passed on `logs/rl-transitions-defense-v1-4-3-3.ndjson --tail-rows 1000`; the default action list now includes the split guard and new Ryu actions.
- one-step offline DQN smoke passed against `logs/rl-transitions-defense-v1-4-3-3.ndjson --limit 2000`; the published manifest carried `action_set_version=2` and the expanded action list.

Follow-up:
- use a fresh transition log for live evaluation of this action-set version; old transition logs can still be analyzed, but old q-table/DQN model quality is not comparable.
- watch live `ready_threat_dx` for whether `guard-stand` / `guard-crouch` appear under `atk1_close` or `atk1_mid` while `back` remains usable for spacing.

## 2026-04-27: Add Readable Move Names To Policy Taxonomy

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / action namespace documentation

Files changed:
- `docs/rl-policy-action-taxonomy.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- make the all-character policy action taxonomy readable by humans instead of relying on generic source handlers such as `Att_HADOUKEN`.
- keep policy IDs, source command slots, routine numbers, handlers, and macro templates unchanged.

Implementation notes:
- added a `move_name` column to every character command registry table.
- mapped command rows to SF3 move-list names such as `Hadouken`, `Shoryuken`, `Genei-jin`, `Aegis Reflector`, and `Light of Virtue`.
- rows that combine EX, air, or source-only branches keep slash-separated aliases, for example Oro EX command rows and Twelve source kick variant rows.
- the taxonomy still treats source handlers and command slots as the executable source of truth; move names are display aliases for analysis and curriculum planning.

Validation:
- `python3 -m py_compile tools/rl_probe_server.py tools/analyze_rl_transitions.py tools/train_dqn_learner.py` passed.
- markdown table smoke checked that every character registry row has the new `move_name` column.
- `git diff --check -- docs/rl-policy-action-taxonomy.md docs/plan-remote-rl-agent.md docs/remote-rl-agent-engineering-log.md` passed.

Follow-up:
- validate ambiguous aliases before live curriculum use, especially Oro EX variants, Twelve `qcf+k`, and Akuma Hyakkishu / Ashura Senku branches.

## 2026-04-27: Migrate Live Actions To Policy Action Attribution

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / action namespace implementation

Files changed:
- `src/rl/rl_protocol.h`
- `src/rl/rl_session.c`
- `tools/rl_probe_server.py`
- `tools/analyze_rl_transitions.py`
- `tools/train_dqn_learner.py`
- `docs/rl-policy-action-taxonomy.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- move the current live probe/C action path from wire-only attribution toward the policy action ID / sub-action ID taxonomy.
- keep existing tabular and DQN behavior compatible while making transition logs ready for the later `back` vs `guard` split.

Implementation notes:
- bumped the RL protocol to `3` and action schema to `2`; `RLActionPacket` now carries `policy_action_id`, `policy_sub_action_id`, and `policy_action_step` alongside the final executable `action_wire`.
- C-side queued actions and decision ledger entries now preserve requested and executed policy action attribution and export it in transition NDJSON rows.
- probe-side action selection now returns a `PolicyActionFrame` instead of only a wire value; fixed actions and macro steps stamp taxonomy IDs for `walk`, `guard`, `normal`, `command_normal`, `throw`, Ryu `fireball` / `tatsu` / `shoryuken`, and `jump-forward-mk`.
- current model-selected `back` still expands into the guard macro and is stamped as `guard/stand`; learner import maps that metadata back to the old `back` bucket until `back` and `guard` are separate actions.
- transition analyzers and the offline DQN trainer now prefer `executed_policy_action_id` / `executed_policy_sub_action_id` and fall back to `executed_action_wire` for older logs.

Validation:
- `python3 -m py_compile tools/rl_probe_server.py tools/analyze_rl_transitions.py tools/train_dqn_learner.py` passed.
- Python packet smoke passed: action packet size is `48` bytes and `ryu-fireball` stamps `1229/lp` with the expected macro step.
- Python macro-step smoke passed for `ryu-fireball` and `jump-forward-mk`, producing steps `0..5` without wrapping the last step to `-1`.
- old-log analyzer smoke passed on `logs/rl-transitions-defense-v1-4-3-3.ndjson` tail `2000` rows using fallback wire decoding.
- `git diff --check` passed for the touched source/docs.
- `tools/mister/build-game.sh --flavor telemetry` passed and produced `build/mister-telemetry-package`.

Follow-up:
- deploy probe server and MiSTer runtime together; protocol `3` action packets are not compatible with the previous runtime.
- split `back` and `guard` into separate high-level actions after confirming the schema migration is stable in live logs.

## 2026-04-27: Draft All-Character Policy Action Taxonomy

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / action namespace design

Files changed:
- `docs/rl-policy-action-taxonomy.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- define a stable policy action ID / sub-action ID scheme before adding more SF3 moves to tabular or DQN.
- avoid mixing high-level model choices, concrete strength variants, and probe-side macro expansion in a single flat action string.
- create a source-backed inventory of command-recognized character actions for later curriculum subsets.

Implementation notes:
- universal actions use IDs below `1000` for movement, defense, normals, command normals, throws, tech, quick stand, and taunt.
- character command actions use `1000 + character_id * 100 + source_command_slot`, so IDs stay traceable to `cmd_data.c`.
- the registry records source command slot, source routine numbers, `plpatXX.c` handler names, macro template, and sub-action group.
- source handler names remain the first source of truth; official move aliases are intentionally deferred because handlers such as `Att_HADOUKEN` are reused across characters and move families.
- macros marked `button_or_charge`, `*_raw`, or numeric button groups require manual validation before live learner enablement.

Validation:
- source inspection matched the registry against `src/sf33rd/Source/Game/engine/cmd_data.c`, `cmd_main.c`, `pls03.c`, `plpat.c`, and `plpatXX.c`.
- `git diff --check -- docs/rl-policy-action-taxonomy.md docs/plan-remote-rl-agent.md docs/remote-rl-agent-engineering-log.md` passed.

Follow-up:
- add transition fields for requested/executed policy action ID, sub-action ID, and policy action step.
- split `back` and `guard` before training defensive DQN action heads.
- add official move aliases and validate uncertain macro templates only as each character enters the curriculum.

## 2026-04-27: Add Offline DQN Learner And Probe Inference

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / first ML baseline

Files changed:
- `tools/rl_probe_server.py`
- `tools/train_dqn_learner.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- prepare the first q-table-vs-ML comparison while a fresh tabular transition run is still collecting.
- train a simple DQN/MLP Q actor offline from transition NDJSON before allowing it to control live MiSTer.
- keep the first ML path independent from MiSTer/C changes and from external Python packages.

Implementation notes:
- added `policy=dqn` as a probe-side model policy, separate from scripted policies and `tabular`.
- DQN actors use the same high-level action set as tabular: `forward`, `back`, `hp`, `forward-hp`, `fireball`, `throw`, and `jump-forward-mk`.
- DQN features are normalized numeric OBS values: absolute spacing, front/back edge distances, `opp_in_front`, and validated opponent routine attack state.
- `tools/train_dqn_learner.py` reads transition logs, builds `(state, action, reward, next_state, done)` experiences, applies delayed HP-delta reward to the most recent explicit action like the tabular learner, trains a small stdlib-only MLP with target-network DQN updates, and publishes a `policy=dqn` actor manifest.
- `tools/rl_probe_server.py` can hot-load `policy=dqn` manifests from `--model-dir`, run MLP inference from same-frame OBS payloads, and reuse the existing action adapter / macro lock.
- `--learner-auto-publish` remains tabular/scripted-only; DQN publication is owned by the offline trainer for this first version.

Validation:
- `python3 -m py_compile tools/rl_probe_server.py tools/train_dqn_learner.py tools/analyze_rl_transitions.py` passed.
- `python3 tools/train_dqn_learner.py --help` passed.
- synthetic offline training smoke passed: `tools/train_dqn_learner.py` trained from a temporary NDJSON replay and published `policy=dqn` `current.json`.
- synthetic probe inference smoke passed: `ActorModelStore` loaded the generated DQN actor, `dqn_actor_action_name()` returned a valid high-level action, and `policy_action_wire()` returned a valid wire action.
- real-log smoke was attempted, but the checked local candidate transition logs were empty or missing in this worktree; rerun it after the in-progress live tabular run finishes.
- `git diff --check -- tools/rl_probe_server.py tools/train_dqn_learner.py docs/plan-remote-rl-agent.md docs/remote-rl-agent-engineering-log.md` passed.

Follow-up:
- next implementation action after DQN pipeline smoke: split `back` and `guard` into separate high-level actions, then carry high-level action / macro attribution into transition rows so DQN can learn `opp_attack=1 + close/mid -> guard` without mixing that credit with retreat/back-spacing behavior.
- after the current `jump-forward-mk` tabular live run finishes, train DQN offline on that full transition log and inspect loss, greedy action distribution, and reward/action coverage before running `--policy dqn` live.
- if DQN inference works but action quality is poor, compare against the tabular baseline using the same action set and avoid adding reward shaping until action attribution and replay coverage are understood.

## 2026-04-27: Add Tabular Jump-Forward MK Macro

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / action-set refinement

Files changed:
- `tools/rl_probe_server.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- give the current tabular learner one active approach attack that can earn immediate HP-delta reward when it connects.
- avoid adding pure `advance` yet, because the current contextual-bandit learner cannot reliably assign later attack reward back to spacing-only movement.
- keep the change scoped to the probe-side action adapter; no guard logic, reward rules, C-side protocol fields, or transition schema were changed.

Implementation notes:
- added Python-side constants for `RL_MOVE_UP_FORWARD` and `BTN_MK`.
- added `jump-forward-mk` to `POLICY_CHOICES` so it can be run as a fixed scripted probe policy.
- added `jump-forward-mk` to `TABULAR_ACTION_NAMES` so the tabular actor can explore and select it.
- added a macro sequence: `up-forward -> up-forward -> up-forward+MK -> up-forward+MK -> neutral -> neutral`.
- mapped the `up-forward+MK` wire phase back to the high-level `jump-forward-mk` tabular action bucket for learner credit.

Validation:
- `python3 -m py_compile tools/rl_probe_server.py tools/analyze_rl_transitions.py` passed.
- synthetic macro/action smoke passed: `scripted_sequence("jump-forward-mk")` produced `0x0006, 0x0006, 0x0206, 0x0206, 0x0000, 0x0000`.
- learner credit smoke passed: `tabular_action_name(0x0206)` maps to `jump-forward-mk`, and a synthetic tabular actor selected `jump-forward-mk` when it was the only eligible positive q-score.
- `git diff --check -- tools/rl_probe_server.py docs/plan-remote-rl-agent.md docs/remote-rl-agent-engineering-log.md` passed.

Follow-up:
- run a fresh live tabular pass and watch whether `ready_dx` / `ready_threat_dx` start selecting `jump-forward-mk` at close or mid spacing.
- if the MK timing is too early or too late visually, tune the macro sequence before changing reward or transition schema.

## 2026-04-27: Add Threat/Distance Ready-Action Stats

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / strike-defense policy diagnosis

Files changed:
- `tools/rl_probe_server.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- make live learner output show whether `fireball` and `back` are being selected in reasonable threat/distance regions.
- distinguish healthy far-range `opp_attack=1` fireball choices from risky close/mid-range fireball choices.
- diagnose over-defensive policy maps without changing learner updates, rewards, or action execution.

Implementation notes:
- `summarize_ready_actions()` now also returns `ready_threat_dx_actions`, keyed by `atk0_close`, `atk0_mid`, `atk0_far`, `atk1_close`, `atk1_mid`, and `atk1_far`.
- learner stats now print `ready_threat_dx=atk0_close{...} atk0_mid{...} atk0_far{...} atk1_close{...} atk1_mid{...} atk1_far{...}`.
- this is a Q-table readiness summary only: it counts ready greedy actions by state bucket and does not count actual executed actions.

Validation:
- `python3 -m py_compile tools/rl_probe_server.py tools/analyze_rl_transitions.py` passed.
- synthetic summary smoke passed: `ready_threat_dx` formatter produced the expected ordered buckets and separated `atk1_close{back:1}` from `atk1_mid{fireball:1}` / `atk1_far{fireball:1}`.
- replay smoke passed on the first `5000` rows of `logs/rl-transitions-tabular-4-3-3.ndjson`, producing `ready_threat_dx=...` from a real learner snapshot.
- `git diff --check -- tools/rl_probe_server.py docs/plan-remote-rl-agent.md docs/remote-rl-agent-engineering-log.md` passed.

Follow-up:
- in live runs, expect `atk1_close` / `atk1_mid` to trend toward `back` if strike defense is learning, while `atk1_far` and `atk0_far` may reasonably keep `fireball`.

## 2026-04-26: Add Tabular Back Guard Macro

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / strike-defense learning

Files changed:
- `tools/rl_probe_server.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- make defensive `back` decisions last long enough to cover a realistic strike-defense window.
- avoid globally increasing `action_hold_frames`, which would also slow movement, throws, fireballs, and attack timing.
- keep transition credit on the existing `back` action bucket instead of adding a separate tabular `guard` action that the C-side transition log cannot currently distinguish from plain `back` wire input.

Implementation notes:
- added a scripted `guard` policy sequence for fixed-policy validation: six consecutive `RL_MOVE_BACK` decision replies.
- tabular inference now maps a greedy/exploratory `back` action into that guard macro via the existing macro lock.
- with the current `decision_interval=3` and `action_hold=3`, one tabular `back` selection now produces about an 18-frame stand-guard window.
- `TABULAR_ACTION_NAMES` intentionally remains `forward`, `back`, `hp`, `forward-hp`, `fireball`, and `throw`; learner updates still see wire-level `back` and therefore train the `back` bucket.

Validation:
- `python3 -m py_compile tools/rl_probe_server.py tools/analyze_rl_transitions.py` passed.
- guard scripted-policy smoke passed: `scripted_sequence("guard")` produced six consecutive `0x0003` (`RL_MOVE_BACK`) decision replies.
- tabular macro-lock smoke passed: after a tabular `back` selection, a synthetic actor that switched to preferring `hp` still emitted six `back` wires before allowing `hp`.
- `git diff --check -- tools/rl_probe_server.py docs/plan-remote-rl-agent.md docs/remote-rl-agent-engineering-log.md` passed.

Follow-up:
- run a fresh tabular model/log and watch `ready_opp_attack=1{back:...}` plus visible guard behavior.
- if low attacks become a blocker, add a separate down-back guard macro after validating that action/credit semantics stay clear.

## 2026-04-26: Promote Opponent Strike Warning Into Tabular State

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / strike-defense learning

Files changed:
- `tools/rl_probe_server.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- let the tabular learner distinguish normal spacing states from states where the opponent is already in a validated strike-attack routine.
- keep throw defense as a spacing / close-range risk problem instead of inventing a fake "about to throw" observation.
- keep contact-reaction fields out of learner state because live samples showed they behave as outcome/debug labels rather than pre-contact warnings.

Live findings before promotion:
- schema cleanup was confirmed on `logs/rl-transitions-back-4-3-3.ndjson` (`3562` rows) and `logs/rl-transitions-hp-4-3-3.ndjson` (`831` rows): both carried `obs_opp_routine_attack_state` and `obs_self_contact_reaction_state`, and neither carried old `span_*` / `*_seen` fields.
- fixed `back` reduced observed self damage sharply versus the `hp` control run:
  - `back`: `self_damage=155`, `self_damage_rows=8`, `self_dmg_per_100=4.35`
  - `hp` control: `self_damage=320`, `self_damage_rows=25`, about `38.5` self damage per 100 rows overall
- damage rows were usually preceded by opponent routine attack state:
  - `back`: `5/8` damage rows had recent `obs_opp_routine_attack_state=1`
  - `hp` control: `23/25` damage rows had recent `obs_opp_routine_attack_state=1`
- timing samples showed `obs_opp_routine_attack_state=1` commonly appears one to four decisions before strike damage, making it suitable as a learner-visible strike warning.
- timing samples also showed `obs_self_contact_reaction_state=1` often appears after damage/contact, making it unsuitable as a first policy state feature.
- throw samples showed `obs_opp_routine_attack_state=0` with `obs_self_contact_reaction_state=1`, confirming that the routine attack flag is not a throw detector; close-range throw risk should be learned from spacing/action history later.

Implementation notes:
- `tabular_state_key()` now includes `opp_attack=0/1` from `obs_opp_routine_attack_state`.
- `obs_self_contact_reaction_state` remains imported for analysis but is not included in the tabular state key.
- learner stats now print `ready_opp_attack=0{...} 1{...}` so live runs can show whether ready greedy choices under strike-warning states start preferring defensive actions such as `back`.
- reward remains unchanged as learner-local HP delta: `delta_opp_hp - delta_self_hp`.

Validation:
- `python3 -m py_compile tools/rl_probe_server.py tools/analyze_rl_transitions.py` passed.
- state-key smoke passed: otherwise identical rows now produce distinct keys with `opp_attack=0` and `opp_attack=1`.
- ready-summary smoke passed: `summarize_ready_actions()` and `format_opp_attack_action_counts()` produced `ready_opp_attack=0{back:1} 1{back:1}` for synthetic ready states.
- replay smoke passed on existing local logs:
  - `logs/rl-transitions-back-4-3-3.ndjson`: imported `697` rows, produced `18` tabular states, all with `opp_attack=...`
  - `logs/rl-transitions-hp-4-3-3.ndjson`: imported `831` rows, produced `11` tabular states, all with `opp_attack=...`
- `git diff --check -- tools/rl_probe_server.py docs/plan-remote-rl-agent.md docs/remote-rl-agent-engineering-log.md` passed.

Follow-up:
- run a fresh tabular model/log after this change and check whether `ready_opp_attack=1{back:...}` appears as enough strike-warning states become ready.
- do not promote close-range throw defense until a separate action/feature plan is chosen; throw pressure should initially be treated as spacing risk, not as a visible startup flag.

## 2026-04-26: Remove Routine Span Probes From Transition Export

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / observation quality

Files changed:
- `src/rl/rl_session.c`
- `tools/rl_probe_server.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- keep transition NDJSON from mixing decision-time observations with post-observation span labels.
- prevent `*_seen` style fields from being mistaken for learner-safe OBS features.

Implementation notes:
- new transition rows no longer export:
  - `span_self_routine_attack_seen`
  - `span_opp_routine_attack_seen`
  - `span_self_contact_reaction_seen`
  - `span_opp_contact_reaction_seen`
- `obs_self_routine_attack_state`, `obs_opp_routine_attack_state`, `obs_self_contact_reaction_state`, and `obs_opp_contact_reaction_state` remain because they are decision-observation snapshots.
- run-level defensive-success analysis should be reconstructed offline from consecutive `obs_*` rows plus HP/stun deltas instead of storing future-window labels in each row.

## 2026-04-26: Rename Routine Span Probes

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / observation quality

Files changed:
- `src/rl/rl_session.c`
- `tools/rl_probe_server.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- avoid confusing decision-span labels with decision-observation fields.
- make it clear that `*_seen` fields contain events that happened during the action span after the observation was sampled.

Implementation notes:
- transition NDJSON briefly wrote routine/contact span aggregate fields with a `span_` prefix.
- `obs_*` fields remain reserved for decision-time snapshots that the remote policy can actually observe at inference time.
- this intermediate experiment was superseded the same day by removing span probes from new transition exports.

## 2026-04-26: Add Routine Attack / Contact Reaction Validation Probes

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / observation quality

Files changed:
- `src/rl/rl_observation.h`
- `src/rl/rl_observation.c`
- `src/rl/rl_protocol.h`
- `src/rl/rl_session.c`
- `tools/rl_probe_server.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- validate whether `routine_no[1] == 4` is a trustworthy opponent/self attack-state flag.
- validate whether `routine_no[1] == 1` can identify contact / defensive reaction windows when paired with subsequent HP delta.
- keep these fields validation-only before using them in the learner state key or reward shaping.

Implementation notes:
- `RLObservationV1` now derives:
  - `self_routine_attack_state`
  - `opp_routine_attack_state`
  - `self_contact_reaction_state`
  - `opp_contact_reaction_state`
- UDP OBS payload schema advanced to version `2` and now carries those four derived flags alongside the compact spacing fields.
- Transition NDJSON now exports decision-observation flags:
  - `obs_self_routine_attack_state`
  - `obs_opp_routine_attack_state`
  - `obs_self_contact_reaction_state`
  - `obs_opp_contact_reaction_state`
- An intermediate build also exported decision-span flags, but those were removed from new transition rows because they mixed post-observation labels into the learner-visible log.
- `tools/rl_probe_server.py` parses the schema-v2 OBS payload and imports the new decision-observation transition fields, but `tabular_state_key()` still ignores them so live policy behavior does not change yet.

Validation plan:
- run the usual Windows probe command with the updated script and redeployed runtime.
- confirm `obs_opp_routine_attack_state` lines up with overlay `OR*,4,*` on opponent attacks.
- infer defensive-success windows offline from consecutive `obs_*` rows plus HP/stun deltas, instead of relying on per-row span labels.
- do not promote these flags to learner features until live logs show stable semantics across normals, projectiles, throws, and multistage moves.

## 2026-04-26: Add Transition Reward Attribution Analyzer

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / reward diagnosis

Files changed:
- `tools/analyze_rl_transitions.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- make long-run tabular policy interpretation repeatable by summarizing HP-delta reward by action and distance bucket
- distinguish direct action-row reward from delayed neutral/recovery reward credited back to the latest explicit action

Implementation notes:
- added `tools/analyze_rl_transitions.py`.
- the analyzer reuses `rl_probe_server.py`'s tabular action mapping, `tabular_training_reward()`, and `obs_abs_dx` bucket thresholds.
- output includes:
  - `DIRECT_BY_ACTION`
  - `DIRECT_BY_ACTION_DX`
  - `CREDITED_BY_ACTION`
  - `CREDITED_BY_ACTION_DECISION_DX`
  - `DELAYED_CREDIT_DECISION_DX_TO_REWARD_DX`
- delayed credit is episode-scoped: nonzero reward on a neutral/unknown row is attributed to the most recent explicit tabular action in the same `(run_id, episode_id)`.

Validation:
- `python3 -m py_compile tools/analyze_rl_transitions.py` passed.
- `python3 tools/analyze_rl_transitions.py logs/rl-transitions-tabular-4-3-3.ndjson --tail-rows 100000 --limit 30` passed.
- `python3 tools/analyze_rl_transitions.py logs/rl-transitions-tabular-4-3-3.ndjson --limit 30` passed on `383918` rows.
- `git diff --check -- tools/analyze_rl_transitions.py docs/plan-remote-rl-agent.md docs/remote-rl-agent-engineering-log.md` passed.

Long-run readout from `logs/rl-transitions-tabular-4-3-3.ndjson`:
- full log analyzed: `rows=383918`, `done=448`, `explicit_rows=122774`, `reward_rows=13115`, `delayed_credit_rows=9236`.
- direct action rows:
  - `hp`: `reward=+2900`, `mean=+0.072`
  - `fireball`: `reward=+439`, `mean=+0.015`
  - `throw`: `reward=-109`, `mean=-0.007`
- direct distance split:
  - `fireball dx=far`: `reward=+1625`, `mean=+0.074`
  - `fireball dx=mid`: `reward=-832`, `mean=-0.125`
  - `fireball dx=close`: `reward=-354`, `mean=-0.609`
  - `throw dx=far`: `reward=+514`, `mean=+0.041`
  - `throw dx=mid`: `reward=-444`, `mean=-0.119`
  - `throw dx=close`: `reward=-179`, `mean=-0.577`
- credited view:
  - `fireball`: `reward=+2391`, `mean=+0.071`
  - `hp`: `reward=-2303`, `mean=-0.054`
  - `throw`: `reward=-3435`, `mean=-0.200`
- key interpretation:
  - far fireball is currently the cleanest positive signal.
  - mid/close fireball is strongly punished, so the policy should keep learning spacing sensitivity rather than treating fireball as universally good.
  - throw is not yet a reliable positive action in the credited view, even if some far throw rows look mildly positive; that far-throw signal is likely spacing/credit leakage rather than real throw strength.

Follow-up:
- use this analyzer after each long run before changing the action set.
- if throw remains selected despite negative credited reward, inspect whether the learner's q-table has stale lucky throw buckets or whether move-level labels are needed before throw can be learner-safe.
- add move-level transition labeling before using projectile/throw/DP labels as hard reward features.

## 2026-04-26: Fix Transition Sender Running-State Race

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / long-run stability

Files changed:
- `src/rl/rl_net.c`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- fix the remaining transition sender lifecycle race after ruling out perf-capture config as the latest long-run restart cause

Investigation notes:
- MiSTer remote config at `/media/fat/games/3s-arm/config` had no `perf-*` keys.
- recent MiSTer-side logs contained no `PERF capture` entries.
- `lock-status` reported the remote lock as free before the read-only config check.
- `busy-status` using the old default host failed, so the follow-up check used explicit `192.168.0.133`.
- review found `transition_sender_thread_running` was still read/written from both the game thread and sender thread without the queue mutex.
- there was a missed-wakeup window: the sender could observe an empty queue and be about to exit while a new batch was enqueued; the game thread could still see `running=true` and skip starting a replacement sender.

Implementation notes:
- `transition_sender_thread_running` is now cleared by `RLNet_PopQueuedTransitionBatch()` while holding `transition_queue_mutex` when the queue is observed empty.
- `RLNet_MaybeStartTransitionSenderThread()` now checks `transition_sender_thread_running`, reaps completed thread handles, and starts replacement sender threads under the same queue mutex.
- completed sender threads are still joined outside the mutex to avoid deadlock.
- `RLNet_Shutdown()` now snapshots and waits the sender thread without clearing the handle while it is still running, then clears handle/state under the mutex after wait.
- `reset_transition_queue()` now locks the queue mutex when it already exists before freeing queued payloads.

Validation:
- read-only remote config check confirmed no active perf-capture config keys and no recent `PERF capture` logs.
- `git diff --check -- src/rl/rl_net.c` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed and produced `build/mister-telemetry-package`.

Follow-up:
- deploy this telemetry package before the next long RL run.
- during the next long run, watch transition counters and MiSTer `dmesg`; if the process still restarts without OOM or perf-capture logs, collect uptime plus the last 100 lines of dmesg immediately after restart.

## 2026-04-26: Add Anti-DP Fireball Macro Variant

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / tabular macro-action execution

Files changed:
- `tools/rl_probe_server.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- reduce accidental shoryuken parsing from the learned fireball macro so damage credit is less likely to be assigned to `fireball` when the game actually performed a DP

Investigation notes:
- transition logs contained no direct shoryuken final inputs:
  - `down-forward + LP` (`0x0018`) count was `0`
  - `down-forward + HP` (`0x0048`) count was `0`
- visible accidental shoryukens were most likely caused by command-buffer context, where a previous `forward`-like action plus QCF+LP looked like a DP motion to the game parser.
- since current learner credit is input-level (`executed_action_wire`) rather than move-code-level, such accidental DPs would be credited as `fireball` if they ended on `forward + LP`.

Implementation notes:
- `fireball` and `ryu-fireball` scripted sequences now emit:
  - `down-back -> down -> down-forward -> forward+LP -> neutral -> neutral`
- the leading `down-back` is intended to clear a prior `forward` from the effective command sequence before the QCF+LP finish.

Validation:
- `python3 -m py_compile tools/rl_probe_server.py` passed.
- synthetic sequence smoke passed: both `fireball` and `ryu-fireball` now expand to `0x7,0x2,0x8,0x14,0x0,0x0`.
- synthetic macro smoke passed: tabular fireball emits the same anti-DP sequence while macro-locked.

Follow-up:
- rerun live tabular and confirm fireballs still appear while accidental shoryuken frequency drops.
- long-term fix remains move-level transition labeling so learner credit can distinguish actual fireball from actual shoryuken.

## 2026-04-26: Lock Tabular Fireball Macro Sequence

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / tabular macro-action execution

Files changed:
- `tools/rl_probe_server.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- make tabular `fireball` execute as one uninterrupted QCF+LP macro instead of letting every OBS reply re-run q-table selection and break the motion

Investigation notes:
- transition logs showed `fireball` was attempted (`forward + LP`, `0x0014`) only `16` times while `throw` appeared `220` times.
- all recorded fireball attempts had `delta_opp_hp = 0` and `delta_self_hp = 0`.
- the user confirmed no projectile was visible on screen.
- root cause: tabular selection could choose `fireball` for one decision, then the next decision could choose `hp`, `throw`, or another action before the full `down -> down-forward -> forward -> forward+LP` sequence finished.

Implementation notes:
- `policy_action_wire()` now receives a `macro_states` table keyed by session/run/episode.
- when tabular chooses a multi-step scripted action, the probe server starts an active macro and emits the first sequence step.
- later OBS replies for the same episode emit the next macro step before consulting the q-table again.
- the macro state is cleared after the full sequence, including neutral recovery frames, is emitted.
- fixed single-step actions such as `throw` still execute immediately without macro lock.

Validation:
- `python3 -m py_compile tools/rl_probe_server.py` passed.
- synthetic macro-lock smoke passed: after a tabular `fireball` selection, later calls whose q-table preferred `hp` still emitted `0x2,0x8,0x4,0x14,0x0,0x0`, then returned to `hp`.

Follow-up:
- rerun live tabular and confirm a visible projectile appears when fireball is selected.
- after live confirmation, check transition log for `0x0014` rows followed by nonzero `delta_opp_hp` when fireballs connect.

## 2026-04-26: Fix Long-Run RL Transition Sender Thread Leak

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / long-run stability

Files changed:
- `src/rl/rl_net.c`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- stop long RL runs from eventually exhausting MiSTer memory and getting `3s-arm` killed by the kernel OOM killer

Investigation notes:
- MiSTer `dmesg` showed:
  - `Out of memory: Killed process ... (3s-arm)`
  - `total-vm:459000kB`
  - `anon-rss:445584kB`
- the device itself had about `492MB` RAM, so this matched the observed "MiSTer side restarts" symptom: `3s-arm` was killed and the wrapper/front-end recovered.
- the highest-risk RL path was transition batch sending:
  - every episode can queue a transition batch
  - `RLNet_MaybeStartTransitionSenderThread()` created a short-lived sender thread
  - when the thread finished, it only set `transition_sender_thread_running = false`
  - the next batch could overwrite `transition_sender_thread` with a new handle without joining the completed thread

Implementation notes:
- `RLNet_MaybeStartTransitionSenderThread()` now:
  - returns while an existing sender is still running
  - joins and clears a completed sender thread before creating another one
  - sets `transition_sender_thread_running` before thread creation and clears it on create failure
- runtime reset now frees any queued transition batch payloads before clearing the queue, covering the rare reset/create-failure path.

Validation:
- `git diff --check -- src/rl/rl_net.c docs/plan-remote-rl-agent.md docs/remote-rl-agent-engineering-log.md` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed and produced `build/mister-telemetry-package`.

Follow-up:
- deploy and run a long RL session while sampling `/proc/<3s-arm pid>/status`; `VmRSS` should stop climbing episode-by-episode.
- watch MiSTer overlay transition counters `TBQ/TBS/TBA/TBF` to confirm transition batches still send after the thread lifecycle change.

## 2026-04-26: Add Fireball / Throw To Tabular Action Set

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / tabular action diversity and observability

Files changed:
- `tools/rl_probe_server.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- expand the first tabular learner action set beyond movement and HP so distance-specific behavior has clearer options to discover
- expose ready greedy action distribution by distance bucket instead of relying only on the single global `top_ready` action

Implementation notes:
- the default tabular action set is now `forward`, `back`, `hp`, `forward-hp`, `fireball`, and `throw`.
- tabular `throw` maps to the same single-frame wire used by the scripted throw probe: `forward + LP + LK`.
- tabular `fireball` runs the existing QCF+LP scripted sequence under the shorter learner action name `fireball`.
- transition rows map the final `forward + LP` execution wire back to `fireball`, allowing delayed HP-delta rewards to be credited to the high-level tabular action.
- learner snapshots now count the best ready greedy action per state and print:
  - `ready_actions=<action>:<state_count>,...`
  - `ready_dx=close{...} mid{...} far{...}`
- this summary uses the same `min_n` and positive-score gate as greedy tabular inference.

Validation:
- `python3 -m py_compile tools/rl_probe_server.py` passed.
- synthetic Python smoke passed:
  - `forward+LP` mapped to `fireball`
  - `forward+LP+LK` mapped to `throw`
  - ready summary produced `close{throw:1} mid{fireball:1} far{forward:1}` for a hand-built q-table
- synthetic policy smoke passed: a tabular q-table whose best ready action was `fireball` emitted the expected QCF+LP sequence (`0x2`, `0x8`, `0x4`, `0x14`).
- `git diff --check -- tools/rl_probe_server.py docs/plan-remote-rl-agent.md docs/remote-rl-agent-engineering-log.md` passed.

Follow-up:
- run live tabular and watch whether `ready_actions` / `ready_dx` diversify beyond `hp`.
- expect early learning to be slower because the action space grew from four actions to six.

## 2026-04-26: Same-Frame OBS Spacing Payload For Tabular Inference

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / tabular state freshness

Files changed:
- `src/rl/rl_protocol.h`
- `src/rl/rl_net.h`
- `src/rl/rl_net.c`
- `src/rl/rl_session.c`
- `tools/rl_probe_server.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- remove the tabular actor's dependence on the latest transition-replay bucket when choosing a live action
- make each UDP OBS request carry the current compact spacing snapshot so the PC chooses from the state seen on that OBS frame

Implementation notes:
- `RLObsSpacingPayloadV1` was added as a packed, schema-versioned payload behind the existing `RLObsPacketHeader.obs_len` field.
- MiSTer OBS packets now send `header + RLObsSpacingPayloadV1` and set `obs_len = sizeof(payload)`.
- the spacing payload uses the same fields already exported in transition rows: `obs_abs_dx`, `obs_abs_dy`, both players' front/back edge distances, and `obs_opp_in_front`.
- `RLSession_CaptureObservationSpacing()` and OBS payload creation share the same fill helper so ledger rows and live OBS state stay aligned.
- `tools/rl_probe_server.py` now parses the spacing payload, derives the same tabular bucket key, and passes that same-frame key to tabular inference.
- header-only or invalid OBS payloads still fall back to `latest_tabular_state`, preserving compatibility with older MiSTer builds.
- learner stats now include `obs=<payload>/<header-only>` and `tab_state=obs:<n>/latest:<n>` to make live state-source checks visible.

Validation:
- `python3 -m py_compile tools/rl_probe_server.py` passed.
- synthetic Python smoke packed an OBS spacing payload, parsed it, derived a tabular key, and selected the expected `forward-hp` action through the min-count gate.
- `git diff --check -- src/rl/rl_protocol.h src/rl/rl_net.h src/rl/rl_net.c src/rl/rl_session.c tools/rl_probe_server.py docs/plan-remote-rl-agent.md docs/remote-rl-agent-engineering-log.md` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed and produced `build/mister-telemetry-package`.

Follow-up:
- live-run tabular and confirm learner stats show `obs` payload counts rising and `tab_state=obs` dominating `latest`.

## 2026-04-25: Auto-Select VS Rematch For RL Sessions

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / automated reset loop

Files changed:
- `src/sf33rd/Source/Game/menu/menu.c`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- let RL sessions continue into another match without manual VS result input
- use the safest available path first by reusing the existing VS result rematch branch instead of hard-resetting match state

Implementation notes:
- a checkpoint commit was created before this change:
  - `9882679c checkpoint: before rl auto rematch`
- in `VS_Result()` case 4, when `RLSession_IsActive()` and `Mode_Type == MODE_VERSUS`, the menu now auto-confirms both result cursors and advances to existing case 6.
- case 6 still performs the real rematch transition through `Setup_VS_Mode(...)`, `G_No[1] = 12`, and `G_No[2] = 1`.
- the existing RL rematch guard in case 6 still forces `MODE_VERSUS`, `Play_Mode = 1`, and reapplies `RLSession_ApplyVersusOperatorSetup()`.
- live testing showed this reached character select but did not auto-confirm the same characters into the next match.
- the RL rematch path now marks both players with `Sel_PL_Complete = -0x8000`, reusing the existing character-select fast path that keeps `My_char[]` and enqueues player loading.
- when that fast path runs while RL is active in VS mode, `PL_Sel_1st()` immediately marks SA selection complete for the retained character, including the no-SA / `My_char == 0` paths.
- live testing still required each side to press LK twice, so the sentinel handling was moved earlier into `Sel_PL_Control()`:
  - `RLSession_AutoConfirmRematchSelect()` consumes `Sel_PL_Complete = -0x8000`
  - it enqueues player loading for the retained `My_char[]`
  - it marks character and SA selection complete before normal select input handling can wait for manual attack confirms
- live testing then reached the handicap/stage and CPU-character-select path. Root cause: RL-vs-CPU select still looked like one human operator plus one CPU operator, so normal VS/CPU selection logic did not take the "both sides selected" exit path.
- the auto-rematch select helper now temporarily marks both players as operators during the select exit path, sets an `rl_auto_rematch_select_ready` guard, and skips the handicap branch only for this guarded RL rematch path. `Game2_0()` still reapplies `RLSession_ApplyVersusOperatorSetup()` before battle, restoring the configured agent-vs-CPU operator split.
- this is the conservative auto-rematch path; direct skip from win scene to next match remains deferred until this proves stable.

Validation:
- previous `git diff --check -- src/sf33rd/Source/Game/menu/menu.c docs/plan-remote-rl-agent.md docs/remote-rl-agent-engineering-log.md` passed before the character-select follow-up.
- previous `tools/mister/build-game.sh --flavor telemetry` passed and produced `build/mister-telemetry-package` before the character-select follow-up.
- `git diff --check -- src/sf33rd/Source/Game/menu/menu.c src/sf33rd/Source/Game/screen/sel_pl.c docs/plan-remote-rl-agent.md docs/remote-rl-agent-engineering-log.md` passed after the character-select follow-up.
- `tools/mister/build-game.sh --flavor telemetry` passed after the character-select follow-up and produced `build/mister-telemetry-package`.
- `git diff --check -- src/sf33rd/Source/Game/screen/sel_pl.c docs/plan-remote-rl-agent.md docs/remote-rl-agent-engineering-log.md` passed after moving sentinel handling into `Sel_PL_Control()`.
- `tools/mister/build-game.sh --flavor telemetry` passed after moving sentinel handling into `Sel_PL_Control()` and produced `build/mister-telemetry-package`.
- `git diff --check -- src/sf33rd/Source/Game/screen/sel_pl.c docs/plan-remote-rl-agent.md docs/remote-rl-agent-engineering-log.md` passed after adding the guarded both-operators select exit.
- `tools/mister/build-game.sh --flavor telemetry` passed after adding the guarded both-operators select exit and produced `build/mister-telemetry-package`.

Follow-up:
- deploy the telemetry package and verify a full RL match can end and enter the next match without manual VS result input.
- confirm transition batches keep arriving after the automatically rematched match ends.

## 2026-04-25: Split Tabular Raw Top From Ready Top

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / tabular live-log accuracy

Files changed:
- `tools/rl_probe_server.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- make learner logs distinguish the highest raw q-score from the highest action that is actually eligible for greedy tabular inference
- avoid misleading logs such as `min_n=8 top=hp:1.10/4`, where the displayed top action was below the min-count gate and could not be used by the actor's greedy path

Implementation notes:
- `TabularPolicyLearner.snapshot(...)` now accepts `min_action_count`.
- snapshots still report the raw top q-score.
- snapshots also report `ready_*` fields for the highest positive q-score whose state/action count is at least `min_action_count`.
- learner stats now print:
  - `top_raw=<action>:<score>/<count>`
  - `top_ready=<action>:<score>/<count>`
- actor selection behavior is unchanged.

Validation:
- `python3 -m py_compile tools/rl_probe_server.py` passed.
- `git diff --check -- tools/rl_probe_server.py docs/plan-remote-rl-agent.md docs/remote-rl-agent-engineering-log.md` passed.
- synthetic snapshot smoke passed:
  - raw top was `hp 10.0/1`
  - ready top was `forward 1.0/8`
- learner-only smoke against the current tabular transition log printed both fields:
  - `top_raw=hp:2.24/14`
  - `top_ready=hp:2.24/14`
  - duplicate publish gate still held `model_pub=1` on repeated unchanged stats ticks

Follow-up:
- rerun live tabular and judge min-count readiness from `top_ready`, not `top_raw`.

## 2026-04-25: Skip Duplicate Tabular Actor Publishes

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / tabular live-log hygiene

Files changed:
- `tools/rl_probe_server.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- stop learner auto-publish from creating new actor versions when no new transition rows have produced tabular updates
- reduce live-log noise where model versions kept increasing while `rows`, `tab_updates`, and q-table contents were unchanged

Implementation notes:
- `LearnerLogTailer` now records the last published tabular update count.
- when auto-publish is due for `policy=tabular`, it publishes only if current `tab_updates` is greater than the last published value.
- skipped duplicate publishes still advance the next publish deadline so the learner does not spin on an expired timer.
- non-tabular learner publish behavior is unchanged.

Validation:
- `python3 -m py_compile tools/rl_probe_server.py` passed.
- `git diff --check -- tools/rl_probe_server.py docs/plan-remote-rl-agent.md docs/remote-rl-agent-engineering-log.md` passed.
- learner-only smoke with `--learner-stats-interval-sec 1` and `--learner-publish-interval-sec 1` passed:
  - first ready stats tick published `MODEL published version=1`
  - subsequent stats ticks had unchanged `rows=37870` and `tab_updates=26073`
  - `model_pub` stayed at `1` and no duplicate learner model versions were published

Follow-up:
- rerun live tabular and confirm `MODEL published version=...` only appears after a new transition batch/import increases `tab_updates`.

## 2026-04-25: Add Tabular Minimum-Sample Gate

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / tabular policy stability

Files changed:
- `tools/rl_probe_server.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- prevent sparse lucky-hit tabular q-scores from immediately becoming greedy actions during live play
- make early tabular learning more stable before adding same-frame OBS payloads or a neural learner

Implementation notes:
- `TabularPolicyLearner` now tracks per-state/action update counts alongside q-scores.
- learner-published tabular actor manifests now include:
  - `q_counts`
  - `min_action_count`
- `tabular_actor_action_wire()` only uses a positive q-score for greedy inference when that state/action count is at least `min_action_count`.
- `--tabular-min-action-count` defaults to `8`.
- epsilon exploration can still sample the configured tabular action set; the min-count gate applies to greedy q-table selection.
- learner stats now print `min_n=<count>` and `top=<action>:<score>/<count>` so live logs show whether the top-scoring action is well-supported or sparse.

Validation:
- `python3 -m py_compile tools/rl_probe_server.py` passed.
- synthetic actor smoke passed:
  - with `hp=10.0/count=1`, `forward=1.0/count=8`, and `min_action_count=8`, tabular inference selected `forward` (`wire=4`)
  - after raising `hp` to `count=8`, tabular inference selected `hp` (`wire=64`)
- learner-only smoke against the current tabular transition log published a tabular actor with `min_action_count=8`, `metadata.tabular_min_action_count=8`, and `q_counts` in `current.json`.

Follow-up:
- rerun live tabular with `--tabular-min-action-count 8`.
- watch for `top=.../<count>` and confirm low-count actions no longer dominate live behavior.
- if policy remains unstable after this gate, the next code step is same-frame OBS payload support so inference no longer depends on the latest learner-imported transition bucket.

Live follow-up:
- Windows Python running from a `\\wsl.localhost\Ubuntu\...` model directory hit a transient `PermissionError` during atomic `current.json` replacement:
  - `PermissionError: [WinError 5] Access is denied: '.current.<tmp>' -> 'current.json'`
- `tools/rl_probe_server.py` now wraps actor-manifest `os.replace(...)` calls in a short retry loop so a temporary Windows/UNC file lock does not kill the learner thread.

## 2026-04-25: Split Tabular Reward From Episode Reward

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / minimum learner reward hygiene

Files changed:
- `tools/rl_probe_server.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- keep terminal win/loss reward available for future sequential RL while preventing the current contextual-bandit tabular learner from assigning the whole `+100/-100` episode result to the last executed action

Implementation notes:
- transition `reward_accum` remains unchanged and still represents the full reward stream, including terminal win/loss bonus.
- tabular q-score updates now use learner-local `tabular_reward = delta_opp_hp - delta_self_hp`.
- neutral/recovery rows are still not learned as greedy actions.
- if a neutral/recovery row carries nonzero HP-delta reward, delayed credit now applies that HP-delta reward to the most recent explicit action bucket.
- learner stats now include `tab_reward=hp-delta:<sum>` to distinguish the tabular training signal from aggregate transition `rew=...`.
- learner-published actor metadata includes:
  - `tabular_reward_source = hp-delta`
  - `tabular_training_reward_total`

Validation:
- `python3 -m py_compile tools/rl_probe_server.py` passed.
- `git diff --check -- tools/rl_probe_server.py docs/plan-remote-rl-agent.md docs/remote-rl-agent-engineering-log.md` passed.
- synthetic learner-only smoke passed:
  - a terminal `forward` row with `reward_accum=105` but `delta_opp_hp=5` updated toward `5`, not `105`
  - a nonterminal `hp` row with `delta_opp_hp=15` became top action with `hp:0.75`
  - learner stats reported `tab_reward=hp-delta:20.0`
  - actor metadata included `tabular_reward_source=hp-delta` and `tabular_training_reward_total=20.0`

Follow-up:
- rerun live tabular smoke after deploy; expect HP-delta action scores to favor actions that directly cause damage or avoid damage, while `reward_accum` remains available for the future DQN/sequence learner.

## 2026-04-25: Preserve RL Transition Flush Across VS Rematch

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / live tabular smoke stability

Files changed:
- `src/rl/rl_session.c`
- `src/sf33rd/Source/Game/menu/menu.c`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- fix the live observation where second-match action control continued but transition batches stopped arriving after a later round ended
- keep RL active VS rematch flow from falling back into an arcade-style next-opponent route

Implementation notes:
- `RLSession_ApplyRemoteActionToBuffers()` now calls a reset guard before clearing remote runtime state.
- The guard finalizes the current episode ledger before reset when the remote runtime is initialized and gameplay has left the override-eligible battle state.
- This prevents `RLSession_ResetRemoteRuntime(false)` from clearing `transition_batch_payload` without first queueing it through `RLNet_QueueTransitionBatch(...)`.
- VS result rematch now forces `Mode_Type = MODE_VERSUS` and `Play_Mode = 1` while RL is active before entering the character-select transition.
- The VS rematch path also reapplies `RLSession_ApplyVersusOperatorSetup()` after forcing mode state, so the configured RL agent/operator split is restored for the next match.

Validation:
- `git diff --check -- src/rl/rl_session.c src/sf33rd/Source/Game/menu/menu.c` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed.

Follow-up:
- deploy the telemetry package to MiSTer before the next live test.
- rerun `--policy tabular` and confirm that a second match can end a round and still append transition rows.
- watch for duplicate `episode_end` rows; the transition importer dedupes by `(run_id, episode_id, decision_id)`, but duplicate terminal rows would still indicate C-side finalize sequencing needs one more guard.

## 2026-04-25: Minimal Tabular Learner Actor Loop

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / minimum training loop

Files changed:
- `tools/rl_probe_server.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- make the remote RL path train something real before adding more transition fields or neural-network dependencies
- prove that replay rows can update an actor manifest and that the action path can use the updated actor

Implementation notes:
- added `--policy tabular`.
- added a small contextual-bandit learner inside `tools/rl_probe_server.py`.
- transition rows are bucketed using the compact spacing snapshot:
  - `obs_abs_dx`
  - `obs_abs_dy`
  - `obs_self_front_edge_dist`
  - `obs_self_back_edge_dist`
  - `obs_opp_front_edge_dist`
  - `obs_opp_back_edge_dist`
  - `obs_opp_in_front`
- supported learned actions are:
  - `forward`
  - `back`
  - `hp`
  - `forward-hp`
- neutral rows are intentionally not learned as greedy actions in this first version, because delayed damage / recovery rewards can make "do nothing" look falsely positive before reward attribution is refined.
- when a neutral/recovery row carries nonzero reward, the learner conservatively credits that reward to the most recent explicit action bucket. This is a small learner-side credit-delay patch, not a replacement for later reward/transition refinement.
- each imported replay row updates one score with:
  - `score += alpha * (reward_accum - score)`
- learner-published `tabular` actor manifests now include:
  - `actions`
  - `epsilon`
  - `fallback_policy`
  - `updated_rows`
  - `q`
- OBS inference chooses from the active tabular q-table only when the latest known state has a positive-scoring action. Otherwise it falls back to a scripted policy, defaulting to `hp`.
- Current limitation:
  - MiSTer still sends a header-only OBS packet with `obs_len=0`.
  - Therefore Python-side tabular inference uses the latest spacing bucket imported by the learner from transition replay, not an exact same-frame OBS-derived state.
  - This is acceptable for the first closed-loop smoke, but a later schema-versioned OBS payload is needed before treating tabular policy quality as meaningful gameplay evidence.
- learner stats now include:
  - `tab_states`
  - `tab_updates`
  - `tab_ignored`
  - `tab_delayed`
  - `eps`
  - `top`

Validation:
- `python3 -m py_compile tools/rl_probe_server.py` passed.
- `git diff --check -- tools/rl_probe_server.py` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed.
- synthetic smoke passed:
  - one HP replay row with positive reward created one spacing bucket
  - publishing that q-table as a `tabular` actor selected `executed_action_wire=64` for the same latest bucket
- learner-only smoke against `logs/rl-transitions-hp-4-3-3.ndjson` imported `585` rows, created `13` tabular states, applied `87` updates, ignored `518` neutral rows, credited `20` delayed reward rows back to the previous explicit action, published tabular actors, and reported `top=hp:10.38`.

Follow-up:
- run first live `tabular` pass at timing `4/3/3`.
- confirm learner logs show nonzero `tab_states` and `tab_updates`.
- confirm actor manifests in `model/rl-model-tabular` contain `q`.
- confirm transition rows show `model_version_executed` advancing after learner publishes.
- do not judge gameplay quality until OBS carries same-frame learner state or the transition/import delay is explicitly modeled.

## 2026-04-25: Add Compact Spacing State To Transition Replay Rows

Milestone:
- Milestone 5: Async learner and model hot-swap / Milestone 6 transition data quality

Files changed:
- `src/rl/rl_session.c`
- `tools/rl_probe_server.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- keep the RL loop moving while restoring the minimum spacing state replay-only learners need to learn distance, approach, retreat, and corner pressure
- avoid restoring the full debug-heavy observation schema into transition rows

Implementation notes:
- transition NDJSON now includes a decision-observation spacing snapshot:
  - `obs_abs_dx`
  - `obs_abs_dy`
  - `obs_self_front_edge_dist`
  - `obs_self_back_edge_dist`
  - `obs_opp_front_edge_dist`
  - `obs_opp_back_edge_dist`
  - `obs_opp_in_front`
- `obs_abs_dx` / `obs_abs_dy` are raw absolute enemy distances from the controlled agent's perspective.
- front/back edge distances are derived from each fighter's facing sign:
  - facing world-left: front is left edge, back is right edge
  - facing world-right: front is right edge, back is left edge
- `tools/rl_probe_server.py` learner replay import now preserves the same seven fields.
- Signed `dx/dy` and left/right corner ratios remain useful debug/future-schema candidates, but are intentionally not part of the first learner-safe replay spacing subset.

Validation:
- `git diff --check -- src/rl/rl_session.c tools/rl_probe_server.py docs/plan-remote-rl-agent.md docs/remote-rl-agent-engineering-log.md` passed.
- `python3 -m py_compile tools/rl_probe_server.py` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed.
- local synthetic `learner_replay_row()` smoke passed for the new spacing fields: `obs_abs_dx`, `obs_abs_dy`, front/back edge distances, and `obs_opp_in_front`.
- live `hp` policy validation produced `logs/rl-transitions-hp-4-3-3.ndjson` with:
  - `rows=585`
  - `done=2`
  - `terminal_reason` counts: `decision_replaced=583`, `episode_end=2`
  - `obs_frame` out-of-order count: `0`
  - spacing fields present on all `585` rows
  - `obs_abs_dx` range: `1..322`
  - `obs_abs_dy` range: `0..125`
  - `obs_opp_in_front`: `579` rows true, `6` rows false
  - actions: `executed_action_wire=64` on `67` rows, neutral on `518` rows
  - both episodes ended with `final_self_hp=160`, `final_opp_hp=0`, `total_reward=260`

## 2026-04-25: Slim Transition Log From 55 to 22 Fields

Milestone:
- Milestone 5: Async learner and model hot-swap / transition data quality

Files changed:
- `src/rl/rl_session.c`
- `tools/rl_probe_server.py`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- reduce transition log (rl-transitions.ndjson) to only the fields needed for RL training and debugging
- remove 33 debug-only, redundant, and stale fields to shrink per-row JSON size and simplify the learner pipeline

Kept fields (22):
- Identity: `run_id`, `episode_id`, `decision_id`, `round_num`, `obs_frame`
- Characters: `agent_character_id`, `opponent_character_id`
- Action: `executed_action_wire`
- Combat deltas: `delta_self_hp`, `delta_opp_hp`, `delta_self_stun`, `delta_opp_stun`
- Movement deltas: `delta_self_y`, `delta_opp_y`, `delta_self_forward`, `delta_opp_forward`
- Debug HP: `final_self_hp`, `final_opp_hp`
- Model: `model_version_executed`
- RL core: `reward_accum`, `done`, `terminal_reason`

Removed fields (33):
- Config constants repeated every row: `decision_delay_frames`, `decision_interval_frames`, `action_hold_frames`
- Redundant HP snapshots: `start_self_hp`, `start_opp_hp` (recoverable from prior final_hp)
- Redundant action decomposition: `executed_move_intent`, `executed_attack_bits`, `requested_action_wire`, `requested_move_intent`, `requested_attack_bits`
- Now-constant flags: `was_executed` (always true), `execution_source` (always remote)
- Debug timing: `target_frame`, `execution_frame_actual`
- Redundant position: `delta_self_x`, `delta_opp_x` (forward already accounts for facing)
- Debug model versions: `model_version_expected`, `model_version_requested`
- Overlay attack counters: `overlay_attack_event_finalized`, `overlay_attack_contact`, `overlay_attack_whiff`
- Requested attack tracking: `requested_attack_entered_state`, `requested_attack_made_contact`, `requested_attack_likely_whiffed`, `requested_attack_input_started`, `requested_attack_became_active`
- Observed attack tracking: `observed_attack_state_started`, `observed_attack_code_changed`, `observed_attack_counter_started`
- Throw tracking: `self_throw_started`, `opp_throw_caught_started`, `self_throw_seen`, `opp_throw_caught_seen`

Python side changes:
- `learner_replay_row()` whitelist updated to match 22-field schema
- Removed `was_executed` guard (no longer needed, all exported rows are executed)
- `LearnerLogTailer._consume_row()` simplified: removed timing bucket, execution source, overlay attack, and throw counter tracking
- `LearnerLogTailer._print_stats()` simplified: removed timing/source/fallback reporting
- Removed stale init member variables
- Removed `RLSession_ExecutionSourceLabel()` (unused after removing execution_source from log)

Validation:
- `python3 -m py_compile tools/rl_probe_server.py` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed.


## 2026-04-25: Remove Pending Attack Outcome Mechanism — Fix Reward Routing And Log Ordering

Milestone:
- Milestone 5: Async learner and model hot-swap / transition correctness follow-up

Files changed:
- `src/rl/rl_session.c`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- fix severe reward routing bug where 98.5% of transition rows had `reward_accum = 0` because the `pending_attack_outcome` mechanism routed all HP damage reward to old decisions instead of the currently active one
- fix out-of-order `obs_frame` in transition logs caused by delayed finalization of attack outcome entries

Root cause analysis:
- the earlier `pending_attack_outcome` mechanism (added 2026-04-25 "Attack Outcome Attribution Window Fix") held old decisions alive for 240 frames to capture delayed HP damage
- this caused `combat_entry` to point at a stale ledger entry instead of the currently active one, so per-frame `opp_hp_delta - self_hp_delta` reward accumulated on old decisions
- when the 240-frame window expired, the old entry was finalized with `terminal_reason = attack_outcome_window_closed` and written to the log after much newer entries, breaking obs_frame ordering
- evidence from `logs/rl-transitions-throw-4-3-3.ndjson`:
  - 1404 of 1426 rows (98.5%) had `reward_accum = 0`
  - 21 `attack_outcome_window_closed` rows carried all the HP damage reward
  - 25 out-of-order obs_frame entries, each delayed by exactly 237 frames (~4 seconds)
  - 3 `episode_end` done=true rows per episode instead of one

Implementation notes:
- removed the `pending_attack_outcome` and `attack_outcome_deadline_frame` fields from `RLDecisionLedgerEntry`
- removed `RLSession_FindPendingAttackOutcomeEntry()` and `RLSession_FinalizeExpiredAttackOutcomeEntries()` functions
- removed terminal_reason `4` (`attack_outcome_window_closed`) — only `decision_replaced`, `episode_end`, and `not_terminal` remain
- removed `RL_ATTACK_OUTCOME_WINDOW_FRAMES` constant
- simplified `RLSession_SetActiveLedgerEntry()` — old entries are always finalized with `decision_replaced` instead of being held alive
- simplified `RLSession_FinalizeEpisodeLedger()` — win/loss +100/-100 bonus goes directly to `active_ledger_entry`
- simplified `RLSession_OnObservationFrameEnd()`:
  - removed `pending_attack_entry`, `combat_entry`, and `has_combat_signal` variables
  - all HP delta / stun / combat signals now accumulate on the currently active decision entry
  - `RLSession_IsRoundEndHpSync()` guard simplified (no longer conditioned on pending_attack_entry)
- overlay attack counters (ACC/AWC/AH) remain unchanged — they use their own independent `overlay_attack_event_pending` / `overlay_attack_event_seq` mechanism which is not affected

Design rationale:
- for RL training, the reward signal must be associated with the decision that was **active when damage occurred**, not the decision that initiated the attack
- the RL learner will learn temporal credit assignment through its own value function / Q-network; the transition export should not try to do temporal credit assignment itself
- this makes every `decision_replaced` row self-contained: it includes all HP/stun deltas and reward that occurred during that decision's active window

Expected behavior after fix:
- every `decision_replaced` row that spans a damage frame will have nonzero `delta_opp_hp` or `delta_self_hp`
- `reward_accum` will be nonzero on the decision that was active when damage actually occurred
- transition log will always be in `obs_frame` order (no delayed finalization)
- each episode will have exactly one `done=true` row with `terminal_reason = episode_end`

Validation:
- `git diff --check -- src/rl/rl_session.c` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed.
- Hardware validation needed: rerun throw policy match and confirm rewarded rows are spread across active decisions instead of concentrated on stale attack outcomes.


## 2026-04-25: Attack Outcome Attribution Window Fix

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / transition correctness follow-up

Files changed:
- `src/rl/rl_session.c`
- `tools/rl_probe_server.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- fix severe transition shrinkage where attacks visibly hit but HP reward and attack outcome labels were exported on later neutral rows or compressed into terminal rows

Implementation notes:
- attack decisions now keep a 240-frame pending outcome window after their input frame instead of being finalized immediately when the next decision becomes active
- pending attack ledgers are protected from reuse until exported, so later hit/contact/throw observations can still be attributed back to the attack that caused them
- combat deltas now prefer the most recent pending attack ledger within the outcome window; movement span data still accrues to the active decision row
- terminal observations now compute and apply the final HP/stun/contact deltas before episode finalization instead of returning early
- round win/loss bonus now also prefers the pending attack owner, so final-hit damage and KO reward land on the same attack decision when possible
- round-end HP sync suppression is no longer allowed to drop large terminal damage if a pending attack owner exists
- transition rows again export the requested attack outcome fields:
  - `requested_attack_entered_state`
  - `requested_attack_made_contact`
  - `requested_attack_likely_whiffed`
  - `requested_attack_input_started`
  - `requested_attack_became_active`
  - `observed_attack_state_started`
  - `observed_attack_code_changed`
  - `observed_attack_counter_started`
- learner stats now print `reqatk=<active>/<contact>/<whiff>` alongside the existing overlay `atk=` summary

Validation:
- `git diff --check -- src/rl/rl_session.c tools/rl_probe_server.py` passed.
- `python3 -m py_compile tools/rl_probe_server.py` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed.

Follow-up:
- rerun short `hp`, `throw`, and one special policy pass to confirm positive damage rows now align with attack-request rows instead of mostly neutral/terminal rows
- tune `RL_ATTACK_OUTCOME_WINDOW_FRAMES` if 240 frames is too wide for overlapping multi-attack policies or still too short for slow projectile/special outcomes

## 2026-04-25: Throw Transition HP Span Fix

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum

Files changed:
- `src/rl/rl_session.c`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- fix move-family review evidence where `logs/rl-transitions-throw-4-3-3.ndjson` won two rounds by throw but exported too few positive damage rows and misleading round-start HP spans

Implementation notes:
- reviewed `logs/rl-transitions-throw-4-3-3.ndjson`:
  - `rows=256`
  - `done=2`
  - `total_delta_opp_hp=320`
  - `estimated_16hp_successes=20`
  - `row_positive_damage=5`
- root cause:
  - transition rows exported `start_self_hp` / `start_opp_hp` from round-start HP, not decision-start HP
  - terminal non-battle observations could be accumulated as combat damage before episode finalization, compressing remaining round damage into the last decision row
- `RLSession_SendRemoteObservationIfDue()` and the active-ledger fallback now initialize `start_*_hp` from the current observation HP
- `RLSession_OnObservationFrameEnd()` now finalizes terminal observations before damage/reward accumulation, preserving the round-win bonus without treating post-round state cleanup as a huge hit

Validation:
- old-log review command:
  ```sh
  jq -s '{rows:length,done:map(select(.done==true))|length,row_positive_damage:map(select(.delta_opp_hp>0))|length,total_delta_opp_hp:(map(.delta_opp_hp)|add),estimated_16hp_successes:((map(.delta_opp_hp)|add)/16),positive_reward_rows:map(select(.reward_accum>0))|length,total_reward:(map(.reward_accum)|add),rounds:([.[].episode_id]|unique)}' logs/rl-transitions-throw-4-3-3.ndjson
  ```
- old-log review result:
  ```text
  rows=256 done=2 row_positive_damage=5 total_delta_opp_hp=320 estimated_16hp_successes=20 positive_reward_rows=5 total_reward=520 rounds=1,2
  ```
- `git diff --check -- src/rl/rl_session.c` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed.

Follow-up after rerun:
- a new `logs/rl-transitions-throw-4-3-3.ndjson` still showed the same shape:
  - `rows=256`
  - `done=2`
  - `row_positive_damage=4`
  - `total_delta_opp_hp=314`
  - `estimated_16hp_successes=19.625`
  - `positive_reward_rows=4`
- the first fix worked for decision-local `start_opp_hp`, but did not remove the round-end HP sync:
  - the last row in episode 2 exported `start_opp_hp=144`, `final_opp_hp=3`, `delta_opp_hp=141`, `reward_accum=241`
- the log also showed only six rows where the throw macro was actually requested / executed, so "won two rounds by throw" cannot be validated by counting requested throw action rows alone
- added direct throw/caught observation and transition fields:
  - `self_throw_started`
  - `opp_throw_caught_started`
  - `self_throw_seen`
  - `opp_throw_caught_seen`
- learner stats now print `throw=<self_started>/<opp_caught_started>` for live validation
- added a conservative round-end HP sync guard to keep large `<=3 HP` conclusion-state jumps out of per-decision HP reward while preserving the explicit round-win bonus

Follow-up validation:
- `python3 -m py_compile tools/rl_probe_server.py` passed.
- `git diff --check -- src/rl/rl_session.c src/rl/rl_observation.c src/rl/rl_observation.h tools/rl_probe_server.py` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed.

## 2026-04-24: First Scripted Move-Family Pass Set Completed

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum

Files changed:
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- record the first full fixed-policy move-family pass set and establish the next phase after baseline timing stabilization

Implementation notes:
- the first fixed `4/3/3` move-family pass set was completed for:
  - `hp`
  - `throw`
  - `ryu-fireball`
  - `tatsu`
  - `shoryuken`
- all five runs kept the control path healthy:
  - `sources=remote:...`
  - `fallback_pct=0.00`
  - `policy_fallback_pct=0.00`
  - stable sub-millisecond `inf` telemetry
- current first-pass interpretation:
  - `ryu-fireball`: pass
  - `shoryuken`: pass
  - `throw`: provisional pass
  - `tatsu`: provisional pass
  - `hp`: control-path pass, but not a clean apples-to-apples comparison run because it used the live learner/model-dir path instead of the fixed-policy-only path
- this is enough to move to the next sub-phase:
  - fixed movement-prefix attack validation
  - examples: walk-forward-then-attack, crouch-then-attack, short retreat-then-attack
- this is not yet enough to promote all attack-outcome fields to learner-safe labels across every move family

Validation:
- representative learner logs:
  ```text
  LEARNER rows=256 done=2 run=5 ep=5 atk=6/6/0 replay=256/256 skipped=0 rew=+6/-0/0250 timing=4/3/3 timing_rows=256 timing_done=2 timing_rew=+6/-0/0250 policy=ryu-fireball policy_rows=256 policy_done=2 policy_rew=+6/-0/0250 sources=remote:256 fallback_pct=0.00 timing_fallback_pct=0.00 policy_fallback_pct=0.00 ready=yes warmup=100 batch=32 batch_mean=0.000 model_exec=0 model_active=0 model_pub=0 model_load=0 model_counts=0/0 inf=512:106.9/205.9/368.8us
  LEARNER rows=256 done=2 run=9 ep=2 atk=6/6/0 replay=256/256 skipped=0 rew=+7/-0/0249 timing=4/3/3 timing_rows=256 timing_done=2 timing_rew=+7/-0/0249 policy=shoryuken policy_rows=256 policy_done=2 policy_rew=+7/-0/0249 sources=remote:256 fallback_pct=0.00 timing_fallback_pct=0.00 policy_fallback_pct=0.00 ready=yes warmup=100 batch=32 batch_mean=0.000 model_exec=0 model_active=0 model_pub=0 model_load=0 model_counts=0/0 inf=512:111.9/207.3/289.2us
  LEARNER rows=256 done=2 run=8 ep=2 atk=4/3/1 replay=256/256 skipped=0 rew=+4/-0/0252 timing=4/3/3 timing_rows=256 timing_done=2 timing_rew=+4/-0/0252 policy=tatsu policy_rows=256 policy_done=2 policy_rew=+4/-0/0252 sources=remote:256 fallback_pct=0.00 timing_fallback_pct=0.00 policy_fallback_pct=0.00 ready=yes warmup=100 batch=32 batch_mean=8.125 model_exec=0 model_active=0 model_pub=0 model_load=0 model_counts=0/0 inf=512:118.8/204.6/278.3us
  ```

## 2026-04-24: Policy-Bucket Learner Summary For Move-Family Validation

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum

Files changed:
- `tools/rl_probe_server.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- prepare move-family validation by letting one learner log report per-policy replay aggregates, not just overall or per-timing aggregates

Implementation notes:
- `ActorModelStore` now keeps a lightweight version-to-policy lookup using published actor manifests
- learner log tailing now maintains a small aggregate bucket per executed policy
- each `LEARNER` line now reports for the latest executed policy:
  - `policy=...`
  - `policy_rows=...`
  - `policy_done=...`
  - `policy_rew=+/-/0`
  - `policy_fallback_pct=...`
- this is aimed at upcoming scripted move-family passes with policies such as:
  - `hp`
  - `throw`
  - `ryu-fireball`
  - `tatsu`
  - `shoryuken`
- the current implementation assumes actor manifests remain available in `--model-dir` for executed model versions that appear in transition rows

Validation:
- `python3 -m py_compile tools/rl_probe_server.py` pending.
- `git diff --check -- tools/rl_probe_server.py docs/plan-remote-rl-agent.md docs/remote-rl-agent-engineering-log.md` pending.

## 2026-04-24: First Clean 4/3/3 Timing Candidate

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum

Files changed:
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- record the first short live timing sweep where `4/3/3` produced clean remote-only execution with zero fallback in the learner log

Implementation notes:
- live learner logs for `timing=4/3/3` showed:
  - `sources=remote:128`, then `sources=remote:256`
  - `fallback_pct=0.00`
  - `timing_fallback_pct=0.00`
  - `inf=512:95.7/189.2/939.6us` by the second sampled window
- the same run also showed stable publish-to-execute lag:
  - `model_exec=596 model_active=599 model_pub=599`
  - later `model_exec=599 model_active=600 model_pub=600`
- this is strong early evidence that `4/3/3` is a viable Milestone 6 timing candidate from a transport/control-path perspective
- this does not yet prove stronger gameplay outcomes than `4/4/4`; the sample is still small:
  - `rows=256`
  - `done=2`
  - `rew=+2/-6/0248`

Validation:
- Live log evidence:
  ```text
  LEARNER rows=128 done=1 run=5 ep=2 atk=7/1/6 replay=128/128 skipped=0 rew=+0/-1/0127 timing=4/3/3 timing_rows=128 timing_done=1 timing_rew=+0/-1/0127 sources=remote:128 fallback_pct=0.00 timing_fallback_pct=0.00 ready=yes warmup=100 batch=32 batch_mean=0.000 model_exec=596 model_active=599 model_pub=599 model_load=599 model_counts=3/1 inf=512:109.5/201.2/300.1us
  TRANSITIONS batch run=5 ep=3 rows=128 bytes=123703 from=192.168.0.133:40378
  LEARNER rows=256 done=2 run=5 ep=3 atk=10/4/6 replay=256/256 skipped=0 rew=+2/-6/0248 timing=4/3/3 timing_rows=256 timing_done=2 timing_rew=+2/-6/0248 sources=remote:256 fallback_pct=0.00 timing_fallback_pct=0.00 ready=yes warmup=100 batch=32 batch_mean=0.000 model_exec=599 model_active=600 model_pub=600 model_load=600 model_counts=4/1 inf=512:95.7/189.2/939.6us
  ```

## 2026-04-24: Per-Timing Learner Summary For Sweep Comparison

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum

Files changed:
- `tools/rl_probe_server.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- make timing sweeps easier to compare when one learner log contains rows from multiple timing configurations

Implementation notes:
- learner log tailing now keeps a small aggregate bucket per timing tuple:
  - `(decision_delay_frames, decision_interval_frames, action_hold_frames)`
- each `LEARNER` line now reports for the latest timing tuple:
  - `timing_rows`
  - `timing_done`
  - `timing_rew=+/-/0`
  - `timing_fallback_pct`
- this is meant to support Milestone 6 timing sweeps without forcing a separate transition log file for every short experiment
- the overall `rows`, `rew`, `sources`, and `fallback_pct` fields still describe the full imported replay set

Validation:
- `python3 -m py_compile tools/rl_probe_server.py` pending.
- `git diff --check -- tools/rl_probe_server.py docs/plan-remote-rl-agent.md docs/remote-rl-agent-engineering-log.md` pending.

## 2026-04-24: Milestone 6 Timing-Tuning Telemetry Bring-Up

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum

Files changed:
- `src/rl/rl_session.c`
- `tools/rl_probe_server.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- make timing sweeps for `k / decision_interval_frames / action_hold_frames` traceable in transition data and learner logs before changing policy cadence itself

Implementation notes:
- transition NDJSON / episode-batch export now includes:
  - `decision_delay_frames`
  - `decision_interval_frames`
  - `action_hold_frames`
- `tools/rl_probe_server.py` now carries those timing fields into the learner-safe replay row metadata
- learner stats now print:
  - `timing=<k>/<decision_interval>/<action_hold>`
  - `fallback_pct=<percent>`
- this should make it much easier to compare runs after config changes without relying on separate handwritten notes
- this change does not yet alter runtime timing behavior; it only improves observability for the next Milestone 6 tuning passes

Validation:
- `python3 -m py_compile tools/rl_probe_server.py` passed.
- `git diff --check -- src/rl/rl_session.c tools/rl_probe_server.py docs/plan-remote-rl-agent.md docs/remote-rl-agent-engineering-log.md` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed.

## 2026-04-24: Transition Export Slimming For Runtime Smoothness

Milestone:
- Milestone 5: Async learner and model hot-swap / Milestone 6 prep

Files changed:
- `src/rl/rl_session.c`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- reduce live gameplay stutter by shrinking per-decision transition export work before attempting bigger control-timing changes

Implementation notes:
- `RLSession_FormatTransitionLogLine(...)` now exports a smaller learner-safe / validation-safe subset instead of the previous debug-heavy row
- removed from the serialized NDJSON / transition-batch payload:
  - character-name strings duplicated by character IDs
  - span-state booleans such as airborne / hit-stop / contact / damage-state flags
  - older requested/observed attack heuristics that the learner path does not currently ingest
  - overlay attack active/contact/whiff running counts
  - several attack-start / attack-code / airborne-start booleans that were mainly useful for early bring-up forensics
- kept in the serialized output:
  - run / episode / decision ids
  - frame ids
  - start/final HP
  - character IDs
  - model-version expected/requested/executed
  - requested / executed action wires and decoded executed action fields
  - compact HP / stun / position / facing-relative deltas
  - overlay attack finalized/contact/whiff flags
  - execution source, reward, done, and terminal reason
- `RLSession_FinalizeLedgerEntry(...)` no longer formats the same transition row twice; it now reuses the already-formatted line for both local append and episode-batch accumulation
- this change reduces both CPU formatting cost and TCP batch payload size, but it does not yet explain or fix the higher `neutral-fallback` rate from the latest run

Validation:
- `git diff --check -- src/rl/rl_session.c docs/plan-remote-rl-agent.md docs/remote-rl-agent-engineering-log.md tools/rl_probe_server.py` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed.

## 2026-04-24: Inference Latency Telemetry Precision Fix

Milestone:
- Milestone 5: Async learner and model hot-swap

Files changed:
- `tools/rl_probe_server.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- fix the probe server latency telemetry bug where `inf=` frequently collapsed to `0/0/16000us`, which made Milestone 5 latency evidence unreliable

Implementation notes:
- the probe server now measures OBS-to-action service time with `time.perf_counter_ns()` instead of `time.monotonic_ns()`
- `InferenceStats` now stores raw nanosecond samples instead of truncating to integer microseconds before aggregation
- learner stats still print microseconds, but now with one decimal place:
  - `inf=<count>:<p50_us>/<p95_us>/<max_us>us`
- this should preserve sub-millisecond variation and make it much easier to distinguish real Python-side service cost from occasional scheduler spikes

Validation:
- `python3 -m py_compile tools/rl_probe_server.py` pending.
- `git diff --check -- tools/rl_probe_server.py docs/plan-remote-rl-agent.md docs/remote-rl-agent-engineering-log.md` pending.

## 2026-04-24: Live Hot-Swap Execute-Path Confirmation

Milestone:
- Milestone 5: Async learner and model hot-swap

Files changed:
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- record the first live run where learner-published actor versions were observed catching up in executed transitions, not just in publish telemetry

Implementation notes:
- during live learner/inference testing, the probe server showed:
  - a temporary lag where `model_exec=346` while `model_active=model_pub=model_load=351`
  - a later catch-up where `MODEL published version=352` was followed by transition rows with `model_exec=352 model_active=352 model_pub=352 model_load=352`
- this is the strongest current evidence that the Milestone 5 hot-swap path is functioning end-to-end:
  - learner publishes new actor versions
  - the in-memory active actor updates
  - subsequent executed transitions report the new model version
- the same live run also showed:
  - `rows=3084`
  - `done=11`
  - `sources=neutral-fallback:1,remote:3083`
- these counts suggest transition upload and replay import are continuing normally and that fallback execution is now rare in the measured run
- `model_counts=39/1` indicates the active actor is usually updated directly by local learner publishes rather than by repeated background reloads from disk; this is acceptable for the current single-process learner/inference setup
- latency proof is still incomplete:
  - `inf=512:0/0/16000us` does not yet provide enough confidence to mark `Action latency stays stable during training` complete

Validation:
- Live log evidence observed with the current Windows-to-WSL learner command:
  ```text
  LEARNER rows=2742 done=10 run=3 ep=10 ... model_exec=346 model_active=351 model_pub=351 model_load=351 model_counts=38/1 inf=512:0/0/16000us
  MODEL published version=352 policy=hp source=learner
  TRANSITIONS batch run=3 ep=11 rows=342 bytes=645060 from=192.168.0.133:44936
  LEARNER rows=3084 done=11 run=3 ep=11 ... model_exec=352 model_active=352 model_pub=352 model_load=352 model_counts=39/1 inf=512:0/0/16000us
  ```
- Additional live evidence from the same run continued to show stable catch-up:
  ```text
  LEARNER rows=4603 done=16 run=3 ep=16 atk=271/217/54 replay=4603/4603 skipped=0 rew=+120/-119/04364 sources=neutral-fallback:1,remote:4602 ready=yes warmup=100 batch=32 batch_mean=1.000 model_exec=375 model_active=376 model_pub=376 model_load=376 model_counts=63/1 inf=512:0/0/16000us
  MODEL published version=377 policy=hp source=learner
  ```
- This later sample suggests the execute path is now usually within one published version of the active actor, which is consistent with a healthy publish-to-execute lag instead of a stuck hot-swap path.

## 2026-04-24: Learner And Actor Version Observability Tightening

Milestone:
- Milestone 5: Async learner and model hot-swap

Files changed:
- `tools/rl_probe_server.py`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- make Milestone 5 hot-swap validation easier by separating learner replay progress from actor publish/load/execute version telemetry in the probe-server stats line

Implementation notes:
- `ActorModelStore` now exposes a status snapshot with:
  - active actor version
  - last published version
  - last loaded version
  - publish count
  - load count
- learner stats now print:
  - `run`
  - `model_exec`
  - `model_active`
  - `model_pub`
  - `model_load`
  - `model_counts`
- this should make it obvious whether:
  - new transition batches are still arriving
  - learner publishes are advancing
  - the in-memory actor has switched
  - executed transitions are still coming from an older actor version

Validation:
- `python3 -m py_compile tools/rl_probe_server.py` passed.
- `git diff --check -- tools/rl_probe_server.py docs/remote-rl-agent-engineering-log.md` passed.
- Current live test command:
  ```sh
  python \\wsl.localhost\Ubuntu\home\olhua\src\3s-mister-arm\tools\rl_probe_server.py --host 0.0.0.0 --port 37330 --action-port 37331 --policy hp --policy-repeat-delay-ms 3000 --model-version 0 --model-dir \\wsl.localhost\Ubuntu\home\olhua\src\3s-mister-arm\model\rl-model-live --transition-log \\wsl.localhost\Ubuntu\home\olhua\src\3s-mister-arm\logs\rl-transitions-live.ndjson --learner-auto-publish --learner-publish-interval-sec 10 --learner-warmup-rows 100 --learner-batch-size 32
  ```

## 2026-04-24: HP-Zero Active-Round Control And Background Model Watch

Milestone:
- Milestone 5: Async learner and model hot-swap / Milestone 4 ledger correctness follow-up

Files changed:
- `src/rl/rl_session.c`
- `tools/rl_probe_server.py`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- keep remote input alive when visible HP reaches zero but the game has not yet ended the round, and remove model-manifest filesystem checks from the inference hot path

Implementation notes:
- RL input/observation gating now follows the game battle-active flags (`Allow_a_battle_f != 0 && Demo_Time_Stop == 0`) instead of requiring both players' raw HP to stay above zero
- HP reaching zero remains an observation/reward signal, but no longer directly stops remote input or finalizes the episode
- episode finalization now waits for the game to leave battle-active state, so it should align with the actual round conclusion instead of the first zero-HP frame
- `ActorModelStore.current()` now returns only the in-memory actor
- external `current.json` refresh checks moved to a background watcher thread, while learner publishes still update the in-memory actor immediately

Validation:
- `python3 -m py_compile tools/rl_probe_server.py` passed.
- `git diff --check -- src/rl/rl_session.c tools/rl_probe_server.py docs/remote-rl-agent-engineering-log.md` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed.
- Fresh hardware validation needed: confirm auto punch continues while `Allow_a_battle_f` is still active even if visible HP is zero, and confirm inference `p95/max` improves because OBS replies no longer touch the model directory.

## 2026-04-24: Fixed-Policy Repeat Delay And Model Refresh Throttle

Milestone:
- Milestone 5: Async learner and model hot-swap

Files changed:
- `tools/rl_probe_server.py`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- fix `--policy-repeat-delay-ms` being ignored by fixed policies such as `hp`, and reduce inference latency spikes caused by checking `current.json` on every observation packet

Implementation notes:
- fixed policies now share the same per `(nonce, run_id, episode_id, policy)` cooldown state as scripted policies
- `--policy hp --policy-repeat-delay-ms 3000` now emits one HP action, then neutral actions until the 3000 ms cooldown expires
- `ActorModelStore.current()` now throttles external `current.json` refresh checks to every 250 ms by default instead of every observation
- the refresh interval can be overridden with `RL_MODEL_REFRESH_INTERVAL_SEC`
- learner-side publishes still update the in-memory active actor immediately

Validation:
- `python3 -m py_compile tools/rl_probe_server.py` passed.
- `git diff --check -- tools/rl_probe_server.py docs/remote-rl-agent-engineering-log.md` passed.
- local policy smoke confirmed fixed `hp` emits `[64, 0, 64]` across a 200 ms cooldown.

## 2026-04-24: Learner Actor Manifest Publish And Hot-Swap Skeleton

Milestone:
- Milestone 5: Async learner and model hot-swap

Files changed:
- `tools/rl_probe_server.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- add a first versioned actor publication and atomic hot-swap path so the remote inference service can move from fixed `--model-version` stamping to learner-published actor versions

Implementation notes:
- added `ActorModelStore` to `tools/rl_probe_server.py`
- `--model-dir DIR` enables actor manifest storage:
  - `actor-vN.json` records immutable published actor metadata
  - `current.json` is updated through `os.replace()` for atomic hot-swap
- inference reads the current actor before each observation reply and stamps action packets with that actor's `version` and `policy`
- `--learner-auto-publish` lets the learner/log-reader publish a new actor manifest after replay warmup and every `--learner-publish-interval-sec`
- `--learner-publish-policy POLICY` can force the policy used by learner-published manifests; otherwise publishing keeps the active policy

Validation:
- `python3 -m py_compile tools/rl_probe_server.py` passed.
- `git diff --check -- tools/rl_probe_server.py docs/plan-remote-rl-agent.md docs/remote-rl-agent-engineering-log.md` passed.
- learner-only smoke with `--model-dir`, `--learner-auto-publish`, and existing `logs/rl-transitions.ndjson` ran under `timeout 3`; expected timeout exit `124` after publishing `actor-v0.json` through `actor-v5.json` and atomically updating `current.json`.
- Live MiSTer validation still needed: run the probe server with `--model-dir` and confirm RL overlay/logs show `model_version_executed` increasing after learner publication while observation replies continue.

## 2026-04-24: RL Round-Playable Episode Boundary Fix

Milestone:
- Milestone 5: Async learner and model hot-swap / Milestone 4 ledger correctness follow-up

Files changed:
- `src/rl/rl_session.c`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- fix fresh hardware logs where each episode began after the round HP was already terminal, causing the whole HP/reward delta to land on the final executed decision and adding one extra `was_executed=false` terminal row per round

Implementation notes:
- remote input override and observation send are now gated on a playable round:
  - `Allow_a_battle_f != 0`
  - `Demo_Time_Stop == 0`
  - both agent and opponent HP are above zero
- stale action packets received during non-playable round phases are rejected before they can initialize a new runtime episode
- terminal HP observations now finalize the active episode immediately at frame end, before the next frame can clear the ledger during KO / round-end flow
- unexecuted in-flight ledger entries are discarded at episode finalization instead of being exported as zero-reward terminal transitions

Validation:
- `git diff --check -- src/rl/rl_session.c docs/remote-rl-agent-engineering-log.md` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed.
- Fresh hardware validation still needed: run a 3-round match and confirm each episode starts at live HP, HP deltas appear before the terminal row when damage occurs mid-round, and no extra `was_executed=false` terminal row is emitted.

## 2026-04-24: Protocol v2 Run ID And Unique Round Episodes

Milestone:
- Milestone 5: Async learner and model hot-swap

Files changed:
- `src/rl/rl_protocol.h`
- `src/rl/rl_net.h`
- `src/rl/rl_net.c`
- `src/rl/rl_session.h`
- `src/rl/rl_session.c`
- `tools/rl_probe_server.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- make every round-scoped RL episode uniquely identifiable in `rl-transitions.ndjson`, remote action packets, and transition-batch uploads instead of reusing `Round_num` as `episode_id`

Implementation notes:
- bumped the RL observation/action/batch protocol to v2 while keeping the UDP hello/ping probe packet version at v1
- added `run_id` to:
  - `RLObsPacketHeader`
  - `RLActionPacket`
  - `RLTransitionBatchHeader`
  - `RLTransitionBatchAck`
- MiSTer now persists the last allocated run id in `logs/rl-run-state.txt`
- `episode_id` is now a per-run monotonic round rollout sequence
- transition NDJSON now exports:
  - `run_id`
  - unique per-run `episode_id`
  - game-facing `round_num`
- expected-decision, queued-action, seen-action, and decision-ledger lookups now key by `run_id` as well as `episode_id` / `decision_id`
- learner replay import now keeps `run_id` / `round_num` and dedupes by `(run_id, episode_id, decision_id)`
- transition-batch ACKs validate both `run_id` and `episode_id`

Validation:
- `python3 -m py_compile tools/rl_probe_server.py` passed.
- `git diff --check -- src/rl/rl_protocol.h src/rl/rl_net.h src/rl/rl_net.c src/rl/rl_session.h src/rl/rl_session.c tools/rl_probe_server.py` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed.

## 2026-04-24: Ledger HP Delta Recovery And Round Boundary Cleanup

Milestone:
- Milestone 5: Async learner and model hot-swap / Milestone 4 ledger correctness follow-up

Files changed:
- `src/rl/rl_observation.h`
- `src/rl/rl_observation.c`
- `src/rl/rl_session.c`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- fix transition rows where round win/loss rewards were present but every per-decision HP delta stayed zero, making training depend almost entirely on sparse terminal rewards

Implementation notes:
- `RLObservationV1` now carries raw `self_hp`, `opp_hp`, `self_hp_start`, and `opp_hp_start`
- ledger reward accumulation now derives HP deltas from cumulative round damage:
  - `self_damage_total = self_hp_start - self_hp`
  - `opp_damage_total = opp_hp_start - opp_hp`
  - each observation contributes the difference from the previous observed damage total
- transition rows now include diagnostic HP fields:
  - `start_self_hp`
  - `start_opp_hp`
  - `final_self_hp`
  - `final_opp_hp`
- round episode changes now key only off `Round_num` to avoid `PL_Wins` / `VS_Win_Record` updates creating empty skipped episode ids during round-end flow

Validation:
- `python3 -m py_compile tools/rl_probe_server.py` passed.
- `git diff --check -- src/rl/rl_observation.h src/rl/rl_observation.c src/rl/rl_session.c` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed.
- Needs hardware replay validation with a fresh `rl-transitions.ndjson` to confirm `hp_rows > 0` when visible HP damage occurs.

## 2026-04-23: Milestone 5 Episode Batch Transport

Milestone:
- Milestone 5: Async learner and model hot-swap

Files changed:
- `src/rl/rl_protocol.h`
- `src/rl/rl_net.h`
- `src/rl/rl_net.c`
- `src/rl/rl_session.c`
- `tools/rl_probe_server.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- replace manual transition-log copying with a first formal non-critical transport that uploads completed episode batches from MiSTer to the remote learner while keeping local NDJSON logging intact

Implementation notes:
- added `RLTransitionBatchHeader` / `RLTransitionBatchAck` protocol structs
- MiSTer now:
  - keeps local `rl-transitions.ndjson` append behavior unchanged
  - accumulates finalized NDJSON rows for the current episode in memory
  - queues the completed episode for background TCP upload on `obs_port + 2`
  - expects a per-episode ACK from the remote learner service
- transport work is kept off the action critical path by a background sender thread and a small pending queue in `src/rl/rl_net.c`
- `tools/rl_probe_server.py` now also hosts a TCP transition-batch listener:
  - appends received payloads into `--transition-log`
  - ACKs the batch after a successful append
  - defaults `--transition-port` to `--action-port + 1` when transition logging is enabled
- the earlier pull-mirror path remains available for smoke / fallback use, but the intended path is now direct episode-batch upload

Validation:
- `python3 -m py_compile tools/rl_probe_server.py` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed.
- local socket-level runtime smoke for the TCP listener could not be completed in this sandbox because local Python socket creation is denied with `PermissionError: [Errno 1] Operation not permitted`.

## 2026-04-23: Milestone 5 Transition Pull Mirror

Milestone:
- Milestone 5: Async learner and model hot-swap

Files changed:
- `tools/rl_probe_server.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- remove the manual-copy requirement for learner bring-up by letting the remote-side probe server mirror a MiSTer transition log into a local learner file on a non-critical background thread

Implementation notes:
- added a `TransitionPuller` background thread to `tools/rl_probe_server.py`
- the puller supports:
  - `--transition-pull-remote-path PATH` for read-only SCP polling from MiSTer using `MISTER_HOST`, `MISTER_USER`, and `MISTER_PASSWORD` defaults
  - `--transition-pull-local-source PATH` for local smoke tests of the same mirror/update path
- the puller writes into the local `--transition-log` path:
  - appends only the new suffix when the fetched file is a strict extension of the current mirror
  - rewrites the mirror if the source diverges, while the learner importer dedupes replay rows by `(episode_id, decision_id)`
- added `--learner-only` so the transition pull / replay import path can run without binding the UDP action server

Validation:
- `python3 -m py_compile tools/rl_probe_server.py` passed.
- local mirror smoke passed with:
  - `python3 tools/rl_probe_server.py --learner-only --transition-pull-local-source <source> --transition-log <mirror> --learner-tail-from-start --learner-stats-interval-sec 0.2 --transition-pull-interval-sec 0.2 --learner-warmup-rows 2 --learner-batch-size 1`
  - first pull imported one replay row
  - appending a second row to the source produced:
    - `PULLER updated local mirror pulls=2`
    - `replay=2/2`
    - `done=1`
    - `ready=yes`

## 2026-04-23: Milestone 5 Replay Buffer Import Skeleton

Milestone:
- Milestone 5: Async learner and model hot-swap

Files changed:
- `tools/rl_probe_server.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- move the learner skeleton from "tail transition logs and print counters" to "import a learner-safe replay subset and report replay readiness" without adding real training yet

Implementation notes:
- added a fixed-capacity in-memory replay buffer to `tools/rl_probe_server.py`
- added `learner_replay_row(...)` to import only the current learner-safe subset:
  - executed action fields
  - reward / done / terminal fields
  - compact HP / stun / movement deltas
  - overlay attack auxiliary labels
  - character IDs and executed model version as metadata
- rows with `was_executed != true` are skipped during replay import
- learner stats now report:
  - replay size and imported row count
  - skipped unexecuted rows
  - positive / negative / zero reward counts
  - execution-source mix
  - warmup readiness and sampled batch mean reward
- added CLI knobs:
  - `--replay-capacity`
  - `--learner-batch-size`
  - `--learner-warmup-rows`

Validation:
- `python3 -m py_compile tools/rl_probe_server.py` passed.
- `python3 tools/rl_probe_server.py --transition-log logs/rl-transitions.ndjson --learner-tail-from-start --learner-stats-interval-sec 0.2 --learner-warmup-rows 10 --learner-batch-size 8 --port 0` printed stable learner stats with:
  - `rows=4423`
  - `replay=4420/4420`
  - `skipped=3`
  - `sources=remote:3173,repeated-last-action:1247`
  - `ready=yes`
  - `model=12`

## 2026-04-23: First Learner Replay Subset And Reward Notes

Milestone:
- Milestone 5 follow-up planning / Milestone 6 preparation

Files changed:
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- document which transition fields are learner-safe for a first replay-buffer import and clarify how the current HP-based reward is expected to teach defense only through delayed credit

Implementation notes:
- recorded a first learner whitelist centered on:
  - executed action fields
  - reward / done / terminal fields
  - HP / stun / movement deltas
  - character IDs and executed model version as metadata
- explicitly marked requested-action heuristics, observed attack-state fields, and cumulative overlay counters as debug / analysis-only for the first learner import
- clarified that:
  - `reward_accum` remains `delta_opp_hp - delta_self_hp` plus round win/loss bonus
  - defense and avoidance are expected to arrive through long-horizon credit rather than a dedicated v1 defensive label
  - `overlay_attack_*` fields remain auxiliary labels until move-family validation proves they are learner-safe across normals, specials, projectiles, throws, and multistage moves

Validation:
- reviewed the updated learner-field and reward notes against the existing Milestone 4 closeout notes and current `src/rl/rl_session.c` reward / ledger export logic

## 2026-04-23: Milestone 5 Model Version Plumbing

Milestone:
- Milestone 5: Async learner and model hot-swap

Files changed:
- `src/rl/rl_session.h`
- `src/rl/rl_session.c`
- `src/rl/rl_observation.c`
- `tools/rl_probe_server.py`
- `docs/config.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- make model versions visible in packets, overlay, and transition logs before adding learner hot-swap machinery

Implementation notes:
- MiSTer now sends `RLObsPacketHeader.model_version_expected` from the currently executed remote model version
- accepted remote action packets store `RLActionPacket.model_version` in the queue and ledger
- transition NDJSON now exports:
  - `model_version_expected`
  - `model_version_requested`
  - `model_version_executed`
- RL net overlay shows current model version as `MV`
- `tools/rl_probe_server.py --model-version N` stamps fixed-policy action packets for bring-up

Validation:
- `python3 -m py_compile tools/rl_probe_server.py` passed.
- `git diff --check` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed.

## 2026-04-23: Milestone 5 Async Learner Skeleton

Milestone:
- Milestone 5: Async learner and model hot-swap

Files changed:
- `tools/rl_probe_server.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- split the remote-side critical inference path from slower learner/log processing before adding real training or hot-swap

Implementation notes:
- `tools/rl_probe_server.py` now keeps UDP observation handling and action replies on the main thread
- optional `--transition-log PATH` starts a daemon learner/log-reader thread that tails local transition NDJSON
- the learner/log reader reports:
  - transition rows and done count
  - latest episode
  - attack event/contact/whiff counts
  - latest executed model version
  - inference response latency samples as `count:p50/p95/maxus`
- `--learner-tail-from-start` imports an existing file from the beginning; default behavior tails only new rows
- this is intentionally a skeleton: it proves non-critical learner work can run beside inference, but it does not train or hot-swap weights yet

Validation:
- `python3 -m py_compile tools/rl_probe_server.py` passed.
- local UDP bind / learner-tail smoke passed with `/tmp/rl-transitions-smoke.ndjson`, reporting `rows=2 done=1 ep=1 atk=2/1/1 model=12`
- `git diff --check` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed.

## 2026-04-23: Probe Scripted Move Policies

Milestone:
- Milestone 5: Async learner and model hot-swap

Files changed:
- `tools/rl_probe_server.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- add deterministic special/throw action scripts for validating command input, contact, whiff, and future outcome labeling

Implementation notes:
- added `--policy ryu-fireball`, which loops:
  - `DOWN`
  - `DOWN_FORWARD`
  - `FORWARD`
  - `FORWARD + LP`
  - neutral recovery frames
- added `--policy throw`, which loops:
  - `FORWARD + LP + LK`
  - neutral recovery frames
- added `--policy tatsu`, which loops:
  - `DOWN`
  - `DOWN_BACK`
  - `BACK`
  - `BACK + LK`
  - neutral recovery frames
- added `--policy shoryuken`, which loops:
  - `FORWARD`
  - `DOWN`
  - `DOWN_FORWARD`
  - `DOWN_FORWARD + HP`
  - neutral recovery frames
- added `--policy-repeat-delay-ms N`, which holds neutral after each scripted policy loop before repeating
- scripted policies use the existing relative-movement action wire, so MiSTer still maps forward/back/down-forward/down-back at execution time based on current facing

Validation:
- `python3 -m py_compile tools/rl_probe_server.py` passed.
- `git diff --check` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed.

## 2026-04-23: Character Identity in Transition Ledger

Milestone:
- Milestone 4 closeout / Milestone 5 preparation

Files changed:
- `src/rl/rl_session.c`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- make transition rows self-describing for matchup-aware learner import

Implementation notes:
- each transition NDJSON row now includes:
  - `agent_character_id`
  - `agent_character_name`
  - `opponent_character_id`
  - `opponent_character_name`
- character IDs are captured from runtime `My_char[self/opp]` when the decision ledger entry is created
- learner import should use the ID fields as canonical and names as debug metadata

Validation:
- `git diff --check` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed.

## 2026-04-23: Event-Aligned Attack Outcomes in Ledger

Milestone:
- Milestone 4: Decision ledger and transition logging

Files changed:
- `src/rl/rl_session.c`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- align transition ledger attack contact / whiff accounting with the verified RL outcome overlay counters

Implementation notes:
- transition NDJSON now exports event-level overlay outcome fields:
  - `overlay_attack_event_finalized`
  - `overlay_attack_contact`
  - `overlay_attack_whiff`
  - `overlay_attack_active_count`
  - `overlay_attack_contact_count`
  - `overlay_attack_whiff_count`
- only the first exported transition after an attack event finalizes gets `overlay_attack_event_finalized=1`, so jq counting should filter on that flag to avoid duplicate counts
- the older `requested_attack_made_contact` / `requested_attack_likely_whiffed` decision-window heuristics remain in the log for comparison, but the event-level overlay fields are the preferred bring-up counters now

Validation:
- `git diff --check` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed.
- Hardware ledger/overlay closeout passed with the sampled window:
  - `rows=274`
  - `overlay_attack_events=23`
  - `overlay_attack_contacts=3`
  - `overlay_attack_whiffs=20`
  - `last_ah=23`
  - `last_acc=3`
  - `last_awc=20`
  - ledger event totals matched the RL Outcome overlay counters

Status:
- Milestone 4 is closed.
- Remaining refinement items are intentionally deferred to later schema/learner work:
  - split `contact` into hit / blocked / throw when we need richer reward shaping
  - decide whether the older decision-window `requested_attack_*` heuristics should be removed after replay-buffer import lands
  - make model/version fields part of Milestone 5 logs and packets

## 2026-04-23: Outcome Overlay Attack Counters

Milestone:
- Milestone 4: Decision ledger and transition logging

Files changed:
- `src/rl/rl_observation.c`
- `src/rl/rl_session.h`
- `src/rl/rl_session.c`
- `docs/config.md`

Purpose:
- make on-screen RL debug easier to compare against visible gameplay by adding per-round accumulated attack-start / contact / whiff counters

Implementation notes:
- added round-episode counters to `RLRemoteDebugState`:
  - `episode_attack_active_count`
  - `episode_attack_contact_count`
  - `episode_attack_whiff_count`
- these counters now finalize per overlay attack event instead of per exported transition:
  - `ACC` increments when the finalized event saw contact
  - `AWC` increments when the finalized event ended as a likely whiff
  - `AH` increments once per finalized attack event
- counters reset on remote runtime reset and on round/episode rollover
- outcome overlay now adds:
  - `AH`: accumulated real attack starts this round
  - `ACC`: accumulated contacts this round
  - `AWC`: accumulated likely whiffs this round
  - `AC` / `AW`: last finalized overlay attack event outcome, aligned with the accumulated counters rather than the raw ledger heuristics

Validation:
- `git diff --check` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed.

## 2026-04-23: Milestone 4 Attack Activation Refinement

Milestone:
- Milestone 4: Decision ledger and transition logging

Files changed:
- `src/rl/rl_observation.h`
- `src/rl/rl_observation.c`
- `src/rl/rl_session.h`
- `src/rl/rl_session.c`
- `docs/config.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- separate raw attack-button pulses from the smaller set of decisions that actually become a new in-game attack, so whiff/contact counts line up better with observed gameplay

Implementation notes:
- added runtime edge fields for both attack-routine and attack-counter bring-up:
  - `self_attack_routine_started`
  - `opp_attack_routine_started`
  - `self_attack_counter_started`
  - `opp_attack_counter_started`
- transition logs now also export:
  - `requested_attack_became_active`
  - `observed_attack_counter_started`
- `requested_attack_became_active` is now driven by the defender-side `Attack_Counter` edge and is the preferred first-pass count for "real punches/kicks actually started"
- `requested_attack_likely_whiffed` now keys off `requested_attack_became_active && !requested_attack_made_contact` instead of the broader `current_attack != 0` state-seen flag
- RL outcome overlay now shows `AR` so runtime bring-up can distinguish:
  - `AI`: input pulse sent
  - `AR`: attack counter actually advanced
  - `OS`: older `current_attack`-derived debug signals plus attack-counter edge

Validation:
- `git diff --check` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed.

Follow-up:
- retest `--policy hp` and compare `requested_attack_became_active` against visible punch count

## 2026-04-23: Human-Opponent Remote Policy Routing

Milestone:
- Milestone 3: Remote inference only

Files changed:
- `src/rl/rl_session.c`
- `docs/config.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- let `P1H` / `P2H` use the same remote-policy inference path as CPU-opponent sessions so human-opponent testing and debug runs stay on the real network/action pipeline

Implementation notes:
- `RLSession_RemoteControlEnabled()` no longer disables the remote path just because `human_opponent` is enabled
- when `rl-opponent-mode = human`:
  - `rl-network = on` now uses remote action queue/execution
  - `rl-network = off` still uses the old scripted movement helper for Milestone 0B validation
- guarded the older scripted/local-fake helpers so they do not run when the remote path is active
- this keeps `P1H` / `P2H` labels accurate while making them more useful for controlled remote debugging

Validation:
- `git diff --check` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed.

Follow-up:
- hardware-test `P1H` / `P2H` with `rl-network = on` and confirm `OBS/Q/EX` advance normally while the opponent side remains human-controlled

## 2026-04-23: Milestone 4 Attack Outcome Semantics Refinement

Milestone:
- Milestone 4: Decision ledger and transition logging

Files changed:
- `src/rl/rl_observation.h`
- `src/rl/rl_observation.c`
- `src/rl/rl_session.h`
- `src/rl/rl_session.c`
- `docs/config.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- separate "RL actually sent an attack input pulse" from "the game runtime observed an attack-state edge" so transition logs can be used for learner/debug analysis without over- or under-counting attacks

Implementation notes:
- added `requested_attack_input_started` to transition logs; it is true when the executed decision contains nonzero attack bits
- added observed runtime fields:
  - `observed_attack_state_started`
  - `observed_attack_code_changed`
  - `self_attack_code_changed` / `opp_attack_code_changed`
- `observed_attack_state_started` remains the strict `current_attack: 0 -> nonzero` edge, which explains why it can be much lower than the number of HP decisions when `current_attack` stays nonzero
- `observed_attack_code_changed` captures nonzero runtime attack-code changes and is useful for diagnosing engine semantics, but it is not the source of truth for input attempts
- removed the temporary `requested_attack_started` alias so the schema now has one canonical input-attempt field
- RL outcome overlay now shows `AI`, `OS`, `AC`, and `AW` instead of the older compact `ASstarted/state/contact/whiff` grouping

Validation:
- `git diff --check` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed.

Follow-up:
- hardware-test `--policy hp` and count `requested_attack_input_started` versus `observed_attack_state_started` / `observed_attack_code_changed`

## 2026-04-22: Milestone 3 Remote Queue And Execution MVP

Milestone:
- Milestone 3: Remote inference only

Files changed:
- `src/rl/rl_protocol.h`
- `src/rl/rl_net.h`
- `src/rl/rl_net.c`
- `src/rl/rl_session.h`
- `src/rl/rl_session.c`
- `src/rl/rl_observation.c`
- `tools/rl_probe_server.py`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- move Milestone 3 from packet counting into the first real remote control loop
- queue accepted remote actions by `target_frame` and execute them through the existing raw-input override path

Implementation notes:
- added a packed `RLObsPacketHeader` for the first decision-frame observation send path
- MiSTer now sends an observation header every `decision_interval_frames` once hello/ack is accepted
- `src/rl/rl_session.c` now owns a small pending action queue plus a small in-flight expectation table keyed by `(episode_id, decision_id, target_frame)`
- accepted `RLActionPacket` now flows through:
  - Milestone 2 session gate in `src/rl/rl_net.c`
  - minimal expectation-table match in `src/rl/rl_session.c`
  - pending queue insertion by `target_frame`
  - execution on the intended frame through `p1sw_buff/p2sw_buff`
- added a first fallback policy:
  - if a due expected target frame has no valid queued action, reuse the last executed remote action for `action_hold_frames`
- extended `RL Debug` with Milestone 3 counters:
  - `OBS`, `Q`, `EX`, `LT`, `DU`, `TM`, `FB`
- extended `tools/rl_probe_server.py` so it can receive Milestone 3 observation headers and reply with a fixed action policy while still preserving the Milestone 2 gate-test modes

Validation:
- `python3 -c "import ast, pathlib; ast.parse(pathlib.Path('tools/rl_probe_server.py').read_text())"` passed.
- `git diff --check` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed.

Follow-up:
- run MiSTer-side validation for fixed remote actions and confirm `OBS/Q/EX` move together on hardware
- separate real duplicate-rule handling from queue-capacity fallback once the first hardware run is in
- keep the full decision ledger / transition logging work for Milestone 4

Update after hardware retest:
- MiSTer hardware produced stable packet flow with:
  - `OBS891 Q1/890 EX886 LT1 DU0 TM0 FB1`
- `--policy hp` exposed one MVP behavior bug:
  - the overlay showed HP pressed, but the character often did not punch because remote attack bits were held for the full `action_hold_frames` window instead of producing a one-frame press edge
- fixed in `src/rl/rl_session.c`:
  - movement bits still hold for `action_hold_frames`
  - attack bits now pulse for one frame only
- hardware retest confirmed `--policy hp` now produces visible punches as expected

Further Milestone 3 closeout work:
- duplicate-rule handling now persists a small seen-decision table in `src/rl/rl_session.c`
- first accepted `(episode_id, decision_id, target_frame)` is remembered even after execution/fallback
- later packets with the same tuple are now counted as `DU`
- later packets with the same `(episode_id, decision_id)` but a different `target_frame` are now counted as `TM`
- `tools/rl_probe_server.py` gained:
  - `--obs-reply-mode normal`
  - `--obs-reply-mode duplicate`
  - `--obs-reply-mode wrong-target`
  so MiSTer-side `DU/TM` counters can be validated deterministically on hardware

Milestone 3 closeout:
- hardware validation also confirmed delayed relative `forward/back` behavior remains correct across side switches
- Milestone 3 is now considered complete

## 2026-04-22: Milestone 4 Decision Ledger And Transition Export MVP

Milestone:
- Milestone 4: Decision ledger and transition logging

Files changed:
- `src/rl/rl_session.h`
- `src/rl/rl_session.c`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- make the remote control loop trainable by recording what was requested, what actually executed, and what reward span that executed decision accrued

Implementation notes:
- added a fixed-size decision ledger keyed by `(episode_id, decision_id)` in `src/rl/rl_session.c`
- ledger entries are created when MiSTer sends an observation header
- when an action packet arrives, the ledger entry records `requested_action_wire`
- when the decision becomes active, the ledger entry records:
  - `executed_action_wire`
  - `execution_frame_actual`
  - `execution_source`
  - decoded `executed_move_intent`
  - decoded `executed_attack_bits`
- exported transitions now also include:
  - decoded `requested_move_intent`
  - decoded `requested_attack_bits`
  - `was_executed`
  - `terminal_reason`
- reward now accumulates onto the currently active ledger entry using:
  - per-frame `delta_opp_hp - delta_self_hp`
  - plus `+100/-100` round result bonus at episode closeout
- round changes now finalize the previous episode's ledger entries with `done=true`
- transitions are exported as NDJSON to `logs/rl-transitions.ndjson` under `Paths_GetPrefPath()`

Validation:
- `git diff --check` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed.

Follow-up:
- run a short MiSTer session and inspect `rl-transitions.ndjson`
- revisit richer event-delta fields from the Human-Fighter Observer Gap Review
- add remote-side transition transport after the local ledger output is validated

## 2026-04-22: Milestone 4 First-Pass Action Outcome And Event Delta Fields

Milestone:
- Milestone 4: Decision ledger and transition logging

Files changed:
- `src/rl/rl_observation.h`
- `src/rl/rl_observation.c`
- `src/rl/rl_session.c`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- make the local observer and exported transitions more useful for training by adding first-pass action-outcome and event-delta signals that are already derivable from stable runtime state

Implementation notes:
- `RLObservationV1` now includes per-frame derived fields for:
  - HP delta
  - X/Y delta
  - stun delta
  - airborne
  - entered hit-stop
  - entered contact state
  - entered damage state
- the transition ledger now accumulates and exports decision-span aggregates for:
  - HP delta
  - stun delta
  - self / opponent X and Y movement
  - airborne-seen flags
  - entered hit-stop / contact / damage flags
- kept the derivation conservative:
  - airborne uses `position_y != 0`
  - contact state uses `guard_flag != 0 || hit_stop`
  - damage state uses HP loss or stun increase
- moved the aggregation source to `RLObservation_OnFrameEnd()` so the ledger records post-logic frame results rather than pre-logic input staging
- explicitly deferred crouching and richer action-phase labels until a more trustworthy runtime source is identified

Validation:
- `git diff --check` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed.

Follow-up:
- verify the new `DH/DS/AB/EH/EC/ED` RL debug overlay lines on MiSTer
- inspect `rl-transitions.ndjson` for the new delta / event fields during hit, block, jump, and whiff cases
- revisit explicit `hit / blocked / whiff / throw` outcome enums in a later Milestone 4 refinement

## 2026-04-23: Milestone 4 Relative Movement And Request Outcome Fields

Milestone:
- Milestone 4: Decision ledger and transition logging

Files changed:
- `src/rl/rl_observation.h`
- `src/rl/rl_observation.c`
- `src/rl/rl_session.h`
- `src/rl/rl_session.c`
- `src/port/config/config.h`
- `src/port/config/config.c`
- `src/port/sdl/sdl_app.c`
- `vendor/Menu_MiSTer/menu.sv`
- `vendor/Main_MiSTer/thirdsarm_wrapper.cpp`
- `docs/config.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- make transition records easier for the learner to consume by adding facing-relative movement and first-pass requested-action outcome fields

Implementation notes:
- added opponent facing to `RLObservationV1` so opponent movement can also be converted into facing-relative motion
- transition logs now include:
  - `delta_self_forward`
  - `delta_opp_forward`
  - `requested_movement_succeeded`
  - `requested_attack_entered_state`
  - `requested_attack_made_contact`
  - `requested_attack_likely_whiffed`
  - `requested_attack_input_started`
  - `observed_attack_state_started`
  - `observed_attack_code_changed`
  - `requested_jump_started`
  - `self_attack_started` / `opp_attack_started`
  - `self_attack_code_changed` / `opp_attack_code_changed`
  - `self_airborne_started` / `opp_airborne_started`
- RL debug overlay now includes a compact outcome line:
  - `RFself/opp`
  - `MS`
  - `AI`
  - `OSstate/code`
  - `AC`
  - `AW`
  - `J`
- documented that:
  - world X/Y deltas remain signed world-coordinate deltas
  - forward deltas are facing-relative
  - stun deltas are signed and can be negative when stun recovers
  - contact state is conservative and not a precise hit/block enum
  - unexecuted terminal entries should usually be filtered by the first replay buffer
- `rl-transitions.ndjson` is still an evolving debug/training schema
- attack and airborne edge fields were added so match-level analysis can count starts instead of counting all decision windows that merely saw an attack/airborne state
- added `rl-debug-view` and the MiSTer OSD `RL Debug View` selector:
  - `Off`
  - `All`
  - `Net`
  - `Input`
  - `Fight`
  - `Outcome`
- switching `RL Debug View` persists `rl-debug-view` and signals the runtime to reread overlay settings
- the colored key row now appears only in `All` and `Input` views

Validation:
- `git diff --check` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed.
- `/home/olhua/src/3s-mister-arm/tools/mister-wrapper/build-hps.sh` passed.

Follow-up:
- verify `forward` produces nonzero `delta_self_forward` and `requested_movement_succeeded=1`
- verify `hp` produces attack entered/contact/whiff outcomes in plausible cases
- defer precise `hit / blocked / whiff / throw` enums until the hitcheck and throw paths are decoded more confidently

## 2026-04-22: Milestone 2 Action Session Gate

Milestone:
- Milestone 2: Session handshake, network probe, and delay budget

Files changed:
- `src/rl/rl_protocol.h`
- `src/rl/rl_net.h`
- `src/rl/rl_net.c`
- `src/rl/rl_observation.c`
- `src/args.c`
- `tools/rl_probe_server.py`
- `docs/config.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- finish the remaining Milestone 2 session-protection work for future action packets
- reject unacknowledged or stale-session action traffic before Milestone 3 queue/execution begins

Implementation notes:
- added `RLActionPacket` to `src/rl/rl_protocol.h`
- MiSTer now binds a local non-blocking UDP action socket on `rl-agent-action-port`
- action packets are counted and gated by:
  - valid magic/version
  - hello/ack accepted
  - matching live `session_nonce`
- accepted action packets are counted as gate-passed only; they are intentionally not queued or executed yet
- added counters to `RL Debug`:
  - `ACT`, `OK`, `UA`, `SN`, `BV`, `BM`
- extended `tools/rl_probe_server.py` with:
  - `--action-port`
  - `--action-mode valid`
  - `--action-mode stale`
  - `--action-mode pre-ack`
  so MiSTer-side gate behavior can be validated from one tool

Validation:
- `git diff --check` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed.
- `python3 -c "import ast, pathlib; ast.parse(pathlib.Path('tools/rl_probe_server.py').read_text())"` passed.

Follow-up:
- Milestone 2 gate work is complete.
- Milestone 3 should start with queueing accepted action packets by `target_frame` instead of only counting them.

## 2026-04-22: Milestone 2 Target-Network Timing Baseline

Milestone:
- Milestone 2: Session handshake, network probe, and delay budget

Files changed:
- `src/rl/rl_protocol.c`
- `src/port/config/config.c`
- `src/main.c`
- `docs/config.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- record the first real MiSTer <-> remote PC RTT measurement
- stop treating `k / decision_interval / action_hold` as placeholders

Implementation notes:
- measured on the actual MiSTer + Windows probe path using the `RL Debug` overlay:
  - `NETOK S128 P16819/17568/20752 MAX30718`
  - `p50 = 16819us`
  - `p95 = 17568us`
  - `p99 = 20752us`
  - `max = 30718us`
- one frame at 60fps is about `16667us`, so this path sits around one frame at p50 and can burst toward two frames at the max sample.
- selected the first conservative baseline as:
  - `candidate_k_delay_frames = 4`
  - `decision_interval_frames = 4`
  - `action_hold_frames = 4`
- updated runtime defaults so config-generated and protocol-default timing now match the chosen baseline.

Validation:
- MiSTer runtime probe reached `NETOK` and accumulated 128 samples on the actual target network.
- `git diff --check` pending local re-run after this doc/default sync.

Follow-up:
- Milestone 2 timing baseline is now fixed and ready for Milestone 3
- use `4/4/4` as the Milestone 3 starting point unless new measurements on the target network meaningfully change

## 2026-04-22: Milestone 2 OSD Network Toggle

Milestone:
- Milestone 2: Session handshake, network probe, and delay budget

Files changed:
- `vendor/Menu_MiSTer/menu.sv`
- `vendor/Main_MiSTer/thirdsarm_wrapper.cpp`
- `src/configuration.h`
- `src/args.c`
- `src/main.c`
- `src/port/config/config.h`
- `src/port/config/config.c`
- `src/rl/rl_net.c`
- `docs/config.md`
- `docs/plan-remote-rl-agent.md`

Purpose:
- put the RL network probe enable/disable control in MiSTer OSD
- keep remote IP, obs/action ports, and timing knobs in `games/3s-arm/config` for easy manual editing

Implementation notes:
- added OSD `RL Settings -> RL Network (Restart), Off/On`
- wrapper persists that menu item as `rl-network = off|on`
- wrapper strips forwarded RL network CLI/config knobs and injects only `--rl-network` from the persisted setting, keeping the config file authoritative for IP/ports/timing
- runtime now requires all three conditions before opening a UDP socket:
  - `--rl-agent` / RL agent mode active
  - `rl-network = on` / `--rl-network`
  - `rl-agent-remote-ip` / `--rl-remote-ip` is set
- `rl-agent-remote-ip`, `rl-agent-obs-port`, `rl-agent-action-port`, `rl-agent-delay-frames`, `rl-agent-decision-interval`, and `rl-agent-action-hold` are read from config after `Config_Init()`

Validation:
- `git diff --check` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed.
- `/home/olhua/src/3s-mister-arm/tools/mister-wrapper/build-hps.sh` passed and produced `build/mister-wrapper-hps/MiSTer_3S-ARM`.
- FPGA wrapper core / `.rbf` rebuild is still required before `RL Network (Restart)` appears on MiSTer OSD hardware.

Follow-up:
- rebuild wrapper/core so the new `CONF_STR` entry appears on MiSTer OSD
- on hardware, verify `RL Network (Restart)` writes `rl-network = on/off` and that `RL Debug` stays `NETOFF` until network is on plus a remote IP is configured

## 2026-04-22: Milestone 2 UDP Probe Path

Milestone:
- Milestone 2: Session handshake, network probe, and delay budget

Files changed:
- `src/rl/rl_net.h`
- `src/rl/rl_net.c`
- `src/rl/rl_observation.c`
- `src/configuration.h`
- `src/args.c`
- `src/main.c`
- `src/port/config/config.h`
- `src/port/config/config.c`
- `tools/rl_probe_server.py`
- `docs/config.md`
- `docs/plan-remote-rl-agent.md`

Purpose:
- add the first live remote RL transport probe without changing gameplay input behavior
- make target-network RTT/jitter visible in `RL Debug`

Implementation notes:
- RL UDP probe is default-off.
- It opens a socket only when RL agent mode is enabled and `rl-agent-remote-ip` / `--rl-remote-ip` is set.
- MiSTer sends `HELLO`, accepts matching `ACK`, then sends periodic `PING` packets and records matching `PONG` RTT samples.
- `RL Debug` now shows `NETOFF`, `NETHELLO`, `NETOK`, or `NETERR`, plus sample count, p50/p95/p99/max RTT, and error count.
- `tools/rl_probe_server.py` is the matching minimal remote-side UDP ACK/PONG responder.
- `rl-agent-obs-port`, `rl-agent-action-port`, `rl-agent-delay-frames`, `rl-agent-decision-interval`, and `rl-agent-action-hold` are now config/CLI backed. The action port is reserved for the later action packet path.

Validation:
- `tools/mister/build-game.sh --flavor telemetry` passed.
- `git diff --check` passed.
- `python3 -c "import ast, pathlib; ast.parse(pathlib.Path('tools/rl_probe_server.py').read_text())"` passed.
- Local UDP smoke test passed with `tools/rl_probe_server.py` bound to `127.0.0.1:37330` and a small Python client confirming:
  - `HELLO` receives `ACK`
  - `PING` receives `PONG`
  - `PONG` preserves the original ping timestamp for RTT measurement

Follow-up:
- run the probe on the actual MiSTer + remote PC network
- record p50/p95/p99/max RTT after at least 128 samples
- choose `candidate_k_delay_frames`, `decision_interval_frames`, and `action_hold_frames` from the recorded target-network data
- then connect the action queue / stale nonce rejection path

Primary plan:

- `docs/plan-remote-rl-agent.md`

Current branch policy:

- keep upstream baseline branches clean
- implement RL work on the local work branch only
- keep RL implementation independent from `src/netplay/*`

Project rules:

- `AGENTS.md`
- `docs/agent-memory/remote-rl-agent-rules.md`

## How To Use This Log

- Add one work-session entry whenever code, config, protocol, or deployment behavior changes.
- Link each entry to the relevant milestone from `docs/plan-remote-rl-agent.md`.
- Record exact commands, build artifacts, MiSTer deploy paths, and observed behavior.
- Record failed attempts too; they are useful for avoiding repeated debugging.
- Keep milestone checkboxes in the plan as the high-level tracker.
- Keep this file as the detailed implementation journal.

## Current Status

Last updated: 2026-04-24

- [x] Milestone 0A: Baseline match-flow confirmation spike
- [x] Milestone 0B: Facing and remap validation micro-spike
- [x] Milestone 0C: Local fake agent spike
- [x] Milestone 1: Compact observation builder
- [x] Milestone 2: Session handshake, network probe, and delay budget
- [x] Milestone 3: Remote inference only
- [x] Milestone 4: Decision ledger and transition logging
- [ ] Milestone 5: Async learner and model hot-swap
- [ ] Milestone 6: Higher-control-rate policy and curriculum

Current read:

- Milestone 5 is active.
- Implemented Milestone 5 slices include protocol v2 run identity, unique round episode ids, model-version packet/log plumbing, learner-safe replay import, transition pull mirroring, and non-critical episode-batch upload.
- Remaining Milestone 5 work is real versioned actor publication, atomic actor hot-swap, and latency validation while learner updates are active.

## Decision Log

### 2026-04-21: Keep RL Agent Independent From Netplay

Status:

- accepted

Decision:

- implement the remote RL agent as a local input provider plus observation exporter
- keep implementation under `src/rl/*`
- do not implement RL transport or scheduling inside `src/netplay/*`
- do not treat the remote PC as a Gekko or P2P netplay peer
- use `MODE_VERSUS + rl_session_active` as the v1 baseline match flow

Reason:

- upstream may later implement or rewrite P2P netplay
- isolating RL code keeps future upstream merges smaller and safer
- the RL architecture is authoritative MiSTer simulation plus remote inference, not peer-to-peer rollback

Follow-up:

- keep shared-file edits limited to small hook calls
- use neutral modules only if a helper must be shared with future upstream netplay

### 2026-04-21: Use Relative-Direction Wire Mode

Status:

- accepted

Decision:

- remote sends `action_wire` with a relative movement subfield and final attack/button bits
- MiSTer remaps relative movement into raw directional `SWKey` bits at execution time
- MiSTer does not own macro expansion or semantic policy interpretation

Reason:

- action decisions are delayed from `obs_frame` to `target_frame`
- characters may switch sides during that delay
- absolute `LEFT` / `RIGHT` actions can invert the intended forward/back meaning

Follow-up:

- Milestone 0B must verify `rl_flag`, forward/back remap, delayed side-switch behavior, and fallback remap behavior

### 2026-04-21: Round-Scoped Episodes

Status:

- accepted

Decision:

- v1 uses one round as one `episode_id`
- match progress remains observation context through `round_num`, `self_round_wins`, and `opp_round_wins`
- `frame_id` remains session-wide monotonic across episode resets

Reason:

- round boundaries reset key fighting state and simplify queue, ledger, and recurrent-state reset behavior

Follow-up:

- transition logs must preserve enough match context to analyze multi-round behavior later

## Work Sessions

### 2026-04-21: Planning And Tracking Setup

Milestones:

- Milestone 0A through Milestone 6 planning

Changes:

- created remote RL agent implementation plan
- converted milestones into a tracking checklist
- added this engineering log

Notes:

- implementation has not started yet
- first implementation step should be Milestone 0A

Commands:

```sh
# No build or test commands run for this documentation-only setup.
```

Results:

- plan exists at `docs/plan-remote-rl-agent.md`
- engineering log exists at `docs/remote-rl-agent-engineering-log.md`

### 2026-04-21: Added Remote RL Agent Project Rules

Milestones:

- Project workflow setup

Changes:

- added `docs/agent-memory/remote-rl-agent-rules.md`
- updated `AGENTS.md` to require loading the remote RL agent rules for RL-related sessions
- linked the engineering log to the project rules

Notes:

- new sessions should read the plan, checklist, engineering log, and project rules before implementation
- future code changes should state purpose, expected effect, risks, planned files, and validation before editing
- after code changes, update the plan checklist and engineering log, then commit code and related docs together unless explicitly told not to commit

Commands:

```sh
# No build or test commands run for this documentation-only workflow update.
```

Results:

- project rules exist at `docs/agent-memory/remote-rl-agent-rules.md`
- root agent instructions now point to the remote RL agent rules

### 2026-04-21: Milestone 0A Operator Setup Hook

Milestones:

- Milestone 0A: Baseline match-flow confirmation spike

Files changed:

- `src/configuration.h`
- `src/args.c`
- `src/main.c`
- `src/rl/rl_session.h`
- `src/rl/rl_session.c`
- `src/sf33rd/Source/Game/menu/menu.c`
- `src/sf33rd/Source/Game/game.c`

Purpose:

- add a default-off RL session flag for the baseline `MODE_VERSUS + rl_session_active` spike
- allow `--rl-agent --rl-player 1|2` to force one side to player-input control and the other side to CPU control

Implementation notes:

- added `RemoteRLAgentConfiguration`
- added CLI flags `--rl-agent` and `--rl-player`
- added `RLSession_ApplyVersusOperatorSetup()`
- hook is called after `Setup_VS_Mode()` sets both players to human
- hook is also called in `Game2_0()` after existing `Partner_Type` logic can set a side to CPU
- implementation stays under `src/rl/*` and does not touch `src/netplay/*`

Validation:

```sh
tools/mister/build-game.sh --flavor telemetry
```

Result:

- passed
- package created at `build/mister-telemetry-package`

Failures or surprises:

- first build failed because `rl_session.c` included `workuser.h` but not `plcnt.h`, so `plw` was undeclared
- fixed by including `sf33rd/Source/Game/engine/plcnt.h`

Follow-up:

- run the game with `--rl-agent --rl-player 1` or `--rl-agent --rl-player 2`
- verify round start behavior
- verify round end behavior
- verify winner flow behavior
- verify reset behavior
- only mark Milestone 0A checklist items complete after runtime validation

### 2026-04-21: MiSTer OSD RL Agent Launch Toggle

Milestones:

- Milestone 0A: Baseline match-flow confirmation spike

Files changed:

- `vendor/Menu_MiSTer/menu.sv`
- `vendor/Main_MiSTer/thirdsarm_wrapper.cpp`
- `docs/config.md`

Purpose:

- remove the need to launch from the MiSTer console with manual `--rl-agent --rl-player` arguments
- add an OSD menu toggle that persists RL agent launch mode and injects the correct startup args on relaunch

Implementation notes:

- added `RL Agent (Restart)` to `CONF_STR` with `Off / Player 1 / Player 2`
- assigned the menu to wrapper status bits `[48:47]`, which required widening the wrapper-side `status` bus
- added wrapper config read/write helpers for `rl-agent-player = off|1|2`
- wrapper now strips any forwarded `--rl-agent` / `--rl-player` args and re-injects launch args from the persisted OSD setting so wrapper config stays authoritative on MiSTer
- RL agent mode is seeded back into the OSD from persisted config on startup and restart
- changing the OSD option persists immediately, but takes effect only after wrapper `Restart`

Validation:

```sh
/home/olhua/src/3s-mister-arm/tools/mister-wrapper/build-hps.sh
/home/olhua/src/3s-mister-arm/tools/mister/build-game.sh --flavor telemetry
```

Result:

- passed
- HPS wrapper built at `build/mister-wrapper-hps/MiSTer_3S-ARM`
- telemetry package still built at `build/mister-telemetry-package`
- FPGA core / `.rbf` rebuild still pending because the `CONF_STR` change must be rolled into the menu/core image before OSD deployment testing

Follow-up:

- rebuild the menu/core image because `CONF_STR` changed
- deploy to MiSTer and verify:
  - `RL Agent (Restart)` appears in the OSD
  - selecting `Player 1` relaunches with `--rl-agent --rl-player 1`
  - selecting `Player 2` relaunches with `--rl-agent --rl-player 2`
  - selecting `Off` removes RL launch args on restart

### 2026-04-21: Lock VS Player-Type Menu Rows While RL Agent Is Active

Milestones:

- Milestone 0A: Baseline match-flow confirmation spike

Files changed:

- `src/sf33rd/Source/Game/menu/menu.c`

Purpose:

- keep the in-game VS option menu aligned with the actual RL baseline behavior
- avoid letting users interact with P1/P2 player-type rows that are later overridden by `RLSession_ApplyVersusOperatorSetup()`

Implementation notes:

- added a small local helper that treats game-option rows `8` and `9` as RL-managed when `RLSession_IsActive()`
- when RL is active, cursor movement skips those rows
- when RL is active, left/right modification is ignored on those rows
- this is a minimal v1 UX fix; it prevents contradictory editing without introducing new menu text assets

Validation:

```sh
/home/olhua/src/3s-mister-arm/tools/mister/build-game.sh --flavor telemetry
```

Result:

- passed
- telemetry package created at `build/mister-telemetry-package`

Follow-up:

- confirm on-device that the VS option cursor jumps over the two player-type rows while RL agent mode is enabled
- if stronger UX is needed later, add a visible `managed by RL agent` label or dimmed-state treatment

### 2026-04-21: Add RL Debug FPS Overlay Mode

Milestones:

- Milestone 0A: Baseline match-flow confirmation spike

Files changed:

- `vendor/Menu_MiSTer/menu.sv`
- `vendor/Main_MiSTer/thirdsarm_wrapper.cpp`
- `src/port/sdl/sdl_app.c`
- `src/port/sdl/fbdev_presenter.c`
- `docs/config.md`

Purpose:

- extend the MiSTer OSD `FPS Counter` menu with a fourth mode, `RL Debug`
- display RL baseline session state directly in the overlay during bring-up

Implementation notes:

- expanded the `FPS Counter` `CONF_STR` entry from `Off/FPS/Debug` to `Off/FPS/Debug/RL Debug`
- extended wrapper-side `show-fps` parsing and persistence to accept `rl-debug`
- extended game-side FPS overlay parsing with `FPS_OVERLAY_RL_DEBUG`
- when `rl-debug` is active, overlay text is now the compact slot marker `P0`, `P1`, or `P2`
- this mode intentionally reuses the existing `show-fps`/`SIGUSR1` path instead of adding a second OSD debug toggle

Validation:

```sh
/home/olhua/src/3s-mister-arm/tools/mister/build-game.sh --flavor telemetry
/home/olhua/src/3s-mister-arm/tools/mister-wrapper/build-hps.sh
```

Result:

- passed
- game package built successfully at `build/mister-telemetry-package`
- HPS wrapper built successfully at `build/mister-wrapper-hps/MiSTer_3S-ARM`
- FPGA core / `.rbf` rebuild is still required before the new `RL Debug` OSD menu item appears on MiSTer hardware

Follow-up:

- verify on MiSTer that `FPS Counter` cycles through all 4 modes
- verify `RL Debug` shows `P0`, `P1`, or `P2` correctly after wrapper restart

### 2026-04-21: Baseline VS Validation And RL Overlay Simplification

Milestones:

- Milestone 0A: Baseline match-flow confirmation spike

Files changed:

- `src/port/sdl/sdl_app.c`
- `docs/config.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:

- record successful MiSTer validation that the RL baseline VS flow works for both agent-side selections
- simplify the RL debug overlay text from `RL Agent: Off/P1/P2` to compact `P0/P1/P2`

Implementation notes:

- MiSTer validation confirmed that baseline RL VS launch works when the RL agent controls either player 1 or player 2
- `P0` now means RL agent disabled, while `P1` and `P2` indicate the active controlled slot
- the overlay remains specific to the dedicated `rl-debug` FPS counter mode

Validation:

```sh
# Hardware validation reported by MiSTer run testing.
```

Result:

- passed
- baseline VS mode works with RL agent configured for player 1
- baseline VS mode works with RL agent configured for player 2
- RL debug overlay text simplified to `P0`, `P1`, and `P2`

Follow-up:

- use Milestone 0A as the baseline foundation for the next scripted local fake-agent work

### 2026-04-21: Milestone 0A Runtime Validation Matrix Passed

Milestones:

- Milestone 0A: Baseline match-flow confirmation spike

Files changed:

- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:

- record that baseline runtime validation has completed successfully on MiSTer hardware
- close Milestone 0A with an explicit test matrix instead of a generic "seems okay" note

Implementation notes:

- validation was performed using the current baseline mode where the selected RL side remains on player-input routing and the opposite side remains on CPU routing
- this is still a baseline flow test, not a scripted or remote-agent control test

Validation:

```text
RL player 1: player wins a round
RL player 1: CPU wins a round
RL player 2: player wins a round
RL player 2: CPU wins a round
```

Result:

- passed
- `MODE_VERSUS + rl_session_active` works for RL player 1 and RL player 2
- round end, winner flow, and next-round reset behaved correctly in all four tested scenarios
- no blocking reason was found to fall back to a training-based baseline

Follow-up:

- move to Milestone 0B for `rl_flag` and delayed direction remap validation

### 2026-04-21: Add RL Settings And Scripted Movement For Milestone 0B

Milestones:

- Milestone 0B: Facing and remap validation micro-spike

Files changed:

- `src/configuration.h`
- `src/main.c`
- `src/args.c`
- `src/rl/rl_session.h`
- `src/rl/rl_session.c`
- `src/port/sdl/sdl_app.c`
- `vendor/Menu_MiSTer/menu.sv`
- `vendor/Main_MiSTer/thirdsarm_wrapper.cpp`
- `docs/config.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:

- support a human-controlled non-agent side during Milestone 0B so facing/remap checks are easier to reproduce than against live CPU behavior
- extend the RL debug overlay with concise opponent-routing and scripted-movement information
- group RL-related OSD settings under one `RL Settings` submenu

Implementation notes:

- added `--rl-opponent-human` on the game side and `rl-opponent-mode = cpu|human` on the MiSTer wrapper side
- moved `RL Agent (Restart)` and `RL Opponent (Restart)` into a new MiSTer OSD `RL Settings` submenu
- added `RL Movement` with `Forward`, `Back`, `Jump Forward`, and `Down Back`
- `RLSession_ApplyVersusOperatorSetup()` now routes the non-agent side to CPU or human input according to the RL opponent mode
- `RLSession_ApplyScriptedMovementToBuffers()` writes the selected fixed relative movement into the RL side's raw input buffer after `keyConvert()` and before input latch
- scripted movement is intentionally active only when RL is enabled and the non-agent side is routed to human input
- `rl-debug` overlay now shows concise routing codes:
  - `P0`: RL agent disabled
  - `P1C` / `P2C`: RL player 1 / 2 with CPU opponent
  - `P1H` / `P2H`: RL player 1 / 2 with human opponent
  - `:F`, `:B`, `:JF`, or `:DB`: active scripted movement in human-opponent validation mode

Validation:

```sh
/home/olhua/src/3s-mister-arm/tools/mister/build-game.sh --flavor telemetry
/home/olhua/src/3s-mister-arm/tools/mister-wrapper/build-hps.sh
```

Result:

- passed
- game package built successfully at `build/mister-telemetry-package`
- HPS wrapper built successfully at `build/mister-wrapper-hps/MiSTer_3S-ARM`
- FPGA core / `.rbf` rebuild is still required before the new `RL Settings` submenu appears on MiSTer hardware

Follow-up:

- verify on MiSTer that `RL Settings` contains `RL Agent`, `RL Opponent`, and `RL Movement`
- verify on MiSTer that `RL Opponent (Restart)` correctly switches the non-agent side between CPU and human input
- verify each scripted movement remaps correctly for both facings
- use the new human-opponent mode to run the Milestone 0B facing/remap spot checks

### 2026-04-21: Fix Scripted Movement Gate And Facing Remap

Milestones:

- Milestone 0B: Facing and remap validation micro-spike

Files changed:

- `src/rl/rl_session.c`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:

- prevent scripted RL movement from driving the cursor while still inside VS menu flow
- fix the observed forward/back inversion in the relative movement remap

Implementation notes:

- scripted movement now requires `mpp_w.inGame`, `Play_Mode == 1`, and `Game_pause == 0` in addition to RL active + human-opponent + `MODE_VERSUS`
- MiSTer testing showed the original `rl_flag` mapping assumption was inverted
- remap contract is now:
  - `rl_flag == 0`: facing world-left, so forward maps to `SWK_LEFT`
  - `rl_flag == 1`: facing world-right, so forward maps to `SWK_RIGHT`
- plan schema and Milestone 0B checklist were updated to match the observed contract

Validation:

```sh
/home/olhua/src/3s-mister-arm/tools/mister/build-game.sh --flavor telemetry
```

Result:

- passed
- game package built successfully at `build/mister-telemetry-package`

Follow-up:

- verify on MiSTer that scripted movement no longer acts in VS menu
- verify `Forward`, `Back`, `Jump Forward`, and `Down Back` now move in the intended relative direction for both `P1H` and `P2H`

### 2026-04-21: Stabilize Scripted Jump-Forward Across Cross-Over

Milestones:

- Milestone 0B: Facing and remap validation micro-spike

Files changed:

- `src/rl/rl_session.c`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:

- avoid one stale-facing jump after the RL side crosses over the human opponent

Implementation notes:

- MiSTer validation showed `Forward`, `Back`, `Jump Forward`, and `Down Back` were basically correct after the previous fix
- one remaining issue was observed: after a jump-forward crossed over the opponent, the next jump-forward could jump backward once, then recover on the following jump
- this suggests `rl_flag` can lag the cross-over by one input decision at the scripted-input hook point
- the 0B scripted movement helper now maps forward/back from current relative X position:
  - agent left of opponent -> forward is `SWK_RIGHT`
  - agent right of opponent -> forward is `SWK_LEFT`
  - exact same X position falls back to the current `rl_flag` mapping
- this change is intentionally scoped to the validation helper; the final remote action path can still decide whether to use facing, position, or explicit wire-mode semantics

Validation:

```sh
/home/olhua/src/3s-mister-arm/tools/mister/build-game.sh --flavor telemetry
```

Result:

- passed
- game package built successfully at `build/mister-telemetry-package`

Follow-up:

- verify on MiSTer that repeated `Jump Forward` remains toward the opponent immediately after crossing over

### 2026-04-21: Milestone 0B P1H/P2H Runtime Validation Passed

Milestones:

- Milestone 0B: Facing and remap validation micro-spike

Files changed:

- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:

- record successful MiSTer validation for the human-opponent relative movement checks
- close Milestone 0B before starting local fake-agent work

Implementation notes:

- runtime validation was reported for both `P1H` and `P2H`
- the tested RL movement selector values were:
  - `Forward`
  - `Back`
  - `Jump Forward`
  - `Down Back`
- validation covered the practical remap contract needed by the next local fake-agent step, including cross-over behavior after the position-based remap stabilization

Validation:

```text
P1H: RL Forward passed
P1H: RL Back passed
P1H: RL Jump Forward passed
P1H: RL Down Back passed
P2H: RL Forward passed
P2H: RL Back passed
P2H: RL Jump Forward passed
P2H: RL Down Back passed
```

Result:

- passed
- Milestone 0B checklist closed in the plan

Follow-up:

- start Milestone 0C by adding a CPU-opponent local fake-agent path that writes held scripted actions into the selected RL player's raw input buffer

### 2026-04-21: Start Milestone 0C Local Fake-Agent Sequence

Milestones:

- Milestone 0C: Local fake agent spike

Files changed:

- `src/main.c`
- `src/rl/rl_session.h`
- `src/rl/rl_session.c`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:

- start proving AI-vs-CPU control without networking
- add a local held-action sequence that drives the selected RL player while the non-agent side remains CPU-controlled

Implementation notes:

- renamed the main input hook call site to `RLSession_ApplyInputOverrideToBuffers()`
- retained the existing human-opponent 0B movement validation path
- added a CPU-opponent local fake-agent sequence with held forward, neutral attack, down-back, jump-forward attack, and back actions
- the sequence writes to `p1sw_buff` or `p2sw_buff` after `keyConvert()` and before the input latch
- local fake-agent state resets whenever the override is inactive, when human-opponent validation is active, or when gameplay is outside active unpaused VS play
- the implementation remains in `src/rl/*` plus the existing small `src/main.c` hook and does not touch `src/netplay/*`

Validation:

```sh
tools/mister/build-game.sh --flavor telemetry
```

Result:

- passed
- package created at `build/mister-telemetry-package`

Follow-up:

- verify on MiSTer with `P1C` and `P2C` that the agent-controlled side moves and attacks
- verify the non-agent side still runs CPU behavior
- verify held actions and sequence reset behavior across round transitions/menu exits

### 2026-04-21: Milestone 0C Runtime Validation Passed

Milestones:

- Milestone 0C: Local fake agent spike

Files changed:

- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:

- record successful MiSTer validation for the local CPU-opponent fake-agent path
- close Milestone 0C before moving to observation work

Implementation notes:

- runtime validation was reported for the local fake-agent path
- validation covered the selected RL side writing held scripted movement/attack input into the raw input buffer
- validation covered the non-agent side continuing to use CPU behavior
- no menu or round-flow regression was reported

Validation:

```text
P1C/P2C local fake-agent runtime validation passed.
Agent-controlled side moves and attacks.
CPU-controlled side fights normally.
Held scripted actions and reset behavior are acceptable for closing Milestone 0C.
```

Result:

- passed
- Milestone 0C checklist closed in the plan

Follow-up:

- move to Milestone 1: compact observation builder
- first implementation step should add a local `RLObservationV1` builder and an end-of-frame hook after `hit_check_main_process()`

### 2026-04-21: Add RL Observation Debug Overlay

Milestones:

- Milestone 1: Compact observation builder

Files changed:

- `src/rl/rl_observation.h`
- `src/rl/rl_observation.c`
- `src/sf33rd/Source/Game/game.c`
- `src/port/sdl/sdl_app.c`
- `src/port/sdl/fbdev_presenter.c`
- `docs/config.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:

- start local observation validation without networking or file logging
- put compact observation debug output into the existing `RL Debug` overlay
- show the RL-controlled side's effective raw input buttons on screen

Implementation notes:

- added `RLObservation_OnFrameEnd()` after `hit_check_main_process()`
- added a compact `RLObservationV1` state cache built from live player, stun, super, round, and input globals
- captured `round_start_hp[i]` on the first active observed round frame and recaptured on round changes or HP reset increases
- formatted `RL Debug` as three short lines:
  - route plus HP percentages
  - super, stun, X distance, facing sign, and round number
  - active input labels
- added multi-line overlay support for both SDL renderer debug text and MiSTer fbdev rasterized text
- kept output overlay-only for this slice; no disk logging or network path was added

Validation:

```sh
tools/mister/build-game.sh --flavor telemetry
```

Result:

- passed
- package created at `build/mister-telemetry-package`

Follow-up:

- verify on MiSTer that the overlay remains readable and does not cover important gameplay information
- validate HP, super, stun, position, facing, round, and input labels against visible gameplay
- fill out the rest of `RLObservationV1`, especially action-context fields, before closing Milestone 1

### 2026-04-21: Fix RL Debug Overlay Multiline And Low-HP Percent

Milestones:

- Milestone 1: Compact observation builder

Files changed:

- `src/port/sdl/fbdev_presenter.c`
- `src/rl/rl_observation.c`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:

- fix the reported issue where MiSTer `RL Debug` only showed the first line of overlay text
- avoid displaying `HP0` while the fighter still has visible remaining life

Implementation notes:

- updated `FBDevPresenter_ApplyFPSOverlayToBuffer()` to use the same multi-line text layout rules as the main fbdev overlay path
- this closes the remaining single-line layout path that could still clip RL debug text to the first line
- updated observation percent formatting so any positive HP value displays at least `1%`

Validation:

```sh
tools/mister/build-game.sh --flavor telemetry
```

Result:

- passed
- package created at `build/mister-telemetry-package`

Follow-up:

- verify on MiSTer that `RL Debug` now shows all expected lines
- verify that near-empty health now shows `HP1` instead of `HP0`

### 2026-04-21: Switch RL Debug Overlay To Raw HP And Colored Input Tokens

Milestones:

- Milestone 1: Compact observation builder

Files changed:

- `src/rl/rl_observation.h`
- `src/rl/rl_observation.c`
- `src/port/sdl/sdl_app.c`
- `src/port/sdl/fbdev_presenter.h`
- `src/port/sdl/fbdev_presenter.c`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:

- make the RL debug overlay more useful for direct gameplay inspection
- avoid misleading `HP0` display while the fighter is still alive
- show a fixed input legend where active buttons are highlighted in red

Implementation notes:

- line 1 now shows raw HP values instead of percentages, using `current/max`
- line 2 keeps compact state values using raw super and stun gauges
- line 3 is now a fixed token row:
  - `U D L R LP MP HP LK MK HK`
- inactive tokens stay white
- active tokens are drawn red
- SDL renderer and MiSTer fbdev presenter now both render the token row through dedicated per-token draw logic instead of the generic single-color text path
- fbdev presenter now receives the current RL input `SWKey` through a dedicated setter so token highlighting matches the active input on hardware

Validation:

```sh
tools/mister/build-game.sh --flavor telemetry
```

Result:

- passed
- package created at `build/mister-telemetry-package`

Follow-up:

- verify on MiSTer that line 1 shows raw HP values matching the visible life bar
- verify on MiSTer that the fixed input legend is always visible and active buttons turn red at the right frames

### 2026-04-21: Fix RL Debug Button Labels To Use Logical Attack Mapping

Milestones:

- Milestone 1: Compact observation builder

Files changed:

- `src/rl/rl_observation.h`
- `src/rl/rl_observation.c`
- `src/port/sdl/sdl_app.c`
- `src/port/sdl/fbdev_presenter.c`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:

- fix the reported issue where `LK`, `MK`, and `HK` appeared shifted in the RL debug input legend
- make the attack labels reflect gameplay button meaning instead of raw physical `SWKey` slot ordering

Implementation notes:

- directions still use raw `SWKey` bits for `U`, `D`, `L`, and `R`
- attack tokens now use a logical display mask built from the same `Convert_User_Setting()` mapping path used by gameplay
- this means `LP/MP/HP/LK/MK/HK` follow the current `Pad_Infor[].Shot[]` configuration instead of assuming raw `SWKey` slot order
- SDL and fbdev token highlighting now both read the same logical attack mask

Validation:

```sh
tools/mister/build-game.sh --flavor telemetry
```

Result:

- passed
- package created at `build/mister-telemetry-package`

Follow-up:

- verify on MiSTer that `LK`, `MK`, and `HK` now light the expected tokens

### 2026-04-22: Milestone 1 Status Review

Milestones:

- Milestone 1: Compact observation builder

Files changed:

- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:

- reconcile the current implementation against the Milestone 1 checklist
- record whether Milestone 1 can be closed or still has meaningful gaps

Implementation notes:

- current state is strong enough for observation bring-up and iterative debug:
  - end-of-frame hook exists
  - `RL Debug` overlay is readable on MiSTer
  - raw HP and logical button display now match runtime behavior well enough for spot checks
- Milestone 1 is still not ready to close because the implementation does not yet cover the full canonical schema from the plan
- remaining gaps include:
  - no implemented `last_executed_*`
  - no implemented `next_scheduled_*`
  - no implemented `frames_until_next_action`
  - no implemented corner-distance fields in the runtime observation path
  - no systematic MiSTer validation pass for position / guard / attack / round-state coverage
  - no observation build-cost measurement yet

Validation:

```text
Overlay bring-up looks healthy, but milestone-close criteria are still only partially satisfied.
```

Result:

- Milestone 1 remains open
- the right next step is still to finish Milestone 1 rather than start Milestone 2

Follow-up:

- finish the remaining canonical `RLObservationV1` fields in code
- validate the missing observation groups on MiSTer
- measure observation build cost on MiSTer or the closest equivalent target

## Milestone Notes

### Milestone 0A: Baseline Match-Flow Confirmation Spike

Objective:

- verify `MODE_VERSUS + rl_session_active` can run one agent-controlled side against one CPU side

Implementation notes:

- `--rl-agent` and `--rl-player` config/CLI path added
- `RLSession_ApplyVersusOperatorSetup()` applies operator flags for the baseline spike
- hook sites are `Setup_VS_Mode()` and `Game2_0()`

Validation notes:

- telemetry build passed on 2026-04-21
- runtime validation passed on MiSTer hardware for:
  - RL player 1 with player win
  - RL player 1 with CPU win
  - RL player 2 with player win
  - RL player 2 with CPU win

Open questions:

- exact automation mechanism for unattended round cycling once local scripted control is added

### Milestone 0B: Facing And Remap Validation Micro-Spike

Objective:

- verify `rl_flag` semantics and relative-direction remap behavior

Implementation notes:

- human-opponent validation mode added for deterministic spot checks
- RL debug overlay reports `P1H` / `P2H` during human-opponent validation and appends the selected movement label
- fixed movement selector covers forward, back, jump-forward, and down-back
- remap now uses relative X position first, with `rl_flag` as the same-X fallback, to avoid stale-facing behavior immediately after cross-over

Validation notes:

- MiSTer runtime validation passed for `P1H` and `P2H` with forward, back, jump-forward, and down-back

Open questions:

- final remote action path still needs to choose whether to use facing, position, or an explicit negotiated remap rule for delayed side-switch execution

### Milestone 0C: Local Fake Agent Spike

Objective:

- verify local scripted input override before networking

Implementation notes:

- started with a local CPU-opponent fake-agent sequence in `src/rl/rl_session.c`
- the sequence writes held movement and attack actions into the selected RL player's raw input buffer after `keyConvert()` and before input latch
- the local fake-agent sequence is active only for RL-enabled `MODE_VERSUS` gameplay when the opponent is CPU-controlled

Validation notes:

- telemetry build passed after initial implementation
- on-device local fake-agent runtime validation passed

Open questions:

- exact first playable frame for `round_start_hp[i]` capture now moves to Milestone 1

### Milestone 1: Compact Observation Builder

Objective:

- build and validate `RLObservationV1`

Implementation notes:

- started with a local `RLObservationV1` builder in `src/rl/rl_observation.c`
- added an end-of-frame hook after `hit_check_main_process()`
- `RL Debug` overlay now uses a compact multi-line observation view instead of only the routing label
- overlay includes RL routing, HP, super, stun, opponent X distance, facing sign, round number, and the RL-side raw input buttons
- input labels are `U`, `D`, `L`, `R`, `LP`, `MP`, `HP`, `LK`, `MK`, and `HK`
- fbdev and SDL renderer overlays now support short multi-line debug text
- raw HP display and logical attack-button display are now working well enough for runtime spot checks
- the runtime struct is still only a partial subset of the full canonical schema from the plan

Validation notes:

- telemetry build passed after initial implementation
- on-device overlay readability and button-label correctness are now good
- full observation-group validation and build-cost measurement are still pending

Open questions:

- validate whether the current first active-frame `round_start_hp[i]` capture matches round bootstrap on hardware
- validate positions, HP, super, stun, attack state, guard state, and round state against visible gameplay

### 2026-04-22: Close Milestone 1 Observation Builder

Milestones:

- Milestone 1: Compact observation builder

Purpose:

- finish the runtime observation schema so it matches the canonical `RLObservationV1` table
- expose action-context and corner-distance directly on MiSTer
- make the `RL Debug` overlay sufficient for validation and cost measurement without extra tooling

Changes:

- updated `src/rl/rl_observation.h` so `RLObservationV1` now uses the canonical schema fields:
  - normalized HP / super / stun ratios
  - normalized `opp_dx_ratio` / `opp_dy_ratio`
  - normalized self / opponent corner ratios
  - all fixed state / round / action-context fields from plan section `4A`
- updated `src/rl/rl_observation.c`:
  - compute ratios from `round_start_hp`, `sa->store_max`, `py->genkai`, and `scrl/scrr`
  - keep raw debug values for overlay readability
  - measure observation build cost per frame and expose running `avg/max` microseconds
  - expand `RL Debug` into a compact multiline validation view covering:
    - HP / super / stun / round / wins
    - `DX`, `DY`, facing, and corner distances
    - guard flags and attack ids
    - do-not-move / hit-stop / high-jump flags
    - self / opponent routine triplets
    - action-context and observation cost
- updated `src/rl/rl_session.h` / `src/rl/rl_session.c`:
  - added explicit `RL_MOVE_*` intent enum matching the plan
  - added `RLActionContext`
  - fake-agent and human-opponent validation paths now publish:
    - `last_executed_move_intent`
    - `last_executed_attack_bits`
    - `next_scheduled_move_intent`
    - `next_scheduled_attack_bits`
    - `frames_until_next_action`
- updated docs:
  - `docs/plan-remote-rl-agent.md`
  - `docs/config.md`

Validation:

- local build passed:
  - `tools/mister/build-game.sh --flavor telemetry`
- lint-style patch check passed:
  - `git diff --check`
- MiSTer validation path is now documented as a concrete matrix using existing OSD controls:
  - `RL Settings -> RL Agent`
  - `RL Settings -> RL Opponent`
  - `RL Settings -> RL Movement`
  - `FPS Counter = RL Debug`

Result:

- Milestone 1 is now ready to close
- the next stage can focus on Milestone 2 handshake / delay-budget work instead of more local observation bring-up
- decide whether to finish the remaining schema fields in the current runtime struct or refactor it to mirror the plan table more literally

### 2026-04-22: Align RL Debug Super And Win Semantics With MiSTer Validation

Milestones:

- Milestone 1: Compact observation builder follow-up

Purpose:

- correct two observation/overlay assumptions that MiSTer runtime validation disproved
- show both super-stock count and current gauge fill
- move round-win tracking to the versus-specific counter path

Changes:

- updated `src/rl/rl_observation.h` / `src/rl/rl_observation.c`
  - canonical observation now carries:
    - `self_super_stock`, `self_super_stock_max`
    - `opp_super_stock`, `opp_super_stock_max`
    - `self_super_gauge_ratio`, `opp_super_gauge_ratio`
  - `RL Debug` now shows:
    - `SAa/b` for full-stock count
    - `SGx/y` for current gauge fill progress
  - round-win display now reads from `VS_Win_Record[*]`
- increased RL overlay text buffers in:
  - `src/port/sdl/sdl_app.c`
  - `src/port/sdl/fbdev_presenter.c`
- updated docs:
  - `docs/plan-remote-rl-agent.md`
  - `docs/config.md`

Validation input from MiSTer:

- `SA` was observed as `0/2`, `1/2`, `2/2`, confirming the old display was stock count instead of gauge progress
- round wins stayed `0-0`, indicating `Win_Record[*]` was not the right versus overlay source

Result:

- RL overlay semantics now better match actual versus runtime behavior

### 2026-04-22: Audit RL Debug Raw-State Semantics And Rename Overlay Labels

Milestones:

- Milestone 1: Compact observation builder follow-up

Purpose:

- reconcile the remaining RL Debug raw-state labels with MiSTer runtime observations and code audit results
- make the overlay names less misleading before moving on to networking work

Changes:

- updated `src/rl/rl_observation.c`
  - renamed the multiline overlay labels to better match current runtime semantics:
    - `M` for cumulative versus match wins
    - `CF` for raw combat/contact state from `guard_flag`
    - `AK` for `current_attack` button-category codes
    - `NM` for raw `do_not_move`
    - `HS` for contact-oriented `hit_stop`
    - `HJ` for the high-jump-only flag
    - `SR` / `OR` for self / opponent routine triplets
- updated docs:
  - `docs/plan-remote-rl-agent.md`
    - corrected canonical-field notes for `guard_flag`, `current_attack`, `do_not_move`, `hit_stop`, `high_jump_flag`, and `VS_Win_Record`
    - added a dedicated `RL Debug` validated-semantics section based on MiSTer observations plus code audit
    - updated the Milestone 1 MiSTer validation matrix to use the new labels and meanings
  - `docs/config.md`
    - updated `show-fps = rl-debug` notes to explain the renamed overlay abbreviations

Code-audit conclusions captured in docs:

- `guard_flag` is not a pure block boolean; many hit / guard / catch paths set it to `3`
- `current_attack` comes from `shot_data_refresh()` and currently behaves as an attack button-category code (`LP/MP/HP/LK/MK/HK`)
- `do_not_move` appears to be low-signal in the current versus path and is commonly `0`
- `hit_stop` often behaves like a shared contact stop on both players
- `high_jump_flag` is specific to high-jump / hijump-cancel logic, not generic airborne state
- `routine_no[0..2]` remains the most informative raw state bundle; `routine_no[1]` cleanly separates normal / damage / catch / caught / attack

Validation:

```sh
tools/mister/build-game.sh --flavor telemetry
git diff --check
```

Result:

- RL Debug labels and docs now line up with the current raw-state interpretation used during MiSTer bring-up

### 2026-04-22: Add Current-Match Round Score And MVP Observation Set

Milestones:

- Milestone 1: Compact observation builder follow-up

Purpose:

- expose both current-match round score and cumulative VS match wins in `RL Debug`
- document the minimum observation subset intended for the first usable RL training loop

Changes:

- updated `src/rl/rl_observation.h` / `src/rl/rl_observation.c`
  - added `self_match_round_wins` and `opp_match_round_wins` from `PL_Wins[*]`
  - changed the first overlay line to show `R`, `RW`, and `M` separately:
    - `R`: current round
    - `RW`: current match's round score from the RL perspective
    - `M`: cumulative versus match wins from `VS_Win_Record[*]`
- updated docs:
  - `docs/plan-remote-rl-agent.md`
    - added `PL_Wins[*]` fields to the canonical schema
    - added an MVP training observation subset
    - updated `RL Debug` line-1 semantics and validation matrix
  - `docs/config.md`
    - updated `show-fps = rl-debug` notes for `RW`

Validation plan:

```sh
tools/mister/build-game.sh --flavor telemetry
git diff --check
```

MiSTer follow-up:

- verify `RW` increments after each round win inside a match
- verify `RW` resets when a new match starts
- verify `M` still tracks cumulative VS match wins

### 2026-04-22: Document Human-Fighter Observer Gap Review

Milestones:

- Milestone 1: Compact observation builder follow-up
- Milestone 4 / Milestone 6 planning input

Purpose:

- capture the gap between the current MVP observer and the information a human player naturally uses during a match
- keep Milestone 2 unblocked while preserving the review items for transition logging, reward design, and later observation expansion

Changes:

- updated `docs/plan-remote-rl-agent.md`
  - added `Human-Fighter Observer Gap Review` under the observation schema section
  - marked the Milestone 1 current read to say these gaps are documented and do not block Milestone 2
  - added Milestone 4 tasks to review action-outcome and event-delta candidates
  - added Milestone 6 tasks to review derived movement/action-phase candidates before schema expansion

Summary:

- current MVP is sufficient for spacing, resources, coarse combat state, and delayed action context
- likely missing or implicit fields include opponent movement intent, action phase, own action outcome, and event deltas
- priority follow-up areas are:
  - action outcomes and deltas for Milestone 4 transition/reward design
  - derived movement/action-phase features for Milestone 6 policy strength

Validation:

```sh
# Documentation-only update.
```

### 2026-04-22: Refresh Milestone 1 RL Debug Validation Matrix

Milestones:

- Milestone 1: Compact observation builder follow-up

Purpose:

- keep the Milestone 1 MiSTer validation matrix aligned with the latest `RL Debug` overlay layout

Changes:

- updated `docs/plan-remote-rl-agent.md`
  - added the current line-by-line overlay example to the Milestone 1 validation matrix
  - corrected line references for `DX/DY/F`, `CL/CR/OL/OR`, action-context, input-row tokens, and observation cost
  - documented the first-line `R`, `RW`, and `M` meanings in the matrix itself

Validation:

```sh
git diff --check
```

### 2026-04-22: Start Milestone 2 Protocol Skeleton

Milestones:

- Milestone 2: Session handshake, network probe, and delay budget

Purpose:

- start the remote RL session handshake/probe milestone with a safe data-layer-only implementation
- define the hello/ack/config/hash/probe-stat helpers before adding live socket I/O

Changes:

- added `src/rl/rl_protocol.h`
  - protocol/schema/action version constants
  - `RLSessionConfig`
  - `RLSessionHello`
  - `RLSessionAck`
  - ack status enum
  - `RLProbeStats`
- added `src/rl/rl_protocol.c`
  - default config
  - deterministic FNV-1a config hash
  - timing/config validation helpers
  - ack validation helper
  - sorted-sample p50/p95/p99 probe-stat helper
- added `src/rl/rl_net.h` / `src/rl/rl_net.c`
  - no-op disabled network state
  - no socket open/send/receive path yet
  - default config state only, so existing fake-agent and overlay behavior stay unchanged
- updated `docs/plan-remote-rl-agent.md`
  - checked off protocol data-layer tasks
  - split percentile helper work from target-network latency measurement work
  - documented current no-op disabled path and placeholder timing values

Validation plan:

```sh
tools/mister/build-game.sh --flavor telemetry
git diff --check
```

Follow-up:

- add the actual UDP ping/pong packet path
- expose remote host/port configuration
- collect target-network RTT / jitter / p50 / p95 / p99 before choosing final `k`, `decision_interval_frames`, and `action_hold_frames`

### Milestone 2: Session Handshake, Network Probe, And Delay Budget

Objective:

- agree on session config and measure real network timing

Implementation notes:

- TBD

Validation notes:

- TBD

Open questions:

- final `config_hash` algorithm
- exact feature flag bit assignments

### Milestone 3: Remote Inference Only

Objective:

- connect MiSTer to a remote heuristic server

Implementation notes:

- TBD

Validation notes:

- TBD

Open questions:

- first remote server language and runtime
- whether to keep remote heuristic server in this repo or a separate repo

### Milestone 4: Decision Ledger And Transition Logging

Objective:

- make the environment trainable with executed-action-aligned transitions

Implementation notes:

- TBD

Validation notes:

- TBD

Open questions:

- transition log format
- transport for non-critical learner data

### Milestone 5: Async Learner And Model Hot-Swap

Objective:

- train online without blocking inference

Implementation notes:

- TBD

Validation notes:

- TBD

Open questions:

- model runtime
- weight hot-swap protocol

### Milestone 6: Higher-Control-Rate Policy And Curriculum

Objective:

- improve agent strength after the transport/control path is stable

Implementation notes:

- TBD

Validation notes:

- TBD

Open questions:

- curriculum schedule
- expanded observation schema versioning strategy
- whether `overlay_attack_event_finalized` / `overlay_attack_contact` / `overlay_attack_whiff` keep consistent learner semantics across normals, specials, projectiles, throws, and multistage moves, or should remain debug / auxiliary-only labels until move-family validation is complete
- how human-vs-CPU demo episodes should be recorded and tagged so they can bootstrap learner training without being confused with remote-agent-generated experience

## Test And Build Records

### Move-Family Validation SOP

Use this SOP for the first stable scripted attack-policy validation passes.

1. Choose one policy for the pass:
   - `hp`
   - `throw`
   - `ryu-fireball`
   - `tatsu`
   - `shoryuken`

2. Pick a dedicated transition log path for that pass:
   ```text
   logs/rl-transitions-<policy>-4-3-3.ndjson
   ```

3. Start the probe server with:
   - the selected `--policy`
   - the dedicated `--transition-log`
   - the usual live learner arguments

   Example:
   ```sh
   python \\wsl.localhost\Ubuntu\home\olhua\src\3s-mister-arm\tools\rl_probe_server.py --host 0.0.0.0 --port 37330 --action-port 37331 --policy hp --policy-repeat-delay-ms 3000 --model-version 0 --model-dir \\wsl.localhost\Ubuntu\home\olhua\src\3s-mister-arm\model\rl-model-live --transition-log \\wsl.localhost\Ubuntu\home\olhua\src\3s-mister-arm\logs\rl-transitions-hp-4-3-3.ndjson --learner-auto-publish --learner-publish-interval-sec 10 --learner-warmup-rows 100 --learner-batch-size 32
   ```

4. On the MiSTer/game side, set the timing baseline to `4/3/3`:
   ```ini
   rl-agent-delay-frames = 4
   rl-agent-decision-interval = 3
   rl-agent-action-hold = 3
   ```

5. Restart the MiSTer/game runtime after changing timing config.
   Do not assume editing config live will change the active run.

6. Use one fixed opponent behavior for the whole pass:
   - preferred first pass: opponent steadily approaches the RL side
   - avoid mixing free-form CPU behavior and scripted approach behavior in the same comparison set

7. Run the pass until at least:
   - `rows >= 256`
   - `done >= 2`

8. Capture one or more representative `LEARNER` lines including:
   - `timing=...`
   - `policy=...`
   - `policy_rows=...`
   - `policy_rew=...`
   - `policy_fallback_pct=...`
   - `atk=...`
   - `inf=...`

9. Do a visible gameplay sanity check:
   - attack visibly occurs: yes / no
   - contact observed: yes / no
   - whiff observed: yes / no

10. Record the run in the move-family validation template below:
    - date
    - policy
    - opponent setup
    - timing
    - command
    - log summary
    - visible outcome check
    - pass / fail
    - follow-up notes

11. Repeat the same procedure for the next policy, changing only:
    - `--policy`
    - `--transition-log`

### Move-Family Validation Record Template

Date:

- YYYY-MM-DD

Milestone:

- Milestone 6: Higher-control-rate policy and curriculum

Policy:

- `hp` / `throw` / `ryu-fireball` / `tatsu` / `shoryuken`

Opponent setup:

- steady approach / other fixed setup

Timing:

- `k/decision_interval/action_hold`

Command:

```sh
# learner/probe command here
# note any MiSTer-side timing/config overrides here
```

Log summary:

- `rows=`
- `done=`
- `policy_rows=`
- `policy_rew=`
- `policy_fallback_pct=`
- `atk=`
- `inf=`

Visible outcome check:

- attack visibly occurs: yes / no
- contact observed: yes / no
- whiff observed: yes / no

Result:

- pass / fail

Notes:

- spacing / timing observations
- whether labels looked plausible
- follow-up action

### Template

Date:

- YYYY-MM-DD

Milestone:

- TBD

Command:

```sh
# command here
```

Result:

- TBD

Notes:

- TBD

## MiSTer Deploy Records

### Template

Date:

- YYYY-MM-DD

Build artifact:

- TBD

Deploy command:

```sh
# command here
```

MiSTer target:

- TBD

Result:

- TBD

Notes:

- TBD

## Open Issues

- [ ] Validate whether overlay attack-outcome fields are learner-safe across normals, specials, projectiles, throws, and multistage moves
- [ ] Revisit transition/replay SA state after the RL loop runs reliably: live observations already include super stock and gauge ratios, but replay-only learner rows may need compact `self_super_stock`, `self_super_gauge_ratio`, `opp_super_stock`, and `opp_super_gauge_ratio` fields or derived `can_super` flags so policies can learn when supers are available.
- [ ] Define a human-demo recording / ingest path for learner bootstrapping, including replay metadata and mixing policy with remote-agent episodes

## Closed Issues

- [x] Confirm exact `MODE_VERSUS + rl_session_active` setup hook
- [x] Confirm `rl_flag` mapping with runtime observation
- [x] Confirm first playable frame for `round_start_hp[i]`
- [x] Choose `config_hash` algorithm
- [x] Choose remote heuristic server location
- [x] Choose transition log format

## 2026-05-01: V57/V58 Projectile Defensive Expert Margin

Milestone:
- Milestone 6: higher-control-rate policy and projectile curriculum.

Code:
- added `--projectile-defensive-expert-margin-loss` to
  `tools/train_dqn_learner.py`.
- added defensive expert diagnostics and metadata.
- added `--projectile-defensive-expert-margin-all-competitors`.
- added `projectile-response-v6` to `tools/rl_auto_retrain.py`.

Validation:
- `python3 -m py_compile tools/train_dqn_learner.py tools/rl_auto_retrain.py`
- smoke train:
  - `/tmp/rl-v57-def-expert-smoke`
  - `/tmp/rl-v58-allcomp-smoke`
- full train:
  - `model/dqn-projectile-schema-v5-full-actions-v57-defensive-expert-candidate`
  - `model/dqn-projectile-schema-v5-full-actions-v58-defensive-allcomp-candidate`

Findings:
- V57 moved human-defense projectile Q gaps closer to defense but leaked into
  `tatsu-mk` / `shoryuken-hp` and regressed safe-jump Q-gap.
- V58 all-competitor mode fixed the special leakage and restored safe-jump
  Q-gap (`2770/2780` top-1), but urgent/borderline rows still stayed jump top-1.
- Neither V57 nor V58 is promotable.

Conclusion:
- targeted training-mode human-demo logging works and is useful.
- current auxiliary defensive margin is not sufficient to make
  `time_to_self <= 12` rows prefer `guard`/`back`.
- V59 should use more tightly filtered clean defensive demos and/or a
  policy-time projectile timing prior instead of another blind margin increase.

## 2026-05-01: V59/V60 Projectile Batch Group

Milestone:
- Milestone 6: higher-control-rate policy and projectile curriculum.

Code:
- added an opt-in `projectile` balanced batch group to
  `tools/train_dqn_learner.py`.
- added `--projectile-batch-group` selector flags.
- added projectile batch diagnostics and metadata.
- added auto-retrain preset `projectile-response-v7`.

Validation:
- `python3 -m py_compile tools/train_dqn_learner.py tools/rl_auto_retrain.py`
- `tools/rl_auto_retrain.py --reward-preset projectile-response-v7 --dry-run`
- smoke train:
  - `/tmp/rl-v59-projectile-batch-smoke`
- full trains:
  - `model/dqn-projectile-schema-v5-full-actions-v59-projectile-batch-candidate`
  - `model/dqn-projectile-schema-v5-full-actions-v60-projectile-batch-strong-candidate`

Findings:
- projectile batch pool was populated as intended:
  - `825` projectile experiences.
  - `461` defensive-clean.
  - `364` late-jump-hit.
- V59 kept safe-jump Q-gap but did not change urgent projectile top-1.
- V60 stronger sampling moved human-defense Q gaps closer:
  - `0-6` mean competitor-minus-defense gap: `0.0760` -> `0.0265`.
  - `7-12` mean competitor-minus-defense gap: `0.0726` -> `0.0240`.
- V60 still did not flip urgent/borderline top-1 away from jump.

Conclusion:
- projectile batch sampling is useful infrastructure, but replay sampling alone
  is not enough to solve medium/close projectile defense.
- V59/V60 are not promotable.
- V61 should add a policy-time projectile timing prior/mask or a stronger
  filtered BC/classification objective for `time_to_self <= 12`.

## 2026-05-01: V61 Projectile Timing Prior

Milestone:
- Milestone 6: higher-control-rate policy and projectile curriculum.

Code:
- added opt-in DQN inference prior flags to `tools/rl_probe_server.py`.
- `--dqn-projectile-timing-prior` applies a soft jump-start Q penalty only when
  an opponent projectile is incoming, close enough, and the player is grounded.
- default penalties:
  - `time_to_self 0-6`: `0.05`
  - `time_to_self 7-12`: `0.03`
  - `13+`: no penalty
- prior skips rows where `obs_self_airborne != 0` or
  `obs_self_jump_phase >= 2`.

Validation:
- `python3 -m py_compile tools/rl_probe_server.py`
- `python3 tools/rl_probe_server.py --help | rg "dqn-projectile"`
- smoke helper check:
  - urgent bucket returns `0.05`
  - borderline bucket returns `0.03`
  - `13+` and airborne rows return `0.0`
- smoke ranking check:
  - a synthetic close projectile row flipped from
    `jump-forward-start` over `back` to `back` over `jump-forward-start`
    after the prior was enabled.

Findings:
- V61 is an inference/data-collection bootstrap, not a new trained model yet.
- The prior does not add a global `back`/`guard` bonus, which avoids amplifying
  the V60 global back-bias failure mode.
- `--model-version` remains an integer stamp; use `--model-version 61` and keep
  descriptive names such as `v61-prior` in the log path or model directory.

Next:
- run a live V61 probe with V60 weights plus the prior enabled.
- collect on-policy close projectile `guard`/`back` success rows before doing
  another incremental retrain.

## 2026-05-01: V61 Live Probe Analysis And V61b Timing Window

Milestone:
- Milestone 6: higher-control-rate policy and projectile curriculum.

Input:
- `logs/rl-transitions-v61-prior-live-probe.ndjson`
- V60 weights with `--dqn-projectile-timing-prior`.

Findings:
- rows: `6,224`.
- incoming opponent projectile rows within the usual threat gate: `1,855`.
- grounded `time_to_self <= 12` rows where the prior could intervene: only `66`.
- `0-6` prior-eligible rows already selected guard/crouch and had no immediate
  damage in the sampled rows.
- `7-12` still selected `jump-neutral-start` in `10` rows; half of those jump
  starts took damage.
- V60 raw Q gaps in `7-12` often exceeded the original `0.03` penalty:
  - p50 jump-over-defense gap: about `0.0289`.
  - p90: about `0.0496`.
  - max: about `0.0845`.
- The largest live failure mode was not close jump only; it was too-early far
  jump timing:
  - `19-24` jump-neutral starts: `0/62` damaged.
  - `25-30`: `13/81` damaged.
  - `31-36`: `64/82` damaged.
  - `37-48`: `84/84` damaged.

Code:
- extended `tools/rl_probe_server.py` projectile timing prior with an optional
  too-early far timing bucket:
  - `--dqn-projectile-prior-early-jump-penalty`
  - `--dqn-projectile-prior-early-min-time-to-self`
  - `--dqn-projectile-prior-early-max-time-to-self`

Conclusion:
- the safe live jump window in this probe is closer to `time_to_self 19-30`,
  not all `13+` rows.
- V61b should use stronger close/borderline penalties and an optional
  too-early penalty for `31-48`, while leaving `19-30` unpenalized.

## 2026-05-01: V61b/V61c Live Timing-Window Probes

Milestone:
- Milestone 6: higher-control-rate policy and projectile curriculum.

Input:
- `logs/rl-transitions-v61b-timing-window-live-probe.ndjson`
- `logs/rl-transitions-v61c-timing-window-live-probe.ndjson`
- both used V60 weights with the policy-time projectile timing prior.

V61b findings:
- rows: `4,539`.
- incoming opponent projectile rows: `1,372`.
- `31-48` jump-starts disappeared, which confirmed the too-early far prior
  worked.
- remaining jump-starts were concentrated in the intended `19-30` window.
- `19-22` still had occasional damage:
  - `t=19`: `3/10` jump starts damaged.
  - `t=22`: `1/11` jump starts damaged.

V61c findings:
- rows: `5,343`.
- incoming opponent projectile rows: `1,817`.
- moving the unpenalized jump window to about `23-30` improved behavior:
  - `19-22`: only `1` jump start, `0` damaged.
  - `23-30`: `98` jump starts, `2` damaged.
  - `31-48`: no jump-starts.
- episode outcomes improved versus V61b:
  - V61b final self HP: `0`, `0`, `29`.
  - V61c final self HP: `26`, `14`, `44`.
  - V61c also dealt more opponent damage in the sampled episodes.

Combined V61b/V61c filtered data candidates:
- clean defensive rows with `time_to_self <= 12`: `748`.
- clean defensive rows with `time_to_self <= 18`: `1,140`.
- clean defensive rows with `time_to_self <= 22`: `1,320`.
- clean defensive rows with `time_to_self <= 48`: `2,029`.
- clean jump starts in `time_to_self 23-30`: `162`.
- bad jump starts: `6`, mostly `19-22`.

Conclusion:
- V61c is the best policy-time prior so far.
- The live-safe jump window for this setup is closer to `23-30`.
- V62 should try a filtered retrain with V61b/V61c on-policy rows:
  - reinforce defense for `<=22` and `31-48`.
  - preserve jump for clean `23-30`.
  - avoid using all far `guard` rows blindly, because far guard often still
    takes chip or delayed damage.

## 2026-05-01: V62 Projectile Timing Group Margin Retrain

Milestone:
- Milestone 6: higher-control-rate policy and projectile curriculum.

Code:
- extended `tools/train_dqn_learner.py` with reusable projectile timing
  ranges:
  - `--projectile-batch-time-ranges`
  - `--projectile-expert-margin-time-ranges`
  - `--projectile-expert-margin-sources`
  - `--projectile-defensive-expert-margin-time-ranges`
- added `--projectile-timing-group-margin-loss`, a filtered group margin
  objective for incoming projectile rows:
  - defense group target: `back`, `guard-stand`, `guard-crouch`.
  - jump group target: `jump-forward-start`, `jump-neutral-start`,
    `jump-back-start`.
  - V62 recipe used defense ranges `0-22,31-48` and jump range `23-30`.

Validation:
- `python3 -m py_compile tools/train_dqn_learner.py`
- `python3 tools/train_dqn_learner.py --help`
- smoke train:
  - `/tmp/rl-v62-group-margin-smoke`
- full trains:
  - `model/dqn-projectile-schema-v5-full-actions-v62-timing-window-retrain-candidate`
  - `model/dqn-projectile-schema-v5-full-actions-v62-group-margin-candidate`
  - `model/dqn-projectile-schema-v5-full-actions-v62-group-margin-strong-candidate`

Findings:
- the first V62 filtered retrain without the new group objective did not
  materially change V60 top-1 behavior.
- `v62-group-margin-candidate` did move the learned policy in the intended
  direction without a severe global back-bias regression:
  - training greedy distribution: `forward 43.9%`, `back 34.7%`,
    `jump-neutral-start 10.9%`, `guard-stand 6.5%`.
  - human-demo safe-jump top-1 stayed healthy: `495/504`.
- grounded V61b/V61c live incoming-projectile rows improved versus V60:
  - `0-6` jump rate: `41.4% -> 20.7%`; defense: `40.2% -> 72.4%`.
  - `7-12` jump rate: `71.4% -> 35.2%`; defense: `14.8% -> 54.5%`.
  - `31-36` jump rate: `90.6% -> 69.4%`; defense: `5.9% -> 30.6%`.
  - `37-48` jump rate: `91.3% -> 67.4%`; defense: `1.5% -> 32.6%`.
- `v62-group-margin-strong-candidate` overshot:
  - training greedy distribution shifted to `guard-stand 18.6%`.
  - safe-jump top-1 collapsed to `93/504`, with `guard-stand` blocking most
    clean `23-30` jump rows.
  - do not promote the strong candidate.
- applying a small policy-time jump penalty on top of
  `v62-group-margin-candidate` should be enough to finish the live behavior:
  - synthetic grounded analysis with a `0.02` jump penalty in `0-22,31-48`
    left `23-30` unchanged while reducing `31-36` jump to `0%` and
    `37-48` jump to `11.4%`.
  - a `0.03` penalty made `0-22` and `31-48` mostly defensive while still
    leaving `23-30` unchanged.

Conclusion:
- V62 successfully added the missing trainer infrastructure and partially
  internalized V61c timing behavior.
- V62 standalone is not fully promotable yet because `13-22` and `31-48`
  still jump too often.
- recommended next live probe: use `v62-group-margin-candidate` with a much
  lighter policy-time prior than V61c, starting around `0.02-0.03` for
  `0-22` and `31-48`, with no penalty for `23-30`.

## 2026-05-02: Full-Retrain M1 Movement Baseline

Milestone:
- Milestone 6: full-retrain staged curriculum.

Input:
- `logs/rl-transitions-retrain-p1-movement-human-v1.ndjson`
- `logs/rl-transitions-retrain-p8-natural-cpudemo-v1.ndjson`
- `logs/rl-transitions-retrain-p8-natural-human-v1.ndjson`

Replay mix:
- created deterministic local replay
  `/tmp/rl-retrain-m1-mix-70-20-10.ndjson` with seed `7`.
- rows:
  - Phase 1 movement: `12,533` rows, `70.0%`.
  - natural CPU-demo: sampled `3,581` rows, `20.0%`.
  - natural human-demo: sampled `1,790` rows, `10.0%`.
- source mix by execution source is `human-demo 80%`, `cpu-demo 20%`, because
  Phase 1 and natural human are both `human-demo`; log-level sampling was
  needed to preserve the intended `70/20/10` file mix.

Model:
- `model/dqn-retrain-m1-movement-baseline-v1`
- version: `101`.
- action set:
  `forward`, `back`, `guard-stand`, `guard-crouch`, `jump-forward-start`,
  `jump-neutral-start`, `jump-back-start`.

Training command notes:
- `--steps 3000`
- `--batch-size 64`
- `--hidden-sizes 64,64`
- `--training-mode-hp-delta-mode damage-only`
- `--batch-sampling balanced`
- `--balanced-batch-ratios movement=1.0,normal=0.0,special=0.0`
- `--dqn-valid-action-mask action-start-v1`
- spacing shaping:
  `target_dx=50-120`, improve `0.5`, worsen `0.2`, maintain `0.1`,
  close-threat-back `0.3`.

Validation:
- full train completed.
- training experiences: `8,269`.
- training greedy distribution:
  `forward 51.6%`, `guard-crouch 26.9%`, `back 16.6%`,
  `jump-forward-start 4.8%`.
- no top-1 collapse by the `70%` threshold.
- natural-log comparison:
  `back 44.6%`, `guard-crouch 26.2%`, `forward 25.9%`,
  `jump-forward-start 1.8%`.
- natural close non-attacking rows:
  `guard-crouch 64.5%`, `back 16.7%`, `forward 15.7%`.
- Phase 1 curriculum-only comparison:
  `forward 58.1%`, `guard-crouch 23.1%`, `back 15.0%`.

Findings:
- M1 is acceptable as a movement/spacing base, not as a live fighting policy.
- The full action-set smoke collapsed to `fireball-lp`; M1 should stay
  movement-only until Phase 2 normals and Phase 3 specials are intentionally
  added.
- Phase 1-only rows still skew toward forward, but the natural holdout is more
  balanced and does not attack.

Next:
- collect Phase 2 normals:
  `logs/rl-transitions-retrain-p2-normals-human-v1.ndjson`.
- include hit, whiff, blocked, and punished examples for stand/crouch normals.
- warm-start M2 from `model/dqn-retrain-m1-movement-baseline-v1` and keep the
  M1 replay mix in the cumulative training set.

## 2026-05-02: Full-Retrain M2 Normals Baseline

Milestone:
- Milestone 6: full-retrain staged curriculum.

Input:
- `/tmp/rl-retrain-m1-mix-70-20-10.ndjson`
- `logs/rl-transitions-retrain-p2-normals-human-v1.ndjson`

Phase 2 data gate:
- rows: `38,801`.
- `execution_source = 4`.
- engine-labeled rows: `1,713`.
- projectile active rate: `5.6%`.
- normal coverage includes hit, whiff, and punished examples across standing,
  crouching, and air normals.

Training attempts:
- warm-start from `model/dqn-retrain-m1-movement-baseline-v1` failed because
  `tools/train_dqn_learner.py` currently requires exact action-list matches for
  `--init-model`.
- `model/dqn-retrain-m2-normals-baseline-v1`:
  - full normals action set without throw.
  - raw model trained, but M1 movement replay attack rate was `21.5%`.
  - rejected as a standalone candidate.
- `model/dqn-retrain-m2-normals-baseline-v2`:
  - stronger attack-risk shaping and more movement batch weight.
  - raw M1 replay attack rate improved to `13.8%`, still too high for a
    movement-regression pass.
  - with support-prior rerank, M1 replay attack rate dropped to `4.4%`.
  - accepted as the current M2 candidate only when support-prior is enabled.
- `model/dqn-retrain-m2-normals-baseline-v3`:
  - added conservative action penalty.
  - did not solve the movement regression enough to beat v2 plus support-prior.
- `model/dqn-retrain-m2-ground-normals-baseline-v1`:
  - excluded air normals and throw.
  - P2 replay attack rate was low, but M1 replay attack rate rose to `38.3%`
    due to ground-normal overgeneralization.
  - rejected.

Accepted M2 evaluation condition:
- model: `model/dqn-retrain-m2-normals-baseline-v2`.
- use:
  - `--dqn-valid-action-mask action-start-v1`
  - `--dqn-support-prior-min-count 300`
  - `--dqn-support-prior-count-penalty 0.05`
  - `--dqn-support-prior-negative-mean-penalty 0.05`
  - `--dqn-support-prior-exempt-actions forward,back,guard-stand,guard-crouch,jump-forward-start,jump-neutral-start,jump-back-start`

Accepted training command:
- `python3 tools/train_dqn_learner.py /tmp/rl-retrain-m1-mix-70-20-10.ndjson logs/rl-transitions-retrain-p2-normals-human-v1.ndjson --model-dir model/dqn-retrain-m2-normals-baseline-v2 --model-version 202 --steps 3000 --batch-size 64 --hidden-sizes 64,64 --actions forward,back,guard-stand,guard-crouch,jump-forward-start,jump-neutral-start,jump-back-start,stand-lp,stand-mp,stand-hp,stand-lk,stand-mk,stand-hk,forward-hp,crouch-lp,crouch-mp,crouch-hp,crouch-lk,crouch-mk,crouch-hk,air-lp,air-mp,air-hp,air-lk,air-mk,air-hk --learning-rate 0.001 --gamma 0.9 --target-sync-steps 200 --dqn-target-mode standard --training-mode-hp-delta-mode damage-only --training-action-source auto --reward-risk-profile all-attacks --reward-risk-window-decisions 15 --reward-attack-no-damage-cost 0.3 --reward-attack-punished-cost 1.0 --reward-shoryuken-no-damage-extra-cost 0.0 --reward-shoryuken-punished-extra-cost 0.0 --reward-jump-attack-no-damage-extra-cost 0.5 --reward-jump-attack-punished-extra-cost 1.0 --reward-guard-success-bonus 0.0 --reward-guard-success-window-decisions 6 --reward-guard-threat-max-dx 120 --reward-passive-guard-cost 0.3 --reward-far-guard-cost 0.5 --reward-spacing-target-min-dx 50 --reward-spacing-target-max-dx 120 --reward-spacing-improve-bonus 0.5 --reward-spacing-worsen-cost 0.2 --reward-spacing-maintain-bonus 0.1 --reward-spacing-threat-back-bonus 0.3 --engine-outcome-training-mode prefer-engine-action --engine-outcome-window-decisions 10 --engine-outcome-action-windows forward-hp=12 --engine-outcome-hit-bonus 0.7 --engine-outcome-no-damage-cost 0.2 --engine-outcome-punished-cost 1.0 --engine-outcome-oversample 1 --batch-sampling balanced --balanced-batch-ratios movement=0.45,normal=0.55,special=0.0 --dqn-valid-action-mask action-start-v1 --dqn-unsupported-action-regularization --dqn-unsupported-action-min-count 50 --dqn-unsupported-action-q-ceiling 0.0 --dqn-unsupported-action-loss-weight 0.05 --epsilon 0.05 --fallback-policy back --seed 7 --log-interval 500 --eval-limit 5000 --diagnostic-top-n 12 --replay-recipe-name retrain-m2-normals-no-throw-risk-v2 --replay-recipe-base-logs logs/rl-transitions-retrain-p1-movement-human-v1.ndjson,logs/rl-transitions-retrain-p8-natural-cpudemo-v1.ndjson,logs/rl-transitions-retrain-p8-natural-human-v1.ndjson,logs/rl-transitions-retrain-p2-normals-human-v1.ndjson`

Parameter rationale:
- `throw` was excluded because the first M2 smoke collapsed to throw.
- specials were excluded because they belong to Phase 3.
- `movement=0.45,normal=0.55` kept movement replay present while allowing normal
  events to influence batches.
- attack risk costs were raised versus the first smoke to reduce random normals
  in movement-only states.
- jump-attack extra risk costs were added after air normals overgeneralized into
  movement states.
- engine outcome training used `prefer-engine-action` to train from engine
  normal labels when available.
- `forward-hp=12` used a shorter explicit window than specials; specials are
  not in M2.

Validation:
- M1 replay comparison with support-prior:
  - `attack_rate 4.4%`
  - `forward 62.6%`
  - `jump-forward-start 23.2%`
  - `back 9.6%`
  - no top-action collapse.
- P2 replay comparison with support-prior:
  - `attack_rate 9.0%`
  - `forward 53.7%`
  - `back 30.7%`
  - `air-lp 6.1%`
  - `guard-crouch 4.0%`
  - no top-action collapse.

Validation commands:
- M1 movement regression:
  - `python3 tools/compare_dqn_models.py /tmp/rl-retrain-m1-mix-70-20-10.ndjson --model M2v2=model/dqn-retrain-m2-normals-baseline-v2 --limit 10000 --top-n 12 --focus-actions forward,back,guard-stand,guard-crouch,jump-forward-start,stand-mp,stand-hp,stand-mk,stand-hk,forward-hp,crouch-mp,crouch-hp,crouch-mk,crouch-hk --focus-rank-limit 3 --training-action-source auto --dqn-valid-action-mask action-start-v1 --dqn-support-prior-min-count 300 --dqn-support-prior-count-penalty 0.05 --dqn-support-prior-negative-mean-penalty 0.05 --dqn-support-prior-exempt-actions forward,back,guard-stand,guard-crouch,jump-forward-start,jump-neutral-start,jump-back-start`
- P2 normals behavior:
  - `python3 tools/compare_dqn_models.py logs/rl-transitions-retrain-p2-normals-human-v1.ndjson --model M2v2=model/dqn-retrain-m2-normals-baseline-v2 --limit 12000 --top-n 12 --focus-actions forward,back,guard-stand,guard-crouch,jump-forward-start,stand-mp,stand-hp,stand-mk,stand-hk,forward-hp,crouch-mp,crouch-hp,crouch-mk,crouch-hk --focus-rank-limit 3 --training-action-source auto --dqn-valid-action-mask action-start-v1 --dqn-support-prior-min-count 300 --dqn-support-prior-count-penalty 0.05 --dqn-support-prior-negative-mean-penalty 0.05 --dqn-support-prior-exempt-actions forward,back,guard-stand,guard-crouch,jump-forward-start,jump-neutral-start,jump-back-start`

Quality gates used:
- no single top action at or above `70%`.
- M1 movement replay attack rate below about `5%` with support-prior.
- P2 normals replay attack rate nonzero but modest.
- no throw/special action in the M2 action set.
- reject candidates that overgeneralize normals into M1 movement-only rows.
- reject candidates that require raw-model behavior without support-prior; M2
  v2 is accepted only with support-prior.

Findings:
- P2 data is good enough for a first M2 baseline.
- M2 should not be live-tested without support-prior yet.
- The trainer needs an action-expansion warm-start or a context-aware
  no-attack/movement regression objective before later stages can cleanly add
  larger action sets without rerank help.

Next:
- collect Phase 3 specials:
  `logs/rl-transitions-retrain-p3-specials-human-v1.ndjson`.
- keep M2 v2 as the current cumulative baseline and carry the support-prior
  condition into probe commands and offline comparisons.

## 2026-05-02: Full-Retrain M2v4 Raw Support-Prior-Free Baseline

Milestone:
- Milestone 6: full-retrain staged curriculum.

Files changed:
- `tools/train_dqn_learner.py`
- `docs/agent-memory/remote-rl-retrain-data-collection-plan.md`
- `docs/plan-remote-rl-agent.md`
- `docs/remote-rl-agent-engineering-log.md`

Purpose:
- remove the M2 dependency on inference-time support-prior reranking by adding
  trainer support for action-expansion warm-start and a context-aware movement
  regression loss.

Implementation notes:
- added `--init-model-action-mode exact|expand`.
  - `exact` preserves the old behavior.
  - `expand` allows an init model whose action list is a subset of the target
    action list; shared action output rows are copied and new action rows are
    initialized from the existing output-row mean plus small deterministic
    noise, with low output bias.
- added movement regression loss flags:
  - `--movement-regression-loss-weight`
  - `--movement-regression-target-q-margin`
  - `--movement-regression-far-dx-threshold`
  - `--movement-regression-action-groups`
- the movement regression loss applies only in far, grounded,
  no-projectile, non-opponent-attack contexts. It penalizes the best selected
  normal-attack Q when it exceeds the best movement/guard/jump-start Q by the
  configured margin.

Validation:
- syntax/CLI:
  - `python3 -m py_compile tools/train_dqn_learner.py`
  - `python3 tools/train_dqn_learner.py --help | rg "init-model-action-mode|movement-regression"`
- smoke:
  - `/tmp/rl-m2v4-smoke`, version `1`, trained for `10` steps with
    `--init-model model/dqn-retrain-m1-movement-baseline-v1`
    and `--init-model-action-mode expand`.
  - result: published successfully; `init=warm-start:101`; movement regression
    and unsupported-action regularization both produced nonzero training loss.
- rejected candidates:
  - `model/dqn-retrain-m2-normals-baseline-v4`, version `204`:
    M1 raw attack rate `0.0%`, but P2 raw attack rate also `0.0%`; too
    conservative.
  - `model/dqn-retrain-m2-normals-baseline-v4b`, version `205`:
    lighter M1-expand warm-start remained too conservative; P2 raw attack
    rate stayed `0.0%`.
- accepted candidate:
  - `model/dqn-retrain-m2-normals-baseline-v4c`, version `206`.
  - initialized from attack-capable `model/dqn-retrain-m2-normals-baseline-v2`
    rather than M1, then retrained with:
    `/tmp/rl-retrain-m1-mix-70-20-10.ndjson`,
    `logs/rl-transitions-retrain-p2-normals-human-v1.ndjson`, and
    `logs/rl-transitions-retrain-p2-far-whiff-negative-human-v1.ndjson`.
  - training used Double DQN, LR `0.0003`, `3500` steps,
    balanced batch `movement=0.50,normal=0.50`, attack risk cost
    `0.5/1.0`, jump attack extra cost `0.8/1.0`,
    engine outcome `hit=1.0,no-damage=0.3,punished=1.0`, and movement
    regression `weight=0.02,margin=0.5,far_dx=120`.
- raw validation without support-prior:
  - M1 replay:
    `attack_rate 4.7%`, `forward 63.1%`, `back 31.9%`,
    `air-lp 4.2%`, no top-action collapse.
  - P2 normals replay:
    `attack_rate 11.2%`, `forward 56.4%`, `back 31.1%`,
    `air-lp 6.0%`, `crouch-lp 2.0%`, `air-hk 1.7%`,
    `stand-hk 1.2%`, no top-action collapse.
  - far-whiff negative replay:
    `attack_rate 8.0%`, mostly `air-lp`; this is a residual risk to monitor,
    but the primary M1/P2 gates pass.

Findings:
- partial M1->M2 action expansion works mechanically, but M1-only warm-start
  was too conservative for this M2 data mix.
- starting from M2v2 preserved attack knowledge while the far-whiff negative
  log and movement regression loss internalized enough of the old
  support-prior behavior to pass raw gates.
- support-prior is no longer required for M2v4c replay validation/probe, but
  `--dqn-valid-action-mask action-start-v1` remains required.

Next:
- use `model/dqn-retrain-m2-normals-baseline-v4c` as the M2 baseline for Phase
  3 specials.
- before live probing, remember that M2 still lacks specials, projectile
  defense, anti-air, corner, and oki stages.
- watch the far-whiff residual `air-lp` rate during later live or holdout
  checks; finer distance buckets may still be useful.

## 2026-05-02 - Remote RL full retrain M3 specials first attempts

Purpose:
- train Phase 3 / M3 on top of accepted M2v4c using
  `logs/rl-transitions-retrain-p3-specials-human-v1.ndjson`.

P3 data gate:
- accepted for first-pass training.
- rows: `23098`; episodes: `32`; skipped JSON: `0`.
- execution source: all `human-demo`.
- engine-labeled special coverage included:
  `fireball-lp 131`, `fireball-mp 64`, `fireball-hp 27`,
  `shoryuken-lp 97`, `shoryuken-mp 53`, `shoryuken-hp 64`,
  `tatsu-lk 47`, `tatsu-mk 57`, `tatsu-hk 33`.

Trainer changes:
- added `--special-expert-margin-loss` and related flags:
  `--special-expert-margin`, `--special-expert-margin-weight`,
  `--special-expert-margin-batch-size`, `--special-expert-margin-min-reward`,
  `--special-expert-margin-sources`, and
  `--special-expert-margin-valid-action-mask`.
- positive special expert rows are engine-labeled `fireball-*`,
  `shoryuken-*`, or `tatsu-*` experiences whose scaled reward is at least the
  configured minimum.
- added `fireball`, `shoryuken`, and `tatsu` to
  `--movement-regression-action-groups`.
- added `--movement-regression-exclude-special-expert-eligible` so successful
  special examples can be exempted from anti-attack movement regression.

Validation:
- `python3 -m py_compile tools/train_dqn_learner.py`
- `python3 tools/train_dqn_learner.py --help | rg "movement-regression-action-groups|movement-regression-exclude|special-expert-margin"`
- short smoke with `/tmp/rl-m3-special-margin-smoke` confirmed
  `special_margin` triggers and reports eligible rows.

M3 candidates:
- `model/dqn-retrain-m3-specials-baseline-v1`, version `301`:
  preserved M1/M2, but P3 was too conservative; P3 attack rate `2.2%` and no
  special top-1.
- `model/dqn-retrain-m3-specials-baseline-v2`, version `302`:
  stronger special oversampling moved `fireball-lp` into top-2/top-3 but P3
  still had only `0.2%` `fireball-lp` top-1 and `forward` collapsed to
  `72.5%`.
- `model/dqn-retrain-m3-specials-baseline-v3`, version `303`:
  disabled spacing shaping; P3 `fireball-lp` improved only to `0.6%`, still
  no usable specials.
- `model/dqn-retrain-m3-specials-baseline-v4`, version `304`:
  direct special margin made specials top-1 (`fireball-lp 42.7%` on training
  summary; P3 `fireball-lp 10.1%`) but polluted M1 replay badly:
  M1 attack rate `83.0%`.
- `model/dqn-retrain-m3-specials-baseline-v5`, version `305`:
  softened margin; M1 replay recovered to `5.5%` attack rate, but P3 remained
  too conservative (`5.2%` attack rate and no special top-1).
- `model/dqn-retrain-m3-specials-baseline-v6`, version `306`:
  added special-aware movement regression; still failed both gates:
  M1 attack rate `13.1%`, P3 attack rate `8.6%`, no special top-1.

Conclusion:
- no M3 candidate is promoted.
- direct special margin proves the trainer can force specials, but the current
  data/features do not separate "use special now" from M1-style movement
  states cleanly enough.
- next M3 attempt should collect split, targeted P3 logs or add finer context
  features/gates before another long training sweep.

## 2026-05-03: Phase A Trainer Improvements — Entropy Regularization And Adaptive Unsupported-Action Ceiling

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / M3 specials training

Files changed:
- `tools/train_dqn_learner.py`

Purpose:
- add entropy regularization to prevent action collapse in DQN training.
- add adaptive unsupported-action Q ceiling computed from movement action mean Q.

Implementation:
- added `--dqn-entropy-reg-weight` (float, default 0.0): softmax entropy bonus
  applied per-batch to Q-values, encouraging all actions to maintain non-zero
  probability mass.
- added `--dqn-unsupported-action-adaptive-ceiling` (BooleanOptionalAction):
  when enabled, the per-row unsupported-action Q ceiling is set to
  `min(static_ceiling, mean(Q_movement_actions))` instead of a fixed value.
- added `adaptive_ceiling` field to `DQNUnsupportedActionRegularizationConfig`.
- training loop collects all batch Q-values and computes per-row entropy after
  the main forward pass; entropy reg loss is subtracted from total loss.
- entropy reg weight and adaptive ceiling flag are recorded in model metadata.

Validation:
- `python3 -m py_compile tools/train_dqn_learner.py`
- `python3 tools/train_dqn_learner.py --help` confirmed new flags.
- smoke test with `--dqn-entropy-reg-weight 0.001` and
  `--dqn-unsupported-action-adaptive-ceiling` on 500 P3 rows: entropy_reg=0.0017,
  unsupported_reg=0.0004.

## 2026-05-03: M3a Fireball-Only Incremental Training

Milestone:
- Milestone 6: Higher-control-rate policy and curriculum / M3 specials training

Code:
- used existing `train_dqn_learner.py` with A1-A8 improvements.

Purpose:
- test whether incremental training (fireball only on M2v4c warm-start) solves
  the specials learning problem without BC pre-training.

M3a recipe:
- warm-start from `model/dqn-retrain-m2-normals-baseline-v4c` (M2v4c).
- action set: M2's 26 actions + fireball-lp/mp/hp = 29 actions.
- `--movement-regression-action-groups stand-normal,crouch-normal,air-normal,fireball`
- all A4-A8 improvements active (gamma 0.95, double DQN, conservative penalty
  0.15, guard success bonus 0.3, attack risk costs, entropy reg 0.0003,
  adaptive ceiling).
- engine outcome oversampling for fireball: 10x/8x/5x.
- balanced batch: movement=0.5, normal=0.3, special=0.2.
- 4000 steps, LR 0.0003.

Result:
- training greedy: **forward 59.5%, back 39.2%, fireball 0%**.
- engine outcome: 3419 events, 575 hits, 2362 no_damage, engine_outcome_net=-498.9.
- same pattern as all previous M3 attempts — fireball cannot become top-1.
- confirms incremental training alone does not solve the context blindness
  problem.

Conclusion:
- Phase A (强化DQN + incremental training) failed to make M3 specials learnable
  within plan's three-attempt budget.
- per plan conditions, transition to Phase B (BC pre-training).

## 2026-05-03: Phase B1 — Engine Label Coverage Feasibility For BC Pre-Training

Milestone:
- Milestone 6: BC pre-training feasibility assessment

Purpose:
- assess whether existing P3 transition logs have enough label coverage for
  Behavioral Cloning pre-training.

Method:
- analyzed `obs_self_routine_1` / `obs_self_routine_2` / `obs_self_kind_of_waza`
  observation-level engine state fields as label sources.
- mapped engine routine state to action labels:
  - R1=4, R2=16 + KW → fireball-lp/mp/hp.
  - R1=4, R2=17 + KW → shoryuken-lp/mp/hp.
  - R1=4, R2=18 + KW → tatsu-lk/mk/hk.
  - R1=3 → throw.
  - input_action_id != 0 → input action label (movement, normals).
- filtered out contact-reaction rows (R1=1) as non-decision states.

Findings:
- raw combined label coverage: **91.7%** (21,179 / 23,098 rows).
- after filtering contact-reaction rows: **70.6%** (16,301 rows) actionable.
- label distribution: back 19.7%, shoryuken-hp 15.8%, fireball-lp 13.0%,
  tatsu-mk 9.5%, stand-lp 1.4%, throw 1.3%, stand-hp 0.8%, stand-mk 0.6%.
- **70.6% coverage exceeds the 30-50% threshold required for BC pre-training.**
- BC pre-training on existing P3 data is feasible.

## 2026-05-03: Phase B2 — BC Training Mode Implementation

Milestone:
- Milestone 6: BC pre-training implementation

Files changed:
- `tools/train_dqn_learner.py`

Purpose:
- add Behavioral Cloning (supervised cross-entropy) training mode alongside the
  existing DQN training path.

Implementation:
- added `derive_bc_label(row, actions)` function that combines engine state
  labels (for attacks/specials) and input labels (for movement/normals) into
  a single action index, returning None for non-decision rows.
- added `train_bc(rows, actions, ...)` function: builds labeled dataset,
  initializes MLP layers, trains with cross-entropy loss + optional entropy
  regularization, returns trained layers.
- added `--training-mode {dqn,bc}` CLI flag (default: dqn).
- modified `publish_model()` to accept `policy` parameter ("dqn" or "bc").
- modified `load_init_dqn_model()` to accept BC models (policy=bc) as warm-start
  for DQN fine-tuning.
- BC training outputs the same model format as DQN for compatibility with
  inference and warm-start.

Validation:
- `python3 -m py_compile tools/train_dqn_learner.py`
- smoke test on 3000 P3 rows: 2757 labeled (91.9%), BC loss 3.03→3.03,
  labels: forward 1332, back 783, shoryuken-lp 422, stand-mp 131.

## 2026-05-03: BC Pre-Training On Full Retrain Data (M3bc v320)

Milestone:
- Milestone 6: BC pre-training baseline for M3

Command:
```sh
python3 tools/train_dqn_learner.py \
  /tmp/rl-retrain-m1-mix-70-20-10.ndjson \
  logs/rl-transitions-retrain-p2-normals-human-v1.ndjson \
  logs/rl-transitions-retrain-p2-far-whiff-negative-human-v1.ndjson \
  logs/rl-transitions-retrain-p3-specials-human-v1.ndjson \
  --model-dir model/dqn-retrain-bc-m3-v1 --model-version 320 \
  --steps 5000 --batch-size 64 --hidden-sizes 64,64 \
  --actions <full 35-action set> \
  --training-mode bc --dqn-entropy-reg-weight 0.0003 \
  --learning-rate 0.001 --log-interval 500
```

Result:
- **66,756 labeled rows out of 93,802 (71.2%)** — exceeds 30-50% threshold.
- BC loss: 3.74 → 1.41 (well-converged).
- label distribution: forward 30,218 (45.3%), back 20,908 (31.3%),
  shoryuken-lp 4,017 (6.0%), fireball-lp 3,774 (5.7%), tatsu-mk 2,473 (3.7%),
  jump-forward-start 1,797 (2.7%), guard-crouch 1,561 (2.3%).
- skipped: 26,482 attack-unknown + 564 no-label.
- model exported with policy=bc, source=offline-bc.

## 2026-05-03: DQN Fine-Tuning From BC Baseline (M3bc+dqn v330) — Breakthrough

Milestone:
- Milestone 6: first successful M3 specials training

Command:
```sh
python3 tools/train_dqn_learner.py \
  /tmp/rl-retrain-m1-mix-70-20-10.ndjson \
  logs/rl-transitions-retrain-p2-normals-human-v1.ndjson \
  logs/rl-transitions-retrain-p2-far-whiff-negative-human-v1.ndjson \
  logs/rl-transitions-retrain-p3-specials-human-v1.ndjson \
  --model-dir model/dqn-retrain-m3-bc-plus-dqn-v1 --model-version 330 \
  --init-model model/dqn-retrain-bc-m3-v1 --init-model-action-mode expand \
  --actions <full 35-action set> \
  --steps 4000 --batch-size 64 --hidden-sizes 64,64 \
  --learning-rate 0.0001 --gamma 0.95 --target-sync-steps 100 \
  --dqn-target-mode double \
  <all A4-A8 reward/regularization flags>
```

Key parameters for conservative fine-tuning:
- learning_rate 0.0001 (10x lower than standard 0.001).
- conservative_action_penalty 0.05 (mild).
- unsupported_action_regularization with adaptive ceiling, loss_weight 0.03.
- entropy_reg_weight 0.0003.
- movement_regression_loss_weight 0.01 (half of M2's 0.02).
- movement_regression_action_groups: stand-normal, crouch-normal, air-normal,
  fireball, shoryuken, tatsu.
- engine outcome oversampling for all special types.
- balanced batch: movement=0.4, normal=0.2, special=0.4.

Result — **breakthrough: first time special moves appear as top-1 greedy**:
- training greedy: **shoryuken-lp 52.8%**, back 44.5%, forward 2.7%.
- top-2: shoryuken-lp 97.1%, back 58.8%.
- top-3: forward 100%, shoryuken-lp 97.3%, back 84.5%, tatsu-mk 15.5%.
- DQN loss: 9.12 → 1.04 (good convergence from BC initialization).
- engine outcome: 3419 events, 733 hits, shoryuken-mp mean reward +0.034,
  shoryuken-hp mean reward +0.038.
- fireball-lp: 0% top-1 (mean reward -0.014 due to 57% whiff rate in P3 data).

Comparison against all previous M3 attempts:

| Metric | M3 v1-v6, M3a | M3bc+dqn v330 |
|--------|--------------|---------------|
| Top greedy | forward 55-73% | shoryuken-lp 52.8% |
| Specials at top-1 | 0% (all attempts) | 52.8% |
| back | 0-39% | 44.5% |
| forward | 55-73% | 2.7% |

Analysis:
- BC prior successfully survived DQN fine-tuning for movement actions
  (back at 44.5% from BC's 31.3%).
- DQN correctly deprioritized over-represented BC forward (45.3% → 2.7%).
- Shoryuken got amplified (BC 6.0% → DQN 52.8%) because shoryuken has positive
  mean reward (+0.034 to +0.038) from 42-55% hit rates.
- Fireball was suppressed (BC 5.7% → DQN 0%) because fireball has negative mean
  reward (-0.014) from 57% whiff rate in current P3 data.
- shoryuken-lp at 52.8% is too concentrated; needs balancing with fireball
  positive data or stronger entropy regularization.

Conclusion:
- **BC pre-training + DQN fine-tuning is the correct approach for M3.**
- The BC behavioral prior prevents random-initialization action collapse and
  provides a human-like starting distribution.
- DQN TD learning makes local adjustments based on reward outcomes.
- Fireball still fails because P3 data has net-negative fireball outcomes.
- Next: collect fireball-specific positive data or add context features so
  model can distinguish good fireball range from bad.

Follow-up:
- collect P3 fireball-good data (far range, opponent grounded) to increase
  fireball hit rate in training distribution.
- tune entropy reg weight to reduce shoryuken over-concentration.
- run M3bc+dqn-v2 with balanced fireball/shoryuken data.
- consider adding derived context features (opp_airborne, fireball_safe_range)
  to DQN input for better scene differentiation.

## 2026-05-03: Per-Instance Segment-Based KW Propagation For BC Labels

Milestone:
- Milestone 6: BC pre-training label precision improvement

Files changed:
- `tools/train_dqn_learner.py`

Problem:
- The previous per-episode KW map (`_derive_episode_kw_map`) could only
  record one KW strength per (episode, family) pair, collapsing all
  fireball/shoryuken/tatsu instances in the same episode to the most common
  strength.
- C-side KW cache and dm_kind_of_waza fallback attempts did not work because
  the game engine clears `kind_of_waza` before end-of-frame observation.

Discovery:
- Engine outcome rows appear just BEFORE their corresponding attack segment
  in the transition log, not after or during.
- Observation timing: engine outcome fires at routine start, but observation
  captures it during standing/recovery frames (R1=0, R2=4). The actual attack
  segment (R1=4, R2=16/17/18) follows immediately after in the log.
- Confirmed on v3 log row 168: engine outcome (KW=0x09 tatsu-LK) at frame 501,
  attack segment starts at row 168 frame 504.

Algorithm:
- `_derive_segment_kw_map(rows)` replaces `_derive_episode_kw_map`:
  1. Find engine outcome anchors (engine_action_id != 0, KW != 0).
  2. For each anchor, scan forward to find the next contiguous attack segment
     (R1=4, family R2 matching engine_action_id mapping) in the same episode.
  3. Map every (episode_id, decision_id) in that segment to the anchor's KW.
  4. Skip segments already claimed by an earlier anchor.
- `derive_bc_label` uses `_BC_SEGMENT_KW_MAP[(episode_id, decision_id)]` for
  KW lookup when `engine_kind_of_waza == 0`.

Validation:
- All 3 tatsu instances in v3 log verified:
  - tatsu-LK (rows 168-182): 15/15 rows labeled KW=0x09 (LK) ✓
  - tatsu-MK (rows 200-217): 18/18 rows labeled KW=0x0B (MK) ✓
  - tatsu-MK #2 (rows 220-242): 23/23 rows labeled KW=0x0B (MK) ✓
- Full v3 special distribution now shows all 9 strengths:
  shoryuken-mp:170, shoryuken-hp:113, shoryuken-lp:64,
  tatsu-hk:48, tatsu-mk:41, tatsu-lk:25,
  fireball-hp:32, fireball-lp:30, fireball-mp:30

Limitation:
- Engine outcome only fires for human-demo and cpu-demo execution sources
  (C-side guard: `RLSession_IsDemoExecutionSource`). Remote/policy rows
  never get engine_action_id or engine_kind_of_waza populated.
- BC pre-training should use `--replay-source-include human-demo,cpu-demo`
  to exclude remote rows which provide no KW anchors.

## 2026-05-03: Fix Fireball No-Damage Penalty For Blocked/Cancelled Fireballs

Milestone:
- Milestone 6: fix fireball false-whiff penalty and shoryuken over-concentration

Problem:
- SF3 normal specials deal 0 chip damage when blocked (only EX/supers do).
- `reward_risk_cost()` and `engine_outcome_reward()` classified any
  `opponent_damage == 0` attack as "no-damage", penalizing blocked fireballs
  the same as true whiffs.
- Blocked fireballs and projectile-cancel fireballs are positive zoning
  outcomes, not mistakes.
- Shoryuken had no extra no-damage penalty despite being highly unsafe on
  block/whiff (long recovery, easy to punish).

Discovery:
- Schema v6 transition rows capture chip damage for blocked fireballs in
  ~78-93% of cases (`delta_opp_hp=1` in the engine outcome window).
- The remaining ~7-22% are timing edge cases where chip damage falls between
  observation frames.
- `obs_opp_contact_reaction_state != 0` reliably detects blocked fireballs
  in the lookahead window (opponent enters guard routine `r1=1, r2=5/6/12`).
- `obs_projectile_owner == 2` in the window indicates opponent projectile
  was present — fireball likely cancelled it.

Implementation:
- `tools/train_dqn_learner.py`: `reward_risk_cost()` and
  `engine_outcome_reward()`:
  - For `fireball-*` actions: skip no-damage cost when
    `obs_opp_contact_reaction_state != 0` (blocked) or
    `obs_projectile_owner == 2` (projectile cancel) in the lookahead window.
  - Punished cost (self damaged) still applies regardless.
  - Non-fireball actions unchanged.

Validation:
- Fireball-good log smoke: `risk_shape no_damage` dropped from 822 → 0.
- Fireball-good mean reward: fireball-hp -9.71 → +33.42 (v335).

## 2026-05-03: M3bc+dqn v332-v335 Training Iterations

Milestone:
- Milestone 6: fireball gate and shoryuken concentration tuning

v332 (context-gated special expert margin + self-routine features):
- Init: BC-coverage v322 with feature expansion (44→72 features).
- New: self routine one-hot features, context-gated special expert margin,
  fireball zoning movement-regression exemption.
- Result: shoryuken-lp 23.9% (down from v331's 38.9%), but fireball still 0% top1.
- fireball-good top3 fireball-hp: 1.3%.

v333 (add fireball guard/cancel no-damage fix):
- Same data as v332, with guard/cancel fix in reward functions.
- Result: shoryuken-lp 39.2% (rebound), fireball-hp top3: 5.1%.
- Fireball reward improved but shoryuken BC prior amplified it more.

v334 (add schema v6 natural-serious-human-v4 log):
- Added 18k rows of natural human play with proper chip damage.
- Result: shoryuken-lp 30.4%, fireball-hp mean reward 33.42, top3: 18.1%.
- More data helped balance.

v335 (shoryuken whiff penalty + stronger expert margin):
- `--reward-shoryuken-no-damage-extra-cost 0.5` (was 0.0)
- `--special-expert-margin-weight 1.0` (was 0.5)
- **Breakthrough: fireball-hp at top1 for the first time (15.1% trainer, 4.7% FB-good).**
- First meaningful fireball good/bad separation: 4.7% vs 1.3% (3.6x).
- Fireball top3 on FB-good: 14.8% (2x vs v334).

Quality gate summary:

| Gate | v332 | v333 | v334 | v335 |
|------|------|------|------|------|
| Trainer shoryuken-lp top1 | 23.9% | 39.2% | 30.4% | 35.2% |
| Trainer fireball-hp top1 | 0% | 0% | 0% | 15.1% |
| FB-good fireball top1 | 0% | 0% | 0% | 4.7% |
| FB-good fireball top3 | 1.3% | 5.1% | 7.1% | 14.8% |
| FB-bad fireball top1 | 0% | 0% | 0% | 1.3% |
| FB-bad fireball top3 | 0.4% | 5.6% | 6.9% | 9.1% |
| M1 movement shoryuken-lp | 22.6% | 36.7% | 28.6% | 32.1% |

Conclusion:
- Fireball gate: first-ever top1 appearance and meaningful good/bad separation.
- Shoryuken over-concentration improved from v330 (52.8%) but still elevated
  (35.2%). Further tuning needed.
- Model promoted to v335 as current best.

## 2026-05-07: Combat Event Attack Contact Lifecycle Resolve

Milestone:
- Combat event attribution Phase 6b-5 / Phase 8 analyzer hygiene

Problem:
- Live overlay showed close-range attacks that clearly contacted the opponent
  (hit or blocked) left `CE A +1` active for a long time.
- After the max pending window, the attack lifecycle timed out and incremented
  `CER U +1`, even though CEM/CEA/CDR attribution already had contact evidence.

Implementation:
- Added attack lifecycle `result=contact` and
  `finalize_reason=contact_resolved`.
- Non-projectile, non-throw attack events that saw target contact/damage now
  finalize as contact once the actor leaves attack state.
- Analyzer buckets these rows as `contact_resolved` instead of unknown.

Expected live effect:
- Close LP/MP/HP/LK/MK/HK hit or block should drop `CE A` shortly after the
  attack state ends and should not later add `CER U`.
- True whiffs should still finalize through `CER W`.
- Projectile-like parent attacks remain delegated to projectile lifecycle.

Risk:
- If the target contact/damage evidence is noisy, a small number of boundary
  whiffs could be lifecycle-resolved as contact. Hit/block truth remains in
  attribution/defense-result rows; this change only prevents timeout pollution.

## 2026-05-07: Combat Event Attack Start Debounce Widening

Milestone:
- Combat event attribution Phase 6b-6 live overlay accuracy cleanup

Problem:
- Live overlay still showed a single close-range hit/block attack sometimes
  adding `CE S/F +2`.
- The likely sequence is one start edge at attack startup, followed more than
  six frames later by a contact/Attack_Counter edge for the same physical move.
  The previous same-signature debounce window was too short, so the second
  edge created a duplicate attack event.

Implementation:
- Widened same-signature combat attack-start debounce from 6 to 24 frames.

Expected live effect:
- One close LP/MP/HP/LK/MK/HK hit or block should usually add only
  `CE S/F +1`.
- Fast repeated same-move chains may continue to be merged conservatively as a
  single event, which is accepted for this phase.

Risk:
- Very fast same-move chains inside 24 frames are less likely to be counted as
  separate starts. Different-move cancels can still start separate events when
  their signature changes.

## 2026-05-07: Ryu Engine-Owned Combat Attack Starts

Milestone:
- Combat event attribution Phase 6b-7 / Ryu-vs-Ryu engine state-machine cleanup

Problem:
- Live self-side move distribution was wrong when the agent character was Ken
  because only Ryu has source-backed engine attribution today.
- Before expanding to Ken and other characters, the Ryu-vs-Ryu path needs a
  cleaner state-machine contract: engine attack identity should own attack
  starts, while `Attack_Counter` and contact edges should be evidence only.

Implementation:
- Added a strict engine-start attribution path for Ryu attack events.
- For Ryu sides, attack starts require routine/current-attack based engine
  attribution and no longer accept `Attack_Counter` alone as a start edge.
- Existing permissive engine attribution remains for transition/debug labeling.
- Attack journal rows now include raw `routine_1`, `routine_2`,
  `current_attack`, `kind_of_waza`, and matching engine routine/KW fields so
  Ryu-vs-Ryu logs can be audited directly.

Expected live effect:
- In Ryu-vs-Ryu tests, one physical normal/special attack should create one
  attack event from engine state.
- Delayed contact / `Attack_Counter` evidence should not create a second
  `CE S/F` for the same Ryu attack.
- Analyzer move stats should primarily use engine labels for both sides.

Risk:
- Ryu attacks that only expose `Attack_Counter` without a routine/current-attack
  start edge may be undercounted. Live Ryu-vs-Ryu six-button, projectile, throw,
  and special smokes are required before extending this pattern to Ken.

## 2026-05-07: Ryu Attack Lifecycle Throw/Contact Cleanup

Milestone:
- Combat event attribution Phase 6b-8 / Ryu-vs-Ryu lifecycle cleanup

Problem:
- Live Ryu-vs-Ryu logs showed throw routines appearing as attack rows in
  addition to real throw rows.
- Some attacks with later attribution evidence still finalized as
  `basic_unknown_timeout`, and some superseded attacks with contact evidence
  finalized as `superseded_by_new_start` unknown.

Implementation:
- Ryu engine-owned attack starts now reject engine attribution rows whose
  lifecycle action is `RL_POLICY_ACTION_THROW`; throw attempts remain owned by
  the throw event ring.
- The generic attack start path also drops starts whose effective lifecycle
  action is throw, preventing policy/input throw rows from entering the attack
  ring.
- `RLCombatEvent_FinalizeActiveSide()` now resolves superseded active attacks
  as `contact_resolved` when target contact/damage evidence was already seen,
  before falling back to clean-whiff or unknown handling.
- `RLCombatEvent_TryBasicFinalize()` now applies the same contact-resolve check
  at max-pending timeout before emitting `basic_unknown_timeout`.

Expected live effect:
- Attack move stats should no longer contain throw-like attack rows; throws
  should remain only in `event_kind=throw`.
- Ryu `shoryuken-*` or heavy normal rows that have hit/block attribution should
  stop ending as `timeout_unknown` / `rollover_unknown`.
- Rows with no contact/damage evidence remain conservative unknowns.

Risk:
- No-contact events are intentionally unchanged. Contact-resolved is still a
  lifecycle label only; hit/block truth continues to come from attribution and
  defense-result rows.

## 2026-05-07: Recent Source Continuation for Attribution

Milestone:
- Combat event attribution Phase 6a-2 / recent confirmed source continuation

Problem:
- Live event journals still showed `defense_result=unknown` rows with
  `failure_reason=no_source_candidate`, `edge_type=hp_delta`, and target
  hitstun shortly after successful hit/block attribution.
- These rows are likely continuation damage/chip from a source that was already
  confirmed but no longer active in the matcher window.

Implementation:
- Added a tiny per-direction recent attribution cache for successful
  attack/projectile source matches only.
- If a later HP/stun delta has no active attack/projectile/throw source
  candidate, the matcher may reconnect it to the most recent same-direction
  confirmed source.
- Continuation is allowed only within a short window: 8 frames for attacks and
  12 frames for projectiles.
- Continuation is rejected if an opposite-direction confirmed attribution
  happened after the candidate source, if the previous source was throw, or if
  the previous defense result was not hit/block/chip.
- Continuation rows do not open new punish candidates, so multi-hit continuation
  does not double-count punish opportunities.

Expected live effect:
- `source_family=unknown` / `no_source_candidate` HP-delta rows should drop for
  multi-hit or delayed chip/hit cases.
- The same source event id should be reused for short continuation damage.
- Throw rows and ambiguous long gaps remain conservative unknowns.

Risk:
- Wrong-source continuation is possible in chaotic trades. The first pass keeps
  the window short, requires same source/target direction, and refuses to bridge
  across an intervening confirmed opposite-side attribution.

## 2026-05-07: Finalized Attack Rescue for Orphan Attribution

Milestone:
- Combat event attribution Phase 6a-3 / finalized attack rescue attribution

Problem:
- A live Ryu-vs-Ryu log recorded with only self `MK` and `fireball-mp` still
  had three `defense_result=unknown` / `failure_reason=no_source_candidate`
  HP-delta attribution rows.
- Two self-side examples showed damage a few frames after an `air-mk` had
  already finalized as `whiff`, or while a `crouch-mk` source overlapped an
  older projectile and was therefore not selected as the active attack source.

Implementation:
- `RLCombatEvent_FindAttackCandidateForSide()` now chooses the newest active
  non-projectile attack and no longer rejects an otherwise valid strike just
  because it has observed a same-side projectile. Projectile candidates still
  have higher priority, so real projectile contact remains projectile-owned.
- Added a finalized attack rescue path for strong HP/stun/damage edges with no
  projectile, throw, or active attack candidate.
- Rescue can only select the newest same-side non-projectile attack finalized
  as clean `whiff` or `superseded_by_new_start` unknown within an 18-frame
  window. Active/newer sources win before rescue, so cases like blocked
  `air-mk` followed by hit `crouch-mk` should credit the newer `crouch-mk`.

Expected live effect:
- Late air-normal contact and short delayed normal damage should stop becoming
  `source_family=unknown` / `no_source_candidate`.
- `MK` / `fireball-mp` only logs should keep self move stats limited to MK
  normals and MP fireballs, aside from true input/execution mistakes.

Risk:
- The 18-frame window is intentionally narrow but still heuristic. Chaotic
  trades can remain unresolved if multiple finalized sources are plausible; the
  matcher picks the most recently ended/newest source and otherwise keeps the
  standard projectile/throw/active-attack priority.

Validation:
- `tools/mister/build-game.sh --flavor telemetry` passed and rebuilt
  `src/rl/rl_combat_event.c`.
- Re-running `tools/analyze_rl_combat_events.py` on the pre-fix live log is
  unchanged as expected, because the fix affects new C-side journal emission.

## 2026-05-07: Per-Frame Combat Context Fallback

Milestone:
- Combat event attribution Phase 7A-3 / event journal source reliability

Problem:
- Live MK / tatsu-MK testing reduced attribution unknowns to one row, but the
  remaining row showed opponent `routine1=4/routine2=17` damaging self while
  `opp_engine_*` and `source_event_id` were zero.
- `RLSession_OnObservationFrameEnd()` runs every frame, but combat event
  updates were only applied when an active decision ledger entry existed. A
  source start edge that occurs outside that span can therefore be observed by
  the game-state sampler but not promoted into the combat event ring.

Implementation:
- Added a lightweight per-frame combat context in `rl_session.c`. When there is
  no active ledger entry, the context fills run/episode/frame/nearest-decision
  and character metadata from live state, then updates combat attack/projectile/
  throw/contact rings without writing a transition row or accumulating reward.
- Added `RLCombatEvent_HasActiveAttackForSide()` so source fallback can avoid
  opening a duplicate attack when a normal active source already exists.
- Split Ryu special strength decoding so special KW `0x08/0x0A/0x0C` and
  `0x09/0x0B/0x0D` are treated as explicit strengths, while missing KW can
  still create an unknown-strength special source instead of failing entirely.
- Added a damage-triggered Ryu non-projectile special fallback for shoryuken,
  tatsu, air tatsu, joudan, and shin shoryuken when target HP/stun damage
  arrives and no same-side active attack source exists.
- Analyzer now renders sub-action `0` as `unknown`, e.g.
  `shoryuken-unknown`, rather than `sub0`.

Expected live effect:
- Opponent `routine2=17` damage without a captured start edge should become a
  shoryuken-family source with unknown strength instead of
  `failure_reason=no_source_candidate`.
- Event capture should be less dependent on active ledger lifetime, while
  transition rows and reward accumulation remain ledger-owned.
- MK/tatsu move distribution should not inflate because fallback is gated by
  target damage, no active same-side attack, and the existing start debounce.

Risk:
- Unknown-strength fallback is heuristic. Chaotic trades can still remain
  unresolved, and a bad routine/KW window could label a source at damage time
  instead of true startup time.
- Re-test live overlay counters for CE/CER/CDR inflation, especially repeated
  specials and simultaneous attacks.

Validation:
- First `tools/mister/build-game.sh --flavor telemetry` caught an unused helper
  after the KW split; removed it.
- Second `tools/mister/build-game.sh --flavor telemetry` passed.
- `python3 -m py_compile tools/analyze_rl_combat_events.py` passed.
- Python smoke confirmed analyzer renders `(shoryuken, sub_action=0)` as
  `shoryuken-unknown` with `unknown_strength` tags.
- Existing `logs/phase7a-event-journal-live-*.ndjson` files were not present in
  the workspace at validation time, so C-side behavior requires a fresh MiSTer
  deploy and live log.

## 2026-05-07: Ryu R2=2 Air-MP Continuation Fix

Milestone:
- Combat event attribution Phase 7A-4 / Ryu taxonomy and source correction

Problem:
- Fresh Ryu-vs-Ryu MP-only live logs showed transition rows where self entered
  `R1=4/R2=2` four times, with three complete sequences producing two HP/stun
  deltas each.
- The event journal recorded those HP-delta rows as
  `failure_reason=no_source_candidate` because C still treated Ryu `R2=2` as a
  throw-like routine and rejected it from attack-event starts.
- Source review showed the old taxonomy was wrong: Ryu `R2=2` comes from the
  common `Attack_02000` path and the Ryu MP AS table entry, not from throw.

Implementation:
- Updated `docs/rl-policy-action-taxonomy.md`:
  - Ryu `R1=4/R2=2` is documented as common `Attack_02000`, sourced from
    `asstbl_lv_0010[_arcade][Ryu][MP][2]` (`.r_no=2`, `.char_ix=5`,
    `.data_ix=21`), and live-observed as an air-MP continuation/follow-up damage
    window.
  - Ryu throw startup is now documented as `R1=4/R2=14` or `R1=4/R2=15`, with
    successful throw ownership validated through `R1=2`/`R1=3` catch states.
  - Ken's normal AS tables were checked and have no `.r_no=2` normal entry, so
    the Ryu continuation rule must not be copied to Ken without separate live
    validation.
- Updated `src/rl/rl_session.c`:
  - Removed Ryu `R2=2 -> RL_POLICY_ACTION_THROW`.
  - Added `R2=15` to the Ryu throw-start routine check.
  - Added a damage-triggered Ryu `R2=2` fallback source labeled as
    `RL_POLICY_ACTION_AIR_NORMAL / MP`, used only when target damage/stun arrives
    and no same-side active source exists.

Expected live effect:
- New logs for the same MP-only smoke should attach `R2=2` HP/stun deltas to an
  air-MP continuation source instead of emitting self-side
  `no_source_candidate` attribution rows.
- Throw counters should no longer be affected by Ryu `R2=2`.
- Ken remains unchanged.

Risk:
- Ryu `R2=2` has both a source-table standing forward-MP branch and a
  live-observed air-MP continuation role. The current runtime fix is deliberately
  damage-gated and Ryu-only, but a future detailed normal-table pass may need a
  more precise `char_ix/data_ix`-backed label if the two uses must be separated.

Validation:
- `tools/mister/build-game.sh --flavor telemetry` passed and rebuilt
  `src/rl/rl_session.c`. The only warning was the existing minizip `mktemp`
  linker warning.
- `python3 -m py_compile tools/analyze_rl_combat_events.py` passed.
- Existing live logs remain useful for diagnosis but cannot show the C-side
  source fix retroactively; deploy and re-record the MP-only smoke to verify
  self-side `no_source_candidate` rows drop for Ryu `R2=2` HP/stun deltas.

## 2026-05-07: Ryu R2=2 Damage Fallback Branch Fix

Milestone:
- Combat event attribution Phase 7A-4a / Ryu `R2=2` fallback correction

Problem:
- A fresh MP-only live log after the taxonomy/source correction still showed two
  self-side `failure_reason=no_source_candidate` attribution rows.
- The remaining unknown rows occurred while transition rows had self
  `R1=4/R2=2` and target HP/stun deltas at decisions 174 and 177.
- Code review found the damage fallback mapper tested the Ryu special mapper
  inverted, so non-special `R2=2` states never reached the air-MP continuation
  branch.

Implementation:
- Updated `src/rl/rl_session.c`:
  - `RLSession_BuildRyuDamageFallbackStateAttributionForSide()` now first accepts
    real Ryu special routine metadata.
  - If the special mapper does not match, it then checks the Ryu-only `R2=2`
    air-MP continuation fallback.
  - Other characters, including Ken, remain unchanged.
- Updated `docs/plan-remote-rl-agent.md` with the Phase 7A-4a checklist item.

Expected live effect:
- Re-recording the same Ryu-vs-Ryu MP-only smoke should attach the delayed
  `R2=2` HP/stun deltas to an air-MP continuation source.
- The analyzer's self-side `no_source_candidate` count for those `R2=2` damage
  rows should drop from 2 to 0.

Risk:
- This remains a conservative damage-gated fallback. It should not create an
  attack row for harmless `R2=2` windows with no target HP/stun delta.

Validation:
- `git diff --check` passed.
- `python3 -m py_compile tools/analyze_rl_combat_events.py` passed.
- `tools/mister/build-game.sh --flavor telemetry` passed and rebuilt
  `src/rl/rl_session.c`. The only warning was the existing minizip `mktemp`
  linker warning.
- Existing live logs showed the pre-fix symptom (`no_source_candidate=2`) and
  cannot validate the changed C branch retroactively; deploy this build and
  re-record the MP-only smoke to confirm the count drops to 0.

## 2026-05-07: Ken Engine Attribution Support

Milestone:
- Combat event attribution Phase 7A-5 / Ken source-backed engine attribution

Problem:
- Combat event engine-owned attack starts were deliberately Ryu-only while the
  Ryu state machine was being validated.
- The next character target is Ken. Ken's command routine table is
  source-backed in `plpat11.c`, and the taxonomy already records the expected
  `R2` values, but C did not yet use those rows for combat event source labels.
- The recent Ryu `R2=2` edge case should stay Ryu-only; Ken's normal AS tables
  have no validated `.r_no=2` meaning.

Implementation:
- Updated `src/rl/rl_session.c`:
  - added Ken policy action constants (`2120/2121/2122/2128/2129/2130/2146`)
    and `RL_CHARACTER_KEN`.
  - generalized the engine-owned character gate to Ryu or Ken.
  - added Ken special routine mapping:
    - `R2=16` Hadouken -> `2129`
    - `R2=17` Shoryuken -> `2128`
    - `R2=18` Tatsumaki -> `2130`
    - `R2=19` Shoryureppa -> `2120`
    - `R2=20` Shinryuken -> `2121`
    - `R2=21` Shippu Jinraikyaku -> `2122`
    - `R2=22` Air Tatsumaki -> `2146`
  - kept common throw startup on `R2=14/15` for both Ryu and Ken.
  - kept Ryu `R2=2` air-MP continuation fallback Ryu-only.
  - added Ken Hadouken as projectile-like, and Ken non-projectile specials as
    allowed damage fallback sources.
- Updated `tools/analyze_rl_combat_events.py` and `tools/rl_probe_server.py` so
  Ken `212x` action IDs are summarized with the same generic move names used for
  Ryu (`fireball-*`, `shoryuken-*`, `tatsu-*`, `air-tatsu-*`) plus Ken super
  names.
- Updated `docs/plan-remote-rl-agent.md` and
  `docs/rl-policy-action-taxonomy.md`.

Expected live effect:
- Ken-vs-Ryu or Ken-vs-Ken event logs should no longer show Ken special attacks
  as unknown engine actions when routine edges are visible.
- Ken Hadouken attack rows should be marked projectile-like and delegate to
  projectile journal rows.
- Ken normal attacks should use the existing generic normal identity path.
- Ken `R2=2` should remain unmapped unless a future Ken-specific live/source
  pass proves a concrete meaning.

Risk:
- Ken super-art strength/sub-action is still conservative (`sub_action=none`).
- This does not change learner/reward behavior; it only affects combat event
  labeling and analyzer summaries.

Validation:
- `git diff --check` passed.
- `python3 -m py_compile tools/analyze_rl_combat_events.py tools/rl_probe_server.py`
  passed.
- `tools/mister/build-game.sh --flavor telemetry` passed and rebuilt
  `src/rl/rl_session.c`. The only warning was the existing minizip `mktemp`
  linker warning.
- Existing Ryu event journal analyzer smoke passed on
  `logs/phase7a-event-journal-live-events.ndjson` joined with
  `logs/phase7a-event-journal-live-transitions.ndjson`.
- Direct Python mapping smoke confirmed Ken action IDs `2129/2128/2130/2146`
  map to `fireball-*`, `shoryuken-*`, `tatsu-*`, and `air-tatsu-*`, and Ken
  super IDs `2120/2121/2122` map to `shoryureppa`, `shinryuken`, and
  `shippu-jinraikyaku`.
- Live Ken logs are still required to validate routine timing and edge counts on
  device.

## 2026-05-07: Phase 9 Event-Aware Trainer Data Recollection Gate

Milestone:
- Combat event attribution Phase 9 / learner adoption planning

Purpose:
- Document that event-aware DQN training requires fresh paired
  transition/event logs, not old transition-only replay data.
- Keep event rows as training labels/metadata until explicit trainer flags opt
  into reward shaping or event-derived replay experiences.

Implementation:
- Updated `docs/plan-remote-rl-agent.md`:
  - added Phase 9A data recollection, schema, analyzer, and training eligibility
    gates.
  - specified the first recollection curriculum for Ryu vs Ryu, Ken vs Ryu,
    side-symmetry, and negative/safety cases.
  - added Phase 9B/9C/9D trainer adoption steps for reader, reward-shaping MVP,
    prefer-event-action, and event-aware sampling.
- Updated `docs/agent-memory/remote-rl-combat-event-attribution-plan.md` with
  the same paired-file collection contract and eligibility thresholds.

Expected effect:
- Future trainer work will first collect and validate sibling
  `*-transitions.ndjson` and `*-events.ndjson` files from the same probe batch
  envelope before any combat event label can affect rewards.
- Candidate datasets must pass analyzer checks for schema, event id ordering,
  missing refs, transition joins, projectile counters, unknown/no_source counts,
  and side splits.

Risk:
- Documentation-only change. Runtime, probe, event journal export, and trainer
  behavior are unchanged.

Validation:
- Markdown updates reviewed by diff. No code validation required for this
  planning-only change.
