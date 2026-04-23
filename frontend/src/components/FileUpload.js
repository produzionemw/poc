import React, { useState } from 'react';
import './FileUpload.css';

function FileUpload({ onUploadSuccess }) {
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [message, setMessage] = useState(null);
  const [error, setError] = useState(null);

  const handleFileChange = (e) => {
    const selectedFile = e.target.files[0];
    if (selectedFile) {
      if (selectedFile.type !== 'application/pdf') {
        setError('Solo i file PDF sono supportati');
        setFile(null);
        return;
      }
      if (selectedFile.size > 16 * 1024 * 1024) {
        setError('Il file è troppo grande. Dimensione massima: 16MB');
        setFile(null);
        return;
      }
      setFile(selectedFile);
      setError(null);
      setMessage(null);
    }
  };

  const handleUpload = async () => {
    if (!file) {
      setError('Seleziona un file PDF');
      return;
    }

    setUploading(true);
    setError(null);
    setMessage(null);

    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await fetch('/api/upload', {
        method: 'POST',
        body: formData,
      });

      const data = await response.json();

      if (response.ok) {
        setMessage('Preventivo caricato con successo! Le informazioni sono state estratte.');
        setFile(null);
        // Reset file input
        document.getElementById('file-input').value = '';
        if (onUploadSuccess) {
          onUploadSuccess();
        }
      } else {
        setError(data.error || 'Errore durante il caricamento');
      }
    } catch (err) {
      setError('Errore di connessione. Assicurati che il backend sia in esecuzione.');
      console.error('Errore upload:', err);
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="card">
      <h2>Carica Preventivo PDF</h2>
      <p className="description">
        Carica un file PDF contenente un preventivo. Il sistema estrarrà automaticamente
        tutte le informazioni utilizzando Claude (Anthropic).
      </p>

      <div className="upload-area">
        <input
          id="file-input"
          type="file"
          accept=".pdf"
          onChange={handleFileChange}
          disabled={uploading}
          className="file-input"
        />
        <label htmlFor="file-input" className="file-label">
          {file ? file.name : 'Seleziona file PDF'}
        </label>
      </div>

      {file && (
        <div className="file-info">
          <p><strong>File selezionato:</strong> {file.name}</p>
          <p><strong>Dimensione:</strong> {(file.size / 1024 / 1024).toFixed(2)} MB</p>
        </div>
      )}

      {error && <div className="error">{error}</div>}
      {message && <div className="success">{message}</div>}

      <button
        className="button"
        onClick={handleUpload}
        disabled={!file || uploading}
      >
        {uploading ? 'Caricamento in corso...' : 'Carica e Analizza'}
      </button>

      {uploading && (
        <div className="loading-indicator">
          <div className="spinner"></div>
          <p>Estrazione informazioni in corso...</p>
        </div>
      )}
    </div>
  );
}

export default FileUpload;
