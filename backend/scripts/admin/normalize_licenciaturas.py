"""normalize_licenciaturas.py — Paso 1 del Prompt Utel KB: extrae y normaliza
las fichas técnicas de licenciatura (PDF) a markdown, un documento por
programa, en scripts/admin/utel_kb_source/03_licenciaturas/.

Deduplica por HASH DEL TEXTO EXTRAÍDO (no del PDF crudo) — dos PDFs pueden
ser bit-a-bit distintos (metadata/timestamps embebidos) pero contener
exactamente el mismo texto visible; solo el hash del contenido extraído
detecta eso de forma confiable.

Los PDFs vienen en dos formatos distintos (confirmado leyendo varios de cada
uno antes de escribir este parser, no asumido):
  Familia A ("Sobre la Licenciatura", sin selector de modalidad ni Perfil de
    ingreso/egreso — el propio ficha no lo trae): "Dónde podrás trabajar",
    "Lo que aprenderás", "Asignaturas" + "Áreas de concentración*".
  Familia B ("Elige en qué modalidad estudiar" — este marcador es el que se
    usa para clasificar, es el único que no aparece nunca en Familia A):
    descripción corta, "Lo que aprenderás", selector de 3 modalidades,
    "Duración: ... meses", "Perfil de ingreso", "Perfil de egreso",
    "Dónde podrás trabajar".

Extracción de texto: pdftotext -layout -enc UTF-8 — SIN -enc UTF-8 el output
sale en ISO-8859 con los acentos rotos (confirmado corriendo un sample antes
de escribir esto), -layout preserva mejor las dos columnas.

Nombre de la licenciatura: se deriva del NOMBRE DE ARCHIVO (siempre presente
y consistente en las 3 familias de naming), no del primer renglón del PDF —
varios PDFs (confirmado en al menos uno) tienen el título con las letras
intercaladas/rotas por una capa de texto decorativo superpuesta, incluso sin
-layout. Los acentos del nombre (ausentes en el filename) se restauran
buscando el nombre sin-acentos dentro del cuerpo del texto extraído
(que SÍ tiene acentos correctos) — si no se encuentra, se deja tal cual
viene del filename y se marca REVISAR.

Uso:
    .venv/Scripts/python.exe scripts/admin/normalize_licenciaturas.py
"""
from __future__ import annotations

import hashlib
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

SOURCE_DIR = Path(__file__).resolve().parent / "utel_kb_source" / "licenciaturas_pdfs"
OUT_DIR = Path(__file__).resolve().parent / "utel_kb_source" / "03_licenciaturas"

_MODALIDAD_MARKER = "elige en qué modalidad estudiar"
_DURACION_FIJA = (
    "Programa base: 44 meses · Intensivo: 34 meses · Super intensivo: ~26 meses"
)

FILENAME_PATTERNS = [
    # MX_Licenciatura_en__{Name}_Nuevos_Programas_Bloque_N_....pdf
    re.compile(r"^MX_Licenciatura_en__(.+?)_Nuevos_Programas_Bloque_\d+_"),
    # Utel_Universidad_Editorial_Mx_Licenciatura_{Name}_FT_....pdf
    re.compile(r"^Utel_Universidad_Editorial_Mx_Licenciatura_(.+?)_FT_"),
    # Utel_MX_Fichas_Tecnicas_Prog_Eje_Lic_{Name}_....pdf
    re.compile(r"^Utel_MX_Fichas_Tecnicas_Prog_Eje_Lic_(.+?)_[0-9a-f]{8,}\.pdf$", re.IGNORECASE),
    # Utel_Mx_Fichas_Tecnicas_Lic_{Name}_....pdf
    re.compile(r"^Utel_Mx_Fichas_Tecnicas_Lic_(.+?)_[0-9a-f]{8,}\.pdf$", re.IGNORECASE),
]


def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def _slug(name: str) -> str:
    ascii_name = _strip_accents(name).lower()
    ascii_name = re.sub(r"[^a-z0-9]+", "-", ascii_name).strip("-")
    return ascii_name


