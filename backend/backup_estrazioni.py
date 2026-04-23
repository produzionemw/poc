#!/usr/bin/env python3
"""
Esporta le estrazioni Claude dal DB in file JSON individuali + un file riepilogativo.

Output:
  backup_estrazioni/
    <filename_senza_estensione>.json   (uno per preventivo)
    _all.json                          (tutti in unico array)
    _summary.txt                       (riepilogo conteggi)
"""
import json
import os
import sqlite3
import sys
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "preventivi.db")
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backup_estrazioni")


def run():
    os.makedirs(OUT_DIR, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT id, filename, upload_date, updated_at, extracted_info
        FROM preventivi
        WHERE extracted_info IS NOT NULL
          AND extracted_info != ''
          AND (json_extract(extracted_info, '$.import_bulk') IS NULL
               OR json_extract(extracted_info, '$.import_bulk') = 0)
        ORDER BY filename
    """)
    rows = cur.fetchall()
    conn.close()

    all_records = []
    salvati = 0
    saltati = 0

    for pid, filename, upload_date, updated_at, ext_raw in rows:
        try:
            info = json.loads(ext_raw)
        except Exception:
            saltati += 1
            continue

        record = {
            "id": pid,
            "filename": filename,
            "upload_date": upload_date,
            "updated_at": updated_at,
            "extracted_info": info,
        }
        all_records.append(record)

        # File individuale: nome basato sul filename PDF
        base = os.path.splitext(filename)[0] if filename else pid
        out_path = os.path.join(OUT_DIR, f"{base}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)
        salvati += 1

    # File riepilogativo unico
    all_path = os.path.join(OUT_DIR, "_all.json")
    with open(all_path, "w", encoding="utf-8") as f:
        json.dump(all_records, f, ensure_ascii=False, indent=2)

    # Summary
    summary_path = os.path.join(OUT_DIR, "_summary.txt")
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(f"Backup estrazioni — {datetime.now().isoformat()}\n")
        f.write(f"Salvati: {salvati}\n")
        f.write(f"Saltati (JSON non valido): {saltati}\n")
        f.write(f"Cartella: {OUT_DIR}\n")

    print(f"✓ Backup completato: {salvati} file JSON in {OUT_DIR}")
    print(f"  Riepilogo: {summary_path}")
    print(f"  File unico: {all_path}")
    if saltati:
        print(f"  Saltati (JSON malformato): {saltati}")

    return salvati


if __name__ == "__main__":
    run()
