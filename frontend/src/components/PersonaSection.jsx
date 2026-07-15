import { useEffect, useMemo, useState } from "react";
import { getPersonaPresets, putPersona } from "../api/client";
import InlineAlert from "./InlineAlert";

const PERSONA_FIELDS = [
  {
    key: "val_bro_prof",
    label: "Vocabulary",
    low: "Bro",
    high: "Professorial",
    help:
      "Controls word choice and film-literacy depth in the LLM prompt. Low = casual fan talk; high = movement, craft, and auteur vocabulary.",
  },
  {
    key: "val_dipl_snark",
    label: "Directness",
    low: "Diplomatic",
    high: "Snarky",
    help:
      "Controls how blunt recommendations and critiques are. Low = context-first, softened critiques; high = lead with verdicts and call out weak picks plainly.",
  },
  {
    key: "val_pass_auto",
    label: "Initiative",
    low: "Passive",
    high: "Autonomous",
    help:
      "Controls how proactively the curator proposes next steps. Low = suggest and wait; high = concrete queue/purge plans and pattern callouts.",
  },
  {
    key: "val_depth",
    label: "Depth",
    low: "Quick picks",
    high: "Deep dives",
    help:
      "Controls recommendation depth. Low = surface-level picks and quick lists; high = contextual deep dives with thematic reasoning.",
  },
  {
    key: "val_obscurity",
    label: "Obscurity",
    low: "Mainstream",
    high: "Niche",
    help:
      "Controls how far off the beaten path recommendations go. Low = popular crowd-pleasers; high = hidden gems and festival circuit picks.",
  },
  {
    key: "val_verbosity",
    label: "Verbosity",
    low: "Concise",
    high: "Detailed",
    help:
      "Controls response length. Low = short punchy answers; high = rich, detailed explanations with context and comparisons.",
  },
  {
    key: "val_formality",
    label: "Formality",
    low: "Chatty",
    high: "Structured",
    help:
      "Controls conversational register. Low = relaxed chat with slang; high = organized, well-structured prose.",
  },
];

function isCustomMode(persona) {
  return persona?.persona_mode === "custom" || Boolean(String(persona?.persona_prompt_override || "").trim());
}

