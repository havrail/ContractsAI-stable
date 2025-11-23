/** @type {import('tailwindcss').Config} */
export default {
    content: [
        "./index.html",
        "./src/**/*.{js,ts,jsx,tsx}",
    ],
    theme: {
        extend: {
            colors: {
                primary: "#10B981", // Emerald 500
                secondary: "#3B82F6", // Blue 500
                dark: "#1F2937", // Gray 800
                darker: "#111827", // Gray 900
                card: "#374151", // Gray 700
            },
            fontFamily: {
                sans: ['Inter', 'sans-serif'],
            }
        },
    },
    plugins: [],
}
