"use client";

import { TextInput } from "@/components/text-input";
import { QuestionCard } from "@/components/question-card";
import { MentionCard } from "@/components/mention-card";
import { MentionInstruction } from "@/components/mention-instruction";
import { SPARQLEditor } from "@/components/sparql-editor";
import { QueryResults } from "@/components/query-results";
import { ChatPanel } from "@/components/chat-panel";
import { useEffect, useState } from "react";
import { useSchemaContext } from "@/contexts/SchemaContext";
import {
  createTrace,
  getCurrentTrace,
  getTrace,
  saveTrace,
  setCurrentTraceId,
  updateTrace,
} from "@/lib/logging";
import { DEFAULT_MODEL } from "@/lib/models";
import { Button } from "@/components/ui/button";
import { ChevronDown, ChevronUp, Download } from "lucide-react";
import {
  DetailedMention,
  DetailedMentionWithSelection,
  RequestMentions,
  RequestQueryGeneration,
  LinkedMention,
  QueryResponse,
  SparqlResponse,
} from "@/lib/types";
import {
  buildRestoredTraceState,
  DEFAULT_OPEN_PANELS,
  deriveLinkedMentions,
  getExamples,
  getOpenPanelsForStage,
  type PipelineStage,
} from "./page-helpers";
import { CHAT_MODE_EVENT, readChatModeFromStorage } from "@/lib/chat-mode";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api";

