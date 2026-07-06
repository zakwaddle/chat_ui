from __future__ import annotations

try:
    from .models import FUTURE_MEMORY_LAYERS
except ImportError:
    from models import FUTURE_MEMORY_LAYERS


def list_future_memory_layers() -> list[dict[str, str]]:
    return [
        {
            "name": layer.name,
            "table_name": layer.table_name,
            "purpose": layer.purpose,
        }
        for layer in FUTURE_MEMORY_LAYERS
    ]
