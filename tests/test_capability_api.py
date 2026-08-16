from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from src.capability_api import CapabilityCatalog, create_app
from src.replay.models import ReplayResult


ARTIFACT = {
    "schema_version": "1.0",
    "capability": {
        "id": "member_savings_balance",
        "name": "Read Member Savings Balance",
        "description": "Return the member's savings balance.",
        "version": "1.0.0"
    },
    "target": {
        "application_family": "legacy_member_servicing",
        "surface_type": "web",
        "entry_point": "http://127.0.0.1:8000/",
        "compatible_versions": None
    },
    "inputs": {
        "member_id": {
            "type": "string",
            "required": True,
            "description": "Member identifier."
        }
    },
    "outputs": {
        "savings_balance": {
            "type": "string",
            "required": True,
            "description": "Current savings balance.",
            "extractor": {
                "strategy": "table_cell",
                "row_text": "Savings",
                "column_header": "Balance"
            }
        }
    },
    "steps": [
        {
            "id": "step_1_type",
            "action": "type",
            "target": {
                "description": "Member ID",
                "candidates": [
                    {
                        "strategy": "structural",
                        "value": 'input[name="member_id"]'
                    }
                ]
            },
            "value": {
                "kind": "parameter",
                "name": "member_id"
            },
            "checkpoint": {
                "page_title": "Member Search",
                "required_text": []
            },
            "risk": "safe"
        }
    ],
    "success_checkpoint": {
        "page_title": "Member Details",
        "required_text": ["Savings"]
    },
    "business_outcomes": []
}


def write_artifact(tmp_path: Path) -> Path:
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    path = artifact_dir / "member_savings_balance.json"
    path.write_text(
        json.dumps(ARTIFACT),
        encoding="utf-8",
    )
    return artifact_dir


class FakeInvoker:
    def __init__(self) -> None:
        self.calls = []

    async def invoke(self, *, artifact, arguments):
        self.calls.append(
            {
                "artifact_id": artifact.capability.id,
                "arguments": arguments,
            }
        )
        return ReplayResult(
            status="success",
            run_id="run_api_test",
            capability_id=artifact.capability.id,
            capability_version=artifact.capability.version,
            outputs={"savings_balance": "$2,614.09"},
        )


def test_catalog_exposes_typed_agent_tool_schema(tmp_path: Path):
    artifact_dir = write_artifact(tmp_path)
    catalog = CapabilityCatalog(artifact_dir)

    summaries = catalog.list_summaries()

    assert len(summaries) == 1
    summary = summaries[0]

    assert summary.id == "member_savings_balance"
    assert summary.input_schema == {
        "type": "object",
        "properties": {
            "member_id": {
                "type": "string",
                "description": "Member identifier.",
            }
        },
        "required": ["member_id"],
        "additionalProperties": False,
    }
    assert summary.output_schema["properties"]["savings_balance"]["type"] == "string"
    assert summary.tool_schema["type"] == "function"
    assert summary.tool_schema["name"] == "member_savings_balance"


def test_api_lists_and_describes_capabilities(tmp_path: Path):
    artifact_dir = write_artifact(tmp_path)
    client = TestClient(
        create_app(artifact_dir=str(artifact_dir))
    )

    response = client.get("/v1/capabilities")
    assert response.status_code == 200

    body = response.json()
    assert len(body["capabilities"]) == 1
    assert body["capabilities"][0]["id"] == "member_savings_balance"

    detail = client.get(
        "/v1/capabilities/member_savings_balance"
    )
    assert detail.status_code == 200
    assert detail.json()["tool_schema"]["parameters"]["required"] == [
        "member_id"
    ]


def test_api_returns_404_for_unknown_capability(tmp_path: Path):
    artifact_dir = write_artifact(tmp_path)
    client = TestClient(
        create_app(artifact_dir=str(artifact_dir))
    )

    response = client.get("/v1/capabilities/not_real")
    assert response.status_code == 404


def test_agent_can_invoke_capability_by_name_with_typed_args(
    tmp_path: Path,
):
    artifact_dir = write_artifact(tmp_path)
    invoker = FakeInvoker()

    client = TestClient(
        create_app(
            artifact_dir=str(artifact_dir),
            invoker=invoker,
        )
    )

    response = client.post(
        "/v1/capabilities/member_savings_balance/invoke",
        json={
            "arguments": {
                "member_id": "67890"
            }
        },
    )

    assert response.status_code == 200

    result = response.json()
    assert result["status"] == "success"
    assert result["outputs"] == {
        "savings_balance": "$2,614.09"
    }

    assert invoker.calls == [
        {
            "artifact_id": "member_savings_balance",
            "arguments": {
                "member_id": "67890"
            },
        }
    ]
