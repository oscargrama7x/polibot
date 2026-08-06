import difflib
from datetime import datetime

from config import (
    TIPOS_PROYECTO,
    MENU_TIPO_PROYECTO,
    MENU_ESTATUS,
    ESTATUS_OPTIONS,
    MENU_QUIEN_LO_PIDE,
    QUIEN_LO_PIDE_OPTIONS,
    JEFAS,
)
from whatsapp_client import send_whatsapp_message
from monday_client import crear_solicitud_en_monday

# --- Conversation state ---
# One entry per phone number, e.g.:
# SESSIONS["5218126293873"] = {"step": "nombre_proyecto", "data": {"tipo_proyecto": "Encuesta de campo"}}
# NOTE: this dict lives only in memory — it resets every time the server restarts.
SESSIONS = {}


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
