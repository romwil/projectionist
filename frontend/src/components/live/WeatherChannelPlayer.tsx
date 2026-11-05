import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { getLiveWeatherChannel } from "../../api/client";
import {
  activeWarning,
  captionDwellMs,
  CHYRON_SUMMARY_MS,
  chyronGroups,
  formatWeatherClock,
  initialPlannerState,
  nextWeatherSegment,
  PAYLOAD_POLL_MS,
  pickVariant,
  segmentLabel,
  weatherSky,
  type PlannerState,
} from "../../lib/weatherChannel";
import { WeatherMusicBed, type AudioLike } from "../../lib/weatherMusic";
import WeatherLocationPicker from "../weather/WeatherLocationPicker";
import TheaterPlayer from "../theater/TheaterPlayer";
import {
  AlertsBoard,
  AlmanacBoard,
  CurrentBoard,
  FiveDayBoard,
  HeadlinesBoard,
  HourlyBoard,
  OverviewBoard,
  RadarBoard,
  RegionalBoard,
  SatelliteBoard,
  SeasonalBoard,
  WebcamsBoard,
} from "./weather/WeatherBoards";

type WeatherPayload = Record<string, any>;

export type WeatherChannelPlayerProps = {
  className?: string;
  onClose?: (...args: any[]) => void;
};

const VOICE_GAP_MS = 1_200;

function errorMessage(err: unknown, fallback: string): string {
  if (err instanceof Error && err.message) return err.message;
  if (typeof err === "object" && err && "message" in err) {
    const message = (err as { message: unknown }).message;
    if (typeof message === "string" && message) return message;
  }
  return fallback;
}

function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(
    () => typeof window !== "undefined" && !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches,
  );
  useEffect(() => {
    const query = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    if (!query) return undefined;
    const onChange = () => setReduced(query.matches);
    query.addEventListener?.("change", onChange);
    return () => query.removeEventListener?.("change", onChange);
  }, []);
  return reduced;
}

function renderBoard(segment: string, payload: WeatherPayload, elapsedMs: number, reducedMotion: boolean) {
  const boards = payload?.boards || {};
  const label = segmentLabel(payload, segment);
  switch (segment) {
    case "current":
      return boards.current ? <CurrentBoard board={boards.current} label={label} /> : null;
    case "overview":
      return boards.overview ? <OverviewBoard board={boards.overview} label={label} /> : null;
    case "hourly":
      return <HourlyBoard hours={boards.hourly || []} label={label} />;
    case "five_day":
      return <FiveDayBoard days={boards.five_day || []} label={label} />;
    case "alerts":
      return <AlertsBoard items={boards.alerts?.items || []} label={label} />;
    case "regional":
      return <RegionalBoard cities={boards.regional || []} label={label} />;
    case "radar":
      return boards.radar ? (
        <RadarBoard radar={boards.radar} label={label} elapsedMs={elapsedMs} reducedMotion={reducedMotion} />
      ) : null;
    case "satellite":
      return boards.satellite ? <SatelliteBoard satellite={boards.satellite} label={label} /> : null;
    case "webcams":
      return <WebcamsBoard cams={boards.webcams || []} label={label} />;
    case "almanac":
      return boards.almanac ? <AlmanacBoard board={boards.almanac} label={label} /> : null;
    case "seasonal":
      return boards.seasonal ? <SeasonalBoard board={boards.seasonal} label={label} /> : null;
    case "headlines":
      return <HeadlinesBoard scopes={payload?.headlines?.scopes || []} label={label} />;
    default:
      return null;
  }
}

/**
 * Cable-style Weather Channel: a segment player over server-cached boards, a
 * weather-only chyron, a separate headline segment with a spoken recap between
 * weather pieces, a red bulletin bar for Warnings, server-rendered narration,
 * and a shuffled music bed that fades around each voiceover.
 */