def _extract_pdf_text(pdf_path: Path) -> str:
    # SIN -layout, a propósito — contrario a lo que asumía el prompt
    # ("-layout preserva mejor las dos columnas"): confirmado comparando el
    # output de ambos modos en varias muestras que -layout en realidad
    # INTERCALA el texto de las dos columnas carácter-a-carácter dentro de
    # la misma línea física (ilegible: mezcla "Sobre la Licenciatura" con
    # "Lo que aprenderás" a mitad de oración), mientras que el modo plano
    # (orden de lectura del content stream del PDF) extrae cada columna
    # completa y en orden, sin mezclar. -enc UTF-8 sigue siendo necesario
    # (sin eso los acentos salen rotos, confirmado aparte).
    result = subprocess.run(
        ["pdftotext", "-enc", "UTF-8", str(pdf_path), "-"],
        capture_output=True, check=True,
    )
    raw = result.stdout.decode("utf-8", errors="replace")
    # Ligaduras tipográficas (ﬁ/ﬂ) que pdftotext no descompone solo —
    # confirmado en varias fichas ("Aﬁna", "ﬁnancieros", "conﬂictos").
    raw = raw.replace("ﬁ", "fi").replace("ﬂ", "fl").replace("ﬀ", "ff")
    # Footer que se repite en (casi) cada página, sin valor de contenido.
    raw = re.sub(r"^\s*utel\.edu\.mx\s*$", "", raw, flags=re.IGNORECASE | re.MULTILINE)
    return raw


def _name_from_filename(filename: str) -> str | None:
    for pattern in FILENAME_PATTERNS:
        m = pattern.match(filename)
        if m:
            raw = m.group(1)
            # " (1)" suffix / trailing junk from filesystem dedup artifacts, and
            # the double-underscore some patterns use as a separator.
            raw = raw.replace("__", " ").replace("_", " ")
            raw = re.sub(r"\s*\(\d+\)\s*$", "", raw).strip()
            return raw
    return None


def _left_column(line: str) -> str:
    """pdftotext -layout pone columnas lado a lado separadas por >=3
    espacios — el título vive en la columna izquierda, pero la línea física
    completa suele traer también contenido de la columna derecha (ej. 'Lo
    que aprenderás') pegado en el mismo renglón. Se corta ahí."""
    m = re.match(r"^(.*?)(?:\s{3,}|$)", line)
    return (m.group(1) if m else line).strip()


def _extract_title_from_body(text: str) -> str | None:
    """Toma el nombre real de las primeras líneas del cuerpo extraído —
    confirmado más confiable que el filename para la mayoría de los PDFs
    (título limpio en Familia A completa y en la mayor parte de Familia B).
    Busca la línea marcador ('Licenciatura en' / 'Licencitura en' — hay un
    typo real en al menos un PDF de origen, se tolera — / 'Licenciatura
    Ejecutiva en') dentro de las primeras 8 líneas, y junta las líneas no
    vacías siguientes (SOLO columna izquierda, ver _left_column) hasta la
    primera línea en blanco."""
    lines = text.split("\n")
    marker_idx = None
    for i, l in enumerate(lines[:8]):
        # \w{0,3} entre "licen" y "tura" tolera tanto "licenciatura" (normal)
        # como "licencitura" (typo real confirmado en al menos un PDF de
        # origen — falta la "a" de "cia") y "licentiatura".
        # Al menos un PDF de origen usa "Carrera en" en vez de "Licenciatura
        # en" (plantilla distinta, confirmado en 1 archivo) — se tolera acá.
        if re.search(r"licen\w{0,3}tura|^carrera\s+en\s*$", _left_column(l), re.IGNORECASE):
            marker_idx = i
            break
    if marker_idx is None:
        return None
    # Sin -layout no hay línea en blanco confiable entre el nombre y el
    # párrafo de descripción que le sigue (confirmado: "Licenciatura en\n
    # Ingeniería Robótica\nDesarrolla sistemas robóticos..." — 3 líneas
    # seguidas, sin separador) — juntar hasta la primera línea vacía se
    # comía el párrafo entero como si fuera el nombre. El nombre es siempre
    # UNA sola línea no vacía en todas las muestras confirmadas, así que se
    # toma exactamente esa y se para ahí.
    name_lines: list[str] = []
    for l in lines[marker_idx + 1: marker_idx + 4]:
        stripped = _left_column(l)
        if not stripped:
            continue
        name_lines.append(stripped)
        break
    if not name_lines:
        return None
    return " ".join(name_lines).strip()


