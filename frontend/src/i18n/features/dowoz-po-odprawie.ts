// Dowóz kontenera po odprawie (hub/port → magazyn): drogowo / intermodal
import { defineFeature } from '../feature'

export default defineFeature({
  pl: { onCarriage: 'Dowóz po odprawie', transport_drogowo: 'drogowo', transport_intermodal: 'intermodal',
    histField_on_carriage: 'Dowóz po odprawie' },
  en: { onCarriage: 'On-carriage', transport_drogowo: 'road', transport_intermodal: 'intermodal',
    histField_on_carriage: 'On-carriage' },
  pt: { onCarriage: 'Transporte pós-desembaraço', transport_drogowo: 'rodoviário', transport_intermodal: 'intermodal',
    histField_on_carriage: 'Transporte pós-desembaraço' },
})
