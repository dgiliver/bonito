"""Command-line interface for the Bonito agent."""

from datetime import datetime, timedelta
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Prompt
from rich.table import Table

from bonito.logging import setup_logging

app = typer.Typer(
    name="bonito",
    help="AI-native algorithmic trading platform",
    no_args_is_help=True,
)

# Subcommand group for data operations
data_app = typer.Typer(help="Data management commands")
app.add_typer(data_app, name="data")

# Subcommand group for research operations
research_app = typer.Typer(help="Autonomous strategy research")
app.add_typer(research_app, name="research")

# Subcommand group for live trading (Robinhood option-A pipeline)
live_app = typer.Typer(help="Live/paper trading on the configured universe")
app.add_typer(live_app, name="live")

console = Console()


def _get_store():
    """Get a MarketDataStore instance."""
    from bonito.data.store import MarketDataStore

    return MarketDataStore()


@app.callback()
def main(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging"),
) -> None:
    """AI-native algorithmic trading platform."""
    level = "DEBUG" if verbose else "INFO"
    setup_logging(level=level)


@app.command()
def chat(
    model: str = typer.Option("anthropic", "--model", "-m", help="LLM provider: anthropic, openai"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show tool calls and thinking"),
) -> None:
    """Start an interactive chat session with the Bonito agent."""
    import asyncio

    asyncio.run(_chat_loop(model, verbose))


async def _chat_loop(model: str, verbose: bool) -> None:
    """Async chat loop with the agent."""
    from bonito.agent.llm import get_llm_client
    from bonito.agent.orchestrator import (
        AgentOrchestrator,
        ErrorEvent,
        ResponseEvent,
        ToolCallEvent,
        ToolResultEvent,
    )
    from bonito.agent.tools import get_agent_tools

    # Initialize
    try:
        llm = get_llm_client(model)
    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
        return

    registry, _, _ = get_agent_tools()
    agent = AgentOrchestrator(llm=llm, tools=registry)

    console.print(
        Panel.fit(
            "[bold blue]Bonito[/bold blue]\n"
            "AI-native algorithmic trading assistant\n\n"
            "Ask me to create and backtest trading strategies.\n"
            "Type 'quit' to exit, 'reset' to clear history.",
            border_style="blue",
        )
    )

    while True:
        try:
            user_input = Prompt.ask("\n[bold green]You[/bold green]")

            if user_input.lower() in ("quit", "exit", "q"):
                console.print("[dim]Goodbye![/dim]")
                break

            if user_input.lower() == "reset":
                agent.reset()
                console.print("[dim]Conversation reset.[/dim]")
                continue

            if not user_input.strip():
                continue

            # Process with agent
            console.print()
            async for event in agent.process(user_input):
                if isinstance(event, ToolCallEvent):
                    if verbose:
                        console.print(
                            f"[yellow]→ {event.tool_name}[/yellow] [dim]{event.arguments}[/dim]"
                        )
                    else:
                        console.print(f"[yellow]→ {event.tool_name}[/yellow]")

                elif isinstance(event, ToolResultEvent):
                    if verbose:
                        status = "[green]✓[/green]" if event.success else "[red]✗[/red]"
                        console.print(f"  {status} {event.tool_name} completed")

                elif isinstance(event, ResponseEvent):
                    console.print(f"\n[bold blue]Agent[/bold blue]: {event.content}")

                elif isinstance(event, ErrorEvent):
                    console.print(f"[red]Error: {event.error}[/red]")

        except KeyboardInterrupt:
            console.print("\n[dim]Interrupted. Goodbye![/dim]")
            break


@app.command()
def ingest(
    symbols: list[str] = typer.Argument(..., help="Symbols to download (e.g., SPY AAPL QQQ)"),
    start: str = typer.Option("2020-01-01", "--start", "-s", help="Start date (YYYY-MM-DD)"),
    end: str = typer.Option(None, "--end", "-e", help="End date (YYYY-MM-DD), defaults to today"),
    timeframe: str = typer.Option("1d", "--timeframe", "-t", help="Timeframe: 1d, 1h, 15m, 5m, 1m"),
) -> None:
    """Download historical market data from Yahoo Finance."""
    if end is None:
        end = datetime.now().strftime("%Y-%m-%d")

    store = _get_store()
    total_bars = 0

    console.print(f"\n[dim]Downloading data from {start} to {end} ({timeframe})[/dim]\n")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        for symbol in symbols:
            task = progress.add_task(f"Downloading {symbol}...", total=None)
            try:
                count = store.ingest_from_yahoo(
                    symbol=symbol.upper(),
                    start=start,
                    end=end,
                    timeframe=timeframe,
                )
                total_bars += count
                progress.update(
                    task, description=f"[green]✓[/green] {symbol.upper()}: {count:,} bars"
                )
            except Exception as e:
                progress.update(task, description=f"[red]✗[/red] {symbol.upper()}: {str(e)}")

    store.close()

    console.print(f"\n[green]Done![/green] Ingested {total_bars:,} total bars")
    console.print(f"[dim]Data stored in {store.db_path}[/dim]")


@data_app.command("list")
def data_list() -> None:
    """List all symbols with available data."""
    store = _get_store()
    symbols = store.list_symbols()

    if not symbols:
        console.print("[yellow]No data found. Run 'bonito ingest <SYMBOL>' first.[/yellow]")
        store.close()
        return

    table = Table(title="Available Market Data")
    table.add_column("Symbol", style="cyan", no_wrap=True)
    table.add_column("Start Date", style="dim")
    table.add_column("End Date", style="dim")
    table.add_column("Bars", justify="right")

    for symbol in symbols:
        date_range = store.get_date_range(symbol)
        if date_range:
            bar_count = store.get_bar_count(symbol)
            table.add_row(
                symbol,
                date_range[0].strftime("%Y-%m-%d"),
                date_range[1].strftime("%Y-%m-%d"),
                f"{bar_count:,}",
            )

    store.close()
    console.print(table)


@data_app.command("info")
def data_info(
    symbol: str = typer.Argument(..., help="Symbol to get info for"),
    validate: bool = typer.Option(False, "--validate", help="Run data quality checks"),
) -> None:
    """Show detailed information about a symbol's data."""
    store = _get_store()
    symbol = symbol.upper()

    date_range = store.get_date_range(symbol)
    if not date_range:
        console.print(f"[red]No data found for {symbol}[/red]")
        console.print("[dim]Run 'bonito ingest {symbol}' to download data.[/dim]")
        store.close()
        return

    # Get statistics
    stats = store.conn.execute(
        """
        SELECT
            COUNT(*) as bars,
            MIN(close) as min_price,
            MAX(close) as max_price,
            AVG(close) as avg_price,
            AVG(volume) as avg_volume,
            MIN(volume) as min_volume,
            MAX(volume) as max_volume
        FROM bars
        WHERE symbol = ?
    """,
        [symbol],
    ).fetchone()

    console.print(f"\n[bold cyan]{symbol}[/bold cyan] Data Summary\n")
    console.print(
        f"  📅 Date Range:  {date_range[0].strftime('%Y-%m-%d')} to {date_range[1].strftime('%Y-%m-%d')}"
    )
    console.print(f"  📊 Total Bars:  {stats[0]:,}")
    console.print(f"  💰 Price Range: ${stats[1]:.2f} - ${stats[2]:.2f}")
    console.print(f"  📈 Avg Price:   ${stats[3]:.2f}")
    console.print(f"  📦 Avg Volume:  {stats[4]:,.0f}")

    # Get most recent bars
    recent = store.conn.execute(
        """
        SELECT timestamp, open, high, low, close, volume
        FROM bars
        WHERE symbol = ?
        ORDER BY timestamp DESC
        LIMIT 5
    """,
        [symbol],
    ).fetchall()

    if recent:
        console.print("\n  [dim]Recent bars:[/dim]")
        for row in recent:
            ts, open_price, high, low, close, vol = row
            console.print(
                f"    {ts.strftime('%Y-%m-%d')}: O={open_price:.2f} H={high:.2f} L={low:.2f} C={close:.2f} V={vol:,.0f}"
            )

    # Validation
    if validate:
        console.print("\n  [dim]Running validation...[/dim]")
        result = store.validate_bars(symbol)

        if result["valid"]:
            console.print("  [green]✓ Data validation passed[/green]")
        else:
            console.print("  [yellow]⚠ Data quality issues found:[/yellow]")
            for issue in result["issues"]:
                console.print(f"    - {issue}")

    store.close()


@data_app.command("delete")
def data_delete(
    symbol: str = typer.Argument(..., help="Symbol to delete"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
) -> None:
    """Delete data for a symbol."""
    symbol = symbol.upper()

    if not force:
        confirm = Prompt.ask(
            f"[yellow]Delete all data for {symbol}?[/yellow]",
            choices=["y", "n"],
            default="n",
        )
        if confirm != "y":
            console.print("[dim]Cancelled.[/dim]")
            return

    store = _get_store()
    # DuckDB doesn't return row count from DELETE, so we count first
    count = store.get_bar_count(symbol)

    if count == 0:
        console.print(f"[yellow]No data found for {symbol}[/yellow]")
    else:
        store.conn.execute("DELETE FROM bars WHERE symbol = ?", [symbol])
        console.print(f"[green]Deleted {count:,} bars for {symbol}[/green]")

    store.close()


@app.command()
def backtest(
    strategy_file: str = typer.Argument(..., help="Path to strategy config JSON file"),
    symbol: str = typer.Option(None, "--symbol", "-s", help="Override strategy symbol"),
    start: str = typer.Option("2020-01-01", "--start", help="Start date (YYYY-MM-DD)"),
    end: str = typer.Option(None, "--end", "-e", help="End date (YYYY-MM-DD), defaults to today"),
    capital: float = typer.Option(100000, "--capital", "-c", help="Initial capital"),
    output: str = typer.Option(None, "--output", "-o", help="Save results to JSON file"),
) -> None:
    """Run a backtest for a strategy configuration."""
    import json
    from pathlib import Path

    from bonito.backtest.engine import BacktestEngine
    from bonito.backtest.models import BacktestConfig
    from bonito.backtest.strategy import StrategyConfig

    # Load strategy
    strategy_path = Path(strategy_file)
    if not strategy_path.exists():
        console.print(f"[red]Strategy file not found: {strategy_file}[/red]")
        raise typer.Exit(1)

    with open(strategy_path) as f:
        strategy_data = json.load(f)

    try:
        strategy = StrategyConfig(**strategy_data)
    except Exception as e:
        console.print(f"[red]Invalid strategy configuration: {e}[/red]")
        raise typer.Exit(1) from None

    # Override symbol if provided
    if symbol:
        strategy = strategy.model_copy(update={"symbols": [symbol.upper()]})

    target_symbol = strategy.symbols[0]

    # Parse dates
    start_date = datetime.strptime(start, "%Y-%m-%d")
    end_date = datetime.strptime(end, "%Y-%m-%d") if end else datetime.now()

    # Load data
    store = _get_store()

    console.print(f"\n[bold]Loading data for {target_symbol}...[/bold]")
    data = store.get_bars(target_symbol, start_date, end_date, strategy.timeframe)
    store.close()

    if data is None:
        console.print(f"[red]No data found for {target_symbol}[/red]")
        console.print(f"[dim]Run 'bonito ingest {target_symbol}' first.[/dim]")
        raise typer.Exit(1)

    console.print(
        f"[dim]Loaded {len(data)} bars from {data.timestamps[0].strftime('%Y-%m-%d')} to {data.timestamps[-1].strftime('%Y-%m-%d')}[/dim]"
    )

    # Run backtest
    console.print(f"\n[bold]Running backtest: {strategy.name}[/bold]")

    config = BacktestConfig(
        start_date=start_date,
        end_date=end_date,
        initial_capital=capital,
    )
    engine = BacktestEngine(config)

    with console.status("[bold blue]Backtesting...[/bold blue]"):
        result = engine.run(strategy, data)

    # Display results
    console.print(result.summary())

    # Metrics table
    m = result.metrics
    metrics_table = Table(title="Performance Metrics", show_header=False)
    metrics_table.add_column("Metric", style="cyan")
    metrics_table.add_column("Value", justify="right")

    metrics_table.add_row("Total Return", f"{m.total_return:.2%}")
    metrics_table.add_row("Annualized Return", f"{m.annualized_return:.2%}")
    metrics_table.add_row("Sharpe Ratio", f"{m.sharpe_ratio:.2f}")
    metrics_table.add_row("Sortino Ratio", f"{m.sortino_ratio:.2f}")
    metrics_table.add_row("Max Drawdown", f"{m.max_drawdown:.2%}")
    metrics_table.add_row("Win Rate", f"{m.win_rate:.1%}")
    metrics_table.add_row("Profit Factor", f"{m.profit_factor:.2f}")
    metrics_table.add_row("Total Trades", str(m.total_trades))

    console.print(metrics_table)

    # Trade table
    if result.trades:
        console.print("\n[bold]Recent Trades:[/bold]")

        trade_table = Table()
        trade_table.add_column("Entry Date", style="dim")
        trade_table.add_column("Exit Date", style="dim")
        trade_table.add_column("Entry $", justify="right")
        trade_table.add_column("Exit $", justify="right")
        trade_table.add_column("P&L", justify="right")
        trade_table.add_column("Return", justify="right")
        trade_table.add_column("Reason")

        for trade in result.trades[-10:]:  # Last 10 trades
            pnl_style = "green" if trade.pnl > 0 else "red"
            trade_table.add_row(
                trade.entry_time.strftime("%Y-%m-%d"),
                trade.exit_time.strftime("%Y-%m-%d"),
                f"${trade.entry_price:.2f}",
                f"${trade.exit_price:.2f}",
                f"[{pnl_style}]${trade.pnl:,.2f}[/{pnl_style}]",
                f"[{pnl_style}]{trade.pnl_percent:.2%}[/{pnl_style}]",
                trade.exit_reason,
            )

        console.print(trade_table)

    # Save results if requested
    if output:
        output_path = Path(output)
        result_data = {
            "strategy_name": result.strategy_name,
            "symbol": result.symbol,
            "period": f"{start} to {end_date.strftime('%Y-%m-%d')}",
            "initial_capital": result.initial_capital,
            "final_capital": result.final_capital,
            "metrics": {
                "total_return": result.metrics.total_return,
                "annualized_return": result.metrics.annualized_return,
                "sharpe_ratio": result.metrics.sharpe_ratio,
                "sortino_ratio": result.metrics.sortino_ratio,
                "max_drawdown": result.metrics.max_drawdown,
                "total_trades": result.metrics.total_trades,
                "win_rate": result.metrics.win_rate,
                "profit_factor": result.metrics.profit_factor,
            },
            "trades": [
                {
                    "entry_time": t.entry_time.isoformat(),
                    "exit_time": t.exit_time.isoformat(),
                    "entry_price": t.entry_price,
                    "exit_price": t.exit_price,
                    "pnl": t.pnl,
                    "pnl_percent": t.pnl_percent,
                    "exit_reason": t.exit_reason,
                }
                for t in result.trades
            ],
        }
        with open(output_path, "w") as f:
            json.dump(result_data, f, indent=2, default=str)
        console.print(f"\n[dim]Results saved to {output_path}[/dim]")


@research_app.command("run")
def research_run(
    symbol: str = typer.Option("SPY", "--symbol", "-s", help="Symbol to research"),
    iterations: int = typer.Option(1000, "--iterations", "-n", help="Max mutation iterations"),
    seed: str = typer.Option(None, "--seed", help="Path to seed strategy JSON"),
    output_dir: str = typer.Option(None, "--output-dir", "-o", help="Output directory"),
    start: str = typer.Option("2020-01-01", "--start", help="Data start date (YYYY-MM-DD)"),
    end: str = typer.Option("2025-03-20", "--end", "-e", help="Data end date (YYYY-MM-DD)"),
) -> None:
    """Run autonomous strategy research (Karpathy-style mutation loop)."""
    from pathlib import Path

    from bonito.research.autoresearch_trading import run

    console.print(
        Panel.fit(
            f"[bold blue]Autonomous Strategy Research[/bold blue]\n"
            f"Symbol: {symbol} | Iterations: {iterations}\n"
            f"Data: {start} to {end}",
            border_style="blue",
        )
    )

    run(
        symbol=symbol.upper(),
        iterations=iterations,
        seed_path=Path(seed) if seed else None,
        output_dir=Path(output_dir) if output_dir else None,
        start_date=start,
        end_date=end,
    )


@research_app.command("clusters")
def research_clusters(
    universe_path: str = typer.Option("config/universe.json", "--universe", "-u"),
    start: str = typer.Option("2022-01-01", "--start"),
    holdout: str = typer.Option("2025-01-01", "--holdout", help="Out-of-sample boundary"),
    end: str = typer.Option(None, "--end", help="Default: today"),
    apply: bool = typer.Option(
        False,
        "--apply",
        help="Write winning strategies to strategies/ and merge passing pairs "
        "into universe.symbol_strategies (dry-run report otherwise)",
    ),
) -> None:
    """Per-cluster strategy research over a fixed parameter grid.

    Clusters the universe by realized volatility, ranks ~144 candidates per
    cluster on the TRAIN window only, then gates the single winner on the
    holdout kill filter. Assignments are per (symbol, strategy) pair —
    symbols where nothing passes keep the default strategy.
    """
    from datetime import UTC as _UTC
    from datetime import datetime as _dt

    from bonito.research.cluster_research import (
        apply_assignments,
        candidate_grid,
        run_cluster_research,
        save_report,
    )

    universe = _load_universe(universe_path)
    store = _get_store()
    start_dt = datetime.strptime(start, "%Y-%m-%d")
    holdout_dt = datetime.strptime(holdout, "%Y-%m-%d")
    end_dt = datetime.strptime(end, "%Y-%m-%d") if end else _dt.now(_UTC).replace(tzinfo=None)

    n_candidates = len(candidate_grid())
    console.print(
        Panel.fit(
            f"[bold blue]Cluster Research[/bold blue]\n"
            f"Train: {start} → {holdout} | Holdout: {holdout} → {end or 'today'}\n"
            f"{n_candidates} candidates per cluster, ranked on train, gated on holdout",
            border_style="blue",
        )
    )

    with Progress(
        SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console
    ) as prog:
        task = prog.add_task("researching...", total=None)
        done = {"n": 0}

        def tick():
            done["n"] += 1
            prog.update(task, description=f"researching... {done['n']} candidates evaluated")

        report = run_cluster_research(universe, store, start_dt, holdout_dt, end_dt, progress=tick)

    report_path = save_report(report)

    for cluster in report.clusters:
        table = Table(
            title=f"{cluster.name} — {len(cluster.members)} symbols, "
            f"{cluster.candidates_eligible}/{cluster.candidates_evaluated} candidates eligible"
        )
        for col in (
            "Symbol",
            "Vol",
            "T.Sharpe",
            "T.DD %",
            "H.Trades",
            "H.Ret %",
            "H.Sharpe",
            "H.DD %",
            "Verdict",
        ):
            table.add_column(col, justify="right")
        if cluster.winner_name is None:
            console.print(
                f"[yellow]{cluster.name}: no candidate passed the train filter on a "
                f"majority of members — no assignment[/yellow]"
            )
            continue
        for v in cluster.verdicts:
            verdict = (
                "[green]PASS[/green]" if v.passes else f"[red]{'; '.join(v.holdout_reasons)}[/red]"
            )
            table.add_row(
                v.symbol,
                f"{cluster.volatility.get(v.symbol, 0) * 100:.0f}%",
                f"{v.train.sharpe:.2f}",
                f"{v.train.max_drawdown * 100:.1f}",
                str(v.holdout.trades),
                f"{v.holdout.total_return * 100:+.1f}",
                f"{v.holdout.sharpe:.2f}",
                f"{v.holdout.max_drawdown * 100:.1f}",
                verdict,
            )
        console.print(table)
        console.print(
            f"  winner: [bold]{cluster.winner_name}[/bold] ({cluster.winner_hash}) "
            f"train score {cluster.winner_train_score}\n"
        )

    assignments = report.assignments()
    console.print(f"[dim]Report saved to {report_path}[/dim]")
    if not assignments:
        console.print("[yellow]No (symbol, strategy) pairs passed the holdout gate.[/yellow]")
        return

    console.print(
        f"[bold]{len(assignments)} symbol(s) qualify for per-symbol assignment:[/bold] "
        + ", ".join(sorted(assignments))
    )
    if apply:
        written = apply_assignments(report, Path(universe_path))
        for symbol, path in sorted(written.items()):
            console.print(f"  {symbol} → {path}")
        console.print(
            "[green]universe.json updated.[/green] Open positions are unaffected "
            "(they exit under their pinned strategy)."
        )
    else:
        console.print("[dim]Dry run — re-run with --apply to write assignments.[/dim]")


# --- Live trading commands (Robinhood option-A pipeline) ---


def _load_universe(universe_path: str):
    from pathlib import Path

    from bonito.trading.live_runner import UniverseConfig

    return UniverseConfig.load(Path(universe_path))


def _load_ledger(universe):
    from bonito.trading.paper import PaperLedger, ledger_path_for_mode

    return PaperLedger.load_or_create(
        ledger_path_for_mode(universe.mode), starting_cash=universe.risk.starting_cash_usd
    )


@live_app.command("refresh")
def live_refresh(
    universe_path: str = typer.Option("config/universe.json", "--universe", "-u"),
) -> None:
    """Ingest fresh daily bars for every universe symbol."""
    from bonito.trading.live_runner import refresh_data

    universe = _load_universe(universe_path)
    results = refresh_data(universe, _get_store())

    table = Table(title="Data Refresh")
    table.add_column("Symbol")
    table.add_column("Bars", justify="right")
    failed = []
    for symbol, count in results.items():
        table.add_row(symbol, str(count) if count >= 0 else "[red]FAILED[/red]")
        if count < 0:
            failed.append(symbol)
    console.print(table)
    if failed:
        console.print(f"[red]Failed: {', '.join(failed)}[/red]")
        raise typer.Exit(1)


@live_app.command("signals")
def live_signals(
    universe_path: str = typer.Option("config/universe.json", "--universe", "-u"),
) -> None:
    """Generate trade intents (no execution). Writes livetrade/intents/*.json."""
    from bonito.trading.live_runner import generate_intents, save_intents
    from bonito.trading.paper import DEFAULT_LEDGER_PATH

    universe = _load_universe(universe_path)
    ledger = _load_ledger(universe)
    intents, prices = generate_intents(universe, _get_store(), ledger)
    ledger.save()  # persist high-water-mark updates

    if not intents:
        console.print("[dim]No trade intents today.[/dim]")
        return

    path = save_intents(intents)
    table = Table(title=f"Trade Intents ({universe.mode})")
    for col in ("Side", "Symbol", "Size", "Signal Px", "Reason"):
        table.add_column(col)
    for i in intents:
        size = f"${i.dollar_amount:.2f}" if i.dollar_amount else f"{i.quantity:.4f} sh"
        table.add_row(i.side.upper(), i.symbol, size, f"${i.signal_price:.2f}", i.reason)
    console.print(table)
    console.print(f"[dim]Saved to {path} | ledger: {DEFAULT_LEDGER_PATH}[/dim]")


@live_app.command("run")
def live_run(
    universe_path: str = typer.Option("config/universe.json", "--universe", "-u"),
    refresh: bool = typer.Option(True, "--refresh/--no-refresh", help="Refresh data first"),
) -> None:
    """Full daily cycle: refresh data, generate intents, fill in paper mode.

    In live mode this stops after writing intents — real orders are placed
    by the Claude session via the Robinhood MCP, never by this CLI.
    """
    from bonito.trading.live_runner import (
        execute_paper,
        generate_intents,
        refresh_data,
        save_intents,
    )

    universe = _load_universe(universe_path)
    if universe.mode == "live" and not universe.live_enabled:
        console.print(
            "[red]mode is 'live' but live_enabled is false in universe.json — refusing.[/red]"
        )
        raise typer.Exit(1)

    store = _get_store()

    if refresh:
        results = refresh_data(universe, store)
        ok = sum(1 for c in results.values() if c >= 0)
        console.print(f"Refreshed {ok}/{len(results)} symbols")

    ledger = _load_ledger(universe)
    intents, prices = generate_intents(universe, store, ledger)

    if intents:
        path = save_intents(intents)
        console.print(f"[bold]{len(intents)} intent(s)[/bold] → {path}")
        for i in intents:
            size = f"${i.dollar_amount:.2f}" if i.dollar_amount else f"{i.quantity:.4f} sh"
            console.print(f"  {i.side.upper()} {i.symbol} {size} — {i.reason}")
    else:
        console.print("[dim]No trade intents today.[/dim]")

    if universe.mode == "paper":
        buy_strategies = {
            i.symbol: universe.load_strategy_for(i.symbol) for i in intents if i.side == "buy"
        }
        fills, errors = execute_paper(ledger, intents, prices, strategies=buy_strategies)
        for e in errors:
            console.print(f"[red]Rejected: {e}[/red]")
        console.print(f"Paper fills: {len(fills)}")
    else:
        console.print(
            "[yellow]Live mode: intents written, execute via Robinhood MCP "
            "then record fills with `bonito live record-fill`.[/yellow]"
        )

    ledger.save()
    _print_status(ledger, prices)


@live_app.command("check-stops")
def live_check_stops(
    prices_json: str = typer.Argument(
        ..., help='Current prices as JSON, e.g. \'{"TSLA": 412.5, "NVDA": 180.2}\''
    ),
    universe_path: str = typer.Option("config/universe.json", "--universe", "-u"),
    execute: bool = typer.Option(
        False, "--execute", help="Fill triggered exits in the paper ledger at given prices"
    ),
) -> None:
    """Intraday stop-loss/take-profit sweep against supplied prices."""
    import json as _json

    universe = _load_universe(universe_path)
    ledger = _load_ledger(universe)
    prices = {k.upper(): float(v) for k, v in _json.loads(prices_json).items()}
    _sweep_stops(universe, ledger, prices, execute)


@live_app.command("sweep")
def live_sweep(
    universe_path: str = typer.Option("config/universe.json", "--universe", "-u"),
    execute: bool = typer.Option(
        False, "--execute", help="Fill triggered exits in the paper ledger"
    ),
    no_refresh: bool = typer.Option(
        False, "--no-refresh", help="Skip refreshing daily bars (the ATR source)"
    ),
) -> None:
    """Self-contained intraday stop sweep.

    Fetches live quotes for every open position via yfinance and runs the
    stop-loss/take-profit check — same as check-stops, but it sources its
    own prices. Built for the scheduled intraday-stops workflow.
    """
    from bonito.data.quotes import fetch_latest_quotes
    from bonito.trading.live_runner import refresh_data

    universe = _load_universe(universe_path)
    ledger = _load_ledger(universe)
    if not ledger.positions:
        console.print("[dim]No open positions — nothing to monitor.[/dim]")
        return

    symbols = sorted(ledger.positions)
    if not no_refresh:
        refresh_data(universe, _get_store(), symbols=symbols)

    prices = fetch_latest_quotes(symbols)
    missing = [s for s in symbols if s not in prices]
    if missing:
        console.print(f"[yellow]No quotes for {', '.join(missing)} — holding those.[/yellow]")
    if not prices:
        console.print("[red]All quote lookups failed — sweep aborted.[/red]")
        raise typer.Exit(1)

    _sweep_stops(universe, ledger, prices, execute)


def _sweep_stops(universe, ledger, prices: dict[str, float], execute: bool) -> None:
    """Shared body of check-stops/sweep: ATRs → stop check → report/execute."""
    from bonito.trading.live_runner import (
        check_stops,
        compute_position_atrs,
        execute_paper,
        save_intents,
    )

    atrs = compute_position_atrs(universe, ledger, _get_store())
    intents = check_stops(universe, ledger, prices, atrs=atrs)
    if not intents:
        console.print(f"[dim]No stops triggered ({len(prices)} price(s) checked).[/dim]")
        ledger.save()  # persist high-water-mark updates
        return

    path = save_intents(intents)
    for i in intents:
        console.print(f"[bold red]EXIT {i.symbol}[/bold red] @ ${i.signal_price:.2f} — {i.reason}")
    console.print(f"[dim]Saved to {path}[/dim]")

    if execute and universe.mode == "paper":
        fills, errors = execute_paper(ledger, intents, prices)
        for e in errors:
            console.print(f"[red]Rejected: {e}[/red]")
        console.print(f"Paper fills: {len(fills)}")

    ledger.save()


@live_app.command("reconcile")
def live_reconcile(
    positions_json: str = typer.Argument(
        ...,
        help='Broker positions as JSON {"SYMBOL": quantity, ...} '
        "(from Robinhood MCP get_equity_positions; {} if account is flat)",
    ),
    universe_path: str = typer.Option("config/universe.json", "--universe", "-u"),
) -> None:
    """Verify the ledger matches the broker's actual positions.

    MUST pass before any live-mode trading. Exits non-zero on drift so
    automated sessions hard-stop instead of trading on bad state.
    """
    import json as _json

    from bonito.trading.live_runner import reconcile_positions

    universe = _load_universe(universe_path)
    ledger = _load_ledger(universe)
    broker_positions = {k.upper(): float(v) for k, v in _json.loads(positions_json).items()}

    report = reconcile_positions(ledger, broker_positions)
    if report.in_sync:
        console.print("[green]✓ Ledger and broker are in sync[/green]")
        return

    console.print("[bold red]DRIFT DETECTED — do not trade until resolved:[/bold red]")
    console.print(report.describe())
    console.print(
        "[dim]Resolve with `bonito live record-fill` using the actual fill data "
        "from Robinhood order history (get_equity_orders, placed_agent=agentic).[/dim]"
    )
    raise typer.Exit(1)


@live_app.command("status")
def live_status(
    universe_path: str = typer.Option("config/universe.json", "--universe", "-u"),
    prices_json: str = typer.Option(
        None, "--prices", help="Optional current prices JSON for mark-to-market"
    ),
) -> None:
    """Show paper ledger status: cash, positions, P&L."""
    import json as _json

    universe = _load_universe(universe_path)
    ledger = _load_ledger(universe)
    prices = (
        {k.upper(): float(v) for k, v in _json.loads(prices_json).items()} if prices_json else {}
    )
    _print_status(ledger, prices)


def _print_status(ledger, prices: dict[str, float]) -> None:
    s = ledger.summary(prices)
    if s["halted"]:
        console.print(
            Panel.fit(
                f"[bold red]KILL SWITCH ACTIVE[/bold red]\n{s['halt_reason']}\n"
                "No new entries until `bonito live resume`.",
                border_style="red",
            )
        )
    console.print(
        Panel.fit(
            f"[bold]Equity: ${s['equity']:.2f}[/bold] ({s['total_return_pct']:+.2f}%)\n"
            f"Cash: ${s['cash']:.2f} | Realized P&L: ${s['realized_pnl']:+.2f} | "
            f"Unrealized: ${s['unrealized_pnl']:+.2f} | Fills: {s['total_fills']}",
            title="Paper Account",
            border_style="green" if s["total_return_pct"] >= 0 else "red",
        )
    )
    if s["open_positions"]:
        table = Table(title="Open Positions")
        for col in ("Symbol", "Qty", "Entry", "Current", "Value", "P&L"):
            table.add_column(col, justify="right")
        for p in s["open_positions"]:
            table.add_row(
                p["symbol"],
                f"{p['quantity']:.4f}",
                f"${p['entry_price']:.2f}",
                f"${p['current_price']:.2f}",
                f"${p['market_value']:.2f}",
                f"${p['unrealized_pnl']:+.2f}",
            )
        console.print(table)


@live_app.command("record-fill")
def live_record_fill(
    symbol: str = typer.Argument(...),
    side: str = typer.Argument(..., help="buy or sell"),
    price: float = typer.Argument(..., help="Actual fill price from Robinhood"),
    dollar_amount: float = typer.Option(None, "--dollars", help="Notional for buys"),
    reason: str = typer.Option("live fill", "--reason"),
    universe_path: str = typer.Option("config/universe.json", "--universe", "-u"),
) -> None:
    """Record a real Robinhood fill into the ledger (live mode bookkeeping)."""
    from datetime import UTC as _UTC
    from datetime import datetime as _dt

    from bonito.trading.live_runner import execute_paper
    from bonito.trading.signals import TradeIntent

    universe = _load_universe(universe_path)
    ledger = _load_ledger(universe)
    symbol = symbol.upper()

    if side == "buy" and not dollar_amount:
        console.print("[red]Buys require --dollars[/red]")
        raise typer.Exit(1)

    quantity = ledger.positions[symbol].quantity if side == "sell" else None
    intent = TradeIntent(
        symbol=symbol,
        side=side,  # type: ignore[arg-type]
        dollar_amount=dollar_amount,
        quantity=quantity,
        reason=reason,
        signal_price=price,
        signal_date=_dt.now(_UTC),
        strategy_name="live",
    )
    strategies = {symbol: universe.load_strategy_for(symbol)} if side == "buy" else None
    fills, errors = execute_paper(ledger, [intent], {symbol: price}, strategies=strategies)
    for e in errors:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    ledger.save()
    console.print(f"Recorded {side.upper()} {symbol} @ ${price:.2f}")


@app.command("dashboard")
def dashboard(
    port: int = typer.Option(8050, "--port", "-p"),
    host: str = typer.Option("127.0.0.1", "--host"),
) -> None:
    """Serve the read-only live-trading dashboard (positions, P&L, regime)."""
    import uvicorn

    console.print(f"[bold]Bonito dashboard[/bold] → http://{host}:{port}")
    uvicorn.run("bonito.dashboard.app:app", host=host, port=port)


@live_app.command("resume")
def live_resume(
    universe_path: str = typer.Option("config/universe.json", "--universe", "-u"),
) -> None:
    """Clear a kill-switch halt (explicit human action).

    The kill switch flattens all positions and blocks new entries when
    account drawdown breaches risk.max_drawdown_halt. Resuming requires a
    human to have reviewed what went wrong.
    """
    universe = _load_universe(universe_path)
    ledger = _load_ledger(universe)
    if not ledger.halted:
        console.print("[dim]Ledger is not halted.[/dim]")
        return
    reason = ledger.halt_reason
    ledger.resume()
    ledger.save()
    console.print(f"[green]Halt cleared[/green] (was: {reason})")


@live_app.command("backtest-universe")
def live_backtest_universe(
    universe_path: str = typer.Option("config/universe.json", "--universe", "-u"),
    start: str = typer.Option("2022-01-01", "--start"),
    end: str = typer.Option(None, "--end", help="Default: today"),
    holdout: str = typer.Option(
        "2025-01-01",
        "--holdout",
        help="Out-of-sample boundary: verdict is computed on [holdout, end]. "
        "Pass 'none' to apply the kill filter to the full period instead.",
    ),
    strategy_path: str = typer.Option(
        None,
        "--strategy",
        help="Backtest this strategy file for every symbol instead of the "
        "universe's assigned (per-symbol) strategies",
    ),
) -> None:
    """Validate strategies across the universe with a kill-filter verdict.

    One full-range simulation per symbol; metrics are then sliced into
    train ([start, holdout)) and holdout ([holdout, end]) windows so
    indicator warmup never bleeds into the out-of-sample numbers. The
    kill filter (trade count, max drawdown, Sharpe ceiling) runs on the
    holdout window — strategies must work on data they weren't tuned on.
    """
    from datetime import UTC as _UTC
    from datetime import datetime as _dt

    from bonito.backtest.engine import BacktestEngine
    from bonito.backtest.models import BacktestConfig
    from bonito.trading.validation import kill_verdict, window_metrics

    universe = _load_universe(universe_path)
    store = _get_store()

    start_dt = datetime.strptime(start, "%Y-%m-%d")
    end_dt = datetime.strptime(end, "%Y-%m-%d") if end else _dt.now(_UTC).replace(tzinfo=None)
    holdout_dt = None if holdout.lower() == "none" else datetime.strptime(holdout, "%Y-%m-%d")
    engine = BacktestEngine(
        BacktestConfig(
            start_date=start_dt,
            end_date=end_dt,
            initial_capital=universe.risk.starting_cash_usd,
        )
    )

    override = None
    if strategy_path:
        import json as _json

        override = _json.loads(Path(strategy_path).read_text())

    # Regime data is shared across symbols — fetch once per reference symbol.
    regime_cache: dict[tuple[str, int], object] = {}

    def regime_bars(strategy):
        if strategy.regime_filter is None:
            return None
        key = (strategy.regime_filter.symbol.upper(), strategy.regime_filter.sma_period)
        if key not in regime_cache:
            from bonito.trading.live_runner import REGIME_WARMUP_DAYS

            regime_start = start_dt - timedelta(days=REGIME_WARMUP_DAYS)
            bars = store.get_bars(key[0], regime_start, end_dt, universe.data.timeframe)
            if bars is None or len(bars) < strategy.regime_filter.sma_period:
                console.print(
                    f"[red]Regime symbol {key[0]} has insufficient data — "
                    f"run `bonito live refresh` first.[/red]"
                )
                raise typer.Exit(1)
            regime_cache[key] = bars
        return regime_cache[key]

    if holdout_dt:
        title = (
            f"Universe Validation ({start} → {end or 'today'}, "
            f"holdout from {holdout}, verdict on holdout)"
        )
        columns = (
            "Symbol",
            "Strategy",
            "Trades",
            "Ret %",
            "Sharpe",
            "DD %",
            "H.Trades",
            "H.Ret %",
            "H.Sharpe",
            "H.DD %",
            "Verdict",
        )
    else:
        title = f"Universe Validation ({start} → {end or 'today'}, verdict on full period)"
        columns = ("Symbol", "Strategy", "Trades", "Win %", "Ret %", "Sharpe", "DD %", "Verdict")

    table = Table(title=title)
    for col in columns:
        table.add_column(col, justify="right")

    from bonito.backtest.strategy import StrategyConfig

    passed = 0
    for symbol in universe.symbols:
        if override is not None:
            strategy = StrategyConfig(**override)
        else:
            strategy = universe.load_strategy_for(symbol)
        data = store.get_bars(symbol, start_dt, end_dt, universe.data.timeframe)
        if data is None or len(data) < 50:
            table.add_row(symbol, strategy.name, "[dim]no data[/dim]", *[""] * (len(columns) - 3))
            continue
        per_symbol = strategy.model_copy(update={"symbols": [symbol]})
        result = engine.run(per_symbol, data, regime_data=regime_bars(strategy))

        full = window_metrics(result, start_dt, end_dt)
        if holdout_dt:
            hold = window_metrics(result, holdout_dt, end_dt)
            reasons = kill_verdict(hold)
            verdict = "[green]PASS[/green]" if not reasons else f"[red]{'; '.join(reasons)}[/red]"
            passed += not reasons
            table.add_row(
                symbol,
                strategy.name,
                str(full.trades),
                f"{full.total_return * 100:+.1f}",
                f"{full.sharpe:.2f}",
                f"{full.max_drawdown * 100:.1f}",
                str(hold.trades),
                f"{hold.total_return * 100:+.1f}",
                f"{hold.sharpe:.2f}",
                f"{hold.max_drawdown * 100:.1f}",
                verdict,
            )
        else:
            reasons = kill_verdict(full)
            verdict = "[green]PASS[/green]" if not reasons else f"[red]{'; '.join(reasons)}[/red]"
            passed += not reasons
            table.add_row(
                symbol,
                strategy.name,
                str(full.trades),
                f"{full.win_rate * 100:.0f}",
                f"{full.total_return * 100:+.1f}",
                f"{full.sharpe:.2f}",
                f"{full.max_drawdown * 100:.1f}",
                verdict,
            )

    console.print(table)
    console.print(f"[bold]{passed}/{len(universe.symbols)} symbols pass the kill filter[/bold]")


if __name__ == "__main__":
    app()
