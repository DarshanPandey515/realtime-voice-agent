/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        pine: '#1f3a35',
        pineDeep: '#122624',
        snow: '#f7f4ee',
        ink: '#14201f',
        sand: '#ece5d8',
        ember: '#c8553d',
        emberDark: '#a8432e',
        gold: '#c9a45c',
        ctaRed: '#DC143C',
      },
      borderWidth: {
        1: '1px',
      },
      borderRadius: {
        lg: '100px',
      },
      fontFamily: {
        display: ['Inter', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
}