(() => {
  "use strict";

  /**
   * Lobby theater kiosk client — assume resource-starved Chromium on aging silicon.
   * Rules: static DOM img pool only, opacity/transform compositing, local idle deck
   * keeps cycling through SSE hiccups (no error screens, no Image() churn).
   */

  const SILENCE_MS = 45000;
  const MAX_PANELS = 4;

  const stage = document.getElementById("stage");
  const board = document.getElementById("board");
  const emptyWell = document.getElementById("empty-well");
  const disabledNote = document.getElementById("disabled-note");
  const units = Array.from(document.querySelectorAll(".unit"));

  /** @type {EventSource | null} */
  let source = null;
  let lastByteAt = Date.now();
  let rotateTimer = null;
  let progressTimer = null;
  let watchdogTimer = null;
  let rotateSeconds = 12;
  let deck = [];
  let deckIndex = 0;
  let multiMode = "rotator";
  let headerMode = "dynamic";
  let currentMode = "empty";
  /** @type {Array<object>} */
  let liveSessions = [];
  /** @type {string} */
  let idleFeed = "recently_added";

  /** URLs that failed to load this session; cleared when deck drops them. */
  const deadPosters = new Set();
  /** Cached contrast choice per poster URL — avoid re-sampling on Pi-class CPUs. */
  const contrastByUrl = new Map();
  /** Single reused canvas for luminance samples (never allocate per reveal). */
  const sampleCanvas = document.createElement("canvas");
  const sampleCtx = sampleCanvas.getContext("2d", { willReadFrequently: true });

  function markByte() {
    lastByteAt = Date.now();
  }

  function pruneDeadPosters(activeUrls) {
    const keep = new Set(
      (activeUrls || []).filter((u) => typeof u === "string" && u),
    );
    for (const url of Array.from(deadPosters)) {
      if (!keep.has(url)) deadPosters.delete(url);
    }
    for (const url of Array.from(contrastByUrl.keys())) {
      if (!keep.has(url)) contrastByUrl.delete(url);
    }
  }

  function markPosterDead(url) {
    if (url) deadPosters.add(url);
  }

  function isPosterDead(url) {
    return Boolean(url) && deadPosters.has(url);
  }

  function nextLiveDeckIndex(fromIndex) {
    if (!deck.length) return 0;
    let idx = fromIndex % deck.length;
    for (let i = 0; i < deck.length; i += 1) {
      const url = deck[idx] && deck[idx].poster_url;
      if (url && !isPosterDead(url)) return idx;
      idx = (idx + 1) % deck.length;
    }
    return fromIndex % deck.length;
  }

  function setHeader(unitEl, label) {
    const text = unitEl.querySelector(".header-text");
    if (text) text.textContent = label || "";
  }

  function setProgress(unitEl, ratio, visible) {
    const track = unitEl.querySelector(".progress-track");
    const fill = unitEl.querySelector(".progress-fill");
    if (!track || !fill) return;
    if (!visible) {
      track.hidden = true;
      fill.style.transform = "scaleX(0)";
      return;
    }
    track.hidden = false;
    const clamped = Math.max(0, Math.min(1, Number(ratio) || 0));
    fill.style.transform = `scaleX(${clamped})`;
  }

  /** Mid-contrast default when canvas sample fails (tainted / empty). */
  const PROGRESS_FALLBACK = {
    fill: "#cfc8b8",
    track: "rgba(255, 255, 255, 0.18)",
  };
  const PROGRESS_ON_DARK = {
    fill: "#e8e4dc",
    track: "rgba(255, 255, 255, 0.22)",
  };
  const PROGRESS_ON_LIGHT = {
    fill: "#1a1a1a",
    track: "rgba(0, 0, 0, 0.28)",
  };

  function applyProgressContrast(unitEl, colors) {
    unitEl.style.setProperty("--theater-progress-fill", colors.fill);
    unitEl.style.setProperty("--theater-progress-track", colors.track);
  }

  /**
   * Sample the lower ~8% of the visible poster and pick a bar that contrasts
   * with average luminance (light art → dark bar, dark art → light bar).
   * Reuses one canvas; caches result per URL.
   */
  function syncProgressContrast(unitEl, img) {
    if (!unitEl || !img || !img.naturalWidth || !img.naturalHeight) {
      if (unitEl) applyProgressContrast(unitEl, PROGRESS_FALLBACK);
      return;
    }
    const srcUrl = img.getAttribute("src") || "";
    if (srcUrl && contrastByUrl.has(srcUrl)) {
      applyProgressContrast(unitEl, contrastByUrl.get(srcUrl));
      return;
    }
    if (!sampleCtx) {
      applyProgressContrast(unitEl, PROGRESS_FALLBACK);
      return;
    }
    try {
      const srcW = img.naturalWidth;
      const srcH = img.naturalHeight;
      const bandFrac = 0.08;
      const bandH = Math.max(1, Math.floor(srcH * bandFrac));
      const sampleW = Math.min(64, srcW);
      sampleCanvas.width = sampleW;
      sampleCanvas.height = Math.min(16, bandH);
      sampleCtx.drawImage(
        img,
        0,
        srcH - bandH,
        srcW,
        bandH,
        0,
        0,
        sampleCanvas.width,
        sampleCanvas.height,
      );
      const { data } = sampleCtx.getImageData(
        0,
        0,
        sampleCanvas.width,
        sampleCanvas.height,
      );
      let sum = 0;
      let count = 0;
      for (let i = 0; i < data.length; i += 4) {
        const a = data[i + 3];
        if (a < 16) continue;
        // Rec. 709 relative luminance
        sum += (0.2126 * data[i] + 0.7152 * data[i + 1] + 0.0722 * data[i + 2]) / 255;
        count += 1;
      }
      if (!count) {
        applyProgressContrast(unitEl, PROGRESS_FALLBACK);
        return;
      }
      const luminance = sum / count;
      const colors = luminance >= 0.52 ? PROGRESS_ON_LIGHT : PROGRESS_ON_DARK;
      if (srcUrl) contrastByUrl.set(srcUrl, colors);
      applyProgressContrast(unitEl, colors);
    } catch (_) {
      applyProgressContrast(unitEl, PROGRESS_FALLBACK);
    }
  }

  function showPoster(unitEl, url) {
    if (!url || isPosterDead(url)) return;
    const a = unitEl.querySelector(".slot-a");
    const b = unitEl.querySelector(".slot-b");
    if (!a || !b) return;
    const active = a.classList.contains("visible") ? a : b.classList.contains("visible") ? b : null;
    const next = active === a ? b : a;
    if (active && active.getAttribute("src") === url) {
      if (active.complete) syncProgressContrast(unitEl, active);
      return;
    }

    const reveal = () => {
      next.classList.add("visible");
      if (active) active.classList.remove("visible");
      syncProgressContrast(unitEl, next);
    };

    if (next.getAttribute("src") === url && next.complete) {
      reveal();
      return;
    }
    const onLoad = () => {
      next.removeEventListener("load", onLoad);
      next.removeEventListener("error", onError);
      reveal();
    };
    const onError = () => {
      next.removeEventListener("load", onLoad);
      next.removeEventListener("error", onError);
      markPosterDead(url);
    };
    next.addEventListener("load", onLoad);
    next.addEventListener("error", onError);
    next.src = url;
    // Prefer waiting for decode so contrast sample sees real pixels; CSS
    // already disables the opacity transition when reduced-motion is set.
    if (next.complete) {
      next.removeEventListener("load", onLoad);
      next.removeEventListener("error", onError);
      if (next.naturalWidth > 0) {
        reveal();
      } else {
        markPosterDead(url);
      }
    }
  }

  function clearTimers() {
    if (rotateTimer) {
      clearInterval(rotateTimer);
      rotateTimer = null;
    }
    if (progressTimer) {
      clearInterval(progressTimer);
      progressTimer = null;
    }
  }

  function showEmpty() {
    clearTimers();
    board.hidden = true;
    emptyWell.hidden = false;
    currentMode = "empty";
  }

  function showBoard() {
    board.hidden = false;
    emptyWell.hidden = true;
  }

  function visibleUnits(count) {
    units.forEach((unit, index) => {
      unit.hidden = index >= count;
    });
  }

  function startRotator(label) {
    clearTimers();
    showBoard();
    board.classList.toggle("panelled", false);
    visibleUnits(1);
    const unit = units[0];
    setHeader(unit, label);
    setProgress(unit, 0, false);
    if (!deck.length) {
      showEmpty();
      return;
    }
    deckIndex = nextLiveDeckIndex(deckIndex);
    showPoster(unit, deck[deckIndex].poster_url);
    rotateTimer = setInterval(() => {
      if (!deck.length) return;
      deckIndex = nextLiveDeckIndex(deckIndex + 1);
      showPoster(unit, deck[deckIndex].poster_url);
    }, Math.max(8, rotateSeconds) * 1000);
    currentMode = "now_available";
  }

  function tickProgress() {
    const now = Date.now();
    liveSessions.forEach((session, index) => {
      if (index >= MAX_PANELS) return;
      const unit = units[index];
      if (!unit || unit.hidden) return;
      let ratio = Number(session.progress) || 0;
      if (session.state === "playing" && session.duration_ms > 0) {
        const base = session.baseProgress != null ? session.baseProgress : ratio;
        const baseAt = session.baseAt != null ? session.baseAt : now;
        ratio = Math.max(0, Math.min(1, base + (now - baseAt) / session.duration_ms));
      }
      setProgress(unit, ratio, true);
    });
  }

  function showNowPlaying(snapshot) {
    clearTimers();
    showBoard();
    const sessions = Array.isArray(snapshot.sessions) ? snapshot.sessions : [];
    liveSessions = sessions.slice(0, MAX_PANELS).map((s) => ({
      ...s,
      baseProgress: Number(s.progress) || 0,
      baseAt: Date.now(),
    }));
    const label = snapshot.header_label || "NOW PLAYING";
    const panelled = multiMode === "panelled" && liveSessions.length > 1;
    board.classList.toggle("panelled", panelled);
    if (!liveSessions.length) {
      showEmpty();
      return;
    }
    if (panelled) {
      visibleUnits(liveSessions.length);
      liveSessions.forEach((session, index) => {
        const unit = units[index];
        setHeader(unit, label);
        showPoster(unit, session.poster_url);
        setProgress(unit, session.progress, true);
      });
    } else {
      visibleUnits(1);
      let idx = 0;
      const paint = () => {
        const session = liveSessions[idx % liveSessions.length];
        setHeader(units[0], label);
        showPoster(units[0], session.poster_url);
        setProgress(units[0], session.progress, true);
      };
      paint();
      if (liveSessions.length > 1) {
        rotateTimer = setInterval(() => {
          idx = (idx + 1) % liveSessions.length;
          paint();
        }, Math.max(8, rotateSeconds) * 1000);
      }
    }
    progressTimer = setInterval(tickProgress, 1000);
    currentMode = "now_playing";
  }

  function applySnapshot(snapshot) {
    if (!snapshot || typeof snapshot !== "object") return;
    if (snapshot.enabled === false) {
      clearTimers();
      board.hidden = true;
      emptyWell.hidden = true;
      disabledNote.hidden = false;
      return;
    }
    disabledNote.hidden = true;
    rotateSeconds = Number(snapshot.rotate_seconds) || 12;
    multiMode = snapshot.multi_mode === "panelled" ? "panelled" : "rotator";
    headerMode = snapshot.header_mode === "static" ? "static" : "dynamic";
    stage.classList.toggle("orientation-portrait", snapshot.orientation === "portrait");
    stage.classList.toggle("orientation-landscape", snapshot.orientation !== "portrait");
    stage.dataset.mode = snapshot.mode || "empty";

    // Always honor an available array (including empty) so an empty
    // snapshot clears a stale local deck instead of keeping rotation alive.
    if (Array.isArray(snapshot.available)) {
      deck = snapshot.available.filter((item) => item && item.poster_url);
    }
    if (snapshot.feed && snapshot.feed !== idleFeed) {
      idleFeed = String(snapshot.feed);
    }

    const activeUrls = [];
    (snapshot.sessions || []).forEach((s) => {
      if (s && s.poster_url) activeUrls.push(s.poster_url);
    });
    deck.forEach((item) => {
      if (item && item.poster_url) activeUrls.push(item.poster_url);
    });
    pruneDeadPosters(activeUrls);

    if (snapshot.mode === "now_playing" || snapshot.watching) {
      showNowPlaying(snapshot);
      return;
    }
    if (snapshot.mode === "now_available") {
      if (!deck.length) {
        showEmpty();
        return;
      }
      // Keep cycling the local deck; only restart rotator if we left idle.
      if (currentMode === "now_available" && rotateTimer) {
        setHeader(units[0], snapshot.header_label || "NOW AVAILABLE");
        return;
      }
      startRotator(snapshot.header_label || "NOW AVAILABLE");
      return;
    }
    showEmpty();
  }

  function readFeedParam() {
    try {
      const params = new URLSearchParams(window.location.search);
      const raw = params.get("feed");
      if (!raw) return "recently_added";
      const token = String(raw).trim().toLowerCase().replace(/-/g, "_");
      if (token === "recently_added" || token === "recentlyadded") {
        return "recently_added";
      }
      if (
        token === "recently_released" ||
        token === "recent_releases" ||
        token === "recentlyreleased"
      ) {
        return "recently_released";
      }
      if (token === "trending" || token === "popular") {
        return "trending";
      }
      return "recently_added";
    } catch (_) {
      return "recently_added";
    }
  }

  function eventsUrl() {
    const base = "/api/theater/events";
    if (!idleFeed || idleFeed === "recently_added") return base;
    return `${base}?feed=${encodeURIComponent(idleFeed)}`;
  }

  function connect() {
    if (source) {
      try {
        source.close();
      } catch (_) {
        /* ignore */
      }
      source = null;
    }
    // Do not clearTimers / wipe the board — local idle deck keeps running
    // while SSE reconnects through a hiccup.
    source = new EventSource(eventsUrl());
    markByte();

    const onPayload = (event) => {
      markByte();
      try {
        applySnapshot(JSON.parse(event.data));
      } catch (_) {
        /* ignore */
      }
    };

    source.addEventListener("open", markByte);
    source.addEventListener("hydrate", onPayload);
    source.addEventListener("now_playing", onPayload);
    source.addEventListener("idle", onPayload);
    source.addEventListener("ping", markByte);
    source.addEventListener("progress", (event) => {
      markByte();
      try {
        const snapshot = JSON.parse(event.data);
        if (currentMode === "now_playing") {
          const sessions = Array.isArray(snapshot.sessions) ? snapshot.sessions : [];
          liveSessions = sessions.slice(0, MAX_PANELS).map((s) => ({
            ...s,
            baseProgress: Number(s.progress) || 0,
            baseAt: Date.now(),
          }));
          if (headerMode === "dynamic" && snapshot.header_label) {
            units.forEach((unit) => {
              if (!unit.hidden) setHeader(unit, snapshot.header_label);
            });
          }
        } else {
          applySnapshot(snapshot);
        }
      } catch (_) {
        /* ignore */
      }
    });
    // Quiet reconnect — never paint an error surface on scrap kiosks.
    source.onerror = markByte;
  }

  function startWatchdog() {
    if (watchdogTimer) clearInterval(watchdogTimer);
    watchdogTimer = setInterval(() => {
      if (Date.now() - lastByteAt > SILENCE_MS) {
        connect();
      }
    }, 5000);
  }

  idleFeed = readFeedParam();
  connect();
  startWatchdog();
})();
