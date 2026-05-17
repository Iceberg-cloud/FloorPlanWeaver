from typing import Literal

from pydantic import BaseModel, Field


class ValidationResult(BaseModel):
    hard_constraints_passed: bool = True
    notes: list[str] = Field(default_factory=list)


class DrawerDraft(BaseModel):
    drawing_state: Literal["IMAGE_READY"]
    image_url: str | None = None
    image_base64: str | None = None
    image_mime_type: str = "image/png"
    image_prompt: str
    model: str
    size: str = "1024x1024"
    validation: ValidationResult = Field(default_factory=ValidationResult)
