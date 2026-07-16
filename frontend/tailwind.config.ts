import type { Config } from 'tailwindcss'

/**
 * 墨韵朱砂 (Ink & Cinnabar) design tokens.
 * 暖墨黑底 + 朱砂红强调 + 暖金点缀 + 米白稿纸阅读面。
 * 所有颜色以 CSS 变量暴露，主题层可在 index.css 覆盖。
 */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        // 墨 — warm near-black backgrounds, ascending surfaces
        ink: {
          950: '#141210',
          900: '#1a1613',
          800: '#211c18',
          700: '#2b2520',
          600: '#3a322b',
          500: '#4d433a',
        },
        // 宣 — warm paper / parchment reading surfaces
        paper: {
          50: '#f7f1e6',
          100: '#f1e8d8',
          200: '#e6d9c2',
          300: '#d4c3a5',
        },
        // 朱砂 — cinnabar red, the signature accent
        cinnabar: {
          50: '#fbeae6',
          300: '#e8836f',
          400: '#e0654d',
          500: '#d8452f',
          600: '#c0341f',
          700: '#9c2817',
        },
        // 金 — warm gold, secondary accent for highlights & foreshadowing
        gold: {
          300: '#e0c977',
          400: '#d4b355',
          500: '#c9a227',
          600: '#a8851c',
        },
        // 墨绿 — jade, used for "done/confirmed" states (warmer than emerald)
        jade: {
          400: '#7fae8f',
          500: '#5c8f6e',
          600: '#47765a',
        },
        // primary alias kept so any stray primary-* utils resolve to cinnabar
        primary: {
          50: '#fbeae6',
          100: '#f7d5cc',
          200: '#efab99',
          300: '#e8836f',
          400: '#e0654d',
          500: '#d8452f',
          600: '#c0341f',
          700: '#9c2817',
          800: '#7a1f12',
          900: '#5c170d',
        },
      },
      fontFamily: {
        display: ['Fraunces', 'Noto Serif SC', 'serif'],
        serif: ['"Noto Serif SC"', 'Fraunces', 'Georgia', 'serif'],
        sans: ['"Noto Sans SC"', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono: ['"IBM Plex Mono"', 'ui-monospace', 'monospace'],
      },
      boxShadow: {
        seal: '0 2px 0 0 rgba(156, 40, 23, 0.45)',
        lift: '0 12px 40px -12px rgba(0, 0, 0, 0.6)',
        paper: '0 1px 0 rgba(255,255,255,0.04), 0 18px 50px -20px rgba(0,0,0,0.7)',
      },
      keyframes: {
        'fade-up': {
          '0%': { opacity: '0', transform: 'translateY(10px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        'fade-in': {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        'scale-in': {
          '0%': { opacity: '0', transform: 'scale(0.96)' },
          '100%': { opacity: '1', transform: 'scale(1)' },
        },
        'toast-in': {
          '0%': { opacity: '0', transform: 'translateX(16px)' },
          '100%': { opacity: '1', transform: 'translateX(0)' },
        },
        'ink-pulse': {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.3' },
        },
      },
      animation: {
        'fade-up': 'fade-up 0.5s cubic-bezier(0.16, 1, 0.3, 1) both',
        'fade-in': 'fade-in 0.4s ease both',
        'scale-in': 'scale-in 0.22s cubic-bezier(0.16, 1, 0.3, 1) both',
        'toast-in': 'toast-in 0.3s cubic-bezier(0.16, 1, 0.3, 1) both',
        'ink-pulse': 'ink-pulse 1.2s ease-in-out infinite',
      },
    },
  },
  plugins: [],
} satisfies Config
