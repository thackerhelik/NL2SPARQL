import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { AlertCircleIcon } from "lucide-react";

export function MentionInstruction() {
  return (
    <Alert className="mb-6">
      <AlertCircleIcon className="mr-2" />
      <AlertTitle>Instructions</AlertTitle>
      <AlertDescription>
        Click the &quot;Show more&quot; button to expand each mention, then
        select the best matching candidate from the list.
      </AlertDescription>
    </Alert>
  );
}
