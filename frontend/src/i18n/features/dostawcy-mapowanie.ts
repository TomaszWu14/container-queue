// Dostawcy: mapowanie nazw z pliku kolejki (aliasy per spółka pliku)
import { defineFeature } from '../feature'

export default defineFeature({
  pl: {
    supUnmappedTitle: 'Do zmapowania',
    supUnmappedHint: 'Nazwy dostawców z pliku kolejki bez dopasowania w słowniku — zmapuj na dostawcę, a kolejne importy trafią same.',
    supContainersN: '{n} kont.',
    supPick: 'wybierz dostawcę',
    supMap: 'Mapuj',
    supNewFromName: '+ Nowy dostawca',
    supMappedN: 'Przypisano kontenerów: {n}',
    supRawHint: 'Nazwa z pliku — do zmapowania',
  },
  en: {
    supUnmappedTitle: 'To map',
    supUnmappedHint: 'Supplier names from the queue file with no dictionary match — map them to a supplier and future imports will follow.',
    supContainersN: '{n} cont.',
    supPick: 'pick a supplier',
    supMap: 'Map',
    supNewFromName: '+ New supplier',
    supMappedN: 'Containers assigned: {n}',
    supRawHint: 'Name from file — to be mapped',
  },
  pt: {
    supUnmappedTitle: 'Por mapear',
    supUnmappedHint: 'Nomes de fornecedores do ficheiro da fila sem correspondência no dicionário — mapeie-os e as próximas importações seguirão.',
    supContainersN: '{n} cont.',
    supPick: 'escolha o fornecedor',
    supMap: 'Mapear',
    supNewFromName: '+ Novo fornecedor',
    supMappedN: 'Contentores atribuídos: {n}',
    supRawHint: 'Nome do ficheiro — por mapear',
  },
})
