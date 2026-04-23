import json
import os
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

# Sempre accanto a questo modulo (indipendente dalla cwd del processo Flask)
SIMILARITY_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'similarity_config.json')


def save_config(config_dict):
    """Salva la configurazione campi/soglia usata da /api/config POST e da load_config."""
    with open(SIMILARITY_CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(config_dict, f, ensure_ascii=False, indent=2)


def load_config():
    """Carica la configurazione dei campi per la somiglianza (pesi, abilitati, soglia)."""
    config_file = SIMILARITY_CONFIG_PATH
    
    # Configurazione di default
    default_config = {
        "fields": [
            {
                "name": "cliente",
                "weight": 1.0,
                "enabled": True
            },
            {
                "name": "descrizione_lavori",
                "weight": 1.5,
                "enabled": True
            },
            {
                "name": "materiali",
                "weight": 1.2,
                "enabled": True
            },
            {
                "name": "totale",
                "weight": 0.8,
                "enabled": True
            },
            {
                "name": "note",
                "weight": 0.5,
                "enabled": False
            }
        ],
        "similarity_threshold": 0.3
    }
    
    if os.path.exists(config_file):
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
                # Merge con default per assicurarsi che tutti i campi necessari ci siano
                default_config.update(config)
                return default_config
        except Exception as e:
            print(f"Errore nel caricamento configurazione: {e}")
            return default_config
    
    save_config(default_config)
    return default_config

def _stringify_field_value(value):
    """Serializza valori per confronto/UI: dict/list come JSON (non repr Python con apici singoli)."""
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        try:
            return json.dumps(value, ensure_ascii=False)
        except (TypeError, ValueError):
            return str(value)
    return str(value)

def get_field_value(preventivo, field_name):
    """Estrae il valore di un campo dal preventivo"""
    extracted_info = preventivo.get('extracted_info', {})
    
    # Prova vari nomi di campo comuni
    field_variations = [
        field_name,
        field_name.lower(),
        field_name.upper(),
        field_name.replace('_', ' '),
        field_name.replace('_', '')
    ]
    
    for variation in field_variations:
        if variation in extracted_info:
            value = extracted_info[variation]
            if value is not None:
                return _stringify_field_value(value)
    
    # Cerca anche in modo case-insensitive
    for key, value in extracted_info.items():
        if key.lower() == field_name.lower() and value is not None:
            return _stringify_field_value(value)

    # "materiale" in config → nei JSON spesso è sotto materiali.materiale (non chiave top-level)
    if field_name.lower() == 'materiale':
        mat = extracted_info.get('materiali')
        if isinstance(mat, dict):
            inner = mat.get('materiale')
            if inner is not None and inner != '':
                return _stringify_field_value(inner)
            if mat:
                return _stringify_field_value(mat)

    return ""

def _looks_like_json_structure(s):
    if not s or not isinstance(s, str):
        return False
    t = s.strip()
    return t.startswith("{") or t.startswith("[")

def calculate_text_similarity(text1, text2):
    """Calcola la somiglianza tra due testi usando TF-IDF e cosine similarity"""
    # Due campi vuoti non sono "identici al 100%": non c'è contenuto da confrontare.
    if not text1 and not text2:
        return 0.0
    if not text1 or not text2:
        return 0.0
    
    try:
        vectorizer = TfidfVectorizer()
        tfidf_matrix = vectorizer.fit_transform([text1, text2])
        similarity = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0]
        return float(similarity)
    except Exception as e:
        print(f"Errore nel calcolo somiglianza testuale: {e}")
        return 0.0

def calculate_numeric_similarity(value1, value2):
    """Calcola la somiglianza tra due valori numerici"""
    try:
        # Estrae numeri dalle stringhe se necessario
        def extract_number(value):
            if isinstance(value, (int, float)):
                return float(value)
            if isinstance(value, str):
                # Rimuove caratteri non numerici tranne punto e virgola
                cleaned = ''.join(c for c in value if c.isdigit() or c in '.,')
                cleaned = cleaned.replace(',', '.')
                try:
                    return float(cleaned)
                except:
                    return 0.0
            return 0.0
        
        num1 = extract_number(value1)
        num2 = extract_number(value2)
        
        if num1 == 0 and num2 == 0:
            return 1.0
        if num1 == 0 or num2 == 0:
            return 0.0
        
        # Calcola la differenza percentuale
        diff = abs(num1 - num2)
        avg = (abs(num1) + abs(num2)) / 2
        if avg == 0:
            return 1.0
        
        similarity = 1.0 - min(diff / avg, 1.0)
        return similarity
    except Exception as e:
        print(f"Errore nel calcolo somiglianza numerica: {e}")
        return 0.0

def calculate_similarity(reference_preventivo, preventivi):
    """
    Calcola la somiglianza tra il preventivo di riferimento e gli altri.
    Ogni dict deve avere la chiave `extracted_info` (dati strutturati estratti dall'offerta in DB).
    """
    config = load_config()
    enabled_fields = [f for f in config['fields'] if f.get('enabled', True)]
    threshold = config.get('similarity_threshold', 0.3)
    
    results = []
    
    for preventivo in preventivi:
        total_similarity = 0.0
        total_weight = 0.0
        field_similarities = {}
        
        for field_config in enabled_fields:
            field_name = field_config['name']
            weight = field_config.get('weight', 1.0)
            
            ref_value = get_field_value(reference_preventivo, field_name)
            comp_value = get_field_value(preventivo, field_name)
            
            # Oggetti/array serializzati come JSON sono sempre confronto testuale (TF-IDF)
            is_numeric = False
            if not (_looks_like_json_structure(ref_value) or _looks_like_json_structure(comp_value)):
                try:
                    float(''.join(c for c in ref_value if c.isdigit() or c in '.,'))
                    float(''.join(c for c in comp_value if c.isdigit() or c in '.,'))
                    is_numeric = True
                except Exception:
                    pass
            
            if is_numeric:
                similarity = calculate_numeric_similarity(ref_value, comp_value)
            else:
                similarity = calculate_text_similarity(ref_value, comp_value)
            
            field_similarities[field_name] = {
                'similarity': similarity,
                'weight': weight,
                'ref_value': ref_value if ref_value else "",
                'comp_value': comp_value if comp_value else ""
            }
            
            total_similarity += similarity * weight
            total_weight += weight
        
        if total_weight > 0:
            final_similarity = total_similarity / total_weight
        else:
            final_similarity = 0.0
        
        if final_similarity >= threshold:
            results.append({
                'preventivo': {
                    'id': preventivo['id'],
                    'filename': preventivo['filename'],
                    'upload_date': preventivo['upload_date'],
                    'extracted_info': preventivo['extracted_info']
                },
                'similarity_score': round(final_similarity, 4),
                'field_similarities': field_similarities
            })
    
    # Ordina per somiglianza decrescente
    results.sort(key=lambda x: x['similarity_score'], reverse=True)
    
    return results
