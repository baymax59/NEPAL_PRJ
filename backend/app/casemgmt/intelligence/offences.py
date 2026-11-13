"""Offence-section suggestions (docs/case-management/02 Part A "Provision extraction"; spec §21 Case Intelligence).

Two lists, both found automatically and both only prompts for the investigator:

1. Sections cited in this case: provisions detected in the documents and notes the user may see in the case
   (the existing provision patterns, app/explain/provisions.py), with where each is cited.
2. Sections cited by similar past cases: provisions that the most similar knowledge-base cases cite and this
   case doesn't (yet), with how many of them cite it and which.

Short descriptions are given for well-known sections, for orientation only: they are the common headings, not the
legal text. Nothing here is a legal assessment or a charging decision; DISCLAIMER says so on every answer.
"""

import uuid
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.access import AccessContext
from app.casemgmt.enums import TextStatus
from app.casemgmt.intelligence import index
from app.casemgmt.intelligence.scope import GENERATED_TYPES, Source
from app.casemgmt.intelligence.similar import case_passage_bar
from app.db.models import Case, DocumentProvision
from app.embeddings.model import Embedder
from app.schemas.cases import CaseFilters
from app.similar.service import QueryDocument, find_similar_cases

SIMILAR_CASES_CONSIDERED = 10
DISCLAIMER = (
    "Found automatically: sections cited in this case's documents and notes, and sections cited by the most similar past "
    "cases. They are prompts to consider, not a legal assessment or a charging decision. The descriptions are short "
    "headings for orientation: check the official text of each provision."
)

PROCEDURE = {"CrPC", "BNSS", "CPC", "Evidence Act", "BSA"}
CRIMINAL = {"IPC", "BNS", "NDPS Act", "NI Act", "PMLA", "PC Act", "Information Technology Act"}

# The common headings of well-known sections, for orientation. Keys as made by app/explain/provisions.py.
DESCRIPTIONS = {
    # Indian Penal Code, 1860
    "ipc|section|34": "Acts done by several persons in furtherance of common intention",
    "ipc|section|120B": "Punishment of criminal conspiracy",
    "ipc|section|201": "Causing disappearance of evidence of an offence, or giving false information to screen the offender",
    "ipc|section|302": "Punishment for murder",
    "ipc|section|304": "Punishment for culpable homicide not amounting to murder",
    "ipc|section|304A": "Causing death by negligence",
    "ipc|section|304B": "Dowry death",
    "ipc|section|306": "Abetment of suicide",
    "ipc|section|307": "Attempt to murder",
    "ipc|section|323": "Punishment for voluntarily causing hurt",
    "ipc|section|354": "Assault or criminal force to a woman with intent to outrage her modesty",
    "ipc|section|363": "Punishment for kidnapping",
    "ipc|section|376": "Punishment for rape",
    "ipc|section|379": "Punishment for theft",
    "ipc|section|380": "Theft in a dwelling house, etc.",
    "ipc|section|392": "Punishment for robbery",
    "ipc|section|395": "Punishment for dacoity",
    "ipc|section|406": "Punishment for criminal breach of trust",
    "ipc|section|409": "Criminal breach of trust by a public servant, banker, merchant or agent",
    "ipc|section|411": "Dishonestly receiving stolen property",
    "ipc|section|419": "Punishment for cheating by personation",
    "ipc|section|420": "Cheating and dishonestly inducing delivery of property",
    "ipc|section|467": "Forgery of a valuable security, will, etc.",
    "ipc|section|468": "Forgery for the purpose of cheating",
    "ipc|section|471": "Using as genuine a forged document or electronic record",
    "ipc|section|498A": "Husband or relative of husband subjecting a woman to cruelty",
    "ipc|section|506": "Punishment for criminal intimidation",
    # Bharatiya Nyaya Sanhita, 2023
    "bns|section|61": "Criminal conspiracy",
    "bns|section|64": "Punishment for rape",
    "bns|section|74": "Assault or criminal force to a woman with intent to outrage her modesty",
    "bns|section|85": "Husband or relative of husband subjecting a woman to cruelty",
    "bns|section|103": "Punishment for murder",
    "bns|section|105": "Punishment for culpable homicide not amounting to murder",
    "bns|section|106": "Causing death by negligence",
    "bns|section|109": "Attempt to murder",
    "bns|section|115": "Voluntarily causing hurt",
    "bns|section|137": "Kidnapping",
    "bns|section|303": "Theft",
    "bns|section|309": "Robbery",
    "bns|section|310": "Dacoity",
    "bns|section|316": "Criminal breach of trust",
    "bns|section|317": "Stolen property",
    "bns|section|318": "Cheating",
    "bns|section|319": "Cheating by personation",
    "bns|section|336": "Forgery",
    "bns|section|338": "Forgery of a valuable security, will, etc.",
    "bns|section|340": "Forged document or electronic record, and using it as genuine",
    "bns|section|351": "Criminal intimidation",
    # Information Technology Act, 2000
    "information technology act|section|43": "Penalty and compensation for damage to a computer or computer system",
    "information technology act|section|66": "Computer-related offences",
    "information technology act|section|66C": "Punishment for identity theft",
    "information technology act|section|66D": "Punishment for cheating by personation by using a computer resource",
    "information technology act|section|67": "Punishment for publishing or transmitting obscene material in electronic form",
    # Other Acts
    "ndps act|section|20": "Contravention in relation to cannabis plant and cannabis",
    "ndps act|section|21": "Contravention in relation to manufactured drugs and preparations",
    "ndps act|section|22": "Contravention in relation to psychotropic substances",
    "ni act|section|138": "Dishonour of a cheque for insufficiency of funds",
}


