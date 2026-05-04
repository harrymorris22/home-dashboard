import { type HTMLAttributes, type ReactNode } from "react";

export function Card({
  children,
  className = "",
  strong = false,
  ...rest
}: HTMLAttributes<HTMLDivElement> & { children: ReactNode; strong?: boolean }) {
  const base = strong ? "glass-strong" : "glass";
  return (
    <div className={`${base} p-5 ${className}`} {...rest}>
      {children}
    </div>
  );
}
