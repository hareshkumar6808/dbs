from typing import Literal
from pydantic import BaseModel, Field, model_validator


class Simulation(BaseModel):
    disruption_type: Literal["RUNWAY_CLOSURE", "AIRPORT_CLOSURE", "SEVERE_WEATHER"]
    airport_id: int = Field(gt=0)
    runway_id: int | None = Field(default=None, gt=0)
    severity: int = Field(default=4, ge=1, le=5)
    duration_minutes: int = Field(default=120, ge=15, le=720)

    @model_validator(mode="after")
    def runway_required(self):
        if self.disruption_type == "RUNWAY_CLOSURE" and self.runway_id is None:
            raise ValueError("Choose a runway for a runway closure")
        return self


class CopilotQuestion(BaseModel):
    question: str = Field(min_length=3, max_length=300)
