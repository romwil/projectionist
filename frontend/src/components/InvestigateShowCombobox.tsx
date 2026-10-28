import { useEffect, useId, useMemo, useRef, useState } from "react";
import {
  filterInvestigateShows,
  formatInvestigateShowLabel,
} from "../lib/episodeInvestigate.js";
import { moveTypeaheadIndex } from "../lib/tagSearch.js";

/**
 * Searchable show picker for Admin → Libraries → Investigate episodes.
 * Combobox: type to filter, arrow keys + Enter to pick, Escape to close.
 */
/** Props for InvestigateShowCombobox. `any` = API/handler bags until Wave 4 client generics. */
type InvestigateShowComboboxProps = {
  shows?: any[];
  value?: string | number;
  onChange?: (...args: any[]) => void;
  disabled?: boolean;
};

export default function InvestigateShowCombobox({
  shows = [],
  value = "",
  onChange,
  disabled = false,
}: InvestigateShowComboboxProps) {
  const listId = useId();
  const rootRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const selected = useMemo(
    () => (shows as any).find((item: any) => String(item.id) === String(value)) || null,
    [shows, value],
  );
  const [query, setQuery] = useState(() => formatInvestigateShowLabel(selected));
  const [open, setOpen] = useState(false);
  const [highlight, setHighlight] = useState(-1);

  useEffect(() => {
    if (!open) {
      setQuery(formatInvestigateShowLabel(selected));
    }
  }, [selected, open]);

  const filtered = useMemo(
    () => filterInvestigateShows(shows, open ? query : "", { limit: 50 }),
    [shows, open, query],
  );

  useEffect(() => {
    if (!open) return undefined;
    function onPointerDown(event: any) {
      if (!rootRef.current?.contains(event.target)) {
        setOpen(false);
        setHighlight(-1);
      }
    }
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [open]);

  useEffect(() => {
    if (!open || highlight < 0) return;
    const node = document.getElementById(`${listId}-opt-${highlight}`);
    node?.scrollIntoView({ block: "nearest" });
  }, [open, highlight, listId]);

  function commitShow(show: any) {
    const nextId = show ? String(show.id) : "";
    onChange?.(nextId);
    setQuery(formatInvestigateShowLabel(show));
    setOpen(false);
    setHighlight(-1);
  }

  function clearShow() {
    onChange?.("");
    setQuery("");
    setOpen(true);
    setHighlight(-1);
    inputRef.current?.focus();
  }

  function handleKeyDown(event: any) {
    if (disabled) return;
    if (event.key === "ArrowDown" || event.key === "ArrowUp" || event.key === "Home" || event.key === "End") {
      event.preventDefault();
      if (!open) setOpen(true);
      setHighlight((prev) => moveTypeaheadIndex(prev, event.key, filtered.length));
      return;
    }
    if (event.key === "Enter") {
      if (open && highlight >= 0 && filtered[highlight]) {
        event.preventDefault();
        commitShow(filtered[highlight]);
      }
      return;
    }
    if (event.key === "Escape") {
      if (open) {
        event.preventDefault();
        setOpen(false);
        setHighlight(-1);
        setQuery(formatInvestigateShowLabel(selected));
      }
    }
  }

  const activeId = open && highlight >= 0 ? `${listId}-opt-${highlight}` : undefined;

  return (
    <div className="investigate-show-combobox" ref={rootRef}>
      <div className="investigate-show-input-row">
        <input
          ref={inputRef}
          id="investigate-show-input"
          type="search"
          role="combobox"
          autoComplete="off"
          spellCheck={false}
          data-testid="investigate-show"
          aria-label="Show"
          aria-autocomplete="list"
          aria-expanded={open}
          aria-controls={listId}
          aria-activedescendant={activeId}
          placeholder="Type a show title…"
          value={query}
          disabled={disabled}
          onFocus={() => {
            if (!disabled) {
              setOpen(true);
              setHighlight(-1);
            }
          }}
          onChange={(event) => {
            const next = event.target.value;
            setQuery(next);
            setOpen(true);
            setHighlight(-1);
            if (selected && next !== formatInvestigateShowLabel(selected)) {
              onChange?.("");
            }
          }}
          onKeyDown={handleKeyDown}
        />
        {value ? (
          <button
            type="button"
            className="ghost investigate-show-clear"
            data-testid="investigate-show-clear"
            aria-label="Clear show"
            disabled={disabled}
            onClick={clearShow}
          >
            Clear
          </button>
        ) : null}
      </div>
      {open && !disabled ? (
        <ul
          id={listId}
          className="investigate-show-list"
          role="listbox"
          aria-label="Matching shows"
          data-testid="investigate-show-list"
        >
          {filtered.length ? (
            filtered.map((item, index) => {
              const label = formatInvestigateShowLabel(item);
              const isActive = index === highlight;
              const isSelected = String(item.id) === String(value);
              return (
                <li key={item.id} role="presentation">
                  <button
                    type="button"
                    id={`${listId}-opt-${index}`}
                    role="option"
                    aria-selected={isActive || isSelected}
                    className={`investigate-show-option${isActive ? " is-active" : ""}`}
                    data-testid="investigate-show-option"
                    onMouseEnter={() => setHighlight(index)}
                    onMouseDown={(event) => {
                      event.preventDefault();
                      commitShow(item);
                    }}
                  >
                    {label}
                  </button>
                </li>
              );
            })
          ) : (
            <li className="investigate-show-empty" role="option" aria-selected={false} data-testid="investigate-show-empty">
              {(shows as any).length
                ? `No shows match “${String(query || "").trim()}”.`
                : "No shows loaded yet."}
            </li>
          )}
        </ul>
      ) : null}
    </div>
  );
}
