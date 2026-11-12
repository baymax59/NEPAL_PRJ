"""PLACEHOLDER field list for an authorised police-records export (Step 14.4).

Nothing here comes from a real system. The column names are an assumption, modelled on the fields an
Indian FIR register usually has, so the mapping and its tests can be built before access is granted.
**Every line must be checked against the real export, with the data owner, before any real data is
imported.** The questions to ask are in docs/steps/14-4-police-records-connector.md.

The export is assumed to be a folder holding records.csv (UTF-8, one row per FIR, header row) and,
optionally, one document per FIR (PDF, Word or text), named in the fir_document column.
"""

SOURCE_SYSTEM = "police_records"
CONNECTOR_VERSION = "0.1-template"  # bump whenever the mapping changes
RAW_DIR = "police_raw"  # under the data folder: data/police_raw/<export folder>/
RECORDS_FILE = "records.csv"

# Identity: an FIR number is unique within one police station and one year.
ID_FIELDS = ("police_station_code", "fir_year", "fir_number")

# Export column -> where it goes. "personal data" marks columns that identify people.
FIELDS = {
    "fir_number": "reference_numbers.fir_number (and the case ID)",
    "fir_year": "the case ID",
    "police_station_code": "reference_numbers.police_station_code (and the case ID)",
    "police_station_name": "court_or_agency",
    "district": "source_extra.district",
    "registration_date": "dates: registration (the main date: sorting and year filters)",
    "occurrence_date": "dates: occurrence",
    "acts_sections": "category, e.g. 'BNS 318(4), 316(2)'",
    "complainant_name": "parties: complainant (personal data)",
    "accused_names": "parties: accused, separated by ';' (personal data)",
    "investigating_officer": "officials: investigating_officer",
    "investigation_status": "status",
    "final_report_type": "outcome, e.g. 'Chargesheet filed', 'Closure report'",
    "final_report_date": "outcome date; dates: final_report",
    "brief_facts": "summary (personal data: the narrative names people)",
    "sensitivity": "sensitivity: 'confidential' is kept; anything else becomes 'restricted'",
    "protected_identity": "yes/true/1: identities protected by law -> confidential, names not imported",
    "fir_document": "documents: file name inside the export folder (PDF, .docx or .txt)",
}

# Values meaning "yes" in flag columns such as protected_identity.
YES = {"yes", "y", "true", "1"}

# Date formats tried in order. Numeric dates are day first, the Indian convention.
DATE_FORMATS = ("%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y", "%Y-%m-%d")
