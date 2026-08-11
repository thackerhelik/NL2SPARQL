import {
  type Dispatch,
  type RefObject,
  type SetStateAction,
  memo,
} from "react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Alert, AlertDescription } from "@/components/ui/alert";

export type ChatRole = "user" | "agent" | "tool" | "system" | "progress";

export interface ChatPanelMessage {
  id: string;
  role: ChatRole;
  text: string;
}

export interface ChatPanelViewProps {
  currentStatus: string;
  messages: ChatPanelMessage[];
  pendingRetryQuery: boolean;
  retryQueryGeneration: () => void;
  quickPrefillActions: ReadonlyArray<{ label: string; value: string }>;
  prefillMessage: (value: string) => void;
  isInputLocked: boolean;
  messageInputRef: RefObject<HTMLTextAreaElement | null>;
  question: string;
  setQuestion: Dispatch<SetStateAction<string>>;
  sendQuestion: () => void;
}

const roleClassMap: Record<ChatRole, string> = {
  user: "bg-blue-50 text-blue-900",
  tool: "bg-gray-100 text-gray-600 text-xs",
  progress: "bg-gray-100 text-gray-600 text-xs",
  agent: "bg-emerald-50 text-emerald-900",
  system: "bg-amber-50 text-amber-900",
};

export const ChatPanelView = memo(function ChatPanelView({
  currentStatus,
  messages,
  pendingRetryQuery,
  retryQueryGeneration,
  quickPrefillActions,
  prefillMessage,
  isInputLocked,
  messageInputRef,
  question,
  setQuestion,
  sendQuestion,
}: ChatPanelViewProps) {
  return (
    <aside className="h-fit self-start w-full rounded-xl border border-gray-200 bg-white shadow-sm">
      <div className="border-b border-gray-100 px-4 py-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-gray-900">Agent Chat</h2>
        </div>
        <p className="mt-1 text-xs text-gray-500">
          Ask in natural language. Confirm moves to next step; typed messages
          are agent suggestions.
        </p>
        <p className="mt-2 text-xs text-gray-600">Status: {currentStatus}</p>
      </div>

      <div className="max-h-[45vh] min-h-[280px] space-y-2 overflow-y-auto px-4 py-3">
        {messages.length === 0 ? (
          <p className="text-sm text-gray-400">No messages yet.</p>
        ) : (
          messages.map((msg) => (
            <div
              key={msg.id}
              className={`whitespace-pre-wrap rounded-md px-3 py-2 text-sm ${roleClassMap[msg.role]}`}
            >
              {msg.text}
            </div>
          ))
        )}
      </div>

      <div className="space-y-2 border-t border-gray-100 px-4 py-3">
        {pendingRetryQuery && (
          <Alert variant="destructive" className="border-red-200 bg-red-50">
            <AlertDescription className="text-xs text-red-900">
              Query generation failed due to iteration limit. Retry immediately
              from the same linked entities.
            </AlertDescription>
            <div className="mt-2 flex gap-2">
              <Button
                type="button"
                className="flex-1"
                onClick={retryQueryGeneration}
              >
                Try Again
              </Button>
            </div>
          </Alert>
        )}

        <div className="flex flex-wrap gap-2">
          {quickPrefillActions.map((action) => (
            <Button
              key={action.value}
              type="button"
              variant="outline"
              size="sm"
              onClick={() => prefillMessage(action.value)}
              disabled={isInputLocked}
            >
              {action.label}
            </Button>
          ))}
        </div>

        <Textarea
          ref={messageInputRef}
          className="min-h-20"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Write a message to the agent..."
          disabled={isInputLocked}
        />

        <Button
          className="w-full"
          onClick={sendQuestion}
          disabled={isInputLocked}
        >
          {isInputLocked ? "Running..." : "Send Message to Agent"}
        </Button>
      </div>
    </aside>
  );
});
