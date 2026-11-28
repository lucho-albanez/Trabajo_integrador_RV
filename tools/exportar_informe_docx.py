#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generador del Informe Técnico en formato Microsoft Word (.docx) nativo (OOXML).
Replica la portada oficial UNCUYO–FING, encabezado/pie institucional, Índice con
referencias de página y marcadores internos, tablas estilizadas, bloques de código,
ecuaciones limpias, imágenes embebidas y diagramas Mermaid renderizados en alta
resolución mediante Chrome Headless + recorte automático con Pillow (si disponible).

Uso:
    python tools/exportar_informe_docx.py [salida.docx]
"""

from __future__ import annotations

import html
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MD_PATH = ROOT / "informe_tecnico.md"
LOGO_PATH = ROOT / "docs_referencia" / "logo_uncuyo_fing.jpg"
DEFAULT_DOCX = ROOT / "informe_tecnico_preliminar.docx"
PDF_REF = ROOT / "informe_tecnico_preliminar.pdf"


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


def find_pillow_python() -> str | None:
    candidates = [
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Python\Python312\python.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Python\Python311\python.exe"),
        sys.executable,
    ]
    for c in candidates:
        if os.path.isfile(c):
            res = subprocess.run([c, "-c", "import PIL"], capture_output=True)
            if res.returncode == 0:
                return c
    return None


def render_mermaid_diagrams(mermaid_blocks: list[str], out_dir: Path) -> list[Path | None]:
    """Renderiza cada bloque Mermaid a un PNG recortado de alta resolución."""
    if not mermaid_blocks:
        return []
    browser = find_browser()
    if not browser:
        return [None] * len(mermaid_blocks)

    pil_py = find_pillow_python()
    results: list[Path | None] = []
    profile_dir = out_dir / "chrome_profile"
    profile_dir.mkdir(parents=True, exist_ok=True)

    for idx, code in enumerate(mermaid_blocks):
        html_file = out_dir / f"mmd_{idx}.html"
        raw_png = out_dir / f"mmd_{idx}_raw.png"
        crop_png = out_dir / f"mmd_{idx}.png"

        esc = html.escape(code, quote=False)
        html_content = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
  html, body {{ margin: 0; padding: 24px; background: #ffffff; font-family: 'Segoe UI', Arial, sans-serif; }}
  .mermaid {{ display: inline-block; background: #ffffff; }}
</style>
<script src="https://cdn.jsdelivr.net/npm/mermaid@10.9.1/dist/mermaid.min.js"></script>
<script>
  mermaid.initialize({{
    startOnLoad: true,
    theme: 'base',
    securityLevel: 'loose',
    themeVariables: {{
      fontFamily: 'Segoe UI, Arial, sans-serif',
      fontSize: '14px',
      primaryColor: '#e8f0fe',
      primaryTextColor: '#0f172a',
      primaryBorderColor: '#2563eb',
      lineColor: '#334155',
      secondaryColor: '#f1f5f9',
      tertiaryColor: '#f0fdf4'
    }},
    flowchart: {{ htmlLabels: true, curve: 'basis' }}
  }});
</script>
</head><body><div id="box" class="mermaid">{esc}</div></body></html>"""
        html_file.write_text(html_content, encoding="utf-8")

        cmd = [
            browser,
            "--headless",
            "--disable-gpu",
            "--hide-scrollbars",
            "--force-device-scale-factor=2",
            "--window-size=1500,1400",
            "--virtual-time-budget=8000",
            f"--user-data-dir={profile_dir}",
            f"--screenshot={raw_png}",
            html_file.as_uri(),
        ]
        subprocess.run(cmd, capture_output=True)
        if not raw_png.exists() or raw_png.stat().st_size < 1000:
            results.append(None)
            continue

        if pil_py:
            crop_script = (
                "from PIL import Image, ImageChops\n"
                f"im = Image.open(r'{raw_png}').convert('RGB')\n"
                "bg = Image.new('RGB', im.size, (255, 255, 255))\n"
                "diff = ImageChops.difference(im, bg)\n"
                "bbox = diff.getbbox()\n"
                "if bbox:\n"
                "    pad = 24\n"
                "    l = max(0, bbox[0] - pad)\n"
                "    t = max(0, bbox[1] - pad)\n"
                "    r = min(im.width, bbox[2] + pad)\n"
                "    b = min(im.height, bbox[3] + pad)\n"
                "    im = im.crop((l, t, r, b))\n"
                f"im.save(r'{crop_png}', 'PNG')\n"
            )
            subprocess.run([pil_py, "-c", crop_script], capture_output=True)

        results.append(crop_png if crop_png.exists() else raw_png)
    return results


def get_image_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    if data[:8] == b"\x89PNG\r\n\x1a\n" and data[12:16] == b"IHDR":
        w, h = struct.unpack(">II", data[16:24])
        return int(w), int(h)
    if data[:2] == b"\xff\xd8":
        idx = 2
        n = len(data)
        while idx < n - 9:
            if data[idx] != 0xFF:
                idx += 1
                continue
            marker = data[idx + 1]
            while marker == 0xFF and idx + 2 < n:
                idx += 1
                marker = data[idx + 1]
            idx += 2
            if marker in (0xD8, 0xD9) or (0xD0 <= marker <= 0xD7):
                continue
            seg_len = struct.unpack(">H", data[idx : idx + 2])[0]
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                h, w = struct.unpack(">HH", data[idx + 3 : idx + 7])
                return int(w), int(h)
            idx += seg_len
    return (1280, 720)


