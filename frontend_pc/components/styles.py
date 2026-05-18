import streamlit as st


def inject_swb_brand():
    """Inject the SWB (Sahara World Business) branding footer.

    Fixed-position badge that appears on every page. Streamlit's multipage
    architecture runs each page as an independent script, so this helper
    must be called from EVERY page (app.py + each file in pages/) — the
    main DOM is reset on every navigation.

    Style: gold (#C9A84C) on dark (#1a1a2e), 11px, fixed bottom, z-index
    above all Streamlit chrome. Adds 40px of bottom padding to
    .block-container so the badge never overlaps the last UI element on
    long pages.
    """
    st.markdown(
        """
        <style>
        .swb-brand {
            position: fixed;
            bottom: 0;
            left: 0;
            width: 100%;
            text-align: center;
            padding: 6px 0;
            background: #1a1a2e;
            border-top: 1px solid #2a2a4a;
            z-index: 9999;
            font-size: 11px;
            color: #C9A84C;
            letter-spacing: 0.5px;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            pointer-events: none;
        }
        /* Push page content up so the fixed footer doesn't overlap the
         * last element on any page. 40px = 6+6 padding + 11px font +
         * 1px border + a comfortable safety margin. */
        .block-container { padding-bottom: 50px !important; }
        </style>
        <div class="swb-brand">⚡ SWB — Sahara World Business</div>
        """,
        unsafe_allow_html=True,
    )


def inject_custom_css():
    """Inyecta CSS para el calendario nativo y tarjetas móviles."""
    st.markdown("""
    <style>
    /* Calendario Nativo */
    .calendar-header {
        display: flex;
        justify-content: space-around;
        background: #f3f4f6;
        padding: 8px;
        border-radius: 8px 8px 0 0;
        margin-bottom: 2px;
        border: 1px solid #e5e7eb;
    }
    .calendar-header span {
        color: #374151;
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
        color: #9ca3af;
        border: 1px dashed #d1d5db;
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
        color: #6b7280;
    }
    .legend-dot {
        width: 12px;
        height: 12px;
        border-radius: 50%;
    }
    .legend-dot.free { background: transparent; border: 1px dashed #d1d5db; }
    .legend-dot.medium { background: rgba(76, 175, 80, 0.3); border: 2px solid #4CAF50; }
    .legend-dot.high { background: rgba(244, 67, 54, 0.3); border: 2px solid #F44336; }
    </style>
    """, unsafe_allow_html=True)
