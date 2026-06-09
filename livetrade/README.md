# Live Trading State

Persistent state for the Robinhood option-A pipeline (`bonito live ...`).
This directory is **committed to git on purpose** — Claude sessions run in
ephemeral containers, so the ledger only survives between daily runs by
being pushed to the repo.

| File | Purpose |
|------|---------|
| `paper_ledger.json` | Paper account: cash, open positions, fills, realized P&L |
| `live_ledger.json` | Same bookkeeping for live mode (created when mode flips; never shared with paper) |
| `intents/*.json` | Timestamped trade intents from each run (audit trail; in live mode these are the ONLY orders a session may place) |

Every fill ever executed stays in the ledger's `fills` array (positions are
tagged with the strategy that opened them), and `bonito live reconcile`
verifies the ledger against actual broker positions before live sessions
trade — see the `/robinhood-trade` skill.

Configuration lives in `config/universe.json` (symbols, risk caps, mode).
The session runbook is `.claude/skills/robinhood-trade/SKILL.md`.

To reset the paper account:

```bash
rm livetrade/paper_ledger.json
python -c "from bonito.trading.paper import PaperLedger; PaperLedger.load_or_create(starting_cash=150.0).save()"
```
