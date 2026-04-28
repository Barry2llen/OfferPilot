import { apiRequest } from "./client";
import type {
  ModelSelectionResponse,
  ModelSelectionCreate,
  ModelSelectionUpdate,
} from "./types";

export const modelSelectionsApi = {
  list: () => apiRequest<ModelSelectionResponse[]>("/model-selections"),

  get: (id: number) =>
    apiRequest<ModelSelectionResponse>(`/model-selections/${id}`),

  create: (data: ModelSelectionCreate) =>
    apiRequest<ModelSelectionResponse>("/model-selections", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  update: (id: number, data: ModelSelectionUpdate) =>
    apiRequest<ModelSelectionResponse>(`/model-selections/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  delete: (id: number) =>
    apiRequest<void>(`/model-selections/${id}`, { method: "DELETE" }),
};
