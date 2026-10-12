# -*- coding: utf-8 -*-
"""真实社交回复训练器 — Windows/macOS/Linux desktop app using only Python's standard library."""
import tkinter as tk
from tkinter import ttk, messagebox
import json
import os
import threading
import urllib.request
import urllib.error
from pathlib import Path

APP_DIR = Path(os.environ.get("APPDATA", str(Path.home() / ".config"))) / "SocialReplyTrainer"
SETTINGS_FILE = APP_DIR / "settings.json"
CUSTOM_SCENES_FILE = APP_DIR / "custom_scenes.json"

# This prompt is embedded in the program and is also provided as AI_PROMPT.md.
SYSTEM_PROMPT = r"""你是“真实社交回复训练器”的沟通教练。你的任务是根据用户提供的真实社交情景，生成自然、可直接说出口的中文回复。

核心原则：
1. 目标是清晰表达需求、偏好和边界；既不讨好，也不羞辱、操纵或报复对方。
2. 先理解现实情境，特别是权力差异、经济依赖、职场后果、熟人社会中的面子与冲突成本。不要机械地鼓励强硬对抗；必要时优先低冲突、可执行的方案。
3. 不要默认对方恶意，也不要无条件替对方找借口。区分单次意外和反复出现的模式。
4. 不要为了显得成熟而过度解释、说教、使用心理学术语。回复要简洁、口语化、符合真实中文对话。
5. 提供两种可用回复：soft（温和但清晰）、firm（坚定直接）。坚定不等于攻击；温和不等于退让。
6. bad 字段说明常见但不理想的反应，例如讨好、憋着不说、被动攻击、讽刺、冷暴力或冲动升级；不要羞辱用户。
7. rule 字段用一到三句话解释关键原则，并给出适用于这个场景的判断依据。
8. 如果信息不足，基于合理假设给出稳妥版本，不要反问；不要编造情景里没有提供的事实。
9. 如果情景涉及威胁、暴力、跟踪、严重职场报复或现实安全风险，优先考虑安全、留证、寻求可信支持或正式渠道，不要只教一句“强势回复”。

只返回一个合法 JSON 对象，不要使用 Markdown 代码围栏，也不要添加 JSON 以外的文字。结构必须严格如下：
{
  "soft": "温和但清晰、可以直接说出口的回复",
  "firm": "坚定直接、但不过度攻击的回复",
  "bad": "这个情景下容易出现的不理想反应",
  "rule": "简洁解释关键沟通原则"
}
所有字段都必须是非空字符串，使用简体中文。"""

DEFAULT_MODEL = "deepseek-flash"
API_URL = "https://api.deepseek.com/chat/completions"


def _load_json(path, fallback):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError, TypeError):
        return fallback


def _save_json(path, data):
    APP_DIR.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    temp_path.replace(path)

