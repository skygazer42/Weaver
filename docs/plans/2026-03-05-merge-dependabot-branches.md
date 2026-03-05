# Merge Dependabot Branches Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Merge the remaining `origin/dependabot/*` branches into `main` safely, verify locally (aligned with CI where possible), and push to remote.

**Architecture:** Create an isolated integration worktree/branch from `origin/main`, merge each dependabot branch, resolve conflicts, run verification commands, then fast-forward `main` to the integration branch and push. If direct pushes to `main` are blocked, push the integration branch and open a PR.

**Tech Stack:** git, Python 3.11, pytest, ruff, Node 20, pnpm, Next.js

---

### Task 1: Inventory Branches To Merge

**Files:**
- Modify: none

**Step 1: Fetch and list candidate branches**

Run:
```powershell
git fetch --all --prune
git branch -r | Select-String -Pattern 'origin/dependabot/' | ForEach-Object { $_.ToString().Trim() }
git branch -r --no-merged origin/main
```

Expected: A small list of remaining `origin/dependabot/*` branches not merged into `origin/main`.

### Task 2: Create Isolated Integration Worktree

**Files:**
- Modify: `.gitignore` (only if `.worktrees/` not ignored)

**Step 1: Choose worktree directory**

Run:
```powershell
Test-Path .worktrees
Test-Path worktrees
```

**Step 2: Verify the directory is ignored (project-local only)**

Run:
```powershell
git check-ignore -q .worktrees; echo $LASTEXITCODE
```

Expected: exit code `0` (ignored). If not ignored, add `.worktrees/` to `.gitignore` and commit.

**Step 3: Create the integration worktree**

Run:
```powershell
$branch = "integrate/dependabot-2026-03-05"
git worktree add .worktrees/$branch -b $branch origin/main
```

Expected: new worktree directory at `.worktrees/integrate/dependabot-2026-03-05`.

### Task 3: Merge GitHub Actions Dependabot Branches

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `.github/workflows/benchmark-nightly.yml`

**Step 1: Merge**

Run (inside the worktree):
```powershell
git merge --no-edit origin/dependabot/github_actions/actions/upload-artifact-7
git merge --no-edit origin/dependabot/github_actions/actions/download-artifact-8
```

Expected: merges apply cleanly or produce conflicts in workflow YAMLs that must be resolved.

### Task 4: Merge Python Dependabot Branch

**Files:**
- Modify: `requirements.txt`
- Modify: `requirements-dev.txt`
- Modify: `requirements-optional.txt`

**Step 1: Merge**

Run (inside the worktree):
```powershell
git merge --no-edit origin/dependabot/pip/python-38f07c100e
```

### Task 5: Merge Web Dependabot Branch

**Files:**
- Modify: `web/package.json`
- Modify: `web/pnpm-lock.yaml`

**Step 1: Merge**

Run (inside the worktree):
```powershell
git merge --no-edit origin/dependabot/npm_and_yarn/web/web-ef61703fb9
```

### Task 6: Verification (Evidence Before Claims)

**Files:**
- Modify: none

**Step 1: Python verification (aligned with CI)**

Run:
```powershell
python -m pip install -U pip
pip install -r requirements.txt -r requirements-dev.txt
python -m pip check
python -m compileall -q .
pytest -q
```

Expected: `pip check` reports no broken requirements; `pytest` exits 0.

**Step 2: Frontend verification (aligned with CI, if pnpm available)**

Run:
```powershell
pnpm -C web install --frozen-lockfile
pnpm -C web lint
pnpm -C web build
```

Expected: lint/build exit 0.

### Task 7: Fast-Forward main to Integration Branch and Push

**Files:**
- Modify: none (git metadata only)

**Step 1: Merge integration branch into main**

Run (in the original worktree, where `main` is checked out):
```powershell
git pull --rebase
git merge --ff-only integrate/dependabot-2026-03-05
git push
git status -sb
```

Expected: push succeeds; status shows `main...origin/main` and clean.

**Fallback (if pushing to main is blocked):**

Run:
```powershell
git push -u origin integrate/dependabot-2026-03-05
```

Then open a PR via GitHub UI or `gh pr create` if available.

### Task 8: Cleanup

**Files:**
- Modify: none

**Step 1: Remove integration worktree**

Run:
```powershell
git worktree remove .worktrees/integrate/dependabot-2026-03-05
```

**Step 2: Optional remote branch cleanup**

Only after confirming the changes are in `origin/main`, delete merged dependabot branches:
```powershell
git push origin --delete dependabot/github_actions/actions/upload-artifact-7
git push origin --delete dependabot/github_actions/actions/download-artifact-8
git push origin --delete dependabot/pip/python-38f07c100e
git push origin --delete dependabot/npm_and_yarn/web/web-ef61703fb9
```

