import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { BarChart, Bar, XAxis, YAxis, Tooltip,
         ResponsiveContainer, Cell } from 'recharts';
import './FattoreKView.css';

const FASE_LABELS = {
  OreProg:   'Progettazione', OreNest:   'Nesting',
  OreTaglio: 'Taglio',        OrePieg:   'Piegatura',
  OreSald:   'Saldatura',     OreImb:    'Imballaggio',
};
const FASE_COLORS = {
  OreProg:   '#1a4578', OreNest:   '#2e75b5',
  OreTaglio: '#5a9fd4', OrePieg:   '#85b7eb',
  OreSald:   '#b5d4f4', OreImb:    '#d0e4f5',
};

const getKBadgeStyle = (p) => {
  if (!p) return { bg: '#f5f5f5', color: '#888' };
  if (p >= 90) return { bg: '#fde8e8', color: '#a32d2d' };
  if (p >= 75) return { bg: '#fff3e0', color: '#e65100' };
  if (p >= 50) return { bg: '#fff8e1', color: '#f57f17' };
  return        { bg: '#e8f5e9', color: '#2e7d32' };
};
const getKLabel = (p) => {
  if (!p) return 'N/D';
  if (p >= 90) return 'Alta';
  if (p >= 75) return 'Medio-alta';
  if (p >= 50) return 'Media';
  return 'Bassa';
};

/** API confronto-af può passare cliente/modello come stringa o oggetto (estrazione PDF). */
function displayCell(v) {
  if (v == null || v === '') return '—';
  if (typeof v === 'object') {
    if (typeof v.nome === 'string') return v.nome;
    if (typeof v.descrizione === 'string') return v.descrizione;
    try {
      return JSON.stringify(v);
    } catch {
      return '—';
    }
  }
  return String(v);
}

function buildChartRows(row) {
  if (!row?.ore_per_fase) return [];
  return Object.entries(row.ore_per_fase).map(([f, v]) => ({
    fase: FASE_LABELS[f] || f,
    key: f,
    ore: v.valore,
    low: v.low,
    high: v.high,
    color: FASE_COLORS[f] || '#2e75b5',
  }));
}

