"""Bili Study: localhost-only app, Python standard library, no installed packages."""
import argparse
import sys
import secrets
import hmac
import workspace_features
import accounts
from contextlib import contextmanager
import json
import os
import re
import sqlite3
import threading
import time
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen, build_opener, HTTPRedirectHandler

ROOT = Path(__file__).resolve().parent
PROMPT = (ROOT / "prompts" / "coach.md").read_text(encoding="utf-8")
DB = Path(os.getenv('STUDY_DATA_DIR', str(ROOT / 'data'))) / 'study.sqlite3'
MAX_BODY = 12_000_000
PAIR_TOKEN = ''
ALLOWED_HOSTS = set()
MAX_MATERIAL = 55_000
CONFIG_LOCK = threading.Lock()
SESSION_LOCK = threading.Lock()
CONFIG = {"base_url": os.getenv("STUDY_API_BASE", "https://api.openai.com/v1"),
          "model": os.getenv("STUDY_MODEL", ""), "api_key": os.getenv("STUDY_API_KEY", "")}


class AppError(Exception):
    pass


@contextmanager
def database():
    target = accounts.db_path() or DB
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(target)
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def init_db():
    DB.parent.mkdir(parents=True, exist_ok=True)
    with database() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, updated REAL, body TEXT)")


def save_session(session):
    session["updated"] = time.time()
    with database() as conn:
        conn.execute("INSERT OR REPLACE INTO sessions VALUES (?, ?, ?)",
                     (session["id"], session["updated"], json.dumps(session, ensure_ascii=False)))


def get_session(sid):
    with database() as conn:
        row = conn.execute("SELECT body FROM sessions WHERE id=?", (sid,)).fetchone()
    if not row:
        raise AppError("这次学习不存在，请重新选择。")
    return json.loads(row[0])


def list_sessions():
    with database() as conn:
        rows = conn.execute("SELECT body FROM sessions ORDER BY updated DESC").fetchall()
    return [{"id": s["id"], "title": s["title"], "updated": s["updated"],
             "demo": s["demo"], "ended": s["ended"], "count": len(s["plan"]["points"])}
            for s in (json.loads(r[0]) for r in rows)]


def stamp(seconds):
    seconds = int(float(seconds))
    return f"{seconds // 3600:02}:{seconds // 60 % 60:02}:{seconds % 60:02}"


def parse_transcript(raw):
    if not isinstance(raw, str) or not raw.strip():
        raise AppError("请粘贴字幕或导入字幕文件。")
    if len(raw) > MAX_MATERIAL:
        raise AppError("字幕超过 55,000 字符。请分段导入；本次不会静默截断材料。")
    raw = raw.lstrip("\ufeff").strip()
    segments = []
    if raw.startswith(("{", "[")):
        try:
            data = json.loads(raw)
            rows = data.get("body", data.get("segments", [])) if isinstance(data, dict) else data
            if not isinstance(rows, list):
                raise AppError("JSON 字幕需要 body 或 segments 数组。")
            for row in rows:
                content = str(row.get("content", row.get("text", ""))).strip()
                if content:
                    start, end = row.get("from", row.get("start")), row.get("to", row.get("end"))
                    segments.append({"text": content, "start": stamp(start) if start is not None else None,
                                     "end": stamp(end) if end is not None else None})
        except (ValueError, TypeError, AttributeError):
            raise AppError("JSON 字幕无法解析，请检查格式。")
    else:
        blocks = re.split(r"\n\s*\n", raw.replace("\r\n", "\n"))
        clock = r"(?:\d{1,2}:)?\d{2}:\d{2}[.,]\d{3}"
        for block in blocks:
            lines = block.splitlines()
            timed = next((i for i, line in enumerate(lines) if "-->" in line), None)
            if timed is not None:
                times = re.findall(clock, lines[timed])
                content = " ".join(lines[timed + 1:]).strip()
                if content:
                    segments.append({"text": content, "start": times[0].replace(",", ".") if times else None,
                                     "end": times[1].replace(",", ".") if len(times) > 1 else None})
            elif not block.startswith(("WEBVTT", "NOTE", "STYLE", "REGION")):
                for line in lines:
                    if line.strip():
                        segments.append({"text": line.strip(), "start": None, "end": None})
    if not segments:
        raise AppError("没有找到有效字幕正文。")
    for i, seg in enumerate(segments, 1):
        seg["id"] = f"S{i}"
    return segments


