"""Content templates and executable visual tokens are deliberately independent."""

import re
from copy import deepcopy

from app.models.favorite import FavoriteTargetType
from app.schemas.studio import StudioBrief, StudioDraft, StudioShot

TEMPLATES = [
    {"id": "cinematic_arc", "name": "叙事短片", "category": "视频结构", "description": "用一条清晰的视觉动作线，把主题推进到情绪转折。", "image": None, "modes": ["video_prompt", "animation_video"], "beats": [
        "用一个具体的视觉悬念开场", "交代主角、环境与欲望", "让阻力打破原有秩序",
        "以行动而非解释推进冲突", "用选择完成情绪与意义的转折", "留下与开场呼应的余韵",
    ]},
    {"id": "visual_essay", "name": "视觉论述", "category": "视频结构", "description": "把一个现象拆成观察、证据、对照和结论，适合知识与热点内容。", "image": None, "modes": ["video_prompt", "animation_video"], "beats": [
        "呈现一个矛盾现象", "用可核对的事实界定问题", "给出第一个观察角度",
        "以对照画面检验解释", "将个体问题连接到更大背景", "以开放问题收束",
    ]},
    {"id": "product_reveal", "name": "产品演绎", "category": "视频结构", "description": "从痛点进入，用连续动作展示产品价值，最后落到真实使用场景。", "image": None, "modes": ["video_prompt", "animation_video"], "beats": [
        "展示痛点的视觉隐喻", "首次揭示主体轮廓", "展示真实功能与使用动作",
        "用一个前后对比证明价值", "回到使用者的情绪", "定格主体与必要标题",
    ]},
    {"id": "lyric_journey", "name": "歌词叙事", "category": "MV结构", "description": "让歌词成为时间轴，用人物、空间和意象承接歌曲情绪。", "image": None, "modes": ["music_video"], "beats": [
        "前奏建立母题", "主歌建立节奏", "副歌展开视觉", "桥段改变构图", "末段回收母题", "尾奏留白",
    ]},
    {"id": "beat_geometry", "name": "节奏与几何", "category": "MV结构", "description": "用形状、色块和运动响应鼓点，适合电子、舞曲和抽象音乐。", "image": None, "modes": ["music_video"], "beats": [
        "建立几何母题", "逐层增加节奏", "强调副歌", "收敛元素", "重复并变奏", "结束与留白",
    ]},
    {"id": "explainer", "name": "问题拆解", "category": "文章结构", "description": "先提出问题，再用背景、证据与建议把复杂议题讲清楚。", "image": None, "modes": ["article"], "beats": [
        "问题", "背景", "核心解释", "证据与反例", "具体建议", "结尾",
    ]},
    {"id": "personal_essay", "name": "个人观点", "category": "文章结构", "description": "从具体场景出发，形成个人判断，再回到可执行的现实落点。", "image": None, "modes": ["article"], "beats": [
        "具体场景", "个人判断", "理由", "反方观点", "判断边界", "回到场景",
    ]},
]