def extract_pdf_toc_pages(pdf_path: Path) -> dict[str, int]:
    """Extrae los números de página exactos desde informe_tecnico_preliminar.pdf si existe."""
    if not pdf_path.exists():
        return {}
    pdf_bytes = pdf_path.read_bytes()
    objects: dict[int, bytes] = {}
    for m in re.finditer(rb"(\d+)\s+0\s+obj\b(.*?)endobj", pdf_bytes, re.S):
        objects[int(m.group(1))] = m.group(2)

    pages_root = None
    for oid, body in objects.items():
        if re.search(rb"/Type\s*/Pages\b", body) and not re.search(rb"/Parent\b", body):
            pages_root = oid
            break
    if pages_root is None:
        return {}

    page_order: list[int] = []

    def walk(oid: int) -> None:
        body = objects.get(oid, b"")
        if re.search(rb"/Type\s*/Page\b", body):
            page_order.append(oid)
            return
        mk = re.search(rb"/Kids\s*\[([^\]]+)\]", body, re.S)
        if mk:
            for kid in re.findall(rb"(\d+)\s+0\s+R", mk.group(1)):
                walk(int(kid))

    walk(pages_root)
    obj_to_page = {oid: idx + 1 for idx, oid in enumerate(page_order)}
    out: dict[str, int] = {}
    for m in re.finditer(rb"/(sec-\d+)\s*\[\s*(\d+)\s+0\s+R", pdf_bytes):
        sid = m.group(1).decode("ascii")
        tid = int(m.group(2))
        if tid in obj_to_page:
            out[sid] = obj_to_page[tid]
    return out


SUB_MAP = {
    "0": "₀", "1": "₁", "2": "₂", "3": "₃", "4": "₄",
    "5": "₅", "6": "₆", "7": "₇", "8": "₈", "9": "₉",
    "a": "ₐ", "e": "ₑ", "i": "ᵢ", "o": "ₒ", "u": "ᵤ",
    "x": "ₓ", "p": "ₚ", "t": "ₜ", "m": "ₘ", "n": "ₙ",
}
SUP_MAP = {
    "0": "⁰", "1": "¹", "2": "²", "3": "³", "4": "⁴",
    "5": "⁵", "6": "⁶", "7": "⁷", "8": "⁸", "9": "⁹",
    "+": "⁺", "-": "⁻",
}


def tex_to_readable(tex: str) -> str:
    s = tex.strip()
    s = s.replace(r"\%", "%")
    s = re.sub(r"\\text\{\s*([^}]*)\}", r" \1", s)
    s = re.sub(r"\\mathbf\{([^}]*)\}", r"\1", s)
    s = re.sub(r"\\mathcal\{O\}", "O", s)
    s = re.sub(r"\\mathbb\{R\}\^\{3\\times 3\}", "ℝ³ˣ³", s)
    s = re.sub(r"\\mathbb\{R\}\^3", "ℝ³", s)
    s = re.sub(r"\\mathbb\{R\}", "ℝ", s)
    s = re.sub(r"\\sqrt\{([^}]*)\}", r"√(\1)", s)
    s = re.sub(r"\\|\|", "‖", s)  # wait: handle \| first below!
    return s


def convert_math_expr(expr: str) -> str:
    s = expr.strip()
    s = s.replace(r"\|", "‖")
    s = s.replace(r"\%", "%")
    s = s.replace("{,}", ",")
    s = s.replace(r"\,", " ").replace(r"\;", " ").replace(r"\quad", "   ")
    s = re.sub(r"\\text\{([^}]*)\}", r"\1", s)
    s = re.sub(r"\\mathbf\{([^}]*)\}", r"\1", s)
    s = re.sub(r"\\mathcal\{O\}", "O", s)
    s = s.replace(r"\mathbb{R}^{3\times 3}", "ℝ³ˣ³").replace(r"\mathbb{R}^3", "ℝ³").replace(r"\mathbb{R}", "ℝ")
    s = re.sub(r"\\sqrt\{([A-Za-z0-9_]+)\}", r"√\1", s)
    s = re.sub(r"\\sqrt\{([^}]+)\}", r"√(\1)", s)
    replacements = [
        (r"\Longleftrightarrow", "⟺"),
        (r"\Longrightarrow", "⟹"),
        (r"\leftrightarrow", "↔"),
        (r"\rightarrow", "→"),
        (r"\leftarrow", "←"),
        (r"\varnothing", "Ø"),
        (r"\approx", "≈"),
        (r"\sim", "~"),
        (r"\propto", "∝"),
        (r"\times", "×"),
        (r"\cdot", "·"),
        (r"\pm", "±"),
        (r"\le", "≤"),
        (r"\ge", "≥"),
        (r"\neq", "≠"),
        (r"\in", "∈"),
        (r"\Delta", "Δ"),
        (r"\Omega", "Ω"),
        (r"\theta", "θ"),
        (r"\alpha", "α"),
        (r"\beta", "β"),
        (r"^{\circ}", "°"),
        (r"^\circ", "°"),
    ]
    for old, new in replacements:
        s = s.replace(old, new)

    # Subíndices _{...} o _x
    def sub_repl(m: re.Match[str]) -> str:
        val = m.group(1) or m.group(2)
        if all(ch in SUB_MAP for ch in val):
            return "".join(SUB_MAP[ch] for ch in val)
        return f"_{val}"

    s = re.sub(r"_\{([^}]+)\}|_([A-Za-z0-9])", sub_repl, s)

    # Superíndices ^{...} o ^x
    def sup_repl(m: re.Match[str]) -> str:
        val = m.group(1) or m.group(2)
        if all(ch in SUP_MAP for ch in val):
            return "".join(SUP_MAP[ch] for ch in val)
        return f"^{val}"

    s = re.sub(r"\^\{([^}]+)\}|\^([0-9+\-])", sup_repl, s)
    s = re.sub(r"\s{2,}", " ", s)
    return s.strip()


def clean_inline_math(text: str) -> str:
    return re.sub(r"\$([^$]+)\$", lambda m: convert_math_expr(m.group(1)), text)


def xml_esc(s: str) -> str:
    return html.escape(s, quote=True)


def split_md_row(row: str) -> list[str]:
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


