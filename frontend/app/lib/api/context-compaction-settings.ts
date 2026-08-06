import { apiRequest } from "./client";
import type {
  ContextCompactionSettingsResponse,
  ContextCompactionSettingsUpdate,
} from "./types";

export const contextCompactionSettingsApi = {
  get: () =>
    apiRequest<ContextCompactionSettingsResponse>(
      "/context-compaction-settings",
    ),

  update: (data: ContextCompactionSettingsUpdate) =>
    apiRequest<ContextCompactionSettingsResponse>(
      "/context-compaction-settings",
      {
        method: "PATCH",
        body: JSON.stringify(data),
      },
    ),
};
