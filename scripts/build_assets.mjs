// Prepara gli asset del front-end in locale, così l'app non dipende da CDN esterne:
//   - src/web/vendor/tailwind.css   (stili Tailwind precompilati, solo le classi usate in index.html)
//   - src/web/vendor/chart.umd.js   (Chart.js, per i grafici)
//
// Uso (serve Node.js 18+ e connessione internet; dalla radice del progetto):
//     node scripts/build_assets.mjs
// Poi fai commit di src/web/vendor/. Il server usa questi file da solo non appena esistono.
// Va rieseguito quando aggiungi nuove classi Tailwind a index.html.
import { execFileSync } from "node:child_process";
import { copyFileSync, mkdirSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const TAILWIND_VERSION = "3.4.17";
const CHARTJS_VERSION = "4.4.7";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const outDir = join(root, "src", "web", "vendor");
const work = mkdtempSync(join(tmpdir(), "gymtracker-assets-"));
const npm = process.platform === "win32" ? "npm.cmd" : "npm";

// Comandi e argomenti sono costanti o percorsi calcolati qui: nessun input esterno nella riga di comando.
// useShell serve solo per npm su Windows (npm.cmd non si può avviare senza shell). In quel caso ogni
// argomento va tra virgolette, altrimenti i percorsi con spazi (es. "C:\Program Files\nodejs") si spezzano.
function run(cmd, args, { useShell = false } = {}) {
  const finalArgs = useShell ? args.map((a) => `"${a}"`) : args;
  execFileSync(cmd, finalArgs, { cwd: root, stdio: "inherit", shell: useShell });
}

try {
  mkdirSync(outDir, { recursive: true });

  console.log(`\n== Scarico Chart.js ${CHARTJS_VERSION} e Tailwind ${TAILWIND_VERSION} (cartella temporanea)`);
  run(npm, ["install", "--prefix", work, "--no-audit", "--no-fund", "--no-save",
            `chart.js@${CHARTJS_VERSION}`, `tailwindcss@${TAILWIND_VERSION}`],
      { useShell: process.platform === "win32" });

  console.log("\n== Copio Chart.js");
  const chartDir = join(work, "node_modules", "chart.js");
  copyFileSync(join(chartDir, "dist", "chart.umd.js"), join(outDir, "chart.umd.js"));
  copyFileSync(join(chartDir, "LICENSE.md"), join(outDir, "chart.js.LICENSE.md"));

  console.log("\n== Compilo Tailwind");
  run(process.execPath, [
    join(work, "node_modules", "tailwindcss", "lib", "cli.js"),
    "-c", join(root, "tools", "tailwind.config.js"),
    "-i", join(root, "tools", "tailwind-input.css"),
    "-o", join(outDir, "tailwind.css"),
    "--minify",
  ]);

  console.log(`\nFatto. File creati in ${outDir}\nOra: git add src/web/vendor && git commit`);
} finally {
  rmSync(work, { recursive: true, force: true });
}
