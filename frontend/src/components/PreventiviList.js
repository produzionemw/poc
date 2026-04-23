import React, { useState, useEffect, useMemo } from 'react';
import { API_BASE } from '../apiConfig';
import './PreventiviList.css';

function buildSearchHaystack(preventivo) {
  const name = (preventivo.filename || '').toLowerCase();
  let json = '';
  try {
    json = JSON.stringify(preventivo.extracted_info || {}).toLowerCase();
  } catch {
    json = '';
  }
  return `${name} ${json}`;
}

function PreventiviList({ preventivi, onPreventivoSelect, selectedId }) {
  const [searchQuery, setSearchQuery] = useState('');
  const [showModal, setShowModal] = useState(false);
  const [selectedPreventivo, setSelectedPreventivo] = useState(null);
  const [fullPreventivo, setFullPreventivo] = useState(null);
  const [loadingDetails, setLoadingDetails] = useState(false);

  useEffect(() => {
    if (showModal && selectedPreventivo) {
      loadFullPreventivo(selectedPreventivo.id);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showModal, selectedPreventivo]);

  const filteredPreventivi = useMemo(() => {
    const q = searchQuery.trim();
    if (!q) return preventivi;
    const tokens = q.toLowerCase().split(/\s+/).filter(Boolean);
    return preventivi.filter((p) => {
      const hay = buildSearchHaystack(p);
      return tokens.every((t) => hay.includes(t));
    });
  }, [preventivi, searchQuery]);

  const loadFullPreventivo = async (preventivoId) => {
    setLoadingDetails(true);
    try {
      const response = await fetch(`${API_BASE}/api/preventivi/${preventivoId}`);
      const data = await response.json();
      if (data.preventivo) {
        setFullPreventivo(data.preventivo);
      }
    } catch (error) {
      console.error('Errore nel caricamento dettagli:', error);
      setFullPreventivo(selectedPreventivo); // Usa i dati già disponibili
    } finally {
      setLoadingDetails(false);
    }
  };
  const formatDate = (dateString) => {
    try {
      const date = new Date(dateString);
      return date.toLocaleDateString('it-IT', {
        year: 'numeric',
        month: 'long',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
      });
    } catch {
      return dateString;
    }
  };

  const formatDateShort = (dateString) => {
    try {
      const date = new Date(dateString);
      return date.toLocaleString('it-IT', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return dateString;
    }
  };

  const getFieldValue = (preventivo, fieldName) => {
    if (!preventivo) return 'N/A';
    if (!preventivo.extracted_info) return 'N/A';
    const info = preventivo.extracted_info || {};
    if (!info || typeof info !== 'object') return 'N/A';
    
    // Funzione helper per cercare in strutture annidate
    const searchNested = (obj, searchKey) => {
      if (!obj || typeof obj !== 'object' || obj === null) return null;
      
      // Cerca direttamente
      if (obj[searchKey] !== undefined && obj[searchKey] !== null) {
        const value = obj[searchKey];
        if (typeof value === 'object' && !Array.isArray(value) && value !== null) {
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
      'descrizione_lavori': ['descrizione_lavori', 'descrizione', 'description', 'modello_struttura', 'tipologia']
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

  if (preventivi.length === 0) {
    return (
      <div className="card">
        <h2>Lista Preventivi</h2>
        <p className="empty-message">Nessun preventivo caricato. Carica il primo preventivo dalla sezione "Carica Preventivo".</p>
      </div>
    );
  }

  const total = preventivi.length;
  const shown = filteredPreventivi.length;
  const hasFilter = searchQuery.trim().length > 0;

  const renderValue = (value) => {
    if (value === null || value === undefined) return 'N/A';
    if (typeof value === 'object') {
      if (Array.isArray(value)) {
        return value.length > 0 ? value.join(', ') : 'Nessuno';
      }
      return JSON.stringify(value, null, 2);
    }
    return String(value);
  };

  const renderDetails = (obj, prefix = '') => {
    if (!obj || typeof obj !== 'object') return null;
    
    return Object.keys(obj).map(key => {
      const value = obj[key];
      const fullKey = prefix ? `${prefix}.${key}` : key;
      
      if (value === null || value === undefined) {
        return null;
      }
      
      if (typeof value === 'object' && !Array.isArray(value)) {
        return (
          <div key={fullKey} className="detail-section">
            <h4 className="detail-section-title">{key.replace(/_/g, ' ').toUpperCase()}</h4>
            <div className="detail-nested">
              {renderDetails(value, fullKey)}
            </div>
          </div>
        );
      }
      
      if (Array.isArray(value)) {
        return (
          <div key={fullKey} className="detail-item">
            <span className="detail-label">{key.replace(/_/g, ' ')}:</span>
            <div className="detail-array">
              {value.map((item, idx) => (
                <div key={idx} className="detail-array-item">• {renderValue(item)}</div>
              ))}
            </div>
          </div>
        );
      }
      
      return (
        <div key={fullKey} className="detail-item">
          <span className="detail-label">{key.replace(/_/g, ' ')}:</span>
          <span className="detail-value">{renderValue(value)}</span>
        </div>
      );
    });
  };

  return (
    <>
      <div className="card">
        <div className="preventivi-list-header">
          <h2>
            {`Lista Preventivi (${shown}${hasFilter && shown !== total ? ` di ${total}` : ''})`}
          </h2>
          <div className="preventivi-search-wrap">
            <label htmlFor="preventivi-search" className="sr-only">
              Cerca in file e dati estratti
            </label>
            <input
              id="preventivi-search"
              type="search"
              className="preventivi-search-input"
              placeholder="Cerca per nome file o contenuto estratto (cliente, importi, note…)"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              autoComplete="off"
            />
            {hasFilter && (
              <button
                type="button"
                className="preventivi-search-clear"
                onClick={() => setSearchQuery('')}
              >
                Azzera
              </button>
            )}
          </div>
        </div>
        {hasFilter && shown === 0 ? (
          <p className="empty-message search-empty">
            Nessun preventivo corrisponde alla ricerca. Prova altre parole o azzera il filtro.
          </p>
        ) : (
        <div className="preventivi-table-wrap">
          <table className="preventivi-table">
            <thead>
              <tr>
                <th scope="col">File</th>
                <th scope="col">Ultima modifica</th>
                <th scope="col">Cliente</th>
                <th scope="col">Totale</th>
                <th scope="col">Descrizione</th>
                <th scope="col" className="preventivi-table-col-actions">Azioni</th>
              </tr>
            </thead>
            <tbody>
              {filteredPreventivi.map((preventivo) => {
                const descRaw = getFieldValue(preventivo, 'descrizione_lavori');
                const descSnippet =
                  descRaw === 'N/A'
                    ? descRaw
                    : descRaw.length > 120
                      ? `${descRaw.substring(0, 120)}…`
                      : descRaw;
                return (
                  <tr
                    key={preventivo.id}
                    className={selectedId === preventivo.id ? 'selected' : ''}
                    onClick={() => onPreventivoSelect && onPreventivoSelect(preventivo.id)}
                  >
                    <td className="preventivi-td-file" title={preventivo.filename}>
                      <span className="preventivi-file-name">{preventivo.filename}</span>
                    </td>
                    <td className="preventivi-td-date">
                      {formatDateShort(preventivo.updated_at || preventivo.upload_date)}
                    </td>
                    <td>{getFieldValue(preventivo, 'cliente')}</td>
                    <td>{getFieldValue(preventivo, 'totale')}</td>
                    <td className="preventivi-td-desc" title={descRaw !== 'N/A' ? descRaw : ''}>
                      {descSnippet}
                    </td>
                    <td className="preventivi-td-actions">
                      <button
                        type="button"
                        className="button-table-details"
                        onClick={(e) => {
                          e.stopPropagation();
                          setSelectedPreventivo(preventivo);
                          setShowModal(true);
                        }}
                      >
                        Dettagli
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        )}
      </div>

      {showModal && selectedPreventivo && (
        <div className="modal-overlay" onClick={() => {
          setShowModal(false);
          setFullPreventivo(null);
        }}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Dettagli Preventivo</h2>
              <button className="modal-close" onClick={() => {
                setShowModal(false);
                setFullPreventivo(null);
              }}>×</button>
            </div>
            <div className="modal-body">
              {loadingDetails ? (
                <div className="loading">Caricamento dettagli...</div>
              ) : (
                <>
                  <div className="modal-section">
                    <h3>Informazioni Generali</h3>
                    <div className="detail-item">
                      <span className="detail-label">File:</span>
                      <span className="detail-value">{(fullPreventivo || selectedPreventivo).filename}</span>
                    </div>
                    <div className="detail-item">
                      <span className="detail-label">Caricato il:</span>
                      <span className="detail-value">{formatDate((fullPreventivo || selectedPreventivo).upload_date)}</span>
                    </div>
                    {(fullPreventivo || selectedPreventivo).updated_at &&
                      (fullPreventivo || selectedPreventivo).updated_at !==
                        (fullPreventivo || selectedPreventivo).upload_date && (
                      <div className="detail-item">
                        <span className="detail-label">Ultima estrazione / modifica:</span>
                        <span className="detail-value">
                          {formatDate((fullPreventivo || selectedPreventivo).updated_at)}
                        </span>
                      </div>
                    )}
                    <div className="detail-item">
                      <span className="detail-label">ID:</span>
                      <span className="detail-value">{(fullPreventivo || selectedPreventivo).id}</span>
                    </div>
                  </div>
                  
                  {(fullPreventivo || selectedPreventivo).extracted_info && (
                    <div className="modal-section">
                      <h3>Informazioni Estratte</h3>
                      <div className="details-container">
                        {renderDetails((fullPreventivo || selectedPreventivo).extracted_info)}
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}

export default PreventiviList;
