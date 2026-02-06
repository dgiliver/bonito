---
name: trading-security-audit
description: Audit trading code for credential security issues and potential leaks.
allowed-tools: Read, Grep, Glob, Bash
---

# Trading Security Audit Skill

Audit the trading module for security vulnerabilities.

## Usage
```bash
/trading-security-audit              # Full audit
/trading-security-audit --quick      # Quick check
/trading-security-audit --fix        # Audit and suggest fixes
```

## Audit Checklist

### 1. Check for Exposed Credentials
```bash
# Search for raw API key usage
grep -r "api_key" src/bonito/trading/ --include="*.py" | grep -v "SecretStr"

# Search for secret exposure
grep -r "secret" src/bonito/trading/ --include="*.py" | grep -v "SecretStr" | grep -v "get_secret_value"

# Check logging statements
grep -r "logger\." src/bonito/trading/ --include="*.py" | grep -E "(api|key|secret|password)"
```

### 2. Check API Responses
```bash
# Ensure responses don't include secrets
grep -r "return\|response" src/bonito/api/routes/trading.py | grep -v "preview\|redacted"
```

### 3. Check Frontend
```bash
# Ensure no localStorage for credentials
grep -r "localStorage" web/src/ --include="*.tsx" | grep -E "(api|key|secret)"

# Ensure password inputs
grep -r "type=" web/src/components/trading/ --include="*.tsx" | grep "input"
```

### 4. Run Security Tests
```bash
pytest tests/test_credential_security.py -v
```

## Report Format

```markdown
## Trading Security Audit Report

**Date**: YYYY-MM-DD
**Auditor**: security-auditor agent

### Summary
- [ ] No credential leaks in code
- [ ] No credentials in logs
- [ ] No credentials in API responses
- [ ] Frontend uses password inputs
- [ ] No browser storage of credentials

### Issues Found
[List any issues]

### Recommendations
[List recommendations]
```
