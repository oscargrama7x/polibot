import difflib
import json
import os
import threading
import time
from datetime import datetime
import requests
from dotenv import load_dotenv
from flask import Flask, request, jsonify

load_dotenv()  # reads the .env file and makes its values available via os.environ

app = Flask(__name__)

# Choose any string you want here — you'll type this SAME string
# into the Meta dashboard's "Verify token" field in a later step.
VERIFY_TOKEN = "poligrama_verify_123"

# --- Fill these in with YOUR current values ---
ACCESS_TOKEN = os.environ["META_ACCESS_TOKEN"]
PHONE_NUMBER_ID = "1227828833752720"  # your test number's Phone Number ID

GRAPH_API_URL = f"https://graph.facebook.com/v21.0/{PHONE_NUMBER_ID}/messages"

# --- Conversation state ---
# One entry per phone number, e.g.:
# SESSIONS["5218126293873"] = {"step": "nombre_proyecto", "data": {"tipo_proyecto": "Encuesta de campo"}}
# NOTE: this dict lives only in memory — it resets every time the server restarts.
SESSIONS = {}

TIPOS_PROYECTO = {
    "1": "Encuesta de campo",
    "2": "Encuesta telefónica",
    "3": "Push call",
    "4": "Grupos de enfoque",
    "5": "SMS",
    "6": "Entregable administrativo",
    "7": "Genérico (reporte simple)",
    "8": "Ajuste rapido / Sin plantilla",
}

MENU_TIPO_PROYECTO = (
    "¿Qué tipo de proyecto es? Responde con el número:\n"
    "1. Encuesta de campo\n"
    "2. Encuesta telefónica\n"
    "3. Push call\n"
    "4. Grupos de enfoque\n"
    "5. SMS\n"
    "6. Entregable administrativo\n"
    "7. Genérico (reporte simple)\n"
    "8. Ajuste rápido / sin plantilla"
)

# Quick tweaks/small adjustments -- get a bare Tareas item with no subtasks,
# instead of triggering the "no template found" warning path.
# NOTE: this string must match the Monday status label EXACTLY (including
# accents/capitalization) -- the actual saved label is "Ajuste rapido /
# Sin plantilla" (missing accent, capital S), not the cleaner spelling
# shown in the menu text above.
AJUSTE_RAPIDO_LABEL = "Ajuste rapido / Sin plantilla"

MENU_ESTATUS = (
    "¿Cómo quieres marcar esta solicitud? Responde con el número:\n"
    "1. Proyecto nuevo (sigue el proceso automático)\n"
    "2. Por clasificar (alguien la asignará manualmente después)"
)

ESTATUS_OPTIONS = {
    "1": "Proyecto nuevo",
    "2": "Por clasificar",
}

MENU_QUIEN_LO_PIDE = (
    "¿Quién lo pide? Responde con el número:\n"
    "1. Gybram\n"
    "2. Pato\n"
    "3. Héctor"
)

QUIEN_LO_PIDE_OPTIONS = {
    "1": "Gybram",
    "2": "Pato",
    "3": "Héctor",
}


def parsear_fecha_ddmmaaaa(texto):
    """
    Parses a DD/MM/AAAA string into Monday's expected YYYY-MM-DD format.
    Returns None if the text isn't a valid date in that format (catches
    both wrong formatting and impossible dates like 31/02/2026).
    """
    try:
        fecha = datetime.strptime(texto.strip(), "%d/%m/%Y")
    except ValueError:
        return None
    return fecha.strftime("%Y-%m-%d")

# --- Monday.com config ---
MONDAY_API_TOKEN = os.environ["MONDAY_API_TOKEN"]
MONDAY_API_URL = "https://api.monday.com/v2"
SOLICITUDES_BOARD_ID = "18423114045"

# Jefas allowed to use the bot -> their Monday.com user info.
# Key is what they type in WhatsApp (lowercase), matched case-insensitively.
JEFAS = {
    "sergio": {"id": "77165762", "name": "Sergio Morelos"},
    "karina": {"id": "78712932", "name": "Karina Gutierrez Peña"},
    "gybram": {"id": "79095202", "name": "Gybram Vásquez"},
    "oscar": {"id": "112077190", "name": "Oscar Daniel Retes Torres"},
}

