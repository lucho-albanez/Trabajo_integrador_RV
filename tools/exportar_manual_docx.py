#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generador de Manual de Uso en formato Microsoft Word (.docx) nativo (OOXML).
Replica fielmente la estética, tipografía, colores, líneas divisorias,
recuadros y disposición de docs_referencia/Manual_de_uso.pdf sin requerir
librerías externas más allá de la biblioteca estándar de Python (usa Pillow
opcionalmente si está disponible para leer dimensiones exactas de imágenes).

Uso:
    python tools/exportar_manual_docx.py [salida.docx]
"""

from __future__ import annotations

import html
import re
import struct
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MD_PATH = ROOT / "manual_de_uso.md"
DEFAULT_DOCX = ROOT / "Manual_de_uso_preliminar.docx"

# Mapa automático opcional: si el usuario coloca cualquiera de estos archivos en
# docs_referencia/, el script reemplaza automáticamente el marcador [INSERTAR IMAGEN Mx]
AUTO_IMAGE_MAP = {
    "IMAGEN M1": ["docs_referencia/manual_m1_portaelectrodo.png", "docs_referencia/manual_m1_portaelectrodo.jpg", "docs_referencia/figura_4_portaelectrodo.jpg"],
    "IMAGEN M2": ["docs_referencia/figura_7_opencv.png", "docs_referencia/figura_7_opencv.jpg", "docs_referencia/manual_m2_opencv.png"],
    "IMAGEN M3": ["docs_referencia/figura_5a_menu.png", "docs_referencia/figura_5a_menu.jpg", "docs_referencia/manual_m3_menu.png"],
    "IMAGEN M4": ["docs_referencia/figura_5b_taller.png", "docs_referencia/figura_5b_taller.jpg", "docs_referencia/manual_m4_taller.png"],
    "IMAGEN M5": ["docs_referencia/figura_5c_soldando.png", "docs_referencia/figura_5c_soldando.jpg", "docs_referencia/manual_m5_soldando.png"],
    "IMAGEN M6": ["docs_referencia/figura_5d_informe.png", "docs_referencia/figura_5d_informe.jpg", "docs_referencia/manual_m6_informe.png"],
}

# Colores semánticos para la sección "2. Significado del LED y la vibración"
LED_LABEL_COLORS = {
    "Violeta / Naranja:": "7C3AED",
    "Azul": "1D4ED8",
    "Verde": "15803D",
    "Amarillo:": "B45309",
    "Rojo": "DC2626",
    "Rojo fijo + vibración intensa al 100 %:": "B91C1C",
}


def get_image_size(path: Path) -> tuple[int, int]:
    """Obtiene (ancho_px, alto_px) leyendo cabeceras PNG/JPEG sin depender de paquetes externos."""
    data = path.read_bytes()
    # PNG
    if data[:8] == b"\x89PNG\r\n\x1a\n" and data[12:16] == b"IHDR":
        w, h = struct.unpack(">II", data[16:24])
        return int(w), int(h)
    # JPEG
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


def clean_tex_inline(text: str) -> str:
    """Convierte expresiones simples $...$ del Markdown a texto Unicode limpio para Word."""
    def repl(m: re.Match[str]) -> str:
        s = m.group(1)
        s = s.replace(r"\text{ a }", " a ")
        s = s.replace(r"\text{ s}", " s")
        s = s.replace(r"\text{ mm}", " mm")
        s = re.sub(r"\\text\{([^}]*)\}", r"\1", s)
        s = s.replace("{,}", ",")
        s = s.replace(r"^\circ", "°").replace(r"^{\circ}", "°")
        s = s.replace(r"\varnothing", "Ø")
        return s

    return re.sub(r"\$([^$]+)\$", repl, text)


def xml_esc(s: str) -> str:
    return html.escape(s, quote=True)


class DocxBuilder:
    def __init__(self) -> None:
        self.body_xml: list[str] = []
        self.media: list[tuple[str, Path, str]] = []  # (rId, path, media_name)
        self._docpr_id = 1

    def register_image(self, img_path: Path) -> str:
        idx = len(self.media) + 1
        rid = f"rIdImg{idx}"
        ext = img_path.suffix.lower()
        if ext == ".jpeg":
            ext = ".jpg"
        media_name = f"image{idx}{ext}"
        self.media.append((rid, img_path, media_name))
        return rid

    def _run_xml(
        self,
        text: str,
        *,
        bold: bool = False,
        italic: bool = False,
        code: bool = False,
        size_hp: int = 22,
        color: str = "111111",
    ) -> str:
        if not text:
            return ""
        rpr: list[str] = []
        font = "Consolas" if code else "Segoe UI"
        rpr.append(f'<w:rFonts w:ascii="{font}" w:hAnsi="{font}" w:cs="{font}"/>')
        if bold:
            rpr.append("<w:b/><w:bCs/>")
        if italic:
            rpr.append("<w:i/><w:iCs/>")
        rpr.append(f'<w:color w:val="{color}"/>')
        sz = size_hp - 2 if code else size_hp
        rpr.append(f'<w:sz w:val="{sz}"/><w:szCs w:val="{sz}"/>')
        if code:
            rpr.append('<w:shd w:val="clear" w:color="auto" w:fill="F1F5F9"/>')
        rpr_str = "".join(rpr)
        return f'<w:r><w:rPr>{rpr_str}</w:rPr><w:t xml:space="preserve">{xml_esc(text)}</w:t></w:r>'

    def inline_runs(
        self,
        text: str,
        *,
        size_hp: int = 22,
        default_color: str = "111111",
        default_bold: bool = False,
        default_italic: bool = False,
        color_first_bold_map: dict[str, str] | None = None,
    ) -> str:
        text = clean_tex_inline(text)
        # Tokenize `code`, **bold**, *italic*
        token_re = re.compile(r"(`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*)")
        pos = 0
        runs: list[str] = []
        first_bold_seen = False

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
            if tok.startswith("`"):
                inner = tok[1:-1]
                runs.append(
                    self._run_xml(
                        inner,
                        bold=default_bold,
                        italic=default_italic,
                        code=True,
                        size_hp=size_hp,
                        color="0F172A",
                    )
                )
            elif tok.startswith("**"):
                inner = tok[2:-2]
                # Permitir `codigo` dentro de **negrita**
                b_color = default_color
                if color_first_bold_map and not first_bold_seen:
                    first_bold_seen = True
                    for k, hex_c in color_first_bold_map.items():
                        if inner.strip() == k or inner.strip().startswith(k):
                            b_color = hex_c
                            break
                sub_pos = 0
                for sm in re.finditer(r"`([^`]+)`", inner):
                    if sm.start() > sub_pos:
                        runs.append(
                            self._run_xml(
                                inner[sub_pos : sm.start()],
                                bold=True,
                                italic=default_italic,
                                size_hp=size_hp,
                                color=b_color,
                            )
                        )
                    runs.append(
                        self._run_xml(
                            sm.group(1),
                            bold=True,
                            italic=default_italic,
                            code=True,
                            size_hp=size_hp,
                            color=b_color,
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
                            color=b_color,
                        )
                    )
            elif tok.startswith("*"):
                inner = tok[1:-1]
                runs.append(
                    self._run_xml(
                        inner,
                        bold=default_bold,
                        italic=True,
                        size_hp=size_hp,
                        color="334155" if default_color == "111111" else default_color,
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

    def add_title(self, text: str) -> None:
        runs = self.inline_runs(text, size_hp=42, default_color="0F172A", default_bold=True)
        self.body_xml.append(
            f'<w:p><w:pPr><w:spacing w:before="0" w:after="100" w:line="265" w:lineRule="auto"/>'
            f"<w:keepNext/></w:pPr>{runs}</w:p>"
        )

    def add_subtitle_blue(self, text: str) -> None:
        runs = self.inline_runs(text, size_hp=34, default_color="4A86E8", default_bold=True)
        self.body_xml.append(
            f'<w:p><w:pPr><w:spacing w:before="40" w:after="140" w:line="260" w:lineRule="auto"/>'
            f"<w:keepNext/></w:pPr>{runs}</w:p>"
        )

    def add_hr(self) -> None:
        self.body_xml.append(
            '<w:p><w:pPr><w:spacing w:before="80" w:after="140" w:line="60" w:lineRule="exact"/>'
            '<w:pBdr><w:bottom w:val="single" w:sz="6" w:space="1" w:color="7F8C8D"/></w:pBdr>'
            "</w:pPr></w:p>"
        )

    def add_h2(self, text: str) -> None:
        runs = self.inline_runs(text, size_hp=32, default_color="0F172A", default_bold=True)
        self.body_xml.append(
            f'<w:p><w:pPr><w:spacing w:before="160" w:after="120" w:line="265" w:lineRule="auto"/>'
            f"<w:keepNext/></w:pPr>{runs}</w:p>"
        )

    def add_h3(self, text: str) -> None:
        runs = self.inline_runs(text, size_hp=24, default_color="0F172A", default_bold=True)
        self.body_xml.append(
            f'<w:p><w:pPr><w:spacing w:before="100" w:after="80" w:line="265" w:lineRule="auto"/>'
            f"<w:keepNext/></w:pPr>{runs}</w:p>"
        )

    def make_paragraph_xml(
        self,
        text: str,
        *,
        align: str = "left",
        before: int = 0,
        after: int = 120,
        left_indent: int = 0,
        hanging: int = 0,
        size_hp: int = 22,
        color: str = "111111",
        bold: bool = False,
        italic: bool = False,
        prefix_run: str = "",
        color_first_bold_map: dict[str, str] | None = None,
    ) -> str:
        ind = f'<w:ind w:left="{left_indent}" w:hanging="{hanging}"/>' if (left_indent or hanging) else ""
        jc = f'<w:jc w:val="{align}"/>' if align != "left" else ""
        runs = prefix_run + self.inline_runs(
            text,
            size_hp=size_hp,
            default_color=color,
            default_bold=bold,
            default_italic=italic,
            color_first_bold_map=color_first_bold_map,
        )
        return (
            f'<w:p><w:pPr>{jc}{ind}<w:spacing w:before="{before}" w:after="{after}" '
            f'w:line="295" w:lineRule="auto"/></w:pPr>{runs}</w:p>'
        )

    def add_paragraph(self, text: str) -> None:
        self.body_xml.append(self.make_paragraph_xml(text, before=0, after=120))

    def make_list_item_xml(
        self,
        marker: str,
        text: str,
        *,
        level: int = 0,
        color_first_bold_map: dict[str, str] | None = None,
    ) -> str:
        left = 500 if level == 0 else 880
        hanging = 280
        prefix = self._run_xml(f"{marker}\t", bold=False, size_hp=22, color="111111")
        return (
            f'<w:p><w:pPr><w:tabs><w:tab w:val="left" w:pos="{left}"/></w:tabs>'
            f'<w:ind w:left="{left}" w:hanging="{hanging}"/>'
            f'<w:spacing w:before="20" w:after="95" w:line="285" w:lineRule="auto"/></w:pPr>'
            f"{prefix}"
            + self.inline_runs(text, size_hp=22, color_first_bold_map=color_first_bold_map)
            + "</w:p>"
        )

    def add_callout_box(self, lines: list[str]) -> None:
        """Recuadro centrado con borde negro fino idéntico al de la Sección 3 del manual modelo."""
        paras = []
        for idx, ln in enumerate(lines):
            after = 40 if idx < len(lines) - 1 else 0
            paras.append(self.make_paragraph_xml(ln.strip(), align="center", before=0, after=after, size_hp=22))
        inner = "".join(paras)
        self.body_xml.append(
            '<w:tbl><w:tblPr><w:tblW w:w="5200" w:type="dxa"/><w:jc w:val="center"/>'
            '<w:tblBorders>'
            '<w:top w:val="single" w:sz="8" w:space="0" w:color="111111"/>'
            '<w:left w:val="single" w:sz="8" w:space="0" w:color="111111"/>'
            '<w:bottom w:val="single" w:sz="8" w:space="0" w:color="111111"/>'
            '<w:right w:val="single" w:sz="8" w:space="0" w:color="111111"/>'
            "</w:tblBorders>"
            '<w:tblCellMar><w:top w:w="140" w:type="dxa"/><w:left w:w="220" w:type="dxa"/>'
            '<w:bottom w:w="140" w:type="dxa"/><w:right w:w="220" w:type="dxa"/></w:tblCellMar>'
            "</w:tblPr>"
            '<w:tblGrid><w:gridCol w:w="5200"/></w:tblGrid>'
            f'<w:tr><w:tc><w:tcPr><w:tcW w:w="5200" w:type="dxa"/></w:tcPr>{inner}</w:tc></w:tr>'
            "</w:tbl>"
            '<w:p><w:pPr><w:spacing w:before="0" w:after="80"/></w:pPr></w:p>'
        )

    def make_placeholder_table_xml(self, text: str, width_dxa: int = 7600, min_height_dxa: int = 2100) -> str:
        p = self.make_paragraph_xml(
            text,
            align="center",
            before=120,
            after=120,
            size_hp=20,
            color="1E3A8A",
        )
        return (
            f'<w:tbl><w:tblPr><w:tblW w:w="{width_dxa}" w:type="dxa"/><w:jc w:val="center"/>'
            '<w:tblBorders>'
            '<w:top w:val="dashed" w:sz="10" w:space="0" w:color="2563EB"/>'
            '<w:left w:val="dashed" w:sz="10" w:space="0" w:color="2563EB"/>'
            '<w:bottom w:val="dashed" w:sz="10" w:space="0" w:color="2563EB"/>'
            '<w:right w:val="dashed" w:sz="10" w:space="0" w:color="2563EB"/>'
            "</w:tblBorders>"
            '<w:tblCellMar><w:top w:w="180" w:type="dxa"/><w:left w:w="220" w:type="dxa"/>'
            '<w:bottom w:w="180" w:type="dxa"/><w:right w:w="220" w:type="dxa"/></w:tblCellMar>'
            "</w:tblPr>"
            f'<w:tblGrid><w:gridCol w:w="{width_dxa}"/></w:tblGrid>'
            f'<w:tr><w:trPr><w:trHeight w:val="{min_height_dxa}" w:hRule="atLeast"/><w:cantSplit/></w:trPr>'
            f'<w:tc><w:tcPr><w:tcW w:w="{width_dxa}" w:type="dxa"/><w:vAlign w:val="center"/>'
            '<w:shd w:val="clear" w:color="auto" w:fill="EFF6FF"/></w:tcPr>'
            f"{p}</w:tc></w:tr></w:tbl>"
        )

    def make_image_paragraph_xml(
        self,
        img_path: Path,
        *,
        max_w_cm: float = 12.2,
        max_h_cm: float = 7.4,
    ) -> str:
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
        name_esc = xml_esc(img_path.name)

        return (
            '<w:p><w:pPr><w:jc w:val="center"/><w:spacing w:before="80" w:after="60"/></w:pPr>'
            "<w:r><w:drawing>"
            '<wp:inline distT="0" distB="0" distL="0" distR="0">'
            f'<wp:extent cx="{cx}" cy="{cy}"/>'
            '<wp:effectExtent l="0" t="0" r="0" b="0"/>'
            f'<wp:docPr id="{docpr}" name="Picture {docpr}" descr="{name_esc}"/>'
            "<wp:cNvGraphicFramePr>"
            '<a:graphicFrameLocks xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" noChangeAspect="1"/>'
            "</wp:cNvGraphicFramePr>"
            '<a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
            '<a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
            '<pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">'
            "<pic:nvPicPr>"
            f'<pic:cNvPr id="{docpr}" name="{name_esc}"/>'
            "<pic:cNvPicPr/>"
            "</pic:nvPicPr>"
            "<pic:blipFill>"
            f'<a:blip r:embed="{rid}"/>'
            "<a:stretch><a:fillRect/></a:stretch>"
            "</pic:blipFill>"
            "<pic:spPr>"
            f'<a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
            '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
            "</pic:spPr>"
            "</pic:pic>"
            "</a:graphicData>"
            "</a:graphic>"
            "</wp:inline>"
            "</w:drawing></w:r></w:p>"
        )

    def resolve_placeholder_image(self, placeholder_text: str) -> Path | None:
        for key, candidates in AUTO_IMAGE_MAP.items():
            if key in placeholder_text:
                for rel in candidates:
                    p = ROOT / rel
                    if p.exists():
                        return p
        return None

    def add_placeholder_or_auto_image(self, placeholder_text: str) -> None:
        found = self.resolve_placeholder_image(placeholder_text)
        if found is not None:
            self.body_xml.append(self.make_image_paragraph_xml(found))
        else:
            self.body_xml.append(self.make_placeholder_table_xml(placeholder_text))
            self.body_xml.append('<w:p><w:pPr><w:spacing w:before="0" w:after="60"/></w:pPr></w:p>')

    def add_side_by_side_section1(self, list_xmls: list[str], placeholder_text: str) -> None:
        """Disposición a 2 columnas sin bordes (pasos a la izquierda + foto a la derecha) igual a pág. 1 del modelo."""
        left_w = 5650
        right_w = 3420
        found = self.resolve_placeholder_image(placeholder_text)
        if found is not None:
            right_content = self.make_image_paragraph_xml(found, max_w_cm=5.4, max_h_cm=7.2)
            trailing_p = ""
        else:
            right_content = self.make_placeholder_table_xml(placeholder_text, width_dxa=3150, min_height_dxa=2900)
            trailing_p = '<w:p><w:pPr><w:spacing w:before="0" w:after="0"/></w:pPr></w:p>'

        left_content = "".join(list_xmls)
        self.body_xml.append(
            f'<w:tbl><w:tblPr><w:tblW w:w="{left_w + right_w}" w:type="dxa"/>'
            '<w:tblBorders>'
            '<w:top w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
            '<w:left w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
            '<w:bottom w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
            '<w:right w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
            '<w:insideH w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
            '<w:insideV w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
            "</w:tblBorders>"
            '<w:tblCellMar><w:top w:w="40" w:type="dxa"/><w:left w:w="0" w:type="dxa"/>'
            '<w:bottom w:w="40" w:type="dxa"/><w:right w:w="120" w:type="dxa"/></w:tblCellMar>'
            "</w:tblPr>"
            f'<w:tblGrid><w:gridCol w:w="{left_w}"/><w:gridCol w:w="{right_w}"/></w:tblGrid>'
            f'<w:tr><w:trPr><w:cantSplit/></w:trPr>'
            f'<w:tc><w:tcPr><w:tcW w:w="{left_w}" w:type="dxa"/><w:vAlign w:val="center"/></w:tcPr>{left_content}</w:tc>'
            f'<w:tc><w:tcPr><w:tcW w:w="{right_w}" w:type="dxa"/><w:vAlign w:val="center"/></w:tcPr>{right_content}{trailing_p}</w:tc>'
            "</w:tr></w:tbl>"
        )

    def save(self, out_path: Path) -> None:
        sect_pr = (
            "<w:sectPr>"
            '<w:pgSz w:w="11906" w:h="16838"/>'
            '<w:pgMar w:top="1247" w:right="1418" w:bottom="1247" w:left="1418" '
            'w:header="709" w:footer="709" w:gutter="0"/>'
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

        # Relationships
        rels = [
            '<Relationship Id="rIdStyles" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
        ]
        has_png = False
        has_jpg = False
        for rid, img_path, media_name in self.media:
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
            'xmlns:dc="http://purl.org/dc/elements/1.1/" '
            'xmlns:dcterms="http://purl.org/dc/terms/" '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
            "<dc:title>ArcSim_VR - Manual de uso</dc:title>"
            "<dc:creator>Ezequiel García; Luciano Albanez</dc:creator>"
            "</cp:coreProperties>"
        )

        app_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">'
            "<Application>ArcSim_VR Docx Builder</Application>"
            "</Properties>"
        )

        styles_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            "<w:docDefaults>"
            "<w:rPrDefault><w:rPr>"
            '<w:rFonts w:ascii="Segoe UI" w:hAnsi="Segoe UI" w:cs="Segoe UI"/>'
            '<w:sz w:val="22"/><w:szCs w:val="22"/>'
            '<w:lang w:val="es-AR" w:eastAsia="es-AR" w:bidi="ar-SA"/>'
            "</w:rPr></w:rPrDefault>"
            "<w:pPrDefault><w:pPr>"
            '<w:spacing w:after="120" w:line="285" w:lineRule="auto"/>'
            "</w:pPr></w:pPrDefault>"
            "</w:docDefaults>"
            '<w:style w:type="paragraph" w:default="1" w:styleId="Normal">'
            '<w:name w:val="Normal"/>'
            "</w:style>"
            "</w:styles>"
        )

        ext_defaults = ['<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>', '<Default Extension="xml" ContentType="application/xml"/>']
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
            zf.writestr("word/_rels/document.xml.rels", doc_rels_xml)
            for _, img_path, media_name in self.media:
                zf.writestr(f"word/media/{media_name}", img_path.read_bytes())


def parse_and_build(md_text: str, builder: DocxBuilder) -> None:
    lines = md_text.splitlines()
    n = len(lines)
    i = 0
    current_h2 = ""

    while i < n:
        line = lines[i]
        s = line.strip()

        if not s:
            i += 1
            continue

        # Main Title
        if s.startswith("# "):
            builder.add_title(s[2:].strip())
            i += 1
            continue

        # H2 (Subtitle or numbered section)
        if s.startswith("## "):
            h2_text = s[3:].strip()
            current_h2 = h2_text
            if h2_text.lower() == "manual de uso":
                builder.add_subtitle_blue(h2_text)
            else:
                builder.add_h2(h2_text)
            i += 1
            continue

        # H3
        if s.startswith("### "):
            builder.add_h3(s[4:].strip())
            i += 1
            continue

        # Horizontal Rule
        if re.match(r"^-{3,}$", s):
            builder.add_hr()
            i += 1
            continue

        # Image markdown ![alt](path) + optional *caption*
        m_img = re.match(r"^!\[([^\]]*)\]\(([^)]+)\)$", s)
        if m_img:
            img_path = ROOT / m_img.group(2).strip()
            if img_path.exists():
                builder.body_xml.append(builder.make_image_paragraph_xml(img_path))
            else:
                builder.add_placeholder_or_auto_image(f"**[IMAGEN NO ENCONTRADA: {m_img.group(2)}]**")
            i += 1
            if i < n and re.match(r"^\*[^*].*\*$", lines[i].strip()):
                cap = lines[i].strip()[1:-1]
                builder.body_xml.append(
                    builder.make_paragraph_xml(cap, align="center", before=0, after=120, size_hp=19, color="475569", italic=True)
                )
                i += 1
            continue

        # Blockquote (either [INSERTAR IMAGEN ...] or centered callout box)
        if s.startswith(">"):
            q_lines: list[str] = []
            while i < n and lines[i].strip().startswith(">"):
                q_lines.append(re.sub(r"^>\s?", "", lines[i].strip()))
                i += 1
            joined = " ".join(q_lines).strip()
            if "INSERTAR IMAGEN" in joined:
                builder.add_placeholder_or_auto_image(joined)
            else:
                builder.add_callout_box(q_lines)
            continue

        # Lists (ordered or unordered, including 2nd level indented items)
        m_list = re.match(r"^(\s*)([*\-]|\d+\.)\s+(.*)$", line)
        if m_list:
            list_xmls: list[str] = []
            in_led_sec = current_h2.startswith("2.")
            while i < n:
                ml = re.match(r"^(\s*)([*\-]|\d+\.)\s+(.*)$", lines[i])
                if not ml:
                    break
                indent = len(ml.group(1))
                lvl = 1 if indent >= 2 else 0
                raw_marker = ml.group(2)
                marker = raw_marker if raw_marker.endswith(".") else ("●" if lvl == 0 else "○")
                item_text = ml.group(3).strip()
                list_xmls.append(
                    builder.make_list_item_xml(
                        marker,
                        item_text,
                        level=lvl,
                        color_first_bold_map=LED_LABEL_COLORS if in_led_sec else None,
                    )
                )
                i += 1

            # Si estamos en la Sección 1 y justo después viene el marcador IMAGEN M1,
            # maquetarlo en 2 columnas (pasos a la izquierda + foto a la derecha) igual al modelo!
            j = i
            while j < n and not lines[j].strip():
                j += 1
            if current_h2.startswith("1.") and j < n and lines[j].strip().startswith(">") and "IMAGEN M1" in lines[j]:
                q_lines = []
                while j < n and lines[j].strip().startswith(">"):
                    q_lines.append(re.sub(r"^>\s?", "", lines[j].strip()))
                    j += 1
                builder.add_side_by_side_section1(list_xmls, " ".join(q_lines).strip())
                i = j
            else:
                builder.body_xml.extend(list_xmls)
            continue

        # Normal paragraph
        p_lines = [s]
        i += 1
        while (
            i < n
            and lines[i].strip()
            and not lines[i].strip().startswith(("#", ">", "![", "---"))
            and not re.match(r"^(\s*)([*\-]|\d+\.)\s+", lines[i])
        ):
            p_lines.append(lines[i].strip())
            i += 1
        builder.add_paragraph(" ".join(p_lines))


def main() -> int:
    out_docx = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DEFAULT_DOCX
    if not MD_PATH.exists():
        print(f"[ERROR] No se encontró {MD_PATH}")
        return 1

    md_text = MD_PATH.read_text(encoding="utf-8")
    builder = DocxBuilder()
    parse_and_build(md_text, builder)
    builder.save(out_docx)
    print(f"[OK] Archivo Word generado exitosamente: {out_docx} ({out_docx.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
