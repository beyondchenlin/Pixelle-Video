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

from pydantic import BaseModel


class APIConfig(BaseModel):
    """API configuration"""
    
    # Server settings
    host: str = "0.0.0.0"
    port: int = 8000
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
    completed_reuse_seconds: int = 86400
    execution_mode: Literal["embedded", "worker"] = "embedded"
    worker_poll_interval_seconds: float = 2.0

    # Artifact settings
    artifact_backend: Literal["local", "s3"] = "local"
    artifact_base_url: str = "/api/files"
    artifact_base_path: str = "output"
    
    # File upload settings
    max_upload_size: int = 100 * 1024 * 1024  # 100MB
    
    # API settings
    api_prefix: str = "/api"
    docs_url: Optional[str] = "/docs"
    redoc_url: Optional[str] = "/redoc"
    openapi_url: Optional[str] = "/openapi.json"

    @classmethod
    def from_env(cls) -> "APIConfig":
        """Build API config from PIXELLE_* environment variables."""
        return cls(
            task_backend=os.getenv("PIXELLE_TASK_BACKEND", "memory"),
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
            completed_reuse_seconds=_env_int(
                "PIXELLE_COMPLETED_REUSE_SECONDS",
                default=86400,
            ),
            execution_mode=os.getenv("PIXELLE_EXECUTION_MODE", "embedded"),
            worker_poll_interval_seconds=_env_float(
                "PIXELLE_WORKER_POLL_INTERVAL_SECONDS",
                default=2.0,
            ),
            artifact_backend=os.getenv("PIXELLE_ARTIFACT_BACKEND", "local"),
            artifact_base_url=os.getenv("PIXELLE_ARTIFACT_BASE_URL", "/api/files"),
            artifact_base_path=os.getenv("PIXELLE_ARTIFACT_BASE_PATH", "output"),
        )


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


# Global config instance
api_config = APIConfig.from_env()
