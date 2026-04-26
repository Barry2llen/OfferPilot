"use client";

import type { ReactNode } from "react";

interface FormDrawerProps {
  open: boolean;
  title: string;
  children: ReactNode;
  onClose: () => void;
}

export default function FormDrawer({
  open,
  title,
  children,
  onClose,
}: FormDrawerProps) {
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[70] flex justify-end">
      <div
        className="fixed inset-0 bg-black/15 backdrop-blur-sm"
        onClick={onClose}
      />
      <div className="relative w-full max-w-md bg-white h-full shadow-elevated overflow-y-auto animate-slide-in">
        <div className="sticky top-0 bg-white border-b border-border-light px-6 py-4 flex items-center justify-between">
          <h2 className="font-display text-lg font-semibold text-text-primary">
            {title}
          </h2>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-surface-secondary transition-colors"
            aria-label="Close"
          >
            <svg
              className="w-5 h-5 text-text-muted"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
          </button>
        </div>
        <div className="p-6">{children}</div>
      </div>

      <style jsx>{`
        @keyframes slideIn {
          from {
            transform: translateX(100%);
          }
          to {
            transform: translateX(0);
          }
        }
        .animate-slide-in {
          animation: slideIn 0.2s ease-out;
        }
      `}</style>
    </div>
  );
}
