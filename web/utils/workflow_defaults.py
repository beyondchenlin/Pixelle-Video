from pixelle_video.config.workflow_defaults import resolve_default_workflow


def resolve_selectbox_default_index(
    domain: str,
    workflow_keys: list[str],
    configured_workflow: str | None,
) -> int:
    resolved_key = resolve_default_workflow(
        domain=domain,
        available_keys=workflow_keys,
        configured_workflow=configured_workflow,
    )
    return workflow_keys.index(resolved_key) if resolved_key in workflow_keys else 0
