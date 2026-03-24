"""Autonomous strategy research — Karpathy-style mutation loop.

Editable asset: StrategyConfig (JSON DSL)
Scalar metric: Sharpe ratio (on trade-day returns only)
Cycle: ~100ms backtest + LLM mutation

Usage:
    python -m bonito.research.autoresearch_trading --symbol SPY --iterations 1000
"""

import hashlib
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

import anthropic

from bonito.backtest.engine import BacktestEngine
from bonito.backtest.models import BacktestConfig, BacktestResult
from bonito.backtest.strategy import StrategyConfig
from bonito.data.models import BarData
from bonito.data.store import MarketDataStore

logger = logging.getLogger(__name__)

# --- Constants ---

MUTATION_MODEL = "claude-sonnet-4-20250514"
MUTATIONS_PER_BATCH = 5
MAX_CONSECUTIVE_ERRORS = 10
CONVERGENCE_THRESHOLD = 100  # consecutive no-improvement iterations
HISTORY_FULL_SIZE = 10  # last N mutations with full details
HISTORY_SUMMARY_SIZE = 20  # older N mutations as summaries

DEFAULT_SEED_PATH = Path("strategies/ema_cross_rsi_optimized.json")
DEFAULT_OUTPUT_DIR = Path("research_output")

# Kill filter thresholds
MIN_TRADES = 30
MAX_DRAWDOWN = 0.25
MAX_INDICATORS = 3
MAX_SHARPE = 3.0  # Overfitting ceiling

# Train/validation split dates
TRAIN_END = "2023-12-31"
VAL_END = "2024-12-31"
# Holdout: 2025+ (never touched by loop)


def load_seed_strategy(seed_path: Path | None, output_dir: Path) -> StrategyConfig:
    """Load seed strategy: resume from best, use --seed, or fall back to default.

    Handles the wrapper format: {"id": ..., "config": {...}} by unwrapping.
    """
    # Priority 1: Resume from previous best
    best_path = output_dir / "best_strategy.json"
    if best_path.exists():
        logger.info("Resuming from previous best: %s", best_path)
        with open(best_path) as f:
            data = json.load(f)
        return StrategyConfig(**data)

    # Priority 2: Explicit seed
    path = seed_path or DEFAULT_SEED_PATH
    if not path.exists():
        raise FileNotFoundError(f"Seed strategy not found: {path}")

    logger.info("Loading seed strategy: %s", path)
    with open(path) as f:
        data = json.load(f)

    # Unwrap {"config": {...}} wrapper if present
    if "config" in data and isinstance(data["config"], dict):
        data = data["config"]

    return StrategyConfig(**data)


def split_data(
    data: BarData,
    train_end: str = TRAIN_END,
    val_end: str = VAL_END,
) -> tuple[BarData, BarData]:
    """Split BarData into train and validation sets by date.

    Returns:
        (train_data, val_data). Holdout (2025+) is excluded entirely.
    """
    train_cutoff = datetime.strptime(train_end, "%Y-%m-%d")
    val_cutoff = datetime.strptime(val_end, "%Y-%m-%d")

    train_indices = [i for i, t in enumerate(data.timestamps) if t <= train_cutoff]
    val_indices = [i for i, t in enumerate(data.timestamps) if train_cutoff < t <= val_cutoff]

    if not train_indices:
        raise ValueError(f"No training data before {train_end}")
    if not val_indices:
        raise ValueError(f"No validation data between {train_end} and {val_end}")

    train_data = data.slice(train_indices[0], train_indices[-1] + 1)
    val_data = data.slice(val_indices[0], val_indices[-1] + 1)

    logger.info(
        "Data split: train=%d bars (%s to %s), val=%d bars (%s to %s)",
        len(train_data),
        train_data.timestamps[0].strftime("%Y-%m-%d"),
        train_data.timestamps[-1].strftime("%Y-%m-%d"),
        len(val_data),
        val_data.timestamps[0].strftime("%Y-%m-%d"),
        val_data.timestamps[-1].strftime("%Y-%m-%d"),
    )

    return train_data, val_data


def validate_no_lookahead(strategy: StrategyConfig, data_length: int) -> str | None:
    """Reject strategies with future-looking parameters.

    Returns error message if invalid, None if OK.
    """
    for ind in strategy.indicators:
        period = ind.params.get("period") or ind.params.get("length") or 0
        if period > data_length:
            return f"Indicator {ind.name} period {period} > data length {data_length}"

    for rule in strategy.entry_rules + strategy.exit_rules:
        for cond in rule.conditions:
            if cond.lookback and cond.lookback > data_length:
                return f"Lookback {cond.lookback} > data length {data_length}"

    return None


