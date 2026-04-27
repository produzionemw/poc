#!/usr/bin/env python3
"""
Training dei 6 modelli Random Forest (ore per fase).

Esecuzione dalla root del progetto:
  python train_models.py
      Sceglie automaticamente il dataset più ricco: tra tutti i dati/Estrazione*.xlsx
      e tra i fogli Elaborato delle commesse (es. 24 vs 25 .xlsm) quello con più righe.

  python train_models.py --no-auto
      Usa i percorsi fissi --legacy-xlsx e --commesse-xlsx (default sotto).

  python train_models.py --legacy-only
  python train_models.py --from-db

Richiede: backend/ml_model.py, dipendenze in backend (pandas, sklearn, ...).
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys


def _root() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def _backend() -> str:
    return os.path.join(_root(), "backend")


def main() -> int:
    root = _root()
    backend = _backend()
    ml = os.path.join(backend, "ml_model.py")

    legacy = os.path.join(root, "dati", "Estrazione fattore k (1).xlsx")
    _ore_candidates = [
        os.path.join(root, "dati", "ORE PER REPARTO PER COMMESSA commesse 25.xlsm"),
        os.path.join(root, "dati", "ORE_PER_REPARTO_commesse_25_Elaborato.csv"),
        os.path.join(root, "ORE PER REPARTO PER COMMESSA commesse 25.xlsm"),
    ]
    commesse = next((p for p in _ore_candidates if os.path.isfile(p)), _ore_candidates[0])
    db = os.path.join(backend, "preventivi.db")

    p = argparse.ArgumentParser(description="Addestra i modelli ML (MetalWorkingPOC)")
    p.add_argument(
        "--no-auto",
        action="store_true",
        help="Non scansionare la cartella: usa solo --legacy-xlsx e --commesse-xlsx indicati",
    )
    p.add_argument(
        "--legacy-only",
        action="store_true",
        help="Solo file storico Metal+ (senza sostituire le ore dal foglio commesse)",
    )
    p.add_argument(
        "--from-db",
        action="store_true",
        help="Dataset solo da DB + Excel commesse (serve estrazione dimensioni sui preventivi)",
    )
    p.add_argument(
        "--legacy-xlsx",
        default=legacy,
        help="Dataset storico con dimensioni e Commessa (con --no-auto)",
    )
    p.add_argument(
        "--commesse-xlsx",
        default=commesse,
        help="Excel ore reparto / foglio Elaborato (con --no-auto o come fallback)",
    )
    p.add_argument("--db", default=db, help="Percorso preventivi.db")
    p.add_argument(
        "--min-rows",
        type=int,
        default=40,
        help="Solo per --from-db: numero minimo di righe",
    )
    p.add_argument(
        "--commessa-crosswalk",
        default=None,
        help="CSV commessa_storica,commessa_2025 (merge)",
    )
    args = p.parse_args()

    if args.legacy_only and args.from_db:
        print("ERRORE: usare solo uno tra --legacy-only e --from-db", file=sys.stderr)
        return 2

    if not os.path.isfile(ml):
        print(f"ERRORE: non trovato {ml}", file=sys.stderr)
        return 1

    use_auto = not args.no_auto
    legacy_path = os.path.abspath(args.legacy_xlsx)
    commesse_path = os.path.abspath(args.commesse_xlsx)

    if use_auto:
        sys.path.insert(0, backend)
        from dataset_pick import find_richest_commesse_elaborato, find_richest_legacy_xlsx

        leg_p, leg_n = find_richest_legacy_xlsx(root)
        ore_p, ore_n = find_richest_commesse_elaborato(root)

        if args.legacy_only:
            if leg_p:
                legacy_path = os.path.abspath(leg_p)
            elif os.path.isfile(legacy_path):
                pass
            else:
                print(f"ERRORE: nessun dati/Estrazione*.xlsx trovato in {root}/dati/", file=sys.stderr)
                return 1
            print("Scelta automatica (più righe nel dataset dimensionale):")
            print(f"  Legacy: {legacy_path} ({leg_n or '?'} righe)")
        elif args.from_db:
            if ore_p:
                commesse_path = os.path.abspath(ore_p)
            elif os.path.isfile(commesse_path):
                pass
            else:
                print("ERRORE: nessun file commesse .xlsm trovato per Elaborato", file=sys.stderr)
                return 1
            print("Scelta automatica (più righe nel foglio Elaborato):")
            print(f"  Ore commesse: {commesse_path} ({ore_n or '?'} righe)")
        else:
            if leg_p:
                legacy_path = os.path.abspath(leg_p)
            if ore_p:
                commesse_path = os.path.abspath(ore_p)
            if not leg_p and not os.path.isfile(legacy_path):
                print(
                    f"ERRORE: nessun dati/Estrazione*.xlsx in {os.path.join(root, 'dati')}",
                    file=sys.stderr,
                )
                return 1
            if not ore_p and not os.path.isfile(commesse_path):
                print("ERRORE: nessun file ORE PER REPARTO... commesse *.xlsm trovato", file=sys.stderr)
                return 1
            print("Scelta automatica (dataset più ricco):")
            print(f"  Legacy: {legacy_path} ({leg_n or '?'} righe)")
            print(f"  Ore Elaborato: {commesse_path} ({ore_n or '?'} righe commessa)")

    cmd: list[str] = [sys.executable, ml]

    if args.from_db:
        if not os.path.isfile(commesse_path):
            print(f"ERRORE: file commesse non trovato: {commesse_path}", file=sys.stderr)
            return 1
        cmd += [
            "--from-commesse",
            "--db",
            os.path.abspath(args.db),
            "--commesse-xlsx",
            commesse_path,
            "--min-rows",
            str(args.min_rows),
        ]
    elif args.legacy_only:
        if not os.path.isfile(legacy_path):
            print(f"ERRORE: file non trovato: {legacy_path}", file=sys.stderr)
            return 1
        cmd += ["--data", legacy_path]
    else:
        if not os.path.isfile(legacy_path):
            print(f"ERRORE: file storico non trovato: {legacy_path}", file=sys.stderr)
            return 1
        if not os.path.isfile(commesse_path):
            print(f"ERRORE: file commesse non trovato: {commesse_path}", file=sys.stderr)
            return 1
        cmd += [
            "--data",
            legacy_path,
            "--merge-commesse-ore",
            "--commesse-xlsx",
            commesse_path,
        ]
        if args.commessa_crosswalk:
            cmd += ["--commessa-crosswalk", os.path.abspath(args.commessa_crosswalk)]

    print("Comando:", " ".join(cmd))
    print("Directory:", backend)
    r = subprocess.run(cmd, cwd=backend)
    return r.returncode


if __name__ == "__main__":
    raise SystemExit(main())
