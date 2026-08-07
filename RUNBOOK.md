# Phase 5 Maintainer Runbook — Manual Steps Punch List

This is the operational checklist **you** run for the Phase 5 feature expansion
(releases 3.1 → 3.7). It exists because the dev sandbox has no outbound access to
GitHub and no `gh`/SSH credentials: code and commits are prepared in the working
copy, but **every step that touches GitHub or PyPI is manual and yours**.

Workflow model (confirmed): **one branch + one PR per subphase, each cut fresh off
`main` and merged before the next slice starts.** Each phase ends by cutting a
SemVer **minor** release. Code review is automated (reviewers already configured),
so "review" below means *watch for and address* review comments, not request them.

Legend: ☐ = a manual step you perform. 🤖 = prepared for you in the working copy
(no action from you until the ☐ that follows).

---

## A. Roles at a glance

| Who | Does what |
|---|---|
| 🤖 Working copy | Creates the branch, writes code/tests/docs, scoped Conventional-Commits commits, `CHANGELOG.md` `[Unreleased]` entry. |
| ☐ You | Push the branch, open the PR (base `main`), approve/merge, then cut the next slice off updated `main`. |
| 🤖 Automated reviewers + CI | Review each PR; run CI / Docs / Security / API-Drift and the ≥90% coverage gate. |

`main` is protected: no direct pushes, squash-merge only, always releasable.
Because each slice builds on the last, **merge a slice before cutting the next** so
its work is already on `main`.

---

## B. The two punch lists you run per subphase

Section D gives the **exact, copy-paste commands** for every slice. These are the
generic versions so you know what each block does.

### B1. Cut the branch (before the work)

1. ☐ Update `main` and branch off it.
   ```bash
   git checkout main && git pull
   git checkout -b phase-<slice>-<slug>
   ```
2. 🤖 I implement the slice on that branch: code, tests, fixtures, docs, and the
   `[Unreleased]` changelog entry.

### B2. Add / commit / push (after the work)

3. ☐ Stage, commit (Conventional Commits), and push.
   ```bash
   git add -A
   git commit -m "feat(<scope>): <summary>"
   git push -u origin phase-<slice>-<slug>
   ```
   > If I've already committed in the working copy, skip `add`/`commit` and just
   > `git push -u origin phase-<slice>-<slug>`.
4. ☐ Open the PR against `main`.
   ```bash
   gh pr create --base main --head phase-<slice>-<slug> --fill
   ```
5. ☐ **Wait for automated review + CI.** Must be green before merge: `CI` (ruff,
   mypy `--strict`, pytest 3.9–3.13, coverage ≥90%), `Docs` (strict build),
   `Security` (pip-audit, bandit, gitleaks, SBOM), and `API Drift`.
6. 🤖 I address review feedback locally; ☐ you `git push` to update the PR. Repeat
   until approved + green.
7. ☐ **Merge (squash) and delete the branch.**
   ```bash
   gh pr merge phase-<slice>-<slug> --squash --delete-branch
   ```
8. ☐ Start the next slice from **B1** (it will pick up this slice's work from the
   freshly pulled `main`).

---

## C. Per-phase release punch list (after the phase's last slice merges)

Each phase ships a minor release (3.1 … 3.7). From `RELEASING.md`:

1. ☐ Confirm `main` is green and `[Unreleased]` lists everything in the phase.
2. 🤖 I prepare the release commit on a `release/3.x` branch: move `[Unreleased]`
   under a dated `[3.x.0]` heading and set `version` in `pyproject.toml` to
   `3.x.0` (drop any `.devN`).
3. ☐ Push, open the PR (`--base main`), let it go green, squash-merge.
4. ☐ **Tag from the merge commit** — triggers trusted publishing:
   ```bash
   git checkout main && git pull
   git tag -a v3.x.0 -m "viyapy 3.x.0"
   git push origin v3.x.0
   ```
5. ☐ Watch the `Release` run; approve the `pypi` environment if required. Confirm
   the new version on PyPI and that docs redeployed.
6. 🤖 Post-release bump to `3.(x+1).0.dev0` + fresh empty `[Unreleased]`; ☐ you
   push + merge that small PR.

One-time (see `RELEASING.md`): the PyPI trusted-publisher config and the `pypi`
GitHub environment must exist before the first tag.

---

## D. Copy-paste commands for every subphase

