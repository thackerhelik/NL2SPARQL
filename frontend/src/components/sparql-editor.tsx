"use client";

import { useEffect, useRef, useState } from "react";
import Editor from "@monaco-editor/react";
import { Button } from "@/components/ui/button";
import { Loader2 } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

interface SPARQLEditorProps {
  query: string;
  schemaId: string;
  onValidate?: (query: string) => void;
  onSubmit: (query: string) => void;
  onSubmitAsNew?: (query: string) => void;
  isLoading?: boolean;
  hasDownstreamData?: boolean;
}

interface EditorHandle {
  getValue: () => string;
  setValue: (value: string) => void;
}

const MIN_EDITOR_HEIGHT = 220;
const MAX_EDITOR_HEIGHT = 420;
const ESTIMATED_LINE_HEIGHT = 20;
const EDITOR_VERTICAL_PADDING = 40;

function getEditorHeight(text: string): number {
  const lineCount = Math.max(1, text.split("\n").length);
  const calculated =
    lineCount * ESTIMATED_LINE_HEIGHT + EDITOR_VERTICAL_PADDING;
  return Math.min(MAX_EDITOR_HEIGHT, Math.max(MIN_EDITOR_HEIGHT, calculated));
}

export function SPARQLEditor({
  query,
  schemaId,
  onValidate,
  onSubmit,
  onSubmitAsNew,
  isLoading,
  hasDownstreamData,
}: SPARQLEditorProps) {
  const editorRef = useRef<EditorHandle | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [editorHeight, setEditorHeight] = useState<number>(
    getEditorHeight(query),
  );
  const [isValidating, setIsValidating] = useState(false);
  const [validationResult, setValidationResult] = useState<{
    valid: boolean;
    error?: string;
  } | null>(null);

  const handleEditorDidMount = (editor: EditorHandle) => {
    editorRef.current = editor;
  };

  useEffect(() => {
    if (!editorRef.current || typeof query !== "string") {
      return;
    }

    const currentValue = editorRef.current.getValue();
    if (currentValue !== query) {
      editorRef.current.setValue(query);
    }
  }, [query]);

  const handleSubmit = () => {
    const code = editorRef.current?.getValue();
    if (code) {
      onSubmit(code);
    }
  };

  const handleValidate = async () => {
    const code = editorRef.current?.getValue();
    if (!code) return;
    onValidate?.(code);
    setIsValidating(true);
    setValidationResult(null);
    try {
      const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api";
      const response = await fetch(`${API_BASE}/queries/validate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: code, schema_id: schemaId }),
      });
      const data = await response.json();
      setValidationResult({ valid: data.valid, error: data.error });
    } catch (e) {
      setValidationResult({ valid: false, error: String(e) });
    } finally {
      setIsValidating(false);
    }
  };

  return (
    <div className="w-full space-y-2">
      <div className="overflow-hidden rounded-md border bg-background">
        <Editor
          height={`${editorHeight}px`}
          defaultLanguage="sparql"
          defaultValue={query}
          onMount={handleEditorDidMount}
          onChange={(value) => {
            const nextQuery = value || "";
            setEditorHeight(getEditorHeight(nextQuery));
            setValidationResult(null);
          }}
          theme="vs-light"
          options={{
            minimap: { enabled: false },
            fontSize: 14,
            lineNumbers: "on",
            wordWrap: "on",
            tabSize: 2,
            scrollBeyondLastLine: false,
            automaticLayout: true,
            readOnly: isLoading,
          }}
        />
      </div>
      {validationResult !== null && (
        <div
          className={`rounded-md border px-4 py-2 text-sm ${
            validationResult.valid
              ? "border-green-200 bg-green-50 text-green-700"
              : "border-red-200 bg-red-50 text-red-700"
          }`}
        >
          {validationResult.valid
            ? "Query is valid."
            : (validationResult.error ?? "Query is invalid.")}
        </div>
      )}
      <div className="flex justify-end gap-2">
        <Button
          variant="outline"
          size="lg"
          onClick={handleValidate}
          disabled={isValidating || isLoading}
        >
          {isValidating ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin mr-2" />
              Validating...
            </>
          ) : (
            "Validate Query"
          )}
        </Button>
        <Button
          onClick={() => {
            if (hasDownstreamData) {
              setConfirmOpen(true);
            } else {
              handleSubmit();
            }
          }}
          size="lg"
          disabled={isLoading}
        >
          {isLoading ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin mr-2" />
              Executing...
            </>
          ) : (
            "Execute Query"
          )}
        </Button>
      </div>

      <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Overwrite existing results?</DialogTitle>
            <DialogDescription>
              Executing this query will overwrite any existing query results.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="outline"
              onClick={() => {
                setConfirmOpen(false);
                const code = editorRef.current?.getValue();
                if (code) {
                  onSubmitAsNew?.(code);
                }
              }}
            >
              Start New Trace
            </Button>
            <Button
              onClick={() => {
                setConfirmOpen(false);
                handleSubmit();
              }}
            >
              Overwrite
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
