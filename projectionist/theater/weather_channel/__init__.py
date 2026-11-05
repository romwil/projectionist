"""Cable-style Weather Channel: data collectors, script writer, TTS renderer, cache.

Layout:

- ``sources/`` — one module per outbound source (forecast, alerts, regional,
  maps, webcams, almanac, seasonal, headlines). Each takes an injectable fetcher
  so tests never touch the network.
- ``scripts`` — LLM voiceover variants, the number / alert / recap checkers, and
  the template variants used when no LLM is configured or a script is dropped.
- ``tts`` — local neural speech (Kokoro, Piper fallback) cached as opus.
- ``service`` — per-location cache, active-viewer tracking, and the background
  refresh loop. Nothing refreshes for a location nobody is watching.
- ``payload`` — assembles boards, segments, chyron, scripts, and music.
"""