STYLES = [
    {"id": "bauhaus", "name": "包豪斯", "category": "几何现代", "description": "原色、几何形与功能网格组成清晰有力的视觉秩序。", "image": None, "colors": ["#F4F4F0", "#D92332", "#193DB1", "#111111"],
     "background": "#F4F4F0", "foreground": "#111111", "accent": "#D92332", "secondary": "#193DB1",
     "rules": ["基础圆、方与直线", "非对称的功能网格", "无衬线粗标题", "纯色块与利落边界"],
     "native_mv": True},
    {"id": "constructivism", "name": "构成主义", "category": "几何现代", "description": "对角线、红黑对比和厚重字形制造强烈的运动感。", "image": None, "colors": ["#EFEAE1", "#C62627", "#171717"],
     "background": "#EFEAE1", "foreground": "#171717", "accent": "#C62627", "secondary": "#171717",
     "rules": ["强对角构图", "红黑双色强调", "厚重字体与几何楔形", "高密度的视觉节奏"],
     "native_mv": True},
    {"id": "swiss", "name": "瑞士国际主义", "category": "编辑排版", "description": "严格网格、左对齐和大面积留白，适合信息型内容。", "image": None, "colors": ["#FFFFFF", "#151515", "#D02435"],
     "background": "#FFFFFF", "foreground": "#151515", "accent": "#D02435", "secondary": "#151515",
     "rules": ["严格列网格", "左对齐与清晰字号阶梯", "大面积留白", "信息层级优先"],
     "native_mv": True},
    {"id": "brutalism", "name": "粗野主义", "category": "实验视觉", "description": "硬边框、高对比和直接的界面语言，适合观点鲜明的表达。", "image": None, "colors": ["#E7FF00", "#181818", "#FFFFFF"],
     "background": "#181818", "foreground": "#FFFFFF", "accent": "#E7FF00", "secondary": "#FFFFFF",
     "rules": ["硬边框和裸露结构", "强对比的大字号", "直接的切换", "原始材质与界面感"],
     "native_mv": True},
    {"id": "deconstruction", "name": "解构", "category": "实验视觉", "description": "错位、断裂网格和局部重叠形成可读的视觉张力。", "image": None, "colors": ["#F6F6F6", "#141414", "#16715D"],
     "background": "#F6F6F6", "foreground": "#141414", "accent": "#16715D", "secondary": "#141414",
     "rules": ["有意错位与阅读路径并置", "断裂网格与文字层次", "少量重叠", "字幕保持清晰"],
     "native_mv": False},
    {"id": "realism", "name": "写实", "category": "影像质感", "description": "自然光线、真实材质与稳定空间连续性，适合人物和生活场景。", "image": None, "colors": ["#E6E8E4", "#222722", "#557966"],
     "background": "#E6E8E4", "foreground": "#222722", "accent": "#557966", "secondary": "#222722",
     "rules": ["有物理依据的光线与材质", "稳定人物和空间连续性", "克制调色", "真实质感与生活尺度"],
     "native_mv": False},
    {"id": "neo_expressionism", "name": "新表现主义", "category": "情绪绘画", "description": "笔触、非自然色与材料纹理把情绪推到画面前景。", "image": None, "colors": ["#F7EEED", "#BA2544", "#22534D"],
     "background": "#F7EEED", "foreground": "#1E1E1E", "accent": "#BA2544", "secondary": "#22534D",
     "rules": ["情绪驱动的笔触和形体", "材料纹理与非自然色", "保留文字可读性", "强烈的情绪对比"],
     "native_mv": False},
]

FREEFORM_BEATS = {
    "article": ["切入场景", "核心判断", "展开论据", "回应疑问", "具体落点", "收束"],
    "music_video": ["建立母题", "进入情绪", "展开视觉", "节奏转折", "回收意象", "留白结束"],
    "video_prompt": ["建立视觉悬念", "交代主体", "推动动作", "制造转折", "完成表达", "留下余韵"],
    "animation_video": ["提出问题", "拆解概念", "展示关系", "用例子说明", "回到结论", "留下记忆点"],
}


def creative_text(text: str) -> str:
    """Keep creative content while dropping generated production disclaimers."""
    warning = re.compile(
        r"版权|授权|使用权|待核查|待核对|待确认|未核查|未核对|未验证|未独立"
        r"|未提供|未上传|未获取|未接入|未完成|未确认|未核实|信息不足|来源不足|素材不足"
        r"|不虚构|不伪造|不要(?:执行|添加|生成|使用|读取|抓取|修改|宣称|重复)"
        r"|禁止(?:执行|逐帧|添加|使用|生成|声明|读取|抓取|出现)"
        r"|不得(?:执行|宣称|添加|使用|生成|读取|修改|泄露)"
        r"|不允许|不生成|不重写|不添加|不做|不认为"
        r"|不宣称|不是口播|不写(?:具体)?歌词|不出现(?:真实歌词|可读|品牌)"
        r"|不能(?:保证|确认|验证|提供)|尚未|风险提示|避免|防止|来源与风险|版权与来源"
        r"|仅作参考|仅供参考|待(?:官方|最终|音频|歌词|校准)|无歌词字幕|仅在获得官方"
        r"|只列结构占位|brief\.bilingual"
        r"|\b(?:copyright|licensing|rights confirmation|do not|must not|no (?:readable )?(?:text|watermark|brand logo|logo|lyrics))\b",
        re.IGNORECASE,
    )
    text = re.sub(r"[（(]\s*(?:暂定|待核查|待确认)\s*[）)]", "", text)
    text = re.sub(r"\s*[/|·]\s*(?:待核查|待核对|待确认)\s*", "", text)
    text = re.sub(r"暂定(?=总长|时长|方案|版本|标题)", "", text)
    text = re.sub(
        r"\s+(?:with\s+)?(?:no|without)\s+(?:readable\s+)?(?:text|lyrics|words|watermarks?|brand\s+logos?|logos?)\b[^,.;]*",
        "", text, flags=re.IGNORECASE,
    )
    cleaned = []
    for paragraph in text.splitlines():
        if re.match(r"^\s*(?:#+\s*)?(来源与风险|版权|授权|风险提示)", paragraph):
            continue
        parts = re.findall(r"[^。！？；;，,]+[。！？；;，,]*", paragraph)
        kept = "".join(part for part in parts if not warning.search(part))
        kept = re.sub(r"([，,；;])(?:\s*[，,；;])+", r"\1", kept)
        kept = kept.strip().rstrip("；;，,")
        if kept:
            cleaned.append(kept)
    return "\n".join(cleaned)


