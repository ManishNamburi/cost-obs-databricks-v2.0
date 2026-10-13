export interface DeploymentMetadata {
  deployed_at: string | null;
  deployer: string | null;
  commit_sha: string | null;
  available: boolean;
  source: string;
}

function parsedDate(value: string | null): Date | null {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function formatDeploymentBadgeDate(
  value: string | null,
  now = new Date(),
  timeZone = Intl.DateTimeFormat().resolvedOptions().timeZone,
): string | null {
  const date = parsedDate(value);
  if (!date) return null;
  const deployedYear = Number(new Intl.DateTimeFormat("en-US", {
    year: "numeric",
    timeZone,
  }).format(date));
  const currentYear = Number(new Intl.DateTimeFormat("en-US", {
    year: "numeric",
    timeZone,
  }).format(now));
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    ...(deployedYear === currentYear ? {} : { year: "numeric" as const }),
    timeZone,
  }).format(date);
}

function timestampInZone(date: Date, timeZone: string): string {
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
    timeZoneName: "short",
    timeZone,
  }).format(date);
}

export function formatDeploymentTimestamp(
  value: string | null,
  localTimeZone = Intl.DateTimeFormat().resolvedOptions().timeZone,
): string | null {
  const date = parsedDate(value);
  if (!date) return null;
  const utc = timestampInZone(date, "UTC");
  if (localTimeZone === "UTC" || localTimeZone === "Etc/UTC") return utc;
  return `${utc} · ${timestampInZone(date, localTimeZone)}`;
}

export function abbreviateCommit(commitSha: string | null): string | null {
  const value = commitSha?.trim();
  return value ? value.slice(0, 8) : null;
}
