#!/usr/bin/env python3
"""
Import massivo da cartella: i preventivi vengono creati/aggiornati SOLO dopo estrazione Anthropic (Claude).
Non si inseriscono più righe “vuote” senza extracted_info valido.

Uso (da directory backend):
  python import_offerte_folder.py "C:\\path\\to\\OFFERTE"
  python import_offerte_folder.py "C:\\path\\to\\OFFERTE" --extract-only
  python import_offerte_folder.py "C:\\path\\to\\OFFERTE" --cleanup-bulk-only

Dopo l’esecuzione (anche se interrotta con Ctrl+C), eventuali residui import_bulk nella cartella
vengono rimossi, salvo --keep-pending.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import uuid
from datetime import datetime

from werkzeug.utils import secure_filename

from commesse_ore import (
    default_xlsx_path,
    import_to_sqlite,
    load_rows_from_xlsx,
    match_preventivi_filenames,
    rows_grouped_by_cliente_norm,
)
from offerta_commessa_mapping import (
    default_mapping_xlsx_path,
    import_mapping_to_sqlite,
    load_rows_from_mapping_xlsx,
)

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "preventivi.db")
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")


def _ensure_updated_at_column():
    """Allinea schema con app.py (colonna updated_at) senza importare Flask."""
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(preventivi)")
        cols = [r[1] for r in cur.fetchall()]
        if "updated_at" not in cols:
            cur.execute("ALTER TABLE preventivi ADD COLUMN updated_at TEXT")
        cur.execute(
            "UPDATE preventivi SET updated_at = upload_date WHERE updated_at IS NULL OR TRIM(COALESCE(updated_at, '')) = ''"
        )
        conn.commit()
    finally:
        conn.close()

DATA_DIR = os.path.join(os.path.dirname(UPLOAD_FOLDER), "data")


def _fatal_anthropic_config_error(info: dict) -> bool:
    """True se l'estrazione non può proseguire (es. API key mancante)."""
    err = info.get("error")
    if err is None:
        return False
    es = str(err).lower()
    return (
        "anthropic_api_key" in es
        or "api key" in es and ("mancant" in es or "missing" in es or "not found" in es)
        or "claude_api_key" in es
    )


def _estrazione_salvabile_in_db(info: dict | None) -> bool:
    """
    True se possiamo persistere il preventivo: estrazione Anthropic riuscita o con dati parziali utili.
    False se solo errore (senza altri campi) o errore configurazione.
    """
    if not info or not isinstance(info, dict):
        return False
    if _fatal_anthropic_config_error(info):
        return False
    if info.get("error") is not None:
        rest = set(info.keys()) - {"error", "raw_text", "note"}
        if not rest:
            return False
    return True


def _delete_one_preventivo(cur, conn, pid: str, filepath: str | None, has_af_cache: bool) -> None:
    if has_af_cache:
        cur.execute("DELETE FROM fattore_af_cache WHERE preventivo_id = ?", (pid,))
    cur.execute("DELETE FROM preventivi WHERE id = ?", (pid,))
    if filepath and os.path.isfile(filepath):
        try:
            os.remove(filepath)
        except OSError:
            pass
    jp = os.path.join(DATA_DIR, f"{pid}.json")
    if os.path.isfile(jp):
        try:
            os.remove(jp)
        except OSError:
            pass
    conn.commit()


def _extracted_info_senza_estrazione(raw: str | None) -> bool:
    """True se extracted_info è vuoto, malformato o ancora solo placeholder import bulk."""
    if raw is None or not str(raw).strip():
        return True
    try:
        d = json.loads(raw)
    except json.JSONDecodeError:
        return True
    if not isinstance(d, dict):
        return True
    if not d:
        return True
    if d.get("import_bulk") is True:
        return True
    return False


