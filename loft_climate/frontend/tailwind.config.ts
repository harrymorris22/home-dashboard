import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        glass: {
          surface: "rgb(255 255 255 / 0.05)",
          border: "rgb(255 255 255 / 0.10)",
        },
      },
      backdropBlur: {
        xl: "24px",
        "2xl": "40px",
      },
      boxShadow: {
        glass: "0 12px 40px -12px rgba(0, 0, 0, 0.6)",
      },
    },
  },
  plugins: [],
} satisfies Config;
