"use client";

import { Card, CardAction, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { SquarePen, Plus } from "lucide-react";
import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

export function QuestionCard({
  text,
  onCreate,
  onEditAsNew,
  onEditOverwrite,
  hasDownstreamData,
}: {
  text: string;
  onCreate?: () => void;
  onEditAsNew: () => void;
  onEditOverwrite?: () => void;
  hasDownstreamData?: boolean;
}) {
  const [confirmOpen, setConfirmOpen] = useState(false);

  const handleEditClick = () => {
    if (hasDownstreamData) {
      setConfirmOpen(true);
    } else {
      onEditAsNew();
    }
  };

  return (
    <>
      <Card className="w-full max-w-2xl">
        <CardHeader>
          <CardTitle>{text}</CardTitle>
          <CardAction>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="icon"
                onClick={handleEditClick}
                aria-label="Edit question"
              >
                <SquarePen className="h-4 w-4" />
              </Button>
              <Button
                variant="outline"
                size="icon"
                onClick={() => onCreate?.()}
                aria-label="New trace"
                title="Start new trace"
              >
                <Plus className="h-4 w-4" />
              </Button>
            </div>
          </CardAction>
        </CardHeader>
      </Card>

      <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Edit question?</DialogTitle>
            <DialogDescription>
              Editing the question will clear all detected mentions, the SPARQL
              query, and any query results.
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
                onEditAsNew();
              }}
            >
              Start New Trace
            </Button>
            <Button
              onClick={() => {
                setConfirmOpen(false);
                onEditOverwrite?.();
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
