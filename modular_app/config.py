import os
from dotenv import load_dotenv

load_dotenv()  # reads the .env file and makes its values available via os.environ

# --- WhatsApp / Meta config ---
# Choose any string you want here — you'll type this SAME string
# into the Meta dashboard's "Verify token" field in a later step.
VERIFY_TOKEN = "poligrama_verify_123"

ACCESS_TOKEN = os.environ["META_ACCESS_TOKEN"]
PHONE_NUMBER_ID = "1227828833752720"  # your test number's Phone Number ID
GRAPH_API_URL = f"https://graph.facebook.com/v21.0/{PHONE_NUMBER_ID}/messages"

# --- Monday.com config ---
MONDAY_API_TOKEN = os.environ["MONDAY_API_TOKEN"]
MONDAY_API_URL = "https://api.monday.com/v2"

SOLICITUDES_BOARD_ID = "18433041710"
PIPELINE_BOARD_ID = "18433042098"
TAREAS_BOARD_ID = "18433042251"
TAREAS_ACTIVE_GROUP_ID = "group_mm5pb0qr"  # 🟢 Proyectos activos
DISENO_BOARD_ID = "18433042352"
DISENO_GROUP_ID = "topics"  # Diseño

# Pipeline board column ids
PIPELINE_TIPO_COLUMN = "color_mm5f84fz"
PIPELINE_JEFA_COLUMN = "multiple_person_mm5fs9qd"
PIPELINE_SEMAFORO_COLUMN = "color_mm5f545g"
PIPELINE_LINK_TAREAS_COLUMN = "board_relation_mm5fsvg8"

# --- Conversation menu text and lookup tables ---
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

# Jefas allowed to use the bot -> their Monday.com user info.
# Key is what they type in WhatsApp (lowercase), matched case-insensitively.
JEFAS = {
    "sergio": {"id": "77165762", "name": "Sergio Morelos"},
    "karina": {"id": "78712932", "name": "Karina Gutierrez Peña"},
    "gybram": {"id": "79095202", "name": "Gybram Vásquez"},
    "oscar": {"id": "112077190", "name": "Oscar Daniel Retes Torres"},
    "violeta": {"id": "79096528", "name": "Violeta Sias"},
    "rodrigo": {"id": "79096568", "name": "Rodrigo Irigoyen"},
    "veronica": {"id": "79096680", "name": "Verónica Infante Martinez"},
    "yuliana": {"id": "79096757", "name": "Yuliana Garza Lopez"},
    "carolina": {"id": "79152777", "name": "Carolina Gonzalez"},
    "fabiola": {"id": "79215163", "name": "Fabiola Vallejo Uresti"},
    "keren": {"id": "80755784", "name": "Keren De los Reyes"},
    "carola": {"id": "88223460", "name": "Carola Castillo García"},
    "aleida": {"id": "88245819", "name": "Aleida Soto"},
    "liliana": {"id": "95600841", "name": "Liliana Berenice Martinez Morales"},
    "carlos": {"id": "98022280", "name": "Krlos Chavarria"},
    "jose": {"id": "102602024", "name": "José Eduardo Salazar Cepeda"},
    "valeria": {"id": "104660029", "name": "Valeria Balleza"},
    "rosana": {"id": "105185612", "name": "Rosana De La Rosa"},
    "nicole": {"id": "110292208", "name": "Nicole Velazquez García"},
    "silvana": {"id": "111598773", "name": "Silvana Riveroll"},
}

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