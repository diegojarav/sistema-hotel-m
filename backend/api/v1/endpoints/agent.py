"""
Hotel PMS API - AI Agent with Gemini 2.5 Flash
==================================================

Architecture: Hybrid Cloud-Local
- User query sent to Gemini API with tool definitions
- Gemini decides which tool to call (automatic function calling)
- Backend executes Python function locally (SQL queries)
- Gemini formats the final natural language response

RELIABILITY HARDENED:
- Retry logic with exponential backoff (tenacity)
- Input sanitization to prevent prompt injection
- Graceful fallback on API failures

Uses the google-genai SDK v1.0+ with automatic_function_calling.
"""

import os
import re
from datetime import date
from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel, Field

# Google Gemini SDK
from google import genai
from google.genai import types

# Retry logic
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

# Import tools and dependencies
from api.v1.endpoints.ai_tools import TOOLS_LIST
from api.deps import get_current_user
from database import User

# Centralized logging
from logging_config import get_logger
logger = get_logger(__name__)

router = APIRouter()


# ==========================================
# CONFIGURATION
# ==========================================

MODEL_NAME = "gemini-2.5-flash"
FALLBACK_RESPONSE = "Lo siento, el asistente no está disponible en este momento. Por favor intente más tarde."

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

# Initialize Gemini client
# API key loaded from environment variable GOOGLE_API_KEY
try:
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY not found in environment")
    client = genai.Client(api_key=api_key)
    logger.info("Gemini client initialized successfully")
except Exception as e:
    logger.warning(f"Failed to initialize Gemini client: {e}")
    client = None


# ==========================================
# SCHEMAS
# ==========================================

class AgentQueryRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=2000, description="Consulta para el agente")


class AgentQueryResponse(BaseModel):
    response: str
    model: str
    tools_used: list = []
    status: str = "success"


# ==========================================
# SECURITY: INPUT SANITIZATION
# ==========================================

def sanitize_hotel_name(name: str) -> str:
    """
    Sanitize hotel name to prevent prompt injection.
    Removes special characters that could be used for manipulation.
    """
    # Only allow alphanumeric, spaces, and basic punctuation
    sanitized = re.sub(r'[^\w\s\-\.]', '', name)
    return sanitized[:50].strip() or "Hotel"


def sanitize_user_query(query: str) -> str:
    """
    Basic sanitization of user query.
    Removes control characters and limits length.
    """
    # Remove control characters
    sanitized = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', query)
    return sanitized.strip()


# ==========================================
# SYSTEM INSTRUCTION
# ==========================================

