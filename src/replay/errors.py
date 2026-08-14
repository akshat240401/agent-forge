from enum import Enum


class RuntimeCondition(str, Enum):
    MEMBER_NOT_FOUND = "member_not_found"
    TRANSIENT_SLOW_LOAD = "transient_slow_load"
    KNOWN_INTERSTITIAL = "known_interstitial"
    PERMISSION_DENIED = "permission_denied"
    UNKNOWN_UI_STATE = "unknown_ui_state"
    CHECKPOINT_FAILED = "checkpoint_failed"
