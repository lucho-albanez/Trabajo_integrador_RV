#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generador de PDF vectorial en alta resolución para el Manual de Uso de ArcSim_VR,
replicando fielmente el diseño visual de docs_referencia/Manual_de_uso.pdf:
- Título principal negro en negrita + subtítulo azul (#4a86e8) "Manual de uso"
- Líneas divisorias horizontales limpias entre secciones
- Sección 1 a dos columnas (pasos numerados a la izquierda + foto vertical del portaelectrodo a la derecha)
- Sección 2 con etiquetas semánticas coloreadas para cada estado del LED RGB
- Sección 3 con recuadro centrado con borde negro fino
- Todas las imágenes embebidas en Base64 sin pérdida de calidad

Uso:
    python tools/exportar_manual_pdf.py [salida.pdf]
"""

from __future__ import annotations

import base64
import html
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MD_PATH = ROOT / "manual_de_uso.md"
DEFAULT_PDF = ROOT / "Manual_de_uso_ArcSim_VR.pdf"

LED_COLORS_HTML = {
    "Violeta / Naranja:": "#7c3aed",
    "Azul": "#2563eb",
    "Verde": "#16a34a",
    "Amarillo:": "#d97706",
    "Rojo": "#dc2626",
    "Rojo fijo + vibración intensa al 100 %:": "#b91c1c",
}


def find_browser() -> str | None:
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return shutil.which("chrome") or shutil.which("msedge")


def img_to_data_uri(rel_path: str) -> str:
    p = ROOT / rel_path.strip()
    if not p.exists():
        return ""
    mime, _ = mimetypes.guess_type(str(p))
    if not mime:
        mime = "image/jpeg" if p.suffix.lower() in (".jpg", ".jpeg") else "image/png"
    b64 = base64.b64encode(p.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def clean_tex(text: str) -> str:
    def repl(m: re.Match[str]) -> str:
        s = m.group(1)
        s = re.sub(r"\\text\{([^}]*)\}", r"\1", s)
        s = s.replace("{,}", ",")
        s = s.replace(r"^\circ", "°").replace(r"^{\circ}", "°")
        return s

    return re.sub(r"\$([^$]+)\$", repl, text)


def fmt_inline(text: str, *, color_led: bool = False) -> str:
    text = clean_tex(text)
    tokens: list[str] = []

    def stash(h: str) -> str:
        idx = len(tokens)
        tokens.append(h)
        return f"\x00T{idx}\x00"

    # Inline code inside or outside bold
    text = re.sub(r"`([^`]+)`", lambda m: stash(f"<code>{html.escape(m.group(1))}</code>"), text)
    text = html.escape(text, quote=False)

    first_bold = True

    def bold_repl(m: re.Match[str]) -> str:
        nonlocal first_bold
        inner = m.group(1)
        if color_led and first_bold:
            first_bold = False
            for k, col in LED_COLORS_HTML.items():
                if inner.strip() == k or inner.strip().startswith(k):
                    return f'<strong style="color:{col}">{inner}</strong>'
        return f"<strong>{inner}</strong>"

    text = re.sub(r"\*\*(.+?)\*\*", bold_repl, text)
    text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)

    for idx, val in enumerate(tokens):
        text = text.replace(f"\x00T{idx}\x00", val)
    return text


def build_html(md_text: str) -> str:
    lines = md_text.splitlines()
    n = len(lines)
    i = 0
    blocks: list[str] = []
    cur_h2 = ""

    while i < n:
        line = lines[i]
        s = line.strip()
        if not s:
            i += 1
            continue

        if s.startswith("# "):
            blocks.append(f"<h1>{fmt_inline(s[2:].strip())}</h1>")
            i += 1
            continue

        if s.startswith("## "):
            h2_t = s[3:].strip()
            cur_h2 = h2_t
            if h2_t.lower() == "manual de uso":
                blocks.append(f'<div class="subtitle">{fmt_inline(h2_t)}</div>')
            else:
                blocks.append(f"<h2>{fmt_inline(h2_t)}</h2>")
            i += 1
            continue

        if s.startswith("### "):
            blocks.append(f"<h3>{fmt_inline(s[4:].strip())}</h3>")
            i += 1
            continue

        if re.match(r"^-{3,}$", s):
            blocks.append("<hr>")
            i += 1
            continue

        m_img = re.match(r"^!\[([^\]]*)\]\(([^)]+)\)$", s)
        if m_img:
            uri = img_to_data_uri(m_img.group(2))
            alt = html.escape(m_img.group(1))
            i += 1
            # Si viene inmediatamente otra imagen seguida (como las dos partes del Informe en sección 7), agruparlas!
            j = i
            while j < n and not lines[j].strip():
                j += 1
            if j < n and re.match(r"^!\[([^\]]*)\]\(([^)]+)\)$", lines[j].strip()):
                m_img2 = re.match(r"^!\[([^\]]*)\]\(([^)]+)\)$", lines[j].strip())
                uri2 = img_to_data_uri(m_img2.group(2))
                alt2 = html.escape(m_img2.group(1))
                blocks.append(
                    f'<div class="fig-pair">'
                    f'<img src="{uri}" alt="{alt}">'
                    f'<img src="{uri2}" alt="{alt2}">'
                    f"</div>"
                )
                i = j + 1
            else:
                blocks.append(f'<div class="fig-center"><img src="{uri}" alt="{alt}"></div>')
            continue

        if s.startswith(">"):
            ql = []
            while i < n and lines[i].strip().startswith(">"):
                ql.append(re.sub(r"^>\s?", "", lines[i].strip()))
                i += 1
            inner = "<br>".join(fmt_inline(x) for x in ql)
            blocks.append(f'<div class="callout-box">{inner}</div>')
            continue

        m_list = re.match(r"^(\s*)([*\-]|\d+\.)\s+(.*)$", line)
        if m_list:
            in_led = cur_h2.startswith("2.")
            raw_items: list[tuple[int, str, str, int]] = []
            while i < n:
                ml = re.match(r"^(\s*)([*\-]|\d+\.)\s+(.*)$", lines[i])
                if not ml:
                    break
                lvl = 1 if len(ml.group(1)) >= 2 else 0
                raw_m = ml.group(2)
                tag = "ol" if raw_m.endswith(".") else "ul"
                num = int(raw_m[:-1]) if raw_m.endswith(".") else 1
                raw_items.append((lvl, tag, ml.group(3).strip(), num))
                i += 1

            # Build nested HTML list preserving exact <ol start="N">
            out_l: list[str] = []
            stack: list[tuple[int, str]] = []
            for lvl, tag, txt, num in raw_items:
                rendered = fmt_inline(txt, color_led=(in_led and lvl == 0))
                while stack and (stack[-1][0] > lvl or (stack[-1][0] == lvl and stack[-1][1] != tag)):
                    _, ctag = stack.pop()
                    out_l.append(f"</li></{ctag}>")
                if not stack or stack[-1][0] < lvl:
                    start_attr = f' start="{num}"' if (tag == "ol" and num > 1) else ""
                    out_l.append(f"<{tag}{start_attr}><li>{rendered}")
                    stack.append((lvl, tag))
                else:
                    out_l.append(f"</li><li>{rendered}")
            while stack:
                _, ctag = stack.pop()
                out_l.append(f"</li></{ctag}>")
            list_html = "".join(out_l)

            # En Sección 1: combinar pasos a la izquierda + foto vertical del portaelectrodo a la derecha
            j = i
            while j < n and not lines[j].strip():
                j += 1
            if cur_h2.startswith("1.") and j < n and re.match(r"^!\[([^\]]*)\]\(([^)]+)\)$", lines[j].strip()):
                m1 = re.match(r"^!\[([^\]]*)\]\(([^)]+)\)$", lines[j].strip())
                uri1 = img_to_data_uri(m1.group(2))
                alt1 = html.escape(m1.group(1))
                blocks.append(
                    f'<div class="sec1-grid">'
                    f'<div class="sec1-left">{list_html}</div>'
                    f'<div class="sec1-right"><img src="{uri1}" alt="{alt1}"></div>'
                    f"</div>"
                )
                i = j + 1
            else:
                blocks.append(list_html)
            continue

        # Normal paragraph
        pl = [s]
        i += 1
        while (
            i < n
            and lines[i].strip()
            and not lines[i].strip().startswith(("#", ">", "![", "---"))
            and not re.match(r"^(\s*)([*\-]|\d+\.)\s+", lines[i])
        ):
            pl.append(lines[i].strip())
            i += 1
        blocks.append(f"<p>{fmt_inline(' '.join(pl))}</p>")

    body = "\n".join(blocks)
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>Manual de uso — ArcSim_VR</title>
<style>
  @page {{
    size: A4;
    margin: 20mm 22mm 20mm 22mm;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    font-family: "Segoe UI", Roboto, Calibri, Arial, sans-serif;
    font-size: 10.8pt;
    line-height: 1.48;
    color: #111111;
    margin: 0;
    padding: 0;
  }}
  h1 {{
    font-size: 21pt;
    line-height: 1.22;
    font-weight: 700;
    color: #0f172a;
    margin: 0 0 6pt 0;
  }}
  .subtitle {{
    font-size: 16.5pt;
    font-weight: 700;
    color: #4a86e8;
    margin: 0 0 10pt 0;
  }}
  hr {{
    border: none;
    border-top: 1px solid #7f8c8d;
    margin: 12pt 0 13pt 0;
  }}
  h2 {{
    font-size: 16.5pt;
    font-weight: 700;
    color: #0f172a;
    margin: 4pt 0 9pt 0;
    break-after: avoid;
    page-break-after: avoid;
  }}
  h3 {{
    font-size: 11.5pt;
    font-weight: 700;
    color: #111111;
    margin: 6pt 0 6pt 0;
    break-after: avoid;
    page-break-after: avoid;
  }}
  p {{
    margin: 0 0 8pt 0;
  }}
  ol, ul {{
    margin: 4pt 0 9pt 0;
    padding-left: 20pt;
  }}
  li {{
    margin-bottom: 5.5pt;
  }}
  li ul {{
    margin-top: 4pt;
    margin-bottom: 4pt;
  }}
  code {{
    font-family: Consolas, "Courier New", monospace;
    font-size: 9.6pt;
    background: #f1f5f9;
    padding: 1pt 3.5pt;
    border-radius: 3px;
    color: #0f172a;
  }}
  .sec1-grid {{
    display: flex;
    align-items: center;
    gap: 16pt;
    margin: 4pt 0 6pt 0;
    break-inside: avoid;
    page-break-inside: avoid;
  }}
  .sec1-left {{
    flex: 1.45;
  }}
  .sec1-right {{
    flex: 0.85;
    text-align: center;
  }}
  .sec1-right img {{
    max-width: 100%;
    max-height: 66mm;
    border-radius: 5px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.12);
  }}
  .callout-box {{
    width: fit-content;
    min-width: 68mm;
    margin: 8pt auto 10pt auto;
    padding: 7pt 16pt;
    border: 1.1pt solid #111111;
    text-align: center;
    font-size: 10.5pt;
    line-height: 1.45;
    break-inside: avoid;
  }}
  .fig-center {{
    text-align: center;
    margin: 8pt auto 10pt auto;
    break-inside: avoid;
    page-break-inside: avoid;
  }}
  .fig-center img {{
    max-width: 86%;
    max-height: 68mm;
    width: auto;
    height: auto;
    border-radius: 4px;
    box-shadow: 0 1px 5px rgba(0,0,0,0.14);
  }}
  .fig-pair {{
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 7pt;
    margin: 8pt auto 10pt auto;
    break-inside: avoid;
    page-break-inside: avoid;
  }}
  .fig-pair img {{
    max-width: 84%;
    max-height: 58mm;
    width: auto;
    height: auto;
    border-radius: 4px;
    box-shadow: 0 1px 5px rgba(0,0,0,0.14);
  }}
</style>
</head>
<body>
{body}
</body>
</html>"""


def main() -> int:
    pdf_out = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DEFAULT_PDF
    browser = find_browser()
    if not browser:
        print("[ERROR] No se encontró Chrome/Edge para renderizar el PDF.")
        return 1

    html_str = build_html(MD_PATH.read_text(encoding="utf-8"))
    html_tmp = pdf_out.with_suffix(".tmp.html")
    html_tmp.write_text(html_str, encoding="utf-8")

    tmp_profile = Path(tempfile.gettempdir()) / "arcsim_manual_pdf_profile"
    tmp_profile.mkdir(parents=True, exist_ok=True)

    cmd = [
        browser,
        "--headless",
        "--disable-gpu",
        "--no-first-run",
        "--no-default-browser-check",
        f"--user-data-dir={tmp_profile}",
        "--no-pdf-header-footer",
        "--virtual-time-budget=6000",
        f"--print-to-pdf={pdf_out}",
        html_tmp.as_uri(),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    html_tmp.unlink(missing_ok=True)

    if pdf_out.exists() and pdf_out.stat().st_size > 10_000:
        print(f"[OK] Manual de Uso PDF generado: {pdf_out} ({pdf_out.stat().st_size // 1024} KB)")
        return 0
    print(f"[ERROR] Falló generación PDF: {res.stderr}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
