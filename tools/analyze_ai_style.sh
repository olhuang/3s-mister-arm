#!/usr/bin/env bash
set -eu

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/.." && pwd)"
active_dir="${repo_root}/src/sf33rd/Source/Game/com/active"
passive_dir="${repo_root}/src/sf33rd/Source/Game/com/passive"

characters=(
  "Gill"
  "Alex"
  "Ryu"
  "Yun"
  "Dudley"
  "Necro"
  "Hugo"
  "Ibuki"
  "Elena"
  "Oro"
  "Yang"
  "Ken"
  "Sean"
  "Urien"
  "Akuma"
  "Chun-Li"
  "Makoto"
  "Q"
  "Twelve"
  "Remy"
)

count_pattern() {
  local pattern="$1"
  local file="$2"

  if [[ ! -f "$file" ]]; then
    echo 0
    return
  fi

  rg -o "$pattern" "$file" 2>/dev/null | wc -l | tr -d ' '
}

emit_row() {
  local idx="$1"
  local name="$2"
  local active_file
  local passive_file
  local a_approach
  local p_approach
  local a_search
  local p_search
  local a_jump
  local p_jump
  local a_command
  local p_command
  local a_normal
  local p_normal

  active_file="${active_dir}/active$(printf '%02d' "$idx").c"
  passive_file="${passive_dir}/pass$(printf '%02d' "$idx").c"

  a_approach="$(count_pattern 'Approach_Walk\(' "$active_file")"
  p_approach="$(count_pattern 'Approach_Walk\(' "$passive_file")"
  a_search="$(count_pattern 'Search_Back_Term\(' "$active_file")"
  p_search="$(count_pattern 'Search_Back_Term\(' "$passive_file")"
  a_jump="$(count_pattern 'Jump_Attack\(' "$active_file")"
  p_jump="$(count_pattern 'Jump_Attack\(' "$passive_file")"
  a_command="$(count_pattern 'Command_Attack\(' "$active_file")"
  p_command="$(count_pattern 'Command_Attack\(' "$passive_file")"
  a_normal="$(count_pattern 'Normal_Attack\(' "$active_file")"
  p_normal="$(count_pattern 'Normal_Attack\(' "$passive_file")"

  printf '%02d,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n' \
    "$idx" "$name" \
    "$a_approach" "$p_approach" \
    "$a_search" "$p_search" \
    "$a_jump" "$p_jump" \
    "$a_command" "$p_command" \
    "$a_normal" "$p_normal"
}

echo "idx,character,active_approach_walk,passive_approach_walk,active_search_back_term,passive_search_back_term,active_jump_attack,passive_jump_attack,active_command_attack,passive_command_attack,active_normal_attack,passive_normal_attack"

for idx in "${!characters[@]}"; do
  emit_row "$idx" "${characters[$idx]}"
done