SCENES = [
    {
        "group": "同事", "title": "同事拒绝帮忙后，又来吐槽工作",
        "trigger": "你刚拒绝了同事一个请求。她先说“好吧”，一小时后又发消息向你吐槽工作。",
        "soft": "刚看到，听起来你今天确实挺烦的。我现在不太有精力聊工作，先缓缓吧。",
        "firm": "我知道你现在挺烦的，不过我今晚不想继续聊工作，就先到这儿吧。",
        "bad": "已读不回是为了让她知道自己不爽；或者讽刺一句“怎么又来找我了？”。",
        "rule": "可以关心她，但不必因为她有情绪，就承担起安抚她的责任。你不想聊，可以温和地结束对话。"
    },
    {
        "group": "同事", "title": "同事临时请你帮忙",
        "trigger": "快下班了，同事突然说：“你帮我把这个做了呗，反正你也没什么事。”",
        "soft": "我今天还有自己的安排，这个没法帮你做完。你看看能不能找别人协调一下。",
        "firm": "这个任务我不接。之后需要我协助的话，请提前沟通具体内容和时间。",
        "bad": "“行行行，都给我吧。”然后回头抱怨；或者说“你自己没手吗？”。",
        "rule": "拒绝任务，不等于否定这个人。说明自己的安排，不必攻击对方。"
    },
    {
        "group": "工作", "title": "下班后仍被要求处理工作",
        "trigger": "晚上十点，工作群里有人私聊：“这个很急，你今晚赶紧弄一下。”但没有说明截止时间和后果。",
        "soft": "我看到了。我今晚已经休息了，明天上班后我优先处理。",
        "firm": "我今晚不方便处理。明天上班后我会跟进；如果必须今晚完成，请明确截止时间和优先级。",
        "bad": "明明不愿意却立刻答应；或者积累怨气后，突然对同事发火。",
        "rule": "先确认真实紧急程度，再决定是否调整安排。边界不意味着拒绝所有紧急任务，而是避免默认全天候待命。"
    },
    {
        "group": "父母", "title": "父母否定你的个人选择",
        "trigger": "你想花钱学习、做 AI 项目，父母说：“你又乱花钱了，这些东西有什么用？”",
        "soft": "我知道你们担心我花钱没有结果。我会控制预算，这次想自己试一试，结果由我来承担。",
        "firm": "我会考虑你们的意见，但这笔预算和项目由我自己决定。我会控制好风险。",
        "bad": "立刻证明父母什么都不懂；或者为了不让他们失望，直接放弃自己的计划。",
        "rule": "不要把沟通变成争夺谁更聪明。解释必要的信息、守住决策权，然后用结果说话。"
    },
    {
        "group": "父母", "title": "家人用孝顺让你答应要求",
        "trigger": "家人说：“养你这么大，让你帮这点忙都不行？”但这件事会严重打乱你的计划。",
        "soft": "我知道你希望我帮忙，也不是不在乎家里。但我现在确实做不到这么多，我们看看有没有别的办法。",
        "firm": "我愿意承担自己能承担的部分，但不能因为内疚就答应所有事情。我们具体谈这次需要我做什么。",
        "bad": "“我什么都不管了！”或者为了摆脱内疚，答应超出自己能力的事。",
        "rule": "在家庭关系中，尤其需要考虑现实依赖和冲突成本。先明确自己能做多少，再讨论具体方案；不必急着把关系推向对立。"
    },
    {
        "group": "朋友", "title": "朋友向你借钱",
        "trigger": "朋友突然找你借一笔钱，但你自己的现金也不宽裕。",
        "soft": "最近我自己的预算也比较紧，这次没法借你，抱歉。希望你能找到其他办法。",
        "firm": "这笔钱我不能借，就先跟你说清楚，免得之后双方为难。",
        "bad": "怕伤感情就借出去，之后焦虑；或者嘲讽对方不会管理钱。",
        "rule": "不借超出承受范围的钱。你可以理解对方的困难，但不必用自己的财务安全来证明友情。"
    },
    {
        "group": "朋友", "title": "朋友反复临时取消约定",
        "trigger": "对方已经好几次临时取消见面，而你为此空出了时间。",
        "soft": "这次我们就改天吧。之后时间如果有变化，尽量早点告诉我，我也好安排自己的事。",
        "firm": "最近临时取消已经不止一次了，我之后就不再提前空出整段时间了。等双方时间确定再约吧。",
        "bad": "嘴上说没事，心里记账；然后突然拉黑，或发一长段指责。",
        "rule": "一次意外可以理解，反复出现的模式则值得调整。减少投入、改变安排，比惩罚对方更有效。"
    },
    {
        "group": "社交", "title": "别人拿你的家庭或出身开玩笑",
        "trigger": "饭桌上有人说：“你们农村出来的就是……”周围人跟着笑。",
        "soft": "这个说法我不太喜欢，咱们换个话题吧。",
        "firm": "你可以开玩笑，但别拿我的家庭和出身贬低我。",
        "bad": "陪笑，之后独自生气；或者立刻用对方的缺点反击，让冲突升级。",
        "rule": "不必自证自己的出身值得尊重。根据关系、场合和安全程度，先轻量制止；对方持续羞辱时，再明确边界或离开。"
    },
    {
        "group": "两性社交", "title": "约对方见面，对方说最近很忙",
        "trigger": "你提出周末见面，对方回复：“最近有点忙。”没有主动提出其他时间。",
        "soft": "好，那你先忙。之后你时间合适、也想见面的话，可以告诉我。",
        "firm": "好，那这次就先不约了。之后你想见面再告诉我。",
        "bad": "连续追问“到底忙什么”；或者讽刺“行，你忙吧”，希望对方来哄你。",
        "rule": "留出一次自然接球的空间，然后看对方是否有实际行动。尊重对方的选择，也保护自己的投入。"
    },
    {
        "group": "两性社交", "title": "对方回复很慢，你开始焦虑",
        "trigger": "对方半天没回复。你开始反复看手机，想补发消息，或故意不理对方报复。",
        "soft": "如果没有具体事情要说，就先做自己的事。等她回复后，再自然地继续聊天。",
        "firm": "如果长期都是我单方面推动，我会降低投入，把时间放回自己的生活。",
        "bad": "连发消息索取保证；故意冷落对方，让她体验自己的感受。",
        "rule": "一次延迟不代表拒绝。判断互动是否互相投入，要看一段时间的整体模式，而不是一次回复速度。"
    },
    {
        "group": "朋友与同事", "title": "别人想让你免费做一整份 AI 项目",
        "trigger": "朋友说：“你不是在学 AI 吗？顺便帮我做个小工具呗。”实际工作量可能很大。",
        "soft": "我可以跟你聊聊思路，但完整做出来需要不少时间。咱们可以先把具体需求和工作量理清楚。",
        "firm": "给你简单建议没问题，但完整开发我这次不免费接。要做的话，我们先谈清楚范围、时间和费用。",
        "bad": "为了证明自己有用，直接接下任务；或者讽刺对方只会占便宜。",
        "rule": "人情和劳动可以同时存在。先说清楚工作量，再决定免费帮忙、收费合作还是拒绝。"
    },
    {
        "group": "日常社交", "title": "大家都在做一件你不想做的事",
        "trigger": "一群朋友决定去某个地方，你其实不想去，却担心说出来会扫兴。",
        "soft": "我个人更想去 A。如果大家都想去 B，你们可以按自己的安排，我这次可能就不参加了。",
        "firm": "我这次不想去 B，你们按自己的计划走就好，我会安排别的活动。",
        "bad": "一直附和，临出门才抱怨；或者要求大家必须按自己的偏好来。",
        "rule": "表达偏好不是命令别人。你负责说明自己想要什么，对方也有选择权。"
    },
    {
        "group": "日常社交", "title": "别人追问你的收入或私事",
        "trigger": "熟人反复问你的工资、存款或恋爱情况，而你不想透露。",
        "soft": "目前还没什么特别值得说的，我暂时不太想展开，之后有合适的事情再聊。",
        "firm": "这个属于我的个人隐私，我不太想说。",
        "bad": "为了显得坦诚，把所有信息都交代出来；或者突然质问对方为什么打听。",
        "rule": "隐私不需要先证明自己有隐私的理由。你可以礼貌回答，也可以不回答。"
    },
    {
        "group": "朋友与家人", "title": "别人说你变自私了",
        "trigger": "你第一次拒绝一个要求，对方说：“你现在怎么变得这么自私？”",
        "soft": "我知道你可能不习惯我这次拒绝，但我不是不在乎你，只是这件事我确实做不到。",
        "firm": "我开始考虑自己的安排，不代表我不在乎别人。这次决定不会变。",
        "bad": "为了证明自己不自私，马上收回拒绝；或者反过来给对方扣自私的帽子。",
        "rule": "不要把是否善良交给对方的一句评价决定。检查自己的要求是否合理，再决定要不要调整。"
    },
    {
        "group": "日常社交", "title": "你犯错了，对方当面指出",
        "trigger": "同事指出你的工作失误，语气不太好。你很想立刻辩解或反击。",
        "soft": "这个问题我先确认一下。如果确实是我疏忽了，我会把它改好。",
        "firm": "工作问题可以直接指出，我们聚焦具体错误和解决办法就行。",
        "bad": "一味道歉、贬低自己；或者马上反击“你自己不也犯错？”。",
        "rule": "承认具体错误不等于否定整个人；对方语气不好，也不意味着他说的内容一定错误。"
    },
]

