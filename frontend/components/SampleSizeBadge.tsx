import type { SampleStatus } from "@/lib/types";

interface SampleSizeBadgeProps {
  status: SampleStatus;
  sampleSize?: number;
  compact?: boolean;
}

export function SampleSizeBadge({
  status,
  sampleSize,
  compact = false,
}: SampleSizeBadgeProps) {
  const sufficient = status === "sufficient";
  const statusLabel = sufficient ? "Sufficient" : "Small sample";

  return (
    <span className="sample-badge" data-status={status} data-compact={compact}>
      <span className="sample-badge__dot" aria-hidden="true" />
      {sampleSize !== undefined ? `n=${sampleSize} · ` : ""}
      {statusLabel}
    </span>
  );
}
