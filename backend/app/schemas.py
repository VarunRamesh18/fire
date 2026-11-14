"""
FireGuard AI - API request models.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class ScenarioAction(BaseModel):
    """Presenter control-panel action."""

    action: Literal["ignite", "false_alarm", "inject_smoke", "set_distance", "select_clips",
                    "pause", "resume", "reset"]
    fire_clip: Optional[str] = None
    normal_clip: Optional[str] = None
    distance_m: Optional[float] = Field(default=None, ge=0.2, le=12.0)
    duration_s: Optional[float] = Field(default=None, gt=0, le=60)