export default function WeatherChannelPlayer({ className = "", onClose }: WeatherChannelPlayerProps) {
  const [payload, setPayload] = useState<WeatherPayload | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(true);
  const [editingPlace, setEditingPlace] = useState(false);
  const [segment, setSegment] = useState("");
  const [caption, setCaption] = useState("");
  const [segmentStart, setSegmentStart] = useState(() => Date.now());
  const [now, setNow] = useState(() => Date.now());
  const [clock, setClock] = useState(() => formatWeatherClock());
  const [summary, setSummary] = useState("");
  const [warningAnnouncement, setWarningAnnouncement] = useState("");
  const [soundBlocked, setSoundBlocked] = useState(false);
  const reducedMotion = usePrefersReducedMotion();

  const payloadRef = useRef<WeatherPayload | null>(null);
  const plannerRef = useRef<PlannerState>(initialPlannerState());
  const countersRef = useRef<Record<string, number>>({});
  const versionRef = useRef<number | null>(null);
  const timerRef = useRef<number | null>(null);
  const voiceRef = useRef<HTMLAudioElement | null>(null);
  const bedRef = useRef<WeatherMusicBed | null>(null);
  const deckARef = useRef<HTMLAudioElement | null>(null);
  const deckBRef = useRef<HTMLAudioElement | null>(null);
  const announcedRef = useRef<Set<string>>(new Set());
  const startedRef = useRef(false);

  const clearTimer = () => {
    if (timerRef.current != null) window.clearTimeout(timerRef.current);
    timerRef.current = null;
  };

  const advance = useCallback(() => {
    clearTimer();
    const data = payloadRef.current;
    if (!data) return;
    const next = nextWeatherSegment(plannerRef.current, data, new Date());
    plannerRef.current = next.state;
    if (!next.segment) return;
    const picked = pickVariant(data.scripts, next.segment, countersRef.current);
    countersRef.current = picked.counters;
    const text = String(picked.variant?.text || "");
    const audioUrl = picked.variant?.audio_url ? String(picked.variant.audio_url) : "";
    setSegment(next.segment);
    setCaption(text);
    setSegmentStart(Date.now());
    const voice = voiceRef.current;
    if (audioUrl && voice && data.narration?.enabled) {
      voice.src = audioUrl;
      voice.currentTime = 0;
      const started = voice.play?.();
      if (started && typeof started.catch === "function") {
        started.catch(() => {
          setSoundBlocked(true);
          timerRef.current = window.setTimeout(advance, captionDwellMs(next.segment, text));
        });
      }
      return;
    }
    timerRef.current = window.setTimeout(advance, captionDwellMs(next.segment, text));
  }, []);

  const applyPayload = useCallback(
    (data: WeatherPayload) => {
      payloadRef.current = data;
      setPayload(data);
      if (versionRef.current !== data?.scripts_version) {
        versionRef.current = data?.scripts_version ?? null;
        countersRef.current = {};
      }
      const warning = activeWarning(data);
      const warningId = warning ? String(warning.id || warning.event) : "";
      if (warningId && !announcedRef.current.has(warningId)) {
        announcedRef.current.add(warningId);
        setWarningAnnouncement(`Weather bulletin: ${warning?.event} for ${warning?.area_short || "the area"}.`);
      }
      if (!startedRef.current) {
        startedRef.current = true;
        setSummary(String(data?.chyron_summary || ""));
        advance();
      } else if (warningId && !plannerRef.current.warningsPlayed.includes(warningId)) {
        voiceRef.current?.pause();
        if (bedRef.current?.isDucked) bedRef.current.voiceEnd(performance.now());
        advance();
      }
    },
    [advance],
  );

  const loadForecast = useCallback(
    async (reset = false) => {
      if (reset) {
        setBusy(true);
        plannerRef.current = initialPlannerState();
        startedRef.current = false;
      }
      setError("");
      try {
        applyPayload((await getLiveWeatherChannel()) as WeatherPayload);
      } catch (err: unknown) {
        setError(errorMessage(err, "Weather channel unavailable."));
      } finally {
        setBusy(false);
      }
    },
    [applyPayload],
  );

  useEffect(() => {
    loadForecast(true);
    const poll = window.setInterval(() => loadForecast(false), PAYLOAD_POLL_MS);
    return () => {
      window.clearInterval(poll);
      clearTimer();
    };
  }, [loadForecast]);

  // Music bed: shuffle every file; fade around each voiceover.
  const trackKey = (payload?.music?.tracks || []).map((t: any) => t.id).join(",");
  useEffect(() => {
    const tracks = payloadRef.current?.music?.tracks || [];
    if (!tracks.length) return undefined;
    const decks = [deckARef.current, deckBRef.current];
    let made = 0;
    const bed = new WeatherMusicBed({
      tracks,
      createAudio: () => (decks[made++] || new Audio()) as unknown as AudioLike,
    });
    bedRef.current = bed;
    bed.start(performance.now());
    const tick = window.setInterval(() => bed.tick(performance.now()), 100);
    const blocked = window.setTimeout(() => {
      if (bed.activeDeck.paused && !bed.isDucked) setSoundBlocked(true);
    }, 1500);
    return () => {
      window.clearInterval(tick);
      window.clearTimeout(blocked);
      bed.stop();
      bedRef.current = null;
    };
  }, [trackKey]);

  useEffect(() => {
    const voice = voiceRef.current;
    if (!voice) return undefined;
    const onPlay = () => bedRef.current?.voiceStart(performance.now());
    const onDone = () => {
      bedRef.current?.voiceEnd(performance.now());
      clearTimer();
      timerRef.current = window.setTimeout(advance, VOICE_GAP_MS);
    };
    const onError = () => {
      if (bedRef.current?.isDucked) bedRef.current.voiceEnd(performance.now());
      clearTimer();
      timerRef.current = window.setTimeout(advance, captionDwellMs("", voice.dataset.caption || ""));
    };
    voice.addEventListener("play", onPlay);
    voice.addEventListener("ended", onDone);
    voice.addEventListener("error", onError);
    return () => {
      voice.removeEventListener("play", onPlay);
      voice.removeEventListener("ended", onDone);
      voice.removeEventListener("error", onError);
      voice.pause();
    };
  }, [advance]);

  useEffect(() => {
    const id = window.setInterval(() => setClock(formatWeatherClock()), 30_000);
    return () => window.clearInterval(id);
  }, []);

  useEffect(() => {
    const id = window.setInterval(() => setSummary(String(payloadRef.current?.chyron_summary || "")), CHYRON_SUMMARY_MS);
    return () => window.clearInterval(id);
  }, []);

  const animating = segment === "radar" && !reducedMotion;
  useEffect(() => {
    if (!animating) return undefined;
    const id = window.setInterval(() => setNow(Date.now()), 250);
    return () => window.clearInterval(id);
  }, [animating]);

  const warning = activeWarning(payload);
  const groups = useMemo(() => chyronGroups(payload), [payload]);
  const sky = weatherSky(payload);
  const board = payload && segment ? renderBoard(segment, payload, Math.max(0, now - segmentStart), reducedMotion) : null;
  const narrationOn = !!payload?.narration?.enabled;
  const egress: Array<{ host: string; purpose: string }> = Array.isArray(payload?.egress) ? payload.egress : [];

  const enableSound = () => {
    setSoundBlocked(false);
    bedRef.current?.resume();
    const voice = voiceRef.current;
    if (voice?.src && voice.paused && narrationOn) voice.play?.()?.catch?.(() => {});
  };

  return (
    <TheaterPlayer
      src=""
      className={`weather-channel ${className}`.trim()}
      testId="weather-channel"
      osdVisible={false}
      dataAttrs={{ sky, board: segment || "empty", warning: warning ? "true" : "false", motion: reducedMotion ? "reduced" : "full" }}
    >
      <div className="weather-channel-sky" aria-hidden="true" />
      <div className="weather-channel-controls">
        {onClose ? (
          <button type="button" className="ghost weather-channel-close" onClick={onClose} data-testid="weather-channel-close">
            Back to Live
          </button>
        ) : null}
        <button
          type="button"
          className="ghost weather-channel-place-toggle"
          data-testid="weather-location-toggle"
          onClick={() => setEditingPlace((open) => !open)}
        >
          {editingPlace ? "Hide place" : "Change place"}
        </button>
        {soundBlocked ? (
          <button type="button" className="ghost" data-testid="weather-sound-on" onClick={enableSound}>
            Turn on sound
          </button>
        ) : null}
      </div>
      {editingPlace ? (
        <WeatherLocationPicker
          variant="channel"
          savedPlace={payload?.location_source === "profile" ? payload?.place || "" : ""}
          source={payload?.location_source || "household"}
          householdPlace={payload?.household_place || ""}
          onSaved={() => {
            setEditingPlace(false);
            loadForecast(true);
          }}
        />
      ) : null}

      {busy && !payload ? <p className="weather-channel-status">Tuning the forecast…</p> : null}
      {error ? <p className="weather-channel-status weather-channel-status--error">{error}</p> : null}
      {payload?.error ? <p className="weather-channel-status">{payload.error}</p> : null}

      <div className="weather-stage" data-testid="weather-board-stage">
        <header className="weather-stage-top">
          <span className="weather-stage-segment">{segment ? segmentLabel(payload, segment) : "Local forecast"}</span>
          <span className="weather-stage-place">{payload?.place || "Local conditions"}</span>
          <span className="weather-stage-clock">{clock}</span>
        </header>
        {warning ? (
          <p className="weather-bulletin-bar" data-testid="weather-bulletin-bar">
            <span className="weather-bulletin-kicker">Weather bulletin</span>
            <span>
              {warning.event} · {warning.area_short}
              {warning.ends_label ? ` · until ${warning.ends_label}` : ""}
            </span>
          </p>
        ) : null}
        <div className="weather-stage-body" key={segment}>
          {board}
        </div>
        {caption ? (
          <p className="weather-caption" data-testid="weather-caption">
            {caption}
          </p>
        ) : null}
        {groups.length ? (
          <div className="weather-channel-ticker weather-chyron" data-testid="weather-chyron">
            <div className="weather-chyron-track" aria-hidden="true">
              {[0, 1].map((copy) => (
                <span key={copy} className="weather-chyron-run">
                  {groups.map((group) => (
                    <span key={`${copy}-${group.group}`} className="weather-chyron-group">
                      <span className="weather-chyron-label">{group.group}</span>
                      {group.items.map((item, i) => (
                        <span key={`${item}-${i}`} className="weather-chyron-item">
                          {item}
                        </span>
                      ))}
                    </span>
                  ))}
                </span>
              ))}
            </div>
            <p className="sr-only" aria-live="polite" data-testid="weather-chyron-summary">
              {summary}
            </p>
          </div>
        ) : null}
      </div>

      <p className="sr-only" aria-live="assertive" data-testid="weather-warning-announcement">
        {warningAnnouncement}
      </p>
      <p className="sr-only" aria-live="polite">
        {segment ? `Now showing: ${segmentLabel(payload, segment)}` : ""}
      </p>

      <footer className="weather-channel-egress" data-testid="weather-channel-egress">
        <p>
          This channel calls{" "}
          {egress.map((row, index) => (
            <span key={row.host} title={row.purpose}>
              {row.host}
              {index < egress.length - 1 ? ", " : ""}
            </span>
          ))}
          {egress.length ? "" : "nothing yet"}. They get the place’s coordinates or name, never who is watching.
        </p>
        <p>
          {payload?.music?.tracks?.length
            ? `Music: ${payload.music.tracks.length} track${payload.music.tracks.length === 1 ? "" : "s"} from the owner’s folder, shuffled.`
            : payload?.muzak_note || "No soundtrack — the forecast plays without music."}{" "}
          {narrationOn ? "Narration: local voice on this server." : "Narration is off, so the forecast is captioned."}
        </p>
      </footer>
      <audio ref={deckARef} data-testid="weather-channel-muzak" preload="auto" />
      <audio ref={deckBRef} data-testid="weather-channel-muzak-next" preload="auto" />
      <audio ref={voiceRef} data-testid="weather-channel-voice" data-caption={caption} preload="auto" />
    </TheaterPlayer>
  );
}