def delete_preventivi_senza_estrazione_in_folder(folder: str) -> dict:
    """
    Elimina dal DB i preventivi della cartella ancora senza estrazione reale
    (solo import_bulk / JSON vuoto). Rimuove file in uploads/, riga in fattore_af_cache, data/<id>.json.
    Utile dopo un'estrazione interrotta (es. bloccata al PDF 45).
    """
    folder = os.path.abspath(folder)
    if not os.path.isdir(folder):
        raise FileNotFoundError(folder)

    pdf_names: set[str] = set()
    for name in os.listdir(folder):
        if not name.lower().endswith(".pdf"):
            continue
        s = secure_filename(name)
        if s:
            pdf_names.add(s)

    if not pdf_names:
        return {"cancellati": 0, "file_rimossi": 0, "cache_rimosse": 0, "errori": []}

    _ensure_dirs()
    os.makedirs(DATA_DIR, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    placeholders = ",".join("?" * len(pdf_names))
    cur.execute(
        f"SELECT id, filename, filepath, extracted_info FROM preventivi WHERE filename IN ({placeholders})",
        tuple(pdf_names),
    )
    rows = cur.fetchall()

    cancellati = 0
    file_rimossi = 0
    cache_rimosse = 0
    errori: list[str] = []

    cur.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='fattore_af_cache'"
    )
    has_af_cache = cur.fetchone() is not None

    for pid, fname, fpath, ext_raw in rows:
        if not _extracted_info_senza_estrazione(ext_raw):
            continue
        try:
            if has_af_cache:
                cur.execute("DELETE FROM fattore_af_cache WHERE preventivo_id = ?", (pid,))
                cache_rimosse += 1
            cur.execute("DELETE FROM preventivi WHERE id = ?", (pid,))
            cancellati += 1
            if fpath and os.path.isfile(fpath):
                try:
                    os.remove(fpath)
                    file_rimossi += 1
                except OSError as e:
                    errori.append(f"{fname} file: {e}")
            json_side = os.path.join(DATA_DIR, f"{pid}.json")
            if os.path.isfile(json_side):
                try:
                    os.remove(json_side)
                except OSError as e:
                    errori.append(f"{fname} json: {e}")
        except Exception as e:
            errori.append(f"{fname}: {e}")

    conn.commit()
    conn.close()

    return {
        "cancellati": cancellati,
        "file_rimossi": file_rimossi,
        "cache_rimosse": cache_rimosse,
        "errori": errori,
    }


def _ensure_dirs():
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(os.path.join(os.path.dirname(UPLOAD_FOLDER), "data"), exist_ok=True)