def _classify_family(text: str) -> str:
    return "B" if _MODALIDAD_MARKER in text.lower() else "A"


def _extract_section(text: str, start_headers: list[str], end_headers: list[str]) -> str | None:
    """Extrae el texto entre la primera ocurrencia de cualquier start_header
    y la primera ocurrencia (después de eso) de cualquier end_header."""
    lines = text.split("\n")
    lower_lines = [l.strip().lower() for l in lines]
    start_idx = None
    for i, l in enumerate(lower_lines):
        if any(l == h.lower() or l.startswith(h.lower()) for h in start_headers):
            start_idx = i
            break
    if start_idx is None:
        return None
    end_idx = len(lines)
    for i in range(start_idx + 1, len(lines)):
        if any(lower_lines[i] == h.lower() or lower_lines[i].startswith(h.lower()) for h in end_headers):
            end_idx = i
            break
    section = "\n".join(lines[start_idx + 1: end_idx]).strip()
    return section or None


_RVOE_RE = re.compile(
    # El número/código de RVOE es casi siempre solo dígitos, pero al menos
    # una ficha real (Marketing y Publicidad) trae un código alfanumérico de
    # OTRA institución ("RVOE AL-IV 141/2017" de UNICA, no de Utel/SEP) — se
    # generaliza el patrón para capturarlo tal cual en vez de perderlo, y
    # esa ficha igual queda con <!-- REVISAR --> por lo inusual del caso.
    # Tolera coma antes de "de/con fecha" (confirmado: al menos un PDF trae
    # "RVOE 20231340, de fecha ...") y salto de línea dentro de la fecha
    # (confirmado en el caso alfanumérico de arriba).
    r"RVOE\s+([A-Za-z0-9][A-Za-z0-9\-/\s]{0,20}?[0-9])\s*,?\s+(?:de|con)\s+fecha\s+([^,]+?)"
    r"(?:,|\s+modalidad|\s+emitido|$)",
    re.IGNORECASE,
)
_CREDITOS_RE = re.compile(r"Cr[eé]ditos\s+totales:?\s*\n?\s*(\d+)", re.IGNORECASE)

_ALL_HEADERS = [
    "sobre la licenciatura", "lo que aprenderás", "dónde podrás trabajar",
    "asignaturas", "áreas de concentración", "validez académica",
    "elige en qué modalidad estudiar", "duración", "perfil de ingreso",
    "perfil de egreso", "créditos totales", "elige una licenciatura",
    "elige una", "arma la mejor experiencia", "¿por qué utel?",
    "calidad académica", "inscríbete hoy",
]


def _clean_bullets(block: str) -> str:
    """Colapsa líneas partidas por el layout de 2 columnas en párrafos
    razonables — no reformatea agresivo, solo baja el ruido de saltos de
    línea a mitad de oración que deja pdftotext -layout."""
    lines = [l.strip() for l in block.split("\n")]
    out: list[str] = []
    for l in lines:
        if not l:
            if out and out[-1] != "":
                out.append("")
            continue
        out.append(l)
    return "\n".join(out).strip()


