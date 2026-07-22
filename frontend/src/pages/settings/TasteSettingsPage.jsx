import { useEffect, useMemo, useState } from "react";
import { deleteTasteCluster, getTasteProfile, patchTasteProfile } from "../../api/client";
import SettingsPageHeader from "../../components/settings/SettingsPageHeader";
import SettingsPanel from "../../components/settings/SettingsPanel";

function formatWeight(weight) {
  const n = Number(weight);
  if (!Number.isFinite(n)) return "—";
  return `${Math.round(n * 100)}%`;
}

export default function TasteSettingsPage() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [clusters, setClusters] = useState([]);
  const [drafts, setDrafts] = useState({});
  const [status, setStatus] = useState(null);
  const [error, setError] = useState("");

  function reload() {
    setLoading(true);
    getTasteProfile()
      .then((data) => {
        const list = Array.isArray(data?.clusters) ? data.clusters : [];
        setClusters(list);
        const next = {};
        for (const cluster of list) {
          next[cluster.cluster_tag] = {
            weight: Number(cluster.weight),
            explicit_lock: Boolean(cluster.explicit_lock),
          };
        }
        setDrafts(next);
        setError("");
      })
      .catch((err) => {
        setError(err.message || "Could not load taste profile.");
      })
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    reload();
  }, []);

  const dirty = useMemo(() => {
    return clusters.some((cluster) => {
      const draft = drafts[cluster.cluster_tag];
      if (!draft) return false;
      return (
        Number(draft.weight).toFixed(3) !== Number(cluster.weight).toFixed(3) ||
        Boolean(draft.explicit_lock) !== Boolean(cluster.explicit_lock)
      );
    });
  }, [clusters, drafts]);

  async function handleSave(event) {
    event.preventDefault();
    const payload = clusters
      .map((cluster) => {
        const draft = drafts[cluster.cluster_tag];
        if (!draft) return null;
        if (
          Number(draft.weight).toFixed(3) === Number(cluster.weight).toFixed(3) &&
          Boolean(draft.explicit_lock) === Boolean(cluster.explicit_lock)
        ) {
          return null;
        }
        return {
          cluster_tag: cluster.cluster_tag,
          weight: Number(draft.weight),
          explicit_lock: Boolean(draft.explicit_lock),
        };
      })
      .filter(Boolean);
    if (!payload.length) {
      setStatus({ type: "success", message: "Nothing to save." });
      return;
    }
    setSaving(true);
    setStatus(null);
    try {
      await patchTasteProfile(payload);
      setStatus({
        type: "success",
        message: "Taste weights saved. Locked clusters stay put on refresh.",
      });
      reload();
    } catch (err) {
      setStatus({ type: "error", message: err.message || "Could not save taste profile." });
    } finally {
      setSaving(false);
    }
  }

  async function handleReset(tag) {
    setSaving(true);
    try {
      await deleteTasteCluster(tag);
      setStatus({ type: "success", message: `Removed your override for “${tag}”.` });
      reload();
    } catch (err) {
      setStatus({ type: "error", message: err.message || "Could not reset cluster." });
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <div className="settings-stack" data-testid="settings-taste">
        <SettingsPageHeader title="Taste">Loading…</SettingsPageHeader>
      </div>
    );
  }

  return (
    <div className="settings-stack" data-testid="settings-taste">
      <SettingsPageHeader title="Taste">
        Tune how strongly CuratorX leans on each cluster. Lock a weight so the weekly refresh cannot
        drift it.
      </SettingsPageHeader>

      {error ? <p className="status status-error">{error}</p> : null}

      <form onSubmit={handleSave}>
        <SettingsPanel title="Your clusters" testId="taste-clusters-panel">
          {!clusters.length ? (
            <p className="status status-secondary">
              No taste clusters yet. Rate a few titles or chat with the curator — then come back to
              tune the weights.
            </p>
          ) : (
            <ul className="taste-cluster-list" data-testid="taste-cluster-list">
              {clusters.map((cluster) => {
                const draft = drafts[cluster.cluster_tag] || {
                  weight: cluster.weight,
                  explicit_lock: cluster.explicit_lock,
                };
                return (
                  <li
                    key={cluster.cluster_tag}
                    className="taste-cluster-row"
                    data-testid={`taste-row-${cluster.cluster_tag}`}
                  >
                    <div className="taste-cluster-meta">
                      <strong>{cluster.cluster_tag}</strong>
                      <span className="status status-secondary">
                        {formatWeight(draft.weight)}
                        {cluster.source === "user" ? " · your override" : " · from library taste"}
                      </span>
                    </div>
                    <label className="taste-weight-slider">
                      <span className="visually-hidden">Weight for {cluster.cluster_tag}</span>
                      <input
                        type="range"
                        min="0"
                        max="1"
                        step="0.05"
                        value={draft.weight}
                        onChange={(event) =>
                          setDrafts((prev) => ({
                            ...prev,
                            [cluster.cluster_tag]: {
                              ...draft,
                              weight: Number(event.target.value),
                            },
                          }))
                        }
                        data-testid={`taste-weight-${cluster.cluster_tag}`}
                      />
                    </label>
                    <label className="taste-lock">
                      <input
                        type="checkbox"
                        checked={Boolean(draft.explicit_lock)}
                        onChange={(event) =>
                          setDrafts((prev) => ({
                            ...prev,
                            [cluster.cluster_tag]: {
                              ...draft,
                              explicit_lock: event.target.checked,
                            },
                          }))
                        }
                        data-testid={`taste-lock-${cluster.cluster_tag}`}
                      />
                      Lock
                    </label>
                    {cluster.source === "user" ? (
                      <button
                        type="button"
                        className="text-button"
                        onClick={() => handleReset(cluster.cluster_tag)}
                        disabled={saving}
                        data-testid={`taste-reset-${cluster.cluster_tag}`}
                      >
                        Reset
                      </button>
                    ) : null}
                  </li>
                );
              })}
            </ul>
          )}
        </SettingsPanel>

        {status ? (
          <p
            className={`status ${status.type === "error" ? "status-error" : "status-success"}`}
            data-testid="taste-status"
          >
            {status.message}
          </p>
        ) : null}

        <div className="settings-actions">
          <button
            type="submit"
            className="primary"
            disabled={saving || !dirty}
            data-testid="taste-save"
          >
            {saving ? "Saving…" : "Save taste"}
          </button>
        </div>
      </form>
    </div>
  );
}