def clean_draft(draft: StudioDraft) -> StudioDraft:
    return draft.model_copy(update={
        **{key: creative_text(getattr(draft, key)) for key in ("title", "logline", "body")},
        "shots": [
            shot.model_copy(update={
                key: creative_text(getattr(shot, key))
                for key in ("beat", "visual", "camera", "audio", "transition", "caption", "prompt")
            })
            for shot in draft.shots
        ],
    })


def _custom_template(item) -> dict:
    snapshot = item.snapshot if isinstance(item.snapshot, dict) else {}
    modes = list(snapshot["modes"]) if isinstance(snapshot.get("modes"), list) else ["animation_video", "video_prompt", "article", "music_video"]
    if "video_prompt" in modes and "animation_video" not in modes:
        modes.append("animation_video")
    beats = snapshot.get("beats") or ["建立切口", "展开内容", "推进观点", "形成转折", "落到行动"]
    return {
        "id": f"favorite:template:{item.id}",
        "name": item.title,
        "category": snapshot.get("category") or "我的模板",
        "description": item.note or snapshot.get("description") or "来自收藏夹的自定义内容结构。",
        "image": item.cover_url or snapshot.get("image") or (f"/api/v1/favorites/{item.id}/file" if snapshot.get("local_path") else None),
        "modes": modes,
        "beats": beats,
        "custom": True,
        "favorite_id": item.id,
    }


