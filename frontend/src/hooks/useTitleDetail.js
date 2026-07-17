import { useEffect, useState } from "react";
import { api } from "../api/client";

export function buildTitleDetailFetchQuery(idType) {
  const params = new URLSearchParams();
  if (idType && idType !== "tmdb") params.set("id_type", idType);
  params.set("enrich", "0");
  return params;
}

/** Load title detail with fast local paint (enrich=0) then progressive TMDB enrichment. */
export function useTitleDetail({ mediaType, itemId, idType = "tmdb", enabled = true }) {
  const [detail, setDetail] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(Boolean(enabled && mediaType && itemId));

  useEffect(() => {
    if (!enabled || !mediaType || !itemId) {
      setDetail(null);
      setError("");
      setLoading(false);
      return undefined;
    }

    setDetail(null);
    setError("");
    setLoading(true);

    const controller = new AbortController();
    const enrichController = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), 12_000);

    const params = buildTitleDetailFetchQuery(idType);
    const query = params.toString() ? `?${params.toString()}` : "";

    api(`/title/${mediaType}/${itemId}${query}`, { signal: controller.signal })
      .then((data) => {
        setDetail(data);
        setLoading(false);
        const enrichParams = new URLSearchParams(params);
        enrichParams.set("enrich", "1");
        api(`/title/${mediaType}/${itemId}?${enrichParams.toString()}`, {
          signal: enrichController.signal,
        })
          .then((enriched) => {
            if (enriched) setDetail(enriched);
          })
          .catch(() => {});
      })
      .catch((err) => {
        setLoading(false);
        if (err?.name === "AbortError") {
          setError("Timed out loading this title. Try again.");
          return;
        }
        setError(err.message || "Failed to load title");
      })
      .finally(() => window.clearTimeout(timeoutId));

    return () => {
      window.clearTimeout(timeoutId);
      controller.abort();
      enrichController.abort();
    };
  }, [mediaType, itemId, idType, enabled]);

  return { detail, setDetail, error, loading };
}
