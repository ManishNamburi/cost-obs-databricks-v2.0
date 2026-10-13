import type { ReactNode } from "react";
import { Spinner } from "@/components/Spinner";
import { InfoPopover } from "@/components/ui/InfoPopover";

interface KPICardProps {
  title: string;
  value: ReactNode;
  subtitle?: ReactNode;
  icon?: ReactNode;
  onActivate?: () => void;
  ariaLabel?: string;
  infoText?: string;
  infoLabel?: string;
  isLoading?: boolean;
  unavailableReason?: string;
  titleNoWrap?: boolean;
  className?: string;
  valueClassName?: string;
  valueTestId?: string;
}

export function KPICard({
  title,
  value,
  subtitle,
  icon,
  onActivate,
  ariaLabel,
  infoText,
  infoLabel,
  isLoading = false,
  unavailableReason,
  titleNoWrap = false,
  className = "",
  valueClassName = "",
  valueTestId,
}: KPICardProps) {
  const interactive = Boolean(onActivate && !unavailableReason);
  const content = (
    <span className="co-kpi-card__layout">
      {icon && <span className="co-kpi-card__icon">{icon}</span>}
      <span className="co-kpi-card__content">
        <span className="co-kpi-card__title">
          <span className={titleNoWrap ? "co-kpi-card__title--nowrap whitespace-nowrap" : ""}>{title}</span>
          {infoText && (
            <InfoPopover
              className="pointer-events-auto relative z-[2] ml-1.5"
              label={infoLabel ?? `About ${title}`}
              text={infoText}
              stopClick
            />
          )}
        </span>
        {isLoading ? (
          <span className="co-kpi-card__loading">
            <Spinner size="sm" />
          </span>
        ) : (
          <span
            data-testid={valueTestId}
            className={`co-kpi-card__value ${valueClassName}`}
          >
            {unavailableReason ? "N/A" : value}
          </span>
        )}
        {!isLoading && (
          <span className="co-kpi-card__subtitle">
            {unavailableReason ? `Unavailable: ${unavailableReason}` : subtitle}
          </span>
        )}
        {interactive && (
          <span className="co-kpi-card__trend" aria-hidden="true">
            See trend <span>→</span>
          </span>
        )}
      </span>
    </span>
  );

  const sharedProps = {
    className: `co-kpi-card ${interactive ? "co-kpi-card--interactive" : ""} ${unavailableReason ? "co-kpi-card--unavailable" : ""} ${className}`.trim(),
    title: unavailableReason,
  };

  if (interactive) {
    return (
      <div {...sharedProps}>
        <button
          type="button"
          className="co-kpi-card co-kpi-card--interactive co-kpi-card__hit-area"
          onClick={onActivate}
          aria-label={ariaLabel ?? `See ${title} trend`}
        >
          <span className="sr-only">See trend</span>
        </button>
        {content}
      </div>
    );
  }

  return <div {...sharedProps}>{content}</div>;
}