def _custom_style(item) -> dict:
    snapshot = item.snapshot if isinstance(item.snapshot, dict) else {}
    colors = [color for color in snapshot.get("colors", []) if isinstance(color, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", color)][:5]
    colors = colors or ["#F1F5F9", "#2563EB", "#0F172A"]
    while len(colors) < 3:
        colors.append(colors[-1])
    return {
        "id": f"favorite:style:{item.id}",
        "name": item.title,
        "category": snapshot.get("category") or "我的风格",
        "description": item.note or snapshot.get("description") or "来自收藏夹的自定义视觉风格。",
        "image": item.cover_url or snapshot.get("image") or (f"/api/v1/favorites/{item.id}/file" if snapshot.get("local_path") else None),
        "colors": colors,
        "background": colors[0],
        "foreground": colors[-1],
        "accent": colors[1],
        "secondary": colors[-1],
        "rules": snapshot.get("rules") or ["主体与空间保持连续", "信息层级清晰", "色板贯穿全片"],
        "native_mv": bool(snapshot.get("native_mv", True)),
        "custom": True,
        "favorite_id": item.id,
    }


def catalog() -> dict:
    return deepcopy({"templates": TEMPLATES, "styles": STYLES})


async def catalog_for_user(db, user_id: int) -> dict:
    from app.repositories.favorite_repo import FavoriteRepo

    repo = FavoriteRepo(db, user_id)
    templates, _ = await repo.list_paginated(page=1, page_size=200, target_type=FavoriteTargetType.TEMPLATE)
    styles, _ = await repo.list_paginated(page=1, page_size=200, target_type=FavoriteTargetType.STYLE)
    result = catalog()
    for key, items, convert in (("templates", templates, _custom_template), ("styles", styles, _custom_style)):
        builtin_ids = {preset["id"] for preset in result[key]}
        for item in items:
            if item.status == "archived" or item.target_key in builtin_ids:
                continue
            result[key].append(convert(item))
    return result


def _default_template(mode: str) -> dict:
    preferred = {
        "article": "explainer",
        "music_video": "lyric_journey",
        "video_prompt": "cinematic_arc",
        "animation_video": "visual_essay",
    }.get(mode, "cinematic_arc")
    return next(item for item in TEMPLATES if item["id"] == preferred)


def resolve(
    brief: StudioBrief,
    *,
    templates: list[dict] | None = None,
    styles: list[dict] | None = None,
) -> tuple[dict, dict | None]:
    """Resolve suggestions without turning them into creative constraints.

    A missing template/style is a valid freeform brief. Explicitly selected
    values are still checked so a typo is surfaced, while a mode mismatch
    falls back to the mode's default structure instead of blocking project
    creation.
    """
    template_pool = templates or TEMPLATES
    style_pool = styles or STYLES
    template = next((item for item in template_pool if item["id"] == brief.template_id), None)
    if brief.template_id is None:
        template = None
    elif template is None or brief.mode not in template["modes"]:
        template = _default_template(brief.mode)
    style = next((item for item in style_pool if item["id"] == brief.style_id), None)
    return template, style


def compile_draft(brief: StudioBrief, previous: StudioDraft, template_override: dict | None = None) -> StudioDraft:
    template = template_override
    if template is None:
        template, _ = resolve(brief)
    beats = template["beats"] if template else FREEFORM_BEATS[brief.mode]
    if brief.mode == "article":
        body = "\n\n".join(
            f"## {beat}\n围绕「{brief.theme}」展开这一部分，先给出具体事实，再落到读者可以理解的判断。"
            for beat in beats
        )
        return StudioDraft(
            title=brief.theme,
            logline=brief.intent or f"用清晰的事实和例子讲清楚「{brief.theme}」。",
            body=body,
            provenance="compiled",
        )
    animation = brief.mode == "animation_video" or brief.presentation in {"kinetic", "ascii", "tui"}
    body = ""
    if brief.mode in {"video_prompt", "animation_video"}:
        body = "\n\n".join(
            f"### {beat}\n旁白：围绕「{brief.theme}」解释这一层内容。\n"
            + ("动画动作：用图形、数字和动作把这一层关系呈现出来。" if animation else "画面：设计主体、动作与场景。")
            for beat in beats
        )
    elif brief.mode == "music_video":
        body = "\n\n".join(
            f"### {beat}\n视觉段落：围绕「{brief.theme}」展开这一段的情绪、意象和节奏。"
            for beat in beats
        )
    shots = [
        StudioShot(
            seconds=round(brief.duration_seconds / len(beats), 3),
            beat=beat,
            visual=(
                f"围绕「{brief.theme}」：{beat}。用图形、箭头、数字和具体例子把因果关系画出来。"
                if animation else
                f"围绕「{brief.theme}」：{beat}。以具体主体的行动或形态变化表达。"
            ),
            camera=(
                "二维动画构图，元素分层进入；用平移、缩放和局部强调引导视线。"
                if animation else
                "明确主体与空间关系；交替使用建立镜头、动作中景和细节特写。"
            ),
            audio=(
                "旁白解释核心概念；数字变化、图形出现和转场与语句重音同步。"
                if animation else
                "环境声建立空间；音乐随叙事推进；关键动作与音效呼应。"
            ),
            transition="动作或构图匹配切换",
            prompt=(
                f"动画讲解「{brief.theme}」的{beat}：用清晰图形、标注、数字和动作解释一个因果关系。"
                if animation else
                f"设计这一段的主体、场景和动作：{beat}。保持相邻镜头的主体、光线与运动方向连续。"
            ),
        )
        for beat in beats
    ]
    shots[-1].seconds = round(brief.duration_seconds - sum(shot.seconds for shot in shots[:-1]), 3)
    return StudioDraft(
        title=brief.theme,
        logline=brief.intent or f"用一条清晰的视觉线索讲明「{brief.theme}」。",
        body=body,
        shots=shots,
        cues=previous.cues,
        provenance="compiled",
    )


def production_prompt(
    brief: StudioBrief,
    draft: StudioDraft,
    source: dict,
    *,
    template_override: dict | None = None,
    style_override: dict | None = None,
) -> str:
    draft = clean_draft(draft)
    if brief.mode == "article":
        return creative_text("\n\n".join([
            f"# {draft.title or brief.theme}", f"任务：文章成稿；主题：{brief.theme}",
            f"创作意图：{brief.intent or draft.logline}", draft.logline, draft.body,
            "交付：文章正文与可编辑 Markdown。",
        ]))
    template = template_override
    style = style_override
    if template is None and style is None:
        template, style = resolve(brief)
    elif template is None:
        template, _ = resolve(brief)
    elif style is None:
        _, style = resolve(brief)
    style_name = style["name"] if style else "自由视觉"
    style_colors = ", ".join(style["colors"]) if style else "由制作阶段决定"
    style_rules = style["rules"] if style else ["保持主体连续性", "字幕由排版层绘制", "信息层级清晰"]
    template_name = template["name"] if brief.template_id else "自由结构"
    task_name = {
        "article": "文章成稿",
        "music_video": "音乐 MV",
        "video_prompt": "普通视频",
        "animation_video": "动画讲解视频",
    }[brief.mode]
    lines = [
        f"# {draft.title or brief.theme}",
        f"任务：{task_name}；主题：{brief.theme}",
        f"成片时长：{brief.duration_seconds:g} 秒；画幅：{brief.aspect_ratio}",
        f"受众：{brief.audience or '创作者自定'}；内容结构：{template_name}",
        f"创作意图：{brief.intent or draft.logline or '由导演方案明确主题与情绪变化'}",
        "", "## 成稿内容", draft.logline, draft.body,
        "模板与视觉风格作为本次制作的参考层，创作者可在制作阶段继续调整。",
        "",
    ]
    lines += [
            f"## 视觉规则：{style_name}",
            f"色板：{style_colors}",
            *[f"- {rule}" for rule in style_rules],
            "字体槽使用 Noto Sans SC / Noto Serif SC 等开源字体；中文文字由排版层绘制。",
            f"表现方案：{brief.presentation or '自由安排'}；制作路径：{brief.production or '导演安排'}",
            (
                "完整中文旁白配套中文字幕，按配音逐句显示；工作台生成字幕时间轴并渲染到 MP4，随工程交付 SRT。"
                if brief.mode == "animation_video"
                else "电影字幕卡中英双语。" if brief.bilingual else "字幕跟随内容节奏出现。"
            ),
            "", "## 分镜与声音",
    ]
    cursor = 0.0
    for index, shot in enumerate(draft.shots, 1):
        end = cursor + shot.seconds
        lines += [
                f"### 镜头 {index:02d} | {cursor:.3f}–{end:.3f}s | {shot.beat}",
                f"画面：{shot.visual}", f"镜头：{shot.camera}", f"声音：{shot.audio}",
                f"衔接：{shot.transition}",
                f"字幕：{shot.audio if brief.mode == 'animation_video' else shot.caption or '跟随画面排版'}",
                f"生成提示词：{shot.prompt}",
                f"执行重点：{'; '.join(style_rules)}。",
        ]
        cursor = end
    if draft.cues:
        lines += ["", "## 歌词时间轴（音频时间轴）"]
        lines += [f"[{cue.time:.3f}s] {cue.text}" for cue in draft.cues]
    lines += ["", "## 制作与交付"]
    if brief.production == "code_animation":
        lines += [
            "交付可运行的动画工程、画面脚本和最终 MP4。动画项目保留源工程，视频由工程渲染生成。",
            "动态排版使用 Canvas 或 CSS；3D 使用 Three.js；ASCII/TUI 使用字符网格或终端界面。",
            "中文使用本地字体槽，输出源工程、资源清单、可复现渲染命令、音画同步检查与最终视频。",
        ]
    elif brief.production == "video_model":
        lines += [
            "先建立主体参考图与连续性表，再以分镜级提示词逐镜生成。",
            "每镜交付独立生成提示词、参考图需求、可用片段和实际时长；审核后再剪辑。",
            "音效、音乐和字幕独立制作；交付剪辑时间轴、字幕与素材清单。",
        ]
    elif brief.production == "native_mv":
        lines += ["这是音乐 MV 渲染路径：以音频为时间轴，读取 LRC，按歌曲段落和歌词节拍渲染动态画面。"]
    else:
        lines += ["制作路径由导演确定；交付可执行分镜、提示词、音频与字幕计划。"]
    return creative_text("\n".join(line for line in lines if line is not None))