Each block below is self-contained: cut the branch off `main`, I do the work where
the comment says, then you add/commit/push and open the PR. Merge each slice before
cutting the next. Commit messages are suggestions — keep them Conventional Commits.

### Phase 5.1 — MAS introspection & validation → release **3.1**
Decided: client-side validation **raises** `ViyaValidationError` on a signature
mismatch (fail fast). Viya rejects mismatched inputs anyway, but only deeper in
the execution chain where the error is harder to debug; raising locally points
straight at the offending field.

```bash
# 5.1a — pagination iterator + mas.list / mas.get
git checkout main && git pull
git checkout -b phase-5.1a-mas-list-pagination
#   … 🤖 implement 5.1a …
git add -A && git commit -m "feat(mas): add pagination iterator and module list/get"
git push -u origin phase-5.1a-mas-list-pagination
gh pr create --base main --head phase-5.1a-mas-list-pagination --fill

# 5.1b — step signatures
git checkout main && git pull
git checkout -b phase-5.1b-mas-signatures
#   … 🤖 implement 5.1b …
git add -A && git commit -m "feat(mas): add step signature retrieval"
git push -u origin phase-5.1b-mas-signatures
gh pr create --base main --head phase-5.1b-mas-signatures --fill

# 5.1c — client-side input validation
git checkout main && git pull
git checkout -b phase-5.1c-mas-client-validation
#   … 🤖 implement 5.1c …
git add -A && git commit -m "feat(mas): add client-side input validation (ViyaValidationError)"
git push -u origin phase-5.1c-mas-client-validation
gh pr create --base main --head phase-5.1c-mas-client-validation --fill

# 5.1d — server-side validation
git checkout main && git pull
git checkout -b phase-5.1d-mas-server-validation
#   … 🤖 implement 5.1d …
git add -A && git commit -m "feat(mas): add server-side validation endpoint"
git push -u origin phase-5.1d-mas-server-validation
gh pr create --base main --head phase-5.1d-mas-server-validation --fill
```
→ then Section C, tag `v3.1.0`.

### Phase 5.2 — MAS execution modes, binary I/O & module mgmt → release **3.2**
Settle first: confirm binary-`b64` fixture shape against the live Viya 4 instance.

```bash
# 5.2a — waitTime sync / fire-and-forget / timeout
git checkout main && git pull
git checkout -b phase-5.2a-mas-wait-modes
#   … 🤖 implement 5.2a …
git add -A && git commit -m "feat(mas): support waitTime sync/async/timeout execution modes"
git push -u origin phase-5.2a-mas-wait-modes
gh pr create --base main --head phase-5.2a-mas-wait-modes --fill

# 5.2b — binary (b64) I/O + execution metadata
git checkout main && git pull
git checkout -b phase-5.2b-mas-binary-metadata
#   … 🤖 implement 5.2b …
git add -A && git commit -m "feat(mas): add binary b64 I/O and execution metadata"
git push -u origin phase-5.2b-mas-binary-metadata
gh pr create --base main --head phase-5.2b-mas-binary-metadata --fill

# 5.2c — module create/update/delete + source
git checkout main && git pull
git checkout -b phase-5.2c-mas-module-crud
#   … 🤖 implement 5.2c …
git add -A && git commit -m "feat(mas): add module CRUD and source retrieval"
git push -u origin phase-5.2c-mas-module-crud
gh pr create --base main --head phase-5.2c-mas-module-crud --fill

# 5.2d — async compile jobs + job poller
git checkout main && git pull
git checkout -b phase-5.2d-mas-compile-jobs
#   … 🤖 implement 5.2d …
git add -A && git commit -m "feat(mas): add async compile jobs and reusable job poller"
git push -u origin phase-5.2d-mas-compile-jobs
gh pr create --base main --head phase-5.2d-mas-compile-jobs --fill
```
→ then Section C, tag `v3.2.0`.

### Phase 5.3 — Decisions read & revisions → release **3.3**
Settle first: none blocking.

