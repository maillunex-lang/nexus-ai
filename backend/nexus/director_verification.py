"""Deterministic verification gate for proposed Godot source changes.

Pure functions: no filesystem access, no Godot execution, no network. The gate
runs before a change is queued for the isolated Godot validation, so obviously
broken or risky edits are rejected without spending host CPU.

Verdicts: "pass" (no findings), "warn" (owner should read the findings),
"block" (the change may not be queued). These are static heuristics, not a
replacement for the Godot parser, which still validates the isolated copy.
"""
import re

MAX_CHECKS = 120

# Process control has no place in a game client change made through NEXUS.
BLOCKED_APIS = (
    (r"\bOS\s*\.\s*(?:execute|execute_with_pipe|create_process|create_instance|kill|shell_open)\s*\(",
     "process_execution_api", "Запуск внешних процессов из игрового кода запрещён в автоматических изменениях."),
)
REVIEW_APIS = (
    (r"\b(?:HTTPRequest|HTTPClient|WebSocketPeer|StreamPeerTCP|StreamPeerTLS|PacketPeerUDP|TCPServer|UDPServer|ENetMultiplayerPeer|WebRTCPeerConnection)\b",
     "network_api_introduced", "Изменение добавляет сетевой API: проверьте адреса и передаваемые данные."),
    (r"\b(?:DirAccess\s*\.\s*(?:remove_absolute|remove)|OS\s*\.\s*move_to_trash)\s*\(|\.\s*remove_absolute\s*\(",
     "file_deletion_api", "Изменение добавляет удаление файлов: проверьте пути."),
    (r"\bJavaScriptBridge\s*\.\s*eval\s*\(|\bExpression\s*\.\s*new\s*\(",
     "dynamic_code_api", "Изменение добавляет выполнение динамического кода."),
)
PAIRS = {")": "(", "]": "[", "}": "{"}


def _scan_gdscript(source: str) -> dict:
    """Blank out strings and comments; track bracket depth at each line start."""
    out = []
    stack = []            # (bracket, line)
    statement_lines = []  # 1-based lines that start at depth 0 outside strings
    errors = []
    i, n, line = 0, len(source), 1
    line_start = True
    while i < n:
        c = source[i]
        if line_start:
            if not stack:
                statement_lines.append(line)
            line_start = False
        if c == "\n":
            out.append(c)
            line += 1
            line_start = True
            i += 1
        elif c == "#":
            while i < n and source[i] != "\n":
                out.append(" ")
                i += 1
        elif c in "\"'":
            raw = bool(out) and out[-1] == "r" and (len(out) < 2 or not (out[-2].isalnum() or out[-2] == "_"))
            quote = source[i:i + 3] if source[i:i + 3] in ('"""', "'''") else c
            opened = line
            i += len(quote)
            out.append(" " * len(quote))
            closed = False
            while i < n:
                if source[i] == "\\" and not raw and i + 1 < n:
                    out.append("\n" if source[i + 1] == "\n" else "  ")
                    if source[i + 1] == "\n":
                        line += 1
                    i += 2
                    continue
                if source.startswith(quote, i):
                    out.append(" " * len(quote))
                    i += len(quote)
                    closed = True
                    break
                if source[i] == "\n":
                    if len(quote) == 1:
                        break
                    line += 1
                    out.append("\n")
                else:
                    out.append(" ")
                i += 1
            if not closed:
                errors.append(("unterminated_string", opened))
                if len(quote) == 3:
                    break
        elif c in "([{":
            stack.append((c, line))
            out.append(c)
            i += 1
        elif c in ")]}":
            if not stack or stack[-1][0] != PAIRS[c]:
                errors.append(("unbalanced_brackets", line))
                stack = []
            else:
                stack.pop()
            out.append(c)
            i += 1
        else:
            out.append(c)
            i += 1
    if stack:
        errors.append(("unbalanced_brackets", stack[-1][1]))
    return {"code": "".join(out), "statement_lines": statement_lines, "errors": errors}


def _strip_c_like(source: str) -> str:
    source = re.sub(r"/\*.*?\*/", lambda m: re.sub(r"[^\n]", " ", m.group(0)), source, flags=re.S)
    return re.sub(r"//[^\n]*", "", source)


def _balanced(code: str):
    stack = []
    line = 1
    for c in code:
        if c == "\n":
            line += 1
        elif c in "([{":
            stack.append((c, line))
        elif c in ")]}":
            if not stack or stack[-1][0] != PAIRS[c]:
                return line
            stack.pop()
    return stack[-1][1] if stack else None


def _count(pattern: str, code: str) -> int:
    return len(re.findall(pattern, code))