def _parse_one(pdf_path: Path) -> dict:
    filename = pdf_path.name
    text = _extract_pdf_text(pdf_path)
    family = _classify_family(text)

    issues: list[str] = []
    # Los PDFs "MX_Licenciatura_en__..." tienen el título ROTO en el propio
    # texto extraído (confirmado: una capa de texto decorativo superpuesta
    # intercala las letras, con y sin -layout) en el 100% de una muestra de
    # 4/4 — para ESOS, el filename ya trae el nombre completo Y acentuado,
    # así que se usa directo. Para el resto (confirmado título limpio en
    # todas las muestras de las otras 3 familias de naming), se extrae del
    # cuerpo del texto, que es más confiable que reconstruir desde un
    # filename a veces abreviado (ej. "Admin_Negocios" en vez de
    # "Administración de Negocios").
    if filename.startswith("MX_Licenciatura_en__"):
        raw_name = _name_from_filename(filename)
        if raw_name is None:
            raw_name = pdf_path.stem
            issues.append(f"no se pudo derivar el nombre del filename: {filename!r}")
        name = raw_name
    else:
        body_name = _extract_title_from_body(text)
        if body_name and 2 <= len(body_name) <= 100:
            name = body_name
        else:
            fallback = _name_from_filename(filename) or pdf_path.stem
            issues.append(
                f"no se pudo extraer un título limpio del cuerpo del texto "
                f"(candidato: {body_name!r}) — se usa el nombre derivado del filename: {fallback!r}"
            )
            name = fallback

    # RVOE
    rvoe_match = _RVOE_RE.search(text)
    if rvoe_match:
        rvoe_code = re.sub(r"\s+", " ", rvoe_match.group(1)).strip()
        rvoe_date = re.sub(r"\s+", " ", rvoe_match.group(2)).strip()
        rvoe_text = f"RVOE {rvoe_code} de fecha {rvoe_date}"
        if not rvoe_code.isdigit():
            issues.append(f"RVOE con formato inusual (no es solo numérico, revisar institución emisora): {rvoe_text!r}")
    else:
        # El patrón estructurado no matcheó — pero eso no significa que el
        # dato no exista en la ficha (confirmado: al menos un PDF dice "No.
        # de Acuerdo 20231350" en vez de "RVOE 20231350", con la fecha ANTES
        # del número). Escribir "No disponible" acá sería INCORRECTO — el
        # dato sí está, solo no en el formato que el regex espera. Se cae a
        # la sección "Validez Académica" cruda tal cual salió del PDF, sin
        # reformatear, y se flagea REVISAR para que alguien la limpie a mano.
        validez_raw = _extract_section(
            text, ["validez académica"],
            ["elige una", "arma la mejor", "¿por qué utel", "perfil de egreso", "dónde podrás trabajar", "asignaturas"],
        )
        if validez_raw:
            rvoe_text = _clean_bullets(validez_raw)
            issues.append("RVOE no se pudo extraer en formato estructurado — se dejó el texto crudo de 'Validez Académica' tal cual, revisar formato")
        else:
            rvoe_text = None
            issues.append("no se encontró RVOE ni sección 'Validez Académica' en el texto extraído")

    # Créditos
    creditos_match = _CREDITOS_RE.search(text)
    creditos = creditos_match.group(1) if creditos_match else None

    if family == "A":
        sobre = _extract_section(text, ["sobre la licenciatura", "sobre la carrera"], ["dónde podrás trabajar", "lo que aprenderás"])
        aprenderas = _extract_section(text, ["lo que aprenderás"], ["asignaturas", "validez académica", "elige una"])
        donde = _extract_section(text, ["dónde podrás trabajar"], ["asignaturas", "lo que aprenderás", "validez académica"])
        perfil_ingreso = None
        areas = _extract_section(text, ["áreas de concentración"], ["créditos totales", "validez académica", "elige una"])
        if not sobre:
            issues.append("Familia A sin sección 'Sobre la Licenciatura' detectable")
        if not donde:
            issues.append("Familia A sin sección 'Dónde podrás trabajar' detectable")
    else:
        sobre = _extract_section(text, ["lo que aprenderás"], ["elige en qué modalidad"])
        # En Familia B la descripción corta está ANTES de "Lo que aprenderás",
        # no en una sección con nombre propio — se toma todo lo anterior al
        # primer header conocido, después del título.
        pre_lo_que = text.split("Lo que aprenderás")[0] if "Lo que aprenderás" in text else ""
        # Nos quedamos solo con las últimas líneas no vacías antes del header
        # (para no arrastrar basura de portada/encabezado).
        pre_lines = [l.strip() for l in pre_lo_que.split("\n") if l.strip()]
        # Filtra la línea marcador ("Licenciatura en" / "Carrera en") y la
        # línea del nombre mismo — si no, quedan repetidas dentro de "Sobre
        # la licenciatura" (confirmado, ej. ficha de Ingeniería Robótica).
        # OJO: re.search sobre la línea completa haría falso-positivo en
        # cualquier oración que mencione "la licenciatura" de paso (pasó en
        # la primera versión de este filtro — se comía párrafos enteros de
        # descripción real) — por eso se acota a líneas CORTAS (la línea
        # marcador es siempre 1-4 palabras, nunca una oración).
        pre_lines = [
            l for l in pre_lines
            if not (len(l) <= 30 and re.search(r"licen\w{0,3}tura|^carrera\s+en\s*$", l, re.IGNORECASE))
            and l.strip().lower() != name.lower()
        ]
        if filename.startswith("MX_Licenciatura_en__"):
            # Estos 23 traen el título con las letras intercaladas por la
            # capa decorativa superpuesta (confirmado, ver _parse_one arriba)
            # — la primera línea SIEMPRE es ese fragmento roto, y a veces
            # deja una o dos líneas de "cola" limpia que son en realidad
            # parte del nombre (ej. "Diversidad Cultural" de "Antropología y
            # Diversidad Cultural"), no descripción real. Se descarta la
            # primera línea (siempre garbage acá) y cualquier línea restante
            # que sea substring del nombre ya resuelto (por filename).
            if pre_lines:
                pre_lines = pre_lines[1:]
            name_flat = _strip_accents(name).lower()
            pre_lines = [l for l in pre_lines if _strip_accents(l).lower() not in name_flat]
        sobre = "\n".join(pre_lines[-6:]) if pre_lines else None

        aprenderas = _extract_section(text, ["lo que aprenderás"], ["elige en qué modalidad"])
        perfil_ingreso = _extract_section(text, ["perfil de ingreso"], ["validez académica"])
        donde = _extract_section(text, ["dónde podrás trabajar"], ["asignaturas", "créditos totales"])
        perfil_egreso = _extract_section(text, ["perfil de egreso"], ["dónde podrás trabajar", "asignaturas"])
        if donde is None:
            donde = perfil_egreso
        elif perfil_egreso:
            donde = perfil_egreso + "\n\n" + donde
        areas = None
        if not perfil_ingreso:
            issues.append("Familia B sin sección 'Perfil de ingreso' detectable")
        if not aprenderas:
            issues.append("Familia B sin sección 'Lo que aprenderás' detectable")

    return {
        "filename": filename, "family": family, "name": name.strip(),
        "sobre": _clean_bullets(sobre) if sobre else None,
        "aprenderas": _clean_bullets(aprenderas) if aprenderas else None,
        "donde": _clean_bullets(donde) if donde else None,
        "perfil_ingreso": _clean_bullets(perfil_ingreso) if (family == "B" and perfil_ingreso) else None,
        "areas": _clean_bullets(areas) if areas else None,
        "rvoe": rvoe_text, "creditos": creditos,
        "issues": issues, "raw_text_len": len(text),
        "body_hash": hashlib.sha256(re.sub(r"\s+", " ", text).strip().encode("utf-8")).hexdigest(),
    }


