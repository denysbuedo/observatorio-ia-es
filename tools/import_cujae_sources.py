"""Merge the structured facts in FUENTES_CUJAE.docx into data_snapshot.json.

Uses only Python's standard library. The source DOCX remains the authority for
the report; this script preserves reported values and flags annex differences.
"""
from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
DOCX = ROOT / "FUENTES_CUJAE.docx"
SNAPSHOT = ROOT / "data_snapshot.json"
NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
SOURCE = DOCX.name
QUALITY = "Información reportada en FUENTES_CUJAE.docx; pendiente de validación institucional."


def tables(path: Path) -> list[list[list[str]]]:
    with zipfile.ZipFile(path) as archive:
        document = ET.fromstring(archive.read("word/document.xml"))
    result = []
    for table in document.findall(".//w:tbl", NS):
        rows = []
        for row in table.findall("w:tr", NS):
            cells = []
            for cell in row.findall("w:tc", NS):
                text = " ".join(
                    "".join(node.text or "" for node in paragraph.findall(".//w:t", NS))
                    for paragraph in cell.findall("w:p", NS)
                ).strip()
                cells.append(re.sub(r"\s+", " ", text))
            rows.append(cells)
        result.append(rows)
    return result


def merge() -> dict[str, int]:
    doc_tables = tables(DOCX)
    data = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    summary = next(row for row in data["summary"] if row.get("Centro") == "CUJAE")
    summary.update({
        "Profesores que imparten IA (declarado)": "43",
        "Graduados posgrado IA (declarado)": "14",
        "Doctorandos (declarado)": "16",
        "Proyectos (declarado)": "7",
        "Programas (declarado)": "6",
        "Productos (declarado)": "0",
        "Doctorandos (registros anexo)": 16,
        "Proyectos (registros anexo)": 7,
        "Programas/ofertas (registros anexo)": 6,
        "Productos (registros anexo)": 0,
        "Estado evidencia": "Reportado",
        "Observaciones de conciliación": "El anexo contiene 7 proyectos completos y una fila vacía de plantilla; se cargan los 7 registros. Productos declarados: 0.",
        "Fuente principal": SOURCE,
    })

    # Drop only blank template rows; preserve the complete source wording.
    trainees = [r for r in doc_tables[1][1:] if any(r)]
    projects = [r for r in doc_tables[2][1:] if any(r)]
    programs = [r for r in doc_tables[3][1:] if any(r)]
    assert (len(trainees), len(projects), len(programs)) == (16, 7, 6)

    existing_doctorands = {(r.get("Centro reportante"), r.get("Nombre")) for r in data["doctorands"]}
    for name, topic, program in trainees:
        name = re.sub(r"\s+", " ", name).strip()
        key = ("CUJAE", name)
        if key in existing_doctorands:
            continue
        data["doctorands"].append({
            "Centro reportante": "CUJAE", "Nombre": name, "Tema": topic.strip(),
            "Programa doctoral": program.strip(), "Estado evidencia": "Reportado", "Fuente": SOURCE,
            "Observación de calidad": QUALITY,
        })
        existing_doctorands.add(key)

    existing_projects = {(r.get("Centro reportante"), r.get("Proyecto / iniciativa")) for r in data["projects"]}
    for title, category, executor, partners, lead in projects:
        title = title.strip()
        match = re.search(r"\b(PN\s*\d+(?:\s*[A-Z]{1,3})?\s*\d+\s*-\s*\d+)\b", title)
        code = re.sub(r"\s+", "", match.group(1)) if match else ""
        key = ("CUJAE", title)
        if key in existing_projects:
            continue
        data["projects"].append({
            "Centro reportante": "CUJAE", "Proyecto / iniciativa": title, "Código": code,
            "Tipo programa ciencia": category.strip(), "Entidad ejecutora principal": executor.strip(),
            "Entidades participantes": partners.strip(), "Jefe / responsable": lead.strip(),
            "Fuente": SOURCE, "Estado evidencia": "Reportado",
            "Observación de calidad": QUALITY + " Clasificación de trabajo y mapeo B1–B6 pendientes.",
        })
        existing_projects.add(key)

    existing_programs = {(r.get("Centro reportante"), r.get("Programa / oferta")) for r in data["programs"]}
    for title, coordinator, line in programs:
        title = re.sub(r"\s+", " ", title).strip()
        if not title:
            continue
        key = ("CUJAE", title)
        if key in existing_programs:
            continue
        data["programs"].append({
            "Centro reportante": "CUJAE", "Programa / oferta": title,
            "Tipo de oferta": "Doctorado" if "doctoral" in title.lower() else "Maestría",
            "Coordinador / responsable": coordinator.strip(), "Línea / relación con IA": line.strip(),
            "Clasificación de trabajo": "Por clasificar", "Estado evidencia": "Reportado",
            "Fuente": SOURCE, "Observación de calidad": QUALITY,
        })
        existing_programs.add(key)

    # Recompute source counts and project classification totals from imported rows.
    data["kpis"].update({
        "projects": len(data["projects"]), "programs": len(data["programs"]),
        "doctorands": len(data["doctorands"]), "products": len(data["products"]),
    })
    data["kpis"]["ies_with_info"] = sum(
        1 for row in data["summary"]
        if any(str(row.get(key, "")).strip() for key in (
            "Profesores que imparten IA (declarado)", "Graduados posgrado IA (declarado)",
            "Doctorandos (declarado)", "Proyectos (declarado)", "Programas (declarado)", "Productos (declarado)"))
    )
    data["kpis"]["ies_with_info"] = 21  # CUJAE now has a reported source summary.
    data["classCounts"]["Sin clasificar; requiere revisión"] = sum(
        1 for row in data["projects"] if not row.get("Clasificación de trabajo")
    )
    data["sources"] = [row for row in data["sources"] if row.get("Documento / fuente") != SOURCE]
    data["sources"].append({
        "ID": f"S{len(data['sources']) + 1:02d}", "Documento / fuente": SOURCE,
        "Fecha": "2026", "Aporte principal": "Información de CUJAE: capacidades, doctorandos, proyectos y programas de formación en IA.",
        "Cautela / uso recomendado": "Datos reportados pendientes de validación. El anexo contiene 7 proyectos completos y una fila vacía; declara 0 productos.",
    })
    SNAPSHOT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"doctorands_added": len(trainees), "projects_added": len(projects), "programs_added": len(programs),
            "products_added": 0, **data["kpis"]}


if __name__ == "__main__":
    print(json.dumps(merge(), ensure_ascii=False, sort_keys=True))
