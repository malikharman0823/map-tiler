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
      colors: {
        primary: "#0066cc",
        "primary-focus": "#0071e3",
        "primary-on-dark": "#2997ff",
        ink: "#1d1d1f",
        muted: "#7a7a7a",
        hairline: "#e0e0e0",
        parchment: "#f5f5f7",
        pearl: "#fafafc",
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
