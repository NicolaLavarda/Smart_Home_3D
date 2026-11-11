import fs from 'fs';

const content = fs.readFileSync('HA_DEVICES_MAPPING.md', 'utf8');
const blocks = content.split('### `');

console.log('=== ENTITÀ COMPILATE DALL\'UTENTE ===\n');

let count = 0;
for (const b of blocks.slice(1)) {
  const firstLine = b.split('\n')[0];
  const id = firstLine.split('`')[0].trim();
  
  const posMatch = b.match(/- \*\*Posizione 3D:\*\*\s*([^\n]*)/);
  const azioneMatch = b.match(/- \*\*Azione:\*\*\s*`([^`]+)`/);
  const noteMatch = b.match(/- \*\*Funzionamento \/ Note:\*\*\s*([^\n]*)/);

  let pos = posMatch ? posMatch[1].trim() : '';
  const azione = azioneMatch ? azioneMatch[1].trim() : '';
  let note = noteMatch ? noteMatch[1].trim() : '';

  if (pos.startsWith('- **Funzionamento')) pos = '';
  if (note.startsWith('---')) note = '';

  const hasRealPos = pos.length > 0 && !b.includes('GIA_MAPPATO') && pos !== 'Già funzionante';
  const isMappa = azione === 'mappa';

  if (hasRealPos || isMappa) {
    count++;
    console.log(`[${count}] ID: ${id}`);
    console.log(`    Azione: ${azione}`);
    console.log(`    Posizione: ${pos}`);
    if (note) console.log(`    Note: ${note}`);
    console.log('');
  }
}

console.log(`Totale entità realmente compilate dall'utente: ${count}`);
