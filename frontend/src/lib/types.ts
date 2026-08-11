export interface CandidateVariant {
  uri: string;
  pred: string;
  label?: string;
  role?: string;
  match_exact?: boolean;
}

export interface OneHopTriple {
  p: string;
  value: string;
}

export interface Candidate {
  score: number | null;
  uri: string;
  variants: CandidateVariant[];
  context: OneHopTriple[];
}

export interface Mention {
  text: string;
  type: string;
  label_pred: string;
  attrs: Record<string, string>;
  selected_candidate_iri?: string;
}

export interface DetailedMention extends Mention {
  candidates: Candidate[];
}

/** Frontend UI version of DetailedMention that stores state about the selected candidate */
export interface DetailedMentionWithSelection extends DetailedMention {
  selectedCandidate?: Candidate;
}

export interface LinkedMention extends Mention {
  iri: string;
}

export interface LinkedMentions {
  mentions: LinkedMention[];
}

export interface RequestMentions {
  query: string;
  schema_id: string;
  model: string;
  limit?: number;
}

export interface RequestQueryGeneration {
  question: string;
  mentions: LinkedMentions;
  schema_id: string;
  model: string;
}

export interface QueryResponse {
  query: string;
}

// See https://www.w3.org/TR/2013/REC-sparql11-results-json-20130321/#select-encode-terms
export interface SparqlBindingValue {
  type: string;
  value: string;
  datatype?: string;
  "xml:lang"?: string;
}

export interface SparqlResponse {
  head: {
    vars?: string[];
  };
  results?: {
    bindings?: Record<string, SparqlBindingValue>[];
  };
  boolean?: boolean;
}

export interface SchemaCacheItem {
  schema_id: string;
  name: string;
}

export interface SchemaIndex {
  endpoint?: string;
  namespaces: Record<string, string>;
  // We can add classes/props if we need them later in the UI
}