# --- Phase 4: Pipeline -> Tareas sync config ---
PIPELINE_BOARD_ID = "18423106654"
TAREAS_BOARD_ID = "18423108744"
TAREAS_ACTIVE_GROUP_ID = "group_mm5pb0qr"  # 🟢 Proyectos activos
DISENO_BOARD_ID = "18424123773"
DISENO_GROUP_ID = "topics"  # Diseño

# Pipeline board column ids
PIPELINE_TIPO_COLUMN = "color_mm5f84fz"
PIPELINE_JEFA_COLUMN = "multiple_person_mm5fs9qd"
PIPELINE_SEMAFORO_COLUMN = "color_mm5f545g"
PIPELINE_LINK_TAREAS_COLUMN = "board_relation_mm5fsvg8"

# Maps each Tipo de proyecto label -> list of subtask names from its template.
# Built directly from the Plantillas maestras group on the Tareas board.
TEMPLATES = {
    "Encuesta de campo": [
        "Recepción de solicitud", "Solicitud de muestra", "Presupuesto",
        "Cuestionario", "Ajustes de muestra", "Preparación operativa",
        "Programación del cuestionario", "Coordinación logística",
        "Materiales operativos", "Entrega de materiales al supervisor",
        "Pre-arranque de actividades de campo", "Ejecución de encuestas en campo",
        "Procesamiento de resultados", "Elaboración del reporte (diseño)",
        "Entrega del reporte final",
    ],
    "Push call": [
        "Recepción de indicaciones", "Definir mensaje / pregunta",
        "Preparar y limpiar listas (VIPs)", "Programar con proveedor de SMS",
        "Realizar pruebas a teléfonos de prueba (responsable del proyecto + 2 personas de la empresa)",
        "Ejecutar campañas (masivas + VIP)", "Reporte de resultados (diseño)",
        "Llenado de bitácora de envíos", "Reporte de inconsistencias",
    ],
    "Encuesta telefónica": [
        "Recepción de cuestionario", "Programación en Telencuestas",
        "Ejecución de la encuesta", "Descarga de resultados",
        "Resultados y análisis (tablas + Sheets)", "Validación de resultados",
        "Diseño del entregable", "Envío del entregable final",
    ],
    "Entregable administrativo": [
        "Definición de entregables mensuales", "Definición de cuestionarios",
        "Google Sheet de resultados (propuesta %)", "Creación de base de datos",
        "Revisión y corrección del entregable", "Carga del entregable",
    ],
    "Grupos de enfoque": [
        "Recepción del proyecto", "Cotización del proyecto",
        "Preparación del grupo (guía, moderador)",
        "Ejecución del grupo (presencial/virtual)",
        "Análisis de resultados y hallazgos", "Diseño del entregable",
        "Revisión y envío al cliente",
    ],
    "SMS": [
        "Recepción de indicaciones (brief)", "Organización del proyecto (listas, VIPs)",
        "Preparación del mensaje (160 car + link)",
        "Ejecución del envío (prueba → VIP/masivo)",
        "Reporte de resultados (diseño)", "Creación del plan de trabajo y aprobación",
    ],
    "Genérico (reporte simple)": [
        "Recepción de solicitud", "Google Sheet de resultados",
        "Generación / carga de base", "Validación de resultados",
        "Diseño del entregable", "Entrega final",
    ],
    # "Reporte electoral" has no matching template yet -- intentionally omitted.
}


def extract_created_item_id(response, context=""):
    """
    Safely pulls the new item's id out of a create_item response.
    If Monday rejected the mutation (e.g. an invalid status label), the
    response has no 'create_item' data -- instead of crashing with a
    cryptic TypeError, raise a clear error showing Monday's actual
    complaint.
    """
    data = response.json()
    create_item = (data.get("data") or {}).get("create_item")
    if create_item:
        return create_item["id"]

    label = f" ({context})" if context else ""
    raise RuntimeError(f"Monday create_item failed{label}: {data}")


def monday_headers():
    return {
        "Authorization": MONDAY_API_TOKEN,
        "Content-Type": "application/json",
    }


