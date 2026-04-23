import React, { useState } from 'react';

const VALID_USER = 'admin';
const VALID_PASS = 'pocMW26';

export function isAuthenticated() {
  return sessionStorage.getItem('auth') === '1';
}

function Login({ onLogin }) {
  const [user, setUser] = useState('');
  const [pass, setPass] = useState('');
  const [error, setError] = useState('');

  const handleSubmit = (e) => {
    e.preventDefault();
    if (user === VALID_USER && pass === VALID_PASS) {
      sessionStorage.setItem('auth', '1');
      onLogin();
    } else {
      setError('Credenziali non valide');
    }
  };

  return (
    <div style={styles.overlay}>
      <div style={styles.box}>
        <h2 style={styles.title}>METAL WORKING</h2>
        <p style={styles.subtitle}>Gestione Preventivi</p>
        <form onSubmit={handleSubmit}>
          <input
            style={styles.input}
            type="text"
            placeholder="Utente"
            value={user}
            onChange={e => setUser(e.target.value)}
            autoFocus
          />
          <input
            style={styles.input}
            type="password"
            placeholder="Password"
            value={pass}
            onChange={e => setPass(e.target.value)}
          />
          {error && <p style={styles.error}>{error}</p>}
          <button style={styles.button} type="submit">Accedi</button>
        </form>
      </div>
    </div>
  );
}

const styles = {
  overlay: {
    position: 'fixed', inset: 0,
    background: '#1a1a2e',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    zIndex: 9999,
  },
  box: {
    background: '#fff',
    borderRadius: 8,
    padding: '40px 48px',
    width: 340,
    boxShadow: '0 8px 32px rgba(0,0,0,0.3)',
    textAlign: 'center',
  },
  title: {
    margin: '0 0 4px',
    fontSize: 22,
    fontWeight: 700,
    letterSpacing: 1,
    color: '#1a1a2e',
  },
  subtitle: {
    margin: '0 0 24px',
    fontSize: 13,
    color: '#666',
  },
  input: {
    display: 'block',
    width: '100%',
    padding: '10px 12px',
    marginBottom: 12,
    border: '1px solid #ddd',
    borderRadius: 4,
    fontSize: 14,
    boxSizing: 'border-box',
  },
  error: {
    color: '#e53e3e',
    fontSize: 13,
    margin: '0 0 12px',
  },
  button: {
    width: '100%',
    padding: '11px',
    background: '#1a1a2e',
    color: '#fff',
    border: 'none',
    borderRadius: 4,
    fontSize: 15,
    fontWeight: 600,
    cursor: 'pointer',
    marginTop: 4,
  },
};

export default Login;
