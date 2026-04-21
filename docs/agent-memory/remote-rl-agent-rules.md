# Remote RL Agent Project Rules

Use this document for any work related to the remote RL agent, RL bridge, RL observation/action protocol, RL training loop, or AI-vs-CPU automation.

## Required Session Startup

At the start of every new remote RL agent session:

- Read `docs/plan-remote-rl-agent.md`.
- Read `docs/remote-rl-agent-engineering-log.md`.
- Check the milestone checklist before choosing work.
- Check the engineering log for current status, open issues, previous failed attempts, and validation notes.
- Confirm the current git branch is a local work branch before implementation.
- Do not start by editing `src/netplay/*`.

## Before Code Changes

Before changing code:

- State the milestone or checklist item being worked on.
- State the purpose of the change.
- State the expected behavior or validation outcome.
- State the main risks and possible side effects.
- Identify the files or modules expected to change.
- Keep the RL implementation independent from upstream/future P2P netplay.

Required framing:

- Purpose:
- Expected effect:
- Risk / side effect:
- Planned files:
- Validation:

## Implementation Rules

- Keep substantial RL implementation under `src/rl/*`.
- Treat the remote RL agent as a local input provider plus observation exporter.
- Do not treat the remote PC as a Gekko or P2P netplay peer.
- Do not depend on `src/netplay/*`, upstream P2P session objects, rollback session state, or netplay packet formats.
- Do not use `MODE_NETWORK` for RL v1.
- Use `MODE_VERSUS + rl_session_active` as the v1 baseline until the plan says otherwise.
- Keep shared game-file edits as small hook calls where possible.
- Put shared helper code in neutral modules such as `src/input/*`, `src/session/*`, or `src/debug/*` only if needed.

## After Code Changes

After changing code:

- Run the smallest relevant validation command available.
- Update `docs/plan-remote-rl-agent.md` checklist items that are now implemented and verified.
- Update `docs/remote-rl-agent-engineering-log.md` with:
  - milestone
  - files changed
  - purpose
  - implementation notes
  - validation commands and results
  - failures or surprises
  - follow-up tasks
- Record MiSTer deploy details if a MiSTer build was deployed.
- Commit code and related documentation together unless the user explicitly asks not to commit.

## Commit Rules

- Commit only intentional changes for the current task.
- Do not include unrelated local edits.
- Use a clear commit message that names the milestone or subsystem.
- Do not amend existing commits unless explicitly requested.
- Do not push unless explicitly requested.

## Documentation Sync Rules

The plan and engineering log must stay in sync:

- If implementation completes a task, check it in the plan.
- If implementation reveals a new risk, add it to the engineering log and update the plan if it changes design direction.
- If a validation result contradicts the plan, update the plan before continuing.
- If a milestone scope changes, update both the milestone checklist and the engineering log.

## Validation Rules

- Prefer local-only validation before MiSTer deploy.
- Use MiSTer deploy only when the milestone requires on-device behavior.
- For MiSTer deploy/probe work, also read `docs/mister-runbook.md` and `docs/agent-memory/mister-remote-safety.md`.
- Record exact commands and outputs that determine pass/fail.
- Do not mark checklist items complete without validation notes.

## Current First Implementation Step

Start with:

- Milestone 0A: Baseline match-flow confirmation spike

Do not start networking, observation serialization, or learner work until Milestone 0A and Milestone 0B are validated.
