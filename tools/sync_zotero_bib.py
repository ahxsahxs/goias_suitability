"""Generate thesis/Bibliography/bibliography.bib from the Zotero export (CLAUDE.md §12).

Zotero is the source of truth for the bibliography. Its BibLaTeX export
(thesis/Bibliography/zotero_bibliography.bib) and attachment folder
(thesis/Bibliography/zotero_storage/<ID>/) are local-only and gitignored
(copyright). This script:

  1. strips fields that must not reach the public repo / APA list
     (file, abstract, keywords, urldate, shorttitle) and writes the committed
     bibliography.bib loaded by thesis/Config/4_files.tex;
  2. checks every \\cite*{} key used in thesis/Chapters + thesis/Config exists in
     the export -- exits non-zero (and writes nothing) if any is missing;
  3. reports entries with no local PDF under zotero_storage/.

  --rewrite-keys  one-off migration: rewrites legacy keys (e.g. Abatzoglou2018)
                  inside \\cite*{} to the Zotero keys, matched by DOI then title
                  against the current bibliography.bib.
  --check         run the checks and the PDF report without writing anything.

Run:  uv run python tools/sync_zotero_bib.py [--rewrite-keys] [--check]
"""
from __future__ import annotations

import argparse
import glob
import os
import re
import sys
import unicodedata

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "thesis")
BIB_DIR = os.path.join(ROOT, "Bibliography")
ZOTERO_BIB = os.path.join(BIB_DIR, "zotero_bibliography.bib")
ZOTERO_STORAGE = os.path.join(BIB_DIR, "zotero_storage")
OUT_BIB = os.path.join(BIB_DIR, "bibliography.bib")
TEX_GLOBS = [os.path.join(ROOT, "Chapters", "*.tex"), os.path.join(ROOT, "Config", "*.tex")]

DROP_FIELDS = {"file", "abstract", "keywords", "urldate", "shorttitle"}
IGNORE_KEYS = {"*", "Artho04"}  # \nocite{*}; template test entry in glossary.tex (list not printed)
# Legacy keys whose Zotero replacement is a deliberate change, not a DOI/title match.
KEY_OVERRIDES = {"Saaty1980": "saaty_analytic_1987", "FAO1976": "noauthor_global_2021"}

HEADER = """\
% bibliography.bib -- GERADO por tools/sync_zotero_bib.py a partir do export do
% Zotero (thesis/Bibliography/zotero_bibliography.bib). NAO EDITAR A MAO: corrigir
% ou acrescentar fontes no Zotero, reexportar e rodar o script (CLAUDE.md §12).

"""

CITE_RE = re.compile(r"\\[a-zA-Z]*cite[a-zA-Z]*\*?((?:\[[^\]]*\]){0,2})\{([^}]*)\}")


def parse_entries(text: str) -> list[tuple[str, str, list[tuple[str, str]]]]:
    """Return [(type, key, [(field, raw_value_with_braces), ...])] -- brace-balanced."""
    entries = []
    for m in re.finditer(r"@(\w+)\s*\{\s*([^,\s]+)\s*,", text):
        typ, key, i = m.group(1), m.group(2), m.end()
        fields = []
        while True:
            fm = re.compile(r"\s*(\w+)\s*=\s*").match(text, i)
            if not fm:
                break
            j = fm.end()
            if text[j] == "{":
                depth, k = 0, j
                while True:
                    c = text[k]
                    if c == "\\":
                        k += 2
                        continue
                    depth += c == "{"
                    depth -= c == "}"
                    k += 1
                    if depth == 0:
                        break
            else:  # bare number / macro
                k = re.compile(r"[^,}\s]+").match(text, j).end()
            fields.append((fm.group(1).lower(), text[j:k]))
            i = re.compile(r"\s*,?").match(text, k).end()
        entries.append((typ, key, fields))
    return entries


def unbrace(v: str) -> str:
    return v[1:-1] if v.startswith("{") and v.endswith("}") else v


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKD", s or "").lower())


def pdf_paths(file_field: str) -> list[str]:
    """Resolve a Zotero `file` field to local paths under zotero_storage/."""
    out = []
    for part in re.split(r"(?<!\\);", file_field):
        bits = re.split(r"(?<!\\):", part)
        if len(bits) < 3 or bits[-1] != "application/pdf":
            continue
        path = ":".join(bits[1:-1]).replace("\\:", ":").replace("\\\\", "\\")
        m = re.search(r"storage[\\/]([A-Z0-9]{8})[\\/](.+)$", path)
        out.append(os.path.join(ZOTERO_STORAGE, m.group(1), m.group(2)) if m else path)
    return out


