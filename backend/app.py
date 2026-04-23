from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import os
import json

import subprocess
import sys
import threading

# Fix encoding su Windows (emoji nelle risposte Claude)
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ('utf-8', 'utf-8-sig'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
if sys.stderr.encoding and sys.stderr.encoding.lower() not in ('utf-8', 'utf-8-sig'):
    try:
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
import hashlib
import re
import base64
from werkzeug.utils import secure_filename
import PyPDF2
from google import genai
from google.genai import types as genai_types
from dotenv import load_dotenv
import psycopg2
import psycopg2.extras
from datetime import datetime, timedelta, timezone
import uuid
from similarity import calculate_similarity, load_config, save_config
import numpy as np
from ml_model import (
    CHARTS_DIR,
    TARGETS,
    clear_ml_artifacts,
    load_metrics,
    load_model,
    predict as ml_predict,
    _invalidate_metrics_cache,
)
from commesse_ore import (
    default_xlsx_path,
    import_to_sqlite,
    load_rows_from_xlsx,
    match_preventivi_filenames,
    rows_grouped_by_cliente_norm,
)
from offerta_commessa_mapping import (
    default_mapping_xlsx_path,
    import_mapping_to_sqlite,
    load_rows_from_mapping_xlsx,
)

# Carica il file .env dalla directory del backend
base_dir = os.path.dirname(os.path.abspath(__file__))
repo_root = os.path.dirname(base_dir)
env_path = os.path.join(base_dir, '.env')
env_path_abs = os.path.abspath(env_path)

# Carica variabili da .env (backend e root repo); poi override da variabili di sistema
load_dotenv(dotenv_path=env_path_abs, override=False)
load_dotenv(dotenv_path=os.path.join(repo_root, '.env'), override=False)

gemini_api_key = os.getenv('GEMINI_API_KEY')

if gemini_api_key:
    print(f"OK: GEMINI_API_KEY caricata (lunghezza: {len(gemini_api_key)} caratteri)")
else:
    print("ATTENZIONE: GEMINI_API_KEY non trovata (estrazione PDF disabilitata fino a configurazione)")
    print(f"Percorso .env cercato: {env_path_abs}")

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=False)

@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization'
    response.headers['Access-Control-Allow-Methods'] = 'GET,POST,PUT,DELETE,OPTIONS'
    return response

@app.errorhandler(500)
def internal_error(e):
    response = jsonify({'error': f'Errore interno del server: {str(e)}'})
    response.status_code = 500
    return response

# Configurazione
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'pdf'}
MAX_FILE_SIZE = 16 * 1024 * 1024  # 16MB

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE

# Cartella JSON (sempre sotto backend/, indipendente dalla cwd)
DATA_DIR = os.path.join(base_dir, "data")

# Crea cartelle necessarie
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(os.path.join(base_dir, 'ml_artifacts'), exist_ok=True)

# Database PostgreSQL
DATABASE_URL = os.environ.get('DATABASE_URL', '')

def get_db_connection():
    """Ottiene una connessione al database PostgreSQL."""
    conn = psycopg2.connect(
        DATABASE_URL,
        connection_factory=psycopg2.extras.RealDictConnection,
    )
    return conn


def init_db():
    """Inizializza il database PostgreSQL."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS preventivi (
            id TEXT PRIMARY KEY,
            filename TEXT UNIQUE NOT NULL,
            filepath TEXT NOT NULL,
            upload_date TEXT NOT NULL,
            extracted_info TEXT,
            raw_text TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS planning_config (
            id SERIAL PRIMARY KEY,
            num_operatori INTEGER DEFAULT 5,
            tempo_commessa_giorni INTEGER DEFAULT 30,
            tempo_recupero_materie_giorni INTEGER DEFAULT 7,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('SELECT COUNT(*) AS cnt FROM planning_config')
    if cursor.fetchone()['cnt'] == 0:
        cursor.execute('''
            INSERT INTO planning_config (num_operatori, tempo_commessa_giorni, tempo_recupero_materie_giorni)
            VALUES (5, 30, 7)
        ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS commesse_ore (
            nr_commessa TEXT PRIMARY KEY,
            cliente TEXT NOT NULL,
            cliente_norm TEXT NOT NULL,
            ore_imba REAL,
            ore_nest REAL,
            ore_pieg REAL,
            ore_prod REAL,
            ore_prog REAL,
            ore_sald REAL,
            ore_totale REAL,
            source_file TEXT,
            updated_at TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS offerta_commessa_map (
            id SERIAL PRIMARY KEY,
            nr_preventivo INTEGER NOT NULL,
            nr_commessa TEXT NOT NULL,
            ragione_sociale TEXT,
            riferimento_offerta TEXT,
            data_doc TEXT,
            source_file TEXT,
            updated_at TEXT
        )
    ''')
    cursor.execute(
        'CREATE INDEX IF NOT EXISTS idx_ocm_preventivo ON offerta_commessa_map(nr_preventivo)'
    )

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS fattore_af_cache (
            preventivo_id TEXT PRIMARY KEY,
            dims_fingerprint TEXT NOT NULL,
            model_fingerprint TEXT NOT NULL,
            result_json TEXT NOT NULL,
            updated_at TEXT
        )
    ''')

    conn.commit()
    conn.close()
    print("Database PostgreSQL inizializzato.")


def _migrate_preventivi_updated_at():
    """Aggiunge updated_at se manca; backfill da upload_date."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'preventivi' AND table_schema = 'public'"
    )
    cols = [r['column_name'] for r in cursor.fetchall()]
    if "updated_at" not in cols:
        cursor.execute("ALTER TABLE preventivi ADD COLUMN IF NOT EXISTS updated_at TEXT")
    cursor.execute(
        "UPDATE preventivi SET updated_at = upload_date WHERE updated_at IS NULL OR TRIM(COALESCE(updated_at, '')) = ''"
    )
    conn.commit()
    conn.close()


# Inizializza il database all'avvio
init_db()
_migrate_preventivi_updated_at()

_ML_MODEL = load_model()
_ML_METRICS = load_metrics()
if _ML_MODEL is not None and _ML_METRICS is not None:
    print(f"OK: Modello ML caricato. R²={_ML_METRICS.get('r2', '?')}")
else:
    print("ATTENZIONE: Modello ML non trovato. Eseguire: python ml_model.py --data <xlsx>")

_training_lock = threading.Lock()
_training_running = False
_training_message = ""
_training_error = None
_training_exit_code = None
_training_log_tail = ""


def _training_worker(mode: str):
    global _training_running, _training_message, _training_error, _training_exit_code, _training_log_tail
    try:
        _training_message = "Rimozione modelli e metriche precedenti..."
        clear_ml_artifacts(base_dir)
        _invalidate_metrics_cache()

        train_script = os.path.join(repo_root, "train_models.py")
        if not os.path.isfile(train_script):
            _training_error = f"Script non trovato: {train_script}"
            _training_exit_code = -1
            return

        cmd = [sys.executable, train_script]
        if mode == "legacy_only":
            cmd.append("--legacy-only")
        elif mode == "from_db":
            cmd.append("--from-db")

        _training_message = "Training in corso (può richiedere alcuni minuti)..."
        r = subprocess.run(
            cmd,
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=7200,
        )
        out = (r.stdout or "") + "\n" + (r.stderr or "")
        _training_log_tail = out[-8000:]
        _training_exit_code = r.returncode
        if r.returncode != 0:
            _training_error = (r.stderr or r.stdout or "Training fallito").strip()[-3000:]
        else:
            _training_message = "Training completato."
            _invalidate_metrics_cache()
    except subprocess.TimeoutExpired:
        _training_error = "Timeout training (oltre 2 ore)."
        _training_exit_code = -1
    except Exception as e:
        _training_error = str(e)
        _training_exit_code = -1
    finally:
        with _training_lock:
            _training_running = False


def _start_ml_training(mode: str) -> bool:
    global _training_running, _training_message, _training_error, _training_exit_code, _training_log_tail
    with _training_lock:
        if _training_running:
            return False
        _training_running = True
        _training_message = "Avvio..."
        _training_error = None
        _training_exit_code = None
        _training_log_tail = ""
    t = threading.Thread(target=_training_worker, args=(mode,), daemon=True)
    t.start()
    return True


