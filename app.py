import difflib
import json
import time
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# Choose any string you want here — you'll type this SAME string
# into the Meta dashboard's "Verify token" field in a later step.
VERIFY_TOKEN = "poligrama_verify_123"

# --- Fill these in with YOUR current values ---
ACCESS_TOKEN = "EAAe7ZCVa2EDYBSLi8AMU3y7Qk2AHEGITb9NylYVx0K9Q9vf9mSLUp5wkFf8dIKT4SrcXR0ZAeJNirvzxovXzQuThCclUekngYQpM1LsNPyDjjl9nvk4ZArUow0FIUOQ3jECufwt0CXOsaYYfZAZAxXSuBV3tpfVdYyZCIKAKR7Ai661davTv8AZCvnDMZAcvi6jVMQZDZD"
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
}

MENU_TIPO_PROYECTO = (
    "¿Qué tipo de proyecto es? Responde con el número:\n"
    "1. Encuesta de campo\n"
    "2. Encuesta telefónica\n"
    "3. Push call\n"
    "4. Grupos de enfoque"
)

# --- Monday.com config ---
MONDAY_API_TOKEN = "eyJhbGciOiJIUzI1NiJ9.eyJ0aWQiOjY4OTI0MzE1NiwiYWFpIjoxMSwidWlkIjoxMTIwNzcxOTAsImlhZCI6IjIwMjYtMDgtMDNUMTU6NDM6NDguNzU3WiIsInBlciI6Im1lOndyaXRlIiwiYWN0aWQiOjI5OTYzNDM1LCJyZ24iOiJ1c2UxIn0.nY4z0lzqWKNzNcE5f4gtxnNHyo5ltoM221Eicemtx5o"
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

# Pipeline board column ids
PIPELINE_TIPO_COLUMN = "color_mm5f84fz"
PIPELINE_JEFA_COLUMN = "multiple_person_mm5fs9qd"
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


def monday_headers():
    return {
        "Authorization": MONDAY_API_TOKEN,
        "Content-Type": "application/json",
    }


def get_solicitud_data(nombre_proyecto):
    """
    Looks up the Solicitudes item with this exact name and returns its
    Tipo de proyecto (as text) and Jefa asignada (as a list of Monday user
    ids). Returns None if no matching item is found.
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

    # Names aren't guaranteed unique in Monday -- if two Solicitudes share
    # the same name, pick the most recently created one (highest numeric
    # id) rather than whichever happens to appear first in the list.
    matches = [item for item in items if item["name"] == nombre_proyecto]
    if not matches:
        print(f"[get_solicitud_data] No Solicitud named {nombre_proyecto!r} found.")
        return None

    if len(matches) > 1:
        print(
            f"[get_solicitud_data] WARNING: {len(matches)} Solicitudes named "
            f"{nombre_proyecto!r} found -- using the most recent one. "
            f"Consider using more distinct project names."
        )

    item = max(matches, key=lambda i: int(i["id"]))

    tipo_proyecto = None
    jefa_ids = []
    for col in item["column_values"]:
        if col["id"] == "color_mm5wgrz5":
            tipo_proyecto = col["text"]
        elif col["id"] == "multiple_person_mm5fdarq":
            value = json.loads(col["value"]) if col["value"] else {}
            jefa_ids = [p["id"] for p in value.get("personsAndTeams", [])]

    return {"tipo_proyecto": tipo_proyecto, "jefa_ids": jefa_ids}


def set_pipeline_tipo_y_jefa(pipeline_item_id, tipo_proyecto, jefa_ids):
    """Writes Tipo de proyecto and Jefa responsable onto a Pipeline item."""
    tipo_value = json.dumps({"label": tipo_proyecto})
    jefa_value = json.dumps(
        {"personsAndTeams": [{"id": jid, "kind": "person"} for jid in jefa_ids]}
    )

    for column_id, value in [
        (PIPELINE_TIPO_COLUMN, tipo_value),
        (PIPELINE_JEFA_COLUMN, jefa_value),
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


def crear_tareas_item_con_subtareas(nombre_proyecto, subtask_names):
    """Creates a new item in Tareas -> Proyectos activos, plus one subitem
    per name in subtask_names. Returns the new item's id."""
    query = """
    mutation ($boardId: ID!, $groupId: String!, $itemName: String!) {
      create_item (
        board_id: $boardId, group_id: $groupId, item_name: $itemName
      ) { id }
    }
    """
    variables = {
        "boardId": TAREAS_BOARD_ID,
        "groupId": TAREAS_ACTIVE_GROUP_ID,
        "itemName": nombre_proyecto,
    }
    response = requests.post(
        MONDAY_API_URL,
        json={"query": query, "variables": variables},
        headers=monday_headers(),
    )
    tareas_item_id = response.json()["data"]["create_item"]["id"]

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


