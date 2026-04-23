"""
Training e inferenza Random Forest — ore per fase + AF normalizzato.

Esempi:
  python ml_model.py --data "../dati/Estrazione fattore k (1).xlsx"
  python ml_model.py --data "../dati/....xlsx" --merge-commesse-ore
      --commesse-xlsx "../ORE PER REPARTO PER COMMESSA commesse 25.xlsm"
  python ml_model.py --from-commesse --db preventivi.db
      (richiede preventivi con estrazione dimensioni + mapping in DB)
"""
import argparse
import glob
import json
import os
import shutil
from datetime import datetime, timezone

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE_DIR, "ml_model.pkl")
METRICS_PATH = os.path.join(BASE_DIR, "ml_metrics.json")
CHARTS_DIR = os.path.join(BASE_DIR, "ml_charts")
ML_MODELS_DIR = os.path.join(BASE_DIR, "ml_models")

FEATURE_COLS = [
    "Peso_kg",
    "Portata",
    "LatoCorto_mm",
    "LatoLungo_mm",
    "Altezza_mm",
    "Volume_mm3",
]

TARGETS = [
    "OreProg",
    "OreNest",
    "OreTaglio",
    "OrePieg",
    "OreSald",
    "OreImb",
]


def _feature_importance_list(model) -> list:
    return [
        {"feature": f, "importance": round(float(i), 4)}
        for f, i in sorted(
            zip(FEATURE_COLS, model.feature_importances_),
            key=lambda x: x[1],
            reverse=True,
        )
    ]


