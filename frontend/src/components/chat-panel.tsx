"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { DetailedMention, SparqlResponse } from "@/lib/types";
import {
  ChatPanelView,
  type ChatPanelMessage,
} from "@/components/chat-panel-view";

type MentionWithSelection = DetailedMention & {
  selectedCandidate?: { uri: string };
};

type Role = ChatPanelMessage["role"];

interface ChatPanelProps {
  schemaId: string;
  model: string;
  currentQuestion?: string | null;
  currentQuery?: string | null;
  querySyncNonce?: number;
  currentQueryResult?: SparqlResponse | null;
  externalQuestion?: string | null;
  externalMentions?: DetailedMention[] | null;
  onQuestionSubmitted?: (question: string) => void;
  onMentionsDetected?: (mentions: DetailedMention[]) => void;
  onGeneratedQuery?: (query: string) => void;
  onQueryResult?: (result: SparqlResponse) => void;
}

interface LinkedMentionPayload {
  text: string;
  type: string;
  label_pred: string;
  attrs: Record<string, string>;
  iri: string;
}

interface SetMentionsPayload {
  type: "set_mentions";
  mentions: Array<{
    text: string;
    type: string;
    label_pred: string;
    attrs: Record<string, string>;
    selected_candidate_iri?: string;
  }>;
}

type MentionsSyncDecision = "skip_ack" | "skip_duplicate" | "send";

const MAX_RECONNECT_ATTEMPTS = 4;
const BASE_RECONNECT_DELAY_MS = 800;
const WS_DIAG_PREFIX = "[agent_ws_diag]";
const WS_DEBUG_ENABLED = process.env.NEXT_PUBLIC_AGENT_WS_DEBUG === "1";

function logWsDiag(event: string, details?: Record<string, unknown>) {
  if (!WS_DEBUG_ENABLED) {
    return;
  }
  console.info(WS_DIAG_PREFIX, event, details || {});
}

function buildWsUrl(): string {
  const configured = process.env.NEXT_PUBLIC_WS_URL;
  if (configured) {
    if (configured.startsWith("ws://") || configured.startsWith("wss://")) {
      return configured.endsWith("/")
        ? `${configured}agent/ws`
        : `${configured}/agent/ws`;
    }

    if (configured.startsWith("http://") || configured.startsWith("https://")) {
      const parsedConfigured = new URL(configured);
      parsedConfigured.protocol =
        parsedConfigured.protocol === "https:" ? "wss:" : "ws:";
      parsedConfigured.pathname = `${parsedConfigured.pathname.replace(/\/$/, "")}/agent/ws`;
      return parsedConfigured.toString();
    }

    if (configured.startsWith("/")) {
      const proto = window.location.protocol === "https:" ? "wss" : "ws";
      const basePath = configured.replace(/\/$/, "");
      return `${proto}://${window.location.host}${basePath}/agent/ws`;
    }
  }

  const apiBase = process.env.NEXT_PUBLIC_API_URL || "/api";
  if (apiBase.startsWith("http://") || apiBase.startsWith("https://")) {
    const parsed = new URL(apiBase);
    parsed.protocol = parsed.protocol === "https:" ? "wss:" : "ws:";
    parsed.pathname = `${parsed.pathname.replace(/\/$/, "")}/agent/ws`;
    return parsed.toString();
  }

  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  const basePath = apiBase.startsWith("/") ? apiBase : "/api";
  return `${proto}://${window.location.host}${basePath.replace(/\/$/, "")}/agent/ws`;
}

