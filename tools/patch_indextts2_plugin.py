import argparse
import ast
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

INDEXTTS2_PLUGIN_ENV = "INDEXTTS2_PLUGIN_DIR"
UTILS_RELATIVE_PATH = Path("indextts2") / "utils.py"
INFER_V2_RELATIVE_PATH = Path("indextts2") / "vendor" / "indextts" / "infer_v2.py"


@dataclass(frozen=True)
class PatchResult:
    changed_files: list[Path]


def resolve_target_path(target_arg: str | os.PathLike[str] | None) -> Path:
    if target_arg:
        return Path(target_arg)

    target_env = os.environ.get(INDEXTTS2_PLUGIN_ENV)
    if target_env:
        return Path(target_env)

    raise ValueError(f"Pass --target or set {INDEXTTS2_PLUGIN_ENV} to the ComfyUI-Index-TTS directory")


def patch_plugin(target: str | os.PathLike[str]) -> PatchResult:
    plugin_dir = Path(target)
    if not plugin_dir.exists():
        raise FileNotFoundError(f"target plugin directory does not exist: {plugin_dir}")
    if not plugin_dir.is_dir():
        raise NotADirectoryError(f"target plugin path is not a directory: {plugin_dir}")

    utils_path = plugin_dir / UTILS_RELATIVE_PATH
    infer_path = plugin_dir / INFER_V2_RELATIVE_PATH
    _require_file(utils_path, UTILS_RELATIVE_PATH)
    _require_file(infer_path, INFER_V2_RELATIVE_PATH)

    changed_files: list[Path] = []
    if _patch_file(utils_path, _patch_utils):
        changed_files.append(utils_path)
    if _patch_file(infer_path, _patch_infer_v2):
        changed_files.append(infer_path)
    return PatchResult(changed_files=changed_files)


def _require_file(path: Path, relative_path: Path) -> None:
    display_path = relative_path.as_posix()
    if not path.exists():
        raise FileNotFoundError(f"required plugin file is missing: {display_path}")
    if not path.is_file():
        raise FileNotFoundError(f"required plugin path is not a file: {display_path}")


def _patch_file(path: Path, patcher) -> bool:
    original = path.read_text(encoding="utf-8")
    patched = patcher(original)
    if patched == original:
        return False
    path.write_text(patched, encoding="utf-8")
    return True


def _ensure_import(text: str, import_line: str) -> str:
    if re.search(rf"^{re.escape(import_line)}$", text, flags=re.MULTILINE):
        return text

    lines = text.splitlines()
    insert_at = 0
    while insert_at < len(lines):
        line = lines[insert_at]
        if line.startswith("import ") or line.startswith("from "):
            insert_at += 1
            continue
        if not line.strip():
            insert_at += 1
            continue
        break
    lines.insert(insert_at, import_line)
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")


def _patch_utils(text: str) -> str:
    text = _ensure_import(text, "import hashlib")
    text = re.sub(r"^INDEXTTS2_WAV_CACHE_DIR\s*=.*\n\n?", "", text, flags=re.MULTILINE)

    if "def _is_valid_cached_wav" in text:
        text = _replace_function(text, "_is_valid_cached_wav", STABLE_IS_VALID_CACHED_WAV)
    else:
        text = text.replace("\ndef save_temp_wav", "\n" + STABLE_IS_VALID_CACHED_WAV + "def save_temp_wav", 1)

    if "_REF_CACHE_DIR" in text:
        text = re.sub(
            r'^_REF_CACHE_DIR\s*=.*$',
            '_REF_CACHE_DIR = "indextts2_ref_cache"',
            text,
            count=1,
            flags=re.MULTILINE,
        )
    else:
        text = text.replace(
            "\ndef _is_valid_cached_wav",
            '\n_REF_CACHE_DIR = "indextts2_ref_cache"\n\n\ndef _is_valid_cached_wav',
            1,
        )

    return _replace_function(text, "save_temp_wav", STABLE_SAVE_TEMP_WAV)


