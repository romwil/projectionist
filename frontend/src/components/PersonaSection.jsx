import { useEffect, useState } from "react";
import { getPersonaPresets, putPersona } from "../api/client";
import { personaDropdownLabel } from "../lib/personaLabels";
import {
  CURATOR_CAPABILITIES,
  curatorCapabilitiesIntro,
} from "../lib/curatorCapabilities.js";
import InlineAlert from "./InlineAlert";

// Admin /api/persona (PersonaMetrics) only persists these three sliders.
// Extra template axes (depth/obscurity/…) live on /api/personas templates.
const PERSONA_FIELDS = [
  {
    key: "val_bro_prof",
    label: "Vocabulary",
    low: "Bro",
    high: "Professorial",
    help:
      "How film-literate the voice sounds. Low = casual fan talk; high = craft and auteur vocabulary.",
  },
  {
    key: "val_dipl_snark",
    label: "Directness",
    low: "Diplomatic",
    high: "Snarky",
    help:
      "How blunt recommendations and critiques are. Low = context-first; high = lead with verdicts.",
  },
  {
    key: "val_pass_auto",
    label: "Initiative",
    low: "Passive",
    high: "Autonomous",
    help:
      "How proactively the curator proposes next steps. Low = suggest and wait; high = concrete plans.",
  },
];

function sliderValue(persona, key) {
  const raw = persona?.[key];
  const num = typeof raw === "number" ? raw : Number(raw);
  return Number.isFinite(num) ? num : 0.5;
}

function hasLegacyCustomPrompt(persona) {
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
  const [showCapabilities, setShowCapabilities] = useState(false);
  const [confirmAction, setConfirmAction] = useState(null);

  const legacyCustom = hasLegacyCustomPrompt(persona);

  useEffect(() => {
    getPersonaPresets().then(setPresets).catch(console.error);
  }, []);

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
    if (legacyCustom) {
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
      } else if (type === "preset") {
        const { presetId } = confirmAction;
        const preset = presets.find((item) => item.id === presetId);
        if (!preset) return;
        const updated = await persistPersona({
          apply_preset: presetId,
          clear_persona_override: true,
        });
        setPersona(updated);
      }
    } finally {
      setConfirmAction(null);
    }
  }

  function handlePresetSelect(presetId) {
    if (legacyCustom) {
      setConfirmAction({ type: "preset", presetId });
      return;
    }
    persistPersona({ apply_preset: presetId });
  }

  async function resetLegacyCustomPrompt() {
    const updated = await persistPersona(
      { clear_persona_override: true },
      "Reset to preset sliders.",
    );
    setPersona(updated);
  }

  if (!persona) return null;

  return (
    <section className="config-section persona-section" data-testid="persona-section">
      <h2>Curator persona</h2>
      <p className="wizard-note">
        Shape how your curator talks and recommends — name, identity, presets, and behavior sliders.
        Capability wiring stays in Projectionist; you tune voice here, not internal prompts or tools.
      </p>

      <div className="persona-capabilities" data-testid="persona-capabilities">
        <div className="persona-capabilities-header">
          <h3>What your curator can do</h3>
          <button
            type="button"
            className="ghost persona-capabilities-toggle"
            data-testid="persona-capabilities-toggle"
            onClick={() => setShowCapabilities((open) => !open)}
          >
            {showCapabilities ? "Hide details" : "Show details"}
          </button>
        </div>
        <p className="wizard-note">{curatorCapabilitiesIntro()}</p>
        <ul className="persona-capabilities-list">
          {CURATOR_CAPABILITIES.slice(0, showCapabilities ? undefined : 4).map((item) => (
            <li key={item.id}>
              <strong>{item.label}</strong>
              {showCapabilities && item.detail ? (
                <span className="persona-capability-detail">{item.detail}</span>
              ) : null}
            </li>
          ))}
        </ul>
        {!showCapabilities && CURATOR_CAPABILITIES.length > 4 ? (
          <p className="wizard-note persona-capabilities-more">
            Plus research, lists, collections, and more — expand for the full list.
          </p>
        ) : null}
      </div>

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
              <strong>{personaDropdownLabel(preset)}</strong>
              {preset.tagline ? <em className="preset-tagline">{preset.tagline}</em> : null}
              <span>{preset.description}</span>
            </button>
          ))}
        </div>
      </div>

      <div className={`persona-sliders ${legacyCustom ? "persona-sliders-disabled" : ""}`}>
        <div className="persona-sliders-header">
          <h3>Behavior sliders</h3>
          {legacyCustom ? (
            <span className="persona-mode-badge" data-testid="persona-legacy-custom-badge">
              Legacy custom prompt — reset to use sliders
            </span>
          ) : null}
        </div>
        <p className="wizard-note">
          Each slider adjusts tone bands (low / mid / high). Changes apply on release — no prompt editing needed.
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
                <span className="slider-value">{sliderValue(persona, key).toFixed(2)}</span>
              </div>
              <p className="slider-help-text">{help}</p>
              <input
                type="range"
                min="0"
                max="1"
                step="0.01"
                value={sliderValue(persona, key)}
                disabled={legacyCustom || savingPersona}
                data-testid={`persona-slider-${key}`}
                onChange={(event) => handleSliderChange(key, Number(event.target.value))}
                onMouseUp={(event) => {
                  if (!legacyCustom) applySliderChange(key, Number(event.target.value));
                }}
                onTouchEnd={(event) => {
                  if (!legacyCustom) applySliderChange(key, Number(event.target.value));
                }}
              />
              <div className="slider-range-labels">
                <span>{low}</span>
                <span>{high}</span>
              </div>
            </label>
          ))}
        </div>
        {legacyCustom ? (
          <div className="persona-legacy-reset">
            <p className="wizard-note">
              This install still has a legacy custom system prompt from an earlier version. Reset to presets and
              sliders — editing raw prompts is no longer supported in Admin.
            </p>
            <button
              type="button"
              className="ghost"
              data-testid="persona-reset-legacy-custom"
              onClick={resetLegacyCustomPrompt}
              disabled={savingPersona}
            >
              Reset to slider-based persona
            </button>
          </div>
        ) : null}
      </div>

      {confirmAction ? (
        <div className="persona-confirm-banner" data-testid="persona-confirm-banner" role="alertdialog">
          <p>
            {confirmAction.type === "preset"
              ? "Applying a preset will replace your legacy custom prompt and update sliders. Your identity text is kept unless empty. Continue?"
              : "Adjusting sliders will replace your legacy custom prompt with the slider-generated default. Continue?"}
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