def _extracted_info_valorizzato_per_af(info: dict | None, raw: str | None) -> bool:
    """
    True se extracted_info contiene un'estrazione utile (non solo import bulk o solo errore API).
    Il calcolo AF viene eseguito solo in questo caso.
    """
    if raw is None or not str(raw).strip():
        return False
    if not info or not isinstance(info, dict):
        return False
    if info.get("import_bulk") is True:
        return False
    keys = set(info.keys())
    noise = {"note", "import_bulk", "extraction_method"}
    # Solo errore di estrazione / chiave mancante
    if keys <= {"error"} or keys <= {"error", "raw_text"}:
        return False
    if not (keys - noise):
        return False
    return True


def _parse_first_float(val):
    """Primo numero in una stringa (es. '9180 mm') o conversione da numerico."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        m = re.search(r'\d+(?:[.,]\d+)?', val.replace('\xa0', ' '))
        if m:
            try:
                return float(m.group(0).replace(',', '.'))
            except ValueError:
                return None
    return None


def _parse_two_lati_pianta(val):
    """
    Coppia (lato_a, lato_b) da dict lunghezza/larghezza o stringhe tipo '1470 x 1630', '1330 x 1320 mm'.
    """
    if val is None:
        return None, None
    if isinstance(val, dict):
        a = val.get('lunghezza') or val.get('larghezza')
        b = val.get('larghezza') or val.get('lunghezza')
        if a is not None and b is not None:
            try:
                return float(a), float(b)
            except (TypeError, ValueError):
                pass
        return None, None
    if isinstance(val, str):
        nums = re.findall(r'\d+(?:[.,]\d+)?', val.replace(',', '.'))
        if len(nums) >= 2:
            try:
                return float(nums[0].replace(',', '.')), float(nums[1].replace(',', '.'))
            except ValueError:
                pass
    return None, None


def _extract_dims(info):
    """
    Estrae peso, lato_a, lato_b, altezza da extracted_info di un preventivo.
    Ritorna dict con 4 chiavi float, oppure None se i dati sono insufficienti.

    Supporta varianti di estrazione: caratteristiche vs caratteristiche_dimensioni,
    dimensioni_pianta_mm / dimensioni_pianta oltre a dimensioni_in_pianta_mm,
    altezza come stringa o numeri in più chiavi.
    """
    dims = info.get('caratteristiche_dimensioni') or info.get('caratteristiche') or {}
    if not isinstance(dims, dict):
        dims = {}

    peso_raw = info.get('peso_stimato', {})
    peso = None
    if isinstance(peso_raw, dict):
        peso = peso_raw.get('struttura_kg')
        if peso is None:
            peso = peso_raw.get('totale_kg')
        if peso is None and peso_raw.get('struttura_kg') is not None and peso_raw.get(
            'tamponamenti_kg'
        ) is not None:
            try:
                peso = float(peso_raw['struttura_kg']) + float(peso_raw['tamponamenti_kg'])
            except (TypeError, ValueError):
                pass
    if not peso:
        peso = info.get('peso') or info.get('peso_kg')
    if isinstance(peso, dict):
        peso = peso.get('struttura_kg') or peso.get('valore') or peso.get('kg')
    if isinstance(peso, str):
        peso = _parse_first_float(peso)

    dp = dims.get('dimensioni_in_pianta_mm')
    if dp is None:
        dp = dims.get('dimensioni_pianta_mm')
    if dp is None:
        dp = dims.get('dimensioni_pianta')

    lato_a, lato_b = _parse_two_lati_pianta(dp)

    altezza = (
        dims.get('h_totale_struttura_mm')
        or dims.get('altezza_totale_struttura_mm')
        or dims.get('altezza_mm')
        or dims.get('h_netto_mm')
        or dims.get('altezza_totale_struttura')
        or dims.get('altezza')
    )
    altezza = _parse_first_float(altezza)

    if not all([peso, lato_a is not None, lato_b is not None, altezza]):
        return None

    return {
        'peso': float(peso),
        'lato_a': float(lato_a),
        'lato_b': float(lato_b),
        'altezza': float(altezza),
    }




def _ml_metrics_fingerprint():
    """Cambia dopo ogni training: invalida cache AF senza ricalcolare tutto a mano."""
    p = os.path.join(base_dir, 'ml_metrics.json')
    if not os.path.isfile(p):
        return 'no_metrics'
    return str(int(os.path.getmtime(p)))


def _dims_fingerprint(dims, raw_extracted):
    """
    Impronta degli input usati per ml_predict. Se mancano dimensioni,
    dipende dall'estrazione completa così un re-estrazione aggiorna la cache.
    """
    if dims is None:
        s = raw_extracted if raw_extracted else ''
        return 'no_dims:' + hashlib.sha256(s.encode('utf-8')).hexdigest()
    norm = {}
    for k in ('peso', 'lato_a', 'lato_b', 'altezza', 'portata'):
        if k not in dims or dims[k] is None:
            continue
        norm[k] = round(float(dims[k]), 6)
    return json.dumps(norm, sort_keys=True, ensure_ascii=False)


def _fattore_af_cache_try_get(preventivo_id, dims_fp, model_fp):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        'SELECT dims_fingerprint, model_fingerprint, result_json FROM fattore_af_cache WHERE preventivo_id = %s',
        (preventivo_id,),
    )
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    if row['dims_fingerprint'] == dims_fp and row['model_fingerprint'] == model_fp:
        return json.loads(row['result_json'])
    return None


def _fattore_af_cache_save(preventivo_id, dims_fp, model_fp, payload):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        '''
        INSERT INTO fattore_af_cache
        (preventivo_id, dims_fingerprint, model_fingerprint, result_json, updated_at)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (preventivo_id) DO UPDATE SET
            dims_fingerprint = EXCLUDED.dims_fingerprint,
            model_fingerprint = EXCLUDED.model_fingerprint,
            result_json = EXCLUDED.result_json,
            updated_at = EXCLUDED.updated_at
        ''',
        (
            preventivo_id,
            dims_fp,
            model_fp,
            json.dumps(payload, ensure_ascii=False),
            datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        ),
    )
    conn.commit()
    conn.close()


def check_preventivo_exists(filename):
    """Verifica se un preventivo con lo stesso nome esiste già"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id, filename, upload_date FROM preventivi WHERE filename = %s', (filename,))
    result = cursor.fetchone()
    conn.close()
    return dict(result) if result else None

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_text_from_pdf(pdf_path):
    """Estrae il testo da un file PDF"""
    text = ""
    try:
        with open(pdf_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            for page in pdf_reader.pages:
                text += page.extract_text() + "\n"
    except Exception as e:
        print(f"Errore nell'estrazione del testo: {e}")
    return text

def add_missing_commas(json_string, error_line, error_col):
    """Tenta di aggiungere virgole mancanti nel JSON"""
    import re
    
    # Converti posizione in caratteri
    lines = json_string.split('\n')
    char_pos = sum(len(line) + 1 for line in lines[:error_line - 1]) + error_col - 1
    
    if char_pos < len(json_string):
        # Prendi il contesto intorno all'errore
        start = max(0, char_pos - 200)
        end = min(len(json_string), char_pos + 200)
        context = json_string[start:end]
        
        # Pattern: cerca "key": value seguito da "key" senza virgola
        # Pattern 1: "key": value "key" (virgola mancante tra valori)
        pattern1 = r'("[\w_]+"\s*:\s*[^,}\]]+)\s+("[\w_]+")'
        if re.search(pattern1, context):
            fixed_context = re.sub(pattern1, r'\1, \2', context)
            return json_string[:start] + fixed_context + json_string[end:]
        
        # Pattern 2: } "key" (virgola mancante dopo oggetto chiuso)
        pattern2 = r'(\})\s+("[\w_]+")'
        if re.search(pattern2, context):
            fixed_context = re.sub(pattern2, r'\1, \2', context)
            return json_string[:start] + fixed_context + json_string[end:]
        
        # Pattern 3: ] "key" (virgola mancante dopo array chiuso)
        pattern3 = r'(\])\s+("[\w_]+")'
        if re.search(pattern3, context):
            fixed_context = re.sub(pattern3, r'\1, \2', context)
            return json_string[:start] + fixed_context + json_string[end:]
    
    return json_string

def ask_gemini_to_fix_json(broken_json, api_key):
    """Chiede a Gemini di correggere un JSON malformato."""
    try:
        error_context = broken_json[:4000] if len(broken_json) > 4000 else broken_json
        fix_prompt = f"""Il seguente JSON è malformato. Correggilo e restituisci SOLO il JSON valido, senza markdown né spiegazioni.

JSON da correggere:
{error_context}"""

        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model='gemini-2.0-flash',
            contents=fix_prompt,
            config=genai_types.GenerateContentConfig(
                system_instruction=(
                    "Sei un esperto nel correggere JSON malformati. "
                    "Restituisci SOLO il JSON corretto, senza markdown, senza spiegazioni."
                ),
            ),
        )
        fixed_content = response.text.strip()

        if fixed_content.startswith("```json"):
            fixed_content = fixed_content[7:]
        elif fixed_content.startswith("```"):
            fixed_content = fixed_content[3:]
        if fixed_content.endswith("```"):
            fixed_content = fixed_content[:-3]
        fixed_content = fixed_content.strip()

        json_start = fixed_content.find('{')
        json_end = fixed_content.rfind('}') + 1
        if json_start != -1 and json_end > json_start:
            fixed_content = fixed_content[json_start:json_end]

        json.loads(fixed_content)
        print("✅ JSON corretto con successo da Gemini")
        return fixed_content

    except json.JSONDecodeError as e:
        print(f"JSON corretto da Gemini ancora non valido: {e}")
        return None
    except Exception as e:
        print(f"Errore nella correzione JSON con Gemini: {e}")
        return None