STABLE_IS_VALID_CACHED_WAV = '''def _is_valid_cached_wav(path: str, sr: int) -> bool:
    try:
        info = sf.info(path)
        if int(info.samplerate) != int(sr) or int(info.frames) <= 0:
            return False
        data, read_sr = sf.read(path, frames=1, always_2d=False)
        return int(read_sr) == int(sr) and np.asarray(data).size > 0
    except Exception:
        return False


'''


STABLE_SAVE_TEMP_WAV = '''def save_temp_wav(wave_sr: Tuple[np.ndarray, int]) -> str:
    """
    Save (wave, sr) to a temporary mono WAV file and return the path.
    Wave is expected in float32 [-1, 1] range or int16.
    """
    wave, sr = wave_sr
    if wave is None:
        raise ValueError("wave is None")
    if wave.ndim > 1:
        # force mono
        wave = wave.reshape(-1)
    # ensure float32
    if wave.dtype != np.float32:
        if wave.dtype == np.int16:
            wave = (wave.astype(np.float32) / 32768.0).clip(-1.0, 1.0)
        else:
            wave = wave.astype(np.float32)
    else:
        wave = np.asarray(wave, dtype=np.float32)
    wave = np.ascontiguousarray(wave)
    sr = int(sr)
    digest = hashlib.sha256()
    digest.update(str(sr).encode("ascii"))
    digest.update(str(wave.dtype).encode("ascii"))
    digest.update(str(wave.shape).encode("ascii"))
    digest.update(wave.tobytes())
    cache_dir = os.path.join(tempfile.gettempdir(), _REF_CACHE_DIR)
    os.makedirs(cache_dir, exist_ok=True)
    path = os.path.join(cache_dir, f"indextts2_{digest.hexdigest()[:24]}.wav")
    if os.path.exists(path) and _is_valid_cached_wav(path, sr):
        return path

    fd, tmp_path = tempfile.mkstemp(
        prefix=f".{os.path.basename(path)}.",
        suffix=".wav",
        dir=cache_dir,
    )
    os.close(fd)
    try:
        sf.write(tmp_path, wave, int(sr))
        os.replace(tmp_path, path)
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
    return path
'''


def _replace_function(text: str, function_name: str, replacement: str) -> str:
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        raise ValueError(f"could not parse file while locating function to patch: {function_name}") from exc

    matches = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name
    ]
    if len(matches) != 1:
        raise ValueError(f"could not find function to patch: {function_name}")

    node = matches[0]
    if node.end_lineno is None:
        raise ValueError(f"could not determine function bounds while patching: {function_name}")

    start_lineno = node.lineno
    if node.decorator_list:
        start_lineno = min(decorator.lineno for decorator in node.decorator_list)

    lines = text.splitlines(keepends=True)
    end_index = node.end_lineno
    while end_index < len(lines) and not lines[end_index].strip():
        end_index += 1
    return "".join(lines[: start_lineno - 1]) + replacement + "".join(lines[end_index:])


def _patch_infer_v2(text: str) -> str:
    text = _patch_qwen_initialization(text)
    text = _ensure_qwen_getter(text)
    text = _patch_use_emo_text_getter(text)
    text = _patch_do_sample_argument(text)
    return text


def _patch_qwen_initialization(text: str) -> str:
    if (
        "self.qwen_emo_path = os.path.join(self.model_dir, qwen_subdir)" in text
        and "self.qwen_emo = None" in text
    ):
        return text

    pattern = re.compile(
        r"^(?P<indent>\s*)self\.qwen_emo\s*=\s*QwenEmotion\("
        r"\s*os\.path\.join\(\s*self\.model_dir\s*,\s*"
        r"(?P<subdir>self\.cfg\.qwen_emo_path|qwen_subdir)\s*\)\s*\)\s*$",
        flags=re.MULTILINE,
    )

    def replace(match: re.Match[str]) -> str:
        indent = match.group("indent")
        lines = []
        if match.group("subdir") == "self.cfg.qwen_emo_path":
            lines.append(f"{indent}qwen_subdir = str(self.cfg.qwen_emo_path).strip()")
        lines.extend(
            [
                f"{indent}self.qwen_emo_path = os.path.join(self.model_dir, qwen_subdir)",
                f"{indent}self.qwen_emo = None",
            ]
        )
        return "\n".join(lines)

    patched, count = pattern.subn(replace, text, count=1)
    if count != 1:
        raise ValueError("could not find supported eager QwenEmotion initialization to patch")
    return patched


