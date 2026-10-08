import { defineFeature } from '../feature'

// Podpowiedzi „dlaczego nieaktywny” dla przycisków zapisu na karcie kontenera (audyt UI A31)
export default defineFeature({
  pl: { hintTypeMessage: 'Wpisz treść wiadomości', hintTypeCustomer: 'Wpisz nazwę klienta',
    hintChangeStatus: 'Wybierz inny status, aby zapisać' },
  en: { hintTypeMessage: 'Type a message', hintTypeCustomer: 'Type the customer name',
    hintChangeStatus: 'Choose a different status to save' },
  pt: { hintTypeMessage: 'Escreva a mensagem', hintTypeCustomer: 'Escreva o nome do cliente',
    hintChangeStatus: 'Escolha outro estado para guardar' },
})
