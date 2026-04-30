from typing import Mapping, Protocol


class TraceRepository(Protocol):
    async def append_llm_interaction(
        self,
        workspace_id: str,
        trace: Mapping[str, object],
    ) -> dict[str, object]:
        ...

    async def list_llm_interactions(
        self,
        workspace_id: str,
        filters: Mapping[str, object] | None = None,
    ) -> list[dict[str, object]]:
        ...

    async def append_generation_event(
        self,
        workspace_id: str,
        event: Mapping[str, object],
    ) -> dict[str, object]:
        ...

    async def list_generation_events(
        self,
        workspace_id: str,
        filters: Mapping[str, object] | None = None,
    ) -> list[dict[str, object]]:
        ...
