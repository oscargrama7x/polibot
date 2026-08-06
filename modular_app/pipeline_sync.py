import json
import threading
import requests

from config import SOLICITUDES_BOARD_ID, MONDAY_API_URL, TEMPLATES, AJUSTE_RAPIDO_LABEL
from monday_client import (
    monday_headers,
    set_pipeline_tipo_y_jefa,
    crear_diseno_item,
    crear_tareas_item_con_subtareas,
    set_pipeline_link_to_tareas,
    delete_pipeline_item,
    post_pipeline_update,
)

# Tracks which specific Solicitud item ids have already been used to
# build a Tareas item. This is the real fix for duplicate detection --
# NOT matching by name+timing (which can never tell apart "Monday's
# automation misfired twice for the same request" from "two genuinely
# different requests that happen to share a name"). Same-named
# Solicitudes are treated as a queue: each Pipeline event claims the
# oldest not-yet-used one. A true duplicate finds nothing left to claim.
# NOTE: this is in-memory only, same as SESSIONS -- resets on restart.
SYNCED_SOLICITUD_IDS = set()

# Serializes Pipeline sync processing. Without this, two duplicate Pipeline
# webhook events arriving nearly simultaneously (two background threads)
# could both check the Solicitud queue before either has finished consuming
# one -- both could see the same unconsumed entry and both claim it. This
# lock forces one sync to fully finish before the next one starts.
PIPELINE_SYNC_LOCK = threading.Lock()


def get_solicitud_data(nombre_proyecto):
    """
    Looks up Solicitudes items with this exact name, and returns the
    OLDEST one that hasn't already been consumed by a previous sync
    (tracked in SYNCED_SOLICITUD_IDS). Returns a dict with a "status"
    key:
      - {"status": "not_found"} -- no Solicitud with this name exists at all
      - {"status": "already_synced"} -- one or more exist, but all were
        already used -- this is a genuine duplicate Pipeline event
      - {"status": "ok", "solicitud_id": ..., "tipo_proyecto": ...,
        "jefa_ids": ...} -- a fresh, unconsumed match was found
    """
    query = """
    query ($boardId: ID!) {
      boards(ids: [$boardId]) {
        items_page(limit: 100) {
          items {
            id
            name
            column_values(ids: ["color_mm5wgrz5", "multiple_person_mm5fdarq"]) {
              id
              text
              value
            }
          }
        }
      }
    }
    """
    variables = {"boardId": SOLICITUDES_BOARD_ID}
    response = requests.post(
        MONDAY_API_URL,
        json={"query": query, "variables": variables},
        headers=monday_headers(),
    )
    items = response.json()["data"]["boards"][0]["items_page"]["items"]

    matches = [item for item in items if item["name"] == nombre_proyecto]
    if not matches:
        print(f"[get_solicitud_data] No Solicitud named {nombre_proyecto!r} found.")
        return {"status": "not_found"}

    unconsumed = [m for m in matches if m["id"] not in SYNCED_SOLICITUD_IDS]
    if not unconsumed:
        print(
            f"[get_solicitud_data] All {len(matches)} Solicitud(es) named "
            f"{nombre_proyecto!r} are already synced -- genuine duplicate."
        )
        return {"status": "already_synced"}

    if len(matches) > 1:
        print(
            f"[get_solicitud_data] {len(matches)} Solicitudes named "
            f"{nombre_proyecto!r} found, {len(unconsumed)} not yet synced -- "
            f"using the oldest unconsumed one. Consider using more distinct "
            f"project names."
        )

    # Oldest unconsumed match first -- treats same-named Solicitudes as a
    # FIFO queue, so each Pipeline event claims a different one in order.
    item = min(unconsumed, key=lambda i: int(i["id"]))

    tipo_proyecto = None
    jefa_ids = []
    for col in item["column_values"]:
        if col["id"] == "color_mm5wgrz5":
            tipo_proyecto = col["text"]
        elif col["id"] == "multiple_person_mm5fdarq":
            value = json.loads(col["value"]) if col["value"] else {}
            jefa_ids = [p["id"] for p in value.get("personsAndTeams", [])]

    return {
        "status": "ok",
        "solicitud_id": item["id"],
        "tipo_proyecto": tipo_proyecto,
        "jefa_ids": jefa_ids,
    }


