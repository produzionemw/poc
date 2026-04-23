import React, { useState, useEffect } from 'react';
import { API_BASE } from './apiConfig';
import './App.css';
import Login, { isAuthenticated } from './components/Login';
import FileUpload from './components/FileUpload';
import PreventiviList from './components/PreventiviList';
import SimilarityView from './components/SimilarityView';
import ConfigPanel from './components/ConfigPanel';
import CommesseOreView from './components/CommesseOreView';
import PlanningView from './components/PlanningView';
import ModelView from './components/ModelView';
import FattoreKView from './components/FattoreKView';

/** Impostare true per mostrare di nuovo il menu Pianificazione */
const SHOW_PLANNING_MENU = false;

function App() {
  const [auth, setAuth] = useState(isAuthenticated());
  const [preventivi, setPreventivi] = useState([]);
  const [selectedPreventivo, setSelectedPreventivo] = useState(null);
  const [similarPreventivi, setSimilarPreventivi] = useState([]);
  const [loading, setLoading] = useState(false);

  const [activeTab, setActiveTab] = useState('upload');
  const [config, setConfig] = useState(null);

  useEffect(() => {
    if (!auth) return;
    loadPreventivi();
    loadConfig();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [auth]);

  const loadPreventivi = async () => {
    try {
      const response = await fetch(`${API_BASE}/api/preventivi`);
      const data = await response.json();
      if (data.preventivi) {
        setPreventivi(data.preventivi);
      }
    } catch (error) {
      console.error('Errore nel caricamento preventivi:', error);
    }
  };

  const loadConfig = async () => {
    try {
      const response = await fetch(`${API_BASE}/api/config`);
      const data = await response.json();
      setConfig(data);
    } catch (error) {
      console.error('Errore nel caricamento configurazione:', error);
    }
  };

  const handleUploadSuccess = () => {
    loadPreventivi();
  };

  const handlePreventivoSelect = async (preventivoId) => {
    setSelectedPreventivo(preventivoId);
    setLoading(true);
    try {
      const response = await fetch(`${API_BASE}/api/preventivi/${preventivoId}/similar`);
      const data = await response.json();
      if (data.similar_preventivi) {
        setSimilarPreventivi(data.similar_preventivi);
      }
    } catch (error) {
      console.error('Errore nel calcolo somiglianza:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleConfigUpdate = async (newConfig) => {
    try {
      const response = await fetch(`${API_BASE}/api/config`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(newConfig),
      });
      const data = await response.json();
      if (data.success) {
        setConfig(newConfig);
        if (selectedPreventivo) {
          handlePreventivoSelect(selectedPreventivo);
        }
      }
    } catch (error) {
      console.error('Errore nell\'aggiornamento configurazione:', error);
    }
  };

  if (!auth) return <Login onLogin={() => setAuth(true)} />;

  return (
    <div className="App">
      <header className="App-header">
        <h1>METAL WORKING</h1>
        <p>Sistema di Gestione e Analisi Preventivi con Intelligenza Artificiale</p>
      </header>

      <nav className="tabs">
        <button
          className={activeTab === 'upload' ? 'active' : ''}
          onClick={() => setActiveTab('upload')}
          type="button"
        >
          Carica Preventivo
        </button>
        <button
          className={activeTab === 'list' ? 'active' : ''}
          onClick={() => setActiveTab('list')}
          type="button"
        >
          Lista Preventivi
        </button>
        <button
          className={activeTab === 'similarity' ? 'active' : ''}
          onClick={() => setActiveTab('similarity')}
          type="button"
        >
          Analisi Somiglianza
        </button>
        <button
          className={activeTab === 'fattore-af' ? 'active' : ''}
          onClick={() => setActiveTab('fattore-af')}
          type="button"
        >
          Fattore AF
        </button>
        {SHOW_PLANNING_MENU && (
          <button
            className={activeTab === 'planning' ? 'active' : ''}
            onClick={() => setActiveTab('planning')}
            type="button"
          >
            Pianificazione
          </button>
        )}
        <button
          className={activeTab === 'model' ? 'active' : ''}
          onClick={() => setActiveTab('model')}
          type="button"
        >
          Modello AI
        </button>
        <button
          className={activeTab === 'commesse-ore' ? 'active' : ''}
          onClick={() => setActiveTab('commesse-ore')}
          type="button"
        >
          Ore commesse
        </button>
        <button
          className={activeTab === 'config' ? 'active' : ''}
          onClick={() => setActiveTab('config')}
          type="button"
        >
          Configurazione
        </button>
      </nav>

      <main className="main-content">
        {activeTab === 'upload' && (
          <FileUpload onUploadSuccess={handleUploadSuccess} />
        )}

        {activeTab === 'list' && (
          <PreventiviList
            preventivi={preventivi}
            onPreventivoSelect={handlePreventivoSelect}
            selectedId={selectedPreventivo}
          />
        )}

        {activeTab === 'similarity' && (
          <SimilarityView
            preventivi={preventivi}
            selectedPreventivo={selectedPreventivo}
            similarPreventivi={similarPreventivi}
            loading={loading}
            onPreventivoSelect={handlePreventivoSelect}
          />
        )}

        {activeTab === 'fattore-af' && (
          <FattoreKView />
        )}

        {SHOW_PLANNING_MENU && activeTab === 'planning' && <PlanningView />}

        {activeTab === 'model' && (
          <ModelView />
        )}

        {activeTab === 'commesse-ore' && (
          <CommesseOreView />
        )}

        {activeTab === 'config' && (
          <ConfigPanel config={config} onConfigUpdate={handleConfigUpdate} />
        )}
      </main>

      <footer className="App-footer">
        <p>Metal Working · Gestione preventivi e modello predittivo — POC</p>
      </footer>
    </div>
  );
}

export default App;
