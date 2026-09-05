"""Apply the reviewed GGUF unpatch compatibility fix to an installed node package.

Adapted from city96/ComfyUI-GGUF PR #445, commit b543b78 (Apache-2.0):
https://github.com/city96/ComfyUI-GGUF/pull/445/files
The installed package is backed up; unrelated local customizations are preserved.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import tempfile
from pathlib import Path

OLD = """        # TODO: Find another way to not unload after patches
        return super().unpatch_model(device_to=device_to, unpatch_weights=unpatch_weights)
"""
NEW = """        if device_to is not None and self.model.model_lowvram:
            for m in self.model.modules():
                comfy.model_patcher.move_weight_functions(m, device_to)
        # Avoid nn.Module.to touching host-resident mmap-backed GGUF tensors.
        # Keep base backup restoration, hook cleanup and memory accounting intact.
        # Upstream: city96/ComfyUI-GGUF#445 (b543b78, Apache-2.0).
        super().unpatch_model(device_to=None, unpatch_weights=unpatch_weights)
        if unpatch_weights and device_to is not None:
            device_to = torch.device(device_to)
            for key, param in list(self.model.named_parameters(remove_duplicate=False)):
                if param.device != device_to:
                    comfy.utils.set_attr_param(self.model, key, param.to(device_to))
            for key, buf in list(self.model.named_buffers(remove_duplicate=False)):
                if buf.device != device_to:
                    comfy.utils.set_attr(self.model, key, buf.to(device_to))
            self.model.device = device_to
"""


def repair(plugin_dir: Path) -> dict[str, str]:
    target = plugin_dir.resolve() / "nodes.py"
    if target.is_symlink() or not target.is_file():
        raise ValueError("Expected a regular installed nodes.py file")
    original = target.read_bytes()
    before = original.decode("utf-8").replace("\r\n", "\n")
    if NEW in before and OLD not in before:
        return {"status": "already_applied"}
    if before.count(OLD) != 1 or "class GGUFModelPatcher(" not in before:
        raise ValueError("Installed source differs from reviewed version; refusing to patch")
    after = before.replace(OLD, NEW, 1)
    compile(after, str(target), "exec")
    digest = hashlib.sha256(original).hexdigest()
    backup = target.with_name(f"nodes.py.pixelle-backup-{digest[:16]}")
    if backup.exists() and backup.read_bytes() != original:
        raise ValueError("Existing backup differs; refusing to overwrite")
    if not backup.exists():
        shutil.copy2(target, backup)
    newline = "\r\n" if b"\r\n" in original else "\n"
    updated = after.replace("\n", newline).encode("utf-8")
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(updated)
            handle.flush()
            os.fsync(handle.fileno())
        if target.read_bytes() != original:
            raise ValueError("Installed source changed during repair; refusing to overwrite")
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return {
        "status": "applied",
        "backup": backup.name,
        "before_sha256": digest,
        "after_sha256": hashlib.sha256(updated).hexdigest(),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plugin_dir", type=Path)
    arguments = parser.parse_args()
    print(repair(arguments.plugin_dir))
