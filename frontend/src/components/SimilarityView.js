import React, { useState, useEffect } from 'react';
import axios from 'axios';
import './SimilarityView.css';

function KBadgeInline({ preventivoId }) {
  const [kData, setKData] = useState(null);
  useEffect(() => {
    axios.get(`/api/preventivi/${preventivoId}/fattore-af`)
      .then(r => setKData(r.data))
      .catch(() => setKData({ error: true }));
  }, [preventivoId]);

  if (!kData) return <span style={{fontSize:10,color:'#999'}}>Calcolo AF...</span>;
  if (kData.error || kData.k_normalizzato == null) return null;

  const color = kData.k_percentile >= 75 ? '#a32d2d'
              : kData.k_percentile >= 50 ? '#e65100' : '#2e7d32';
  return (
    <div style={{
      display:'inline-flex', gap:12, background:'#f0f7ff',
      borderRadius:6, padding:'8px 14px', marginBottom:12,
      fontSize:11, flexWrap:'wrap'
    }}>
      <span><strong style={{color}}>AF: {kData.k_normalizzato?.toFixed(1)}</strong> ore/ton</span>
      <span>Ore totali: <strong>{kData.ore_totali?.toFixed(1)}h</strong></span>
      <span>Complessità:{' '}
        <strong style={{color}}>
          {kData.k_percentile >= 75 ? 'Alta'
           : kData.k_percentile >= 50 ? 'Media' : 'Bassa'}
        </strong>
      </span>
    </div>
  );
}

