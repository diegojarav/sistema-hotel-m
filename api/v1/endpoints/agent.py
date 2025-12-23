"""
Hotel Munich API - AI Agent Endpoints
======================================

RAG-enabled AI agent with Context Injection.
Queries the database before LLM calls to provide real data.
"""

from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel, Field
from typing import Optional
from sqlalchemy.orm import Session
from datetime import date, datetime, timedelta

# LangChain Ollama integration
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, SystemMessage

# Import from root - Hybrid Monolith
from api.deps import get_db
from database import Reservation, CheckIn, Room
from services import ReservationService

router = APIRouter()


# ==========================================
# CONFIGURATION
# ==========================================

OLLAMA_BASE_URL = "http://localhost:11434"
MODEL_NAME = "qwen3-custom"

# System instruction with role definition
SYSTEM_INSTRUCTION = """Eres el asistente inteligente del Hotel Munich, un hotel de 14 habitaciones.
Tu rol es responder consultas sobre reservas, huéspedes, habitaciones y ocupación.
REGLAS:
1. Responde SOLO con la información que te proporciono en el CONTEXTO.
2. Si la información no está en el contexto, di "No tengo esa información disponible".
3. Sé conciso y directo.
4. Responde en español."""

# Initialize LLM with anti-repetition settings
llm = ChatOllama(
    base_url=OLLAMA_BASE_URL,
    model=MODEL_NAME,
    temperature=0.2,        # Very low for factual responses
    num_ctx=4096,           # Larger context for data
    num_predict=100,        # Very short responses
    repeat_penalty=1.8,     # Strong penalty for repetition
    stop=["\\n\\n", "¿Deseas", "CONSULTA", "==="],  # Stop sequences
    timeout=120,
)


# ==========================================
# SCHEMAS
# ==========================================

class AgentQueryRequest(BaseModel):
    prompt: str = Field(..., min_length=1, description="Consulta para el agente")
    context: Optional[str] = Field(default=None, description="Contexto adicional")


class AgentQueryResponse(BaseModel):
    response: str
    model: str
    status: str = "success"
    context_size: int = 0


# ==========================================
# CONTEXT BUILDER (RAG)
# ==========================================