# Tracks which specific Solicitud item ids have already been used to
# build a Tareas item. This is the real fix for duplicate detection --
# NOT matching by name+timing (which can never tell apart "Monday's
# automation misfired twice for the same request" from "two genuinely
# different requests that happen to share a name"). Same-named
# Solicitudes are treated as a queue: each Pipeline event claims the
# oldest not-yet-used one. A true duplicate finds nothing left to claim.
# NOTE: this is in-memory only, same as SESSIONS -- resets on restart.
SYNCED_SOLICITUD_IDS = set()


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


def set_pipeline_tipo_y_jefa(pipeline_item_id, tipo_proyecto, jefa_ids):
    """Writes Tipo de proyecto, Jefa responsable, and Semaforo onto a
    Pipeline item. Semaforo especially matters here: it's a genuine
    status column (not a live mirror), and Monday's own automation only
    sets it once, at the exact moment it creates the item -- copying
    whatever Solicitudes' Estatus happened to be at that instant. If our
    retry loop hadn't stabilized yet, that snapshot can be stale forever.
    Setting it explicitly here guarantees it's correct."""
    tipo_value = json.dumps({"label": tipo_proyecto})
    jefa_value = json.dumps(
        {"personsAndTeams": [{"id": jid, "kind": "person"} for jid in jefa_ids]}
    )
    semaforo_value = json.dumps({"label": "Proyecto nuevo"})

    for column_id, value in [
        (PIPELINE_TIPO_COLUMN, tipo_value),
        (PIPELINE_JEFA_COLUMN, jefa_value),
        (PIPELINE_SEMAFORO_COLUMN, semaforo_value),
    ]:
        query = """
        mutation ($boardId: ID!, $itemId: ID!, $columnId: String!, $value: JSON!) {
          change_column_value (
            board_id: $boardId, item_id: $itemId,
            column_id: $columnId, value: $value
          ) { id }
        }
        """
        variables = {
            "boardId": PIPELINE_BOARD_ID,
            "itemId": pipeline_item_id,
            "columnId": column_id,
            "value": value,
        }
        response = requests.post(
            MONDAY_API_URL,
            json={"query": query, "variables": variables},
            headers=monday_headers(),
        )
        print(f"Set {column_id} on Pipeline item: {response.status_code} {response.text}")


def crear_tareas_item_con_subtareas(nombre_proyecto, subtask_names, jefa_ids):
    """Creates a new item in Tareas -> Proyectos activos, with Responsable
    set to jefa_ids, plus one subitem per name in subtask_names. Returns
    the new item's id."""
    tareas_jefa_column = "multiple_person_mm5f2z26"  # Responsable
    column_values = {
        tareas_jefa_column: {
            "personsAndTeams": [{"id": jid, "kind": "person"} for jid in jefa_ids]
        }
    }

    query = """
    mutation ($boardId: ID!, $groupId: String!, $itemName: String!, $columnValues: JSON!) {
      create_item (
        board_id: $boardId, group_id: $groupId, item_name: $itemName,
        column_values: $columnValues
      ) { id }
    }
    """
    variables = {
        "boardId": TAREAS_BOARD_ID,
        "groupId": TAREAS_ACTIVE_GROUP_ID,
        "itemName": nombre_proyecto,
        "columnValues": json.dumps(column_values),
    }
    response = requests.post(
        MONDAY_API_URL,
        json={"query": query, "variables": variables},
        headers=monday_headers(),
    )
    tareas_item_id = extract_created_item_id(response, context="Tareas item")

    subitem_query = """
    mutation ($parentItemId: ID!, $itemName: String!) {
      create_subitem (parent_item_id: $parentItemId, item_name: $itemName) {
        id
      }
    }
    """
    for subtask_name in subtask_names:
        subitem_variables = {
            "parentItemId": tareas_item_id,
            "itemName": subtask_name,
        }
        requests.post(
            MONDAY_API_URL,
            json={"query": subitem_query, "variables": subitem_variables},
            headers=monday_headers(),
        )
    print(f"Created Tareas item {tareas_item_id} with {len(subtask_names)} subtasks")

    return tareas_item_id