def request_json(url, headers=None, payload=None):
    body = json.dumps(payload, ensure_ascii=False).encode() if payload is not None else None
    req = Request(url, data=body, headers=headers or {})
    try:
        class NoRedirect(HTTPRedirectHandler):
            def redirect_request(self,*args,**kwargs):return None
        opener=build_opener(NoRedirect()).open if accounts.current.get() else urlopen
        with opener(req, timeout=100) as response:
            return json.load(response)
    except HTTPError as exc:
        raise AppError(f"远程服务返回 HTTP {exc.code}。请检查连接、权限和设置。")
    except (URLError, TimeoutError, OSError):
        raise AppError("远程连接失败或超时，请检查网络与服务地址。")
    except ValueError:
        raise AppError("远程服务没有返回有效 JSON。")


def import_bilibili(value):
    value = value.strip()
    if re.fullmatch(r"BV[0-9A-Za-z]{10}", value):
        bvid, page = value, 1
    else:
        parsed = urlparse(value)
        if parsed.scheme != "https" or parsed.hostname not in ("www.bilibili.com", "bilibili.com"):
            raise AppError("请使用完整的 https://www.bilibili.com/video/BV… 链接或 BV 号；短链请先展开。")
        match = re.search(r"/video/(BV[0-9A-Za-z]{10})(?:/|$)", parsed.path)
        if not match:
            raise AppError("没有找到有效 BV 号。")
        bvid = match.group(1)
        try:
            page = int(parse_qs(parsed.query).get("p", [1])[0])
        except ValueError:
            raise AppError("分 P 编号应为数字。")
    headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.bilibili.com/"}
    if os.getenv("BILI_SESSDATA") and not accounts.current.get():
        headers["Cookie"] = "SESSDATA=" + os.environ["BILI_SESSDATA"]
    meta = request_json(f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}", headers)
    if meta.get("code") != 0:
        raise AppError("无法读取这个视频。请检查链接，或改为导入字幕。")
    data = meta["data"]
    pages = data.get("pages", [])
    if not 1 <= page <= len(pages):
        raise AppError("视频没有这个分 P。")
    part = pages[page - 1]
    player = request_json(f"https://api.bilibili.com/x/player/v2?bvid={bvid}&cid={part['cid']}", headers)
    subtitles = player.get("data", {}).get("subtitle", {}).get("subtitles", [])
    subtitles = [s for s in subtitles if s.get("subtitle_url")]
    if not subtitles:
        raise AppError("没有读到可访问的字幕：可能未提供字幕、需要登录或接口受限。请导入 TXT / SRT / VTT / JSON 字幕。此 App 尚未包含音频转写。")
    subtitles.sort(key=lambda s: (not s.get("lan", "").startswith("zh"), "ai" in s.get("lan", "")))
    sub = subtitles[0]
    url = sub["subtitle_url"]
    if url.startswith("//"):
        url = "https:" + url
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or not parsed.hostname.endswith(".hdslb.com"):
        raise AppError("字幕地址不在受支持的 Bilibili 字幕域名中，请改用文件导入。")
    # Never forward the login cookie to a CDN.
    transcript = request_json(url, {"User-Agent": headers["User-Agent"]})
    segments = parse_transcript(json.dumps(transcript, ensure_ascii=False))
    return {"title": data["title"] + (f" · P{page} {part['part']}" if len(pages) > 1 else ""),
            "url": f"https://www.bilibili.com/video/{bvid}/?p={page}", "segments": segments,
            "subtitle": sub.get("lan_doc", sub.get("lan", "未知语言"))}


