import streamlit as st


def inject_custom_css():
    """Inyecta CSS para el calendario nativo y tarjetas móviles."""
    st.markdown("""
    <style>
    /* Calendario Nativo */
    .calendar-header {
        display: flex;
        justify-content: space-around;
        background: linear-gradient(135deg, #1e3a5f, #2d5a87);
        padding: 8px;
        border-radius: 8px 8px 0 0;
        margin-bottom: 2px;
    }
    .calendar-header span {
        color: white;
        font-weight: bold;
        font-size: 12px;
        width: 14%;
        text-align: center;
    }
    .calendar-row {
        display: flex;
        justify-content: space-around;
        margin-bottom: 2px;
    }
    .day-circle {
        width: 38px;
        height: 38px;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 14px;
        font-weight: 500;
        margin: 2px auto;
        cursor: pointer;
        transition: all 0.2s ease;
    }
    .day-circle:hover {
        transform: scale(1.1);
        box-shadow: 0 2px 8px rgba(0,0,0,0.3);
    }
    .status-free {
        background: transparent;
        color: #aaa;
        border: 1px dashed #555;
    }
    .status-medium {
        background: rgba(76, 175, 80, 0.3);
        color: #4CAF50;
        border: 2px solid #4CAF50;
        font-weight: bold;
    }
    .status-high {
        background: rgba(244, 67, 54, 0.3);
        color: #F44336;
        border: 2px solid #F44336;
        font-weight: bold;
    }
    .status-today {
        box-shadow: 0 0 0 3px #2196F3, 0 0 10px rgba(33, 150, 243, 0.5);
    }
    .day-empty {
        width: 38px;
        height: 38px;
        margin: 2px auto;
    }

    /* Leyenda del Calendario */
    .calendar-legend {
        display: flex;
        justify-content: center;
        gap: 20px;
        padding: 10px;
        margin-top: 10px;
    }
    .legend-item {
        display: flex;
        align-items: center;
        gap: 6px;
        font-size: 12px;
        color: #888;
    }
    .legend-dot {
        width: 12px;
        height: 12px;
        border-radius: 50%;
    }
    .legend-dot.free { background: transparent; border: 1px dashed #555; }
    .legend-dot.medium { background: rgba(76, 175, 80, 0.3); border: 2px solid #4CAF50; }
    .legend-dot.high { background: rgba(244, 67, 54, 0.3); border: 2px solid #F44336; }
    </style>
    """, unsafe_allow_html=True)
