from src.surface.base import ComputerSurface, SurfaceSnapshot
from src.surface.browser import BrowserSurface
from src.surface.observation import BrowserObserver, ObservedControl, StructuredObservation
from src.surface.targeting import first_matching_locator, locator_from_candidate

__all__ = [
    "BrowserObserver",
    "BrowserSurface",
    "ComputerSurface",
    "ObservedControl",
    "StructuredObservation",
    "SurfaceSnapshot",
    "first_matching_locator",
    "locator_from_candidate",
]