def build_hotel_context(db: Session) -> str:
    """
    Build comprehensive context from database for RAG.
    Queries all relevant data to inject into the LLM prompt.
    """
    today = date.today()
    context_parts = []
    
    # 1. OCCUPANCY SUMMARY
    summary = ReservationService.get_today_summary(db)
    context_parts.append(f"""
## RESUMEN DE HOY ({today.strftime('%d/%m/%Y')}):
- Habitaciones ocupadas: {summary.ocupadas} de 14
- Habitaciones libres: {summary.libres}
- Llegadas hoy: {summary.llegadas_hoy}
- Salidas hoy: {summary.salidas_hoy}
- Porcentaje ocupación: {summary.porcentaje_ocupacion}%""")
    
    # 2. ROOM STATUS
    rooms = db.query(Room).all()
    room_list = [f"  - {r.id}: {r.type or 'Standard'}" for r in sorted(rooms, key=lambda x: x.id)]
    context_parts.append(f"""
## HABITACIONES DISPONIBLES:
Pisos 2 y 3 (21-28, 31-36):
{chr(10).join(room_list)}""")
    
    # 3. ACTIVE RESERVATIONS (confirmed, not cancelled)
    active_reservations = db.query(Reservation).filter(
        Reservation.status.in_(["Confirmada", "Check-In"]),
        Reservation.check_in_date >= today - timedelta(days=30)
    ).order_by(Reservation.check_in_date.desc()).limit(20).all()
    
    if active_reservations:
        res_lines = []
        for r in active_reservations:
            checkout = r.check_in_date + timedelta(days=r.stay_days) if r.check_in_date else None
            res_lines.append(
                f"  - ID:{r.id} | Hab:{r.room_id} | {r.guest_name} | "
                f"Entrada:{r.check_in_date} | Salida:{checkout} | Estado:{r.status}"
            )
        context_parts.append(f"""
## RESERVAS ACTIVAS (últimas 20):
{chr(10).join(res_lines)}""")
    else:
        context_parts.append("\n## RESERVAS ACTIVAS: Ninguna")
    
    # 4. RECENT CHECK-INS (fichas de huéspedes)
    recent_checkins = db.query(CheckIn).order_by(CheckIn.created_at.desc()).limit(15).all()
    
    if recent_checkins:
        checkin_lines = []
        for c in recent_checkins:
            checkin_lines.append(
                f"  - Hab:{c.room_id} | {c.last_name}, {c.first_name} | "
                f"Doc:{c.document_number} | País:{c.country} | Fecha:{c.created_at}"
            )
        context_parts.append(f"""
## CHECK-INS RECIENTES (últimos 15):
{chr(10).join(checkin_lines)}""")
    else:
        context_parts.append("\n## CHECK-INS RECIENTES: Ninguno")
    
    # 5. UPCOMING ARRIVALS (next 7 days)
    next_week = today + timedelta(days=7)
    upcoming = db.query(Reservation).filter(
        Reservation.status == "Confirmada",
        Reservation.check_in_date >= today,
        Reservation.check_in_date <= next_week
    ).order_by(Reservation.check_in_date).all()
    
    if upcoming:
        upcoming_lines = [
            f"  - {r.check_in_date}: {r.guest_name} (Hab:{r.room_id})"
            for r in upcoming
        ]
        context_parts.append(f"""
## PRÓXIMAS LLEGADAS (7 días):
{chr(10).join(upcoming_lines)}""")
    
    # 6. TODAY'S ROOM STATUS
    daily_status = ReservationService.get_daily_status(db, today)
    occupied_rooms = [s for s in daily_status if s["status"] == "OCUPADA"]
    free_rooms = [s for s in daily_status if s["status"] == "Libre"]
    
    if occupied_rooms:
        occ_lines = [f"  - {s['room_id']}: {s['huesped']}" for s in occupied_rooms]
        context_parts.append(f"""
## HABITACIONES OCUPADAS HOY:
{chr(10).join(occ_lines)}""")
    
    if free_rooms:
        free_ids = [s['room_id'] for s in free_rooms]
        context_parts.append(f"""
## HABITACIONES LIBRES HOY: {', '.join(free_ids)}""")
    
    return "\n".join(context_parts)


# ==========================================
# ENDPOINTS
# ==========================================

@router.post(
    "/query",
    response_model=AgentQueryResponse,
    summary="Query AI Agent (RAG)",
    description="Consulta al asistente con acceso a datos reales del hotel."
)
async def query_agent(
    request: AgentQueryRequest,
    db: Session = Depends(get_db)
):
    """
    RAG-enabled query: fetches real data from DB before calling LLM.
    """
    try:
        # BUILD CONTEXT FROM DATABASE (RAG step)
        hotel_context = build_hotel_context(db)
        
        # Combine: system + context + user query
        full_prompt = f"""{SYSTEM_INSTRUCTION}

=== CONTEXTO DEL HOTEL (DATOS REALES) ===
{hotel_context}
=== FIN CONTEXTO ===

CONSULTA DEL USUARIO: {request.prompt}

RESPUESTA:"""

        messages = [HumanMessage(content=full_prompt)]
        
        # Call LLM with real context
        response = await llm.ainvoke(messages)
        
        return AgentQueryResponse(
            response=response.content.strip(),
            model=MODEL_NAME,
            status="success",
            context_size=len(hotel_context)
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"El cerebro de IA está desconectado. Error: {str(e)}"
        )


@router.get(
    "/status",
    summary="Check AI Agent Status"
)
async def check_agent_status():
    """Check if Ollama is available."""
    try:
        test = [HumanMessage(content="ok")]
        await llm.ainvoke(test)
        return {"status": "online", "model": MODEL_NAME, "rag": "enabled"}
    except Exception:
        return {"status": "offline", "model": MODEL_NAME, "rag": "enabled"}


@router.get(
    "/context-preview",
    summary="Preview RAG Context",
    description="See what context would be injected into the LLM."
)
def preview_context(db: Session = Depends(get_db)):
    """Preview the context that gets injected into LLM prompts."""
    context = build_hotel_context(db)
    return {
        "context": context,
        "size_chars": len(context),
        "approx_tokens": len(context) // 4
    }
