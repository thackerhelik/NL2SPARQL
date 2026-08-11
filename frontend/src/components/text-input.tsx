"use client";

import { useState, useEffect } from "react";
import {
  ArrowUpIcon,
  ChevronDown,
  Loader2,
  Plus,
  RotateCw,
} from "lucide-react";

import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import {
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from "@/components/ui/hover-card";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  InputGroup,
  InputGroupAddon,
  InputGroupButton,
  InputGroupTextarea,
} from "@/components/ui/input-group";
import { Separator } from "@/components/ui/separator";
import { useSchemaContext } from "@/contexts/SchemaContext";
import { SchemaUploadDialog } from "@/components/schema-upload-dialog";
import {
  DEFAULT_MODEL,
  fetchAvailableModels,
  mergeModelOptions,
  MODEL_OPTIONS,
  type ModelOption,
} from "@/lib/models";

export function TextInput({
  onSubmit,
  onSchemaChange,
  initialText = "",
  initialSchema = "",
  initialModel = DEFAULT_MODEL,
  isLoading = false,
  examples = [],
}: {
  onSubmit: (
    text: string,
    model: string,
    schema: string,
    skipMentionExtraction: boolean,
  ) => void;
  onSchemaChange?: (schema: string) => void;
  initialText?: string;
  initialSchema?: string;
  initialModel?: string;
  isLoading?: boolean;
  examples?: string[];
}) {
  const { schemas, isLoading: schemasLoading } = useSchemaContext();
  const [selectedModel, setSelectedModel] = useState(initialModel);
  const [modelOptions, setModelOptions] = useState<ModelOption[]>(
    mergeModelOptions(MODEL_OPTIONS, [initialModel]),
  );
  const [selectedSchema, setSelectedSchema] = useState(initialSchema);
  const [inputText, setInputText] = useState(initialText);
  const [isUploadDialogOpen, setIsUploadDialogOpen] = useState(false);
  const [skipMentionExtraction, setSkipMentionExtraction] = useState(false);
  const [isRefreshingModels, setIsRefreshingModels] = useState(false);

  const refreshModels = async () => {
    setIsRefreshingModels(true);
    try {
      const availableModels = await fetchAvailableModels();
      setModelOptions(
        mergeModelOptions(MODEL_OPTIONS, [...availableModels, initialModel]),
      );
    } catch {
      setModelOptions(mergeModelOptions(MODEL_OPTIONS, [initialModel]));
    } finally {
      setIsRefreshingModels(false);
    }
  };

  // Get the name of the currently selected schema for display
  const selectedSchemaName =
    schemas.find((s) => s.schema_id === selectedSchema)?.name || selectedSchema;

  // Keep schema in sync with resume/overwrite context.
  useEffect(() => {
    if (schemas.length === 0) {
      return;
    }
    if (initialSchema && schemas.some((s) => s.schema_id === initialSchema)) {
      setSelectedSchema(initialSchema);
    }
  }, [schemas, initialSchema]);

  // Ensure local schema selection remains valid if available schemas change.
  useEffect(() => {
    if (schemas.length === 0) {
      return;
    }
    if (!schemas.some((s) => s.schema_id === selectedSchema)) {
      setSelectedSchema(schemas[0].schema_id);
    }
  }, [schemas, selectedSchema]);

  // Keep textarea in sync when parent updates initialText (e.g. Resume trace).
  useEffect(() => {
    setInputText(initialText);
  }, [initialText]);

  useEffect(() => {
    setSelectedModel(initialModel);
    setModelOptions((prev) => mergeModelOptions(prev, [initialModel]));
  }, [initialModel]);

  useEffect(() => {
    let isCancelled = false;

    const loadModels = async () => {
      try {
        const availableModels = await fetchAvailableModels();
        if (!isCancelled) {
          setModelOptions(
            mergeModelOptions(MODEL_OPTIONS, [
              ...availableModels,
              initialModel,
            ]),
          );
        }
      } catch {
        if (!isCancelled) {
          setModelOptions(mergeModelOptions(MODEL_OPTIONS, [initialModel]));
        }
      }
    };

    void loadModels();

    return () => {
      isCancelled = true;
    };
  }, [initialModel]);

  const handleSend = () => {
    if (inputText.trim() && !isLoading) {
      onSubmit(inputText, selectedModel, selectedSchema, skipMentionExtraction);
    }
  };

  return (
    <div className="grid w-full max-w-2xl gap-3">
      <InputGroup>
        <InputGroupTextarea
          placeholder="e.g., Who are the authors of the paper named: Attentions is all you need?"
          value={inputText}
          disabled={isLoading}
          onChange={(e) => setInputText(e.target.value)}
          onKeyDown={(e) => {
            if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
              e.preventDefault();
              handleSend();
            }
          }}
        />
        <InputGroupAddon align="block-end" className="justify-end">
          <div className="flex items-center gap-1.5">
            <Checkbox
              id="skip-mention-extraction"
              checked={skipMentionExtraction}
              onCheckedChange={(checked) =>
                setSkipMentionExtraction(checked === true)
              }
              disabled={isLoading}
            />
            <HoverCard openDelay={200} closeDelay={100}>
              <HoverCardTrigger asChild>
                <Label
                  htmlFor="skip-mention-extraction"
                  className="text-xs font-medium text-muted-foreground cursor-pointer select-none leading-none"
                >
                  Skip Mention Extraction
                </Label>
              </HoverCardTrigger>
              <HoverCardContent
                side="bottom"
                align="start"
                className="w-72 text-sm"
              >
                <p className="font-semibold mb-1">Skip Mention Extraction</p>
                <p className="text-muted-foreground leading-relaxed text-[12px]">
                  When enabled, the mention extraction step is skipped and the
                  query is generated directly from your question. Use this when
                  your question contains no named entities that need to be
                  linked, or when entity linking is not required for the query.
                </p>
              </HoverCardContent>
            </HoverCard>
          </div>
          <Separator orientation="vertical" className="!h-4" />
          <div className="flex items-center gap-1">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/50">
              Schema:
            </span>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <InputGroupButton
                  variant="ghost"
                  className="text-muted-foreground hover:text-foreground !gap-1 px-2 text-xs"
                  disabled={schemasLoading || isLoading}
                >
                  {selectedSchemaName}
                  <ChevronDown className="h-3 w-3 opacity-50" />
                </InputGroupButton>
              </DropdownMenuTrigger>
              <DropdownMenuContent
                side="bottom"
                align="end"
                className="[--radius:0.95rem] max-h-60 overflow-y-auto"
              >
                {schemas.map((schema) => (
                  <DropdownMenuItem
                    key={schema.schema_id}
                    onClick={() => {
                      setSelectedSchema(schema.schema_id);
                      onSchemaChange?.(schema.schema_id);
                    }}
                  >
                    {schema.name}
                  </DropdownMenuItem>
                ))}
                {schemas.length === 0 && (
                  <DropdownMenuItem disabled>
                    No schemas available
                  </DropdownMenuItem>
                )}
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  onSelect={(e) => {
                    e.preventDefault();
                    setIsUploadDialogOpen(true);
                  }}
                >
                  <Plus className="mr-2 h-4 w-4" />
                  Add new schema
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
          <Separator orientation="vertical" className="!h-4" />
          <div className="flex items-center gap-1">
            <InputGroupButton
              variant="ghost"
              size="icon-xs"
              className="text-muted-foreground hover:text-foreground"
              onClick={() => {
                void refreshModels();
              }}
              disabled={isLoading || isRefreshingModels}
            >
              <RotateCw
                className={`h-3 w-3 ${isRefreshingModels ? "animate-spin" : ""}`}
              />
              <span className="sr-only">Refresh models</span>
            </InputGroupButton>
            <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/50">
              Model:
            </span>
            <DropdownMenu>
              <HoverCard openDelay={200} closeDelay={100}>
                <HoverCardTrigger asChild>
                  <DropdownMenuTrigger asChild>
                    <InputGroupButton
                      variant="ghost"
                      className="text-muted-foreground hover:text-foreground !gap-1 px-2 text-xs"
                      disabled={isLoading}
                    >
                      {selectedModel}
                      <ChevronDown className="h-3 w-3 opacity-50" />
                    </InputGroupButton>
                  </DropdownMenuTrigger>
                </HoverCardTrigger>
                <HoverCardContent
                  side="bottom"
                  align="start"
                  className="w-56 text-sm"
                >
                  <p className="font-semibold mb-1">Model compatibility</p>
                  <p className="text-muted-foreground leading-relaxed text-[12px]">
                    System is tested for gpt-oss-120b, but it supports models
                    that are good with structured outputs and function calling.
                  </p>
                </HoverCardContent>
              </HoverCard>
              <DropdownMenuContent
                side="top"
                align="end"
                className="[--radius:0.95rem] max-h-60 overflow-y-auto"
              >
                {modelOptions.map((model) => (
                  <DropdownMenuItem
                    key={model.value}
                    onClick={() => setSelectedModel(model.value)}
                  >
                    {model.label || model.value}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
          <Separator orientation="vertical" className="!h-4" />
          <InputGroupButton
            variant="default"
            className="rounded-full"
            size="icon-xs"
            onClick={handleSend}
            disabled={!inputText.trim() || isLoading}
          >
            {isLoading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <ArrowUpIcon />
            )}
            <span className="sr-only">Send</span>
          </InputGroupButton>
        </InputGroupAddon>
      </InputGroup>
      {examples.length > 0 && (
        <div className="flex flex-col gap-2">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/50">
            Try:
          </span>
          <div className="flex flex-col gap-2">
            {examples.map((example) => (
              <button
                key={example}
                type="button"
                disabled={isLoading}
                onClick={() => setInputText(example)}
                className="rounded-full bg-muted px-3 py-1 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground disabled:opacity-40 disabled:cursor-not-allowed text-left w-fit"
              >
                {example}
              </button>
            ))}
          </div>
        </div>
      )}
      <SchemaUploadDialog
        open={isUploadDialogOpen}
        onOpenChange={setIsUploadDialogOpen}
      />
    </div>
  );
}
