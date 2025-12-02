"""Command-line interface for the quant agent."""

from datetime import datetime

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Prompt
from rich.table import Table

from quant_agent.logging import setup_logging

app = typer.Typer(
    name="quant",
    help="AI-native algorithmic trading platform",
    no_args_is_help=True,
)

# Subcommand group for data operations
data_app = typer.Typer(help="Data management commands")
app.add_typer(data_app, name="data")

console = Console()


def _get_store():
    """Get a MarketDataStore instance."""
    from quant_agent.data.store import MarketDataStore
    return MarketDataStore()


@app.callback()
def main(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging"),
) -> None:
    """AI-native algorithmic trading platform."""
    level = "DEBUG" if verbose else "INFO"
    setup_logging(level=level)


@app.command()
def chat() -> None:
    """Start an interactive chat session with the quant agent."""
    console.print(
        Panel.fit(
            "[bold blue]Quant Agent[/bold blue]\n"
            "AI-native algorithmic trading platform\n\n"
            "Type your request or 'quit' to exit.",
            border_style="blue",
        )
    )
    
    while True:
        try:
            user_input = Prompt.ask("\n[bold green]You[/bold green]")
            
            if user_input.lower() in ("quit", "exit", "q"):
                console.print("[dim]Goodbye![/dim]")
                break
            
            # TODO: Integrate with agent
            console.print(
                f"\n[bold blue]Agent[/bold blue]: "
                f"[dim](Agent not yet implemented. You said: {user_input})[/dim]"
            )
            
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
                    task, 
                    description=f"[green]✓[/green] {symbol.upper()}: {count:,} bars"
                )
            except Exception as e:
                progress.update(
                    task, 
                    description=f"[red]✗[/red] {symbol.upper()}: {str(e)}"
                )
    
    store.close()
    
    console.print(f"\n[green]Done![/green] Ingested {total_bars:,} total bars")
    console.print(f"[dim]Data stored in {store.db_path}[/dim]")


@data_app.command("list")
def data_list() -> None:
    """List all symbols with available data."""
    store = _get_store()
    symbols = store.list_symbols()
    
    if not symbols:
        console.print("[yellow]No data found. Run 'quant ingest <SYMBOL>' first.[/yellow]")
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
        console.print("[dim]Run 'quant ingest {symbol}' to download data.[/dim]")
        store.close()
        return
    
    # Get statistics
    stats = store.conn.execute("""
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
    """, [symbol]).fetchone()
    
    console.print(f"\n[bold cyan]{symbol}[/bold cyan] Data Summary\n")
    console.print(f"  📅 Date Range:  {date_range[0].strftime('%Y-%m-%d')} to {date_range[1].strftime('%Y-%m-%d')}")
    console.print(f"  📊 Total Bars:  {stats[0]:,}")
    console.print(f"  💰 Price Range: ${stats[1]:.2f} - ${stats[2]:.2f}")
    console.print(f"  📈 Avg Price:   ${stats[3]:.2f}")
    console.print(f"  📦 Avg Volume:  {stats[4]:,.0f}")
    
    # Get most recent bars
    recent = store.conn.execute("""
        SELECT timestamp, open, high, low, close, volume
        FROM bars
        WHERE symbol = ?
        ORDER BY timestamp DESC
        LIMIT 5
    """, [symbol]).fetchall()
    
    if recent:
        console.print("\n  [dim]Recent bars:[/dim]")
        for row in recent:
            ts, o, h, l, c, v = row
            console.print(f"    {ts.strftime('%Y-%m-%d')}: O={o:.2f} H={h:.2f} L={l:.2f} C={c:.2f} V={v:,.0f}")
    
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
    strategy: str = typer.Argument(..., help="Path to strategy config JSON file"),
    symbol: str = typer.Option("SPY", help="Symbol to backtest"),
    start: str = typer.Option("2020-01-01", help="Start date (YYYY-MM-DD)"),
    end: str = typer.Option("2024-01-01", help="End date (YYYY-MM-DD)"),
) -> None:
    """Run a backtest for a strategy configuration."""
    console.print(f"[dim]Backtesting {strategy} on {symbol} from {start} to {end}...[/dim]")
    # TODO: Implement in Week 2
    console.print("[yellow]Backtest engine not yet implemented. Coming in Week 2![/yellow]")


if __name__ == "__main__":
    app()
