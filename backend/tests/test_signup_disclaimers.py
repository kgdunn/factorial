"""Tests for the signup disclaimer acceptance field.

Uses the SignupSubmitRequest schema directly so no DB/HTTP fixtures are
needed — validation lives entirely in Pydantic.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.signup import SignupSubmitRequest


def _base_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "email": "applicant@example.com",
        "use_case": "I want to run factorial designs on our reactor.",
        "requested_role": "chemical_engineer",
        "accepted_disclaimers": True,
    }
    payload.update(overrides)
    return payload


class TestAcceptedDisclaimers:
    def test_happy_path(self):
        body = SignupSubmitRequest.model_validate(_base_payload())
        assert body.accepted_disclaimers is True

    def test_missing_field_is_422(self):
        payload = _base_payload()
        del payload["accepted_disclaimers"]
        with pytest.raises(ValidationError) as exc:
            SignupSubmitRequest.model_validate(payload)
        assert any(err["loc"] == ("accepted_disclaimers",) for err in exc.value.errors())

    def test_false_is_rejected(self):
        with pytest.raises(ValidationError) as exc:
            SignupSubmitRequest.model_validate(_base_payload(accepted_disclaimers=False))
        assert any("accept" in err["msg"].lower() for err in exc.value.errors())
