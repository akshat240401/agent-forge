
from src.agent.models import DiscoveryDecision, DiscoveryOutput, DiscoveryResult, DiscoveryStep
from src.capability import CapabilityCompiler, CompilerConfig, InputBinding, ParameterValue, TableOutputRule
from src.models import ActionType, CapabilityValueType

def sample_discovery():
    return DiscoveryResult(
        status="success", run_id="run_test",
        steps=[
            DiscoveryStep(
                step_number=1, page_url="http://127.0.0.1:8000/", page_title="Member Search",
                decision=DiscoveryDecision(action=ActionType.TYPE, control_index=0, value="12345", reason="Enter member."),
                target={"description":"textbox / Member ID","candidates":[{"strategy":"structural","value":'input[name="member_id"]'}]},
                observed_text=["Member Search","Member ID","Search"],
            ),
            DiscoveryStep(
                step_number=2, page_url="http://127.0.0.1:8000/", page_title="Member Search",
                decision=DiscoveryDecision(action=ActionType.CLICK, control_index=1, reason="Search."),
                target={"description":"button / Search","candidates":[{"strategy":"role_name","value":"button|Search"}]},
                observed_text=["Member Search","Member ID","Search"],
            ),
            DiscoveryStep(
                step_number=3, page_url="http://127.0.0.1:8000/members/search", page_title="Member Details",
                decision=DiscoveryDecision(
                    action=ActionType.FINISH, reason="Done.",
                    result=[DiscoveryOutput(name="savings_balance", value="$4,821.37")]
                ),
                target=None, observed_text=["Member Record","Accounts","Savings","$4,821.37"],
            )
        ],
        outputs={"savings_balance":"$4,821.37"}
    )

def cfg():
    return CompilerConfig(
        capability_id="member_savings_balance",
        capability_name="Read Member Savings Balance",
        description="Lookup balance.",
        version="1.0.0",
        application_family="legacy_member_servicing",
        entry_point="http://127.0.0.1:8000/",
        inputs=(InputBinding(name="member_id", sample_value="12345", description="Member ID"),),
        outputs=(TableOutputRule(name="savings_balance", row_text="Savings", column_header="Balance", description="Savings balance"),),
    )

def test_compiler_parameterizes_sample_literal():
    artifact = CapabilityCompiler().compile(sample_discovery(), cfg())
    assert isinstance(artifact.steps[0].value, ParameterValue)
    assert artifact.steps[0].value.name == "member_id"
    assert '"12345"' not in artifact.model_dump_json()

def test_compiler_preserves_order_and_targets():
    artifact = CapabilityCompiler().compile(sample_discovery(), cfg())
    assert [s.action for s in artifact.steps] == [ActionType.TYPE, ActionType.CLICK]
    assert artifact.steps[1].target.candidates[0].value == "button|Search"

def test_compiler_adds_output_extractor_and_success_checkpoint():
    artifact = CapabilityCompiler().compile(sample_discovery(), cfg())
    out = artifact.outputs["savings_balance"]
    assert out.extractor.row_text == "Savings"
    assert out.extractor.column_header == "Balance"
    assert artifact.success_checkpoint.page_title == "Member Details"
    assert "Savings" in artifact.success_checkpoint.required_text
