"""Pagina principale: usa gli asset locali (src/web/vendor/) se esistono, altrimenti ricade sulle CDN."""
from pathlib import Path

VENDOR_START = "<!--VENDOR-START-->"
VENDOR_END = "<!--VENDOR-END-->"
CSS_FILE = "tailwind.css"
CHART_FILE = "chart.umd.js"


def render_index(web_dir: Path) -> str:
    """
    index.html contiene tra i marcatori VENDOR-START/END i tag che caricano Tailwind e Chart.js dalle CDN.
    Se i file locali (creati con scripts/build_assets.mjs) esistono entrambi, quel blocco viene sostituito
    con i tag locali: l'app funziona senza dipendere da siti esterni. Se ne manca anche uno, resta il blocco CDN.
    """
    html = (web_dir / "index.html").read_text(encoding="utf-8")
    css, chart = web_dir / "vendor" / CSS_FILE, web_dir / "vendor" / CHART_FILE
    if not (css.is_file() and chart.is_file()):
        return html

    start, end = html.find(VENDOR_START), html.find(VENDOR_END)
    if start == -1 or end == -1 or end < start:
        return html

    # ?v=<data di modifica>: quando rigeneri i file, i browser scaricano la versione nuova
    local = (
        f'<link rel="stylesheet" href="/static/vendor/{CSS_FILE}?v={int(css.stat().st_mtime)}" />\n'
        f'  <script src="/static/vendor/{CHART_FILE}?v={int(chart.stat().st_mtime)}"></script>'
    )
    return html[:start] + local + html[end + len(VENDOR_END):]
