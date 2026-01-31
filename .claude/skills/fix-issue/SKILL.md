---
name: fix-issue
description: Fix a GitHub issue following project conventions
allowed-tools: Bash, Read, Grep, Glob, Edit, Write
---

# Fix Issue Skill

Fix GitHub issue $ARGUMENTS following Bonito project conventions.

## Steps

1. **Read the issue**
   ```bash
   gh issue view $ARGUMENTS
   ```

2. **Understand the context**
   - Search for related code
   - Read relevant files
   - Check existing tests

3. **Plan the fix**
   - Identify root cause
   - Consider edge cases
   - Think about backward compatibility

4. **Implement the fix**
   - Make minimal changes
   - Follow code style (Python: ruff, TS: eslint)
   - Add/update tests if needed

5. **Verify the fix**
   ```bash
   make test-fast          # Quick tests
   make lint               # Linting
   make typecheck          # Type checking
   ```

6. **Create commit**
   ```bash
   git add <files>
   git commit -m "$(cat <<'EOF'
   fix: <description of fix>

   Fixes #$ARGUMENTS

   Co-Authored-By: Claude <noreply@anthropic.com>
   EOF
   )"
   ```

## Guidelines

- Keep changes focused on the issue
- Don't refactor unrelated code
- Update documentation if behavior changes
- Add regression test for bugs