def get_system_instruction() -> str:
    """Generate system instruction with current date and sanitized hotel name."""
    from services import SettingsService
    today_str = date.today().strftime("%d/%m/%Y")
    raw_hotel_name = SettingsService.get_hotel_name()
    hotel_name = sanitize_hotel_name(raw_hotel_name)
    
    return f"""Eres el Recepcionista Virtual del {hotel_name}, un hotel en Asunción, Paraguay.

HOY ES: {today_str}

CONTEXTO DEL HOTEL:
- 15 habitaciones activas (categorías: Estándar, Matrimonial, Triple, Familiar)
- Moneda: Guaraníes (Gs) - PYG
- Zona horaria: America/Asuncion (UTC-3/-4)
- Estacionamiento disponible para huéspedes

REGLAS:
1. SIEMPRE usa una herramienta cuando la consulta requiera datos del hotel.
2. Responde en español, breve, profesional y amable.
3. Si una herramienta retorna "No encontré", responde exactamente eso — NUNCA inventes datos.
4. Si no hay herramienta apropiada, responde educadamente que no puedes ayudar con eso.
5. Formatea números grandes con separadores de miles (ej: 1.500.000 Gs).
6. Para reportes con múltiples filas, usa listas con viñetas o tablas markdown.

HERRAMIENTAS DISPONIBLES (14):

📋 CONSULTAS EN TIEMPO REAL:
- check_availability(check_date, stay_days): Habitaciones libres para una fecha
- get_hotel_rates(room_type): Precios y tarifas por categoría
- get_today_summary(): Resumen de hoy (ocupación, llegadas, salidas)
- calculate_price(category_name, check_in_date, stay_days, client_type): Cotización detallada con temporada y descuentos

🔍 BÚSQUEDAS:
- search_reservation(query): Buscar reservas por nombre, ID o documento
- search_guest(query): Buscar fichas de check-in (huéspedes que ya llegaron)

📊 REPORTES Y ANÁLISIS:
- get_reservations_report(start_date, end_date, room_number): Lista de reservas en un rango de fechas
- get_occupancy_for_month(year, month): Resumen de ocupación mensual
- get_room_performance(start_date, end_date, room_code): Rendimiento por habitación (ingresos, ocupación, tarifa promedio)
- get_booking_sources(start_date, end_date): De dónde vienen las reservas (Booking, Airbnb, Directo, etc.)
- get_parking_status(start_date, end_date): Uso del estacionamiento
- get_revenue_summary(period, custom_start, custom_end): Ingresos totales por período (hoy/semana/mes/año/custom)

💰 CAJA Y PAGOS:
- consultar_caja(): Estado de sesiones de caja abiertas, balance, movimientos de efectivo
- resumen_ingresos_por_metodo(period, custom_start, custom_end): Ingresos desglosados por método de pago (EFECTIVO, TRANSFERENCIA, POS)

GUÍA DE DECISIÓN:
- "¿Cuándo llega X?" → search_reservation
- "¿Hay habitaciones para mañana?" → check_availability
- "¿Cuánto cuesta 3 noches?" → calculate_price
- "Dame un resumen" → get_today_summary
- "¿Cómo estuvo la ocupación en marzo?" → get_occupancy_for_month
- "¿Cuál habitación rinde más?" → get_room_performance
- "¿De dónde vienen las reservas?" → get_booking_sources
- "¿Hay lugar en el estacionamiento?" → get_parking_status
- "Reservas de esta semana" → get_reservations_report
- "¿Cuánto facturamos este mes?" → get_revenue_summary
- "¿Cuánto hay en caja?" → consultar_caja
- "¿Cuánto se cobró por transferencia?" → resumen_ingresos_por_metodo
- "Hola" → Saludo amable sin herramientas"""


# ==========================================
# CORE AGENT FUNCTION WITH RETRY
# ==========================================

# Define retryable exceptions - HTTP 429 (rate limit) and 503 (service unavailable)
class RetryableAPIError(Exception):
    """Custom exception for retryable API errors."""
    pass


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(RetryableAPIError),
    reraise=True
)
def call_gemini_api(user_query: str, config: types.GenerateContentConfig):
    """
    Call Gemini API with retry logic for transient failures.
    
    Retries on:
    - Rate limit errors (429)
    - Service unavailable (503)
    - Connection errors
    
    Args:
        user_query: Sanitized user query
        config: Gemini generation config
        
    Returns:
        Gemini response object
    """
    try:
        return client.models.generate_content(
            model=MODEL_NAME,
            contents=user_query,
            config=config,
        )
    except Exception as e:
        error_str = str(e).lower()
        # Check if this is a retryable error
        if any(code in error_str for code in ['429', '503', 'rate limit', 'overloaded', 'unavailable']):
            logger.warning(f"Retryable Gemini API error: {e}")
            raise RetryableAPIError(str(e)) from e
        # Non-retryable error - raise immediately
        raise