def procesar_nuevo_pipeline_item(pipeline_item_id, nombre_proyecto):
    """
    Full Phase 4 sync, triggered whenever a new item appears on Pipeline:
    1. Pull Tipo de proyecto + Jefa asignada from the matching Solicitud.
    2. Write those onto the Pipeline item (since Monday doesn't carry them over).
    3. Find the matching template and build the Tareas item + subtasks.
    4. Link Pipeline -> Tareas.
    """
    with PIPELINE_SYNC_LOCK:
        solicitud = get_solicitud_data(nombre_proyecto)

        if solicitud["status"] == "not_found":
            print(f"No matching Solicitud found for '{nombre_proyecto}' -- skipping sync.")
            post_pipeline_update(
                pipeline_item_id,
                "⚠️ El bot no pudo encontrar la Solicitud original con este mismo "
                "nombre, así que Tipo de proyecto y Jefa no se copiaron "
                "automáticamente. Revisar manualmente.",
            )
            return

        if solicitud["status"] == "already_synced":
            print(
                f"'{nombre_proyecto}' has no unconsumed Solicitud left -- "
                f"this Pipeline entry is a genuine duplicate, deleting it."
            )
            delete_pipeline_item(pipeline_item_id)
            return

        solicitud_id = solicitud["solicitud_id"]
        tipo_proyecto = solicitud["tipo_proyecto"]
        jefa_ids = solicitud["jefa_ids"]

        if not tipo_proyecto:
            print(f"Solicitud {solicitud_id} for '{nombre_proyecto}' has no Tipo de proyecto -- skipping sync.")
            post_pipeline_update(
                pipeline_item_id,
                "⚠️ La Solicitud original no tiene Tipo de proyecto asignado, "
                "así que no se pudo sincronizar automáticamente. Revisar "
                "manualmente.",
            )
            return

        set_pipeline_tipo_y_jefa(pipeline_item_id, tipo_proyecto, jefa_ids)

        # Genuinely new project (not a duplicate) -- reflect it in Diseño -
        # Entregas too, so the design team sees it regardless of whether a
        # subtask template exists for this tipo de proyecto.
        crear_diseno_item(nombre_proyecto)

        subtask_names = TEMPLATES.get(tipo_proyecto)
        if subtask_names is None and tipo_proyecto != AJUSTE_RAPIDO_LABEL:
            print(f"No template for tipo_proyecto='{tipo_proyecto}' -- skipping Tareas creation.")
            post_pipeline_update(
                pipeline_item_id,
                f"⚠️ No existe una plantilla en Tareas para el tipo de proyecto "
                f"'{tipo_proyecto}'. Crear el item y las tareas manualmente en "
                f"el board de Tareas.",
            )
            # Even without a template, this Solicitud has been legitimately
            # claimed -- mark it consumed so a later duplicate Pipeline
            # event for the same request doesn't try to process it again.
            SYNCED_SOLICITUD_IDS.add(solicitud_id)
            return

        # "Ajuste rápido" intentionally has no template -- it's a small tweak
        # that just needs to be visible, not a full subtask breakdown. Give
        # it a bare Tareas item with an empty subtask list.
        subtask_names = subtask_names or []

        tareas_item_id = crear_tareas_item_con_subtareas(nombre_proyecto, subtask_names, jefa_ids)
        set_pipeline_link_to_tareas(pipeline_item_id, tareas_item_id)
        SYNCED_SOLICITUD_IDS.add(solicitud_id)

        print(f"Synced '{nombre_proyecto}' (Solicitud {solicitud_id}) -> Tareas item {tareas_item_id}")
