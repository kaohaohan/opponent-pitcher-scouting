"use client";

import { PregameDashboard } from "@/components/PregameDashboard";
import { emptyPregameViewModel, toPregameViewModel } from "@/lib/adapters";
import { usePregameBrief } from "@/lib/queries";
import type { PregameBriefRequest } from "@/lib/api";
import { useState } from "react";

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "The pre-game brief could not be loaded.";
}

export function PregamePageClient() {
  const [request, setRequest] = useState<PregameBriefRequest | null>(null);
  const briefQuery = usePregameBrief(request);
  const view = briefQuery.data ? toPregameViewModel(briefQuery.data) : emptyPregameViewModel();

  return (
    <PregameDashboard
      {...view}
      error={briefQuery.error ? errorMessage(briefQuery.error) : undefined}
      isLoading={briefQuery.isFetching}
      onGenerate={(nextRequest) =>
        setRequest({
          pitcher_id: nextRequest.pitcherId,
          start_date: nextRequest.startDate,
          end_date: nextRequest.endDate,
        })
      }
      onRetry={request ? () => void briefQuery.refetch() : undefined}
      statusMessage={
        briefQuery.isFetching
          ? "Fetching pitch data and generating a brief…"
          : briefQuery.data
            ? "Brief loaded from the FastAPI pregame service."
            : briefQuery.error
              ? "The request failed. Check the inputs or retry."
              : undefined
      }
    />
  );
}
