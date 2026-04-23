#!/usr/bin/env python3
"""
Script per caricare massivamente preventivi PDF da una cartella
tramite l'API del backend.
"""

import os
import sys
import requests
import glob
from pathlib import Path

# Configurazione
API_BASE_URL = "http://localhost:5000"
UPLOAD_ENDPOINT = f"{API_BASE_URL}/api/upload"

def find_pdf_folders(pattern="2026_*"):
    """Trova tutte le cartelle che corrispondono al pattern"""
    # Ottieni il percorso assoluto dello script
    script_dir = Path(__file__).parent.absolute()
    
    # Se siamo in backend, cerca nella directory parent (root del progetto)
    if script_dir.name == "backend":
        search_dir = script_dir.parent
    else:
        search_dir = script_dir
    
    folders = []
    
    # Cerca nella directory di ricerca usando glob
    for folder in search_dir.glob(pattern):
        if folder.is_dir():
            folders.append(folder)
    
    # Se non trova nulla, prova anche con ricerca case-insensitive
    if not folders:
        import fnmatch
        for item in search_dir.iterdir():
            if item.is_dir() and fnmatch.fnmatch(item.name, pattern):
                folders.append(item)
    
    return folders

def find_pdfs_in_folder(folder_path):
    """Trova tutti i file PDF in una cartella"""
    pdf_files = list(folder_path.glob("*.pdf"))
    return pdf_files

def upload_pdf(file_path):
    """Carica un singolo PDF tramite l'API"""
    try:
        with open(file_path, 'rb') as f:
            files = {'file': (file_path.name, f, 'application/pdf')}
            response = requests.post(UPLOAD_ENDPOINT, files=files, timeout=300)
        
        if response.status_code == 200:
            data = response.json()
            return {
                'success': True,
                'filename': file_path.name,
                'preventivo_id': data.get('preventivo', {}).get('id', 'N/A'),
                'message': 'Caricato con successo'
            }
        else:
            error_msg = response.json().get('error', 'Errore sconosciuto')
            return {
                'success': False,
                'filename': file_path.name,
                'error': error_msg
            }
    except requests.exceptions.ConnectionError:
        return {
            'success': False,
            'filename': file_path.name,
            'error': 'Impossibile connettersi al backend. Assicurati che sia in esecuzione.'
        }
    except requests.exceptions.Timeout:
        return {
            'success': False,
            'filename': file_path.name,
            'error': 'Timeout durante il caricamento'
        }
    except Exception as e:
        return {
            'success': False,
            'filename': file_path.name,
            'error': str(e)
        }

def bulk_upload(folder_pattern="2026_*"):
    """Carica tutti i PDF dalle cartelle che corrispondono al pattern"""
    print(f"[*] Cerca cartelle con pattern: {folder_pattern}\n")
    
    # Trova le cartelle
    folders = find_pdf_folders(folder_pattern)
    
    if not folders:
        print(f"[!] Nessuna cartella trovata con pattern '{folder_pattern}'")
        print("    Cerca nella directory corrente e nella directory parent...")
        return
    
    print(f"[OK] Trovate {len(folders)} cartella/e:\n")
    for folder in folders:
        print(f"    - {folder}")
    
    # Raccogli tutti i PDF
    all_pdfs = []
    for folder in folders:
        pdfs = find_pdfs_in_folder(folder)
        all_pdfs.extend(pdfs)
        print(f"\n[*] Trovati {len(pdfs)} PDF in {folder.name}/")
    
    if not all_pdfs:
        print("\n[!] Nessun file PDF trovato nelle cartelle")
        return
    
    print(f"\n[*] Totale PDF da caricare: {len(all_pdfs)}\n")
    print("=" * 60)
    
    # Carica i PDF
    results = {
        'success': [],
        'failed': []
    }
    
    for i, pdf_file in enumerate(all_pdfs, 1):
        print(f"\n[{i}/{len(all_pdfs)}] Caricamento: {pdf_file.name}")
        print(f"    Percorso: {pdf_file}")
        
        result = upload_pdf(pdf_file)
        
        if result['success']:
            print(f"    [OK] {result['message']}")
            print(f"    ID: {result['preventivo_id']}")
            results['success'].append(result)
        else:
            print(f"    [ERR] Errore: {result['error']}")
            results['failed'].append(result)
    
    # Riepilogo
    print("\n" + "=" * 60)
    print("\n[*] RIEPILOGO CARICAMENTO")
    print("=" * 60)
    print(f"[OK] Caricati con successo: {len(results['success'])}")
    print(f"[ERR] Falliti: {len(results['failed'])}")
    print(f"[*] Totale: {len(all_pdfs)}")
    
    if results['failed']:
        print("\n[!] File con errori:")
        for failed in results['failed']:
            print(f"    - {failed['filename']}: {failed['error']}")
    
    if results['success']:
        print("\n[OK] File caricati con successo:")
        for success in results['success']:
            print(f"    - {success['filename']} (ID: {success['preventivo_id']})")

if __name__ == "__main__":
    # Verifica che il backend sia raggiungibile
    try:
        response = requests.get(f"{API_BASE_URL}/api/preventivi", timeout=5)
        print("[OK] Backend raggiungibile\n")
    except requests.exceptions.ConnectionError:
        print("[ERR] ERRORE: Impossibile connettersi al backend!")
        print(f"    Assicurati che il backend sia in esecuzione su {API_BASE_URL}")
        print("    Avvia il backend con: cd backend && python app.py")
        sys.exit(1)
    except Exception as e:
        print(f"[ERR] Errore di connessione: {e}")
        sys.exit(1)
    
    # Esegui il caricamento
    bulk_upload("2026_*")
