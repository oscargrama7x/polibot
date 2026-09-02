# Checklist: Migrating to a New Month's Boards

Run this once at the start of each new month, when creating fresh Solicitudes /
Pipeline de proyectos / Tareas / Diseño — Entregas boards.

**Decision made (see project chat history for reasoning):** duplicate
**"Structure only"** — do NOT duplicate with data. Ongoing projects from the
previous month stay in the previous month's boards and finish out there,
regardless of their deadline. Only genuinely new requests go into the new
month's boards. This avoids creating disconnected duplicate copies of
still-active projects.

---

## Part 1 — Monday.com side (manual, in the Monday UI)

- [ ] Duplicate each of the 4 boards: Solicitudes, Pipeline de proyectos,
      Tareas, Diseño — Entregas
- [ ] Duplicate type: **"Structure only"** (not "Structure and data")
- [ ] Move the new boards into the new month's folder
- [ ] **Critical — verify every cross-board automation on the NEW boards
      points at the NEW sibling boards, not the old month's:**
  - [ ] Solicitudes: "When Estatus changes to Proyecto nuevo, create item
        in Pipeline de proyectos" → points at new Pipeline board?
  - [ ] Pipeline: any automation creating items in Tareas → points at new
        Tareas board?
  - [ ] Any other cross-board automation you've since added
  - (Monday's docs do not guarantee this remaps automatically — check
    each one manually, don't assume.)
- [ ] **Delete the OLD month's Pipeline webhook subscription** (see Part 2,
      step 5) BEFORE the new month's webhook is registered — only one
      month's Pipeline board should ever have an active webhook at a time.
      Leaving the old one active risks our code writing new-month column
      IDs onto old-month items.

## Part 2 — Code side (once the new boards exist)

- [ ] Get the new board IDs (from each board's URL)
- [ ] Re-run the column/group discovery scripts (in `scripts/`) against
      each new board to get fresh column IDs and group IDs — these are
      NEW even for identically-named columns, never reuse old IDs
  - Solicitudes: Tipo de proyecto, Estatus, Jefa asignada, Cliente/proyecto,
    Qué se necesita, Deadline, Quién lo pide, active group ID
  - Pipeline: Tipo de proyecto, Jefa responsable, Semáforo, link to Tareas
  - Tareas: Responsable, active group ID ("Proyectos activos")
  - Diseño — Entregas: active group ID
- [ ] Update all corresponding IDs in `config.py`
- [ ] Delete the old month's Monday webhook subscription (via a small
      script using the `delete_webhook` mutation, or ask me to write one)
- [ ] Register a new Monday webhook pointing at the new month's Pipeline
      board (`scripts/create_pipeline_webhook.py`, update the board ID)
- [ ] Commit and push `config.py` changes
- [ ] Confirm Render redeployed
- [ ] Run one full end-to-end test (WhatsApp → Solicitudes → Pipeline →
      Tareas → Diseño) before considering the switch complete
