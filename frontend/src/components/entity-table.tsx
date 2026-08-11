"use client";

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { CheckCircle2 } from "lucide-react";

interface Item {
  entity_url: string;
  entity_label: string;
  entity_type: string;
  score: number;
}

interface EntityTableProps {
  items: Item[];
  onSelectItem?: (item: Item) => void;
}

export function EntityTable({ items, onSelectItem }: EntityTableProps) {
  return (
    <div className="w-full overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            {onSelectItem && (
              <TableHead className="min-w-16 text-center">Select</TableHead>
            )}
            <TableHead className="min-w-64">Entity URI</TableHead>
            <TableHead className="min-w-96">Entity Label</TableHead>
            <TableHead className="min-w-24">Entity Type</TableHead>
            <TableHead className="min-w-20">Score</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {items.map((item, index) => (
            <TableRow key={index}>
              {onSelectItem && (
                <TableCell className="text-center">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => onSelectItem(item)}
                    className="hover:bg-green-50"
                  >
                    <CheckCircle2 className="w-5 h-5 text-green-600" />
                  </Button>
                </TableCell>
              )}
              <TableCell>
                <a
                  href={item.entity_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-blue-500 hover:underline break-all"
                >
                  {item.entity_url}
                </a>
              </TableCell>
              <TableCell className="break-words">{item.entity_label}</TableCell>
              <TableCell>{item.entity_type}</TableCell>
              <TableCell>{item.score}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
