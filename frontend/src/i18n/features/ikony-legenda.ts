import { defineFeature } from '../feature'

// Legenda kodów kolorów kolejki (audyt UI A16) i nieaktywna koperta bez e-maila (B28)
export default defineFeature({
  pl: {
    kqStageBar: 'Etap: {stage}', kqLegend: 'Legenda kolorów',
    kqLegendText: 'Czerwona kropka przy numerze — kontener opóźniony. Kolorowy pasek z lewej — etap (nazwa w podpowiedzi). Tło wiersza — magazyn: DLT różowe, ACME zielone, bez magazynu białe.',
    userNoEmail: 'Brak adresu e-mail',
  },
  en: {
    kqStageBar: 'Stage: {stage}', kqLegend: 'Colour legend',
    kqLegendText: 'Red dot next to the number — delayed container. Coloured bar on the left — stage (name in the tooltip). Row background — warehouse: DLT pink, ACME green, no warehouse white.',
    userNoEmail: 'No e-mail address',
  },
  pt: {
    kqStageBar: 'Etapa: {stage}', kqLegend: 'Legenda de cores',
    kqLegendText: 'Ponto vermelho junto ao número — contentor atrasado. Barra colorida à esquerda — etapa (nome na dica). Fundo da linha — armazém: DLT rosa, ACME verde, sem armazém branco.',
    userNoEmail: 'Sem endereço de e-mail',
  },
})
