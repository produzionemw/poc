"""
Scelta automatica dei file per il training: dataset dimensionale (Estrazione*.xlsx)
e foglio ore commesse (Elaborato) più ricco tra candidati 24/25/...
"""
from __future__ import annotations

import glob
import os

from commesse_ore import load_rows_from_xlsx
from ml_model import _load_training_frame


def find_richest_legacy_xlsx(repo_root: str) -> tuple[str | None, int]:
    """
    Tra tutti i file dati/Estrazione*.xlsx, restituisce quello con più righe
    utilizzabili da _load_training_frame.
    """
    pattern = os.path.join(repo_root, "dati", "Estrazione*.xlsx")
    paths = sorted(glob.glob(pattern))
    best: tuple[str | None, int] = (None, 0)
    for p in paths:
        try:
            df = _load_training_frame(p)
            n = len(df)
            if n > best[1]:
                best = (p, n)
        except Exception:
            continue
    return best


def find_richest_commesse_elaborato(repo_root: str) -> tuple[str | None, int]:
    """
    Tra i fogli Elaborato dei candidati .xlsm (commesse 24, 25, ...), restituisce
    il file con più righe commessa.
    """
    candidates: list[str] = []
    for pat in (
        "ORE PER REPARTO PER COMMESSA commesse *.xlsm",
        "*commesse*commesse*.xlsm",
    ):
        candidates.extend(glob.glob(os.path.join(repo_root, pat)))

    seen = set()
    uniq: list[str] = []
    for p in candidates:
        ap = os.path.normpath(os.path.abspath(p))
        if ap not in seen and os.path.isfile(ap):
            seen.add(ap)
            uniq.append(ap)

    best: tuple[str | None, int] = (None, 0)
    for p in uniq:
        try:
            rows = load_rows_from_xlsx(p)
            n = len(rows)
            if n > best[1]:
                best = (p, n)
        except Exception:
            continue
    return best


def pick_training_sources(repo_root: str) -> dict:
    """
    Restituisce percorsi scelti e conteggi per logging.
    """
    leg_path, leg_n = find_richest_legacy_xlsx(repo_root)
    ore_path, ore_n = find_richest_commesse_elaborato(repo_root)
    return {
        "legacy_xlsx": leg_path,
        "legacy_rows": leg_n,
        "commesse_xlsx": ore_path,
        "commesse_elaborato_rows": ore_n,
    }
