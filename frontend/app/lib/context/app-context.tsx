import {
  createContext,
  useContext,
  useReducer,
  useCallback,
  useEffect,
  type ReactNode,
} from "react";
import type { AgentStatus } from "@/app/lib/api/types";
import { useAnalysisEvents } from "@/app/hooks/use-analysis-events";
import { analysisTaskKey, type AnalysisEvent, type AnalysisTaskSnapshot } from "@/app/lib/analysis-events/types";
import { reduceAnalysisEvent, updateAnalysisTaskMap } from "@/app/lib/analysis-events/adapter";

interface AppState {
  currentModelSelection: number | null;
  currentThreadId: string | null;
  currentThreadRequiresImageInput: boolean;
  agentStatus: AgentStatus;
  chatHistoryVersion: number;
  analysisTasks: Record<string, AnalysisTaskSnapshot>;
  analysisEventVersions: { resume: number; job_description: number };
}

type AppAction =
  | { type: "SET_MODEL_SELECTION"; payload: number | null }
  | { type: "SET_THREAD_ID"; payload: string | null }
  | { type: "SET_THREAD_REQUIRES_IMAGE_INPUT"; payload: boolean }
  | { type: "SET_AGENT_STATUS"; payload: AgentStatus }
  | { type: "BUMP_CHAT_HISTORY_VERSION" }
  | { type: "ANALYSIS_EVENT"; payload: AnalysisEvent };

const SELECTION_STORAGE_KEY = "offerpilot.chat.selection";

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
    case "ANALYSIS_EVENT": {
      const event = action.payload;
      if (event.event === "snapshot" && Array.isArray(event.data.tasks)) {
        const tasks: Record<string, AnalysisTaskSnapshot> = {};
        for (const data of event.data.tasks) {
          if (!data || typeof data !== "object" || Array.isArray(data)) continue;
          const task = reduceAnalysisEvent(undefined, { event: "snapshot", data });
          if (task) tasks[analysisTaskKey(task.resourceType, task.resourceId)] = task;
        }
        return { ...state, analysisTasks: tasks, analysisEventVersions: {
          resume: state.analysisEventVersions.resume + 1,
          job_description: state.analysisEventVersions.job_description + 1,
        } };
      }
      const result = updateAnalysisTaskMap(state.analysisTasks, event);
      if (!result.task) return state;
      const invalidate = ["resume", "job_description", "final", "error"].includes(event.event);
      const resource = result.task.resourceType;
      return { ...state, analysisTasks: result.tasks, analysisEventVersions: invalidate
        ? { ...state.analysisEventVersions, [resource]: state.analysisEventVersions[resource] + 1 }
        : state.analysisEventVersions };
    }
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
    default:
      return state;
  }
}

const AppContext = createContext<{
  state: AppState;
  dispatch: React.Dispatch<AppAction>;
} | null>(null);

export function AppProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(appReducer, initialState, (defaults) => {
    try {
      const parsed: unknown = JSON.parse(
        localStorage.getItem(SELECTION_STORAGE_KEY) || "{}",
      );
      const saved =
        parsed && typeof parsed === "object"
          ? (parsed as Record<string, unknown>)
          : {};
      return {
        ...defaults,
        currentThreadId: typeof saved.thread === "string" ? saved.thread : null,
        currentModelSelection:
          typeof saved.model === "number" &&
          Number.isSafeInteger(saved.model) &&
          saved.model > 0
            ? saved.model
            : null,
      };
    } catch {
      return defaults;
    }
  });
  useEffect(() => {
    try {
      localStorage.setItem(
        SELECTION_STORAGE_KEY,
        JSON.stringify({
          thread: state.currentThreadId,
          model: state.currentModelSelection,
        }),
      );
    } catch {
      /* Persistence is optional; keep the in-memory selection. */
    }
  }, [state.currentThreadId, state.currentModelSelection]);
  const onAnalysisEvent = useCallback((event: AnalysisEvent) => {
    dispatch({ type: "ANALYSIS_EVENT", payload: event });
  }, []);
  useAnalysisEvents(onAnalysisEvent);
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
      (id: number | null) =>
        dispatch({ type: "SET_MODEL_SELECTION", payload: id }),
      [dispatch],
    ),
    setThreadId: useCallback(
      (id: string | null) => dispatch({ type: "SET_THREAD_ID", payload: id }),
      [dispatch],
    ),
    setThreadRequiresImageInput: useCallback(
      (value: boolean) =>
        dispatch({ type: "SET_THREAD_REQUIRES_IMAGE_INPUT", payload: value }),
      [dispatch],
    ),
    setAgentStatus: useCallback(
      (status: AgentStatus) =>
        dispatch({ type: "SET_AGENT_STATUS", payload: status }),
      [dispatch],
    ),
    bumpChatHistoryVersion: useCallback(
      () => dispatch({ type: "BUMP_CHAT_HISTORY_VERSION" }),
      [dispatch],
    ),
  };
}
