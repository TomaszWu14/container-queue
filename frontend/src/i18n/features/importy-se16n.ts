// Plakietki tabel SE16N przy importach z SAP (SapSource.tsx)
import { defineFeature } from '../feature'

export default defineFeature({
  pl: {
    se16nSource: 'Źródło w SAP',
    se16n_EKKO: 'SE16N → EKKO\nNagłówki zamówień: dostawca (LIFNR), waluta, Incoterms, daty.\nKlucz: Dok.zaopatrz.',
    se16n_EKPO: 'SE16N → EKPO\nPozycje zamówień: materiał, ilość, jednostka, wagi.\nKlucz: Dok.zaopatrz. + Pozycja.',
    se16n_MARM: 'SE16N → MARM\nJednostki materiału: przeliczniki, wymiary, wagi, EAN. Zakłada materiały do dopasowania faktur.\nKlucz: Materiał + Alternatywna jednostka miary.',
    se16n_LFA1: 'SE16N → LFA1\nKartoteka dostawców: kod SAP, nazwa, kraj, adres, NIP.\nKlucz: Dostawca.',
  },
  en: {
    se16nSource: 'SAP source',
    se16n_EKKO: 'SE16N → EKKO\nPurchase order headers: vendor (LIFNR), currency, Incoterms, dates.\nKey: purchasing document.',
    se16n_EKPO: 'SE16N → EKPO\nPurchase order items: material, quantity, unit, weights.\nKey: purchasing document + item.',
    se16n_MARM: 'SE16N → MARM\nMaterial units: conversions, dimensions, weights, EAN. Creates materials for invoice matching.\nKey: material + alternative unit.',
    se16n_LFA1: 'SE16N → LFA1\nVendor master: SAP code, name, country, address, VAT no.\nKey: vendor.',
  },
  pt: {
    se16nSource: 'Origem no SAP',
    se16n_EKKO: 'SE16N → EKKO\nCabeçalhos de pedidos: fornecedor (LIFNR), moeda, Incoterms, datas.\nChave: documento de compra.',
    se16n_EKPO: 'SE16N → EKPO\nItens de pedidos: material, quantidade, unidade, pesos.\nChave: documento de compra + item.',
    se16n_MARM: 'SE16N → MARM\nUnidades do material: conversões, dimensões, pesos, EAN. Cria materiais para a conciliação de faturas.\nChave: material + unidade alternativa.',
    se16n_LFA1: 'SE16N → LFA1\nCadastro de fornecedores: código SAP, nome, país, endereço, NIF.\nChave: fornecedor.',
  },
})
