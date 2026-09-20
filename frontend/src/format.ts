export function formatPercentage(value: number | null): string {
  return value === null ? "—" : `${value.toFixed(2)}%`;
}

export function formatSyncTime(value: string | null): string {
  return value ? new Date(value).toLocaleString() : "Not synced yet";
}
