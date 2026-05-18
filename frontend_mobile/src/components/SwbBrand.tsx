/**
 * SwbBrand — fixed branding footer that appears on every page.
 *
 * Rendered once inside the root <body> in app/layout.tsx so it shows up on
 * every route, including login, dashboards, and modals. Marked as a Server
 * Component (no "use client" directive) — pure presentational, no hooks.
 *
 * Design spec:
 *   - position: fixed bottom (cannot be hidden by scrolling)
 *   - dark background matching the app's nav theme
 *   - gold text (#C9A84C — SWB brand color), 11px, letter-spaced
 *   - subtle, not a watermark
 *   - pointer-events: none so it never blocks taps on underlying UI
 *
 * Bottom-padding is added globally in app/globals.css (.swb-pad-host
 * pattern) so the footer never covers the last button on any page.
 */
export default function SwbBrand() {
    return (
        <div
            style={{
                position: "fixed",
                bottom: 0,
                left: 0,
                width: "100%",
                textAlign: "center",
                padding: "6px 0",
                background: "#1a1a2e",
                borderTop: "1px solid #2a2a4a",
                zIndex: 9999,
                fontSize: "11px",
                color: "#C9A84C",
                letterSpacing: "0.5px",
                fontFamily:
                    "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
                pointerEvents: "none",
            }}
        >
            ⚡ SWB — Sahara World Business
        </div>
    );
}
