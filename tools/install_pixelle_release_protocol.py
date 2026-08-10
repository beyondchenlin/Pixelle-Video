"""Pixelle Release Protocol 安装脚本。

自动安装 Pixelle 所需的 ComfyUI 插件：

Usage:
    python tools/install_pixelle_release_protocol.py
    python tools/install_pixelle_release_protocol.py --custom-nodes "E:\ComfyUIData\custom_nodes"
"""

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.resolve()
TOOLS_DIR = REPO_ROOT / "tools"
COMFYUI_TOOLS_DIR = TOOLS_DIR / "comfyui" / "custom_nodes"
PIXELLE_PLUGIN = COMFYUI_TOOLS_DIR / "ComfyUI-Pixelle-Release-Protocol"


def resolve_custom_nodes_dir(custom_nodes_arg: str | os.PathLike[str] | None) -> Path:
    """解析 custom_nodes 目录路径。"""
    if custom_nodes_arg:
        return Path(custom_nodes_arg)

    env_path = os.environ.get("COMFYUI_CUSTOM_NODES_DIR")
    if env_path:
        return Path(env_path)

    raise ValueError(
        "请指定 --custom-nodes 参数或设置 COMFYUI_CUSTOM_NODES_DIR 环境变量\n"
        "例如: python tools/install_pixelle_release_protocol.py --custom-nodes E:\\ComfyUIData\\custom_nodes"
    )


def install_pixelle_plugin(custom_nodes: Path) -> bool:
    """安装 Pixelle Release Protocol 插件（使用符号链接）。"""
    if not PIXELLE_PLUGIN.exists():
        print(f"  ✗ Pixelle 插件源码不存在: {PIXELLE_PLUGIN}")
        return False

    plugin_link = custom_nodes / "ComfyUI-Pixelle-Release-Protocol"

    if plugin_link.exists():
        if plugin_link.is_symlink() or (os.name == 'nt' and os.path.isdir(plugin_link) and os.path.islink(plugin_link)):
            print(f"  ✓ 符号链接已存在: {plugin_link}")
            return True
        else:
            print(f"  ✗ 目标路径已存在但不是符号链接: {plugin_link}")
            return False

    try:
        if os.name == 'nt':
            os.symlink(str(PIXELLE_PLUGIN), str(plugin_link), target_is_directory=True)
        else:
            os.symlink(PIXELLE_PLUGIN, plugin_link)
        print(f"  ✓ 创建符号链接: {plugin_link} -> {PIXELLE_PLUGIN}")
        return True
    except OSError as e:
        print(f"  ✗ 符号链接创建失败: {e}")
        print("    请手动创建符号链接:")
        if os.name == 'nt':
            print(f'    New-Item -ItemType Junction -Path "{plugin_link}" -Target "{PIXELLE_PLUGIN}"')
        else:
            print(f'    ln -s "{PIXELLE_PLUGIN}" "{plugin_link}"')
        return False


def main():
    parser = argparse.ArgumentParser(description="安装 Pixelle Release Protocol")
    parser.add_argument(
        "--custom-nodes",
        help="ComfyUI custom_nodes 目录路径",
    )
    args = parser.parse_args()

    try:
        custom_nodes = resolve_custom_nodes_dir(args.custom_nodes)
    except ValueError as e:
        print(f"错误: {e}")
        sys.exit(1)

    print(f"\n使用 custom_nodes 目录: {custom_nodes}")
    print("=" * 60)

    if not custom_nodes.exists():
        print(f"错误: 目录不存在: {custom_nodes}")
        sys.exit(1)

    print("\n[1/1] 安装 Pixelle Release Protocol 插件...")
    if install_pixelle_plugin(custom_nodes):
        print("\n" + "=" * 60)
        print("✓ 安装完成！")
        print("\n请重启 ComfyUI 以使更改生效。")
        sys.exit(0)
    else:
        print("\n" + "=" * 60)
        print("⚠ 安装失败，请检查上面的错误信息。")
        sys.exit(1)


if __name__ == "__main__":
    main()