def set_pipeline_link_to_tareas(pipeline_item_id, tareas_item_id):
    """Connects Pipeline's 'link to Tareas' column to the new Tareas item."""
    value = json.dumps({"item_ids": [int(tareas_item_id)]})
    query = """
    mutation ($boardId: ID!, $itemId: ID!, $columnId: String!, $value: JSON!) {
      change_column_value (
        board_id: $boardId, item_id: $itemId,
        column_id: $columnId, value: $value
      ) { id }
    }
    """
    variables = {
        "boardId": PIPELINE_BOARD_ID,
        "itemId": pipeline_item_id,
        "columnId": PIPELINE_LINK_TAREAS_COLUMN,
        "value": value,
    }
    response = requests.post(
        MONDAY_API_URL,
        json={"query": query, "variables": variables},
        headers=monday_headers(),
    )
    print(f"Linked Pipeline -> Tareas: {response.status_code} {response.text}")


def delete_pipeline_item(pipeline_item_id):
    """Deletes a Pipeline item outright. Used only for confirmed duplicate
    entries (a Tareas item with the same name already exists), so this is
    safe -- but it's a real, non-reversible deletion, no undo."""
    query = """
    mutation ($itemId: ID!) {
      delete_item (item_id: $itemId) { id }
    }
    """
    variables = {"itemId": pipeline_item_id}
    response = requests.post(
        MONDAY_API_URL,
        json={"query": query, "variables": variables},
        headers=monday_headers(),
    )
    print(f"Deleted duplicate Pipeline item {pipeline_item_id}: {response.status_code}")


def post_pipeline_update(pipeline_item_id, message):
    """Posts a comment (Monday 'update') directly on a Pipeline item, so
    the failure is visible to whoever looks at the board -- not just in
    our terminal, which nobody else can see."""
    query = """
    mutation ($itemId: ID!, $body: String!) {
      create_update (item_id: $itemId, body: $body) { id }
    }
    """
    variables = {"itemId": pipeline_item_id, "body": message}
    response = requests.post(
        MONDAY_API_URL,
        json={"query": query, "variables": variables},
        headers=monday_headers(),
    )
    print(f"Posted update to Pipeline item {pipeline_item_id}: {response.status_code}")


def crear_diseno_item(nombre_proyecto):
    """Creates a new item in Diseño - Entregas -> Diseño group, with just
    the project name (that board only needs the name to reflect a new
    project -- Prioridad/Estado/Diseñadora get filled in manually by the
    design team later)."""
    query = """
    mutation ($boardId: ID!, $groupId: String!, $itemName: String!) {
      create_item (
        board_id: $boardId, group_id: $groupId, item_name: $itemName
      ) { id }
    }
    """
    variables = {
        "boardId": DISENO_BOARD_ID,
        "groupId": DISENO_GROUP_ID,
        "itemName": nombre_proyecto,
    }
    response = requests.post(
        MONDAY_API_URL,
        json={"query": query, "variables": variables},
        headers=monday_headers(),
    )
    diseno_item_id = extract_created_item_id(response, context="Diseño item")
    print(f"Created Diseño - Entregas item {diseno_item_id}: {nombre_proyecto!r}")
    return diseno_item_id


# Serializes Pipeline sync processing. Without this, two duplicate Pipeline
# webhook events arriving nearly simultaneously (two background threads)
# could both check the Solicitud queue before either has finished consuming
# one -- both could see the same unconsumed entry and both claim it. This
# lock forces one sync to fully finish before the next one starts.
PIPELINE_SYNC_LOCK = threading.Lock()


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


