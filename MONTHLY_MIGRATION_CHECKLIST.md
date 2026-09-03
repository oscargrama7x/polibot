# Checklist: Migrating to a New Month's Boards

Run this once at the start of each new month, when creating fresh Solicitudes /
Pipeline de proyectos / Tareas / Diseño — Entregas boards.

**Decision made (see project chat history for reasoning):** duplicate
**"Structure only"** — do NOT duplicate with data. Ongoing projects from the
previous month stay in the previous month's boards and finish out there,
regardless of their deadline. Only genuinely new requests go into the new
month's boards. This avoids creating disconnected duplicate copies of
still-active projects.

**Lessons from the first real migration (Aug -> Sep):**
- Column IDs and group IDs turned out IDENTICAL between old and new boards
  after duplicating — Monday's "duplicate board" feature preserves them.
  Don't assume this will always hold; verify with the discovery script
  every time rather than skipping step 6 below.
- Renaming each new board (adding a month suffix, e.g. "Sep") BEFORE
  checking automations makes verification much easier — the collapsed
  automation summary shows the real board name once renamed.
- When re-pointing a cross-board automation, Monday may prompt for
  additional required fields (e.g. "Group") that weren't visible before.
  Always pick the specific NAMED group, never "Top group (Currently X)" --
  the named option stays anchored even if groups get reordered later.
- Manage webhooks via API scripts (`list_webhooks.py`, `delete_webhook.py`,
  `create_pipeline_webhook.py`), not Monday's webhook UI directly -- that
  UI has been slow/unresponsive in practice.
- Old, stale webhook subscriptions can accumulate silently (we found one
  from the very first ngrok-era setup, months old, still failing every
  time). Worth running `list_webhooks.py` periodically to check for dead
  entries, not just during a monthly migration.

---

## Part 1 — Monday.com side (manual, in the Monday UI)

- [ ] Duplicate each of the 4 boards: Solicitudes, Pipeline de proyectos,
      Tareas, Diseño — Entregas
- [ ] Duplicate type: **"Structure only"** (not "Structure and data")
- [ ] Move the new boards into the new month's folder
- [ ] Rename each new board with a clear month suffix (e.g. "Sep") --
      makes the next step much easier
- [ ] **Check EVERY board's automations panel for cross-board references**
      (not just Solicitudes -- check Pipeline, Tareas, and Diseño too,
      even if they had none last time):
  - [ ] Solicitudes: "When Estatus changes to Proyecto nuevo, create item
        in Pipeline de proyectos" → points at new Pipeline board?
  - [ ] Solicitudes: "When Estatus changes to [X], ... create item in
        Tareas" → points at new Tareas board?
  - [ ] Pipeline, Tareas, Diseño: any automations of their own?
  - [ ] Any other cross-board automation added since last migration
  - (Monday's docs do not guarantee this remaps automatically — check
    each one manually, don't assume.)
  - When re-pointing, watch for newly-required fields (e.g. Group) --
    fill in with the NAMED group, not "Top group"
- [ ] **Delete the OLD month's Pipeline webhook subscription** (see Part 2,
      step 5) BEFORE the new month's webhook is registered — only one
      month's Pipeline board should ever have an active webhook at a time.
      Leaving the old one active risks our code writing new-month column
      IDs onto old-month items.

## Part 2 — Code side (once the new boards exist)

- [ ] Get the new board IDs (from each board's URL)
- [ ] Re-run the discovery script (`scripts/get_september_boards_structure.py`
      -- rename/adapt for the new month) against all four new boards at
      once to get their column IDs and group IDs
- [ ] **Compare against the previous month's IDs** -- don't assume they
      match, verify
- [ ] Update the board ID constants in `config.py`
- [ ] IF any column/group ID actually changed (unlike Aug->Sep), also
      update the hardcoded references in `monday_client.py` and
      `pipeline_sync.py`
- [ ] Delete the old month's Monday webhook subscription
      (`scripts/delete_webhook.py`, with the old webhook's id -- find it
      via `scripts/list_webhooks.py` first)
- [ ] Register a new Monday webhook pointing at the new month's Pipeline
      board (`scripts/create_pipeline_webhook.py`, update the board ID)
- [ ] Commit and push `config.py` changes
- [ ] Confirm Render redeployed (check the Events tab)
- [ ] Run one full end-to-end test (WhatsApp → Solicitudes → Pipeline →
      Tareas → Diseño) before considering the switch complete