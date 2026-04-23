# Documentazione Sistema Metal Working - Gestione Preventivi

## 📋 Indice
1. [Panoramica](#panoramica)
2. [Architettura](#architettura)
3. [Funzionalità](#funzionalità)
4. [Database](#database)
5. [API Endpoints](#api-endpoints)
6. [Frontend](#frontend)
7. [Configurazione](#configurazione)
8. [Installazione e Avvio](#installazione-e-avvio)

---

## 🎯 Panoramica

Sistema completo per la gestione e analisi di preventivi PDF con:
- Estrazione automatica di informazioni tramite OpenAI (GPT-4o, GPT-4o-mini)
- Analisi di somiglianza tra preventivi
- Pianificazione temporale delle commesse con Gantt Chart
- Database SQLite per persistenza dati
- Interfaccia web React moderna

---

## 🏗️ Architettura

### Backend (Python/Flask)
- **Framework**: Flask 3.0+
- **Database**: SQLite (`preventivi.db`)
- **AI**: OpenAI API (GPT-4o, GPT-4o-mini, GPT-4-turbo)
- **PDF Processing**: PyPDF2 + pdf2image (visione diretta)
- **Similarity**: scikit-learn (TF-IDF + Cosine Similarity)

### Frontend (React)
- **Framework**: React
- **Styling**: CSS personalizzato (stile Metal Working)
- **Componenti principali**:
  - FileUpload: Caricamento PDF
  - PreventiviList: Lista preventivi con modal dettagli
  - SimilarityView: Analisi somiglianza
  - PlanningView: Gantt Chart pianificazione
  - ConfigPanel: Configurazione campi somiglianza

---

## ✨ Funzionalità

### 1. Caricamento e Estrazione PDF
- **Upload PDF**: Caricamento file PDF (max 16MB)
- **Estrazione Testo**: Estrazione testo con PyPDF2
- **Estrazione con Visione**: Conversione PDF→immagini e analisi con OpenAI Vision
- **Estrazione Strutturata**: Estrazione informazioni in JSON tramite OpenAI
- **Controllo Duplicati**: Verifica automatica se il preventivo esiste già (basato su nome file)
- **Riparazione JSON**: Sistema multi-livello per correggere JSON malformati
  - Parsing iniziale
  - Riparazione automatica
  - Correzione con ChatGPT
  - Fallback con regex

### 2. Analisi Somiglianza
- **Calcolo TF-IDF**: Analisi testuale dei preventivi
- **Cosine Similarity**: Calcolo somiglianza tra preventivi
- **Campi Configurabili**: Configurazione campi e pesi per il calcolo
- **Visualizzazione**: Lista preventivi ordinata per somiglianza

### 3. Pianificazione Temporale
- **Algoritmo di Scheduling**: Distribuzione automatica su N operatori
- **Fasi**:
  - **Recupero Materie Prime**: Fase iniziale (configurabile in giorni)
  - **Commessa**: Fase di lavorazione (configurabile in giorni)
- **Gantt Chart Aggregato**: Visualizzazione per operatore
  - Timeline orizzontale
  - Barre colorate per fase
  - Visualizzazione lavori in parallelo
  - Dettagli commesse

### 4. Database SQLite
- **Tabella `preventivi`**:
  - `id`: UUID univoco
  - `filename`: Nome file (UNIQUE)
  - `filepath`: Percorso file salvato
  - `upload_date`: Data caricamento
  - `extracted_info`: JSON estratto (TEXT)
  - `raw_text`: Testo grezzo PDF
  - `created_at`: Timestamp creazione

- **Tabella `planning_config`**:
  - `num_operatori`: Numero operatori disponibili
  - `tempo_commessa_giorni`: Durata commessa
  - `tempo_recupero_materie_giorni`: Durata recupero materie prime
  - `updated_at`: Timestamp aggiornamento

---

## 🔌 API Endpoints

### Upload e Gestione Preventivi

#### `POST /api/upload`
Carica un PDF preventivo e estrae informazioni.

**Request**:
- `file`: File PDF (multipart/form-data)

**Response**:
```json
{
  "success": true,
  "preventivo": {
    "id": "uuid",
    "filename": "nome_file.pdf",
    "filepath": "uploads/uuid_nome_file.pdf",
    "upload_date": "2026-02-24T15:18:54.607075",
    "extracted_info": { ... },
    "raw_text": "..."
  }
}
```

**Errori**:
- `409 Conflict`: Preventivo già presente (duplicato)
- `400 Bad Request`: File non valido o errore estrazione

#### `GET /api/preventivi`
Ottiene tutti i preventivi caricati.

**Response**:
```json
{
  "preventivi": [
    {
      "id": "uuid",
      "filename": "nome_file.pdf",
      "upload_date": "2026-02-24T15:18:54.607075",
      "extracted_info": { ... }
    }
  ]
}
```

#### `GET /api/preventivi/<preventivo_id>`
Ottiene un preventivo specifico.

#### `GET /api/preventivi/<preventivo_id>/similar`
Calcola preventivi simili a quello specificato.

**Response**:
```json
{
  "reference_id": "uuid",
  "similar_preventivi": [
    {
      "preventivo": { ... },
      "similarity_score": 0.85,
      "field_similarities": { ... }
    }
  ]
}
```

### Pianificazione

#### `GET /api/planning`
Ottiene la pianificazione temporale.

**Query Parameters**:
- `num_operatori` (opzionale): Numero operatori
- `tempo_commessa` (opzionale): Giorni per commessa
- `tempo_recupero` (opzionale): Giorni per recupero materie prime

**Response**:
```json
{
  "planning": [
    {
      "preventivo_id": "uuid",
      "filename": "nome_file.pdf",
      "operatore": 1,
      "cliente": "A.R.E. SRL",
      "totale": "6.928,00 €",
      "data_inizio_recupero": "2026-02-24T00:00:00",
      "data_fine_recupero": "2026-03-03T00:00:00",
      "data_inizio_commessa": "2026-03-03T00:00:00",
      "data_fine_commessa": "2026-04-02T00:00:00",
      "data_consegna": "2026-04-02T00:00:00",
      "tempo_recupero_giorni": 7,
      "tempo_commessa_giorni": 30
    }
  ],
  "config": {
    "num_operatori": 5,
    "tempo_commessa_giorni": 30,
    "tempo_recupero_materie_giorni": 7
  }
}
```

#### `GET /api/planning/config`
Ottiene la configurazione del planning.

#### `POST /api/planning/config`
Aggiorna la configurazione del planning.

**Request**:
```json
{
  "num_operatori": 5,
  "tempo_commessa_giorni": 30,
  "tempo_recupero_materie_giorni": 7
}
```

### Configurazione Somiglianza

#### `GET /api/config`
Ottiene la configurazione dei campi per la somiglianza.

#### `POST /api/config`
Aggiorna la configurazione dei campi per la somiglianza.

---

## 🎨 Frontend

### Componenti

#### FileUpload
- Caricamento file PDF
- Validazione formato e dimensione
- Indicatore di progresso
- Messaggi di successo/errore

#### PreventiviList
- Grid di card preventivi
- Informazioni principali (Cliente, Totale, Descrizione)
- Modal dettagli completo
- Visualizzazione ricorsiva di JSON annidati
- Selezione preventivo per analisi somiglianza

#### SimilarityView
- Preventivo di riferimento
- Lista preventivi simili ordinati
- Score di somiglianza con colori
- Dettagli per campo
- Espansione/collasso dettagli

#### PlanningView
- **Configurazione**: Parametri pianificazione
- **Gantt Chart Aggregato**:
  - Riga per ogni operatore
  - Timeline orizzontale con date
  - Barre colorate per fase (Recupero/Commessa)
  - Visualizzazione lavori in parallelo
  - Tooltip con date precise
- **Dettagli Commesse**: Grid con informazioni complete

#### ConfigPanel
- Configurazione campi per somiglianza
- Pesi configurabili
- Salvataggio configurazione

### Stile
- **Palette Colori**: Grigi scuri, blu scuro (stile Metal Working)
- **Design**: Professionale, industriale
- **Responsive**: Adattabile a diverse risoluzioni

---

## ⚙️ Configurazione

### Backend

#### File `.env`
```
OPENAI_API_KEY=sk-proj-...
```

#### Database
Il database SQLite viene creato automaticamente all'avvio:
- File: `backend/preventivi.db`
- Tabelle create automaticamente
- Configurazione default inserita

#### Configurazione Somiglianza
File: `backend/similarity_config.json`
```json
{
  "fields": [
    {
      "name": "cliente",
      "weight": 1.0,
      "enabled": true
    },
    {
      "name": "modello_struttura",
      "weight": 0.8,
      "enabled": true
    }
  ]
}
```

---

## 🚀 Installazione e Avvio

### Prerequisiti
- Python 3.8+
- Node.js 14+
- OpenAI API Key

### Backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate  # Windows
pip install -r requirements.txt
python app.py
```

Il backend si avvia su `http://localhost:5000`

### Frontend

```bash
cd frontend
npm install
npm start
```

Il frontend si avvia su `http://localhost:3000`

### Script Batch (Windows)

- `start_backend.bat`: Avvia il backend
- `start_frontend.bat`: Avvia il frontend

### Bulk Upload

```bash
cd backend
python bulk_upload.py
```

Carica tutti i PDF dalla cartella `2026_*` tramite API.

---

## 📊 Struttura Dati

### Preventivo (JSON estratto)
```json
{
  "cliente": {
    "nome": "A.R.E. SRL",
    "indirizzo": "VIA E. FERMI 29",
    "riferimento_cliente": "10637M ordine 1397"
  },
  "data": "20 02 26",
  "riferimento": "METAL WORKING SRL CO 2600334/16779",
  "modello_struttura": "F1",
  "tipologia": "Conferma d'ordine",
  "prezzo_totale_fornitura": "6.928,00 €",
  "caratteristiche_dimensioni": { ... },
  "condizioni_vendita": { ... },
  "dettaglio_foritura": { ... },
  "note": [ ... ]
}
```

### Planning Item
```json
{
  "preventivo_id": "uuid",
  "filename": "nome_file.pdf",
  "operatore": 1,
  "cliente": "A.R.E. SRL",
  "totale": "6.928,00 €",
  "data_inizio_recupero": "2026-02-24T00:00:00",
  "data_fine_recupero": "2026-03-03T00:00:00",
  "data_inizio_commessa": "2026-03-03T00:00:00",
  "data_fine_commessa": "2026-04-02T00:00:00",
  "data_consegna": "2026-04-02T00:00:00",
  "tempo_recupero_giorni": 7,
  "tempo_commessa_giorni": 30
}
```

---

## 🔧 Algoritmi

### Estrazione Informazioni
1. Estrazione testo PDF (PyPDF2)
2. Tentativo estrazione con visione (PDF→immagini→OpenAI Vision)
3. Se visione non disponibile, usa testo estratto
4. Estrazione strutturata con OpenAI (JSON)
5. Riparazione JSON multi-livello se necessario
6. Fallback con regex se tutto fallisce

### Calcolo Somiglianza
1. Estrazione testo da tutti i campi configurati
2. Calcolo TF-IDF per ogni campo
3. Calcolo Cosine Similarity
4. Media pesata dei punteggi
5. Ordinamento per somiglianza decrescente

### Pianificazione Temporale
1. Ordinamento preventivi per data upload
2. Assegnazione all'operatore disponibile prima
3. Calcolo date:
   - Inizio recupero materie prime
   - Fine recupero → Inizio commessa
   - Fine commessa → Consegna
4. Aggiornamento disponibilità operatore

---

## 📁 Struttura File

```
MetalWorkingPOC/
├── backend/
│   ├── app.py                 # Flask application
│   ├── similarity.py          # Calcolo somiglianza
│   ├── similarity_config.json # Configurazione somiglianza
│   ├── requirements.txt       # Dipendenze Python
│   ├── .env                   # API Key OpenAI
│   ├── bulk_upload.py         # Script bulk upload
│   ├── preventivi.db          # Database SQLite
│   ├── uploads/               # PDF caricati
│   └── data/                  # JSON preventivi (backup)
├── frontend/
│   ├── src/
│   │   ├── App.js             # Componente principale
│   │   ├── components/
│   │   │   ├── FileUpload.js
│   │   │   ├── PreventiviList.js
│   │   │   ├── SimilarityView.js
│   │   │   ├── PlanningView.js
│   │   │   └── ConfigPanel.js
│   │   └── ...
│   └── package.json
└── README.md
```

---

## 🛠️ Tecnologie Utilizzate

### Backend
- **Flask 3.0+**: Web framework
- **SQLite3**: Database
- **OpenAI 1.3+**: AI per estrazione informazioni
- **PyPDF2 3.0+**: Estrazione testo PDF
- **pdf2image 1.16+**: Conversione PDF→immagini
- **scikit-learn 1.3+**: Machine learning per somiglianza
- **numpy 1.24+**: Calcoli numerici

### Frontend
- **React**: Framework UI
- **CSS3**: Styling personalizzato

---

## 📝 Note Tecniche

### Gestione Errori
- **Quota OpenAI**: Rilevamento e messaggio esplicito
- **Modelli non disponibili**: Fallback automatico tra modelli
- **JSON malformato**: Riparazione multi-livello
- **File duplicati**: Controllo preventivo e errore 409

### Performance
- **Estrazione Visione**: Limitata a prime 3 pagine per costi
- **Similarity**: Calcolo efficiente con TF-IDF
- **Planning**: Algoritmo O(n) per assegnazione operatori

### Sicurezza
- **File Upload**: Validazione formato e dimensione
- **API Key**: Caricamento da `.env` (non committato)
- **CORS**: Abilitato per sviluppo locale

---

## 🔄 Workflow Tipico

1. **Caricamento PDF**:
   - Upload file → Estrazione testo/visione → Estrazione JSON → Salvataggio DB

2. **Analisi Somiglianza**:
   - Selezione preventivo → Calcolo somiglianza → Visualizzazione risultati

3. **Pianificazione**:
   - Configurazione parametri → Calcolo planning → Visualizzazione Gantt

---

## 📈 Stato Attuale

✅ **Completato**:
- Upload e estrazione PDF
- Database SQLite
- Controllo duplicati
- Analisi somiglianza
- Pianificazione temporale
- Gantt Chart aggregato
- Frontend completo
- Stile Metal Working

🔄 **In Sviluppo**:
- Miglioramenti estrazione informazioni
- Ottimizzazioni performance

---

## 📞 Supporto

Per problemi o domande:
- Verificare i log del backend
- Controllare la console del browser
- Verificare configurazione OpenAI API Key

---

**Ultimo aggiornamento**: 2026-02-24
**Versione**: 1.0.0