def cited_keys() -> dict[str, list[str]]:
    keys: dict[str, list[str]] = {}
    for pattern in TEX_GLOBS:
        for path in sorted(glob.glob(pattern)):
            with open(path, encoding="utf8") as fh:
                text = re.sub(r"(?<!\\)%.*", "", fh.read())  # ignore commented-out \cite
                for m in CITE_RE.finditer(text):
                    for k in m.group(2).split(","):
                        k = k.strip()
                        if k and k not in IGNORE_KEYS:
                            keys.setdefault(k, []).append(os.path.relpath(path, ROOT))
    return keys


def key_map(old_entries, new_entries) -> dict[str, str]:
    by_doi, by_title = {}, {}
    for _, key, fields in new_entries:
        f = {n: unbrace(v) for n, v in fields}
        if f.get("doi"):
            by_doi.setdefault(norm(f["doi"]), key)
        by_title.setdefault(norm(f.get("title"))[:40], key)
    mapping = {}
    for _, key, fields in old_entries:
        f = {n: unbrace(v) for n, v in fields}
        new = KEY_OVERRIDES.get(key) or by_doi.get(norm(f.get("doi"))) or by_title.get(norm(f.get("title"))[:40])
        if new:
            mapping[key] = new
    return mapping


def rewrite_keys(mapping: dict[str, str]) -> None:
    def sub(m):
        keys = [k.strip() for k in m.group(2).split(",")]
        new = ",".join(mapping.get(k, k) for k in keys)
        return m.group(0)[: m.start(2) - m.start(0)] + new + "}"

    for pattern in TEX_GLOBS:
        for path in sorted(glob.glob(pattern)):
            with open(path, encoding="utf8") as fh:
                text = fh.read()
            new_text = CITE_RE.sub(sub, text)
            if new_text != text:
                n = sum(1 for a, b in zip(CITE_RE.findall(text), CITE_RE.findall(new_text)) if a != b)
                with open(path, "w", encoding="utf8") as fh:
                    fh.write(new_text)
                print(f"rewrote {n} \\cite in {os.path.relpath(path, ROOT)}")


def render(entries) -> str:
    chunks = []
    for typ, key, fields in entries:
        body = ",\n".join(f"\t{n} = {v}" for n, v in fields if n not in DROP_FIELDS)
        chunks.append(f"@{typ}{{{key},\n{body},\n}}\n")
    return HEADER + "\n".join(chunks)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rewrite-keys", action="store_true", help="migrate legacy \\cite keys to Zotero keys")
    ap.add_argument("--check", action="store_true", help="report only; write nothing")
    args = ap.parse_args()

    with open(ZOTERO_BIB, encoding="utf8") as fh:
        new_entries = parse_entries(fh.read())
    new_keys = {k for _, k, _ in new_entries}

    if args.rewrite_keys and not args.check:
        with open(OUT_BIB, encoding="utf8") as fh:
            old_entries = parse_entries(fh.read())
        mapping = {o: n for o, n in key_map(old_entries, new_entries).items() if o != n}
        unmapped = sorted(k for _, k, _ in old_entries if k not in mapping and k not in new_keys)
        rewrite_keys(mapping)
        if unmapped:
            print("legacy keys with no Zotero match (left untouched):", ", ".join(unmapped))

    missing = {k: v for k, v in cited_keys().items() if k not in new_keys}
    print(f"{len(new_entries)} entries in the Zotero export")
    no_pdf = []
    for _, key, fields in new_entries:
        f = dict(fields)
        if not any(os.path.exists(p) for p in pdf_paths(unbrace(f.get("file", "")))):
            no_pdf.append(key)
    print(f"entries without a local PDF ({len(no_pdf)}):", ", ".join(no_pdf) or "none")

    if missing:
        print("\nERROR: cited keys missing from the Zotero export -- bibliography.bib NOT written:")
        for k, where in sorted(missing.items()):
            print(f"  {k}  ({', '.join(sorted(set(where)))})")
        return 1
    if not args.check:
        with open(OUT_BIB, "w", encoding="utf8") as fh:
            fh.write(render(new_entries))
        print(f"wrote {os.path.relpath(OUT_BIB, os.path.join(ROOT, '..'))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
