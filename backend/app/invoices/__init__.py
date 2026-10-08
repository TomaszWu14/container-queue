"""Faktury (CIPL) → Excel — lokalny pipeline (dawniej zewnętrzna aplikacja Compare).

Kroki: `splitter` (PDF-zestaw → faktura / proforma / packing lista), `extractor`
(tabela pozycji z warstwy tekstowej PDF — pdfplumber, bez OCR), `packing_list` (wagi per
REF), `matching` (REF → master data materiałów + przeliczniki JM), `pipeline`
(orkiestracja + zatwierdzanie), `excel` (arkusz o stałym kontrakcie 11 kolumn),
`master_import` (import słownika materiałów z xlsx).
"""
