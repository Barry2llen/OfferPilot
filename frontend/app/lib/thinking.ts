import type { ThinkingType } from "@/app/lib/api/types";

export const providerThinkingTypes: Record<string, ThinkingType[]> = {
  OpenAI: ["effort"], "OpenAI Compatible": ["effort"],
  Google: ["level", "budget"], DeepSeek: ["deepseek"], Anthropic: ["adaptive", "budget"],
};

export function defaultThinkingType(provider: string): ThinkingType {
  return providerThinkingTypes[provider]?.[0] ?? "effort";
}