function SimilarityView({ preventivi, selectedPreventivo, similarPreventivi, loading, onPreventivoSelect }) {
  const [expandedId, setExpandedId] = useState(null);

  const getPreventivoById = (id) => {
    return preventivi.find(p => p.id === id);
  };

  const getFieldValue = (preventivo, fieldName) => {
    if (!preventivo) return 'N/A';
    if (!preventivo.extracted_info) return 'N/A';
    const info = preventivo.extracted_info;
    if (!info || typeof info !== 'object') return 'N/A';

    if (fieldName.toLowerCase() === 'materiale' && info.materiali && typeof info.materiali === 'object' && !Array.isArray(info.materiali)) {
      const v = info.materiali.materiale;
      if (v !== undefined && v !== null && v !== '') return String(v);
    }

    // Funzione helper per cercare in strutture annidate
    const searchNested = (obj, searchKey) => {
      if (!obj || typeof obj !== 'object' || obj === null) return null;
      
      // Cerca direttamente
      if (obj[searchKey] !== undefined && obj[searchKey] !== null) {
        const value = obj[searchKey];
        if (value !== null && typeof value === 'object' && !Array.isArray(value)) {
          // Se è un oggetto, prova a estrarre valori comuni
          return value.nome || value.name || value.valore || value.value || JSON.stringify(value);
        }
        return String(value);
      }
      
      // Cerca in oggetti annidati
      for (const key in obj) {
        if (obj.hasOwnProperty(key) && key.toLowerCase().includes(searchKey.toLowerCase())) {
          const value = obj[key];
          if (value !== null && value !== undefined && typeof value === 'object' && !Array.isArray(value)) {
            // Se è un oggetto cliente, cerca nome
            if (searchKey === 'cliente' && value && value.nome) {
              return value.nome;
            }
            // Altrimenti prova a estrarre valori (solo se value non è null)
            if (value) {
              return value.nome || value.name || value.valore || value.value || JSON.stringify(value);
            }
          }
          if (value !== null && value !== undefined) {
            return String(value);
          }
        }
      }
      
      // Cerca ricorsivamente
      for (const key in obj) {
        if (obj.hasOwnProperty(key) && typeof obj[key] === 'object' && obj[key] !== null) {
          const result = searchNested(obj[key], searchKey);
          if (result) return result;
        }
      }
      
      return null;
    };
    
    // Mappatura campi comuni
    const fieldMapping = {
      'cliente': ['cliente', 'cliente.nome', 'cliente_name', 'customer'],
      'totale': ['prezzo_totale_fornitura', 'totale', 'prezzo', 'price', 'total', 'prezzo_complessivo'],
      'descrizione_lavori': ['descrizione_lavori', 'descrizione', 'description', 'modello_struttura', 'tipologia'],
      materiale: ['materiale', 'materiali'],
    };
    
    // Cerca usando il mapping
    const searchKeys = fieldMapping[fieldName] || [fieldName];
    for (const searchKey of searchKeys) {
      const result = searchNested(info, searchKey);
      if (result && result !== 'null' && result !== 'undefined') {
        return result;
      }
    }
    
    // Cerca direttamente con variazioni
    const variations = [
      fieldName,
      fieldName.toLowerCase(),
      fieldName.replace('_', ' '),
      fieldName.replace('_', '')
    ];
    
    for (const variation of variations) {
      const result = searchNested(info, variation);
      if (result && result !== 'null' && result !== 'undefined') {
        return result;
      }
    }
    
    return 'N/A';
  };

  const formatSimilarity = (score) => {
    return `${(score * 100).toFixed(1)}%`;
  };

  const formatFieldLabel = (key) => key.replace(/_/g, ' ');

  const renderScalar = (value) => {
    if (value === null || value === undefined) return 'N/A';
    if (typeof value === 'boolean') return value ? 'Sì' : 'No';
    return String(value);
  };

  /** Prova a interpretare ref/comp dalla API come JSON (dict/list serializzati dal backend). */
  const parseStructuredString = (raw) => {
    if (raw === null || raw === undefined || raw === '') return null;
    if (typeof raw !== 'string') return null;
    const trimmed = raw.trim();
    if (!trimmed.startsWith('{') && !trimmed.startsWith('[')) return null;
    try {
      const parsed = JSON.parse(trimmed);
      if (parsed !== null && typeof parsed === 'object') return parsed;
    } catch {
      /* stringa non JSON (es. testo lungo) */
    }
    return null;
  };

  /** Albero nome : valore per extracted_info (oggetti annidati e array). `compact` = blocchi Riferimento/Confronto. */
  const renderExtractedFields = (obj, prefix = '', depth = 0, compact = false) => {
    if (!obj || typeof obj !== 'object') return null;
    return Object.keys(obj).map((key) => {
      const value = obj[key];
      const fullKey = prefix ? `${prefix}.${key}` : key;
      const label = formatFieldLabel(key);
      const isRoot = depth === 0;
      const rowClass = compact ? 'extracted-row field-sim-row' : isRoot ? 'detail-item' : 'extracted-row';

      if (value === null || value === undefined) {
        return (
          <div key={fullKey} className={rowClass}>
            <span className="detail-label">{label}:</span>
            <span className="detail-value">N/A</span>
          </div>
        );
      }

      if (typeof value === 'object' && !Array.isArray(value)) {
        const titleClass = compact
          ? 'extracted-subsection-title field-sim-subtitle'
          : isRoot
            ? 'detail-label extracted-tree-heading'
            : 'extracted-subsection-title';
        const containerClass = compact
          ? 'extracted-subsection field-sim-subsection'
          : isRoot
            ? 'detail-item extracted-tree-root'
            : 'extracted-subsection';
        return (
          <div key={fullKey} className={containerClass}>
            <div className={titleClass}>{label}</div>
            <div className={compact ? 'extracted-nested field-sim-nested' : 'extracted-nested'}>
              {renderExtractedFields(value, fullKey, depth + 1, compact)}
            </div>
          </div>
        );
      }

      if (Array.isArray(value)) {
        if (value.length === 0) {
          return (
            <div key={fullKey} className={rowClass}>
              <span className="detail-label">{label}:</span>
              <span className="detail-value">Nessuno</span>
            </div>
          );
        }
        const primitivesOnly = value.every(
          (item) => item === null || item === undefined || typeof item !== 'object'
        );
        if (primitivesOnly) {
          return (
            <div key={fullKey} className={rowClass}>
              <span className="detail-label">{label}:</span>
              <span className="detail-value">{value.map(renderScalar).join(', ')}</span>
            </div>
          );
        }
        const arrayContainerClass = compact
          ? 'extracted-array-block field-sim-array'
          : isRoot
            ? 'detail-item extracted-tree-root'
            : 'extracted-array-block';
        const arrayHeadingClass = compact
          ? 'extracted-subsection-title field-sim-subtitle'
          : isRoot
            ? 'detail-label extracted-tree-heading'
            : 'detail-label';
        return (
          <div key={fullKey} className={arrayContainerClass}>
            <div className={arrayHeadingClass}>{label}</div>
            <div className="extracted-array">
              {value.map((item, idx) => (
                <div key={idx} className="extracted-array-card">
                  {item !== null && typeof item === 'object' && !Array.isArray(item) ? (
                    renderExtractedFields(item, `${fullKey}[${idx}]`, depth + 1, compact)
                  ) : Array.isArray(item) ? (
                    <span className="detail-value">{JSON.stringify(item)}</span>
                  ) : (
                    <span className="detail-value">{renderScalar(item)}</span>
                  )}
                </div>
              ))}
            </div>
          </div>
        );
      }

      return (
        <div key={fullKey} className={rowClass}>
          <span className="detail-label">{label}:</span>
          <span className="detail-value">{renderScalar(value)}</span>
        </div>
      );
    });
  };

  const renderComparisonValue = (raw) => {
    const parsed = parseStructuredString(raw);
    if (parsed) {
      return <div className="field-sim-tree">{renderExtractedFields(parsed, '', 0, true)}</div>;
    }
    const text = raw === null || raw === undefined || raw === '' ? 'N/A' : String(raw);
    return <span className="field-sim-plain">{text}</span>;
  };

  /** Valore grezzo da extracted_info (allineato ai nomi campo della config somiglianza). */
  const getRawExtractedField = (preventivo, fieldName) => {
    const info = preventivo?.extracted_info;
    if (!info || typeof info !== 'object') return undefined;
    const variations = [
      fieldName,
      fieldName.toLowerCase(),
      fieldName.toUpperCase(),
      fieldName.replace(/_/g, ' '),
      fieldName.replace(/_/g, ''),
    ];
    for (const v of variations) {
      if (Object.prototype.hasOwnProperty.call(info, v) && info[v] !== undefined) {
        return info[v];
      }
    }
    const lower = fieldName.toLowerCase();
    for (const key of Object.keys(info)) {
      if (key.toLowerCase() === lower) {
        return info[key];
      }
    }
    // Config "materiale" → dati spesso in materiali.materiale
    if (lower === 'materiale') {
      const mat = info.materiali;
      if (mat && typeof mat === 'object' && !Array.isArray(mat)) {
        if (mat.materiale !== undefined && mat.materiale !== null && mat.materiale !== '') {
          return mat.materiale;
        }
        return mat;
      }
    }
    return undefined;
  };

  const renderStructuredFieldValue = (raw) => {
    if (raw === undefined || raw === null) {
      return <span className="field-sim-plain">N/A</span>;
    }
    if (typeof raw === 'object') {
      return <div className="field-sim-tree">{renderExtractedFields(raw, '', 0, true)}</div>;
    }
    return <span className="field-sim-plain">{String(raw)}</span>;
  };

  /** Usa extracted_info (oggetti reali); solo se manca il campo usa la stringa API. */
  const renderFieldComparisonCell = (rawFromExtracted, apiString) => {
    if (rawFromExtracted !== undefined) {
      return renderStructuredFieldValue(rawFromExtracted);
    }
    return renderComparisonValue(apiString);
  };

  const getSimilarityColor = (score) => {
    if (score >= 0.7) return '#4caf50';
    if (score >= 0.5) return '#ff9800';
    return '#f44336';
  };

  if (!selectedPreventivo) {
    return (
      <div className="card">
        <h2>Analisi Somiglianza</h2>
        <p className="info-message">
          Seleziona un preventivo: la somiglianza usa i dati estratti e salvati in database per ogni offerta
          (campo <code>extracted_info</code>), non i file locali.
        </p>
      </div>
    );
  }

  const referencePreventivo = getPreventivoById(selectedPreventivo);

  if (!referencePreventivo) {
    return (
      <div className="card">
        <h2>Analisi Somiglianza</h2>
        <p className="error">Preventivo di riferimento non trovato.</p>
      </div>
    );
  }

  return (
    <div>
      <div className="card">
        <h2>Preventivo di Riferimento</h2>
        <div className="reference-preventivo">
          <h3>{referencePreventivo.filename}</h3>
          <div className="reference-info">
            <div className="info-item">
              <span className="label">Cliente:</span>
              <span className="value">{getFieldValue(referencePreventivo, 'cliente')}</span>
            </div>
            <div className="info-item">
              <span className="label">Totale:</span>
              <span className="value">{getFieldValue(referencePreventivo, 'totale')}</span>
            </div>
            <div className="info-item">
              <span className="label">Descrizione:</span>
              <span className="value">{getFieldValue(referencePreventivo, 'descrizione_lavori')}</span>
            </div>
          </div>
        </div>
      </div>

      <div className="card">
        <h2>Preventivi Simili ({similarPreventivi.length})</h2>
        {loading ? (
          <div className="loading">Calcolo somiglianza in corso...</div>
        ) : similarPreventivi.length === 0 ? (
          <p className="info-message">Nessun preventivo simile trovato con la configurazione attuale.</p>
        ) : (
          <div className="similar-list">
            {similarPreventivi.map((item, index) => {
              const preventivo = item.preventivo;
              const isExpanded = expandedId === preventivo.id;
              
              return (
                <div key={preventivo.id} className="similar-item">
                  <div className="similar-header" onClick={() => setExpandedId(isExpanded ? null : preventivo.id)}>
                    <div className="similar-rank">
                      <span className="rank-number">#{index + 1}</span>
                      <div className="similarity-badge" style={{ backgroundColor: getSimilarityColor(item.similarity_score) }}>
                        {formatSimilarity(item.similarity_score)}
                      </div>
                    </div>
                    <div className="similar-info">
                      <h4>{preventivo.filename}</h4>
                      <p className="similar-preview">
                        Cliente: {getFieldValue(preventivo, 'cliente')} | 
                        Totale: {getFieldValue(preventivo, 'totale')}
                      </p>
                    </div>
                    <button className="expand-button">
                      {isExpanded ? '▼' : '▶'}
                    </button>
                  </div>
                  
                  {isExpanded && (
                    <div className="similar-details">
                      <div className="similarity-field-details-panel">
                        <h5 className="similarity-field-details-heading">Dettagli somiglianza per campo</h5>
                        <p className="similarity-field-details-sub">
                          Confronto riferimento vs <strong>{preventivo.filename}</strong>
                          <span className="similarity-field-details-score">
                            {' '}
                            ({formatSimilarity(item.similarity_score)} complessivo)
                          </span>
                        </p>
                        <div className="field-similarities field-similarities--pastel">
                          {Object.entries(item.field_similarities || {}).map(([field, data]) => (
                            <div key={field} className="field-similarity field-similarity--pastel">
                              <div className="field-header">
                                <span className="field-name">{field}</span>
                                <span className="field-score" style={{ color: getSimilarityColor(data.similarity) }}>
                                  {formatSimilarity(data.similarity)}
                                </span>
                              </div>
                              <div className="field-values">
                                <div className="field-value field-value-with-tree">
                                  <strong className="field-value-label">Riferimento</strong>
                                  <div className="field-value-body">
                                    {renderFieldComparisonCell(
                                      getRawExtractedField(referencePreventivo, field),
                                      data.ref_value
                                    )}
                                  </div>
                                </div>
                                <div className="field-value field-value-with-tree">
                                  <strong className="field-value-label">Confronto</strong>
                                  <div className="field-value-body">
                                    {renderFieldComparisonCell(
                                      getRawExtractedField(preventivo, field),
                                      data.comp_value
                                    )}
                                  </div>
                                </div>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                      <KBadgeInline preventivoId={preventivo.id} />
                      <div className="details-section">
                        <h5>Informazioni Preventivo</h5>
                        <div className="details-grid">
                          {renderExtractedFields(preventivo.extracted_info || {})}
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

export default SimilarityView;
