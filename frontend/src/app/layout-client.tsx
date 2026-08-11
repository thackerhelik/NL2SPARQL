"use client";

import { ReactNode, useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { History, Settings } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  CHAT_MODE_EVENT,
  readChatModeFromStorage,
  writeChatModeToStorage,
} from "@/lib/chat-mode";

export default function RootLayoutClient({
  children,
}: Readonly<{
  children: ReactNode;
}>) {
  const pathname = usePathname();
  const [chatModeEnabled, setChatModeEnabled] = useState(false);

  useEffect(() => {
    const sync = () => {
      setChatModeEnabled(readChatModeFromStorage());
    };

    const onStorage = () => {
      sync();
    };

    const onChatModeChanged = (event: Event) => {
      const customEvent = event as CustomEvent<boolean>;
      if (typeof customEvent.detail === "boolean") {
        setChatModeEnabled(customEvent.detail);
        return;
      }
      sync();
    };

    sync();
    window.addEventListener("storage", onStorage);
    window.addEventListener(CHAT_MODE_EVENT, onChatModeChanged);
    return () => {
      window.removeEventListener("storage", onStorage);
      window.removeEventListener(CHAT_MODE_EVENT, onChatModeChanged);
    };
  }, []);

  const toggleChatMode = () => {
    writeChatModeToStorage(!chatModeEnabled);
  };

  const showChatToggle = pathname === "/";

  return (
    <>
      <header className="w-full border-b bg-gray-100">
        <div className="max-w-4xl mx-auto px-4 h-12 flex items-center justify-between">
          <Link
            href="/"
            className="font-semibold text-gray-900 hover:text-gray-700"
          >
            NL2SPARQL
          </Link>
          <div className="flex items-center gap-4">
            {showChatToggle && (
              <Button
                variant={chatModeEnabled ? "default" : "outline"}
                size="sm"
                onClick={toggleChatMode}
              >
                {chatModeEnabled ? "Disable Chat" : "Enable Chat"}
              </Button>
            )}
            <Link
              href="/history"
              className="flex items-center gap-1.5 text-sm text-gray-600 hover:text-gray-900"
            >
              <History className="w-4 h-4" />
              History
            </Link>
            <Link
              href="/settings"
              className="flex items-center gap-1.5 text-sm text-gray-600 hover:text-gray-900"
            >
              <Settings className="w-4 h-4" />
              Settings
            </Link>
          </div>
        </div>
      </header>
      {children}
    </>
  );
}
