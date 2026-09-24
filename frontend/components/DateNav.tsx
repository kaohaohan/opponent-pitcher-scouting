"use client";

/**
 * "Today" on MLB's calendar, not the viewer's. The schedule API files games
 * under their US Eastern date, so a Taiwan-morning viewer's local date is
 * already tomorrow's slate while tonight's games are still in progress.
 */
export function todayIso(): string {
  // en-CA formats as YYYY-MM-DD.
  return new Intl.DateTimeFormat("en-CA", { timeZone: "America/New_York" }).format(new Date());
}

export function shiftDate(date: string, days: number): string {
  const [year, month, day] = date.split("-").map(Number);
  const next = new Date(Date.UTC(year, month - 1, day + days));
  return next.toISOString().slice(0, 10);
}

interface DateNavProps {
  date: string;
  onChange: (date: string) => void;
}

/**
 * Previous day / date input / Today / Next day controls, extracted from the
 * old `GamePicker` so both game discovery and any future date-scoped view
 * can share the same date-switching UI.
 */
export function DateNav({ date, onChange }: DateNavProps) {
  return (
    <div className="date-nav">
      <button type="button" className="secondary-button" onClick={() => onChange(shiftDate(date, -1))}>
        ← Previous day
      </button>
      <input
        type="date"
        value={date}
        onChange={(event) => event.target.value && onChange(event.target.value)}
        aria-label="Choose a date"
      />
      <button type="button" className="secondary-button" onClick={() => onChange(todayIso())}>
        Today
      </button>
      <button type="button" className="secondary-button" onClick={() => onChange(shiftDate(date, 1))}>
        Next day →
      </button>
    </div>
  );
}