def apply_kill_filters(result: BacktestResult, strategy: StrategyConfig) -> str | None:
    """Apply kill filters to reject bad strategies.

    Returns rejection reason (string) or None if strategy passes.
    """
    m = result.metrics

    if m.total_trades < MIN_TRADES:
        return f"too_few_trades ({m.total_trades} < {MIN_TRADES})"
    if m.max_drawdown > MAX_DRAWDOWN:
        return f"excessive_drawdown ({m.max_drawdown:.1%} > {MAX_DRAWDOWN:.0%})"
    if len(strategy.indicators) > MAX_INDICATORS:
        return f"too_many_indicators ({len(strategy.indicators)} > {MAX_INDICATORS})"
    if m.sharpe_ratio > MAX_SHARPE:
        return f"suspiciously_high_sharpe ({m.sharpe_ratio:.2f} > {MAX_SHARPE})"

    return None


def strategy_hash(strategy: StrategyConfig) -> str:
    """Generate a short hash for a strategy config."""
    config_str = strategy.model_dump_json(exclude={"name", "description", "version"})
    return hashlib.sha256(config_str.encode()).hexdigest()[:12]


def build_system_prompt(schema: dict, n_mutations: int = MUTATIONS_PER_BATCH) -> str:
    """Build the system prompt for the LLM mutation API call."""
    return f"""You are a quantitative trading strategy researcher. Your job is to propose \
mutations to a trading strategy to improve its risk-adjusted returns (Sharpe ratio).

## Rules
1. Generate EXACTLY {n_mutations} mutations. Each mutation changes ONE thing from the current best strategy.
2. Stay within 3 indicators maximum.
3. NEVER use future information: no conditions on future bars, no lookahead periods exceeding available history.
4. Each mutation must be meaningfully different from the others and from the history provided.
5. Valid indicator types: sma, ema, rsi, macd, atr, bbands, stoch, adx, cci, mom, roc, willr, obv, cmf, mfi, vwap, trix, tsi, ppo, dema, tema, hma, kama, wma, zlma, supertrend, psar, donchian, kc, natr, stochrsi, ao, fisher, rvi
6. Valid comparisons: gt, gte, lt, lte, eq, crosses_above, crosses_below, was_above, was_below, crossed_above_within, crossed_below_within
7. Valid stop loss types: percent, trailing_percent, trailing_atr, atr, breakeven, fixed
8. Valid position size types: percent_equity, fixed_value, fixed_quantity

## Strategy JSON Schema
```json
{json.dumps(schema, indent=2)}
```

## Output Format
Return valid JSON only, no markdown fences:
{{"mutations": [{{"strategy": {{...full StrategyConfig...}}, "description": "Changed X from Y to Z"}}, ...]}}
"""


def build_user_prompt(
    current: StrategyConfig,
    train_sharpe: float,
    val_sharpe: float,
    train_result: BacktestResult,
    history: list[dict],
) -> str:
    """Build the user prompt with current state and mutation history."""
    m = train_result.metrics

    # Format history
    history_lines = []
    for i, h in enumerate(history):
        if i < HISTORY_FULL_SIZE:
            history_lines.append(
                f"  {h['iteration']}: {h['description']} → "
                f"train_sharpe={h['train_sharpe']:.2f}, "
                f"val_sharpe={h.get('val_sharpe', 'N/A')}, "
                f"status={h['status']}"
            )
        else:
            # Summarized older entries
            history_lines.append(f"  {h['iteration']}: {h['description']} → {h['status']}")

    history_str = "\n".join(history_lines) if history_lines else "  (none yet)"

    return f"""## Current Best Strategy
```json
{current.model_dump_json(indent=2)}
```

## Current Performance
- Train Sharpe: {train_sharpe:.3f}
- Validation Sharpe: {val_sharpe:.3f}
- Total Return: {m.total_return:.2%}
- Max Drawdown: {m.max_drawdown:.2%}
- Total Trades: {m.total_trades}
- Win Rate: {m.win_rate:.1%}
- Profit Factor: {m.profit_factor:.2f}

## Recent Mutation History (do NOT repeat these)
{history_str}

Propose {MUTATIONS_PER_BATCH} new mutations. Each should change exactly ONE thing."""


