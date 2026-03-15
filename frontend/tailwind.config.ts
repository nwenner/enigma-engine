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
          DEFAULT: "#0c0e12",
          surface: "#111318",
          elevated: "#1a1e2a",
          border: "#2d3347",
        },
      },
      fontFamily: {
        diablo: ["Cinzel", "Georgia", "serif"],
      },
      keyframes: {
        fadeIn: {
          "0%": { opacity: "0", transform: "translateY(6px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        glowPulse: {
          "0%, 100%": { boxShadow: "0 0 4px rgba(200,168,75,0.15)" },
          "50%": { boxShadow: "0 0 18px rgba(200,168,75,0.45), 0 0 4px rgba(200,168,75,0.15)" },
        },
        navSlide: {
          "0%": { opacity: "0", transform: "translateX(-4px)" },
          "100%": { opacity: "1", transform: "translateX(0)" },
        },
        shimmer: {
          "0%": { backgroundPosition: "-300% center" },
          "100%": { backgroundPosition: "300% center" },
        },
        stampIn: {
          "0%": { opacity: "0", transform: "scale(1.6)" },
          "55%": { opacity: "1", transform: "scale(0.9)" },
          "100%": { opacity: "1", transform: "scale(1)" },
        },
      },
      animation: {
        fadeIn: "fadeIn 0.25s ease-out",
        glowPulse: "glowPulse 2.5s ease-in-out infinite",
        navSlide: "navSlide 0.2s ease-out",
        shimmer: "shimmer 3s linear infinite",
        glowPulseOnce: "glowPulse 2.8s ease-in-out 1",
        stampIn: "stampIn 0.5s cubic-bezier(0.34, 1.56, 0.64, 1) both",
      },
    },
  },
  plugins: [],
} satisfies Config;
