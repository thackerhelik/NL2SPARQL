export const RWTH_GPT_PREFIX = "RWTH-GPT-";
const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api";

export type ModelOption = {
  value: string;
  label?: string;
};

export const MODEL_OPTIONS: ModelOption[] = [
  { value: `${RWTH_GPT_PREFIX}gpt-oss-120b` },
];

export const DEFAULT_MODEL = `${RWTH_GPT_PREFIX}gpt-oss-120b`;

function toModelOptions(models: string[]): ModelOption[] {
  return models.map((model) => ({ value: model }));
}

export function mergeModelOptions(
  baseOptions: ModelOption[],
  dynamicModels: string[],
): ModelOption[] {
  const merged: ModelOption[] = [
    ...baseOptions,
    ...toModelOptions(dynamicModels),
  ];
  const seen = new Set<string>();

  return merged.filter((option) => {
    const key = option.value;
    if (seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
}

export async function fetchAvailableModels(): Promise<string[]> {
  const response = await fetch(`${API_BASE}/models`);
  if (!response.ok) {
    throw new Error(`Failed to load models (${response.status})`);
  }

  const data: unknown = await response.json();
  if (!Array.isArray(data)) {
    return [];
  }

  return data.filter((item): item is string => typeof item === "string");
}
