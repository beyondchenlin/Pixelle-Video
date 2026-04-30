from typing import Mapping, Protocol


class AssetBibleRepository(Protocol):
    async def save_asset_bible(
        self,
        workspace_id: str,
        asset_bible: Mapping[str, object],
    ) -> dict[str, object]:
        ...

    async def load_asset_bible(
        self,
        workspace_id: str,
        asset_bible_id: str,
    ) -> dict[str, object] | None:
        ...

    async def save_scene_cast(
        self,
        workspace_id: str,
        scene_cast: Mapping[str, object],
    ) -> dict[str, object]:
        ...

    async def load_scene_cast(
        self,
        workspace_id: str,
        scene_cast_id: str,
    ) -> dict[str, object] | None:
        ...
