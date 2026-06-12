# Re-export for backwards compatibility — Activity model lives in activity.py
from app.models.activity import ACTIVITY_TYPES, Activity

__all__ = ["Activity", "ACTIVITY_TYPES"]
