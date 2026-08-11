import { type Trace } from "@/lib/logging";
import {
  DetailedMention,
  DetailedMentionWithSelection,
  LinkedMention,
  SparqlResponse,
} from "@/lib/types";

const EXAMPLES_DBLP = [
  "Who are the authors of the paper named: Attention is All You Need?",
  "List all coauthors of Yoshua Bengio.",
  "Which papers did Dan O. Popa publish in the last 9 years?",
  "What is the average number of papers published by Darko Kirovski per year?",
  "What is the webpage of Ravi Kumar?",
  "Mention the year in which Nestor R. Polanco published the most papers.",
  "Did Ye, Xinyue publish the paper 'Assessment of drought occurrence in Bei-bu wheat districts, China between 1960 and 2012' in the last 7 years?",
  "Was the paper 'A Priority Queue Transform' not published by the person Michael L. Fredman?",
  "In IHM and 3DUI, what papers did S. Conversy publish?",
  "Which papers did author W. Kwasowiec publish and in which year?",
  "What is the last published paper?",
];

const EXAMPLES_BY_SCHEMA: Record<string, string[]> = {
  dblp: EXAMPLES_DBLP,
};

export type PipelineStage =
  | "input"
  | "mention_selection"
  | "sparql_editing"
  | "results";

export const DEFAULT_OPEN_PANELS = {
  mentions: true,
  query: false,
  results: false,
};

export function getExamples(
  schemaId: string,
  schemas: { schema_id: string; name: string }[],
): string[] {
  const name = schemas.find((s) => s.schema_id === schemaId)?.name ?? schemaId;
  const key = Object.keys(EXAMPLES_BY_SCHEMA).find((k) =>
    name.toLowerCase().includes(k),
  );
  return key ? EXAMPLES_BY_SCHEMA[key] : [];
}

export function deriveLinkedMentions(
  mentions:
    | DetailedMentionWithSelection[]
    | DetailedMention[]
    | null
    | undefined,
): LinkedMention[] {
  if (!mentions || mentions.length === 0) {
    return [];
  }

  return mentions
    .map((mention) => {
      const selectedMention = mention as DetailedMentionWithSelection;
      const selectedFromIri = selectedMention.selected_candidate_iri
        ? mention.candidates.find(
            (candidate) =>
              candidate.uri === selectedMention.selected_candidate_iri,
          )
        : null;
      const best =
        selectedMention.selectedCandidate ||
        selectedFromIri ||
        (mention.candidates.length > 0
          ? mention.candidates.reduce((left, right) =>
              (right.score || 0) > (left.score || 0) ? right : left,
            )
          : null);

      if (!best) {
        return null;
      }

      return {
        text: mention.text,
        type: mention.type,
        label_pred: mention.label_pred,
        attrs: mention.attrs || {},
        iri: best.uri,
      };
    })
    .filter((item): item is LinkedMention => item !== null);
}

export function getOpenPanelsForStage(stage: PipelineStage) {
  switch (stage) {
    case "input":
    case "mention_selection":
      return { mentions: true, query: false, results: false };
    case "sparql_editing":
      return { mentions: false, query: true, results: false };
    case "results":
      return { mentions: false, query: false, results: true };
  }
}

export function deriveStageFromTrace(trace: Trace): PipelineStage {
  if (trace.queryResults) {
    return "results";
  }
  if (trace.sparqlQuery) {
    return "sparql_editing";
  }
  if (trace.mentionCandidates) {
    return "mention_selection";
  }
  return "input";
}

export function buildRestoredTraceState(trace: Trace) {
  return {
    traceId: trace.id,
    question: trace.question || null,
    schemaId: trace.schemaId,
    model: trace.model,
    mentions:
      (trace.mentionCandidates as DetailedMentionWithSelection[] | undefined) ||
      null,
    query: trace.sparqlQuery || null,
    results: (trace.queryResults as SparqlResponse | undefined) || null,
    stage: deriveStageFromTrace(trace),
  };
}
