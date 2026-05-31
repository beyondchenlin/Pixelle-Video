from __future__ import annotations

from pydantic import BaseModel, Field

from web.utils.streamlit_helpers import build_model_from_form, populate_form_from_model


class _ExampleModel(BaseModel):
    title: str = ""
    tags: list[str] = Field(default_factory=list)


class _ExampleKeys:
    title = "example_title"
    tags = "example_tags"


def test_populate_form_from_model_accepts_explicit_session_state() -> None:
    session_state: dict[str, str] = {}

    populate_form_from_model(
        _ExampleModel(title="hello", tags=["a", "b"]),
        _ExampleKeys,
        session_state=session_state,
    )

    assert session_state == {"example_title": "hello", "example_tags": "a, b"}


def test_build_model_from_form_accepts_explicit_session_state() -> None:
    session_state = {"example_title": "hello", "example_tags": "a, b"}

    model = build_model_from_form(
        _ExampleModel,
        _ExampleKeys,
        session_state=session_state,
    )

    assert model == _ExampleModel(title="hello", tags=["a", "b"])
