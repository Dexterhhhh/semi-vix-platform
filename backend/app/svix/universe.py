"""Extendable composition definitions for the semiconductor index."""

from app.svix.constants import AI_WEIGHTS, CORE_WEIGHTS, MEMORY_WEIGHTS

DEFAULT_UNIVERSE = tuple((*CORE_WEIGHTS, *MEMORY_WEIGHTS, *AI_WEIGHTS))
COMPONENT_ASSETS = {
    "core": CORE_WEIGHTS,
    "memory": MEMORY_WEIGHTS,
    "ai": AI_WEIGHTS,
}
