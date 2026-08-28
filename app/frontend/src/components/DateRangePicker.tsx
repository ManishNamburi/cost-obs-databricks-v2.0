import { useState } from "react";
import { useUpdatingIndicator, UPDATING_SPINNER_PATH } from "@/hooks/useUpdatingIndicator";
import { format, parseISO, subDays, subMonths, startOfMonth } from "date-fns";
import type { DateRange } from "@/types/billing";

interface DateRangePickerProps {
  value: DateRange;
  onChange: (range: DateRange) => void;
}

// End date is always yesterday — today's cost data is incomplete/inaccurate
const yesterday = () => format(subDays(new Date(), 1), "yyyy-MM-dd");

const PRESETS = [
  { label: "Last 7 days", getDates: () => ({ startDate: format(subDays(new Date(), 8), "yyyy-MM-dd"), endDate: yesterday() }) },
  { label: "Last 14 days", getDates: () => ({ startDate: format(subDays(new Date(), 15), "yyyy-MM-dd"), endDate: yesterday() }) },
  { label: "Last 30 days", getDates: () => ({ startDate: format(subDays(new Date(), 31), "yyyy-MM-dd"), endDate: yesterday() }) },
  { label: "Last 90 days", getDates: () => ({ startDate: format(subDays(new Date(), 91), "yyyy-MM-dd"), endDate: yesterday() }) },
  { label: "This month", getDates: () => ({ startDate: format(startOfMonth(new Date()), "yyyy-MM-dd"), endDate: yesterday() }) },
  { label: "Last 6 months", getDates: () => ({ startDate: format(subMonths(new Date(), 6), "yyyy-MM-dd"), endDate: yesterday() }) },
  { label: "Year to date", getDates: () => ({ startDate: `${new Date().getFullYear()}-01-01`, endDate: yesterday() }) },
];

export function DateRangePicker({ value, onChange }: DateRangePickerProps) {
  const { updating, arm } = useUpdatingIndicator();
  const [isOpen, setIsOpen] = useState(false);
  const [customStart, setCustomStart] = useState(value.startDate);
  const [customEnd, setCustomEnd] = useState(value.endDate);

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
    arm();
    setIsOpen(false);
  };

  const handleCustomApply = () => {
    onChange({ startDate: customStart, endDate: customEnd });
    arm();
    setIsOpen(false);
  };

  return (
    <div className="relative">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="co-filter flex w-80 items-center gap-2 px-4"
      >
        {updating ? (
          <svg className="h-4 w-4 shrink-0 animate-spin text-lava" viewBox="0 0 24 24" fill="none">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d={UPDATING_SPINNER_PATH} />
          </svg>
        ) : (
          <svg className="h-4 w-4 shrink-0 text-gray-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
          </svg>
        )}
        <span className="flex-1 text-center">
          {updating ? "Updating…" : `${formatDisplayDate(value.startDate)} – ${formatDisplayDate(value.endDate)}`}
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
          <div className="co-filter-menu absolute right-0 z-20 mt-2 w-80 p-4">
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
                  <label className="block text-xs text-gray-500">Start</label>
                  <input
                    type="date"
                    value={customStart}
                    onChange={(e) => setCustomStart(e.target.value)}
                    className="mt-1 w-full rounded-md border border-gray-300 px-2 py-1 text-sm"
                  />
                </div>
                <div className="flex-1">
                  <label className="block text-xs text-gray-500">End</label>
                  <input
                    type="date"
                    value={customEnd}
                    onChange={(e) => setCustomEnd(e.target.value)}
                    className="mt-1 w-full rounded-md border border-gray-300 px-2 py-1 text-sm"
                  />
                </div>
              </div>
              <button
                onClick={handleCustomApply}
                className="btn-brand mt-3 w-full rounded-md px-4 py-2 text-sm font-medium text-white transition-colors"
              >
                Apply
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
