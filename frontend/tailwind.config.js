/** Paleta TechSupport S.A.: niebla, azul acero y esmeralda */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        niebla: { DEFAULT: '#EEF2F5', 200: '#E2E8EE', 300: '#D5DEE6', 400: '#B8C6D3' },
        acero: { DEFAULT: '#1E3A5F', 700: '#18304F', 800: '#132740', 900: '#0E1D30', 500: '#2F527F', 300: '#6F8BAE', 100: '#DCE5EF' },
        esmeralda: { DEFAULT: '#10B981', 600: '#059669', 700: '#047857', 100: '#D1FAE5', 50: '#ECFDF5' },
        tinta: '#16263B',
      },
      fontFamily: {
        sans: ['"IBM Plex Sans"', 'system-ui', 'sans-serif'],
        mono: ['"IBM Plex Mono"', 'ui-monospace', 'monospace'],
      },
    },
  },
  plugins: [],
}
