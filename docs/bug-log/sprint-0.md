# Sprint 0 — Bug Log

Sprint 0 covers environment setup: Python virtual environment, Node.js, Git, VS Code, and initial project scaffolding.

---

## Bug 0.1 — PowerShell execution policy blocks venv activation

- **Date:** 2026-03-01
- **Task:** 0.1 (environment setup)
- **Severity:** Blocker
- **Symptom:** Running `.\venv\Scripts\Activate.ps1` in PowerShell produced:

  ```
  .\venv\Scripts\Activate.ps1 cannot be loaded because running scripts is disabled on this system.
  ```

- **Root Cause:** Windows PowerShell's default execution policy is `Restricted`, which prevents any local scripts (including virtualenv activation scripts) from running.
- **Fix:** Set the execution policy to allow locally-created scripts:

  ```powershell
  Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
  ```

  `RemoteSigned` allows local scripts to run while still requiring remote scripts to be signed. The `-Scope CurrentUser` flag avoids needing admin privileges.

- **Prevention:** Document this as a one-time setup step in the project README for any new developer on a Windows machine. It only needs to be run once per user account.
- **Files changed:** None (system configuration change)
- **Related bugs:** —

---

## Bug 0.2 — Node.js not recognized in VS Code terminal after installation

- **Date:** 2026-03-01
- **Task:** 0.1 (environment setup)
- **Severity:** Blocker
- **Symptom:** After installing Node.js, running `node -v` or `npm -v` in the VS Code integrated terminal returned:

  ```
  node: The term 'node' is not recognized as the name of a cmdlet, function, script file, or operable program.
  ```

  Running the same command in a standalone PowerShell window (opened after installation) worked fine.

- **Root Cause:** VS Code reads the system `PATH` once when it launches. Node.js appends itself to `PATH` during installation, but any VS Code session that was already open when Node was installed does not see the updated `PATH`.
- **Fix:** Close VS Code completely and reopen it. The new terminal session inherits the updated `PATH` and `node`/`npm` are recognized.
- **Prevention:** Install all required CLI tools (Node.js, Python, Git, etc.) before opening VS Code. If a tool must be installed mid-session, restart VS Code before continuing.
- **Files changed:** None
- **Related bugs:** —

---

## Bug 0.3 — Git push rejected — remote already has content (GitHub default README)

- **Date:** 2026-03-01
- **Task:** 0.2 (repository setup)
- **Severity:** Blocker
- **Symptom:** `git push -u origin main` failed with:

  ```
  error: failed to push some refs to 'https://github.com/...'
  hint: Updates were rejected because the remote contains work that you do not have locally.
  ```

  GitHub had auto-created a `README.md` when the repository was initialized through the GitHub UI, causing a diverged history.

- **Root Cause:** The GitHub repository was created with "Initialize this repository with a README" checked. This created an initial commit on the remote that was not in the local git history, making the histories incompatible for a fast-forward push.
- **Fix:** Force-push to overwrite the remote's initial commit with the local project:

  ```bash
  git remote add origin https://github.com/<org>/<repo>.git
  git branch -M main
  git push -u origin main --force
  ```

  `--force` is safe here because the remote content (a GitHub-generated README) has no value that needs preserving.

- **Prevention:** When creating a GitHub repository that will be pushed to from an existing local project, leave all initialization options unchecked (no README, no .gitignore, no license). An empty remote has no diverged history.
- **Files changed:** None (git configuration)
- **Related bugs:** —

---
