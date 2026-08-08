import { ImageResponse } from "next/og";

export const dynamic = "force-static";
export const alt = "TokenTelemetry — Local observability for coding agents and Hermes Agent";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default function OpenGraphImage() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          padding: "80px",
          background:
            "radial-gradient(circle at 20% 10%, #1e3a8a55 0%, transparent 60%), radial-gradient(circle at 90% 90%, #06402855 0%, transparent 60%), #020617",
          color: "#ffffff",
          fontFamily: "system-ui, -apple-system, sans-serif",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "20px" }}>
            <div
              style={{
                width: "72px",
                height: "72px",
                background: "#2563eb",
                borderRadius: "16px",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              <svg width="44" height="44" viewBox="0 0 32 32" fill="none">
                <path
                  d="M27 16h-2.48a2 2 0 0 0-1.93 1.46l-2.35 8.36a.5.5 0 0 1-.96 0L14.24 6.18a.5.5 0 0 0-.96 0l-2.35 8.36A2 2 0 0 1 9 16H7"
                  stroke="#ffffff"
                  strokeWidth="2.6"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </div>
            <div style={{ display: "flex", fontSize: "44px", fontWeight: 900, letterSpacing: "-1px" }}>
              TokenTelemetry
            </div>
          </div>

          {/* Hermes Agent chip - signals the new autonomous-agent support */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "12px",
              padding: "10px 18px",
              borderRadius: "999px",
              background: "rgba(234, 179, 8, 0.12)",
              border: "2px solid rgba(234, 179, 8, 0.4)",
              color: "#fde047",
              fontSize: "22px",
              fontWeight: 600,
            }}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#fde047" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
              <line x1="12" y1="3" x2="12" y2="21" />
              <path d="M8 5L4.5 2.5L6.5 6" />
              <path d="M16 5L19.5 2.5L17.5 6" />
              <path d="M9 9C7.5 11 7.5 13 9 15" />
              <path d="M15 9C16.5 11 16.5 13 15 15" />
            </svg>
            <span style={{ display: "flex" }}>NEW · Hermes Agent</span>
          </div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: "24px" }}>
          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              fontSize: "76px",
              fontWeight: 900,
              lineHeight: 1.1,
              letterSpacing: "-2px",
              maxWidth: "1040px",
              gap: "16px",
            }}
          >
            <span style={{ color: "#ffffff" }}>See exactly what your</span>
            <span style={{ color: "#60a5fa" }}>AI agents</span>
            <span style={{ color: "#ffffff" }}>cost, think, and do.</span>
          </div>
          <div style={{ display: "flex", fontSize: "28px", color: "#94a3b8", fontWeight: 500 }}>
            <span style={{ color: "#fde047", fontWeight: 600 }}>Hermes Agent</span>
            <span style={{ display: "flex", color: "#94a3b8" }}>&nbsp;· Claude · Codex · Gemini · Cursor · Copilot · and 11 more.</span>
          </div>
        </div>

        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            color: "#64748b",
            fontSize: "22px",
            fontFamily: "ui-monospace, monospace",
          }}
        >
          <div style={{ display: "flex" }}>tokentelemetry.com</div>
          <div style={{ display: "flex", gap: "20px" }}>
            <span style={{ display: "flex" }}>100% local</span>
            <span style={{ display: "flex" }}>·</span>
            <span style={{ display: "flex" }}>MIT</span>
            <span style={{ display: "flex" }}>·</span>
            <span style={{ display: "flex" }}>open source</span>
          </div>
        </div>
      </div>
    ),
    size,
  );
}