def _build_markdown(doc: dict) -> str:
    name = doc["name"]
    lines: list[str] = []
    if doc["issues"]:
        lines.append(f"<!-- REVISAR: {'; '.join(doc['issues'])} -->")
    lines.append(f"# Licenciatura en {name}")
    lines.append("")
    lines.append("## Sobre la licenciatura")
    lines.append(doc["sobre"] or "No disponible en la ficha técnica original — no inventar contenido aquí.")
    lines.append("")
    lines.append("## Lo que aprenderás")
    lines.append(doc["aprenderas"] or "No disponible en la ficha técnica original — no inventar contenido aquí.")
    lines.append("")
    lines.append("## Perfil de ingreso")
    if doc["family"] == "B" and doc["perfil_ingreso"]:
        lines.append(doc["perfil_ingreso"])
    else:
        lines.append("No disponible en la ficha técnica original — no inventar contenido aquí.")
    lines.append("")
    lines.append("## Perfil de egreso / Dónde podrás trabajar")
    lines.append(doc["donde"] or "No disponible en la ficha técnica original — no inventar contenido aquí.")
    lines.append("")
    lines.append("## Duración")
    lines.append(_DURACION_FIJA)
    lines.append("")
    lines.append("## Modalidad híbrida")
    lines.append(
        "Disponible. Ver 02_modalidad_hibrida.md y 04_sedes_horarios.md para el detalle de "
        "Power Skills, precio y sedes — no repetir ese contenido acá, solo confirmar que esta "
        "licenciatura específica SÍ está disponible en modalidad híbrida."
    )
    lines.append("")
    lines.append("## Validez académica")
    lines.append(doc["rvoe"] or "No disponible en la ficha técnica original — no inventar contenido aquí.")
    if doc["areas"]:
        lines.append("")
        lines.append("## Áreas de concentración / especialización")
        lines.append(doc["areas"])
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    if not SOURCE_DIR.is_dir():
        print(f"No existe {SOURCE_DIR} — colocar los PDFs ahí antes de correr esto.")
        return 1

    pdfs = sorted(SOURCE_DIR.glob("*.pdf"))
    print(f"Encontrados {len(pdfs)} PDFs en {SOURCE_DIR}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    parsed: list[dict] = []
    for pdf_path in pdfs:
        try:
            parsed.append(_parse_one(pdf_path))
        except Exception as exc:
            print(f"  ERROR procesando {pdf_path.name}: {exc}")
            return 1

    # Dedup por hash del TEXTO extraído (no del PDF crudo).
    seen_hashes: dict[str, str] = {}
    unique: list[dict] = []
    duplicates: list[tuple[str, str]] = []
    for doc in parsed:
        h = doc["body_hash"]
        if h in seen_hashes:
            duplicates.append((doc["filename"], seen_hashes[h]))
            continue
        seen_hashes[h] = doc["filename"]
        unique.append(doc)

    print(f"\nDuplicados por contenido (texto extraído idéntico): {len(duplicates)}")
    for dup, original in duplicates:
        print(f"  {dup!r} es duplicado de {original!r} — omitido")

    print(f"\nDocumentos únicos a normalizar: {len(unique)}")

    slugs_used: dict[str, int] = {}
    revisar_count = 0
    written: list[tuple[str, str, list[str]]] = []  # (filename, slug, issues)

    for doc in unique:
        base_slug = _slug(doc["name"])
        n = slugs_used.get(base_slug, 0)
        slugs_used[base_slug] = n + 1
        slug = base_slug if n == 0 else f"{base_slug}-{n + 1}"

        title = f"Licenciatura en {doc['name']}"
        if len(title) > 255:
            doc["issues"].append(f"title excede 255 caracteres ({len(title)})")

        md = _build_markdown(doc)
        if len(md) > 20_000:
            doc["issues"].append(f"content excede 20,000 caracteres ({len(md)})")
            md = _build_markdown(doc)  # rebuild — el comentario REVISAR ya quedó adentro por issues previos, pero si el único issue nuevo es este, hay que reconstruir con el flag puesto

        out_path = OUT_DIR / f"{slug}.md"
        out_path.write_text(md, encoding="utf-8")
        if doc["issues"]:
            revisar_count += 1
        written.append((doc["filename"], slug, doc["issues"]))

    print(f"\n✓ {len(written)} fichas normalizadas en {OUT_DIR}")
    print(f"  Con comentario <!-- REVISAR --> pendiente: {revisar_count}")
    if revisar_count:
        print("\n  Detalle de fichas con REVISAR:")
        for filename, slug, issues in written:
            if issues:
                print(f"    {slug}.md ({filename}): {'; '.join(issues)}")

    family_counts: dict[str, int] = {}
    for doc in unique:
        family_counts[doc["family"]] = family_counts.get(doc["family"], 0) + 1
    print(f"\n  Familia A: {family_counts.get('A', 0)}  |  Familia B: {family_counts.get('B', 0)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
