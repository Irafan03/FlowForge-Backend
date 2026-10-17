from importlib import import_module

__all__ = [
    "fire_manual_trigger",
    "fire_webhook_trigger",
    "fire_due_schedules",
    "compute_next_run",
]


def __getattr__(name: str):
    """Import trigger modules on demand so integrations do not require scheduler extras."""
    modules = {
        "fire_manual_trigger": "manual",
        "fire_webhook_trigger": "webhook",
        "fire_due_schedules": "schedule",
        "compute_next_run": "schedule",
    }
    if name not in modules:
        raise AttributeError(name)
    return getattr(import_module(f"app.triggers.{modules[name]}"), name)
