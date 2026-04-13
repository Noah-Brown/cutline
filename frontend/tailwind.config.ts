import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        navy: {
          50: "#f2f5fb",
          100: "#dfe6f1",
          500: "#3c557a",
          700: "#1f3558",
          900: "#0f1f3b",
        },
        cutline: {
          green: "#34d399",
          red: "#ef4444",
          yellow: "#facc15",
          gray: "#4b5563",
        },
      },
      fontFamily: {
        sans: [
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "Helvetica",
          "Arial",
          "sans-serif",
        ],
      },
    },
  },
  plugins: [],
};

export default config;