```bash
# 5.3a — list decision flows
git checkout main && git pull
git checkout -b phase-5.3a-decisions-list
#   … 🤖 implement 5.3a …
git add -A && git commit -m "feat(decisions): add flow listing"
git push -u origin phase-5.3a-decisions-list
gh pr create --base main --head phase-5.3a-decisions-list --fill

# 5.3b — revisions + revision/lock mixin
git checkout main && git pull
git checkout -b phase-5.3b-decisions-revisions
#   … 🤖 implement 5.3b …
git add -A && git commit -m "feat(decisions): add revisions and reusable revision/lock mixin"
git push -u origin phase-5.3b-decisions-revisions
gh pr create --base main --head phase-5.3b-decisions-revisions --fill

# 5.3c — generated DS2 code / mappedCode
git checkout main && git pull
git checkout -b phase-5.3c-decisions-code
#   … 🤖 implement 5.3c …
git add -A && git commit -m "feat(decisions): add generated code retrieval"
git push -u origin phase-5.3c-decisions-code
gh pr create --base main --head phase-5.3c-decisions-code --fill

# 5.3d — external artifacts
git checkout main && git pull
git checkout -b phase-5.3d-decisions-artifacts
#   … 🤖 implement 5.3d …
git add -A && git commit -m "feat(decisions): add external artifact retrieval"
git push -u origin phase-5.3d-decisions-artifacts
gh pr create --base main --head phase-5.3d-decisions-artifacts --fill
```
→ then Section C, tag `v3.3.0`.

### Phase 5.4 — Decisions authoring → release **3.4**
Settle first: **decision-flow builder scope** (typed objects vs raw JSON).

```bash
# 5.4a — create/update/delete flows
git checkout main && git pull
git checkout -b phase-5.4a-decisions-crud
#   … 🤖 implement 5.4a …
git add -A && git commit -m "feat(decisions): add flow create/update/delete"
git push -u origin phase-5.4a-decisions-crud
gh pr create --base main --head phase-5.4a-decisions-crud --fill

# 5.4b — typed decision-flow builder
git checkout main && git pull
git checkout -b phase-5.4b-decision-flow-builder
#   … 🤖 implement 5.4b …
git add -A && git commit -m "feat(decisions): add typed decision-flow builder"
git push -u origin phase-5.4b-decision-flow-builder
gh pr create --base main --head phase-5.4b-decision-flow-builder --fill

# 5.4c — reusable code files
git checkout main && git pull
git checkout -b phase-5.4c-decisions-code-files
#   … 🤖 implement 5.4c …
git add -A && git commit -m "feat(decisions): add reusable code files"
git push -u origin phase-5.4c-decisions-code-files
gh pr create --base main --head phase-5.4c-decisions-code-files --fill

# 5.4d — revision locking
git checkout main && git pull
git checkout -b phase-5.4d-decisions-revision-lock
#   … 🤖 implement 5.4d …
git add -A && git commit -m "feat(decisions): add revision lock/unlock"
git push -u origin phase-5.4d-decisions-revision-lock
gh pr create --base main --head phase-5.4d-decisions-revision-lock --fill
```
→ then Section C, tag `v3.4.0`.

### Phase 5.5 — Business Rules → release **3.5**
Settle first: none blocking (wire into the 5.4 builder).

```bash
# 5.5a — rulesets read
git checkout main && git pull
git checkout -b phase-5.5a-rulesets-read
#   … 🤖 implement 5.5a …
git add -A && git commit -m "feat(rules): add ruleset read"
git push -u origin phase-5.5a-rulesets-read
gh pr create --base main --head phase-5.5a-rulesets-read --fill

# 5.5b — rulesets write + revisions
git checkout main && git pull
git checkout -b phase-5.5b-rulesets-write
#   … 🤖 implement 5.5b …
git add -A && git commit -m "feat(rules): add ruleset write and revisions"
git push -u origin phase-5.5b-rulesets-write
gh pr create --base main --head phase-5.5b-rulesets-write --fill

# 5.5c — rules CRUD
git checkout main && git pull
git checkout -b phase-5.5c-rules-crud
#   … 🤖 implement 5.5c …
git add -A && git commit -m "feat(rules): add rule CRUD"
git push -u origin phase-5.5c-rules-crud
gh pr create --base main --head phase-5.5c-rules-crud --fill

# 5.5d — builder integration
git checkout main && git pull
git checkout -b phase-5.5d-rules-builder-integration
#   … 🤖 implement 5.5d …
git add -A && git commit -m "feat(rules): integrate rulesets into the flow builder"
git push -u origin phase-5.5d-rules-builder-integration
gh pr create --base main --head phase-5.5d-rules-builder-integration --fill
```
→ then Section C, tag `v3.5.0`.