export function ChatPanel({
  schemaId,
  model,
  currentQuestion,
  currentQuery,
  querySyncNonce = 0,
  currentQueryResult,
  externalQuestion,
  externalMentions,
  onQuestionSubmitted,
  onMentionsDetected,
  onGeneratedQuery,
  onQueryResult,
}: ChatPanelProps) {
  const messageInputRef = useRef<HTMLTextAreaElement | null>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const reconnectingRef = useRef(false);
  const reconnectAttemptRef = useRef(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastBackendMentionsSignatureRef = useRef<string | null>(null);
  const pendingBackendMentionsAckSignatureRef = useRef<string | null>(null);
  const initialRestoreSentRef = useRef(false);
  const latestMentionsRef = useRef<DetailedMention[] | null>(null);
  const latestQueryRef = useRef<string | null>(null);
  const latestResultRef = useRef<SparqlResponse | null>(null);
  const sessionStartedRef = useRef(false);
  const [messages, setMessages] = useState<ChatPanelMessage[]>([]);
  const [question, setQuestion] = useState("");
  const [isConnected, setIsConnected] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [pendingRetryQuery, setPendingRetryQuery] = useState(false);
  const [sessionStarted, setSessionStarted] = useState(false);
  const [currentStatus, setCurrentStatus] = useState("Idle");
  const [isProcessing, setIsProcessing] = useState(false);
  const [lastStartQuestion, setLastStartQuestion] = useState<string | null>(
    null,
  );

  const wsUrl = useMemo(() => buildWsUrl(), []);
  const isInputLocked = isProcessing || isSending;

  const pushProgress = (text: string) => {
    const message = text.trim();
    if (!message) {
      return;
    }
    pushMessage("progress", message);
  };

  const pushMessage = (role: Role, text: string) => {
    setMessages((prev) => [
      ...prev,
      { id: `${Date.now()}-${Math.random()}`, role, text },
    ]);
  };

  const clearReconnectTimer = () => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
  };

  const sendWhenSocketReady = (socket: WebSocket, send: () => void) => {
    if (socket.readyState === WebSocket.OPEN) {
      send();
      return;
    }

    socket.addEventListener("open", send, { once: true });
  };

  const mentionsSignature = (
    mentions: DetailedMention[] | null | undefined,
  ) => {
    if (!mentions || mentions.length === 0) {
      return "[]";
    }
    return JSON.stringify(
      mentions.map((mention) => ({
        text: mention.text,
        type: mention.type,
        label_pred: mention.label_pred,
        attrs: mention.attrs || {},
        selected_candidate_iri:
          (mention as MentionWithSelection).selected_candidate_iri ||
          (mention as MentionWithSelection).selectedCandidate?.uri ||
          null,
      })),
    );
  };

  const buildLinkedMentionsFromMentions = (
    mentions: DetailedMention[] | null | undefined,
  ): LinkedMentionPayload[] => {
    if (!mentions || mentions.length === 0) {
      return [];
    }

    return mentions
      .map((mention) => {
        if (!mention.candidates || mention.candidates.length === 0) {
          return null;
        }
        const selectedIri =
          (mention as MentionWithSelection).selected_candidate_iri ||
          (mention as MentionWithSelection).selectedCandidate?.uri ||
          null;
        const selectedCandidate = selectedIri
          ? mention.candidates.find(
              (candidate) => candidate.uri === selectedIri,
            )
          : null;
        const best = mention.candidates.reduce((left, right) =>
          (right.score || 0) > (left.score || 0) ? right : left,
        );
        return {
          text: mention.text,
          type: mention.type,
          label_pred: mention.label_pred,
          attrs: mention.attrs || {},
          iri: (selectedCandidate || best).uri,
        };
      })
      .filter((item): item is LinkedMentionPayload => item !== null);
  };

  const normalizeMentionsForBackend = (
    mentions: DetailedMention[] | null | undefined,
  ) => {
    if (!mentions) {
      return undefined;
    }

    return mentions.map((mention) => ({
      ...mention,
      selected_candidate_iri:
        (mention as MentionWithSelection).selected_candidate_iri ||
        (mention as MentionWithSelection).selectedCandidate?.uri ||
        undefined,
    }));
  };

  const sendSetMentionsPayload = (payload: SetMentionsPayload) => {
    const socket = ensureSocket();
    const sendNow = () => {
      logWsDiag("outgoing", {
        request_type: "set_mentions",
        mention_count: payload.mentions.length,
      });
      socket.send(JSON.stringify(payload));
    };

    sendWhenSocketReady(socket, sendNow);
  };

  const classifyMentionsSyncDecision = (
    signature: string,
  ): MentionsSyncDecision => {
    const pendingAckSignature = pendingBackendMentionsAckSignatureRef.current;
    if (pendingAckSignature) {
      if (signature === pendingAckSignature) {
        return "skip_ack";
      }
      return "send";
    }
    if (signature === lastBackendMentionsSignatureRef.current) {
      return "skip_duplicate";
    }
    return "send";
  };

  const scheduleReconnectRetry = () => {
    if (!reconnectingRef.current) {
      return;
    }

    if (reconnectAttemptRef.current >= MAX_RECONNECT_ATTEMPTS) {
      reconnectAttemptRef.current = 0;
      setCurrentStatus("Reconnect pending");
      pushMessage(
        "system",
        "Reconnect attempts exhausted. Retrying in background.",
      );
      clearReconnectTimer();
      reconnectTimerRef.current = setTimeout(() => {
        if (!reconnectingRef.current) {
          return;
        }
        ensureSocket();
      }, 5000);
      return;
    }

    const attemptNumber = reconnectAttemptRef.current + 1;
    const delay = BASE_RECONNECT_DELAY_MS * 2 ** reconnectAttemptRef.current;
    reconnectAttemptRef.current = attemptNumber;
    setCurrentStatus(
      `Reconnecting (attempt ${attemptNumber}/${MAX_RECONNECT_ATTEMPTS})`,
    );
    clearReconnectTimer();
    reconnectTimerRef.current = setTimeout(() => {
      if (!reconnectingRef.current) {
        return;
      }
      ensureSocket();
    }, delay);
  };

  const getResultSummary = () => {
    const result = latestResultRef.current;
    const hasBoolean = typeof result?.boolean === "boolean";
    const rowCount = Array.isArray(result?.results?.bindings)
      ? result.results.bindings.length
      : undefined;
    return {
      query_result_row_count: rowCount,
      query_result_boolean: hasBoolean ? result?.boolean : undefined,
      query_result_is_ask: hasBoolean,
    };
  };

  const buildRestorePayload = (
    questionToRestore: string,
    mentionsToRestore: DetailedMention[] | null | undefined,
  ) => {
    const restoreStage = mentionsToRestore?.some(
      (mention) => (mention.candidates || []).length > 0,
    )
      ? "linked_entities"
      : "mention_confirmation";

    return {
      type: "start",
      question: questionToRestore,
      schema_id: schemaId,
      model,
      current_query: latestQueryRef.current || undefined,
      has_generated_query: Boolean(latestQueryRef.current),
      detailed_mentions: normalizeMentionsForBackend(mentionsToRestore),
      linked_mentions:
        restoreStage === "linked_entities"
          ? buildLinkedMentionsFromMentions(mentionsToRestore)
          : undefined,
      ...getResultSummary(),
    };
  };

  const restoreSessionFromLocalProgress = (
    socket: WebSocket,
    mode: "reconnect" | "initial",
  ) => {
    const restoreQuestion = (lastStartQuestion || currentQuestion || "").trim();
    const latestMentions = latestMentionsRef.current;
    if (!restoreQuestion || !latestMentions || latestMentions.length === 0) {
      return false;
    }

    const restorePayload = buildRestorePayload(restoreQuestion, latestMentions);
    const restoreStage = latestMentions.some(
      (mention) => (mention.candidates || []).length > 0,
    )
      ? "linked_entities"
      : "mention_confirmation";
    logWsDiag("outgoing", {
      request_type: "start",
      mode,
      restore_stage: restoreStage,
      mention_count: latestMentions.length,
      has_query: Boolean(latestQueryRef.current),
    });
    socket.send(JSON.stringify(restorePayload));
    setIsSending(true);
    setLastStartQuestion(restoreQuestion);
    setSessionStarted(true);
    setCurrentStatus(
      mode === "reconnect"
        ? "Reconnected: restoring session"
        : "Connected: restoring session",
    );
    if (mode === "initial") {
      initialRestoreSentRef.current = true;
    }
    return true;
  };

  const ensureSocket = () => {
    if (
      socketRef.current &&
      (socketRef.current.readyState === WebSocket.OPEN ||
        socketRef.current.readyState === WebSocket.CONNECTING)
    ) {
      return socketRef.current;
    }

    const socket = new WebSocket(wsUrl);
    socketRef.current = socket;

    socket.onopen = () => {
      logWsDiag("socket_open", { reconnecting: reconnectingRef.current });
      setIsConnected(true);
      clearReconnectTimer();
      reconnectAttemptRef.current = 0;
      if (reconnectingRef.current) {
        const restored = restoreSessionFromLocalProgress(socket, "reconnect");
        setIsProcessing(restored);
        reconnectingRef.current = false;
        if (restored) {
          return;
        }
      }

      const hasAutoRestorableContext = Boolean(
        !initialRestoreSentRef.current &&
        !sessionStarted &&
        currentQuestion &&
        latestMentionsRef.current &&
        latestMentionsRef.current.length > 0,
      );
      if (hasAutoRestorableContext) {
        const restored = restoreSessionFromLocalProgress(socket, "initial");
        if (restored) {
          setIsProcessing(true);
          reconnectingRef.current = false;
          return;
        }
      }

      if (reconnectingRef.current) {
        reconnectingRef.current = false;
      }

      setCurrentStatus("Connected");
      setIsProcessing(false);
      reconnectingRef.current = false;
    };

    socket.onclose = () => {
      const hasSessionStarted = sessionStartedRef.current;
      logWsDiag("socket_close", { session_started: hasSessionStarted });
      setIsConnected(false);
      setIsSending(false);
      setCurrentStatus("Disconnected");
      setIsProcessing(false);
      if (hasSessionStarted) {
        reconnectingRef.current = true;
        scheduleReconnectRetry();
      }
    };

    socket.onerror = () => {
      logWsDiag("socket_error");
    };

    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as {
          type: string;
          payload: Record<string, unknown>;
        };
        logWsDiag("incoming", {
          event_type: data.type,
          phase_name: data.payload?.name,
          phase_status: data.payload?.status,
          stage: data.payload?.stage,
          error_type: data.payload?.error_type,
        });

        if (data.type === "connection") {
          const status = String(data.payload?.status || "ready");
          setCurrentStatus(status === "ready" ? "Connected" : status);
          setIsSending(false);
          setIsProcessing(false);
          return;
        }

        if (data.type === "stage_context") {
          const stage = String(data.payload?.stage || "");
          const stageLabel = stage ? stage.replaceAll("_", " ") : "stage";
          const note = String(data.payload?.note || "").trim();
          if (note) {
            pushProgress(`${stageLabel}: ${note}`);
          } else {
            const notes = data.payload?.notes;
            if (Array.isArray(notes) && notes.length > 0) {
              const latest = String(notes[notes.length - 1] || "").trim();
              if (latest) {
                pushProgress(`${stageLabel}: ${latest}`);
              }
            }
          }
          return;
        }

        if (data.type === "agent_decision") {
          return;
        }

        if (data.type === "final_query") {
          const query = String(data.payload?.query || "");
          latestQueryRef.current = query;
          setPendingRetryQuery(false);
          onGeneratedQuery?.(query);
          pushMessage("agent", `Generated SPARQL query.\n${query}`);
          setIsProcessing(false);
          return;
        }

        if (data.type === "query_result") {
          setPendingRetryQuery(false);
          onQueryResult?.(data.payload as unknown as SparqlResponse);
          pushProgress("query execution: finished");
          setCurrentStatus("Completed");
          setIsSending(false);
          setIsProcessing(false);
          return;
        }

        if (data.type === "query_synced") {
          const syncedQuery = String(data.payload?.current_query || "");
          latestQueryRef.current = syncedQuery || null;
          pushMessage(
            "agent",
            syncedQuery
              ? "Query synced with backend."
              : "Query cleared in backend session.",
          );
          return;
        }

        if (data.type === "mentions_detected") {
          const mentions =
            (data.payload?.mentions as DetailedMention[] | undefined) || [];
          const backendSignature = mentionsSignature(mentions);
          lastBackendMentionsSignatureRef.current = backendSignature;
          pendingBackendMentionsAckSignatureRef.current = backendSignature;
          onMentionsDetected?.(mentions);
          setIsSending(false);
          const message = String(data.payload?.message || "").trim();
          if (message) {
            pushMessage("agent", message);
          }
          setIsProcessing(false);
          return;
        }

        if (data.type === "linked_entities_ready") {
          setIsSending(false);
          const message = String(data.payload?.message || "").trim();
          if (message) {
            pushMessage("agent", message);
          }
          setIsProcessing(false);
          return;
        }

        if (data.type === "mention_linked") {
          const mention =
            (data.payload?.mention as DetailedMention | undefined) || null;
          const linked = Boolean(data.payload?.linked);
          const candidateCount = Number(data.payload?.candidate_count || 0);
          const mentions =
            (data.payload?.mentions as DetailedMention[] | undefined) || [];
          if (mentions.length > 0) {
            onMentionsDetected?.(mentions);
          }
          if (mention) {
            if (linked) {
              pushMessage(
                "tool",
                `Linked mention: ${mention.text} (${candidateCount} candidates).`,
              );
            } else {
              pushMessage(
                "tool",
                `Could not link mention: ${mention.text} (0 candidates). You can send mention feedback before retrying.`,
              );
            }
          }
          return;
        }

        if (data.type === "mention_linking_complete") {
          const mentions =
            (data.payload?.mentions as DetailedMention[] | undefined) || [];
          const linkedCount = Number(data.payload?.linked_count || 0);
          const unlinkedCount = Number(data.payload?.unlinked_count || 0);
          if (mentions.length > 0) {
            onMentionsDetected?.(mentions);
          }
          pushProgress(
            `entity linking: completed (${linkedCount} linked, ${unlinkedCount} unlinked)`,
          );
          return;
        }

        if (data.type === "tool_calls") {
          const calls = (data.payload?.calls as Array<{ name: string }>) || [];
          const names = calls.map((c) => c.name).join(", ");
          pushMessage("tool", `Tool calls: ${names}`);
          return;
        }

        if (data.type === "tool_result") {
          const name = String(data.payload?.name || "tool");
          pushMessage("tool", `${name} returned.`);
          return;
        }

        if (data.type === "agent_reply") {
          const message = String(data.payload?.message || "").trim();
          if (message) {
            pushMessage("agent", message);
          }
          setCurrentStatus("Awaiting input");
          setIsSending(false);
          setIsProcessing(false);
          return;
        }

        if (data.type === "error") {
          const message = String(data.payload?.message || "Unknown error");
          pushMessage("system", message);
          if (message.includes("iteration limit")) {
            pushProgress(
              "query generation: iteration limit hit. retry is available.",
            );
            setPendingRetryQuery(true);
          }
          setCurrentStatus("Error");
          setIsSending(false);
          setIsProcessing(false);
          return;
        }

        if (data.type === "phase") {
          const name = String(data.payload?.name || "phase");
          const status = String(data.payload?.status || "unknown");
          setCurrentStatus(`${name}: ${status}`);
          pushProgress(`${name.replaceAll("_", " ")}: ${status}`);

          if (status === "started") {
            setIsProcessing(true);
          } else if (
            status === "finished" ||
            status === "failed" ||
            status === "restored" ||
            status === "awaiting_confirmation"
          ) {
            setIsProcessing(false);
          }

          if (status === "restored") {
            setIsSending(false);
          }
          if (name === "query_generation" && status === "started") {
            setPendingRetryQuery(false);
          }

          return;
        }

        logWsDiag("incoming_unhandled", { event_type: data.type });
      } catch {
        logWsDiag("incoming_non_json");
      }
    };

    return socket;
  };

  const sendQuestion = (rawQuestion?: string) => {
    const trimmed = (rawQuestion ?? question).trim();
    if (!trimmed || !schemaId || !model) {
      return;
    }
    const socket = ensureSocket();
    const initialQuestion = (currentQuestion || trimmed).trim();
    const hasRestorableMentions = Boolean(
      currentQuestion && externalMentions && externalMentions.length > 0,
    );

    const restorePayload = hasRestorableMentions
      ? {
          type: "start",
          question: initialQuestion,
          schema_id: schemaId,
          model,
          current_query: latestQueryRef.current || currentQuery || undefined,
          detailed_mentions: externalMentions,
          linked_mentions: buildLinkedMentionsFromMentions(externalMentions),
        }
      : null;

    const shouldSendAgentMessage = sessionStarted || hasRestorableMentions;
    const payload = shouldSendAgentMessage
      ? {
          type: "agent_message",
          message: trimmed,
        }
      : {
          type: "start",
          question: initialQuestion,
          schema_id: schemaId,
          model,
        };

    const sendNow = () => {
      if (!sessionStarted && restorePayload) {
        const restoreStage = externalMentions?.some(
          (mention) => (mention.candidates || []).length > 0,
        )
          ? "linked_entities"
          : "mention_confirmation";
        logWsDiag("outgoing", {
          request_type: "start",
          trigger: "send_question",
          restore_stage: restoreStage,
          mention_count: externalMentions?.length || 0,
        });
        socket.send(JSON.stringify(restorePayload));
        setLastStartQuestion(initialQuestion);
        setSessionStarted(true);
      }
      logWsDiag("outgoing", {
        request_type: payload.type,
        intent:
          payload.type === "agent_message"
            ? trimmed.toLowerCase().includes("continue")
              ? "continue"
              : "free_text"
            : "start",
      });
      socket.send(JSON.stringify(payload));
      pushMessage("user", trimmed);
      setIsProcessing(true);
      if (!sessionStarted) {
        setIsSending(true);
        setLastStartQuestion(initialQuestion);
        onQuestionSubmitted?.(initialQuestion);
        setSessionStarted(true);
      }
      if (rawQuestion === undefined) {
        setQuestion("");
      }
    };

    sendWhenSocketReady(socket, sendNow);
  };

  useEffect(() => {
    latestMentionsRef.current = externalMentions || null;
  }, [externalMentions]);

  useEffect(() => {
    sessionStartedRef.current = sessionStarted;
  }, [sessionStarted]);

  useEffect(() => {
    latestQueryRef.current = currentQuery || null;
    if (!sessionStartedRef.current) {
      return;
    }

    const socket = ensureSocket();
    const send = () => {
      const payload = {
        type: "set_query" as const,
        current_query: currentQuery || undefined,
      };
      logWsDiag("outgoing", {
        request_type: "set_query",
        has_query: Boolean(payload.current_query),
      });
      socket.send(JSON.stringify(payload));
    };

    sendWhenSocketReady(socket, send);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentQuery]);

  useEffect(() => {
    if (!sessionStartedRef.current) {
      return;
    }

    const socket = ensureSocket();
    const send = () => {
      const payload = {
        type: "set_query" as const,
        current_query: latestQueryRef.current || undefined,
      };
      logWsDiag("outgoing", {
        request_type: "set_query",
        trigger: "explicit_sync",
        has_query: Boolean(payload.current_query),
      });
      socket.send(JSON.stringify(payload));
    };

    sendWhenSocketReady(socket, send);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [querySyncNonce]);

  useEffect(() => {
    latestResultRef.current = currentQueryResult || null;
  }, [currentQueryResult]);

  useEffect(() => {
    setCurrentStatus("Connecting");
    ensureSocket();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!externalQuestion) {
      return;
    }
    sendQuestion(externalQuestion);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [externalQuestion]);

  useEffect(() => {
    if (!externalMentions) {
      return;
    }

    const signature = mentionsSignature(externalMentions);

    const decision = classifyMentionsSyncDecision(signature);
    if (decision === "skip_ack") {
      pendingBackendMentionsAckSignatureRef.current = null;
      return;
    }

    if (decision === "skip_duplicate") {
      return;
    }

    const payload: SetMentionsPayload = {
      type: "set_mentions",
      mentions: externalMentions.map((mention) => ({
        text: mention.text,
        type: mention.type,
        label_pred: mention.label_pred,
        attrs: mention.attrs || {},
        selected_candidate_iri:
          (mention as MentionWithSelection).selected_candidate_iri ||
          (mention as MentionWithSelection).selectedCandidate?.uri ||
          undefined,
      })),
    };

    sendSetMentionsPayload(payload);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [externalMentions]);

  useEffect(() => {
    if (
      !sessionStarted ||
      !lastStartQuestion ||
      isConnected ||
      reconnectingRef.current
    ) {
      return;
    }

    reconnectingRef.current = true;
    reconnectAttemptRef.current = 0;
    setCurrentStatus("Reconnecting");
    ensureSocket();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isConnected, lastStartQuestion, sessionStarted]);

  useEffect(() => {
    return () => {
      clearReconnectTimer();
      if (socketRef.current) {
        socketRef.current.onopen = null;
        socketRef.current.onclose = null;
        socketRef.current.onerror = null;
        socketRef.current.onmessage = null;
        if (
          socketRef.current.readyState === WebSocket.OPEN ||
          socketRef.current.readyState === WebSocket.CONNECTING
        ) {
          socketRef.current.close();
        }
      }
    };
  }, []);

  const prefillMessage = (value: string) => {
    setQuestion(value);
    requestAnimationFrame(() => {
      if (!messageInputRef.current) {
        return;
      }
      messageInputRef.current.focus();
      messageInputRef.current.setSelectionRange(value.length, value.length);
    });
  };

  const quickPrefillActions = [
    { label: "Continue", value: "continue" },
    { label: "Link Entities", value: "link entities" },
    { label: "Generate Query", value: "generate query" },
  ] as const;

  const retryQueryGeneration = () => {
    const socket = ensureSocket();

    const sendNow = () => {
      logWsDiag("outgoing", {
        request_type: "agent_message",
        intent: "retry_query_generation",
      });
      socket.send(
        JSON.stringify({
          type: "agent_message",
          message: "Retry query generation",
        }),
      );
      pushMessage("user", "Try again.");
      setIsSending(true);
      setIsProcessing(true);
      setPendingRetryQuery(false);
    };

    sendWhenSocketReady(socket, sendNow);
  };

  return (
    <ChatPanelView
      currentStatus={currentStatus}
      messages={messages}
      pendingRetryQuery={pendingRetryQuery}
      retryQueryGeneration={retryQueryGeneration}
      quickPrefillActions={quickPrefillActions}
      prefillMessage={prefillMessage}
      isInputLocked={isInputLocked}
      messageInputRef={messageInputRef}
      question={question}
      setQuestion={setQuestion}
      sendQuestion={() => sendQuestion()}
    />
  );
}
