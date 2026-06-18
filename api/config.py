# Copyright (C) 2025 AIDC-AI
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""API Configuration."""

import os
from typing import Literal, Optional

from pydantic import BaseModel, model_validator


class APIConfig(BaseModel):
    """API configuration"""
    
    # Runtime profile
    runtime_profile: Literal["dev", "production"] = "dev"

    # Server settings
    host: str = "0.0.0.0"
    port: int = 8888
    reload: bool = False
    
    # CORS settings
    cors_enabled: bool = True
    cors_origins: list[str] = ["*"]
    
    # Task settings
    max_concurrent_tasks: int = 5
    task_cleanup_interval: int = 3600  # Clean completed tasks every hour
    task_retention_time: int = 86400   # Keep task results for 24 hours
    task_backend: Literal["memory", "postgres"] = "memory"
    postgres_dsn: Optional[str] = None
    redis_url: Optional[str] = None
    require_distributed_coordination: bool = False
    generation_lease_ttl_seconds: int = 120
    generation_heartbeat_seconds: int = 30
    generation_submit_lock_wait_seconds: float = 2.0
    generation_submit_lock_poll_seconds: float = 0.05
    completed_reuse_seconds: int = 86400
    execution_mode: Literal["embedded", "worker"] = "embedded"
    worker_poll_interval_seconds: float = 2.0

    # Artifact settings
    artifact_backend: Literal["local", "s3"] = "local"
    artifact_base_url: str = "/api/files"
    artifact_base_path: str = "output"
    artifact_object_store_endpoint_url: Optional[str] = None
    artifact_object_store_bucket: Optional[str] = None
    
    # File upload settings
    max_upload_size: int = 100 * 1024 * 1024  # 100MB

    # Reference image gray API settings
    reference_image_api_enabled: bool = False
    reference_image_upload_base_path: str = "_runtime/reference_image_uploads"
    reference_image_max_upload_size_mb: int = 20
    reference_image_max_edge_px: int = 8192
    reference_image_max_pixels: int = 40_000_000
    reference_image_upload_ttl_seconds: int = 7 * 24 * 60 * 60
    
    # API settings
    api_prefix: str = "/api"
    docs_url: Optional[str] = "/docs"
    redoc_url: Optional[str] = "/redoc"
    openapi_url: Optional[str] = "/openapi.json"

    @classmethod
    def from_env(cls) -> "APIConfig":
        """Build API config from PIXELLE_* environment variables."""
        return cls(
            host=_env_str("PIXELLE_API_HOST", default="0.0.0.0"),
            port=_env_int("PIXELLE_API_PORT", default=8888),
            reload=_env_bool("PIXELLE_API_RELOAD", default=False),
            runtime_profile=_env_str("PIXELLE_RUNTIME_PROFILE", default="dev"),
            task_backend=_env_str("PIXELLE_TASK_BACKEND", default="memory"),
            postgres_dsn=os.getenv("PIXELLE_POSTGRES_DSN"),
            redis_url=os.getenv("PIXELLE_REDIS_URL"),
            require_distributed_coordination=_env_bool(
                "PIXELLE_REQUIRE_DISTRIBUTED_COORDINATION",
                default=False,
            ),
            generation_lease_ttl_seconds=_env_int(
                "PIXELLE_GENERATION_LEASE_TTL_SECONDS",
                default=120,
            ),
            generation_heartbeat_seconds=_env_int(
                "PIXELLE_GENERATION_HEARTBEAT_SECONDS",
                default=30,
            ),
            generation_submit_lock_wait_seconds=_env_float(
                "PIXELLE_GENERATION_SUBMIT_LOCK_WAIT_SECONDS",
                default=2.0,
            ),
            generation_submit_lock_poll_seconds=_env_float(
                "PIXELLE_GENERATION_SUBMIT_LOCK_POLL_SECONDS",
                default=0.05,
            ),
            completed_reuse_seconds=_env_int(
                "PIXELLE_COMPLETED_REUSE_SECONDS",
                default=86400,
            ),
            execution_mode=_env_str("PIXELLE_EXECUTION_MODE", default="embedded"),
            worker_poll_interval_seconds=_env_float(
                "PIXELLE_WORKER_POLL_INTERVAL_SECONDS",
                default=2.0,
            ),
            artifact_backend=_env_str("PIXELLE_ARTIFACT_BACKEND", default="local"),
            artifact_base_url=os.getenv("PIXELLE_ARTIFACT_BASE_URL", "/api/files"),
            artifact_base_path=os.getenv("PIXELLE_ARTIFACT_BASE_PATH", "output"),
            artifact_object_store_endpoint_url=os.getenv(
                "PIXELLE_ARTIFACT_OBJECT_STORE_ENDPOINT_URL"
            ),
            artifact_object_store_bucket=os.getenv("PIXELLE_ARTIFACT_OBJECT_STORE_BUCKET"),
            reference_image_api_enabled=_env_bool(
                "PIXELLE_REFERENCE_IMAGE_API_ENABLED",
                default=False,
            ),
            reference_image_upload_base_path=_env_str(
                "PIXELLE_REFERENCE_IMAGE_UPLOAD_BASE_PATH",
                default="_runtime/reference_image_uploads",
            ),
            reference_image_max_upload_size_mb=_env_int(
                "PIXELLE_REFERENCE_IMAGE_MAX_UPLOAD_SIZE_MB",
                default=20,
            ),
            reference_image_max_edge_px=_env_int(
                "PIXELLE_REFERENCE_IMAGE_MAX_EDGE_PX",
                default=8192,
            ),
            reference_image_max_pixels=_env_int(
                "PIXELLE_REFERENCE_IMAGE_MAX_PIXELS",
                default=40_000_000,
            ),
            reference_image_upload_ttl_seconds=_env_int(
                "PIXELLE_REFERENCE_IMAGE_UPLOAD_TTL_SECONDS",
                default=7 * 24 * 60 * 60,
            ),
        )

    @model_validator(mode="after")
    def validate_distributed_timing(self) -> "APIConfig":
        if self.generation_heartbeat_seconds >= self.generation_lease_ttl_seconds:
            raise ValueError(
                "generation_heartbeat_seconds must be less than generation_lease_ttl_seconds"
            )
        if self.generation_submit_lock_poll_seconds <= 0:
            raise ValueError("generation_submit_lock_poll_seconds must be greater than 0")
        if self.generation_submit_lock_wait_seconds < self.generation_submit_lock_poll_seconds:
            raise ValueError(
                "generation_submit_lock_wait_seconds must be greater than or equal to generation_submit_lock_poll_seconds"
            )
        return self

    @model_validator(mode="after")
    def validate_reference_image_upload_settings(self) -> "APIConfig":
        if self.reference_image_max_upload_size_mb < 1:
            raise ValueError("reference_image_max_upload_size_mb must be at least 1")
        if self.reference_image_max_edge_px < 1:
            raise ValueError("reference_image_max_edge_px must be at least 1")
        if self.reference_image_max_pixels < 1:
            raise ValueError("reference_image_max_pixels must be at least 1")
        if self.reference_image_upload_ttl_seconds < 0:
            raise ValueError("reference_image_upload_ttl_seconds must be greater than or equal to 0")
        return self

    @model_validator(mode="after")
    def validate_runtime_profile(self) -> "APIConfig":
        if self.runtime_profile != "production":
            return self

        missing: list[str] = []
        if self.task_backend != "postgres":
            missing.append("PIXELLE_TASK_BACKEND=postgres")
        if _is_blank(self.postgres_dsn):
            missing.append("PIXELLE_POSTGRES_DSN")
        if _is_blank(self.redis_url):
            missing.append("PIXELLE_REDIS_URL")
        if self.artifact_backend != "s3":
            missing.append("PIXELLE_ARTIFACT_BACKEND=s3")
        if _is_blank(self.artifact_object_store_endpoint_url):
            missing.append("PIXELLE_ARTIFACT_OBJECT_STORE_ENDPOINT_URL")
        if _is_blank(self.artifact_object_store_bucket):
            missing.append("PIXELLE_ARTIFACT_OBJECT_STORE_BUCKET")

        if missing:
            joined = ", ".join(missing)
            raise ValueError(f"production runtime profile requires: {joined}")
        return self


def _env_bool(name: str, *, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, *, default: int) -> int:
    value = os.getenv(name)
    return default if value is None else int(value)


def _env_float(name: str, *, default: float) -> float:
    value = os.getenv(name)
    return default if value is None else float(value)


def _env_str(name: str, *, default: str) -> str:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return value


def _is_blank(value: Optional[str]) -> bool:
    return value is None or value.strip() == ""


# Global config instance
api_config = APIConfig.from_env()
