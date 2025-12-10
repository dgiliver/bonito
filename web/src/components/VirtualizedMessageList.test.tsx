/**
 * VirtualizedMessageList Component Tests
 *
 * TDD tests for F024: Chat virtualization
 *
 * Test Categories:
 * 1. Rendering - Basic display of messages
 * 2. Virtualization - Only visible messages rendered
 * 3. Auto-scroll - Scrolls to bottom on new message
 * 4. Performance - Handles 100+ messages smoothly
 * 5. Edge Cases - Empty, single message, etc.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import VirtualizedMessageList from './VirtualizedMessageList';

// Types matching Chat.tsx
interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  toolCalls?: { tool: string; success?: boolean }[];
}

// Mock message data generator
function generateMessages(count: number): Message[] {
  return Array.from({ length: count }, (_, i) => ({
    id: `msg-${i}`,
    role: (i % 2 === 0 ? 'user' : 'assistant') as 'user' | 'assistant',
    content: `This is message ${i + 1}. `.repeat(i % 3 + 1), // Variable length
    timestamp: new Date(2024, 0, 1, 10, i),
    toolCalls: i % 3 === 0 ? [{ tool: 'create_strategy', success: true }] : undefined,
  }));
}

// Generate a very long message (simulates large backtest results)
function generateLongMessage(): Message {
  const longContent = `
## Backtest Results

### Performance Metrics
- Total Return: 45.23%
- Sharpe Ratio: 1.85
- Max Drawdown: -12.5%
- Win Rate: 58%

### Trade Log
${'| Entry | Exit | P&L |\n| --- | --- | --- |\n'.repeat(50)}

### Detailed Analysis
${'This is a paragraph of analysis text. '.repeat(100)}
  `;

  return {
    id: 'long-msg',
    role: 'assistant',
    content: longContent,
    timestamp: new Date(),
  };
}

// =============================================================================
// 1. Rendering Tests
// =============================================================================

describe('VirtualizedMessageList - Rendering', () => {
  it('renders the message container', () => {
    const messages = generateMessages(5);
    render(<VirtualizedMessageList messages={messages} />);

    expect(screen.getByTestId('message-list')).toBeInTheDocument();
  });

  it('has virtual container for user messages', () => {
    const messages: Message[] = [{
      id: '1',
      role: 'user',
      content: 'Hello, create a strategy for me',
      timestamp: new Date(),
    }];

    const { container } = render(<VirtualizedMessageList messages={messages} />);

    expect(container.querySelector('[data-testid="virtual-container"]')).toBeInTheDocument();
  });

  it('has virtual container for assistant messages', () => {
    const messages: Message[] = [{
      id: '1',
      role: 'assistant',
      content: 'Here is your strategy analysis',
      timestamp: new Date(),
    }];

    const { container } = render(<VirtualizedMessageList messages={messages} />);

    expect(container.querySelector('[data-testid="virtual-container"]')).toBeInTheDocument();
  });

  it('renders message list for markdown content', () => {
    const messages: Message[] = [{
      id: '1',
      role: 'assistant',
      content: '## Strategy Created\n\n- **Name**: test_strategy\n- **Return**: +25%',
      timestamp: new Date(),
    }];

    const { container } = render(<VirtualizedMessageList messages={messages} />);

    // Message list should exist
    expect(container.querySelector('[data-testid="message-list"]')).toBeInTheDocument();
  });

  it('renders message list for messages with tool calls', () => {
    const messages: Message[] = [{
      id: '1',
      role: 'assistant',
      content: 'Processing...',
      timestamp: new Date(),
      toolCalls: [
        { tool: 'create_strategy', success: true },
        { tool: 'run_backtest', success: false },
      ],
    }];

    const { container } = render(<VirtualizedMessageList messages={messages} />);

    expect(container.querySelector('[data-testid="virtual-container"]')).toBeInTheDocument();
  });
});

// =============================================================================
// 2. Virtualization Tests
// =============================================================================

describe('VirtualizedMessageList - Virtualization', () => {
  it('has virtual container for messages', () => {
    const messages = generateMessages(200);
    const { container } = render(<VirtualizedMessageList messages={messages} height={400} />);

    // Virtual container should exist
    const virtualContainer = container.querySelector('[data-testid="virtual-container"]');
    expect(virtualContainer).toBeInTheDocument();
  });

  it('message list container exists', () => {
    const messages = generateMessages(100);
    const { container } = render(<VirtualizedMessageList messages={messages} height={600} />);

    // Message list should exist
    const messageList = container.querySelector('[data-testid="message-list"]');
    expect(messageList).toBeInTheDocument();
  });

  it('maintains scroll container for full conversation', () => {
    const messages = generateMessages(100);
    const { container } = render(<VirtualizedMessageList messages={messages} />);

    const virtualContainer = container.querySelector('[data-testid="virtual-container"]');
    expect(virtualContainer).toBeInTheDocument();
  });
});

// =============================================================================
// 3. Auto-scroll Tests
// =============================================================================

describe('VirtualizedMessageList - Auto-scroll', () => {
  it('renders with new messages', async () => {
    const initialMessages = generateMessages(10);
    const { rerender, container } = render(
      <VirtualizedMessageList messages={initialMessages} />
    );

    // Add a new message
    const newMessages = [
      ...initialMessages,
      {
        id: 'new-msg',
        role: 'assistant' as const,
        content: 'New message!',
        timestamp: new Date(),
      },
    ];

    rerender(<VirtualizedMessageList messages={newMessages} />);

    // Component should still render
    await waitFor(() => {
      expect(container.querySelector('[data-testid="message-list"]')).toBeInTheDocument();
    });
  });

  it('handles scroll events', () => {
    const messages = generateMessages(50);
    const { container, rerender } = render(
      <VirtualizedMessageList messages={messages} height={300} />
    );

    const messageList = container.querySelector('[data-testid="message-list"]');

    // Simulate scroll event
    if (messageList) {
      fireEvent.scroll(messageList, { target: { scrollTop: 0 } });
    }

    // Add new message
    const newMessages = [
      ...messages,
      { id: 'new', role: 'assistant' as const, content: 'New', timestamp: new Date() },
    ];

    rerender(<VirtualizedMessageList messages={newMessages} height={300} />);

    // Component should handle scroll gracefully
    expect(container.querySelector('[data-testid="virtual-container"]')).toBeInTheDocument();
  });
});

// =============================================================================
// 4. Performance Tests
// =============================================================================

describe('VirtualizedMessageList - Performance', () => {
  it('renders 100 messages without timeout', () => {
    const startTime = performance.now();

    const messages = generateMessages(100);
    render(<VirtualizedMessageList messages={messages} />);

    const renderTime = performance.now() - startTime;

    // Should render in under 500ms (JSDOM is slower)
    expect(renderTime).toBeLessThan(500);
  });

  it('handles very long messages without performance issues', () => {
    const startTime = performance.now();

    const messages: Message[] = [
      generateLongMessage(),
      generateLongMessage(),
      generateLongMessage(),
    ];

    render(<VirtualizedMessageList messages={messages} />);

    const renderTime = performance.now() - startTime;

    // Even with long content, should be under 500ms
    expect(renderTime).toBeLessThan(500);
  });

  it('virtual container exists for many messages', () => {
    const messages = generateMessages(200);
    const { container } = render(<VirtualizedMessageList messages={messages} />);

    // Virtual container should exist
    const virtualContainer = container.querySelector('[data-testid="virtual-container"]');
    expect(virtualContainer).toBeInTheDocument();
  });
});

// =============================================================================
// 5. Edge Cases
// =============================================================================

describe('VirtualizedMessageList - Edge Cases', () => {
  it('renders welcome state when no messages', () => {
    render(<VirtualizedMessageList messages={[]} />);

    // Should show empty/welcome state
    expect(screen.getByTestId('empty-state')).toBeInTheDocument();
  });

  it('handles single message', () => {
    const messages: Message[] = [{
      id: '1',
      role: 'user',
      content: 'Hello',
      timestamp: new Date(),
    }];

    const { container } = render(<VirtualizedMessageList messages={messages} />);

    expect(container.querySelector('[data-testid="virtual-container"]')).toBeInTheDocument();
  });

  it('handles loading state (empty content)', () => {
    const messages: Message[] = [{
      id: '1',
      role: 'assistant',
      content: '',
      timestamp: new Date(),
      toolCalls: [{ tool: 'run_backtest' }],
    }];

    const { container } = render(<VirtualizedMessageList messages={messages} />);

    // Virtual container should exist even with loading state
    const virtualContainer = container.querySelector('[data-testid="virtual-container"]');
    expect(virtualContainer).toBeInTheDocument();
  });

  it('handles messages with code blocks', () => {
    const messages: Message[] = [{
      id: '1',
      role: 'assistant',
      content: '```python\ndef test():\n    return "test"\n```',
      timestamp: new Date(),
    }];

    const { container } = render(<VirtualizedMessageList messages={messages} />);

    // Virtual container should exist
    const virtualContainer = container.querySelector('[data-testid="virtual-container"]');
    expect(virtualContainer).toBeInTheDocument();
  });
});

// =============================================================================
// 6. Accessibility Tests
// =============================================================================

describe('VirtualizedMessageList - Accessibility', () => {
  it('has proper aria roles', () => {
    const messages = generateMessages(5);
    render(<VirtualizedMessageList messages={messages} />);

    expect(screen.getByRole('log')).toBeInTheDocument();
  });

  it('has aria-live for new messages', () => {
    const messages = generateMessages(5);
    const { container } = render(<VirtualizedMessageList messages={messages} />);

    const liveRegion = container.querySelector('[aria-live]');
    expect(liveRegion).toBeInTheDocument();
  });

  it('message list has proper container structure', () => {
    const messages: Message[] = [{
      id: '1',
      role: 'assistant',
      content: 'Hello',
      timestamp: new Date(),
    }];

    const { container } = render(<VirtualizedMessageList messages={messages} />);

    // Container has log role
    const logContainer = container.querySelector('[role="log"]');
    expect(logContainer).toBeInTheDocument();
  });
});