async def process_query(user_query: str) -> tuple[str, list[str]]:
    """
    Process a user query using Gemini with automatic function calling.
    
    The SDK handles the entire tool calling loop automatically:
    1. Model receives query + tool definitions
    2. Model decides which tool(s) to call
    3. SDK executes the Python function locally
    4. SDK sends result back to model
    5. Model generates final response
    
    Includes retry logic for transient API failures.
    
    Args:
        user_query: The user's question or request
        
    Returns:
        Tuple of (response_text, list_of_tools_used)
    """
    if client is None:
        raise RuntimeError("Gemini client not initialized. Check GOOGLE_API_KEY.")
    
    # Sanitize input
    clean_query = sanitize_user_query(user_query)
    if not clean_query:
        return "Por favor, ingresa una consulta válida.", ["direct"]
    
    tools_used = []
    
    try:
        # Configure the request with tools and system instruction
        config = types.GenerateContentConfig(
            system_instruction=get_system_instruction(),
            tools=TOOLS_LIST,  # Pass Python functions directly
            temperature=0.3,  # Low temperature for precision
        )
        
        # Make the request with retry logic
        response = call_gemini_api(clean_query, config)
        
        # Extract tools used from the response (if available)
        if hasattr(response, 'candidates') and response.candidates:
            for candidate in response.candidates:
                if hasattr(candidate, 'content') and candidate.content:
                    for part in candidate.content.parts:
                        if hasattr(part, 'function_call') and part.function_call:
                            tools_used.append(part.function_call.name)
        
        # Get the text response
        response_text = response.text if hasattr(response, 'text') else str(response)
        
        # Clean up response (remove any thinking tags if present)
        if "<think>" in response_text:
            response_text = re.sub(r'<think>.*?</think>', '', response_text, flags=re.DOTALL)
        
        return response_text.strip(), list(set(tools_used)) if tools_used else ["direct"]
        
    except RetryableAPIError as e:
        logger.error(f"Gemini API exhausted retries: {e}")
        return FALLBACK_RESPONSE, ["error"]
    except Exception as e:
        logger.error(f"Gemini API error: {e}")
        raise


# ==========================================
# ENDPOINTS
# ==========================================

@router.post(
    "/query",
    response_model=AgentQueryResponse,
    summary="Query AI Agent (Gemini 2.5 Flash)",
    description="Consulta al agente con función calling automático. Requiere autenticación."
)
async def query_agent(
    request: AgentQueryRequest,
    current_user: User = Depends(get_current_user)  # 🔒 Protected
):
    """
    Query the AI agent using Gemini 2.5 Flash with automatic function calling.
    Requires valid JWT authentication.
    """
    try:
        response_text, tools_used = await process_query(request.prompt)
        
        return AgentQueryResponse(
            response=response_text,
            model=MODEL_NAME,
            tools_used=tools_used,
            status="success"
        )
        
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="El agente no esta disponible. Intente mas tarde."
        )
    except Exception as e:
        logger.error(f"Agent query error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al procesar la consulta. Por favor intente de nuevo."
        )


@router.get(
    "/status",
    summary="Check AI Agent Status"
)
async def check_agent_status():
    """Check if agent is available."""
    if client is None:
        return {
            "status": "offline",
            "model": MODEL_NAME,
            "error": "Servicio de IA no disponible."
        }
    
    try:
        # Simple test call
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents="Responde solo: ok",
            config=types.GenerateContentConfig(
                temperature=0,
                max_output_tokens=10
            )
        )
        
        return {
            "status": "online",
            "model": MODEL_NAME,
            "mode": "gemini_function_calling",
            "reliability": "retry_enabled",
            "tools_available": [f.__name__ for f in TOOLS_LIST]
        }
    except Exception as e:
        return {
            "status": "offline",
            "model": MODEL_NAME,
            "error": "Error al verificar el estado del agente"
        }


@router.get(
    "/tools",
    summary="List Available Tools"
)
def list_tools():
    """List all tools available to the agent."""
    return {
        "tools": [
            {
                "name": f.__name__,
                "description": f.__doc__.split('\n')[1].strip() if f.__doc__ else "No description"
            }
            for f in TOOLS_LIST
        ]
    }