def set_config(data):
    base = str(data.get("base_url", "")).strip().rstrip("/")
    parsed = urlparse(base)
    if parsed.scheme not in ("https", "http") or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise AppError("服务地址应为没有密码和查询参数的 HTTP(S) 地址。")
    if parsed.scheme == "http" and parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
        raise AppError("远程模型服务请使用 HTTPS；本地模型可以使用 HTTP。")
    if accounts.current.get() and base not in accounts.PROVIDERS:
        raise AppError('服务地址不在管理员允许的服务商列表中。')
    model = str(data.get("model", "")).strip()
    if not model or len(model) > 200:
        raise AppError("请输入服务提供商支持的模型名称。")
    with CONFIG_LOCK:
        cfg=accounts.config(CONFIG)
        if cfg["base_url"] != base:
            cfg["api_key"] = ""
        cfg.update(base_url=base, model=model)
        if data.get("api_key"):
            cfg["api_key"] = str(data["api_key"]).strip()
        if data.get("clear_key"):
            cfg["api_key"] = ""
    return public_config()


def public_config():
    with CONFIG_LOCK:
        cfg=accounts.config(CONFIG)
        return {"base_url": cfg["base_url"], "model": cfg["model"], "has_key": bool(cfg["api_key"])}


def model_call(instruction, material):
    with CONFIG_LOCK:
        config = dict(accounts.config(CONFIG))
    if not config["model"]:
        raise AppError("请先在模型设置中填写服务地址和模型名称，或体验演示课程。")
    headers = {"Content-Type": "application/json"}
    if config["api_key"]:
        headers["Authorization"] = "Bearer " + config["api_key"]
    payload = {"model": config["model"], "messages": [
        {"role": "system", "content": PROMPT + "\n\n" + instruction},
        {"role": "user", "content": json.dumps(material, ensure_ascii=False)}]}
    result = request_json(config["base_url"].rstrip("/") + "/chat/completions", headers, payload)
    try:
        content = result["choices"][0]["message"]["content"].strip()
        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content)
        output = json.loads(content)
        if not isinstance(output, dict):
            raise ValueError()
        return output
    except (KeyError, TypeError, AttributeError, ValueError, IndexError):
        raise AppError("模型输出没有遵守 JSON 格式。请重试，或换用支持指令的模型；本次进度未修改。")


def string_field(data, key, maxlen=6000):
    value = data.get(key)
    if not isinstance(value, str) or not value.strip() or len(value) > maxlen:
        raise AppError(f"模型输出缺少有效字段：{key}。本次进度未修改。")
    return value.strip()


def validate_plan(raw, segments):
    plan = {key: string_field(raw, key) for key in ("main_idea", "overview", "coverage", "structure")}
    prereqs = raw.get("prerequisites", [])
    if not isinstance(prereqs, list) or len(prereqs) > 12 or not all(isinstance(p, str) and len(p) < 1500 for p in prereqs):
        raise AppError("模型前置知识格式无效。")
    plan["prerequisites"] = prereqs
    points = raw.get("points", [])
    if not isinstance(points, list) or not 1 <= len(points) <= 5:
        raise AppError("模型需要输出 1–5 个知识点；材料充分时应为 3–5 个。")
    ids = {s["id"] for s in segments}
    plan["points"] = []
    for i, point in enumerate(points):
        p = {key: string_field(point, key) for key in ("title", "claim", "why", "conditions", "pitfall", "question")}
        refs = point.get("refs", [])
        if not isinstance(refs, list) or not refs or not all(isinstance(r, str) and r in ids for r in refs):
            raise AppError("模型引用了不存在的字幕段落；请重试。本次没有保存虚构引用。")
        kind = point.get("kind", "原文")
        if kind not in ("原文", "推断", "补充"):
            raise AppError("模型观点类型无效。")
        p.update(id=f"K{i + 1}", refs=list(dict.fromkeys(refs)), kind=kind)
        plan["points"].append(p)
    return plan


