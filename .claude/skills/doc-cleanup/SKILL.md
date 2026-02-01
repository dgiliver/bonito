---
name: doc-cleanup
description: Consolidate, update, and clean up project documentation. Use when docs are stale, redundant, or need reorganization.
allowed-tools: Read, Write, Edit, Bash, Grep, Glob
---

# Documentation Cleanup Skill

Audit, consolidate, and refresh project documentation.

## Usage

```bash
/doc-cleanup              # Full audit and cleanup
/doc-cleanup --audit      # Audit only (no changes)
/doc-cleanup --readme     # Focus on README.md
/doc-cleanup --consolidate # Merge redundant docs
```

## Documentation Audit Protocol

### 1. Inventory All Docs
```bash
# Find all markdown files
find . -name "*.md" -not -path "./node_modules/*" -not -path "./.git/*" | head -50

# Check last modified dates
ls -lt docs/*.md | head -20
```

### 2. Check for Staleness
For each doc, verify:
- [ ] Version numbers match current release
- [ ] Features described actually exist
- [ ] Code examples run successfully
- [ ] Links are not broken
- [ ] No references to removed features

### 3. Identify Redundancy
Common redundancy patterns:
- ARCHITECTURE.md vs ARCHITECTURE_V2.md
- README.md vs docs/GETTING_STARTED.md
- Multiple roadmap files
- Repeated explanations across docs

### 4. Prioritize Cleanup
| Priority | Criteria |
|----------|----------|
| P0 | User-facing, outdated, actively misleading |
| P1 | Developer docs, missing critical info |
| P2 | Internal docs, minor inaccuracies |
| P3 | Nice-to-have improvements |

## Consolidation Rules

### When to Merge
- Two docs covering same topic at same depth
- One doc is clearly superset of another
- Maintaining both creates sync burden

### When to Keep Separate
- Different audiences (user vs developer)
- Different purposes (tutorial vs reference)
- Content naturally belongs in different contexts

### Merge Process
```
1. Read both documents fully
2. Create outline combining unique content
3. Write merged document
4. Preserve the better-written sections
5. Add note to deprecated doc pointing to new location
6. Update all cross-references
```

## Bonito-Specific Cleanup Tasks

### Consolidate Architecture Docs
```
ARCHITECTURE.md + ARCHITECTURE_V2.md → ARCHITECTURE.md
- Keep V2 content (more comprehensive)
- Remove V1-only content if outdated
- Update version references to current
```

### Clean Up Plans
```
HIGH_PRIORITY_PLAN.md → Check completed items, archive done features
MVP_ROADMAP.md → Update to reflect post-MVP state
LAUNCH_PLAN.md → Verify still actionable
```

### Archive Historical Docs
```
PHASE_0_TESTING_GUIDE.md → Move to docs/archive/ or delete
Any doc referencing only completed phases → Archive
```

### Update README.md
```
- Verify quick start actually works
- Update example session if APIs changed
- Check all links are valid
- Remove references to planned features if implemented
```

### Create Missing Docs
```
CONTRIBUTING.md - How to contribute (missing)
docs/CLI.md - CLI reference (missing)
docs/API.md - REST API reference (minimal)
```

## Quality Standards

### README.md
- Under 500 lines
- Quick start works in <5 minutes
- No broken links
- Updated installation instructions

### Architecture Docs
- Diagrams match current implementation
- No "TODO" or "planned" for shipped features
- Clear separation of current vs future

### API Documentation
- All endpoints documented
- Request/response examples
- Error codes explained

## Cleanup Checklist

```markdown
## Documentation Cleanup Report

**Date**: [YYYY-MM-DD]
**Scope**: [full/partial]

### Inventory
- Total docs found: [N]
- Current: [N]
- Stale: [N]
- Redundant: [N]

### Actions Taken
- [ ] Consolidated: [list files merged]
- [ ] Updated: [list files refreshed]
- [ ] Archived: [list files moved/deleted]
- [ ] Created: [list new files]

### Remaining Issues
- [List any deferred cleanup]

### Recommendations
- [Future maintenance suggestions]
```

## Automation

### Pre-commit Doc Check
```bash
# Add to pre-commit hooks
- Check for broken internal links
- Verify code blocks have language tags
- Check for TODO/FIXME in user docs
```

### Scheduled Audit
```bash
# Monthly documentation review
/doc-cleanup --audit
# Review report, prioritize fixes
```

## Integration with Development

### Feature Development
```
1. Before implementing: Check docs for related content
2. During implementation: Note what docs need updating
3. After implementation: Update docs in same PR
4. Review: Verify docs match implementation
```

### Release Process
```
1. Update CHANGELOG.md
2. Update version numbers in all docs
3. Review README.md quick start
4. Archive completed roadmap items
```
