import { useId, useState } from "react";
import { testMyAppriseSend } from "../../api/client";
import {
  APPRISE_SCHEME_OPTIONS,
  appriseTypeLabel,
  buildAppriseUrl,
  builderFieldsFor,
  defaultBuilderFields,
  maskAppriseUrl,
  parseAppriseUrlFields,
} from "../../lib/appriseDestinations.js";

/**
 * Self-serve Apprise destination grid + builder.
 * Parent owns the URL list; this component only edits the array of row objects.
 */
export default function AppriseDestinationsEditor({
  rows,
  onChange,
  disabled = false,
  ownerConfigured = false,
}) {
  const baseId = useId();
  const [mode, setMode] = useState(null); // null | 'pick' | 'form'
  const [editingId, setEditingId] = useState(null);
  const [schemeId, setSchemeId] = useState("discord");
  const [fields, setFields] = useState(() => defaultBuilderFields("discord"));
  const [formError, setFormError] = useState(null);
  const [rowStatus, setRowStatus] = useState({}); // id -> { type, message }
  const [testingId, setTestingId] = useState(null);

  function resetBuilder() {
    setMode(null);
    setEditingId(null);
    setSchemeId("discord");
    setFields(defaultBuilderFields("discord"));
    setFormError(null);
  }

  function openAdd() {
    setEditingId(null);
    setSchemeId("discord");
    setFields(defaultBuilderFields("discord"));
    setFormError(null);
    setMode("pick");
  }

  function openPasteOwn() {
    setEditingId(null);
    setSchemeId("custom");
    setFields(defaultBuilderFields("custom"));
    setFormError(null);
    setMode("form");
  }

  function chooseScheme(nextId) {
    setSchemeId(nextId);
    setFields(defaultBuilderFields(nextId));
    setFormError(null);
    setMode("form");
  }

  function openEdit(row) {
    const parsed = parseAppriseUrlFields(row.url);
    setEditingId(row.id);
    setSchemeId(parsed.schemeId);
    setFields({ ...defaultBuilderFields(parsed.schemeId), ...parsed.fields });
    setFormError(null);
    setMode("form");
  }

  function patchField(name, value) {
    setFields((prev) => ({ ...prev, [name]: value }));
  }

  function handleSubmit(event) {
    if (event?.preventDefault) event.preventDefault();
    setFormError(null);
    let url;
    try {
      url = buildAppriseUrl(schemeId, fields);
    } catch (error) {
      setFormError(error.message || "Could not build URL.");
      return;
    }

    if (editingId) {
      onChange(rows.map((row) => (row.id === editingId ? { ...row, url } : row)));
    } else {
      const exists = rows.some((row) => row.url === url);
      if (exists) {
        setFormError("That destination is already in your list.");
        return;
      }
      onChange([
        ...rows,
        { id: `dest-new-${Date.now().toString(36)}`, url },
      ]);
    }
    resetBuilder();
  }

  function handleDelete(row) {
    const label = appriseTypeLabel(row.url);
    if (!window.confirm(`Remove this ${label} destination?`)) return;
    onChange(rows.filter((entry) => entry.id !== row.id));
    setRowStatus((prev) => {
      const next = { ...prev };
      delete next[row.id];
      return next;
    });
    if (editingId === row.id) resetBuilder();
  }

  async function handleTest(row) {
    setTestingId(row.id);
    setRowStatus((prev) => ({ ...prev, [row.id]: null }));
    try {
      const result = await testMyAppriseSend({ url: row.url });
      setRowStatus((prev) => ({
        ...prev,
        [row.id]: {
          type: "success",
          message: `Test sent${result.notified ? ` (${result.notified})` : ""}.`,
        },
      }));
    } catch (error) {
      setRowStatus((prev) => ({
        ...prev,
        [row.id]: {
          type: "error",
          message: error.message || "Test failed.",
        },
      }));
    } finally {
      setTestingId(null);
    }
  }

  const schemeMeta = APPRISE_SCHEME_OPTIONS.find((entry) => entry.id === schemeId);
  const fieldDefs = builderFieldsFor(schemeId);
  const formTitle = editingId ? "Edit destination" : "Add destination";

  return (
    <div className="apprise-destinations" data-testid="notifications-apprise-destinations">
      <div className="apprise-destinations-header">
        <div>
          <p className="apprise-destinations-title">Your Apprise destinations (self-serve)</p>
          <p className="settings-field-hint">
            These are yours alone — no owner setup required. Household-wide destinations
            {ownerConfigured ? " are also on" : " (if any)"} come from Admin → Mail.
          </p>
        </div>
        <div className="apprise-destinations-actions">
          <button
            type="button"
            className="ghost"
            onClick={openAdd}
            disabled={disabled || mode === "pick" || mode === "form"}
            data-testid="notifications-apprise-add"
          >
            Add destination
          </button>
          <button
            type="button"
            className="ghost"
            onClick={openPasteOwn}
            disabled={disabled || mode === "form"}
            data-testid="notifications-apprise-paste"
          >
            Paste your own
          </button>
        </div>
      </div>

      {rows.length === 0 && mode === null ? (
        <p className="apprise-destinations-empty" data-testid="notifications-apprise-empty">
          No destinations yet. Add a popular target or paste an Apprise URL.
        </p>
      ) : null}

      {rows.length > 0 ? (
        <ul className="apprise-destinations-grid" data-testid="notifications-apprise-grid">
          {rows.map((row) => {
            const status = rowStatus[row.id];
            return (
              <li key={row.id} className="apprise-destination-row" data-testid="notifications-apprise-row">
                <div className="apprise-destination-main">
                  <span className="apprise-destination-badge" title={appriseTypeLabel(row.url)}>
                    {appriseTypeLabel(row.url)}
                  </span>
                  <code className="apprise-destination-url" title="Secrets are masked in this view">
                    {maskAppriseUrl(row.url)}
                  </code>
                </div>
                <div className="apprise-destination-row-actions">
                  <button
                    type="button"
                    className="ghost"
                    onClick={() => openEdit(row)}
                    disabled={disabled}
                    data-testid="notifications-apprise-edit"
                  >
                    Edit
                  </button>
                  <button
                    type="button"
                    className="ghost"
                    onClick={() => handleTest(row)}
                    disabled={disabled || testingId === row.id}
                    data-testid="notifications-apprise-test"
                  >
                    {testingId === row.id ? "Testing…" : "Test"}
                  </button>
                  <button
                    type="button"
                    className="ghost"
                    onClick={() => handleDelete(row)}
                    disabled={disabled}
                    data-testid="notifications-apprise-delete"
                  >
                    Delete
                  </button>
                </div>
                {status ? (
                  <p
                    className={`status ${status.type === "error" ? "status-error" : "status-success"}`}
                    data-testid="notifications-apprise-row-status"
                  >
                    {status.message}
                  </p>
                ) : null}
              </li>
            );
          })}
        </ul>
      ) : null}

      {mode === "pick" ? (
        <div className="apprise-builder" data-testid="notifications-apprise-picker">
          <div className="apprise-builder-header">
            <h4 className="apprise-builder-title">Choose a destination type</h4>
            <button type="button" className="ghost" onClick={resetBuilder}>
              Cancel
            </button>
          </div>
          <div className="apprise-scheme-grid" role="list">
            {APPRISE_SCHEME_OPTIONS.map((option) => (
              <button
                key={option.id}
                type="button"
                className="apprise-scheme-card"
                role="listitem"
                onClick={() => chooseScheme(option.id)}
                data-testid={`notifications-apprise-scheme-${option.id}`}
              >
                <span className="apprise-scheme-card-label">{option.label}</span>
                <span className="apprise-scheme-card-blurb">{option.blurb}</span>
              </button>
            ))}
          </div>
          <p className="settings-field-hint">
            Need something else?{" "}
            <a
              href="https://github.com/caronc/apprise#supported-notifications"
              target="_blank"
              rel="noreferrer"
            >
              See all Apprise notification types
            </a>
            .
          </p>
        </div>
      ) : null}

      {mode === "form" ? (
        <div
          className="apprise-builder"
          data-testid="notifications-apprise-builder"
          aria-labelledby={`${baseId}-builder-title`}
        >
          <div className="apprise-builder-header">
            <div>
              <h4 id={`${baseId}-builder-title`} className="apprise-builder-title">
                {formTitle}
              </h4>
              {schemeMeta ? (
                <p className="settings-field-hint">{schemeMeta.blurb}</p>
              ) : null}
            </div>
            <button type="button" className="ghost" onClick={resetBuilder}>
              Cancel
            </button>
          </div>

          {!editingId ? (
            <label className="settings-field">
              <span>Type</span>
              <select
                value={schemeId}
                onChange={(event) => chooseScheme(event.target.value)}
                data-testid="notifications-apprise-scheme-select"
              >
                {APPRISE_SCHEME_OPTIONS.map((option) => (
                  <option key={option.id} value={option.id}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
          ) : null}

          <div className="apprise-builder-fields">
            {fieldDefs.map((field) => {
              const inputId = `${baseId}-${field.name}`;
              if (field.type === "checkbox") {
                return (
                  <label key={field.name} className="apprise-builder-check" htmlFor={inputId}>
                    <input
                      id={inputId}
                      type="checkbox"
                      checked={fields[field.name] !== "0" && fields[field.name] !== "false"}
                      onChange={(event) => patchField(field.name, event.target.checked ? "1" : "0")}
                      data-testid={`notifications-apprise-field-${field.name}`}
                    />
                    <span>
                      {field.label}
                      {field.hint ? (
                        <span className="settings-field-hint">{field.hint}</span>
                      ) : null}
                    </span>
                  </label>
                );
              }
              return (
                <label key={field.name} className="settings-field" htmlFor={inputId}>
                  <span>
                    {field.label}
                    {field.required ? " *" : ""}
                  </span>
                  <input
                    id={inputId}
                    type={field.type || "text"}
                    value={fields[field.name] || ""}
                    onChange={(event) => patchField(field.name, event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter") {
                        event.preventDefault();
                        handleSubmit(event);
                      }
                    }}
                    placeholder={field.placeholder}
                    required={Boolean(field.required)}
                    autoComplete="off"
                    spellCheck={false}
                    data-testid={`notifications-apprise-field-${field.name}`}
                  />
                  {field.hint ? <span className="settings-field-hint">{field.hint}</span> : null}
                </label>
              );
            })}
          </div>

          {formError ? (
            <p className="status status-error" data-testid="notifications-apprise-builder-error">
              {formError}
            </p>
          ) : null}

          <div className="apprise-builder-footer">
            <button
              type="button"
              className="primary"
              onClick={handleSubmit}
              data-testid="notifications-apprise-builder-save"
            >
              {editingId ? "Update destination" : "Add to list"}
            </button>
            <p className="settings-field-hint">
              Remember to click <strong>Save preferences</strong> below to persist changes.{" "}
              <a
                href="https://github.com/caronc/apprise#supported-notifications"
                target="_blank"
                rel="noreferrer"
              >
                Apprise docs
              </a>
            </p>
          </div>
        </div>
      ) : null}

      {mode === null && rows.length > 0 ? (
        <p className="settings-field-hint">
          Secrets are masked above. See{" "}
          <a
            href="https://github.com/caronc/apprise#supported-notifications"
            target="_blank"
            rel="noreferrer"
          >
            Apprise notification types
          </a>{" "}
          for every supported scheme.
        </p>
      ) : null}
    </div>
  );
}
