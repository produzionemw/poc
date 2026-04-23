import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts';
import './ModelView.css';

const PHASES = [
  { key: 'OreProg', label: 'Progettazione' },
  { key: 'OreNest', label: 'Nesting' },
  { key: 'OreTaglio', label: 'Taglio' },
  { key: 'OrePieg', label: 'Piegatura' },
  { key: 'OreSald', label: 'Saldatura' },
  { key: 'OreImb', label: 'Imballaggio' },
];

function ChartImage({ src, alt }) {
  const [loaded, setLoaded] = useState(false);
  const [errored, setErrored] = useState(false);

  useEffect(() => {
    setLoaded(false);
    setErrored(false);
  }, [src]);

  return (
    <div className="chart-img-wrap">
      {!loaded && !errored && <div className="chart-skeleton" aria-hidden />}
      {errored ? (
        <div className="chart-placeholder">Grafico non disponibile. Eseguire ml_model.py</div>
      ) : (
        <img
          src={src}
          alt={alt}
          style={{ display: loaded ? 'block' : 'none' }}
          onLoad={() => setLoaded(true)}
          onError={() => setErrored(true)}
        />
      )}
    </div>
  );
}

function ModelView() {
  const [activePhase, setActivePhase] = useState('OreImb');
  const [stats, setStats] = useState(null);
  const [statsLoading, setStatsLoading] = useState(true);
  const [statsError, setStatsError] = useState(null);

  const [form, setForm] = useState({
    peso: '',
    lato_a: '',
    lato_b: '',
    altezza: '',
    portata: '',
  });
  const [prediction, setPrediction] = useState(null);
  const [similar, setSimilar] = useState([]);
  const [predLoading, setPredLoading] = useState(false);
  const [predError, setPredError] = useState(null);

  const [training, setTraining] = useState(false);
  const [trainMode, setTrainMode] = useState('merge');
  const [trainMsg, setTrainMsg] = useState('');
  const [trainError, setTrainError] = useState(null);

  const loadStats = useCallback(async () => {
    setStatsLoading(true);
    setStatsError(null);
    try {
      const res = await axios.get('/api/ml/stats');
      setStats(res.data);
    } catch (err) {
      setStats(null);
      if (err.response?.status === 503) {
        setStatsError(
          'Modello non ancora addestrato. Usa «Elimina modelli e ritraina» oppure da terminale: python train_models.py',
        );
      } else {
        setStatsError('Errore nel caricamento delle metriche.');
      }
    } finally {
      setStatsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadStats();
  }, [loadStats]);

  const handleTrain = async () => {
    if (
      !window.confirm(
        'Verranno eliminati tutti i modelli (.pkl), le metriche (ml_metrics.json) e i grafici in ml_charts/, poi avviato un nuovo training automatico sui dati del progetto. Può richiedere molti minuti. Continuare?',
      )
    ) {
      return;
    }
    setTrainError(null);
    setTrainMsg('');
    try {
      const res = await axios.post('/api/ml/train', { mode: trainMode });
      if (res.status === 202) {
        setTraining(true);
        setTrainMsg('Training avviato...');
      }
    } catch (err) {
      if (err.response?.status === 409) {
        setTrainError('Un training è già in corso sul server.');
      } else {
        setTrainError(err.response?.data?.error || err.message || 'Errore');
      }
    }
  };

  useEffect(() => {
    if (!training) return undefined;
    const poll = async () => {
      try {
        const r = await axios.get('/api/ml/training-status');
        setTrainMsg(r.data.message || '');
        if (!r.data.running) {
          setTraining(false);
          if (r.data.error) {
            const tail = r.data.log_tail
              ? `\n\n--- log (fine) ---\n${String(r.data.log_tail).slice(-1200)}`
              : '';
            setTrainError((r.data.error || 'Training fallito') + tail);
          } else {
            setTrainError(null);
            await loadStats();
          }
        }
      } catch (e) {
        setTraining(false);
        setTrainError('Impossibile leggere lo stato del training.');
      }
    };
    poll();
    const id = setInterval(poll, 2000);
    return () => clearInterval(id);
  }, [training, loadStats]);

  const handleInput = (e) => {
    setForm({ ...form, [e.target.name]: e.target.value });
  };

  const handlePredict = async (e) => {
    e.preventDefault();
    setPredLoading(true);
    setPredError(null);
    setPrediction(null);
    setSimilar([]);

    try {
      const body = {
        peso: parseFloat(form.peso),
        lato_a: parseFloat(form.lato_a),
        lato_b: parseFloat(form.lato_b),
        altezza: parseFloat(form.altezza),
      };
      if (form.portata) body.portata = parseFloat(form.portata);

      const [predRes, simRes] = await Promise.all([
        axios.post('/api/ml/predict', body),
        axios.get('/api/ml/similar', {
          params: {
            peso: body.peso,
            lato_a: body.lato_a,
            lato_b: body.lato_b,
            altezza: body.altezza,
          },
        }),
      ]);

      setPrediction(predRes.data);
      setSimilar(simRes.data.similar || []);
    } catch (err) {
      setPredError(err.response?.data?.error || 'Errore nella previsione.');
    } finally {
      setPredLoading(false);
    }
  };

  const featureLabels = {
    Peso_kg: 'Peso (kg)',
    LatoCorto_mm: 'Lato A corto',
    LatoLungo_mm: 'Lato B lungo',
    Altezza_mm: 'Altezza H',
    Portata: 'Portata (m³/h)',
    Volume_mm3: 'Volume',
  };

  const phaseFeatureImportance =
    stats?.modelli_per_fase?.[activePhase]?.feature_importance;
  const chartData = (
    phaseFeatureImportance || stats?.feature_importance
  )
    ?.slice(0, 6)
    .map((f) => ({
      ...f,
      label: featureLabels[f.feature] || f.feature,
      pct: parseFloat((f.importance * 100).toFixed(1)),
    })) || [];

  const phaseMeta = PHASES.find((p) => p.key === activePhase) || PHASES[5];
  const phaseData = prediction?.ore_per_fase?.[activePhase];
  const phaseMetrics = stats?.modelli_per_fase?.[activePhase];
  const hasPhaseTestMetrics =
    phaseMetrics &&
    typeof phaseMetrics.rmse === 'number' &&
    typeof phaseMetrics.accuracy_band_1h === 'number';

  const predVal = phaseData?.valore ?? null;
  const predLow = phaseData?.low ?? null;
  const predHigh = phaseData?.high ?? null;
  const scaleMax = Math.max(predHigh || 0, predVal || 0, 1) * 1.15;

  const chartBust = stats?.trained_at
    ? `&cb=${encodeURIComponent(stats.trained_at)}`
    : '';

  return (
    <div className="model-view">
      <div className="card">
        <h2>Modello AI — previsione ore per fase</h2>
        <p className="subtitle">
          Sei modelli Random Forest (uno per reparto). Stessi input; la previsione mostrata cambia in
          base al tab selezionato.
        </p>

        <div className="train-panel">
          <div className="train-panel-row">
            <label htmlFor="train-mode" className="train-label">
              Modalità
            </label>
            <select
              id="train-mode"
              className="train-mode-select"
              value={trainMode}
              onChange={(e) => setTrainMode(e.target.value)}
              disabled={training}
            >
              <option value="merge">Storico Metal+ + ore commesse (merge, consigliato)</option>
              <option value="legacy_only">Solo Excel storico (senza merge commesse)</option>
              <option value="from_db">Solo DB preventivi + Elaborato commesse</option>
            </select>
            <button
              type="button"
              className="train-danger-btn"
              onClick={handleTrain}
              disabled={training}
            >
              {training ? (trainMsg || 'Training in corso…') : 'Elimina modelli e ritraina'}
            </button>
          </div>
          {trainError && (
            <pre className="train-error-log">{trainError}</pre>
          )}
        </div>

        <nav className="model-subtabs" aria-label="Fasi produttive">
          {PHASES.map((p) => (
            <button
              key={p.key}
              type="button"
              className={activePhase === p.key ? 'active' : ''}
              onClick={() => setActivePhase(p.key)}
            >
              {p.label}
            </button>
          ))}
        </nav>

        <p className="model-phase-title">Fase attiva: {phaseMeta.label}</p>

        <h3 style={{ marginTop: 12, fontSize: '1.1rem', color: '#1a4578' }}>
          Previsione ore — {phaseMeta.label}
        </h3>
        <p className="subtitle">Inserisci le dimensioni del filtro per ottenere la previsione.</p>
        <form onSubmit={handlePredict} className="predict-form">
          <div className="form-grid">
            {[
              { name: 'peso', label: 'Peso (kg)', placeholder: 'es. 1200' },
              { name: 'lato_a', label: 'Lato A corto (mm)', placeholder: 'es. 1440' },
              { name: 'lato_b', label: 'Lato B lungo (mm)', placeholder: 'es. 1700' },
              { name: 'altezza', label: 'Altezza H (mm)', placeholder: 'es. 8500' },
              { name: 'portata', label: 'Portata m³/h (opz.)', placeholder: 'es. 300' },
            ].map((f) => (
              <div key={f.name} className="form-field">
                <label htmlFor={`mv-${f.name}`}>{f.label}</label>
                <input
                  id={`mv-${f.name}`}
                  type="number"
                  name={f.name}
                  value={form[f.name]}
                  onChange={handleInput}
                  placeholder={f.placeholder}
                  required={f.name !== 'portata'}
                  step="any"
                />
              </div>
            ))}
          </div>
          <button type="submit" disabled={predLoading} className="predict-btn">
            {predLoading ? 'Calcolo...' : 'Calcola previsione (tutte le fasi)'}
          </button>
        </form>

        {predError && <p className="error">{predError}</p>}

        {prediction && (
          <div className="prediction-result">
            {predVal != null ? (
              <>
                <div className="prediction-main">
                  <span className="prediction-label">Ore previste ({phaseMeta.label})</span>
                  <span className="prediction-value">{Number(predVal).toFixed(1)}h</span>
                </div>
                <div className="confidence-bar">
                  <span className="conf-label">
                    Intervallo 80%: {Number(predLow).toFixed(1)}h — {Number(predHigh).toFixed(1)}h
                  </span>
                  <div className="conf-track">
                    <div
                      className="conf-fill"
                      style={{
                        width: `${Math.min(100, ((predHigh || 0) / scaleMax) * 100)}%`,
                      }}
                    />
                    <div
                      className="conf-point"
                      style={{
                        left: `${Math.min(100, ((predVal || 0) / scaleMax) * 100)}%`,
                      }}
                    />
                  </div>
                  <span className="conf-note">
                    Basato su 200 alberi decisionali | Volume: {prediction.volume_m3} m³ | Ore totali
                    (somma fasi): {prediction.ore_totali != null ? `${prediction.ore_totali}h` : '—'}
                  </span>
                </div>
              </>
            ) : (
              <p className="subtitle" style={{ margin: 0 }}>
                Nessun output per questa fase: addestra tutti i modelli con{' '}
                <code>python ml_model.py</code> oppure il modello per questa fase non è disponibile.
              </p>
            )}
          </div>
        )}
      </div>

      {similar.length > 0 && (
        <div className="card">
          <h2>Commesse simili nel dataset storico</h2>
          <p className="subtitle">
            Le 3 commesse con dimensioni più vicine. Le ore imballaggio indicate sono reali (solo
            fase Imballaggio).
          </p>
          <div className="similar-grid">
            {similar.map((s, i) => (
              <div key={`${s.commessa_id}-${i}`} className="similar-card">
                <div className="similar-rank">#{i + 1}</div>
                <div className="similar-commessa">{s.commessa_id}</div>
                <div className="similar-ore">
                  <span className="ore-label">Ore imb. reali</span>
                  <span className="ore-value">{s.ore_imb_reale}h</span>
                </div>
                <div className="similar-dims">
                  {s.peso_kg} kg | {s.lato_a}×{s.lato_b}×{s.altezza} mm
                </div>
                <div
                  className="similarity-badge"
                  style={{
                    background: s.similarity_pct >= 70 ? '#e8f5e9' : '#fff3e0',
                    color: s.similarity_pct >= 70 ? '#2e7d32' : '#e65100',
                  }}
                >
                  {Number(s.similarity_pct).toFixed(0)}% simile
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {statsLoading && (
        <div className="card">
          <div className="loading">Caricamento metriche...</div>
        </div>
      )}
      {statsError && (
        <div className="card">
          <p className="error">{statsError}</p>
        </div>
      )}

      {stats && (
        <div className="card">
          <h2>Performance — {phaseMeta.label}</h2>
          <p className="subtitle">
            {hasPhaseTestMetrics
              ? 'Metriche calcolate sul test set (20%) per il modello della fase selezionata.'
              : 'Rieseguire il training con ml_model aggiornato per RMSE e precisioni per fase; sotto alcuni valori sono ancora quelli globali (OreImb).'}
          </p>
          <div className="metrics-grid">
            {phaseMetrics ? (
              <>
                <div className="metric-card">
                  <span className="metric-label">R² (fase)</span>
                  <span className="metric-value">{phaseMetrics.r2.toFixed(3)}</span>
                </div>
                <div className="metric-card">
                  <span className="metric-label">MAE (fase)</span>
                  <span className="metric-value">{phaseMetrics.mae.toFixed(2)}h</span>
                </div>
                <div className="metric-card">
                  <span className="metric-label">Training (fase)</span>
                  <span className="metric-value">
                    {phaseMetrics.n_train.toLocaleString('it-IT')}
                  </span>
                </div>
                <div className="metric-card">
                  <span className="metric-label">Test (fase)</span>
                  <span className="metric-value">
                    {phaseMetrics.n_test != null
                      ? Number(phaseMetrics.n_test).toLocaleString('it-IT')
                      : '—'}
                  </span>
                </div>
              </>
            ) : (
              <>
                <div className="metric-card">
                  <span className="metric-label">Accuratezza (R²) globale</span>
                  <span className="metric-value">{(stats.r2 * 100).toFixed(1)}%</span>
                </div>
                <div className="metric-card">
                  <span className="metric-label">Errore medio (MAE) globale</span>
                  <span className="metric-value">{stats.mae.toFixed(1)}h</span>
                </div>
              </>
            )}
            <div className="metric-card">
              <span className="metric-label">
                RMSE test {hasPhaseTestMetrics ? '(fase)' : '(globale OreImb)'}
              </span>
              <span className="metric-value">
                {(hasPhaseTestMetrics ? phaseMetrics.rmse : stats.rmse).toFixed(1)}h
              </span>
            </div>
            <div className="metric-card">
              <span className="metric-label">
                Precisione ±1h {hasPhaseTestMetrics ? '(fase)' : '(globale OreImb)'}
              </span>
              <span className="metric-value">
                {hasPhaseTestMetrics ? phaseMetrics.accuracy_band_1h : stats.accuracy_band_1h}%
              </span>
            </div>
            <div className="metric-card">
              <span className="metric-label">
                Precisione ±3h {hasPhaseTestMetrics ? '(fase)' : '(globale OreImb)'}
              </span>
              <span className="metric-value">
                {hasPhaseTestMetrics ? phaseMetrics.accuracy_band_3h : stats.accuracy_band_3h}%
              </span>
            </div>
            <div className="metric-card">
              <span className="metric-label">Ore annue risparmiate (stima POC)</span>
              <span className="metric-value">~{stats.potential_annual_hours_saved}h</span>
            </div>
            <div className="metric-card">
              <span className="metric-label">Ultimo training</span>
              <span className="metric-value">
                {stats.trained_at
                  ? new Date(stats.trained_at).toLocaleDateString('it-IT')
                  : 'N/A'}
              </span>
            </div>
          </div>
        </div>
      )}

      {chartData.length > 0 && (
        <div className="card">
          <h2>Importanza delle variabili — {phaseMeta.label}</h2>
          <p className="subtitle">
            Stesse feature per tutti i modelli; importanza stimata sul training per il modello della
            fase selezionata.
          </p>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart
              data={chartData}
              layout="vertical"
              margin={{ left: 20, right: 30, top: 10, bottom: 10 }}
            >
              <XAxis type="number" tickFormatter={(v) => `${v}%`} domain={[0, 'dataMax']} />
              <YAxis type="category" dataKey="label" width={120} tick={{ fontSize: 10 }} />
              <Tooltip formatter={(v) => [`${Number(v).toFixed(1)}%`, 'Importanza']} />
              <Bar dataKey="pct" radius={[0, 4, 4, 0]}>
                {chartData.map((_, i) => (
                  <Cell key={i} fill={i === 0 ? '#1a4578' : '#2e75b5'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {stats && (
        <div className="card">
          <h2>Grafici di valutazione — {phaseMeta.label}</h2>
          <p className="subtitle">
            PNG dal training per la fase selezionata (test set 20%).
          </p>
          <div className="charts-gallery">
            {[
              { key: 'feature_importance', title: 'Importanza delle variabili (PNG)' },
              { key: 'predicted_vs_actual', title: 'Previsto vs Reale (test set)' },
              { key: 'residuals', title: 'Distribuzione degli errori' },
            ].map((c) => (
              <div key={c.key} className="chart-item">
                <h4>{c.title}</h4>
                <ChartImage
                  src={`/api/ml/charts/${c.key}?phase=${encodeURIComponent(activePhase)}${chartBust}`}
                  alt={`${c.title} (${phaseMeta.label})`}
                />
              </div>
            ))}
          </div>
        </div>
      )}

      {stats && (
        <div className="card methodology-note">
          <p>
            <strong>Dataset:</strong> {stats.n_train + stats.n_test} commesse Metal+ (2024–2025) |{' '}
            <strong>Modelli:</strong> 6 Random Forest (200 alberi ciascuno) |{' '}
            <strong>Feature:</strong> peso, lato A, lato B, altezza, portata, volume |{' '}
            <strong>Split:</strong> 80% training / 20% test | stratificato per fascia ore
          </p>
        </div>
      )}
    </div>
  );
}

export default ModelView;
