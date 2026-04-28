import type { HTMLAttributes, ReactNode } from "react";

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
  shadow?: "card" | "brand" | "elevated" | "none";
  radius?: "sm" | "md" | "lg";
  padding?: "sm" | "md" | "lg";
}

const shadowMap: Record<string, string> = {
  card: "shadow-card",
  brand: "shadow-brand-glow",
  elevated: "shadow-elevated",
  none: "",
};

const radiusMap: Record<string, string> = {
  sm: "rounded-lg",
  md: "rounded-[13px]",
  lg: "rounded-[20px]",
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
      className={`bg-white border border-border-light ${shadowMap[shadow]} ${radiusMap[radius]} ${paddingMap[padding]} ${className}`}
      {...props}
    >
      {children}
    </div>
  );
}
