#!/usr/bin/env python3
"""
Generador de PDF estilo cátedra Realidad Virtual (UNCuyo - Facultad de Ingeniería).
Renderiza portada oficial con logo institucional, Índice automático en página 2 con
numeración exacta calculada en doble pasada, encabezado/pie institucional en páginas 2..N,
diagramas vectoriales Mermaid, ecuaciones KaTeX e imágenes locales en Base64.

Uso:
    python tools/exportar_informe_pdf.py [salida.pdf]
"""
import base64
import html
import mimetypes
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MD_PATH = ROOT / "informe_tecnico.md"
LOGO_PATH = ROOT / "docs_referencia" / "logo_uncuyo_fing.jpg"
DEFAULT_PDF = ROOT / "informe_tecnico_preliminar.pdf"


def embed_image(rel_path: str) -> str:
    img_path = (ROOT / rel_path).resolve()
    if not img_path.exists():
        return rel_path
    mime, _ = mimetypes.guess_type(str(img_path))
    mime = mime or "image/png"
    b64 = base64.b64encode(img_path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"


class MarkdownToModelHTML:
    def __init__(self, md_text: str):
        self.md = md_text.replace("\r\n", "\n")
        self.tokens: list[str] = []
        self.toc_entries: list[dict] = []  # {"id", "level", "title_html"}

    def _stash(self, html_fragment: str) -> str:
        idx = len(self.tokens)
        self.tokens.append(html_fragment)
        return f"\x00TOK{idx}END\x00"

    def _unstash(self, text: str) -> str:
        for _ in range(4):
            if "\x00TOK" not in text:
                break
            text = re.sub(
                r"\x00TOK(\d+)END\x00",
                lambda m: self.tokens[int(m.group(1))],
                text,
            )
        return text

    def format_inline(self, text: str) -> str:
        def repl_code(m: re.Match) -> str:
            inner = html.escape(m.group(1), quote=False)
            if inner.startswith("[COMPLETAR"):
                return self._stash(f'<span class="completar-badge">{inner}</span>')
            return self._stash(f"<code>{inner}</code>")

        text = re.sub(r"`([^`\n]+)`", repl_code, text)

        text = re.sub(
            r"\$\$(.+?)\$\$",
            lambda m: self._stash(
                f'<div class="math-display">\\[{html.escape(m.group(1), quote=False)}\\]</div>'
            ),
            text,
        )
        text = re.sub(
            r"(?<!\$)\$(?!\$)([^\$\n]+?)(?<!\$)\$(?!\$)",
            lambda m: self._stash(
                f'<span class="math-inline">\\({html.escape(m.group(1), quote=False)}\\)</span>'
            ),
            text,
        )

        def repl_img(m: re.Match) -> str:
            alt = html.escape(m.group(1), quote=True)
            src = embed_image(m.group(2).strip())
            return self._stash(f'<div class="figure-box"><img src="{src}" alt="{alt}"></div>')

        text = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", repl_img, text)

        def repl_link(m: re.Match) -> str:
            label = self.format_inline(m.group(1))
            url = m.group(2).strip()
            if url.startswith("file:///"):
                return self._stash(f'<span class="file-ref">{label}</span>')
            esc_url = html.escape(url, quote=True)
            return self._stash(f'<a href="{esc_url}">{label}</a>')

        text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", repl_link, text)

        text = html.escape(text, quote=False)

        text = re.sub(
            r"(https?://[^\s<)]+)",
            lambda m: self._stash(f'<a href="{m.group(1)}">{m.group(1)}</a>'),
            text,
        )

        text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
        text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)

        return self._unstash(text)

    def _parse_table(self, lines: list[str]) -> str:
        def split_row(row: str) -> list[str]:
            row = row.strip()
            if row.startswith("|"):
                row = row[1:]
            if row.endswith("|"):
                row = row[:-1]
            cells: list[str] = []
            cur: list[str] = []
            in_code = False
            in_math = False
            j = 0
            while j < len(row):
                ch = row[j]
                if ch == "`":
                    in_code = not in_code
                    cur.append(ch)
                elif ch == "$" and not in_code:
                    in_math = not in_math
                    cur.append(ch)
                elif ch == "|" and not in_code and not in_math and (j == 0 or row[j - 1] != "\\"):
                    cells.append("".join(cur).strip())
                    cur = []
                else:
                    cur.append(ch)
                j += 1
            cells.append("".join(cur).strip())
            return cells

        headers = split_row(lines[0])
        align_cells = split_row(lines[1])
        aligns = []
        for ac in align_cells:
            ac = ac.strip()
            if ac.startswith(":") and ac.endswith(":"):
                aligns.append("center")
            elif ac.endswith(":"):
                aligns.append("right")
            else:
                aligns.append("left")

        out = ['<div class="table-wrap"><table><thead><tr>']
        for idx, h in enumerate(headers):
            al = aligns[idx] if idx < len(aligns) else "left"
            out.append(f'<th style="text-align:{al}">{self.format_inline(h)}</th>')
        out.append("</tr></thead><tbody>")

        for rline in lines[2:]:
            if not rline.strip():
                continue
            cells = split_row(rline)
            out.append("<tr>")
            for idx, c in enumerate(cells):
                al = aligns[idx] if idx < len(aligns) else "left"
                out.append(f'<td style="text-align:{al}">{self.format_inline(c)}</td>')
            out.append("</tr>")
        out.append("</tbody></table></div>")
        return "\n".join(out)

    def _parse_list(self, lines: list[str]) -> str:
        items = []
        k = 0
        while k < len(lines):
            line = lines[k]
            s = line.strip()
            if s.startswith("```") and items:
                lang = s[3:].strip()
                k += 1
                c_lines = []
                while k < len(lines) and not lines[k].strip().startswith("```"):
                    c_lines.append(re.sub(r"^ {1,4}", "", lines[k]))
                    k += 1
                k += 1
                esc_c = html.escape("\n".join(c_lines), quote=False)
                badge = f'<div class="code-lang">{html.escape(lang)}</div>' if lang else ""
                items[-1][2].append(("html", f'<div class="code-wrap">{badge}<pre><code>{esc_c}</code></pre></div>'))
                continue
            m = re.match(r"^(\s*)([*\-]|\d+\.)\s+(.*)$", line)
            if m:
                indent = len(m.group(1))
                lvl = 1 if indent >= 2 else 0
                tag = "ol" if m.group(2).endswith(".") else "ul"
                items.append([lvl, tag, [("text", m.group(3).strip())]])
            elif items:
                if items[-1][2] and items[-1][2][-1][0] == "text":
                    items[-1][2][-1] = ("text", items[-1][2][-1][1] + " " + s)
                else:
                    items[-1][2].append(("text", s))
            k += 1

        def render_parts(parts) -> str:
            return "".join(self.format_inline(p[1]) if p[0] == "text" else p[1] for p in parts)

        out: list[str] = []
        stack: list[tuple[int, str]] = []

        for lvl, tag, parts in items:
            rendered = render_parts(parts)
            while stack and (stack[-1][0] > lvl or (stack[-1][0] == lvl and stack[-1][1] != tag)):
                _, closed_tag = stack.pop()
                out.append(f"</li></{closed_tag}>")
            if not stack or stack[-1][0] < lvl:
                out.append(f"<{tag}><li>{rendered}")
                stack.append((lvl, tag))
            else:
                out.append(f"</li><li>{rendered}")

        while stack:
            _, closed_tag = stack.pop()
            out.append(f"</li></{closed_tag}>")

        return "\n".join(out)

    def parse_body(self) -> tuple[str, str]:
        # Split cover section (up to first ---) from main body
        parts = re.split(r"\n---\s*\n", self.md, maxsplit=1)
        cover_md = parts[0] if len(parts) > 1 else ""
        body_md = parts[1] if len(parts) > 1 else self.md

        # Extract title from cover_md
        m_title = re.search(r"^#\s+(.+)$", cover_md, re.M)
        title_html = self.format_inline(m_title.group(1).strip()) if m_title else "Proyecto Integrador"

        # Extract alumno lines
        legajos = re.findall(r"^(García.*|Albanez.*)$", cover_md, re.M)
        alumnos_html = "<br>".join(self.format_inline(l.strip()) for l in legajos)

        logo_uri = embed_image("docs_referencia/logo_uncuyo_fing.jpg") if LOGO_PATH.exists() else ""
        logo_img_cover = f'<img class="cover-logo" src="{logo_uri}" alt="UNCUYO - Facultad de Ingeniería">' if logo_uri else ""

        cover_html = f"""
        <div class="cover-page">
          <div class="cover-top">{logo_img_cover}</div>
          <div class="cover-center">
            <h1 class="cover-title">{title_html}</h1>
            <div class="cover-sub1">Proyecto Integrador</div>
            <div class="cover-sub2">Realidad Virtual</div>
          </div>
          <div class="cover-bottom">
            <div class="cover-group">
              <div class="cover-role">Profesores</div>
              <div class="cover-person">Profesor Titular: Javier Rosenstein</div>
              <div class="cover-person">JTP: Carlos Tomba</div>
            </div>
            <div class="cover-group">
              <div class="cover-role">Alumnos</div>
              <div class="cover-person">{alumnos_html}</div>
            </div>
          </div>
        </div>
        """

        lines = body_md.split("\n")
        n = len(lines)
        i = 0
        blocks: list[str] = []
        sec_counter = 0

        while i < n:
            line = lines[i]
            stripped = line.strip()

            if not stripped or stripped.startswith("<!--"):
                i += 1
                continue

            if stripped.startswith("```"):
                lang = stripped[3:].strip()
                i += 1
                code_lines = []
                while i < n and not lines[i].strip().startswith("```"):
                    code_lines.append(lines[i])
                    i += 1
                i += 1
                raw_code = "\n".join(code_lines)
                if lang == "mermaid":
                    esc_mermaid = html.escape(raw_code, quote=False)
                    blocks.append(f'<div class="mermaid-box"><pre class="mermaid">{esc_mermaid}</pre></div>')
                else:
                    esc_code = html.escape(raw_code, quote=False)
                    lang_badge = f'<div class="code-lang">{html.escape(lang)}</div>' if lang else ""
                    blocks.append(f'<div class="code-wrap">{lang_badge}<pre><code>{esc_code}</code></pre></div>')
                continue

            if stripped.startswith("$$"):
                if stripped.endswith("$$") and len(stripped) > 4:
                    expr = stripped[2:-2].strip()
                    i += 1
                else:
                    expr_lines = [stripped[2:]]
                    i += 1
                    while i < n and not lines[i].strip().endswith("$$"):
                        expr_lines.append(lines[i])
                        i += 1
                    if i < n:
                        expr_lines.append(lines[i].strip()[:-2])
                        i += 1
                    expr = "\n".join(expr_lines).strip()
                blocks.append(f'<div class="math-display">\\[{html.escape(expr, quote=False)}\\]</div>')
                continue

            if re.match(r"^-{3,}\s*$", stripped):
                i += 1
                continue

            m_h = re.match(r"^(#{2,4})\s+(.*)$", stripped)
            if m_h:
                lvl = len(m_h.group(1))
                raw_title = m_h.group(2).strip()
                h_html = self.format_inline(raw_title)
                sec_id = f"sec-{sec_counter}"
                sec_counter += 1
                # Strip parenthetical code suffixes in TOC to keep it clean like model PDF
                clean_toc_title = re.sub(r"\s*\(`[^`]+`\)", "", raw_title)
                self.toc_entries.append({
                    "id": sec_id,
                    "level": lvl,  # 2, 3, or 4
                    "title_html": self.format_inline(clean_toc_title),
                })
                blocks.append(f'<h{lvl} id="{sec_id}">{h_html}</h{lvl}>')
                i += 1
                continue

            if stripped.startswith(">"):
                q_lines = []
                while i < n and lines[i].strip().startswith(">"):
                    q_lines.append(re.sub(r"^>\s?", "", lines[i].strip()))
                    i += 1
                q_text = " ".join(q_lines)
                if "INSERTAR FIGURA" in q_text:
                    blocks.append(
                        f'<div class="figure-placeholder"><div class="ph-inner">{self.format_inline(q_text)}</div></div>'
                    )
                else:
                    blocks.append(f"<blockquote>{self.format_inline(q_text)}</blockquote>")
                continue

            if (
                "|" in stripped
                and i + 1 < n
                and re.match(r"^\s*\|?[\s:\-]+\|[\s:\-|]+$", lines[i + 1])
            ):
                t_lines = [lines[i], lines[i + 1]]
                i += 2
                while i < n and "|" in lines[i] and lines[i].strip():
                    t_lines.append(lines[i])
                    i += 1
                blocks.append(self._parse_table(t_lines))
                continue

            if re.match(r"^(\s*)([*\-]|\d+\.)\s+", line):
                l_lines = []
                while i < n and lines[i].strip() and (
                    re.match(r"^(\s*)([*\-]|\d+\.)\s+", lines[i])
                    or lines[i].startswith("  ")
                ):
                    l_lines.append(lines[i])
                    i += 1
                blocks.append(self._parse_list(l_lines))
                continue

            if stripped.startswith("!["):
                img_html = self.format_inline(stripped)
                i += 1
                cap_html = ""
                if i < n and re.match(r"^\*[^*].*\*\s*$", lines[i].strip()):
                    cap_html = f'<div class="figure-caption">{self.format_inline(lines[i].strip())}</div>'
                    i += 1
                blocks.append(f'<div class="figure-container">{img_html}{cap_html}</div>')
                continue

            p_lines = []
            while (
                i < n
                and lines[i].strip()
                and not lines[i].strip().startswith(("```", "$$", "#", ">", "![", "<!--"))
                and not re.match(r"^-{3,}\s*$", lines[i].strip())
                and not re.match(r"^(\s*)([*\-]|\d+\.)\s+", lines[i])
                and not (
                    "|" in lines[i]
                    and i + 1 < n
                    and re.match(r"^\s*\|?[\s:\-]+\|[\s:\-|]+$", lines[i + 1])
                )
            ):
                p_lines.append(lines[i].strip())
                i += 1
            blocks.append(f"<p>{self.format_inline(' '.join(p_lines))}</p>")

        return cover_html, "\n\n".join(blocks)

    def build_toc_html(self, page_map: dict[str, int] | None = None) -> str:
        rows = ['<div class="toc-page"><h2 class="toc-heading">Índice</h2><div class="toc-list">']
        for entry in self.toc_entries:
            sid = entry["id"]
            lvl = entry["level"]  # 2, 3, 4
            pg = str(page_map.get(sid, "•")) if page_map else "•"
            rows.append(
                f'<a class="toc-row toc-lvl-{lvl}" href="#{sid}">'
                f'<span class="toc-title">{entry["title_html"]}</span>'
                f'<span class="toc-dots"></span>'
                f'<span class="toc-page-num">{pg}</span>'
                f"</a>"
            )
        rows.append("</div></div>")
        return "\n".join(rows)


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>Proyecto Integrador — Realidad Virtual — ArcSim_VR</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.css">
<script src="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/contrib/auto-render.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/mermaid@10.9.1/dist/mermaid.min.js"></script>
<style>
  @page {
    size: A4;
    margin: 15mm 22mm 21mm 22mm;
    @bottom-left {
      content: "Albanez, Luciano; García, Ezequiel";
      font-family: "Segoe UI", Calibri, Arial, sans-serif;
      font-style: italic;
      font-size: 9.8pt;
      color: #111111;
      border-top: 1.5pt solid #111111;
      padding-top: 3mm;
      vertical-align: top;
    }
    @bottom-right {
      content: "Página " counter(page) " de " counter(pages);
      font-family: "Segoe UI", Calibri, Arial, sans-serif;
      font-size: 9.8pt;
      color: #111111;
      border-top: 1.5pt solid #111111;
      padding-top: 3mm;
      vertical-align: top;
    }
  }
  @page :first {
    margin: 22mm 22mm 22mm 22mm;
    @bottom-left { content: none; border: none; }
    @bottom-right { content: none; border: none; }
  }
  * { box-sizing: border-box; }
  body {
    font-family: "Segoe UI", Calibri, -apple-system, Arial, sans-serif;
    font-size: 11.4pt;
    line-height: 1.58;
    color: #111111;
    margin: 0;
    padding: 0;
  }

  /* Portada (Página 1 calcada al informe modelo) */
  .cover-page {
    height: 248mm;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    page-break-after: always;
    break-after: page;
  }
  .cover-top {
    text-align: center;
    padding-top: 6mm;
  }
  .cover-logo {
    width: 104mm;
    height: auto;
  }
  .cover-center {
    text-align: center;
    padding: 0 6mm;
  }
  .cover-title {
    font-size: 22pt;
    font-weight: 700;
    line-height: 1.32;
    color: #000000;
    margin: 0 0 18mm 0;
    border: none;
  }
  .cover-sub1 {
    font-size: 15pt;
    font-weight: 700;
    color: #111111;
    margin-bottom: 4mm;
  }
  .cover-sub2 {
    font-size: 15pt;
    font-weight: 600;
    color: #666666;
  }
  .cover-bottom {
    padding-bottom: 8mm;
  }
  .cover-group {
    margin-top: 9mm;
  }
  .cover-role {
    font-size: 11.5pt;
    font-weight: 700;
    margin-bottom: 3mm;
    color: #000000;
  }
  .cover-person {
    font-size: 11pt;
    line-height: 1.65;
    color: #111111;
  }

  /* Estructura repetitiva de encabezado institucional en páginas 2..N */
  table.doc-shell {
    width: 100%;
    border-collapse: collapse;
  }
  table.doc-shell > thead {
    display: table-header-group;
  }
  table.doc-shell > thead th {
    background: #ffffff;
    color: #111111;
    border: none;
    border-bottom: 1.5pt solid #111111;
    padding: 0 0 2.5mm 0;
    font-weight: normal;
  }
  .running-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    width: 100%;
  }
  .running-logo {
    height: 11mm;
    width: auto;
  }
  .running-right {
    text-align: right;
    font-size: 9.8pt;
    line-height: 1.3;
    color: #111111;
  }
  table.doc-shell > tbody > tr > td {
    border: none;
    padding: 5mm 0 0 0;
    background: transparent !important;
  }

  /* Índice en Página 2 */
  .toc-page {
    page-break-after: always;
    break-after: page;
  }
  .toc-heading {
    font-size: 18pt;
    font-weight: 700;
    margin: 2mm 0 7mm 0;
    border: none;
    color: #000000;
  }
  .toc-list {
    display: flex;
    flex-direction: column;
    gap: 2.3mm;
  }
  .toc-row {
    display: flex;
    align-items: baseline;
    text-decoration: none;
    color: #111111;
    font-size: 10.5pt;
  }
  .toc-lvl-2 {
    font-weight: 700;
    margin-top: 1.2mm;
  }
  .toc-lvl-3 {
    padding-left: 6mm;
    font-weight: 400;
  }
  .toc-lvl-4 {
    padding-left: 12mm;
    font-weight: 400;
    font-size: 10pt;
  }
  .toc-title {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .toc-dots {
    flex: 1;
    border-bottom: 1.2px dotted #444444;
    margin: 0 2mm;
    min-width: 10mm;
  }
  .toc-page-num {
    font-weight: 600;
    min-width: 5mm;
    text-align: right;
  }

  /* Tipografía de secciones (flujo continuo orgánico igual al informe modelo) */
  h2 {
    font-size: 16.5pt;
    font-weight: 700;
    color: #000000;
    margin: 14pt 0 7pt 0;
    break-after: avoid;
    page-break-after: avoid;
  }
  h3 {
    font-size: 13pt;
    font-weight: 700;
    color: #111111;
    margin: 12pt 0 5.5pt 0;
    break-after: avoid;
    page-break-after: avoid;
  }
  h4 {
    font-size: 11pt;
    font-weight: 700;
    color: #111111;
    margin: 10pt 0 4.5pt 0;
    break-after: avoid;
    page-break-after: avoid;
  }
  p {
    margin: 0 0 7.5pt 0;
    text-align: justify;
  }
  ul, ol {
    margin: 3pt 0 8pt 0;
    padding-left: 18pt;
  }
  li {
    margin-bottom: 3.5pt;
    text-align: justify;
  }

  code {
    font-family: Consolas, "Cascadia Mono", monospace;
    font-size: 8.8pt;
    background: #f3f4f6;
    padding: 1px 4px;
    border-radius: 3px;
  }
  .code-wrap {
    background: #f8fafc;
    border: 1px solid #d1d5db;
    border-radius: 5px;
    margin: 7pt 0 10pt 0;
    break-inside: avoid;
    page-break-inside: avoid;
  }
  .code-lang {
    font-family: Consolas, monospace;
    font-size: 7.5pt;
    color: #4b5563;
    background: #e5e7eb;
    padding: 2px 8px;
    text-transform: uppercase;
    font-weight: 600;
  }
  .code-wrap pre {
    margin: 0;
    padding: 7pt 9pt;
    white-space: pre-wrap;
    word-break: break-word;
  }
  .code-wrap pre code {
    background: transparent;
    padding: 0;
    font-size: 8pt;
    line-height: 1.36;
  }

  /* Tablas limpias */
  .table-wrap {
    margin: 7pt 0 10pt 0;
  }
  .table-wrap table {
    width: 100%;
    border-collapse: collapse;
    font-size: 8.6pt;
    line-height: 1.34;
  }
  .table-wrap thead {
    display: table-header-group;
  }
  .table-wrap tr {
    break-inside: avoid;
    page-break-inside: avoid;
  }
  .table-wrap th {
    background: #1f2937;
    color: #ffffff;
    font-weight: 600;
    padding: 5pt 6.5pt;
    border: 1px solid #1f2937;
  }
  .table-wrap th code {
    background: rgba(255, 255, 255, 0.18);
    color: #ffffff;
  }
  .table-wrap td {
    padding: 4.5pt 6.5pt;
    border: 1px solid #cbd5e1;
    vertical-align: top;
  }
  .table-wrap tbody tr:nth-child(even) td {
    background: #f8fafc;
  }

  /* Figuras y marcadores con altura realista reservada */
  .figure-container {
    margin: 11pt auto 13pt auto;
    text-align: center;
    break-inside: avoid;
    page-break-inside: avoid;
  }
  .figure-box img {
    max-width: 94%;
    max-height: 98mm;
    height: auto;
    border-radius: 3px;
  }
  .figure-caption {
    font-size: 9.8pt;
    font-style: italic;
    color: #222222;
    margin-top: 4pt;
    text-align: center;
  }
  .figure-placeholder {
    margin: 11pt auto 13pt auto;
    min-height: 76mm;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 14pt 18pt;
    border: 1.8px dashed #2563eb;
    background: #f0f7ff;
    color: #1e3a8a;
    border-radius: 6px;
    text-align: center;
    font-size: 9.8pt;
    break-inside: avoid;
    page-break-inside: avoid;
  }
  .completar-badge {
    background: #fef3c7;
    color: #92400e;
    border: 1px solid #f59e0b;
    padding: 1px 5px;
    border-radius: 4px;
    font-weight: 600;
    font-size: 8.6pt;
  }
  .mermaid-box {
    margin: 8pt auto 10pt auto;
    padding: 6pt;
    text-align: center;
    break-inside: avoid;
    page-break-inside: avoid;
  }
  .mermaid-box svg {
    max-width: 95% !important;
    height: auto !important;
    max-height: 145mm;
  }
  .math-display {
    margin: 6pt 0;
    text-align: center;
    break-inside: avoid;
  }
  a {
    color: #1d4ed8;
    text-decoration: underline;
  }
  .toc-row {
    text-decoration: none;
  }
</style>
</head>
<body>
__COVER__
<table class="doc-shell">
  <thead>
    <tr>
      <th>
        <div class="running-header">
          <div>__LOGO_RUNNING__</div>
          <div class="running-right">Realidad Virtual<br>Proyecto Integrador</div>
        </div>
      </th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>
        __TOC__
        __BODY__
      </td>
    </tr>
  </tbody>
</table>
<script>
  document.addEventListener("DOMContentLoaded", async () => {
    if (window.renderMathInElement) {
      renderMathInElement(document.body, {
        delimiters: [
          {left: "\\\\[", right: "\\\\]", display: true},
          {left: "\\\\(", right: "\\\\)", display: false}
        ],
        throwOnError: false
      });
    }
    if (window.mermaid) {
      mermaid.initialize({
        startOnLoad: false,
        theme: "base",
        themeVariables: {
          primaryColor: "#e8f0fe",
          primaryBorderColor: "#3b82f6",
          primaryTextColor: "#111827",
          lineColor: "#374151",
          secondaryColor: "#fef3c7",
          tertiaryColor: "#ecfdf5",
          fontSize: "13px"
        },
        securityLevel: "loose",
        flowchart: { htmlLabels: true, curve: "basis" },
        fontFamily: "Segoe UI, Calibri, sans-serif"
      });
      await mermaid.run({ querySelector: ".mermaid" });
    }
  });
</script>
</body>
</html>
"""


def extract_toc_page_numbers(pdf_bytes: bytes, toc_ids: list[str]) -> dict[str, int]:
    """Lee las anotaciones /Subtype /Link de la página 2 (Índice) en el PDF generado por Chrome
    y resuelve a qué número de página 1-based apunta cada destino interno."""
    objects: dict[int, bytes] = {}
    for m in re.finditer(rb"(\d+)\s+0\s+obj\b(.*?)endobj", pdf_bytes, re.S):
        objects[int(m.group(1))] = m.group(2)

    # Orden real de páginas desde el nodo /Pages -> /Kids [...]
    page_order: list[int] = []

    def collect_kids(obj_id: int) -> None:
        body = objects.get(obj_id, b"")
        if re.search(rb"/Type\s*/Page\b", body) and not re.search(rb"/Type\s*/Pages\b", body):
            page_order.append(obj_id)
            return
        m_kids = re.search(rb"/Kids\s*\[([^\]]+)\]", body, re.S)
        if m_kids:
            for kid in re.findall(rb"(\d+)\s+0\s+R", m_kids.group(1)):
                collect_kids(int(kid))

    for oid, body in objects.items():
        if re.search(rb"/Type\s*/Catalog\b", body):
            m_pages = re.search(rb"/Pages\s+(\d+)\s+0\s+R", body)
            if m_pages:
                collect_kids(int(m_pages.group(1)))
            break

    if len(page_order) < 2:
        return {}

    obj_to_page_num = {oid: idx + 1 for idx, oid in enumerate(page_order)}

    # Chrome genera destinos nombrados directos: /sec-N [PAGE_OBJ_ID 0 R /XYZ ...]
    result: dict[str, int] = {}
    for m in re.finditer(rb"/(sec-\d+)\s*\[\s*(\d+)\s+0\s+R", pdf_bytes):
        sid = m.group(1).decode("ascii")
        target_oid = int(m.group(2))
        if target_oid in obj_to_page_num:
            result[sid] = obj_to_page_num[target_oid]
    return result


def find_browser() -> str | None:
    for c in [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]:
        if os.path.exists(c):
            return c
    return None


def render_pdf(browser: str, html_path: Path, pdf_path: Path, tmp_profile: Path) -> bool:
    cmd = [
        browser,
        "--headless",
        "--disable-gpu",
        "--no-first-run",
        "--no-default-browser-check",
        f"--user-data-dir={tmp_profile}",
        "--no-pdf-header-footer",
        "--virtual-time-budget=10000",
        f"--print-to-pdf={pdf_path}",
        html_path.as_uri(),
    ]
    subprocess.run(cmd, capture_output=True, text=True)
    return pdf_path.exists() and pdf_path.stat().st_size > 10_000


def main() -> int:
    pos_args = [a for a in sys.argv[1:] if not a.startswith("--")]
    pdf_out = Path(pos_args[0]).resolve() if pos_args else DEFAULT_PDF
    html_out = pdf_out.with_suffix(".html")

    md_text = MD_PATH.read_text(encoding="utf-8")
    parser = MarkdownToModelHTML(md_text)
    cover_html, body_html = parser.parse_body()
    logo_running = (
        f'<img class="running-logo" src="{embed_image("docs_referencia/logo_uncuyo_fing.jpg")}" alt="UNCUYO">'
        if LOGO_PATH.exists()
        else "<strong>UNCUYO | FACULTAD DE INGENIERÍA</strong>"
    )

    def write_html(page_map: dict[str, int] | None) -> None:
        toc_html = parser.build_toc_html(page_map)
        full = (
            HTML_TEMPLATE.replace("__COVER__", cover_html)
            .replace("__LOGO_RUNNING__", logo_running)
            .replace("__TOC__", toc_html)
            .replace("__BODY__", body_html)
        )
        html_out.write_text(full, encoding="utf-8")

    write_html(None)
    if "--html-only" in sys.argv:
        print(f"[OK] HTML generado: {html_out}")
        return 0

    browser = find_browser()
    if not browser:
        print("[ERROR] No se encontró Chrome/Edge.")
        return 1

    tmp_profile = Path(tempfile.gettempdir()) / "arcsim_chrome_pdf_profile"
    tmp_profile.mkdir(parents=True, exist_ok=True)

    print("[INFO] Pasada 1/2: Calculando paginación exacta para el Índice...")
    if not render_pdf(browser, html_out, pdf_out, tmp_profile):
        print("[ERROR] Falló pasada 1 de renderizado PDF.")
        return 1

    toc_ids = [e["id"] for e in parser.toc_entries]
    page_map = extract_toc_page_numbers(pdf_out.read_bytes(), toc_ids)
    print(f"[INFO] Pasada 2/2: Inyectando {len(page_map)}/{len(toc_ids)} números de página en el Índice...")
    write_html(page_map)
    if not render_pdf(browser, html_out, pdf_out, tmp_profile):
        print("[ERROR] Falló pasada 2 de renderizado PDF.")
        return 1

    html_out.unlink(missing_ok=True)
    print(f"[OK] PDF final generado: {pdf_out} ({pdf_out.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
