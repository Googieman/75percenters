export function formatPercentage(value: number | null): string {
  return value === null ? "—" : `${value.toFixed(2)}%`;
}

export function formatSyncTime(value: string | null): string {
  return value ? new Date(value).toLocaleString() : "Not synced yet";
}

type GuidanceSummary = {
  target_reachable: boolean;
  additional_absences_allowed: number;
  additional_attended_hours: number;
};

export function formatGuidance(guidance: GuidanceSummary): string {
  if (!guidance.target_reachable) {
    return "Target is not reachable";
  }

  if (guidance.additional_absences_allowed > 0) {
    return `${guidance.additional_absences_allowed} Margin`;
  }

  if (guidance.additional_attended_hours > 0) {
    return `${guidance.additional_attended_hours} Required`;
  }

  return "0 Margin";
}
