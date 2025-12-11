"""Tests for ChartControlTool - Agent chart manipulation capabilities."""

import pytest

from bonito.agent.tools import ChartControlTool


@pytest.fixture
def tool() -> ChartControlTool:
    """Create a ChartControlTool instance."""
    return ChartControlTool()


class TestChartControlToolMetadata:
    """Tests for tool metadata."""

    def test_tool_name(self, tool: ChartControlTool) -> None:
        """Tool has correct name."""
        assert tool.name == "chart_control"

    def test_tool_description(self, tool: ChartControlTool) -> None:
        """Tool has informative description."""
        assert "chart" in tool.description.lower()
        assert "indicator" in tool.description.lower()

    def test_parameters_schema(self, tool: ChartControlTool) -> None:
        """Tool has valid parameter schema."""
        params = tool.parameters
        assert params["type"] == "object"
        assert "action" in params["properties"]
        assert params["required"] == ["action"]


class TestAddIndicator:
    """Tests for add_indicator action."""

    @pytest.mark.asyncio
    async def test_add_sma(self, tool: ChartControlTool) -> None:
        """Add SMA indicator returns correct intent."""
        result = await tool.execute(
            action="add_indicator",
            indicator_type="sma",
            indicator_params={"period": 20},
        )

        assert result.success
        assert result.data is not None
        assert "intent" in result.data
        intent = result.data["intent"]
        assert intent["type"] == "overlay"
        assert intent["indicator"]["type"] == "sma"
        assert intent["indicator"]["name"] == "SMA(20)"
        assert intent["indicator"]["params"]["period"] == 20
        assert intent["indicator"]["visible"] is True

    @pytest.mark.asyncio
    async def test_add_ema(self, tool: ChartControlTool) -> None:
        """Add EMA indicator returns correct intent."""
        result = await tool.execute(
            action="add_indicator",
            indicator_type="ema",
            indicator_params={"period": 12},
        )

        assert result.success
        intent = result.data["intent"]
        assert intent["indicator"]["name"] == "EMA(12)"

    @pytest.mark.asyncio
    async def test_add_rsi(self, tool: ChartControlTool) -> None:
        """Add RSI indicator returns correct intent."""
        result = await tool.execute(
            action="add_indicator",
            indicator_type="rsi",
            indicator_params={"period": 14},
        )

        assert result.success
        intent = result.data["intent"]
        assert intent["indicator"]["name"] == "RSI(14)"

    @pytest.mark.asyncio
    async def test_add_bbands(self, tool: ChartControlTool) -> None:
        """Add Bollinger Bands returns correct intent."""
        result = await tool.execute(
            action="add_indicator",
            indicator_type="bbands",
            indicator_params={"period": 20},
        )

        assert result.success
        intent = result.data["intent"]
        assert intent["indicator"]["name"] == "BB(20)"

    @pytest.mark.asyncio
    async def test_add_indicator_missing_type(self, tool: ChartControlTool) -> None:
        """Add indicator without type fails."""
        result = await tool.execute(action="add_indicator")

        assert not result.success
        assert "indicator_type" in result.error


class TestAnnotate:
    """Tests for annotate action."""

    @pytest.mark.asyncio
    async def test_annotate_arrow(self, tool: ChartControlTool) -> None:
        """Annotate with arrow returns correct intent."""
        result = await tool.execute(
            action="annotate",
            annotation_type="arrow",
            timestamp="2024-03-15",
            annotation_text="Entry signal!",
        )

        assert result.success
        intent = result.data["intent"]
        assert intent["type"] == "annotate"
        assert intent["annotation"]["text"] == "Entry signal!"
        assert intent["annotation"]["icon"] == "signal"

    @pytest.mark.asyncio
    async def test_annotate_label_with_price(self, tool: ChartControlTool) -> None:
        """Annotate with label at price level returns correct intent."""
        result = await tool.execute(
            action="annotate",
            annotation_type="label",
            timestamp="2024-03-15",
            annotation_text="Resistance",
            price=450.0,
        )

        assert result.success
        intent = result.data["intent"]
        assert intent["annotation"]["price"] == 450.0
        assert intent["annotation"]["icon"] == "info"

    @pytest.mark.asyncio
    async def test_annotate_missing_timestamp(self, tool: ChartControlTool) -> None:
        """Annotate without timestamp fails."""
        result = await tool.execute(
            action="annotate",
            annotation_type="arrow",
            annotation_text="Test",
        )

        assert not result.success
        assert "timestamp" in result.error