def crear_solicitud_en_monday(
    nombre_proyecto,
    tipo_proyecto,
    jefa,
    cliente_proyecto,
    que_se_necesita,
    deadline_iso,
    quien_lo_pide,
    sender,
    resumen_inicial,
    marcar_proyecto_nuevo=True,
):
    """
    Creates a new item on the Solicitudes board via Monday's GraphQL API.
    `jefa` is a dict like {"id": "77165762", "name": "Sergio Morelos"}.
    `deadline_iso` must already be in YYYY-MM-DD format (use
    parsear_fecha_ddmmaaaa on the raw user input before calling this).

    If marcar_proyecto_nuevo is False, the jefa chose "Por clasificar"
    instead of "Proyecto nuevo" -- we skip forcing Estatus entirely and
    just let Monday's own "on create, set to Por clasificar" automation
    stand as-is. A human will manually flip it to "Proyecto nuevo" later
    whenever they're ready, which triggers the exact same downstream
    Pipeline sync automatically (it doesn't care who/what triggered it).
    """
    headers = {
        "Authorization": MONDAY_API_TOKEN,
        "Content-Type": "application/json",
    }

    column_values = {
        "color_mm5wgrz5": {"label": tipo_proyecto},  # Tipo de proyecto
        "multiple_person_mm5fdarq": {
            "personsAndTeams": [{"id": jefa["id"], "kind": "person"}]
        },  # Jefa asignada
        "short_texto171dwf9": cliente_proyecto,  # Cliente / proyecto (plain text)
        "long_textqg5prhm3": {"text": que_se_necesita},  # Qué se necesita exactamente
        "datefgo81jlq": {"date": deadline_iso},  # Deadline
        "short_textzwzx6ahz": quien_lo_pide,  # Quién lo pide (plain text)
    }

    query = """
    mutation ($boardId: ID!, $itemName: String!, $columnValues: JSON!) {
      create_item (
        board_id: $boardId,
        item_name: $itemName,
        column_values: $columnValues
      ) {
        id
        name
      }
    }
    """
    variables = {
        "boardId": SOLICITUDES_BOARD_ID,
        "itemName": nombre_proyecto,
        "columnValues": json.dumps(column_values),
    }

    response = requests.post(
        MONDAY_API_URL,
        json={"query": query, "variables": variables},
        headers=headers,
    )
    item_id = extract_created_item_id(response, context="Solicitud item")
    print(f"Created Solicitud item {item_id}: {nombre_proyecto!r}")

    # Send the "confirming, this may take a few minutes" message right
    # away -- the wait loop below can take up to ~5 minutes worst case,
    # and the jefa shouldn't be left with zero feedback that whole time.
    send_whatsapp_message(sender, resumen_inicial)

    if not marcar_proyecto_nuevo:
        # "Por clasificar" chosen -- nothing more to do here. Item stays
        # at Monday's own default status until a human classifies it.
        return True

    # Now set Estatus as a SEPARATE mutation, after creation. Some Monday
    # automations ("when status changes to X") only fire on a real change
    # event -- setting the value in the same call that creates the item
    # doesn't count as a 'change', so the automation silently never fires.

    # Monday has its own automation: "when an item is created, set Estatus
    # to Por clasificar." That runs automatically, at some UNPREDICTABLE
    # delay after creation -- so a single fixed sleep is a guess, not a
    # guarantee. Instead: set Estatus, then read it back to confirm it
    # actually stuck; if Monday's automation clobbered it, try again.
    estatus_query = """
    mutation ($boardId: ID!, $itemId: ID!, $columnId: String!, $value: String!) {
      change_simple_column_value (
        board_id: $boardId,
        item_id: $itemId,
        column_id: $columnId,
        value: $value
      ) {
        id
      }
    }
    """
    estatus_variables = {
        "boardId": SOLICITUDES_BOARD_ID,
        "itemId": item_id,
        "columnId": "color_mm5fned8",
        "value": "Proyecto nuevo",
    }

    check_query = """
    query ($itemId: [ID!]) {
      items(ids: $itemId) {
        column_values(ids: ["color_mm5fned8"]) {
          text
        }
      }
    }
    """
    check_variables = {"itemId": [item_id]}

    # Growing wait schedule instead of a flat interval: start quick (in case
    # Monday's automation is fast this time), but escalate significantly if
    # it isn't. Monday's own "set to Por clasificar on create" automation
    # appears to now take noticeably longer to fire than it used to --
    # possibly a platform-side change out of our control -- so a short
    # fixed window increasingly means we ALWAYS lose the race. This runs
    # in a background thread already, so a longer worst case here doesn't
    # block anything else; it just means the jefa's "done" confirmation
    # can take longer to arrive in the worst case.
    WAIT_SCHEDULE = [3, 5, 8, 12, 15, 20, 25, 30, 30, 30, 30, 30, 30, 30, 30]
    max_attempts = len(WAIT_SCHEDULE)  # worst case ~5 minutes total
    estatus_confirmed = False
    for attempt in range(1, max_attempts + 1):
        time.sleep(WAIT_SCHEDULE[attempt - 1])

        requests.post(
            MONDAY_API_URL,
            json={"query": estatus_query, "variables": estatus_variables},
            headers=headers,
        )
        check_response = requests.post(
            MONDAY_API_URL,
            json={"query": check_query, "variables": check_variables},
            headers=headers,
        )
        current_value = (
            check_response.json()["data"]["items"][0]["column_values"][0]["text"]
        )

        if current_value != "Proyecto nuevo":
            print(f"Estatus attempt {attempt}: still {current_value!r}, retrying...")
            continue

        # Seen "Proyecto nuevo" once -- but Monday's own automation might
        # still revert it a moment later if it's running slowly. Wait
        # longer and check again before fully trusting it.
        time.sleep(5)
        recheck_response = requests.post(
            MONDAY_API_URL,
            json={"query": check_query, "variables": check_variables},
            headers=headers,
        )
        recheck_value = (
            recheck_response.json()["data"]["items"][0]["column_values"][0]["text"]
        )

        if recheck_value == "Proyecto nuevo":
            print(f"Estatus confirmed stable as 'Proyecto nuevo' (attempt {attempt})")
            estatus_confirmed = True
            break
        else:
            print(
                f"Estatus attempt {attempt}: reverted to {recheck_value!r} "
                f"after initial confirmation -- retrying..."
            )
    else:
        print(
            f"WARNING: Estatus still not 'Proyecto nuevo' after {max_attempts} "
            f"attempts -- may need manual fix or automation review."
        )

    if estatus_confirmed:
        send_whatsapp_message(
            sender,
            f"✅ ¡Listo! '{nombre_proyecto}' quedó marcado como 'Proyecto "
            f"nuevo' y ya sigue el proceso automático.",
        )
    else:
        send_whatsapp_message(
            sender,
            f"⚠️ No pude confirmar que '{nombre_proyecto}' quedó marcado "
            f"como 'Proyecto nuevo' después de varios intentos. Por favor "
            f"revisa el item manualmente en Monday.",
        )

    return estatus_confirmed