PLAN_INSTRUCTION = '''建立学习地图，只输出 JSON：
{"main_idea":"一句话主旨","overview":"逻辑概要","coverage":"字幕实际覆盖范围与缺口",
"structure":"带关系的概念链","prerequisites":["必要前置知识"],
"points":[{"title":"知识点","claim":"核心观点","why":"价值","conditions":"适用条件",
"pitfall":"易错点","kind":"原文|推断|补充","refs":["真实段落 ID"],"question":"一个理解问题"}]}
材料充分时选 3–5 个知识点，材料极短时可以少于 3 个。以原文知识点为主，不能为了凑数创造内容。
refs 只能使用输入 segments 中的 ID，不得伪造。
不要包含练习答案。coverage 如实描述字幕首尾与画面信息缺口。'''

TURN_INSTRUCTION = '''根据当前题目和学习者动作反馈，只输出 JSON：
{"feedback":"准确部分与一个主要遗漏，或本轮提示/讲解",
"verdict":"correct|partial|incorrect|unassessed", "question":"一个下一步问题",
"advance":false,"evidence":"判断依据"}
action=answer 时评估实际回答。提示后的正确回答不能证明独立掌握。
当前 stage=explain 时，独立解释充分则 verdict=correct，advance=false，question 提出一个迁移题。
当前 stage=apply 时，应用充分则 verdict=correct，advance=true；否则用更小的问题继续。
action=hint 时只能给一级提示，verdict=unassessed，advance=false，question 继续当前子目标。
action=explain 时可直接讲解，再给一个新的理解题，verdict=unassessed，advance=false。
每轮只问一个问题。所有原文依据来自提供的 segments，指出补充知识。'''

DEMO_TEXT = '''主动回忆是暂时合上材料，尝试从记忆中说出或写出学过的内容，再对照原材料纠正遗漏。
重新阅读时的熟悉感不能直接证明自己已经掌握。能够独立解释和在新情境中使用，才提供更有力的证据。
练习可以从定义、原因、比较进入应用。例如学习缓存后，不只背缓存定义，还要解释它为何有用，判断新场景是否适合。
反馈应定位具体错误。遇到困难可以先得到一个方向提示，再尝试；依赖提示的正确回答需要之后独立验证。
学习结束时记录薄弱点，并安排下一次无提示复述或应用任务。'''


def demo_plan(segments):
    templates = [
        ("主动回忆", "合上材料，从记忆中重建，再对照纠错。", "暴露遗漏，获得真实反馈。", "已经学习过一段材料。", "把重读的熟悉感当成记得。", "S1", "学完一段视频后，怎样做一次主动回忆？"),
        ("掌握需要证据", "独立解释与新情境应用是更有力的掌握证据。", "区分熟悉与理解。", "用实际回答判断。", "提示后答对就标记完全掌握。", "S2", "为什么“看起来很熟悉”不足以证明你已经掌握？"),
        ("从理解走向应用", "练习逐步检验定义、原因、比较和应用。", "让知识可以迁移。", "具备必要前置知识。", "只背定义，不检验新情境。", "S3", "除了复述缓存的定义，还可以怎样检验理解？"),
        ("反馈与复习", "定位错误，分级提示，并在之后独立验证。", "把反馈转化为下一次练习。", "保存具体的薄弱点。", "把依赖提示的回答算作独立应用。", "S4", "提示后答对了，下一次练习应怎样安排？")]
    raw = {"main_idea": "用主动回忆、渐进提问与反馈检验理解。", "overview": "先回忆，再识别遗漏；从解释进入应用，最后记录薄弱点。",
           "coverage": "自带的 5 段文字示例，无视频、无时间戳。", "structure": "学习材料 → 主动回忆 → 发现遗漏 → 定位反馈 → 独立解释 → 新场景应用",
           "prerequisites": ["主动回忆：暂时离开原文，尝试从记忆中重建内容。"], "points": []}
    for title, claim, why, conditions, pitfall, ref, question in templates:
        raw["points"].append(dict(title=title, claim=claim, why=why, conditions=conditions, pitfall=pitfall, refs=[ref], question=question, kind="原文"))
    return validate_plan(raw, segments)


def active_point(s):
    return s["plan"]["points"][s["current"]]


