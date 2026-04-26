"use client";

import type { ButtonHTMLAttributes, ReactNode } from "react";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md" | "lg";
  pill?: boolean;
  children: ReactNode;
}

const base =
  "inline-flex items-center justify-center gap-2 font-sans font-semibold transition-all duration-150 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/40 disabled:opacity-40 disabled:pointer-events-none cursor-pointer";

const variants: Record<string, string> = {
  primary:
    "bg-text-charcoal text-white hover:bg-text-charcoal/90 active:bg-text-charcoal shadow-sm",
  secondary:
    "bg-surface-secondary text-text-primary hover:bg-border-default active:bg-border-default/80",
  ghost:
    "bg-transparent text-text-secondary hover:bg-black/[0.04] active:bg-black/[0.08]",
  danger:
    "bg-error-text text-white hover:bg-error-text/90 active:bg-error-text/80",
};

const sizes: Record<string, string> = {
  sm: "text-[13px] h-8 px-3.5 rounded-lg",
  md: "text-sm h-10 px-5 rounded-lg",
  lg: "text-base h-12 px-6 rounded-xl",
};

export default function Button({
  variant = "primary",
  size = "md",
  pill = false,
  children,
  className = "",
  ...props
}: ButtonProps) {
  return (
    <button
      className={`${base} ${variants[variant]} ${sizes[size]} ${
        pill ? "rounded-[9999px]" : ""
      } ${className}`}
      {...props}
    >
      {children}
    </button>
  );
}
