"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import Editor from "@monaco-editor/react";
import {
  ArrowLeft,
  Plus,
  Trash2,
  Save,
  RefreshCw,
  Download,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useSchemaContext } from "@/contexts/SchemaContext";
import { SchemaUploadDialog } from "@/components/schema-upload-dialog";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api";

interface SchemaExample {
  question: string;
  sparql: string;
}

interface SchemaSettingsResponse {
  schema_id: string;
  name: string;
  endpoint: string;
  examples: SchemaExample[];
  description: string;
}

export default function SettingsPage() {
  const {
    schemas,
    refreshSchemas,
    isLoading: schemasLoading,
  } = useSchemaContext();
  const [selectedSchemaId, setSelectedSchemaId] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [endpoint, setEndpoint] = useState("");
  const [examples, setExamples] = useState<SchemaExample[]>([]);
  const [baseIri, setBaseIri] = useState("");
  const [description, setDescription] = useState("");
  const DESCRIPTION_MAX = 500;
  const [loadingSettings, setLoadingSettings] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isUploadDialogOpen, setIsUploadDialogOpen] = useState(false);

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

  const selectedSchema = useMemo(
    () =>
      schemas.find((schema) => schema.schema_id === selectedSchemaId) ?? null,
    [schemas, selectedSchemaId],
  );

  useEffect(() => {
    if (schemas.length === 0) {
      setSelectedSchemaId(null);
      return;
    }
    if (
      !selectedSchemaId ||
      !schemas.some((s) => s.schema_id === selectedSchemaId)
    ) {
      setSelectedSchemaId(schemas[0].schema_id);
    }
  }, [schemas, selectedSchemaId]);

  const loadSettings = async (schemaId: string) => {
    setLoadingSettings(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE}/schema/${schemaId}`);
      if (!response.ok) {
        throw new Error(`Failed to load schema settings (${response.status})`);
      }
      const data: SchemaSettingsResponse = await response.json();
      setName(data.name);
      setEndpoint(data.endpoint);
      setDescription(data.description || "");
      setExamples(data.examples || []);
      // Also fetch parsed schema data to obtain base IRI (if present)
      try {
        const parsedResp = await fetch(`${API_BASE}/schema/${schemaId}/data`);
        if (parsedResp.ok) {
          const parsed = await parsedResp.json();
          setBaseIri(parsed.base_iri || parsed.baseIri || "");
        } else {
          setBaseIri("");
        }
      } catch {
        setBaseIri("");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load settings.");
      setName("");
      setEndpoint("");
      setExamples([]);
    } finally {
      setLoadingSettings(false);
    }
  };

  useEffect(() => {
    if (!selectedSchemaId) return;
    loadSettings(selectedSchemaId);
  }, [selectedSchemaId]);

  const upsertExample = (
    idx: number,
    field: keyof SchemaExample,
    value: string,
  ) => {
    setExamples((prev) =>
      prev.map((example, currentIdx) =>
        currentIdx === idx ? { ...example, [field]: value } : example,
      ),
    );
  };

  const addExample = () => {
    setExamples((prev) => [...prev, { question: "", sparql: "" }]);
  };

  const removeExample = (idx: number) => {
    setExamples((prev) => prev.filter((_, currentIdx) => currentIdx !== idx));
  };

  const saveAll = async () => {
    if (!selectedSchemaId) return;
    setIsSaving(true);
    setError(null);
    try {
      // Trim description to max allowed length for safety
      const trimmedDescription = (description || "").slice(0, DESCRIPTION_MAX);
      const response = await fetch(`${API_BASE}/schema/${selectedSchemaId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name,
          endpoint,
          examples,
          description: trimmedDescription,
        }),
      });
      if (!response.ok) {
        const detail = await response.text();
        throw new Error(
          detail || `Failed to save settings (${response.status})`,
        );
      }
      await refreshSchemas();
      await loadSettings(selectedSchemaId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save settings.");
    } finally {
      setIsSaving(false);
    }
  };

  const deleteSchema = async (schemaId: string) => {
    const confirmed = window.confirm(
      `Delete schema "${schemaId}"? This cannot be undone.`,
    );
    if (!confirmed) return;
    setIsSaving(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE}/schema/${schemaId}`, {
        method: "DELETE",
      });
      if (!response.ok) {
        let detail = `Failed to delete schema (${response.status})`;
        try {
          const payload = await response.json();
          if (typeof payload?.detail === "string" && payload.detail.trim()) {
            detail = payload.detail.trim();
          }
        } catch {
          const fallback = await response.text();
          if (fallback.trim()) {
            detail = fallback.trim();
          }
        }
        throw new Error(detail);
      }
      await refreshSchemas();
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Failed to delete schema.";
      setError(message);
      showToast(message);
    } finally {
      setIsSaving(false);
    }
  };

  const downloadSchemaData = async () => {
    if (!selectedSchemaId) return;
    setError(null);
    try {
      // Fetch parsed schema data
      const parsedResp = await fetch(
        `${API_BASE}/schema/${selectedSchemaId}/data`,
      );
      if (!parsedResp.ok) {
        const detail = await parsedResp.text();
        throw new Error(
          detail ||
            `Failed to load schema data for download (${parsedResp.status})`,
        );
      }
      const parsed = await parsedResp.json();

      // Also fetch schema metadata (to include description, examples, base IRI, etc.)
      let meta: Partial<SchemaSettingsResponse> = {};
      try {
        const metaResp = await fetch(`${API_BASE}/schema/${selectedSchemaId}`);
        if (metaResp.ok) {
          meta = await metaResp.json();
        }
      } catch {
        meta = {};
      }

      const combined = {
        meta: {
          schema_id: selectedSchemaId,
          name: meta.name || name,
          endpoint: meta.endpoint || endpoint,
          base_iri: parsed.base_iri || parsed.baseIri || baseIri || "",
          examples: meta.examples || examples || [],
          description: meta.description || description || "",
        },
        schema_index: parsed,
      };

      const blob = new Blob([JSON.stringify(combined, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `schema_data_${selectedSchemaId}.json`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to download schema data.",
      );
    }
  };

  const downloadMetadata = () => {
    if (!selectedSchemaId) return;
    setError(null);
    try {
      const data = {
        schema_id: selectedSchemaId,
        name,
        endpoint,
        base_iri: baseIri,
        examples,
        description: (description || "").slice(0, DESCRIPTION_MAX),
      };
      const blob = new Blob([JSON.stringify(data, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `schema_metadata_${selectedSchemaId}.json`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to download metadata.",
      );
    }
  };

  return (
    <div className="flex flex-col items-center px-4 py-8 gap-6">
      <div className="w-full max-w-6xl">
        <Link href="/">
          <Button variant="outline" className="gap-2 mb-4">
            <ArrowLeft className="w-4 h-4" />
            Back
          </Button>
        </Link>
        <h1 className="text-3xl font-bold text-gray-900 mb-6">
          Schema Settings
        </h1>
      </div>

      <div className="w-full max-w-6xl grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card className="lg:col-span-1">
          <CardHeader>
            <CardTitle>Schemas</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex gap-2">
              <Button
                variant="outline"
                className="flex-1 gap-2"
                onClick={() => refreshSchemas()}
                disabled={schemasLoading}
              >
                <RefreshCw className="w-4 h-4" />
                Refresh
              </Button>
              <Button
                className="flex-1 gap-2"
                onClick={() => setIsUploadDialogOpen(true)}
              >
                <Plus className="w-4 h-4" />
                Add Schema
              </Button>
            </div>

            {schemas.length === 0 ? (
              <p className="text-sm text-gray-500">No schemas available.</p>
            ) : (
              <div className="space-y-2">
                {schemas.map((schema) => (
                  <div
                    key={schema.schema_id}
                    className={`border rounded-md p-3 ${schema.schema_id === selectedSchemaId ? "border-black bg-gray-50" : "border-gray-200"}`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <button
                        className="text-left flex-1"
                        onClick={() => setSelectedSchemaId(schema.schema_id)}
                      >
                        <p className="font-medium text-sm">{schema.name}</p>
                        <p className="text-xs text-gray-500 font-mono break-all">
                          {schema.schema_id}
                        </p>
                      </button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => deleteSchema(schema.schema_id)}
                        aria-label={`Delete schema ${schema.schema_id}`}
                        disabled={isSaving}
                      >
                        <Trash2 className="w-4 h-4 text-red-600" />
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>
              {selectedSchema
                ? `Edit ${selectedSchema.schema_id}`
                : "Select a schema"}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-6">
            {!selectedSchemaId ? (
              <p className="text-sm text-gray-500">
                Select a schema from the left panel to edit it.
              </p>
            ) : loadingSettings ? (
              <p className="text-sm text-gray-500">
                Loading schema settings...
              </p>
            ) : (
              <>
                <div className="space-y-2">
                  <label className="text-sm font-medium">Schema Name</label>
                  <Input
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                  />
                </div>

                <div className="space-y-2">
                  <label className="text-sm font-medium">Endpoint URL</label>
                  <Input
                    value={endpoint}
                    onChange={(e) => setEndpoint(e.target.value)}
                  />
                </div>

                <div className="space-y-2">
                  <label className="text-sm font-medium">Base IRI</label>
                  <Input value={baseIri} readOnly />
                </div>

                <div className="space-y-2">
                  <label className="text-sm font-medium">Description</label>
                  <textarea
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    className="w-full rounded-md border px-3 py-2 text-sm"
                    placeholder="Optional schema / ontology description"
                    rows={4}
                    maxLength={DESCRIPTION_MAX}
                  />
                  <div className="flex justify-end">
                    <p
                      className={`text-sm ${
                        description.length >= DESCRIPTION_MAX
                          ? "text-red-700"
                          : "text-gray-500"
                      }`}
                    >
                      {description.length} / {DESCRIPTION_MAX}
                    </p>
                  </div>
                </div>

                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <h2 className="text-lg font-semibold">Examples</h2>
                    <Button
                      variant="outline"
                      className="gap-2"
                      onClick={addExample}
                    >
                      <Plus className="w-4 h-4" />
                      Add Example
                    </Button>
                  </div>
                  {examples.length === 0 ? (
                    <p className="text-sm text-gray-500">
                      No examples yet. Add one to guide query generation.
                    </p>
                  ) : (
                    <div className="space-y-4">
                      {examples.map((example, idx) => (
                        <div
                          key={idx}
                          className="border rounded-md p-4 space-y-3"
                        >
                          <div className="space-y-2">
                            <label className="text-sm font-medium">
                              Question
                            </label>
                            <Input
                              value={example.question}
                              onChange={(e) =>
                                upsertExample(idx, "question", e.target.value)
                              }
                              placeholder="Natural language question"
                            />
                          </div>
                          <div className="space-y-2">
                            <label className="text-sm font-medium">
                              SPARQL
                            </label>
                            <div className="overflow-hidden rounded-md border bg-background">
                              <Editor
                                height="130px"
                                defaultLanguage="sparql"
                                value={example.sparql}
                                onChange={(value) =>
                                  upsertExample(idx, "sparql", value || "")
                                }
                                theme="vs-light"
                                options={{
                                  minimap: { enabled: false },
                                  fontSize: 13,
                                  lineNumbers: "on",
                                  wordWrap: "on",
                                  tabSize: 2,
                                  scrollBeyondLastLine: false,
                                  automaticLayout: true,
                                }}
                              />
                            </div>
                          </div>
                          <div className="flex justify-end">
                            <Button
                              variant="ghost"
                              className="gap-2"
                              onClick={() => removeExample(idx)}
                            >
                              <Trash2 className="w-4 h-4 text-red-600" />
                              Remove
                            </Button>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                <div className="flex flex-wrap gap-2 justify-end">
                  <Button
                    variant="outline"
                    className="gap-2"
                    onClick={downloadMetadata}
                  >
                    <Download className="w-4 h-4" />
                    Download Metadata
                  </Button>
                  <Button
                    variant="outline"
                    className="gap-2"
                    onClick={downloadSchemaData}
                  >
                    <Download className="w-4 h-4" />
                    Download Parsed Data
                  </Button>
                  <Button
                    className="gap-2"
                    onClick={saveAll}
                    disabled={isSaving}
                  >
                    <Save className="w-4 h-4" />
                    Save Changes
                  </Button>
                </div>
              </>
            )}

            {error && <p className="text-sm text-red-700">{error}</p>}
          </CardContent>
        </Card>
      </div>

      <SchemaUploadDialog
        open={isUploadDialogOpen}
        onOpenChange={setIsUploadDialogOpen}
      />
    </div>
  );
}
