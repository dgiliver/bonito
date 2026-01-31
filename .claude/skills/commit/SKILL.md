---
name: commit
description: Create a well-formatted git commit with proper conventional commit message
allowed-tools: Bash, Read, Grep
---

# Git Commit Skill

Create a commit for staged changes with a proper conventional commit message.

## Steps

1. Check current git status:
   ```bash
   git status
   ```

2. Review the diff of staged changes:
   ```bash
   git diff --cached
   ```

3. If no staged changes, stage relevant files:
   ```bash
   git add <specific files>
   ```

4. Run pre-commit hooks to verify quality:
   ```bash
   make pre-commit
   ```

5. Create commit with conventional message format:
   ```bash
   git commit -m "$(cat <<'EOF'
   <type>: <description>

   <optional body explaining what and why>

   Co-Authored-By: Claude <noreply@anthropic.com>
   EOF
   )"
   ```

## Commit Types
- `feat:` - New feature
- `fix:` - Bug fix
- `refactor:` - Code refactoring (no behavior change)
- `docs:` - Documentation only
- `test:` - Adding/updating tests
- `chore:` - Build process, dependencies
- `style:` - Formatting, whitespace

## Rules
- Keep subject line under 72 characters
- Use imperative mood: "Add feature" not "Added feature"
- Don't commit .env files or secrets
- Run tests before committing if changes affect core logic
