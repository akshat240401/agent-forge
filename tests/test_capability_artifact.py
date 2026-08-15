
import pytest
from pydantic import ValidationError
from src.capability import CheckpointSpec

def test_checkpoint_requires_assertion():
    with pytest.raises(ValidationError):
        CheckpointSpec()
