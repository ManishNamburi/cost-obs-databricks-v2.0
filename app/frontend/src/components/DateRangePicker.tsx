import { useRef, useState } from "react";
import { useUpdatingIndicator } from "@/hooks/useUpdatingIndicator";
import {
  format,
  isValid,
  parseISO,
  startOfMonth,
  subDays,
  subMonths,
} from "date-fns";
import type { DateRange } from "@/types/billing";
import { Spinner } from "./Spinner";
import { FloatingMenu } from "./ui/FloatingMenu";

interface DateRangePickerProps {
  value: DateRange;
  onChange: (range: DateRange) => void;
}

// End date is always yesterday: today's cost data is incomplete/inaccurate.
const yesterdayDate = () => subDays(new Date(), 1);
const yesterday = () => format(yesterdayDate(), "yyyy-MM-dd");
const inclusiveWindow = (days: number) => {
  const end = yesterdayDate();
  return {
    startDate: format(subDays(end, days - 1), "yyyy-MM-dd"),
    endDate: format(end, "yyyy-MM-dd"),
  };
};
const boundedStart = (candidate: Date, end: Date) =>
  candidate > end ? end : candidate;

const PRESETS = [
  { label: "Last 7 days", getDates: () => inclusiveWindow(7) },
  { label: "Last 14 days", getDates: () => inclusiveWindow(14) },
  { label: "Last 30 days", getDates: () => inclusiveWindow(30) },
  { label: "Last 90 days", getDates: () => inclusiveWindow(90) },
  {
    label: "This month",
    getDates: () => {
      const end = yesterdayDate();
      return {
        startDate: format(boundedStart(startOfMonth(new Date()), end), "yyyy-MM-dd"),
        endDate: format(end, "yyyy-MM-dd"),
      };
    },
  },
  {
    label: "Last 6 months",
    getDates: () => {
      const end = yesterdayDate();
      return {
        startDate: format(subMonths(end, 6), "yyyy-MM-dd"),
        endDate: format(end, "yyyy-MM-dd"),
      };
    },
  },
  {
    label: "Year to date",
    getDates: () => {
      const end = yesterdayDate();
      return {
        startDate: `${new Date().getFullYear()}-01-01`,
        endDate: format(end, "yyyy-MM-dd"),
      };
    },
  },
];

export function DateRangePicker({ value, onChange }: DateRangePickerProps) {
  const menuAnchorRef = useRef<HTMLDivElement>(null);
  const { updating, arm } = useUpdatingIndicator();
  const [isOpen, setIsOpen] = useState(false);
  const [customStart, setCustomStart] = useState(value.startDate);
  const [customEnd, setCustomEnd] = useState(value.endDate);
  const [customError, setCustomError] = useState<string | null>(null);

  const formatDisplayDate = (dateStr: string) => {
    try {
      return format(parseISO(dateStr), "MMM d, yyyy");
    } catch {
      return dateStr;
    }
  };

  const handlePresetClick = (preset: typeof PRESETS[0]) => {
    const dates = preset.getDates();
    onChange(dates);
    setCustomStart(dates.startDate);
    setCustomEnd(dates.endDate);
    setCustomError(null);
    arm();
    setIsOpen(false);
  };

  const handleCustomApply = () => {
    const parsedStart = parseISO(customStart);
    const parsedEnd = parseISO(customEnd);
    if (!customStart || !customEnd || !isValid(parsedStart) || !isValid(parsedEnd)) {
      setCustomError("Enter a valid start and end date.");
      return;
    }
    if (parsedStart > parsedEnd) {
      setCustomError("Start date must be on or before end date.");
      return;
    }
    if (customEnd > yesterday()) {
      setCustomError("End date must be yesterday or earlier.");
      return;
    }
    if (parsedStart < subMonths(parsedEnd, 6)) {
      setCustomError("Date range cannot exceed 6 calendar months.");
      return;
    }
    setCustomError(null);
    onChange({ startDate: customStart, endDate: customEnd });
    arm();
    setIsOpen(false);
  };

  return (
    <div ref={menuAnchorRef} className="relative w-full sm:w-80">
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        aria-haspopup="dialog"
        aria-expanded={isOpen}
        className="co-filter flex w-full items-center gap-2 px-4"
      >
        {updating ? (
          <Spinner size="sm" />
        ) : (
          <svg className="h-4 w-4 shrink-0 text-gray-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
          </svg>
        )}
        <span className="flex-1 text-center">
          {updating ? "Updating…" : `${formatDisplayDate(value.startDate)} to ${formatDisplayDate(value.endDate)}`}
        </span>
        <svg className={`h-4 w-4 shrink-0 text-gray-500 transition-transform ${isOpen ? "rotate-180" : ""}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {isOpen && (
        <>
          <div
            className="fixed inset-0 z-10"
            onClick={() => setIsOpen(false)}
          />
          <FloatingMenu
            anchorRef={menuAnchorRef}
            role="dialog"
            aria-label="Choose date range"
            gap={8}
            className="co-filter-menu w-[min(20rem,calc(100vw-2rem))] p-4"
          >
            <div className="mb-4">
              <h4 className="mb-2 text-sm font-medium text-gray-700">Quick Select</h4>
              <div className="flex flex-wrap gap-2">
                {PRESETS.map((preset) => (
                  <button
                    key={preset.label}
                    onClick={() => handlePresetClick(preset)}
                    className="rounded-md bg-gray-100 px-3 py-1 text-xs font-medium text-gray-700 hover:bg-gray-200"
                  >
                    {preset.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="border-t border-gray-200 pt-4">
              <h4 className="mb-2 text-sm font-medium text-gray-700">Custom Range</h4>
              <div className="flex gap-2">
                <div className="flex-1">
                  <label htmlFor="custom-date-start" className="block text-xs text-gray-500">Start</label>
                  <input
                    id="custom-date-start"
                    type="date"
                    value={customStart}
                    max={yesterday()}
                    aria-invalid={customError ? "true" : undefined}
                    aria-describedby={customError ? "custom-date-error" : undefined}
                    onChange={(e) => {
                      setCustomStart(e.target.value);
                      setCustomError(null);
                    }}
                    className="mt-1 w-full rounded-md border border-gray-300 px-2 py-1 text-sm"
                  />
                </div>
                <div className="flex-1">
                  <label htmlFor="custom-date-end" className="block text-xs text-gray-500">End</label>
                  <input
                    id="custom-date-end"
                    type="date"
                    value={customEnd}
                    max={yesterday()}
                    aria-invalid={customError ? "true" : undefined}
                    aria-describedby={customError ? "custom-date-error" : undefined}
                    onChange={(e) => {
                      setCustomEnd(e.target.value);
                      setCustomError(null);
                    }}
                    className="mt-1 w-full rounded-md border border-gray-300 px-2 py-1 text-sm"
                  />
                </div>
              </div>
              {customError && (
                <p id="custom-date-error" role="alert" className="mt-2 text-xs text-red-700">
                  {customError}
                </p>
              )}
              <button
                onClick={handleCustomApply}
                className="btn-brand mt-3 w-full rounded-md px-4 py-2 text-sm font-medium text-white transition-colors"
              >
                Apply
              </button>
            </div>
          </FloatingMenu>
        </>
      )}
    </div>
  );
}
