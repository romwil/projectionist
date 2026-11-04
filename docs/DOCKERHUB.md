# Projectionist

**Projectionist is a private movie-and-TV companion for your Plex household: ask for something to watch, browse your library by mood and connection, and keep everyone's picks their own.**

Self-hosted. One container, one data folder, no cloud account, no phone-home.

## What you need

- A **Plex Media Server** you can reach from the container
- **Docker** or **Unraid** (amd64 or arm64)
- Optional: an AI key (OpenAI, Anthropic, OpenRouter) or a local **Ollama** for chat. Explore, Search, and Library work without one.
- Optional: Radarr, Sonarr, or Seerr. Only the owner adds titles, and only after confirming.

## Run it

```bash
docker run -d --name projectionist -p 8788:8788 \
  -e PROJECTIONIST_SESSION_SECRET="$(openssl rand -hex 32)" \
  -v /path/to/projectionist/config:/config romwil/projectionist:latest
```

Open `http://your-server:8788` and finish the setup wizard (Name → Connections → Libraries). Keep port 8788 on your home network, or put it behind an authenticated reverse proxy. Don't expose it to the internet directly.

On Unraid, install from **Community Applications** (search "Projectionist").

## What you get

- **Chat** with a curator that knows your library and says why each pick fits
- **Explore** rails by mood, era, people, and named connections between titles
- **Owner, member, and Youth accounts for one household**, each with their own chats, watchlist, and inbox
- **Live channels** and a lobby wall display, fed from your own library
- **Daily on-box backups** of your settings and database

## Tags

| Tag | Use |
|-----|-----|
| `latest` | Newest release. Most people want this. |
| `X.Y` (e.g. `1.38`) | Newest patch on a minor line |
| `X.Y.Z` (e.g. `1.38.0`) | One exact release. Pin this if you want to control upgrades. |

Images are multi-arch (`linux/amd64`, `linux/arm64`).

## Privacy

No phone-home. Activity (chat turn counts, plays started here) is counted on your server, kept 90 days, and never sent anywhere. Chat goes only to the AI provider you choose. Details: [Privacy](https://github.com/romwil/projectionist/blob/main/docs/PRIVACY.md).

## Links

- Source and full README: [github.com/romwil/projectionist](https://github.com/romwil/projectionist)
- Docker and Unraid guide: [docs/DOCKER.md](https://github.com/romwil/projectionist/blob/main/docs/DOCKER.md)
- Configuration: [docs/CONFIGURATION.md](https://github.com/romwil/projectionist/blob/main/docs/CONFIGURATION.md)
- License: AGPL-3.0-only
