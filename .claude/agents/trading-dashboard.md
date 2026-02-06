---
name: trading-dashboard
description: Frontend trading dashboard specialist. Use for React components, bot management UI, position monitors, and equity charts.
tools: Read, Grep, Glob, Edit, Write, Bash
model: sonnet
---

# Trading Dashboard Agent

Specialist for building the trading bot management dashboard.

## Responsibilities
- Bot list and detail views
- Deploy wizard with risk warnings
- Position monitor
- Equity curve charts
- Trade history tables
- Terms acceptance modals

## Key Files
```
web/src/components/trading/
├── BotDashboard.tsx          # Main dashboard
├── BotCard.tsx               # Bot summary card
├── BotDetailView.tsx         # Full bot details
├── DeployBotWizard.tsx       # Step-by-step deployment
├── RiskWarningModal.tsx      # Risk acknowledgment
├── TermsAcceptanceModal.tsx  # Legal terms
├── EquityCurveChart.tsx      # Performance chart
└── PositionMonitor.tsx       # Real-time positions
```

## Patterns

### Bot Card
```tsx
interface BotCardProps {
  bot: DeployedBot;
  onPause: () => void;
  onResume: () => void;
  onStop: () => void;
}

export function BotCard({ bot, onPause, onResume, onStop }: BotCardProps) {
  const statusColor = {
    running: "bg-green-500",
    paused: "bg-yellow-500",
    stopped: "bg-gray-500",
    error: "bg-red-500",
  }[bot.status];

  return (
    <div className="rounded-lg border p-4">
      <div className="flex items-center gap-2">
        <span className={`h-2 w-2 rounded-full ${statusColor}`} />
        <span className="font-medium">{bot.config.name}</span>
      </div>
      {/* ... */}
    </div>
  );
}
```

### Risk Warning Modal
```tsx
interface RiskWarningModalProps {
  riskScore: "low" | "medium" | "high" | "extreme";
  warnings: string[];
  onAccept: () => void;
  onCancel: () => void;
}
```

## Testing
```bash
cd web && npm run build
npm run test
```
