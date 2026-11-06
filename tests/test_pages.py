from src.pages import render_index


def _site(tmp_path, with_css=True, with_chart=True):
    (tmp_path / "index.html").write_text(
        "<head>\n  <!--VENDOR-START-->\n  <script src=\"https://cdn.tailwindcss.com\"></script>\n"
        "  <!--VENDOR-END-->\n</head><body>ciao</body>", encoding="utf-8")
    (tmp_path / "vendor").mkdir()
    if with_css:
        (tmp_path / "vendor" / "tailwind.css").write_text("a{}")
    if with_chart:
        (tmp_path / "vendor" / "chart.umd.js").write_text("var Chart;")
    return tmp_path


def test_falls_back_to_cdn_without_local_files(tmp_path):
    html = render_index(_site(tmp_path, with_css=False, with_chart=False))
    assert "cdn.tailwindcss.com" in html and "/static/vendor/" not in html


def test_partial_local_files_keep_cdn(tmp_path):
    html = render_index(_site(tmp_path, with_chart=False))
    assert "cdn.tailwindcss.com" in html and "/static/vendor/" not in html


def test_uses_local_files_when_both_exist(tmp_path):
    html = render_index(_site(tmp_path))
    assert "cdn.tailwindcss.com" not in html
    assert "/static/vendor/tailwind.css?v=" in html and "/static/vendor/chart.umd.js?v=" in html
    assert "VENDOR-START" not in html and "<body>ciao</body>" in html


def test_real_index_has_markers():
    from pathlib import Path
    real = (Path(__file__).resolve().parent.parent / "src" / "web" / "index.html").read_text(encoding="utf-8")
    assert real.count("<!--VENDOR-START-->") == 1 and real.count("<!--VENDOR-END-->") == 1
