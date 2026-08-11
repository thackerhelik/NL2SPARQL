// Trace logging utility for client-side storage using localStorage

export interface TraceStep {
  stage:
    | "question_input"
    | "mention_extraction"
    | "mention_selection"
    | "query_generation"
    | "query_execution";
  timestamp: number;
  data: Record<string, unknown>;
}

export interface Trace {
  id: string;
  createdAt: number;
  question?: string;
  schemaId?: string;
  model?: string;
  mentionCandidates?: unknown;
  selectedMentions?: unknown;
  sparqlQuery?: string;
  queryResults?: unknown;
}

const STORAGE_KEY = "nl2sparql_traces";
const CURRENT_TRACE_KEY = "nl2sparql_current_trace";
const MAX_TRACES = 30;

/**
 * Generate a unique trace ID
 */
export function generateTraceId(): string {
  return `trace_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
}

/**
 * Get the traces from localStorage
 */
function getTracesFromStorage(): Trace[] {
  if (typeof window === "undefined") {
    return [];
  }
  try {
    const data = window.localStorage.getItem(STORAGE_KEY);
    return data ? JSON.parse(data) : [];
  } catch (error) {
    console.error("Failed to retrieve traces from localStorage:", error);
    return [];
  }
}

/**
 * Save traces to localStorage
 */
function saveTracesToStorage(traces: Trace[]): void {
  if (typeof window === "undefined") {
    return;
  }
  try {
    // Keep only the most recent MAX_TRACES
    const recentTraces = traces.slice(-MAX_TRACES);
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(recentTraces));

    const currentTraceId = getCurrentTraceId();
    if (
      currentTraceId &&
      !recentTraces.some((trace) => trace.id === currentTraceId)
    ) {
      clearCurrentTraceId();
    }
  } catch (error) {
    console.error("Failed to save traces to localStorage:", error);
  }
}

export function setCurrentTraceId(traceId: string | null): void {
  if (typeof window === "undefined") {
    return;
  }

  try {
    if (!traceId) {
      window.localStorage.removeItem(CURRENT_TRACE_KEY);
      return;
    }
    window.localStorage.setItem(CURRENT_TRACE_KEY, traceId);
  } catch (error) {
    console.error("Failed to persist current trace id:", error);
  }
}

export function getCurrentTraceId(): string | null {
  if (typeof window === "undefined") {
    return null;
  }

  try {
    return window.localStorage.getItem(CURRENT_TRACE_KEY);
  } catch (error) {
    console.error("Failed to read current trace id:", error);
    return null;
  }
}

export function clearCurrentTraceId(): void {
  setCurrentTraceId(null);
}

export function getCurrentTrace(): Trace | null {
  const currentTraceId = getCurrentTraceId();
  if (!currentTraceId) {
    return null;
  }

  const trace = getTrace(currentTraceId);
  if (!trace) {
    clearCurrentTraceId();
  }
  return trace;
}

/**
 * Create a new trace
 */
export function createTrace(
  question: string,
  options?: { schemaId?: string; model?: string },
): Trace {
  const trace: Trace = {
    id: generateTraceId(),
    createdAt: Date.now(),
    question,
    schemaId: options?.schemaId,
    model: options?.model,
  };
  return trace;
}

/**
 * Save a trace to localStorage
 */
export function saveTrace(trace: Trace): void {
  const traces = getTracesFromStorage();
  traces.push(trace);
  saveTracesToStorage(traces);
}

/**
 * Update a trace in localStorage
 */
export function updateTrace(traceId: string, updates: Partial<Trace>): void {
  const traces = getTracesFromStorage();
  const index = traces.findIndex((t) => t.id === traceId);

  if (index !== -1) {
    traces[index] = { ...traces[index], ...updates };
    saveTracesToStorage(traces);
  }
}

/**
 * Get a single trace by ID
 */
export function getTrace(traceId: string): Trace | null {
  const traces = getTracesFromStorage();
  return traces.find((t) => t.id === traceId) || null;
}

/**
 * Get all traces
 */
export function getAllTraces(): Trace[] {
  return getTracesFromStorage();
}

/**
 * Delete a trace by ID
 */
export function deleteTrace(traceId: string): void {
  const traces = getTracesFromStorage();
  const filtered = traces.filter((t) => t.id !== traceId);
  saveTracesToStorage(filtered);

  if (getCurrentTraceId() === traceId) {
    clearCurrentTraceId();
  }
}

/**
 * Clear all traces
 */
export function clearAllTraces(): void {
  if (typeof window === "undefined") {
    return;
  }
  try {
    window.localStorage.removeItem(STORAGE_KEY);
    window.localStorage.removeItem(CURRENT_TRACE_KEY);
  } catch (error) {
    console.error("Failed to clear traces from localStorage:", error);
  }
}

/**
 * Export traces as JSON string
 */
export function exportTracesAsJson(): string {
  const traces = getTracesFromStorage();
  return JSON.stringify(traces, null, 2);
}

/**
 * Format timestamp to readable date string
 */
export function formatTimestamp(timestamp: number): string {
  return new Date(timestamp).toLocaleString();
}
