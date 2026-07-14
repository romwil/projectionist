import assert from "node:assert/strict";
import test from "node:test";

import {
  extractSpeakableText,
  joinTranscript,
  reduceRecognitionResults,
  shouldShowMicButton,
  shouldSpeakReply,
  speakText,
  stopSpeaking,
  stripMarkdownForSpeech,
} from "./voiceSpeech.js";

test("stripMarkdownForSpeech removes common markdown noise", () => {
  assert.equal(
    stripMarkdownForSpeech("Try **Heat** and `Taxi Driver` — [link](https://x.test)"),
    "Try Heat and Taxi Driver — link"
  );
});

test("extractSpeakableText joins text blocks only", () => {
  assert.equal(
    extractSpeakableText({
      blocks: [
        { type: "text", content: "Hello **world**" },
        { type: "title_card", payload: { title: "Heat" } },
        { type: "text", content: "More." },
      ],
    }),
    "Hello world More."
  );
  assert.equal(extractSpeakableText({ blocks: [] }), "");
});

test("joinTranscript inserts a single space when needed", () => {
  assert.equal(joinTranscript("hello", "world"), "hello world");
  assert.equal(joinTranscript("hello ", " world"), "hello world");
  assert.equal(joinTranscript("hello,", "world"), "hello, world");
  assert.equal(joinTranscript("hello", ", world"), "hello, world");
  assert.equal(joinTranscript("", "hi"), "hi");
});

test("reduceRecognitionResults splits final vs interim", () => {
  const results = [
    { isFinal: true, 0: { transcript: "one " } },
    { isFinal: false, 0: { transcript: "two" } },
  ];
  results.length = 2;
  assert.deepEqual(reduceRecognitionResults(results, 0), {
    finalChunk: "one ",
    interimChunk: "two",
  });
});

test("shouldShowMicButton respects prefs and support", () => {
  assert.equal(shouldShowMicButton({ prefs: { voice_input_enabled: true }, support: { input: true } }), true);
  assert.equal(shouldShowMicButton({ prefs: { voice_input_enabled: false }, support: { input: true } }), false);
  assert.equal(shouldShowMicButton({ prefs: { voice_input_enabled: true }, support: { input: false } }), false);
});

test("shouldSpeakReply respects muted, listening, prefs, and empty text", () => {
  const ok = {
    prefs: { voice_speak_replies: true },
    support: { speak: true },
    text: "Hello",
  };
  assert.equal(shouldSpeakReply(ok), true);
  assert.equal(shouldSpeakReply({ ...ok, muted: true }), false);
  assert.equal(shouldSpeakReply({ ...ok, listening: true }), false);
  assert.equal(shouldSpeakReply({ ...ok, prefs: { voice_speak_replies: false } }), false);
  assert.equal(shouldSpeakReply({ ...ok, text: "   " }), false);
});

test("speakText cancels prior speech and speaks when not muted", () => {
  const spoken = [];
  const synthesis = {
    cancelCalls: 0,
    cancel() {
      this.cancelCalls += 1;
    },
    speak(utterance) {
      spoken.push(utterance.text);
    },
  };
  const utterance = speakText("  Hi there  ", {
    synthesis,
    utteranceFactory: (value) => ({ text: value, onstart: null, onend: null, onerror: null }),
  });
  assert.equal(synthesis.cancelCalls, 1);
  assert.equal(utterance.text, "Hi there");
  assert.deepEqual(spoken, ["Hi there"]);

  assert.equal(speakText("nope", { synthesis, muted: true }), null);
  assert.equal(speakText("nope", { synthesis: null }), null);
});

test("stopSpeaking cancels synthesis safely", () => {
  let cancelled = 0;
  stopSpeaking({
    cancel() {
      cancelled += 1;
    },
  });
  stopSpeaking(null);
  assert.equal(cancelled, 1);
});
