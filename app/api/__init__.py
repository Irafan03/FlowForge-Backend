from importlib import import_module

__all__ = [
    "auth_router",
    "workflows_router",
    "executions_router",
    "webhooks_router",
    "credentials_router",
]


def __getattr__(name: str):
    """Import API routers on demand instead of initializing every dependency at package import."""
    modules = {
        "auth_router": "auth",
        "workflows_router": "workflows",
        "executions_router": "executions",
        "webhooks_router": "webhooks",
        "credentials_router": "credentials",
    }
    if name not in modules:
        raise AttributeError(name)
    return getattr(import_module(f"app.api.{modules[name]}"), "router")
