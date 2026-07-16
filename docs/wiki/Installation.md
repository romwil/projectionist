# Installation

CuratorX runs as a **single container**. Persist `/config` for `settings.json`, `curatorx.db`, and `jobs_state.json`. The image runs as non-root user `curatorx` (UID/GID 1000); the entrypoint auto-fixes `/config` ownership on upgrade.

## Docker Hub (fastest)

Multi-arch images (**linux/amd64** + **linux/arm64**):

```bash
docker pull romwil/curatorx:latest

docker run -d --name curatorx --restart unless-stopped \
  -p 8788:8788 \
  -v /path/to/curatorx/config:/config \
  romwil/curatorx:latest
```

| Tag | Meaning |
|-----|---------|
| `romwil/curatorx:latest` | Newest stable (CA template default) |
| `romwil/curatorx:1.7` | 1.7 line |
| `romwil/curatorx:1.7.13` | Exact release |

Open **http://\<host\>:8788**.

## Docker Compose

From a clone of the repo:

```bash
cp .env.example .env
# Edit .env with Plex / TMDB / LLM seeds (optional but helpful)
docker compose up -d --build
```

Compose builds from the local `Dockerfile` by default. To run the published image instead, set the image to `romwil/curatorx:latest` in `docker-compose.yml`.

## Local (dev)

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[web]"
cd frontend && npm install && npm run build && cd ..
DATA_DIR=./config python -m curatorx.web
```

## After install

1. Complete the **Settings** wizard (`/config`) — Name → Connections → Libraries
2. Run **Sync library**
3. Chat from the main workspace

Next: [Configuration](Configuration.md) · [Unraid](Unraid.md) · [Library Sync](Library-Sync.md)
