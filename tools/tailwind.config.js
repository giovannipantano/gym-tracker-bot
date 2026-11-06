// Configurazione usata SOLO da scripts/build_assets.mjs per generare src/web/vendor/tailwind.css.
const path = require("path");

module.exports = {
  content: [path.join(__dirname, "..", "src", "web", "index.html")],
  theme: { extend: {} },
};
