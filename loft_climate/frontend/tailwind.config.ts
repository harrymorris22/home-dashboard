import type { Config } from "tailwindcss";

// Tokens from /design.md (sports-hud, strict adherence).
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        primary: "#0E1016",     // headlines + body text
        secondary: "#5B6270",   // borders, captions, metadata
        tertiary: "#00E676",    // single interaction accent. reserve.
        neutral: "#F1F3F5",     // page foundation
        surface: "#FFFFFF",     // card backgrounds
      },
      fontFamily: {
        // Archivo + Archivo Black are loaded via Google Fonts in index.html.
        sans: ['Archivo', 'system-ui', 'sans-serif'],
        display: ['"Archivo Black"', 'Archivo', 'system-ui', 'sans-serif'],
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
        // Override Tailwind's defaults so stale rounded-2xl etc. degrade safely.
        xl: "6px",
        "2xl": "6px",
        "3xl": "6px",
        full: "9999px",
      },
      letterSpacing: {
        label: "0.14em",
      },
    },
  },
  plugins: [],
} satisfies Config;
