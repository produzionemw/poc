"""
Costruisce un DataFrame per il training unendo:
- ore per reparto dal foglio Elaborato (commesse 25 xlsm);
- peso/dimensioni da `preventivi.extracted_info` in SQLite;
- legame commessa ↔ nr. preventivo da `offerta_commessa_map`.

Senza mapping importato e preventivi con estrazione OpenAI, le righe utilizzabili sono zero.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
from typing import Any

import numpy as np
import pandas as pd

from commesse_ore import default_xlsx_path, load_rows_from_xlsx


def normalize_commessa_key(s: Any) -> str | None:
    """
    Chiave unica per confrontare commesse tra file diversi.
    Es. 25/1 e 25/001 -> 25/001; rimuove suffissi tipo [I] da gestionale.
    """
    if s is None or (isinstance(s, float) and np.isnan(s)):
        return None
    t = str(s).strip()
    if not t or t.lower() == "nuova":
        return None
    t = re.sub(r"\s*\[[IC]\]\s*$", "", t, flags=re.IGNORECASE)
    t = t.strip()
    m = re.match(r"^(\d{2})/(\d{1,4})$", t)
    if m:
        return f"{m.group(1)}/{int(m.group(2)):03d}"
    return t


def load_commessa_crosswalk(path: str) -> dict[str, str]:
    """
    CSV con colonne: commessa_storica, commessa_2025
    (valori come in Excel, es. 878/23 -> 25/042). La lookup usa la stringa storica esatta.
    """
    import csv

    out: dict[str, str] = {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        r = csv.DictReader(f)
        for row in r:
            a = (row.get("commessa_storica") or row.get("storica") or "").strip()
            b = (row.get("commessa_2025") or row.get("2025") or "").strip()
            if a and b:
                out[a] = b
    return out


def extract_dims_from_info(info: dict[str, Any]) -> dict[str, float] | None:
    """Stessa logica di app._extract_dims: peso + lati + altezza."""
    if not info:
        return None
    dims = info.get("caratteristiche_dimensioni", {})
    peso_raw = info.get("peso_stimato", {})

    peso = None
    if isinstance(peso_raw, dict):
        peso = peso_raw.get("struttura_kg")
    if not peso:
        peso = info.get("peso") or info.get("peso_kg")

    lato_a = lato_b = altezza = None
    if isinstance(dims, dict):
        dp = dims.get("dimensioni_in_pianta_mm", {})
        if isinstance(dp, dict):
            lato_a = dp.get("lunghezza") or dp.get("larghezza")
            lato_b = dp.get("larghezza") or dp.get("lunghezza")
        elif isinstance(dp, str):
            parts = [x.strip() for x in dp.replace("×", "x").replace("X", "x").lower().split("x")]
            if len(parts) >= 2:
                try:
                    lato_a = float(parts[0])
                    lato_b = float(parts[1])
                except ValueError:
                    pass
        altezza = (
            dims.get("h_totale_struttura_mm")
            or dims.get("altezza_mm")
            or dims.get("h_netto_mm")
        )

    if not all([peso, lato_a, lato_b, altezza]):
        return None

    return {
        "peso": float(peso),
        "lato_a": float(lato_a),
        "lato_b": float(lato_b),
        "altezza": float(altezza),
    }


def _filename_matches_preventivo(filename: str, nr_prev: int) -> bool:
    """Es. ..._preventivo_12826.pdf o ..._12826_conferma."""
    stem = os.path.splitext(os.path.basename(filename))[0]
    stem = re.sub(r"\s+conferma\s*$", "", stem, flags=re.IGNORECASE)
    m = re.match(r"^(\d{4})_(.+?)_preventivo_(\d+)", stem, re.IGNORECASE)
    if not m:
        return False
    return int(m.group(3)) == int(nr_prev)


def build_training_frame_from_commesse_join(
    db_path: str,
    ore_xlsx_path: str,
) -> pd.DataFrame:
    ore_rows = load_rows_from_xlsx(ore_xlsx_path)
    ore_by_comm = {r["nr_commessa"]: r for r in ore_rows}

    if not os.path.isfile(db_path):
        raise FileNotFoundError(db_path)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    try:
        cur.execute("SELECT nr_preventivo, nr_commessa FROM offerta_commessa_map")
        mapping_rows = cur.fetchall()
    except sqlite3.OperationalError:
        mapping_rows = []
    cur.execute("SELECT filename, extracted_info FROM preventivi")
    preventivi = cur.fetchall()
    conn.close()

    commessa_to_prevs: dict[str, set[int]] = {}
    for prev, comm in mapping_rows:
        if prev is None or comm is None:
            continue
        c = str(comm).strip()
        try:
            pv = int(float(prev))
        except (TypeError, ValueError):
            continue
        commessa_to_prevs.setdefault(c, set()).add(pv)

    out: list[dict[str, Any]] = []
    for nr_comm, prevs in commessa_to_prevs.items():
        ore = ore_by_comm.get(nr_comm)
        if not ore:
            continue

        dims_info = None
        for pv in sorted(prevs):
            for fn, raw in preventivi:
                if not raw or str(raw).strip() in ("", "{}"):
                    continue
                if not _filename_matches_preventivo(fn, pv):
                    continue
                try:
                    info = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if not isinstance(info, dict):
                    continue
                d = extract_dims_from_info(info)
                if d:
                    dims_info = d
                    break
            if dims_info:
                break

        if not dims_info:
            continue

        la = dims_info["lato_a"]
        lb = dims_info["lato_b"]
        h = dims_info["altezza"]
        peso = dims_info["peso"]
        vol = la * lb * h

        def oz(key: str) -> float:
            v = ore.get(key)
            if v is None or (isinstance(v, float) and np.isnan(v)):
                return 0.0
            return float(v)

        out.append(
            {
                "Peso_kg": peso,
                "Portata": 300.0,
                "LatoCorto_mm": la,
                "LatoLungo_mm": lb,
                "Altezza_mm": h,
                "Volume_mm3": vol,
                "OreProg": oz("ore_prog"),
                "OreNest": oz("ore_nest"),
                "OreTaglio": 0.0,
                "OrePieg": oz("ore_pieg"),
                "OreSald": oz("ore_sald"),
                "OreImb": oz("ore_imba"),
                "Commessa": nr_comm,
            }
        )

    if not out:
        return pd.DataFrame()

    df = pd.DataFrame(out)
    df = df[df["LatoCorto_mm"] < 10_000]
    df["Portata"] = df["Portata"].fillna(df["Portata"].median())
    return df


def merge_commesse_targets_into_legacy(
    df_legacy: pd.DataFrame,
    ore_xlsx_path: str,
    crosswalk: dict[str, str] | None = None,
) -> tuple[pd.DataFrame, int, dict[str, int]]:
    """
    Sostituisce le colonne ore (TARGETS) nel dataset storico quando la colonna Commessa
    coincide (normalizzata) con una riga del foglio Elaborato.

    Nota: spesso il file storico usa codici tipo N/24 mentre l'Elaborato 2025 usa 25/NNN;
    in quel caso servono poche coincidenze dirette. Opzionale: CSV di crosswalk
    commessa_storica -> commessa_2025.

    OreTaglio viene messa a 0 (nel foglio commesse il NEST include il taglio).
    """
    ore_rows = load_rows_from_xlsx(ore_xlsx_path)
    by_comm: dict[str, dict[str, Any]] = {}
    for r in ore_rows:
        k = normalize_commessa_key(r.get("nr_commessa"))
        if k:
            by_comm[k] = r

    crosswalk = crosswalk or {}
    tgt_map = [
        ("OreProg", "ore_prog"),
        ("OreNest", "ore_nest"),
        ("OrePieg", "ore_pieg"),
        ("OreSald", "ore_sald"),
        ("OreImb", "ore_imba"),
    ]

    df = df_legacy.copy()
    matched = 0
    direct = 0
    via_xw = 0
    for i in df.index:
        raw = df.at[i, "Commessa"]
        raw_s = str(raw).strip() if raw is not None and not (
            isinstance(raw, float) and np.isnan(raw)
        ) else ""

        ck = normalize_commessa_key(raw)
        used_crosswalk = False
        if not ck or ck not in by_comm:
            if raw_s in crosswalk:
                ck = normalize_commessa_key(crosswalk[raw_s])
                used_crosswalk = bool(ck and ck in by_comm)
            if not ck or ck not in by_comm:
                continue
            if used_crosswalk:
                via_xw += 1
        else:
            direct += 1

        o = by_comm[ck]
        matched += 1

        for tgt, ok in tgt_map:
            v = o.get(ok)
            if v is not None and not (isinstance(v, float) and np.isnan(v)):
                df.at[i, tgt] = float(v)
        df.at[i, "OreTaglio"] = 0.0

    stats = {
        "matched": matched,
        "direct_normalize": direct,
        "via_crosswalk": via_xw,
    }
    return df, matched, stats
