---
name: review-loop
description: Open a PR and run a gated review→fix→test→re-review loop with the pr-reviewer agent until it returns ACCEPTABLE. Catches real issues before merge; the orchestrator addresses findings and re-reviews each round.
allowed-tools: Task, Bash, Read, Write, Edit, Grep, Glob
---

# PR Review Loop

Gate a branch before merge with an independent adversarial reviewer, then drive
it to green. The loop has a terminal state — `## VERDICT: ACCEPTABLE` — and you
drive it there round by round.

## When to use
- A branch of completed work that's ready to merge (often right after
  `/pipeline`).
- Re-checking a PR after addressing earlier feedback.

## The reviewer
Uses the **`pr-reviewer`** agent (`.claude/agents/pr-reviewer.md`): read-only,
reproduces the full `base...HEAD` diff itself, triages by risk
(trading/correctness first, docs last), **mutation-tests** load-bearing claims
against the real code, tags findings BLOCKER/MAJOR/MINOR/NIT, and ends with
exactly `## VERDICT: ACCEPTABLE` (zero BLOCKER/MAJOR) or `## VERDICT: NEEDS_WORK`.
Only BLOCKER/MAJOR gate the merge.

## Pre-flight: make the PR diff clean
Before opening the PR, **sync the branch so the diff is only your work**:
```bash
git fetch origin main
git rev-list --count HEAD..origin/main      # behind?  → merge main in first
git diff --stat origin/main..HEAD            # what the PR will show
```
If behind (common after a squash-merge + automation commits), `git merge
origin/main`, resolving conflicts toward **your** version for code you changed
(e.g. keep the uv-based `ci.yml`) and toward **main** for automation artifacts
(`livetrade/*.json`, the paper ledger — take theirs). Verify the diff is then
just your files and `git rev-list --count HEAD..origin/main` is 0. This avoids a
PR that silently reverts main's automation.

Open the PR with `mcp__github__create_pull_request` (check for a PR template
first; mirror its headings if present). Do **not** create a PR unless asked, and
do **not** merge unless asked.

## The loop
1. **Dispatch `pr-reviewer`** with the PR number, head→base, a one-paragraph
   description of what the PR does, the per-file risk triage, and the cheap
   checks to run (`pytest -m "not slow"`, `ruff check .`, scope-discipline grep
   that no human-only file leaked in). Tell it to leave the tree clean and end
   with the verdict line.
2. **Read the verdict.**
   - `ACCEPTABLE` → done. Report the green verdict; offer to squash-merge (don't
     merge unless asked).
   - `NEEDS_WORK` → for each BLOCKER/MAJOR: fix it, **verify the fix yourself**
     (and independently reproduce one finding's evidence — e.g. the reviewer
     said a section is duplicated → confirm, dedupe with a self-verifying
     script). MINOR/NIT: address if cheap, or note why you're leaving it
     (consistency with existing convention is a valid reason).
3. **Commit + push** the fixes (conventional commit; repo footers).
4. **Re-dispatch `pr-reviewer` (next round)** scoped to: confirm the prior
   findings are resolved, nothing regressed since last round (`git diff
   <prev-tip>..HEAD` is only the fixes), suite still green. Loop to step 2.
5. Repeat until `ACCEPTABLE`. Refresh the picture each round; if a finding is
   genuinely out of scope or pre-existing, say so explicitly rather than
   churning.

## Orchestrator discipline
- **Verify, don't just relay.** Reproduce the reviewer's headline finding and
  the headline fix yourself (a quick mutation/grep), so the verdict is earned.
- **Don't merge unprompted.** When the loop is green, confirm CI is also green
  (`mcp__github__actions_list` for the tip SHA) and offer the squash-merge.
- **Squash-merge** is the default here — the branch history is usually already
  collapsed; squash yields one clean commit. Provide a real title + body.
- The reviewer agent type may not hot-load mid-session the turn it's created;
  if `subagent_type: pr-reviewer` isn't found, drive the same loop via
  `code-reviewer` with the pr-reviewer brief (incl. the verdict contract)
  inlined, and it'll be available next session.

## Output
A PR driven to `## VERDICT: ACCEPTABLE` with CI green, each round's fix committed
and pushed, ready for a (user-approved) squash-merge.