def new_session(data):
    demo = data.get("demo") is True
    if demo:
        segments = parse_transcript(DEMO_TEXT)
        title, url = "如何真正学会一个知识点", ""
    else:
        segments = parse_transcript(data.get("transcript", ""))
        title, url = str(data.get("title", "未命名学习"))[:200], str(data.get("url", ""))[:500]
    goals = {"goal": str(data.get("goal", "理解并应用核心知识"))[:1000],
             "level": str(data.get("level", "基础了解"))[:200], "minutes": str(data.get("minutes", "20"))[:20]}
    plan = demo_plan(segments) if demo else validate_plan(model_call(PLAN_INSTRUCTION, {"segments": segments, "learning": goals}), segments)
    s = {"id": uuid.uuid4().hex, "title": title or "未命名学习", "url": url, "demo": demo,
         "segments": segments, "learning": goals, "plan": plan, "current": 0, "stage": "explain",
         "assisted": False, "ended": False, "records": {}, "messages": [], "created": time.time()}
    for point in plan["points"]:
        s["records"][point["id"]] = {"status": "未验证", "evidence": [], "skipped": False}
    add_message(s, "coach", "学习地图已准备好。" + ("这是固定演示课程，反馈不评判答案正确性。" if demo else "先从一个理解问题开始。"), plan["points"][0]["question"])
    save_session(s)
    return s


def add_message(s, role, text, question=""):
    s["messages"].append({"role": role, "text": text, "question": question, "time": time.time(),
                          "point": active_point(s)["id"]})


def latest_question(s):
    return next((m["question"] for m in reversed(s["messages"]) if m.get("question")), "")


def advance_point(s):
    s["assisted"] = False
    s["stage"] = "explain"
    if s["current"] + 1 >= len(s["plan"]["points"]):
        s["ended"] = True
        return ""
    s["current"] += 1
    return active_point(s)["question"]


def apply_turn(s, action, answer=""):
    if s["ended"]:
        raise AppError("本轮学习已结束。可以导出笔记，或从薄弱点继续。")
    point = active_point(s)
    record = s["records"][point["id"]]
    if action == "answer" and (not isinstance(answer, str) or not answer.strip() or len(answer) > 6000):
        raise AppError("请输入 1–6000 字符的回答。")
    if action == "skip":
        add_message(s, "user", "跳过当前知识点")
        record["skipped"] = True
        question = advance_point(s)
        add_message(s, "coach", "已跳过，掌握程度保留原有证据。" if question else "本轮已结束。跳过的知识点仍需练习。", question)
    elif action == "end":
        add_message(s, "user", "结束学习")
        s["ended"] = True
        add_message(s, "coach", "本次学习已保存。下方进度保留掌握证据；你可以导出笔记或继续薄弱点。")
    elif action in ("answer", "hint", "explain"):
        if s["demo"]:
            add_message(s, "user", answer.strip() if action == "answer" else {"hint": "给提示", "explain": "直接讲解"}[action])
            if action == "hint":
                feedback, question = "演示提示：关注原文中的动作、条件与检验方式。", latest_question(s)
            elif action == "explain":
                feedback, question = "演示讲解：" + point["claim"], "请用自己的例子说明这个观点。"
            else:
                feedback = "已保存你的回答。演示模式没有模型，不评判正确性，掌握状态保持未验证。"
                question = "把这个方法用于你下一次学习的视频，你会怎样做？" if s["stage"] == "explain" else advance_point(s)
                if s["stage"] == "explain" and question.startswith("把这个"):
                    s["stage"] = "apply"
            add_message(s, "coach", feedback, question)
        else:
            result = model_call(TURN_INSTRUCTION, {"action": action, "answer": answer,
                "question": latest_question(s), "point": point, "segments": s["segments"],
                "stage": s["stage"], "assisted": s["assisted"], "learning": s["learning"],
                "history": s["messages"][-12:], "record": record})
            feedback = string_field(result, "feedback")
            question = string_field(result, "question", 2000)
            evidence = string_field(result, "evidence", 2000)
            verdict = result.get("verdict")
            if verdict not in ("correct", "partial", "incorrect", "unassessed") or not isinstance(result.get("advance"), bool):
                raise AppError("模型反馈格式无效。本次回答未修改进度，请重试。")
            if action != "answer" and (verdict != "unassessed" or result["advance"]):
                raise AppError("模型试图把提示或讲解算作掌握，已拒绝更新。请重试。")
            add_message(s, "user", answer.strip() if action == "answer" else {"hint": "给提示", "explain": "直接讲解"}[action])
            record["evidence"].append({"action": action, "answer": answer, "question": latest_question(s),
                                       "verdict": verdict, "reason": evidence, "assisted": s["assisted"], "stage": s["stage"]})
            if action in ("hint", "explain"):
                s["assisted"] = True
                if record["status"] == "未验证":
                    record["status"] = "需要提示"
                if action == "explain":
                    s["stage"] = "explain"
            elif verdict == "correct":
                if s["assisted"]:
                    feedback += "\n这次有提示支持，还需要一次独立解释验证。"
                    s["assisted"] = False
                    s["stage"] = "explain"
                    question = "请合上概要，用你自己的例子解释这个知识点的作用和适用条件。"
                elif s["stage"] == "explain":
                    record["status"] = "可独立解释"
                    s["stage"] = "apply"
                elif result["advance"]:
                    record["status"] = "可迁移应用"
                    question = advance_point(s)
                    feedback += "\n这个知识点已有独立解释与应用证据。" + ("进入下一个知识点。" if question else "本轮学习已完成。")
            elif verdict in ("partial", "incorrect"):
                s["assisted"] = True
                if record["status"] == "未验证":
                    record["status"] = "需要提示"
            add_message(s, "coach", feedback, question)
    else:
        raise AppError("未知学习动作。")
    save_session(s)
    return s


