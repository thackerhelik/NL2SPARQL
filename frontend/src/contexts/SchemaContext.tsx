"use client";

import React, {
  createContext,
  useContext,
  useState,
  useEffect,
  ReactNode,
} from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api";

export interface SchemaMetadata {
  schema_id: string;
  name: string;
  endpoint: string;
}

interface SchemaContextType {
  schemas: SchemaMetadata[];
  isLoading: boolean;
  error: string | null;
  refreshSchemas: () => Promise<void>;
  uploadSchema: (formData: FormData) => Promise<SchemaMetadata>;
}

const SchemaContext = createContext<SchemaContextType | undefined>(undefined);

const STORAGE_KEY = "app_cached_schemas";

/**
 * Load schemas from localStorage
 */
function loadFromStorage(): SchemaMetadata[] {
  try {
    if (typeof window === "undefined") {
      return [];
    }
    const cached = localStorage.getItem(STORAGE_KEY);
    return cached ? JSON.parse(cached) : [];
  } catch (error) {
    console.error("Failed to load schemas from localStorage:", error);
    return [];
  }
}

/**
 * Save schemas to localStorage
 */
function saveToStorage(schemas: SchemaMetadata[]): void {
  try {
    if (typeof window === "undefined") {
      return;
    }
    localStorage.setItem(STORAGE_KEY, JSON.stringify(schemas));
  } catch (error) {
    console.error("Failed to save schemas to localStorage:", error);
  }
}

export function SchemaProvider({ children }: { children: ReactNode }) {
  const [schemas, setSchemas] = useState<SchemaMetadata[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Initialize schemas from backend on mount
  useEffect(() => {
    // Try to load from localStorage first for immediate display
    const cached = loadFromStorage();
    if (cached.length > 0) {
      setSchemas(cached);
      console.log(`Restored ${cached.length} schemas from localStorage`);
    }

    // Then fetch fresh data from backend
    refreshSchemas();
  }, []);

  const refreshSchemas = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE}/schema`);
      if (!response.ok) {
        throw new Error(`Failed to fetch schemas: ${response.statusText}`);
      }
      const data: SchemaMetadata[] = await response.json();
      console.log("Fetched schemas from backend:", data);
      setSchemas(data);
      saveToStorage(data);
      console.log(`Fetched and cached ${data.length} schemas from backend`);
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : "Unknown error";
      setError(errorMsg);
      console.error("Error refreshing schemas:", err);
    } finally {
      setIsLoading(false);
    }
  };

  const uploadSchema = async (formData: FormData): Promise<SchemaMetadata> => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE}/schema/upload`, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        let errorMsg = `Upload failed: ${response.statusText}`;
        try {
          const errorData = await response.json();
          errorMsg = errorData.detail || errorMsg;
        } catch {
          /* use default */
        }
        throw new Error(errorMsg);
      }

      const newSchema: SchemaMetadata = await response.json();
      console.log("Uploaded new schema:", newSchema);

      // Refresh the list to include the new schema
      await refreshSchemas();

      return newSchema;
    } catch (err) {
      const errorMsg =
        err instanceof Error ? err.message : "Unknown error during upload";
      setError(errorMsg);
      console.error("Error uploading schema:", err);
      throw err;
    } finally {
      setIsLoading(false);
    }
  };

  const value: SchemaContextType = {
    schemas,
    isLoading,
    error,
    refreshSchemas,
    uploadSchema,
  };

  return (
    <SchemaContext.Provider value={value}>{children}</SchemaContext.Provider>
  );
}

/**
 * Hook to use Schema Context
 * Must be called within a component wrapped by SchemaProvider
 */
export function useSchemaContext(): SchemaContextType {
  const context = useContext(SchemaContext);
  if (context === undefined) {
    throw new Error("useSchemaContext must be used within a SchemaProvider");
  }
  return context;
}