def _ensure_qwen_getter(text: str) -> str:
    if "def _get_qwen_emo(self):" in text:
        return text

    getter = (
        "    def _get_qwen_emo(self):\n"
        "        if self.qwen_emo is None:\n"
        "            self.qwen_emo = QwenEmotion(self.qwen_emo_path)\n"
        "        return self.qwen_emo\n"
        "\n"
    )
    for anchor in ("\n    @torch.no_grad()\n", "\n    def get_emb("):
        if anchor in text:
            return text.replace(anchor, "\n" + getter + anchor.lstrip("\n"), 1)
    raise ValueError("could not find insertion point for QwenEmotion getter")


def _patch_use_emo_text_getter(text: str) -> str:
    if "self._get_qwen_emo().inference(emo_text)" in text:
        return text
    if "self.qwen_emo.inference(emo_text)" not in text:
        raise ValueError("could not find use_emo_text QwenEmotion inference call to patch")
    return text.replace(
        "self.qwen_emo.inference(emo_text)",
        "self._get_qwen_emo().inference(emo_text)",
        1,
    )


def _patch_do_sample_argument(text: str) -> str:
    call_span = _find_inference_speech_call_span(text)
    if call_span is None:
        raise ValueError("could not find self.gpt.inference_speech call to patch")

    call_start, call_end = call_span
    call_text = text[call_start:call_end]
    if re.search(r"\bdo_sample\s*=\s*do_sample\b", call_text):
        return text

    patched_call, count = re.subn(
        r"\bdo_sample\s*=\s*True\b",
        "do_sample=do_sample",
        call_text,
        count=1,
    )
    if count != 1:
        raise ValueError("could not find do_sample=True argument in self.gpt.inference_speech call to patch")
    return text[:call_start] + patched_call + text[call_end:]


def _find_inference_speech_call_span(text: str) -> tuple[int, int] | None:
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        raise ValueError("could not parse infer_v2.py while locating self.gpt.inference_speech call") from exc

    line_starts = _line_start_offsets(text)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not _is_self_gpt_inference_speech(node.func):
            continue
        if node.end_lineno is None or node.end_col_offset is None:
            raise ValueError("could not determine self.gpt.inference_speech call bounds")
        start = line_starts[node.lineno - 1] + node.col_offset
        end = line_starts[node.end_lineno - 1] + node.end_col_offset
        return start, end
    return None


def _line_start_offsets(text: str) -> list[int]:
    starts = [0]
    for match in re.finditer(r"\n", text):
        starts.append(match.end())
    return starts


def _is_self_gpt_inference_speech(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "inference_speech"
        and isinstance(node.value, ast.Attribute)
        and node.value.attr == "gpt"
        and isinstance(node.value.value, ast.Name)
        and node.value.value.id == "self"
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Patch a ComfyUI-Index-TTS plugin directory for Pixelle's local runtime."
    )
    parser.add_argument(
        "--target",
        help=f"Path to ComfyUI-Index-TTS. Defaults to ${INDEXTTS2_PLUGIN_ENV}.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        target = resolve_target_path(args.target)
        result = patch_plugin(target)
    except (FileNotFoundError, NotADirectoryError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if result.changed_files:
        for path in result.changed_files:
            print(f"patched: {path}")
    else:
        print(f"already patched: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
