// Awatar użytkownika (profil) — miniatura w „Śledzone przez…" i na mapie
import { defineFeature } from '../feature'

export default defineFeature({
  pl: { avatarTitle: 'Zdjęcie profilowe', avatarChange: 'Zmień zdjęcie', avatarRemove: 'Usuń zdjęcie',
        avatarHint: 'JPG, PNG, WEBP lub GIF, do 2 MB. Widoczne dla zespołu przy obserwowanych kontenerach i statkach.' },
  en: { avatarTitle: 'Profile photo', avatarChange: 'Change photo', avatarRemove: 'Remove photo',
        avatarHint: 'JPG, PNG, WEBP or GIF, up to 2 MB. Shown to the team next to watched containers and vessels.' },
  pt: { avatarTitle: 'Foto de perfil', avatarChange: 'Alterar foto', avatarRemove: 'Remover foto',
        avatarHint: 'JPG, PNG, WEBP ou GIF, até 2 MB. Visível para a equipa junto de contentores e navios observados.' },
})
