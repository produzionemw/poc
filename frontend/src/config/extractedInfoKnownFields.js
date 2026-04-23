/**
 * Campi tipici in extracted_info (estrazione offerte Metal Working).
 * Il nome `name` è quello da usare nella config somiglianza: deve combaciare
 * con le chiavi in extracted_info o con gli alias gestiti in backend (es. materiale).
 */
export const EXTRACTED_INFO_KNOWN_FIELD_GROUPS = [
  {
    id: 'ident',
    label: 'Identificazione e offerta',
    items: [
      { name: 'data', label: 'Data documento', hint: 'Es. "23 01 26"' },
      { name: 'tipologia', label: 'Tipologia', hint: 'Es. Offerta preliminare, Conferma d\'ordine' },
      { name: 'riferimento', label: 'Riferimento MW', hint: 'Testo riferimento commessa / offerta' },
      { name: 'riferimento_metal_working', label: 'Riferimento Metal Working (alt.)', hint: 'Variante nome chiave in alcune estrazioni' },
      { name: 'cliente', label: 'Cliente', hint: 'Oggetto con nome, indirizzo, riferimenti; confronto su JSON serializzato' },
      { name: 'modello_struttura', label: 'Modello struttura', hint: 'Es. F1, DISCOVERY' },
    ],
  },
  {
    id: 'descr',
    label: 'Descrizione e lavori',
    items: [
      { name: 'descrizione_lavori', label: 'Descrizione lavori', hint: 'Testo lungo descrittivo del modello / fornitura' },
    ],
  },
  {
    id: 'dims',
    label: 'Dimensioni e caratteristiche',
    items: [
      { name: 'caratteristiche_dimensioni', label: 'Caratteristiche e dimensioni (blocco)', hint: 'Oggetto: fossa, corsa, testata, piani, ecc. (nomi interni possono variare)' },
      { name: 'caratteristiche', label: 'Caratteristiche (variante)', hint: 'In alcune offerte al posto di caratteristiche_dimensioni' },
    ],
  },
  {
    id: 'mat',
    label: 'Materiali e finiture',
    items: [
      {
        name: 'materiale',
        label: 'Materiale (profili / lamiera)',
        hint: 'Alias: legge da materiali.materiale o materiali.descrizione se presente',
        recommended: true,
      },
      { name: 'materiali', label: 'Blocco materiali (intero)', hint: 'Oggetto completo: materiale, verniciatura, imballo, ecc.' },
      { name: 'imballo', label: 'Imballo', hint: 'A volte stringa a livello radice, a volte dentro materiali' },
    ],
  },
  {
    id: 'weight',
    label: 'Pesi',
    items: [
      { name: 'peso_stimato', label: 'Peso stimato', hint: 'Oggetto con struttura_kg, tamponamenti_kg' },
    ],
  },
  {
    id: 'price',
    label: 'Prezzi',
    items: [
      { name: 'prezzi', label: 'Prezzi (blocco)', hint: 'Es. totale_fornitura_escluse_varianti, prezzo_complessivo_varianti' },
      { name: 'totale', label: 'Totale (se presente)', hint: 'In alcuni JSON compare come chiave top-level; altrimenti usare prezzi' },
    ],
  },
  {
    id: 'supply',
    label: 'Fornitura e condizioni',
    items: [
      { name: 'dettaglio_fornitura', label: 'Dettaglio fornitura', hint: 'Varianti, voci, prezzi opzionali (oggetto grande)' },
      { name: 'condizioni_vendita', label: 'Condizioni di vendita', hint: 'Termini consegna, pagamento, garanzia' },
    ],
  },
  {
    id: 'norm',
    label: 'Norme e note',
    items: [
      { name: 'classe_esecuzione', label: 'Classe di esecuzione', hint: 'Es. EXC2' },
      { name: 'classe_uso', label: 'Classe d\'uso', hint: 'Es. "2"' },
      { name: 'norma_costruzione', label: 'Norma di costruzione', hint: 'Es. UNI EN 1090-1' },
      { name: 'note_aggiuntive', label: 'Note aggiuntive', hint: 'Testo libero' },
      { name: 'note', label: 'Note', hint: 'Chiave alternativa (se usata dall\'estrazione)' },
    ],
  },
];

export function flattenKnownFields() {
  const out = [];
  for (const g of EXTRACTED_INFO_KNOWN_FIELD_GROUPS) {
    for (const item of g.items) {
      out.push({ ...item, groupId: g.id, groupLabel: g.label });
    }
  }
  return out;
}
