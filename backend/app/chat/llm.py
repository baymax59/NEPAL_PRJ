"""Talking to the local language model (Ollama). Nothing is sent to an outside service."""

import json
import time
from collections.abc import Callable
from typing import Protocol

import httpx

from app.core.config import get_settings


class ChatModelUnavailable(Exception):
    """The model server is down, the model isn't installed, or it took too long."""


class ChatModel(Protocol):
    name: str

    def complete(self, messages: list[dict[str, str]]) -> str: ...


class OllamaChatModel:
    def __init__(
        self,
        base_url: str,
        name: str,
        timeout_seconds: int,
        transport: httpx.BaseTransport | None = None,  # tests pass a fake Ollama
        clock: Callable[[], float] = time.monotonic,
    ):
        self.base_url = base_url.rstrip("/")
        self.name = name
        self.timeout = timeout_seconds
        self.transport = transport
        self.clock = clock

    def complete(self, messages: list[dict[str, str]]) -> str:
        """The whole answer. `timeout_seconds` limits the total time, not just the wait for the first word.

        The answer arrives piece by piece (streamed), so the limit is checked as it comes in. Stopping
        early closes the connection, which also stops Ollama working on the answer.
        """
        deadline = self.clock() + self.timeout
        body = {
            "model": self.name,
            "messages": messages,
            "stream": True,
            "keep_alive": "30m",  # stay loaded between questions
            # Low temperature: stick closely to the sources. Short answers are faster on a CPU.
            "options": {"temperature": 0.1, "num_ctx": 8192, "num_predict": 400},
        }
        parts: list[str] = []
        finished = False
        # Each message says what to do about it, for whoever runs this computer.
        try:
            with httpx.Client(transport=self.transport, timeout=httpx.Timeout(self.timeout, connect=10)) as client:
                with client.stream("POST", f"{self.base_url}/api/chat", json=body) as response:
                    if response.status_code == 404:
                        raise ChatModelUnavailable(
                            f"The chat model '{self.name}' is not installed. Run: ollama pull {self.name}"
                        )
                    if response.status_code != 200:
                        raise ChatModelUnavailable(f"The chat model returned an error (HTTP {response.status_code})")
                    for line in response.iter_lines():
                        if self.clock() > deadline:
                            raise self._too_slow()
                        if not line.strip():
                            continue
                        piece = json.loads(line)
                        if "error" in piece:
                            raise ChatModelUnavailable(f"The chat model returned an error ({str(piece['error'])[:200]})")
                        parts.append(piece.get("message", {}).get("content", ""))
                        if piece.get("done"):
                            finished = True
                            break
        except httpx.TimeoutException as exc:
            raise self._too_slow() from exc
        except httpx.ConnectError as exc:
            raise ChatModelUnavailable("The chat model is not running. Start Ollama and try again.") from exc
        except httpx.HTTPError as exc:
            raise ChatModelUnavailable(f"The chat model could not be reached ({type(exc).__name__})") from exc
        except ValueError as exc:  # a line that isn't JSON
            raise ChatModelUnavailable("The chat model sent a reply that could not be read.") from exc
        if not finished:
            # Never pass on half an answer as if it were complete.
            raise ChatModelUnavailable("The chat model stopped before finishing its answer. Try again.")
        return "".join(parts)

    def _too_slow(self) -> ChatModelUnavailable:
        return ChatModelUnavailable(
            f"The chat model took longer than {self.timeout} seconds to answer. "
            "The computer may be busy with another question; try again in a few minutes."
        )


def get_chat_model() -> ChatModel:
    """FastAPI dependency (tests replace it with a fake)."""
    settings = get_settings()
    return OllamaChatModel(settings.ollama_url, settings.chat_model, settings.chat_timeout_seconds)
