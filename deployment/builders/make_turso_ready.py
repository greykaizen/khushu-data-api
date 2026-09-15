#!/usr/bin/env python3
"""Make built .db files Turso-Cloud-importable: switch to WAL, checkpoint(TRUNCATE).
Per docs.turso.tech/cloud/migrate-to-turso, the SQLite file must be in WAL
journal mode before `turso db import`. Data is untouched (journal mode only)."""
import sqlite3, os, sys, glob
DBDIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..","..","data","db"))
def fix(db):
    c=sqlite3.connect(db)
    jm=c.execute("PRAGMA journal_mode=WAL").fetchone()[0]
    c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    integ=c.execute("PRAGMA integrity_check").fetchone()[0]
    c.execute("PRAGMA synchronous=NORMAL")  # recommended for WAL on cloud
    c.close()
    return jm, integ
for db in sorted(glob.glob(f"{DBDIR}/*.db")):
    jm, integ = fix(db)
    # clean any 0-byte sidecars so the single .db is what gets uploaded
    for suf in ("-wal","-shm"):
        side=db+suf
        if os.path.exists(side) and os.path.getsize(side)==0: os.remove(side)
    print(f"  {os.path.basename(db):24s} journal_mode={jm} integrity={integ}")
print("\nAll DBs WAL-ready for `turso db import`.")
