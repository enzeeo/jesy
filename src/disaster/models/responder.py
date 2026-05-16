"""ResponderUnit: simulated dispatch units shown on the map."""
from __future__ import annotations

from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from disaster.models.incident import Location


class ResponderType(StrEnum):
    ALS = "ALS"      # Advanced Life Support ambulance
    BLS = "BLS"      # Basic Life Support ambulance
    FIRE = "Fire"
    RESCUE = "Rescue"


class ResponderStatus(StrEnum):
    IDLE = "idle"
    ASSIGNED = "assigned"     # dispatched but not yet en route
    EN_ROUTE = "en_route"
    ON_SCENE = "on_scene"
    OUT_OF_SERVICE = "out_of_service"


class ResponderUnit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    callsign: str = Field(min_length=1, max_length=20)        # e.g., "ALS-2"
    type: ResponderType
    location: Location
    status: ResponderStatus = ResponderStatus.IDLE
    capabilities: list[str] = Field(default_factory=list, max_length=20)
    assigned_incident_id: UUID | None = None
