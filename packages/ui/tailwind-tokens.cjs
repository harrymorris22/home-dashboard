// Shared Tailwind theme.extend object.
// Both loft_climate and desk import this into their tailwind.config.ts.
// Single source of truth for the Sports HUD strict-adherence design tokens.

module.exports = {
  colors: {
    primary: "#0E1016",     // headlines + body text
    secondary: "#5B6270",   // borders, captions, metadata
    tertiary: "#00E676",    // single interaction accent. reserve.
    neutral: "#F1F3F5",     // page foundation
    surface: "#FFFFFF",     // card backgrounds
  },
  fontFamily: {
    // Archivo + Archivo Black loaded via Google Fonts in each app's index.html.
    sans: ["Archivo", "system-ui", "sans-serif"],
    display: ['"Archivo Black"', "Archivo", "system-ui", "sans-serif"],
  },
  fontSize: {
    display: ["4rem", { lineHeight: "1", letterSpacing: "-0.03em", fontWeight: "900" }],
    h1: ["2.25rem", { lineHeight: "1.1", fontWeight: "800" }],
    body: ["0.95rem", { lineHeight: "1.5" }],
    label: ["0.72rem", { letterSpacing: "0.14em", fontWeight: "700" }],
  },
  borderRadius: {
    sm: "2px",
    DEFAULT: "4px",
    md: "4px",
    lg: "6px",
    xl: "6px",
    "2xl": "6px",
    "3xl": "6px",
    full: "9999px",
  },
  letterSpacing: {
    label: "0.14em",
  },
};
