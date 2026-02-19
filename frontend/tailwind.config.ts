import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        d2gold: {
          DEFAULT: "#c8a84b",
          light: "#e6c96a",
          dark: "#9a7a2e",
        },
        d2bg: {
          DEFAULT: "#1a1008",
          surface: "#241808",
          elevated: "#2e2010",
          border: "#4a3010",
        },
      },
    },
  },
  plugins: [],
} satisfies Config;
