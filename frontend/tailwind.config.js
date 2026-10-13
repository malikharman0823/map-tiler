/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    screens: {
      "small-phone": "420px",
      phone: "641px",
      tablet: "736px",
      "tablet-landscape": "834px",
      "small-desktop": "1024px",
      desktop: "1069px",
      wide: "1441px",
    },
    extend: {
      fontFamily: {
        sans: ['Inter', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
      colors: {
        primary: "#0066cc",
        "primary-focus": "#0071e3",
        "primary-on-dark": "#2997ff",
        ink: "#1d1d1f",
        body: "#1d1d1f",
        "body-on-dark": "#ffffff",
        "body-muted": "#cccccc",
        "ink-muted-80": "#333333",
        "ink-muted-48": "#7a7a7a",
        muted: "#7a7a7a",
        "divider-soft": "#f0f0f0",
        hairline: "#e0e0e0",
        canvas: "#ffffff",
        parchment: "#f5f5f7",
        "canvas-parchment": "#f5f5f7",
        pearl: "#fafafc",
        "surface-pearl": "#fafafc",
        "surface-tile-1": "#272729",
        "surface-tile-2": "#2a2a2c",
        "surface-tile-3": "#252527",
        "surface-black": "#000000",
        "surface-chip-translucent": "#d2d2d7",
        "near-black": "#272729",
      },
      borderRadius: {
        utility: "18px",
      },
      maxWidth: {
        canvas: "1440px",
      },
    },
  },
  plugins: [],
}