export default function PersonaSection({
  persona,
  setPersona,
  savingPersona,
  setSavingPersona,
  actionAlert,
  setActionFeedback,
  showIdentityField = true,
  showCuratorName = false,
  onCuratorNameBlur,
}) {
  const [presets, setPresets] = useState([]);
  const [editingBehavioral, setEditingBehavioral] = useState(false);
  const [draftBehavioral, setDraftBehavioral] = useState("");
  const [confirmAction, setConfirmAction] = useState(null);

  const customMode = isCustomMode(persona);

  useEffect(() => {
    getPersonaPresets().then(setPresets).catch(console.error);
  }, []);

  useEffect(() => {
    if (!editingBehavioral && persona) {
      setDraftBehavioral(persona.behavioral_prompt || "");
    }
  }, [persona?.behavioral_prompt, persona?.persona_mode, editingBehavioral]);

  const assembledPreview = useMemo(() => persona?.assembled_prompt || "", [persona?.assembled_prompt]);

  async function persistPersona(payload, successMessage = "Persona updated.") {
    setSavingPersona(true);
    try {
      const updated = await putPersona(payload);
      setPersona(updated);
      if (payload.curator_name !== undefined && onCuratorNameBlur) {
        await onCuratorNameBlur(payload.curator_name);
      }
      setActionFeedback("persona", "success", successMessage);
      return updated;
    } catch (error) {
      setActionFeedback("persona", "error", error.message);
      throw error;
    } finally {
      setSavingPersona(false);
    }
  }

  async function saveIdentity(value) {
    await persistPersona({ persona_identity: value });
  }

  async function applySliderChange(key, value, clearOverride = false) {
    await persistPersona({
      [key]: value,
      clear_persona_override: clearOverride,
    });
  }

  function handleSliderChange(key, value) {
    if (customMode) {
      setConfirmAction({ type: "slider", key, value });
      return;
    }
    setPersona({ ...persona, [key]: value });
  }

  async function confirmPendingAction() {
    if (!confirmAction) return;
    const { type } = confirmAction;
    try {
      if (type === "slider") {
        const { key, value } = confirmAction;
        setPersona({ ...persona, [key]: value, persona_mode: "sliders", persona_prompt_override: null });
        await applySliderChange(key, value, true);
        setEditingBehavioral(false);
      } else if (type === "preset") {
        const { presetId } = confirmAction;
        const preset = presets.find((item) => item.id === presetId);
        if (!preset) return;
        const updated = await persistPersona({
          apply_preset: presetId,
          clear_persona_override: true,
        });
        setPersona(updated);
        setEditingBehavioral(false);
      }
    } finally {
      setConfirmAction(null);
    }
  }

  function handlePresetSelect(presetId) {
    if (customMode) {
      setConfirmAction({ type: "preset", presetId });
      return;
    }
    persistPersona({ apply_preset: presetId });
  }

  async function enterCustomMode() {
    setEditingBehavioral(true);
    setDraftBehavioral(persona.behavioral_prompt || "");
  }

  async function saveCustomBehavioral() {
    const text = draftBehavioral.trim();
    if (!text) {
      setActionFeedback("persona", "error", "Behavioral prompt cannot be empty.");
      return;
    }
    const updated = await persistPersona({ persona_prompt_override: text });
    setPersona(updated);
    setEditingBehavioral(false);
  }

  async function resetToSliders() {
    const updated = await persistPersona({ clear_persona_override: true });
    setPersona(updated);
    setEditingBehavioral(false);
  }

  if (!persona) return null;

  return (
    <section className="config-section persona-section" data-testid="persona-section">
      <h2>Curator persona</h2>
      <p className="wizard-note">
        Shape how your curator talks and recommends. Write a short identity, try a preset, then fine-tune with
        sliders. Your written identity stays unless you edit it — presets only fill it when empty.
      </p>

      {showCuratorName ? (
        <label className="identity-field">
          <span>Curator name</span>
          <input
            type="text"
            data-testid="curator-name-input"
            value={persona.curator_name}
            disabled={savingPersona}
            onChange={(event) => setPersona({ ...persona, curator_name: event.target.value })}
            onBlur={(event) => persistPersona({ curator_name: event.target.value })}
          />
        </label>
      ) : null}

      {showIdentityField ? (
        <label className="persona-identity-field">
          <span>Who are they?</span>
          <textarea
            data-testid="persona-identity"
            rows={4}
            placeholder="Voice, taste, and personality — written here is never overwritten by sliders."
            value={persona.persona_identity || ""}
            disabled={savingPersona}
            onChange={(event) => setPersona({ ...persona, persona_identity: event.target.value })}
            onBlur={(event) => saveIdentity(event.target.value)}
          />
        </label>
      ) : null}

      <div className="persona-presets">
        <h3>Presets</h3>
        <p className="wizard-note">Quick starting points for tone and taste. You can still tweak the sliders after.</p>
        <div className="preset-grid" data-testid="persona-preset-grid">
          {presets.map((preset) => (
            <button
              key={preset.id}
              type="button"
              className={`preset-card ${persona.persona_preset_id === preset.id ? "preset-card-active" : ""}`}
              data-testid={`persona-preset-${preset.id}`}
              disabled={savingPersona}
              onClick={() => handlePresetSelect(preset.id)}
            >
              <strong>{preset.name}</strong>
              {preset.tagline ? <em className="preset-tagline">{preset.tagline}</em> : null}
              <span>{preset.description}</span>
              {preset.behavioral_anchor ? (
                <span className="preset-anchor-preview">{preset.behavioral_anchor}</span>
              ) : null}
            </button>
          ))}
        </div>
      </div>

      <div className={`persona-sliders ${customMode ? "persona-sliders-disabled" : ""}`}>
        <div className="persona-sliders-header">
          <h3>Behavior sliders</h3>
          {customMode ? (
            <span className="persona-mode-badge" data-testid="persona-custom-badge">
              Custom persona — reset sliders to re-enable
            </span>
          ) : null}
        </div>
        <p className="wizard-note">
          Each slider maps to multi-sentence behavioral guidance in the generated prompt (low / mid / high bands).
        </p>
        <div className="slider-grid">
          {PERSONA_FIELDS.map(({ key, label, low, high, help }) => (
            <label key={key} className="slider-field">
              <div className="slider-labels">
                <span className="slider-label-with-help">
                  {label}
                  <button
                    type="button"
                    className="slider-help"
                    title={help}
                    aria-label={`${label} slider effect`}
                    data-testid={`persona-slider-help-${key}`}
                  >
                    ?
                  </button>
                </span>
                <span className="slider-value">{persona[key].toFixed(2)}</span>
              </div>
              <p className="slider-help-text">{help}</p>
              <input
                type="range"
                min="0"
                max="1"
                step="0.01"
                value={persona[key]}
                disabled={customMode || savingPersona}
                data-testid={`persona-slider-${key}`}
                onChange={(event) => handleSliderChange(key, Number(event.target.value))}
                onMouseUp={(event) => {
                  if (!customMode) applySliderChange(key, Number(event.target.value));
                }}
                onTouchEnd={(event) => {
                  if (!customMode) applySliderChange(key, Number(event.target.value));
                }}
              />
              <div className="slider-range-labels">
                <span>{low}</span>
                <span>{high}</span>
              </div>
            </label>
          ))}
        </div>
        {customMode ? (
          <button type="button" className="ghost" data-testid="persona-reset-sliders" onClick={resetToSliders}>
            Reset to slider-generated prompt
          </button>
        ) : null}
      </div>

      <div className="persona-behavioral">
        <div className="persona-behavioral-header">
          <h3>Behavioral prompt</h3>
          {!editingBehavioral && !customMode ? (
            <button type="button" className="ghost" data-testid="persona-edit-prompt" onClick={enterCustomMode}>
              Edit prompt
            </button>
          ) : null}
        </div>
        {editingBehavioral || customMode ? (
          <>
            <textarea
              data-testid="persona-behavioral-edit"
              rows={8}
              value={draftBehavioral}
              disabled={savingPersona}
              onChange={(event) => setDraftBehavioral(event.target.value)}
            />
            <div className="persona-behavioral-actions">
              <button type="button" onClick={saveCustomBehavioral} disabled={savingPersona}>
                Save custom prompt
              </button>
              {!customMode ? (
                <button type="button" className="ghost" onClick={() => setEditingBehavioral(false)}>
                  Cancel
                </button>
              ) : null}
            </div>
          </>
        ) : (
          <pre className="persona-prompt-preview" data-testid="persona-behavioral-preview">
            {persona.behavioral_prompt}
          </pre>
        )}
      </div>

      <div className="persona-live-preview">
        <h3>Live assembled prompt</h3>
        <p className="wizard-note">Identity + behavioral text as injected into the agent system prompt.</p>
        <pre className="persona-prompt-preview persona-assembled-preview" data-testid="persona-assembled-preview">
          {assembledPreview || "No persona prompt configured yet."}
        </pre>
      </div>

      {confirmAction ? (
        <div className="persona-confirm-banner" data-testid="persona-confirm-banner" role="alertdialog">
          <p>
            {confirmAction.type === "preset"
              ? "Applying a preset will replace your custom behavioral prompt and update sliders. Your identity text is kept unless empty. Continue?"
              : "Adjusting sliders will replace your custom behavioral prompt with the slider-generated default. Continue?"}
          </p>
          <div className="persona-confirm-actions">
            <button type="button" data-testid="persona-confirm-yes" onClick={confirmPendingAction}>
              Continue
            </button>
            <button type="button" className="ghost" data-testid="persona-confirm-no" onClick={() => setConfirmAction(null)}>
              Cancel
            </button>
          </div>
        </div>
      ) : null}

      <InlineAlert
        type={actionAlert?.area === "persona" ? actionAlert.type : null}
        message={actionAlert?.area === "persona" ? actionAlert.message : null}
      />
    </section>
  );
}
