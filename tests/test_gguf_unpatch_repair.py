from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.comfyui.repair_gguf_unpatch import NEW, OLD, repair


def test_repair_preserves_customizations_and_backup(tmp_path: Path):
    source = "# local customization\nclass GGUFModelPatcher(Base):\n    def unpatch_model(self, device_to=None, unpatch_weights=True):\n" + OLD
    target = tmp_path / "nodes.py"
    target.write_bytes(source.replace("\n", "\r\n").encode())
    original = target.read_bytes()
    result = repair(tmp_path)
    assert (tmp_path / result["backup"]).read_bytes() == original
    assert target.read_text().startswith("# local customization\n")
    assert NEW in target.read_text()
    assert repair(tmp_path)["status"] == "already_applied"


def test_unknown_source_is_not_modified(tmp_path: Path):
    target = tmp_path / "nodes.py"
    target.write_text("# another plugin version")
    with pytest.raises(ValueError, match="differs"):
        repair(tmp_path)
    assert target.read_text() == "# another plugin version"
    assert len(list(tmp_path.iterdir())) == 1


def test_unpatch_skips_host_mmap_and_retains_base_cleanup():
    events = []

    class Tensor:
        def __init__(self, device):
            self.device = device

        def to(self, device):
            assert self.device != device, "same-device mmap tensor must never be touched"
            events.append(("move", self.device, device))
            return Tensor(device)

    class Model:
        model_lowvram = True
        device = "cuda"

        def modules(self):
            return [self]

        def named_parameters(self, remove_duplicate):
            assert not remove_duplicate
            return [("host", Tensor("cpu")), ("gpu", Tensor("cuda"))]

        def named_buffers(self, remove_duplicate):
            return [("host_buffer", Tensor("cpu")), ("gpu_buffer", Tensor("cuda"))]

    class Base:
        def unpatch_model(self, device_to=None, unpatch_weights=True):
            assert device_to is None
            events.append(("base", unpatch_weights))
            self.model.model_lowvram = False

    namespace = {
        "Base": Base,
        "torch": SimpleNamespace(device=lambda value: value),
        "comfy": SimpleNamespace(
            model_patcher=SimpleNamespace(move_weight_functions=lambda *args: events.append("lowvram")),
            utils=SimpleNamespace(set_attr_param=setattr, set_attr=setattr),
        ),
    }
    exec("class Patched(Base):\n    def unpatch_model(self, device_to=None, unpatch_weights=True):\n" + NEW, namespace)
    patcher = namespace["Patched"]()
    patcher.model = Model()
    patcher.unpatch_model("cpu")
    assert events == ["lowvram", ("base", True), ("move", "cuda", "cpu"), ("move", "cuda", "cpu")]
    assert patcher.model.device == "cpu"
    events.clear()
    patcher.unpatch_model("cpu", unpatch_weights=False)
    assert events == [("base", False)]
