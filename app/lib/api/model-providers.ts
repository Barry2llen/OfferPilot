import { apiRequest } from "./client";
import type {
  ModelProviderResponse,
  ModelProviderCreate,
  ModelProviderUpdate,
} from "./types";

export const modelProvidersApi = {
  list: () => apiRequest<ModelProviderResponse[]>("/model-providers"),

  get: (name: string) =>
    apiRequest<ModelProviderResponse>(`/model-providers/${name}`),

  create: (data: ModelProviderCreate) =>
    apiRequest<ModelProviderResponse>("/model-providers", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  update: (name: string, data: ModelProviderUpdate) =>
    apiRequest<ModelProviderResponse>(`/model-providers/${name}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  delete: (name: string) =>
    apiRequest<void>(`/model-providers/${name}`, { method: "DELETE" }),
};
