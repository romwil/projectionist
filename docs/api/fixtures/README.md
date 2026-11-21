# Client response fixtures

Example responses for the routes tagged `client`. Client repositories decode these files. They come from a test household: one film (`Heat`), a frozen pairing, a short stand-in playlist, and the checked-in Chicago weather forecast. They are not a recording of anyone's library.

Regenerate after a client route changes shape:

```bash
./scripts/export-fixtures.sh
./scripts/check-fixtures.sh
```

Each file is one route. `body` is JSON. `body_text` is a playlist. `body_base64` is a small image or segment. `example_path` is the concrete URL the example was fetched from. `index.json` lists them.

**Honest limits.** Live tune is the "not enabled" response, because this household has no lineup. Weather audio and map-frame examples are the not-rendered responses. The weather document itself is the success payload. Sign-in examples are the answers this household gives when that method is off or the token is not an invite, so a device credential and a Plex nonce never appear in these files. The Plex token never appears in these files.
