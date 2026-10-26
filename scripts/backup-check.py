"""Verify a SQLite backup can restore into a distinct temporary database."""
import sqlite3, tempfile
from pathlib import Path
source=Path(__file__).resolve().parent.parent/'data/office.sqlite3'
with tempfile.TemporaryDirectory() as d:
    backup=Path(d)/'backup.sqlite3'; restored=Path(d)/'restored.sqlite3'
    with sqlite3.connect(source) as original, sqlite3.connect(backup) as copy:
        original.backup(copy)
    with sqlite3.connect(backup) as copy, sqlite3.connect(restored) as target:
        copy.backup(target)
    with sqlite3.connect(source) as original, sqlite3.connect(restored) as target:
        assert target.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        for table in ['auth_user','office_document','office_line','office_entry','office_audit']:
            assert original.execute(f'SELECT * FROM {table} ORDER BY id').fetchall()==target.execute(f'SELECT * FROM {table} ORDER BY id').fetchall()
    print('PASS: SQLite online backup restored to a separate temporary database; integrity check and all user/document/line/ledger/audit rows match. Temporary copies removed.')