BG = "#F5F6F4"
CARD = "#FFFFFF"
TEXT = "#202722"
MUTED = "#68736D"
BLUE = "#416B5A"
BORDER = "#E2E7E3"
GREEN = "#416B5A"
RED = "#A34F4A"
ACCENT_LIGHT = "#EAF1ED"
FONT_FAMILY = "Microsoft YaHei UI"
FONT_BODY = (FONT_FAMILY, 14)
FONT_INPUT = (FONT_FAMILY, 15)
FONT_LABEL = (FONT_FAMILY, 14, "bold")
FONT_TITLE = (FONT_FAMILY, 25, "bold")
FONT_SCENE_TITLE = (FONT_FAMILY, 20, "bold")
FONT_REPLY = (FONT_FAMILY, 16)

class SocialReplyTrainer:
    def __init__(self, root):
        self.root = root
        self.root.title("真实社交回复训练器")
        self.root.geometry("1240x820")
        self.root.minsize(1020, 720)
        self.root.configure(bg=BG)
        saved_custom = _load_json(CUSTOM_SCENES_FILE, [])
        if not isinstance(saved_custom, list):
            saved_custom = []
        self.custom_scenes = [s for s in saved_custom if isinstance(s, dict) and all(k in s for k in ("group", "title", "trigger", "soft", "firm", "bad", "rule"))]
        self.scenes = list(SCENES) + self.custom_scenes
        self.settings = _load_json(SETTINGS_FILE, {})
        if not isinstance(self.settings, dict):
            self.settings = {}
        self.selected_index = 0
        self.tone = tk.StringVar(value="soft")
        self.category = tk.StringVar(value="全部场景")
        self.show_analysis = False
        self.show_answer = True
        self._setup_styles()
        self._build_ui()
        self._refresh_scene_list()
        self._select_scene(0)

    def _setup_styles(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TFrame", background=BG)
        style.configure("Card.TFrame", background=CARD)
        style.configure("TLabel", background=BG, foreground=TEXT, font=FONT_BODY)
        style.configure("Muted.TLabel", background=BG, foreground=MUTED, font=FONT_BODY)
        style.configure("Title.TLabel", background=BG, foreground=TEXT, font=FONT_TITLE)
        style.configure("SubTitle.TLabel", background=BG, foreground=MUTED, font=FONT_BODY)
        style.configure("CardTitle.TLabel", background=CARD, foreground=TEXT, font=FONT_LABEL)
        style.configure("Field.TLabel", background=BG, foreground=TEXT, font=FONT_LABEL)
        style.configure("CardText.TLabel", background=CARD, foreground=TEXT, font=FONT_BODY, wraplength=760, justify="left")
        style.configure("TButton", font=FONT_BODY, padding=(16, 11), borderwidth=0)
        style.map("TButton", background=[("active", "#EDF1EE")])
        style.configure("Accent.TButton", background=BLUE, foreground="white", font=FONT_LABEL, borderwidth=0, padding=(18, 12))
        style.map("Accent.TButton", background=[("active", "#355948"), ("pressed", "#2D4D3F")])
        style.configure("Soft.TButton", background=ACCENT_LIGHT, foreground=BLUE, borderwidth=0, padding=(16, 11))
        style.map("Soft.TButton", background=[("active", "#DDE9E1")])
        style.configure("TCombobox", padding=8, font=FONT_BODY, fieldbackground=CARD, foreground=TEXT, arrowsize=16)
        style.configure("TEntry", padding=8, font=FONT_INPUT, fieldbackground=CARD, foreground=TEXT)
        style.configure("TCheckbutton", background=BG, foreground=TEXT, font=FONT_BODY)
        style.configure("TRadiobutton", background=CARD, foreground=TEXT, font=FONT_BODY)
        style.configure("TSeparator", background=BORDER)

    def _build_ui(self):
        outer = ttk.Frame(self.root, padding=(30, 26, 30, 20))
        outer.pack(fill="both", expand=True)

        header = ttk.Frame(outer)
        header.pack(fill="x", pady=(0, 23))
        title_block = ttk.Frame(header)
        title_block.pack(side="left", fill="x", expand=True)
        ttk.Label(title_block, text="真实社交回复训练器", style="Title.TLabel").pack(anchor="w")
        ttk.Label(title_block, text="不讨好，不攻击。练习清晰表达，也尊重彼此。", style="SubTitle.TLabel").pack(anchor="w", pady=(4, 0))
        header_actions = ttk.Frame(header)
        header_actions.pack(side="right", anchor="e", pady=(7, 0))
        ttk.Button(header_actions, text="＋ 新增场景 / AI 生成", style="Accent.TButton", command=self._open_add_scene).pack(side="left", padx=(0, 8))
        ttk.Button(header_actions, text="API 设置", command=self._open_api_settings).pack(side="left")

        body = ttk.Frame(outer)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=0, minsize=255)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        sidebar = tk.Frame(body, bg=CARD, highlightbackground=BORDER, highlightthickness=1, width=255)
        sidebar.grid(row=0, column=0, sticky="nsew", padx=(0, 15))
        sidebar.grid_propagate(False)
        tk.Label(sidebar, text="选择训练场景", bg=CARD, fg=TEXT, font=FONT_LABEL).pack(anchor="w", padx=17, pady=(19, 12))
        self.category_combo = ttk.Combobox(sidebar, textvariable=self.category, state="readonly", values=["全部场景"] + sorted({s["group"] for s in self.scenes}), width=22)
        self.category_combo.pack(fill="x", padx=13, pady=(0, 10))
        self.category_combo.bind("<<ComboboxSelected>>", lambda _e: self._refresh_scene_list())
        list_wrap = tk.Frame(sidebar, bg=CARD)
        list_wrap.pack(fill="both", expand=True, padx=(10, 6), pady=(0, 9))
        self.scene_list = tk.Listbox(list_wrap, activestyle="none", selectmode="single", relief="flat", borderwidth=0,
                                     bg=CARD, fg=TEXT, selectbackground=ACCENT_LIGHT, selectforeground=BLUE,
                                     font=FONT_BODY, highlightthickness=0,
                                     yscrollcommand=None, exportselection=False)
        scrollbar = ttk.Scrollbar(list_wrap, orient="vertical", command=self.scene_list.yview)
        self.scene_list.configure(yscrollcommand=scrollbar.set)
        self.scene_list.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.scene_list.bind("<<ListboxSelect>>", self._on_scene_select)
        tk.Label(sidebar, text="先看情景，再选择一种回复风格。", bg=CARD, fg=MUTED, font=FONT_BODY, wraplength=230, justify="left").pack(anchor="w", padx=17, pady=(0, 17))

        self.content = ttk.Frame(body)
        self.content.grid(row=0, column=1, sticky="nsew")
        self.content.columnconfigure(0, weight=1)
        self.content.rowconfigure(4, weight=1)

        self.scene_heading = ttk.Frame(self.content)
        self.scene_heading.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        self.category_badge = tk.Label(self.scene_heading, text="同事", bg=ACCENT_LIGHT, fg=BLUE, font=(FONT_FAMILY, 12, "bold"), padx=11, pady=5)
        self.category_badge.pack(side="left", padx=(0, 10))
        self.scene_title = tk.Label(self.scene_heading, text="场景标题", bg=BG, fg=TEXT, font=FONT_SCENE_TITLE, anchor="w", justify="left", wraplength=760)
        self.scene_title.pack(side="left", fill="x", expand=True)

        self._card_label(self.content, "情景还原", 1, pady=(0, 6))
        self.situation_card = tk.Frame(self.content, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
        self.situation_card.grid(row=2, column=0, sticky="ew", pady=(0, 13))
        self.situation_label = tk.Label(self.situation_card, text="", bg=CARD, fg=TEXT, font=FONT_BODY, justify="left", anchor="w", wraplength=760, padx=19, pady=18)
        self.situation_label.pack(fill="x")

        response_head = ttk.Frame(self.content)
        response_head.grid(row=3, column=0, sticky="ew", pady=(0, 7))
        ttk.Label(response_head, text="推荐回复", style="CardTitle.TLabel").pack(side="left")
        self.tone_frame = tk.Frame(response_head, bg=BG)
        self.tone_frame.pack(side="right")
        self.soft_btn = tk.Radiobutton(self.tone_frame, text="温和但清晰", value="soft", variable=self.tone, command=self._update_reply,
                                       indicatoron=False, selectcolor=ACCENT_LIGHT, bg=BG, fg=MUTED, activebackground=BG,
                                       font=FONT_BODY, padx=14, pady=9, bd=0, highlightthickness=0)
        self.soft_btn.pack(side="left", padx=(0, 4))
        self.firm_btn = tk.Radiobutton(self.tone_frame, text="坚定直接", value="firm", variable=self.tone, command=self._update_reply,
                                       indicatoron=False, selectcolor=ACCENT_LIGHT, bg=BG, fg=MUTED, activebackground=BG,
                                       font=FONT_BODY, padx=14, pady=9, bd=0, highlightthickness=0)
        self.firm_btn.pack(side="left")

        self.reply_card = tk.Frame(self.content, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
        self.reply_card.grid(row=4, column=0, sticky="nsew", pady=(0, 10))
        self.reply_card.rowconfigure(0, weight=1)
        self.reply_card.columnconfigure(0, weight=1)
        self.reply_text = tk.Text(self.reply_card, height=5, wrap="word", relief="flat", bd=0, bg=CARD, fg=TEXT,
                                  font=FONT_REPLY, padx=22, pady=20, spacing1=5, spacing3=6,
                                  selectbackground="#DCE9E2", selectforeground=TEXT)
        self.reply_text.grid(row=0, column=0, sticky="nsew")
        self.reply_text.configure(state="disabled")

        buttons = ttk.Frame(self.content)
        buttons.grid(row=5, column=0, sticky="ew", pady=(0, 10))
        self.copy_btn = ttk.Button(buttons, text="复制推荐回复", style="Accent.TButton", command=self._copy_reply)
        self.copy_btn.pack(side="left")
        self.analysis_btn = ttk.Button(buttons, text="为什么这样回复？", style="Soft.TButton", command=self._toggle_analysis)
        self.analysis_btn.pack(side="left", padx=(8, 0))
        self.practice_btn = ttk.Button(buttons, text="先自己练一句 ↓", command=self._toggle_practice)
        self.practice_btn.pack(side="right")

        self.analysis_frame = tk.Frame(self.content, bg="#F0F5F1", highlightbackground="#DCE7E0", highlightthickness=1)
        self.analysis_frame.grid(row=6, column=0, sticky="ew", pady=(0, 10))
        self.analysis_frame.columnconfigure(0, weight=1)
        self.rule_title = tk.Label(self.analysis_frame, text="这句话的核心逻辑", bg="#F0F5F1", fg=GREEN, font=FONT_LABEL, anchor="w")
        self.rule_title.pack(fill="x", padx=13, pady=(11, 4))
        self.rule_label = tk.Label(self.analysis_frame, text="", bg="#F0F5F1", fg=TEXT, font=FONT_BODY, justify="left", anchor="w", wraplength=760)
        self.rule_label.pack(fill="x", padx=13, pady=(0, 9))
        tk.Frame(self.analysis_frame, bg="#DCE7E0", height=1).pack(fill="x", padx=13, pady=1)
        tk.Label(self.analysis_frame, text="尽量避免", bg="#F0F5F1", fg=RED, font=FONT_LABEL, anchor="w").pack(fill="x", padx=13, pady=(8, 4))
        self.bad_label = tk.Label(self.analysis_frame, text="", bg="#F0F5F1", fg=TEXT, font=FONT_BODY, justify="left", anchor="w", wraplength=760)
        self.bad_label.pack(fill="x", padx=13, pady=(0, 12))
        self.analysis_frame.grid_remove()

        self.practice_frame = tk.Frame(self.content, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
        self.practice_frame.grid(row=7, column=0, sticky="ew", pady=(0, 8))
        tk.Label(self.practice_frame, text="先自己写一句（可选）", bg=CARD, fg=TEXT, font=FONT_LABEL, anchor="w").pack(fill="x", padx=16, pady=(14, 6))
        tk.Label(self.practice_frame, text="不用追求完美。先写出你第一反应想说的话，再对照推荐回复。", bg=CARD, fg=MUTED, font=FONT_BODY, anchor="w", justify="left", wraplength=760).pack(fill="x", padx=16, pady=(0, 9))
        self.practice_text = tk.Text(self.practice_frame, height=3, wrap="word", relief="solid", bd=1, bg="#FBFCFE", fg=TEXT,
                                     font=FONT_INPUT, padx=13, pady=12, undo=True)
        self.practice_text.pack(fill="x", padx=16, pady=(0, 10))
        practice_actions = tk.Frame(self.practice_frame, bg=CARD)
        practice_actions.pack(fill="x", padx=13, pady=(0, 11))
        ttk.Button(practice_actions, text="清空练习", command=self._clear_practice).pack(side="left")
        ttk.Button(practice_actions, text="复制我的回复", command=self._copy_practice).pack(side="left", padx=(7, 0))
        self.practice_frame.grid_remove()

        footer = ttk.Frame(outer)
        footer.pack(fill="x", pady=(10, 0))
        self.status_label = ttk.Label(footer, text="练习目标：表达清楚，而不是让每个人都满意。", style="Muted.TLabel")
        self.status_label.pack(side="left")
        ttk.Label(footer, text="AI 生成需要网络和 DeepSeek API 密钥", style="Muted.TLabel").pack(side="right")

    def _card_label(self, parent, text, row, pady=(0, 0)):
        label = ttk.Label(parent, text=text, style="CardTitle.TLabel")
        label.grid(row=row, column=0, sticky="w", pady=pady)
        return label

    def _refresh_scene_list(self):
        current = self.selected_index
        chosen = self.category.get()
        self.visible_indices = [i for i, s in enumerate(self.scenes) if chosen == "全部场景" or s["group"] == chosen]
        self.scene_list.delete(0, tk.END)
        for idx in self.visible_indices:
            s = self.scenes[idx]
            self.scene_list.insert(tk.END, f"{s['group']}  ·  {s['title']}")
        if current not in self.visible_indices:
            current = self.visible_indices[0] if self.visible_indices else 0
        if self.visible_indices:
            self._select_scene(current)

    def _on_scene_select(self, _event=None):
        selection = self.scene_list.curselection()
        if not selection:
            return
        pos = selection[0]
        if pos < len(self.visible_indices):
            self._select_scene(self.visible_indices[pos])

    def _select_scene(self, index):
        self.selected_index = index
        s = self.scenes[index]
        self.category_badge.configure(text=s["group"])
        self.scene_title.configure(text=s["title"])
        self.situation_label.configure(text=s["trigger"])
        if index in self.visible_indices:
            pos = self.visible_indices.index(index)
            self.scene_list.selection_clear(0, tk.END)
            self.scene_list.selection_set(pos)
            self.scene_list.see(pos)
        self._update_reply()
        self._update_analysis()
        self.practice_text.delete("1.0", tk.END)
        self.status_label.configure(text=f"当前场景：{index + 1}/{len(self.scenes)}  ·  练习目标：表达清楚，而不是让每个人都满意。")

    def _update_reply(self):
        s = self.scenes[self.selected_index]
        reply = s[self.tone.get()]
        self.reply_text.configure(state="normal")
        self.reply_text.delete("1.0", tk.END)
        self.reply_text.insert("1.0", reply)
        self.reply_text.configure(state="disabled")
        self.soft_btn.configure(fg=BLUE if self.tone.get() == "soft" else MUTED, font=(FONT_FAMILY, 14, "bold" if self.tone.get() == "soft" else "normal"))
        self.firm_btn.configure(fg=BLUE if self.tone.get() == "firm" else MUTED, font=(FONT_FAMILY, 14, "bold" if self.tone.get() == "firm" else "normal"))

    def _update_analysis(self):
        s = self.scenes[self.selected_index]
        self.rule_label.configure(text=s["rule"])
        self.bad_label.configure(text=s["bad"])

    def _open_api_settings(self):
        win = tk.Toplevel(self.root)
        win.title("DeepSeek API 设置")
        win.transient(self.root)
        win.grab_set()
        win.configure(bg=BG)
        win.geometry("720x440")
        win.minsize(680, 410)

        outer = ttk.Frame(win, padding=28)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="连接 DeepSeek", style="Title.TLabel").pack(anchor="w")
        ttk.Label(outer, text="密钥只保存在这台电脑的用户配置目录，不会写入程序或 ZIP 压缩包。", style="SubTitle.TLabel", wraplength=650).pack(anchor="w", pady=(7, 20))

        ttk.Label(outer, text="API 密钥", style="CardTitle.TLabel").pack(anchor="w", pady=(0, 5))
        key_var = tk.StringVar(value=self.settings.get("api_key", ""))
        key_entry = ttk.Entry(outer, textvariable=key_var, show="•", font=FONT_INPUT)
        key_entry.pack(fill="x", ipady=7)
        show_var = tk.BooleanVar(value=False)
        def toggle_key():
            key_entry.configure(show="" if show_var.get() else "•")
        ttk.Checkbutton(outer, text="显示密钥", variable=show_var, command=toggle_key).pack(anchor="w", pady=(6, 15))

        ttk.Label(outer, text="模型名称", style="CardTitle.TLabel").pack(anchor="w", pady=(0, 5))
        model_var = tk.StringVar(value=self.settings.get("model", DEFAULT_MODEL))
        model_entry = ttk.Entry(outer, textvariable=model_var, font=FONT_INPUT)
        model_entry.pack(fill="x", ipady=6)
        ttk.Label(outer, text="默认使用 deepseek-flash。API 调用会产生费用，请在 DeepSeek 控制台查看余额与价格。", style="Muted.TLabel", wraplength=630).pack(anchor="w", pady=(8, 12))

        actions = ttk.Frame(outer)
        actions.pack(fill="x", side="bottom")
        def save_settings():
            key = key_var.get().strip()
            model = model_var.get().strip() or DEFAULT_MODEL
            if not key:
                if not messagebox.askyesno("确认清除密钥", "密钥为空。保存后将清除本机已保存的 API 密钥，确定继续吗？", parent=win):
                    return
            self.settings["api_key"] = key
            self.settings["model"] = model
            try:
                _save_json(SETTINGS_FILE, self.settings)
            except OSError as e:
                messagebox.showerror("保存失败", f"无法保存设置：{e}", parent=win)
                return
            self.status_label.configure(text="DeepSeek API 设置已保存到本机。")
            win.destroy()
        ttk.Button(actions, text="保存设置", style="Accent.TButton", command=save_settings).pack(side="right")
        ttk.Button(actions, text="取消", command=win.destroy).pack(side="right", padx=(0, 8))
        key_entry.focus_set()

    def _open_add_scene(self):
        win = tk.Toplevel(self.root)
        win.title("新增社交场景 · AI 生成合理回复")
        win.transient(self.root)
        win.grab_set()
        win.configure(bg=BG)
        win.geometry("900x720")
        win.minsize(820, 650)

        outer = ttk.Frame(win, padding=(30, 27, 30, 24))
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="新增社交场景", style="Title.TLabel").pack(anchor="w")
        ttk.Label(outer, text="写清楚发生了什么、你和对方是什么关系，以及你担心什么。AI 会生成两种回复和沟通分析。", style="SubTitle.TLabel", wraplength=830).pack(anchor="w", pady=(8, 20))

        form = ttk.Frame(outer)
        form.pack(fill="both", expand=True)
        form.columnconfigure(1, weight=1)
        ttk.Label(form, text="场景分类", style="Field.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 16), pady=(0, 13))
        group_var = tk.StringVar(value="日常社交")
        group_combo = ttk.Combobox(form, textvariable=group_var, values=["同事", "工作", "父母", "朋友", "社交", "两性社交", "日常社交", "朋友与同事", "朋友与家人", "自定义"], width=18, font=FONT_INPUT)
        group_combo.grid(row=0, column=1, sticky="ew", pady=(0, 13), ipady=4)

        ttk.Label(form, text="场景标题", style="Field.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 16), pady=(0, 13))
        title_var = tk.StringVar()
        title_entry = ttk.Entry(form, textvariable=title_var, font=FONT_INPUT)
        title_entry.grid(row=1, column=1, sticky="ew", pady=(0, 13), ipady=6)

        ttk.Label(form, text="具体情景", style="Field.TLabel").grid(row=2, column=0, sticky="nw", padx=(0, 16), pady=(0, 13))
        situation = tk.Text(form, height=10, wrap="word", font=FONT_INPUT, bg=CARD, fg=TEXT, insertbackground=BLUE, relief="flat", bd=0, padx=14, pady=12, undo=True, highlightthickness=1, highlightbackground=BORDER, highlightcolor=BLUE)
        situation.grid(row=2, column=1, sticky="nsew", pady=(0, 13))
        form.rowconfigure(2, weight=1)
        situation.insert("1.0", "例如：对方说了什么？你原本想怎么回应？你担心什么后果？")

        ttk.Label(form, text="额外要求（可选）", style="Field.TLabel").grid(row=3, column=0, sticky="nw", padx=(0, 16), pady=(0, 13))
        extra = tk.Text(form, height=3, wrap="word", font=FONT_INPUT, bg=CARD, fg=TEXT, insertbackground=BLUE, relief="flat", bd=0, padx=14, pady=12, undo=True, highlightthickness=1, highlightbackground=BORDER, highlightcolor=BLUE)
        extra.grid(row=3, column=1, sticky="ew", pady=(0, 13))
        extra.insert("1.0", "例如：不想把关系闹僵；考虑对方是我的上级；回复不要太长。")

        status = ttk.Label(outer, text="提示：首次使用前，请点击主窗口的“API 设置”填入新的 DeepSeek API 密钥。", style="Muted.TLabel", wraplength=830)
        status.pack(anchor="w", pady=(8, 13))

        actions = ttk.Frame(outer)
        actions.pack(fill="x")
        generate_btn = ttk.Button(actions, text="AI 生成并添加场景", style="Accent.TButton")
        generate_btn.pack(side="right")
        ttk.Button(actions, text="取消", command=win.destroy).pack(side="right", padx=(0, 8))

        def on_generate():
            key = self.settings.get("api_key", "").strip()
            model = self.settings.get("model", DEFAULT_MODEL).strip() or DEFAULT_MODEL
            title = title_var.get().strip()
            group = group_var.get().strip() or "日常社交"
            trigger = situation.get("1.0", "end-1c").strip()
            extra_notes = extra.get("1.0", "end-1c").strip()
            if extra_notes.startswith("例如："):
                extra_notes = ""
            if not key:
                messagebox.showwarning("尚未设置 API 密钥", "请先关闭此窗口，点击主窗口右上角“API 设置”，填入新建的 DeepSeek API 密钥。", parent=win)
                return
            if not title:
                messagebox.showwarning("请填写标题", "给这个社交情景起一个简短标题。", parent=win)
                title_entry.focus_set()
                return
            if not trigger or trigger.startswith("例如："):
                messagebox.showwarning("请填写具体情景", "请把示例提示替换成你真实遇到的情况。", parent=win)
                situation.focus_set()
                return
            generate_btn.configure(state="disabled", text="正在请求 AI…")
            status.configure(text="正在向 DeepSeek 请求回复，通常需要几秒钟。请不要关闭窗口。")

            def worker():
                try:
                    result = self._request_ai_replies(key, model, group, title, trigger, extra_notes)
                    self.root.after(0, lambda: on_success(result, group, title, trigger))
                except Exception as e:
                    err = str(e)
                    self.root.after(0, lambda err=err: on_error(err))

            def on_success(result, group, title, trigger):
                scene = {
                    "group": group,
                    "title": title,
                    "trigger": trigger,
                    "soft": result["soft"],
                    "firm": result["firm"],
                    "bad": result["bad"],
                    "rule": result["rule"]
                }
                self.custom_scenes.append(scene)
                try:
                    _save_json(CUSTOM_SCENES_FILE, self.custom_scenes)
                except OSError as e:
                    self.custom_scenes.pop()
                    messagebox.showerror("保存失败", f"AI 已生成回复，但无法保存到本机：{e}", parent=win)
                    generate_btn.configure(state="normal", text="AI 生成并添加场景")
                    status.configure(text="请检查本机文件权限后重试。")
                    return
                self.scenes.append(scene)
                self.category.set("全部场景")
                self.category_combo.configure(values=["全部场景"] + sorted({s["group"] for s in self.scenes}))
                self._refresh_scene_list()
                new_index = len(self.scenes) - 1
                self._select_scene(new_index)
                self.status_label.configure(text=f"AI 已生成并保存新场景：{title}")
                messagebox.showinfo("添加成功", "AI 已生成两种回复和沟通分析，新场景已保存到本机。下次启动仍会保留。", parent=win)
                win.destroy()

            def on_error(err):
                generate_btn.configure(state="normal", text="重新生成")
                status.configure(text="生成失败。请检查 API 设置、网络和 DeepSeek 账户余额。")
                messagebox.showerror("AI 生成失败", err, parent=win)

            threading.Thread(target=worker, daemon=True).start()

        generate_btn.configure(command=on_generate)
        title_entry.focus_set()

    def _request_ai_replies(self, api_key, model, group, title, trigger, extra_notes):
        user_content = (
            f"请为以下真实社交情景生成适当的沟通回复。\n\n"
            f"分类：{group}\n场景标题：{title}\n具体情景：{trigger}\n"
            f"用户的额外要求：{extra_notes or '无'}\n\n"
            "请按系统要求只返回 JSON。回复必须自然、简洁、可直接说出口。"
        )
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content}
            ],
            "stream": False,
            "thinking": {"type": "disabled"},
            "response_format": {"type": "json_object"},
            "temperature": 0.7,
            "max_tokens": 1800
        }
        request = urllib.request.Request(
            API_URL,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": "Bearer " + api_key},
            method="POST"
        )
        try:
            with urllib.request.urlopen(request, timeout=75) as response:
                response_data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            try:
                details = e.read().decode("utf-8", errors="replace")
                parsed = json.loads(details)
                details = parsed.get("error", {}).get("message", details)
            except Exception:
                details = str(e)
            if e.code == 401:
                raise RuntimeError("API 密钥无效或已失效（401）。请在 DeepSeek 控制台创建新密钥，再到程序的“API 设置”里更新。")
            if e.code == 402:
                raise RuntimeError("DeepSeek 账户余额不足或账户状态不允许调用（402）。请检查控制台余额和服务状态。")
            if e.code == 429:
                raise RuntimeError("请求过于频繁或触发额度限制（429）。稍后重试，并检查账户限额。")
            raise RuntimeError(f"DeepSeek API 返回 HTTP {e.code}：{details}")
        except urllib.error.URLError as e:
            raise RuntimeError(f"无法连接 DeepSeek API：{e.reason}\n请检查网络连接。")
        except TimeoutError:
            raise RuntimeError("请求超时。请检查网络后重试。")
        try:
            content = response_data["choices"][0]["message"]["content"]
            result = json.loads(content)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as e:
            raise RuntimeError(f"AI 返回格式无法识别，请重新生成。详细信息：{e}")
        required = ("soft", "firm", "bad", "rule")
        if not isinstance(result, dict) or any(not isinstance(result.get(k), str) or not result[k].strip() for k in required):
            raise RuntimeError("AI 返回的数据缺少必要字段。请点击重新生成再试一次。")
        return {k: result[k].strip() for k in required}

    def _copy_reply(self):
        text = self.scenes[self.selected_index][self.tone.get()]
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.status_label.configure(text="已复制推荐回复，可以直接粘贴使用。")

    def _toggle_analysis(self):
        self.show_analysis = not self.show_analysis
        if self.show_analysis:
            # Keep the page compact: show either the analysis or practice section at once.
            if self.show_answer:
                self.show_answer = False
                self.practice_frame.grid_remove()
                self.practice_btn.configure(text="先自己练一句 ↓")
            self.analysis_frame.grid()
            self.analysis_btn.configure(text="收起分析 ↑")
        else:
            self.analysis_frame.grid_remove()
            self.analysis_btn.configure(text="为什么这样回复？")

    def _toggle_practice(self):
        self.show_answer = not self.show_answer
        if self.show_answer:
            # Keep the page compact: show either the analysis or practice section at once.
            if self.show_analysis:
                self.show_analysis = False
                self.analysis_frame.grid_remove()
                self.analysis_btn.configure(text="为什么这样回复？")
            self.practice_frame.grid()
            self.practice_btn.configure(text="收起练习 ↑")
            self.practice_text.focus_set()
        else:
            self.practice_frame.grid_remove()
            self.practice_btn.configure(text="先自己练一句 ↓")

    def _clear_practice(self):
        self.practice_text.delete("1.0", tk.END)
        self.status_label.configure(text="练习区已清空。再试一次，写出你更愿意说出口的版本。")

    def _copy_practice(self):
        text = self.practice_text.get("1.0", "end-1c").strip()
        if not text:
            messagebox.showinfo("还没有内容", "先在练习区写一句自己的回复，再复制。")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.status_label.configure(text="已复制你的练习回复。")


def main():
    root = tk.Tk()
    SocialReplyTrainer(root)
    # Windows 下启动时最大化，给更大的字体和换行内容留出空间。
    try:
        root.state("zoomed")
    except tk.TclError:
        pass
    root.mainloop()

if __name__ == "__main__":
    main()
