import os
import streamlit as st
from pydantic import ValidationError
from PIL import Image

# Google Gemini for document analysis (optional)
try:
    from google import genai
    API_KEY = os.getenv("GOOGLE_API_KEY")
    gemini_client = genai.Client(api_key=API_KEY) if API_KEY else None
except ImportError:
    print("[INFO] google-genai not installed. Document AI analysis will be disabled.")
    gemini_client = None


def _format_validation_error(e: ValidationError) -> str:
    """Extrae mensajes legibles de ValidationError de Pydantic."""
    errors = e.errors()
    messages = []
    for err in errors:
        field = " -> ".join(str(loc) for loc in err['loc'])
        msg = err['msg']
        messages.append(f"• {field}: {msg}")
    return "Error de validación:\n" + "\n".join(messages)


def analizar_documento_con_ia(imagen_upload):
    """Analiza documento con Gemini Vision AI."""
    try:
        if not gemini_client: return None
        img = Image.open(imagen_upload)
        prompt = """
        Actúa como un recepcionista experto en documentos internacionales. Analiza esta imagen.
        Puede ser: Cédula de Paraguay, DNI de Argentina, RG/CNH de Brasil o Pasaporte.

        Reglas OBLIGATORIAS:
        1. Devuelve SOLO un JSON válido.
        2. Si un dato no aparece, devuelve null o string vacío.
        3. Fechas: Formato YYYY-MM-DD.
        4. Nro_Documento: Solo números y letras, sin puntos.

        Estructura JSON:
        {
            "Apellidos": "string",
            "Nombres": "string",
            "Nacionalidad": "string",
            "Fecha_Nacimiento": "YYYY-MM-DD",
            "Nro_Documento": "string",
            "Pais": "string",
            "Sexo": "string",
            "Estado_Civil": "string",
            "Procedencia": "string"
        }
        """
        response = gemini_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[prompt, img]
        )
        texto_limpio = response.text.replace("```json", "").replace("```", "").strip()
        import json
        return json.loads(texto_limpio)
    except Exception as e:
        st.error(f"Error IA: {e}")
        return None
