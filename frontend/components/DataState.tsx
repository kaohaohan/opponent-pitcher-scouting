import type { ReactNode } from "react";

interface DataStateProps {
  children: ReactNode;
  kind?: "empty" | "error" | "loading";
  onRetry?: () => void;
}

export function DataState({ children, kind = "empty", onRetry }: DataStateProps) {
  return (
    <div className="data-state" data-kind={kind} role={kind === "error" ? "alert" : undefined}>
      <span className="data-state__dot" aria-hidden="true" />
      <span>{children}</span>
      {onRetry ? (
        <button className="secondary-button" onClick={onRetry} type="button">
          Retry
        </button>
      ) : null}
    </div>
  );
}
