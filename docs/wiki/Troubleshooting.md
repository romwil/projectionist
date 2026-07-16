# Troubleshooting

## Container will not start

- Confirm port `8788` is free (or remap the host port)
- Check logs: `docker logs curatorx` / `docker compose logs -f curatorx`
- Ensure the `/config` volume is writable by the container user

## Setup wizard stuck

- Verify each service with **Test / Verify** on the Config page
- Plex section dropdowns unlock only after Plex verifies successfully
- Env-backed API keys work for Verify without re-typing secrets into the UI

## Sync fails or looks stuck

- After a **container restart**, an in-flight sync job is marked failed: *Interrupted by server restart — start sync again*. Start sync again; phase checkpoints resume unfinished work when still valid (≤72h)
- Confirm Plex server URL / server token and movie/TV section mapping
- Check TMDB key if enrichment fails mid-sync
- Tail logs with `CURATORX_LOG_LEVEL=DEBUG`

## Status dock shows no progress

- Open Config → Library sync card for the same job payload
- Hard-refresh the browser; jobs are polled from `GET /api/jobs`
- Ensure you are not looking at an interrupted (failed) job from a prior restart

## Chat / LLM errors

- Confirm `LLM_PROVIDER`, base URL, API key, and model
- For Ollama on Unraid, use a reachable host URL from inside the container (see [Unraid](Unraid.md))

## Radarr / Sonarr add fails

- Root folder and quality profile must be set
- Adds are confirmation-gated — confirm in chat cards or the status-dock prompt
- “Already exists” responses are handled gracefully; check the dock feedback

## Multi-user / Seerr

- Features are off by default — enable flags explicitly
- Sign-in methods: **Plex PIN**, optional **local password**, optional **OIDC** (configure in Admin)
- Sync via `/sync` is blocked for members when multi-user is on — use Config as owner
- If Plex PIN login never completes, confirm outbound HTTPS to plex.tv from the container
- If the container fails on upgrade from a root-owned `/config`, ensure you are on **v1.7.3+** (entrypoint auto-chowns); check `docker logs` for permission messages

More: [FAQ](FAQ.md) · [Library Sync](Library-Sync.md) · [../DOCKER.md](../DOCKER.md)
