import { useCallback, useEffect, useRef, useState } from "react";
import {
  getSpeechRecognitionCtor,
  loadVoicePrefs,
  speechSupported,
  VOICE_PREFS_EVENT,
  VOICE_PREFS_KEY,
} from "../lib/voicePrefs.js";
import {
  joinTranscript,
  reduceRecognitionResults,
  shouldShowMicButton,
  shouldSpeakReply,
  speakText,
  stopSpeaking,
} from "../lib/voiceSpeech.js";

/**
 * Browser voice mode: mic dictation + optional TTS for assistant replies.
 */
export default function useVoiceMode({ getComposerText, setComposerText } = {}) {
  const [prefs, setPrefs] = useState(() => loadVoicePrefs());
  const [listening, setListening] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [ttsMuted, setTtsMuted] = useState(false);
  const [voiceStatus, setVoiceStatus] = useState("");
  const recognitionRef = useRef(null);
  const baseTranscriptRef = useRef("");
  const support = speechSupported();

  useEffect(() => {
    function syncFromStorage() {
      setPrefs(loadVoicePrefs());
    }
    function onPrefsEvent(event) {
      if (event?.detail) setPrefs(event.detail);
      else syncFromStorage();
    }
    function onStorage(event) {
      if (event.key === VOICE_PREFS_KEY) syncFromStorage();
    }
    window.addEventListener(VOICE_PREFS_EVENT, onPrefsEvent);
    window.addEventListener("storage", onStorage);
    return () => {
      window.removeEventListener(VOICE_PREFS_EVENT, onPrefsEvent);
      window.removeEventListener("storage", onStorage);
    };
  }, []);

  const stopListening = useCallback(() => {
    const recognition = recognitionRef.current;
    recognitionRef.current = null;
    if (recognition) {
      try {
        recognition.onresult = null;
        recognition.onerror = null;
        recognition.onend = null;
        recognition.stop();
      } catch {
        try {
          recognition.abort();
        } catch {
          // ignore
        }
      }
    }
    setListening(false);
  }, []);

  const muteTts = useCallback(() => {
    setTtsMuted(true);
    stopSpeaking();
    setSpeaking(false);
  }, []);

  const unmuteTts = useCallback(() => {
    setTtsMuted(false);
  }, []);

  const stopTts = useCallback(() => {
    stopSpeaking();
    setSpeaking(false);
  }, []);

  useEffect(() => {
    return () => {
      stopListening();
      stopSpeaking();
    };
  }, [stopListening]);

  useEffect(() => {
    if (!prefs.voice_speak_replies) {
      stopTts();
    }
  }, [prefs.voice_speak_replies, stopTts]);

  useEffect(() => {
    if (!prefs.voice_input_enabled && listening) {
      stopListening();
    }
  }, [prefs.voice_input_enabled, listening, stopListening]);

  const speakReply = useCallback(
    (text) => {
      if (
        !shouldSpeakReply({
          prefs,
          support,
          muted: ttsMuted,
          listening,
          text,
        })
      ) {
        return;
      }
      speakText(text, {
        muted: ttsMuted,
        onStart: () => setSpeaking(true),
        onEnd: () => setSpeaking(false),
        onError: () => setSpeaking(false),
      });
    },
    [prefs, support, ttsMuted, listening]
  );

  const startListening = useCallback(() => {
    if (!prefs.voice_input_enabled || !support.input) {
      setVoiceStatus("Voice input is off or unavailable in this browser.");
      return;
    }
    const Recognition = getSpeechRecognitionCtor();
    if (!Recognition) {
      setVoiceStatus("Speech recognition is not available in this browser.");
      return;
    }

    stopTts();
    stopListening();
    setVoiceStatus("");

    const current = typeof getComposerText === "function" ? getComposerText() || "" : "";
    baseTranscriptRef.current = current;

    let recognition;
    try {
      recognition = new Recognition();
    } catch {
      setVoiceStatus("Could not start speech recognition.");
      return;
    }

    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = typeof navigator !== "undefined" && navigator.language
      ? navigator.language
      : "en-US";

    recognition.onresult = (event) => {
      const { finalChunk, interimChunk } = reduceRecognitionResults(
        event.results,
        event.resultIndex
      );
      if (finalChunk) {
        baseTranscriptRef.current = joinTranscript(baseTranscriptRef.current, finalChunk);
      }
      const next = joinTranscript(baseTranscriptRef.current, interimChunk);
      if (typeof setComposerText === "function") {
        setComposerText(next);
      }
    };

    recognition.onerror = (event) => {
      const code = event?.error || "error";
      if (code === "aborted" || code === "no-speech") {
        setVoiceStatus("");
      } else if (code === "not-allowed") {
        setVoiceStatus("Microphone permission denied.");
      } else {
        setVoiceStatus(`Voice input error: ${code}`);
      }
      setListening(false);
      recognitionRef.current = null;
    };

    recognition.onend = () => {
      if (recognitionRef.current === recognition) {
        recognitionRef.current = null;
        setListening(false);
      }
    };

    recognitionRef.current = recognition;
    try {
      recognition.start();
      setListening(true);
    } catch {
      recognitionRef.current = null;
      setListening(false);
      setVoiceStatus("Could not start speech recognition.");
    }
  }, [
    prefs.voice_input_enabled,
    support.input,
    getComposerText,
    setComposerText,
    stopListening,
    stopTts,
  ]);

  const toggleListening = useCallback(() => {
    if (listening) stopListening();
    else startListening();
  }, [listening, startListening, stopListening]);

  const showMic = shouldShowMicButton({ prefs, support });

  return {
    prefs,
    support,
    listening,
    speaking,
    ttsMuted,
    voiceStatus,
    showMic,
    startListening,
    stopListening,
    toggleListening,
    speakReply,
    stopTts,
    muteTts,
    unmuteTts,
    setVoiceStatus,
  };
}
