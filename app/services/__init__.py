from importlib import import_module

__all__ = [
    "auth_service",
    "credential_service",
    "execution_service",
    "workflow_service",
]


def __getattr__(name: str):
    """Load a service only when requested, keeping unrelated integrations isolated."""
    if name not in __all__:
        raise AttributeError(name)
    return import_module(f"app.services.{name}")
