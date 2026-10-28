# Post-1.36.0 hardening — archived

This sprint guide is **closed**. Do not treat it as an active board.

| Thread | Status |
|--------|--------|
| **A** perimeter | Shipped in 1.36.x (auth fail-closed, chat POST stream, features leak, setup status, …) |
| **B** storage / honesty | Shipped (`library_counts`, sync single-flight, WAL `PASSIVE` checkpoint, …) |
| **C** client polls | Shipped (`visibleBusyPoll.js`) |
| **D** cruft / decoupling | **Closed by doing.** Library + chat HTTP now live in `projectionist/web/library_routes.py` and `projectionist/web/chat_routes.py`. `app.py` calls `register_library_routes` / `register_chat_routes` with the house factory (`db_factory`, `settings_factory`, `safe_error_detail`). Lifespan stays in `app.py`. Route modules do not `import projectionist.web.app`. |

Leftover D notes that are **other P1 slices** (auth/setup still bind via `app_mod`; user-visible CuratorX strings; ConfigPage / `useChatSession`) are not copied here and are **not** postponed into the parking lot. Frozen bets only: [TECH-DEBT.md](TECH-DEBT.md).

Approximate sizes after the carve: `app.py` ~4.3k, `library_routes.py` ~2.0k, `chat_routes.py` ~0.4k. Living numbers: [ARCHITECTURE.md](ARCHITECTURE.md) (module-size table under Backend).