def repair_json(json_string):
    """Tenta di riparare un JSON malformato"""
    import re
    
    # Rimuove caratteri di controllo non validi in JSON
    cleaned = ''.join(char for char in json_string if ord(char) >= 32 or char in '\n\r\t')
    
    # Sostituisce caratteri unicode problematici
    replacements = {
        '\u201c': '"',  # Left double quotation mark
        '\u201d': '"',  # Right double quotation mark
        '\u2018': "'",  # Left single quotation mark
        '\u2019': "'",  # Right single quotation mark
        '\u2013': '-',  # En dash
        '\u2014': '-',  # Em dash
        '\u20ac': 'EUR',  # Euro sign
        '\u00a0': ' ',  # Non-breaking space
    }
    for old, new in replacements.items():
        cleaned = cleaned.replace(old, new)
    
    # Rimuove trailing commas prima di } o ]
    cleaned = re.sub(r',\s*}', '}', cleaned)
    cleaned = re.sub(r',\s*]', ']', cleaned)
    
    # Prova a trovare e estrarre solo la parte JSON valida
    # Cerca il primo { e l'ultimo }
    first_brace = cleaned.find('{')
    last_brace = cleaned.rfind('}')
    
    if first_brace != -1 and last_brace > first_brace:
        # Estrae solo la parte tra le parentesi graffe
        json_part = cleaned[first_brace:last_brace + 1]
        
        # Prova a bilanciare le parentesi se necessario
        open_braces = json_part.count('{')
        close_braces = json_part.count('}')
        if open_braces > close_braces:
            json_part += '}' * (open_braces - close_braces)
        elif close_braces > open_braces:
            json_part = '{' * (close_braces - open_braces) + json_part
        
        # Rimuove virgole duplicate
        json_part = re.sub(r',\s*,+', ',', json_part)
        
        # Rimuove virgole prima di } o ] (trailing commas)
        json_part = re.sub(r',(\s*[}\]])', r'\1', json_part)
        
        # Tenta di aggiungere virgole mancanti tra chiavi/valori
        # Pattern: "key": value seguito da "key" (senza virgola)
        json_part = re.sub(r'("\s*:\s*[^,}\]]+)\s*"', r'\1, "', json_part)
        # Rimuove virgole duplicate che potrebbero essere state create
        json_part = re.sub(r',\s*,+', ',', json_part)
        # Rimuove virgole prima di } o ] che potrebbero essere state aggiunte
        json_part = re.sub(r',(\s*[}\]])', r'\1', json_part)
        
        return json_part
    
    return cleaned

def extract_fallback_info(raw_text, ai_response):
    """Estrae informazioni di base dal testo quando il JSON non è valido"""
    import re
    info = {}
    
    # Cliente
    cliente_match = re.search(r'CLIENTE:\s*([A-Z][A-Z\s\.&]+)', raw_text, re.IGNORECASE)
    if cliente_match:
        info['cliente'] = cliente_match.group(1).strip()
    
    # Numero preventivo
    preventivo_match = re.search(r'(?:CO|preventivo|rif\.?)\s*(\d+[/-]\d+)', raw_text, re.IGNORECASE)
    if preventivo_match:
        info['numero_preventivo'] = preventivo_match.group(1).strip()
    
    # Totale
    totale_match = re.search(r'(?:TOTALE|PREZZO\s+TOTALE|prezzo\s+relativo).*?(\d+[.,]\d+)\s*[€EUR]', raw_text, re.IGNORECASE | re.DOTALL)
    if totale_match:
        info['totale'] = totale_match.group(1).strip().replace(',', '.')
    
    # Data
    data_match = re.search(r'DATA\s+(\d{2}\s+\d{2}\s+\d{2})', raw_text, re.IGNORECASE)
    if data_match:
        info['data'] = data_match.group(1).strip()
    
    # Descrizione lavori
    desc_match = re.search(r'(?:DESCRIZIONE|MODELLO\s+STRUTTURA|TIPOLOGIA)\s*:?\s*([^\n]+)', raw_text, re.IGNORECASE)
    if desc_match:
        info['descrizione_lavori'] = desc_match.group(1).strip()[:200]
    
    info['extraction_method'] = 'fallback_regex'
    return info

def pdf_to_images(pdf_path):
    """Converte un PDF in immagini (una per pagina)"""
    try:
        from pdf2image import convert_from_path
        images = convert_from_path(pdf_path, dpi=200)
        return images
    except ImportError:
        print("⚠️  pdf2image non installato. Installa con: pip install pdf2image")
        print("   Su Windows potrebbe servire anche Poppler: https://github.com/oschwartz10612/poppler-windows/releases/")
        return None
    except Exception as e:
        print(f"Errore nella conversione PDF->immagini: {e}")
        return None

def image_to_base64(image):
    """Converte un'immagine PIL in data URL base64 (legacy)."""
    import io
    buffered = io.BytesIO()
    image.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode()
    return f"data:image/png;base64,{img_str}"


def image_to_base64_raw_png(image):
    """Base64 puro PNG (legacy)."""
    import io
    buffered = io.BytesIO()
    image.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode()


def _pil_to_bytes(image):
    """Converte PIL Image in bytes PNG."""
    import io
    buffered = io.BytesIO()
    image.save(buffered, format="PNG")
    return buffered.getvalue()


