import { defineFeature } from '../feature'

// Master data → Wzory plików dla agencji (pages/masterdata/AgencyTemplatesTab.tsx)
export default defineFeature({
  pl: {
    atplTitle: 'Wzory plików dla agencji',
    atplInfo: 'Jaki plik przyjmuje agencja: kolumny w kolejności, skąd aplikacja bierze dane i które są wymagane. Gdy agencja zmieni wzór — wgraj nowy plik albo popraw kolumny tutaj.',
    atplLayout: 'Układ', atplLayoutText: 'arkusz „{sheet}”, {n} kolumn (wymagane: {req}), wiersz 1 = nagłówki, dalej jeden wiersz na materiał.',
    atplCol: 'Kol.', atplName: 'Nazwa kolumny', atplSource: 'Skąd dane', atplValue: 'Wartość', atplRequired: 'Wymagana',
    atplExample: 'Przykład z wzoru', atplNote: 'Uwagi', atplUp: 'W górę', atplDown: 'W dół', atplAdd: 'Dodaj kolumnę',
    atplUnsaved: 'Niezapisane zmiany', atplSaved: 'Wzór zapisany.', atplSampleSaved: 'Nowy wzór wgrany — kolumny z pliku, mapowanie znanych kolumn zachowane.',
    atplUpload: 'Wgraj nowy wzór (.xlsx)', atplDownload: 'Pobierz wzór agencji',
  },
  en: {
    atplTitle: 'Agency file templates',
    atplInfo: 'Which file the agency accepts: columns in order, where the app takes the data from and which are required. When the agency changes the template — upload the new file or edit the columns here.',
    atplLayout: 'Layout', atplLayoutText: 'sheet “{sheet}”, {n} columns (required: {req}), row 1 = headers, then one row per material.',
    atplCol: 'Col.', atplName: 'Column name', atplSource: 'Data source', atplValue: 'Value', atplRequired: 'Required',
    atplExample: 'Example from template', atplNote: 'Notes', atplUp: 'Up', atplDown: 'Down', atplAdd: 'Add column',
    atplUnsaved: 'Unsaved changes', atplSaved: 'Template saved.', atplSampleSaved: 'New template uploaded — columns from the file, mapping of known columns kept.',
    atplUpload: 'Upload new template (.xlsx)', atplDownload: 'Download agency template',
  },
  pt: {
    atplTitle: 'Modelos de ficheiros do despachante',
    atplInfo: 'Que ficheiro o despachante aceita: colunas por ordem, de onde a aplicação tira os dados e quais são obrigatórias. Quando o despachante mudar o modelo — carregue o novo ficheiro ou edite as colunas aqui.',
    atplLayout: 'Estrutura', atplLayoutText: 'folha “{sheet}”, {n} colunas (obrigatórias: {req}), linha 1 = cabeçalhos, depois uma linha por material.',
    atplCol: 'Col.', atplName: 'Nome da coluna', atplSource: 'Origem dos dados', atplValue: 'Valor', atplRequired: 'Obrigatória',
    atplExample: 'Exemplo do modelo', atplNote: 'Notas', atplUp: 'Subir', atplDown: 'Descer', atplAdd: 'Adicionar coluna',
    atplUnsaved: 'Alterações não guardadas', atplSaved: 'Modelo guardado.', atplSampleSaved: 'Novo modelo carregado — colunas do ficheiro, mapeamento das colunas conhecidas mantido.',
    atplUpload: 'Carregar novo modelo (.xlsx)', atplDownload: 'Descarregar modelo do despachante',
  },
})
