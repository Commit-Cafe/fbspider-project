"""
command_parser.py

自然语言命令解析器 — 将用户的多行自然语言输入解析为结构化的批量操作任务。

支持的命令格式:

  1. 分享像素到账户:
     分享像素到账户
     1.将像素：NYC01
     分享到账户：21324536476857、756643232344
     将像素：NYC02
     2.分享到账户：9876544343432、43256787987867

  2. 分享像素到BM:
     分享像素到BM
     1.将像素：NYC02、NYC03
     分享到BM：32321312322323
     2.将像素：NYC04、NYC05
     分享到BM：32321312322323

  3. 分享BM (邀请人员进BM):
     分享BM
     1.将BM：23432434324324243
     分享到个号：DFgfsfsd@gmail.com
     2.将BM：65676576576
     分享到个号：dsd@gmail.com

  也兼容单行简写:
     - "分享像素到账户 将像素：NYC01 分享到账户：21324536476857"
     - "分享像素到BM 将像素：NYC02 分享到BM：32321312322323"
"""
import re


def parse_command(text):
    """
    解析自然语言命令，返回结构化指令（支持多任务批量）。

    Returns:
        dict with keys:
            - action: "share_pixel_to_account" | "share_pixel_to_bm" | "share_bm" | "unknown"
            - tasks: list[dict]  每个任务包含该类型所需的参数
            - raw: str
            - error: str | None
    """
    if not text or not isinstance(text, str):
        return {"action": "unknown", "tasks": [], "raw": text or "", "error": "空命令"}

    raw = text.strip()
    command_type = _detect_command_type(raw)

    if command_type == "unknown":
        return {"action": "unknown", "tasks": [], "raw": raw, "error": "无法识别的命令，支持的命令: 分享像素到账户、分享像素到BM、分享BM"}

    tasks = _parse_tasks(raw, command_type)

    error = None
    if not tasks:
        error = "未找到有效的任务条目"
    else:
        for i, t in enumerate(tasks):
            if t.get("_error"):
                error = f"任务{i + 1}: {t['_error']}"
                break

    return {"action": command_type, "tasks": tasks, "raw": raw, "error": error}


def _detect_command_type(text):
    lower = text.lower()

    account_keywords = [
        "分享像素到账户", "分享像素到广告账户", "分享像素到账号",
        "像素分享到账户", "像素分享到广告账户",
    ]
    for kw in account_keywords:
        if kw in lower:
            return "share_pixel_to_account"

    pixel_bm_keywords = [
        "分享像素到bm", "分享像素给bm",
        "像素分享到bm", "像素分享给bm",
    ]
    for kw in pixel_bm_keywords:
        if kw in lower:
            return "share_pixel_to_bm"

    share_bm_keywords = ["分享bm", "分享个号", "邀请bm"]
    for kw in share_bm_keywords:
        if kw in lower:
            return "share_bm"

    has_pixel = bool(re.search(r"像素|pixel", lower))
    has_account = bool(re.search(r"(广告)?账户|账号", lower))
    has_bm = bool(re.search(r"bm", lower))
    has_email = bool(re.search(r"个号|邮箱|email|@", lower))

    if has_pixel and has_account:
        return "share_pixel_to_account"
    if has_pixel and has_bm:
        return "share_pixel_to_bm"
    if has_bm and has_email:
        return "share_bm"
    if has_bm:
        return "share_pixel_to_bm"
    if has_account:
        return "share_pixel_to_account"

    return "unknown"


def _strip_header(text):
    return re.sub(
        r"^(?:分享像素到账户|分享像素到广告账户|分享像素到账号|分享像素到BM|分享像素给BM|像素分享到BM|像素分享给BM|分享BM|分享个号|邀请BM)\s*",
        "", text, flags=re.IGNORECASE
    ).strip()


