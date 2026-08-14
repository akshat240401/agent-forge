\
from src.policy import redact, redact_text


def test_redact_text_masks_common_sensitive_values():
    value = (
        "email=person@example.com "
        "ssn=123-45-6789 "
        "Authorization: Bearer abc.def.ghi "
        "api_key=supersecret"
    )

    redacted = redact_text(value)

    assert "person@example.com" not in redacted
    assert "123-45-6789" not in redacted
    assert "abc.def.ghi" not in redacted
    assert "supersecret" not in redacted


def test_recursive_redaction_masks_secret_fields_without_mutating_shape():
    payload = {
        "member_id": "12345",
        "token": "secret-token",
        "nested": {
            "password": "secret-password",
            "message": "contact person@example.com",
        },
    }

    safe = redact(payload)

    assert safe["member_id"] == "12345"
    assert safe["token"] == "[REDACTED]"
    assert safe["nested"]["password"] == "[REDACTED]"
    assert safe["nested"]["message"] == "contact [EMAIL_REDACTED]"