def mutate_strategy_batch(
    client: anthropic.Anthropic,
    current: StrategyConfig,
    train_sharpe: float,
    val_sharpe: float,
    train_result: BacktestResult,
    history: list[dict],
    schema: dict,
) -> list[tuple[StrategyConfig, str]]:
    """Request N mutations in one API call.

    Returns list of (StrategyConfig, description) tuples.
    """
    response = client.messages.create(
        model=MUTATION_MODEL,
        max_tokens=4096,
        system=build_system_prompt(schema),
        messages=[
            {
                "role": "user",
                "content": build_user_prompt(
                    current, train_sharpe, val_sharpe, train_result, history
                ),
            }
        ],
    )

    # Extract text content
    text = ""
    for block in response.content:
        if block.type == "text":
            text += block.text

    # Parse JSON (strip markdown fences if present)
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    data = json.loads(text)
    mutations = data.get("mutations", [])

    results = []
    for mut in mutations:
        try:
            strategy = StrategyConfig(**mut["strategy"])
            description = mut.get("description", "unknown mutation")
            results.append((strategy, description))
        except Exception as e:
            logger.warning("Invalid mutation from LLM: %s", e)

    return results


def log_iteration(
    log_file: Path,
    iteration: int,
    description: str,
    train_result: BacktestResult | None,
    val_result: BacktestResult | None,
    indicator_count: int,
    status: str,
    filter_reason: str,
    strat_hash: str,
) -> None:
    """Append a TSV row to the experiment log."""
    ts = datetime.now().isoformat()
    tm = train_result.metrics if train_result else None
    vm = val_result.metrics if val_result else None

    row = "\t".join(
        [
            str(iteration),
            ts,
            description.replace("\t", " "),
            f"{tm.sharpe_ratio:.4f}" if tm else "",
            f"{vm.sharpe_ratio:.4f}" if vm else "",
            f"{tm.total_return:.4f}" if tm else "",
            f"{vm.total_return:.4f}" if vm else "",
            f"{tm.max_drawdown:.4f}" if tm else "",
            str(tm.total_trades) if tm else "",
            f"{tm.win_rate:.4f}" if tm else "",
            f"{tm.profit_factor:.4f}" if tm else "",
            str(indicator_count),
            status,
            filter_reason,
            strat_hash,
        ]
    )

    with open(log_file, "a") as f:
        f.write(row + "\n")


def save_best(
    output_dir: Path,
    strategy: StrategyConfig,
    train_result: BacktestResult,
    val_result: BacktestResult,
) -> None:
    """Save best strategy and both result sets."""
    with open(output_dir / "best_strategy.json", "w") as f:
        f.write(strategy.model_dump_json(indent=2))

    train_metrics = {
        "sharpe_ratio": train_result.metrics.sharpe_ratio,
        "total_return": train_result.metrics.total_return,
        "max_drawdown": train_result.metrics.max_drawdown,
        "total_trades": train_result.metrics.total_trades,
        "win_rate": train_result.metrics.win_rate,
        "profit_factor": train_result.metrics.profit_factor,
    }
    with open(output_dir / "best_train_result.json", "w") as f:
        json.dump(train_metrics, f, indent=2)

    val_metrics = {
        "sharpe_ratio": val_result.metrics.sharpe_ratio,
        "total_return": val_result.metrics.total_return,
        "max_drawdown": val_result.metrics.max_drawdown,
        "total_trades": val_result.metrics.total_trades,
        "win_rate": val_result.metrics.win_rate,
        "profit_factor": val_result.metrics.profit_factor,
    }
    with open(output_dir / "best_val_result.json", "w") as f:
        json.dump(val_metrics, f, indent=2)


def write_summary(
    output_dir: Path,
    symbol: str,
    total_iterations: int,
    best_train_sharpe: float,
    best_val_sharpe: float,
    strategies_tested: int,
    strategies_passing: int,
    elapsed_seconds: float,
) -> None:
    """Write a markdown summary of the research run."""
    summary = f"""# Research Run Summary

- **Date**: {datetime.now().strftime("%Y-%m-%d %H:%M")}
- **Symbol**: {symbol}
- **Iterations**: {total_iterations}
- **Elapsed**: {elapsed_seconds / 60:.1f} minutes
- **Best Train Sharpe**: {best_train_sharpe:.3f}
- **Best Validation Sharpe**: {best_val_sharpe:.3f}
- **Strategies Tested**: {strategies_tested}
- **Strategies Passing Filters**: {strategies_passing}
- **Pass Rate**: {strategies_passing / max(strategies_tested, 1):.1%}
"""
    with open(output_dir / "summary.md", "w") as f:
        f.write(summary)


