# Installation

CuratorX runs as a **single container**. Persist `/config` for `settings.json`, `curatorx.db`, and `jobs_state.json`.

## Docker Hub (fastest)

Multi-arch images (**linux/amd64** + **linux/arm64**):

```bash
docker pull romwil/curatorx:1.0

docker run -d --name curatorx --restart unless-stopped \
  -p 8788:8788 \
  -v /path/to/curatorx/config:/config \
  romwil/curatorx:1.0
```

| Tag | Meaning |
|-----|---------|
| `romwil/curatorx:1.0.12` | Exact release |
| `romwil/curatorx:1.0` | 1.0 line |
| `romwil/curatorx:latest` | Newest stable |

Open **http://\<host\>:8788**.

## Docker Compose

From a clone of the repo:

```bash
cp .env.example .env
# Edit .env with Plex / TMDB / LLM seeds (optional but helpful)
docker compose up -d --build
```

Compose builds from the local `Dockerfile` by default. To run the published image instead, set the image to `romwil/curatorx:1.0` in `docker-compose.yml`.

## Local (dev)

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[web]"
cd frontend && npm install && npm run build && cd ..
DATA_DIR=./config python -m curatorx.web
```

## After install

1. Complete the **Settings** wizard (`/config`)
2. Run **Sync library**
3. Chat from the main workspace

Next: [Configuration](Configuration.md) · [Unraid](Unraid.md) · [Library Sync](Library-Sync.md)
