import {
  createContext,
  useContext,
  useReducer,
  useCallback,
  type ReactNode,
} from "react";
import type { AgentStatus } from "@/app/lib/api/types";
import { useAnalysisEvents } from "@/app/hooks/use-analysis-events";
import { updateAnalysisTaskMap } from "@/app/lib/analysis-events/adapter";
import type {
  AnalysisEvent,
  AnalysisResourceType,
  AnalysisTaskSnapshot,
} from "@/app/lib/analysis-events/types";

interface AppState {
  currentModelSelection: number | null;
  currentThreadId: string | null;
  currentThreadRequiresImageInput: boolean;
  agentStatus: AgentStatus;
  chatHistoryVersion: number;
  analysisTasks: Record<string, AnalysisTaskSnapshot>;
  analysisEventVersions: Record<AnalysisResourceType, number>;
}

type AppAction =
  | { type: "SET_MODEL_SELECTION"; payload: number | null }
  | { type: "SET_THREAD_ID"; payload: string | null }
  | { type: "SET_THREAD_REQUIRES_IMAGE_INPUT"; payload: boolean }
  | { type: "SET_AGENT_STATUS"; payload: AgentStatus }
  | { type: "BUMP_CHAT_HISTORY_VERSION" }
  | { type: "ANALYSIS_EVENT"; payload: AnalysisEvent };

const initialState: AppState = {
  currentModelSelection: null,
  currentThreadId: null,
  currentThreadRequiresImageInput: false,
  agentStatus: "idle",
  chatHistoryVersion: 0,
  analysisTasks: {},
  analysisEventVersions: { resume: 0, job_description: 0 },
};

function appReducer(state: AppState, action: AppAction): AppState {
  switch (action.type) {
    case "SET_MODEL_SELECTION":
      return { ...state, currentModelSelection: action.payload };
    case "SET_THREAD_ID":
      return { ...state, currentThreadId: action.payload };
    case "SET_THREAD_REQUIRES_IMAGE_INPUT":
      return { ...state, currentThreadRequiresImageInput: action.payload };
    case "SET_AGENT_STATUS":
      return { ...state, agentStatus: action.payload };
    case "BUMP_CHAT_HISTORY_VERSION":
      return {
        ...state,
        chatHistoryVersion: state.chatHistoryVersion + 1,
      };
    case "ANALYSIS_EVENT": {
      const result = updateAnalysisTaskMap(state.analysisTasks, action.payload);
      if (!result.task) return state;
      const shouldRefreshResource = [
        "resume",
        "job_description",
        "final",
        "error",
      ].includes(action.payload.event);
      return {
        ...state,
        analysisTasks: result.tasks,
        analysisEventVersions: shouldRefreshResource
          ? {
              ...state.analysisEventVersions,
              [result.task.resourceType]:
                state.analysisEventVersions[result.task.resourceType] + 1,
            }
          : state.analysisEventVersions,
      };
    }
    default:
      return state;
  }
}

const AppContext = createContext<{
  state: AppState;
  dispatch: React.Dispatch<AppAction>;
} | null>(null);

export function AppProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(appReducer, initialState);
  const handleAnalysisEvent = useCallback(
    (event: AnalysisEvent) => dispatch({ type: "ANALYSIS_EVENT", payload: event }),
    [],
  );
  useAnalysisEvents(handleAnalysisEvent);

  return (
    <AppContext.Provider value={{ state, dispatch }}>
      {children}
    </AppContext.Provider>
  );
}

export function useAppContext() {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useAppContext must be used within AppProvider");
  return ctx;
}

export function useAppActions() {
  const { dispatch } = useAppContext();

  return {
    setModelSelection: useCallback(
      (id: number | null) => dispatch({ type: "SET_MODEL_SELECTION", payload: id }),
      [dispatch]
    ),
    setThreadId: useCallback(
      (id: string | null) => dispatch({ type: "SET_THREAD_ID", payload: id }),
      [dispatch]
    ),
    setThreadRequiresImageInput: useCallback(
      (value: boolean) =>
        dispatch({ type: "SET_THREAD_REQUIRES_IMAGE_INPUT", payload: value }),
      [dispatch]
    ),
    setAgentStatus: useCallback(
      (status: AgentStatus) =>
        dispatch({ type: "SET_AGENT_STATUS", payload: status }),
      [dispatch]
    ),
    bumpChatHistoryVersion: useCallback(
      () => dispatch({ type: "BUMP_CHAT_HISTORY_VERSION" }),
      [dispatch]
    ),
  };
}
