"""
Hotel PMS API - Vision Endpoint (Gemini 2.5 Flash)
=====================================================

Migrates the ID document scanning logic from Streamlit app.py to FastAPI.
Uses Google Gemini 2.5 Flash for vision-based document extraction.
"""

import os
import json
import asyncio
from io import BytesIO

from fastapi import APIRouter, UploadFile, File, HTTPException, status
from pydantic import BaseModel
from typing import Optional
from PIL import Image

from google import genai

# Import logging
from logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter()

# ==========================================
# CONFIGURATION
# ==========================================

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if not GOOGLE_API_KEY:
    logger.warning("GOOGLE_API_KEY not found. Vision endpoint will not work.")

# Initialize client (new SDK)
gemini_client = genai.Client(api_key=GOOGLE_API_KEY) if GOOGLE_API_KEY else None

# PERF-08-10: Limits for vision endpoint hardening
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB
GEMINI_TIMEOUT_SECONDS = 30


# ==========================================
# SCHEMAS
# ==========================================

class ExtractedDocumentData(BaseModel):
    """Data extracted from ID document by Gemini Vision."""
    Apellidos: Optional[str] = None
    Nombres: Optional[str] = None
    Nacionalidad: Optional[str] = None
    Fecha_Nacimiento: Optional[str] = None  # YYYY-MM-DD
    Nro_Documento: Optional[str] = None
    Pais: Optional[str] = None
    Sexo: Optional[str] = None
    Estado_Civil: Optional[str] = None
    Procedencia: Optional[str] = None


class VisionResponse(BaseModel):
    """Response from vision endpoint."""
    success: bool
    data: Optional[ExtractedDocumentData] = None
    error: Optional[str] = None


# ==========================================
# GEMINI PROMPT (FROM ORIGINAL app.py)
# ==========================================

DOCUMENT_EXTRACTION_PROMPT = """
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


# ==========================================
# ENDPOINTS
# ==========================================

@router.post(
    "/extract-data",
    response_model=VisionResponse,
    summary="Extract Data from ID Document",
    description="Upload an ID document image (Cédula, DNI, Pasaporte, etc.) and extract personal data using Gemini 2.5 Flash."
)
async def extract_document_data(
    file: UploadFile = File(..., description="ID document image (JPG, PNG, WebP)")
):
    """
    Extract personal data from an ID document using Gemini 2.5 Flash Vision.
    
    Supports:
    - Cédula de Paraguay
    - DNI de Argentina
    - RG/CNH de Brasil
    - Pasaportes internacionales
    
    Returns JSON with extracted fields: Apellidos, Nombres, Nacionalidad, etc.
    """
    # Check client is configured
    if not gemini_client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Servicio de vision no disponible."
        )
    
    # Validate file type
    allowed_types = ["image/jpeg", "image/png", "image/webp", "image/jpg"]
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type: {file.content_type}. Allowed: {', '.join(allowed_types)}"
        )
    
    try:
        # Read file with size check
        contents = await file.read()
        if len(contents) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Archivo demasiado grande. Maximo: 5MB."
            )

        image = Image.open(BytesIO(contents))
        logger.info(f"Processing image: {file.filename}, size: {len(contents)} bytes, dimensions: {image.size}")

        # Generate content with Gemini 2.5 Flash + timeout
        loop = asyncio.get_event_loop()
        response = await asyncio.wait_for(
            loop.run_in_executor(
                None,
                lambda: gemini_client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=[DOCUMENT_EXTRACTION_PROMPT, image]
                )
            ),
            timeout=GEMINI_TIMEOUT_SECONDS
        )

        # Clean response (remove markdown code blocks if present)
        raw_text = response.text
        cleaned_text = raw_text.replace("```json", "").replace("```", "").strip()

        logger.info(f"Gemini response: {cleaned_text[:200]}...")

        # Parse JSON
        extracted_data = json.loads(cleaned_text)

        return VisionResponse(
            success=True,
            data=ExtractedDocumentData(**extracted_data)
        )

    except HTTPException:
        raise  # Re-raise HTTP exceptions (413, etc.)
    except asyncio.TimeoutError:
        logger.warning(f"Gemini API timeout after {GEMINI_TIMEOUT_SECONDS}s for {file.filename}")
        return VisionResponse(
            success=False,
            error="El servicio de vision tardo demasiado. Intente de nuevo."
        )
    except json.JSONDecodeError as e:
        logger.error(f"JSON parse error from Gemini: {e}")
        return VisionResponse(
            success=False,
            error="No se pudo interpretar la respuesta del servicio de vision."
        )
    except Exception as e:
        logger.error(f"Vision processing error: {e}", exc_info=True)
        return VisionResponse(
            success=False,
            error="Error al procesar el documento. Intente con otra imagen."
        )


@router.get(
    "/status",
    summary="Check Vision Service Status",
    description="Check if the Gemini Vision service is configured and ready."
)
def get_vision_status():
    """Check if vision service is available."""
    return {
        "configured": GOOGLE_API_KEY is not None,
        "model": "gemini-2.5-flash",
        "status": "ready" if GOOGLE_API_KEY else "unavailable"
    }
