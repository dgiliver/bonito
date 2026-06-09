# Live Trading State

Persistent state for the Robinhood option-A pipeline (`bonito live ...`).
This directory is **committed to git on purpose** — Claude sessions run in
ephemeral containers, so the ledger only survives between daily runs by
being pushed to the repo.

| File | Purpose |
|------|---------|
| `paper_ledger.json` | Paper account: cash, open positions, fills, realized P&L |
| `intents/*.json` | Timestamped trade intents from each run (audit trail; in live mode these are the ONLY orders a session may place) |

Configuration lives in `config/universe.json` (symbols, risk caps, mode).
The session runbook is `.claude/skills/robinhood-trade/SKILL.md`.

To reset the paper account:

```bash
rm livetrade/paper_ledger.json
python -c "from bonito.trading.paper import PaperLedger; PaperLedger.load_or_create(starting_cash=150.0).save()"
```