def run(
    symbol: str = "SPY",
    iterations: int = 1000,
    seed_path: Path | None = None,
    output_dir: Path | None = None,
    start_date: str = "2020-01-01",
    end_date: str = "2025-03-20",
) -> None:
    """Run the autonomous strategy research loop.

    Args:
        symbol: Symbol to backtest on
        iterations: Maximum number of mutation iterations
        seed_path: Path to seed strategy JSON (optional)
        output_dir: Output directory for results
        start_date: Data start date
        end_date: Data end date
    """
    start_time = time.time()

    # Setup output directory
    if output_dir is None:
        output_dir = DEFAULT_OUTPUT_DIR / datetime.now().strftime("%Y-%m-%d")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(output_dir / "research.log"),
        ],
    )

    logger.info("=== Autonomous Strategy Research ===")
    logger.info("Symbol: %s | Iterations: %d", symbol, iterations)

    # Initialize TSV log with headers
    log_file = output_dir / "experiment_log.tsv"
    if not log_file.exists():
        headers = "\t".join(
            [
                "iteration",
                "timestamp",
                "mutation_description",
                "train_sharpe",
                "val_sharpe",
                "train_return",
                "val_return",
                "max_drawdown",
                "total_trades",
                "win_rate",
                "profit_factor",
                "indicator_count",
                "status",
                "filter_reason",
                "strategy_hash",
            ]
        )
        with open(log_file, "w") as f:
            f.write(headers + "\n")

    # Load data
    store = MarketDataStore()
    s = datetime.strptime(start_date, "%Y-%m-%d")
    e = datetime.strptime(end_date, "%Y-%m-%d")
    data = store.get_bars(symbol, s, e, "1d")
    store.close()

    if data is None:
        logger.error(
            "No data found for %s. Run: bonito ingest %s --start %s --end %s",
            symbol,
            symbol,
            start_date,
            end_date,
        )
        sys.exit(1)

    logger.info("Loaded %d bars for %s", len(data), symbol)

    # Split into train/validation
    train_data, val_data = split_data(data)

    # Load seed strategy
    current = load_seed_strategy(seed_path, output_dir)
    # Ensure symbol matches
    current = current.model_copy(update={"symbols": [symbol]})

    logger.info("Seed strategy: %s (%d indicators)", current.name, len(current.indicators))

    # Initialize backtest engine
    engine = BacktestEngine(
        BacktestConfig(
            start_date=s,
            end_date=e,
        )
    )

    # Baseline backtest on seed
    train_result = engine.run(current, train_data)
    val_result = engine.run(current, val_data)
    best_train_sharpe = train_result.metrics.sharpe_ratio
    best_val_sharpe = val_result.metrics.sharpe_ratio
    best_strategy = current
    best_train_result = train_result

    logger.info(
        "Seed performance: train_sharpe=%.3f, val_sharpe=%.3f, trades=%d",
        best_train_sharpe,
        best_val_sharpe,
        train_result.metrics.total_trades,
    )

    # Save initial best
    save_best(output_dir, current, train_result, val_result)

    # Initialize Anthropic client — load key from .env (override empty shell vars)
    import os

    from dotenv import dotenv_values

    api_key = os.environ.get("ANTHROPIC_API_KEY") or ""
    if not api_key:
        # Shell may have ANTHROPIC_API_KEY="" (e.g., Claude Code sandbox).
        # Fall back to reading .env directly.
        env_vals = dotenv_values(".env")
        api_key = env_vals.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        logger.error("ANTHROPIC_API_KEY not set. Add to .env or environment.")
        sys.exit(1)
    client = anthropic.Anthropic(api_key=api_key)
    schema = StrategyConfig.model_json_schema()

    # Mutation history (most recent first)
    history: list[dict] = []
    consecutive_no_improvement = 0
    consecutive_errors = 0
    total_tested = 0
    total_passing = 0
    iteration = 0

    logger.info("Starting research loop (max %d iterations)...", iterations)

    while iteration < iterations:
        # Check convergence
        if consecutive_no_improvement >= CONVERGENCE_THRESHOLD:
            logger.info(
                "Converged after %d iterations (%d consecutive no-improvement)",
                iteration,
                consecutive_no_improvement,
            )
            break

        # Request batch of mutations
        try:
            # Provide recent history (last 30, newest first)
            recent_history = history[: HISTORY_FULL_SIZE + HISTORY_SUMMARY_SIZE]

            mutations = mutate_strategy_batch(
                client=client,
                current=best_strategy,
                train_sharpe=best_train_sharpe,
                val_sharpe=best_val_sharpe,
                train_result=best_train_result,
                history=recent_history,
                schema=schema,
            )
            consecutive_errors = 0
        except json.JSONDecodeError as e:
            logger.warning("Invalid JSON from LLM (iter %d): %s", iteration, e)
            consecutive_errors += 1
            if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                logger.error("FATAL: %d consecutive errors, aborting", MAX_CONSECUTIVE_ERRORS)
                sys.exit(1)
            iteration += 1
            continue
        except anthropic.RateLimitError:
            logger.warning("Rate limited, backing off...")
            for delay in [1, 2, 4]:
                time.sleep(delay)
                try:
                    mutations = mutate_strategy_batch(
                        client=client,
                        current=best_strategy,
                        train_sharpe=best_train_sharpe,
                        val_sharpe=best_val_sharpe,
                        train_result=best_train_result,
                        history=recent_history,
                        schema=schema,
                    )
                    break
                except anthropic.RateLimitError:
                    continue
            else:
                logger.error("Rate limit persists after retries, aborting")
                sys.exit(1)
            consecutive_errors = 0
        except Exception as e:
            logger.warning("API error (iter %d): %s", iteration, e)
            consecutive_errors += 1
            if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                logger.error("FATAL: %d consecutive errors, aborting", MAX_CONSECUTIVE_ERRORS)
                sys.exit(1)
            iteration += 1
            continue

        if not mutations:
            logger.warning("No valid mutations returned (iter %d)", iteration)
            iteration += 1
            consecutive_no_improvement += 1
            continue

        # Evaluate each mutation
        for strategy, description in mutations:
            iteration += 1
            if iteration > iterations:
                break

            total_tested += 1
            strat_h = strategy_hash(strategy)

            # Validate no lookahead
            lookahead_err = validate_no_lookahead(strategy, len(train_data))
            if lookahead_err:
                logger.debug("Lookahead rejected (iter %d): %s", iteration, lookahead_err)
                log_iteration(
                    log_file,
                    iteration,
                    description,
                    None,
                    None,
                    len(strategy.indicators),
                    "REJECTED",
                    f"lookahead: {lookahead_err}",
                    strat_h,
                )
                history.insert(
                    0,
                    {
                        "iteration": iteration,
                        "description": description,
                        "train_sharpe": 0,
                        "status": "REJECTED",
                    },
                )
                consecutive_no_improvement += 1
                continue

            # Run train backtest
            try:
                train_result = engine.run(strategy, train_data)
            except Exception as e:
                logger.warning("Backtest crash (iter %d): %s", iteration, e)
                log_iteration(
                    log_file,
                    iteration,
                    description,
                    None,
                    None,
                    len(strategy.indicators),
                    "ERROR",
                    str(e)[:100],
                    strat_h,
                )
                history.insert(
                    0,
                    {
                        "iteration": iteration,
                        "description": description,
                        "train_sharpe": 0,
                        "status": "ERROR",
                    },
                )
                consecutive_no_improvement += 1
                continue

            # Apply kill filters on train result
            filter_reason = apply_kill_filters(train_result, strategy)
            if filter_reason:
                logger.debug("Filtered (iter %d): %s", iteration, filter_reason)
                log_iteration(
                    log_file,
                    iteration,
                    description,
                    train_result,
                    None,
                    len(strategy.indicators),
                    "FILTERED",
                    filter_reason,
                    strat_h,
                )
                history.insert(
                    0,
                    {
                        "iteration": iteration,
                        "description": description,
                        "train_sharpe": train_result.metrics.sharpe_ratio,
                        "status": f"FILTERED: {filter_reason}",
                    },
                )
                consecutive_no_improvement += 1
                continue

            # Run validation backtest
            try:
                val_result = engine.run(strategy, val_data)
            except Exception as e:
                logger.warning("Validation backtest crash (iter %d): %s", iteration, e)
                log_iteration(
                    log_file,
                    iteration,
                    description,
                    train_result,
                    None,
                    len(strategy.indicators),
                    "ERROR",
                    f"val: {str(e)[:80]}",
                    strat_h,
                )
                consecutive_no_improvement += 1
                continue

            train_sharpe = train_result.metrics.sharpe_ratio
            val_sharpe = val_result.metrics.sharpe_ratio

            # Overfit check: validation must retain 50% of train Sharpe
            if train_sharpe > 0 and val_sharpe < train_sharpe * 0.5:
                log_iteration(
                    log_file,
                    iteration,
                    description,
                    train_result,
                    val_result,
                    len(strategy.indicators),
                    "OVERFIT",
                    f"val/train={val_sharpe / train_sharpe:.2f}",
                    strat_h,
                )
                history.insert(
                    0,
                    {
                        "iteration": iteration,
                        "description": description,
                        "train_sharpe": train_sharpe,
                        "val_sharpe": val_sharpe,
                        "status": "OVERFIT",
                    },
                )
                consecutive_no_improvement += 1
                continue

            total_passing += 1

            # Check if this is a new best (by validation Sharpe)
            if val_sharpe > best_val_sharpe:
                improvement = val_sharpe - best_val_sharpe
                logger.info(
                    "NEW BEST (iter %d): val_sharpe %.3f → %.3f (+%.3f) | %s",
                    iteration,
                    best_val_sharpe,
                    val_sharpe,
                    improvement,
                    description,
                )
                best_train_sharpe = train_sharpe
                best_val_sharpe = val_sharpe
                best_strategy = strategy
                best_train_result = train_result

                save_best(output_dir, strategy, train_result, val_result)
                consecutive_no_improvement = 0

                log_iteration(
                    log_file,
                    iteration,
                    description,
                    train_result,
                    val_result,
                    len(strategy.indicators),
                    "BEST",
                    "",
                    strat_h,
                )
                history.insert(
                    0,
                    {
                        "iteration": iteration,
                        "description": description,
                        "train_sharpe": train_sharpe,
                        "val_sharpe": val_sharpe,
                        "status": "BEST",
                    },
                )
            else:
                log_iteration(
                    log_file,
                    iteration,
                    description,
                    train_result,
                    val_result,
                    len(strategy.indicators),
                    "KEPT",
                    "",
                    strat_h,
                )
                history.insert(
                    0,
                    {
                        "iteration": iteration,
                        "description": description,
                        "train_sharpe": train_sharpe,
                        "val_sharpe": val_sharpe,
                        "status": "KEPT",
                    },
                )
                consecutive_no_improvement += 1

            # Trim history
            if len(history) > HISTORY_FULL_SIZE + HISTORY_SUMMARY_SIZE:
                history = history[: HISTORY_FULL_SIZE + HISTORY_SUMMARY_SIZE]

        # Progress log every 50 iterations
        if iteration > 0 and iteration % 50 == 0:
            elapsed = time.time() - start_time
            rate = iteration / elapsed * 60  # iterations per minute
            logger.info(
                "Progress: %d/%d iterations | best_val_sharpe=%.3f | "
                "%.1f iter/min | %d passing / %d tested",
                iteration,
                iterations,
                best_val_sharpe,
                rate,
                total_passing,
                total_tested,
            )

    # Final summary
    elapsed = time.time() - start_time
    logger.info("=== Research Complete ===")
    logger.info("Total iterations: %d", iteration)
    logger.info("Elapsed: %.1f minutes", elapsed / 60)
    logger.info("Best train Sharpe: %.3f", best_train_sharpe)
    logger.info("Best validation Sharpe: %.3f", best_val_sharpe)
    logger.info("Strategies tested: %d", total_tested)
    logger.info("Strategies passing filters: %d", total_passing)

    write_summary(
        output_dir,
        symbol,
        iteration,
        best_train_sharpe,
        best_val_sharpe,
        total_tested,
        total_passing,
        elapsed,
    )

    logger.info("Results saved to: %s", output_dir)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Autonomous strategy research")
    parser.add_argument("--symbol", default="SPY", help="Symbol to research")
    parser.add_argument("--iterations", type=int, default=1000, help="Max iterations")
    parser.add_argument("--seed", type=str, default=None, help="Seed strategy path")
    parser.add_argument("--output-dir", type=str, default=None, help="Output directory")
    parser.add_argument("--start-date", default="2020-01-01", help="Data start date")
    parser.add_argument("--end-date", default="2025-03-20", help="Data end date")

    args = parser.parse_args()
    run(
        symbol=args.symbol,
        iterations=args.iterations,
        seed_path=Path(args.seed) if args.seed else None,
        output_dir=Path(args.output_dir) if args.output_dir else None,
        start_date=args.start_date,
        end_date=args.end_date,
    )
