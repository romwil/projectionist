(() => {
  "use strict";

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

  function markByte() {
    lastByteAt = Date.now();
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
      fill.style.width = "0%";
      return;
    }
    track.hidden = false;
    fill.style.width = `${Math.max(0, Math.min(1, Number(ratio) || 0)) * 100}%`;
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
   */
  function syncProgressContrast(unitEl, img) {
    if (!unitEl || !img || !img.naturalWidth || !img.naturalHeight) {
      if (unitEl) applyProgressContrast(unitEl, PROGRESS_FALLBACK);
      return;
    }
    try {
      const srcW = img.naturalWidth;
      const srcH = img.naturalHeight;
      const bandFrac = 0.08;
      const bandH = Math.max(1, Math.floor(srcH * bandFrac));
      const sampleW = Math.min(64, srcW);
      const canvas = document.createElement("canvas");
      canvas.width = sampleW;
      canvas.height = Math.min(16, bandH);
      const ctx = canvas.getContext("2d", { willReadFrequently: true });
      if (!ctx) {
        applyProgressContrast(unitEl, PROGRESS_FALLBACK);
        return;
      }
      ctx.drawImage(
        img,
        0,
        srcH - bandH,
        srcW,
        bandH,
        0,
        0,
        canvas.width,
        canvas.height,
      );
      const { data } = ctx.getImageData(0, 0, canvas.width, canvas.height);
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
      applyProgressContrast(
        unitEl,
        luminance >= 0.52 ? PROGRESS_ON_LIGHT : PROGRESS_ON_DARK,
      );
    } catch (_) {
      applyProgressContrast(unitEl, PROGRESS_FALLBACK);
    }
  }

  function showPoster(unitEl, url) {
    if (!url) return;
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
      reveal();
    };
    next.addEventListener("load", onLoad);
    next.src = url;
    // Prefer waiting for decode so contrast sample sees real pixels; CSS
    // already disables the opacity transition when reduced-motion is set.
    if (next.complete) {
      next.removeEventListener("load", onLoad);
      reveal();
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
    deckIndex = deckIndex % deck.length;
    showPoster(unit, deck[deckIndex].poster_url);
    rotateTimer = setInterval(() => {
      if (!deck.length) return;
      deckIndex = (deckIndex + 1) % deck.length;
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

    if (Array.isArray(snapshot.available) && snapshot.available.length) {
      deck = snapshot.available.filter((item) => item && item.poster_url);
    }

    if (snapshot.mode === "now_playing" || snapshot.watching) {
      showNowPlaying(snapshot);
      return;
    }
    if (snapshot.mode === "now_available") {
      startRotator(snapshot.header_label || "NOW AVAILABLE");
      return;
    }
    showEmpty();
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
    source = new EventSource("/api/theater/events");
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

  connect();
  startWatchdog();
})();