def resume_session(s):
    if not s["ended"]:
        return s
    candidates = [i for i, p in enumerate(s["plan"]["points"]) if s["records"][p["id"]]["status"] != "可迁移应用"]
    if not candidates:
        raise AppError("所有知识点已有迁移证据。可以重新导入材料，设定更深入的目标。")
    s.update(ended=False, current=candidates[0], stage="explain", assisted=False)
    add_message(s, "coach", "继续检验薄弱点；先做一次无提示解释。", active_point(s)["question"])
    save_session(s)
    return s


def export_notes(s):
    lines = ["# " + s["title"], "", "模式：" + ("固定演示（不评判正确性）" if s["demo"] else "模型学习"),
             "目标：" + s["learning"]["goal"], "来源：" + (s["url"] or "导入字幕/文本"), "",
             "## 主旨", s["plan"]["main_idea"], "", "## 概要", s["plan"]["overview"], "",
             "覆盖范围：" + s["plan"]["coverage"], "", "## 知识关系", s["plan"]["structure"]]
    for p in s["plan"]["points"]:
        r = s["records"][p["id"]]
        lines.extend(["", "## " + p["title"], p["claim"], "价值：" + p["why"], "条件：" + p["conditions"],
                      "易错点：" + p["pitfall"], "观点类型：" + p["kind"], "依据：" + ", ".join(p["refs"]),
                      "掌握状态：" + r["status"] + ("（曾跳过）" if r["skipped"] else "")])
        for e in r["evidence"]:
            lines.extend(["- 判断依据：" + e["reason"] + ("（有提示）" if e["assisted"] else "（无提示）")])
    weak = [p["title"] for p in s["plan"]["points"] if s["records"][p["id"]]["status"] != "可迁移应用"]
    lines.extend(["", "## 下一次练习", "仍需验证：" + ("、".join(weak) or "已有迁移证据，可提高难度"),
                  "实践任务：选择一个新情境，独立说明一个核心观点的用途、条件与反例。", "", "## 学习对话"])
    for m in s["messages"]:
        lines.extend(["", ("我：" if m["role"] == "user" else "教练：") + m["text"]])
        if m["question"]:
            lines.append("问题：" + m["question"])
    lines.extend(["", "## 原始材料"])
    for seg in s["segments"]:
        lines.append(f"[{seg['id']}] " + (f"{seg['start']}–{seg['end']} " if seg["start"] else "") + seg["text"])
    return "\n".join(lines)


