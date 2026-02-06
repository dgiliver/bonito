---
name: link-alpaca
description: Securely link an Alpaca paper or live trading account.
allowed-tools: Read, Bash
---

# Link Alpaca Account Skill

Securely connect your Alpaca trading account to Bonito.

## Usage
```bash
/link-alpaca              # Interactive linking
/link-alpaca --paper      # Link paper account
/link-alpaca --live       # Link live account
```

## Prerequisites

1. **Get Alpaca API Keys**
   - Go to https://app.alpaca.markets/
   - Navigate to API Keys
   - Generate Paper Trading keys (or Live if ready)

2. **Verify Keys Format**
   - API Key: Starts with `PK` (paper) or `AK` (live), 20 chars
   - Secret Key: 40 characters

## Linking Flow

```
1. User provides API key + Secret key
2. Backend validates format (Pydantic)
3. Backend tests against Alpaca API
4. If valid → Encrypt and store
5. Return account info (no secrets)
```

## Security Notes

- **Keys are NEVER stored in browser**
- **Keys are encrypted at rest**
- **Keys are only used on backend**
- **HTTPS required for transmission**

## Verification

```bash
# After linking, verify account
curl http://localhost:8000/api/trading/account

# Expected response:
# {
#   "linked": true,
#   "account_id": "PA1234567890",
#   "account_type": "paper",
#   "buying_power": 100000.00,
#   "api_key_preview": "PK12...AB34"
# }
```

## Unlink Account

```bash
curl -X DELETE http://localhost:8000/api/trading/account/link
```
