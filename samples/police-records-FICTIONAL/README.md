# FICTIONAL sample police-records export (Step 14.4)

**Everything in this folder is invented.** No real person, police station, district, FIR or event is
described. It exists only to test the police-records connector *template* before any authorised export
is available. The column names are a placeholder too (`backend/app/connectors/police_records/fields.py`).

- `records.csv`: three FIRs, one row each. The third is marked `protected_identity=yes`, so it is
  imported as confidential and without party names.
- `FICT-0001.txt`, `FICT-0002.txt`: the FIR texts of the first two.

Import (see docs/steps/14-4-police-records-connector.md):

    cd backend
    uv run python -m scripts.police_import --folder ..\samples\police-records-FICTIONAL --authorisation "FICTIONAL SAMPLE: no real data" --dry-run
