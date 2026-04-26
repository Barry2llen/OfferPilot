"use client";

import {
  createContext,
  useContext,
  useReducer,
  useCallback,
  type ReactNode,
} from "react";
import type { AgentStatus } from "@/app/lib/api/types";

interface AppState {
  currentModelSelection: number | null;
  currentThreadId: string | null;
  currentResumeId: number | null;
  agentStatus: AgentStatus;
}

type AppAction =
  | { type: "SET_MODEL_SELECTION"; payload: number | null }
  | { type: "SET_THREAD_ID"; payload: string | null }
  | { type: "SET_RESUME_ID"; payload: number | null }
  | { type: "SET_AGENT_STATUS"; payload: AgentStatus };

const initialState: AppState = {
  currentModelSelection: null,
  currentThreadId: null,
  currentResumeId: null,
  agentStatus: "idle",
};

function appReducer(state: AppState, action: AppAction): AppState {
  switch (action.type) {
    case "SET_MODEL_SELECTION":
      return { ...state, currentModelSelection: action.payload };
    case "SET_THREAD_ID":
      return { ...state, currentThreadId: action.payload };
    case "SET_RESUME_ID":
      return { ...state, currentResumeId: action.payload };
    case "SET_AGENT_STATUS":
      return { ...state, agentStatus: action.payload };
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
    setResumeId: useCallback(
      (id: number | null) => dispatch({ type: "SET_RESUME_ID", payload: id }),
      [dispatch]
    ),
    setAgentStatus: useCallback(
      (status: AgentStatus) =>
        dispatch({ type: "SET_AGENT_STATUS", payload: status }),
      [dispatch]
    ),
  };
}
