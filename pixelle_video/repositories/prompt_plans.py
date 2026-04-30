from typing import Mapping, Protocol


class PromptPlanRepository(Protocol):
    async def save_prompt_plan_bundle(
        self,
        workspace_id: str,
        prompt_plan_bundle: Mapping[str, object],
    ) -> dict[str, object]:
        ...

    async def load_prompt_plans_by_storyboard(
        self,
        workspace_id: str,
        storyboard_id: str,
    ) -> list[dict[str, object]]:
        ...

    async def mark_prompt_plan_stale(
        self,
        workspace_id: str,
        prompt_plan_id: str,
        reason: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        ...