class ReportDocxBuilder:
    def __init__(self) -> None:
        self.body_xml: list[str] = []
        self.doc_media: list[tuple[str, Path, str]] = []  # (rId, path, media_name)
        self._docpr_id = 10
        self._bm_id = 1

    def register_image(self, img_path: Path) -> str:
        for rid, p, _ in self.doc_media:
            if p == img_path:
                return rid
        idx = len(self.doc_media) + 1
        rid = f"rIdImg{idx}"
        ext = img_path.suffix.lower()
        if ext == ".jpeg":
            ext = ".jpg"
        media_name = f"doc_image{idx}{ext}"
        self.doc_media.append((rid, img_path, media_name))
        return rid

    def _run_xml(
        self,
        text: str,
        *,
        bold: bool = False,
        italic: bool = False,
        code: bool = False,
        highlight_yellow: bool = False,
        size_hp: int = 22,
        color: str = "111111",
        font_override: str | None = None,
    ) -> str:
        if not text:
            return ""
        font = font_override or ("Consolas" if code else "Segoe UI")
        rpr = [f'<w:rFonts w:ascii="{font}" w:hAnsi="{font}" w:cs="{font}"/>']
        if bold:
            rpr.append("<w:b/><w:bCs/>")
        if italic:
            rpr.append("<w:i/><w:iCs/>")
        rpr.append(f'<w:color w:val="{color}"/>')
        sz = size_hp - 2 if code else size_hp
        rpr.append(f'<w:sz w:val="{sz}"/><w:szCs w:val="{sz}"/>')
        if highlight_yellow:
            rpr.append('<w:shd w:val="clear" w:color="auto" w:fill="FEF3C7"/>')
        elif code:
            rpr.append('<w:shd w:val="clear" w:color="auto" w:fill="F1F5F9"/>')
        return f'<w:r><w:rPr>{"".join(rpr)}</w:rPr><w:t xml:space="preserve">{xml_esc(text)}</w:t></w:r>'

    def inline_runs(
        self,
        text: str,
        *,
        size_hp: int = 22,
        default_color: str = "111111",
        default_bold: bool = False,
        default_italic: bool = False,
    ) -> str:
        text = clean_inline_math(text)
        token_re = re.compile(r"(`\[COMPLETAR[^\]]*\]`|\[COMPLETAR[^\]]*\]|`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*)")
        pos = 0
        runs: list[str] = []

        for m in token_re.finditer(text):
            if m.start() > pos:
                runs.append(
                    self._run_xml(
                        text[pos : m.start()],
                        bold=default_bold,
                        italic=default_italic,
                        size_hp=size_hp,
                        color=default_color,
                    )
                )
            tok = m.group(0)
            if "COMPLETAR" in tok:
                clean_tok = tok.strip("`")
                runs.append(
                    self._run_xml(
                        clean_tok,
                        bold=True,
                        highlight_yellow=True,
                        size_hp=size_hp - 1,
                        color="92400E",
                    )
                )
            elif tok.startswith("`"):
                runs.append(
                    self._run_xml(
                        tok[1:-1],
                        bold=default_bold,
                        italic=default_italic,
                        code=True,
                        size_hp=size_hp,
                        color="0F172A" if default_color != "FFFFFF" else "FFFFFF",
                    )
                )
            elif tok.startswith("**"):
                inner = tok[2:-2]
                sub_pos = 0
                for sm in re.finditer(r"`([^`]+)`", inner):
                    if sm.start() > sub_pos:
                        runs.append(
                            self._run_xml(
                                inner[sub_pos : sm.start()],
                                bold=True,
                                italic=default_italic,
                                size_hp=size_hp,
                                color=default_color,
                            )
                        )
                    runs.append(
                        self._run_xml(
                            sm.group(1),
                            bold=True,
                            italic=default_italic,
                            code=True,
                            size_hp=size_hp,
                            color=default_color,
                        )
                    )
                    sub_pos = sm.end()
                if sub_pos < len(inner):
                    runs.append(
                        self._run_xml(
                            inner[sub_pos:],
                            bold=True,
                            italic=default_italic,
                            size_hp=size_hp,
                            color=default_color,
                        )
                    )
            elif tok.startswith("*"):
                runs.append(
                    self._run_xml(
                        tok[1:-1],
                        bold=default_bold,
                        italic=True,
                        size_hp=size_hp,
                        color=default_color,
                    )
                )
            pos = m.end()

        if pos < len(text):
            runs.append(
                self._run_xml(
                    text[pos:],
                    bold=default_bold,
                    italic=default_italic,
                    size_hp=size_hp,
                    color=default_color,
                )
            )
        return "".join(runs)

    def make_p(
        self,
        text: str,
        *,
        align: str = "both",
        before: int = 0,
        after: int = 120,
        line: int = 290,
        size_hp: int = 22,
        color: str = "111111",
        bold: bool = False,
        italic: bool = False,
        keep_next: bool = False,
        page_break_before: bool = False,
        bookmark_name: str | None = None,
    ) -> str:
        ppr = [f'<w:jc w:val="{align}"/>', f'<w:spacing w:before="{before}" w:after="{after}" w:line="{line}" w:lineRule="auto"/>']
        if keep_next:
            ppr.append("<w:keepNext/>")
        if page_break_before:
            ppr.append("<w:pageBreakBefore/>")
        bm_start = bm_end = ""
        if bookmark_name:
            bmid = self._bm_id
            self._bm_id += 1
            bm_start = f'<w:bookmarkStart w:id="{bmid}" w:name="{bookmark_name}"/>'
            bm_end = f'<w:bookmarkEnd w:id="{bmid}"/>'
        runs = self.inline_runs(text, size_hp=size_hp, default_color=color, default_bold=bold, default_italic=italic)
        return f'<w:p><w:pPr>{"".join(ppr)}</w:pPr>{bm_start}{runs}{bm_end}</w:p>'

    def make_image_p(self, img_path: Path, *, max_w_cm: float = 14.5, max_h_cm: float = 9.2, before: int = 80, after: int = 40) -> str:
        rid = self.register_image(img_path)
        px_w, px_h = get_image_size(img_path)
        aspect = px_w / max(px_h, 1)
        w_cm = max_w_cm
        h_cm = w_cm / aspect
        if h_cm > max_h_cm:
            h_cm = max_h_cm
            w_cm = h_cm * aspect
        cx = int(w_cm * 360000)
        cy = int(h_cm * 360000)
        docpr = self._docpr_id
        self._docpr_id += 1
        nm = xml_esc(img_path.name)
        return (
            f'<w:p><w:pPr><w:jc w:val="center"/><w:spacing w:before="{before}" w:after="{after}"/><w:keepNext/></w:pPr>'
            "<w:r><w:drawing>"
            '<wp:inline distT="0" distB="0" distL="0" distR="0">'
            f'<wp:extent cx="{cx}" cy="{cy}"/>'
            '<wp:effectExtent l="0" t="0" r="0" b="0"/>'
            f'<wp:docPr id="{docpr}" name="Picture {docpr}" descr="{nm}"/>'
            "<wp:cNvGraphicFramePr><a:graphicFrameLocks noChangeAspect=\"1\"/></wp:cNvGraphicFramePr>"
            "<a:graphic><a:graphicData uri=\"http://schemas.openxmlformats.org/drawingml/2006/picture\">"
            f'<pic:pic><pic:nvPicPr><pic:cNvPr id="{docpr}" name="{nm}"/><pic:cNvPicPr/></pic:nvPicPr>'
            f'<pic:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
            f'<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
            '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic>'
            "</a:graphicData></a:graphic></wp:inline></w:drawing></w:r></w:p>"
        )

    def add_cover_page(self, title: str, student_lines: list[str]) -> None:
        if LOGO_PATH.exists():
            self.body_xml.append(self.make_image_p(LOGO_PATH, max_w_cm=8.8, max_h_cm=3.0, before=120, after=1100))
        self.body_xml.append(
            self.make_p(title, align="center", before=600, after=500, line=275, size_hp=44, bold=True, color="0F172A")
        )
        self.body_xml.append(
            self.make_p("Proyecto Integrador", align="center", before=200, after=80, size_hp=29, bold=True, color="111111")
        )
        self.body_xml.append(
            self.make_p("Realidad Virtual", align="center", before=0, after=2100, size_hp=28, color="4B5563")
        )
        self.body_xml.append(self.make_p("Profesores", align="left", before=200, after=80, size_hp=23, bold=True))
        self.body_xml.append(self.make_p("Profesor Titular: Javier Rosenstein", align="left", before=0, after=40, size_hp=22))
        self.body_xml.append(self.make_p("JTP: Carlos Tomba", align="left", before=0, after=280, size_hp=22))
        self.body_xml.append(self.make_p("Alumnos", align="left", before=60, after=80, size_hp=23, bold=True))
        for sl in student_lines:
            self.body_xml.append(self.make_p(sl, align="left", before=0, after=60, size_hp=22))
        # Page break after cover
        self.body_xml.append('<w:p><w:r><w:br w:type="page"/></w:r></w:p>')

    def add_toc_page(self, toc_entries: list[tuple[int, str, str]], page_map: dict[str, int]) -> None:
        self.body_xml.append(self.make_p("Índice", align="left", before=80, after=240, size_hp=38, bold=True, color="0F172A"))
        right_tab = 9400
        for lvl, title, sec_id in toc_entries:
            clean_t = clean_inline_math(title).replace("`", "")
            indent = 0 if lvl == 2 else (340 if lvl == 3 else 680)
            is_bold = lvl == 2
            sz = 22 if lvl == 2 else (21 if lvl == 3 else 20)
            pg_str = str(page_map.get(sec_id, ""))
            bm_anchor = sec_id.replace("-", "_")

            r_title = self._run_xml(clean_t + " ", bold=is_bold, size_hp=sz, color="111111")
            r_tab = f'<w:r><w:rPr><w:sz w:val="{sz}"/></w:rPr><w:tab/></w:r>'
            r_pg = self._run_xml(" " + pg_str if pg_str else "", bold=is_bold, size_hp=sz, color="111111")

            self.body_xml.append(
                f'<w:p><w:pPr><w:tabs><w:tab w:val="right" w:leader="dot" w:pos="{right_tab}"/></w:tabs>'
                f'<w:ind w:left="{indent}"/>'
                f'<w:spacing w:before="{70 if lvl == 2 else 30}" w:after="45" w:line="250" w:lineRule="auto"/></w:pPr>'
                f'<w:hyperlink w:anchor="{bm_anchor}" w:history="1">{r_title}{r_tab}{r_pg}</w:hyperlink></w:p>'
            )
        self.body_xml.append('<w:p><w:r><w:br w:type="page"/></w:r></w:p>')

    def add_heading(self, lvl: int, text: str, sec_id: str) -> None:
        bm = sec_id.replace("-", "_")
        if lvl == 2:
            self.body_xml.append(
                self.make_p(text, align="left", before=260, after=120, line=260, size_hp=34, bold=True, color="0F172A", keep_next=True, bookmark_name=bm)
            )
        elif lvl == 3:
            self.body_xml.append(
                self.make_p(text, align="left", before=200, after=90, line=260, size_hp=27, bold=True, color="0F172A", keep_next=True, bookmark_name=bm)
            )
        else:
            self.body_xml.append(
                self.make_p(text, align="left", before=160, after=70, line=255, size_hp=23, bold=True, color="1E293B", keep_next=True, bookmark_name=bm)
            )

    def add_list_items(self, items: list[tuple[int, str, str]]) -> None:
        for lvl, marker, text in items:
            left = 440 if lvl == 0 else 800
            hanging = 250
            prefix = self._run_xml(f"{marker}\t", bold=False, size_hp=22, color="111111")
            self.body_xml.append(
                f'<w:p><w:pPr><w:jc w:val="both"/><w:tabs><w:tab w:val="left" w:pos="{left}"/></w:tabs>'
                f'<w:ind w:left="{left}" w:hanging="{hanging}"/>'
                f'<w:spacing w:before="20" w:after="90" w:line="285" w:lineRule="auto"/></w:pPr>'
                f"{prefix}{self.inline_runs(text, size_hp=22)}</w:p>"
            )

    def add_display_math(self, expr: str) -> None:
        pretty = convert_math_expr(expr)
        run = self._run_xml(pretty, italic=True, size_hp=24, color="0F172A", font_override="Cambria Math")
        self.body_xml.append(
            f'<w:p><w:pPr><w:jc w:val="center"/><w:spacing w:before="120" w:after="120" w:line="280" w:lineRule="auto"/></w:pPr>{run}</w:p>'
        )

    def add_code_block(self, lang: str, code_lines: list[str]) -> None:
        paras = []
        if lang:
            paras.append(
                f'<w:p><w:pPr><w:spacing w:before="0" w:after="60" w:line="220" w:lineRule="auto"/></w:pPr>'
                f'{self._run_xml(lang.upper(), bold=True, size_hp=16, color="475569")}</w:p>'
            )
        for idx, cl in enumerate(code_lines):
            after = 20 if idx < len(code_lines) - 1 else 0
            r = self._run_xml(cl if cl else " ", size_hp=17, color="0F172A", font_override="Consolas")
            paras.append(
                f'<w:p><w:pPr><w:spacing w:before="0" w:after="{after}" w:line="225" w:lineRule="auto"/></w:pPr>{r}</w:p>'
            )
        inner = "".join(paras)
        self.body_xml.append(
            '<w:tbl><w:tblPr><w:tblW w:w="9400" w:type="dxa"/><w:jc w:val="center"/>'
            "<w:tblBorders>"
            '<w:top w:val="single" w:sz="6" w:space="0" w:color="CBD5E1"/>'
            '<w:left w:val="single" w:sz="6" w:space="0" w:color="CBD5E1"/>'
            '<w:bottom w:val="single" w:sz="6" w:space="0" w:color="CBD5E1"/>'
            '<w:right w:val="single" w:sz="6" w:space="0" w:color="CBD5E1"/>'
            "</w:tblBorders>"
            '<w:tblCellMar><w:top w:w="100" w:type="dxa"/><w:left w:w="150" w:type="dxa"/>'
            '<w:bottom w:w="100" w:type="dxa"/><w:right w:w="150" w:type="dxa"/></w:tblCellMar>'
            "</w:tblPr><w:tblGrid><w:gridCol w:w=\"9400\"/></w:tblGrid>"
            f'<w:tr><w:trPr><w:cantSplit/></w:trPr><w:tc><w:tcPr><w:tcW w:w="9400" w:type="dxa"/>'
            f'<w:shd w:val="clear" w:color="auto" w:fill="F8FAFC"/></w:tcPr>{inner}</w:tc></w:tr></w:tbl>'
            '<w:p><w:pPr><w:spacing w:before="0" w:after="80"/></w:pPr></w:p>'
        )

    def add_placeholder_box(self, text: str) -> None:
        p = self.make_p(text, align="center", before=120, after=120, size_hp=20, color="1E3A8A")
        self.body_xml.append(
            '<w:tbl><w:tblPr><w:tblW w:w="9000" w:type="dxa"/><w:jc w:val="center"/>'
            "<w:tblBorders>"
            '<w:top w:val="dashed" w:sz="10" w:space="0" w:color="2563EB"/>'
            '<w:left w:val="dashed" w:sz="10" w:space="0" w:color="2563EB"/>'
            '<w:bottom w:val="dashed" w:sz="10" w:space="0" w:color="2563EB"/>'
            '<w:right w:val="dashed" w:sz="10" w:space="0" w:color="2563EB"/>'
            "</w:tblBorders>"
            '<w:tblCellMar><w:top w:w="180" w:type="dxa"/><w:left w:w="220" w:type="dxa"/>'
            '<w:bottom w:w="180" w:type="dxa"/><w:right w:w="220" w:type="dxa"/></w:tblCellMar>'
            "</w:tblPr><w:tblGrid><w:gridCol w:w=\"9000\"/></w:tblGrid>"
            '<w:tr><w:trPr><w:trHeight w:val="2800" w:hRule="atLeast"/><w:cantSplit/></w:trPr>'
            '<w:tc><w:tcPr><w:tcW w:w="9000" w:type="dxa"/><w:vAlign w:val="center"/>'
            f'<w:shd w:val="clear" w:color="auto" w:fill="F0F7FF"/></w:tcPr>{p}</w:tc></w:tr></w:tbl>'
            '<w:p><w:pPr><w:spacing w:before="0" w:after="80"/></w:pPr></w:p>'
        )

    def add_table(self, t_lines: list[str]) -> None:
        headers = split_md_row(t_lines[0])
        align_cells = split_md_row(t_lines[1])
        ncols = max(len(headers), 1)
        total_w = 9400
        col_w = total_w // ncols
        aligns = []
        for ac in align_cells:
            ac = ac.strip()
            if ac.startswith(":") and ac.endswith(":"):
                aligns.append("center")
            elif ac.endswith(":"):
                aligns.append("right")
            else:
                aligns.append("left")

        grid = "".join(f'<w:gridCol w:w="{col_w}"/>' for _ in range(ncols))
        rows_xml: list[str] = []

        # Header row
        h_tcs = []
        for idx, h in enumerate(headers):
            al = aligns[idx] if idx < len(aligns) else "left"
            p = self.make_p(h, align=al, before=20, after=20, line=240, size_hp=19, color="FFFFFF", bold=True)
            h_tcs.append(
                f'<w:tc><w:tcPr><w:tcW w:w="{col_w}" w:type="dxa"/><w:vAlign w:val="center"/>'
                f'<w:shd w:val="clear" w:color="auto" w:fill="1F2937"/></w:tcPr>{p}</w:tc>'
            )
        rows_xml.append(f'<w:tr><w:trPr><w:tblHeader/><w:cantSplit/></w:trPr>{"".join(h_tcs)}</w:tr>')

        # Body rows
        for r_idx, rline in enumerate(t_lines[2:]):
            if not rline.strip():
                continue
            cells = split_md_row(rline)
            while len(cells) < ncols:
                cells.append("")
            fill = "F8FAFC" if r_idx % 2 == 1 else "FFFFFF"
            b_tcs = []
            for idx, c in enumerate(cells[:ncols]):
                al = aligns[idx] if idx < len(aligns) else "left"
                p = self.make_p(c, align=al, before=20, after=20, line=245, size_hp=19, color="111111")
                b_tcs.append(
                    f'<w:tc><w:tcPr><w:tcW w:w="{col_w}" w:type="dxa"/><w:vAlign w:val="top"/>'
                    f'<w:shd w:val="clear" w:color="auto" w:fill="{fill}"/></w:tcPr>{p}</w:tc>'
                )
            rows_xml.append(f'<w:tr><w:trPr><w:cantSplit/></w:trPr>{"".join(b_tcs)}</w:tr>')

        self.body_xml.append(
            f'<w:tbl><w:tblPr><w:tblW w:w="{total_w}" w:type="dxa"/><w:jc w:val="center"/>'
            "<w:tblBorders>"
            '<w:top w:val="single" w:sz="6" w:space="0" w:color="1F2937"/>'
            '<w:left w:val="single" w:sz="4" w:space="0" w:color="CBD5E1"/>'
            '<w:bottom w:val="single" w:sz="6" w:space="0" w:color="94A3B8"/>'
            '<w:right w:val="single" w:sz="4" w:space="0" w:color="CBD5E1"/>'
            '<w:insideH w:val="single" w:sz="4" w:space="0" w:color="CBD5E1"/>'
            '<w:insideV w:val="single" w:sz="4" w:space="0" w:color="CBD5E1"/>'
            "</w:tblBorders>"
            '<w:tblCellMar><w:top w:w="70" w:type="dxa"/><w:left w:w="100" w:type="dxa"/>'
            '<w:bottom w:w="70" w:type="dxa"/><w:right w:w="100" w:type="dxa"/></w:tblCellMar>'
            f"</w:tblPr><w:tblGrid>{grid}</w:tblGrid>{''.join(rows_xml)}</w:tbl>"
            '<w:p><w:pPr><w:spacing w:before="0" w:after="80"/></w:pPr></w:p>'
        )

    def _build_header_xml(self, has_logo: bool) -> str:
        if has_logo:
            cx, cy = int(5.4 * 360000), int(1.42 * 360000)
            left_cell = (
                '<w:p><w:pPr><w:spacing w:before="0" w:after="40"/></w:pPr>'
                "<w:r><w:drawing>"
                '<wp:inline distT="0" distB="0" distL="0" distR="0">'
                f'<wp:extent cx="{cx}" cy="{cy}"/><wp:effectExtent l="0" t="0" r="0" b="0"/>'
                '<wp:docPr id="1" name="HeaderLogo"/>'
                "<wp:cNvGraphicFramePr><a:graphicFrameLocks noChangeAspect=\"1\"/></wp:cNvGraphicFramePr>"
                "<a:graphic><a:graphicData uri=\"http://schemas.openxmlformats.org/drawingml/2006/picture\">"
                '<pic:pic><pic:nvPicPr><pic:cNvPr id="1" name="logo"/><pic:cNvPicPr/></pic:nvPicPr>'
                '<pic:blipFill><a:blip r:embed="rIdHdrLogo"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
                f'<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
                '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic>'
                "</a:graphicData></a:graphic></wp:inline></w:drawing></w:r></w:p>"
            )
        else:
            left_cell = self.make_p("UNCUYO · Facultad de Ingeniería", align="left", before=0, after=20, size_hp=19, bold=True)

        right_cell = (
            self.make_p("Realidad Virtual", align="right", before=0, after=10, line=220, size_hp=19, color="111111")
            + self.make_p("Proyecto Integrador", align="right", before=0, after=40, line=220, size_hp=19, color="111111")
        )
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:hdr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
            'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
            'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
            'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">'
            '<w:tbl><w:tblPr><w:tblW w:w="9400" w:type="dxa"/>'
            "<w:tblBorders>"
            '<w:top w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
            '<w:left w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
            '<w:bottom w:val="single" w:sz="12" w:space="0" w:color="111111"/>'
            '<w:right w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
            '<w:insideV w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
            "</w:tblBorders></w:tblPr>"
            '<w:tblGrid><w:gridCol w:w="5200"/><w:gridCol w:w="4200"/></w:tblGrid>'
            f'<w:tr><w:tc><w:tcPr><w:tcW w:w="5200" w:type="dxa"/><w:vAlign w:val="bottom"/></w:tcPr>{left_cell}</w:tc>'
            f'<w:tc><w:tcPr><w:tcW w:w="4200" w:type="dxa"/><w:vAlign w:val="bottom"/></w:tcPr>{right_cell}</w:tc></w:tr>'
            "</w:tbl>"
            '<w:p><w:pPr><w:spacing w:before="0" w:after="40"/></w:pPr></w:p>'
            "</w:hdr>"
        )

    def _build_footer_xml(self) -> str:
        left_p = self.make_p("García, Ezequiel; Albanez, Luciano", align="left", before=60, after=0, size_hp=19, italic=True)
        right_p = (
            '<w:p><w:pPr><w:jc w:val="right"/><w:spacing w:before="60" w:after="0"/></w:pPr>'
            + self._run_xml("Página ", size_hp=19)
            + '<w:fldSimple w:instr=" PAGE "><w:r><w:rPr><w:sz w:val="19"/></w:rPr><w:t>2</w:t></w:r></w:fldSimple>'
            + self._run_xml(" de ", size_hp=19)
            + '<w:fldSimple w:instr=" NUMPAGES "><w:r><w:rPr><w:sz w:val="19"/></w:rPr><w:t>30</w:t></w:r></w:fldSimple>'
            + "</w:p>"
        )
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:ftr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            '<w:tbl><w:tblPr><w:tblW w:w="9400" w:type="dxa"/>'
            "<w:tblBorders>"
            '<w:top w:val="single" w:sz="12" w:space="0" w:color="111111"/>'
            '<w:left w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
            '<w:bottom w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
            '<w:right w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
            '<w:insideV w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
            "</w:tblBorders></w:tblPr>"
            '<w:tblGrid><w:gridCol w:w="5600"/><w:gridCol w:w="3800"/></w:tblGrid>'
            f'<w:tr><w:tc><w:tcPr><w:tcW w:w="5600" w:type="dxa"/></w:tcPr>{left_p}</w:tc>'
            f'<w:tc><w:tcPr><w:tcW w:w="3800" w:type="dxa"/></w:tcPr>{right_p}</w:tc></w:tr>'
            "</w:tbl></w:ftr>"
        )

    def save(self, out_path: Path) -> None:
        has_logo = LOGO_PATH.exists()
        sect_pr = (
            "<w:sectPr>"
            '<w:headerReference w:type="default" r:id="rIdHeader1"/>'
            '<w:footerReference w:type="default" r:id="rIdFooter1"/>'
            '<w:pgSz w:w="11906" w:h="16838"/>'
            '<w:pgMar w:top="1360" w:right="1247" w:bottom="1300" w:left="1247" '
            'w:header="620" w:footer="680" w:gutter="0"/>'
            "<w:titlePg/>"
            "</w:sectPr>"
        )
        document_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
            'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
            'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
            'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">'
            "<w:body>"
            + "".join(self.body_xml)
            + sect_pr
            + "</w:body></w:document>"
        )

        rels = [
            '<Relationship Id="rIdStyles" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>',
            '<Relationship Id="rIdHeader1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/header" Target="header1.xml"/>',
            '<Relationship Id="rIdFooter1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" Target="footer1.xml"/>',
        ]
        has_png = False
        has_jpg = has_logo
        for rid, _, media_name in self.doc_media:
            rels.append(
                f'<Relationship Id="{rid}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/{media_name}"/>'
            )
            if media_name.endswith(".png"):
                has_png = True
            elif media_name.endswith(".jpg"):
                has_jpg = True

        doc_rels_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            + "".join(rels)
            + "</Relationships>"
        )

        hdr_rels_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            + (
                '<Relationship Id="rIdHdrLogo" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/header_logo.jpg"/>'
                if has_logo
                else ""
            )
            + "</Relationships>"
        )

        root_rels_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
            '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>'
            "</Relationships>"
        )

        core_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/">'
            "<dc:title>Informe Técnico — ArcSim_VR</dc:title>"
            "<dc:creator>García, Ezequiel; Albanez, Luciano</dc:creator>"
            "</cp:coreProperties>"
        )
        app_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">'
            "<Application>ArcSim_VR Report Docx Builder</Application></Properties>"
        )
        styles_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            "<w:docDefaults><w:rPrDefault><w:rPr>"
            '<w:rFonts w:ascii="Segoe UI" w:hAnsi="Segoe UI" w:cs="Segoe UI"/>'
            '<w:sz w:val="22"/><w:szCs w:val="22"/>'
            '<w:lang w:val="es-AR" w:eastAsia="es-AR" w:bidi="ar-SA"/>'
            "</w:rPr></w:rPrDefault><w:pPrDefault><w:pPr>"
            '<w:spacing w:after="120" w:line="290" w:lineRule="auto"/>'
            "</w:pPr></w:pPrDefault></w:docDefaults>"
            '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>'
            "</w:styles>"
        )

        ext_defaults = [
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
            '<Default Extension="xml" ContentType="application/xml"/>',
        ]
        if has_png:
            ext_defaults.append('<Default Extension="png" ContentType="image/png"/>')
        if has_jpg:
            ext_defaults.append('<Default Extension="jpg" ContentType="image/jpeg"/>')

        content_types_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            + "".join(ext_defaults)
            + '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
            '<Override PartName="/word/header1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"/>'
            '<Override PartName="/word/footer1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>'
            '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
            '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
            "</Types>"
        )

        with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("[Content_Types].xml", content_types_xml)
            zf.writestr("_rels/.rels", root_rels_xml)
            zf.writestr("docProps/core.xml", core_xml)
            zf.writestr("docProps/app.xml", app_xml)
            zf.writestr("word/document.xml", document_xml)
            zf.writestr("word/styles.xml", styles_xml)
            zf.writestr("word/header1.xml", self._build_header_xml(has_logo))
            zf.writestr("word/footer1.xml", self._build_footer_xml())
            zf.writestr("word/_rels/document.xml.rels", doc_rels_xml)
            zf.writestr("word/_rels/header1.xml.rels", hdr_rels_xml)
            if has_logo:
                zf.writestr("word/media/header_logo.jpg", LOGO_PATH.read_bytes())
            for _, img_path, media_name in self.doc_media:
                zf.writestr(f"word/media/{media_name}", img_path.read_bytes())


