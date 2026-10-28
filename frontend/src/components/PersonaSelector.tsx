import { useState, useCallback } from "react";
import { useAnchoredPopover } from "../hooks/useAnchoredPopover";
import { personaChipLabel, personaDropdownLabel } from "../lib/personaLabels";

const SLIDER_LABELS = [
  { key: "val_bro_prof", lo: "Casual", hi: "Professorial" },
  { key: "val_dipl_snark", lo: "Diplomatic", hi: "Snarky" },
  { key: "val_pass_auto", lo: "Passive", hi: "Autonomous" },
  { key: "val_depth", lo: "Quick picks", hi: "Deep dives" },
  { key: "val_obscurity", lo: "Mainstream", hi: "Niche" },
  { key: "val_verbosity", lo: "Concise", hi: "Detailed" },
  { key: "val_formality", lo: "Chatty", hi: "Structured" },
];

/** Props for SliderRow. `any` = API/handler bags until Wave 4 client generics. */
type SliderRowProps = {
  label?: any;
  value?: number;
  onChange?: (...args: any[]) => void;
};

function SliderRow({ label, value, onChange }: SliderRowProps) {
  return (
    <label className="persona-slider-row">
      <span className="persona-slider-lo">{(label as any).lo}</span>
      <input
        type="range"
        min="0"
        max="1"
        step="0.05"
        value={value}
        onChange={(e) => onChange?.(Number(e.target.value))}
        className="persona-slider"
      />
      <span className="persona-slider-hi">{(label as any).hi}</span>
    </label>
  );
}

/** Props for PersonaModal. `any` = API/handler bags until Wave 4 client generics. */
type PersonaModalProps = {
  persona?: any;
  onSave?: (...args: any[]) => void;
  onDelete?: (...args: any[]) => void;
  onCancel?: (...args: any[]) => void;
};

function PersonaModal({ persona, onSave, onDelete, onCancel }: PersonaModalProps) {
  const isNew = !persona;
  const [form, setForm] = useState<any>({
    name: persona?.name || "",
    val_bro_prof: persona?.val_bro_prof ?? 0.5,
    val_dipl_snark: persona?.val_dipl_snark ?? 0.5,
    val_pass_auto: persona?.val_pass_auto ?? 0.5,
    val_depth: persona?.val_depth ?? 0.5,
    val_obscurity: persona?.val_obscurity ?? 0.5,
    val_verbosity: persona?.val_verbosity ?? 0.5,
    val_formality: persona?.val_formality ?? 0.5,
    accent_color: persona?.accent_color || "",
  });
  const isBuiltin = persona?.visibility === "builtin";

  const set = (key: any, val: any) => setForm((prev: any) => ({ ...prev, [key]: val }));

  return (
    <div className="persona-modal-backdrop" onClick={onCancel}>
      <div className="persona-modal" onClick={(e) => e.stopPropagation()}>
        <h3 className="persona-modal-title">{isNew ? "New Persona" : `Edit "${form.name}"`}</h3>

        <input
          className="persona-name-input"
          type="text"
          placeholder="Persona name"
          value={form.name}
          onChange={(e) => set("name", e.target.value)}
          disabled={isBuiltin}
          maxLength={100}
          autoFocus
        />

        <div className="persona-sliders">
          {SLIDER_LABELS.map((label) => (
            <SliderRow
              key={label.key}
              label={label}
              value={form[label.key]}
              onChange={(v) => set(label.key, v)}
            />
          ))}
        </div>

        <div className="persona-modal-actions">
          {!isNew && !isBuiltin && onDelete && (
            <button type="button" className="btn-danger" onClick={() => onDelete(persona.id)}>
              Delete
            </button>
          )}
          <span className="spacer" />
          <button type="button" className="ghost" onClick={onCancel}>Cancel</button>
          <button
            type="button"
            className="btn-primary"
            disabled={!form.name.trim()}
            onClick={() => onSave?.(form)}
          >
            {isNew ? "Create" : "Save"}
          </button>
        </div>
      </div>
    </div>
  );
}

/** Props for PersonaSelector. `any` = API/handler bags until Wave 4 client generics. */
type PersonaSelectorProps = {
  personas?: any;
  activePersonaId?: string;
  onSelect?: (...args: any[]) => void;
  onCreate?: (...args: any[]) => void;
  onUpdate?: (...args: any[]) => void;
  onDelete?: (...args: any[]) => void;
  onSetDefault?: (...args: any[]) => void;
  defaultPersonaId?: string;
};

