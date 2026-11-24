"""Añade índice con números de página, pie de página, metadatos y marcadores al manual."""
from __future__ import annotations

import os
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "_manual_raw.pdf"
PDF = ROOT / "Manual_MunchyRoom_Usuario_Administrador.pdf"
TMP = ROOT / "_manual_final.pdf"

user_sections = [
    "1. Conoce MunchyRoom",
    "2. Acceso y seguridad",
    "3. Panel de inicio",
    "4. Calendario de salas",
    "5. Solicitar una sala",
    "6. Mis solicitudes y cancelación",
    "7. Reuniones invitadas",
    "8. Convocatoria por WhatsApp",
    "9. Autorizaciones del jefe",
    "10. Perfil, contraseña y preguntas de seguridad",
    "11. Preguntas frecuentes del usuario",
]
admin_sections = [
    "12. Rol y responsabilidades",
    "13. Primer ingreso y puesta en marcha",
    "14. Panel del administrador",
    "15. Gestión de solicitudes",
    "16. Gestión de salas",
    "17. Usuarios, registros y roles",
    "18. Catálogo de cargos",
    "19. Seguridad y operación",
    "20. Solución de problemas",
]
appendix_sections = [
    "A. Matriz de roles y permisos",
    "B. Estados, reglas y validaciones",
    "C. Glosario",
]


def find_section_page(doc: pymupdf.Document, heading: str, start: int = 3) -> int | None:
    for index in range(start, doc.page_count):
        if doc[index].search_for(heading):
            return index + 1
    # Respaldo: buscar solo el título sin el número.
    title = heading.split(". ", 1)[-1]
    for index in range(start, doc.page_count):
        if doc[index].search_for(title):
            return index + 1
    return None




def main() -> None:
    doc = pymupdf.open(RAW)
    total = doc.page_count

    pages: dict[str, int] = {}
    for heading in user_sections + admin_sections + appendix_sections:
        page = find_section_page(doc, heading)
        if page is None:
            raise SystemExit(f"No se encontró la sección: {heading}")
        pages[heading] = page

    # Las portadillas de parte son la página inmediatamente anterior a la primera sección.
    part1 = pages["1. Conoce MunchyRoom"] - 1
    part2 = pages["12. Rol y responsabilidades"] - 1
    appendix_start = pages[appendix_sections[0]]

    # Números de página en el índice (página 3).
    toc_page = doc[2]
    right = 595.0 - 42.52  # margen derecho de 15 mm
    toc_labels = {"10. Perfil, contraseña y preguntas de seguridad": "Perfil, contraseña y preguntas"}

    for heading in user_sections + admin_sections + appendix_sections:
        title = toc_labels.get(heading, heading.split(". ", 1)[-1])
        hits = toc_page.search_for(title)
        if not hits:
            print("Aviso: título no encontrado en el índice:", title)
            continue
        rect = hits[0]
        number = str(pages[heading])
        width = pymupdf.get_text_length(number, fontname="hebo", fontsize=8.6)
        toc_page.insert_text(
            (right - width, rect.y1 - 1.0),
            number,
            fontname="hebo",
            fontsize=8.6,
            color=(0.0, 0.2, 0.627),
        )

    # Pie de página y numeración.
    skip = {1, part1, part2}
    for index in range(total):
        if index + 1 in skip:
            continue
        page = doc[index]
        width = page.rect.width
        left = 42.52
        right_edge = width - 42.52
        page.draw_line(
            pymupdf.Point(left, 805),
            pymupdf.Point(right_edge, 805),
            color=(0.84, 0.87, 0.93),
            width=0.6,
        )
        page.insert_text(
            (left, 818),
            "MunchyRoom · Manual de usuario y administrador",
            fontname="helv",
            fontsize=7.4,
            color=(0.38, 0.44, 0.54),
        )
        label = f"Página {index + 1} de {total}"
        label_width = pymupdf.get_text_length(label, fontname="hebo", fontsize=7.4)
        page.insert_text(
            (right_edge - label_width, 818),
            label,
            fontname="hebo",
            fontsize=7.4,
            color=(0.0, 0.2, 0.627),
        )

    # Marcadores del PDF.
    outline: list[list] = [
        [1, "Portada", 1],
        [1, "Presentación", 2],
        [1, "Contenido", 3],
        [1, "Parte I · Manual de usuario", part1],
    ]
    outline += [[2, heading, pages[heading]] for heading in user_sections]
    outline.append([1, "Parte II · Manual de administrador", part2])
    outline += [[2, heading, pages[heading]] for heading in admin_sections]
    outline.append([1, "Apéndices", appendix_start])
    outline += [[2, heading, pages[heading]] for heading in appendix_sections]
    doc.set_toc(outline)

    doc.set_metadata(
        {
            "title": "MunchyRoom · Manual de usuario y administrador",
            "author": "Jean Rodríguez · Soluciones de Automatización a la Medida",
            "subject": "Manual de usuario y administrador de MunchyRoom, gestión de salas de reuniones de Alimentos Munchy, C.A.",
            "keywords": "MunchyRoom, salas, reuniones, Alimentos Munchy, manual, administrador",
            "creator": "MunchyRoom",
            "producer": "Chrome Headless / PyMuPDF",
        }
    )

    doc.save(TMP, garbage=4, deflate=True)
    doc.close()
    os.replace(TMP, PDF)
    print("PDF final:", PDF)
    print("Páginas:", total)
    print("Parte I:", part1, "| Parte II:", part2, "| Apéndices:", appendix_start)
    for heading in user_sections + admin_sections + appendix_sections:
        print(f"  {pages[heading]:>2}  {heading}")


if __name__ == "__main__":
    main()
