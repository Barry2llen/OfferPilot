import type { HTMLAttributes, ReactNode } from "react";

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
  shadow?: "card" | "brand" | "elevated" | "none";
  radius?: "sm" | "md" | "lg";
  padding?: "sm" | "md" | "lg";
}

const shadowMap: Record<string, string> = {
  card: "shadow-card",
  brand: "shadow-sm",
  elevated: "shadow-elevated",
  none: "",
};

const radiusMap: Record<string, string> = {
  sm: "rounded-lg",
  md: "rounded-xl",
  lg: "rounded-xl",
};

const paddingMap: Record<string, string> = {
  sm: "p-3",
  md: "p-4",
  lg: "p-6",
};

export default function Card({
  children,
  shadow = "card",
  radius = "lg",
  padding = "md",
  className = "",
  ...props
}: CardProps) {
  return (
    <div
      className={`bg-surface-primary border border-border-light ${shadowMap[shadow]} ${radiusMap[radius]} ${paddingMap[padding]} ${className}`}
      {...props}
    >
      {children}
    </div>
  );
}