def _split_into_blocks(text):
    """
    将多行文本按编号切分为块。编号行之前的非编号行也归入前一个块。

    关键逻辑: 非编号行归入当前最近的编号块。
    如果没有编号，整个文本作为一个块。
    """
    header_stripped = _strip_header(text)
    if not header_stripped:
        return [text]

    has_numbering = bool(re.search(r"(?:^|\n)\s*\d+[\.\s、]", header_stripped))
    if not has_numbering:
        return [header_stripped]

    lines = header_stripped.split("\n")
    blocks = []
    pending_lines = []

    for line in lines:
        if re.match(r"\s*\d+[\.\s、]", line):
            cleaned = re.sub(r"^\s*\d+[\.\s、]+", "", line).strip()
            if pending_lines:
                if blocks:
                    blocks[-1] = blocks[-1] + "\n" + "\n".join(pending_lines)
                else:
                    blocks.append("\n".join(pending_lines))
                pending_lines = []
            if cleaned:
                pending_lines.append(cleaned)
        else:
            stripped = line.strip()
            if stripped:
                pending_lines.append(stripped)

    if pending_lines:
        blocks.append("\n".join(pending_lines))

    return blocks if blocks else [header_stripped]


def _parse_tasks(text, command_type):
    blocks = _split_into_blocks(text)

    tasks = []
    for block in blocks:
        task = _parse_single_block(block, command_type)
        if task:
            tasks.append(task)

    _inherit_missing_fields(tasks, command_type)

    return tasks


def _inherit_missing_fields(tasks, command_type):
    """
    对于缺少像素/目标ID的任务，从前一个任务继承。

    典型场景:
      Block 0: 将像素：NYC01 分享到账户：111
               将像素：NYC02           ← 归入了 Block 0
      Block 1: 分享到账户：222          ← 没有像素，需从 Block 0 继承 NYC02

    策略: 如果前一个任务有多个像素且当前任务没有像素，
          则将前一个任务中"多余"的像素（从末尾取）转移给当前任务。
    """
    if command_type in ("share_pixel_to_account", "share_pixel_to_bm"):
        for i in range(1, len(tasks)):
            prev = tasks[i - 1]
            curr = tasks[i]

            if not curr.get("pixel_names") and not curr.get("pixel_ids"):
                prev_names = list(prev.get("pixel_names", []))
                prev_ids = list(prev.get("pixel_ids", []))

                has_prev_target = bool(
                    prev.get("target_account_ids") or prev.get("target_bm_ids")
                )
                has_curr_target = bool(
                    curr.get("target_account_ids") or curr.get("target_bm_ids")
                )

                if has_prev_target and has_curr_target:
                    if len(prev_names) > 1:
                        curr["pixel_names"] = [prev_names.pop()]
                        prev["pixel_names"] = prev_names
                        if "_error" in curr and "未找到像素" in curr.get("_error", ""):
                            del curr["_error"]
                    elif len(prev_ids) > 1:
                        curr["pixel_ids"] = [prev_ids.pop()]
                        prev["pixel_ids"] = prev_ids
                        if "_error" in curr and "未找到像素" in curr.get("_error", ""):
                            del curr["_error"]

                elif not has_prev_target and has_curr_target:
                    curr["pixel_names"] = prev_names
                    curr["pixel_ids"] = prev_ids
                    prev["pixel_names"] = []
                    prev["pixel_ids"] = []
                    if "_error" in curr and "未找到像素" in curr.get("_error", ""):
                        del curr["_error"]

        last_source_bm = ""
        for task in tasks:
            sbm = task.get("source_bm_id", "")
            if sbm:
                last_source_bm = sbm
            elif last_source_bm:
                task["source_bm_id"] = last_source_bm

        for task in tasks:
            pn = task.get("pixel_names", [])
            pi = task.get("pixel_ids", [])
            if not pn and not pi and "_error" not in task:
                task["_error"] = "未找到像素名称或像素ID"

    elif command_type == "share_bm":
        last_bm_ids = []
        last_emails = []
        for task in tasks:
            if not task.get("bm_ids") and last_bm_ids:
                task["bm_ids"] = list(last_bm_ids)
                if "_error" in task and "未找到BM" in task.get("_error", ""):
                    del task["_error"]
            if not task.get("emails") and last_emails:
                task["emails"] = list(last_emails)
                if "_error" in task and "未找到目标邮箱" in task.get("_error", ""):
                    del task["_error"]
            if task.get("bm_ids"):
                last_bm_ids = list(task["bm_ids"])
            if task.get("emails"):
                last_emails = list(task["emails"])


