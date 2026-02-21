// Tailwind config shim for monorepo / tooling that resolves config paths
// relative to the repo root instead of `web/`.
//
// Source of truth lives at `web/tailwind.config.js`.
module.exports = require("./web/tailwind.config.js");

