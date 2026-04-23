import React, { useState, useEffect, useMemo } from 'react';
import './ConfigPanel.css';
import { EXTRACTED_INFO_KNOWN_FIELD_GROUPS } from '../config/extractedInfoKnownFields';

function filterNorm(s) {
  return s.toLowerCase().normalize('NFD').replace(/\p{M}/gu, '');
}

function ConfigPanel({ config, onConfigUpdate }) {
  const [localConfig, setLocalConfig] = useState(config);
  const [saved, setSaved] = useState(false);
  const [addModalOpen, setAddModalOpen] = useState(false);
  const [fieldSearch, setFieldSearch] = useState('');
  const [customFieldName, setCustomFieldName] = useState('');

  useEffect(() => {
    setLocalConfig(config);
  }, [config]);

  const existingFieldNamesLower = useMemo(
    () => new Set((localConfig?.fields || []).map((f) => String(f.name).toLowerCase())),
    [localConfig]
  );

  const filteredGroups = useMemo(() => {
    const q = filterNorm(fieldSearch.trim());
    if (!q) return EXTRACTED_INFO_KNOWN_FIELD_GROUPS;
    return EXTRACTED_INFO_KNOWN_FIELD_GROUPS.map((g) => ({
      ...g,
      items: g.items.filter((it) => {
        const hay = filterNorm(`${it.name} ${it.label} ${it.hint || ''}`);
        return hay.includes(q);
      }),
    })).filter((g) => g.items.length > 0);
  }, [fieldSearch]);

  if (!localConfig) {
    return (
      <div className="card">
        <h2>Configurazione</h2>
        <div className="loading">Caricamento configurazione...</div>
      </div>
    );
  }

  const handleFieldToggle = (index) => {
    const newConfig = { ...localConfig };
    newConfig.fields[index].enabled = !newConfig.fields[index].enabled;
    setLocalConfig(newConfig);
    setSaved(false);
  };

  const handleWeightChange = (index, value) => {
    const newConfig = { ...localConfig };
    const weight = parseFloat(value);
    if (!isNaN(weight) && weight >= 0) {
      newConfig.fields[index].weight = weight;
      setLocalConfig(newConfig);
      setSaved(false);
    }
  };

  const handleThresholdChange = (value) => {
    const newConfig = { ...localConfig };
    const threshold = parseFloat(value);
    if (!isNaN(threshold) && threshold >= 0 && threshold <= 1) {
      newConfig.similarity_threshold = threshold;
      setLocalConfig(newConfig);
      setSaved(false);
    }
  };

  const addFieldByName = (rawName) => {
    const name = String(rawName || '').trim();
    if (!name || !localConfig) return;
    if (existingFieldNamesLower.has(name.toLowerCase())) return;
    const newConfig = { ...localConfig, fields: [...localConfig.fields] };
    newConfig.fields.push({
      name,
      weight: 1.0,
      enabled: true,
    });
    setLocalConfig(newConfig);
    setSaved(false);
  };

  const openAddModal = () => {
    setFieldSearch('');
    setCustomFieldName('');
    setAddModalOpen(true);
  };

  const closeAddModal = () => {
    setAddModalOpen(false);
    setFieldSearch('');
    setCustomFieldName('');
  };

  const handleAddCustomFromModal = () => {
    addFieldByName(customFieldName);
    if (customFieldName.trim()) closeAddModal();
  };

  const handleRemoveField = (index) => {
    if (window.confirm('Sei sicuro di voler rimuovere questo campo?')) {
      const newConfig = { ...localConfig };
      newConfig.fields.splice(index, 1);
      setLocalConfig(newConfig);
      setSaved(false);
    }
  };

  const handleSave = () => {
    if (onConfigUpdate) {
      onConfigUpdate(localConfig);
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    }
  };

  return (
    <div className="card config-panel-root">
      <h2>Configurazione Campi Somiglianza</h2>
      <p className="config-description">
        Configura quali campi utilizzare per il calcolo della somiglianza tra preventivi.
        Puoi abilitare/disabilitare campi e modificare i pesi per dare più importanza a certi campi.
      </p>

      <div className="config-section">
        <h3>Soglia di Somiglianza</h3>
        <div className="threshold-control">
          <label>
            Valore minimo (0.0 - 1.0):
            <input
              type="number"
              min="0"
              max="1"
              step="0.1"
              value={localConfig.similarity_threshold}
              onChange={(e) => handleThresholdChange(e.target.value)}
              className="input"
            />
          </label>
          <span className="threshold-value">
            {(localConfig.similarity_threshold * 100).toFixed(0)}%
          </span>
        </div>
        <p className="help-text">
          Solo i preventivi con somiglianza superiore a questa soglia verranno mostrati.
        </p>
      </div>

      <div className="config-section">
        <div className="section-header">
          <h3>Campi per il Confronto</h3>
          <button type="button" className="button button-small" onClick={openAddModal}>
            + Aggiungi campo
          </button>
        </div>

        <div className="fields-list">
          {localConfig.fields.map((field, index) => (
            <div key={index} className="field-config">
              <div className="field-header">
                <label className="field-toggle">
                  <input
                    type="checkbox"
                    checked={field.enabled}
                    onChange={() => handleFieldToggle(index)}
                  />
                  <span className="field-name">{field.name}</span>
                </label>
                <button
                  className="button-remove"
                  onClick={() => handleRemoveField(index)}
                  title="Rimuovi campo"
                >
                  ×
                </button>
              </div>
              <div className="field-controls">
                <label>
                  Peso:
                  <input
                    type="number"
                    min="0"
                    step="0.1"
                    value={field.weight}
                    onChange={(e) => handleWeightChange(index, e.target.value)}
                    className="input-small"
                    disabled={!field.enabled}
                  />
                </label>
                <span className="weight-info">
                  {field.enabled
                    ? `Peso attivo: ${field.weight}x`
                    : 'Campo disabilitato'}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="config-actions">
        <button className="button" onClick={handleSave}>
          Salva Configurazione
        </button>
        {saved && <span className="save-message">✓ Configurazione salvata!</span>}
      </div>

      <div className="config-info">
        <h4>Come funziona:</h4>
        <ul>
          <li><strong>Peso:</strong> Un peso maggiore significa che quel campo ha più importanza nel calcolo della somiglianza.</li>
          <li><strong>Abilitazione:</strong> Solo i campi abilitati vengono considerati nel calcolo.</li>
          <li><strong>Soglia:</strong> I preventivi con somiglianza inferiore alla soglia non verranno mostrati.</li>
        </ul>
      </div>

      {addModalOpen && (
        <div
          className="config-modal-backdrop"
          role="presentation"
          onClick={() => closeAddModal()}
        >
          <div
            className="config-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="config-add-field-title"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="config-modal-header">
              <h3 id="config-add-field-title">Aggiungi campo da extracted_info</h3>
              <button
                type="button"
                className="config-modal-close"
                onClick={closeAddModal}
                aria-label="Chiudi"
              >
                ×
              </button>
            </div>
            <p className="config-modal-intro">
              Scegli un nome tra quelli che l’estrazione può salvare in <code>extracted_info</code>.
              I campi oggetto (lista o JSON) vengono confrontati come testo serializzato.
            </p>
            <label className="config-modal-search">
              <span className="config-modal-search-label">Cerca</span>
              <input
                type="search"
                className="input config-modal-search-input"
                placeholder="Nome tecnico, etichetta o descrizione…"
                value={fieldSearch}
                onChange={(e) => setFieldSearch(e.target.value)}
                autoFocus
              />
            </label>
            <div className="config-modal-list">
              {filteredGroups.map((group) => (
                <div key={group.id} className="config-modal-group">
                  <div className="config-modal-group-title">{group.label}</div>
                  <ul className="config-modal-items">
                    {group.items.map((it) => {
                      const taken = existingFieldNamesLower.has(it.name.toLowerCase());
                      return (
                        <li key={it.name} className="config-modal-item">
                          <div className="config-modal-item-main">
                            <div className="config-modal-item-head">
                              <span className="config-modal-item-label">{it.label}</span>
                              {it.recommended && (
                                <span className="config-modal-badge">Consigliato</span>
                              )}
                            </div>
                            <code className="config-modal-item-name">{it.name}</code>
                            {it.hint && (
                              <p className="config-modal-item-hint">{it.hint}</p>
                            )}
                          </div>
                          <button
                            type="button"
                            className="button button-small config-modal-add-btn"
                            disabled={taken}
                            onClick={() => {
                              addFieldByName(it.name);
                              closeAddModal();
                            }}
                          >
                            {taken ? 'Già in lista' : 'Aggiungi'}
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              ))}
              {filteredGroups.length === 0 && (
                <p className="config-modal-empty">Nessun campo corrisponde alla ricerca.</p>
              )}
            </div>
            <div className="config-modal-custom">
              <strong>Nome personalizzato</strong>
              <p className="config-modal-custom-hint">
                Se la chiave esiste solo in alcune offerte, puoi digitare il nome esatto della chiave in{' '}
                <code>extracted_info</code> (es. come in un JSON salvato).
              </p>
              <div className="config-modal-custom-row">
                <input
                  type="text"
                  className="input"
                  placeholder="es. prezzo_totale_fornitura"
                  value={customFieldName}
                  onChange={(e) => setCustomFieldName(e.target.value)}
                />
                <button
                  type="button"
                  className="button button-small"
                  onClick={handleAddCustomFromModal}
                  disabled={!customFieldName.trim() || existingFieldNamesLower.has(customFieldName.trim().toLowerCase())}
                >
                  Aggiungi
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default ConfigPanel;
