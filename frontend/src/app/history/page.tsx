"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import {
  getAllTraces,
  deleteTrace,
  clearAllTraces,
  formatTimestamp,
  type Trace,
} from "@/lib/logging";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ArrowLeft, Trash2, Download } from "lucide-react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

export default function HistoryPage() {
  const [traces, setTraces] = useState<Trace[]>(() => getAllTraces());
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedTrace, setSelectedTrace] = useState<Trace | null>(null);

  const formatTraceId = (traceId: string) =>
    traceId.length > 20
      ? `${traceId.slice(0, 5)}...${traceId.slice(-6)}`
      : traceId;

  const filteredTraces = useMemo(
    () =>
      traces
        .filter(
          (trace) =>
            trace.id.toLowerCase().includes(searchQuery.toLowerCase()) ||
            trace.question?.toLowerCase().includes(searchQuery.toLowerCase()),
        )
        .sort((a, b) => b.createdAt - a.createdAt),
    [searchQuery, traces],
  );

  const handleDelete = (traceId: string) => {
    deleteTrace(traceId);
    const updated = traces.filter((t) => t.id !== traceId);
    setTraces(updated);
    if (selectedTrace?.id === traceId) {
      setSelectedTrace(null);
    }
  };

  const handleClearAll = () => {
    if (
      confirm(
        "Are you sure you want to clear all traces? This cannot be undone.",
      )
    ) {
      clearAllTraces();
      setTraces([]);
      setSelectedTrace(null);
    }
  };

  const handleExport = () => {
    const dataStr = JSON.stringify(filteredTraces, null, 2);
    const dataBlob = new Blob([dataStr], { type: "application/json" });
    const url = URL.createObjectURL(dataBlob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `traces_${Date.now()}.json`;
    link.click();
    URL.revokeObjectURL(url);
  };

  const handleDownloadTrace = (trace: Trace) => {
    const dataStr = JSON.stringify(trace, null, 2);
    const dataBlob = new Blob([dataStr], { type: "application/json" });
    const url = URL.createObjectURL(dataBlob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `trace_${trace.id}.json`;
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="flex flex-col items-center pt-8 gap-8 pb-8">
      <div className="w-full max-w-4xl px-4">
        {/* Back button */}
        <Link href="/">
          <Button variant="outline" className="gap-2 mb-6">
            <ArrowLeft className="w-4 h-4" />
            Back
          </Button>
        </Link>

        {/* Page title */}
        <h1 className="text-3xl font-bold text-gray-900 mb-8">Query History</h1>

        {/* Search bar */}
        <div className="mb-6">
          <Input
            type="text"
            placeholder="Search by Trace ID or Question..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full"
          />
        </div>

        {/* Action buttons */}
        <div className="flex gap-3 mb-6">
          <Button
            onClick={handleExport}
            disabled={filteredTraces.length === 0}
            className="gap-2"
          >
            <Download className="w-4 h-4" />
            Export as JSON
          </Button>
          <Button
            onClick={handleClearAll}
            variant="destructive"
            disabled={traces.length === 0}
          >
            <Trash2 className="w-4 h-4" />
            Clear All
          </Button>
        </div>

        {/* Results count */}
        <p className="text-sm text-gray-600 mb-4">
          {filteredTraces.length} of {traces.length} trace
          {traces.length !== 1 ? "s" : ""}
        </p>

        {filteredTraces.length === 0 ? (
          <Card>
            <CardContent className="pt-8 pb-8">
              <p className="text-center text-gray-500">
                {traces.length === 0
                  ? "No traces found. Start a new query to create one."
                  : "No traces match your search."}
              </p>
            </CardContent>
          </Card>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Traces list */}
            <div className="lg:col-span-2">
              <Card>
                <CardHeader>
                  <CardTitle>Traces</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="overflow-x-auto">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Trace ID</TableHead>
                          <TableHead>Question</TableHead>
                          <TableHead>Created</TableHead>
                          <TableHead>Action</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {filteredTraces.map((trace) => (
                          <TableRow
                            key={trace.id}
                            className="cursor-pointer hover:bg-gray-50"
                            onClick={() => setSelectedTrace(trace)}
                          >
                            <TableCell
                              className="font-mono text-xs"
                              title={trace.id}
                            >
                              {formatTraceId(trace.id)}
                            </TableCell>
                            <TableCell className="truncate max-w-xs">
                              {trace.question || "—"}
                            </TableCell>
                            <TableCell className="text-sm text-gray-600">
                              {formatTimestamp(trace.createdAt)}
                            </TableCell>
                            <TableCell>
                              <div className="flex items-center gap-1">
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  aria-label={`Download trace ${trace.id}`}
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    handleDownloadTrace(trace);
                                  }}
                                >
                                  <Download className="w-4 h-4" />
                                </Button>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  aria-label={`Delete trace ${trace.id}`}
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    handleDelete(trace.id);
                                  }}
                                >
                                  <Trash2 className="w-4 h-4 text-red-600" />
                                </Button>
                              </div>
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                </CardContent>
              </Card>
            </div>

            {/* Trace details panel */}
            {selectedTrace && (
              <div className="lg:col-span-1">
                <Card className="sticky top-8">
                  <CardHeader>
                    <CardTitle className="text-lg">Trace Details</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <div>
                      <p className="text-xs text-gray-600 font-semibold">
                        Trace ID
                      </p>
                      <p className="font-mono text-xs break-all text-blue-900 bg-blue-50 p-2 rounded mt-1">
                        {selectedTrace.id}
                      </p>
                    </div>

                    <div className="flex gap-2">
                      <Link
                        href={`/?trace=${selectedTrace.id}`}
                        className="w-full"
                      >
                        <Button className="w-full">Resume in Home</Button>
                      </Link>
                    </div>

                    <div>
                      <p className="text-xs text-gray-600 font-semibold">
                        Question
                      </p>
                      <p className="text-sm mt-1 break-words">
                        {selectedTrace.question || "—"}
                      </p>
                    </div>

                    <div>
                      <p className="text-xs text-gray-600 font-semibold">
                        Created
                      </p>
                      <p className="text-sm mt-1">
                        {formatTimestamp(selectedTrace.createdAt)}
                      </p>
                    </div>

                    {!!selectedTrace.mentionCandidates && (
                      <div>
                        <p className="text-xs text-gray-600 font-semibold">
                          Mention Candidates
                        </p>
                        <p className="text-xs text-gray-500 mt-1 bg-gray-50 p-2 rounded max-h-24 overflow-y-auto">
                          <code>
                            {JSON.stringify(
                              selectedTrace.mentionCandidates,
                              null,
                              2,
                            )}
                          </code>
                        </p>
                      </div>
                    )}

                    {!!selectedTrace.selectedMentions && (
                      <div>
                        <p className="text-xs text-gray-600 font-semibold">
                          Selected Mentions
                        </p>
                        <p className="text-xs text-gray-500 mt-1 bg-gray-50 p-2 rounded max-h-24 overflow-y-auto">
                          <code>
                            {JSON.stringify(
                              selectedTrace.selectedMentions,
                              null,
                              2,
                            )}
                          </code>
                        </p>
                      </div>
                    )}

                    {selectedTrace.sparqlQuery && (
                      <div>
                        <p className="text-xs text-gray-600 font-semibold">
                          SPARQL Query
                        </p>
                        <p className="text-xs text-gray-900 mt-1 bg-gray-50 p-2 rounded max-h-24 overflow-y-auto font-mono">
                          {selectedTrace.sparqlQuery}
                        </p>
                      </div>
                    )}

                    {!!selectedTrace.queryResults && (
                      <div>
                        <p className="text-xs text-gray-600 font-semibold">
                          Query Results
                        </p>
                        <p className="text-xs text-gray-500 mt-1 bg-gray-50 p-2 rounded max-h-24 overflow-y-auto">
                          <code>
                            {JSON.stringify(
                              selectedTrace.queryResults,
                              null,
                              2,
                            )}
                          </code>
                        </p>
                      </div>
                    )}
                  </CardContent>
                </Card>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