def procesar_nuevo_pipeline_item(pipeline_item_id, nombre_proyecto):
    """
    Full Phase 4 sync, triggered whenever a new item appears on Pipeline:
    1. Pull Tipo de proyecto + Jefa asignada from the matching Solicitud.
    2. Write those onto the Pipeline item (since Monday doesn't carry them over).
    3. Find the matching template and build the Tareas item + subtasks.
    4. Link Pipeline -> Tareas.
    """
    solicitud = get_solicitud_data(nombre_proyecto)
    if not solicitud or not solicitud["tipo_proyecto"]:
        print(f"No matching Solicitud found for '{nombre_proyecto}' -- skipping sync.")
        post_pipeline_update(
            pipeline_item_id,
            "⚠️ El bot no pudo encontrar la Solicitud original con este mismo "
            "nombre, así que Tipo de proyecto y Jefa no se copiaron "
            "automáticamente. Revisar manualmente.",
        )
        return

    tipo_proyecto = solicitud["tipo_proyecto"]
    jefa_ids = solicitud["jefa_ids"]

    set_pipeline_tipo_y_jefa(pipeline_item_id, tipo_proyecto, jefa_ids)

    subtask_names = TEMPLATES.get(tipo_proyecto)
    if not subtask_names:
        print(f"No template for tipo_proyecto='{tipo_proyecto}' -- skipping Tareas creation.")
        post_pipeline_update(
            pipeline_item_id,
            f"⚠️ No existe una plantilla en Tareas para el tipo de proyecto "
            f"'{tipo_proyecto}'. Crear el item y las tareas manualmente en "
            f"el board de Tareas.",
        )
        return

    tareas_item_id = crear_tareas_item_con_subtareas(nombre_proyecto, subtask_names)
    set_pipeline_link_to_tareas(pipeline_item_id, tareas_item_id)

    print(f"Synced '{nombre_proyecto}' -> Tareas item {tareas_item_id}")


def crear_solicitud_en_monday(nombre_proyecto, tipo_proyecto, jefa):
    """
    Creates a new item on the Solicitudes board via Monday's GraphQL API.
    `jefa` is a dict like {"id": "77165762", "name": "Sergio Morelos"}.
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
    item_id = response.json()["data"]["create_item"]["id"]
    print(f"Created Solicitud item {item_id}: {nombre_proyecto!r}")

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

    max_attempts = 5
    estatus_confirmed = False
    for attempt in range(1, max_attempts + 1):
        time.sleep(2)  # give Monday's own automation a moment to act first

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
        time.sleep(4)
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

    return estatus_confirmed


def handle_message(sender, text_body):
    """
    Walks a jefa through the request-creation flow, one WhatsApp
    message at a time, based on what step her session is currently on.
    """
    text_body = text_body.strip()

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

        print(f"COMPLETED REQUEST from {sender}: {session['data']}")

        estatus_confirmed = crear_solicitud_en_monday(
            nombre_proyecto=session["data"]["nombre_proyecto"],
            tipo_proyecto=session["data"]["tipo_proyecto"],
            jefa=jefa,
        )

        if estatus_confirmed:
            resumen = (
                "✅ Solicitud registrada en Monday:\n"
                f"- Tipo de proyecto: {session['data']['tipo_proyecto']}\n"
                f"- Nombre: {session['data']['nombre_proyecto']}\n"
                f"- Jefa asignada: {jefa['name']}"
            )
        else:
            # The item WAS created in Solicitudes (Tipo de proyecto and
            # Jefa are set), but Estatus never confirmed as "Proyecto
            # nuevo" -- meaning it likely won't move to Pipeline
            # automatically. Tell the truth instead of a false "success".
            resumen = (
                "⚠️ La solicitud se creó, pero no pude confirmar que quedó "
                "marcada como 'Proyecto nuevo'. Por favor revisa el "
                f"item '{session['data']['nombre_proyecto']}' en Monday "
                "manualmente."
            )
        send_whatsapp_message(sender, resumen)

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

        handle_message(sender, text_body)

    except (KeyError, IndexError):
        # Not a text message (delivery/read receipt, etc.) -- nothing to do.
        pass

    # We must always respond 200 quickly, or Meta will retry/back off.
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
            procesar_nuevo_pipeline_item(pipeline_item_id, nombre_proyecto)
    except (KeyError, TypeError) as e:
        print(f"Unrecognized Pipeline webhook payload shape: {e}")

    return jsonify({"status": "received"}), 200


if __name__ == "__main__":
    app.run(port=5000, debug=True)