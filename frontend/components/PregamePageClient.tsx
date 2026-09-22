"use client";

import { useSearchParams } from "next/navigation";
import { useState } from "react";

import { PregameDashboard } from "@/components/PregameDashboard";
import { emptyPregameViewModel, toPregameViewModel } from "@/lib/adapters";
import { usePregameBrief } from "@/lib/queries";
import type { PregameBriefRequest } from "@/lib/api";

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "The pre-game brief could not be loaded.";
}

interface PitcherMeta {
  id: number;
  name: string;
  team: string | null;
  throws: "L" | "R" | "—";
}

function normalizeThrows(value: string | null | undefined): "L" | "R" | "—" {
  return value === "L" || value === "R" ? value : "—";
}

export function PregamePageClient() {
  const searchParams = useSearchParams();
  const [request, setRequest] = useState<PregameBriefRequest | null>(null);
  const [pitcherMeta, setPitcherMeta] = useState<PitcherMeta | null>(null);
  const briefQuery = usePregameBrief(request);

  // A pitcher handed off from Player Watch arrives as `?pitcherId=&pitcherName=&pitcherTeam=`.
  const handoffId = Number(searchParams.get("pitcherId"));
  const handoffName = searchParams.get("pitcherName");
  const hasHandoff = Number.isInteger(handoffId) && handoffId > 0 && Boolean(handoffName);

  const rawView = briefQuery.data ? toPregameViewModel(briefQuery.data) : emptyPregameViewModel();
  const view =
    pitcherMeta && pitcherMeta.id === rawView.pitcher.id
      ? {
          ...rawView,
          pitcher: {
            ...rawView.pitcher,
            name: pitcherMeta.name,
            team: pitcherMeta.team ?? "—",
            throws: pitcherMeta.throws,
          },
        }
      : rawView;

  return (
    <PregameDashboard
      {...view}
      error={briefQuery.error ? errorMessage(briefQuery.error) : undefined}
      initialPitcherId={hasHandoff ? handoffId : undefined}
      initialPitcherName={hasHandoff ? (handoffName as string) : undefined}
      initialPitcherTeam={searchParams.get("pitcherTeam")}
      initialPitcherThrows={searchParams.get("pitcherThrows")}
      isLoading={briefQuery.isFetching}
      onGenerate={(nextRequest) => {
        setRequest({
          pitcher_id: nextRequest.pitcherId,
          start_date: nextRequest.startDate,
          end_date: nextRequest.endDate,
        });
        setPitcherMeta(
          nextRequest.pitcherName
            ? {
                id: nextRequest.pitcherId,
                name: nextRequest.pitcherName,
                team: nextRequest.pitcherTeam ?? null,
                throws: normalizeThrows(nextRequest.pitcherThrows),
              }
            : null,
        );
      }}
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
