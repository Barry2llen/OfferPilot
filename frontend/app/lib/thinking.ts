import type { ThinkingType } from "@/app/lib/api/types";

export const providerThinkingTypes: Record<string, ThinkingType[]> = {
  OpenAI: ["effort"], "OpenAI Compatible": ["effort"],
  Google: ["level", "budget"], DeepSeek: ["deepseek"], Anthropic: ["adaptive", "budget"],
};

/** Allowed values per enumerated thinking type; mirrors backend `validate_model_options`. */
export const thinkingValueOptions: Record<Exclude<ThinkingType, "budget">, string[]> = {
  effort: ["none", "minimal", "low", "medium", "high", "xhigh", "max"],
  level: ["minimal", "low", "medium", "high"],
  deepseek: ["disabled", "low", "high", "max"],
  adaptive: ["low", "medium", "high", "xhigh", "max"],
};

export function defaultThinkingType(provider: string): ThinkingType {
  return providerThinkingTypes[provider]?.[0] ?? "effort";
}