export default function PersonaSelector({
  personas = [],
  activePersonaId,
  onSelect,
  onCreate,
  onUpdate,
  onDelete,
  onSetDefault,
  defaultPersonaId,
}: PersonaSelectorProps) {
  const [modal, setModal] = useState<any | null>(null);
  const { open, setOpen, rootRef } = useAnchoredPopover();

  const active = personas.find((p: any) => p.id === activePersonaId);

  const grouped = {
    builtin: personas.filter((p: any) => p.visibility === "builtin"),
    shared: personas.filter((p: any) => p.visibility === "shared"),
    private: personas.filter((p: any) => p.visibility === "private"),
  };

  const handleSave = useCallback(
    async (form: any) => {
      if (modal?.persona) {
        await onUpdate?.(modal.persona.id, form);
      } else {
        await onCreate?.(form);
      }
      setModal(null);
    },
    [modal, onCreate, onUpdate],
  );

  const handleDelete = useCallback(
    async (id: any) => {
      await onDelete?.(id);
      setModal(null);
    },
    [onDelete],
  );

  const renderItem = (p: any) => {
    const isActive = p.id === activePersonaId;
    const isDefault = p.id === defaultPersonaId;
    return (
      <button
        key={p.id}
        type="button"
        className={`persona-dropdown-item ${isActive ? "active" : ""}`}
        onClick={() => {
          onSelect?.(p.id);
          setOpen(false);
        }}
      >
        {p.accent_color && (
          <span className="persona-dot" style={{ background: p.accent_color }} />
        )}
        <span className="persona-item-name">{personaDropdownLabel(p)}</span>
        {isDefault && <span className="persona-default-badge" title="Default">★</span>}
        {p.visibility !== "builtin" && (
          <button
            type="button"
            className="persona-edit-btn ghost"
            title="Edit"
            onClick={(e) => {
              e.stopPropagation();
              setModal({ persona: p });
              setOpen(false);
            }}
          >
            ✎
          </button>
        )}
        {onSetDefault && !isDefault && (
          <button
            type="button"
            className="persona-star-btn ghost"
            title="Set as default"
            onClick={(e) => {
              e.stopPropagation();
              onSetDefault(p.id);
            }}
          >
            ☆
          </button>
        )}
      </button>
    );
  };

  const activeLabel = active ? personaDropdownLabel(active) : "Persona";
  const activeChip = active ? personaChipLabel(active) : "Persona";

  return (
    <div className="persona-selector" ref={rootRef}>
      <button
        type="button"
        className="persona-trigger selectable-oval"
        onClick={() => setOpen(!open)}
        title={active ? `Persona: ${activeLabel}` : "Select persona"}
      >
        {active?.accent_color && (
          <span className="persona-dot" style={{ background: active.accent_color }} />
        )}
        <span className="persona-trigger-label">{activeChip}</span>
        <span className="persona-trigger-chevron material-symbols-outlined" aria-hidden="true">expand_more</span>
      </button>

      {open && (
        <div className="persona-dropdown">
          {grouped.builtin.length > 0 && (
            <>
              <div className="persona-dropdown-section">Presets</div>
              {grouped.builtin.map(renderItem)}
            </>
          )}
          {grouped.shared.length > 0 && (
            <>
              <div className="persona-dropdown-divider" />
              <div className="persona-dropdown-section">Shared</div>
              {grouped.shared.map(renderItem)}
            </>
          )}
          {grouped.private.length > 0 && (
            <>
              <div className="persona-dropdown-divider" />
              <div className="persona-dropdown-section">Private</div>
              {grouped.private.map(renderItem)}
            </>
          )}
          <div className="persona-dropdown-divider" />
          <button
            type="button"
            className="persona-dropdown-item persona-create"
            onClick={() => {
              setModal({ persona: null });
              setOpen(false);
            }}
          >
            + Create new…
          </button>
        </div>
      )}

      {modal !== null && (
        <PersonaModal
          persona={modal.persona}
          onSave={handleSave}
          onDelete={handleDelete}
          onCancel={() => setModal(null)}
        />
      )}
    </div>
  );
}

export { SLIDER_LABELS };