def extract_info_with_gemini_vision(pdf_path, api_key):
    """Estrae informazioni con Gemini (vision) da PDF convertito in immagini."""
    try:
        print("📄 Convertendo PDF in immagini per analisi visione (Gemini)...")
        images = pdf_to_images(pdf_path)

        if not images:
            print("⚠️  Impossibile convertire PDF in immagini, uso estrazione testo")
            return None

        images_to_process = images[:3]
        print(f"👁️  Analizzando {len(images_to_process)} pagine con Gemini vision...")

        prompt = """Analizza questo preventivo e estrai tutte le informazioni rilevanti in formato JSON valido.

REGOLE STRETTE PER IL JSON:
1. Usa SOLO virgolette doppie (") per le stringhe
2. Aggiungi SEMPRE una virgola tra coppie chiave-valore, tranne l'ultima prima di }
3. Non usare virgole finali (trailing commas) prima di } o ]
4. Se un campo non è presente, usa null
5. Restituisci SOLO il JSON, senza markdown, senza spiegazioni

Cerca: cliente, data, numero preventivo, modello struttura, descrizione lavori,
caratteristiche e dimensioni, materiali, prezzi, condizioni, note.

Restituisci SOLO il JSON valido."""

        client = genai.Client(api_key=api_key)
        content_parts = [prompt] + [
            genai_types.Part.from_bytes(data=_pil_to_bytes(img), mime_type='image/png')
            for img in images_to_process
        ]
        for attempt in range(3):
            try:
                response = client.models.generate_content(
                    model='gemini-2.0-flash',
                    contents=content_parts,
                )
                print("✅ Estrazione con visione Gemini riuscita")
                return response.text
            except Exception as e:
                error_str = str(e)
                if "429" in error_str or "quota" in error_str.lower():
                    wait = 20 * (attempt + 1)
                    print(f"⏳ Quota Gemini Vision, attendo {wait}s (tentativo {attempt+1}/3)...")
                    import time as _time
                    _time.sleep(wait)
                else:
                    print(f"Errore visione Gemini: {e}")
                    return None
        return None

    except Exception as e:
        print(f"Errore nell'estrazione con visione Gemini: {e}")
        return None


def extract_info_with_gemini(text, pdf_path=None):
    """Estrae informazioni strutturate dal testo usando Google Gemini (free tier)."""
    try:
        api_key = os.environ.get('GEMINI_API_KEY') or os.getenv('GEMINI_API_KEY')

        if not api_key:
            return {
                "error": (
                    "GEMINI_API_KEY mancante. In backend/.env imposta GEMINI_API_KEY= "
                    "con la chiave da https://aistudio.google.com/app/apikey"
                ),
                "raw_text": text,
            }

        # Prima strategia: estrazione da testo (1 chiamata sola, più stabile)
        # La visione viene usata solo se il testo è troppo corto (<200 caratteri)
        if pdf_path and len(text.strip()) < 200:
            print("Testo estratto insufficiente, tentativo con visione Gemini...")
            vision_result = extract_info_with_gemini_vision(pdf_path, api_key)
            if vision_result:
                try:
                    parsed = json.loads(vision_result)
                    print("✅ Estrazione con visione completata con successo!")
                    return parsed
                except json.JSONDecodeError:
                    cleaned = repair_json(vision_result)
                    try:
                        return json.loads(cleaned)
                    except Exception:
                        print("Riparazione visione fallita, continuo con testo...")
        else:
            print("Estrazione da testo con Gemini...")

        text_limited = text[:80000] if len(text) > 80000 else text

        prompt = f"""Estrai tutte le informazioni rilevanti da questo preventivo e restituiscile in formato JSON valido.

REGOLE STRETTE PER IL JSON:
1. Usa SOLO virgolette doppie (") per le stringhe
2. Aggiungi SEMPRE una virgola tra coppie chiave-valore, tranne l'ultima prima di }}
3. Non usare virgole finali (trailing commas) prima di }} o ]
4. Se un campo non è presente, usa null
5. Restituisci SOLO il JSON, senza markdown, senza testo prima o dopo

Cerca: cliente, data, numero preventivo, modello struttura, descrizione lavori,
caratteristiche e dimensioni, materiali, prezzi, condizioni, note.

Testo del preventivo:
{text_limited}

Restituisci SOLO il JSON valido."""

        import requests as _requests
        last_error = None
        for api_ver, model_name in [
            ('v1', 'gemini-1.5-flash'),
            ('v1beta', 'gemini-2.0-flash'),
            ('v1', 'gemini-1.5-flash-8b'),
            ('v1beta', 'gemini-1.5-flash'),
        ]:
            url = f'https://generativelanguage.googleapis.com/{api_ver}/models/{model_name}:generateContent'
            payload = {
                'system_instruction': {'parts': [{'text': 'Sei un assistente che estrae informazioni strutturate da preventivi. Restituisci SEMPRE e SOLO JSON valido, senza testo aggiuntivo.'}]},
                'contents': [{'parts': [{'text': prompt}]}],
            }
            try:
                resp = _requests.post(url, params={'key': api_key}, json=payload, timeout=55)
                if resp.status_code == 200:
                    rj = resp.json()
                    content = rj['candidates'][0]['content']['parts'][0]['text'].strip()
                    print(f"✅ Estrazione con {api_ver}/{model_name} completata")
                    last_error = None
                    break
                else:
                    last_error = f"{resp.status_code} {resp.text[:150]}"
                    print(f"⚠️ {api_ver}/{model_name}: {last_error}")
                    continue
            except Exception as e:
                last_error = str(e)
                print(f"⚠️ {api_ver}/{model_name} eccezione: {last_error[:100]}")
                continue
        if last_error:
            return {
                "error": f"Tutti i modelli Gemini hanno fallito. Ultimo errore: {last_error[:300]}",
                "error_code": "quota_exceeded",
                "raw_text": text,
            }

        if content.startswith("```json"):
            content = content[7:]
        elif content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        json_start = content.find('{')
        json_end = content.rfind('}') + 1
        if json_start != -1 and json_end > json_start:
            content = content[json_start:json_end]

        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            print(f"Errore parsing JSON iniziale: {e}")
            cleaned = repair_json(content)
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError as e2:
                print(f"Errore parsing JSON dopo riparazione: {e2}")
                try:
                    if hasattr(e2, 'pos') and e2.pos > 0:
                        partial_json = cleaned[:e2.pos]
                        open_count = partial_json.count('{') - partial_json.count('}')
                        if open_count > 0:
                            partial_json += '}' * open_count
                        try:
                            return json.loads(partial_json)
                        except Exception:
                            pass
                except Exception:
                    pass

                print("Tentativo correzione JSON con Gemini...")
                corrected_json = ask_gemini_to_fix_json(cleaned, api_key)
                if corrected_json:
                    try:
                        return json.loads(corrected_json)
                    except json.JSONDecodeError as e3:
                        print(f"JSON corretto da Gemini ancora non valido: {e3}")

                print("Usando estrazione fallback con regex")
                return extract_fallback_info(text, content)
    except Exception as e:
        print(f"Errore nell'estrazione con Gemini: {e}")
        return {"error": str(e), "raw_text": text}


# Alias retro-compatibilità interna
extract_info_with_claude = extract_info_with_gemini
extract_info_with_openai = extract_info_with_gemini

@app.route('/')
def index():
    """Backend API: nessuna pagina HTML; usa gli endpoint sotto /api/."""
    return jsonify({
        'service': 'MetalWorkingPOC backend',
        'status': 'ok',
        'endpoints': {
            'upload': 'POST /api/upload',
            'preventivi_list': 'GET /api/preventivi',
            'preventivo': 'GET /api/preventivi/<id>',
            'similar': 'GET /api/preventivi/<id>/similar',
            'config': 'GET|POST /api/config',
            'planning': 'GET /api/planning',
            'planning_config': 'GET|POST /api/planning/config',
            'ml_stats': 'GET /api/ml/stats',
            'ml_charts': 'GET /api/ml/charts/<name>',
            'ml_predict': 'POST /api/ml/predict',
            'ml_similar': 'GET /api/ml/similar',
            'ml_train': 'POST /api/ml/train',
            'ml_training_status': 'GET /api/ml/training-status',
        },
    })

