#!/usr/bin/env python3
"""Phase 0+1 combat evidence bitmask helpers."""

from __future__ import annotations

from dataclasses import dataclass


EVIDENCE_BITMASK_VERSION_V1 = 1
U32_MAX = 0xFFFFFFFF

EVIDENCE_FIELD_NAMES_V1: tuple[str, ...] = (
    "requested_attack_input_started",
    "requested_attack_became_active",
    "requested_attack_entered_state",
    "requested_attack_made_contact",
    "requested_attack_likely_whiffed",
    "requested_jump_started",
    "requested_movement_succeeded",
    "observed_attack_state_started",
    "observed_attack_code_changed",
    "observed_attack_counter_started",
    "overlay_attack_event_finalized",
    "overlay_attack_contact",
    "overlay_attack_whiff",
    "self_attack_started",
    "opp_attack_started",
    "self_airborne_started",
    "opp_airborne_started",
    "self_entered_hit_stop",
    "opp_entered_hit_stop",
    "self_entered_contact_state",
    "opp_entered_contact_state",
    "self_entered_damage_state",
    "opp_entered_damage_state",
    "self_throw_started",
    "opp_throw_caught_started",
)

EVIDENCE_V1_USED_LO_MASK = (1 << len(EVIDENCE_FIELD_NAMES_V1)) - 1
EVIDENCE_V1_USED_HI_MASK = 0

EVIDENCE_ROOT_KEYS = frozenset(
    {
        "evidence_bitmask_version",
        "evidence_flags_lo",
        "evidence_flags_hi",
        "ep_overlay_attack_active_count",
        "ep_overlay_attack_contact_count",
        "ep_overlay_attack_whiff_count",
    }
)

COMBAT_EVENT_ROOT_KEYS = frozenset(
    {
        "actual_guard_state",
        "actual_guard_state_code",
        "child_projectile_event_id",
        "combat_event_schema_version",
        "confidence",
        "confidence_code",
        "current_attack",
        "decision_id",
        "defense_result",
        "defense_result_code",
        "edge_type",
        "edge_type_code",
        "end_decision_id",
        "end_frame",
        "engine_action_id",
        "engine_current_attack",
        "engine_label_source",
        "engine_sub_action_id",
        "episode_id",
        "event_id",
        "event_kind",
        "failure_reason",
        "failure_reason_code",
        "finalize_reason",
        "finalize_reason_code",
        "frame_id",
        "kind_of_waza",
        "last_rel_x",
        "last_rel_y",
        "last_time_to_self",
        "last_vel_x",
        "owner_side",
        "parent_attack_event_id",
        "path",
        "path_code",
        "policy_action_id",
        "policy_action_step",
        "policy_sub_action_id",
        "projectile_like",
        "punished_attack_event_id",
        "punished_side",
        "punisher_side",
        "reason",
        "reason_code",
        "result",
        "result_code",
        "round_num",
        "run_id",
        "saw_opposing_projectile",
        "saw_opposing_throw",
        "saw_target_caught",
        "saw_throw_escape",
        "side",
        "source_event_id",
        "source_family",
        "source_family_code",
        "source_side",
        "spawn_rel_x",
        "spawn_rel_y",
        "spawn_time_to_self",
        "spawn_vel_x",
        "start_decision_id",
        "start_frame",
        "status",
        "status_code",
        "target_airborne",
        "target_attack_state_active",
        "target_block_reaction",
        "target_guard",
        "target_hp_delta",
        "target_parry_started",
        "target_policy_action_id",
        "target_policy_action_step",
        "target_policy_sub_action_id",
        "target_routine_1",
        "target_routine_2",
        "target_side",
        "target_state",
        "target_state_code",
        "target_stun_delta",
        "target_throw_caught",
        "whiff_eligible",
    }
)


@dataclass(frozen=True)
class EvidenceDecodeResult:
    version: int
    flags_lo: int
    flags_hi: int
    fields: dict[str, bool]
    reserved_lo: int = 0
    reserved_hi: int = 0

    @property
    def reserved_bits_set(self) -> bool:
        return self.reserved_lo != 0 or self.reserved_hi != 0

    def to_jsonable(self) -> dict[str, object]:
        return {
            "version": self.version,
            "flags_lo": self.flags_lo,
            "flags_hi": self.flags_hi,
            "fields": self.fields,
            "reserved_bits_set": self.reserved_bits_set,
            "reserved_lo": self.reserved_lo,
            "reserved_hi": self.reserved_hi,
        }


class EvidenceDecodeError(ValueError):
    pass


def is_forbidden_feature_name(name: object) -> bool:
    text = str(name)
    return (
        text in EVIDENCE_ROOT_KEYS
        or text in COMBAT_EVENT_ROOT_KEYS
        or text.startswith("evidence_")
        or text.startswith("ep_overlay_")
    )


def sanitize_feature_names(names: object) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if not isinstance(names, list):
        return (), ()
    kept: list[str] = []
    stripped: list[str] = []
    for raw_name in names:
        name = str(raw_name)
        if is_forbidden_feature_name(name):
            stripped.append(name)
            continue
        kept.append(name)
    return tuple(kept), tuple(stripped)


def parse_u32_field(row: dict[str, object], key: str) -> int:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise EvidenceDecodeError(f"{key} must be an unsigned 32-bit JSON integer, got {value!r}")
    if value < 0:
        raise EvidenceDecodeError(f"{key} must be non-negative before masking, got {value}")
    if value > U32_MAX:
        raise EvidenceDecodeError(f"{key} must be <= 0xffffffff, got {value}")
    return value & U32_MAX


def decode_evidence(row: dict[str, object], *, strict: bool = False) -> EvidenceDecodeResult | None:
    raw_version = row.get("evidence_bitmask_version")
    if raw_version is None:
        return None
    if isinstance(raw_version, bool) or not isinstance(raw_version, int):
        raise EvidenceDecodeError(f"evidence_bitmask_version must be an integer, got {raw_version!r}")
    if raw_version != EVIDENCE_BITMASK_VERSION_V1:
        if strict:
            raise EvidenceDecodeError(f"unknown evidence_bitmask_version={raw_version}")
        return None

    flags_lo = parse_u32_field(row, "evidence_flags_lo")
    flags_hi = parse_u32_field(row, "evidence_flags_hi")
    fields = {
        name: bool(flags_lo & (1 << bit_index))
        for bit_index, name in enumerate(EVIDENCE_FIELD_NAMES_V1)
    }
    return EvidenceDecodeResult(
        version=raw_version,
        flags_lo=flags_lo,
        flags_hi=flags_hi,
        fields=fields,
        reserved_lo=flags_lo & ~EVIDENCE_V1_USED_LO_MASK,
        reserved_hi=flags_hi & ~EVIDENCE_V1_USED_HI_MASK,
    )
