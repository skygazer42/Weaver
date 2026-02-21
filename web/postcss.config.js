module.exports = {
  plugins: {
    // Turbopack/PostCSS workers sometimes resolve paths relative to the repo root.
    // Force Tailwind's scanning base to the Next.js app root (`web/`) to avoid
    // accidentally scanning the whole monorepo.
    '@tailwindcss/postcss': { base: __dirname },
    autoprefixer: {},
  },
}
