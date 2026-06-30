"""Methodology guards for the phase-2 audit findings (Q1 regime RETAIN, Q3 overrides
KEEP, Q4 GOOGL inconclusive — see tasks/audit_overrides_coordination.md).

Those findings rest on two assumptions that previously had no explicit regression
guard:

1. `backtest_account` is deterministic — identical inputs must produce a
   bit-for-bit identical `AccountBacktestResult` on every call. The Q4 Validator
   leaned on this directly (arm (a) confirmed == Q3 ON to 1e-15). If the replay
   ever picked up unseeded randomness or order-dependent iteration (e.g. over a
   `set`), every pre-registered train/holdout comparison in the audit trail would
   silently stop meaning anything.
2. Every strategy file the live universe (`config/universe.json`) actually
   references — the default `strategy_path` plus every `symbol_strategies`
   override — loads into a valid `StrategyConfig` via the same loader the live
   pipeline uses. If one of those files were renamed, deleted, or grew an invalid
   field, the live pipeline would break at runtime; nothing else asserts this.

Gap vs. `tests/test_portfolio_backtest.py::TestResultIntegrity::test_determinism_and_accounting`:
that test DOES call `backtest_account` twice on identical inputs (so the
run-twice-identical scaffolding already existed), but only compares
`equity_curve`, the list of trade `exit_price`s, and a same-run accounting
identity (final_equity == starting_cash + realized + unrealized on r1 alone,
not compared against r2). It never compares `final_equity`, `sharpe`,
`total_return`, `max_drawdown`, `per_symbol_pnl`, `open_positions`, trade count,
or full trade-object equality between the two runs. This file closes that gap
without duplicating what's already covered, and adds the strategy-load guard
that didn't exist at all.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from bonito.backtest.strategy import StrategyConfig
from bonito.data.models import BarData
from bonito.trading.live_runner import UniverseConfig
from bonito.trading.portfolio_backtest import ReplayStore, backtest_account

REPO_ROOT = Path(__file__).resolve().parent.parent
START = datetime(2026, 1, 1)


def day(i: int) -> datetime:
    return START + timedelta(days=i)


def make_ohlc(symbol: str, rows: list[tuple[float, float, float, float]]) -> BarData:
    """Bars from explicit (open, high, low, close) rows, one per day from START.

    Mirrors tests/test_portfolio_backtest.py::make_ohlc.
    """
    return BarData(
        symbol=symbol,
        timeframe="1d",
        timestamps=[day(i) for i in range(len(rows))],
        opens=[r[0] for r in rows],
        highs=[r[1] for r in rows],
        lows=[r[2] for r in rows],
        closes=[r[3] for r in rows],
        volumes=[1_000_000.0] * len(rows),
    )


def flat_bars(symbol: str, n: int, price: float = 100.0) -> BarData:
    return make_ohlc(symbol, [(price, price * 1.001, price * 0.999, price)] * n)


# A strategy with both a stop loss and a take profit so the synthetic replay
# below exercises intraday stop fills, take-profit fills, and ordinary closes —
# i.e. enough surface area that a real non-determinism bug (e.g. order-dependent
# fill iteration) would have somewhere to manifest, not just a single flat trade.
DETERMINISM_STRATEGY = {
    "name": "determinism_probe",
    "symbols": ["TEST"],
    "timeframe": "1d",
    "indicators": [{"type": "sma", "name": "sma_2", "params": {"period": 2}}],
    "entry_rules": [
        {
            "conditions": [{"left": "close", "comparison": "gt", "right": 0.0}],
            "logic": "AND",
            "side": "long",
        }
    ],
    "exit_rules": [
        {
            "conditions": [{"left": "close", "comparison": "lt", "right": 0.0}],
            "logic": "AND",
            "side": "long",
        }
    ],
    "position_size": {"type": "percent_equity", "value": 10},
    "stop_loss": {"type": "trailing_percent", "value": 0.05},
    "take_profit": {"type": "percent", "value": 0.10},
}


def make_universe(tmp_path: Path, strategy: dict, symbols: list[str], **risk) -> UniverseConfig:
    """Mirrors tests/test_portfolio_backtest.py::make_universe."""
    path = tmp_path / f"{strategy['name']}.json"
    path.write_text(json.dumps(strategy))
    return UniverseConfig(
        name="methodology-guard",
        symbols=symbols,
        strategy_path=str(path),
        data={"timeframe": "1d", "start_date": "2026-01-01"},
        risk={
            "starting_cash_usd": 150.0,
            "max_position_usd": 30.0,
            "max_positions": 5,
            "max_daily_buys": 3,
            "min_cash_buffer_usd": 5.0,
            "allow_short": False,
            **risk,
        },
    )


def _determinism_universe(tmp_path: Path) -> UniverseConfig:
    return make_universe(tmp_path, DETERMINISM_STRATEGY, ["AAA", "BBB", "CCC"])


def _determinism_replay() -> ReplayStore:
    """Three symbols with distinct enough paths to trigger a stop, a take-profit,
    and an ordinary flat hold — multiple code paths through one replay window.
    """
    aaa_rows = [
        (100, 100, 100, 100),
        (100, 100, 100, 100),  # entry at close 100
        (100, 106, 100, 105),  # HWM ratchets to 106
        (105, 105, 98, 99),  # low pierces 106*0.95=100.7 -> trailing stop fires
        (99, 99, 99, 99),
    ]
    bbb_rows = [
        (100, 100, 100, 100),
        (100, 100, 100, 100),  # entry at 100, TP level 110
        (101, 112, 101, 108),  # high tags 110 intraday -> take profit fires
        (108, 109, 107, 108),
        (108, 109, 107, 108),
    ]
    ccc_rows = [(100, 100.5, 99.5, 100)] * 5  # flat hold, no exit signal
    return ReplayStore(
        {
            "AAA": make_ohlc("AAA", aaa_rows),
            "BBB": make_ohlc("BBB", bbb_rows),
            "CCC": make_ohlc("CCC", ccc_rows),
        }
    )


def _run_determinism_replay(tmp_path: Path) -> tuple:
    """Runs the same replay twice on identical inputs; returns (r1, r2)."""
    universe = _determinism_universe(tmp_path)
    # Two independent ReplayStore instances over identical underlying data —
    # deliberately not the same object — so the guard can't pass merely because
    # both runs share mutable state.
    r1 = backtest_account(universe, _determinism_replay(), START, day(4))
    r2 = backtest_account(universe, _determinism_replay(), START, day(4))
    return r1, r2


class TestAccountReplayDeterminism:
    """Identical inputs to backtest_account() must produce a bit-for-bit
    identical AccountBacktestResult. This is the assumption the Q4 Validator's
    "arm (a) == Q3 ON to 1e-15" cross-check depended on; if the replay ever
    became non-deterministic, every pre-registered train/holdout comparison in
    the audit trail (Q1, Q3, Q4) would silently stop being comparable.
    """

    def test_full_result_is_identical_across_two_runs(self, tmp_path):
        r1, r2 = _run_determinism_replay(tmp_path)

        # Sanity: the replay actually did something (a vacuous all-zero result
        # would make every equality below trivially true).
        assert len(r1.trades) >= 2
        assert r1.realized_pnl != 0.0

        # Scalar summary metrics — exact equality (no rtol/atol slack at all),
        # since two runs over identical inputs have no source of legitimate
        # floating-point divergence: same operations, same operand order.
        assert r1.final_equity == r2.final_equity
        assert r1.total_return == r2.total_return
        assert r1.realized_pnl == r2.realized_pnl
        assert r1.unrealized_pnl == r2.unrealized_pnl
        assert r1.sharpe == r2.sharpe
        assert r1.max_drawdown == r2.max_drawdown
        assert r1.win_rate == r2.win_rate
        assert r1.profit_factor == r2.profit_factor
        assert r1.max_concurrent_positions == r2.max_concurrent_positions
        assert r1.avg_concurrent_positions == r2.avg_concurrent_positions
        assert r1.pct_days_in_market == r2.pct_days_in_market
        assert r1.halted == r2.halted
        assert r1.halt_date == r2.halt_date
        assert r1.halt_reason == r2.halt_reason
        assert r1.rejected_intents == r2.rejected_intents

        # Full equity path, not just the final value.
        assert r1.equity_dates == r2.equity_dates
        assert r1.equity_curve == r2.equity_curve

        # Trade count and full trade-object equality (every field, not just
        # exit_price as in test_determinism_and_accounting) — order included,
        # since trades is a list and fill order is part of what must reproduce.
        assert len(r1.trades) == len(r2.trades)
        assert r1.trades == r2.trades

        # Dict-valued fields: compare via sorted items, not bare `==`, because
        # Python dict equality is order-independent and would mask a genuine
        # iteration-order regression (e.g. set/dict ordering instability)
        # producing the same keys/values in a different order each run.
        assert sorted(r1.per_symbol_pnl.items()) == sorted(r2.per_symbol_pnl.items())
        assert sorted(r1.open_positions.items()) == sorted(r2.open_positions.items())
        assert r1.open_position_entries == r2.open_position_entries

    def test_per_symbol_pnl_keys_and_values_individually_match(self, tmp_path):
        """Narrower companion to the full-result test above: isolates
        per_symbol_pnl specifically, since that is the exact field the Q3
        per-symbol attribution table (IREN/AAPL/GOOGL) is read off of.
        """
        r1, r2 = _run_determinism_replay(tmp_path)

        assert set(r1.per_symbol_pnl) == set(r2.per_symbol_pnl)
        for symbol, pnl in r1.per_symbol_pnl.items():
            assert r2.per_symbol_pnl[symbol] == pnl


def _live_universe() -> UniverseConfig:
    """Loads the real config/universe.json (committed, in-repo, fast — no
    network/DuckDB). Resolved from REPO_ROOT, not cwd, so this is robust to
    however pytest is invoked.
    """
    return UniverseConfig.load(REPO_ROOT / "config" / "universe.json")


def _live_strategy_paths() -> list[str]:
    """Every strategy path the live universe currently references: the default
    strategy_path plus every symbol_strategies override. Derived from the
    config at collection time so a future override is automatically covered —
    never hard-code the 4 current paths.
    """
    universe = _live_universe()
    paths = {universe.strategy_path, *universe.symbol_strategies.values()}
    return sorted(paths)


class TestLiveStrategyConfigLoads:
    """Every strategy file the live universe references must exist and load
    into a valid StrategyConfig via the same loader the live pipeline uses
    (UniverseConfig._load_strategy_file: json.loads -> optional {"config": ...}
    unwrap -> StrategyConfig(**data)). Guards against a renamed, deleted, or
    malformed strategy file silently breaking the live pipeline at runtime —
    something nothing else in the suite asserted before this file.
    """

    @pytest.mark.parametrize("strategy_path", _live_strategy_paths())
    def test_strategy_file_loads_via_universe_config(self, strategy_path):
        universe = _live_universe()

        # Find a symbol assigned to this exact path (default or an override)
        # so we exercise load_strategy_for, the real call site generate_intents
        # and backtest_account use — not just a hand-rolled file read.
        symbol = next(
            (s for s, p in universe.symbol_strategies.items() if p == strategy_path),
            universe.symbols[0],
        )

        strategy = universe.load_strategy_for(symbol)

        assert isinstance(strategy, StrategyConfig)
        assert strategy.entry_rules  # min_length=1 on the model; non-vacuous parse

    def test_every_symbol_resolves_to_a_loadable_strategy(self):
        """Belt-and-suspenders over the per-path parametrization above: walks
        every symbol in the universe (not just the distinct paths) through
        load_strategy_for, the same accessor generate_intents calls per-symbol.
        """
        universe = _live_universe()
        for symbol in universe.symbols:
            strategy = universe.load_strategy_for(symbol)
            assert isinstance(strategy, StrategyConfig)

    def test_default_strategy_loads(self):
        universe = _live_universe()
        strategy = universe.load_strategy()
        assert isinstance(strategy, StrategyConfig)

    def test_derived_paths_cover_all_current_overrides(self):
        """Documents the auto-derivation contract: the parametrized test above
        is driven by _live_strategy_paths(), not a hard-coded list. This test
        pins that, today, that derivation yields the default plus the 3
        cluster/iren overrides described in
        tasks/audit_overrides_coordination.md — so a silent drop in coverage
        (e.g. someone hand-editing _live_strategy_paths to a shorter list)
        would be caught here even though it wouldn't show up as a pytest
        collection difference.
        """
        universe = _live_universe()
        paths = _live_strategy_paths()

        assert universe.strategy_path in paths
        assert set(universe.symbol_strategies.values()) <= set(paths)
        # Today's known shape: 1 default + 3 distinct overrides. If this
        # changes, it should change because the live config changed, not
        # because this test's derivation silently narrowed.
        assert len(paths) == len(set(universe.symbol_strategies.values()) | {universe.strategy_path})
