/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        background: '#0B0F19',
        surface: '#1A2332',
        primary: '#3B82F6',
        primaryHover: '#2563EB',
        textMain: '#F8FAFC',
        textMuted: '#94A3B8',
        borderLight: '#2E3B52'
      }
    },
  },
  plugins: [],
}