def handle_message(sender, text_body):
    """
    Walks a jefa through the request-creation flow, one WhatsApp
    message at a time, based on what step her session is currently on.
    """
    text_body = text_body.strip()

    # Safeword: lets someone bail out of a half-finished request at any
    # step, instead of being stuck until it's completed or the server
    # restarts (which would silently wipe SESSIONS anyway).
    CANCEL_WORDS = {"cancelar", "cancel"}
    if text_body.lower() in CANCEL_WORDS:
        if sender in SESSIONS:
            del SESSIONS[sender]
            send_whatsapp_message(
                sender,
                "❌ Solicitud cancelada. Escribe cualquier mensaje para "
                "iniciar una nueva.",
            )
        else:
            send_whatsapp_message(sender, "No tienes ninguna solicitud en curso.")
        return

    # No session yet -> this is the start of a new request.
    if sender not in SESSIONS:
        SESSIONS[sender] = {"step": "tipo_proyecto", "data": {}}
        send_whatsapp_message(sender, MENU_TIPO_PROYECTO)
        return

    session = SESSIONS[sender]
    step = session["step"]

    if step == "tipo_proyecto":
        if text_body not in TIPOS_PROYECTO:
            send_whatsapp_message(
                sender, "No reconocí esa opción. " + MENU_TIPO_PROYECTO
            )
            return
        session["data"]["tipo_proyecto"] = TIPOS_PROYECTO[text_body]
        session["step"] = "nombre_proyecto"
        send_whatsapp_message(sender, "¿Cuál es el nombre del proyecto?")

    elif step == "nombre_proyecto":
        session["data"]["nombre_proyecto"] = text_body
        session["step"] = "cliente_proyecto"
        send_whatsapp_message(sender, "¿Cuál es el cliente / proyecto?")

    elif step == "cliente_proyecto":
        session["data"]["cliente_proyecto"] = text_body
        session["step"] = "que_se_necesita"
        send_whatsapp_message(sender, "¿Qué se necesita exactamente?")

    elif step == "que_se_necesita":
        session["data"]["que_se_necesita"] = text_body
        session["step"] = "deadline"
        send_whatsapp_message(sender, "¿Cuál es la fecha límite? (Formato: DD/MM/AAAA)")

    elif step == "deadline":
        fecha_iso = parsear_fecha_ddmmaaaa(text_body)
        if fecha_iso is None:
            send_whatsapp_message(
                sender,
                "No reconocí esa fecha. Usa el formato DD/MM/AAAA, "
                "por ejemplo 15/08/2026.",
            )
            return
        session["data"]["deadline"] = fecha_iso
        session["step"] = "quien_lo_pide"
        send_whatsapp_message(sender, MENU_QUIEN_LO_PIDE)

    elif step == "quien_lo_pide":
        if text_body not in QUIEN_LO_PIDE_OPTIONS:
            send_whatsapp_message(
                sender, "No reconocí esa opción. " + MENU_QUIEN_LO_PIDE
            )
            return
        session["data"]["quien_lo_pide"] = QUIEN_LO_PIDE_OPTIONS[text_body]
        session["step"] = "jefa_asignada"
        send_whatsapp_message(sender, "¿Quién es la jefa asignada?")

    elif step == "jefa_asignada":
        jefa_key = text_body.lower()

        if jefa_key not in JEFAS:
            # Exact match failed -- try a close match instead of rejecting
            # outright, so small typos ("oskar" instead of "oscar") still
            # work. cutoff=0.6 is fairly lenient but still won't match
            # two genuinely different names by accident.
            close_matches = difflib.get_close_matches(
                jefa_key, JEFAS.keys(), n=1, cutoff=0.6
            )
            if close_matches:
                jefa_key = close_matches[0]
            else:
                nombres = ", ".join(j["name"] for j in JEFAS.values())
                send_whatsapp_message(
                    sender,
                    f"No reconocí ese nombre. Jefas disponibles: {nombres}",
                )
                return

        jefa = JEFAS[jefa_key]
        session["data"]["jefa_asignada"] = jefa
        session["step"] = "estatus_inicial"
        send_whatsapp_message(sender, MENU_ESTATUS)

    elif step == "estatus_inicial":
        if text_body not in ESTATUS_OPTIONS:
            send_whatsapp_message(
                sender, "No reconocí esa opción. " + MENU_ESTATUS
            )
            return

        marcar_proyecto_nuevo = ESTATUS_OPTIONS[text_body] == "Proyecto nuevo"
        session["data"]["estatus_inicial"] = ESTATUS_OPTIONS[text_body]
        jefa = session["data"]["jefa_asignada"]

        print(f"COMPLETED REQUEST from {sender}: {session['data']}")

        deadline_display = datetime.strptime(
            session["data"]["deadline"], "%Y-%m-%d"
        ).strftime("%d/%m/%Y")

        campos_comunes = (
            f"- Tipo de proyecto: {session['data']['tipo_proyecto']}\n"
            f"- Nombre: {session['data']['nombre_proyecto']}\n"
            f"- Cliente / proyecto: {session['data']['cliente_proyecto']}\n"
            f"- Qué se necesita: {session['data']['que_se_necesita']}\n"
            f"- Deadline: {deadline_display}\n"
            f"- Quién lo pide: {session['data']['quien_lo_pide']}\n"
            f"- Jefa asignada: {jefa['name']}"
        )

        if marcar_proyecto_nuevo:
            resumen_inicial = (
                "✅ Solicitud creada en Monday:\n"
                f"{campos_comunes}\n\n"
                "Estoy confirmando que quede marcada como 'Proyecto nuevo' "
                "para que siga el proceso automático -- esto puede tardar "
                "unos minutos, te aviso en cuanto esté listo."
            )
        else:
            resumen_inicial = (
                "✅ Solicitud registrada en Monday como 'Por clasificar':\n"
                f"{campos_comunes}\n\n"
                "Alguien deberá marcarla como 'Proyecto nuevo' manualmente "
                "en Monday cuando esté lista para seguir el proceso."
            )

        crear_solicitud_en_monday(
            nombre_proyecto=session["data"]["nombre_proyecto"],
            tipo_proyecto=session["data"]["tipo_proyecto"],
            jefa=jefa,
            cliente_proyecto=session["data"]["cliente_proyecto"],
            que_se_necesita=session["data"]["que_se_necesita"],
            deadline_iso=session["data"]["deadline"],
            quien_lo_pide=session["data"]["quien_lo_pide"],
            marcar_proyecto_nuevo=marcar_proyecto_nuevo,
            sender=sender,
            resumen_inicial=resumen_inicial,
        )

        # Conversation finished -> clear session so a new message starts fresh.
        del SESSIONS[sender]


