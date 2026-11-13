"""Case types, with suggested folders and branch types (docs/case-management/02 §D).

All types of cases are accepted: this is a starting list, organisations can use their own type codes,
and anything not listed gets the general template. Nothing here is required for a case to be valid.
"""

# Suggested kinds of evidence, for every case type. Any other short code is accepted too.
EVIDENCE_TYPES = [
    "complaint", "statement", "photograph", "screenshot", "chat-export", "audio-recording", "video-recording", "cctv",
    "document", "bank-statement", "transaction-record", "cdr", "ipdr", "network-log", "url-capture", "email",
    "device-image", "forensic-report", "seizure-memo", "medical-report", "other",
]

GENERAL_FOLDERS = [
    "case-information", "complainant", "witness-statements", "digital-evidence", "physical-evidence",
    "investigation-notes", "reports", "court-documents",
]

CASE_TYPES: dict[str, dict] = {
    "cyber_fraud": {
        "label": "Cyber / online fraud",
        "folders": ["case-information", "complainant", "digital-evidence", "cdr-analysis", "ipdr-analysis", "osint",
                    "financial-transactions", "investigation-notes", "reports", "court-documents"],
        "branch_types": ["financial-transactions", "cdr-analysis", "ipdr-analysis", "osint", "suspect-identification",
                         "timeline-reconstruction"],
    },
    "financial_fraud": {
        "label": "Financial fraud / cheating",
        "folders": ["case-information", "complainant", "financial-transactions", "documents", "investigation-notes",
                    "reports", "court-documents"],
        "branch_types": ["financial-transactions", "suspect-identification", "timeline-reconstruction"],
    },
    "theft": {"label": "Theft / burglary", "folders": GENERAL_FOLDERS + ["recovered-property"],
              "branch_types": ["suspect-identification", "cctv-review", "timeline-reconstruction"]},
    "robbery": {"label": "Robbery", "folders": GENERAL_FOLDERS + ["recovered-property"],
                "branch_types": ["suspect-identification", "cdr-analysis", "timeline-reconstruction"]},
    "murder": {"label": "Murder / homicide", "folders": GENERAL_FOLDERS + ["post-mortem", "forensic-reports"],
               "branch_types": ["suspect-identification", "forensics", "cdr-analysis", "timeline-reconstruction"]},
    "missing_person": {"label": "Missing person", "folders": ["case-information", "complainant", "last-seen",
                                                              "witness-statements", "digital-evidence", "investigation-notes", "reports"],
                       "branch_types": ["last-known-movements", "cdr-analysis", "osint", "timeline-reconstruction"]},
    "narcotics": {"label": "Narcotics", "folders": GENERAL_FOLDERS + ["seizure-records", "lab-reports"],
                  "branch_types": ["supply-chain", "financial-transactions", "cdr-analysis"]},
    "cyber_stalking": {"label": "Cyber stalking / harassment", "folders": ["case-information", "complainant",
                                                                            "digital-evidence", "osint", "ipdr-analysis",
                                                                            "investigation-notes", "reports"],
                       "branch_types": ["osint", "ipdr-analysis", "suspect-identification"]},
    "civil_dispute": {"label": "Civil dispute", "folders": ["case-information", "parties", "documents",
                                                            "correspondence", "investigation-notes", "reports"],
                      "branch_types": ["documents-review", "timeline-reconstruction"]},
    "other": {"label": "Other", "folders": GENERAL_FOLDERS,
              "branch_types": ["suspect-identification", "timeline-reconstruction"]},
}


def case_type(code: str) -> dict:
    """The template for a case type; unknown codes get the general one (all types are accepted)."""
    return CASE_TYPES.get(code, {"label": code.replace("_", " ").capitalize(), "folders": GENERAL_FOLDERS,
                                 "branch_types": CASE_TYPES["other"]["branch_types"]})
