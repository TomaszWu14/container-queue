import { defineFeature } from '../feature'

// wspólny plik dla kilku kontenerów (AttachmentActions.tsx, spec 2026-10-06 decyzja 24)
export default defineFeature({
  pl: {
    attSharedWith: 'wspólny z {list}',
    attSharedHint: 'Ten sam plik jest też w innych kontenerach — podmiana działa wszędzie.',
    attAlsoIn: 'Plik jest też w {list} — zniknie także stamtąd.',
    attUnlink: 'Odepnij',
    attUnlinkConfirm: 'Odpiąć „{name}” od tego kontenera? Plik zostanie w {owner}.',
  },
  en: {
    attSharedWith: 'shared with {list}',
    attSharedHint: 'The same file is also in other containers — replacing it updates all of them.',
    attAlsoIn: 'The file is also in {list} — it will disappear there too.',
    attUnlink: 'Unlink',
    attUnlinkConfirm: 'Unlink “{name}” from this container? The file stays in {owner}.',
  },
  pt: {
    attSharedWith: 'partilhado com {list}',
    attSharedHint: 'O mesmo ficheiro está também noutros contentores — a substituição aplica-se a todos.',
    attAlsoIn: 'O ficheiro está também em {list} — desaparecerá também de lá.',
    attUnlink: 'Desligar',
    attUnlinkConfirm: 'Desligar “{name}” deste contentor? O ficheiro fica em {owner}.',
  },
})
