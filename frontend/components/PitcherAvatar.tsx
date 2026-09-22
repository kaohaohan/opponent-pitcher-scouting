"use client";

import { useState } from "react";

import { pitcherHeadshotUrl } from "@/lib/mlb-images";

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0]!.slice(0, 2).toUpperCase();
  return `${parts[0]![0]}${parts[parts.length - 1]![0]}`.toUpperCase();
}

export interface PitcherAvatarProps {
  playerId: number | null;
  name: string;
  size?: number;
  className?: string;
}

/**
 * Circular pitcher headshot, or an initials fallback when there's no id,
 * the request fails, or the image can't be decoded — never a broken-image
 * icon.
 */
export function PitcherAvatar({ playerId, name, size = 40, className }: PitcherAvatarProps) {
  const [failed, setFailed] = useState(false);
  const classes = ["pitcher-avatar", className].filter(Boolean).join(" ");

  if (!playerId || failed) {
    return (
      <div
        aria-hidden="true"
        className={`${classes} pitcher-avatar--fallback`}
        style={{ width: size, height: size, fontSize: Math.max(10, Math.round(size * 0.36)) }}
      >
        {initials(name)}
      </div>
    );
  }

  return (
    <img
      alt=""
      className={classes}
      height={size}
      loading="lazy"
      onError={() => setFailed(true)}
      src={pitcherHeadshotUrl(playerId, Math.max(size * 2, 80))}
      style={{ width: size, height: size }}
      width={size}
    />
  );
}
