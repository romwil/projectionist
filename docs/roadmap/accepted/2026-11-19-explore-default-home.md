# Explore is the default home for everyone

Dropped 2026-11-18. **Decided by the maintainer** (answers red-team Q2 from the 2026-11-01 review, and the open question in `2026-11-18-experience-convergence.md`).

- Explore is the first screen for every member, Youth, and guest, on every client (web, phone, tablet, TV).
- Chat remains a primary peer (Explore · Live · Chat · Search). Its starters stay where Chat is opened.
- Create **EXP-013**: change the server default of `default_page` to `explore` for new accounts and for accounts still on `auto`; keep an explicit `chat` choice working for people who set it. Update `docs/DESIGN.md` principle 2 (“Chat-first”) to *Explore-first, chat-deep*, and `docs/HELP.md` / onboarding copy that says chat is home.
- Done when: a new member’s first sign-in lands on Explore at 390 and 1440; an existing member with `default_page = chat` still lands on Chat; Help describes Explore as home.

---
## Processing note (agent, 2026-11-19)
- Created: EXP-013
- Updated: DESIGN.md principle 2 (Explore-first, chat-deep); HELP.md start-here / member copy; EXPERIENCE.md; board Decisions
- Outbox: none
- Needs the person: nothing (decision already given)