class Handler(BaseHTTPRequestHandler):
    def handle_one_request(self):
        marker=accounts.current.set(None)
        try:super().handle_one_request()
        finally:accounts.current.reset(marker)

    def account_api(self):
        if getattr(self.server,'multi_user',False) and self.path.startswith('/api/'):
            account=accounts.lookup(self.headers)
            if not account:raise PermissionError('请先登录你的账号。')
            accounts.current.set(account)
            init_db()

    def login_response(self,data):
        if self.path=='/api/auth/logout':
            accounts.logout(self.headers);token='';user=None
        else:
            token,user=accounts.authenticate(data,self.path=='/api/auth/register',self.client_address[0])
        payload=json.dumps({'user':user}).encode()
        self.send_response(200)
        secure='; Secure' if accounts.ORIGIN.startswith('https:') else ''
        self.send_header('Set-Cookie','study_login='+token+'; HttpOnly; SameSite=Strict; Path=/; Max-Age='+('43200' if token else '0')+secure)
        self.send_header('Content-Type','application/json')
        self.send_header('Cache-Control','no-store')
        self.send_header('Content-Length',str(len(payload)))
        self.end_headers();self.wfile.write(payload)

    def log_message(self, fmt, *args):
        # Do not log request bodies or API credentials.
        if '/pair?' not in self.path:
            print(f"[{self.log_date_time_string()}] {fmt % args}")

    def send_data(self, data, status=200, content_type="application/json; charset=utf-8"):
        payload = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'")
        self.end_headers()
        self.wfile.write(payload)

    def check_local(self, mutation=False):
        expected = f"127.0.0.1:{self.server.server_port}"
        allowed = {expected, f"localhost:{self.server.server_port}"} | ALLOWED_HOSTS
        multi=getattr(self.server,'multi_user',False)
        if multi and accounts.ORIGIN:allowed.add(urlparse(accounts.ORIGIN).netloc)
        if self.headers.get("Host") not in allowed:
            raise AppError("仅支持本机访问。")
        origin = self.headers.get("Origin")
        origins=({'http://'+expected,f'http://localhost:{self.server.server_port}',accounts.ORIGIN} if multi else {'http://'+host for host in allowed})
        if origin and origin not in origins:
            raise AppError("跨站请求已拒绝。")
        if mutation and self.headers.get("Content-Type", "").split(";")[0] != "application/json":
            raise AppError("请求需要 application/json。")
        if not multi and self.client_address[0] not in ('127.0.0.1','::1'):
            from http.cookies import SimpleCookie
            cookie=SimpleCookie(self.headers.get('Cookie',''))
            value=cookie.get('study_pair')
            if not PAIR_TOKEN or not value or not hmac.compare_digest(value.value,PAIR_TOKEN):
                raise AppError('请在电脑端获取配对地址，并在手机 App 中连接。')

    def do_GET(self):
        try:
            if self.path.startswith('/pair?') and not getattr(self.server,'multi_user',False):
                parsed=urlparse(self.path)
                token=parse_qs(parsed.query).get('token',[''])[0]
                if PAIR_TOKEN and hmac.compare_digest(token,PAIR_TOKEN) and self.headers.get('Host') in ALLOWED_HOSTS:
                    self.send_response(302)
                    self.send_header('Set-Cookie','study_pair='+PAIR_TOKEN+'; HttpOnly; SameSite=Strict; Path=/')
                    self.send_header('Location','/')
                    self.send_header('Cache-Control','no-store')
                    self.end_headers()
                    return
            self.check_local()
            parsed = urlparse(self.path)
            if parsed.path=='/api/auth/me':
                user=accounts.lookup(self.headers) if getattr(self.server,'multi_user',False) else None
                return self.send_data({'multi_user':getattr(self.server,'multi_user',False),'user':{'id':user['id'],'name':user['name']} if user else None,'providers':accounts.PROVIDERS})
            self.account_api()
            if parsed.path == "/api/config":
                return self.send_data(public_config())
            if parsed.path == "/api/sessions":
                return self.send_data(list_sessions())
            if parsed.path == "/api/session":
                sid = parse_qs(parsed.query).get("id", [""])[0]
                return self.send_data(get_session(sid))
            if parsed.path == "/api/export":
                sid = parse_qs(parsed.query).get("id", [""])[0]
                return self.send_data({"markdown": export_notes(get_session(sid))})
            allowed = {"/": ("index.html", "text/html; charset=utf-8"),
                       "/app.js": ("app.js", "application/javascript; charset=utf-8"),
                       "/style.css": ("style.css", "text/css; charset=utf-8"),
                       "/workspace.js": ("workspace.js", "application/javascript; charset=utf-8"),
                       "/auth.js": ("auth.js", "application/javascript; charset=utf-8")}
            if parsed.path not in allowed:
                return self.send_data({"error": "页面不存在"}, 404)
            name, content_type = allowed[parsed.path]
            content=(ROOT/'static'/name).read_bytes()
            if name=='style.css' and getattr(self.server,'multi_user',False):
                content=re.sub(rb'url\("data:image/jpeg;base64,[^"]+"\)',b'none',content)
            self.send_data(content, content_type=content_type)
        except PermissionError as exc:
            self.send_data({'error':str(exc)},401)
        except AppError as exc:
            self.send_data({"error": str(exc)}, 400)

    def do_POST(self):
        try:
            self.check_local(mutation=True)
            length = int(self.headers.get("Content-Length", 0))
            if not 0 < length <= MAX_BODY:
                raise AppError("请求为空或过大。")
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise AppError("请求格式无效。")
            if self.path in ('/api/auth/register','/api/auth/login','/api/auth/logout'):
                if not getattr(self.server,'multi_user',False):raise AppError('当前为个人模式。')
                try:return self.login_response(data)
                except ValueError as exc:raise AppError(str(exc))
            self.account_api()
            if self.path.startswith(('/api/workspace/','/api/pdf/')):
                return self.send_data(workspace_features.handle(sys.modules[__name__],self.path,data))
            if self.path == "/api/config":
                return self.send_data(set_config(data))
            if self.path == "/api/import":
                return self.send_data(import_bilibili(str(data.get("url", ""))))
            if self.path == "/api/start":
                with SESSION_LOCK:
                    result = new_session(data)
                return self.send_data(result)
            if self.path in ("/api/turn", "/api/resume"):
                with SESSION_LOCK:
                    s = get_session(str(data.get("id", "")))
                    if data.get("version") != s["updated"]:
                        raise AppError("学习进度已在另一页面更新，请重新打开这次学习。")
                    result = resume_session(s) if self.path == "/api/resume" else apply_turn(s, data.get("action"), data.get("answer", ""))
                return self.send_data(result)
            self.send_data({"error": "接口不存在"}, 404)
        except PermissionError as exc:
            self.send_data({'error':str(exc)},401)
        except AppError as exc:
            self.send_data({"error": str(exc)}, 400)
        except (ValueError, TypeError):
            self.send_data({"error": "请求数据格式无效。"}, 400)
        except Exception:
            self.send_data({"error": "本地处理失败，已有学习记录保留。请检查终端或重试。"}, 500)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--open", action="store_true")
    parser.add_argument('--multi-user',action='store_true')
    parser.add_argument('--host',default='127.0.0.1')
    args = parser.parse_args()
    init_db()
    if args.host not in ('127.0.0.1','localhost') and (not args.multi_user or not accounts.ORIGIN.startswith('https://')):
        parser.error('公网运行需要多用户模式及 HTTPS STUDY_PUBLIC_ORIGIN，配合 TLS 反向代理。')
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.multi_user=args.multi_user
    print(f"Bili Study is ready: http://127.0.0.1:{args.port}", flush=True)
    if args.open:
        webbrowser.open(f"http://127.0.0.1:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
