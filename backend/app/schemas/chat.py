"""Case chatbot request and response."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.case_record import DISPLAY_ID_PATTERN

CHAT_DISCLAIMER = (
    "Answers are written by an AI model running on this computer, using only the sources listed. "
    "It can make mistakes: check the cited pages. It does not decide guilt, liability or what action to take."
)


class ChatTurn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    content: str = Field(max_length=4000)


class ChatRequest(BaseModel):
    """The conversation is kept by the browser and sent back each time; it is not stored on the server."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    question: str = Field(min_length=1, max_length=1000)
    history: list[ChatTurn] = Field(default_factory=list, max_length=12)
    compare_with: str | None = Field(default=None, pattern=DISPLAY_ID_PATTERN)


class ChatSource(BaseModel):
    id: str  # "S1", "S2", ... as cited in the answer
    kind: Literal["record", "passage"]  # the case's recorded facts, or a passage of a document
    case_display_id: str
    case_title: str | None
    document_id: str | None
    page_start: int | None
    page_end: int | None
    excerpt: str
    cited: bool  # the answer refers to it


class ChatAnswer(BaseModel):
    answer: str
    answered: bool  # False when the model said the records don't contain the answer
    sources: list[ChatSource]
    notices: list[str]
    model: str
    seconds: float
    disclaimer: str = CHAT_DISCLAIMER
