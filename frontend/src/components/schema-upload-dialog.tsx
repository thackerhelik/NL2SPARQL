"use client";

import { useState } from "react";
import { Loader2, Upload } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { useSchemaContext } from "@/contexts/SchemaContext";

interface SchemaUploadDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function SchemaUploadDialog({
  open,
  onOpenChange,
}: SchemaUploadDialogProps) {
  const { uploadSchema } = useSchemaContext();
  const [file, setFile] = useState<File | null>(null);
  const [schemaName, setSchemaName] = useState("");
  const [endpointUrl, setEndpointUrl] = useState("");
  const [baseIri, setBaseIri] = useState("");
  const [isUploading, setIsUploading] = useState(false);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      const selectedFile = e.target.files[0];
      setFile(selectedFile);
      // Automatically set a default name if none is provided
      if (!schemaName) {
        setSchemaName(selectedFile.name.replace(/\.[^/.]+$/, ""));
      }
    }
  };

  const handleUpload = async () => {
    if (!file) return;

    setIsUploading(true);
    try {
      const formData = new FormData();
      formData.append("schema_file", file);

      if (schemaName.trim()) {
        formData.append("name", schemaName.trim());
      }

      if (endpointUrl.trim()) {
        formData.append("endpoint_url", endpointUrl.trim());
      }

      if (baseIri.trim()) {
        formData.append("base_iri", baseIri.trim());
      }

      await uploadSchema(formData);

      // Reset state and close dialog on success
      setFile(null);
      setSchemaName("");
      setEndpointUrl("");
      setBaseIri("");
      onOpenChange(false);
    } catch (error) {
      // Error is already handled/logged in context,
      // but we could show a local alert here if desired.
      console.error("Upload failed in component:", error);
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Upload New Schema</DialogTitle>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          <div className="grid w-full items-center gap-1.5">
            <label htmlFor="schema-name" className="text-sm font-medium">
              Schema Name
            </label>
            <Input
              id="schema-name"
              type="text"
              placeholder="e.g. DBLP Schema"
              value={schemaName}
              onChange={(e) => setSchemaName(e.target.value)}
              disabled={isUploading}
            />
          </div>
          <div className="grid w-full items-center gap-1.5">
            <label htmlFor="schema-file" className="text-sm font-medium">
              Schema File
            </label>
            <Input
              id="schema-file"
              type="file"
              accept=".xml,.rdf,.ttl,.n3,.jsonld"
              onChange={handleFileChange}
              disabled={isUploading}
            />
            <p className="text-xs text-muted-foreground">
              Supports RDF/XML, Turtle, N3, and JSON-LD formats.
            </p>
          </div>
          <div className="grid w-full items-center gap-1.5">
            <label htmlFor="endpoint-url" className="text-sm font-medium">
              SPARQL Endpoint URL{" "}
              <span className="text-muted-foreground font-normal">
                (optional)
              </span>
            </label>
            <Input
              id="endpoint-url"
              type="url"
              placeholder="https://sparql.dblp.org/sparql"
              value={endpointUrl}
              onChange={(e) => setEndpointUrl(e.target.value)}
              disabled={isUploading}
            />
            <p className="text-xs text-muted-foreground">
              The SPARQL endpoint to query this schema against.
            </p>
          </div>
          <div className="grid w-full items-center gap-1.5">
            <label htmlFor="base-iri" className="text-sm font-medium">
              Base IRI{" "}
              <span className="text-muted-foreground font-normal">
                (optional)
              </span>
            </label>
            <Input
              id="base-iri"
              type="text"
              placeholder="https://dblp.org/rdf/schema#"
              value={baseIri}
              onChange={(e) => setBaseIri(e.target.value)}
              disabled={isUploading}
            />
            <p className="text-xs text-muted-foreground">
              Base IRI used to resolve relative URIs in the schema.
            </p>
          </div>
        </div>
        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={isUploading}
          >
            Cancel
          </Button>
          <Button onClick={handleUpload} disabled={!file || isUploading}>
            {isUploading ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Uploading...
              </>
            ) : (
              <>
                <Upload className="mr-2 h-4 w-4" />
                Upload
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
