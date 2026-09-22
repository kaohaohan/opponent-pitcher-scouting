/**
 * MLB's Cloudinary-hosted player headshot CDN, keyed by MLBAM player id.
 * The `d_` (default image) transform makes the request itself resolve to
 * MLB's own generic-player silhouette when a specific headshot doesn't
 * exist, so most requests never 404 — `PitcherAvatar` still handles a
 * network-level failure with its own fallback.
 */
export function pitcherHeadshotUrl(playerId: number, widthPx = 120): string {
  return `https://img.mlbstatic.com/mlb-photos/image/upload/d_people:generic:headshot:67:current.png,w_${widthPx},q_auto:best/v1/people/${playerId}/headshot/67/current`;
}
