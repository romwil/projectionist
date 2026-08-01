import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getFeatures, getLiveChannelsOnNow, getPersona, getPlexMachineId } from "../api/client";
import { ROUTES } from "../lib/backNav.js";
import { liveWatchHref } from "../lib/liveChannels.js";
import {
  formatChannelLabel,
  formatOnNowLine,
  normalizeOnNow,
  visibleOnNowChannels,
} from "../lib/onNow.js";
import { plexLiveTvUrl } from "../lib/titleLinks.js";
import {
  addToTonightQueue,
  clearTonightQueue,
  loadTonightQueue,
  removeFromTonightQueue,
} from "../lib/tonightQueue.js";
import {
  tonightHabitChrome,
  tonightOneLiner,
  tonightReadySpotlight,
} from "../lib/whatsOnTonight.js";

/**
 * Adult / Youth habit surface: persona one-liner + On now dig-in → Watch / Plex.
 * Youth uses rating-gated on-now API rows + safer wording.
 */
export default function WhatsOnTonightHabit({
  compact = false,
  isYouth = false,
  showTonightQueue = true,
  showReadySpotlight = true,
}) {
  const [model, setModel] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [featureOn, setFeatureOn] = useState(false);
  const [plexUrl, setPlexUrl] = useState(plexLiveTvUrl());
  const [persona, setPersona] = useState(null);
  const [digInId, setDigInId] = useState("");
  const [queue, setQueue] = useState(() => loadTonightQueue());
  const [spotlightDismissed, setSpotlightDismissed] = useState(() => {
    try {
      return sessionStorage.getItem("projectionist_tonight_ready_spotlight") === "1";
    } catch {
      return false;
    }
  });

  const chrome = tonightHabitChrome({ isYouth });

  const load = useCallback(async () => {
    try {
      const features = await getFeatures();
      const enabled = Boolean(features?.features?.live_channels_enabled);
      setFeatureOn(enabled);
      if (!enabled) {
        setModel(null);
        setError("");
        setLoading(false);
        return;
      }
      setLoading(true);
      const [snapshot, machineId, personaPayload] = await Promise.all([
        getLiveChannelsOnNow(),
        getPlexMachineId().catch(() => ""),
        getPersona().catch(() => null),
      ]);
      setModel(normalizeOnNow(snapshot));
      setPlexUrl(plexLiveTvUrl(machineId));
      setPersona(personaPayload);
      setError("");
    } catch (err) {
      setError(err.message || "Could not load what’s on tonight.");
      setModel(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (!featureOn) {
    return null;
  }

  const channels = visibleOnNowChannels(model?.channels, { compact });
  const totalChannels = Array.isArray(model?.channels) ? model.channels.length : 0;
  const showEmpty = !loading && featureOn && (!model || !model.ready);
  const digIn =
    channels.find((c) => c.id === digInId) || (channels.length === 1 ? channels[0] : null);
  const oneLiner = tonightOneLiner({
    curatorName: persona?.curator_name || "Curator",
    presetId: persona?.persona_preset_id,
    channels,
    isYouth,
    ready: Boolean(model?.ready),
  });
  const spotlight =
    showReadySpotlight && !spotlightDismissed && model?.ready && totalChannels > 0
      ? tonightReadySpotlight({
          isYouth,
          channelCount: totalChannels,
          curatorName: persona?.curator_name || "Curator",
        })
      : null;

  function dismissSpotlight() {
    setSpotlightDismissed(true);
    try {
      sessionStorage.setItem("projectionist_tonight_ready_spotlight", "1");
    } catch {
      // ignore
    }
  }

  function pinChannel(channel) {
    if (!channel?.nowTitle) return;
    setQueue(
      addToTonightQueue(
        {
          id: `${channel.id}:${channel.nowTitle}`,
          title: channel.nowTitle,
          channelId: channel.id,
        },
        queue,
      ),
    );
  }

  return (
    <section
      className={`whats-on-tonight${compact ? " whats-on-tonight--compact" : ""}`}
      data-testid="whats-on-tonight"
      data-youth={isYouth ? "true" : "false"}
    >
      <div className="whats-on-tonight-head">
        <div>
          <p className="eyebrow">{chrome.eyebrow}</p>
          <h3 className="dash-panel-title">{chrome.title}</h3>
          <p className="whats-on-tonight-line" data-testid="whats-on-tonight-line">
            {oneLiner}
          </p>
          <p className="on-now-panel-meta">{chrome.meta}</p>
        </div>
        <div className="on-now-cta-row">
          <Link
            className="btn on-now-watch-cta"
            data-testid="whats-on-tonight-watch-cta"
            to={liveWatchHref(digIn?.id || channels[0]?.id || "")}
          >
            Watch here
          </Link>
          {!isYouth ? (
            <a
              className="ghost on-now-plex-cta"
              data-testid="whats-on-tonight-plex-cta"
              href={plexUrl}
              target="_blank"
              rel="noreferrer"
            >
              Also in Plex
            </a>
          ) : (
            <span className="ghost on-now-plex-cta" data-testid="whats-on-tonight-plex-youth">
              Ask an adult for Plex
            </span>
          )}
          {totalChannels > 0 ? (
            <Link className="ghost" data-testid="whats-on-tonight-see-all" to={ROUTES.live}>
              See all
            </Link>
          ) : null}
        </div>
      </div>

      {spotlight ? (
        <div className="whats-on-tonight-spotlight" data-testid="whats-on-tonight-spotlight" role="status">
          <div>
            <strong>{spotlight.title}</strong>
            <p>{spotlight.body}</p>
          </div>
          <button type="button" className="ghost" onClick={dismissSpotlight}>
            Got it
          </button>
        </div>
      ) : null}

      {error ? <p className="dash-panel-error">{error}</p> : null}

      {loading ? (
        <p className="status status-secondary">Checking the guide…</p>
      ) : showEmpty ? (
        <p className="dash-empty" data-testid="whats-on-tonight-empty">
          {chrome.empty}
        </p>
      ) : (
        <>
          <p className="whats-on-tonight-dig-hint">{chrome.digInHint}</p>
          <ul className="on-now-list" data-testid="whats-on-tonight-list">
            {channels.map((channel) => {
              const open = digIn?.id === channel.id;
              return (
                <li
                  key={channel.id}
                  className={`on-now-row${open ? " is-open" : ""}`}
                  data-testid="whats-on-tonight-row"
                >
                  <button
                    type="button"
                    className="on-now-row-link whats-on-tonight-row-btn"
                    data-testid="whats-on-tonight-row-btn"
                    aria-expanded={open}
                    onClick={() => setDigInId(open ? "" : channel.id)}
                  >
                    <span className="on-now-channel">{formatChannelLabel(channel)}</span>
                    <span className="on-now-titles">{formatOnNowLine(channel)}</span>
                    {channel.airingWhy ? (
                      <span className="on-now-airing-why" data-testid="whats-on-tonight-airing-why">
                        {channel.airingWhy}
                      </span>
                    ) : null}
                    {channel.progressHint ? (
                      <span className="on-now-progress-meta">{channel.progressHint}</span>
                    ) : null}
                    {channel.percent != null ? (
                      <div
                        className="on-now-progress-bar"
                        role="progressbar"
                        aria-valuemin={0}
                        aria-valuemax={100}
                        aria-valuenow={Math.round(channel.percent)}
                      >
                        <span
                          className="on-now-progress-fill"
                          style={{ width: `${Math.max(0, Math.min(100, channel.percent))}%` }}
                        />
                      </div>
                    ) : null}
                  </button>
                  {open ? (
                    <div className="whats-on-tonight-digin" data-testid="whats-on-tonight-digin">
                      <Link
                        className="btn"
                        to={liveWatchHref(channel.id)}
                        data-testid="whats-on-tonight-digin-watch"
                      >
                        Watch here
                      </Link>
                      {!isYouth ? (
                        <a
                          className="ghost"
                          href={plexUrl}
                          target="_blank"
                          rel="noreferrer"
                          data-testid="whats-on-tonight-digin-plex"
                        >
                          Also in Plex
                        </a>
                      ) : null}
                      {showTonightQueue && channel.nowTitle ? (
                        <button
                          type="button"
                          className="ghost"
                          data-testid="whats-on-tonight-pin"
                          onClick={() => pinChannel(channel)}
                        >
                          Add to tonight’s queue
                        </button>
                      ) : null}
                    </div>
                  ) : null}
                </li>
              );
            })}
          </ul>
        </>
      )}

      {showTonightQueue && queue.length ? (
        <div className="tonight-queue" data-testid="tonight-queue">
          <div className="tonight-queue-head">
            <h4>Tonight’s queue</h4>
            <button
              type="button"
              className="ghost"
              data-testid="tonight-queue-clear"
              onClick={() => setQueue(clearTonightQueue())}
            >
              Clear
            </button>
          </div>
          <ul className="tonight-queue-list">
            {queue.map((item) => (
              <li key={item.id} data-testid="tonight-queue-item">
                <span>{item.title}</span>
                <div className="tonight-queue-actions">
                  {item.channelId ? (
                    <Link className="ghost" to={liveWatchHref(item.channelId)}>
                      Watch
                    </Link>
                  ) : null}
                  <button
                    type="button"
                    className="ghost"
                    onClick={() => setQueue(removeFromTonightQueue(item.id, queue))}
                  >
                    Remove
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}
