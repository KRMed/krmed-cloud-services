from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Hyperparameters:
    learning_rate: float
    epochs: int
    batch_size: int
    lora_rank: int
    lora_alpha: float


@dataclass
class Job:
    id: UUID
    status: JobStatus
    base_model: str
    dataset_path: str
    hyperparameters: Hyperparameters
    checkpoint_path: Optional[str]
    error_message: Optional[str]
    created_at: datetime
    updated_at: datetime
