/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./src/**/*.{ts,tsx}'],
  theme: {
    fontFamily: {
      display: ['var(--font-display)', 'sans-serif'],
      body: ['var(--font-body)', 'sans-serif'],
      mono: ['var(--font-mono)', 'monospace'],
    },
    fontSize: {
      '2xs': ['11px', { lineHeight: '16px' }],
      'xs': ['12px', { lineHeight: '16px' }],
      'sm': ['13px', { lineHeight: '20px' }],
      'base': ['14px', { lineHeight: '20px' }],
      'lg': ['16px', { lineHeight: '24px' }],
      'xl': ['20px', { lineHeight: '28px' }],
      '2xl': ['24px', { lineHeight: '32px' }],
      '3xl': ['32px', { lineHeight: '40px' }],
    },
    extend: {
      colors: {
        void: '#05050A',
        base: '#09090F',
        surface: '#0F0F17',
        elevated: '#161622',
        overlay: '#1C1C2A',
        border: {
          sub: '#16161F',
          DEFAULT: '#1E1E2E',
          em: '#2C2C42',
          hover: '#3A3A52',
        },
        txt: {
          1: '#EEEEF5',
          2: '#8888A8',
          3: '#4A4A62',
          4: '#2E2E42',
        },
        accent: {
          DEFAULT: '#5B6AF5',
          hover: '#7B89F7',
          glow: 'rgba(91,106,245,0.18)',
        },
        success: {
          DEFAULT: '#4ADE80',
          bg: 'rgba(22,163,74,0.12)',
        },
        warning: {
          DEFAULT: '#FBB53A',
          bg: 'rgba(217,119,6,0.12)',
        },
        danger: {
          DEFAULT: '#F87171',
          bg: 'rgba(220,38,38,0.12)',
        },
        info: {
          DEFAULT: '#38BDF8',
          bg: 'rgba(2,132,199,0.12)',
        },
        purple: {
          DEFAULT: '#C084FC',
          bg: 'rgba(192,132,252,0.10)',
        },
      },
      spacing: {
        '4.5': '18px',
        '13': '52px',
        '15': '60px',
        '18': '72px',
        '55': '220px',
        '120': '480px',
      },
      animation: {
        'pulse-status': 'pulse-status 2s ease-in-out infinite',
        'slide-in-right': 'slide-in-right 200ms ease-out',
        'scale-in': 'scale-in 150ms ease-out',
        'fade-in': 'fade-in 150ms ease-out',
      },
      keyframes: {
        'pulse-status': {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.4' },
        },
        'slide-in-right': {
          from: { transform: 'translateX(480px)' },
          to: { transform: 'translateX(0)' },
        },
        'scale-in': {
          from: { transform: 'scale(0.96)', opacity: '0' },
          to: { transform: 'scale(1)', opacity: '1' },
        },
        'fade-in': {
          from: { opacity: '0' },
          to: { opacity: '1' },
        },
      },
      transitionDuration: {
        '80': '80ms',
      },
    },
  },
  plugins: [],
};