@app.route('/api/upload', methods=['POST'])
def upload_file():
    """Endpoint per caricare un PDF preventivo"""
    if 'file' not in request.files:
        return jsonify({'error': 'Nessun file caricato'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Nessun file selezionato'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'error': 'Formato file non supportato. Solo PDF.'}), 400
    
    try:
        # Salva il file
        filename = secure_filename(file.filename)
        
        # Se il preventivo esiste già, elimina il vecchio e riprocessa
        existing = check_preventivo_exists(filename)
        if existing:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('DELETE FROM preventivi WHERE id = %s', (existing['id'],))
            conn.commit()
            conn.close()
        
        unique_filename = f"{uuid.uuid4()}_{filename}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        file.save(filepath)
        
        # Estrae il testo dal PDF (come fallback)
        text = extract_text_from_pdf(filepath)
        
        # Estrae informazioni con Claude (vision se PDF->immagini ok, altrimenti testo)
        extracted_info = extract_info_with_claude(text, pdf_path=filepath)
        
        # Se l'estrazione fallisce completamente, usa il testo estratto come fallback
        if not extracted_info or 'error' in extracted_info:
            if not text.strip():
                return jsonify({'error': 'Impossibile estrarre informazioni dal PDF'}), 400
        
        # Crea il documento preventivo
        now_iso = datetime.now().isoformat()
        preventivo = {
            'id': str(uuid.uuid4()),
            'filename': filename,
            'filepath': filepath,
            'upload_date': now_iso,
            'updated_at': now_iso,
            'extracted_info': extracted_info,
            'raw_text': text
        }
        
        # Salva il preventivo nel database
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO preventivi (id, filename, filepath, upload_date, extracted_info, raw_text, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        ''', (
            preventivo['id'],
            preventivo['filename'],
            preventivo['filepath'],
            preventivo['upload_date'],
            json.dumps(preventivo['extracted_info'], ensure_ascii=False),
            preventivo['raw_text'],
            preventivo['upload_date'],
        ))
        conn.commit()
        conn.close()
        
        # Risposta estrazione Anthropic (JSON strutturato) — copia dedicata
        gemini_payload = {
            "preventivo_id": preventivo["id"],
            "filename": preventivo["filename"],
            "saved_at": now_iso,
            "source": "gemini_ai",
            "extracted_info": extracted_info,
        }
        gemini_file = os.path.join(DATA_DIR, f"{preventivo['id']}_gemini.json")
        with open(gemini_file, "w", encoding="utf-8") as f:
            json.dump(gemini_payload, f, ensure_ascii=False, indent=2)

        # Snapshot completo preventivo (compatibilità)
        data_file = os.path.join(DATA_DIR, f"{preventivo['id']}.json")
        with open(data_file, 'w', encoding='utf-8') as f:
            json.dump(preventivo, f, ensure_ascii=False, indent=2)
        
        return jsonify({
            'success': True,
            'preventivo': preventivo
        }), 200
        
    except Exception as e:
        return jsonify({'error': f'Errore durante il caricamento: {str(e)}'}), 500

@app.route('/api/preventivi', methods=['GET'])
def get_preventivi():
    """Restituisce tutti i preventivi caricati"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, filename, upload_date, extracted_info, updated_at
            FROM preventivi
            ORDER BY COALESCE(NULLIF(TRIM(updated_at), ''), upload_date) DESC
            """
        )
        rows = cursor.fetchall()
        conn.close()
        
        preventivi = []
        for row in rows:
            u = row["updated_at"] if row["updated_at"] else row["upload_date"]
            preventivo = {
                'id': row['id'],
                'filename': row['filename'],
                'upload_date': row['upload_date'],
                'updated_at': u,
                'extracted_info': json.loads(row['extracted_info']) if row['extracted_info'] else {}
            }
            preventivi.append(preventivo)
        
        return jsonify({'preventivi': preventivi}), 200
    except Exception as e:
        return jsonify({'error': f'Errore nel recupero preventivi: {str(e)}'}), 500

def _af_cache_payload_to_confronto_row(base, cached):
    """Ricostruisce una riga tabella AF da payload cache (v2)."""
    if cached.get('v') != 2:
        return None
    if cached.get('calcolo_ok'):
        p = cached['pred']
        return {
            **base,
            'k_normalizzato': p['k_normalizzato'],
            'k_percentile': p['k_percentile'],
            'ore_totali': p['ore_totali'],
            'ore_per_fase': p['ore_per_fase'],
            'input': cached.get('input'),
            'calcolo_ok': True,
        }
    if cached.get('dim_error'):
        return {
            **base,
            'k_normalizzato': None,
            'ore_totali': None,
            'calcolo_ok': False,
            'motivo': 'Dati dimensionali non disponibili',
        }
    return {
        **base,
        'k_normalizzato': None,
        'calcolo_ok': False,
        'motivo': cached.get('motivo', 'Errore'),
    }


@app.route('/api/preventivi/confronto-af', methods=['GET'])
def confronto_af():
    """
    Calcola AF stimato per tutti i preventivi (con cache DB per evitare N× ml_predict ad ogni load).
    Query: ?refresh=1 per forzare ricalcolo e aggiornamento cache.
    """
    refresh = request.args.get('refresh', '').lower() in ('1', 'true', 'yes')

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        'SELECT id, filename, extracted_info FROM preventivi ORDER BY upload_date DESC'
    )
    rows = cursor.fetchall()
    conn.close()

    model_fp = _ml_metrics_fingerprint()
    results = []
    n_senza_estrazione = 0

    for row in rows:
        raw = row['extracted_info'] or ''
        try:
            info = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            n_senza_estrazione += 1
            continue
        if not _extracted_info_valorizzato_per_af(info, raw):
            n_senza_estrazione += 1
            continue

        dims = _extract_dims(info)
        dims_fp = _dims_fingerprint(dims, raw)

        raw_mod = info.get("modello_struttura", "N/D")
        if isinstance(raw_mod, dict):
            modello = (
                raw_mod.get("nome")
                or raw_mod.get("descrizione")
                or json.dumps(raw_mod, ensure_ascii=False)[:300]
            )
        elif isinstance(raw_mod, str):
            modello = raw_mod
        else:
            modello = str(raw_mod) if raw_mod is not None else "N/D"

        cliente = ""
        c = info.get("cliente", {})
        if isinstance(c, dict):
            cliente = c.get("nome") or c.get("descrizione") or ""
            if not cliente and c:
                cliente = json.dumps(c, ensure_ascii=False)[:300]
        elif isinstance(c, str):
            cliente = c

        base = {
            'id': row['id'],
            'filename': row['filename'],
            'modello': modello,
            'cliente': cliente,
        }

        cached = None if refresh else _fattore_af_cache_try_get(row['id'], dims_fp, model_fp)
        if cached is not None:
            row_out = _af_cache_payload_to_confronto_row(base, cached)
            if row_out is not None:
                results.append(row_out)
                continue

        if dims is None:
            payload = {
                'v': 2,
                'calcolo_ok': False,
                'dim_error': True,
            }
            _fattore_af_cache_save(row['id'], dims_fp, model_fp, payload)
            results.append({
                **base,
                'k_normalizzato': None,
                'ore_totali': None,
                'calcolo_ok': False,
                'motivo': 'Dati dimensionali non disponibili',
            })
            continue

        try:
            pred = ml_predict(**dims)
            payload = {'v': 2, 'calcolo_ok': True, 'pred': pred, 'input': dims}
            _fattore_af_cache_save(row['id'], dims_fp, model_fp, payload)
            results.append({
                **base,
                'k_normalizzato': pred['k_normalizzato'],
                'k_percentile': pred['k_percentile'],
                'ore_totali': pred['ore_totali'],
                'ore_per_fase': pred['ore_per_fase'],
                'input': dims,
                'calcolo_ok': True,
            })
        except Exception as e:
            payload = {
                'v': 2,
                'calcolo_ok': False,
                'predict_error': True,
                'motivo': str(e),
            }
            _fattore_af_cache_save(row['id'], dims_fp, model_fp, payload)
            results.append({
                **base,
                'k_normalizzato': None,
                'calcolo_ok': False,
                'motivo': str(e),
            })

    calcolati = sorted(
        [r for r in results if r['calcolo_ok']],
        key=lambda x: x['k_normalizzato'],
        reverse=True,
    )
    non_calcolati = [r for r in results if not r['calcolo_ok']]

    for i, r in enumerate(calcolati):
        r['rank_complessita'] = i + 1

    return jsonify({
        'confronto': calcolati + non_calcolati,
        'n_calcolati': len(calcolati),
        'n_totale': len(results),
        'n_senza_estrazione': n_senza_estrazione,
        'nota': 'Ordinati per complessità stimata decrescente.',
        'cache': not refresh,
    }), 200

@app.route('/api/preventivi/<preventivo_id>/fattore-af', methods=['GET'])
def get_fattore_af(preventivo_id):
    """Calcola ore per fase e indice AF per un singolo preventivo (stessa cache di confronto-af)."""
    refresh = request.args.get('refresh', '').lower() in ('1', 'true', 'yes')

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        'SELECT extracted_info FROM preventivi WHERE id = %s',
        (preventivo_id,),
    )
    row = cursor.fetchone()
    conn.close()

    if not row:
        return jsonify({'error': 'Preventivo non trovato'}), 404

    raw = row['extracted_info'] or ''
    try:
        info = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        info = {}
    if not _extracted_info_valorizzato_per_af(info, raw):
        return jsonify({
            'error': 'Estrazione dati non disponibile per questo preventivo.',
            'suggerimento': (
                'Eseguire l\'estrazione dal PDF (upload o estrazione massiva) prima del calcolo AF.'
            ),
        }), 422

    dims = _extract_dims(info)
    dims_fp = _dims_fingerprint(dims, raw)
    model_fp = _ml_metrics_fingerprint()

    cached = None if refresh else _fattore_af_cache_try_get(preventivo_id, dims_fp, model_fp)
    if cached is not None and cached.get('v') == 2:
        if cached.get('calcolo_ok'):
            pred = cached['pred']
            out = dict(pred)
            out['preventivo_id'] = preventivo_id
            out['input_usato'] = {
                'peso_kg': dims['peso'],
                'lato_a_mm': dims['lato_a'],
                'lato_b_mm': dims['lato_b'],
                'altezza_mm': dims['altezza'],
            }
            out['nota_metodologica'] = (
                'Modello addestrato su commesse Filtrazione. '
                'Valori indicativi per strutture Elevators. '
                'Da calibrare con dati reali Elevators.'
            )
            return jsonify(out), 200
        if cached.get('dim_error'):
            return jsonify({
                'error': 'Dati dimensionali insufficienti per il calcolo AF.',
                'suggerimento': (
                    'Il preventivo non contiene peso e/o dimensioni '
                    'estraibili automaticamente dal PDF.'
                ),
                'campi_disponibili': list(info.keys()),
            }), 422
        if cached.get('predict_error'):
            err = cached.get('motivo', '')
            return jsonify({
                'error': err,
                'status': 'not_trained',
                'suggerimento': 'Eseguire: python ml_model.py --data <xlsx>',
            }), 503

    if dims is None:
        payload = {'v': 2, 'calcolo_ok': False, 'dim_error': True}
        _fattore_af_cache_save(preventivo_id, dims_fp, model_fp, payload)
        return jsonify({
            'error': 'Dati dimensionali insufficienti per il calcolo AF.',
            'suggerimento': (
                'Il preventivo non contiene peso e/o dimensioni '
                'estraibili automaticamente dal PDF.'
            ),
            'campi_disponibili': list(info.keys()),
        }), 422

    try:
        result = ml_predict(**dims)
        payload = {'v': 2, 'calcolo_ok': True, 'pred': result, 'input': dims}
        _fattore_af_cache_save(preventivo_id, dims_fp, model_fp, payload)
        result['preventivo_id'] = preventivo_id
        result['input_usato'] = {
            'peso_kg': dims['peso'],
            'lato_a_mm': dims['lato_a'],
            'lato_b_mm': dims['lato_b'],
            'altezza_mm': dims['altezza'],
        }
        result['nota_metodologica'] = (
            'Modello addestrato su commesse Filtrazione. '
            'Valori indicativi per strutture Elevators. '
            'Da calibrare con dati reali Elevators.'
        )
        return jsonify(result), 200
    except ValueError as e:
        payload = {
            'v': 2,
            'calcolo_ok': False,
            'predict_error': True,
            'motivo': str(e),
        }
        _fattore_af_cache_save(preventivo_id, dims_fp, model_fp, payload)
        return jsonify({
            'error': str(e),
            'status': 'not_trained',
            'suggerimento': 'Eseguire: python ml_model.py --data <xlsx>',
        }), 503
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/preventivi/<preventivo_id>', methods=['GET'])
def get_preventivo(preventivo_id):
    """Restituisce un preventivo specifico"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM preventivi WHERE id = %s', (preventivo_id,))
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return jsonify({'error': 'Preventivo non trovato'}), 404
        
        ua = row['updated_at'] if 'updated_at' in row.keys() and row['updated_at'] else row['upload_date']
        preventivo = {
            'id': row['id'],
            'filename': row['filename'],
            'filepath': row['filepath'],
            'upload_date': row['upload_date'],
            'updated_at': ua,
            'extracted_info': json.loads(row['extracted_info']) if row['extracted_info'] else {},
            'raw_text': row['raw_text']
        }
        
        return jsonify({'preventivo': preventivo}), 200
    except Exception as e:
        return jsonify({'error': f'Errore nel recupero preventivo: {str(e)}'}), 500

def _load_preventivo_dict_for_similarity(preventivo_id: str):
    """
    Carica i dati per la somiglianza **solo dal database** (tabella preventivi):
    usa `extracted_info` JSON prodotto dall'estrazione sull'offerta (Claude / pipeline).
    Non legge più data/*.json così il confronto è allineato ai dati persistiti in DB.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        'SELECT id, filename, upload_date, extracted_info FROM preventivi WHERE id = %s',
        (preventivo_id,),
    )
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    info = json.loads(row['extracted_info']) if row['extracted_info'] else {}
    return {
        'id': row['id'],
        'filename': row['filename'],
        'upload_date': row['upload_date'],
        'extracted_info': info,
    }


@app.route('/api/preventivi/<preventivo_id>/similar', methods=['GET'])
def get_similar_preventivi(preventivo_id):
    """Restituisce preventivi simili in base a extracted_info salvato a DB per ogni offerta."""
    try:
        reference_preventivo = _load_preventivo_dict_for_similarity(preventivo_id)
        if not reference_preventivo:
            return jsonify({'error': 'Preventivo non trovato'}), 404

        # Solo preventivi ancora presenti nel DB (evita file .json orfani in data/)
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            'SELECT id FROM preventivi WHERE id != %s',
            (preventivo_id,),
        )
        other_ids = [row['id'] for row in cursor.fetchall()]
        conn.close()

        preventivi = []
        for oid in other_ids:
            p = _load_preventivo_dict_for_similarity(oid)
            if p:
                preventivi.append(p)

        similar_preventivi = calculate_similarity(reference_preventivo, preventivi)
        
        return jsonify({
            'reference_id': preventivo_id,
            'similar_preventivi': similar_preventivi
        }), 200
    except Exception as e:
        return jsonify({'error': f'Errore nel calcolo somiglianza: {str(e)}'}), 500

@app.route('/api/config', methods=['GET'])
def get_config():
    """Restituisce la configurazione dei campi per la somiglianza"""
    return jsonify(load_config()), 200

@app.route('/api/config', methods=['POST'])
def update_config():
    """Aggiorna la configurazione dei campi per la somiglianza (stesso file usato da calculate_similarity)."""
    try:
        config = request.json
        if not isinstance(config, dict):
            return jsonify({'error': 'Body JSON non valido'}), 400
        if 'fields' not in config:
            return jsonify({'error': 'Campo "fields" obbligatorio'}), 400
        save_config(config)
        return jsonify({'success': True, 'config': load_config()}), 200
    except Exception as e:
        return jsonify({'error': f'Errore nell\'aggiornamento configurazione: {str(e)}'}), 500

def calculate_planning(preventivi, num_operatori=5, tempo_commessa=30, tempo_recupero_materie=7):
    """Calcola la pianificazione temporale dei preventivi"""
    if not preventivi:
        return []
    
    # Ordina i preventivi per data di upload
    sorted_preventivi = sorted(preventivi, key=lambda x: x.get('upload_date', ''))
    
    # Data di inizio (oggi)
    start_date = datetime.now()
    current_date = start_date
    
    # Lista delle commesse pianificate
    planning = []
    
    # Coda dei preventivi da processare
    queue = sorted_preventivi.copy()
    
    # Lista degli operatori disponibili (ogni operatore ha una data di fine lavoro)
    operatori = [start_date] * num_operatori
    
    while queue:
        preventivo = queue.pop(0)
        
        # Trova l'operatore disponibile prima
        operatore_idx = operatori.index(min(operatori))
        operatore_start = operatori[operatore_idx]
        
        # Se l'operatore è occupato, inizia quando finisce
        if operatore_start > current_date:
            start_recupero = operatore_start
        else:
            start_recupero = current_date
        
        # Calcola le date: recupero materie prime PRIMA della commessa
        fine_recupero = start_recupero + timedelta(days=tempo_recupero_materie)
        start_commessa = fine_recupero  # La commessa inizia quando finisce il recupero
        fine_commessa = start_commessa + timedelta(days=tempo_commessa)
        consegna = fine_commessa
        
        # Aggiorna la disponibilità dell'operatore
        operatori[operatore_idx] = fine_commessa
        
        # Estrai informazioni utili dal preventivo
        extracted_info = preventivo.get('extracted_info', {})
        if isinstance(extracted_info, str):
            try:
                extracted_info = json.loads(extracted_info)
            except:
                extracted_info = {}
        
        cliente_nome = 'N/A'
        if isinstance(extracted_info.get('cliente'), dict):
            cliente_nome = extracted_info.get('cliente', {}).get('nome', 'N/A')
        elif extracted_info.get('cliente'):
            cliente_nome = str(extracted_info.get('cliente'))
        
        totale = extracted_info.get('prezzo_totale_fornitura', 'N/A')
        if totale == 'N/A':
            totale = extracted_info.get('totale', 'N/A')
        
        planning_item = {
            'preventivo_id': preventivo['id'],
            'filename': preventivo['filename'],
            'operatore': operatore_idx + 1,
            'cliente': cliente_nome,
            'totale': totale,
            'data_inizio_recupero': start_recupero.isoformat(),
            'data_fine_recupero': fine_recupero.isoformat(),
            'data_inizio_commessa': start_commessa.isoformat(),
            'data_fine_commessa': fine_commessa.isoformat(),
            'data_consegna': consegna.isoformat(),
            'tempo_recupero_giorni': tempo_recupero_materie,
            'tempo_commessa_giorni': tempo_commessa,
            'upload_date': preventivo.get('upload_date', '')
        }
        
        planning.append(planning_item)
        
        # Aggiorna la data corrente se necessario
        if fine_commessa > current_date:
            current_date = fine_commessa
    
    return planning

@app.route('/api/planning', methods=['GET'])
def get_planning():
    """Restituisce la pianificazione temporale dei preventivi"""
    try:
        # Ottieni i parametri dalla query string o dalla configurazione
        num_operatori = request.args.get('num_operatori', type=int)
        tempo_commessa = request.args.get('tempo_commessa', type=int)
        tempo_recupero = request.args.get('tempo_recupero', type=int)
        
        # Se non specificati, usa la configurazione dal database
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM planning_config ORDER BY id DESC LIMIT 1')
        config_row = cursor.fetchone()
        
        if config_row:
            num_operatori = num_operatori or config_row['num_operatori']
            tempo_commessa = tempo_commessa or config_row['tempo_commessa_giorni']
            # Gestisce sia il vecchio campo che il nuovo
            tempo_recupero = tempo_recupero or config_row.get('tempo_recupero_materie_giorni') or config_row.get('tempo_magazzino_giorni', 7)
        else:
            num_operatori = num_operatori or 5
            tempo_commessa = tempo_commessa or 30
            tempo_recupero = tempo_recupero or 7
        
        # Ottieni tutti i preventivi dal database
        cursor.execute('SELECT id, filename, upload_date, extracted_info FROM preventivi ORDER BY upload_date ASC')
        rows = cursor.fetchall()
        conn.close()
        
        preventivi = []
        for row in rows:
            preventivo = {
                'id': row['id'],
                'filename': row['filename'],
                'upload_date': row['upload_date'],
                'extracted_info': json.loads(row['extracted_info']) if row['extracted_info'] else {}
            }
            preventivi.append(preventivo)
        
        # Calcola la pianificazione
        planning = calculate_planning(preventivi, num_operatori, tempo_commessa, tempo_recupero)
        
        return jsonify({
            'planning': planning,
            'config': {
                'num_operatori': num_operatori,
                'tempo_commessa_giorni': tempo_commessa,
                'tempo_recupero_materie_giorni': tempo_recupero
            }
        }), 200
    except Exception as e:
        import traceback
        print(f"Errore nel planning: {e}")
        print(traceback.format_exc())
        return jsonify({'error': str(e)}), 500

@app.route('/api/planning/config', methods=['GET', 'POST'])
def planning_config():
    """Gestisce la configurazione del planning"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if request.method == 'POST':
            data = request.json
            num_operatori = data.get('num_operatori', 5)
            tempo_commessa = data.get('tempo_commessa_giorni', 30)
            tempo_recupero = data.get('tempo_recupero_materie_giorni', 7)
            
            # Aggiorna o inserisci la configurazione
            cursor.execute('''
                UPDATE planning_config
                SET num_operatori = %s, tempo_commessa_giorni = %s, tempo_recupero_materie_giorni = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = (SELECT id FROM planning_config ORDER BY id DESC LIMIT 1)
            ''', (num_operatori, tempo_commessa, tempo_recupero))

            if cursor.rowcount == 0:
                cursor.execute('''
                    INSERT INTO planning_config (num_operatori, tempo_commessa_giorni, tempo_recupero_materie_giorni)
                    VALUES (%s, %s, %s)
                ''', (num_operatori, tempo_commessa, tempo_recupero))
            
            conn.commit()
            conn.close()
            
            return jsonify({
                'success': True,
                'config': {
                    'num_operatori': num_operatori,
                    'tempo_commessa_giorni': tempo_commessa,
                    'tempo_recupero_materie_giorni': tempo_recupero
                }
            }), 200
        else:
            # GET
            cursor.execute('SELECT * FROM planning_config ORDER BY id DESC LIMIT 1')
            config_row = cursor.fetchone()
            conn.close()
            
            if config_row:
                return jsonify({
                    'num_operatori': config_row['num_operatori'],
                    'tempo_commessa_giorni': config_row['tempo_commessa_giorni'],
                    'tempo_recupero_materie_giorni': config_row.get('tempo_recupero_materie_giorni') or 7
                }), 200
            else:
                return jsonify({
                    'num_operatori': 5,
                    'tempo_commessa_giorni': 30,
                    'tempo_recupero_materie_giorni': 7
                }), 200
    except Exception as e:
        import traceback
        print(f"Errore nella configurazione planning: {e}")
        print(traceback.format_exc())
        return jsonify({'error': str(e)}), 500


@app.route('/api/ml/stats', methods=['GET'])
def get_ml_stats():
    """Metriche e feature importance del modello RF."""
    metrics = load_metrics()
    if metrics is None:
        return jsonify({
            'status': 'not_trained',
            'message': 'Modello non disponibile. Eseguire ml_model.py',
        }), 503
    return jsonify(metrics), 200


@app.route('/api/ml/charts/<chart_name>', methods=['GET'])
def get_ml_chart(chart_name):
    """Serve i grafici PNG generati dal training (per fase: ?phase=OreProg ecc.)."""
    allowed = ['feature_importance', 'predicted_vs_actual', 'residuals']
    if chart_name not in allowed:
        return jsonify({'error': 'Chart non valido'}), 404

    phase = request.args.get('phase') or 'OreImb'
    if phase not in TARGETS:
        phase = 'OreImb'

    chart_path = os.path.join(CHARTS_DIR, phase, f'{chart_name}.png')
    if not os.path.exists(chart_path):
        chart_path = os.path.join(CHARTS_DIR, f'{chart_name}.png')
    if not os.path.exists(chart_path):
        return jsonify({'error': 'Chart non trovato. Eseguire ml_model.py'}), 404

    resp = send_file(chart_path, mimetype='image/png')
    resp.headers['Cache-Control'] = 'max-age=3600'
    return resp


@app.route('/api/ml/train', methods=['POST'])
def ml_train():
    """Cancella modelli/metriche/grafici esistenti e avvia train_models.py in background."""
    data = request.get_json(silent=True) or {}
    mode = data.get('mode', 'merge')
    if mode not in ('merge', 'legacy_only', 'from_db'):
        mode = 'merge'
    if not _start_ml_training(mode):
        return jsonify({'error': 'Training già in corso'}), 409
    return jsonify({'status': 'started', 'mode': mode}), 202


@app.route('/api/ml/training-status', methods=['GET'])
def ml_training_status():
    with _training_lock:
        return jsonify({
            'running': _training_running,
            'message': _training_message,
            'error': _training_error,
            'exit_code': _training_exit_code,
            'log_tail': (_training_log_tail[-4000:] if _training_log_tail else ''),
        }), 200


@app.route('/api/ml/predict', methods=['POST'])
def ml_predict_endpoint():
    """Previsione ore imballaggio. Body: peso, lato_a, lato_b, altezza, portata (opz.)."""
    data = request.json or {}
    try:
        peso = float(data['peso'])
        lato_a = float(data['lato_a'])
        lato_b = float(data['lato_b'])
        altezza = float(data['altezza'])
        portata = float(data['portata']) if 'portata' in data else None
    except (KeyError, TypeError, ValueError) as e:
        return jsonify({'error': f'Parametri mancanti o non validi: {e}'}), 400

    try:
        result = ml_predict(peso, lato_a, lato_b, altezza, portata)
        return jsonify(result), 200
    except ValueError as e:
        return jsonify({'error': str(e), 'status': 'not_trained'}), 503


@app.route('/api/ml/similar', methods=['GET'])
def ml_similar():
    """Top 3 commesse simili. Query: peso, lato_a, lato_b, altezza."""
    try:
        peso = float(request.args.get('peso', 0))
        lato_a = float(request.args.get('lato_a', 0))
        lato_b = float(request.args.get('lato_b', 0))
        altezza = float(request.args.get('altezza', 0))
    except (TypeError, ValueError):
        return jsonify({'error': 'Parametri non validi'}), 400

    xlsx_candidates = [
        os.path.join(base_dir, '..', 'dati', 'Estrazione fattore k (1).xlsx'),
        os.path.join(base_dir, 'Estrazione fattore k (1).xlsx'),
    ]
    xlsx_path = next((p for p in xlsx_candidates if os.path.exists(p)), None)

    if not xlsx_path:
        return jsonify({'similar': [], 'error': 'Dataset non trovato'}), 200

    try:
        import pandas as pd

        df = pd.read_excel(xlsx_path, header=1, engine='openpyxl')
        df.columns = [
            '_drop', 'Peso_kg', 'Portata', 'LatoCorto_mm',
            'LatoLungo_mm', 'Altezza_mm', 'OreProg', 'OreNest',
            'OreTaglio', 'OrePieg', 'OreSald', 'OreImb', 'Commessa',
        ]
        df = df.drop(columns=['_drop']).dropna(subset=['Commessa', 'OreImb'])
        df = df[df['LatoCorto_mm'] < 10_000]
        df = df.dropna(subset=['Peso_kg', 'LatoCorto_mm', 'LatoLungo_mm', 'Altezza_mm'])

        features = df[['Peso_kg', 'LatoCorto_mm', 'LatoLungo_mm', 'Altezza_mm']].values.astype(float)
        query = np.array([[peso, lato_a, lato_b, altezza]], dtype=float)

        mins = features.min(axis=0)
        maxs = features.max(axis=0)
        ranges = np.where(maxs - mins == 0, 1, maxs - mins)

        features_norm = (features - mins) / ranges
        query_norm = (query - mins) / ranges

        dists = np.sqrt(((features_norm - query_norm) ** 2).sum(axis=1))
        top3_idx = dists.argsort()[:3]

        similar = []
        for idx in top3_idx:
            row = df.iloc[int(idx)]
            dist = float(dists[int(idx)])
            similarity_pct = round(max(0, (1 - dist) * 100), 1)
            similar.append({
                'commessa_id': str(row['Commessa']),
                'ore_imb_reale': round(float(row['OreImb']), 1),
                'peso_kg': round(float(row['Peso_kg']), 0),
                'lato_a': round(float(row['LatoCorto_mm']), 0),
                'lato_b': round(float(row['LatoLungo_mm']), 0),
                'altezza': round(float(row['Altezza_mm']), 0),
                'similarity_pct': similarity_pct,
            })

        return jsonify({'similar': similar}), 200

    except Exception as e:
        return jsonify({'error': str(e), 'similar': []}), 200


@app.route('/api/commesse-ore/import', methods=['POST'])
def commesse_ore_import():
    """Importa ore da Excel (foglio Elaborato). Body JSON opzionale: {\"path\": \"...\"}"""
    data = request.get_json(silent=True) or {}
    path = data.get('path') or default_xlsx_path()
    path = os.path.abspath(path)
    try:
        rows = load_rows_from_xlsx(path)
    except FileNotFoundError:
        return jsonify({'error': f'File non trovato: {path}'}), 404
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    result = import_to_sqlite(None, rows, path)
    return jsonify({'success': True, **result}), 200


@app.route('/api/commesse-ore', methods=['GET'])
def commesse_ore_list():
    """Elenco commesse con ore importate."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        '''
        SELECT nr_commessa, cliente, cliente_norm,
               ore_imba, ore_nest, ore_pieg, ore_prod, ore_prog, ore_sald, ore_totale,
               source_file, updated_at
        FROM commesse_ore ORDER BY nr_commessa
        '''
    )
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return jsonify({'commesse': rows, 'count': len(rows)}), 200


@app.route('/api/commesse-ore/stats', methods=['GET'])
def commesse_ore_stats():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) AS cnt FROM commesse_ore')
    n = cursor.fetchone()['cnt']
    conn.close()
    by_norm = rows_grouped_by_cliente_norm(None)
    n_norm = len(by_norm)
    ambiguous = sum(1 for v in by_norm.values() if len(v) > 1)
    return jsonify({
        'commesse_count': n,
        'clienti_distinti_norm': n_norm,
        'clienti_con_piu_commesse': ambiguous,
    }), 200


@app.route('/api/commesse-ore/match-preventivi', methods=['GET'])
def commesse_ore_match_preventivi():
    """
    Per ogni preventivo in DB, verifica match con commesse per cliente normalizzato.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT filename FROM preventivi ORDER BY upload_date DESC')
    filenames = [r['filename'] for r in cursor.fetchall()]
    conn.close()

    empty_summary = {
        'preventivi': 0,
        'mapped': 0,
        'mapped_no_ore': 0,
        'ambiguous_mapping': 0,
        'unique': 0,
        'ambiguous': 0,
        'none': 0,
        'unparsed': 0,
    }
    if not filenames:
        return jsonify({'matches': [], 'summary': empty_summary}), 200

    by_norm = rows_grouped_by_cliente_norm(None)
    matches = match_preventivi_filenames(filenames, by_norm, None)
    summary = {**empty_summary, 'preventivi': len(matches)}
    for m in matches:
        k = m.get('match')
        if k in summary:
            summary[k] += 1
    return jsonify({'matches': matches, 'summary': summary}), 200


@app.route('/api/offerta-commessa-mapping/import', methods=['POST'])
def offerta_commessa_mapping_import():
    """Importa elenco offerte ↔ commesse (xlsm Sheet1). Body: {\"path\": \"...\"} opzionale."""
    data = request.get_json(silent=True) or {}
    path = data.get('path') or default_mapping_xlsx_path()
    path = os.path.abspath(path)
    try:
        rows = load_rows_from_mapping_xlsx(path)
    except FileNotFoundError:
        return jsonify({'error': f'File non trovato: {path}'}), 404
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    result = import_mapping_to_sqlite(None, rows, path)
    return jsonify({'success': True, **result}), 200


@app.route('/api/offerta-commessa-mapping/stats', methods=['GET'])
def offerta_commessa_mapping_stats():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) AS cnt FROM offerta_commessa_map')
        n = cursor.fetchone()['cnt']
        conn.close()
    except Exception:
        n = 0
    return jsonify({'rows': n}), 200


if __name__ == '__main__':
    app.run(debug=True, port=5000)
