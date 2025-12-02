"use client";

import { useState } from "react";
import Sidebar from "@/components/Sidebar";
import Chat, { Message } from "@/components/Chat";
import Strategies from "@/components/Strategies";
import Data from "@/components/Data";

type View = "chat" | "strategies" | "data";

export default function Home() {
  const [currentView, setCurrentView] = useState<View>("chat");

  // Lift chat state to preserve across view switches
  const [messages, setMessages] = useState<Message[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);

  return (
    <div className="flex h-screen">
      <Sidebar currentView={currentView} onViewChange={setCurrentView} />
      <main className="flex-1 overflow-hidden">
        {currentView === "chat" && (
          <Chat
            messages={messages}
            setMessages={setMessages}
            sessionId={sessionId}
            setSessionId={setSessionId}
          />
        )}
        {currentView === "strategies" && <Strategies />}
        {currentView === "data" && <Data />}
      </main>
    </div>
  );
}