def check_gdscript(new: str, old: str = "") -> list[dict]:
    checks = []
    scan = _scan_gdscript(new)
    seen = set()
    for code, line in scan["errors"]:
        if code in seen:
            continue
        seen.add(code)
        checks.append({"code": code, "severity": "block", "line": line,
                       "message": {"unterminated_string": "Незакрытая строка.",
                                   "unbalanced_brackets": "Несбалансированные скобки."}[code]})
    if not scan["errors"]:
        lines = new.split("\n")
        tabs = spaces = None
        for number in scan["statement_lines"]:
            text = lines[number - 1] if number - 1 < len(lines) else ""
            indent = text[:len(text) - len(text.lstrip(" \t"))]
            if not indent or not text.strip() or text.lstrip().startswith("#"):
                continue
            if " " in indent and "\t" in indent:
                tabs = tabs or number
                spaces = spaces or number
            elif "\t" in indent:
                tabs = tabs or number
            else:
                spaces = spaces or number
        if tabs and spaces:
            checks.append({"code": "mixed_indentation", "severity": "block", "line": max(tabs, spaces),
                           "message": "Смешаны табуляция и пробелы в отступах: Godot отклонит скрипт."})
    old_code = _scan_gdscript(old)["code"] if old else ""
    for severity, rules in (("block", BLOCKED_APIS), ("warn", REVIEW_APIS)):
        for pattern, code, message in rules:
            if _count(pattern, scan["code"]) > _count(pattern, old_code):
                match = re.search(pattern, scan["code"])
                checks.append({"code": code, "severity": severity,
                               "line": scan["code"].count("\n", 0, match.start()) + 1, "message": message})
    return checks


def check_shader(new: str) -> list[dict]:
    checks = []
    code = _strip_c_like(new)
    if not re.search(r"(?m)^\s*shader_type\s+\w+\s*;", code):
        checks.append({"code": "missing_shader_type", "severity": "block",
                       "message": "Не указан shader_type: шейдер не скомпилируется."})
    line = _balanced(code)
    if line:
        checks.append({"code": "unbalanced_brackets", "severity": "block", "line": line,
                       "message": "Несбалансированные скобки в шейдере."})
    return checks


def check_resource(new: str, suffix: str, exists=None) -> list[dict]:
    checks = []
    header = "[gd_scene" if suffix == ".tscn" else "[gd_resource"
    if not new.lstrip().startswith(header):
        checks.append({"code": "missing_resource_header", "severity": "block", "line": 1,
                       "message": "Отсутствует заголовок " + header + "]: Godot не загрузит файл."})
    if exists is not None:
        missing = []
        for match in re.finditer(r'(?m)^\[ext_resource\b[^\]\n]*\bpath="res://([^"\n]{1,240})"', new):
            target = match.group(1)
            if target not in missing and not exists(target):
                missing.append(target)
                if len(missing) <= 10:
                    checks.append({"code": "missing_ext_resource", "severity": "warn",
                                   "line": new.count("\n", 0, match.start()) + 1,
                                   "message": "Ссылка на отсутствующий ресурс res://" + target})
    return checks


def check_file(path: str, new: str, old: str = "", exists=None) -> list[dict]:
    suffix = "." + path.rsplit(".", 1)[-1] if "." in path else ""
    checks = []
    marker = re.search(r"(?m)^(?:<<<<<<<|>>>>>>>)(?: |$)", new)
    if marker:
        checks.append({"code": "merge_conflict_marker", "severity": "block",
                       "line": new.count("\n", 0, marker.start()) + 1,
                       "message": "В файле остались маркеры конфликта слияния."})
    if not new.strip():
        checks.append({"code": "empty_file", "severity": "block", "message": "Изменение очищает файл целиком."})
    elif len(old) > 2000 and len(new) < len(old) * 0.2:
        checks.append({"code": "large_deletion", "severity": "warn",
                       "message": "Удалено более 80% содержимого файла: подтвердите, что это намеренно."})
    if suffix == ".gd":
        checks += check_gdscript(new, old)
    elif suffix == ".gdshader":
        checks += check_shader(new)
    elif suffix in (".tscn", ".tres"):
        checks += check_resource(new, suffix, exists)
    return [{"path": path, **check} for check in checks]


def verify(files: list[dict], exists=None) -> dict:
    """files: [{"path","old","new"}]. `exists(relative_path)` resolves res:// targets."""
    checks = []
    for item in files:
        checks += check_file(item["path"], item["new"], item.get("old", ""), exists)
    blocking = sum(1 for c in checks if c["severity"] == "block")
    warnings = sum(1 for c in checks if c["severity"] == "warn")
    return {"verdict": "block" if blocking else "warn" if warnings else "pass",
            "blocking": blocking, "warnings": warnings,
            "checks": checks[:MAX_CHECKS], "checks_truncated": len(checks) > MAX_CHECKS,
            "analysis": "static_rules", "godot_executed": False,
            "note": "Статические правила. Окончательную проверку выполняет Godot в изолированной копии."}
