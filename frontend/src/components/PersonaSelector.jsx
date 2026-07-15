import { useState, useEffect, useRef, useCallback } from "react";

const SLIDER_LABELS = [
  { key: "val_bro_prof", lo: "Casual", hi: "Professorial" },
  { key: "val_dipl_snark", lo: "Diplomatic", hi: "Snarky" },
  { key: "val_pass_auto", lo: "Passive", hi: "Autonomous" },
  { key: "val_depth", lo: "Quick picks", hi: "Deep dives" },
  { key: "val_obscurity", lo: "Mainstream", hi: "Niche" },
  { key: "val_verbosity", lo: "Concise", hi: "Detailed" },
  { key: "val_formality", lo: "Chatty", hi: "Structured" },
];

function SliderRow({ label, value, onChange }) {
  return (
    <label className="persona-slider-row">
      <span className="persona-slider-lo">{label.lo}</span>
      <input
        type="range"
        min="0"
        max="1"
        step="0.05"
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="persona-slider"
      />
      <span className="persona-slider-hi">{label.hi}</span>
    </label>
  );
}

function PersonaModal({ persona, onSave, onDelete, onCancel }) {
  const isNew = !persona;
  const [form, setForm] = useState({
    name: persona?.name || "",
    val_bro_prof: persona?.val_bro_prof ?? 0.5,
    val_dipl_snark: persona?.val_dipl_snark ?? 0.5,
    val_pass_auto: persona?.val_pass_auto ?? 0.5,
    val_depth: persona?.val_depth ?? 0.5,
    val_obscurity: persona?.val_obscurity ?? 0.5,
    val_verbosity: persona?.val_verbosity ?? 0.5,
    val_formality: persona?.val_formality ?? 0.5,
    system_prompt_override: persona?.system_prompt_override || "",
    accent_color: persona?.accent_color || "",
  });
  const [showAdvanced, setShowAdvanced] = useState(Boolean(form.system_prompt_override));
  const isBuiltin = persona?.visibility === "builtin";

  const set = (key, val) => setForm((prev) => ({ ...prev, [key]: val }));

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

        <button
          type="button"
          className="ghost persona-advanced-toggle"
          onClick={() => setShowAdvanced(!showAdvanced)}
        >
          {showAdvanced ? "Hide Advanced" : "Show Advanced"}
        </button>

        {showAdvanced && (
          <textarea
            className="persona-prompt-textarea"
            placeholder="Custom system prompt override (optional)"
            value={form.system_prompt_override}
            onChange={(e) => set("system_prompt_override", e.target.value)}
            rows={5}
          />
        )}

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
            onClick={() => onSave(form)}
          >
            {isNew ? "Create" : "Save"}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function PersonaSelector({
  personas = [],
  activePersonaId,
  onSelect,
  onCreate,
  onUpdate,
  onDelete,
  onSetDefault,
  defaultPersonaId,
}) {
  const [open, setOpen] = useState(false);
  const [modal, setModal] = useState(null);
  const ref = useRef(null);

  const active = personas.find((p) => p.id === activePersonaId);

  useEffect(() => {
    if (!open) return;
    const handler = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const grouped = {
    builtin: personas.filter((p) => p.visibility === "builtin"),
    shared: personas.filter((p) => p.visibility === "shared"),
    private: personas.filter((p) => p.visibility === "private"),
  };

  const handleSave = useCallback(
    async (form) => {
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
    async (id) => {
      await onDelete?.(id);
      setModal(null);
    },
    [onDelete],
  );

  const renderItem = (p) => {
    const isActive = p.id === activePersonaId;
    const isDefault = p.id === defaultPersonaId;
    return (
      <button
        key={p.id}
        type="button"
        className={`persona-dropdown-item ${isActive ? "active" : ""}`}
        onClick={() => {
          onSelect(p.id);
          setOpen(false);
        }}
      >
        {p.accent_color && (
          <span className="persona-dot" style={{ background: p.accent_color }} />
        )}
        <span className="persona-item-name">{p.name}</span>
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

  return (
    <div className="persona-selector" ref={ref}>
      <button
        type="button"
        className="persona-trigger ghost"
        onClick={() => setOpen(!open)}
        title={active ? `Persona: ${active.name}` : "Select persona"}
      >
        {active?.accent_color && (
          <span className="persona-dot" style={{ background: active.accent_color }} />
        )}
        <span className="persona-trigger-label">{active?.name || "Persona"}</span>
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
