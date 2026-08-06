import json
import time
import requests

from config import (
    MONDAY_API_TOKEN,
    MONDAY_API_URL,
    SOLICITUDES_BOARD_ID,
    PIPELINE_BOARD_ID,
    TAREAS_BOARD_ID,
    TAREAS_ACTIVE_GROUP_ID,
    DISENO_BOARD_ID,
    DISENO_GROUP_ID,
    PIPELINE_TIPO_COLUMN,
    PIPELINE_JEFA_COLUMN,
    PIPELINE_SEMAFORO_COLUMN,
    PIPELINE_LINK_TAREAS_COLUMN,
)
from whatsapp_client import send_whatsapp_message


def monday_headers():
    return {
        "Authorization": MONDAY_API_TOKEN,
        "Content-Type": "application/json",
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
