#!/usr/bin/env python
"""W14 #47: CLI weryfikacji backupu — cienki wrapper na app.backup_verify.

Użycie (w kontenerze): python scripts/verify_backup.py
Exit code: 0 = ok/skip, 1 = błąd (dump nieodtwarzalny / rozjazd wierszy).
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.backup_verify import verify_backup  # noqa: E402

if __name__ == "__main__":
    result = verify_backup()
    print(result)
    sys.exit(0 if result["status"] in ("ok", "skip") else 1)