def process_pdfs_in_folder(folder: str, *, run_cleanup: bool = True) -> dict:
    """
    Per ogni PDF nella cartella:
    - se già in DB con estrazione valida: salta;
    - se in DB ma solo import_bulk / vuoto: estrae con Anthropic e UPDATE; se non salvabile, rimuove la riga;
    - se non in DB: copia in uploads, estrae, INSERT solo se estrazione salvabile (mai righe senza Claude ok).

    Se run_cleanup, alla fine elimina residui import_bulk nella cartella.
    """
    folder = os.path.abspath(folder)
    if not os.path.isdir(folder):
        raise FileNotFoundError(folder)

    _ensure_updated_at_column()
    _ensure_dirs()
    os.makedirs(DATA_DIR, exist_ok=True)

    backend_dir = os.path.dirname(os.path.abspath(__file__))
    print("[*] Caricamento modulo app (Claude / PDF)...", flush=True)
    prev = os.getcwd()
    os.chdir(backend_dir)
    try:
        import app as app_module  # noqa: E402

        extract_text = app_module.extract_text_from_pdf
        extract_claude = app_module.extract_info_with_claude
    finally:
        os.chdir(prev)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='fattore_af_cache'"
    )
    has_af_cache = cur.fetchone() is not None

    pdfs = sorted(f for f in os.listdir(folder) if f.lower().endswith(".pdf"))
    estratte = 0
    saltati_gia_ok = 0
    saltati_non_salvabile = 0
    errori: list[str] = []

    interrotto = False
    try:
        for idx, name in enumerate(pdfs, 1):
            safe = secure_filename(name)
            if not safe:
                errori.append(f"Nome non valido: {name}")
                continue

            cur.execute(
                "SELECT id, filepath, extracted_info FROM preventivi WHERE filename = ?",
                (safe,),
            )
            row = cur.fetchone()
            pid = None
            filepath: str | None = None
            is_new = False

            if row:
                pid, filepath, ext_raw = row[0], row[1], row[2]
                if not _extracted_info_senza_estrazione(ext_raw):
                    saltati_gia_ok += 1
                    continue
                if not filepath or not os.path.isfile(filepath):
                    errori.append(f"{safe}: file assente su disco ({filepath})")
                    continue
            else:
                src = os.path.join(folder, name)
                unique_disk = f"{uuid.uuid4()}_{safe}"
                filepath = os.path.join(UPLOAD_FOLDER, unique_disk)
                try:
                    with open(src, "rb") as rf, open(filepath, "wb") as wf:
                        wf.write(rf.read())
                except OSError as e:
                    errori.append(f"{name}: {e}")
                    continue
                is_new = True

            print(f"[*] Estrazione ({idx}/{len(pdfs)}): {safe}", flush=True)
            try:
                text = extract_text(filepath)
                extracted_info = extract_claude(text, pdf_path=filepath)
                if not extracted_info:
                    extracted_info = {"error": "estrazione vuota"}
            except Exception as e:
                errori.append(f"{safe}: {e}")
                if is_new and filepath and os.path.isfile(filepath):
                    try:
                        os.remove(filepath)
                    except OSError:
                        pass
                continue

            if _fatal_anthropic_config_error(extracted_info):
                print(
                    "ERRORE: configurazione Anthropic (es. ANTHROPIC_API_KEY in backend/.env). "
                    "Interrompo.",
                    file=sys.stderr,
                    flush=True,
                )
                if is_new and filepath and os.path.isfile(filepath):
                    try:
                        os.remove(filepath)
                    except OSError:
                        pass
                elif pid:
                    _delete_one_preventivo(cur, conn, pid, filepath, has_af_cache)
                sys.exit(1)

            if not _estrazione_salvabile_in_db(extracted_info):
                saltati_non_salvabile += 1
                if pid:
                    _delete_one_preventivo(cur, conn, pid, filepath, has_af_cache)
                elif is_new and filepath and os.path.isfile(filepath):
                    try:
                        os.remove(filepath)
                    except OSError:
                        pass
                continue

            now_u = datetime.now().isoformat()
            if pid:
                cur.execute(
                    "UPDATE preventivi SET extracted_info = ?, raw_text = ?, updated_at = ? WHERE id = ?",
                    (json.dumps(extracted_info, ensure_ascii=False), text, now_u, pid),
                )
            else:
                pid = str(uuid.uuid4())
                cur.execute(
                    """
                    INSERT INTO preventivi (id, filename, filepath, upload_date, extracted_info, raw_text, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        pid,
                        safe,
                        filepath,
                        now_u,
                        json.dumps(extracted_info, ensure_ascii=False),
                        text,
                        now_u,
                    ),
                )
            conn.commit()
            estratte += 1
    except KeyboardInterrupt:
        interrotto = True
        print("\n[!] Interrotto. Pulizia record senza estrazione...", flush=True)
    finally:
        conn.close()

    cleanup: dict = {}
    if run_cleanup:
        print("[*] Rimozione residui import_bulk nella cartella...", flush=True)
        cleanup = delete_preventivi_senza_estrazione_in_folder(folder)
        if cleanup["cancellati"]:
            print(
                f"    Eliminati dal DB: {cleanup['cancellati']} · file uploads rimossi: {cleanup['file_rimossi']}",
                flush=True,
            )

    out = {
        "folder": folder,
        "pdf_in_cartella": len(pdfs),
        "estratte_ok": estratte,
        "saltati_gia_estratti": saltati_gia_ok,
        "saltati_estrazione_non_salvabile": saltati_non_salvabile,
        "errori": errori,
        "interrotto": interrotto,
    }
    if run_cleanup and cleanup:
        out["cleanup_senza_estrazione"] = cleanup
    return out


def main():
    parser = argparse.ArgumentParser(
        description="Import PDF con estrazione Anthropic obbligatoria (nessun record senza Claude)"
    )
    parser.add_argument(
        "cartella",
        nargs="?",
        default=os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "OFFERTE",
        ),
        help="Cartella con i PDF (default: ../OFFERTE nella root del repo)",
    )
    parser.add_argument(
        "--no-commesse",
        action="store_true",
        help="Non reimportare l'Excel commesse",
    )
    parser.add_argument(
        "--no-mapping",
        action="store_true",
        help="Non reimportare l'elenco offerta ↔ commessa (xlsm)",
    )
    parser.add_argument(
        "--extract-only",
        action="store_true",
        help="Solo cartella OFFERTE: salta Excel commesse/mapping; stesso flusso Anthropic (nuovi + bulk da completare)",
    )
    parser.add_argument(
        "--keep-pending",
        action="store_true",
        help="Dopo l'estrazione NON eliminare i record ancora solo import_bulk (per riprendere senza re-import)",
    )
    parser.add_argument(
        "--cleanup-bulk-only",
        action="store_true",
        help="Solo pulizia: elimina dal DB (e uploads) i preventivi di questa cartella ancora senza estrazione",
    )
    args = parser.parse_args()

    if not os.path.isdir(args.cartella):
        print(f"ERRORE: cartella non trovata: {args.cartella}", file=sys.stderr)
        sys.exit(1)

    print(f"[*] Database: {DB_PATH}")
    print(f"[*] Cartella: {args.cartella}")

    if args.cleanup_bulk_only:
        _ensure_updated_at_column()
        cl = delete_preventivi_senza_estrazione_in_folder(args.cartella)
        print()
        print("=== Pulizia import bulk senza estrazione ===")
        print(f"    Eliminati dal DB: {cl['cancellati']}")
        print(f"    File rimossi da uploads: {cl['file_rimossi']}")
        if cl["errori"]:
            print(f"[!] Avvisi: {len(cl['errori'])}")
            for e in cl["errori"][:15]:
                print(f"    {e}")
        return

    if args.extract_only:
        ex = process_pdfs_in_folder(args.cartella, run_cleanup=not args.keep_pending)
        print()
        print("=== Estrazione Anthropic (cartella) ===")
        print(f"    PDF in cartella: {ex['pdf_in_cartella']}")
        print(f"    Inseriti/aggiornati: {ex['estratte_ok']}")
        print(f"    Già estratti (saltati): {ex['saltati_gia_estratti']}")
        print(f"    Non salvati (estrazione insufficiente): {ex['saltati_estrazione_non_salvabile']}")
        if ex.get("cleanup_senza_estrazione"):
            c = ex["cleanup_senza_estrazione"]
            print(f"    Pulizia DB residui: {c['cancellati']} rimossi")
        if ex["errori"]:
            print(f"[!] Errori: {len(ex['errori'])}")
            for e in ex["errori"][:20]:
                print(f"    {e}")
        if ex.get("interrotto"):
            sys.exit(130)
        return

    if not args.no_commesse:
        xlsx = default_xlsx_path()
        if os.path.isfile(xlsx):
            rows = load_rows_from_xlsx(xlsx)
            r = import_to_sqlite(DB_PATH, rows, xlsx)
            print(f"[*] Commesse importate: {r['imported']} da Excel")
        else:
            print(f"[!] Excel commesse non trovato: {xlsx}")

    if not args.no_mapping:
        mx = default_mapping_xlsx_path()
        if os.path.isfile(mx):
            mrows = load_rows_from_mapping_xlsx(mx)
            mr = import_mapping_to_sqlite(DB_PATH, mrows, mx)
            print(f"[*] Mapping offerta↔commessa: {mr['imported']} righe da elenco")
        else:
            print(f"[!] Elenco mapping non trovato: {mx}")

    print("[*] Import + estrazione Anthropic (nessun record senza extracted_info valido)...")
    stats = process_pdfs_in_folder(args.cartella, run_cleanup=not args.keep_pending)
    print(f"[*] PDF in cartella: {stats['pdf_in_cartella']}")
    print(f"[*] Inseriti/aggiornati: {stats['estratte_ok']}")
    print(f"[*] Già estratti (saltati): {stats['saltati_gia_estratti']}")
    print(f"[*] Non salvati (estrazione insufficiente): {stats['saltati_estrazione_non_salvabile']}")
    if stats.get("cleanup_senza_estrazione"):
        c = stats["cleanup_senza_estrazione"]
        print(f"[*] Pulizia residui import_bulk: {c['cancellati']} rimossi")
    if stats["errori"]:
        print(f"[!] Errori: {len(stats['errori'])}")
        for e in stats["errori"][:10]:
            print(f"    {e}")
    if stats.get("interrotto"):
        sys.exit(130)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT filename FROM preventivi")
    filenames = [r[0] for r in cur.fetchall()]
    conn.close()

    by_norm = rows_grouped_by_cliente_norm(DB_PATH)
    matches = match_preventivi_filenames(filenames, by_norm, DB_PATH)
    summary = {
        "preventivi": len(matches),
        "mapped": 0,
        "mapped_no_ore": 0,
        "ambiguous_mapping": 0,
        "unique": 0,
        "ambiguous": 0,
        "none": 0,
        "unparsed": 0,
    }
    for m in matches:
        k = m.get("match")
        if k in summary:
            summary[k] += 1

    print()
    print("=== Match offerte <-> commesse (nr. preventivo + elenco, poi fallback cliente) ===")
    print(f"    Totale preventivi in DB: {summary['preventivi']}")
    print(f"    mapped (nr. prev. -> commessa + ore):     {summary['mapped']}")
    print(f"    mapped_no_ore (commessa senza ore Excel): {summary['mapped_no_ore']}")
    print(f"    ambiguous_mapping (stesso prev, più comm.): {summary['ambiguous_mapping']}")
    print(f"    unique (un solo commessa per cliente): {summary['unique']}")
    print(f"    ambiguous (più commesse stesso cliente): {summary['ambiguous']}")
    print(f"    none (cliente non in elenco commesse): {summary['none']}")
    print(f"    unparsed (nome file non standard):     {summary['unparsed']}")


if __name__ == "__main__":
    main()
