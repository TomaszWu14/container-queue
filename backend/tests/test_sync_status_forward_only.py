"""Synchronizacja z Excela tylko do przodu (decyzja 2026-09-28) — nieaktualny arkusz nie cofa statusu."""
from app.importers.queue import _synced_status
from app.models import ContainerStatus as S


def test_sync_never_moves_status_back():
    assert _synced_status(S.AWIZOWANY, S.W_PORCIE) == S.AWIZOWANY          # wcześniej cofało
    assert _synced_status(S.W_DOSTAWIE, S.W_TRANSPORCIE) == S.W_DOSTAWIE
    assert _synced_status(S.W_PORCIE, S.AWIZOWANY) == S.AWIZOWANY          # do przodu — tak