def _parse_single_block(block, command_type):
    if command_type == "share_pixel_to_account":
        return _parse_pixel_to_account_block(block)
    elif command_type == "share_pixel_to_bm":
        return _parse_pixel_to_bm_block(block)
    elif command_type == "share_bm":
        return _parse_share_bm_block(block)
    return None


def _parse_pixel_to_account_block(block):
    pixel_names, pixel_ids = _extract_all_pixels(block)
    target_ids = _extract_all_account_ids(block)
    source_bm_id = _extract_source_bm_id(block)

    task = {
        "pixel_names": pixel_names,
        "pixel_ids": pixel_ids,
        "target_account_ids": target_ids,
        "source_bm_id": source_bm_id,
    }

    if not pixel_names and not pixel_ids:
        task["_error"] = "未找到像素名称或像素ID"
    if not target_ids:
        task["_error"] = "未找到目标广告账户ID"

    return task


def _parse_pixel_to_bm_block(block):
    pixel_names, pixel_ids = _extract_all_pixels(block)
    target_bms = _extract_target_bm_ids(block)
    source_bm_id = _extract_source_bm_id(block)

    task = {
        "pixel_names": pixel_names,
        "pixel_ids": pixel_ids,
        "target_bm_ids": target_bms,
        "source_bm_id": source_bm_id,
    }

    if not pixel_names and not pixel_ids:
        task["_error"] = "未找到像素名称或像素ID"
    if not target_bms:
        task["_error"] = "未找到目标BM ID"

    return task


def _parse_share_bm_block(block):
    bm_ids = _extract_bm_sources(block)
    emails = _extract_all_emails(block)

    task = {
        "bm_ids": bm_ids,
        "emails": emails,
    }

    if not bm_ids:
        task["_error"] = "未找到BM ID"
    if not emails:
        task["_error"] = "未找到目标邮箱"

    return task


def _extract_all_pixels(text):
    pixel_names = []
    pixel_ids = []

    patterns = [
        re.compile(
            r"(?:像素|pixel)[：:]\s*([^\n]+?)(?:\s*(?:分享|到|给|$))",
            re.IGNORECASE,
        ),
        re.compile(
            r"(?:像素|pixel)\s+([A-Za-z0-9_]+(?:[、，,\s]+[A-Za-z0-9_]+)*)",
            re.IGNORECASE,
        ),
    ]

    for pat in patterns:
        for m in pat.finditer(text):
            raw_names = m.group(1)
            names = re.split(r"[、，,\s]+", raw_names)
            for n in names:
                n = n.strip().strip("：:")
                if n:
                    if re.match(r"^\d{10,}$", n):
                        if n not in pixel_ids:
                            pixel_ids.append(n)
                    else:
                        if n not in pixel_names:
                            pixel_names.append(n)

    if pixel_names or pixel_ids:
        return pixel_names, pixel_ids

    id_pat = re.compile(r"(?:像素\s*(?:ID)?[：:]?\s*)(\d{10,20})", re.IGNORECASE)
    for m in id_pat.finditer(text):
        pid = m.group(1)
        if pid not in pixel_ids:
            pixel_ids.append(pid)

    return pixel_names, pixel_ids


