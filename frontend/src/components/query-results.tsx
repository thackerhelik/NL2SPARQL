"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { SparqlBindingValue, SparqlResponse } from "@/lib/types";

interface QueryResultsProps {
  results: SparqlResponse | null;
}

export function QueryResults({ results }: QueryResultsProps) {
  const bindings = results?.results?.bindings || [];
  const vars = results?.head?.vars || [];

  if (typeof results?.boolean === "boolean") {
    return (
      <div className="w-full space-y-4">
        <Card>
          <CardHeader>
            <CardTitle>ASK Query Result</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-3 py-2">
              <span
                className={`text-2xl font-bold ${results.boolean ? "text-green-600" : "text-red-600"}`}
              >
                {results.boolean ? "True" : "False"}
              </span>
              <span className="text-sm text-gray-500">
                {results.boolean
                  ? "The pattern exists in the dataset."
                  : "The pattern does not exist in the dataset."}
              </span>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (bindings.length === 0) {
    return (
      <div className="text-center text-gray-500 py-8">
        <p>No results found</p>
      </div>
    );
  }

  const renderCellValue = (value: SparqlBindingValue) => {
    if (value.type === "uri") {
      return (
        <a
          href={value.value}
          target="_blank"
          rel="noopener noreferrer"
          className="text-blue-600 hover:underline break-all"
        >
          {value.value}
        </a>
      );
    }
    return <span className="break-words">{value.value}</span>;
  };

  return (
    <div className="w-full space-y-4">
      <div className="text-sm text-gray-600 mb-4">
        Found <strong>{bindings.length}</strong> result
        {bindings.length !== 1 ? "s" : ""}
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Results</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  {vars.map((v) => (
                    <TableHead key={v} className="capitalize font-bold">
                      {v}
                    </TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {bindings.map((binding, idx) => (
                  <TableRow key={idx}>
                    {vars.map((v) => (
                      <TableCell key={`${idx}-${v}`} className="py-2">
                        {binding[v] ? renderCellValue(binding[v]) : "-"}
                      </TableCell>
                    ))}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