/** Dettaglio AF: grafico, barra percentile, differenziale (stesso contenuto di prima, inline sotto la riga). */
function AfDetailPanel({ row, calcolati }) {
  const chartRows = buildChartRows(row);

  return (
    <div className="k-detail-panel-inner">
      <h3 className="k-detail-title">Dettaglio: {row.filename.replace('.pdf', '')}</h3>

      <div className="detail-grid">
        <div className="k-kpi-col">
          <div className="k-big">{row.k_normalizzato?.toFixed(1)}<span className="k-unit"> ore/ton</span></div>
          <div className="k-sublabel">AF normalizzato</div>
          <div className="k-ctx">
            Percentile {row.k_percentile}° nel dataset —{' '}
            complessità <strong>{getKLabel(row.k_percentile)}</strong>
          </div>
          <div className="k-totale">Ore totali stimate: <strong>{row.ore_totali?.toFixed(1)}h</strong></div>
          <div className="k-dims">
            {row.input?.peso?.toLocaleString('it')} kg |{' '}
            {row.input?.lato_a} × {row.input?.lato_b} mm |{' '}
            H {row.input?.altezza} mm
          </div>
        </div>

        <div>
          <div className="chart-title">Ore stimate per fase</div>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart
              data={chartRows}
              margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
              <XAxis dataKey="fase" tick={{ fontSize: 9 }} />
              <YAxis tickFormatter={(v) => `${v}h`} tick={{ fontSize: 9 }} />
              <Tooltip formatter={(v, _, p) => {
                const low = p?.payload?.low ?? 0;
                const high = p?.payload?.high ?? 0;
                return [`${Number(v).toFixed(1)}h (${Number(low).toFixed(1)}–${Number(high).toFixed(1)}h)`, 'Ore'];
              }} />
              <Bar dataKey="ore" radius={[4, 4, 0, 0]}>
                {chartRows.map((cr) => (
                  <Cell key={cr.key} fill={cr.color} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="k-bar-section">
        <span className="k-bar-title">Posizione nel dataset storico</span>
        <div className="k-bar-track">
          <div className="k-bar-fill"
               style={{ width: `${Math.min(100, row.k_percentile)}%` }} />
          <div className="k-bar-pin"
               style={{ left: `${Math.min(100, row.k_percentile)}%` }}>
            <span className="k-pin-label">{row.k_percentile}°</span>
          </div>
        </div>
        <div className="k-bar-ends">
          <span>Bassa complessità</span><span>Alta complessità</span>
        </div>
      </div>

      {calcolati.length > 1 && (() => {
        const idx = calcolati.findIndex((r) => r.id === row.id);
        const prev = idx > 0 ? calcolati[idx - 1] : null;
        const next = idx < calcolati.length - 1 ? calcolati[idx + 1] : null;
        return (
          <div className="diff-section">
            <div className="chart-title">Differenziale vs preventivi vicini</div>
            <div className="diff-row">
              {prev && (
                <div className="diff-box diff-high">
                  <span className="diff-lbl">Più complesso (#{prev.rank_complessita})</span>
                  <span className="diff-fn">{prev.filename.replace('.pdf', '')}</span>
                  <span className="diff-val">
                    +{(prev.k_normalizzato - row.k_normalizzato).toFixed(1)} ore/ton
                    · +{(prev.ore_totali - row.ore_totali).toFixed(1)}h tot.
                  </span>
                </div>
              )}
              <div className="diff-box diff-cur">
                <span className="diff-lbl">Questo preventivo (#{row.rank_complessita})</span>
                <span className="diff-fn">{row.filename.replace('.pdf', '')}</span>
                <span className="diff-val">{row.k_normalizzato?.toFixed(1)} ore/ton</span>
              </div>
              {next && (
                <div className="diff-box diff-low">
                  <span className="diff-lbl">Meno complesso (#{next.rank_complessita})</span>
                  <span className="diff-fn">{next.filename.replace('.pdf', '')}</span>
                  <span className="diff-val">
                    -{(row.k_normalizzato - next.k_normalizzato).toFixed(1)} ore/ton
                    · -{(row.ore_totali - next.ore_totali).toFixed(1)}h tot.
                  </span>
                </div>
              )}
            </div>
          </div>
        );
      })()}
    </div>
  );
}

function FattoreKView() {
  const [confronto, setConfronto] = useState(null);
  const [loading, setLoading]     = useState(true);
  const [error, setError]         = useState(null);
  const [selected, setSelected]   = useState(null);
  const [refreshing, setRefreshing] = useState(false);

  const loadConfronto = useCallback(async (forceRefresh) => {
    setLoading(!forceRefresh);
    if (forceRefresh) setRefreshing(true);
    setError(null);
    try {
      const r = await axios.get('/api/preventivi/confronto-af', {
        params: forceRefresh ? { refresh: 1 } : {},
      });
      setConfronto(r.data);
    } catch (err) {
      if (err.response?.status === 503)
        setError('Modello non addestrato. Eseguire: python ml_model.py --data <xlsx>');
      else
        setError('Errore nel calcolo fattore AF.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    loadConfronto(false);
  }, [loadConfronto]);

  if (loading) return <div className="card"><div className="loading">Calcolo fattore AF...</div></div>;
  if (error)   return <div className="card"><p className="error">{error}</p></div>;
  if (!confronto) return null;

  const calcolati    = confronto.confronto.filter(r => r.calcolo_ok);
  const nonCalcolati = confronto.confronto.filter(r => !r.calcolo_ok);

  return (
    <div className="fattore-af-view">

      <div className="card">
        <div className="fattore-af-header-row">
          <h2>Ranking complessità — Fattore AF stimato</h2>
          <button
            type="button"
            className="fattore-af-refresh-btn"
            onClick={() => loadConfronto(true)}
            disabled={refreshing}
            title="Forza ricalcolo ML e aggiorna la cache (dopo nuovo training o nuovi estratti)"
          >
            {refreshing ? 'Ricalcolo…' : 'Ricalcola tutti'}
          </button>
        </div>
        <p className="subtitle">
          {confronto.n_calcolati}/{confronto.n_totale} preventivi con estrazione e calcolo AF
          {typeof confronto.n_senza_estrazione === 'number' && confronto.n_senza_estrazione > 0 && (
            <> · {confronto.n_senza_estrazione} senza estrazione (esclusi)</>
          )}
          . Clicca una riga per aprire il dettaglio sotto.
          {confronto.cache !== false && (
            <span className="cache-badge"> · da cache DB (caricamento veloce)</span>
          )}
        </p>
        <p className="nota-met">
          Nota: modello addestrato su commesse Filtrazione.
          Per strutture Elevators i valori sono indicativi —
          il ranking relativo tra preventivi è quello più affidabile.
        </p>
      </div>

      <div className="card k-table-card">
        <table className="k-table">
          <thead>
            <tr>
              <th>#</th><th>Preventivo</th><th>Cliente</th><th>Modello</th>
              <th>Peso (kg)</th><th>Ore totali</th>
              <th>AF (ore/ton)</th><th>Complessità</th>
            </tr>
          </thead>
          <tbody>
            {calcolati.map(r => {
              const badge = getKBadgeStyle(r.k_percentile);
              const isOpen = selected?.id === r.id;
              return (
                <React.Fragment key={r.id}>
                  <tr
                    className={isOpen ? 'selected-row' : ''}
                    onClick={() => setSelected(isOpen ? null : r)}
                    aria-expanded={isOpen}
                  >
                    <td className="rank-cell">
                      {r.rank_complessita === 1 && <span className="top-icon">▲ </span>}
                      {r.rank_complessita}
                    </td>
                    <td className="fn-cell">{r.filename.replace('.pdf','')}</td>
                    <td>{displayCell(r.cliente)}</td>
                    <td><span className="mod-badge">{displayCell(r.modello)}</span></td>
                    <td>
                      {r.input?.peso != null && typeof r.input.peso === 'number'
                        ? r.input.peso.toLocaleString('it')
                        : displayCell(r.input?.peso)}
                    </td>
                    <td className="ore-cell">{r.ore_totali?.toFixed(1)}h</td>
                    <td className="k-cell">{r.k_normalizzato?.toFixed(1)}</td>
                    <td>
                      <span className="cx-badge"
                            style={{ background: badge.bg, color: badge.color }}>
                        {getKLabel(r.k_percentile)}
                      </span>
                    </td>
                  </tr>
                  {isOpen && (
                    <tr className="k-detail-expand-row">
                      <td colSpan={8}>
                        <AfDetailPanel row={r} calcolati={calcolati} />
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              );
            })}
            {nonCalcolati.map(r => (
              <tr key={r.id} className="row-na">
                <td>—</td>
                <td className="fn-cell">{r.filename.replace('.pdf','')}</td>
                <td>{displayCell(r.cliente)}</td>
                <td>{displayCell(r.modello)}</td>
                <td colSpan={4} className="motivo-cell">{typeof r.motivo === 'object' ? JSON.stringify(r.motivo) : (r.motivo || '—')}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default FattoreKView;
