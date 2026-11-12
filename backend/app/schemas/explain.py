"""Request and response for "why did this case match?"."""

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.cases import CaseSummary, ProvisionCitation
from app.schemas.search import Passage


class ExplainRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    query: str = Field(min_length=1, max_length=500)


class TermMatch(BaseModel):
    term: str  # as typed in the search
    passages: int  # how many passages of the case contain it


class MatchExplanation(BaseModel):
    """Details-page section E ("AI similarity analysis"). Every item can be checked in the source."""

    case: CaseSummary
    query: str
    reasons: list[str]  # the short version, also shown on the result card
    shared_terms: list[TermMatch]
    missing_terms: list[str]
    shared_provisions: list[ProvisionCitation]  # cited by the case and named in the search
    provisions_only_in_query: list[str]
    case_provisions: list[ProvisionCitation]  # what the case cites most (automatically detected)
    passages: list[Passage]  # closest in meaning and/or wording, with pages
    differences: list[str]
    notices: list[str]
    method_note: str  # how this was produced and its limits: show it with the explanation
