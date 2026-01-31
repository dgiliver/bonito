---
name: review
description: Code review current changes before committing. Checks for bugs, style, and best practices.
allowed-tools: Bash, Read, Grep, Glob
---

# Code Review Skill

Review staged or modified changes before committing.

## Usage

```bash
/review              # Review all changes
/review --staged     # Only staged changes
/review <file>       # Specific file
```

## Review Checklist

### 1. Correctness
- [ ] Logic is correct
- [ ] Edge cases handled
- [ ] No off-by-one errors
- [ ] Types are correct

### 2. Security
- [ ] No secrets in code
- [ ] Input validation present
- [ ] No SQL injection
- [ ] No XSS vulnerabilities

### 3. Performance
- [ ] No O(n²) algorithms where O(n) possible
- [ ] NumPy vectorization used
- [ ] No unnecessary allocations in loops

### 4. Style
- [ ] Follows project conventions
- [ ] Names are clear and descriptive
- [ ] No commented-out code
- [ ] No print statements for debugging

### 5. Tests
- [ ] New code has tests
- [ ] Tests are meaningful (not just coverage)
- [ ] Edge cases tested

## Commands

### View Changes
```bash
# All modified files
git status

# Staged diff
git diff --staged

# Unstaged diff
git diff

# Specific file
git diff src/bonito/backtest/engine.py
```

### Run Checks
```bash
# Linting
make lint

# Type checking
make typecheck

# Tests
make test-fast

# All pre-commit
make pre-commit
```

## Common Issues to Flag

### Python
- Using `dict` instead of Pydantic model
- Missing type annotations
- Bare `except:` clause
- Mutable default arguments

### TypeScript
- Using `any` type
- Missing null checks
- Not handling loading/error states
- Memory leaks (missing cleanup)

### Both
- Magic numbers without constants
- Long functions (>50 lines)
- Deep nesting (>3 levels)
- Duplicate code

## Review Output Format

```
## Summary
[1-2 sentence overview]

## Issues Found
### Critical
- [Must fix before merge]

### Warning
- [Should fix, but not blocking]

### Suggestion
- [Nice to have improvements]

## Approval
[ ] Approved
[ ] Approved with suggestions
[ ] Changes requested
```
