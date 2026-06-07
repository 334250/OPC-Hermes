export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        opc: {
          bg: '#0a0a0f',
          surface: '#14141f',
          'surface-2': '#1e1e2e',
          border: '#2a2a3a',
          text: '#e4e4ec',
          'text-2': '#8888a0',
          accent: '#7c3aed',
          'accent-hover': '#6d28d9',
          success: '#22c55e',
          warning: '#f59e0b',
          error: '#ef4444',
        },
      },
      fontFamily: {
        sans: ['Geist', 'Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
      borderRadius: {
        xl: '12px',
      },
    },
  },
  plugins: [],
}
