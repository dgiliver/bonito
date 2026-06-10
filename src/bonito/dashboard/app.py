"""FastAPI app for the standalone live-trading dashboard.

Run with:
    bonito dashboard                 # or
    make dashboard                   # or
    uvicorn bonito.dashboard.app:app --port 8050

Read-only: the dashboard never mutates the ledger or places orders.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from bonito.dashboard.state import build_dashboard_state
from bonito.data.store import MarketDataStore
from bonito.trading.live_runner import DEFAULT_UNIVERSE_PATH, UniverseConfig
from bonito.trading.paper import PaperLedger, ledger_path_for_mode

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(
    title="Bonito Live Dashboard",
    description="Read-only view of the live/paper trading account",
    version="0.1.0",
)


@app.get("/api/state")
def get_state() -> dict:
    """Full dashboard state: account, positions, regime, fills, equity curve."""
    universe = UniverseConfig.load(DEFAULT_UNIVERSE_PATH)
    ledger = PaperLedger.load_or_create(
        ledger_path_for_mode(universe.mode),
        starting_cash=universe.risk.starting_cash_usd,
    )
    store = MarketDataStore()
    try:
        return build_dashboard_state(universe, ledger, store)
    finally:
        store.close()


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")