def main() -> int:
    out_docx = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DEFAULT_DOCX
    md_text = MD_PATH.read_text(encoding="utf-8")

    # Separar bloque portada del cuerpo después de <!-- INDICE -->
    parts = md_text.split("<!-- INDICE -->", 1)
    cover_md = parts[0] if len(parts) > 1 else ""
    body_md = parts[1] if len(parts) > 1 else md_text

    title_m = re.search(r"^#\s+(.+)$", cover_md, re.M)
    doc_title = title_m.group(1).strip() if title_m else "Simulador de Realidad Mixta SMAW (ArcSim_VR)"
    student_lines = [ln.strip() for ln in cover_md.splitlines() if "Legajo" in ln]

    body_lines = body_md.splitlines()

    # Pre-escanear encabezados (para Índice, coincidiendo con sec-1..sec-N del PDF) y bloques Mermaid
    toc_entries: list[tuple[int, str, str]] = []
    mermaid_codes: list[str] = []
    sec_counter = 0
    in_fence = False
    cur_fence_lang = ""
    cur_fence_lines: list[str] = []

    for ln in body_lines:
        st = ln.strip()
        if st.startswith("```"):
            if not in_fence:
                in_fence = True
                cur_fence_lang = st[3:].strip().lower()
                cur_fence_lines = []
            else:
                if cur_fence_lang == "mermaid":
                    mermaid_codes.append("\n".join(cur_fence_lines))
                in_fence = False
            continue
        if in_fence:
            cur_fence_lines.append(ln)
            continue
        mh = re.match(r"^(#{2,4})\s+(.+)$", st)
        if mh:
            sec_counter += 1
            toc_entries.append((len(mh.group(1)), mh.group(2).strip(), f"sec-{sec_counter}"))

    page_map = extract_pdf_toc_pages(PDF_REF)

    with tempfile.TemporaryDirectory(prefix="arcsim_docx_mmd_") as tmp_dir_str:
        tmp_dir = Path(tmp_dir_str)
        print(f"[INFO] Renderizando {len(mermaid_codes)} diagramas Mermaid a PNG para Word...")
        mmd_pngs = render_mermaid_diagrams(mermaid_codes, tmp_dir)

        builder = ReportDocxBuilder()
        builder.add_cover_page(doc_title, student_lines)
        builder.add_toc_page(toc_entries, page_map)

        i = 0
        n = len(body_lines)
        h_idx = 0
        mmd_idx = 0

        while i < n:
            line = body_lines[i]
            s = line.strip()
            if not s or s.startswith("<!--"):
                i += 1
                continue

            # Headings
            mh = re.match(r"^(#{2,4})\s+(.+)$", s)
            if mh:
                lvl, h_txt, sec_id = toc_entries[h_idx]
                h_idx += 1
                builder.add_heading(lvl, h_txt, sec_id)
                i += 1
                continue

            # Fenced code or Mermaid
            if s.startswith("```"):
                lang = s[3:].strip()
                i += 1
                c_lines = []
                while i < n and not body_lines[i].strip().startswith("```"):
                    c_lines.append(body_lines[i])
                    i += 1
                i += 1  # skip closing ```
                if lang.lower() == "mermaid":
                    png = mmd_pngs[mmd_idx] if mmd_idx < len(mmd_pngs) else None
                    mmd_idx += 1
                    if png is not None and png.exists():
                        builder.body_xml.append(builder.make_image_p(png, max_w_cm=15.4, max_h_cm=9.5))
                    else:
                        builder.add_code_block("mermaid", c_lines)
                    # Optional italic caption right after mermaid
                    if i < n and re.match(r"^\*[^*].*\*$", body_lines[i].strip()):
                        cap = body_lines[i].strip()[1:-1]
                        builder.body_xml.append(
                            builder.make_p(cap, align="center", before=0, after=120, size_hp=19, color="334155", italic=True)
                        )
                        i += 1
                else:
                    builder.add_code_block(lang, c_lines)
                continue

            # Display math $$ ... $$
            if s.startswith("$$"):
                if s.endswith("$$") and len(s) > 4:
                    expr = s[2:-2]
                    i += 1
                else:
                    i += 1
                    mlines = []
                    while i < n and not body_lines[i].strip().endswith("$$"):
                        mlines.append(body_lines[i].strip())
                        i += 1
                    if i < n:
                        mlines.append(body_lines[i].strip()[:-2])
                        i += 1
                    expr = " ".join(mlines)
                builder.add_display_math(expr)
                continue

            # Placeholder or blockquote
            if s.startswith(">"):
                ql = []
                while i < n and body_lines[i].strip().startswith(">"):
                    ql.append(re.sub(r"^>\s?", "", body_lines[i].strip()))
                    i += 1
                q_txt = " ".join(ql).strip()
                builder.add_placeholder_box(q_txt)
                continue

            # Markdown Table
            if "|" in s and i + 1 < n and re.match(r"^\s*\|?[\s:\-]+\|[\s:\-|]+$", body_lines[i + 1]):
                t_lines = [body_lines[i], body_lines[i + 1]]
                i += 2
                while i < n and "|" in body_lines[i] and body_lines[i].strip():
                    t_lines.append(body_lines[i])
                    i += 1
                builder.add_table(t_lines)
                continue

            # Image ![alt](path) + optional *caption*
            m_img = re.match(r"^!\[([^\]]*)\]\(([^)]+)\)$", s)
            if m_img:
                img_p = ROOT / m_img.group(2).strip()
                if img_p.exists():
                    builder.body_xml.append(builder.make_image_p(img_p, max_w_cm=14.8, max_h_cm=9.4))
                else:
                    builder.add_placeholder_box(f"**[IMAGEN NO ENCONTRADA: {m_img.group(2)}]**")
                i += 1
                if i < n and re.match(r"^\*[^*].*\*$", body_lines[i].strip()):
                    cap = body_lines[i].strip()[1:-1]
                    builder.body_xml.append(
                        builder.make_p(cap, align="center", before=0, after=120, size_hp=19, color="334155", italic=True)
                    )
                    i += 1
                continue

            # Lists (including multi-paragraph / display math continuation inside nested items)
            m_list = re.match(r"^(\s*)([*\-]|\d+\.)\s+(.*)$", line)
            if m_list:
                items: list[tuple[int, str, str]] = []
                while i < n:
                    ln_cur = body_lines[i]
                    sc = ln_cur.strip()
                    if not sc:
                        break
                    ml = re.match(r"^(\s*)([*\-]|\d+\.)\s+(.*)$", ln_cur)
                    if ml:
                        indent = len(ml.group(1))
                        lvl = 1 if indent >= 2 else 0
                        rm = ml.group(2)
                        marker = rm if rm.endswith(".") else ("•" if lvl == 0 else "◦")
                        items.append((lvl, marker, ml.group(3).strip()))
                        i += 1
                    elif sc.startswith("$$"):
                        # Flush accumulated list items, render display math, then continue!
                        builder.add_list_items(items)
                        items = []
                        if sc.endswith("$$") and len(sc) > 4:
                            builder.add_display_math(sc[2:-2])
                        i += 1
                    elif ln_cur.startswith("  ") and not sc.startswith(("```", ">", "![", "|", "#")):
                        if items:
                            items[-1] = (items[-1][0], items[-1][1], items[-1][2] + " " + sc)
                        else:
                            builder.body_xml.append(builder.make_p(sc, align="both", before=20, after=90))
                        i += 1
                    else:
                        break
                if items:
                    builder.add_list_items(items)
                continue

            # Normal paragraph
            p_lines = [s]
            i += 1
            while (
                i < n
                and body_lines[i].strip()
                and not body_lines[i].strip().startswith(("#", "```", ">", "![", "$$", "<!--"))
                and not re.match(r"^(\s*)([*\-]|\d+\.)\s+", body_lines[i])
            ):
                p_lines.append(body_lines[i].strip())
                i += 1
            builder.body_xml.append(builder.make_p(" ".join(p_lines)))

        builder.save(out_docx)

    print(f"[OK] Informe Word generado exitosamente: {out_docx} ({out_docx.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
