"""Request and response schemas."""
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt

Binary = Annotated[StrictInt, Field(ge=0, le=1)]


class PatientFeatures(BaseModel):
    """The 21 BRFSS health indicators.

    extra="forbid" plus StrictInt means unknown fields and wrong types are
    rejected rather than silently coerced.
    """

    model_config = ConfigDict(extra="forbid")

    HighBP: Binary
    HighChol: Binary
    CholCheck: Binary
    BMI: Annotated[StrictInt, Field(ge=12, le=98)]
    Smoker: Binary
    Stroke: Binary
    HeartDiseaseorAttack: Binary
    PhysActivity: Binary
    Fruits: Binary
    Veggies: Binary
    HvyAlcoholConsump: Binary
    AnyHealthcare: Binary
    NoDocbcCost: Binary
    GenHlth: Annotated[StrictInt, Field(ge=1, le=5)]
    MentHlth: Annotated[StrictInt, Field(ge=0, le=30)]
    PhysHlth: Annotated[StrictInt, Field(ge=0, le=30)]
    DiffWalk: Binary
    Sex: Binary
    Age: Annotated[StrictInt, Field(ge=1, le=13)]
    Education: Annotated[StrictInt, Field(ge=1, le=6)]
    Income: Annotated[StrictInt, Field(ge=1, le=8)]


class BatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    records: list[PatientFeatures] = Field(min_length=1)


class PredictionResponse(BaseModel):

    inference_id: int
    predicted_class: int
    predicted_label: str
    probability: float
    model_version: str
    preprocessing_version: str
    timestamp: datetime
    input_hash: str
    latency_ms: float
    input: dict


class RowResult(BaseModel):
    """One row of a batch: either a prediction or the reason it failed."""

    row_index: int
    status: Literal["success", "error"]
    predicted_class: int | None = None
    predicted_label: str | None = None
    probability: float | None = None
    input_hash: str | None = None
    errors: list[dict] | None = None


class BatchResponse(BaseModel):
    batch_id: int
    model_version: str
    preprocessing_version: str
    timestamp: datetime
    row_count: int
    success_count: int
    error_count: int
    results: list[RowResult]


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    role: str


class UserResponse(BaseModel):
    username: str
    role: str


class ModelVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: int
    version: str
    display_name: str
    framework: str
    status: str
    preprocessing_version: str
    metrics: dict | None
    notes: str | None
    created_at: datetime


class PromotionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = None


class PromotionEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: int
    version: str
    action: str
    from_status: str
    to_status: str
    performed_by: str
    reason: str | None
    created_at: datetime


class InferenceLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: int
    batch_id: int | None
    row_index: int | None
    model_version: str
    requested_by: str
    request_type: str
    predicted_class: int | None
    probability: float | None
    latency_ms: float | None
    status: str
    error_message: str | None
    input_hash: str | None
    input_json: dict | None
    created_at: datetime


class BatchSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: int
    filename: str
    source: str
    uploaded_by: str
    model_version: str
    row_count: int
    success_count: int
    error_count: int
    created_at: datetime


class BatchDetailResponse(BatchSummaryResponse):
    logs: list[InferenceLogResponse]
