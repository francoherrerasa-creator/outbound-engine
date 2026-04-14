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
    "Mensaje",
    "Modelo de Negocio",
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
        analysis.get("mensaje_outreach", ""),
        analysis.get("modelo_negocio", ""),
        "",  # Notas - vacío para que el usuario complete
    ]

    sheet.append_row(row, value_input_option="USER_ENTERED")

    return sheet.spreadsheet.url