def _save_phase_charts_png(
    target: str,
    model_t,
    y_test_arr: np.ndarray,
    y_pred: np.ndarray,
    r2: float,
    mae: float,
) -> None:
    """Salva i tre PNG di valutazione per la fase in ml_charts/<target>/."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fi = _feature_importance_list(model_t)
    phase_dir = os.path.join(CHARTS_DIR, target)
    os.makedirs(phase_dir, exist_ok=True)

    features = [x["feature"] for x in fi]
    importances = [x["importance"] * 100 for x in fi]
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.barh(features[::-1], importances[::-1], color="#2e75b5")
    ax.set_xlabel("Importanza (%)")
    ax.set_title(f"Importanza delle variabili — {target}")
    ax.grid(axis="x", alpha=0.3)
    plt.tight_layout()
    plt.savefig(
        os.path.join(phase_dir, "feature_importance.png"),
        dpi=120,
        bbox_inches="tight",
    )
    plt.close()

    fig, ax = plt.subplots(figsize=(7, 7))
    ax.scatter(y_test_arr, y_pred, alpha=0.4, color="#2e75b5", s=20)
    lims = [0, float(max(y_test_arr.max(), y_pred.max()) * 1.05)]
    ax.plot(lims, lims, "r--", linewidth=1.5, label="Ideale (y=x)")
    ax.set_xlabel("Ore reali")
    ax.set_ylabel("Ore previste")
    ax.set_title(f"Previsto vs Reale ({target}) — R²={r2:.2f}  MAE={mae:.1f}h")
    ax.legend()
    ax.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(
        os.path.join(phase_dir, "predicted_vs_actual.png"),
        dpi=120,
        bbox_inches="tight",
    )
    plt.close()

    errors = y_pred - y_test_arr
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.hist(errors, bins=40, color="#2e75b5", alpha=0.75, edgecolor="white")
    ax.axvline(0, color="red", linestyle="--", linewidth=1.5)
    ax.set_xlabel("Errore (previsto − reale) in ore")
    ax.set_ylabel("Frequenza")
    ax.set_title(f"Distribuzione degli errori ({target})")
    ax.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(
        os.path.join(phase_dir, "residuals.png"),
        dpi=120,
        bbox_inches="tight",
    )
    plt.close()


def load_model():
    """Carica il modello singolo (OreImb) salvato. Ritorna None se non esiste."""
    if os.path.exists(MODEL_PATH):
        return joblib.load(MODEL_PATH)
    return None


def load_all_models():
    """Carica tutti i modelli per fase. Ritorna dict o None se manca qualunque pkl."""
    models = {}
    for target in TARGETS:
        path = os.path.join(ML_MODELS_DIR, f"model_{target}.pkl")
        if os.path.exists(path):
            models[target] = joblib.load(path)
    return models if len(models) == len(TARGETS) else None


def _load_model_for_target(target: str):
    path = os.path.join(ML_MODELS_DIR, f"model_{target}.pkl")
    if not os.path.isfile(path):
        return None
    return joblib.load(path)


_METRICS_CACHE = None
_METRICS_MTIME = None


def _invalidate_metrics_cache() -> None:
    global _METRICS_CACHE, _METRICS_MTIME
    _METRICS_CACHE = None
    _METRICS_MTIME = None


def clear_ml_artifacts(base_dir: str | None = None) -> None:
    """
    Elimina modelli .pkl, ml_metrics.json e contenuto di ml_charts/
    prima di un nuovo training dall'UI o da script.
    """
    bd = BASE_DIR if base_dir is None else os.path.abspath(base_dir)
    _invalidate_metrics_cache()
    models_dir = os.path.join(bd, "ml_models")
    if os.path.isdir(models_dir):
        for f in glob.glob(os.path.join(models_dir, "model_*.pkl")):
            try:
                os.remove(f)
            except OSError:
                pass
    mp = os.path.join(bd, "ml_model.pkl")
    if os.path.isfile(mp):
        try:
            os.remove(mp)
        except OSError:
            pass
    json_path = os.path.join(bd, "ml_metrics.json")
    if os.path.isfile(json_path):
        try:
            os.remove(json_path)
        except OSError:
            pass
    charts = os.path.join(bd, "ml_charts")
    if os.path.isdir(charts):
        for name in os.listdir(charts):
            p = os.path.join(charts, name)
            try:
                if os.path.isfile(p):
                    os.remove(p)
                elif os.path.isdir(p):
                    shutil.rmtree(p)
            except OSError:
                pass


def enrich_metrics_with_phase_feature_importance(metrics: dict | None) -> dict | None:
    """
    Se ml_metrics.json non ha feature_importance per fase (training vecchio),
    la calcola dai .pkl così UI e API mostrano valori diversi per ogni modello.
    """
    if not metrics or "modelli_per_fase" not in metrics:
        return metrics
    need = False
    for target in TARGETS:
        mp = metrics["modelli_per_fase"].get(target)
        if mp and not mp.get("feature_importance"):
            need = True
            break
    if not need:
        return metrics
    for target in TARGETS:
        mp = metrics["modelli_per_fase"].get(target)
        if not mp or mp.get("feature_importance"):
            continue
        model = _load_model_for_target(target)
        if model is None:
            continue
        mp["feature_importance"] = _feature_importance_list(model)
    return metrics


def load_metrics():
    """Carica le metriche salvate (con cache su mtime file)."""
    global _METRICS_CACHE, _METRICS_MTIME
    if not os.path.exists(METRICS_PATH):
        _invalidate_metrics_cache()
        return None
    mtime = os.path.getmtime(METRICS_PATH)
    if _METRICS_CACHE is not None and _METRICS_MTIME == mtime:
        return _METRICS_CACHE
    with open(METRICS_PATH, "r", encoding="utf-8") as f:
        metrics = json.load(f)
    metrics = enrich_metrics_with_phase_feature_importance(metrics)
    _METRICS_CACHE = metrics
    _METRICS_MTIME = mtime
    return metrics


def regenerate_charts_only(xlsx_path: str) -> None:
    """
    Rigenera PNG per ogni fase e aggiorna feature_importance in ml_metrics.json
    usando i modelli già addestrati (stesso split train/test del train()).
    Richiede lo stesso tipo di file .xlsx usato per l'ultimo training.
    """
    models = load_all_models()
    if not models:
        raise RuntimeError(
            "Servono tutti i file backend/ml_models/model_*.pkl (training completo)."
        )
    if not os.path.isfile(METRICS_PATH):
        raise RuntimeError("Manca ml_metrics.json. Eseguire prima il training.")
    df = _load_training_frame(os.path.abspath(xlsx_path))

    with open(METRICS_PATH, "r", encoding="utf-8") as f:
        metrics_base = json.load(f)
    if "modelli_per_fase" not in metrics_base:
        metrics_base["modelli_per_fase"] = {}

    for target in TARGETS:
        model_t = models[target]
        df_t = df.dropna(subset=[target])
        df_t = df_t.dropna(subset=FEATURE_COLS)
        if len(df_t) < 5:
            print(f"  {target}: troppi pochi campioni, skip grafici")
            continue

        X = df_t[FEATURE_COLS]
        y = df_t[target]
        bins = pd.cut(y, bins=[0, 3, 7, 999], labels=["small", "medium", "large"])
        try:
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=0.2, random_state=42, stratify=bins
            )
        except ValueError:
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=0.2, random_state=42
            )

        y_pred = model_t.predict(X_test)
        y_test_arr_t = np.asarray(y_test).ravel()
        y_pred_t = np.asarray(y_pred).ravel()
        mae = float(mean_absolute_error(y_test_arr_t, y_pred_t))
        r2 = float(r2_score(y_test_arr_t, y_pred_t))

        if target not in metrics_base["modelli_per_fase"]:
            metrics_base["modelli_per_fase"][target] = {}
        metrics_base["modelli_per_fase"][target]["feature_importance"] = (
            _feature_importance_list(model_t)
        )

        _save_phase_charts_png(
            target, model_t, y_test_arr_t, y_pred_t, r2, mae
        )

    with open(METRICS_PATH, "w", encoding="utf-8") as f:
        json.dump(metrics_base, f, indent=2)

    oreimb_charts = os.path.join(CHARTS_DIR, "OreImb")
    for name in (
        "feature_importance.png",
        "predicted_vs_actual.png",
        "residuals.png",
    ):
        src = os.path.join(oreimb_charts, name)
        dst = os.path.join(CHARTS_DIR, name)
        if os.path.isfile(src):
            shutil.copy2(src, dst)

    _invalidate_metrics_cache()
    print("OK: grafici per fase rigenerati in ml_charts/<Fase>/ e ml_metrics.json aggiornato.")


def predict(peso, lato_a, lato_b, altezza, portata=None):
    """
    Previsione con modelli per fase (o fallback OreImb singolo).
    Ritorna ore_per_fase, ore_totali, k_normalizzato, k_percentile, prediction (OreImb), ecc.
    """
    models = load_all_models()
    if not models:
        models = {"OreImb": load_model()}
        if not models["OreImb"]:
            raise ValueError("Modelli non trovati. Eseguire train().")

    portata_val = float(portata) if portata is not None else 300.0
    volume = float(lato_a) * float(lato_b) * float(altezza)
    X = np.array(
        [[peso, portata_val, lato_a, lato_b, altezza, volume]], dtype=float
    )

    ore_per_fase = {}
    for target, model in models.items():
        tree_preds = np.array([t.predict(X)[0] for t in model.estimators_])
        ore_per_fase[target] = {
            "valore": round(max(0, float(model.predict(X)[0])), 2),
            "low": round(max(0, float(np.percentile(tree_preds, 10))), 2),
            "high": round(max(0, float(np.percentile(tree_preds, 90))), 2),
        }

    ore_totali = sum(v["valore"] for v in ore_per_fase.values())
    peso_f = float(peso)
    k_norm = round(ore_totali / (peso_f / 1000), 1) if peso_f > 0 else 0.0

    metrics = load_metrics()
    k_percentile = 50
    if metrics and "k_percentiles" in metrics:
        p = metrics["k_percentiles"]
        if k_norm <= p["p10"]:
            k_percentile = 10
        elif k_norm <= p["p25"]:
            k_percentile = 25
        elif k_norm <= p["p50"]:
            k_percentile = 50
        elif k_norm <= p["p75"]:
            k_percentile = 75
        elif k_norm <= p["p90"]:
            k_percentile = 90
        else:
            k_percentile = 95

    oreibm = ore_per_fase.get("OreImb", {})
    return {
        "ore_per_fase": ore_per_fase,
        "ore_totali": round(ore_totali, 1),
        "k_normalizzato": k_norm,
        "k_percentile": k_percentile,
        "prediction": oreibm.get("valore", 0),
        "prediction_low": oreibm.get("low", 0),
        "prediction_high": oreibm.get("high", 0),
        "volume_m3": round(volume / 1e9, 4),
    }


def _load_training_frame(xlsx_path: str) -> pd.DataFrame:
    df = pd.read_excel(xlsx_path, header=1, engine="openpyxl")
    df.columns = [
        "_drop",
        "Peso_kg",
        "Portata",
        "LatoCorto_mm",
        "LatoLungo_mm",
        "Altezza_mm",
        "OreProg",
        "OreNest",
        "OreTaglio",
        "OrePieg",
        "OreSald",
        "OreImb",
        "Commessa",
    ]
    df = df.drop(columns=["_drop"]).dropna(subset=["Commessa"])
    df = df[df["LatoCorto_mm"] < 10_000]
    df["Portata"] = df["Portata"].fillna(df["Portata"].median())
    df["Volume_mm3"] = df["LatoCorto_mm"] * df["LatoLungo_mm"] * df["Altezza_mm"]
    return df


def train(xlsx_path: str | None = None, df: pd.DataFrame | None = None):
    """
    Addestra un modello per ogni fase e salva pkl, metriche e grafici (OreImb).
    Passare `df` (es. da join ore commesse + DB) oppure `xlsx_path` (formato storico Metal+).
    """
    if df is None:
        if not xlsx_path:
            raise ValueError("Specificare xlsx_path o df")
        df = _load_training_frame(xlsx_path)
    else:
        df = df.copy()
        if "Volume_mm3" not in df.columns:
            df["Volume_mm3"] = (
                df["LatoCorto_mm"] * df["LatoLungo_mm"] * df["Altezza_mm"]
            )
        df["Portata"] = df["Portata"].fillna(df["Portata"].median())

    # AF normalizzato su dataset (ore totali = somma fasi; NaN trattati come 0 per la somma)
    df_k = df.copy()
    for t in TARGETS:
        df_k[t] = df_k[t].fillna(0)
    df_k["OreTotali"] = df_k[TARGETS].sum(axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        k_series = df_k["OreTotali"] / (df_k["Peso_kg"] / 1000.0)
    k_series = k_series.replace([np.inf, -np.inf], np.nan).dropna()
    k_percentiles = {
        "p10": round(float(k_series.quantile(0.10)), 4),
        "p25": round(float(k_series.quantile(0.25)), 4),
        "p50": round(float(k_series.quantile(0.50)), 4),
        "p75": round(float(k_series.quantile(0.75)), 4),
        "p90": round(float(k_series.quantile(0.90)), 4),
    }
    mean_k = round(float(k_series.mean()), 4)
    std_k = round(float(k_series.std(ddof=0)), 4)

    os.makedirs(ML_MODELS_DIR, exist_ok=True)

    modelli_per_fase = {}
    model_oreimb = None
    y_test_oreimb = None
    y_pred_oreimb = None

    print("Training modelli per fase...")
    for target in TARGETS:
        df_t = df.dropna(subset=[target])
        df_t = df_t.dropna(subset=FEATURE_COLS)
        if len(df_t) < 5:
            print(f"  {target}: troppi pochi campioni dopo dropna, skip")
            continue

        X = df_t[FEATURE_COLS]
        y = df_t[target]

        bins = pd.cut(y, bins=[0, 3, 7, 999], labels=["small", "medium", "large"])
        try:
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=0.2, random_state=42, stratify=bins
            )
        except ValueError:
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=0.2, random_state=42
            )

        model_t = RandomForestRegressor(
            n_estimators=200, random_state=42, n_jobs=-1
        )
        model_t.fit(X_train, y_train)
        y_pred = model_t.predict(X_test)
        y_test_arr_t = np.asarray(y_test).ravel()
        y_pred_t = np.asarray(y_pred).ravel()
        mae = float(mean_absolute_error(y_test_arr_t, y_pred_t))
        r2 = float(r2_score(y_test_arr_t, y_pred_t))
        rmse_t = float(np.sqrt(mean_squared_error(y_test_arr_t, y_pred_t)))
        err_t = y_pred_t - y_test_arr_t
        acc1 = float((np.abs(err_t) < 1).mean() * 100)
        acc3 = float((np.abs(err_t) < 3).mean() * 100)

        modelli_per_fase[target] = {
            "mae": round(mae, 2),
            "r2": round(r2, 4),
            "n_train": int(len(X_train)),
            "n_test": int(len(y_test_arr_t)),
            "rmse": round(rmse_t, 2),
            "accuracy_band_1h": round(acc1, 1),
            "accuracy_band_3h": round(acc3, 1),
            "feature_importance": _feature_importance_list(model_t),
        }

        joblib.dump(model_t, os.path.join(ML_MODELS_DIR, f"model_{target}.pkl"))
        if target == "OreImb":
            model_oreimb = model_t
            y_test_oreimb = np.asarray(y_test).ravel()
            y_pred_oreimb = y_pred

        _save_phase_charts_png(
            target, model_t, y_test_arr_t, y_pred_t, r2, mae
        )

        print(f"  {target}...  R²={r2:.3f}  MAE={mae:.1f}h")

    if len(modelli_per_fase) != len(TARGETS):
        raise RuntimeError(
            "Training incompleto: verificare dati e colonne per tutte le fasi."
        )

    # Metriche aggregate e grafici basati su OreImb
    mae = modelli_per_fase["OreImb"]["mae"]
    r2 = modelli_per_fase["OreImb"]["r2"]
    y_test_arr = y_test_oreimb
    y_pred = y_pred_oreimb
    rmse = float(np.sqrt(mean_squared_error(y_test_arr, y_pred)))
    errors = y_pred - y_test_arr
    acc_1h = float((np.abs(errors) < 1).mean() * 100)
    acc_3h = float((np.abs(errors) < 3).mean() * 100)

    fi = _feature_importance_list(model_oreimb)

    trained_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    if not trained_at.endswith("Z"):
        trained_at += "Z"

    metrics = {
        "r2": round(r2, 4),
        "mae": round(mae, 2),
        "rmse": round(rmse, 2),
        "n_train": modelli_per_fase["OreImb"]["n_train"],
        "n_test": int(len(y_test_arr)),
        "trained_at": trained_at,
        "feature_importance": fi,
        "accuracy_band_1h": round(acc_1h, 1),
        "accuracy_band_3h": round(acc_3h, 1),
        "estimated_time_saved_min": 15,
        "potential_annual_hours_saved": round(974 * 15 / 60, 1),
        "modelli_per_fase": modelli_per_fase,
        "k_percentiles": k_percentiles,
        "mean_k_normalizzato": mean_k,
        "std_k_normalizzato": std_k,
    }

    joblib.dump(model_oreimb, MODEL_PATH)
    with open(METRICS_PATH, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)

    _invalidate_metrics_cache()

    # Copia OreImb in radice ml_charts/ per compatibilità con link senza ?phase=
    oreimb_charts = os.path.join(CHARTS_DIR, "OreImb")
    for name in (
        "feature_importance.png",
        "predicted_vs_actual.png",
        "residuals.png",
    ):
        src = os.path.join(oreimb_charts, name)
        dst = os.path.join(CHARTS_DIR, name)
        if os.path.isfile(src):
            shutil.copy2(src, dst)

    print(f"OK: {len(TARGETS)} modelli salvati in ml_models/")
    print(f"   AF normalizzato medio: {mean_k} ore/ton")
    print(
        f"   Percentili AF: p10={k_percentiles['p10']} p25={k_percentiles['p25']} "
        f"p50={k_percentiles['p50']} p75={k_percentiles['p75']} p90={k_percentiles['p90']}"
    )
    print(f"OK: ml_model.pkl (OreImb). R²={r2:.3f}  MAE={mae:.2f}h  RMSE={rmse:.2f}h")
    print(f"   Acc ±1h: {acc_1h:.1f}%  |  Acc ±3h: {acc_3h:.1f}%")
    return metrics


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Training Random Forest per fase (ore) da xlsx storico o da join commesse+DB.",
    )
    parser.add_argument(
        "--data",
        default=None,
        help="Percorso file .xlsx formato storico (con colonne Peso, dimensioni, ore fasi)",
    )
    parser.add_argument(
        "--from-commesse",
        action="store_true",
        help="Costruisce il dataset da: Excel ore commesse (Elaborato) + SQLite preventivi + mapping offerta↔commessa",
    )
    parser.add_argument(
        "--merge-commesse-ore",
        action="store_true",
        help="Con --data: mantiene dimensioni dal file storico ma sostituisce le ore target dove la Commessa coincide con il foglio Elaborato (commesse 25)",
    )
    parser.add_argument(
        "--commessa-crosswalk",
        default=None,
        help="CSV opzionale con colonne commessa_storica,commessa_2025 per allineare codici N/24 al formato 25/NNN",
    )
    parser.add_argument(
        "--db",
        default=os.path.join(BASE_DIR, "preventivi.db"),
        help="Percorso preventivi.db",
    )
    parser.add_argument(
        "--commesse-xlsx",
        default=None,
        help="Excel ore per reparto (default: ORE PER REPARTO... commesse 25.xlsm in root progetto)",
    )
    parser.add_argument(
        "--min-rows",
        type=int,
        default=40,
        help="Numero minimo di righe per procedere con --from-commesse",
    )
    parser.add_argument(
        "--regenerate-charts-only",
        action="store_true",
        help="Rigenera PNG per fase e feature_importance in JSON dai .pkl (richiede --data xlsx storico)",
    )
    args = parser.parse_args()

    if args.regenerate_charts_only:
        if not args.data:
            parser.error("--regenerate-charts-only richiede --data <xlsx storico>")
        regenerate_charts_only(os.path.abspath(args.data))
        raise SystemExit(0)

    if args.from_commesse and args.merge_commesse_ore:
        parser.error("Usare solo uno tra --from-commesse e --merge-commesse-ore")

    if args.from_commesse:
        from commesse_ore import default_xlsx_path
        from ml_training_data import build_training_frame_from_commesse_join

        cx = os.path.abspath(args.commesse_xlsx or default_xlsx_path())
        dbp = os.path.abspath(args.db)
        dfc = build_training_frame_from_commesse_join(dbp, cx)
        print(f"Dataset join (commesse + preventivi con dimensioni): {len(dfc)} righe")
        if len(dfc) < args.min_rows:
            print(
                "ERRORE: campioni insufficienti. Verificare:\n"
                "  - import Excel ore commesse e mapping offerta↔commessa nel DB;\n"
                "  - preventivi con estrazione OpenAI (peso/dimensioni), non solo import bulk senza AI."
            )
            raise SystemExit(1)
        train(df=dfc)
    elif args.merge_commesse_ore:
        if not args.data:
            parser.error("--merge-commesse-ore richiede --data <xlsx storico>")
        from commesse_ore import default_xlsx_path
        from ml_training_data import (
            load_commessa_crosswalk,
            merge_commesse_targets_into_legacy,
        )

        repo_root = os.path.dirname(BASE_DIR)
        default_cw = os.path.join(repo_root, "dati", "commessa_crosswalk.csv")
        cw_path = args.commessa_crosswalk
        if cw_path:
            cw_path = os.path.abspath(cw_path)
        elif os.path.isfile(default_cw):
            cw_path = default_cw

        crosswalk = load_commessa_crosswalk(cw_path) if cw_path and os.path.isfile(cw_path) else {}
        if crosswalk:
            print(f"Crosswalk commesse: {len(crosswalk)} righe da {cw_path}")

        df0 = _load_training_frame(os.path.abspath(args.data))
        cx = os.path.abspath(args.commesse_xlsx or default_xlsx_path())
        df_m, n_m, st = merge_commesse_targets_into_legacy(
            df0, cx, crosswalk=crosswalk or None
        )
        print(
            f"Ore aggiornate dal file commesse (Elaborato): {n_m} righe "
            f"su {len(df0)} nel dataset storico"
        )
        print(
            f"  Match diretto (stesso codice normalizzato): {st['direct_normalize']} | "
            f"via crosswalk CSV: {st['via_crosswalk']}"
        )
        if st["direct_normalize"] + st["via_crosswalk"] < 50:
            print(
                "  Nota: il file storico usa spesso codici tipo N/24; l'Elaborato 2025 usa 25/NNN. "
                "Sono rari i codici identici. Per aggiornare più righe crea dati/commessa_crosswalk.csv "
                "(commessa_storica,commessa_2025) oppure usa --from-commesse con preventivi estratti."
            )
        train(df=df_m)
    else:
        if not args.data:
            parser.error("Specificare --data <xlsx> oppure --from-commesse")
        train(xlsx_path=os.path.abspath(args.data))