def send_whatsapp_message(to, text):
    """
    Sends a plain text WhatsApp message to `to` (a phone number, no '+',
    e.g. '5218126293873' — same format WhatsApp gave us in the incoming
    payload's 'from' field).
    """
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text},
    }

    response = requests.post(GRAPH_API_URL, headers=headers, json=payload)
    print(f"Sent message -> status {response.status_code}: {response.text}")
    return response


@app.route("/webhook", methods=["GET"])
def verify_webhook():
    """
    Meta calls this once, with GET, when you click 'Verify and save'
    in the dashboard. It sends three query params:
      - hub.mode          (should be 'subscribe')
      - hub.verify_token  (should match VERIFY_TOKEN above)
      - hub.challenge     (a random number we must echo back)
    If everything matches, we return hub.challenge as plain text
    and Meta considers the webhook verified.
    """
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        print("Webhook verified successfully!")
        return challenge, 200
    else:
        print("Webhook verification failed.")
        return "Verification failed", 403


@app.route("/webhook", methods=["POST"])
def receive_message():
    """
    Meta calls this with POST every time something happens: an incoming
    message, a delivery receipt, a read receipt, etc. We only care about
    actual incoming text messages -- status updates (sent/delivered/read)
    are expected and frequent, so we quietly ignore them instead of
    logging each one.
    """
    data = request.get_json()

    try:
        entry = data["entry"][0]
        change = entry["changes"][0]["value"]
        message = change["messages"][0]
        sender = message["from"]
        text_body = message["text"]["body"]

        print(f"Message from {sender}: {text_body}")

        # Run in the background instead of blocking here. Our own retry
        # loops (Estatus verification, etc.) can take many seconds --
        # if we don't respond to Meta quickly, it assumes delivery failed
        # and RE-SENDS the same message, causing duplicate processing.
        threading.Thread(target=handle_message, args=(sender, text_body)).start()

    except (KeyError, IndexError):
        # Not a text message (delivery/read receipt, etc.) -- nothing to do.
        pass

    # Respond immediately -- the real work happens in the background thread.
    return jsonify({"status": "received"}), 200


@app.route("/webhook/pipeline", methods=["POST"])
def pipeline_webhook():
    """
    Monday calls this whenever a new item is created on the Pipeline board.
    On FIRST registering the webhook, Monday sends a one-time payload like
    {"challenge": "some_string"} and expects us to echo it straight back --
    that's how Monday confirms we actually own this URL (its own version of
    Meta's GET-based handshake).
    """
    data = request.get_json()

    if "challenge" in data:
        return jsonify({"challenge": data["challenge"]}), 200

    try:
        event = data["event"]
        if event.get("type") == "create_pulse":
            pipeline_item_id = event["pulseId"]
            nombre_proyecto = event["pulseName"]
            print(f"New Pipeline item: {nombre_proyecto!r} (id={pipeline_item_id})")
            threading.Thread(
                target=procesar_nuevo_pipeline_item,
                args=(pipeline_item_id, nombre_proyecto),
            ).start()
    except (KeyError, TypeError) as e:
        print(f"Unrecognized Pipeline webhook payload shape: {e}")

    return jsonify({"status": "received"}), 200


if __name__ == "__main__":
    app.run(port=5000, debug=True)