### Phase 5.6 — Publishing → release **3.6**
Settle first: **confirm exact publish paths on the live deployment, pin in `contracts/`** (before 5.6b).

```bash
# 5.6a — list publishing destinations
git checkout main && git pull
git checkout -b phase-5.6a-publish-destinations
#   … 🤖 implement 5.6a …
git add -A && git commit -m "feat(publishing): add destination listing"
git push -u origin phase-5.6a-publish-destinations
gh pr create --base main --head phase-5.6a-publish-destinations --fill

# 5.6b — publish → maslocal + poll
git checkout main && git pull
git checkout -b phase-5.6b-publish-maslocal
#   … 🤖 implement 5.6b …
git add -A && git commit -m "feat(publishing): publish to maslocal with job polling"
git push -u origin phase-5.6b-publish-maslocal
gh pr create --base main --head phase-5.6b-publish-maslocal --fill

# 5.6c — publish → CAS
git checkout main && git pull
git checkout -b phase-5.6c-publish-cas
#   … 🤖 implement 5.6c …
git add -A && git commit -m "feat(publishing): publish to CAS"
git push -u origin phase-5.6c-publish-cas
gh pr create --base main --head phase-5.6c-publish-cas --fill

# 5.6d — publish status
git checkout main && git pull
git checkout -b phase-5.6d-publish-status
#   … 🤖 implement 5.6d …
git add -A && git commit -m "feat(publishing): add publish status"
git push -u origin phase-5.6d-publish-status
gh pr create --base main --head phase-5.6d-publish-status --fill
```
→ then Section C, tag `v3.6.0`.

### Phase 5.7 — CAS depth & batch scoring → release **3.7**
Settle first: **CAS access strategy** (pure-`requests` REST vs optional `viyapy[cas]`/`swat`) — decide after a spike.

```bash
# 5.7a — caslib / table discovery
git checkout main && git pull
git checkout -b phase-5.7a-cas-discovery
#   … 🤖 implement 5.7a …
git add -A && git commit -m "feat(cas): add caslib and table discovery"
git push -u origin phase-5.7a-cas-discovery
gh pr create --base main --head phase-5.7a-cas-discovery --fill

# 5.7b — load / promote to memory
git checkout main && git pull
git checkout -b phase-5.7b-cas-load-promote
#   … 🤖 implement 5.7b …
git add -A && git commit -m "feat(cas): add table load/promote to memory"
git push -u origin phase-5.7b-cas-load-promote
gh pr create --base main --head phase-5.7b-cas-load-promote --fill

# 5.7c — batch score_table + poll
git checkout main && git pull
git checkout -b phase-5.7c-cas-batch-score
#   … 🤖 implement 5.7c …
git add -A && git commit -m "feat(cas): add batch score_table with job polling"
git push -u origin phase-5.7c-cas-batch-score
gh pr create --base main --head phase-5.7c-cas-batch-score --fill

# 5.7d — result fetch
git checkout main && git pull
git checkout -b phase-5.7d-cas-result-fetch
#   … 🤖 implement 5.7d …
git add -A && git commit -m "feat(cas): add batch result fetch"
git push -u origin phase-5.7d-cas-result-fetch
gh pr create --base main --head phase-5.7d-cas-result-fetch --fill
```
→ then Section C, tag `v3.7.0`. This caps the "fully featured" goal.

---

## E. Cross-cutting reminders (apply to every slice)

- Every PR carries a `CHANGELOG.md` `[Unreleased]` entry, updated docs, and tests
  for any behavior change (per `CONTRIBUTING.md`).
- Grow `contracts/*.yaml` and `tests/fixtures/<generation>/` as new endpoints are
  added, so the API-drift gate keeps covering the surface. Keep Viya 3.5 vs Viya 4
  shapes distinct (notably MAS `output` vs `outputs`).
- Merge each slice to `main` before cutting the next, so later slices build on the
  earlier work (each branch is cut from a freshly pulled `main`).
- Live/integration tests stay opt-in: the Viya 4 tier runs against your instance
  (`VIYAPY_TEST_4_*`); the 3.5 tier stays a skipped scaffold until an instance
  exists.
- Public docs run `strict: true` — any new `docs/*.md` page must be added to the
  `mkdocs.yml` nav, or the `Docs` check fails.
