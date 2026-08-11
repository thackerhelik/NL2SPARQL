"use client";

import { useState } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  Tag,
  Upload,
  ChevronDown,
  ChevronUp,
  Loader2,
  PenLine,
  X,
} from "lucide-react";
import { DetailedMentionWithSelection, Candidate } from "@/lib/types";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

interface MentionCardProps {
  data: DetailedMentionWithSelection[] | null;
  onChange?: (mentions: DetailedMentionWithSelection[]) => void;
  onSubmit?: (mentions: DetailedMentionWithSelection[]) => void;
  onSubmitAsNew?: (mentions: DetailedMentionWithSelection[]) => void;
  onSkipToEditor?: () => void;
  isLoading?: boolean;
  hasDownstreamData?: boolean;
}

export function MentionCard({
  data,
  onChange,
  onSubmit,
  onSubmitAsNew,
  onSkipToEditor,
  isLoading,
  hasDownstreamData,
}: MentionCardProps) {
  const mentions = data || [];
  const [expandedMentions, setExpandedMentions] = useState<Set<number>>(
    new Set(),
  );
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [removeConfirmIdx, setRemoveConfirmIdx] = useState<number | null>(null);
  const hasMentions = mentions.length > 0;

  const handleSelectCandidate = (mentionIdx: number, candidate: Candidate) => {
    const updatedMentions = mentions.map((mention, idx) =>
      idx === mentionIdx
        ? {
            ...mention,
            selectedCandidate: candidate,
            selected_candidate_iri: candidate.uri,
          }
        : mention,
    );
    onChange?.(updatedMentions);
  };

  const handleRemoveMention = (mentionIdx: number) => {
    const updatedMentions = mentions.filter((_, idx) => idx !== mentionIdx);
    onChange?.(updatedMentions);
    setRemoveConfirmIdx(null);
  };

  const toggleExpand = (mentionIdx: number) => {
    setExpandedMentions((prev) => {
      const next = new Set(prev);
      if (next.has(mentionIdx)) {
        next.delete(mentionIdx);
      } else {
        next.add(mentionIdx);
      }
      return next;
    });
  };

  const getCandidateLabel = (candidate: Candidate) => {
    // Try to find a label in variants
    const variantWithLabel = candidate.variants.find((v) => v.label);
    return variantWithLabel?.label || candidate.uri;
  };

  const getSelectedCandidate = (mention: DetailedMentionWithSelection) => {
    if (mention.selectedCandidate) {
      return mention.selectedCandidate;
    }
    if (mention.selected_candidate_iri) {
      const selectedFromIri = mention.candidates.find(
        (candidate) => candidate.uri === mention.selected_candidate_iri,
      );
      if (selectedFromIri) {
        return selectedFromIri;
      }
    }
    return null;
  };

  const getBestCandidate = (mention: DetailedMentionWithSelection) => {
    if (mention.candidates.length === 0) return null;
    return mention.candidates.reduce((best, current) =>
      (current.score || 0) > (best.score || 0) ? current : best,
    );
  };

  const handleGenerateClick = () => {
    if (hasDownstreamData) {
      setConfirmOpen(true);
      return;
    }
    onSubmit?.(mentions);
  };

  return (
    <>
      <div className="w-full max-w-4xl grid gap-4">
        {hasMentions ? (
          mentions.map((mention, mentionIdx) => {
            const selectedCandidate = getSelectedCandidate(mention);
            const bestCandidate =
              selectedCandidate || getBestCandidate(mention);
            const isExpanded = expandedMentions.has(mentionIdx);

            return (
              <Card
                key={`${mention.text}:${mention.type}:${mentionIdx}`}
                className="hover:shadow-lg transition-shadow"
              >
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3 flex-1">
                      <Tag className="w-5 h-5 text-blue-600" />
                      <div>
                        <CardTitle className="text-lg">
                          {mention.text}
                        </CardTitle>
                        <CardDescription>
                          {mention.candidates.length} entity candidate
                          {mention.candidates.length !== 1 ? "s" : ""}
                        </CardDescription>
                      </div>
                    </div>
                    <div className="flex items-center gap-1">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => toggleExpand(mentionIdx)}
                        className="gap-2"
                      >
                        {isExpanded ? (
                          <>
                            <ChevronUp className="w-4 h-4" />
                            Hide
                          </>
                        ) : (
                          <>
                            <ChevronDown className="w-4 h-4" />
                            Show More
                          </>
                        )}
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setRemoveConfirmIdx(mentionIdx)}
                        className="gap-1.5 border-red-100 text-red-500 hover:bg-red-50 hover:text-red-700 hover:border-red-400"
                      >
                        <X className="w-3.5 h-3.5" />
                        Remove
                      </Button>
                    </div>
                  </div>
                </CardHeader>

                <CardContent>
                  <div className="space-y-3">
                    <div>
                      <p className="text-xs font-semibold text-gray-600 mb-1">
                        Mention Type
                      </p>
                      <span className="text-sm bg-blue-50 text-blue-700 px-3 py-1 rounded font-medium">
                        {mention.type}
                      </span>
                    </div>

                    {bestCandidate && (
                      <div>
                        <p className="text-xs font-semibold text-gray-600 mb-2">
                          {selectedCandidate ? "Selected" : "Best Match"}
                        </p>
                        <div
                          className={`border p-3 rounded transition-colors ${selectedCandidate ? "bg-purple-50 border-purple-200" : "bg-green-50 border-green-200"}`}
                        >
                          <p
                            className={`text-sm font-medium ${selectedCandidate ? "text-purple-900" : "text-green-900"}`}
                          >
                            {getCandidateLabel(bestCandidate)}
                          </p>
                          <a
                            href={bestCandidate.uri}
                            target="_blank"
                            rel="noopener noreferrer"
                            onClick={(e) => e.stopPropagation()}
                            className="text-xs text-blue-500 hover:underline truncate inline-block mt-1"
                          >
                            {bestCandidate.uri}
                          </a>
                          <p
                            className={`text-xs mt-1 ${selectedCandidate ? "text-purple-700" : "text-green-700"}`}
                          >
                            Score:{" "}
                            <strong>
                              {bestCandidate.score?.toFixed(4) || "N/A"}
                            </strong>
                          </p>
                        </div>
                      </div>
                    )}

                    {isExpanded && mention.candidates.length > 0 && (
                      <div>
                        <p className="text-xs font-semibold text-gray-600 mb-2">
                          Other Candidates
                        </p>
                        <div className="space-y-2">
                          {mention.candidates.map((item) => (
                            <div
                              key={item.uri}
                              onClick={() =>
                                handleSelectCandidate(mentionIdx, item)
                              }
                              className={`border p-2 rounded cursor-pointer hover:bg-blue-100 transition-colors ${selectedCandidate?.uri === item.uri ? "border-purple-400 bg-purple-50" : ""}`}
                            >
                              <p className="text-sm font-medium text-gray-800">
                                {getCandidateLabel(item)}
                              </p>
                              <a
                                href={item.uri}
                                target="_blank"
                                rel="noopener noreferrer"
                                onClick={(e) => e.stopPropagation()}
                                className="text-xs text-blue-500 hover:underline truncate inline-block"
                              >
                                {item.uri}
                                <span className="sr-only">
                                  (opens in new tab)
                                </span>
                              </a>
                              <p className="text-xs text-gray-600 mt-1">
                                Score:{" "}
                                <strong>
                                  {item.score?.toFixed(4) || "N/A"}
                                </strong>
                              </p>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </CardContent>
              </Card>
            );
          })
        ) : (
          <Card>
            <CardContent className="py-6 text-center text-gray-500">
              No mentions detected for this question.
            </CardContent>
          </Card>
        )}
      </div>

      <div className="w-full max-w-4xl flex justify-end gap-3 mt-6 mb-8">
        <Button
          variant="outline"
          onClick={() => onSkipToEditor?.()}
          className="gap-2"
          size="lg"
          disabled={isLoading}
        >
          <PenLine className="w-4 h-4" />
          Write Query Manually
        </Button>
        <Button
          onClick={handleGenerateClick}
          className="gap-2"
          size="lg"
          disabled={isLoading}
        >
          {isLoading ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <Upload className="w-4 h-4" />
          )}
          Generate Query
        </Button>
      </div>

      <Dialog
        open={removeConfirmIdx !== null}
        onOpenChange={(open) => {
          if (!open) setRemoveConfirmIdx(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Remove mention?</DialogTitle>
            <DialogDescription>
              {removeConfirmIdx !== null && (
                <>
                  Remove{" "}
                  <strong>
                    &ldquo;{mentions[removeConfirmIdx]?.text}&rdquo;
                  </strong>{" "}
                  from the list? It will be excluded when generating the query.
                </>
              )}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRemoveConfirmIdx(null)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={() =>
                removeConfirmIdx !== null &&
                handleRemoveMention(removeConfirmIdx)
              }
            >
              Remove
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Overwrite existing results?</DialogTitle>
            <DialogDescription>
              Submitting new selections will regenerate the SPARQL query and
              overwrite any existing query results.
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
                onSubmitAsNew?.(mentions);
              }}
            >
              Start New Trace
            </Button>
            <Button
              onClick={() => {
                setConfirmOpen(false);
                onSubmit?.(mentions);
              }}
            >
              Overwrite
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