class TestHighlight:
    """Tests for highlight action."""

    @pytest.mark.asyncio
    async def test_highlight_region(self, tool: ChartControlTool) -> None:
        """Highlight region returns correct intent."""
        result = await tool.execute(
            action="highlight",
            start_date="2024-03-01",
            end_date="2024-04-15",
            highlight_color="red",
        )

        assert result.success
        intent = result.data["intent"]
        assert intent["type"] == "highlight"
        assert "highlightRange" in intent
        assert intent["highlightRange"]["color"] == "rgba(239, 68, 68, 0.2)"

    @pytest.mark.asyncio
    async def test_highlight_default_color(self, tool: ChartControlTool) -> None:
        """Highlight with default color returns yellow."""
        result = await tool.execute(
            action="highlight",
            start_date="2024-03-01",
            end_date="2024-04-15",
        )

        assert result.success
        intent = result.data["intent"]
        assert "255, 193, 7" in intent["highlightRange"]["color"]  # yellow

    @pytest.mark.asyncio
    async def test_highlight_missing_dates(self, tool: ChartControlTool) -> None:
        """Highlight without dates fails."""
        result = await tool.execute(action="highlight", start_date="2024-03-01")

        assert not result.success
        assert "end_date" in result.error


class TestNavigate:
    """Tests for navigate action."""

    @pytest.mark.asyncio
    async def test_navigate_to_range(self, tool: ChartControlTool) -> None:
        """Navigate to date range returns correct intent."""
        result = await tool.execute(
            action="navigate",
            start_date="2024-01-01",
            end_date="2024-03-31",
        )

        assert result.success
        intent = result.data["intent"]
        assert intent["type"] == "navigate"
        assert "range" in intent
        assert intent["range"]["start"] < intent["range"]["end"]

    @pytest.mark.asyncio
    async def test_navigate_to_timestamp(self, tool: ChartControlTool) -> None:
        """Navigate to specific timestamp returns correct intent."""
        result = await tool.execute(
            action="navigate",
            timestamp="2024-03-15",
        )

        assert result.success
        intent = result.data["intent"]
        assert intent["type"] == "navigate"
        assert "timestamp" in intent

    @pytest.mark.asyncio
    async def test_navigate_missing_params(self, tool: ChartControlTool) -> None:
        """Navigate without parameters fails."""
        result = await tool.execute(action="navigate")

        assert not result.success
        assert "timestamp" in result.error or "date" in result.error


class TestClear:
    """Tests for clear action."""

    @pytest.mark.asyncio
    async def test_clear_annotations(self, tool: ChartControlTool) -> None:
        """Clear annotations returns correct intent."""
        result = await tool.execute(action="clear", clear_type="annotations")

        assert result.success
        intent = result.data["intent"]
        assert intent["type"] == "clear"
        assert intent["clearType"] == "annotations"

    @pytest.mark.asyncio
    async def test_clear_indicators(self, tool: ChartControlTool) -> None:
        """Clear indicators returns correct intent."""
        result = await tool.execute(action="clear", clear_type="indicators")

        assert result.success
        intent = result.data["intent"]
        assert intent["clearType"] == "indicators"

    @pytest.mark.asyncio
    async def test_clear_all(self, tool: ChartControlTool) -> None:
        """Clear all returns correct intent."""
        result = await tool.execute(action="clear", clear_type="all")

        assert result.success
        intent = result.data["intent"]
        assert intent["clearType"] == "all"

    @pytest.mark.asyncio
    async def test_clear_default(self, tool: ChartControlTool) -> None:
        """Clear without type defaults to all."""
        result = await tool.execute(action="clear")

        assert result.success
        intent = result.data["intent"]
        assert intent["clearType"] == "all"


class TestRemoveIndicator:
    """Tests for remove_indicator action."""

    @pytest.mark.asyncio
    async def test_remove_indicator(self, tool: ChartControlTool) -> None:
        """Remove indicator returns correct intent."""
        result = await tool.execute(
            action="remove_indicator",
            indicator_name="RSI(14)",
        )

        assert result.success
        intent = result.data["intent"]
        assert intent["type"] == "clear"
        assert intent["indicatorName"] == "RSI(14)"

    @pytest.mark.asyncio
    async def test_remove_indicator_missing_name(self, tool: ChartControlTool) -> None:
        """Remove indicator without name fails."""
        result = await tool.execute(action="remove_indicator")

        assert not result.success
        assert "indicator_name" in result.error


class TestUnknownAction:
    """Tests for unknown actions."""

    @pytest.mark.asyncio
    async def test_unknown_action_fails(self, tool: ChartControlTool) -> None:
        """Unknown action fails gracefully."""
        result = await tool.execute(action="teleport")

        assert not result.success
        assert "Unknown action" in result.error
