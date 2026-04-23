import React, { useState, useEffect, useMemo } from 'react';
import './PlanningView.css';

function PlanningView() {
  const [planning, setPlanning] = useState([]);
  const [config, setConfig] = useState({
    num_operatori: 5,
    tempo_commessa_giorni: 30,
    tempo_recupero_materie_giorni: 7
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    loadPlanningConfig();
  }, []);

  useEffect(() => {
    if (config.num_operatori) {
      loadPlanning();
    }
  }, [config]);

  const loadPlanningConfig = async () => {
    try {
      const response = await fetch('/api/planning/config');
      const data = await response.json();
      setConfig({
        num_operatori: data.num_operatori || 5,
        tempo_commessa_giorni: data.tempo_commessa_giorni || 30,
        tempo_recupero_materie_giorni: data.tempo_recupero_materie_giorni || data.tempo_magazzino_giorni || 7
      });
    } catch (error) {
      console.error('Errore nel caricamento configurazione:', error);
    }
  };

  const loadPlanning = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(
        `/api/planning?num_operatori=${config.num_operatori}&tempo_commessa=${config.tempo_commessa_giorni}&tempo_recupero=${config.tempo_recupero_materie_giorni}`
      );
      const data = await response.json();
      if (data.planning) {
        setPlanning(data.planning);
      }
    } catch (error) {
      setError('Errore nel caricamento della pianificazione');
      console.error('Errore:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleConfigChange = (field, value) => {
    setConfig({
      ...config,
      [field]: parseInt(value) || 0
    });
  };

  const handleSaveConfig = async () => {
    try {
      const response = await fetch('/api/planning/config', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          num_operatori: config.num_operatori,
          tempo_commessa_giorni: config.tempo_commessa_giorni,
          tempo_recupero_materie_giorni: config.tempo_recupero_materie_giorni
        }),
      });
      const data = await response.json();
      if (data.success) {
        loadPlanning();
      }
    } catch (error) {
      console.error('Errore nel salvataggio configurazione:', error);
    }
  };

  const formatDate = (dateString) => {
    try {
      const date = new Date(dateString);
      return date.toLocaleDateString('it-IT', {
        year: 'numeric',
        month: 'short',
        day: 'numeric'
      });
    } catch {
      return dateString;
    }
  };

  // Raggruppa i preventivi per operatore
  const planningByOperatore = useMemo(() => {
    const grouped = {};
    planning.forEach(item => {
      const op = item.operatore;
      if (!grouped[op]) {
        grouped[op] = [];
      }
      grouped[op].push(item);
    });
    return grouped;
  }, [planning]);

  // Calcola il range di date totale
  const dateRange = useMemo(() => {
    if (planning.length === 0) return { start: new Date(), end: new Date() };
    
    let minDate = new Date(planning[0].data_inizio_recupero || planning[0].data_inizio_commessa);
    let maxDate = new Date(planning[0].data_consegna || planning[0].data_fine_commessa);
    
    planning.forEach(item => {
      const start = new Date(item.data_inizio_recupero || item.data_inizio_commessa);
      const end = new Date(item.data_consegna || item.data_fine_commessa);
      if (start < minDate) minDate = start;
      if (end > maxDate) maxDate = end;
    });
    
    return { start: minDate, end: maxDate };
  }, [planning]);

  const getDaysBetween = (start, end) => {
    try {
      const startDate = new Date(start);
      const endDate = new Date(end);
      const diffTime = Math.abs(endDate - startDate);
      return Math.ceil(diffTime / (1000 * 60 * 60 * 24));
    } catch {
      return 0;
    }
  };

  const getPositionPercent = (date) => {
    const totalDays = getDaysBetween(dateRange.start, dateRange.end);
    if (totalDays === 0) return 0;
    const daysFromStart = getDaysBetween(dateRange.start, date);
    return (daysFromStart / totalDays) * 100;
  };

  const getWidthPercent = (startDate, endDate) => {
    const totalDays = getDaysBetween(dateRange.start, dateRange.end);
    if (totalDays === 0) return 0;
    const duration = getDaysBetween(startDate, endDate);
    return (duration / totalDays) * 100;
  };

  if (loading) {
    return (
      <div className="card">
        <div className="loading">Caricamento pianificazione...</div>
      </div>
    );
  }

  return (
    <div>
      <div className="card">
        <h2>Pianificazione Temporale Commesse - Gantt Chart</h2>
        
        <div className="planning-config">
          <h3>Configurazione</h3>
          <div className="config-grid">
            <div className="config-item">
              <label>Numero Operatori:</label>
              <input
                type="number"
                min="1"
                max="20"
                value={config.num_operatori}
                onChange={(e) => handleConfigChange('num_operatori', e.target.value)}
              />
            </div>
            <div className="config-item">
              <label>Tempo Commessa (giorni):</label>
              <input
                type="number"
                min="1"
                max="365"
                value={config.tempo_commessa_giorni}
                onChange={(e) => handleConfigChange('tempo_commessa_giorni', e.target.value)}
              />
            </div>
            <div className="config-item">
              <label>Tempo Recupero Materie Prime (giorni):</label>
              <input
                type="number"
                min="1"
                max="365"
                value={config.tempo_recupero_materie_giorni}
                onChange={(e) => handleConfigChange('tempo_recupero_materie_giorni', e.target.value)}
              />
            </div>
          </div>
          <button className="button" onClick={handleSaveConfig}>
            Aggiorna Pianificazione
          </button>
        </div>
      </div>

      {error && (
        <div className="card">
          <div className="error">{error}</div>
        </div>
      )}

      {planning.length === 0 ? (
        <div className="card">
          <p className="empty-message">
            Nessun preventivo disponibile per la pianificazione.
          </p>
        </div>
      ) : (
        <div className="card">
          <h2>Gantt Chart Aggregato - Lavori in Contemporanea</h2>
          <div className="gantt-container">
            {/* Header con date */}
            <div className="gantt-header">
              <div className="gantt-operator-header">Operatore</div>
              <div className="gantt-timeline-header">
                <div className="gantt-date-marker">
                  {formatDate(dateRange.start)}
                </div>
                <div className="gantt-date-marker end">
                  {formatDate(dateRange.end)}
                </div>
              </div>
            </div>

            {/* Riga per ogni operatore */}
            {Array.from({ length: config.num_operatori }, (_, i) => i + 1).map(operatore => {
              const items = planningByOperatore[operatore] || [];
              return (
                <div key={operatore} className="gantt-row">
                  <div className="gantt-operator-label">
                    <span className="operator-badge">Operatore {operatore}</span>
                    <span className="operator-count">({items.length} commesse)</span>
                  </div>
                  <div className="gantt-timeline">
                    {items.map((item, idx) => {
                      const startDate = item.data_inizio_recupero || item.data_inizio_commessa;
                      const endDate = item.data_consegna || item.data_fine_commessa;
                      const left = getPositionPercent(startDate);
                      const width = getWidthPercent(startDate, endDate);
                      
                      const recuperoStart = item.data_inizio_recupero;
                      const recuperoEnd = item.data_fine_recupero || item.data_inizio_commessa;
                      const commessaStart = item.data_inizio_commessa;
                      const commessaEnd = item.data_fine_commessa;
                      
                      const recuperoLeft = getPositionPercent(recuperoStart);
                      const recuperoWidth = getWidthPercent(recuperoStart, recuperoEnd);
                      const commessaLeft = getPositionPercent(commessaStart);
                      const commessaWidth = getWidthPercent(commessaStart, commessaEnd);
                      
                      return (
                        <div key={item.preventivo_id} className="gantt-item-container" style={{ left: `${left}%`, width: `${width}%` }}>
                          <div className="gantt-item">
                            <div 
                              className="gantt-phase recupero"
                              style={{ 
                                left: `${((recuperoLeft - left) / width) * 100}%`,
                                width: `${(recuperoWidth / width) * 100}%`
                              }}
                              title={`Recupero: ${formatDate(recuperoStart)} - ${formatDate(recuperoEnd)}`}
                            >
                              <span className="phase-label-small">R</span>
                            </div>
                            <div 
                              className="gantt-phase commessa"
                              style={{ 
                                left: `${((commessaLeft - left) / width) * 100}%`,
                                width: `${(commessaWidth / width) * 100}%`
                              }}
                              title={`Commessa: ${formatDate(commessaStart)} - ${formatDate(commessaEnd)}`}
                            >
                              <span className="phase-label-small">C</span>
                            </div>
                            <div className="gantt-item-label" title={item.filename}>
                              {item.filename.length > 20 ? item.filename.substring(0, 20) + '...' : item.filename}
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Legenda */}
          <div className="gantt-legend">
            <div className="legend-item">
              <div className="legend-color recupero"></div>
              <span>Recupero Materie Prime</span>
            </div>
            <div className="legend-item">
              <div className="legend-color commessa"></div>
              <span>Commessa</span>
            </div>
          </div>

          {/* Dettagli commesse */}
          <div className="planning-details">
            <h3>Dettagli Commesse</h3>
            <div className="details-grid">
              {planning.map((item) => (
                <div key={item.preventivo_id} className="detail-card">
                  <div className="detail-header">
                    <h4>{item.filename}</h4>
                    <span className="badge operatore">Op. {item.operatore}</span>
                  </div>
                  <div className="detail-info">
                    <div><strong>Cliente:</strong> {item.cliente}</div>
                    {item.totale !== 'N/A' && <div><strong>Totale:</strong> {item.totale}</div>}
                    <div><strong>Recupero:</strong> {formatDate(item.data_inizio_recupero)} - {formatDate(item.data_fine_recupero)}</div>
                    <div><strong>Commessa:</strong> {formatDate(item.data_inizio_commessa)} - {formatDate(item.data_fine_commessa)}</div>
                    <div><strong>Consegna:</strong> {formatDate(item.data_consegna)}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default PlanningView;
