// Typeahead picker for a standard (used by Compare). Accessible combobox with keyboard support.
import { useEffect, useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type { SuggestItem } from "../api/types";
import { useDebounced } from "../lib/hooks";
import { shortTitle } from "../lib/format";

export function StandardPicker({ label, value, onChange, exclude }: { label: string; value: SuggestItem | null; onChange: (s: SuggestItem | null) => void; exclude?: string }) {
  const { t } = useTranslation();
  const id = useId();
  const [text, setText] = useState(value ? value.number ?? value.title : "");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const q = useDebounced(text, 150);
  useEffect(() => setText(value ? value.number ?? value.title : ""), [value]);
  const res = useQuery({
    queryKey: ["suggest", q],
    queryFn: ({ signal }) => api.suggest(q, signal),
    enabled: open && q.trim().length > 0,
    staleTime: 60_000,
  });
  const items = (res.data ?? []).filter((s) => s.kind === "standard" && s.slug !== exclude);
  const pick = (s: SuggestItem) => {
    onChange(s);
    setOpen(false);
  };
  return (
    <div className="relative">
      <label htmlFor={id} className="mb-1 block text-xs font-semibold uppercase tracking-wide text-ink-3">
        {label}
      </label>
      <input
        id={id}
        role="combobox"
        aria-expanded={open && items.length > 0}
        aria-controls={`${id}-list`}
        aria-autocomplete="list"
        aria-activedescendant={open && items[active] ? `${id}-opt-${active}` : undefined}
        value={text}
        onChange={(e) => {
          setText(e.target.value);
          setOpen(true);
          setActive(0);
          if (!e.target.value) onChange(null);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => window.setTimeout(() => setOpen(false), 150)}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") {
            e.preventDefault();
            setActive((a) => Math.min(a + 1, items.length - 1));
          } else if (e.key === "ArrowUp") {
            e.preventDefault();
            setActive((a) => Math.max(a - 1, 0));
          } else if (e.key === "Enter" && items[active]) {
            e.preventDefault();
            pick(items[active]);
          } else if (e.key === "Escape") setOpen(false);
        }}
        placeholder={t("compare.pickerPlaceholder")}
        className="mono h-10 w-full rounded-md border border-line-strong bg-surface px-3 text-[14px] outline-none focus:border-accent"
      />
      {open && items.length > 0 && (
        <ul id={`${id}-list`} role="listbox" className="absolute z-30 mt-1 max-h-72 w-full overflow-y-auto rounded-md border border-line bg-surface py-1 shadow-[var(--shadow-pop)]">
          {items.map((s, i) => (
            <li
              key={s.slug}
              id={`${id}-opt-${i}`}
              role="option"
              aria-selected={i === active}
              onMouseDown={(e) => {
                e.preventDefault();
                pick(s);
              }}
              className={`cursor-pointer px-3 py-2 text-[13px] ${i === active ? "bg-accent-soft" : ""}`}
            >
              <span className="mono font-semibold">{s.number ?? ""}</span> <span className="text-ink-2">{shortTitle(s.title, 70)}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
