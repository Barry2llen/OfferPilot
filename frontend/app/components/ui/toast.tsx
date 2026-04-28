"use client";

import {
  createContext,
  useContext,
  useState,
  useCallback,
  type ReactNode,
} from "react";

interface Toast {
  id: number;
  message: string;
  variant: "success" | "error" | "warning" | "info";
  exiting?: boolean;
}

interface ToastContextType {
  addToast: (message: string, variant?: Toast["variant"]) => void;
}

const ToastContext = createContext<ToastContextType | null>(null);

let toastId = 0;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const addToast = useCallback(
    (message: string, variant: Toast["variant"] = "info") => {
      const id = ++toastId;
      setToasts((prev) => [...prev, { id, message, variant }]);
      setTimeout(() => {
        setToasts((prev) =>
          prev.map((t) => (t.id === id ? { ...t, exiting: true } : t))
        );
        setTimeout(() => {
          setToasts((prev) => prev.filter((t) => t.id !== id));
        }, 200);
      }, 4000);
    },
    []
  );

  return (
    <ToastContext.Provider value={{ addToast }}>
      {children}
      <div className="fixed bottom-4 right-4 z-[100] flex flex-col gap-2 pointer-events-none">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className={`pointer-events-auto px-4 py-2.5 rounded-xl text-sm font-medium shadow-elevated border transition-all duration-200 ${
              toast.exiting ? "opacity-0 translate-y-2" : "opacity-100"
            } ${
              toast.variant === "success"
                ? "bg-success-bg text-success-text border-success-text/20"
                : toast.variant === "error"
                  ? "bg-error-bg text-error-text border-error-text/20"
                  : toast.variant === "warning"
                    ? "bg-warning-bg text-warning-text border-warning-text/20"
                    : "bg-info-bg text-info-text border-info-text/20"
            }`}
          >
            {toast.message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within ToastProvider");
  return ctx;
}
