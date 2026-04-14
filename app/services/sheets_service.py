import json
import os
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
from app.config import GOOGLE_SHEETS_CREDENTIALS_FILE, GOOGLE_SHEET_NAME, GOOGLE_SHEETS_ID

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

HEADERS = [
    "Fecha",
    "Empresa",
    "Sector",
    "Ubicación",
    "Tamaño",
    "Decision Maker",
    "Cargo",
    "Señales",
    "Etapa",
    "Score",
    "Siguiente Acción",
    "Fuente",
    "Notas",
]


def _get_credentials():
    creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
    if creds_json:
        return Credentials.from_service_account_info(
            json.loads(creds_json), scopes=SCOPES
        )
    return Credentials.from_service_account_file(
        GOOGLE_SHEETS_CREDENTIALS_FILE, scopes=SCOPES
    )


def _get_sheet():
    gc = gspread.authorize(_get_credentials())

    if GOOGLE_SHEETS_ID:
        spreadsheet = gc.open_by_key(GOOGLE_SHEETS_ID)
        sheet = spreadsheet.worksheet("Outbound")
    else:
        try:
            sheet = gc.open(GOOGLE_SHEET_NAME).worksheet("Outbound")
        except gspread.SpreadsheetNotFound:
            spreadsheet = gc.create(GOOGLE_SHEET_NAME)
            sheet = spreadsheet.sheet1
            sheet.update_title("Outbound")
            sheet.append_row(HEADERS)
            spreadsheet.share("", perm_type="anyone", role="writer")

    return sheet


def save_prospect(company: dict, analysis: dict) -> str:
    """Save an approved prospect to Google Sheets. Returns the sheet URL."""
    sheet = _get_sheet()

    # Ensure headers exist
    existing = sheet.row_values(1)
    if not existing:
        sheet.append_row(HEADERS)

    senales = ", ".join(analysis.get("senales_compra", []))
    contacto = analysis.get("contacto_ideal", {})

    row = [
        datetime.now().strftime("%Y-%m-%d %H:%M"),
        company.get("name", ""),
        company.get("industry", ""),
        company.get("city", ""),
        company.get("size_estimate", ""),
        contacto.get("nombre_sugerido", "Por investigar"),
        contacto.get("cargo", ""),
        senales,
        "Identificado",
        analysis.get("score", ""),
        "Investigar decision maker",
        "Outbound Engine",
        "",
    ]

    sheet.append_row(row, value_input_option="USER_ENTERED")

    return sheet.spreadsheet.url


# ══════════════════════════════════════════════════════════════════════
# Lectura de prospects para el dashboard
# ══════════════════════════════════════════════════════════════════════

OUTBOUND_STAGES_VALIDAS = {
    "identificado", "investigado", "mensaje_enviado", "respondio",
    "reunion_agendada", "propuesta_enviada", "ganado", "perdido",
}


def _normalizar_stage(etapa: str) -> str:
    """'Mensaje Enviado' → 'mensaje_enviado', 'Respondió' → 'respondio', etc."""
    if not etapa:
        return "identificado"
    e = str(etapa).lower().strip()
    for acento, plano in (("á","a"), ("é","e"), ("í","i"), ("ó","o"), ("ú","u")):
        e = e.replace(acento, plano)
    e = e.replace(" ", "_")
    return e if e in OUTBOUND_STAGES_VALIDAS else "identificado"


def _score_a_prioridad(score) -> str:
    """>80 → Alta, >50 → Media, resto (incluye no-numérico) → Baja."""
    try:
        s = float(score)
    except (ValueError, TypeError):
        return "Baja"
    if s > 80:
        return "Alta"
    if s > 50:
        return "Media"
    return "Baja"


def _fecha_iso(fecha: str) -> str:
    """'2026-04-14 14:30' → '2026-04-14'. Mantiene lo que venga si no hay espacio."""
    if not fecha:
        return ""
    return str(fecha).split(" ")[0]


def _contacto_clave(decision_maker: str, cargo: str) -> str:
    dm = (decision_maker or "").strip()
    ca = (cargo or "").strip()
    if dm and ca:
        return f"{dm} · {ca}"
    return dm or ca


def get_prospects() -> list[dict]:
    """
    Lee todos los prospects de la pestaña Outbound y los mapea al shape
    que espera TabOutbound en el dashboard de Road Tractovan.
    """
    import logging
    logger = logging.getLogger("outbound-engine")
    try:
        sheet = _get_sheet()
        registros = sheet.get_all_records()

        prospects = []
        for i, row in enumerate(registros, start=1):
            fecha = _fecha_iso(row.get("Fecha", ""))
            stage = _normalizar_stage(row.get("Etapa", ""))

            prospects.append({
                "id": i,
                "empresa": row.get("Empresa", ""),
                "industria": row.get("Sector", ""),
                "ciudad": row.get("Ubicación", ""),
                "flota_est": row.get("Tamaño", ""),
                "web": "",
                "stage": stage,
                "prioridad": _score_a_prioridad(row.get("Score", "")),
                "contacto_clave": _contacto_clave(
                    row.get("Decision Maker", ""),
                    row.get("Cargo", ""),
                ),
                "señales": row.get("Señales", ""),
                "fecha_entrada": fecha,
                "fecha_stage": fecha,
                "notas": row.get("Notas", ""),
                "historial": [{"stage": stage, "fecha": fecha}],
            })

        return prospects
    except Exception as e:
        logger.error(f"Error leyendo prospects de Google Sheets: {e}")
        return []