export default function Home() {
  const { schemas } = useSchemaContext();
  const [traceFromQuery, setTraceFromQuery] = useState<string | null>(null);

  const [stage, setStage] = useState<PipelineStage>("input");
  const [openPanels, setOpenPanels] = useState(DEFAULT_OPEN_PANELS);

  // Data state
  const [submittedText, setSubmittedText] = useState<string | null>(null);
  const [selectedModel, setSelectedModel] = useState<string>(DEFAULT_MODEL);
  const [selectedSchema, setSelectedSchema] = useState<string>("");
  const [isLoading, setIsLoading] = useState(false);
  const [mentionsData, setMentionsData] = useState<
    DetailedMentionWithSelection[] | null
  >(null);
  const [sparqlQuery, setSparqlQuery] = useState<string | null>(null);
  const [queryResults, setQueryResults] = useState<SparqlResponse | null>(null);
  const [traceId, setTraceId] = useState<string | null>(null);
  const [pendingOverwriteTraceId, setPendingOverwriteTraceId] = useState<
    string | null
  >(null);
  const [chatModeEnabled, setChatModeEnabled] = useState(false);
  const [chatQueuedQuestion, setChatQueuedQuestion] = useState<string | null>(
    null,
  );
  const [querySyncNonce, setQuerySyncNonce] = useState(0);

  const resetToEmptyView = () => {
    const cleanUrl = `${window.location.pathname}${window.location.hash || ""}`;
    window.history.replaceState({}, "", cleanUrl);
    setTraceId(null);
    setSubmittedText(null);
    setMentionsData(null);
    setSparqlQuery(null);
    setQueryResults(null);
    setChatQueuedQuestion(null);
    setStage("input");
    setOpenPanels(DEFAULT_OPEN_PANELS);
  };

  const applyViewState = (nextStage: PipelineStage) => {
    setStage(nextStage);
    setOpenPanels(getOpenPanelsForStage(nextStage));
  };

  const setInputPanels = () => {
    setOpenPanels(DEFAULT_OPEN_PANELS);
  };

  const closeQueryAndResultsPanels = () => {
    setOpenPanels((p) => ({ ...p, query: false, results: false }));
  };

  const openQueryCloseResultsPanels = () => {
    setOpenPanels((p) => ({ ...p, query: true, results: false }));
  };

  const createAndActivateTrace = (
    question: string,
    schemaId: string,
    model: string,
  ) => {
    const trace = createTrace(question, { schemaId, model });
    saveTrace(trace);
    setTraceId(trace.id);
    return trace.id;
  };

  const upsertCurrentTraceQuestion = (
    question: string,
    schemaId: string,
    model: string,
  ) => {
    if (traceId) {
      updateTrace(traceId, { question, schemaId, model });
      return traceId;
    }
    return createAndActivateTrace(question, schemaId, model);
  };

  const showToast = (message: string) => {
    const existing = document.getElementById("nl2sparql-error-toast");
    if (existing) {
      existing.remove();
    }

    const toast = document.createElement("div");
    toast.id = "nl2sparql-error-toast";
    toast.className =
      "fixed right-4 top-4 z-[9999] max-w-md rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-900 shadow-md";
    toast.textContent = message;
    document.body.appendChild(toast);

    window.setTimeout(() => {
      toast.remove();
    }, 3500);
  };

  const toUserErrorMessage = (error: unknown): string => {
    if (error instanceof Error && error.message.trim()) {
      return error.message;
    }
    return "Unknown error";
  };

  const getErrorDetailFromResponse = async (
    response: Response,
  ): Promise<string> => {
    const code = String(response.status);
    const fallbackText = response.statusText?.trim() || "Request failed";
    let raw = "";

    try {
      raw = await response.text();
    } catch {
      return `${code} ${fallbackText}`.trim();
    }

    if (!raw) {
      return `${code} ${fallbackText}`.trim();
    }

    let message = "";

    try {
      const data = JSON.parse(raw);
      if (typeof data?.detail === "string" && data.detail.trim()) {
        message = data.detail.trim();
      }
      if (!message && Array.isArray(data?.detail)) {
        const msgs = data.detail
          .map((d: { loc?: unknown; msg?: unknown }) => {
            const loc = Array.isArray(d?.loc) ? d.loc.join(".") : "";
            const msg = typeof d?.msg === "string" ? d.msg : "";
            return [loc, msg].filter(Boolean).join(": ");
          })
          .filter(Boolean);
        if (msgs.length > 0) {
          message = msgs.join(" | ");
        }
      }
      if (!message && typeof data?.error === "string" && data.error.trim()) {
        message = data.error.trim();
      }
      if (
        !message &&
        typeof data?.message === "string" &&
        data.message.trim()
      ) {
        message = data.message.trim();
      }
    } catch {
      // Non-JSON response body.
    }

    if (!message) {
      message = raw.trim() || fallbackText;
    }
    return message.startsWith(`${code} `) ? message : `${code} ${message}`;
  };

  // Initialize selectedSchema with first schema_id from context
  useEffect(() => {
    if (schemas.length > 0 && !selectedSchema) {
      setSelectedSchema(schemas[0].schema_id);
    }
  }, [schemas, selectedSchema]);

  useEffect(() => {
    const syncTraceFromUrl = () => {
      const params = new URLSearchParams(window.location.search);
      setTraceFromQuery(params.get("trace"));
    };

    syncTraceFromUrl();
    window.addEventListener("popstate", syncTraceFromUrl);

    return () => {
      window.removeEventListener("popstate", syncTraceFromUrl);
    };
  }, []);

  useEffect(() => {
    const navEntry = performance.getEntriesByType("navigation")[0] as
      | PerformanceNavigationTiming
      | undefined;
    const shouldResetForHardRefresh = navEntry?.type === "reload";

    const activeTrace = traceFromQuery
      ? getTrace(traceFromQuery)
      : getCurrentTrace();

    if (shouldResetForHardRefresh && !traceFromQuery) {
      if (activeTrace) {
        setCurrentTraceId(activeTrace.id);
      } else {
        resetToEmptyView();
        return;
      }
    }

    if (!activeTrace) {
      resetToEmptyView();
      return;
    }

    // Resume a trace from History via ?trace=<id>, else fallback to active trace pointer.
    const restored = buildRestoredTraceState(activeTrace);
    setCurrentTraceId(restored.traceId);
    setTraceId(restored.traceId);
    setSubmittedText(restored.question);

    setMentionsData(restored.mentions);
    setSparqlQuery(restored.query);
    setQueryResults(restored.results);

    if (restored.schemaId) {
      setSelectedSchema(restored.schemaId);
    }
    if (restored.model) {
      setSelectedModel(restored.model);
    }

    applyViewState(restored.stage);
  }, [traceFromQuery]);

  useEffect(() => {
    if (!traceId) {
      return;
    }
    setCurrentTraceId(traceId);
  }, [traceId]);

  const downloadJson = (data: unknown, filename: string) => {
    // Reusable JSON download helper for trace/result exports.
    const dataStr = JSON.stringify(
      data,
      (_key, value) => (value === null ? undefined : value),
      2,
    );
    const dataBlob = new Blob([dataStr], { type: "application/json" });
    const url = URL.createObjectURL(dataBlob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    link.click();
    URL.revokeObjectURL(url);
  };

  // Step 2: User submits a question - ResultCard appears
  const handleTextSubmit = async (
    text: string,
    model: string,
    schema: string,
    skipMentionExtraction: boolean = false,
  ) => {
    if (chatModeEnabled) {
      if (traceId) {
        updateTrace(traceId, { question: text, schemaId: schema, model });
      } else {
        const trace = createTrace(text, { schemaId: schema, model });
        saveTrace(trace);
        setTraceId(trace.id);
      }
      setSubmittedText(text);
      setSelectedModel(model);
      setSelectedSchema(schema);
      setChatQueuedQuestion(text);
      if (stage === "input") {
        applyViewState("sparql_editing");
      }
      return;
    }

    setIsLoading(true);
    setSubmittedText(text);
    setSelectedModel(model);
    setSelectedSchema(schema);
    setMentionsData(null);
    setSparqlQuery(null);
    setQueryResults(null);
    setInputPanels();

    let activeTraceId: string;
    // Overwrite keeps the existing trace id; otherwise create a fresh trace.
    if (pendingOverwriteTraceId) {
      activeTraceId = pendingOverwriteTraceId;
      setPendingOverwriteTraceId(null);
      updateTrace(activeTraceId, { question: text, schemaId: schema, model });
    } else {
      const trace = createTrace(text, { schemaId: schema, model });
      saveTrace(trace);
      activeTraceId = trace.id;
      setTraceId(trace.id);
    }

    try {
      if (skipMentionExtraction) {
        // Skip mention extraction — generate SPARQL directly with no linked mentions.
        const generationRequest: RequestQueryGeneration = {
          question: text,
          mentions: { mentions: [] },
          model: model,
          schema_id: schema,
        };

        const response = await fetch(`${API_BASE}/generation`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(generationRequest),
        });

        if (response.ok) {
          const data: QueryResponse = await response.json();
          const cleanQuery = data.query
            .replace(/^```(sparql)?\n/i, "")
            .replace(/\n```$/m, "")
            .trim();
          setSparqlQuery(cleanQuery);
          updateTrace(activeTraceId, { sparqlQuery: cleanQuery });
          setStage("sparql_editing");
          setOpenPanels({ mentions: false, query: true, results: false });
        } else {
          const detail = await getErrorDetailFromResponse(response);
          console.error("Failed to generate SPARQL:", detail);
          showToast(detail);
        }
      } else {
        const mentionsRequest: RequestMentions = {
          query: text,
          schema_id: schema,
          model: model,
        };

        const response = await fetch(`${API_BASE}/mentions`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify(mentionsRequest),
        });

        if (response.ok) {
          const mentions: DetailedMention[] = await response.json();
          // Initialize selection state
          setMentionsData(mentions);
          updateTrace(activeTraceId, { mentionCandidates: mentions });
          // Move to Step 3: Display MentionCard
          setStage("mention_selection");
          setOpenPanels({ mentions: true, query: false, results: false });
        } else {
          const detail = await getErrorDetailFromResponse(response);
          console.error("Failed to extract mentions:", detail);
          showToast(detail);
        }
      }
    } catch (error: unknown) {
      console.error("Error:", error);
      showToast(toUserErrorMessage(error));
    } finally {
      setIsLoading(false);
    }
  };

  // Step 4: User submits Mention Candidates - hide MentionCard, receive SPARQL
  const handleMentionSubmit = async (
    mentions: DetailedMentionWithSelection[],
    overrideTraceId?: string,
  ) => {
    setIsLoading(true); // Re-use loading state for generation
    setMentionsData(mentions);
    const activeTraceId = overrideTraceId ?? traceId;
    // Clear downstream sections immediately on resubmit/overwrite.
    setSparqlQuery(null);
    setQueryResults(null);
    closeQueryAndResultsPanels();
    if (activeTraceId) {
      updateTrace(activeTraceId, {
        selectedMentions: undefined,
        sparqlQuery: undefined,
        queryResults: undefined,
      });
    }
    try {
      // Convert UI state to backend LinkedMention format
      const linkedMentions: LinkedMention[] = deriveLinkedMentions(mentions);

      const generationRequest: RequestQueryGeneration = {
        question: submittedText || "",
        mentions: { mentions: linkedMentions },
        model: selectedModel,
        schema_id: selectedSchema,
      };

      const response = await fetch(`${API_BASE}/generation`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(generationRequest),
      });

      if (response.ok) {
        const data: QueryResponse = await response.json();
        // Clean up markdown code blocks if the backend didn't do it
        const cleanQuery = data.query
          .replace(/^```(sparql)?\n/i, "")
          .replace(/\n```$/m, "")
          .trim();
        setSparqlQuery(cleanQuery);
        setQueryResults(null);
        if (activeTraceId) {
          updateTrace(activeTraceId, {
            selectedMentions: linkedMentions,
            sparqlQuery: cleanQuery,
          });
        }
        applyViewState("sparql_editing");
      } else {
        const detail = await getErrorDetailFromResponse(response);
        console.error("Failed to generate SPARQL:", detail);
        showToast(detail);
      }
    } catch (error: unknown) {
      console.error("Error generating SPARQL:", error);
      showToast(toUserErrorMessage(error));
    } finally {
      setIsLoading(false);
    }
  };

  const handleMentionSubmitAsNew = async (
    mentions: DetailedMentionWithSelection[],
  ) => {
    // "Start New Trace" from mentions keeps current question context but forks trace id.
    const newTrace = createTrace(submittedText || "", {
      schemaId: selectedSchema,
      model: selectedModel,
    });
    saveTrace(newTrace);
    updateTrace(newTrace.id, {
      mentionCandidates: mentions,
      selectedMentions: deriveLinkedMentions(mentions),
    });
    setTraceId(newTrace.id);
    await handleMentionSubmit(mentions, newTrace.id);
  };

  // Step 6: User submits edited SPARQL - send to backend
  const handleSparqlSubmit = async (
    editedQuery: string,
    overrideTraceId?: string,
  ) => {
    setIsLoading(true);
    const activeTraceId = overrideTraceId ?? traceId;
    // Persist the latest editor text so reopening the panel doesn't restore stale query text.
    setSparqlQuery(editedQuery);
    // Force websocket query sync on every execute, even when text is unchanged.
    setQuerySyncNonce((n) => n + 1);
    // Clear downstream results immediately on resubmit/overwrite.
    setQueryResults(null);
    openQueryCloseResultsPanels();
    if (activeTraceId) {
      updateTrace(activeTraceId, {
        sparqlQuery: editedQuery,
        queryResults: undefined,
      });
    }
    try {
      // 1. Get the endpoint URL from the already loaded schemas in context
      const selectedSchemaMetadata = schemas.find(
        (s) => s.schema_id === selectedSchema,
      );
      const endpoint = selectedSchemaMetadata?.endpoint;

      if (!endpoint) {
        showToast("No SPARQL endpoint found for the selected schema.");
        setIsLoading(false);
        return;
      }

      // 2. Execute the query using the retrieved endpoint
      const response = await fetch(`${API_BASE}/queries/run`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          query: editedQuery,
          endpoint_url: endpoint,
          schema_id: selectedSchema,
        }),
      });

      if (response.ok) {
        const data = await response.json();
        setQueryResults(data);
        if (activeTraceId) {
          updateTrace(activeTraceId, {
            sparqlQuery: editedQuery,
            queryResults: data,
          });
        }
        applyViewState("results");
      } else {
        const detail = await getErrorDetailFromResponse(response);
        console.error("Failed to execute query:", detail);
        showToast(detail);
      }
    } catch (error: unknown) {
      console.error("Error executing query:", error);
      showToast(toUserErrorMessage(error));
    } finally {
      setIsLoading(false);
    }
  };

  const handleSparqlSubmitAsNew = async (editedQuery: string) => {
    // "Start New Trace" from query editor snapshots the current query into a new trace.
    const newTrace = createTrace(submittedText || "", {
      schemaId: selectedSchema,
      model: selectedModel,
    });
    saveTrace(newTrace);
    updateTrace(newTrace.id, {
      schemaId: selectedSchema,
      model: selectedModel,
      mentionCandidates: mentionsData || undefined,
      sparqlQuery: editedQuery,
    });
    setTraceId(newTrace.id);
    await handleSparqlSubmit(editedQuery, newTrace.id);
  };

  const handleSparqlValidate = (editedQuery: string) => {
    setSparqlQuery(editedQuery);
    setQuerySyncNonce((n) => n + 1);
    if (traceId) {
      updateTrace(traceId, { sparqlQuery: editedQuery });
    }
  };

  // Edit: Return to input stage — old trace is preserved, next submit creates a new one
  const handleEditAsNew = () => {
    setMentionsData(null);
    setSparqlQuery(null);
    setQueryResults(null);
    setTraceId(null);
    setPendingOverwriteTraceId(null);
    setChatQueuedQuestion(null);
    setInputPanels();
    setStage("input");
  };

  // Create a new trace while ensuring the current trace is persisted.
  const handleCreateNew = () => {
    if (traceId) {
      updateTrace(traceId, {
        question: submittedText || undefined,
        schemaId: selectedSchema || undefined,
        model: selectedModel || undefined,
        mentionCandidates: mentionsData || undefined,
        sparqlQuery: sparqlQuery || undefined,
        queryResults: queryResults || undefined,
      });
    } else if (submittedText) {
      const t = createTrace(submittedText, {
        schemaId: selectedSchema,
        model: selectedModel,
      });
      saveTrace(t);
    }

    // Clear UI for a fresh trace
    setMentionsData(null);
    setSparqlQuery(null);
    setQueryResults(null);
    setTraceId(null);
    setPendingOverwriteTraceId(null);
    setChatQueuedQuestion(null);
    setSubmittedText(null);
    setInputPanels();
    setStage("input");
  };

  // Edit: Return to input stage — next submit overwrites the existing trace
  const handleEditOverwrite = () => {
    if (traceId) {
      updateTrace(traceId, {
        mentionCandidates: undefined,
        selectedMentions: undefined,
        sparqlQuery: undefined,
        queryResults: undefined,
      });
    }
    setMentionsData(null);
    setSparqlQuery(null);
    setQueryResults(null);
    setPendingOverwriteTraceId(traceId);
    setInputPanels();
    setStage("input");
  };

  // Skip LLM generation — user wants to write the SPARQL query themselves
  const handleSkipToEditor = () => {
    const template = "SELECT ?s ?p ?o WHERE {\n  ?s ?p ?o .\n} LIMIT 10";
    setSparqlQuery(template);
    setQueryResults(null);
    if (traceId) {
      updateTrace(traceId, { sparqlQuery: template, queryResults: undefined });
    }
    applyViewState("sparql_editing");
  };

  const handleChatGeneratedQuery = (query: string) => {
    setSparqlQuery(query);
    setQueryResults(null);
    if (traceId) {
      updateTrace(traceId, {
        sparqlQuery: query,
        queryResults: undefined,
      });
    }
    applyViewState("sparql_editing");
  };

  const handleChatMentionsDetected = (mentions: DetailedMention[]) => {
    setMentionsData(mentions);
    if (traceId) {
      updateTrace(traceId, {
        mentionCandidates: mentions,
        selectedMentions: deriveLinkedMentions(mentions),
      });
    }
    applyViewState("mention_selection");
  };

  const handleChatQueryResult = (result: SparqlResponse) => {
    setQueryResults(result);
    if (traceId) {
      updateTrace(traceId, {
        queryResults: result,
      });
    }
    applyViewState("results");
  };

  const handleChatQuestion = (text: string) => {
    upsertCurrentTraceQuestion(text, selectedSchema, selectedModel);
    setSubmittedText(text);
    setChatQueuedQuestion(null);
    if (stage === "input") {
      applyViewState("sparql_editing");
    }
  };

  useEffect(() => {
    if (!chatModeEnabled || !traceId) {
      return;
    }
    if (!mentionsData) {
      return;
    }
    updateTrace(traceId, {
      mentionCandidates: mentionsData,
      selectedMentions: deriveLinkedMentions(mentionsData),
    });
  }, [chatModeEnabled, mentionsData, traceId]);

  useEffect(() => {
    const applyChatMode = (next: boolean) => {
      if (
        next &&
        !traceId &&
        submittedText &&
        selectedSchema &&
        selectedModel
      ) {
        const createdTraceId = createAndActivateTrace(
          submittedText,
          selectedSchema,
          selectedModel,
        );
        updateTrace(createdTraceId, {
          mentionCandidates: mentionsData || undefined,
          sparqlQuery: sparqlQuery || undefined,
          queryResults: queryResults || undefined,
        });
      }
      setChatModeEnabled(next);
    };

    const sync = () => {
      applyChatMode(readChatModeFromStorage());
    };

    const onStorage = () => {
      sync();
    };

    const onChatModeChanged = (event: Event) => {
      const customEvent = event as CustomEvent<boolean>;
      if (typeof customEvent.detail === "boolean") {
        applyChatMode(customEvent.detail);
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
  }, [
    traceId,
    submittedText,
    selectedSchema,
    selectedModel,
    mentionsData,
    sparqlQuery,
    queryResults,
  ]);

  return (
    <div className="w-full px-4 pb-12 pt-10">
      <div
        className={`mx-auto ${
          chatModeEnabled
            ? "max-w-7xl grid grid-cols-[minmax(0,1fr)_400px] gap-8"
            : "max-w-4xl"
        }`}
      >
        <div className="flex flex-col items-center gap-10">
          {/* Step 1: Initial state - TextInput with example */}
          {stage === "input" ? (
            <TextInput
              onSubmit={handleTextSubmit}
              onSchemaChange={setSelectedSchema}
              initialText={submittedText || ""}
              initialSchema={selectedSchema}
              initialModel={selectedModel}
              isLoading={isLoading}
              examples={getExamples(selectedSchema, schemas)}
            />
          ) : (
            <>
              {/* Steps 2-7: QuestionCard always fixed at top */}
              <QuestionCard
                text={submittedText!}
                onCreate={handleCreateNew}
                onEditAsNew={handleEditAsNew}
                onEditOverwrite={handleEditOverwrite}
                hasDownstreamData={
                  !!(mentionsData || sparqlQuery || queryResults)
                }
              />

              <div className="w-full max-w-4xl space-y-8 pb-8">
                {/* Step 3: Mention review and candidate selection */}
                {mentionsData && (
                  <>
                    <button
                      className="flex items-center gap-2 w-full text-2xl font-bold text-gray-900 mb-2"
                      onClick={() =>
                        setOpenPanels((p) => ({ ...p, mentions: !p.mentions }))
                      }
                    >
                      {openPanels.mentions ? (
                        <ChevronUp className="w-4 h-4" />
                      ) : (
                        <ChevronDown className="w-4 h-4" />
                      )}{" "}
                      Detected Mentions
                    </button>
                    {openPanels.mentions && (
                      <>
                        <MentionInstruction />
                        <MentionCard
                          key={`${traceId ?? "trace"}:${mentionsData
                            .map((m) => `${m.text}:${m.candidates.length}`)
                            .join("|")}`}
                          data={mentionsData}
                          onChange={(updatedMentions) =>
                            setMentionsData(updatedMentions)
                          }
                          onSubmit={handleMentionSubmit}
                          onSubmitAsNew={handleMentionSubmitAsNew}
                          onSkipToEditor={handleSkipToEditor}
                          isLoading={isLoading}
                          hasDownstreamData={!!(sparqlQuery || queryResults)}
                        />
                      </>
                    )}
                  </>
                )}

                {/* Step 5: SPARQL editing and execution */}
                {sparqlQuery && (
                  <>
                    <button
                      className="flex items-center gap-2 w-full text-2xl font-bold text-gray-900 mb-2"
                      onClick={() =>
                        setOpenPanels((p) => ({ ...p, query: !p.query }))
                      }
                    >
                      {openPanels.query ? (
                        <ChevronUp className="w-4 h-4" />
                      ) : (
                        <ChevronDown className="w-4 h-4" />
                      )}{" "}
                      SPARQL Query
                    </button>
                    {openPanels.query && (
                      <SPARQLEditor
                        query={sparqlQuery || ""}
                        schemaId={selectedSchema}
                        onValidate={handleSparqlValidate}
                        onSubmit={handleSparqlSubmit}
                        onSubmitAsNew={handleSparqlSubmitAsNew}
                        isLoading={isLoading}
                        hasDownstreamData={!!queryResults}
                      />
                    )}
                  </>
                )}

                {/* Step 7: Query results display and export */}
                {queryResults && (
                  <>
                    <div className="flex items-center justify-between">
                      <button
                        className="flex items-center gap-2 text-2xl font-bold text-gray-900 mb-2"
                        onClick={() =>
                          setOpenPanels((p) => ({ ...p, results: !p.results }))
                        }
                      >
                        {openPanels.results ? (
                          <ChevronUp className="w-4 h-4" />
                        ) : (
                          <ChevronDown className="w-4 h-4" />
                        )}{" "}
                        Query Results
                      </button>
                      <Button
                        variant="outline"
                        onClick={() =>
                          downloadJson(
                            queryResults,
                            `results_${Date.now()}.json`,
                          )
                        }
                      >
                        <Download className="w-4 h-4 mr-2" />
                        Download Query Results
                      </Button>
                    </div>
                    {openPanels.results && (
                      <QueryResults results={queryResults} />
                    )}
                  </>
                )}
              </div>
            </>
          )}
        </div>

        {chatModeEnabled && (
          <div>
            <ChatPanel
              key={traceId || "no-trace"}
              schemaId={selectedSchema}
              model={selectedModel}
              currentQuestion={submittedText}
              currentQuery={sparqlQuery}
              querySyncNonce={querySyncNonce}
              currentQueryResult={queryResults}
              externalQuestion={chatQueuedQuestion}
              externalMentions={mentionsData}
              onQuestionSubmitted={handleChatQuestion}
              onMentionsDetected={handleChatMentionsDetected}
              onGeneratedQuery={handleChatGeneratedQuery}
              onQueryResult={handleChatQueryResult}
            />
          </div>
        )}
      </div>
    </div>
  );
}
