import { useQuery } from "@tanstack/react-query";
import { Clock } from "lucide-react";
import { InfoPopover } from "@/components/ui/InfoPopover";
import {
  abbreviateCommit,
  formatDeploymentBadgeDate,
  formatDeploymentTimestamp,
  type DeploymentMetadata,
} from "@/utils/deploymentMetadata";

export function DeploymentBadge({
  metadata,
  loading = false,
  variant = "status",
  triggerClassName,
}: {
  metadata: DeploymentMetadata | null | undefined;
  loading?: boolean;
  variant?: "status" | "control";
  triggerClassName?: string;
}) {
  const badgeDate = formatDeploymentBadgeDate(metadata?.deployed_at ?? null);
  const deployedAt = formatDeploymentTimestamp(metadata?.deployed_at ?? null);
  const commit = abbreviateCommit(metadata?.commit_sha ?? null);
  const triggerText = badgeDate ?? "Deploy info";
  const processStartApproximation = metadata?.source?.includes("process_start") ?? false;
  const resolvedTriggerClassName = triggerClassName ?? (
    variant === "control"
      ? "rail-control-border relative inline-flex h-[28px] shrink-0 items-center gap-[5px] rounded-[7px] border bg-white/[.07] px-[8px] text-[11.5px] font-medium text-[#E9EFED] transition-colors hover:bg-[#243F49] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#FF3621]/35 focus-visible:ring-offset-1 focus-visible:ring-offset-[#1B3139]"
      : "rail-status-badge inline-flex h-[22px] w-[104px] min-w-0 shrink-0 items-center justify-center gap-[3px] overflow-hidden rounded-[4px] bg-green-500/20 px-[6px] text-[10px] font-bold leading-[10px] text-green-200 transition-colors hover:bg-green-400/25 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-green-300/40"
  );

  return (
    <span
      data-testid="deployment-badge"
      className={variant === "control"
        ? "inline-flex h-[28px] shrink-0 items-center align-middle"
        : "inline-flex h-[22px] w-[104px] shrink-0 items-center align-middle leading-none"}
    >
      <InfoPopover
        label={`Deployment information: ${triggerText}`}
        className=""
        placement="bottom"
        panelClassName="w-max max-w-[calc(100vw-1rem)] border border-white/[.10] bg-[#0B2026] text-[11.5px]"
        triggerClassName={resolvedTriggerClassName}
        content={loading ? (
          "Loading deployment details…"
        ) : (
          <>
            <span>
              {deployedAt
                ? processStartApproximation
                  ? `Server process started approximately ${deployedAt} (may reflect a restart, not deployment)`
                  : `Deployed ${deployedAt}`
                : "Deployment date unavailable"}
            </span>
            {metadata?.deployer && <span> · by {metadata.deployer}</span>}
            {commit && <span> · commit {commit}</span>}
          </>
        )}
      >
        {variant === "control" ? (
          <>
            <Clock data-testid="deployment-clock" size={14} strokeWidth={1.8} aria-hidden="true" />
            <span data-testid="deployment-badge-date" className="hidden whitespace-nowrap min-[1180px]:inline">
              {triggerText}
            </span>
          </>
        ) : (
          <>
            <span data-testid="deployment-status-dot" className="rail-status-dot healthy-status-dot h-[5px] w-[5px] shrink-0 rounded-full bg-green-400" />
            <span data-testid="deployment-badge-date" className="hidden whitespace-nowrap lg:inline">
              {triggerText}
            </span>
            <Clock data-testid="deployment-clock" size={10} strokeWidth={1.8} aria-hidden="true" />
          </>
        )}
      </InfoPopover>
    </span>
  );
}

export function DeploymentBadgeFromApi({
  variant,
  triggerClassName,
}: {
  variant?: "status" | "control";
  triggerClassName?: string;
}) {
  const { data, isLoading } = useQuery<DeploymentMetadata | null>({
    queryKey: ["deployment-metadata"],
    queryFn: async () => {
      const response = await fetch("/api/deployment");
      if (!response.ok) return null;
      return response.json();
    },
    staleTime: Infinity,
    retry: 1,
  });

  return (
    <DeploymentBadge
      metadata={data}
      loading={isLoading}
      variant={variant}
      triggerClassName={triggerClassName}
    />
  );
}
