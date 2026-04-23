import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import './CommesseOreView.css';

function CommesseOreView() {
  const [stats, setStats] = useState(null);
  const [commesse, setCommesse] = useState([]);
  const [matchData, setMatchData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [importMsg, setImportMsg] = useState(null);
  const [mappingRows, setMappingRows] = useState(null);
  const [error, setError] = useState(null);

  const refresh = useCallback(async () => {
    setError(null);
    try {
      const [s, c, m, mapst] = await Promise.all([
        axios.get('/api/commesse-ore/stats'),
        axios.get('/api/commesse-ore'),
        axios.get('/api/commesse-ore/match-preventivi'),
        axios.get('/api/offerta-commessa-mapping/stats'),
      ]);
      setStats(s.data);
      setCommesse(c.data.commesse || []);
      setMatchData(m.data);
      setMappingRows(mapst.data?.rows ?? 0);
    } catch (e) {
      setError(e.response?.data?.error || e.message || 'Errore caricamento');
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const handleImport = async () => {
    setLoading(true);
    setImportMsg(null);
    setError(null);
    try {
      const r = await axios.post('/api/commesse-ore/import', {});
      setImportMsg(
        `Importate ${r.data.imported} righe da ${r.data.source_file || 'file predefinito'}.`
      );
      await refresh();
    } catch (e) {
      setError(e.response?.data?.error || e.message || 'Import fallito');
    } finally {
      setLoading(false);
    }
  };

  const handleImportMapping = async () => {
    setLoading(true);
    setImportMsg(null);
    setError(null);
    try {
      const r = await axios.post('/api/offerta-commessa-mapping/import', {});
      setImportMsg(
        `Elenco offerta↔commessa: ${r.data.imported} righe (${r.data.source_file || ''}).`
      );
      await refresh();
    } catch (e) {
      setError(e.response?.data?.error || e.message || 'Import mapping fallito');
    } finally {
      setLoading(false);
    }
  };

  const sum = matchData?.summary;

  return (
    <div className="commesse-ore-view">
      <div className="card">
        <h2>Ore reali per commessa</h2>
        <p className="subtitle">
          <strong>Ore reparto:</strong> Excel &quot;Elaborato&quot; (IMBA, NEST, PIEG, PROD, PROG, SALD).{' '}
          <strong>Legame offerta→commessa:</strong> importa l&apos;elenco gestionale (nr. preventivo in
          colonna accanto a &quot;Riferimento Offerta&quot;). Il match usa prima il{' '}
          <strong>numero preventivo</strong> dal nome file, poi il cliente se manca il mapping.
        </p>
        <div className="commesse-actions">
          <button type="button" className="btn-primary" onClick={handleImport} disabled={loading}>
            {loading ? 'Importazione…' : 'Importa ore commesse (Excel)'}
          </button>
          <button type="button" className="btn-primary" onClick={handleImportMapping} disabled={loading}>
            {loading ? 'Importazione…' : 'Importa elenco offerta↔commessa'}
          </button>
          <button type="button" className="btn-secondary" onClick={refresh} disabled={loading}>
            Aggiorna
          </button>
        </div>
        {mappingRows != null && (
          <p className="muted">
            Righe mapping caricate: <strong>{mappingRows}</strong> (file xlsm predefinito in{' '}
            <code>_offerte_extracted/OFFERTE/</code> o <code>dati/</code>)
          </p>
        )}
        {importMsg && <p className="success-msg">{importMsg}</p>}
        {error && <p className="error">{error}</p>}
      </div>

      {stats && (
        <div className="card stats-row">
          <div className="stat-box">
            <span className="stat-val">{stats.commesse_count}</span>
            <span className="stat-lbl">Commesse in archivio</span>
          </div>
          <div className="stat-box">
            <span className="stat-val">{stats.clienti_distinti_norm}</span>
            <span className="stat-lbl">Clienti (nome normalizzato)</span>
          </div>
          <div className="stat-box warn">
            <span className="stat-val">{stats.clienti_con_piu_commesse}</span>
            <span className="stat-lbl">Clienti con più commesse</span>
          </div>
        </div>
      )}

      {sum && (
        <div className="card">
          <h3>Verifica offerte ↔ commesse</h3>
          <p className="subtitle">
            Preventivi: {sum.preventivi} — <strong>mapped</strong> {sum.mapped ?? 0},{' '}
            <strong>mapped_no_ore</strong> {sum.mapped_no_ore ?? 0},{' '}
            <strong>ambiguous_mapping</strong> {sum.ambiguous_mapping ?? 0} — fallback cliente: unique{' '}
            {sum.unique}, ambiguous {sum.ambiguous}, none {sum.none}, unparsed {sum.unparsed}
          </p>
          {matchData?.matches?.length > 0 && (
            <div className="table-wrap">
              <table className="match-table">
                <thead>
                  <tr>
                    <th>File</th>
                    <th>Esito</th>
                    <th>Commessa / nota</th>
                  </tr>
                </thead>
                <tbody>
                  {matchData.matches.map((row, i) => (
                    <tr key={i} className={`match-${row.match}`}>
                      <td className="fn">{row.filename}</td>
                      <td>{row.match}</td>
                      <td>
                        {(row.match === 'mapped' || row.match === 'mapped_no_ore') && row.nr_commessa && (
                          <>
                            <strong>{row.nr_commessa}</strong>
                            {row.ragione_sociale_mapping && (
                              <span className="muted"> — {row.ragione_sociale_mapping}</span>
                            )}
                            {row.commesse?.[0]?.ore_totale != null && (
                              <span> ({row.commesse[0].ore_totale} h)</span>
                            )}
                            {row.match === 'mapped_no_ore' && <span className="muted"> (ore non in Excel)</span>}
                          </>
                        )}
                        {row.commesse?.length === 1 &&
                          row.match !== 'mapped' &&
                          row.match !== 'mapped_no_ore' && (
                          <>
                            <strong>{row.commesse[0].nr_commessa}</strong> — {row.commesse[0].cliente}{' '}
                            ({row.commesse[0].ore_totale != null ? `${row.commesse[0].ore_totale} h` : '—'})
                          </>
                        )}
                        {row.commesse?.length > 1 && (
                          <>
                            {row.commesse.length} commesse (es. {row.commesse[0].nr_commessa} …{' '}
                            {row.commesse[row.commesse.length - 1].nr_commessa})
                          </>
                        )}
                        {!row.commesse?.length && (row.detail || '—')}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      <div className="card">
        <h3>Prime commesse (dati importati)</h3>
        {commesse.length === 0 ? (
          <p className="muted">Nessun dato: eseguire l&apos;import.</p>
        ) : (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Commessa</th>
                  <th>Cliente</th>
                  <th>IMBA</th>
                  <th>NEST</th>
                  <th>PIEG</th>
                  <th>PROD</th>
                  <th>PROG</th>
                  <th>SALD</th>
                  <th>Tot.</th>
                </tr>
              </thead>
              <tbody>
                {commesse.slice(0, 80).map((r) => (
                  <tr key={r.nr_commessa}>
                    <td>{r.nr_commessa}</td>
                    <td>{r.cliente}</td>
                    <td>{r.ore_imba != null ? r.ore_imba.toFixed(2) : '—'}</td>
                    <td>{r.ore_nest != null ? r.ore_nest.toFixed(2) : '—'}</td>
                    <td>{r.ore_pieg != null ? r.ore_pieg.toFixed(2) : '—'}</td>
                    <td>{r.ore_prod != null ? r.ore_prod.toFixed(2) : '—'}</td>
                    <td>{r.ore_prog != null ? r.ore_prog.toFixed(2) : '—'}</td>
                    <td>{r.ore_sald != null ? r.ore_sald.toFixed(2) : '—'}</td>
                    <td>
                      <strong>{r.ore_totale != null ? r.ore_totale.toFixed(2) : '—'}</strong>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {commesse.length > 80 && (
              <p className="muted">Mostrate 80 su {commesse.length} righe.</p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default CommesseOreView;