def _extract_all_account_ids(text):
    ids = []

    patterns = [
        re.compile(
            r"(?:分享到|到|给)?(?:广告)?(?:账户|账号)[：:]\s*([\d、，,\s]+)",
        ),
        re.compile(
            r"(?:分享到|到|给)?(?:广告)?(?:账户|账号)\s+([\d、，,\s]+)",
        ),
    ]

    for pat in patterns:
        for m in pat.finditer(text):
            raw = m.group(1)
            for part in re.split(r"[、，,\s]+", raw):
                part = part.strip()
                if re.match(r"^\d{5,25}$", part) and part not in ids:
                    ids.append(part)

    if ids:
        return ids

    fallback = re.compile(r"(?:账户|账号)\D*(\d{10,25})")
    for m in fallback.finditer(text):
        aid = m.group(1)
        if aid not in ids:
            ids.append(aid)

    return ids


def _extract_target_bm_ids(text):
    """
    提取目标BM ID（排除源BM）。

    规则: "分享到BM" / "分享给BM" / "到BM" 之后的 BM ID 才是目标。
    "把BM xxx" / "BM xxx的像素" 中的 BM 是源 BM，应排除。
    """
    ids = []

    target_patterns = [
        re.compile(
            r"(?:分享到|分享给|到|给)\s*BM[：:]\s*([\d、，,\s]+)",
            re.IGNORECASE,
        ),
        re.compile(
            r"(?:分享到|分享给|到|给)\s*BM\s+([\d、，,\s]+)",
            re.IGNORECASE,
        ),
    ]

    for pat in target_patterns:
        for m in pat.finditer(text):
            raw = m.group(1)
            for part in re.split(r"[、，,\s]+", raw):
                part = part.strip()
                if re.match(r"^\d{5,25}$", part) and part not in ids:
                    ids.append(part)

    if ids:
        return ids

    general_pat = re.compile(r"BM[：:]\s*([\d、，,\s]+)", re.IGNORECASE)
    for m in general_pat.finditer(text):
        before = text[:m.start()]
        if re.search(r"(?:将|把)\s*$", before):
            continue
        raw = m.group(1)
        for part in re.split(r"[、，,\s]+", raw):
            part = part.strip()
            if re.match(r"^\d{5,25}$", part) and part not in ids:
                ids.append(part)

    if ids:
        return ids

    fallback = re.compile(r"BM\D*?(\d{10,25})", re.IGNORECASE)
    for m in fallback.finditer(text):
        before = text[:m.start()]
        if re.search(r"(?:将|把)\s*$", before):
            continue
        bm = m.group(1)
        if bm not in ids:
            ids.append(bm)

    return ids


def _extract_source_bm_id(text):
    """
    提取源 BM ID（像素所属的 BM）。

    新模板格式: "将BM 1632044938058987" 或 "将BM：1632044938058987"
    关键区分: 这行不包含"分享到"/"分享给"等动词，是独立的源BM声明行。
    """
    patterns = [
        re.compile(r"将\s*BM[：:\s]+(\d{5,25})", re.IGNORECASE),
    ]
    for pat in patterns:
        m = pat.search(text)
        if m:
            return m.group(1)

    return ""


def _extract_bm_sources(text):
    ids = []
    patterns = [
        re.compile(r"(?:将)?BM[：:]\s*(\d{5,25})", re.IGNORECASE),
        re.compile(r"BM\s+(\d{5,25})", re.IGNORECASE),
    ]
    for pat in patterns:
        for m in pat.finditer(text):
            bm = m.group(1)
            if bm not in ids:
                ids.append(bm)
    return ids


def _extract_all_emails(text):
    emails = []
    email_pat = re.compile(
        r"(?:个号|邮箱|email|邮件)[：:]*\s*([A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+)",
        re.IGNORECASE,
    )
    for m in email_pat.finditer(text):
        email = m.group(1).strip()
        if email not in emails:
            emails.append(email)

    if emails:
        return emails

    standalone = re.compile(r"([A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,})")
    for m in standalone.finditer(text):
        email = m.group(1).strip()
        if email not in emails:
            emails.append(email)

    return emails