def category(act: str) -> str:
    if act in CRIMINAL:
        return "criminal_law"
    if act in PROCEDURE:
        return "procedure_and_evidence"
    if act == "Constitution":
        return "constitution"
    return "other_law"


def cited_here(session: Session, sources: list[Source]) -> list[dict]:
    """Provisions found in these sources, most-mentioned first, with where each is cited."""
    texts = index.texts_for(session, (s.key for s in sources))
    merged: dict[str, dict] = {}
    for source in sources:
        if source.artifact_type in GENERATED_TYPES:
            continue
        text = texts.get(source.key)
        if text is None or text.status != TextStatus.INDEXED:
            continue
        for p in text.provisions:
            found = merged.setdefault(p["key"], {"key": p["key"], "label": p["label"], "act": p["act"], "category": category(p["act"]),
                                                 "description": DESCRIPTIONS.get(p["key"]), "mentions": 0, "cited_in": []})
            found["mentions"] += p["mentions"]
            found["cited_in"].append({"display_id": source.display_id, "title": source.title, "kind": source.kind.value,
                                      "item_id": str(source.item_id), "path": source.path, "pages": p["pages"]})
    return sorted(merged.values(), key=lambda p: (p["category"] != "criminal_law", -p["mentions"], p["label"]))


def from_similar_cases(session: Session, access: AccessContext, embedder: Embedder | None, doc: QueryDocument,
                       here: set[str]) -> tuple[list[dict], int, list[str]]:
    """Provisions the most similar past cases cite that this case doesn't: (suggestions, cases considered, notices)."""
    if not doc.passages:
        return [], 0, []
    similar = find_similar_cases(session, access, embedder, doc, CaseFilters(), SIMILAR_CASES_CONSIDERED, 0, case_passage_bar(embedder))
    if not similar.results:
        return [], 0, similar.notices
    ids = dict(session.execute(select(Case.display_id, Case.id).where(
        Case.display_id.in_([r.case.display_id for r in similar.results]))).all())
    cited_by: dict[uuid.UUID, dict[str, tuple[str, str]]] = defaultdict(dict)  # case -> key -> (label, act)
    for row in session.execute(select(DocumentProvision.case_id, DocumentProvision.provision_key, DocumentProvision.label,
                                      DocumentProvision.act).where(DocumentProvision.case_id.in_(list(ids.values())))):
        cited_by[row.case_id][row.provision_key] = (row.label, row.act)
    found: dict[str, dict] = {}
    for result in similar.results:
        for key, (label, act) in cited_by.get(ids.get(result.case.display_id), {}).items():
            kind = category(act)
            # Procedure, evidence and the Constitution say how a case was handled in court, not which offence it concerns.
            if key in here or kind in ("procedure_and_evidence", "constitution"):
                continue
            suggestion = found.setdefault(key, {"key": key, "label": label, "act": act, "category": kind,
                                                "description": DESCRIPTIONS.get(key), "count": 0, "cases": []})
            suggestion["count"] += 1
            suggestion["cases"].append({"display_id": result.case.display_id, "title": result.case.title, "relevance": result.relevance})
    suggestions = sorted(found.values(), key=lambda s: (s["category"] != "criminal_law", -s["count"], s["label"]))
    return suggestions, len(similar.results), similar.notices
