import importlib
import sys
import types


def test_parse_args_uses_updated_comfyui_model_root_by_default(monkeypatch):
    fake_modelscope = types.ModuleType("modelscope")
    fake_hub = types.ModuleType("modelscope.hub")
    fake_file_download = types.ModuleType("modelscope.hub.file_download")
    fake_file_download.model_file_download = lambda *args, **kwargs: ""

    monkeypatch.setitem(sys.modules, "modelscope", fake_modelscope)
    monkeypatch.setitem(sys.modules, "modelscope.hub", fake_hub)
    monkeypatch.setitem(sys.modules, "modelscope.hub.file_download", fake_file_download)

    module = importlib.import_module("tools.download_z_image_models")

    monkeypatch.setattr(sys, "argv", ["download_z_image_models.py"])

    args = module.parse_args()

    assert args.model_root == r"E:\comfyui\comfyui\models"
