export const CHAT_MODE_STORAGE_KEY = "nl2sparql_chat_mode_enabled";
export const CHAT_MODE_EVENT = "nl2sparql:chat-mode-changed";

export function readChatModeFromStorage(): boolean {
  if (typeof window === "undefined") {
    return false;
  }
  return window.localStorage.getItem(CHAT_MODE_STORAGE_KEY) === "1";
}

export function writeChatModeToStorage(enabled: boolean): void {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(CHAT_MODE_STORAGE_KEY, enabled ? "1" : "0");
  window.dispatchEvent(
    new CustomEvent<boolean>(CHAT_MODE_EVENT, { detail: enabled }),
  );
}
